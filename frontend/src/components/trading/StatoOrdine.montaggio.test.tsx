// ============================================================================
// StatoOrdine.montaggio.test.tsx — C.12b: il componente e' DAVVERO SU OGNI RIGA.
//
// Un componente condiviso che nessuno monta non risponde a nessuna domanda.
// Qui si prende la STESSA riga (5,00 chiesti, 2,00 abbinati a 2,38, 3,00 ancora
// vivi sul book) e si verifica che Omega, Safe, Mike e la Control Room dicano
// tutti e quattro la stessa cosa, con le stesse parole.
//
// FALSIFICAZIONE: togliere `<StatoOrdineRiga>`/`<StatoOrdineCompatto>` da una
// qualsiasi delle quattro superfici rende rosso il test corrispondente.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
// la scheda monta `AzioniPartita`, che usa `useNavigate`: serve un Router
import { MemoryRouter } from 'react-router-dom';
import { MatchTradesTable } from '@/components/omega/MatchTradesTable';
import { SafeTradesTable } from '@/components/safestrategy/SafeTradesTable';
import { MikeMatchCard } from '@/components/mike/MikeMatchCard';
import { SchedaPartita } from '@/components/controlroom/SchedaPartita';
import { MIKE_PARAM_DEFAULTS, type MikeEvent, type MikeLeg } from '@/lib/mike';
import type { SafeTrade } from '@/lib/safeBot';
import type { MatchTradeLike } from '@/lib/omegaMatches';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';

/** le colonne della migrazione `trades_consapevolezza_ordine_2026-09-16.sql` */
const CONSAPEVOLEZZA = {
    size_requested: 5, size_matched: 2, size_remaining: 3,
    avg_price_matched: 2.38, betfair_updated_at: '2026-09-16T10:00:00.000Z',
};
const NOW = Date.parse('2026-09-16T10:00:45.000Z');

// --------------------------------------------------------------------- OMEGA
describe('OMEGA — MatchTradesTable', () => {
    function trade(): MatchTradeLike {
        return {
            id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', phase: 'ft_cs', side: 'lay',
            status: 'pending', pnl: 0, price: 2.4, size: 2, liability: 2.8,
            placed_at: '2026-09-16T09:59:00Z', settled_at: null,
            kickoff: '2026-09-16T09:00:00Z', closes_trade_id: null, meta: {},
            runner_name: '3 - 2', minute_at_entry: 42, score_at_entry: '0-0',
            origin: 'auto', mode: 'paper', ...CONSAPEVOLEZZA,
        } as MatchTradeLike;
    }

    it('la gamba porta chiesto / abbinato / residuo e lo stato dell ordine', () => {
        render(<MatchTradesTable trades={[trade()]} liveFeed={{} as never}
            feedUpdatedAt={{}} nowMs={NOW} commission={5} day="2026-09-16" />);
        const riga = screen.getByTestId('omega-stato-ordine');
        expect(riga).toHaveAttribute('data-esito', 'parziale');
        expect(within(riga).getByTestId('omega-stato-ordine-chiesto')).toHaveTextContent('chiesto 5,00 €');
        expect(within(riga).getByTestId('omega-stato-ordine-abbinato')).toHaveTextContent('abbinato 2,00 € @2,38');
        expect(within(riga).getByTestId('omega-stato-ordine-residuo')).toHaveTextContent('residuo 3,00 €');
        expect(within(riga).getByTestId('omega-stato-ordine-eta')).toHaveTextContent('45 s');
    });

    it('un ordine solo APPOGGIATO non e piu etichettato APERTO', () => {
        const t = { ...trade(), status: 'open', size_matched: 0, size_remaining: 5 } as MatchTradeLike;
        render(<MatchTradesTable trades={[t]} liveFeed={{} as never}
            feedUpdatedAt={{}} nowMs={NOW} commission={5} day="2026-09-16" />);
        expect(screen.getByTestId('omega-status')).toHaveTextContent('APPOGGIATA · NON ABBINATA');
        expect(screen.getByTestId('omega-status').textContent).not.toBe('APERTO');
    });
});

// ---------------------------------------------------------------------- SAFE
describe('SAFE — SafeTradesTable', () => {
    function trade(over: Partial<SafeTrade> = {}): SafeTrade {
        return {
            id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'base',
            market_id: '1.9', market_type: 'OVER_UNDER_25', selection_id: 1, selection_name: 'Over 2.5',
            side: 'back', mode: 'paper', price: 2.38, size: 2, liability: 2, commission: 0.05,
            minute_at_entry: 60, score_at_entry: '1-0', status: 'pending', pnl: 0, bet_id: null,
            placed_at: '2026-09-16T09:59:00Z', settled_at: null, origin: 'auto',
            closes_trade_id: null, signal_key: null, meta: null,
            ...(CONSAPEVOLEZZA as Partial<SafeTrade>), ...over,
        } as SafeTrade;
    }

    it('sotto la riga ci sono chiesto / abbinato / residuo', () => {
        render(<SafeTradesTable trades={[trade()]} commissionPct={5} liveFeed={{}}
            onCashOut={vi.fn()} nowMs={NOW} />);
        const riga = screen.getByTestId('safe-stato-ordine');
        expect(riga).toHaveAttribute('data-esito', 'parziale');
        expect(within(riga).getByTestId('safe-stato-ordine-chiesto')).toHaveTextContent('chiesto 5,00 €');
        expect(within(riga).getByTestId('safe-stato-ordine-abbinato')).toHaveTextContent('abbinato 2,00 € @2,38');
        expect(within(riga).getByTestId('safe-stato-ordine-residuo')).toHaveTextContent('residuo 3,00 €');
    });

    it('un ordine solo APPOGGIATO non e piu etichettato APERTO', () => {
        render(<SafeTradesTable
            trades={[trade({ status: 'open', ...({ size_matched: 0, size_remaining: 5 } as Partial<SafeTrade>) })]}
            commissionPct={5} liveFeed={{}} onCashOut={vi.fn()} nowMs={NOW} />);
        expect(screen.getByTestId('safe-status')).toHaveTextContent('APPOGGIATA · NON ABBINATA');
    });
});

