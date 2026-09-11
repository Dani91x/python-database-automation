// ============================================================================
// useScanLiveFeed.test.ts — certificazione 11/09 (dati reali): il feed live.
//
// Il bug che questi test chiudono: l'hook faceva UNA sola passata (`useEffect`
// con deps `[]`) e la fotografia iniziale filtrava su `wanted.current`, che al
// mount è VUOTO — gli event_id arrivano dai trade, cioè dopo. Sulla tabella di
// Omega le colonne "quota live / minuto / punteggio / se chiudo ora" restavano
// vuote (e la riga diceva "FEED ASSENTE") finché non arrivava un messaggio
// realtime per quella partita: su un mercato tranquillo, minuti interi.
//
// Garanzie certificate qui:
//   1. l'insieme che arriva DOPO il mount fa scattare la fotografia;
//   2. UNA SELECT per insieme, non una per render;
//   3. il canale Realtime resta UNO per la vita del componente (§18);
//   4. la fotografia non sovrascrive una riga più FRESCA arrivata dal realtime.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const hoisted = vi.hoisted(() => ({
    rows: [] as unknown[],
    fetchCalls: 0,
    subCalls: 0,
    unsubCalls: 0,
    emit: null as null | ((ev: unknown) => void),
}));

vi.mock('@/lib/safeStrategyScan', () => ({
    fetchScanRows: vi.fn(async () => { hoisted.fetchCalls += 1; return hoisted.rows; }),
    subscribeScanRows: vi.fn((cb: (ev: unknown) => void) => {
        hoisted.subCalls += 1;
        hoisted.emit = cb;
        return () => { hoisted.unsubCalls += 1; };
    }),
}));

import { useScanLiveFeedRows, liveScoreLabel } from './useScanLiveFeed';

function row(event_id: string, minute: number, updated_at: string) {
    return {
        sport: 'calcio', event_id, updated_at,
        payload: { minute, score_home: 1, score_away: 0, inplay: true },
    };
}

beforeEach(() => {
    hoisted.rows = [];
    hoisted.fetchCalls = 0;
    hoisted.subCalls = 0;
    hoisted.unsubCalls = 0;
    hoisted.emit = null;
});

