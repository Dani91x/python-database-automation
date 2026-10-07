// 07/10 — «Applica bot» per tutti i bot: le regole pure del riquadro, sul
// catalogo VERO generato dal backend (replayBotCatalogo.ts).
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import {
    botDelloSport, famiglieScenari, gruppiParametri, minutoDiGioco, modalitaDisponibile,
    sostituzioni, testoValore, validaCampo,
} from './applicaBot';
import { CATALOGO_BOT } from './replayBotCatalogo';
import { payloadApplicaBot, type VoceParametro } from './replayBot';

const voce = (p: Partial<VoceParametro>): VoceParametro => ({
    chiave: 'x', etichetta: 'X', tipo: 'float', default: 1.5, min: 1.01, max: 2, passo: 0.01,
    unita: '', gruppo: 'Ingresso', scelte: null, ...p,
});

describe('catalogo per sport: calcio e tennis non si mischiano', () => {
    it('calcio = i sei bot calcio del registro, tennis = i cinque tennis', () => {
        expect(botDelloSport(CATALOGO_BOT, 'calcio').map(b => b.bot).sort()).toEqual(
            ['mike', 'omega', 'safe_base', 'safe_esatto', 'safe_punta', 'scalper_calcio']);
        expect(botDelloSport(CATALOGO_BOT, 'tennis').map(b => b.bot).sort()).toEqual(
            ['safe_tennis', 'tennis_flb', 'tennis_pro', 'tennis_scalper', 'tennis_swing']);
    });
    it('ogni bot ha almeno uno scenario', () => {
        for (const b of CATALOGO_BOT) expect(b.scenari.length, b.bot).toBeGreaterThan(0);
    });
});

describe('famiglie di scenari: la stessa prova in Prova e in Soldi veri simulati', () => {
    it('scalper maker: paper e base nella stessa famiglia', () => {
        const scalper = CATALOGO_BOT.find(b => b.bot === 'scalper_calcio')!;
        const maker = famiglieScenari(scalper).find(f => f.famiglia === 'Scalper - maker')!;
        expect(maker.modi.prova?.scenario).toBe('paper');
        expect(maker.modi.soldi_veri_simulati?.scenario).toBe('base');
    });
    it('una famiglia con una sola modalita\' usa quella', () => {
        const mike = CATALOGO_BOT.find(b => b.bot === 'mike')!;
        const f = famiglieScenari(mike)[0];
        expect(modalitaDisponibile(f, 'prova')).toBe('soldi_veri_simulati');
        const tennis = famiglieScenari(CATALOGO_BOT.find(b => b.bot === 'tennis_flb')!)[0];
        expect(modalitaDisponibile(tennis, 'soldi_veri_simulati')).toBe('prova');
    });
});

describe('validaCampo: le stesse regole del backend', () => {
    it('numeri: dominio, interi, passo degli interi, decimali', () => {
        expect(validaCampo(voce({}), '1.6')).toEqual({ ok: true, valore: 1.6 });
        expect(validaCampo(voce({}), '1,6')).toEqual({ ok: true, valore: 1.6 });
        expect(validaCampo(voce({}), '2.5').ok).toBe(false);
        expect(validaCampo(voce({}), '1.0').errore).toMatch(/minimo/);
        expect(validaCampo(voce({}), '').ok).toBe(false);
        expect(validaCampo(voce({}), 'abc').ok).toBe(false);
        expect(validaCampo(voce({}), '1.555').errore).toMatch(/decimali/);
        const intero = voce({ tipo: 'int', default: 10, min: 0, max: 100, passo: 5 });
        expect(validaCampo(intero, '15').ok).toBe(true);
        expect(validaCampo(intero, '12').errore).toMatch(/passi di 5/);
        expect(validaCampo(intero, '1.5').errore).toMatch(/intero/);
    });
    it('bool e scelte', () => {
        expect(validaCampo(voce({ tipo: 'bool', default: true }), false)).toEqual({ ok: true, valore: false });
        expect(validaCampo(voce({ tipo: 'bool', default: true }), 'no').ok).toBe(false);
        const s = voce({ tipo: 'scelta', default: 'a', scelte: ['a', 'b'] });
        expect(validaCampo(s, 'b').ok).toBe(true);
        expect(validaCampo(s, 'c').ok).toBe(false);
    });
});

describe('sostituzioni: si manda SOLO cio\' che cambia', () => {
    it('valore uguale alla serie non e\' una sostituzione; errori separati', () => {
        const voci = [voce({ chiave: 'a' }), voce({ chiave: 'b', tipo: 'bool', default: false }),
            voce({ chiave: 'c' })];
        const r = sostituzioni(voci, { a: '1.5', b: true, c: '9' });
        expect(r.cambiati).toEqual({ b: true });
        expect(Object.keys(r.errori)).toEqual(['c']);
    });
});

describe('gruppi e testi', () => {
    it('ordine dei gruppi del backend', () => {
        const g = gruppiParametri([voce({ chiave: 'a', gruppo: 'Tetti' }), voce({ chiave: 'b', gruppo: 'Ingresso' }),
            voce({ chiave: 'c', gruppo: 'Uscita' })]);
        expect(g.map(x => x.gruppo)).toEqual(['Ingresso', 'Uscita', 'Tetti']);
    });
    it('testoValore', () => {
        expect(testoValore(voce({ unita: 'EUR' }), 2.5)).toBe('2,5 EUR');
        expect(testoValore(voce({ tipo: 'bool' }), true)).toBe('acceso');
    });
    it('minutoDiGioco: ultimo minuto noto, pre-partita prima', () => {
        const t = [{ ts: '2026-10-06T18:00:00Z', minute: 1 }, { ts: '2026-10-06T18:10:00Z', minute: 11 }];
        expect(minutoDiGioco(t, Date.parse('2026-10-06T17:59:00Z'))).toBe('pre-partita');
        expect(minutoDiGioco(t, Date.parse('2026-10-06T18:05:00Z'))).toBe("1'");
        expect(minutoDiGioco(t, Date.parse('2026-10-06T18:30:00Z'))).toBe("11'");
    });
});

describe('payloadApplicaBot: le chiavi opzionali solo se usate', () => {
    it('di serie: il payload del 06/10', () => {
        expect(payloadApplicaBot('E', 'mike', 'base')).toEqual(
            { tipo: 'applica_bot', bot: 'mike', scenario: 'base', event_id: 'E' });
        expect(payloadApplicaBot('E', 'mike', 'base', { parametri: {}, clic_ms: [] })).toEqual(
            { tipo: 'applica_bot', bot: 'mike', scenario: 'base', event_id: 'E' });
    });
    it('con varianti, accensione e clic', () => {
        expect(payloadApplicaBot('E', 'mike', 'base', { parametri: { stake: 5 }, dal_ms: 12.4, clic_ms: [3] }))
            .toEqual({ tipo: 'applica_bot', bot: 'mike', scenario: 'base', event_id: 'E',
                parametri: { stake: 5 }, dal_ms: 12, clic_ms: [3] });
    });
});
