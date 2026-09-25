// ============================================================================
// Contesto del segnale (cruscotto Direzione) - FREQUENZA e RITARDO allo STATO
// ATTUALE per la lega + il mercato di un segnale.
//
// FREQUENZA: dalla serie binaria di get_market_frequency (un punto per partita
// SETTLATA, esito 0/1; esclude le partite senza HT dai mercati HT).
//
// RITARDO (25/09/2026, reperto R7): si calcola in UN posto solo, la RPC
// get_market_delays (quella della tab Studio Ritardi), con UNA regola: le partite
// senza dato di primo tempo si ESCLUDONO dai mercati HT (non sono 0-0), i mercati FT
// sono invariati (migrations/market_delays_ht_2026-09-25.sql). Prima il cruscotto
// ricalcolava il ritardo nel browser dalla serie di frequenza con formule proprie
// (media dei gap, record sulla corsa aperta) e la tab Ritardi contava l'HT
// mancante come 0-0: due numeri diversi per lo stesso mercato. Ora il cruscotto
// mostra ESATTAMENTE i valori della tab (ritardo attuale, record, media storica,
// ritardo/media) per la stessa lega, lo stesso mercato e tutto lo storico.
// Se la RPC deployata non ha ancora la regola HT (meta.ht_missing_rule assente),
// su un mercato HT il ritardo NON si mostra (sarebbe gonfiato dagli 0-0 finti).
// Caricato pigro: solo quando l'utente espande un mercato.
// ============================================================================
import { fetchMarketFrequency } from './marketFrequency';
import { fetchMarketDelays, type DelayResult } from './marketDelays';

const SEL3: Record<string, string> = { H: '1', D: 'X', A: '2' };

// NB: `dir` e' SEMPRE il codice selezione esatto del cruscotto (H/D/A/Over/Under/Yes/No),
// fissato dalla mappa VALUES della RPC get_direction (confronti case-sensitive corretti per contratto).

// cruscotto (market, direction) -> parametri get_market_frequency (copre TUTTI i 7 mercati)
function freqMap(market: string, dir: string): { market: string; selection: string; line: number | null } | null {
    if (market === '1x2') return SEL3[dir] ? { market: '1x2', selection: SEL3[dir], line: null } : null;
    if (market === 'ht_1x2') return SEL3[dir] ? { market: '1x2_ht', selection: SEL3[dir], line: null } : null;
    if (market === 'btts') return { market: 'btts', selection: dir === 'Yes' ? 'yes' : 'no', line: null };
    if (market === 'over_1_5') return { market: 'ou_ft', selection: dir.toLowerCase(), line: 1.5 };
    if (market === 'over_2_5') return { market: 'ou_ft', selection: dir.toLowerCase(), line: 2.5 };
    if (market === 'over_3_5') return { market: 'ou_ft', selection: dir.toLowerCase(), line: 3.5 };
    if (market === 'first_half_over_0_5') return { market: 'ou_ht', selection: dir.toLowerCase(), line: 0.5 };
    return null;
}

// cruscotto (market, direction) -> parametri get_market_delays (copre TUTTI i 7 mercati;
// i codici 1/2/gg/ng/unpt/pt1/ptx/pt2 sono quelli aggiunti dalla migrazione del 25/09).
const DELAY_1X2: Record<string, string> = { H: '1', D: 'x', A: '2' };
const DELAY_HT_1X2: Record<string, string> = { H: 'pt1', D: 'ptx', A: 'pt2' };
const OU_LINE: Record<string, string> = { over_1_5: '1.5', over_2_5: '2.5', over_3_5: '3.5' };

