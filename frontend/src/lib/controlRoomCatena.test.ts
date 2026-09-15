// ============================================================================
// controlRoomCatena.test.ts — i test della catena dei tempi.
//
// Qui non si misura la correttezza di una formula: si impedisce che la pagina
// dica al trader «istantaneo» quando la verità è «non lo so».
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    delta, catenaOperazione, totaleCatena, totaleNostro, colloDiBottiglia,
    catenaSchermo, fmtMs,
} from './controlRoomCatena';

const T = 1_700_000_000_000;

const tempiOk = { t0_quote_ms: T, t1_feed_ms: T + 120, t2_letto_ms: T + 900, t3_deciso_ms: T + 950 };
const esecOk = { t4_inviato: T + 1000, t5_risposta: T + 1180, betfair_ms: 180 };

describe('delta — «non lo so» non è zero', () => {
    it('misura la differenza quando entrambi gli istanti ci sono', () => {
        expect(delta(T, T + 250)).toBe(250);
    });

    it('un istante MANCANTE dà null, mai 0', () => {
        expect(delta(null, T)).toBeNull();
        expect(delta(T, undefined)).toBeNull();
        expect(delta(T, Number.NaN)).toBeNull();
    });

    it('differenza NEGATIVA (orologi diversi) dà null, non un numero impossibile', () => {
        expect(delta(T + 500, T)).toBeNull();
    });

    it('zero vero resta zero: due istanti uguali sono davvero istantanei', () => {
        expect(delta(T, T)).toBe(0);
    });
});

describe('catenaOperazione — sei salti, da Betfair al fill', () => {
    it('costruisce i sei salti con i numeri giusti', () => {
        const c = catenaOperazione(tempiOk, esecOk, T + 1200);
        expect(c.map((s) => [s.id, s.ms])).toEqual([
            ['eta_prezzo', 120],  // da quanto il prezzo era fermo — NON una latenza
            ['lettura', 780],     // riga -> letta dal bot
            ['decisione', 50],    // in mano -> deciso
            ['invio', 50],        // deciso -> chiamata
            ['betfair', 180],     // risposta di Betfair
            ['fill', 20],         // risposta -> abbinato
        ]);
    });

    it('marca UN SOLO salto come non nostro: quello di Betfair', () => {
        const c = catenaOperazione(tempiOk, esecOk, T + 1200);
        expect(c.filter((s) => !s.nostro).map((s) => s.id)).toEqual(['betfair']);
    });

    it('senza istanti la catena esiste ma è tutta vuota: nessuno zero inventato', () => {
        const c = catenaOperazione(null, null, null);
        expect(c).toHaveLength(6);
        expect(c.every((s) => s.ms === null)).toBe(true);
    });

    it('usa `betfair_ms` del servizio quando c’è, invece di risottrarre', () => {
        const c = catenaOperazione(tempiOk, { t4_inviato: T, t5_risposta: T + 9999, betfair_ms: 210 }, null);
        expect(c.find((s) => s.id === 'betfair')?.ms).toBe(210);
    });

    it('e ripiega sulla sottrazione se `betfair_ms` manca', () => {
        const c = catenaOperazione(tempiOk, { t4_inviato: T, t5_risposta: T + 300 }, null);
        expect(c.find((s) => s.id === 'betfair')?.ms).toBe(300);
    });
});

describe('totali — un totale parziale è peggio di nessun totale', () => {
    it('somma le LATENZE, non l’età del prezzo', () => {
        // 1200 meno i 120 ms di «prezzo già fermo da», che non è un ritardo
        expect(totaleCatena(catenaOperazione(tempiOk, esecOk, T + 1200))).toBe(1080);
    });

    it('BASTA UN SALTO MANCANTE e il totale è null: non si somma quello che si ha', () => {
        const c = catenaOperazione(tempiOk, esecOk, null);   // manca il fill
        expect(totaleCatena(c)).toBeNull();
    });

    it('il totale NOSTRO esclude Betfair', () => {
        expect(totaleNostro(catenaOperazione(tempiOk, esecOk, T + 1200))).toBe(900);
    });

    it('il totale nostro è null se manca un pezzo NOSTRO', () => {
        // manca t1: il salto «Betfair -> feed» e quello dopo non si misurano
        const senzaNostro = catenaOperazione({ t0_quote_ms: T }, esecOk, T + 1200);
        expect(totaleNostro(senzaNostro)).toBeNull();
    });

    it('il tempo di Betfair NON entra nel totale nostro, ed è la sua unica differenza', () => {
        const lento = catenaOperazione(tempiOk, { ...esecOk, betfair_ms: 5000 }, T + 1200);
        // il totale nostro non si muove anche se Betfair ci mette 5 secondi
        expect(totaleNostro(lento)).toBe(900);
        // ma il totale complessivo sì
        expect(totaleCatena(lento)).toBe(900 + 5000);
    });
});

