// ============================================================================
// Contesto del segnale (cruscotto Direzione) — FREQUENZA e RITARDO allo STATO
// ATTUALE per la lega + il mercato di un segnale. Riusa le RPC esistenti
// get_market_frequency / get_market_delays mappando i mercati del cruscotto
// (1x2, over_2_5, btts, ...) sui codici di quelle RPC (che hanno tassonomie diverse).
// Caricato pigro: solo quando l'utente espande un mercato.
// ============================================================================
import { fetchMarketFrequency } from './marketFrequency';
import { fetchMarketDelays } from './marketDelays';

const SEL3: Record<string, string> = { H: '1', D: 'X', A: '2' };

// NB: `dir` e' SEMPRE il codice selezione esatto del cruscotto (H/D/A/Over/Under/Yes/No),
// fissato dalla mappa VALUES della RPC get_direction. I confronti case-sensitive qui sotto
// sono quindi corretti per contratto (certificato: 8/8 ritardi mappati, 0 errori).

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

// cruscotto (market, direction) -> parametri get_market_delays (catalogo ritardi: PARZIALE)
function delayMap(market: string, dir: string): { market: string; target: string | null } | null {
    // Invariante: solo i mercati 'over_N_5' arrivano qui -> split produce "N.5".
    if (['over_1_5', 'over_2_5', 'over_3_5'].includes(market)) {
        const target = market.split('_').slice(1).join('.'); // over_2_5 -> "2.5"
        return { market: dir === 'Over' ? 'over' : 'under', target };
    }
    if (market === 'first_half_over_0_5' && dir === 'Over') return { market: 'ovpt', target: '0.5' };
    if (market === '1x2' && dir === 'D') return { market: 'x', target: null }; // Pareggio
    return null; // 1x2 H/A, ht_1x2, btts, first_half Under: nessun mercato-ritardo pulito
}

export interface SignalContext {
    freq: { current: number | null; baseline: number | null; z: number | null; n: number } | null;
    delay: { current: number | null; media: number | null; record: number | null; ratio: number | null } | null;
    freqAvailable: boolean;
    delayAvailable: boolean;
}

export async function fetchSignalContext(leagueId: number, market: string, dir: string): Promise<SignalContext> {
    const fm = freqMap(market, dir);
    const dm = delayMap(market, dir);
    const out: SignalContext = { freq: null, delay: null, freqAvailable: !!fm, delayAvailable: !!dm };

    if (fm) {
        try {
            const fs = await fetchMarketFrequency({
                leagueId, market: fm.market, selection: fm.selection, line: fm.line, mode: 'last_n', lastN: 300,
            });
            const pts = fs.points || [];
            const last = pts.length ? pts[pts.length - 1] : null;
            out.freq = {
                current: last?.mm10 ?? last?.mm5 ?? null,
                baseline: fs.meta.baseline,
                z: last?.z ?? null,
                n: fs.meta.n_effective,
            };
        } catch { /* lascia freq=null: mostrato come non disponibile */ }
    }
    if (dm) {
        try {
            const dr = await fetchMarketDelays({ leagueId, market: dm.market, target: dm.target, mode: 'all' });
            const s = dr.stats;
            out.delay = {
                current: s.ritardo_attuale,
                media: s.media_ritardi ?? s.media_storica,
                record: s.record,
                ratio: s.rit_vs_media,
            };
        } catch { /* lascia delay=null */ }
    }
    return out;
}
