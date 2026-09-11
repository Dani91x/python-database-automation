// Test PURI del raggruppamento per partita (Omega §14): gambe 1T/2T con
// chiusure attaccate, risultati reali, P&L di gamba e di partita, filtro
// giornata, riepilogo.
import { describe, it, expect } from 'vitest';
import {
    groupTradesByMatch, legPnl, legKindOf, resultsOf, filterMatchesForDay, summarizeMatches, romeDayOf,
    isReconcilingTrade, isTerminalTrade, eventNamesFrom, errorAtOf,
    type MatchTradeLike,
} from './omegaMatches';

function t(over: Partial<MatchTradeLike> & { id: number }): MatchTradeLike {
    return {
        event_id: 'e1', event_name: 'Roma vs Lazio', phase: 'ht_cs', side: 'lay', status: 'open', pnl: 0,
        price: 60, size: 2.5, liability: 147.5, placed_at: '2026-09-11T14:00:00Z', settled_at: null,
        kickoff: '2026-09-11T13:30:00Z', closes_trade_id: null, meta: {}, runner_name: '0 - 3',
        minute_at_entry: 22, score_at_entry: '0-0', origin: 'auto', mode: 'paper', ...over,
    };
}

describe('omegaMatches — gambe', () => {
    it('legKindOf: 1T, 2T (anche v1 senza fase), altro', () => {
        expect(legKindOf({ phase: 'ht_cs' })).toBe('ht');
        expect(legKindOf({ phase: 'ft_cs' })).toBe('ft');
        expect(legKindOf({ phase: null })).toBe('ft');
        expect(legKindOf({ phase: 'scalp' })).toBe('other');
    });

    it('legPnl: regolato (apertura + chiusure), bloccato, aperto', () => {
        expect(legPnl(t({ id: 1, status: 'won', pnl: 2.16 }), [t({ id: 2, status: 'lost', pnl: -24.24, closes_trade_id: 1, side: 'back' })]))
            .toEqual({ state: 'settled', value: -22.08 });
        expect(legPnl(t({ id: 1, status: 'hedged', meta: { locked_pnl: -22.1 } }), [t({ id: 2, closes_trade_id: 1, side: 'back' })]))
            .toEqual({ state: 'locked', value: -22.1 });
        // cash out parziale: apertura ancora 'open' ma con locked_pnl e una chiusura fillata
        expect(legPnl(t({ id: 1, status: 'open', meta: { locked_pnl: 1.2 } }), [t({ id: 2, closes_trade_id: 1, side: 'back' })]))
            .toEqual({ state: 'locked', value: 1.2 });
        expect(legPnl(t({ id: 1, status: 'open' }), [])).toEqual({ state: 'open', value: null });
        expect(legPnl(t({ id: 1, status: 'error' }), [])).toEqual({ state: 'none', value: null });
    });

    it('resultsOf legge solo punteggi validi', () => {
        expect(resultsOf({ meta: { result_ht: '1-0', result_ft: 'boh' } })).toEqual({ ht: '1-0', ft: null });
        expect(resultsOf({ meta: null })).toEqual({ ht: null, ft: null });
    });
});