describe('colloDiBottiglia — dove se ne va il tempo', () => {
    it('trova il salto più lento fra quelli MISURATI', () => {
        const c = catenaOperazione(tempiOk, esecOk, T + 1200);
        expect(colloDiBottiglia(c)?.id).toBe('lettura');   // 780 ms sul database
    });

    it('ignora i salti non misurati invece di trattarli come zero', () => {
        const c = catenaOperazione(
            { t0_quote_ms: T, t1_feed_ms: T, t2_letto_ms: T + 40 }, null, null);
        expect(colloDiBottiglia(c)?.id).toBe('lettura');
    });

    it('L’ETÀ DEL PREZZO NON È UN COLLO DI BOTTIGLIA: non è tempo nostro', () => {
        // prezzo fermo da 5 minuti su un mercato poco scambiato, e una lettura
        // lenta da 800 ms: il colpevole è la lettura, non il mercato immobile.
        const c = catenaOperazione(
            { t0_quote_ms: T, t1_feed_ms: T + 300_000, t2_letto_ms: T + 300_800 },
            null, null);
        expect(colloDiBottiglia(c)?.id).toBe('lettura');
    });

    it('senza nessun salto misurato non inventa un colpevole', () => {
        expect(colloDiBottiglia(catenaOperazione(null, null, null))).toBeNull();
    });
});

describe('catenaSchermo — quanto è vecchio quello che vedo ADESSO', () => {
    it('prende il PEGGIORE dei tre canali, non il migliore', () => {
        const c = catenaSchermo({ feedMs: 800, pushMs: 200, letturaMs: 25_000 });
        expect(c.schermoMs).toBe(25_000);
    });

    it('un canale assente non abbassa il giudizio: si usa quello che si sa', () => {
        expect(catenaSchermo({ feedMs: 900, pushMs: null, letturaMs: null }).schermoMs).toBe(900);
    });

    it('nessun canale noto → null, non zero', () => {
        expect(catenaSchermo({}).schermoMs).toBeNull();
    });

    it('valori impossibili (negativi) non contano', () => {
        expect(catenaSchermo({ feedMs: -5, pushMs: 300 }).schermoMs).toBe(300);
    });
});

describe('fmtMs — si legge a colpo d’occhio', () => {
    it('millisecondi sotto il secondo, secondi sopra, minuti oltre', () => {
        expect(fmtMs(180)).toBe('180 ms');
        expect(fmtMs(1500)).toBe('1.5 s');
        expect(fmtMs(120_000)).toBe('2 min');
    });

    it('ASSENTE è «—», mai «0 ms»', () => {
        expect(fmtMs(null)).toBe('—');
        expect(fmtMs(undefined)).toBe('—');
        expect(fmtMs(Number.NaN)).toBe('—');
    });

    it('zero vero si stampa: è un’informazione, non un’assenza', () => {
        expect(fmtMs(0)).toBe('0 ms');
    });
});

// ===========================================================================
// REVIEW 15/09 — IL PRIMO TRATTO NON È UNA LATENZA.
//
// `t0_quote_ms` è l'istante dell'ultimo CAMBIO di prezzo, non quello in cui
// Betfair ce l'ha mandato. Contarlo come ritardo faceva sembrare lentissima
// una pipeline che gira in millisecondi.
// ===========================================================================

describe('età del prezzo: si mostra, non si somma', () => {
    it('il primo tratto è marcato come NON latenza', () => {
        const c = catenaOperazione(tempiOk, esecOk, T + 1200);
        expect(c[0].id).toBe('eta_prezzo');
        expect(c[0].latenza).toBe(false);
        expect(c.slice(1).every((s) => s.latenza)).toBe(true);
    });

    it('un prezzo fermo da CINQUE MINUTI non gonfia i totali', () => {
        const fermo = {
            t0_quote_ms: T, t1_feed_ms: T + 300_000,
            t2_letto_ms: T + 300_100, t3_deciso_ms: T + 300_150,
        };
        const c = catenaOperazione(fermo, {
            t4_inviato: T + 300_200, t5_risposta: T + 300_400, betfair_ms: 200,
        }, T + 300_450);
        // 100 + 50 + 50 + 200 + 50 = 450 ms, non cinque minuti
        expect(totaleCatena(c)).toBe(450);
        expect(totaleNostro(c)).toBe(250);
    });

    it('il numero dell’età resta comunque LEGGIBILE: è un’informazione utile', () => {
        const c = catenaOperazione({ t0_quote_ms: T, t1_feed_ms: T + 300_000 }, null, null);
        expect(c[0].ms).toBe(300_000);
        expect(c[0].nome).toMatch(/fermo/i);
    });
});
