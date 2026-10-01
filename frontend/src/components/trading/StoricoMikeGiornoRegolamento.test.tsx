// ============================================================================
// StoricoMikeGiornoRegolamento.test.tsx - lo Storico per GIORNO DELLA PARTITA.
//
// 29/09 (piano Mike M8.10): Mike contava il giorno del REGOLAMENTO, Omega e
// Safe il PIAZZAMENTO - tre criteri nella stessa pagina. 01/10 (ordine
// dell'utente, decisione del coordinatore): UN criterio per tutti, il giorno
// della PARTITA, deciso dal database per riga (`in_day`, `giorno_partita`,
// `giorno_da`). Il criterio di prima resta SOLO come ripiego dichiarato
// quando la RPC non manda `in_day` (aggiornamento del database non applicato).
//
// Righe finte con le chiavi di `trading_day_trades` (to_jsonb(o.*) +
// placed_in_day, settled_in_day, closes, total_pnl) PIU' le chiavi del
// contratto del 01/10; le giornate con le 24 chiavi di `get_mike_daily`.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import {
    attributionOf, ripiegoAttribuzione, summarizeDayTrades, normalizeDayTrades, normalizeDailyRows,
    type DayTrade,
} from '@/lib/dailyHistory';
import { TradingHistory } from './TradingHistory';
import { DayDetail } from './DayDetail';

/** riga di `get_mike_day_trades` CON le chiavi del contratto 01/10 */
function riga(over: Record<string, unknown>): Record<string, unknown> {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma v Lazio', side: 'back', mode: 'live',
        price: 1.5, size: 10, liability: 10, status: 'won', pnl: 4.75, bet_id: 'b1',
        pnl_betfair: null, strategy: 'under_entry',
        placed_at: '2026-09-30T21:30:00Z', settled_at: '2026-09-30T23:15:00Z',
        meta: null, closes: [], total_pnl: 4.75, placed_in_day: true, settled_in_day: false,
        giorno_partita: '2026-09-30', giorno_da: 'partita', in_day: true,
        ...over,
    };
}

/** riga di `get_mike_daily` con le chiavi della RPC vera */
function giornata(day: string, pnl: number, over: Record<string, unknown> = {}) {
    return {
        day, won: 0, goal: null, lost: 0, void: 0, avg_win: null, settled: 0, avg_loss: null,
        by_sport: {}, goal_pct: null, win_rate: null, by_origin: {}, best_trade: null, gross_loss: 0,
        by_strategy: {}, worst_trade: null, gross_profit: 0, pnl_realized: pnl, hedged_closed: 0,
        last_trade_at: null, max_liability: null, profit_factor: null, trades_placed: 0,
        first_trade_at: null, commission_paid: null, mode: 'live', ...over,
    };
}

describe('01/10 - un criterio solo: il giorno della PARTITA', () => {
    it('attribuzione unica per i tre bot; il criterio di prima e\' solo ripiego', () => {
        for (const v of ['omega', 'safe', 'mike'] as const) expect(attributionOf(v)).toBe('match');
        expect(ripiegoAttribuzione('mike')).toBe('settled');
    });

    it('partita delle 23:30 regolata alle 01:15: conta nel giorno della PARTITA, non in quello del regolamento', () => {
        // stessa posizione, vista nella risposta del 30/09 (in_day) e del 01/10 (non in_day)
        const del30 = normalizeDayTrades([riga({ id: 1, in_day: true })]);
        const del01 = normalizeDayTrades([riga({ id: 1, in_day: false, placed_in_day: false, settled_in_day: true })]);
        expect(summarizeDayTrades(del30, attributionOf('mike'), ripiegoAttribuzione('mike')).pnl).toBe(4.75);
        const s01 = summarizeDayTrades(del01, attributionOf('mike'), ripiegoAttribuzione('mike'));
        expect(s01.pnl).toBe(0);
        expect(s01.others).toHaveLength(1);
    });

    it('la pagina dice il criterio (una frase sola per i tre bot) e la MONETA', async () => {
        render(<TradingHistory variant="mike" fetchDaily={async () => []} fetchDayTrades={async () => []}
            today="2026-10-01" modo="live" />);
        expect(await screen.findByTestId('history-criterio')).toHaveTextContent(/giorno della PARTITA/);
        expect(screen.getByTestId('history-criterio')).not.toHaveTextContent(/REGOLATE nel giorno|PIAZZATE nel giorno/);
        expect(screen.getByTestId('history-moneta')).toHaveTextContent('SOLDI VERI');
    });

    it('moneta assente: si dichiara «moneta non dichiarata», mai muta', async () => {
        render(<TradingHistory variant="omega" fetchDaily={async () => []} fetchDayTrades={async () => []} today="2026-10-01" />);
        expect(await screen.findByTestId('history-moneta')).toHaveTextContent('moneta non dichiarata');
    });

    it('il selettore della moneta chiede l\'altra APPOSTA (prova)', async () => {
        const onModo = vi.fn();
        render(<TradingHistory variant="omega" fetchDaily={async () => []} fetchDayTrades={async () => []}
            today="2026-10-01" modo="live" onModo={onModo} />);
        fireEvent.click(await screen.findByTestId('history-mode-paper'));
        expect(onModo).toHaveBeenCalledWith('paper');
        expect(screen.getByTestId('history-mode-live')).toHaveAttribute('aria-pressed', 'true');
    });
});

