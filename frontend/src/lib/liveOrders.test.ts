// Test logica pura di liveOrders.ts (helper di legalizzazione lay informativi).
// Le funzioni RPC (sendLiveOrderCommand/fetchLiveOrders/fetchLivePositions) NON
// sono testate qui: richiederebbero la rete/Supabase. Verifichiamo solo la
// matematica lay size<->liability (mirror dei vettori MATEMATICA del backend).
import { describe, it, expect, vi, beforeEach } from 'vitest';

// liveOrders.ts importa il client Supabase, che in fase di import costruisce
// createClient(URL, KEY). In ambiente test le VITE_SUPABASE_* non esistono →
// "supabaseUrl is required" alla collection. Qui testiamo SOLO matematica pura
// (nessuna RPC), quindi mockiamo il modulo client per evitare la rete/login e
// non alterare il comportamento runtime di produzione.
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import {
    layLiabilityFromSize,
    laySizeFromLiability,
    shouldResetLiveConfirm,
    requestRiskRule,
    cancelRiskRule,
    fetchRiskRules,
    sendCashoutAll,
    sendCashoutEvent,
    sendDutch,
    fetchXhedge,
    getLiveSettings,
    setKillSwitch,
    setLiveSettings,
    fetchLiveAudit,
} from './liveOrders';

// accesso tipizzato al mock rpc (definito sopra via vi.mock).
const rpc = supabase.rpc as unknown as ReturnType<typeof vi.fn>;
beforeEach(() => rpc.mockReset());

// Helper: simula il ciclo enqueue+polling di sendLiveOrderCommand.
//   request_betfair_live_order → reqId
//   get_betfair_live_order     → { status:'done', result:{ ok:true, ... } }
// così i test di FORMA payload possono ispezionare la prima chiamata rpc senza rete.
function mockEnqueueDone(reqId = 1): void {
    rpc.mockImplementation((fn: string) => {
        if (fn === 'request_betfair_live_order') return Promise.resolve({ data: reqId, error: null });
        if (fn === 'get_betfair_live_order') {
            return Promise.resolve({ data: { status: 'done', result: { ok: true, action: 'x', mode: 'live' } }, error: null });
        }
        return Promise.resolve({ data: null, error: null });
    });
}
// payload della prima enqueue (request_betfair_live_order) = p passato all'RPC.
function firstEnqueueP(): Record<string, unknown> {
    const call = rpc.mock.calls.find((c) => c[0] === 'request_betfair_live_order');
    return (call?.[1] as { p: Record<string, unknown> }).p;
}

describe('lay size <-> liability', () => {
    it('liability = size*(price-1)', () => {
        expect(layLiabilityFromSize(5, 3.0)).toBe(10);   // 5*(3-1)=10
        expect(layLiabilityFromSize(4, 6.0)).toBe(20);   // 4*(6-1)=20
        expect(layLiabilityFromSize(5, 2.5)).toBe(7.5);  // 5*1.5=7.5
    });
    it('size = liability/(price-1)', () => {
        expect(laySizeFromLiability(10, 3.0)).toBe(5);   // 10/2=5
        expect(laySizeFromLiability(20, 5.0)).toBe(5);   // 20/4=5
        expect(laySizeFromLiability(7.5, 2.5)).toBe(5);  // 7.5/1.5=5
    });
    it('round-trip coerente', () => {
        const liab = layLiabilityFromSize(5, 3.0);
        expect(laySizeFromLiability(liab, 3.0)).toBe(5);
    });
    it('input non validi → 0 (no NaN/Infinity)', () => {
        expect(layLiabilityFromSize(5, 1.0)).toBe(0);    // price-1=0
        expect(laySizeFromLiability(10, 1.0)).toBe(0);
        expect(layLiabilityFromSize(NaN, 3.0)).toBe(0);
    });
});

