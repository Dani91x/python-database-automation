// schedaAlMs.ts - parte pura della scheda al ms (24/09/2026). Righe del ladder
// con la FORMA di `LiveLadderRow` (lib/live.ts).
import { describe, expect, it } from 'vitest';
import {
    prezzoDaLadder, scegliPrezzo, giudica, scarto, prezzoVistoAlClic, etaEFonte, PREZZO_VUOTO,
} from './schedaAlMs';
import { esitoApprovazione } from './safeBot';

const riga = (back: number | null, lay: number | null, status = 'OPEN') => ({
    event_id: 'E', market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'MO', status,
    updated_at: '2026-09-24T21:00:00Z',
    ladder: { updated_ms: 1000, selections: [
        { selection_id: 11, name: 'Uno', ltp: null, tv: null,
            back: back == null ? [] : [[back, 40]] as [number, number][],
            lay: lay == null ? [] : [[lay, 30]] as [number, number][], trd: [],
            wom: { back_pct: 50, lay_pct: 50 } },
    ] },
});

const CRITERI = { min_edge: 0.015, min_size: 20, max_lay_price: 8, min_back_price: 1.02,
    commission: 0.05, min_prob_back: 0.9, max_prob_lay: 0.1, opps_min_edge: 0.03,
    max_liability_per_trade: 0, stake: 5 };

describe('prezzoDaLadder / scegliPrezzo', () => {
    it('legge back/lay migliori con size, istante, fonte e stato', () => {
        expect(prezzoDaLadder(riga(1.5, 1.52), 11, 'canale')).toEqual({
            back: 1.5, backSize: 40, lay: 1.52, laySize: 30, istanteMs: 1000,
            fonte: 'canale', statoMercato: 'OPEN' });
    });
    it('selezione assente = null (mai un prezzo inventato)', () => {
        expect(prezzoDaLadder(riga(1.5, 1.52), 99, 'canale')).toBeNull();
        expect(prezzoDaLadder(null, 11, 'canale')).toBeNull();
    });
    it('ladder senza il lato -> ripiego sullo scanner, dichiarato', () => {
        const lad = prezzoDaLadder(riga(null, 1.52), 11, 'db');
        const scan = { ...PREZZO_VUOTO, back: 1.49, backSize: 10, fonte: 'scanner' as const };
        expect(scegliPrezzo(lad, scan, 'back')).toMatchObject({ back: 1.49, fonte: 'scanner' });
        expect(scegliPrezzo(lad, scan, 'lay')).toMatchObject({ lay: 1.52, fonte: 'db' });
        expect(scegliPrezzo(null, null, 'back')).toMatchObject({ back: null, fonte: null });
    });
});

describe('giudica: semaforo coi criteri del modello', () => {
    const g = (prezzo: number | null, extra = {}) => giudica({ lato: 'back', prezzo, abbinabile: 500,
        pModel: 0.99, criteri: CRITERI, ...extra });
    it('SI / QUASI / NO al prezzo', () => {
        expect(g(1.1).semaforo).toBe('SI');
        expect(g(1.045).semaforo).toBe('QUASI');
        expect(g(1.04).semaforo).toBe('NO');
    });
    it('senza prezzo: NO, e lo dice', () => {
        const r = g(null);
        expect(r.semaforo).toBe('NO');
        expect(r.motivi.join(' ')).toMatch(/non disponibile/);
    });
    it('il servizio dice causa modello: NO anche se il prezzo regge', () => {
        const r = g(1.1, { valutazione: { valida: false, causa: 'modello',
            motivi: [{ codice: 'non_piu_proposta_dal_modello', valore: null, soglia: null, testo: 'non la propone piu' }] } });
        expect(r.semaforo).toBe('NO');
        expect(r.motivi[0]).toBe('non la propone piu');
    });
    it('LAY: il tick contro e\' quello piu\' alto', () => {
        const r = giudica({ lato: 'lay', prezzo: 8, abbinabile: 500, pModel: 0.01, criteri: CRITERI });
        expect(r.semaforo).toBe('QUASI');   // a 8.2 supera max_lay_price 8
    });
});

describe('scarto e prezzo visto al clic', () => {
    it('tick e percentuale dalla proposta', () => {
        expect(scarto(1.13, 1.1)).toEqual({ tick: 3, pct: expect.closeTo(2.727, 2) });
        expect(scarto(null, 1.1)).toEqual({ tick: null, pct: null });
    });
    it('vivo: flag false; ultimo noto: flag true con eta; niente: proposta', () => {
        const base = { vivoIstanteMs: 900, vivoFonte: 'canale' as const, ultimoNoto: 1.2,
            ultimoNotoIstanteMs: 500, ultimoNotoFonte: 'scanner' as const, prezzoProposta: 1.3, nowMs: 1000 };
        expect(prezzoVistoAlClic({ ...base, vivo: 1.25 })).toEqual({ prezzo: 1.25,
            contesto: { eta_ms: 100, fonte: 'canale', prezzo_vivo_assente: false, clic_ms: 1000 } });
        expect(prezzoVistoAlClic({ ...base, vivo: null })).toEqual({ prezzo: 1.2,
            contesto: { eta_ms: 500, fonte: 'scanner', prezzo_vivo_assente: true, clic_ms: 1000 } });
        expect(prezzoVistoAlClic({ ...base, vivo: null, ultimoNoto: null })).toEqual({ prezzo: 1.3,
            contesto: { eta_ms: null, fonte: 'proposta', prezzo_vivo_assente: true, clic_ms: 1000 } });
    });
    it('eta e fonte dichiarate', () => {
        expect(etaEFonte(500, 'canale', 2000)).toMatch(/1,5 s fa · canale al ms/);
        expect(etaEFonte(null, 'scanner', 2000)).toMatch(/età ignota · feed scanner/);
    });
});

describe('esitoApprovazione (lib/safeBot.ts)', () => {
    it('pending = inviata, done = eseguita, error = rifiutata coi due prezzi', () => {
        expect(esitoApprovazione({ id: 5, status: 'pending', result: null }, 5).stato).toBe('inviata');
        expect(esitoApprovazione({ id: 5, status: 'done', result: { message: 'eseguito' } }, 5))
            .toEqual({ id: 5, stato: 'eseguita', testo: 'eseguito' });
        const r = esitoApprovazione({ id: 5, status: 'error', result: {
            message: 'rifiutato: prezzo cambiato', price_visto: 1.3, price_attuale: 1.4 } }, 5);
        expect(r.stato).toBe('rifiutata');
        expect(r.testo).toBe('rifiutato: prezzo cambiato [visto 1,30 · all’esecuzione 1,40]');
        expect(esitoApprovazione(undefined, 9)).toEqual({ id: 9, stato: 'inviata',
            testo: 'inviata: il servizio la sta eseguendo' });
    });
});
