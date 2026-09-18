// ============================================================================
// useTennisVivo.test.ts — Task 2 (18/09): il tennis vivo nella scheda partita.
//
// Copre esattamente le garanzie del brief: UNA sottoscrizione per evento
// (mai una per riga), pulizia allo smontaggio, mercato SUSPENDED visibile,
// correlazione selection_id -> nome, e l'età che non mente.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const hoisted = vi.hoisted(() => ({
    row: null as unknown,
    fetchCalls: 0,
    subCalls: 0,
    unsubCalls: 0,
    emitters: new Map<string, (row: unknown) => void>(),
}));

vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisNow: vi.fn(async () => {
        hoisted.fetchCalls += 1;
        return hoisted.row;
    }),
    subscribeTennisNow: vi.fn((eventId: string, cb: (row: unknown) => void) => {
        hoisted.subCalls += 1;
        hoisted.emitters.set(eventId, cb);
        return () => { hoisted.unsubCalls += 1; hoisted.emitters.delete(eventId); };
    }),
}));

import {
    useTennisVivo, vistaTennisVivo, nomeSelezioneTennis, canaliTennisViviApertiPerTest,
} from './useTennisVivo';
import type { TennisLiveNowRow, TennisScoreState } from '@/lib/tennis';

function score(over: Partial<TennisScoreState> = {}): TennisScoreState {
    return {
        status: 'InPlay', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 },
        points: { p1: '40', p2: '30' }, server: 1, tiebreak: false,
        game_sequence: { p1: ['6'], p2: ['4'] }, service_breaks: { p1: 1, p2: 0 },
        current_set: 2, current_game: 6, set_summary: '6-4 3-2',
        pressure: { break_point: false, set_point: false, game_point: true },
        win_prob_p1: 0.62, source: 'ips', updated_ms: Date.now(), ...over,
    };
}

function row(over: Partial<TennisLiveNowRow> = {}): TennisLiveNowRow {
    return {
        event_id: 'T1', inplay: true, status: 'OPEN',
        state: {
            markets: [{
                market_id: 'M1', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [
                    { selection_id: 111, name: 'Federer R.', back: 1.8, lay: 1.82, ltp: 1.8 },
                    { selection_id: 222, name: 'Nadal R.', back: 2.1, lay: 2.14, ltp: 2.1 },
                ],
            }],
            order_mode: 'LIVE', updated_ms: Date.now(),
        },
        score: score(), points: [], updated_at: new Date().toISOString(), ...over,
    };
}

beforeEach(() => {
    hoisted.row = null;
    hoisted.fetchCalls = 0;
    hoisted.subCalls = 0;
    hoisted.unsubCalls = 0;
    hoisted.emitters.clear();
});

// -------------------------------------------------------------- vista pura
describe('vistaTennisVivo — funzione pura, senza React', () => {
    it('punteggio, server e stato mercato arrivano dalla riga, invariati', () => {
        const v = vistaTennisVivo(row(), true, Date.now());
        expect(v.row?.score?.sets).toEqual({ p1: 1, p2: 0 });
        expect(v.row?.score?.server).toBe(1);
    });

    it('mercato SUSPENDED è VISIBILE: statoMercato non è null e dice SOSPESO', () => {
        const v = vistaTennisVivo(row({ status: 'SUSPENDED' }), true, Date.now());
        expect(v.statoMercato).not.toBeNull();
        expect(v.statoMercato?.label).toBe('SOSPESO');
        expect(v.statoMercato?.alarming).toBe(true);
    });

    it('mercato OPEN: nessun segnale (regola colore = solo anomalia)', () => {
        const v = vistaTennisVivo(row({ status: 'OPEN' }), true, Date.now());
        expect(v.statoMercato).toBeNull();
    });

    it("l'età cresce con l'orologio, non resta congelata al valore di scrittura", () => {
        const scrittoMs = Date.parse('2026-09-18T10:00:00Z');
        const r = row({ score: score({ updated_ms: scrittoMs }), updated_at: '2026-09-18T10:00:00Z' });
        const adesso = scrittoMs + 12_000;
        const v = vistaTennisVivo(r, true, adesso);
        expect(v.etaS).toBe(12);
        expect(v.freschezza).toBe('lenta'); // 12s: oltre 5, entro 20 (soglie condivise)
    });

    it('nessuna riga ancora arrivata: eta ignota, mai zero', () => {
        const v = vistaTennisVivo(null, false, Date.now());
        expect(v.etaS).toBeNull();
        expect(v.freschezza).toBe('ignota');
    });
});

