// 30/09 — la scheda della partita DICE da dove viene il P&L regolato
// (ordine dell'utente: «il trader deve sapere cosa sta guardando e che dati»).
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MikeMatchCard } from './MikeMatchCard';
import { MIKE_PARAM_DEFAULTS, type MikeEvent } from '@/lib/mike';

function ev(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: '36130526', fixture_id: null, event_name: 'FC Vsetin v Bohemians 1905',
        competition: null, league_id: null, ko_at: new Date(Date.now() - 4 * 3600_000).toISOString(),
        mode: 'live', markets: {}, state: 'SETTLED', cycle_no: 0, entry_price_initial: 2.12,
        dossier: null, live: null, positions: [], ctx: null, skipped: false, settled_pnl: -0.05,
        updated_at: new Date().toISOString(), ...over,
    };
}

describe('MikeMatchCard — fonte del P&L regolato', () => {
    it('live dal conto: «conto Betfair» con la scomposizione Mike / utente', () => {
        render(<MikeMatchCard mode="live" params={{ ...MIKE_PARAM_DEFAULTS }} ev={ev({
            ctx: { pnl_conto: { fonte: 'betfair', conto: -0.05, mike: 2.1, utente: -2.15 } },
        })} />);
        const f = screen.getByTestId('mike-regolato-fonte');
        expect(f).toHaveTextContent('conto Betfair');
        expect(f).toHaveTextContent('di cui Mike +2,10');
        expect(f).toHaveTextContent('di cui utente −2,15');
        expect(screen.getByTestId('mike-regolato').getAttribute('title'))
            .toContain('P&L del conto Betfair (tutte le operazioni: Mike + utente)');
        expect(screen.getByTestId('mike-cashout-value')).toHaveTextContent('(conto Betfair)');
    });

    it('live senza regolato di Betfair: «stima»; paper: «simulato»', () => {
        const { unmount } = render(<MikeMatchCard mode="live" params={{ ...MIKE_PARAM_DEFAULTS }}
            ev={ev({ ctx: { pnl_conto: { fonte: 'stima' } } })} />);
        expect(screen.getByTestId('mike-regolato-fonte')).toHaveTextContent('stima');
        unmount();
        render(<MikeMatchCard mode="paper" params={{ ...MIKE_PARAM_DEFAULTS }}
            ev={ev({ mode: 'paper', settled_pnl: 1.87 })} />);
        expect(screen.getByTestId('mike-regolato-fonte')).toHaveTextContent('simulato');
        expect(screen.getByTestId('mike-regolato-fonte')).not.toHaveTextContent('di cui');
    });
});