describe('01/10 - ripiego dichiarato: la RPC non manda il giorno della partita', () => {
    it('il dettaglio usa il criterio di prima di quel bot E lo dice a schermo', () => {
        const vecchie = normalizeDayTrades([
            riga({ id: 1, in_day: undefined, giorno_partita: undefined, giorno_da: undefined, placed_in_day: false, settled_in_day: true }),
        ]).map((t) => { const c = { ...t } as Record<string, unknown>; return c as unknown as DayTrade; });
        render(<DayDetail day="2026-10-01" trades={vecchie} variant="mike" />);
        // Mike col criterio di prima: regolata oggi = di oggi (come la cella vecchia)
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+4,75');
        expect(screen.getByTestId('day-giorno-ripiego')).toHaveTextContent(/non manda ancora il giorno della partita/);
    });

    it('con il contratto nuovo la nota di ripiego NON compare', () => {
        render(<DayDetail day="2026-09-30" trades={normalizeDayTrades([riga({})])} variant="mike" />);
        expect(screen.queryByTestId('day-giorno-ripiego')).toBeNull();
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+4,75');
    });

    it('inizio partita non noto: giorno di piazzamento, detto sulla riga e in testata', () => {
        render(<DayDetail day="2026-09-30" variant="safe"
            trades={normalizeDayTrades([riga({ giorno_partita: null, giorno_da: 'piazzamento' })])} />);
        expect(screen.getByTestId('day-giorno-piazzamento')).toHaveTextContent('1 senza inizio partita noto: giorno di piazzamento');
        expect(within(screen.getByTestId('day-trade-row')).getByTestId('day-trade-giorno-piazzamento')).toBeInTheDocument();
    });
});

describe('accettazione del coordinatore (Mike live, dopo la migrazione del 01/10)', () => {
    // get_mike_daily 30/09 = +1,88, 5 piazzati, 5 regolati (2V 3P); 01/10 = nessuna riga
    const daily = [giornata('2026-09-30', 1.88, { trades_placed: 5, settled: 5, won: 2, lost: 3, win_rate: 0.4 })];
    // le 5 posizioni della partita del 30/09 (due regolate dopo mezzanotte)
    const day30 = [
        riga({ id: 11, pnl: 2.10, total_pnl: 2.10, status: 'won' }),
        riga({ id: 12, pnl: 1.50, total_pnl: 1.50, status: 'won' }),
        riga({ id: 13, pnl: -0.40, total_pnl: -0.40, status: 'lost' }),
        riga({ id: 14, pnl: -0.70, total_pnl: -0.70, status: 'lost', settled_at: '2026-09-30T22:20:00Z', placed_in_day: true, settled_in_day: false }),
        riga({ id: 15, pnl: -0.62, total_pnl: -0.62, status: 'lost', settled_at: '2026-09-30T22:45:00Z' }),
    ];

    it('cella e dettaglio del 30/09 dicono gli STESSI numeri: +1,88, 5 trade, 2V 3P', async () => {
        const fetchDaily = vi.fn(async () => normalizeDailyRows(daily));
        const fetchDayTrades = vi.fn(async (d: string) => (d === '2026-09-30' ? normalizeDayTrades(day30) : []));
        render(<TradingHistory variant="mike" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades}
            today="2026-09-30" modo="live" />);
        await waitFor(() => expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+1,88'));
        expect(screen.getByTestId('day-count')).toHaveTextContent('5 trade');
        expect(screen.getByTestId('day-detail')).toHaveTextContent('2V 3P');
        expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+1,88');
    });

    it('il 01/10 non ha righe: dettaglio vuoto, nessuno zero inventato', async () => {
        const fetchDayTrades = vi.fn(async () => normalizeDayTrades([]));
        render(<TradingHistory variant="mike" fetchDaily={async () => normalizeDailyRows(daily)}
            fetchDayTrades={fetchDayTrades} today="2026-10-01" modo="live" />);
        expect(await screen.findByTestId('day-detail-none')).toBeInTheDocument();
        expect(screen.getByTestId('day-count')).toHaveTextContent('0 trade');
    });
});
