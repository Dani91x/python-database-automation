// ============================================================================
// interruttoriUscite.test.ts — 25/09: lettura e scrittura dell'interruttore
// «Uscite automatiche» per singolo bot. Le regole sono lo SPECCHIO del
// servizio: Omega `uscite_protezione`, Mike `config.merge_params`, Safe
// `bot_service.normalize_uscite_automatiche`, scalper `applica_uscite_automatiche`.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: (...a: unknown[]) => rpc(...a), from: vi.fn(), channel: vi.fn() },
}));
const updateOmegaParams = vi.fn(async () => ({}));
const updateMikeParams = vi.fn(async () => ({}));
const updateSafeParams = vi.fn(async () => ({}));
vi.mock('@/lib/omega', async (orig) => ({ ...(await orig() as object), updateOmegaParams: (...a: unknown[]) => updateOmegaParams(...a as []) }));
vi.mock('@/lib/mike', async (orig) => ({ ...(await orig() as object), updateMikeParams: (...a: unknown[]) => updateMikeParams(...a as []) }));
vi.mock('@/lib/safeBot', async (orig) => ({ ...(await orig() as object), updateSafeParams: (...a: unknown[]) => updateSafeParams(...a as []) }));

import {
    interruttoreDi, statoUscite, usciteInterruttori, paramsConUscite, usciteSafeDi,
    usciteSessioniScalper, conPosizioniAperte, creaInterruttori, UsciteNonGestiteQui,
    INTERRUTTORI, type Interruttore,
} from '@/lib/interruttori';
import type { Bot } from '@/lib/controlRoom';

beforeEach(() => { vi.clearAllMocks(); rpc.mockResolvedValue({ data: 3, error: null }); });

describe('lettura: specchio del servizio', () => {
    it('Omega: solo «automatico» vale automatiche (fail-closed come omega_config)', () => {
        const o = interruttoreDi('omega');
        expect(statoUscite(o, { uscite_protezione: 'automatico' })).toEqual({ automatiche: true });
        expect(statoUscite(o, { uscite_protezione: ' Automatico ' })).toEqual({ automatiche: true });
        expect(statoUscite(o, { uscite_protezione: 'avvisa_e_proponi' })).toEqual({ automatiche: false });
        expect(statoUscite(o, { stake: 1 })).toEqual({ automatiche: false });
        expect(statoUscite(o, null)).toEqual({ automatiche: null });
    });

    it('Mike: assente = automatiche; stringhe come config._coerce', () => {
        const m = interruttoreDi('mike');
        expect(statoUscite(m, { stake: 10 })).toEqual({ automatiche: true });
        expect(statoUscite(m, { uscite_automatiche: false })).toEqual({ automatiche: false });
        expect(statoUscite(m, { uscite_automatiche: 'false' })).toEqual({ automatiche: false });
        expect(statoUscite(m, { uscite_automatiche: 'true' })).toEqual({ automatiche: true });
    });

    it('Safe: la mappa per strategia, il tennis ripiega sul cancelletto storico', () => {
        expect(usciteSafeDi({}, 'base')).toBe(true);
        expect(usciteSafeDi({ tennis_exit_approval: true }, 'tennis')).toBe(false);
        expect(usciteSafeDi({ tennis_exit_approval: true, uscite_automatiche: { tennis: true } }, 'tennis')).toBe(true);
        expect(usciteSafeDi({ uscite_automatiche: { base: 'false' } }, 'base')).toBe(true);
        expect(usciteSafeDi({ uscite_automatiche: { esatto: false } }, 'esatto')).toBe(false);
        expect(statoUscite(interruttoreDi('safe-punta'), { uscite_automatiche: { punta: false } }))
            .toEqual({ automatiche: false });
        expect(statoUscite(interruttoreDi('safe-model'), { uscite_automatiche: { model: false } }))
            .toEqual({ automatiche: false });
    });

    it('righe SENZA interruttore qui: Safe «a mano» e i bot tennis', () => {
        expect(statoUscite(interruttoreDi('safe-manual'), { a: 1 })).toBeNull();
        const tennis = INTERRUTTORI.filter((i) => i.sport === 'tennis' && i.bot !== 'safe');
        expect(tennis.length).toBeGreaterThan(0);
        for (const i of tennis) expect(statoUscite(i, { a: 1 })).toBeNull();
    });

    it('usciteInterruttori copre omega, mike, scalper e le 5 strategie di Safe con uscite', () => {
        const params: Partial<Record<Bot, Record<string, unknown>>> = {
            omega: { uscite_protezione: 'avvisa_e_proponi' }, mike: { stake: 10 },
            safe: { tennis_exit_approval: true }, scalper: usciteSessioniScalper([]),
        };
        const out = usciteInterruttori(INTERRUTTORI, (b) => params[b] ?? null);
        expect(Object.keys(out).sort()).toEqual(
            ['mike', 'omega', 'safe-base', 'safe-esatto', 'safe-model', 'safe-punta', 'safe-tennis', 'scalper']);
        expect(out.omega?.automatiche).toBe(false);
        expect(out['safe-tennis']?.automatiche).toBe(false);
        expect(out['safe-base']?.automatiche).toBe(true);
    });

    it('scalper: aggregato delle sessioni attive', () => {
        const attiva = (p: Record<string, unknown> | null) => ({ status: 'running', params: p });
        expect(usciteSessioniScalper([]).uscite_automatiche).toBe(true);
        expect(usciteSessioniScalper([attiva({ uscite_automatiche: false }), attiva({ uscite_automatiche: false })]))
            .toEqual({ uscite_automatiche: false });
        expect(usciteSessioniScalper([attiva({}), { status: 'stopped', params: { uscite_automatiche: false } }]))
            .toEqual({ uscite_automatiche: true });
        const misto = usciteSessioniScalper([attiva({}), attiva({ uscite_automatiche: false })]);
        expect(misto.uscite_automatiche).toBeNull();
        expect(statoUscite(interruttoreDi('scalper'), misto)).toEqual({ automatiche: null, nota: 'sessioni con scelte diverse' });
    });

    it('posizioni aperte per riga: Safe per strategia (gamba), da quanti minuti la piu’ vecchia', () => {
        const now = Date.parse('2026-09-25T12:00:00Z');
        const out = conPosizioniAperte(
            { mike: { automatiche: false }, 'safe-tennis': { automatiche: false }, 'safe-base': { automatiche: true } },
            [
                { bot: 'mike', piazzataAt: '2026-09-25T11:50:30Z' },
                { bot: 'mike', piazzataAt: '2026-09-25T11:55:00Z' },
                { bot: 'safe', piazzataAt: '2026-09-25T11:30:00Z', gamba: 'Tennis' },
                { bot: 'safe', piazzataAt: '2026-09-25T11:00:00Z', gamba: 'esatto' },
            ],
            now,
        );
        expect(out.mike).toEqual({ automatiche: false, aperte: 2, daMin: 9 });
        expect(out['safe-tennis']).toEqual({ automatiche: false, aperte: 1, daMin: 30 });
        expect(out['safe-base']).toEqual({ automatiche: true, aperte: 0, daMin: null });
    });
});

