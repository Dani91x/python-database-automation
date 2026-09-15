// ============================================================================
// controlRoom.test.ts — i test della matematica della Control Room.
//
// Non verificano «che le funzioni girino»: verificano le REGOLE che, se si
// rompono, mettono un numero falso davanti a chi rischia soldi. Ogni blocco
// dice quale bugia impedisce.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    freschezza, affidabilePerPiazzare, statoPartita, koMs, punteggio, nomePartita, campionato,
    haControlloGioco, coperturaControllo, targetPartita, avanzamentoPartita, soldiPerPartita, latenzaQuoteS,
    marca, costruisciGiornata, totaliGiornata, etaSecondi, statoQuote, quoteAffidabili, realizzatoGiornata,
    SENZA_CAMPIONATO, TARGET_MIN_EUR,
    type PartitaFeedLike,
} from './controlRoom';
import type { PnlTradeLike } from './eventGroups';

const T0 = Date.parse('2026-09-14T15:00:00Z');

function feed(over: Partial<PartitaFeedLike> = {}): PartitaFeedLike {
    return { event_name: 'A – B', competition: 'Serie A', open_date: '2026-09-14T13:00:00Z', inplay: false, ...over };
}

function trade(over: Partial<PnlTradeLike> & { id: number; event_id: string; status: string }): PnlTradeLike {
    // `mode` NON ha default qui apposta: chi scrive un test deve dichiararlo,
    // esattamente come deve dichiararlo il servizio. Senza, vale 'paper'.
    return { placed_at: '2026-09-14T14:00:00Z', ...over } as PnlTradeLike;
}

/** una riga con SOLDI VERI */
function tradeLive(over: Partial<PnlTradeLike> & { id: number; event_id: string; status: string }): PnlTradeLike {
    return trade({ mode: 'live', ...over } as never);
}

// ---------------------------------------------------------------- freschezza

describe('freschezza — un\'età che non sappiamo non è "fresca"', () => {
    it('classifica secondo le soglie condivise (5 s / 20 s)', () => {
        expect(freschezza(0)).toBe('fresca');
        expect(freschezza(5)).toBe('fresca');
        expect(freschezza(6)).toBe('lenta');
        expect(freschezza(20)).toBe('lenta');
        expect(freschezza(21)).toBe('vecchia');
    });

    it('ETÀ ASSENTE = "ignota", MAI "fresca": è il fail-closed', () => {
        expect(freschezza(null)).toBe('ignota');
        expect(freschezza(undefined)).toBe('ignota');
        expect(freschezza(Number.NaN)).toBe('ignota');
    });

    it('su un\'età ignota NON si piazza', () => {
        expect(affidabilePerPiazzare(freschezza(null))).toBe(false);
        expect(affidabilePerPiazzare(freschezza(999))).toBe(false);
        expect(affidabilePerPiazzare(freschezza(3))).toBe(true);
        expect(affidabilePerPiazzare(freschezza(12))).toBe(true);
    });

    it('etaSecondi non restituisce mai 0 per "non lo so"', () => {
        expect(etaSecondi(null, T0)).toBeNull();
        expect(etaSecondi('non-una-data', T0)).toBeNull();
        expect(etaSecondi('2026-09-14T14:59:50Z', T0)).toBe(10);
    });
});

// ------------------------------------------------------------- stato partita