describe('nomeSelezioneTennis — correlazione selection_id -> nome', () => {
    it('trova il nome nel mercato giusto', () => {
        expect(nomeSelezioneTennis(row(), 222)).toBe('Nadal R.');
    });

    it('selection_id assente nei libri: null, mai un nome inventato', () => {
        expect(nomeSelezioneTennis(row(), 999)).toBeNull();
    });

    it('riga assente: null', () => {
        expect(nomeSelezioneTennis(null, 111)).toBeNull();
    });
});

// -------------------------------------------------------------------- hook
describe('useTennisVivo — una sottoscrizione per evento (18/09)', () => {
    it('due montaggi sullo STESSO evento condividono UN solo canale', async () => {
        hoisted.row = row();
        const a = renderHook(() => useTennisVivo('T1'));
        await waitFor(() => expect(a.result.current.loaded).toBe(true));
        const b = renderHook(() => useTennisVivo('T1'));
        await waitFor(() => expect(b.result.current.loaded).toBe(true));

        expect(hoisted.subCalls).toBe(1); // MAI due canali per lo stesso evento
        expect(canaliTennisViviApertiPerTest()).toBe(1);

        a.unmount();
        // il primo si stacca: il secondo lo tiene ancora aperto
        expect(hoisted.unsubCalls).toBe(0);
        expect(canaliTennisViviApertiPerTest()).toBe(1);

        b.unmount();
        // l'ULTIMO che se ne va chiude davvero il canale
        expect(hoisted.unsubCalls).toBe(1);
        expect(canaliTennisViviApertiPerTest()).toBe(0);
    });

    it('smontaggio con un solo consumatore: il canale si chiude', async () => {
        hoisted.row = row();
        const { result, unmount } = renderHook(() => useTennisVivo('T2'));
        await waitFor(() => expect(result.current.loaded).toBe(true));
        expect(hoisted.subCalls).toBe(1);
        unmount();
        expect(hoisted.unsubCalls).toBe(1);
        expect(canaliTennisViviApertiPerTest()).toBe(0);
    });

    it('eventi diversi aprono canali diversi (non e\' un dedup globale sbagliato)', async () => {
        hoisted.row = row();
        const a = renderHook(() => useTennisVivo('E-A'));
        const b = renderHook(() => useTennisVivo('E-B'));
        await waitFor(() => expect(a.result.current.loaded).toBe(true));
        await waitFor(() => expect(b.result.current.loaded).toBe(true));
        expect(hoisted.subCalls).toBe(2);
        a.unmount(); b.unmount();
    });

    it('senza eventId (nessuna posizione tennis aperta): NESSUNA sottoscrizione', () => {
        const { result } = renderHook(() => useTennisVivo(null));
        expect(result.current.row).toBeNull();
        expect(hoisted.subCalls).toBe(0);
    });

    it('un aggiornamento realtime raggiunge tutti i montaggi dello stesso evento', async () => {
        hoisted.row = row({ score: score({ sets: { p1: 0, p2: 0 } }) });
        const a = renderHook(() => useTennisVivo('T3'));
        await waitFor(() => expect(a.result.current.loaded).toBe(true));
        const emit = hoisted.emitters.get('T3');
        expect(emit).toBeTypeOf('function');
        act(() => { emit?.(row({ score: score({ sets: { p1: 1, p2: 0 } }) })); });
        await waitFor(() => expect(a.result.current.row?.score?.sets.p1).toBe(1));
        a.unmount();
    });
});