// ---------------------------------------------------------------------- MIKE
describe('MIKE — MikeMatchCard riusa lo stesso componente', () => {
    function leg(over: Partial<MikeLeg> = {}): MikeLeg {
        return {
            role: 'under_green', market: 'OU35', selection: 'UNDER', side: 'lay',
            price: 2.4, size: 5, matched: 2, avg_price: 2.38, ref: 'r9',
            status: 'pending', placed_at: 0, persistence: 'LAPSE',
            cycle_no: 0, final: false, archived: false, ...over,
        };
    }
    function ev(): MikeEvent {
        return {
            event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A',
            league_id: null, ko_at: new Date(Date.now() - 3600_000).toISOString(), mode: 'paper',
            markets: {}, state: 'LIVE_COVERED', cycle_no: 0, entry_price_initial: 1.5,
            dossier: null, positions: [leg()], ctx: null, skipped: false, settled_pnl: null,
            updated_at: new Date().toISOString(),
            live: {
                inplay: true, minute: 20, goals: 1, ht: false, hazard: 0.1,
                p4_market: 0.15, p4_model: 0.14, liability: 10, locked: 0, pnl_by_total: {},
                feed_age_s: 2, feed_fresh: true,
                cashout: { net: 0.5, gross: 0.55, base: 10, complete: true, pct: 5, per: {} },
                books: {}, cover_wait: null,
            } as MikeEvent['live'],
        } as MikeEvent;
    }

    it('l ordine sul book dice chiesto / abbinato / residuo, col residuo DALLA NOTA', () => {
        render(<MikeMatchCard ev={ev()} params={{ ...MIKE_PARAM_DEFAULTS }} mode="paper" onRequest={vi.fn()} />);
        const riga = screen.getByTestId('mike-stato-ordine');
        expect(riga).toHaveTextContent('chiesti 5,00 € @2,40');
        expect(riga).toHaveTextContent('abbinati 2,00 € @2,38');
        expect(riga).toHaveTextContent('residuo 3,00 €');
        // il residuo di Mike e' DEDOTTO (size - matched), non letto da Betfair:
        // l'asterisco lo dichiara invece di spacciarlo per un fatto dell exchange
        expect(riga).toHaveAttribute('data-dalla-nota', '1');
        expect(riga).toHaveAttribute('data-esito', 'parziale');
    });
});

// -------------------------------------------------------------- CONTROL ROOM
describe('CONTROL ROOM — SchedaPartita', () => {
    const partita: PartitaGiornata = {
        event_id: 'e1', sport: 'calcio', nome: 'Roma vs Lazio', campionato: 'Serie A',
        koMs: Date.now() - 3600_000, stato: 'live', minuto: 60, punteggio: '1-0',
        controlloDisponibile: false, etaFeedS: 2, freschezza: 'fresca',
        latenzaQuoteS: 3, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        media: null, extra: null, marketId: '1.1', soldi: null, target: null, avanzamento: null,
    };

    const op: OperazionePartita = {
        bot: 'safe', id: 1, selezione: 'Over 2.5', lato: 'back', prezzo: 2.38, size: 2,
        stato: 'pending', pnl: null, modalita: 'paper', at: '2026-09-16T09:59:00Z',
        quale: 'base',
        ordine: {
            status: 'pending', side: 'back', price: 2.4, size: 2, meta: null, ...CONSAPEVOLEZZA,
        },
    };

    it('aprendo il bot, l operazione porta chiesto / abbinato / residuo compatti', async () => {
        render(<MemoryRouter><SchedaPartita p={partita} operazioni={[op]} /></MemoryRouter>);
        await userEvent.click(screen.getByTestId('cr-bot-safe-e1'));
        const riga = screen.getByTestId('cr-stato-ordine');
        expect(riga).toHaveTextContent('chiesti 5,00 € @2,40 · abbinati 2,00 € @2,38 · residuo 3,00 €');
        expect(riga).toHaveAttribute('data-esito', 'parziale');
    });

    it('⚠️ senza i numeri lo DICE, non mostra zeri', async () => {
        render(<MemoryRouter><SchedaPartita p={partita} operazioni={[{
            ...op, ordine: { status: 'pending', side: 'back', price: 2.4, size: 2, meta: null },
        }]} /></MemoryRouter>);
        await userEvent.click(screen.getByTestId('cr-bot-safe-e1'));
        const riga = screen.getByTestId('cr-stato-ordine');
        expect(riga).toHaveTextContent('abbinamento non dichiarato dal servizio');
        expect(riga.textContent).not.toMatch(/0,00/);
    });
});
