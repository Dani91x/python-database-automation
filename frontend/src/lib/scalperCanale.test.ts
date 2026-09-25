// ============================================================================
// scalperCanale.test.ts - 25/09: lo scalper dal suo canale (47338), puro.
// Le tre regole di `lib/scalperCanale.ts`: il canale non aggiunge sessioni
// (chiede una rilettura), vince solo se piu' fresco della lettura e
// dell'ultimo messaggio, una sessione che si ferma chiede una rilettura.
// Finti: sessione = `to_jsonb(scalper_control)` + colonne della RPC
// (`__fixtures__/scalperFinti.ts`); messaggio = riga + busta (canale_bot.py).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    overlayScalperVuoto, applicaSessioneCanale, applicaServizioCanale, vistaScalper,
    etaCanaleSessione, ultimoCanaleScalper,
} from '@/lib/scalperCanale';
import { leggiMessaggioRiga, type MessaggioRiga } from '@/lib/righeCanale';
import type { ScalperControlRoom, ServizioScalper } from '@/lib/scalperControlRoom';
import { sessione } from '@/lib/__fixtures__/scalperFinti';

const T0 = 1_000_000;

function msgSessione(riga: Record<string, unknown>, ms: number, seq: number): MessaggioRiga {
    const m = leggiMessaggioRiga({ ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: ms }, 'event_id');
    if (!m) throw new Error('busta non valida');
    return m;
}

function servizio(over: Partial<ServizioScalper> = {}): ServizioScalper {
    return {
        id: 1, status: 'running', mode: 'paper', strategia: 'maker', stake: 25, params: {},
        stats: null, started_at: null, stopped_at: null, updated_at: null, ...over,
    };
}

function cr(over: Partial<ScalperControlRoom> = {}): ScalperControlRoom {
    return {
        sessioni: [sessione({ event_id: '1' })], ordini: [], lettoAt: null,
        servizio: servizio(), servizioLetto: true, ...over,
    };
}

describe('applicaSessioneCanale', () => {
    it('sessione sconosciuta: niente overlay, rilettura', () => {
        const ov = overlayScalperVuoto();
        const r = applicaSessioneCanale(ov, cr(), T0, msgSessione({ event_id: '9', status: 'requested' }, T0 + 1, 1), T0 + 2);
        expect(r.rileggi).toBe(true);
        expect(r.ov).toBe(ov);
    });

    it('piu\' fresco della lettura: overlay; non piu\' fresco: scartato (stesso oggetto)', () => {
        const ov = overlayScalperVuoto();
        const vecchio = applicaSessioneCanale(ov, cr(), T0, msgSessione({ event_id: '1' }, T0, 1), T0 + 5);
        expect(vecchio.ov).toBe(ov);
        const nuovo = applicaSessioneCanale(ov, cr(), T0, msgSessione({ event_id: '1', heartbeat_at: 'X' }, T0 + 1, 1), T0 + 5);
        expect(nuovo.ov.sessioni.get('1')?.riga.heartbeat_at).toBe('X');
        expect(nuovo.rileggi).toBe(false);
        // fra due messaggi vince (ms, seq) maggiore
        const stesso = applicaSessioneCanale(nuovo.ov, cr(), T0, msgSessione({ event_id: '1', heartbeat_at: 'Y' }, T0 + 1, 1), T0 + 6);
        expect(stesso.ov).toBe(nuovo.ov);
        const dopo = applicaSessioneCanale(nuovo.ov, cr(), T0, msgSessione({ event_id: '1', heartbeat_at: 'Z' }, T0 + 1, 2), T0 + 6);
        expect(dopo.ov.sessioni.get('1')?.riga.heartbeat_at).toBe('Z');
    });

    it('la sessione si ferma col messaggio: rilettura (una volta: poi e\' gia\' ferma)', () => {
        const ov = overlayScalperVuoto();
        const r = applicaSessioneCanale(ov, cr(), T0, msgSessione({ event_id: '1', status: 'stopped' }, T0 + 1, 1), T0 + 2);
        expect(r.rileggi).toBe(true);
        const r2 = applicaSessioneCanale(r.ov, cr(), T0, msgSessione({ event_id: '1', status: 'stopped' }, T0 + 2, 2), T0 + 3);
        expect(r2.rileggi).toBe(false);
    });
});

describe('vistaScalper', () => {
    it('canale muto: la lettura identica (stesso oggetto)', () => {
        const c = cr();
        expect(vistaScalper(c, T0, overlayScalperVuoto())).toBe(c);
        expect(vistaScalper(null, T0, overlayScalperVuoto())).toBeNull();
    });

    it('overlay fresco sopra la riga, le colonne della RPC restano', () => {
        const c = cr();
        const { ov } = applicaSessioneCanale(overlayScalperVuoto(), c, T0,
            msgSessione({ event_id: '1', status: 'running', stats: { pnl_locked: 1.2 } }, T0 + 1, 1), T0 + 2);
        const v = vistaScalper(c, T0, ov)!;
        expect(v.sessioni[0].stats).toEqual({ pnl_locked: 1.2 });
        expect(v.sessioni[0].event_name).toBe('Inter v Milan');
        // una lettura PIU' NUOVA del messaggio lo rende inutile
        expect(vistaScalper(c, T0 + 5, ov)).toBe(c);
    });

    it('servizio dal canale solo se la migrazione c\'e\' (servizioLetto)', () => {
        const m = leggiMessaggioRiga({ ...servizio({ status: 'stopped' }), fonte: 'canale', _seq: 1, _pubblicato_ms: T0 + 1 })!;
        const ov = applicaServizioCanale(overlayScalperVuoto(), T0, m, T0 + 2);
        expect(vistaScalper(cr(), T0, ov)!.servizio!.status).toBe('stopped');
        const senza = cr({ servizio: null, servizioLetto: false });
        expect(vistaScalper(senza, T0, ov)).toBe(senza);
        // id diverso da 1: ignorato
        const altro = leggiMessaggioRiga({ ...servizio(), id: 2, fonte: 'canale', _seq: 1, _pubblicato_ms: T0 + 1 })!;
        const ov0 = overlayScalperVuoto();
        expect(applicaServizioCanale(ov0, T0, altro, T0 + 2)).toBe(ov0);
    });
});

describe('eta e ultima notizia', () => {
    it('eta del canale della sessione e ultima ricezione in uso', () => {
        const { ov } = applicaSessioneCanale(overlayScalperVuoto(), cr(), T0,
            msgSessione({ event_id: '1' }, T0 + 1, 1), T0 + 2_000);
        expect(etaCanaleSessione(ov, T0, '1', T0 + 5_000)).toBe(3);
        expect(etaCanaleSessione(ov, T0 + 10, '1', T0 + 5_000)).toBeNull();
        expect(etaCanaleSessione(ov, T0, '2', T0 + 5_000)).toBeNull();
        expect(ultimoCanaleScalper(ov, T0)).toBe(T0 + 2_000);
        expect(ultimoCanaleScalper(ov, T0 + 10)).toBeNull();
    });
});
