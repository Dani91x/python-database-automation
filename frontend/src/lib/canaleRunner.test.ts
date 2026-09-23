// canaleRunner.test.ts - la sovrapposizione dei topic `now`/`position` dei
// runner sul poll del database. I push qui sotto hanno le STESSE chiavi e gli
// stessi tipi dei produttori: Betfair/stream/db.py::upsert_live_position
// (payload = _position_row + updated_at, niente id) e ::update_live_now.
import { describe, it, expect } from 'vitest';
import type { LivePositionRow } from '@/lib/liveOrders';
import {
    applicaPushPosizione, chiavePosizione, istanteMicro, leggiPushNow,
    leggiPushPosizione, nowPiuRecente, potaSovrapposizioni, vistaPosizioni,
    type SovrapposizioniPos,
} from './canaleRunner';

const T0 = '2026-09-23T18:00:00.100000+00:00';
const T1 = '2026-09-23T18:00:00.100500+00:00'; // +500 us: stesso millisecondo di T0
const T2 = '2026-09-23T18:00:05.000000+00:00';

// riga come la restituisce get_live_positions_event (LivePositionRow)
function rigaDb(over: Partial<LivePositionRow> = {}): LivePositionRow {
    return {
        id: 41, mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0,
        matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
        selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
        net_position: 5, updated_at: T0, ...over,
    };
}

// push come lo scrive db.py: chiavi di _position_row + updated_at isoformat()
function pushVero(over: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0.0,
        matched_if_win: 20.0, matched_if_lose: -9.0, worst_if_win: 20.0, worst_if_lose: -9.0,
        selection_exposure: 9.0, unmatched_back_exposure: 0.0, unmatched_lay_exposure: 0.0,
        net_position: 9.0, updated_at: T2, ...over,
    };
}

const VUOTA: SovrapposizioniPos = new Map();

function applica(prev: SovrapposizioniPos, righe: LivePositionRow[], d: Record<string, unknown>) {
    const p = leggiPushPosizione(d);
    if (!p) throw new Error('push non valido nel test');
    return applicaPushPosizione(prev, righe, p);
}

describe('istanteMicro', () => {
    it('conserva i microsecondi (due scritture nello stesso ms non sono pari)', () => {
        const a = istanteMicro(T0)!;
        const b = istanteMicro(T1)!;
        expect(b - a).toBe(500);
    });
    it('isoformat senza frazione (microsecondi 0) e stringhe illeggibili', () => {
        expect(istanteMicro('2026-09-23T18:00:00+00:00')).toBe(Date.parse('2026-09-23T18:00:00+00:00') * 1000);
        expect(istanteMicro('ieri')).toBeNull();
        expect(istanteMicro(null)).toBeNull();
    });
});

describe('leggiPushPosizione', () => {
    it('accetta il payload vero e scarta mode ignoto, selezione non intera, colonna mancante', () => {
        const p = leggiPushPosizione(pushVero());
        expect(p?.chiave).toBe(chiavePosizione('paper', '1.234', 7, 0));
        expect(p?.valori.selection_exposure).toBe(9);
        expect(leggiPushPosizione(pushVero({ mode: 'PAPER' }))).toBeNull();
        expect(leggiPushPosizione(pushVero({ selection_id: '7' }))).toBeNull();
        const senza = pushVero(); delete senza.net_position;
        expect(leggiPushPosizione(senza)).toBeNull();
        expect(leggiPushPosizione(pushVero({ updated_at: 'x' }))).toBeNull();
    });
});

