// ============================================================================
// LA FUSIONE DEL CANALE LOCALE — il push SOVRAPPONE, non sostituisce.
//
// Il servizio spinge le schede sul socket a ogni giro; su Postgres scrive solo
// quando cambia qualcosa di sostanziale. Il socket è quindi più FRESCO ma non
// più COMPLETO (non manda dossier/markets/ctx, che sono fermi e pesanti).
//
// La regola che questi test difendono, e che vale più della velocità:
//   se il socket cade, NON deve sparire nessun numero.
// Un P&L che diventa «—» perché è caduto un WebSocket è peggio di un P&L
// vecchio di due secondi.
// ============================================================================
import { describe, it, expect } from 'vitest';

import { fondiEventiLocali, type MikeEvent, type MikeEventoSpinto } from '@/lib/mike';

const evento = (over: Partial<MikeEvent> = {}): MikeEvent => ({
    event_id: 'E1',
    event_name: 'Tizio v Caio',
    state: 'HOLD',
    mode: 'paper',
    live: { inplay: false, minute: 0 },
    positions: [],
    settled_pnl: null,
    ...over,
} as MikeEvent);

const mappa = (...p: MikeEventoSpinto[]) => new Map(p.map((x) => [x.event_id, x]));

describe('fondiEventiLocali — il push sovrappone', () => {
    it('senza niente dal socket restituisce ESATTAMENTE le schede del database', () => {
        const db = [evento(), evento({ event_id: 'E2' })];
        expect(fondiEventiLocali(db, new Map())).toBe(db);
    });

    it('i campi spinti vincono su quelli del database', () => {
        const db = [evento({ live: { inplay: false, minute: 0 } })];
        const out = fondiEventiLocali(db, mappa({ event_id: 'E1', live: { inplay: true, minute: 63 } }));
        expect(out[0].live).toEqual({ inplay: true, minute: 63 });
    });

    it('i campi che il socket NON manda restano quelli del database', () => {
        // è il cuore della regola: il push non porta dossier/markets/ctx
        const db = [evento({ dossier: { lambda: 2.4 }, markets: { OU35: { market_id: '1.35' } } } as Partial<MikeEvent>)];
        const out = fondiEventiLocali(db, mappa({ event_id: 'E1', state: 'LIVE_UNCOVERED' }));
        expect(out[0].state).toBe('LIVE_UNCOVERED');
        expect((out[0] as unknown as Record<string, unknown>).dossier).toEqual({ lambda: 2.4 });
        expect((out[0] as unknown as Record<string, unknown>).markets).toEqual({ OU35: { market_id: '1.35' } });
    });

    it('una scheda che il socket non ha mandato resta intatta', () => {
        const db = [evento(), evento({ event_id: 'E2', state: 'WATCH' })];
        const out = fondiEventiLocali(db, mappa({ event_id: 'E1', state: 'PRE_OPEN' }));
        expect(out[0].state).toBe('PRE_OPEN');
        expect(out[1].state).toBe('WATCH');
        expect(out).toHaveLength(2);
    });

    it('una partita che il database non ha ancora scritto viene AGGIUNTA', () => {
        // il bot l'ha appena presa in carico: sul socket c'è già, su Postgres no.
        // Mostrarla subito è il punto di tutto il lavoro.
        const out = fondiEventiLocali([evento()], mappa({ event_id: 'E9', state: 'WATCH', event_name: 'Nuova' }));
        expect(out).toHaveLength(2);
        expect(out[1].event_id).toBe('E9');
    });

    it('l’ordine delle schede del database non cambia', () => {
        const db = [evento({ event_id: 'A' }), evento({ event_id: 'B' }), evento({ event_id: 'C' })];
        const out = fondiEventiLocali(db, mappa({ event_id: 'B', state: 'FLAT' }));
        expect(out.map((e) => e.event_id)).toEqual(['A', 'B', 'C']);
    });

    it('NON muta gli oggetti del database', () => {
        const originale = evento({ state: 'HOLD' });
        const db = [originale];
        fondiEventiLocali(db, mappa({ event_id: 'E1', state: 'FLAT' }));
        expect(originale.state).toBe('HOLD');
        expect(db[0]).toBe(originale);
    });

    it('SOCKET CADUTO: nessun numero sparisce', () => {
        // si passa da "push attivo" a "push vuoto": la pagina deve tornare ai
        // numeri del database, non a NIENTE.
        const db = [evento({ settled_pnl: -4.05, live: { inplay: true, minute: 70 } })];
        const conPush = fondiEventiLocali(db, mappa({ event_id: 'E1', live: { inplay: true, minute: 71 } }));
        expect(conPush[0].live).toEqual({ inplay: true, minute: 71 });
        expect(conPush[0].settled_pnl).toBe(-4.05);

        const senzaPush = fondiEventiLocali(db, new Map());
        expect(senzaPush[0].settled_pnl).toBe(-4.05);
        expect(senzaPush[0].live).toEqual({ inplay: true, minute: 70 });
    });

    // ------------------------------------------------------------------
    // IL DIFETTO CRITICO TROVATO IN REVIEW IL 14/09.
    // `updated_at` significa «quando il DATABASE ha scritto questa riga», e la
    // copia che il servizio ha in memoria è quella dell'ultima rilettura —
    // fino a 60 s fa. La card è memoizzata proprio su quel campo: un
    // `updated_at` che ARRETRA la congela, e siccome la card si ridisegna
    // comunque ogni secondo per conto suo, il semaforo del feed diventa rosso
    // e SPEGNE IL BOTTONE DI CASH OUT su una posizione aperta.
    // La funzione nata per rendere la pagina viva l'avrebbe resa 12 volte più
    // vecchia. Questi test impediscono che torni.
    // ------------------------------------------------------------------
    it('l’orologio della scheda NON torna mai indietro', () => {
        const db = [evento({ updated_at: '2026-09-14T10:00:05.000Z' } as Partial<MikeEvent>)];
        const out = fondiEventiLocali(db, mappa({
            event_id: 'E1',
            live: { inplay: true, minute: 71, published_at: '2026-09-14T10:00:09.000Z' },
        } as MikeEventoSpinto));
        expect(Date.parse(String(out[0].updated_at)))
            .toBeGreaterThanOrEqual(Date.parse('2026-09-14T10:00:05.000Z'));
    });

    it('un push VECCHIO non riporta indietro l’ora del database', () => {
        const db = [evento({ updated_at: '2026-09-14T10:00:30.000Z' } as Partial<MikeEvent>)];
        const out = fondiEventiLocali(db, mappa({
            event_id: 'E1',
            live: { inplay: true, published_at: '2026-09-14T10:00:05.000Z' },
        } as MikeEventoSpinto));
        expect(out[0].updated_at).toBe('2026-09-14T10:00:30.000Z');
    });

    it('un push SENZA published_at lascia l’ora del database', () => {
        const db = [evento({ updated_at: '2026-09-14T10:00:30.000Z' } as Partial<MikeEvent>)];
        const out = fondiEventiLocali(db, mappa({ event_id: 'E1', state: 'FLAT' }));
        expect(out[0].updated_at).toBe('2026-09-14T10:00:30.000Z');
        expect(out[0].state).toBe('FLAT');
    });

    it('un push con published_at ILLEGGIBILE non inventa un’ora', () => {
        const db = [evento({ updated_at: '2026-09-14T10:00:30.000Z' } as Partial<MikeEvent>)];
        const out = fondiEventiLocali(db, mappa({
            event_id: 'E1', live: { published_at: 'ieri verso sera' },
        } as MikeEventoSpinto));
        expect(out[0].updated_at).toBe('2026-09-14T10:00:30.000Z');
    });

    it('una partita SOLO nel push prende l’ora dal push, non undefined', () => {
        // `undefined` farebbe scattare lo stesso blocco del cash out, per prudenza
        const out = fondiEventiLocali([], mappa({
            event_id: 'E9', state: 'WATCH',
            live: { published_at: '2026-09-14T10:00:09.000Z' },
        } as MikeEventoSpinto));
        expect(out[0].updated_at).toBe('2026-09-14T10:00:09.000Z');
    });

    it('un push MALFORMATO senza event_id non fa danni', () => {
        const db = [evento()];
        // la mappa è costruita per event_id: una chiave vuota non collide con E1
        const out = fondiEventiLocali(db, new Map([['', { event_id: '' } as MikeEventoSpinto]]));
        expect(out[0].event_id).toBe('E1');
        expect(out[0].state).toBe('HOLD');
        // e non deve nemmeno essere AGGIUNTA in coda: la funzione si difende da
        // sola, non solo grazie al filtro del chiamante
        expect(out).toHaveLength(1);
    });
});
