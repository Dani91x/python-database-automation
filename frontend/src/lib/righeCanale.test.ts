// ============================================================================
// righeCanale.test.ts - C6 b (23/09): la riduzione della MAPPA PER RIGA.
//
// I finti parlano come il vero: la riga e' quella della tabella (`omega_trades`,
// `safe_strategy_trades`, `mike_trades`, come la restituisce `to_jsonb(t.*)`
// nelle RPC e `return=representation` nel produttore), e il messaggio del
// canale e' LA STESSA riga piu' la busta di `Betfair/stream/canale_bot.py`
// (`fonte`="canale", `_seq` int, `_pubblicato_ms` int).
//
// FALSIFICAZIONE (eseguita a mano il 23/09, esito nel referto del delegato):
//   M1 tolto il confronto `msg.ms > v.dbMs`         -> "messaggio vecchio" ROSSO
//   M2 chiave sull'id nudo (senza bot)              -> "chiave composta" ROSSO
//   M3 la sovrapposizione sopravvive a ogni blocco  -> "canale poi RPC" ROSSO
//   M4 il canale aggiunge una riga sconosciuta      -> "non aggiunge" ROSSO
//   M5 il blocco fonde invece di sostituire         -> "riga cancellata" ROSSO
//   M6 la vista copia sempre la riga                -> "parita'" ROSSO
//   M7 fra due messaggi decide solo `_seq`          -> "riavvio" ROSSO
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    mappaVuota, applicaBloccoDb, applicaMessaggioCanale, leggiMessaggioRiga,
    righeDi, etaRiga, ultimeNotizie, chiaveRiga, type MappaRighe, type MessaggioRiga,
} from '@/lib/righeCanale';
import type { OmegaTrade } from '@/lib/omega';
import type { SafeTrade } from '@/lib/safeBot';

// ------------------------------------------------------------------- finti

/** riga di `omega_trades` (le colonne che il tipo conosce + `commission`,
 *  colonna vera della tabella che il tipo non dichiara) */
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

/** Il push del canale: LA riga + la busta (`canale_bot.busta`). */
function busta(riga: object, pubblicatoMs: number, seq: number): Record<string, unknown> {
    return { ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: pubblicatoMs };
}

function msg(riga: object, pubblicatoMs: number, seq: number): MessaggioRiga {
    const m = leggiMessaggioRiga(busta(riga, pubblicatoMs, seq));
    if (!m) throw new Error('finto non valido');
    return m;
}

type Riga = OmegaTrade | SafeTrade;
const T0 = 1_000_000;

function conOmega(righe: OmegaTrade[], lettoMs = T0): MappaRighe<Riga> {
    return applicaBloccoDb(mappaVuota<Riga>(), 'omega', righe, lettoMs);
}

// ================================================================ il busta

describe('leggiMessaggioRiga: la busta di canale_bot.py', () => {
    it('toglie SOLO le tre chiavi della busta e tiene la riga intera', () => {
        const r = rigaOmega(5);
        const m = leggiMessaggioRiga(busta(r, T0 + 10, 3));
        expect(m).not.toBeNull();
        expect(m!.id).toBe(5);
        expect(m!.ms).toBe(T0 + 10);
        expect(m!.seq).toBe(3);
        expect(m!.riga).toEqual(r);
        for (const k of ['fonte', '_seq', '_pubblicato_ms']) expect(k in m!.riga).toBe(false);
    });

    it('una riga senza busta, o con la busta storta, non e\' un messaggio', () => {
        expect(leggiMessaggioRiga(rigaOmega(5))).toBeNull();
        expect(leggiMessaggioRiga({ ...busta(rigaOmega(5), T0, 1), fonte: 'database' })).toBeNull();
        expect(leggiMessaggioRiga({ ...busta(rigaOmega(5), T0, 1), _pubblicato_ms: '12' })).toBeNull();
        expect(leggiMessaggioRiga({ ...busta(rigaOmega(5), T0, 1), _seq: null })).toBeNull();
        expect(leggiMessaggioRiga({ ...busta(rigaOmega(5), T0, 1), id: '5' })).toBeNull();
        expect(leggiMessaggioRiga(null)).toBeNull();
        expect(leggiMessaggioRiga([busta(rigaOmega(5), T0, 1)])).toBeNull();
    });
});

// ================================================================ parita'