// CODE-MED-2: la conferma "ordine REALE" deve essere one-shot, non permanente.
describe('shouldResetLiveConfirm (conferma LIVE one-shot)', () => {
    it('LIVE + esito ok → resetta la conferma', () => {
        expect(shouldResetLiveConfirm(true, true)).toBe(true);
    });
    it('LIVE + esito negativo → NON resetta (la spunta resta per ritentare)', () => {
        expect(shouldResetLiveConfirm(true, false)).toBe(false);
    });
    it('PAPER → mai resetta, qualunque esito (comportamento PAPER invariato)', () => {
        expect(shouldResetLiveConfirm(false, true)).toBe(false);
        expect(shouldResetLiveConfirm(false, false)).toBe(false);
    });
});

// ---------- risk engine: guardie + costruzione payload (mock rpc, no rete) ----------
describe('requestRiskRule (arma regola idempotente)', () => {
    it('offset/stop_loss/trailing_stop SENZA entry_price → throw (no enqueue)', async () => {
        await expect(requestRiskRule({
            mode: 'live', ruleType: 'offset', marketId: '1.1', selectionId: 47,
            entrySide: 'back', params: { offset_ticks: 3 },
        })).rejects.toThrow(/entry_price/);
        expect(rpc).not.toHaveBeenCalled();
    });

    it('take_profit può armare senza entry_price (usa target_amount)', async () => {
        rpc.mockResolvedValue({ data: 77, error: null });
        const id = await requestRiskRule({
            mode: 'paper', ruleType: 'take_profit', marketId: '1.1', selectionId: 47,
            entrySide: 'back', params: { target_amount: 5 },
        });
        expect(id).toBe(77);
    });

    it('costruisce p con client_ref UUID, rule_type e handicap di default, e ritorna l\'id', async () => {
        rpc.mockResolvedValue({ data: 123, error: null });
        const id = await requestRiskRule({
            mode: 'live', ruleType: 'stop_loss', marketId: '1.234', selectionId: 47,
            entrySide: 'lay', entryPrice: 3.5, entrySize: 10, params: { trigger_ticks: 4, greening: true },
        });
        expect(id).toBe(123);
        expect(rpc).toHaveBeenCalledWith('request_live_risk_rule', expect.objectContaining({
            p: expect.objectContaining({
                rule_type: 'stop_loss', market_id: '1.234', selection_id: 47,
                entry_side: 'lay', entry_price: 3.5, entry_size: 10, handicap: 0,
            }),
        }));
        const p = rpc.mock.calls[0][1].p;
        expect(typeof p.client_ref).toBe('string');
        expect(p.client_ref).toMatch(/[0-9a-f-]{36}/i);
    });
});

describe('cancelRiskRule / fetchRiskRules', () => {
    it('cancelRiskRule passa p_id e ritorna la riga', async () => {
        rpc.mockResolvedValue({ data: { id: 9, status: 'cancelled' }, error: null });
        const row = await cancelRiskRule(9);
        expect(rpc).toHaveBeenCalledWith('cancel_live_risk_rule', { p_id: 9 });
        expect(row?.status).toBe('cancelled');
    });
    it('fetchRiskRules estrae rows da { rows }', async () => {
        rpc.mockResolvedValue({ data: { rows: [{ id: 1 }, { id: 2 }] }, error: null });
        const rows = await fetchRiskRules('1.1');
        expect(rows).toHaveLength(2);
    });
    it('fetchRiskRules accetta anche un array nudo', async () => {
        rpc.mockResolvedValue({ data: [{ id: 1 }], error: null });
        expect(await fetchRiskRules('1.1')).toHaveLength(1);
    });
});