describe('omegaMatches — una riga per partita', () => {
    const rows: MatchTradeLike[] = [
        // partita e1: 1T persa in green-up (chiusa a −22,08), 2T vinta 2,4
        t({ id: 70, status: 'won', pnl: 2.16, meta: { locked_pnl: -22.1, exit_kind: 'greenup', result_ht: '1-2', result_ft: '1-2' }, settled_at: '2026-09-11T16:00:00Z' }),
        t({ id: 71, status: 'lost', pnl: -24.24, side: 'back', price: 4.9, size: 24.24, closes_trade_id: 70, placed_at: '2026-09-11T14:30:00Z', settled_at: '2026-09-11T16:00:00Z', meta: { exit_kind: 'greenup' } }),
        t({ id: 72, phase: 'ft_cs', status: 'won', pnl: 2.4, runner_name: '4 - 1', placed_at: '2026-09-11T15:05:00Z', settled_at: '2026-09-11T16:00:00Z', meta: { result_ft: '1-2' } }),
        // partita e2: solo 2T ancora aperta (presa in corsa), piazzata ieri sera
        t({ id: 80, event_id: 'e2', event_name: 'Inter vs Milan', phase: 'ft_cs', status: 'open', placed_at: '2026-09-10T20:10:00Z', kickoff: '2026-09-10T19:00:00Z', meta: { result_ht: '0-0' } }),
        // partita e3: v1 senza fase, regolata ieri
        t({ id: 60, event_id: 'e3', event_name: 'Old', phase: null, status: 'won', pnl: 5, placed_at: '2026-09-10T15:00:00Z', settled_at: '2026-09-10T17:00:00Z' }),
        // chiusura orfana (apertura non in lista): resta visibile da sola
        t({ id: 99, event_id: 'e4', event_name: 'Orfana', phase: null, side: 'back', status: 'open', closes_trade_id: 12345, placed_at: '2026-09-11T10:00:00Z' }),
    ];
    const groups = groupTradesByMatch(rows);

    it('raggruppa per evento con 1T/2T e chiusure attaccate, ordinato per ultima attività', () => {
        expect(groups.map((g) => g.event_id)).toEqual(['e1', 'e4', 'e2', 'e3']);
        const e1 = groups[0];
        expect(e1.ht?.trade.id).toBe(70);
        expect(e1.ht?.closes.map((c) => c.id)).toEqual([71]);
        expect(e1.ft?.trade.id).toBe(72);
        expect(e1.others).toEqual([]);
        expect(e1.legs.map((l) => l.kind)).toEqual(['ht', 'ft']);
        expect(e1.placed_at).toBe('2026-09-11T14:00:00Z');
        expect(e1.last_at).toBe('2026-09-11T16:00:00Z');
        expect(e1.kickoff).toBe('2026-09-11T13:30:00Z');
    });

    it('risultati reali e P&L di partita (verde/rosso): −22,08 + 2,40 = −19,68', () => {
        const e1 = groups[0];
        expect(e1.result_ht).toBe('1-2');
        expect(e1.result_ft).toBe('1-2');
        expect(e1.ht?.pnl).toEqual({ state: 'settled', value: -22.08 });
        expect(e1.ft?.pnl).toEqual({ state: 'settled', value: 2.4 });
        expect(e1.pnl_settled).toBe(-19.68);
        expect(e1.pnl_locked).toBeNull();
        expect(e1.state).toBe('settled');
        expect(e1.live).toBe(false);
    });

    it('partita presa in corsa: solo la 2T, aperta, liability a rischio, risultato 1T noto', () => {
        const e2 = groups[2];
        expect(e2.ht).toBeNull();
        expect(e2.ft?.trade.id).toBe(80);
        expect(e2.state).toBe('open');
        expect(e2.open_liability).toBe(147.5);
        expect(e2.result_ht).toBe('0-0');
        expect(e2.result_ft).toBeNull();
        expect(e2.live).toBe(true);
    });

    it('trade v1 senza fase va nella colonna 2T; chiusura orfana visibile', () => {
        expect(groups[3].ft?.trade.id).toBe(60);
        expect(groups[1].legs[0].trade.id).toBe(99);
        expect(groups[1].legs[0].kind).toBe('other');   // chiusura orfana: mai nella cella 1T/2T
    });

    it('filtro giornata: partite di oggi + vive di ieri; riepilogo', () => {
        const today = filterMatchesForDay(groups, '2026-09-11');
        expect(today.map((g) => g.event_id)).toEqual(['e1', 'e4', 'e2']);   // e3 (ieri, regolata) fuori
        const s = summarizeMatches(today);
        expect(s.matches).toBe(3);
        expect(s.legs).toBe(4);
        expect(s.settled).toBe(2);
        expect(s.won).toBe(1);
        expect(s.lost).toBe(1);
        expect(s.pnl_settled).toBe(-19.68);
        expect(s.pnl_locked).toBeNull();
        expect(s.open_liability).toBe(147.5);           // la chiusura orfana non aggiunge rischio
        expect(s.live).toBe(2);
        expect(romeDayOf('2026-09-10T22:30:00Z')).toBe('2026-09-11');   // 00:30 Rome
        expect(romeDayOf('nope')).toBe('');
    });

    it('stato parziale: una gamba regolata e una bloccata', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'won', pnl: 3 }),
            t({ id: 2, phase: 'ft_cs', status: 'hedged', meta: { locked_pnl: -1.5 } }),
            t({ id: 3, side: 'back', status: 'open', closes_trade_id: 2 }),
        ])[0];
        expect(g.state).toBe('partial');
        expect(g.pnl_settled).toBe(3);
        expect(g.pnl_locked).toBe(-1.5);
        expect(g.n_decided).toBe(2);
        expect(g.open_liability).toBe(0);
    });
});

