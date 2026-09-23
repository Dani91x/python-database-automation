// ============================================================================
// useControlRoom.righeCanale.test.tsx - C6 b (23/09): la Control Room legge le
// righe dei bot dalla MAPPA PER RIGA, alimentata dal poll di 30 s e dai
// messaggi per riga dei canali locali (`*_posizioni`, `*_proposta`).
//
// Cosa si misura qui, sul hook vero (il modulo puro ha i suoi test in
// `lib/righeCanale.test.ts`):
//  1. canale muto: le posizioni sono quelle del database, fonte "database";
//  2. un messaggio `omega_posizioni` piu' fresco aggiorna la posizione;
//     uno piu' vecchio della lettura non la tocca;
//  3. chiave composta: Omega #7 e Safe #7 restano due posizioni distinte e
//     il messaggio `safe_posizioni_tennis` tocca solo Safe;
//  4. `safe_proposta` con la proposta decaduta la toglie subito;
//     `omega_proposta` idem per Omega;
//  5. nessuna lettura in piu': i topic nuovi non chiamano il database.
//
// I finti: le righe hanno le chiavi e i tipi della tabella vera, il messaggio
// e' la riga + la busta di `Betfair/stream/canale_bot.py`
// (`fonte`="canale", `_seq`, `_pubblicato_ms`), il push arriva come `d` del
// `{"t": topic, "d": ...}` di `lib/localChannel.ts`.
//
// FALSIFICAZIONE (23/09, esito nel referto): senza il filtro `propostaViva`
// il gruppo 4 diventa rosso; con il topic sbagliato nella tabella
// `TOPIC_POSIZIONI` il gruppo 2 diventa rosso; senza il confronto di
// freschezza il "messaggio vecchio" diventa rosso.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { OmegaTrade } from '@/lib/omega';
import type { SafeTrade } from '@/lib/safeBot';
import type { PropostaChiusura } from '@/lib/controlRoomProposte';
import type { PropostaUscitaOmega } from '@/lib/omegaProposte';

// ------------------------------------------------------ canale controllabile
type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
function spingi(sport: string, topic: string, d: unknown): void {
    for (const cb of iscritti.get(`${sport}:${topic}`) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn((sport: string) => ({
        getStatus: () => 'connected' as const,
        onStatus: () => () => { /* nessun cambio */ },
        subscribe: (topic: string, cb: Cb) => {
            const k = `${sport}:${topic}`;
            let s = iscritti.get(k);
            if (!s) { s = new Set(); iscritti.set(k, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));

vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig() as object),
    fetchScanRows: vi.fn(async () => []),
    fetchScanStatus: vi.fn(async () => null),
    subscribeScanRows: vi.fn(() => () => { /* nessun evento */ }),
    subscribeScanStatus: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig() as object),
    fetchOmegaState: vi.fn(async () => ({ control: null, aggregates: null, activity: [] })),
    fetchOmegaTrades: vi.fn(async () => []),
    fetchOmegaEvents: vi.fn(async () => []),
    updateOmegaParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
}));
vi.mock('@/lib/controlRoomProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposte: vi.fn(async () => []),
    subscribeProposte: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omegaProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposteOmega: vi.fn(async () => []),
    subscribeProposteOmega: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig() as object),
    fetchMissions: vi.fn(async () => ({ missions: [] })),
}));
vi.mock('@/lib/live', async (orig) => ({
    ...(await orig() as object),
    fetchLiveFollows: vi.fn(async () => []),
}));
vi.mock('@/lib/dailyHistory', async (orig) => ({
    ...(await orig() as object),
    fetchSafeDaily: vi.fn(async () => []),
}));
vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisFollows: vi.fn(async () => []),
    fetchTennisBotServices: vi.fn(async () => []),
    fetchTennisBotDaily: vi.fn(async () => []),
    fetchTennisBotOrdersToday: vi.fn(async () => []),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    fetchLiveAccount: vi.fn(async () => null),
    subscribeLiveAccount: vi.fn(() => () => { /* nessuna spinta */ }),
}));

import { fetchOmegaTrades } from '@/lib/omega';
import { fetchSafeState } from '@/lib/safeBot';
import { fetchProposte } from '@/lib/controlRoomProposte';
import { fetchProposteOmega } from '@/lib/omegaProposte';
import { useControlRoom } from '@/components/controlroom/useControlRoom';

// ------------------------------------------------------------------- finti

