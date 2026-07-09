// ============================================================================
// journalStats.ts — statistica PURA sul Trade Journal (E37, review post-sessione).
// Nessun I/O, nessun React: raggruppamenti per dimensione + join settled.
// ============================================================================
import type { LiveJournalRow } from '@/lib/liveOrders';

export interface PatternStat {
    key: string;
    count: number;
    stakeTotal: number;
}

// Bucket di 15 minuti per il minuto di gioco (90+ per recupero/oltre).
function minuteBucket(row: LiveJournalRow): string {
    const m = row.minute;
    if (m == null) {
        // niente minuto: pre-match se non in gioco; se in gioco è un minuto IGNOTO
        // (onesto: '—', non un bucket inventato).
        return row.inplay === true ? '—' : 'pre-match';
    }
    if (m >= 90) return '90+';
    const i = Math.max(0, Math.floor(m / 15)); // 0..5
    return `${i * 15}-${(i + 1) * 15}`;
}

function keyOf(row: LiveJournalRow, dim: 'tag' | 'action' | 'side' | 'origin' | 'minuteBucket'): string {
    switch (dim) {
        case 'tag': return row.tag == null || row.tag === '' ? '(senza tag)' : row.tag;
        case 'action': return row.action;
        case 'side': return row.side ?? '—';
        case 'origin': return row.origin;
        case 'minuteBucket': return minuteBucket(row);
    }
}

/**
 * Raggruppa il journal per una dimensione. stakeTotal = Σ size (righe senza
 * size → 0). Risultato ordinato per count desc (a parità, ordine di apparizione).
 */
export function groupJournal(
    rows: ReadonlyArray<LiveJournalRow>,
    dim: 'tag' | 'action' | 'side' | 'origin' | 'minuteBucket',
): PatternStat[] {
    const acc = new Map<string, PatternStat>();
    for (const row of rows) {
        const key = keyOf(row, dim);
        const cur = acc.get(key) ?? { key, count: 0, stakeTotal: 0 };
        cur.count += 1;
        cur.stakeTotal += Number.isFinite(row.size as number) ? (row.size as number) : 0;
        acc.set(key, cur);
    }
    // sort stabile: Array.prototype.sort è stabile in ES2019+ → a parità di count
    // resta l'ordine di inserimento.
    return [...acc.values()].sort((a, b) => b.count - a.count);
}

/**
 * Join journal↔settled: mappa market_id → profit REALIZZATO del mercato.
 * Se lo stesso market_id compare più volte (es. paper+live) i profit si SOMMANO
 * (mai sovrascrivere un P&L con un altro).
 */
export function settledByMarket(
    settled: ReadonlyArray<{ market_id: string; profit: number }>,
): Map<string, number> {
    const m = new Map<string, number>();
    for (const s of settled) {
        m.set(s.market_id, (m.get(s.market_id) ?? 0) + s.profit);
    }
    return m;
}
