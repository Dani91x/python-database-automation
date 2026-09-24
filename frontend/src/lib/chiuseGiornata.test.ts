// ============================================================================
// chiuseGiornata.test.ts - UNA giornata alla volta, memorizzata (24/09).
//
// "Posizioni chiuse / storico: e' LENTISSIMO nel caricamento" (utente).
// Qui si prova che: la RPC nuova e' chiamata con giornata E modalita'
// (mai paper+live insieme); tornare su una giornata gia' vista non rilegge;
// oggi scade; "rileggi" forza; una lettura caduta non resta in memoria; senza
// la migrazione si ripiega sulle RPC di storico e lo si DICE.
// Le risposte finte hanno le chiavi di `to_jsonb(t.*)` delle tabelle vere.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import {
    chiuseGiornata, dimenticaChiuseGiornata, leggiChiuseGiornata, righeDaRisposta, righeDaStorico,
    RPC_CHIUSE_GIORNATA, SCADENZA_OGGI_MS, type ChiuseGiornata,
} from './chiuseGiornata';
import { normalizeDayTrades } from './dailyHistory';
import { posizioniChiuse } from './posizioniChiuse';

const rpc = supabase.rpc as unknown as ReturnType<typeof vi.fn>;

/** riga di `omega_trades` com'e' in `to_jsonb(t.*)` */
function omegaRiga(over: Record<string, unknown>) {
    return {
        id: 1, event_id: 'E1', event_name: 'Inter - Milan', market_id: '1.1', selection_id: 5,
        runner_name: '1 - 0', side: 'lay', price: 7, size: 2, liability: 12, status: 'won', pnl: 2,
        mode: 'live', phase: 'ft_cs', origin: 'auto', placed_at: '2026-09-23T10:00:00+00:00',
        settled_at: '2026-09-23T12:00:00+00:00', closes_trade_id: null, bet_id: '111', meta: null,
        pnl_betfair: 1.9, commissione_betfair: 0.1, pnl_betfair_settled_at: '2026-09-23T12:01:00+00:00',
        ...over,
    };
}

/** riga di `tennis_live_orders` com'e' in `to_jsonb(o.*)` */
function tennisRiga(over: Record<string, unknown>) {
    return {
        id: 50, bet_id: 'T50', client_order_ref: 'awtq50', request_id: 50, mode: 'live',
        source: 'tennis_swing', event_id: 'T1', market_id: '1.9', selection_id: 77, handicap: 0,
        side: 'back', order_type: 'LIMIT', price: 2, size: 1, size_matched: 1, size_remaining: 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 2,
        status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: '2026-09-23T09:00:00+00:00',
        matched_at: null, updated_at: '2026-09-23T11:00:00+00:00', pnl: 1, commission: 0.05,
        settled_at: '2026-09-23T11:00:00+00:00', pnl_betfair: null, pnl_betfair_settled_at: null,
        ...over,
    };
}

function finta(giorno: string, modo: 'live' | 'paper', n = 0): ChiuseGiornata {
    return { giorno, modo, righe: [], fonte: 'rpc', avvisi: [], lettoAlle: n };
}

beforeEach(() => {
    dimenticaChiuseGiornata();
    rpc.mockReset();
});

describe('la RPC della giornata', () => {
    it('e\' chiamata con la giornata e UNA modalita\'', async () => {
        rpc.mockResolvedValueOnce({ data: { omega: [], safe: [], mike: [], tennis: [] }, error: null });
        const g = await leggiChiuseGiornata('2026-09-23', 'live');
        expect(rpc).toHaveBeenCalledWith(RPC_CHIUSE_GIORNATA, { p_day: '2026-09-23', p_mode: 'live' });
        expect(g.fonte).toBe('rpc');
        expect(g.avvisi).toEqual([]);
    });

    it('le righe tornano con il bot, e i bot tennis con il legame mancante dichiarato', () => {
        const righe = righeDaRisposta({
            omega: [omegaRiga({ id: 1 }), omegaRiga({ id: 2, closes_trade_id: 1, status: 'lost', pnl: -1, pnl_betfair: -1 })],
            safe: [{ ...omegaRiga({ id: 1 }), sport: 'tennis', selection_name: 'Sinner' }],
            mike: [],
            tennis: [tennisRiga({ id: 50 }), tennisRiga({ id: 51, settled_at: null })],
        });
        expect(righe.map((r) => `${r.__bot}:${r.id}`)).toEqual(['omega:1', 'omega:2', 'safe:1', 'tennis_swing:50']);
        expect(righe.find((r) => r.__bot === 'safe')?.sport).toBe('tennis');
        expect(righe.find((r) => r.__bot === 'tennis_swing')?.__senzaLegame).toBe(true);
        const pos = posizioniChiuse(righe);
        const omega = pos.find((p) => p.bot === 'omega');
        expect(omega?.pnlGlobale).toBe(0.9);        // 1,90 - 1,00 dal netto di Betfair
        expect(omega?.fontePnl).toBe('betfair');
    });

    it('un errore vero della RPC si propaga (la pagina lo mostra)', async () => {
        rpc.mockResolvedValueOnce({ data: null, error: { message: 'permission denied' } });
        await expect(leggiChiuseGiornata('2026-09-23', 'live')).rejects.toThrow('permission denied');
    });
});

