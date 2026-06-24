// ============================================================================
// Contesto del segnale (cruscotto Direzione) — FREQUENZA e RITARDO allo STATO
// ATTUALE per la lega + il mercato di un segnale.
//
// FONTE UNICA E CORRETTA: la serie binaria di get_market_frequency (un punto per
// partita SETTLATA, esito 0/1). Questa serie ESCLUDE correttamente le partite senza
// dati di primo tempo (per i mercati HT), quindi frequenza e ritardo sono coerenti e
// matematicamente validi. Il ritardo lo calcoliamo QUI dalla serie (corse di "non
// uscite"), NON da get_market_delays: quella RPC riproduce 1:1 il foglio Excel
// (HT vuoto = 0-0) e su leghe con HT mancanti gonfia il ritardo (es. 547 su over 0.5
// 1°T). Il pannello Ritardi continua a usare quella RPC per fedelta' al foglio; il
// cruscotto usa il calcolo corretto qui sotto.
// Caricato pigro: solo quando l'utente espande un mercato.
// ============================================================================
import { fetchMarketFrequency, FrequencyPoint } from './marketFrequency';

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

export interface SignalContext {
    freq: { current: number | null; baseline: number | null; z: number | null; n: number } | null;
    delay: { current: number; media: number | null; record: number; ratio: number | null } | null;
    available: boolean;  // il mercato e' mappabile su una serie di frequenza
}

// Ritardo dalla serie binaria (out 0/1, ordine cronologico per idx).
//   current = "non uscite" consecutive in coda (ritardo attuale)
//   record  = corsa massima di "non uscite"
//   media   = media dei gap fra uscite consecutive (ritardo medio)
function computeDelay(points: FrequencyPoint[]): SignalContext['delay'] {
    const pts = points.filter(p => p.out === 0 || p.out === 1).sort((a, b) => a.idx - b.idx);
    if (!pts.length) return null;
    const gaps: number[] = [];   // lunghezza di ogni gap fra due uscite
    let run = 0;
    for (const p of pts) {
        if (p.out === 1) { gaps.push(run); run = 0; }  // uscita: chiude il gap (anche 0)
        else run++;                                    // non-uscita: il ritardo cresce
    }
    const current = run;                               // gap aperto in coda = ritardo attuale
    const record = Math.max(current, ...gaps, 0);
    const media = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : null;
    const ratio = media && media > 0 ? current / media : null;
    return { current, media, record, ratio };
}

export async function fetchSignalContext(leagueId: number, market: string, dir: string): Promise<SignalContext> {
    const fm = freqMap(market, dir);
    const out: SignalContext = { freq: null, delay: null, available: !!fm };
    if (!fm) return out;
    try {
        // mode 'all' = tutta la storia settlata della lega -> ritardo record/media accurati.
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
        out.delay = computeDelay(pts);
    } catch { /* lascia null: mostrato come non disponibile */ }
    return out;
}