describe('statoPartita', () => {
    it('in gioco → live, fischio futuro → pre, fischio passato e non in gioco → chiusa', () => {
        expect(statoPartita(feed({ inplay: true }), T0)).toBe('live');
        expect(statoPartita(feed({ open_date: '2026-09-14T18:00:00Z' }), T0)).toBe('pre');
        expect(statoPartita(feed({ open_date: '2026-09-14T12:00:00Z' }), T0)).toBe('chiusa');
    });

    it('senza riga di feed non si inventa uno stato', () => {
        expect(statoPartita(null, T0)).toBe('chiusa');
        expect(koMs(null)).toBeNull();
        expect(koMs(feed({ open_date: 'boh' }))).toBeNull();
    });

    it('il punteggio assente è null, NON "0-0"', () => {
        expect(punteggio(feed({ score_home: 1, score_away: 0 }))).toBe('1-0');
        expect(punteggio(feed({ score_home: 0, score_away: 0 }))).toBe('0-0');
        expect(punteggio(feed())).toBeNull();
        expect(punteggio(feed({ score_home: 1 }))).toBeNull();
    });

    it('il nome ripiega su home–away e poi sull\'id, senza mai restare vuoto', () => {
        expect(nomePartita(feed(), 'E1')).toBe('A – B');
        expect(nomePartita(feed({ event_name: '  ', home: 'Roma', away: 'Lazio' }), 'E1')).toBe('Roma – Lazio');
        expect(nomePartita(feed({ event_name: null, home: null }), 'E1')).toBe('E1');
        expect(nomePartita(null, 'E1')).toBe('E1');
    });

    it('il campionato mancante finisce in UN solo gruppo di ripiego', () => {
        expect(campionato(feed({ competition: 'Liga' }))).toBe('Liga');
        expect(campionato(feed({ competition: '   ' }))).toBe(SENZA_CAMPIONATO);
        expect(campionato(feed({ competition: null }))).toBe(SENZA_CAMPIONATO);
        expect(campionato(null)).toBe(SENZA_CAMPIONATO);
    });
});

// ------------------------------------------------------------------- tennis

describe('tennis — punteggio, nome, e nessun minuto', () => {
    it('set e game insieme', () => {
        expect(punteggio(feed({ sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 0 } }))).toBe('1-0 · 3-0');
    });

    it('solo set quando i game non ci sono', () => {
        expect(punteggio(feed({ sets: { p1: 2, p2: 1 } }))).toBe('2-1');
    });

    it('0-0 nel tennis È un punteggio: non si confonde con «non lo so»', () => {
        expect(punteggio(feed({ sets: { p1: 0, p2: 0 }, games: { p1: 0, p2: 0 } }))).toBe('0-0 · 0-0');
    });

    it('il nome ripiega sui due giocatori', () => {
        expect(nomePartita(feed({ event_name: null, p1: 'Rune', p2: 'Musetti' }), 'T1')).toBe('Rune – Musetti');
    });

    it('il tennis non ha `pressure_index`: non entra nella copertura', () => {
        expect(haControlloGioco(feed({ sets: { p1: 1, p2: 0 } }))).toBe(false);
    });
});

describe('latenzaQuoteS — quanto è vecchio il prezzo su cui si opera', () => {
    it('misura dall’istante in cui lo scanner ha letto le quote', () => {
        expect(latenzaQuoteS(feed({ odds_ts_ms: T0 - 4000 }), T0)).toBe(4);
    });

    it('ASSENTE vale null, MAI zero: un prezzo di età ignota non è un prezzo fresco', () => {
        expect(latenzaQuoteS(feed(), T0)).toBeNull();
        expect(latenzaQuoteS(feed({ odds_ts_ms: null }), T0)).toBeNull();
        expect(latenzaQuoteS(feed({ odds_ts_ms: 0 }), T0)).toBeNull();
        expect(freschezza(latenzaQuoteS(feed(), T0))).toBe('ignota');
    });

    it('non torna mai negativa se l’orologio dello scanner è avanti', () => {
        expect(latenzaQuoteS(feed({ odds_ts_ms: T0 + 5000 }), T0)).toBe(0);
    });
});

describe('statoQuote — «fermo» e «vecchio» sono due cose diverse', () => {
    it('prezzo recente: fresco, a prescindere dallo scanner', () => {
        expect(statoQuote(3, 2)).toBe('fresco');
        expect(statoQuote(3, 9999)).toBe('fresco');
    });

    it('prezzo vecchio MA scanner vivo = FERMO: il mercato non si muove, il prezzo è corrente', () => {
        expect(statoQuote(120, 4)).toBe('fermo');
        expect(statoQuote(600, 15)).toBe('fermo');
    });

    it('prezzo vecchio E scanner fermo = VECCHIO: non sappiamo cosa fa il mercato', () => {
        expect(statoQuote(120, 300)).toBe('vecchio');
        expect(statoQuote(120, null)).toBe('vecchio');
    });

    it('età del prezzo assente = IGNOTO, mai fresco', () => {
        expect(statoQuote(null, 2)).toBe('ignoto');
        expect(statoQuote(undefined, 2)).toBe('ignoto');
    });

    it('su FERMO si opera (è il prezzo corrente); su VECCHIO e IGNOTO no', () => {
        expect(quoteAffidabili('fresco')).toBe(true);
        expect(quoteAffidabili('fermo')).toBe(true);
        expect(quoteAffidabili('vecchio')).toBe(false);
        expect(quoteAffidabili('ignoto')).toBe(false);
    });
});

