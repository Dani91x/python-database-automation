// righeCanale.rilettura.test.ts - 24/09: quando un messaggio del canale chiede
// una rilettura del database, e le chiavi non numeriche (interruttori tennis).
//
// FALSIFICAZIONE (esito nel referto): con `serveRilettura` che risponde sempre
// false il gruppo "riga sconosciuta" diventa rosso; con EXECUTION_COMPLETE fra
// gli stati terminali diventa rosso "abbinato tutto non e' chiuso".
import { describe, it, expect } from 'vitest';
import {
    applicaBloccoDb, applicaMessaggioCanale, leggiMessaggioRiga, mappaVuota, righeDi,
    rigaTerminale, serveRilettura, type MappaRighe,
} from './righeCanale';

type Riga = { id: number; status: string; price: number; settled_at?: string | null };

function busta(riga: object, ms: number, seq = 1): Record<string, unknown> {
    return { ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: ms };
}

function conUna(riga: Riga): MappaRighe<Riga> {
    return applicaBloccoDb(mappaVuota<Riga>(), 'omega', [riga], 1_000);
}

describe('serveRilettura', () => {
    it('riga sconosciuta: si\' (posizione nuova)', () => {
        const m = conUna({ id: 7, status: 'open', price: 3 });
        const msg = leggiMessaggioRiga(busta({ id: 8, status: 'open', price: 2 }, 2_000))!;
        expect(serveRilettura(m, 'omega', msg)).toBe(true);
    });

    it('la stessa id di un ALTRO bot e\' sconosciuta (chiave composta)', () => {
        const m = conUna({ id: 7, status: 'open', price: 3 });
        const msg = leggiMessaggioRiga(busta({ id: 7, status: 'open', price: 2 }, 2_000))!;
        expect(serveRilettura(m, 'safe', msg)).toBe(true);
        expect(serveRilettura(m, 'omega', msg)).toBe(false);
    });

    it('riga nota che resta aperta: no (basta l\'overlay)', () => {
        const m = conUna({ id: 7, status: 'open', price: 3 });
        const msg = leggiMessaggioRiga(busta({ id: 7, status: 'open', price: 2.5 }, 2_000))!;
        expect(serveRilettura(m, 'omega', msg)).toBe(false);
    });

    it('riga nota che DIVENTA terminale: si\'', () => {
        const m = conUna({ id: 7, status: 'open', price: 3 });
        const msg = leggiMessaggioRiga(busta({ id: 7, status: 'won', price: 3 }, 2_000))!;
        expect(serveRilettura(m, 'omega', msg)).toBe(true);
    });

    it('riga gia\' terminale (anche per overlay): un secondo messaggio terminale no', () => {
        let m = conUna({ id: 7, status: 'open', price: 3 });
        const primo = leggiMessaggioRiga(busta({ id: 7, status: 'won', price: 3 }, 2_000))!;
        m = applicaMessaggioCanale(m, 'omega', primo, 2_001);
        const secondo = leggiMessaggioRiga(busta({ id: 7, status: 'won', price: 3 }, 3_000, 2))!;
        expect(serveRilettura(m, 'omega', secondo)).toBe(false);
    });
});

describe('rigaTerminale', () => {
    it.each(['won', 'lost', 'void', 'VOIDED', 'CANCELLED', 'LAPSED', 'EXPIRED', 'closed', 'error'])(
        '%s e\' terminale', (st) => { expect(rigaTerminale({ status: st })).toBe(true); });

    it.each(['open', 'pending', 'EXECUTABLE', 'EXECUTION_COMPLETE', 'placed', ''])(
        '%s NON e\' terminale (abbinato tutto non e\' chiuso)', (st) => {
            expect(rigaTerminale({ status: st })).toBe(false);
        });

    it('settled_at valorizzato: terminale qualunque sia lo stato', () => {
        expect(rigaTerminale({ status: 'EXECUTION_COMPLETE', settled_at: '2026-09-24T18:00:00+00:00' })).toBe(true);
        expect(rigaTerminale({ status: 'EXECUTION_COMPLETE', settled_at: null })).toBe(false);
    });
});

describe('chiave non numerica: gli interruttori dei bot tennis (bot_key)', () => {
    type Servizio = { bot_key: string; status: string; heartbeat_at: string | null };
    const riga: Servizio = { bot_key: 'tennis_pro', status: 'stopped', heartbeat_at: '2026-09-24T10:00:00+00:00' };

    it('leggiMessaggioRiga con campo chiave `bot_key`', () => {
        const msg = leggiMessaggioRiga(busta(riga, 2_000), 'bot_key');
        expect(msg?.id).toBe('tennis_pro');
        expect(msg?.riga).toEqual(riga);
        // di serie la chiave resta `id` numerico: una riga senza `id` si scarta
        expect(leggiMessaggioRiga(busta(riga, 2_000))).toBeNull();
        expect(leggiMessaggioRiga(busta({ ...riga, bot_key: '' }, 2_000), 'bot_key')).toBeNull();
    });

    it('blocco e messaggio sulla chiave `bot_key`', () => {
        let m = applicaBloccoDb(mappaVuota<Servizio>(), 'tennis_pro', [riga], 1_000, (r) => r.bot_key);
        const msg = leggiMessaggioRiga(busta({ ...riga, status: 'running' }, 2_000), 'bot_key')!;
        m = applicaMessaggioCanale(m, 'tennis_pro', msg, 2_001);
        expect(righeDi(m, 'tennis_pro')[0].status).toBe('running');
        const vecchio = leggiMessaggioRiga(busta({ ...riga, status: 'error' }, 500, 9), 'bot_key')!;
        expect(applicaMessaggioCanale(m, 'tennis_pro', vecchio, 2_002)).toBe(m);
    });
});