describe('scrittura: una chiave cambia, il resto resta', () => {
    const correnti = { stake: 10, altro: { x: 1 }, uscite_automatiche: { base: false } };

    it('Omega scrive uscite_protezione', () => {
        expect(paramsConUscite(interruttoreDi('omega'), { a: 1 }, true))
            .toEqual({ a: 1, uscite_protezione: 'automatico' });
        expect(paramsConUscite(interruttoreDi('omega'), { a: 1 }, false))
            .toEqual({ a: 1, uscite_protezione: 'avvisa_e_proponi' });
    });

    it('Mike scrive il booleano', () => {
        expect(paramsConUscite(interruttoreDi('mike'), { stake: 10 }, false))
            .toEqual({ stake: 10, uscite_automatiche: false });
    });

    it('Safe tocca SOLO la sua strategia; il tennis riallinea il cancelletto', () => {
        const p = paramsConUscite(interruttoreDi('safe-esatto'), correnti, false);
        expect(p).toEqual({ stake: 10, altro: { x: 1 }, uscite_automatiche: { base: false, esatto: false } });
        expect(correnti.uscite_automatiche).toEqual({ base: false }), 'nessuna mutazione dei correnti';
        const t = paramsConUscite(interruttoreDi('safe-tennis'), correnti, true);
        expect(t.uscite_automatiche).toEqual({ base: false, tennis: true });
        expect(t.tennis_exit_approval).toBe(false);
        const t2 = paramsConUscite(interruttoreDi('safe-tennis'), correnti, false);
        expect(t2.tennis_exit_approval).toBe(true);
    });

    it('Safe «a mano» e bot tennis: rifiutato', () => {
        expect(() => paramsConUscite(interruttoreDi('safe-manual'), {}, true)).toThrow(UsciteNonGestiteQui);
    });
});

describe('comando cambiaUscite: la RPC giusta con i parametri composti', () => {
    function comandi(params: Partial<Record<Bot, Record<string, unknown>>>) {
        const dopo = vi.fn();
        const c = creaInterruttori({
            params: (b) => params[b] ?? null,
            servizio: () => ({ inCorsa: true, modalita: 'paper' }),
            obiettivoOmega: () => 10,
        }, dopo);
        return { c, dopo };
    }

    it('Mike -> mike_update_params con TUTTI i parametri + la chiave', async () => {
        const { c, dopo } = comandi({ mike: { stake: 10, reentry_enabled: true } });
        await c.cambiaUscite!('mike', false);
        expect(updateMikeParams).toHaveBeenCalledWith({ stake: 10, reentry_enabled: true, uscite_automatiche: false });
        expect(dopo).toHaveBeenCalled();
    });

    it('Omega -> omega_update_params({params})', async () => {
        const { c } = comandi({ omega: { v3_stake_eur: 1 } });
        await c.cambiaUscite!('omega', true);
        expect(updateOmegaParams).toHaveBeenCalledWith({ params: { v3_stake_eur: 1, uscite_protezione: 'automatico' } });
    });

    it('Safe base -> safe_update_params con la mappa', async () => {
        const { c } = comandi({ safe: { variants: ['base'], strategy_modes: {} } });
        await c.cambiaUscite!('safe-base', false);
        expect(updateSafeParams).toHaveBeenCalledWith({
            variants: ['base'], strategy_modes: {}, uscite_automatiche: { base: false },
        });
    });

    it('Scalper -> RPC scalper_uscite_automatiche', async () => {
        const { c } = comandi({});
        await c.cambiaUscite!('scalper', false);
        expect(rpc).toHaveBeenCalledWith('scalper_uscite_automatiche', { p_automatiche: false });
    });

    it('parametri non letti: niente scrittura', async () => {
        const { c } = comandi({ mike: {} });
        await expect(c.cambiaUscite!('mike', false)).rejects.toThrow();
        expect(updateMikeParams).not.toHaveBeenCalled();
    });

    it('bot tennis: rifiutato (altro perimetro)', async () => {
        const { c } = comandi({});
        const tennis = INTERRUTTORI.find((i: Interruttore) => i.sport === 'tennis' && i.bot !== 'safe')!;
        await expect(c.cambiaUscite!(tennis.id, false)).rejects.toBeInstanceOf(UsciteNonGestiteQui);
    });
});