// Le guardie di sendDutch/sendCashoutAll scattano PRIMA di qualunque enqueue.
describe('sendDutch / sendCashoutAll — guardie money-critical', () => {
    it('sendDutch rifiuta < 2 selezioni (no enqueue)', async () => {
        await expect(sendDutch({
            marketId: '1.1', mode: 'live', selections: [{ selection_id: 1, price: 2.0 }],
            totalStake: 10, side: 'back', dutchMode: 'equal',
        })).rejects.toThrow(/2 selezioni/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('sendDutch rifiuta total_stake <= 0', async () => {
        await expect(sendDutch({
            marketId: '1.1', mode: 'live', selections: [{ selection_id: 1, price: 2 }, { selection_id: 2, price: 3 }],
            totalStake: 0, side: 'back', dutchMode: 'equal',
        })).rejects.toThrow(/total_stake/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('sendCashoutAll rifiuta fraction <= 0 (no enqueue)', async () => {
        await expect(sendCashoutAll({ marketId: '1.1', mode: 'live', fraction: 0 }))
            .rejects.toThrow(/fraction/);
        expect(rpc).not.toHaveBeenCalled();
    });
});

// ---------- cashout_event (intero evento) ----------
describe('sendCashoutEvent', () => {
    it('rifiuta fraction <= 0 PRIMA di ogni enqueue', async () => {
        await expect(sendCashoutEvent({ marketId: '1.1', mode: 'live', fraction: 0 }))
            .rejects.toThrow(/fraction/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('fraction totale (default) → action cashout_event senza params', async () => {
        mockEnqueueDone();
        const res = await sendCashoutEvent({ marketId: '1.234', mode: 'live' });
        expect(res.ok).toBe(true);
        const p = firstEnqueueP();
        expect(p.action).toBe('cashout_event');
        expect(p.market_id).toBe('1.234');
        expect(p.params).toBeUndefined();
    });
    it('fraction parziale → params.fraction arrotondata', async () => {
        mockEnqueueDone();
        await sendCashoutEvent({ marketId: '1.1', mode: 'paper', fraction: 0.3333 });
        expect((firstEnqueueP().params as { fraction: number }).fraction).toBe(0.333);
    });
});

// ---------- fetchXhedge (analisi x-hedge per evento) ----------
describe('fetchXhedge', () => {
    it('chiama get_live_xhedge con p_event_id ed estrae rows', async () => {
        rpc.mockResolvedValue({ data: { rows: [{ event_id: '27:9', mode: 'live', analysis: {}, updated_at: 't' }] }, error: null });
        const rows = await fetchXhedge('27:9');
        expect(rpc).toHaveBeenCalledWith('get_live_xhedge', { p_event_id: '27:9' });
        expect(rows).toHaveLength(1);
        expect(rows[0].event_id).toBe('27:9');
    });
    it('accetta anche un array nudo', async () => {
        rpc.mockResolvedValue({ data: [{ event_id: '1', mode: 'paper', analysis: {}, updated_at: 't' }], error: null });
        expect(await fetchXhedge('1')).toHaveLength(1);
    });
    it('data senza rows → array vuoto', async () => {
        rpc.mockResolvedValue({ data: null, error: null });
        expect(await fetchXhedge('1')).toEqual([]);
    });
    it('error → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'xhedge down' } });
        await expect(fetchXhedge('1')).rejects.toThrow('xhedge down');
    });
});

// ---------- Dutch v2: dutchMode 'target' + pricing ----------
describe('sendDutch v2 (target + pricing)', () => {
    it('target rifiuta target_profit <= 0 (no enqueue)', async () => {
        await expect(sendDutch({
            marketId: '1.1', mode: 'live', side: 'back', dutchMode: 'target',
            selections: [{ selection_id: 1, price: 2 }, { selection_id: 2, price: 3 }],
            targetProfit: 0,
        })).rejects.toThrow(/target_profit/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('pricing nominated rifiuta nominated_price non valido (no enqueue)', async () => {
        await expect(sendDutch({
            marketId: '1.1', mode: 'live', side: 'back', dutchMode: 'equal', totalStake: 10,
            selections: [{ selection_id: 1, price: 2 }, { selection_id: 2, price: 3 }],
            pricing: 'nominated', nominatedPrice: 1,
        })).rejects.toThrow(/nominated_price/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('target → params.mode=target, target_profit, niente total_stake', async () => {
        mockEnqueueDone();
        await sendDutch({
            marketId: '1.5', mode: 'live', side: 'lay', dutchMode: 'target',
            selections: [{ selection_id: 1, price: 2 }, { selection_id: 2, price: 3 }],
            targetProfit: 20, pricing: 'best',
        });
        const params = firstEnqueueP().params as Record<string, unknown>;
        expect(params.mode).toBe('target');
        expect(params.target_profit).toBe(20);
        expect(params.total_stake).toBeUndefined();
        expect(params.pricing).toBe('best');
    });
    it('nominated → params.pricing e nominated_price presenti', async () => {
        mockEnqueueDone();
        await sendDutch({
            marketId: '1.5', mode: 'live', side: 'back', dutchMode: 'equal', totalStake: 10,
            selections: [{ selection_id: 1, price: 2 }, { selection_id: 2, price: 3 }],
            pricing: 'nominated', nominatedPrice: 2.5,
        });
        const params = firstEnqueueP().params as Record<string, unknown>;
        expect(params.pricing).toBe('nominated');
        expect(params.nominated_price).toBe(2.5);
        expect(params.total_stake).toBe(10);
    });
});

// ---------- Risk v2: bracket + entry_bet_id + timing/on_inplay ----------
describe('requestRiskRule v2 (bracket / on_fill / entry_bet_id)', () => {
    it('bracket SENZA entry_bet_id → throw (no offset nudo)', async () => {
        await expect(requestRiskRule({
            mode: 'live', ruleType: 'bracket', marketId: '1.1', selectionId: 47,
            entrySide: 'back', entryPrice: 2.0, params: { offset_ticks: 3, stop_amount: 5 },
        })).rejects.toThrow(/entry_bet_id/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('timing on_fill SENZA entry_bet_id → throw', async () => {
        await expect(requestRiskRule({
            mode: 'live', ruleType: 'offset', marketId: '1.1', selectionId: 47,
            entrySide: 'back', params: { offset_ticks: 3, timing: 'on_fill' },
        })).rejects.toThrow(/entry_bet_id/);
        expect(rpc).not.toHaveBeenCalled();
    });
    it('on_fill con entry_bet_id NON richiede entry_price (deriva dal fill)', async () => {
        rpc.mockResolvedValue({ data: 55, error: null });
        const id = await requestRiskRule({
            mode: 'live', ruleType: 'offset', marketId: '1.1', selectionId: 47,
            entrySide: 'back', entryBetId: 'BET-9',
            params: { offset_ticks: 3, timing: 'on_fill', place_at_ticks: 2, on_inplay: 'rebaseline' },
        });
        expect(id).toBe(55);
        const p = rpc.mock.calls[0][1].p;
        expect(p.entry_bet_id).toBe('BET-9');
        expect(p.entry_price).toBeUndefined();
        expect(p.params.timing).toBe('on_fill');
        expect(p.params.place_at_ticks).toBe(2);
        expect(p.params.on_inplay).toBe('rebaseline');
    });
    it('bracket con entry_bet_id arma (entry_price non obbligatorio) e passa i params v2', async () => {
        rpc.mockResolvedValue({ data: 88, error: null });
        const id = await requestRiskRule({
            mode: 'live', ruleType: 'bracket', marketId: '1.1', selectionId: 47,
            entrySide: 'lay', entryBetId: 'BET-1',
            params: { offset_ticks: 4, stop_amount: 6, target_amount: 8, greening: true, trail_ticks: 2 },
        });
        expect(id).toBe(88);
        const p = rpc.mock.calls[0][1].p;
        expect(p.rule_type).toBe('bracket');
        expect(p.entry_bet_id).toBe('BET-1');
        expect(p.params.stop_amount).toBe(6);
        expect(p.params.target_amount).toBe(8);
        expect(p.params.trail_ticks).toBe(2);
    });
});

// ---------- Fase 6: controlli globali (settings + kill-switch + audit) ----------
describe('getLiveSettings', () => {
    it('chiama get_live_settings con args vuoti e ritorna la riga', async () => {
        const row = {
            id: 1, kill_switch: false, max_exposure_per_selection: 50,
            max_orders_per_min: 30, order_poll_sec: 1, risk_poll_sec: 2, updated_at: '2026-07-01T00:00:00Z',
        };
        rpc.mockResolvedValue({ data: row, error: null });
        const s = await getLiveSettings();
        expect(rpc).toHaveBeenCalledWith('get_live_settings', {});
        expect(s?.kill_switch).toBe(false);
        expect(s?.max_exposure_per_selection).toBe(50);
    });
    it('data null → ritorna null', async () => {
        rpc.mockResolvedValue({ data: null, error: null });
        expect(await getLiveSettings()).toBeNull();
    });
    it('error → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'boom' } });
        await expect(getLiveSettings()).rejects.toThrow('boom');
    });
});

describe('setKillSwitch', () => {
    it('passa p_on e ritorna lo stato aggiornato', async () => {
        rpc.mockResolvedValue({ data: { id: 1, kill_switch: true }, error: null });
        const s = await setKillSwitch(true);
        expect(rpc).toHaveBeenCalledWith('set_live_kill_switch', { p_on: true });
        expect(s?.kill_switch).toBe(true);
    });
    it('off → p_on false', async () => {
        rpc.mockResolvedValue({ data: { id: 1, kill_switch: false }, error: null });
        await setKillSwitch(false);
        expect(rpc).toHaveBeenCalledWith('set_live_kill_switch', { p_on: false });
    });
    it('error → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'nope' } });
        await expect(setKillSwitch(true)).rejects.toThrow('nope');
    });
});

describe('setLiveSettings', () => {
    it('invia il patch dentro { p } e ritorna la riga', async () => {
        rpc.mockResolvedValue({ data: { id: 1, max_orders_per_min: 10 }, error: null });
        const s = await setLiveSettings({ max_orders_per_min: 10, max_exposure_per_selection: null });
        expect(rpc).toHaveBeenCalledWith('set_live_settings', {
            p: { max_orders_per_min: 10, max_exposure_per_selection: null },
        });
        expect(s?.max_orders_per_min).toBe(10);
    });
    it('error → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'bad patch' } });
        await expect(setLiveSettings({ kill_switch: true })).rejects.toThrow('bad patch');
    });
});

describe('fetchLiveAudit', () => {
    it('default limit 100 ed estrae rows da { rows }', async () => {
        rpc.mockResolvedValue({ data: { rows: [{ id: 2 }, { id: 1 }] }, error: null });
        const rows = await fetchLiveAudit();
        expect(rpc).toHaveBeenCalledWith('get_live_audit', { p_limit: 100 });
        expect(rows).toHaveLength(2);
    });
    it('rispetta un limite esplicito', async () => {
        rpc.mockResolvedValue({ data: { rows: [] }, error: null });
        await fetchLiveAudit(50);
        expect(rpc).toHaveBeenCalledWith('get_live_audit', { p_limit: 50 });
    });
    it('data senza rows → array vuoto', async () => {
        rpc.mockResolvedValue({ data: null, error: null });
        expect(await fetchLiveAudit()).toEqual([]);
    });
    it('error → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'audit down' } });
        await expect(fetchLiveAudit()).rejects.toThrow('audit down');
    });
});


// ---------------------------------------------------------------------------
// A3 — buildGreenupParams: guardie money-critical (fix review MEDIUM)
// ---------------------------------------------------------------------------
import { buildGreenupParams } from './liveOrders';

describe('buildGreenupParams (A3)', () => {
    it('fraction <= 0 → errore', () => {
        expect(() => buildGreenupParams(0)).toThrow(/fraction/);
        expect(() => buildGreenupParams(-0.5)).toThrow(/fraction/);
    });
    it('targetPrice fuori (1, 1000] → errore', () => {
        expect(() => buildGreenupParams(undefined, 1)).toThrow(/targetPrice/);
        expect(() => buildGreenupParams(undefined, 1001)).toThrow(/targetPrice/);
        expect(() => buildGreenupParams(undefined, NaN)).toThrow(/targetPrice/);
    });
    it('cancelUnmatched + targetPrice insieme → errore (mai combinazione contraddittoria)', () => {
        expect(() => buildGreenupParams(undefined, 2.5, true)).toThrow(/cancelUnmatched/);
    });
    it('cancelUnmatched da solo → params.cancel_unmatched true', () => {
        expect(buildGreenupParams(undefined, undefined, true)).toEqual({ cancel_unmatched: true });
    });
    it('fraction parziale + cancelUnmatched: consentito dalla lib (la POLICY 100%-only è nel call-site)', () => {
        expect(buildGreenupParams(0.5, undefined, true)).toEqual({ fraction: 0.5, cancel_unmatched: true });
    });
    it('default: nessun param', () => {
        expect(buildGreenupParams()).toEqual({});
        expect(buildGreenupParams(1)).toEqual({});
    });
});