describe('parita\': con il canale muto la mappa E\' il blocco del database', () => {
    it('stesse righe, STESSI oggetti, stesso ordine', () => {
        const righe = [rigaOmega(3), rigaOmega(1), rigaOmega(2)];
        const out = righeDi(conOmega(righe), 'omega');
        expect(out).toHaveLength(3);
        out.forEach((r, i) => expect(r).toBe(righe[i]));
    });

    it('un secondo blocco sostituisce il primo per intero, nell\'ordine nuovo', () => {
        const a = [rigaOmega(1), rigaOmega(2)];
        const b = [rigaOmega(2, { status: 'won', pnl: 1 }), rigaOmega(9)];
        const m = applicaBloccoDb(conOmega(a), 'omega', b, T0 + 30_000);
        const out = righeDi(m, 'omega');
        expect(out).toHaveLength(2);
        out.forEach((r, i) => expect(r).toBe(b[i]));
    });

    it('fonte "database" con l\'eta\' della lettura', () => {
        const m = conOmega([rigaOmega(1)]);
        expect(etaRiga(m, 'omega', 1, T0 + 4_000)).toEqual({ fonte: 'database', etaS: 4 });
        expect(ultimeNotizie([m], 'omega')).toEqual({ canaleMs: null, dbMs: T0 });
    });
});

// ============================================================ RPC poi canale

describe('RPC poi canale: il messaggio piu\' fresco sovrappone la riga', () => {
    it('le colonne del messaggio vincono, le chiavi solo del database restano', () => {
        // Mike: la RPC aggiunge `day_placed_at`, che la tabella non ha
        const db = { ...rigaOmega(1), day_placed_at: '2026-09-23T19:00:00+00:00' };
        const m0 = applicaBloccoDb(mappaVuota<Riga>(), 'omega', [db], T0);
        const m1 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(1, { status: 'won', pnl: 0.95 }), T0 + 500, 7), T0 + 520);
        const [r] = righeDi(m1, 'omega') as (OmegaTrade & { day_placed_at?: string })[];
        expect(r.status).toBe('won');
        expect(r.pnl).toBe(0.95);
        expect(r.day_placed_at).toBe('2026-09-23T19:00:00+00:00');
        expect('_seq' in r).toBe(false);
        expect(etaRiga(m1, 'omega', 1, T0 + 2_520)).toEqual({ fonte: 'locale', etaS: 2 });
        expect(ultimeNotizie([m1], 'omega')).toEqual({ canaleMs: T0 + 520, dbMs: T0 });
    });
});

// ============================================================ canale poi RPC

describe('canale poi RPC: il blocco vince solo se letto DOPO la pubblicazione', () => {
    const conMsg = () => applicaMessaggioCanale(
        conOmega([rigaOmega(1, { price: 8.4 })]), 'omega',
        msg(rigaOmega(1, { price: 7.0 }), T0 + 5_000, 11), T0 + 5_010);

    it('blocco letto PRIMA del messaggio (in volo): la riga del canale resta', () => {
        const m = applicaBloccoDb(conMsg(), 'omega', [rigaOmega(1, { price: 8.4 })], T0 + 4_000);
        expect((righeDi(m, 'omega')[0] as OmegaTrade).price).toBe(7.0);
        expect(etaRiga(m, 'omega', 1, T0 + 6_010)?.fonte).toBe('locale');
    });

    it('a parita\' di istante vince il database', () => {
        const m = applicaBloccoDb(conMsg(), 'omega', [rigaOmega(1, { price: 6.6 })], T0 + 5_000);
        expect((righeDi(m, 'omega')[0] as OmegaTrade).price).toBe(6.6);
        expect(etaRiga(m, 'omega', 1, T0 + 5_000)?.fonte).toBe('database');
    });

    it('blocco letto DOPO: vince il database e la sovrapposizione si butta', () => {
        const fresca = rigaOmega(1, { price: 6.8 });
        const m = applicaBloccoDb(conMsg(), 'omega', [fresca], T0 + 30_000);
        expect(righeDi(m, 'omega')[0]).toBe(fresca);
        expect(ultimeNotizie([m], 'omega').canaleMs).toBeNull();
    });
});

// ======================================================= messaggio vecchio