function rigaOmega(id: number, over: Partial<OmegaTrade> = {}): OmegaTrade & { commission: number | null } {
    return {
        id, event_id: '34567890', event_name: 'Inter v Milan',
        market_id: '1.234567890', selection_id: 1, runner_name: '1 - 0',
        side: 'lay', mode: 'paper', origin: 'auto', phase: 'ft_cs',
        price: 8.4, size: 1, liability: 7.4, commission: null, target: null,
        minute_at_entry: 12, score_at_entry: '0-0', kickoff: '2026-09-23T18:45:00+00:00',
        status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-23T19:00:00+00:00', settled_at: null,
        closes_trade_id: null, meta: {},
        ...over,
    };
}

function rigaSafe(id: number, over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id, event_id: '34567891', event_name: 'Sinner v Alcaraz', sport: 'tennis',
        strategy: 'tennis', market_id: '1.234567891', market_type: 'MATCH_ODDS',
        selection_id: 2, selection_name: 'Sinner', side: 'back', mode: 'paper',
        price: 1.9, size: 2, liability: null, commission: null,
        minute_at_entry: null, score_at_entry: null, status: 'open', pnl: 0,
        bet_id: null, placed_at: '2026-09-23T19:01:00+00:00', settled_at: null,
        origin: 'auto', closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

/** riga di `safe_strategy_requests` (SELECT * della lettura) */
function propostaSafe(id: number, over: Partial<PropostaChiusura> = {}): PropostaChiusura {
    return {
        id, kind: 'cashout', status: 'proposed',
        payload: { trade_id: 11, event_id: '34567891' } as PropostaChiusura['payload'],
        created_at: '2026-09-23T19:02:00+00:00', updated_at: '2026-09-23T19:02:00+00:00',
        ...over,
    };
}

/** riga di `get_omega_proposte` (5 chiavi, SENZA `status`) */
function propostaOmega(id: number): PropostaUscitaOmega {
    return {
        id, kind: 'cashout',
        payload: { trade_id: 7, event_id: '34567890' },
        created_at: '2026-09-23T19:03:00+00:00', updated_at: '2026-09-23T19:03:00+00:00',
    };
}

/** la riga intera di `omega_manual_requests` come la restituisce l'update */
function rigaTabellaPropostaOmega(id: number, status: string): Record<string, unknown> {
    return {
        id, kind: 'cashout', status,
        payload: { trade_id: 7, event_id: '34567890' },
        result: { decaduta: true, motivo: 'la condizione di uscita non regge piu\'' },
        created_at: '2026-09-23T19:03:00+00:00', updated_at: '2026-09-23T19:04:00+00:00',
    };
}

/** busta di `canale_bot.busta` */
function busta(riga: object, pubblicatoMs: number, seq: number): Record<string, unknown> {
    return { ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: pubblicatoMs };
}

beforeEach(() => {
    iscritti.clear();
    vi.mocked(fetchOmegaTrades).mockResolvedValue([]);
    vi.mocked(fetchSafeState).mockResolvedValue({ control: null, trades: [], aggregates: null } as never);
    vi.mocked(fetchProposte).mockResolvedValue([]);
    vi.mocked(fetchProposteOmega).mockResolvedValue([]);
});

async function montato() {
    const h = renderHook(() => useControlRoom());
    await waitFor(() => expect(h.result.current.caricamento).toBe(false));
    return h;
}

// ======================================================= 1) canale muto

describe('canale muto: la pagina e\' quella del database', () => {
    it('posizioni dal blocco e fonte "database"', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni.map((p) => p.id)).toEqual([7]));
        expect(result.current.posizioni[0].prezzo).toBe(8.4);
        expect(result.current.fonteRighe.omega.fonte).toBe('database');
        expect(result.current.etaRiga('omega', 7)?.fonte).toBe('database');
    });

    it('i topic per riga sono sottoscritti sui canali giusti, e non leggono il database', async () => {
        await montato();
        for (const k of ['omega:omega_posizioni', 'omega:omega_proposta',
            'safe:safe_posizioni_calcio', 'safe:safe_posizioni_tennis', 'safe:safe_proposta',
            'mike:mike_posizioni']) {
            expect(iscritti.get(k)?.size ?? 0).toBeGreaterThan(0);
        }
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => { spingi('omega', 'omega_posizioni', busta(rigaOmega(7), Date.now() + 1_000, 1)); });
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima);
    });
});

// ======================================================= 2) freschezza