// ----------------------------------------------------- controllo del gioco

describe('controllo del gioco — assente NON è zero', () => {
    it('zero è un dato ("gioco in equilibrio"), undefined è assenza', () => {
        expect(haControlloGioco(feed({ pressure_index: 0 }))).toBe(true);
        expect(haControlloGioco(feed({ pressure_index: -0.4 }))).toBe(true);
        expect(haControlloGioco(feed())).toBe(false);
        expect(haControlloGioco(feed({ pressure_index: null }))).toBe(false);
    });

    it('REGRESSIONE: un campo undefined non deve contare come DATO PRESENTE', () => {
        // con `!= null` questo passerebbe e la spia direbbe al trader
        // l'esatto contrario del vero.
        const senza = { ...feed() } as PartitaFeedLike;
        delete (senza as Record<string, unknown>).pressure_index;
        expect(haControlloGioco(senza)).toBe(false);
    });

    it('la copertura conta quante partite hanno il dato', () => {
        const c = coperturaControllo([
            feed({ pressure_index: 0.2 }),
            feed({ pressure_index: 0 }),
            feed(),
            null,
        ]);
        expect(c).toEqual({ conDato: 2, senzaDato: 2, totale: 4, pct: 50 });
    });

    it('su zero partite non esiste una percentuale, e non se ne inventa una', () => {
        expect(coperturaControllo([]).pct).toBeNull();
    });
});

// ------------------------------------------------------------------- target

describe('targetPartita — il servizio vince sempre sul ripiego', () => {
    it('usa il target del SERVIZIO quando c\'è, e lo dichiara', () => {
        const t = targetPartita({ targetServizio: 12.5, obiettivo: 250, realizzato: 0, partiteUtili: 4 });
        expect(t).toEqual({ valore: 12.5, fonte: 'servizio' });
    });

    it('ripiega sul calcolo locale SOLO se il servizio non dà un numero, e lo DICHIARA', () => {
        const t = targetPartita({ targetServizio: null, obiettivo: 250, realizzato: 50, partiteUtili: 4 });
        expect(t).toEqual({ valore: 50, fonte: 'ripiego' });
    });

    it('un target del servizio a zero o negativo non è un target', () => {
        expect(targetPartita({ targetServizio: 0, obiettivo: 100, realizzato: 0, partiteUtili: 2 })?.fonte).toBe('ripiego');
        expect(targetPartita({ targetServizio: -3, obiettivo: 100, realizzato: 0, partiteUtili: 2 })?.fonte).toBe('ripiego');
    });

    it('obiettivo CENTRATO → nessun target da spalmare (null, non zero)', () => {
        expect(targetPartita({ obiettivo: 250, realizzato: 250, partiteUtili: 5 })).toBeNull();
        expect(targetPartita({ obiettivo: 250, realizzato: 300, partiteUtili: 5 })).toBeNull();
    });

    it('senza partite utili non si divide per zero', () => {
        expect(targetPartita({ obiettivo: 250, realizzato: 0, partiteUtili: 0 })).toBeNull();
        expect(targetPartita({ obiettivo: 250, realizzato: 0, partiteUtili: null })).toBeNull();
    });

    it('non scende sotto il minimo: un target di 0,01 € non è un obiettivo', () => {
        const t = targetPartita({ obiettivo: 1, realizzato: 0, partiteUtili: 1000 });
        expect(t?.valore).toBe(TARGET_MIN_EUR);
    });
});

