// ============================================================================
// paroleImpianto.test.ts - P5 (30/09): chip dei bot e impianto in parole vere.
// Valori veri: `heartbeat_mode()` scrive 'LIVE+PAPER' o 'PAPER' (runner.py:2191-2192);
// `safe_strategy_status.payload.source` = 'stream' | 'rest' (safe_strategy/service.py:2160);
// freschezza = `freschezzaBattito` del hook ('fresca'|'lenta'|'vecchia'|'ignota').
// ============================================================================
import { describe, it, expect } from 'vitest';
import { modoChip, statoChip, usciteChip, pallinoChip, aggiornatoChip, tettoRunner, sorgenteFeed, riassuntoDati } from './paroleImpianto';

describe('modoChip - sempre il modo dichiarato (T_P5b)', () => {
    it('LIVE resta LIVE col tono live anche a bot fermo; PAPER col suo tono', () => {
        expect(modoChip({ modalita: 'live' })).toEqual({ testo: 'LIVE', tono: 'live' });
        expect(modoChip({ modalita: 'paper' })).toEqual({ testo: 'PAPER', tono: 'paper' });
        expect(modoChip({ modalita: null }).testo).toMatch(/ignota/);
    });
    it('"ultimo modo" SOLO dal ripiego modalitaUltima (scalper senza sessioni)', () => {
        expect(modoChip({ modalita: null, modalitaUltima: 'paper' }).testo).toBe('ultimo modo paper');
        expect(modoChip({ modalita: 'live', modalitaUltima: 'paper' }).testo).toBe('LIVE');
    });
});

describe('statoChip / usciteChip / pallinoChip (T_P5b)', () => {
    it('parole di botStatusMeta: FERMO, IN ARRESTO, INATTIVO, ERRORE (rosso); running nessuna parola', () => {
        expect(statoChip('stopped')).toEqual({ testo: 'FERMO', tono: 'neutro' });
        expect(statoChip('stopping')).toEqual({ testo: 'IN ARRESTO', tono: 'attenzione' });
        expect(statoChip('idle')?.testo).toBe('INATTIVO');
        expect(statoChip('error')).toEqual({ testo: 'ERRORE', tono: 'allarme' });
        expect(statoChip('running')).toBeNull();
    });
    it('stato non letto: "stato non letto", mai "spento"; stato sconosciuto scritto com\'e\'', () => {
        expect(statoChip(null)).toEqual({ testo: 'stato non letto', tono: 'attenzione' });
        expect(statoChip('arming')?.testo).toBe('ARMING');
    });
    it('uscite attive SOLO se il servizio dichiara stop_ferma_solo_aperture e il bot non corre', () => {
        expect(usciteChip({ stato: 'stopped', stopFermaSoloAperture: true })?.testo).toMatch(/uscite attive/);
        expect(usciteChip({ stato: 'stopped', stopFermaSoloAperture: true })?.titolo).toMatch(/cash out e regolamento continuano/);
        expect(usciteChip({ stato: 'stopped', stopFermaSoloAperture: false })).toBeNull();
        expect(usciteChip({ stato: 'stopped' })).toBeNull();
        expect(usciteChip({ stato: 'running', stopFermaSoloAperture: true })).toBeNull();
    });
    it('pallino: fermo in LIVE distinto dal fermo in paper', () => {
        expect(pallinoChip({ inCorsa: false, muto: true, modalita: 'live' })).toBe('fermo-live');
        expect(pallinoChip({ inCorsa: false, muto: true, modalita: 'paper' })).toBe('fermo');
        expect(pallinoChip({ inCorsa: true, muto: true, modalita: 'paper' })).toBe('muto');
        expect(pallinoChip({ inCorsa: true, muto: false, modalita: 'live' })).toBe('vivo');
    });
});

describe('aggiornatoChip - niente piu\' \u00absenza spinta\u00bb', () => {
    it('fermo che non invia: normale, grigio', () => {
        const a = aggiornatoChip({ inCorsa: false, etaS: null, freschezza: 'ignota' });
        expect(a).toEqual({ testo: 'fermo: non invia aggiornamenti', tono: 'neutro' });
    });
    it('acceso e muto oltre la cadenza: ACCESO MA MUTO da N s, rosso', () => {
        expect(aggiornatoChip({ inCorsa: true, etaS: 95, freschezza: 'vecchia' }))
            .toEqual({ testo: 'ACCESO MA MUTO da 1 min', tono: 'allarme' });
        expect(aggiornatoChip({ inCorsa: true, etaS: null, freschezza: 'ignota' }).tono).toBe('allarme');
    });
    it('acceso e fresco: aggiornato N s fa', () => {
        expect(aggiornatoChip({ inCorsa: true, etaS: 2, freschezza: 'fresca' }))
            .toEqual({ testo: 'aggiornato 2 s fa', tono: 'ok' });
    });
    it('in nessun caso scrive \u00absenza spinta\u00bb', () => {
        for (const inCorsa of [true, false]) for (const f of ['fresca', 'lenta', 'vecchia', 'ignota'] as const) {
            expect(aggiornatoChip({ inCorsa, etaS: null, freschezza: f }).testo).not.toMatch(/spinta/);
        }
    });
});

describe('tettoRunner / sorgenteFeed / riassuntoDati', () => {
    it('LIVE+PAPER = ordini veri consentiti; PAPER = solo simulati; mai "live+paper" a schermo', () => {
        expect(tettoRunner('LIVE+PAPER')?.testo).toBe('ordini veri consentiti');
        expect(tettoRunner('PAPER')?.testo).toBe('solo simulati');
        expect(tettoRunner(null)).toBeNull();
        expect(tettoRunner('LIVE+PAPER')?.testo).not.toMatch(/live\+paper/i);
    });
    it('rest = RIPIEGO in ambra; stream = verde', () => {
        expect(sorgenteFeed('rest')).toEqual({ testo: 'RIPIEGO REST (stream fermo)', tono: 'attenzione' });
        expect(sorgenteFeed('stream').tono).toBe('ok');
    });
    it('dati: tempo reale solo se TUTTO arriva dal canale; altrimenti nomina chi no', () => {
        expect(riassuntoDati([{ nome: 'Omega', canale: true }]).testo).toBe('Dati: tempo reale');
        const r = riassuntoDati([{ nome: 'Omega', canale: false }, { nome: 'Safe', canale: true }, { nome: 'Tennis', canale: false }]);
        expect(r.testo).toBe('Dati: dal database (ogni 30 s) per: Omega, Tennis');
    });
});
