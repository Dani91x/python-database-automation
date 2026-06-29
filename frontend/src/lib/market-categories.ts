// ============================================================================
// market-categories.ts — categorizzazione dei mercati Betfair in tab, CONDIVISA
// tra Match Replay e Segui Live così l'organizzazione (e i pulsanti) è identica.
// ============================================================================

export type CatKey = 'MATCH_ODDS' | 'OVER_UNDER' | 'CORRECT_SCORE' | 'FIRST_HALF' | 'BTTS' | 'OTHER';

export const CATEGORIES: { key: CatKey; label: string }[] = [
    { key: 'MATCH_ODDS', label: 'Match Odds' },
    { key: 'OVER_UNDER', label: 'Over/Under' },
    { key: 'CORRECT_SCORE', label: 'Correct Score' },
    { key: 'FIRST_HALF', label: 'First Half' },
    { key: 'BTTS', label: 'BTTS' },
    { key: 'OTHER', label: 'Squadre/Altri' },
];

// categoria di un mercato dal suo market_type.
export function categoryOf(type: string | null): CatKey {
    const t = (type || '').toUpperCase();
    if (t === 'MATCH_ODDS' || t === 'DOUBLE_CHANCE' || t === 'HALF_TIME_FULL_TIME') return 'MATCH_ODDS';
    if (t.startsWith('FIRST_HALF_GOALS') || t === 'HALF_TIME') return 'FIRST_HALF';
    if (t.startsWith('OVER_UNDER')) return 'OVER_UNDER';
    if (t === 'CORRECT_SCORE' || t === 'HALF_TIME_SCORE') return 'CORRECT_SCORE';
    if (t === 'BOTH_TEAMS_TO_SCORE' || t === 'BTTS') return 'BTTS';
    return 'OTHER';
}

// linea numerica da un market_type tipo OVER_UNDER_25 -> 2.5 (per ordinamento ASC).
export function lineOf(type: string | null): number {
    const m = /(\d)(\d)$/.exec((type || '').toUpperCase());
    return m ? Number(`${m[1]}.${m[2]}`) : Number.MAX_SAFE_INTEGER;
}

// Raggruppa una lista di mercati (qualsiasi oggetto con market_type) per categoria,
// ordinando Over/Under e First Half per linea ASC. Ritorna una Map CatKey -> T[].
export function groupByCategory<T extends { market_type: string | null }>(markets: T[]): Map<CatKey, T[]> {
    const byCat = new Map<CatKey, T[]>();
    for (const m of markets) {
        const k = categoryOf(m.market_type);
        const arr = byCat.get(k) ?? [];
        arr.push(m);
        byCat.set(k, arr);
    }
    for (const [k, arr] of byCat) {
        if (k === 'OVER_UNDER' || k === 'FIRST_HALF') {
            arr.sort((a, b) => lineOf(a.market_type) - lineOf(b.market_type));
        }
    }
    return byCat;
}

// Le categorie presenti (con >=1 mercato), nell'ordine canonico di CATEGORIES.
export function presentCategories(byCat: Map<CatKey, unknown[]>): { key: CatKey; label: string }[] {
    return CATEGORIES.filter(c => (byCat.get(c.key)?.length ?? 0) > 0);
}