describe('omega_posizioni: aggiorna solo se piu\' fresco', () => {
    it('messaggio fresco: la posizione cambia e la fonte diventa "locale"', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        act(() => {
            spingi('omega', 'omega_posizioni', busta(rigaOmega(7, { price: 6.2 }), Date.now() + 1_000, 3));
        });
        expect(result.current.posizioni[0].prezzo).toBe(6.2);
        expect(result.current.fonteRighe.omega.fonte).toBe('locale');
        expect(result.current.etaRiga('omega', 7)?.fonte).toBe('locale');
    });

    it('messaggio regolato: la posizione esce dalle aperte', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        act(() => {
            spingi('omega', 'omega_posizioni',
                busta(rigaOmega(7, { status: 'won', pnl: 0.95, settled_at: '2026-09-23T20:40:00+00:00' }), Date.now() + 1_000, 4));
        });
        expect(result.current.posizioni).toHaveLength(0);
    });

    it('messaggio piu\' vecchio della lettura: ignorato', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        act(() => {
            spingi('omega', 'omega_posizioni', busta(rigaOmega(7, { price: 2.0 }), Date.now() - 60_000, 99));
        });
        expect(result.current.posizioni[0].prezzo).toBe(8.4);
        expect(result.current.fonteRighe.omega.fonte).toBe('database');
    });

    it('messaggio per una riga che il database non ha: nessuna posizione nuova', async () => {
        const { result } = await montato();
        act(() => {
            spingi('omega', 'omega_posizioni', busta(rigaOmega(8), Date.now() + 1_000, 1));
        });
        expect(result.current.posizioni).toHaveLength(0);
    });
});

// ======================================================= 3) chiave composta

describe('chiave composta: Omega #7 e Safe #7 sono due posizioni', () => {
    it('il messaggio di Safe tocca solo Safe', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        vi.mocked(fetchSafeState).mockResolvedValue({ control: null, trades: [rigaSafe(7)], aggregates: null } as never);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(2));
        act(() => {
            spingi('safe', 'safe_posizioni_tennis', busta(rigaSafe(7, { price: 1.55 }), Date.now() + 1_000, 2));
        });
        const per = (b: string) => result.current.posizioni.find((p) => p.bot === b);
        expect(per('safe')?.prezzo).toBe(1.55);
        expect(per('omega')?.prezzo).toBe(8.4);
        expect(result.current.fonteRighe.omega.fonte).toBe('database');
        expect(result.current.fonteRighe.safe.fonte).toBe('locale');
    });

    it('una riga tennis arrivata sul topic del calcio si scarta', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ control: null, trades: [rigaSafe(7)], aggregates: null } as never);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        act(() => {
            spingi('safe', 'safe_posizioni_calcio', busta(rigaSafe(7, { price: 1.55 }), Date.now() + 1_000, 2));
        });
        expect(result.current.posizioni[0].prezzo).toBe(1.9);
    });
});

// ======================================================= 4) proposte

describe('*_proposta: una proposta decaduta sparisce subito', () => {
    it('Safe: `status` rejected dal canale toglie la proposta', async () => {
        vi.mocked(fetchProposte).mockResolvedValue([propostaSafe(21), propostaSafe(22)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.proposte.map((p) => p.proposta.id)).toEqual([21, 22]));
        act(() => {
            spingi('safe', 'safe_proposta',
                busta(propostaSafe(21, { status: 'rejected', updated_at: '2026-09-23T19:05:00+00:00' }), Date.now() + 1_000, 5));
        });
        expect(result.current.proposte.map((p) => p.proposta.id)).toEqual([22]);
    });

    it('Omega: la riga intera di omega_manual_requests (con `status`) toglie la proposta', async () => {
        vi.mocked(fetchProposteOmega).mockResolvedValue([propostaOmega(31)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.proposteOmega.map((p) => p.id)).toEqual([31]));
        act(() => {
            spingi('omega', 'omega_proposta', busta(rigaTabellaPropostaOmega(31, 'rejected'), Date.now() + 1_000, 6));
        });
        expect(result.current.proposteOmega).toEqual([]);
    });

    it('Omega: la proposta aggiornata ma ancora viva resta, col payload nuovo', async () => {
        vi.mocked(fetchProposteOmega).mockResolvedValue([propostaOmega(31)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.proposteOmega).toHaveLength(1));
        const viva = { ...rigaTabellaPropostaOmega(31, 'proposed'), payload: { trade_id: 7, event_id: '34567890', back_price: 4.2 } };
        act(() => { spingi('omega', 'omega_proposta', busta(viva, Date.now() + 1_000, 7)); });
        expect(result.current.proposteOmega).toHaveLength(1);
        expect(result.current.proposteOmega[0].payload.back_price).toBe(4.2);
    });
});