describe('useScanLiveFeedRows — la fotografia iniziale segue gli eventi', () => {
    it('event_id che arrivano DOPO il mount: la fotografia scatta e popola le righe', async () => {
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z')];
        // primo render con la lista VUOTA, come nella pagina reale (i trade
        // non sono ancora arrivati dall'RPC)
        const { result, rerender } = renderHook(
            ({ ids }: { ids: string[] }) => useScanLiveFeedRows(ids),
            { initialProps: { ids: [] as string[] } },
        );
        expect(result.current).toEqual({});
        expect(hoisted.fetchCalls, 'nessuna SELECT senza eventi da seguire').toBe(0);

        // arrivano i trade → la pagina passa gli event_id
        rerender({ ids: ['e1'] });
        await waitFor(() => expect(result.current.e1).toBeDefined());
        expect(result.current.e1.payload.minute).toBe(52);
        expect(result.current.e1.updated_at).toBe('2026-09-11T20:00:00Z');
        expect(hoisted.fetchCalls).toBe(1);
    });

    it('una SELECT per INSIEME, non una per render', async () => {
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z')];
        const { rerender } = renderHook(
            ({ ids }: { ids: string[] }) => useScanLiveFeedRows(ids),
            { initialProps: { ids: ['e1'] } },
        );
        await waitFor(() => expect(hoisted.fetchCalls).toBe(1));

        // stesso insieme, array NUOVO (è quello che fa la pagina a ogni render)
        rerender({ ids: ['e1'] });
        rerender({ ids: ['e1'] });
        // stesso insieme in ORDINE diverso e con un duplicato: sempre lo stesso
        rerender({ ids: ['e1', 'e1'] });
        await waitFor(() => expect(hoisted.fetchCalls).toBe(1));

        // insieme DAVVERO cambiato → una sola nuova SELECT
        rerender({ ids: ['e1', 'e2'] });
        await waitFor(() => expect(hoisted.fetchCalls).toBe(2));
        rerender({ ids: ['e2', 'e1'] });      // stesso insieme, altro ordine
        await waitFor(() => expect(hoisted.fetchCalls).toBe(2));
    });

    it('§18: il canale Realtime è UNO per la vita del componente', async () => {
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z')];
        const { rerender, unmount } = renderHook(
            ({ ids }: { ids: string[] }) => useScanLiveFeedRows(ids),
            { initialProps: { ids: [] as string[] } },
        );
        rerender({ ids: ['e1'] });
        rerender({ ids: ['e1', 'e2'] });
        rerender({ ids: ['e3'] });
        await waitFor(() => expect(hoisted.fetchCalls).toBeGreaterThan(0));
        expect(hoisted.subCalls, 'canale riaperto a ogni cambio di insieme').toBe(1);
        expect(hoisted.unsubCalls).toBe(0);
        unmount();
        expect(hoisted.unsubCalls).toBe(1);
    });

    it('la fotografia NON sovrascrive una riga più fresca del realtime', async () => {
        // la SELECT torna una riga VECCHIA (20:00), il realtime ne ha già
        // portata una NUOVA (20:05): vince la nuova
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z')];
        const { result, rerender } = renderHook(
            ({ ids }: { ids: string[] }) => useScanLiveFeedRows(ids),
            { initialProps: { ids: ['e1'] } },
        );
        await waitFor(() => expect(result.current.e1).toBeDefined());

        act(() => {
            hoisted.emit?.({ type: 'upsert', row: row('e1', 70, '2026-09-11T20:05:00Z') });
        });
        await waitFor(() => expect(result.current.e1.payload.minute).toBe(70));

        // nuovo insieme → nuova fotografia, ma la riga del realtime è più fresca
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z'), row('e2', 10, '2026-09-11T20:06:00Z')];
        rerender({ ids: ['e1', 'e2'] });
        await waitFor(() => expect(result.current.e2).toBeDefined());
        expect(result.current.e1.payload.minute, 'la fotografia ha riportato indietro il minuto').toBe(70);
    });

    it('righe di altri sport o di eventi non richiesti restano fuori', async () => {
        hoisted.rows = [
            row('e1', 52, '2026-09-11T20:00:00Z'),
            { ...row('t1', 3, '2026-09-11T20:00:00Z'), sport: 'tennis' },
            row('altro', 1, '2026-09-11T20:00:00Z'),
        ];
        const { result } = renderHook(() => useScanLiveFeedRows(['e1']));
        await waitFor(() => expect(result.current.e1).toBeDefined());
        expect(Object.keys(result.current)).toEqual(['e1']);
    });

    it('una SELECT fallita non rompe l’hook (scanner/migrazione assenti)', async () => {
        const { fetchScanRows } = await import('@/lib/safeStrategyScan');
        vi.mocked(fetchScanRows).mockRejectedValueOnce(new Error('migrazione assente'));
        const { result } = renderHook(() => useScanLiveFeedRows(['e1']));
        await waitFor(() => expect(hoisted.subCalls).toBe(1));
        expect(result.current).toEqual({});
    });

    it('la cancellazione di una riga la toglie dalla mappa', async () => {
        hoisted.rows = [row('e1', 52, '2026-09-11T20:00:00Z')];
        const { result } = renderHook(() => useScanLiveFeedRows(['e1']));
        await waitFor(() => expect(result.current.e1).toBeDefined());
        act(() => { hoisted.emit?.({ type: 'delete', eventId: 'e1' }); });
        await waitFor(() => expect(result.current.e1).toBeUndefined());
    });
});

describe('liveScoreLabel', () => {
    it('"52′ · 1-0" dal payload; null se manca un pezzo', () => {
        expect(liveScoreLabel({ minute: 52, score_home: 1, score_away: 0 } as never)).toBe('52′ · 1-0');
        expect(liveScoreLabel({ minute: null, score_home: 1, score_away: 0 } as never)).toBeNull();
        expect(liveScoreLabel({ minute: 52, score_home: null, score_away: 0 } as never)).toBeNull();
        expect(liveScoreLabel(null)).toBeNull();
        expect(liveScoreLabel(undefined)).toBeNull();
    });
});