describe('avanzamentoPartita — la barra non va all\'indietro', () => {
    it('una partita IN PERDITA vale 0, non un numero negativo', () => {
        expect(avanzamentoPartita(-20, 10)).toBe(0);
    });
    it('si ferma a 100 anche se il target è stato superato', () => {
        expect(avanzamentoPartita(50, 10)).toBe(100);
        expect(avanzamentoPartita(5, 10)).toBe(50);
    });
    it('senza risultato o senza target è null, non zero', () => {
        expect(avanzamentoPartita(null, 10)).toBeNull();
        expect(avanzamentoPartita(5, null)).toBeNull();
        expect(avanzamentoPartita(5, 0)).toBeNull();
    });
});

// ------------------------------------------------------------ soldi e bot

describe('soldiPerPartita — tre bot, una riga per partita', () => {
    it('somma i tre bot sulla stessa partita e ne elenca la provenienza', () => {
        const trades = [
            ...marca([tradeLive({ id: 1, event_id: 'E1', status: 'won', pnl: 10 })], 'omega'),
            ...marca([tradeLive({ id: 2, event_id: 'E1', status: 'won', pnl: 5 })], 'mike'),
            ...marca([tradeLive({ id: 3, event_id: 'E2', status: 'lost', pnl: -4 })], 'safe'),
        ];
        const m = soldiPerPartita(trades);
        expect(m.get('E1')?.live.netPnl).toBe(15);
        expect(m.get('E1')?.bots).toEqual(['omega', 'mike']);   // ordine fisso Ω·S·M
        expect(m.get('E2')?.live.netPnl).toBe(-4);
        expect(m.get('E2')?.bots).toEqual(['safe']);
    });

    it('una partita SENZA righe regolate vale null, non 0', () => {
        const m = soldiPerPartita(marca([tradeLive({ id: 1, event_id: 'E1', status: 'open', liability: 30 })], 'safe'));
        expect(m.get('E1')?.live.netPnl).toBeNull();
        expect(m.get('E1')?.live.aperta).toBe(true);
        expect(m.get('E1')?.live.liability).toBe(30);
    });

    it('le righe in error non sono operazioni: non entrano nel netto', () => {
        const m = soldiPerPartita(marca([
            tradeLive({ id: 1, event_id: 'E1', status: 'won', pnl: 7 }),
            tradeLive({ id: 2, event_id: 'E1', status: 'error', pnl: -100 }),
        ], 'omega'));
        expect(m.get('E1')?.live.netPnl).toBe(7);
    });
});

// ---------------------------------------------------------------- giornata

describe('costruisciGiornata — campionati e orologio', () => {
    const righe = [
        { event_id: 'E3', payload: feed({ event_name: 'Girona – Betis', competition: 'Liga', open_date: '2026-09-14T14:00:00Z', inplay: true }), updated_at: '2026-09-14T14:59:58Z' },
        { event_id: 'E1', payload: feed({ event_name: 'Milan – Inter', competition: 'Serie A', open_date: '2026-09-14T13:00:00Z', inplay: true }), updated_at: '2026-09-14T14:59:59Z' },
        { event_id: 'E2', payload: feed({ event_name: 'Napoli – Roma', competition: 'Serie A', open_date: '2026-09-14T18:00:00Z' }), updated_at: '2026-09-14T14:59:00Z' },
        { event_id: 'E4', payload: feed({ event_name: 'Senza orario', competition: 'Serie A', open_date: null }), updated_at: null },
    ];

    it('raggruppa per campionato e ordina i campionati per primo fischio', () => {
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0, obiettivo: 250, realizzato: 0 });
        expect(g.map((x) => x.campionato)).toEqual(['Serie A', 'Liga']);
    });

    it('dentro il campionato: prima le live, poi le pre, poi le chiuse — e in ordine cronologico', () => {
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0, obiettivo: 250, realizzato: 0 });
        const serieA = g.find((x) => x.campionato === 'Serie A')!;
        expect(serieA.partite.map((p) => p.nome)).toEqual(['Milan – Inter', 'Napoli – Roma', 'Senza orario']);
        expect(serieA.partite.map((p) => p.stato)).toEqual(['live', 'pre', 'chiusa']);
    });

    it('una partita senza orario va in fondo al suo gruppo: non si inventa un fischio', () => {
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0 });
        const serieA = g.find((x) => x.campionato === 'Serie A')!;
        expect(serieA.partite[serieA.partite.length - 1].koMs).toBeNull();
    });

    it('il target si spalma solo sulle partite ANCORA UTILI: le chiuse non possono più rendere', () => {
        // 3 partite non chiuse su 4 → 250/3, non 250/4
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0, obiettivo: 250, realizzato: 0 });
        const t = g[0].partite[0].target!;
        expect(t.fonte).toBe('ripiego');
        expect(t.valore).toBeCloseTo(250 / 3, 6);
    });

    it('il target del servizio, quando c\'è, non viene ricalcolato', () => {
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0, obiettivo: 250, realizzato: 0, targetServizio: 9 });
        expect(g[0].partite[0].target).toEqual({ valore: 9, fonte: 'servizio' });
    });

    it('porta con sé età, freschezza e disponibilità del controllo del gioco', () => {
        const g = costruisciGiornata({ righe, soldi: new Map(), nowMs: T0 });
        const milan = g[0].partite[0];
        expect(milan.etaFeedS).toBe(1);
        expect(milan.freschezza).toBe('fresca');
        expect(milan.controlloDisponibile).toBe(false);
        const senzaOrario = g[0].partite[2];
        expect(senzaOrario.etaFeedS).toBeNull();
        expect(senzaOrario.freschezza).toBe('ignota');
    });
});

