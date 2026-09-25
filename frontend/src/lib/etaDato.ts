// ============================================================================
// ETA' DEL DATO MATERIALIZZATO (reperto R5, 25/09/2026).
// Ogni tab della Dashboard che mostra un dato calcolato PRIMA (snapshot di una
// action notturna, tabella di calibrazione, pagella) dichiara QUANDO e' stato
// prodotto e se e' troppo vecchio. Qui solo la logica pura (testabile senza DOM);
// il componente e' components/dashboard/EtaDato.tsx.
//
// Soglie (motivate nel referto AUDIT5):
//  - previsioni per partita (Poisson/ML/TacticAI, generated_at): la action gira una
//    volta al giorno (02:18 UTC). 36 h = un giorno pieno + 12 h di margine per un
//    run in ritardo: oltre, significa che almeno un run e' saltato.
//  - calibrazione Poisson settimanale (poisson_calibration.generated_at): il lunedi'.
//    8 giorni = una settimana + 1 giorno di margine: oltre, un lunedi' e' saltato.
//  - pagella della Direzione (direction_pagella.generated_at): notturna -> 36 h.
// ============================================================================

export const SOGLIA_PREVISIONE_ORE = 36;
export const SOGLIA_CALIBRAZIONE_ORE = 8 * 24;
export const SOGLIA_PAGELLA_ORE = 36;

export type StatoEta = 'fresco' | 'vecchio' | 'assente';

export interface Eta {
    stato: StatoEta;
    ore: number | null;          // eta' in ore (null se assente)
    testoEta: string | null;     // "2 h", "3 g 4 h" ...
    testoData: string | null;    // data/ora locale it-IT
}

/** Eta' leggibile da ore: minuti sotto l'ora, ore sotto i 2 giorni, poi giorni+ore. */
export function formatEta(ore: number): string {
    if (ore < 1) return `${Math.max(0, Math.round(ore * 60))} min`;
    if (ore < 48) return `${Math.floor(ore)} h`;
    const g = Math.floor(ore / 24);
    const h = Math.floor(ore - g * 24);
    return h > 0 ? `${g} g ${h} h` : `${g} g`;
}

/**
 * Stato del dato rispetto a `now`: 'assente' se manca o non e' una data valida,
 * 'vecchio' se piu' vecchio della soglia (confine: esattamente la soglia e' ancora
 * fresco), altrimenti 'fresco'. Un orario nel futuro (orologi sfasati) conta eta' 0.
 */
export function calcolaEta(at: string | null | undefined, sogliaOre: number, now: Date = new Date()): Eta {
    if (!at) return { stato: 'assente', ore: null, testoEta: null, testoData: null };
    const t = new Date(at);
    if (Number.isNaN(t.getTime())) return { stato: 'assente', ore: null, testoEta: null, testoData: null };
    const ore = Math.max(0, (now.getTime() - t.getTime()) / 3_600_000);
    return {
        stato: ore > sogliaOre ? 'vecchio' : 'fresco',
        ore,
        testoEta: formatEta(ore),
        testoData: t.toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
    };
}
