// ============================================================================
// chiusuraUtente.test.ts — «SE CHIUDO IO, IL BOT DEVE SAPERLO».
//
// Il finto parla come il VERO: i marcatori qui sotto hanno le chiavi ESATTE
// che scrive `Betfair/safe_strategy/bot_service.segna_chiuso_dall_utente`
// (`{"quando": iso, "come": "cashout"|"cashout_event"|"fuori_app",
//   "event_id": …}`) e i payload sono quelli che la RPC `safe_request` valida
// («payload % senza event_id»). Un finto piu' generoso del vero certifica un
// bug — il 15/09 e' costato 32 ordini veri.
//
// FALSIFICAZIONE (verificata a mano, e i test tornano ROSSI):
//   · `marcatoreRiga` che torna un marcatore anche per `false` → rosso;
//   · `statoChiusuraEvento` che deduce la chiusura da «nessuna riga viva» → rosso;
//   · `payloadCashoutEvento` che lascia partire un event_id vuoto → rosso;
//   · l'elenco del servizio ignorato quando le righe non portano il marcatore → rosso.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    marcatoreRiga, statoChiusuraEvento, eventiChiusiDalleRighe, comeLabel,
    payloadCashoutEvento, payloadRiprendiEvento, EventoMancante,
    motivoCashoutSpento, motivoRiprendiSpento,
} from './chiusuraUtente';

/** IDENTICO a quello che scrive il servizio (bot_service.py:1761). */
const MARCATORE = {
    quando: '2026-09-16T20:15:00+00:00',
    come: 'cashout_event',
    event_id: '35797769',
};

describe('marcatoreRiga — si legge quello che il servizio ha scritto', () => {
    it('la forma VERA: dict con quando/come/event_id', () => {
        const m = marcatoreRiga({ event_id: '35797769', meta: { chiuso_dall_utente: MARCATORE } });
        expect(m).not.toBeNull();
        expect(m?.quando).toBe('2026-09-16T20:15:00+00:00');
        expect(m?.come).toBe('cashout_event');
        expect(m?.dettaglio.event_id).toBe('35797769');
    });

    it('riga senza marcatore = NON chiusa dall utente', () => {
        expect(marcatoreRiga({ event_id: 'e1', meta: { hedge: { fraction: 1 } } })).toBeNull();
        expect(marcatoreRiga({ event_id: 'e1', meta: null })).toBeNull();
        expect(marcatoreRiga(null)).toBeNull();
    });

    it('`false` NON e un marcatore: significa «non chiusa», non «chiusa»', () => {
        expect(marcatoreRiga({ event_id: 'e1', meta: { chiuso_dall_utente: false } })).toBeNull();
    });

    it('marcatore degradato a `true`: resta un marcatore (fail-closed), senza istante', () => {
        const m = marcatoreRiga({ event_id: 'e1', meta: { chiuso_dall_utente: true } });
        expect(m).not.toBeNull();
        expect(m?.quando).toBeNull();     // ASSENTE non e «adesso»
        expect(m?.come).toBeNull();
    });

    it('istante vuoto = assente, mai stringa vuota sotto gli occhi', () => {
        const m = marcatoreRiga({ event_id: 'e1', meta: { chiuso_dall_utente: { quando: '  ', come: 'fuori_app' } } });
        expect(m?.quando).toBeNull();
        expect(m?.come).toBe('fuori_app');
    });
});