describe('realizzatoGiornata - soldi veri e simulati non si sommano MAI', () => {
    const righe = [
        { status: 'won',  pnl: 0.29, mode: 'live',  sport: 'tennis' },
        { status: 'lost', pnl: -0.21, mode: 'live',  sport: 'tennis' },
        { status: 'won',  pnl: 1.50, mode: 'paper', sport: 'calcio' },
        { status: 'open', pnl: null, mode: 'live',  sport: 'tennis' },
        { status: 'error', pnl: -99, mode: 'live',  sport: 'tennis' },
    ];

    it('divide per modalita: il live non tocca il paper', () => {
        const r = realizzatoGiornata(righe);
        expect(r.live).toBe(0.08);
        expect(r.paper).toBe(1.5);
    });

    it('divide per SPORT: «quanto ho guadagnato col tennis» ha una risposta', () => {
        const r = realizzatoGiornata(righe);
        expect(r.perSport.tennis).toBe(0.08);
        expect(r.perSport.calcio).toBe(1.5);
    });

    it('le righe NON REGOLATE non valgono zero: non entrano', () => {
        const r = realizzatoGiornata(righe);
        expect(r.righe).toBe(3);
    });

    it('le righe in ERRORE non sono operazioni e non contano', () => {
        const r = realizzatoGiornata([{ status: 'error', pnl: -99, mode: 'live', sport: 'tennis' }]);
        expect(r.totale).toBeNull();
        expect(r.righe).toBe(0);
    });

    it('senza nessuna riga regolata tutto e null, mai zero', () => {
        const r = realizzatoGiornata([{ status: 'open', pnl: null, mode: 'live', sport: 'tennis' }]);
        expect(r.totale).toBeNull();
        expect(r.live).toBeNull();
        expect(r.perSport.tennis).toBeNull();
    });

    it('uno sport sconosciuto finisce in «ignoto», non sparisce e non si somma al calcio', () => {
        const r = realizzatoGiornata([{ status: 'won', pnl: 1, mode: 'live', sport: null }]);
        expect(r.perSport.ignoto).toBe(1);
        expect(r.perSport.calcio).toBeNull();
        expect(r.totale).toBe(1);
    });

    it('arrotonda al centesimo UNA volta sola, alla fine', () => {
        const r = realizzatoGiornata([
            { status: 'won', pnl: 0.005, mode: 'live', sport: 'tennis' },
            { status: 'won', pnl: 0.005, mode: 'live', sport: 'tennis' },
        ]);
        expect(r.totale).toBe(0.01);
    });
});