describe('ripiego senza migrazione: dichiarato, e mai due modalita\' insieme', () => {
    it('usa le RPC di storico, filtra la modalita\' e lo DICE', async () => {
        rpc.mockImplementation(async (nome: string) => {
            if (nome === RPC_CHIUSE_GIORNATA) {
                return { data: null, error: { message: 'Could not find the function public.get_posizioni_chiuse_giornata' } };
            }
            if (nome === 'get_omega_day_trades') {
                return {
                    data: [{
                        ...omegaRiga({ id: 1 }), total_pnl: 1, placed_in_day: true, settled_in_day: true,
                        closes: [omegaRiga({ id: 2, closes_trade_id: 1, pnl: -1, status: 'lost' })],
                    }, {
                        ...omegaRiga({ id: 3, mode: 'paper' }), total_pnl: 1, placed_in_day: true,
                        settled_in_day: true, closes: [],
                    }],
                    error: null,
                };
            }
            return { data: [], error: null };
        });
        const g = await leggiChiuseGiornata('2026-09-23', 'live');
        expect(g.fonte).toBe('ripiego');
        expect(g.avvisi.join(' ')).toMatch(/ripiego/i);
        expect(g.righe.map((r) => r.id).sort()).toEqual([1, 2]);   // la paper (#3) resta fuori
    });

    it('righeDaStorico appiattisce apertura e chiusure senza i campi calcolati', () => {
        const piatte = righeDaStorico(normalizeDayTrades([{
            ...omegaRiga({ id: 1 }), total_pnl: 1, placed_in_day: true, settled_in_day: true,
            closes: [omegaRiga({ id: 2, closes_trade_id: 1 })],
        }]), 'omega', 'calcio');
        expect(piatte.map((r) => r.id)).toEqual([1, 2]);
        expect('closes' in piatte[0]).toBe(false);
        expect('total_pnl' in piatte[0]).toBe(false);
        expect(piatte[1].closes_trade_id).toBe(1);
    });
});

describe('memoria per giornata', () => {
    it('una giornata passata gia\' letta NON si rilegge', async () => {
        const leggi = vi.fn(async (g: string, m: 'live' | 'paper') => finta(g, m));
        await chiuseGiornata('2026-09-20', 'live', { oggi: '2026-09-24', leggi });
        await chiuseGiornata('2026-09-20', 'live', { oggi: '2026-09-24', leggi, ora: Date.now() + 86_400_000 });
        expect(leggi).toHaveBeenCalledTimes(1);
    });

    it('live e paper sono DUE letture diverse', async () => {
        const leggi = vi.fn(async (g: string, m: 'live' | 'paper') => finta(g, m));
        await chiuseGiornata('2026-09-20', 'live', { oggi: '2026-09-24', leggi });
        await chiuseGiornata('2026-09-20', 'paper', { oggi: '2026-09-24', leggi });
        expect(leggi).toHaveBeenCalledTimes(2);
        expect(leggi.mock.calls.map((c) => c[1])).toEqual(['live', 'paper']);
    });

    it('oggi scade dopo la sua finestra, e "rileggi" forza', async () => {
        const leggi = vi.fn(async (g: string, m: 'live' | 'paper') => finta(g, m));
        const t0 = 1_000_000;
        await chiuseGiornata('2026-09-24', 'live', { oggi: '2026-09-24', leggi, ora: t0 });
        await chiuseGiornata('2026-09-24', 'live', { oggi: '2026-09-24', leggi, ora: t0 + 1_000 });
        expect(leggi).toHaveBeenCalledTimes(1);
        await chiuseGiornata('2026-09-24', 'live', { oggi: '2026-09-24', leggi, ora: t0 + SCADENZA_OGGI_MS + 1 });
        expect(leggi).toHaveBeenCalledTimes(2);
        await chiuseGiornata('2026-09-24', 'live', { oggi: '2026-09-24', leggi, ora: t0 + SCADENZA_OGGI_MS + 2, forza: true });
        expect(leggi).toHaveBeenCalledTimes(3);
    });

    it('una lettura caduta NON resta in memoria', async () => {
        const leggi = vi.fn()
            .mockRejectedValueOnce(new Error('rete'))
            .mockResolvedValueOnce(finta('2026-09-20', 'live'));
        await expect(chiuseGiornata('2026-09-20', 'live', { oggi: '2026-09-24', leggi })).rejects.toThrow('rete');
        await chiuseGiornata('2026-09-20', 'live', { oggi: '2026-09-24', leggi });
        expect(leggi).toHaveBeenCalledTimes(2);
    });
});