describe('un messaggio vecchio non sovrascrive mai un dato nuovo', () => {
    it('pubblicato prima della lettura del database: ignorato, stesso stato', () => {
        const m0 = conOmega([rigaOmega(1, { price: 8.4 })], T0);
        const m1 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(1, { price: 3.3 }), T0 - 1, 99), T0 + 5);
        expect(m1).toBe(m0);
        const m2 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(1, { price: 3.3 }), T0, 99), T0 + 5);
        expect(m2).toBe(m0);   // a parita' vince il database
    });

    it('fra due messaggi vince (pubblicato_ms, seq) maggiore', () => {
        const m0 = conOmega([rigaOmega(1)], T0);
        const m1 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(1, { price: 5 }), T0 + 100, 5), T0 + 101);
        // piu' vecchio nel tempo, anche se con seq maggiore: ignorato
        expect(applicaMessaggioCanale(m1, 'omega', msg(rigaOmega(1, { price: 9 }), T0 + 90, 6), T0 + 102)).toBe(m1);
        // stesso istante, seq minore o uguale: ignorato
        expect(applicaMessaggioCanale(m1, 'omega', msg(rigaOmega(1, { price: 9 }), T0 + 100, 5), T0 + 102)).toBe(m1);
        expect(applicaMessaggioCanale(m1, 'omega', msg(rigaOmega(1, { price: 9 }), T0 + 100, 4), T0 + 102)).toBe(m1);
        // stesso istante, seq maggiore: accettato
        const m2 = applicaMessaggioCanale(m1, 'omega', msg(rigaOmega(1, { price: 6 }), T0 + 100, 6), T0 + 103);
        expect((righeDi(m2, 'omega')[0] as OmegaTrade).price).toBe(6);
    });

    it('riavvio del bot: `_seq` riparte da 1 ma il messaggio e\' piu\' nuovo, e vince', () => {
        const m0 = conOmega([rigaOmega(1)], T0);
        const m1 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(1, { price: 5 }), T0 + 100, 500), T0 + 101);
        const m2 = applicaMessaggioCanale(m1, 'omega', msg(rigaOmega(1, { price: 4 }), T0 + 200, 1), T0 + 201);
        expect((righeDi(m2, 'omega')[0] as OmegaTrade).price).toBe(4);
    });
});

// ======================================================= riga cancellata

describe('una riga assente dal blocco nuovo SPARISCE, anche se il canale ne parlava', () => {
    it('cancellata dal database dopo un messaggio fresco', () => {
        let m = conOmega([rigaOmega(1), rigaOmega(2)], T0);
        m = applicaMessaggioCanale(m, 'omega', msg(rigaOmega(2, { price: 2 }), T0 + 9_000, 3), T0 + 9_001);
        // blocco letto PRIMA del messaggio, ma la riga 2 non c'e' piu'
        m = applicaBloccoDb(m, 'omega', [rigaOmega(1)], T0 + 8_000);
        expect(righeDi(m, 'omega').map((r) => r.id)).toEqual([1]);
        expect(m.voci.has(chiaveRiga('omega', 2))).toBe(false);
    });

    it('il canale non AGGIUNGE righe: un messaggio per una riga ignota e\' scartato', () => {
        const m0 = conOmega([rigaOmega(1)], T0);
        const m1 = applicaMessaggioCanale(m0, 'omega', msg(rigaOmega(42), T0 + 1_000, 1), T0 + 1_001);
        expect(m1).toBe(m0);
        expect(righeDi(m1, 'omega').map((r) => r.id)).toEqual([1]);
    });
});

// ======================================================= chiave composta

describe('chiave composta bot+id: stesso id su bot diversi non collide', () => {
    it('Omega #7 e Safe #7 convivono, e il messaggio di uno non tocca l\'altro', () => {
        const o7 = rigaOmega(7, { price: 8.4 });
        const s7 = rigaSafe(7, { price: 1.9 });
        let m = applicaBloccoDb(mappaVuota<Riga>(), 'omega', [o7], T0);
        m = applicaBloccoDb(m, 'safe', [s7], T0);
        expect(righeDi(m, 'omega')).toEqual([o7]);
        expect(righeDi(m, 'safe')).toEqual([s7]);

        m = applicaMessaggioCanale(m, 'safe', msg(rigaSafe(7, { price: 1.5 }), T0 + 100, 1), T0 + 101);
        expect((righeDi(m, 'safe')[0] as SafeTrade).price).toBe(1.5);
        expect(righeDi(m, 'omega')[0]).toBe(o7);
    });

    it('il blocco di un bot non cancella le righe con lo stesso id dell\'altro', () => {
        let m = applicaBloccoDb(mappaVuota<Riga>(), 'omega', [rigaOmega(7)], T0);
        m = applicaBloccoDb(m, 'safe', [rigaSafe(7)], T0);
        m = applicaBloccoDb(m, 'omega', [], T0 + 30_000);
        expect(righeDi(m, 'omega')).toEqual([]);
        expect(righeDi(m, 'safe').map((r) => r.id)).toEqual([7]);
    });
});

// ======================================================= sport del topic

describe('Safe: il topic dice lo sport, la riga deve coincidere (fail-closed)', () => {
    it('una riga tennis arrivata su safe_posizioni_calcio si scarta', () => {
        const m0 = applicaBloccoDb(mappaVuota<Riga>(), 'safe', [rigaSafe(3)], T0);
        const sbagliato = applicaMessaggioCanale(m0, 'safe', msg(rigaSafe(3, { price: 1.2 }), T0 + 10, 1), T0 + 11, 'calcio');
        expect(sbagliato).toBe(m0);
        const giusto = applicaMessaggioCanale(m0, 'safe', msg(rigaSafe(3, { price: 1.2 }), T0 + 10, 1), T0 + 11, 'tennis');
        expect((righeDi(giusto, 'safe')[0] as SafeTrade).price).toBe(1.2);
    });
});