describe('omegaMatches — correzioni review 11/09', () => {
    it('HIGH-1: cash out ancora pendente (locked_pnl null) → gamba APERTA, rischio vivo, mai "0 bloccato"', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'open', liability: 110, meta: { locked_pnl: null, hedge_pending_ids: [2] } }),
            t({ id: 2, side: 'back', status: 'pending', closes_trade_id: 1 }),
        ])[0];
        expect(g.ht?.pnl).toEqual({ state: 'open', value: null });
        expect(g.state).toBe('open');
        expect(g.n_decided).toBe(0);
        expect(g.pnl_locked).toBeNull();
        expect(g.open_liability).toBe(110);
    });

    it('MED-1: chiusura orfana con phase ereditata non occupa la cella 1T/2T e non aggiunge rischio', () => {
        const g = groupTradesByMatch([
            t({ id: 99, phase: 'ht_cs', side: 'back', status: 'open', size: 24, closes_trade_id: 12345 }),
        ])[0];
        expect(g.ht).toBeNull();
        expect(g.ft).toBeNull();
        expect(g.others[0].kind).toBe('other');
        expect(g.open_liability).toBe(0);
    });
});

// ================================================ audit 11/09: H-02 / M-05
describe('omegaMatches — verifica su Betfair e righe terminali', () => {
    it('H-02: un pending in RICONCILIAZIONE è vivo, conta nella liability e si dichiara', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'pending', liability: 573.34, meta: { reconciling: true } }),
        ])[0];
        expect(g.ht?.reconciling).toBe(true);
        expect(g.ht?.live).toBe(true);
        expect(g.open_liability).toBe(573.34);
        expect(g.reconciling_liability).toBe(573.34);
        expect(summarizeMatches([g]).reconciling_liability).toBe(573.34);
    });

    it('H-02: reconciling anche dall’eccezione di piazzamento', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'pending', liability: 100, meta: { reason: 'place_exception_reconciling' } }),
        ])[0];
        expect(g.ht?.reconciling).toBe(true);
        expect(g.reconciling_liability).toBe(100);
    });

    it('un pending normale (riserva) non è "in verifica"', () => {
        const g = groupTradesByMatch([t({ id: 1, status: 'pending', liability: 100 })])[0];
        expect(g.ht?.reconciling).toBe(false);
        expect(g.reconciling_liability).toBe(0);
    });

    it('M-05: riga TERMINALE (leg_failed) non è viva, non è rischio e non tiene aperta la partita', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'pending', liability: 500, meta: { leg_failed: true, error_final: true } }),
            t({ id: 2, phase: 'ft_cs', status: 'won', pnl: 2.5, settled_at: '2026-09-11T16:00:00Z' }),
        ])[0];
        expect(g.ht?.terminal).toBe(true);
        expect(g.ht?.live).toBe(false);
        expect(g.open_liability).toBe(0);
        expect(g.live).toBe(false);
        expect(g.state).toBe('settled');       // prima restava "partial" per sempre
        expect(g.pnl_settled).toBe(2.5);
    });

    it('isReconcilingTrade / isTerminalTrade come predicati puri', () => {
        expect(isReconcilingTrade({ meta: { reconciling: 'true' } })).toBe(true);
        expect(isReconcilingTrade({ meta: null })).toBe(false);
        expect(isTerminalTrade({ meta: { no_fill_at: '2026-09-11T16:00:00Z' } })).toBe(true);
        expect(isTerminalTrade({ meta: {} })).toBe(false);
    });

    it('eventNamesFrom: nome della partita per event_id (l’attività ha solo l’id)', () => {
        expect(eventNamesFrom([
            { event_id: 'e1', event_name: 'Roma vs Lazio' },
            { event_id: 'e1', event_name: 'altro nome ignorato' },
            { event_id: 'e2', event_name: '  ' },
        ])).toEqual({ e1: 'Roma vs Lazio' });
    });
});

describe('omegaMatches — ordinamento con meta.error_at (contratto 11/09)', () => {
    it('errorAtOf legge error_at (ripiego no_fill_at)', () => {
        expect(errorAtOf({ meta: { error_at: '2026-09-11T16:00:00Z' } })).toBe('2026-09-11T16:00:00Z');
        expect(errorAtOf({ meta: { no_fill_at: '2026-09-11T15:00:00Z' } })).toBe('2026-09-11T15:00:00Z');
        expect(errorAtOf({ meta: {} })).toBeNull();
    });

    it('una riga in errore (senza settled_at) aggiorna comunque "ultima attività"', () => {
        const g = groupTradesByMatch([
            t({ id: 1, status: 'error', settled_at: null, meta: { error_final: true, error_at: '2026-09-11T18:00:00Z' } }),
        ])[0];
        expect(g.last_at).toBe('2026-09-11T18:00:00Z');
    });

    it('le partite si ordinano per ultima attività anche quando l’ultimo fatto è un errore', () => {
        const gs = groupTradesByMatch([
            t({ id: 1, event_id: 'vecchia', status: 'won', pnl: 1, settled_at: '2026-09-11T15:00:00Z' }),
            t({ id: 2, event_id: 'recente', status: 'error', settled_at: null, meta: { error_final: true, error_at: '2026-09-11T19:00:00Z' } }),
        ]);
        expect(gs[0].event_id).toBe('recente');
    });
});