describe('statoChiusuraEvento — le due fonti, e chi vince', () => {
    const righe = [
        { event_id: '35797769', meta: { chiuso_dall_utente: MARCATORE } },
        { event_id: '35797769', meta: null },
        { event_id: '35760084', meta: null },
    ];

    it('SAFE: il marcatore vive sulle righe di QUELLA partita', () => {
        const s = statoChiusura('35797769');
        expect(s.chiusa).toBe(true);
        expect(s.fonte).toBe('righe');
        expect(s.marcatore?.come).toBe('cashout_event');
    });

    it('una partita SENZA marcatore non e chiusa, anche se non ha righe vive', () => {
        // la deduzione «non ci sono piu righe vive → l ha chiusa lui» e
        // esattamente l errore che questo file esiste per impedire
        expect(statoChiusura('35760084').chiusa).toBe(false);
        expect(statoChiusura('99999').chiusa).toBe(false);
    });

    it('OMEGA: l elenco del SERVIZIO vince anche senza marcatore sulle righe', () => {
        const s = statoChiusuraEvento({
            eventId: '35760084', righe, eventiDalServizio: ['35760084'],
        });
        expect(s.chiusa).toBe(true);
        expect(s.fonte).toBe('servizio');
        expect(s.marcatore).toBeNull();     // nessun dettaglio: si dichiara, non si inventa
    });

    it('event_id assente = nessuno stato (non si chiede niente al servizio)', () => {
        expect(statoChiusuraEvento({ eventId: null, righe }).chiusa).toBe(false);
        expect(statoChiusuraEvento({ eventId: '   ', righe }).chiusa).toBe(false);
    });

    it('l indice per evento prende il PRIMO marcatore trovato, una volta sola', () => {
        const idx = eventiChiusiDalleRighe(righe);
        expect(idx.size).toBe(1);
        expect(idx.get('35797769')?.come).toBe('cashout_event');
        expect(idx.has('35760084')).toBe(false);
    });

    function statoChiusura(eid: string) {
        return statoChiusuraEvento({ eventId: eid, righe });
    }
});

describe('comeLabel — i tre modi, in italiano', () => {
    it('i tre codici veri del servizio', () => {
        expect(comeLabel('cashout_event')).toContain('cash out globale');
        expect(comeLabel('cashout')).toContain('ultima posizione');
        expect(comeLabel('fuori_app')).toContain('Betfair');
    });
    it('un codice sconosciuto non arriva con gli underscore', () => {
        expect(comeLabel('qualcosa_di_nuovo')).toBe('qualcosa di nuovo');
    });
    it('assente = niente da scrivere', () => {
        expect(comeLabel(null)).toBeNull();
        expect(comeLabel('')).toBeNull();
    });
});

describe('i payload — campo per campo, come li valida la RPC', () => {
    it('cashout_event porta SOLO event_id: quali righe chiudere lo decide il servizio', () => {
        expect(payloadCashoutEvento('35797769')).toEqual({ event_id: '35797769' });
        expect(Object.keys(payloadCashoutEvento('35797769'))).toEqual(['event_id']);
    });

    it('riprendi_evento: stesso payload', () => {
        expect(payloadRiprendiEvento(' 35797769 ')).toEqual({ event_id: '35797769' });
    });

    it('senza event_id la richiesta NON parte, e lo dice in italiano', () => {
        expect(() => payloadCashoutEvento('')).toThrow(EventoMancante);
        expect(() => payloadCashoutEvento(null)).toThrow(/identificativo della partita/);
        expect(() => payloadRiprendiEvento('   ')).toThrow(EventoMancante);
    });
});

describe('un pulsante spento dice PERCHE (mai un disabled muto)', () => {
    it('cash out: senza posizioni vive non c e niente da chiudere', () => {
        expect(motivoCashoutSpento({ eventId: 'e1', posizioniVive: 0, chiusa: false }))
            .toMatch(/nessuna posizione viva/);
    });
    it('cash out: partita gia chiusa da te', () => {
        expect(motivoCashoutSpento({ eventId: 'e1', posizioniVive: 2, chiusa: true }))
            .toMatch(/gia/);
    });
    it('cash out: richiesta in volo', () => {
        expect(motivoCashoutSpento({ eventId: 'e1', posizioniVive: 2, chiusa: false, inCorso: true }))
            .toMatch(/in corso/);
    });
    it('cash out possibile = nessun motivo', () => {
        expect(motivoCashoutSpento({ eventId: 'e1', posizioniVive: 1, chiusa: false })).toBeNull();
    });
    it('riprendi: solo su una partita marcata', () => {
        expect(motivoRiprendiSpento({ eventId: 'e1', chiusa: false })).toMatch(/niente da riprendere/);
        expect(motivoRiprendiSpento({ eventId: 'e1', chiusa: true })).toBeNull();
    });
    it('senza event_id nessuno dei due si accende', () => {
        expect(motivoCashoutSpento({ eventId: '', posizioniVive: 3, chiusa: false })).toBeTruthy();
        expect(motivoRiprendiSpento({ eventId: '', chiusa: true })).toBeTruthy();
    });
});