export function delayMap(market: string, dir: string): { market: string; target: string | null } | null {
    if (market === '1x2') return DELAY_1X2[dir] ? { market: DELAY_1X2[dir], target: null } : null;
    if (market === 'ht_1x2') return DELAY_HT_1X2[dir] ? { market: DELAY_HT_1X2[dir], target: null } : null;
    if (market === 'btts') {
        if (dir === 'Yes') return { market: 'gg', target: null };
        if (dir === 'No') return { market: 'ng', target: null };
        return null;
    }
    if (OU_LINE[market]) {
        if (dir === 'Over') return { market: 'over', target: OU_LINE[market] };
        if (dir === 'Under') return { market: 'under', target: OU_LINE[market] };
        return null;
    }
    if (market === 'first_half_over_0_5') {
        if (dir === 'Over') return { market: 'ovpt', target: '0.5' };
        if (dir === 'Under') return { market: 'unpt', target: '0.5' };
        return null;
    }
    return null;
}

export interface SignalDelay {
    current: number;             // ritardo attuale (= stats.ritardo_attuale della tab)
    media: number | null;        // media storica "ogni N partite" (= stats.media_storica)
    record: number;              // serie storica massima (= stats.record)
    ratio: number | null;        // ritardo / media storica (= stats.rit_vs_media)
    n: number;                   // eventi della serie (= meta.n_effective)
    n_ht_missing: number;        // partite escluse perche' senza HT (0 sui mercati FT)
}

export interface SignalContext {
    freq: { current: number | null; baseline: number | null; z: number | null; n: number } | null;
    delay: SignalDelay | null;
    delayNote: string | null;    // perche' il ritardo manca (se manca per un motivo noto)
    available: boolean;          // il mercato e' mappabile su una serie di frequenza
}

export const NOTA_REGOLA_HT_MANCANTE =
    'ritardo non mostrato: la RPC get_market_delays sul DB non ha ancora la regola HT ' +
    '(conta come 0-0 le partite senza primo tempo). Da applicare: migrations/market_delays_ht_2026-09-25.sql';

/** Estrae il ritardo dal risultato della RPC (pura). null + nota se la RPC deployata
 *  non ha la regola HT e il mercato usa il primo tempo. */
export function delayFromResult(r: DelayResult): { delay: SignalDelay | null; note: string | null } {
    if (r.meta.uses_ht && r.meta.ht_missing_rule !== 'escluse') {
        return { delay: null, note: NOTA_REGOLA_HT_MANCANTE };
    }
    return {
        delay: {
            current: r.stats.ritardo_attuale,
            media: r.stats.media_storica,
            record: r.stats.record,
            ratio: r.stats.rit_vs_media,
            n: r.meta.n_effective,
            n_ht_missing: r.meta.n_ht_missing ?? 0,
        },
        note: null,
    };
}

export async function fetchSignalContext(leagueId: number, market: string, dir: string): Promise<SignalContext> {
    const fm = freqMap(market, dir);
    const dm = delayMap(market, dir);
    const out: SignalContext = { freq: null, delay: null, delayNote: null, available: !!fm };
    await Promise.all([
        (async () => {
            if (!fm) return;
            try {
                // mode 'all' = tutta la storia settlata della lega.
                const fs = await fetchMarketFrequency({
                    leagueId, market: fm.market, selection: fm.selection, line: fm.line, mode: 'all',
                });
                const pts = fs.points || [];
                const last = pts.length ? pts[pts.length - 1] : null;
                out.freq = {
                    current: last?.mm10 ?? last?.mm5 ?? null,
                    baseline: fs.meta.baseline,
                    z: last?.z ?? null,
                    n: fs.meta.n_effective,
                };
            } catch { /* lascia null: mostrato come non disponibile */ }
        })(),
        (async () => {
            if (!dm) return;
            try {
                // stessa RPC, stessi parametri e stesso intervallo (tutto lo storico)
                // della tab Studio Ritardi: stesso numero.
                const r = await fetchMarketDelays({ leagueId, market: dm.market, target: dm.target, mode: 'all' });
                const { delay, note } = delayFromResult(r);
                out.delay = delay;
                out.delayNote = note;
            } catch { /* lascia null: mostrato come non disponibile */ }
        })(),
    ]);
    return out;
}