describe('totaliGiornata', () => {
    it('conta partite, live, pre, posizioni e responsabilità', () => {
        const soldi = soldiPerPartita([
            ...marca([tradeLive({ id: 1, event_id: 'E1', status: 'open', liability: 40 })], 'omega'),
            ...marca([tradeLive({ id: 2, event_id: 'E2', status: 'won', pnl: 12 })], 'safe'),
        ]);
        const g = costruisciGiornata({
            righe: [
                { event_id: 'E1', payload: feed({ inplay: true }), updated_at: '2026-09-14T15:00:00Z' },
                { event_id: 'E2', payload: feed({ open_date: '2026-09-14T19:00:00Z' }), updated_at: '2026-09-14T15:00:00Z' },
            ],
            soldi, nowMs: T0,
        });
        expect(totaliGiornata(g)).toEqual({
            letti: true,
            partite: 2, live: 1, pre: 1,
            conPosizione: 1, conPosizioneLive: 1,
            liability: 40, liabilityPaper: 0,
            netPnl: 12, netPnlPaper: null,
        });
    });

    it('senza nessun risultato il netto è null, non 0,00 €', () => {
        const g = costruisciGiornata({
            righe: [{ event_id: 'E1', payload: feed({ inplay: true }), updated_at: null }],
            soldi: new Map(), nowMs: T0,
        });
        expect(totaliGiornata(g).netPnl).toBeNull();
    });
});

// ========================================================================
// SOLDI VERI E SOLDI FINTI NON SI SOMMANO MAI.
//
// 14/09, parole dell'utente: «NON VOGLIO DATI MISCHIATI». Sul tennis la
// stessa partita puo' avere righe paper e righe live: un numero solo
// sarebbe la media di due mondi, mostrata come se fosse un risultato.
// ========================================================================

describe('soldiPerPartita - le due modalita restano separate', () => {
    it('sulla STESSA partita tiene i due conti distinti e non li somma MAI', () => {
        const m = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'won', pnl: 5, mode: 'live' } as never),
            trade({ id: 2, event_id: 'E1', status: 'lost', pnl: -40, mode: 'paper' } as never),
        ], 'safe'));
        expect(m.get('E1')?.live.netPnl).toBe(5);
        expect(m.get('E1')?.paper.netPnl).toBe(-40);
        // il numero misto (-35) non deve esistere da nessuna parte
        expect(JSON.stringify(m.get('E1'))).not.toContain('-35');
        expect(m.get('E1')?.modi).toEqual(['live', 'paper']);
    });

    it('la responsabilita simulata NON entra in quella vera', () => {
        const m = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'open', liability: 3, mode: 'live' } as never),
            trade({ id: 2, event_id: 'E1', status: 'open', liability: 300, mode: 'paper' } as never),
        ], 'safe'));
        expect(m.get('E1')?.live.liability).toBe(3);
        expect(m.get('E1')?.paper.liability).toBe(300);
    });

    it('una modalita NON DICHIARATA vale paper: ai soldi veri si arriva scrivendolo', () => {
        const m = soldiPerPartita(marca([trade({ id: 1, event_id: 'E1', status: 'won', pnl: 9 })], 'safe'));
        expect(m.get('E1')?.paper.netPnl).toBe(9);
        expect(m.get('E1')?.live.netPnl).toBeNull();
        expect(m.get('E1')?.modi).toEqual(['paper']);
    });

    it('un mode scritto storto non diventa mai soldi veri per caso', () => {
        const m = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'won', pnl: 1, mode: 'LIVE' } as never),
            trade({ id: 2, event_id: 'E2', status: 'won', pnl: 1, mode: 'vivo' } as never),
        ], 'safe'));
        expect(m.get('E1')?.live.netPnl).toBe(1);      // maiuscolo: e' live
        expect(m.get('E2')?.live.netPnl).toBeNull();   // parola ignota: paper
        expect(m.get('E2')?.paper.netPnl).toBe(1);
    });

    it('una partita solo in prova non ha nulla nel ramo dei soldi veri', () => {
        const m = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'open', liability: 50, mode: 'paper' } as never),
        ], 'omega'));
        expect(m.get('E1')?.live).toEqual({ netPnl: null, liability: 0, investito: 0, aperta: false });
        expect(m.get('E1')?.paper.aperta).toBe(true);
    });
});

