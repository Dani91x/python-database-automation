// ============================================================================
// StoricoMikeGiornoRegolamento.test.tsx - piano Mike 29/09, M8.10 (difetto D10):
// lo Storico di Mike attribuisce una posizione al giorno del REGOLAMENTO, come
// «Posizioni chiuse». Omega e Safe restano al giorno di piazzamento.
// Righe finte con le chiavi di `trading_day_trades` (to_jsonb(o.*) + placed_in_day,
// settled_in_day, closes, total_pnl).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { attributionOf, summarizeDayTrades, type DayTrade } from '@/lib/dailyHistory';
import { TradingHistory } from './TradingHistory';

function riga(over: Record<string, unknown>): DayTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma v Lazio', side: 'back', mode: 'paper',
        price: 1.5, size: 10, liability: 10, status: 'won', pnl: 4.75, bet_id: 'b1',
        placed_at: '2026-09-28T21:30:00Z', settled_at: '2026-09-28T23:15:00Z',
        meta: null, closes: [], total_pnl: 4.75, placed_in_day: false, settled_in_day: true, ...over,
    } as never;
}

describe('M8.10 - Mike per giorno di regolamento', () => {
    it('attribuzione: Mike settled, Omega e Safe invariati', () => {
        expect(attributionOf('mike')).toBe('settled');
        expect(attributionOf('omega')).toBe('placed');
        expect(attributionOf('safe')).toBe('placed');
    });

    it('la posizione piazzata ieri sera e regolata oggi conta OGGI nello storico di Mike', () => {
        const ieriOggi = riga({ id: 1 });
        const oggiDomani = riga({ id: 2, pnl: -10, total_pnl: -10, status: 'open', placed_in_day: true, settled_in_day: false, settled_at: null });
        const s = summarizeDayTrades([ieriOggi, oggiDomani], attributionOf('mike'));
        expect(s.pnl).toBeCloseTo(4.75);
        expect(s.settled).toBe(1);
        // ancora aperta, piazzata oggi: resta visibile fra le aperte di oggi
        expect(s.open).toBe(1);
    });

    it('la pagina dice il criterio: posizioni REGOLATE nel giorno', async () => {
        render(<TradingHistory variant="mike" fetchDaily={async () => []} fetchDayTrades={async () => []} today="2026-09-29" />);
        expect(await screen.findByText(/P&L realizzato = posizioni REGOLATE nel giorno/)).toBeTruthy();
    });
});
