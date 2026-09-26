// ============================================================================
// FIX-A (26/09) — Safe: paper e live NON si sommano (E2E fase 3, KO 1).
//
// REPERTO: `get_safe_state` chiamata con `{}` → `safe_aggregates_sql(NULL)` =
// TUTTE le modalità, e la pagina scriveva `realized_total` sotto «P&L totale ·
// PAPER» (−45,25 € = −47,83 paper + 2,58 live, U0485).
//
// Le righe di prova sono le risposte VERE di `safe_aggregates_sql(NULL|'paper'|
// 'live')` lette in sola lettura sul DB il 26/09 (stesse chiavi, stessi tipi).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

const rpc = vi.hoisted(() => vi.fn());
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc } }));

import {
    fetchSafeState, aggregatiDellaModalita, modalitaConAttivita, type SafeAggregates,
} from './safeBot';

const A_ALL = {
    won: 130, lost: 51, mode: null, won_today: 7, day_trades: 11, legs_today: 11, lost_today: 1,
    open_count: 3, events_today: 11, day_liability: 490, operating_day: '2026-09-26',
    open_liability: 104, realized_today: 4.78, realized_total: -40.47, reconciling_count: 0,
    day_liability_model: 0, realized_live_total: 2.58, realized_paper_total: -43.05,
    reconciling_liability: 0,
};
const A_PAPER = { ...A_ALL, won: 112, mode: 'paper', realized_total: -43.05 };
const A_LIVE = {
    ...A_ALL, won: 18, lost: 0, mode: 'live', won_today: 0, day_trades: 0, legs_today: 0,
    lost_today: 0, open_count: 0, events_today: 0, day_liability: 0, open_liability: 0,
    realized_today: 0, realized_total: 2.58,
};

beforeEach(() => {
    rpc.mockReset();
    rpc.mockImplementation(async (fn: string, args: Record<string, unknown>) => {
        if (fn === 'get_safe_state') {
            return { data: { control: null, trades: [], aggregates: A_ALL, activity: [] }, error: null };
        }
        if (fn === 'get_safe_aggregates') {
            return { data: args.p_mode === 'paper' ? A_PAPER : A_LIVE, error: null };
        }
        return { data: null, error: { message: `rpc inattesa ${fn}` } };
    });
});

describe('fetchSafeState({ perModalita }) — gli aggregati di UNA modalità ciascuno', () => {
    it('legge paper e live con p_mode esplicito', async () => {
        const st = await fetchSafeState({ perModalita: true });
        const chiamate = rpc.mock.calls.filter(([fn]) => fn === 'get_safe_aggregates');
        expect(chiamate.map(([, a]) => a)).toEqual([{ p_mode: 'paper' }, { p_mode: 'live' }]);
        expect(st.aggregates_by_mode?.paper?.realized_total).toBe(-43.05);
        expect(st.aggregates_by_mode?.live?.realized_total).toBe(2.58);
    });

    it('senza l’opzione (Control Room) nessuna lettura in più', async () => {
        const st = await fetchSafeState();
        expect(rpc.mock.calls.filter(([fn]) => fn === 'get_safe_aggregates')).toHaveLength(0);
        expect(st.aggregates_by_mode).toBeNull();
    });

    it('una modalità che non si legge resta null: MAI ripiegata sulla somma', async () => {
        rpc.mockImplementation(async (fn: string, args: Record<string, unknown>) => {
            if (fn === 'get_safe_state') return { data: { aggregates: A_ALL }, error: null };
            if (args.p_mode === 'live') return { data: null, error: { message: 'timeout' } };
            return { data: A_PAPER, error: null };
        });
        const st = await fetchSafeState({ perModalita: true });
        expect(st.aggregates_by_mode).toEqual({ paper: A_PAPER, live: null });
    });
});

describe('aggregatiDellaModalita — nessuna cifra sotto un’etichetta di modalità diversa', () => {
    const all = A_ALL as unknown as SafeAggregates;

    it('per modalità: quelli letti apposta', () => {
        const st = { aggregates: all, aggregates_by_mode: { paper: A_PAPER as never, live: A_LIVE as never } };
        expect(aggregatiDellaModalita(st, 'paper')?.realized_total).toBe(-43.05);
        expect(aggregatiDellaModalita(st, 'live')?.realized_total).toBe(2.58);
    });

    it('solo aggregati di TUTTE le modalità: il totale separato, il resto assente (mai −40,47)', () => {
        const p = aggregatiDellaModalita({ aggregates: all, aggregates_by_mode: null }, 'paper');
        expect(p?.realized_total).toBe(-43.05);
        expect(p?.realized_today).toBeUndefined();
        expect(p?.open_liability).toBeUndefined();
        expect(aggregatiDellaModalita({ aggregates: all }, 'live')?.realized_total).toBe(2.58);
    });

    it('RPC vecchia (nessuna chiave mode): attribuita alla modalità del bot e a nessun’altra', () => {
        const vecchia = { realized_today: 1, realized_total: 5, open_liability: 0, open_count: 0, won: 1, lost: 0 };
        expect(aggregatiDellaModalita({ aggregates: vecchia }, 'paper', 'paper')).toBe(vecchia);
        expect(aggregatiDellaModalita({ aggregates: vecchia }, 'live', 'paper')).toBeNull();
    });

    it('l’altra modalità si mostra solo se ha qualcosa', () => {
        expect(modalitaConAttivita(A_LIVE as never)).toBe(true);           // +2,58 storico
        expect(modalitaConAttivita({ ...A_LIVE, realized_total: 0 } as never)).toBe(false);
        expect(modalitaConAttivita(null)).toBe(false);
    });
});