describe('totali di giornata - esposizione e avanzamento sono soldi VERI', () => {
    it("L'ESPOSIZIONE DICHIARATA e' solo quella vera: il paper sta a parte", () => {
        // caso reale del 14/09: la testata diceva 393,68 EUR di esposizione
        // sommando la responsabilita' delle posizioni simulate del calcio,
        // mentre i soldi veri impegnati erano 77,71 EUR.
        const soldi = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'open', liability: 3, mode: 'live' } as never),
            trade({ id: 2, event_id: 'E1', status: 'open', liability: 316, mode: 'paper' } as never),
        ], 'safe'));
        const g = costruisciGiornata({
            righe: [{ event_id: 'E1', payload: feed({ inplay: true }), updated_at: '2026-09-14T15:00:00Z' }],
            soldi, nowMs: T0,
        });
        const t = totaliGiornata(g);
        expect(t.liability).toBe(3);
        expect(t.liabilityPaper).toBe(316);
        expect(t.conPosizioneLive).toBe(1);
    });

    it('una partita aperta SOLO in prova non conta fra quelle con soldi veri', () => {
        const soldi = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'open', liability: 20, mode: 'paper' } as never),
        ], 'omega'));
        const g = costruisciGiornata({
            righe: [{ event_id: 'E1', payload: feed({ inplay: true }), updated_at: '2026-09-14T15:00:00Z' }],
            soldi, nowMs: T0,
        });
        const t = totaliGiornata(g);
        expect(t.conPosizione).toBe(1);
        expect(t.conPosizioneLive).toBe(0);
        expect(t.liability).toBe(0);
    });

    it('LA BARRA DELLA PARTITA si riempie con i soldi veri, non con la prova', () => {
        const soldi = soldiPerPartita(marca([
            trade({ id: 1, event_id: 'E1', status: 'won', pnl: 100, mode: 'paper' } as never),
        ], 'safe'));
        const g = costruisciGiornata({
            righe: [{ event_id: 'E1', payload: feed({ inplay: true }), updated_at: '2026-09-14T15:00:00Z' }],
            soldi, nowMs: T0, obiettivo: 100, realizzato: 0, targetServizio: 10,
        });
        // 100 EUR vinti IN PROVA non devono muovere l'avanzamento di un pixel
        expect(g[0].partite[0].avanzamento).toBeNull();
    });
});

// ===========================================================================
// REVIEW 15/09 — CONTATORI E PERIMETRI.
// ===========================================================================

describe('realizzatoGiornata conta anche vinte e perse', () => {
    it('le conta sulle STESSE righe da cui nasce il P&L', () => {
        const r = realizzatoGiornata([
            { status: 'won', pnl: 3, mode: 'live', sport: 'tennis' },
            { status: 'lost', pnl: -1, mode: 'live', sport: 'tennis' },
            { status: 'won', pnl: 2, mode: 'live', sport: 'calcio' },
        ] as never);
        expect(r.righe).toBe(3);
        expect(r.vinte).toBe(2);
        expect(r.perse).toBe(1);
        expect(r.totale).toBe(4);
    });

    it('una riga a ZERO non e ne vinta ne persa', () => {
        const r = realizzatoGiornata([{ status: 'won', pnl: 0, mode: 'live' }] as never);
        expect(r.righe).toBe(1);
        expect(r.vinte).toBe(0);
        expect(r.perse).toBe(0);
    });

    it('le righe in errore non entrano in nessun contatore', () => {
        const r = realizzatoGiornata([
            { status: 'error', pnl: -99, mode: 'live' },
            { status: 'won', pnl: 1, mode: 'live' },
        ] as never);
        expect(r.righe).toBe(1);
        expect(r.vinte).toBe(1);
    });
});

describe('totali NON LETTI: assenza dichiarata, non zero', () => {
    it('con `letti` false il totale lo dice', () => {
        const g = costruisciGiornata({
            righe: [{ event_id: 'E1', payload: feed({ inplay: true }), updated_at: null }],
            soldi: new Map(), nowMs: T0,
        });
        expect(totaliGiornata(g, false).letti).toBe(false);
        expect(totaliGiornata(g).letti).toBe(true);   // difetto: letti
    });
});