describe('overlay position sul poll', () => {
    it('canale fresco vince: le colonne del push sopra la riga del database', () => {
        const righe = [rigaDb()];
        const s = applica(VUOTA, righe, pushVero());
        const v = vistaPosizioni(righe, s);
        expect(v[0].selection_exposure).toBe(9);
        expect(v[0].net_position).toBe(9);
        expect(v[0].id).toBe(41); // la riga resta quella del database
        expect(v[0].updated_at).toBe(T2);
    });

    it('messaggio vecchio ignorato: non piu\' fresco del database (anche a parita\')', () => {
        const righe = [rigaDb({ updated_at: T2 })];
        expect(applica(VUOTA, righe, pushVero({ updated_at: T0 }))).toBe(VUOTA);
        expect(applica(VUOTA, righe, pushVero({ updated_at: T2 }))).toBe(VUOTA);
    });

    it('messaggio vecchio ignorato: piu\' vecchio della sovrapposizione gia\' tenuta', () => {
        const righe = [rigaDb({ updated_at: T0 })];
        const s1 = applica(VUOTA, righe, pushVero({ updated_at: T2, selection_exposure: 9 }));
        const s2 = applica(s1, righe, pushVero({ updated_at: T1, selection_exposure: 1 }));
        expect(s2).toBe(s1);
        expect(vistaPosizioni(righe, s2)[0].selection_exposure).toBe(9);
    });

    it('microsecondi: un push 500 us dopo la riga del database vince', () => {
        const righe = [rigaDb({ updated_at: T0 })];
        const s = applica(VUOTA, righe, pushVero({ updated_at: T1 }));
        expect(vistaPosizioni(righe, s)[0].selection_exposure).toBe(9);
    });

    it('il canale non aggiunge righe: push di una posizione che il database non ha', () => {
        const righe = [rigaDb()];
        expect(applica(VUOTA, righe, pushVero({ selection_id: 8 }))).toBe(VUOTA);
        expect(applica(VUOTA, righe, pushVero({ mode: 'live' }))).toBe(VUOTA); // modi mai mescolati
        expect(vistaPosizioni(righe, VUOTA)).toBe(righe);
    });

    it('riga sparita dal blocco nuovo: sparisce anche la sovrapposizione', () => {
        const righe = [rigaDb()];
        const s = applica(VUOTA, righe, pushVero());
        const bloccoNuovo: LivePositionRow[] = [];
        const potata = potaSovrapposizioni(s, bloccoNuovo);
        expect(potata.size).toBe(0);
        expect(vistaPosizioni(bloccoNuovo, potata)).toEqual([]);
    });

    it('il database raggiunge il canale: la sovrapposizione si butta', () => {
        const righe = [rigaDb()];
        const s = applica(VUOTA, righe, pushVero());
        const raggiunto = [rigaDb({ updated_at: T2, selection_exposure: 9 })];
        expect(potaSovrapposizioni(s, raggiunto).size).toBe(0);
        // un blocco ancora vecchio non la butta
        expect(potaSovrapposizioni(s, righe)).toBe(s);
    });

    it('parita\': canale muto -> la vista e\' lo STESSO array del database', () => {
        const righe = [rigaDb(), rigaDb({ id: 42, selection_id: 8 })];
        expect(vistaPosizioni(righe, VUOTA)).toBe(righe);
        expect(potaSovrapposizioni(VUOTA, righe)).toBe(VUOTA);
    });

    it('parita\': sovrapposizione non piu\' applicabile (database raggiunto) -> stesso array', () => {
        const s = applica(VUOTA, [rigaDb()], pushVero());
        const raggiunto = [rigaDb({ updated_at: T2, selection_exposure: 9 })];
        expect(vistaPosizioni(raggiunto, s)).toBe(raggiunto);
    });
});

describe('now: piu\' recente vince', () => {
    const now = (updated_at: string | null, minute: number) => ({ event_id: 'ev1', updated_at, minute });
    it('il piu\' recente vince, il vecchio e\' ignorato, a parita\' la nuova', () => {
        const a = now(T0, 10);
        const b = now(T2, 11);
        expect(nowPiuRecente(a, b)).toBe(b);
        expect(nowPiuRecente(b, a)).toBe(b);
        const b2 = now(T2, 11);
        expect(nowPiuRecente(b, b2)).toBe(b2);
        expect(nowPiuRecente(undefined, a)).toBe(a);
        expect(nowPiuRecente(a, now(null, 12)).minute).toBe(12);
    });
    it('leggiPushNow: serve un event_id stringa', () => {
        expect(leggiPushNow({ event_id: 'ev1', updated_at: T0 })).not.toBeNull();
        expect(leggiPushNow({ event_id: 5 })).toBeNull();
        expect(leggiPushNow(null)).toBeNull();
    });
});
