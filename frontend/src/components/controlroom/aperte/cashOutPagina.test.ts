// ============================================================================
// cashOutPagina.test.ts - 08/10 (cantiere W1): le regole pure della pagina
// «Cash Out». Finti con le chiavi VERE (`PartitaGiornata`, `MikeEvent`,
// `OrdineContoFuoriBot` di `get_live_orders_account_open`).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    faseEvento, scatoleCashOut, filtraScatole, ordinaScatole, testoCashOutRiga,
    selezioniFuoriBot, gambeFuoriBot, origineFuoriBot, totaleModalita, contaPerModalita,
    sezioneScatola, motivoCashOutConclusa, TESTO_CONCLUSA,
} from './cashOutPagina';
import type { SintesiCashOut, SintesiModalitaCashOut } from '@/components/controlroom/useCashOutPartita';
import { raggruppaOrdiniConto, ORDINI_CONTO_NON_LETTI } from '@/components/controlroom/ordiniConto';
import { cashOutPartita } from '@/lib/cashOutPartita';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { MikeEvent } from '@/lib/mike';
import type { OrdineContoFuoriBot } from '@/lib/liveOrders';
import type { OperazionePartita, PosizioneAperta } from '@/components/controlroom/useControlRoom';

const ORA = Date.parse('2026-10-08T15:00:00Z');

function partita(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'E1', sport: 'calcio', nome: 'Inter v Milan', campionato: 'Serie A',
        koMs: ORA + 600_000, stato: 'pre', minuto: null, punteggio: null, controlloDisponibile: true,
        etaFeedS: 2, freschezza: 'fresca', latenzaQuoteS: 1, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        media: null, marketId: '1.MO', soldi: null, target: null, avanzamento: null, extra: null,
        ...over,
    };
}

function mike(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: null, competition: null, league_id: null,
        ko_at: null, mode: 'live', markets: {}, state: 'PRE_OPEN', cycle_no: 0, entry_price_initial: null,
        dossier: null, live: null, positions: [], ctx: null, skipped: false, settled_pnl: null,
        updated_at: '2026-10-08T14:59:00Z', ...over,
    };
}

const ordine = { status: 'open', side: 'back', price: 2, size: 5, size_requested: 5, size_matched: 5,
    size_remaining: 0, avg_price_matched: 2, betfair_updated_at: null, meta: null };

function op(o: Partial<OperazionePartita> & Pick<OperazionePartita, 'bot' | 'id'>): OperazionePartita {
    return {
        selezione: 'Under 3.5 Goals', lato: 'back', prezzo: 2, size: 5, stato: 'open', pnl: null,
        modalita: 'live', at: '2026-10-08T14:04:00Z', quale: null, ordine, dettaglio: null,
        marketId: '1.OU35', selectionId: 35, liability: null, vivo: null, etaQuoteS: null, chiusura: null,
        chiusureOrdini: [], eventId: 'E1', chiudeId: null, ...o,
    };
}

function pos(o: Partial<PosizioneAperta> & Pick<PosizioneAperta, 'bot' | 'id' | 'eventId'>): PosizioneAperta {
    return {
        partita: 'Inter v Milan', selezione: 'Under 3.5 Goals', lato: 'back', prezzo: 2, size: 5, liability: 5,
        modalita: 'live', piazzataAt: '2026-10-08T14:04:00Z', chiusura: null, ordine, dettaglio: null, vivo: null, ...o,
    };
}

const SITO: OrdineContoFuoriBot = {
    bet_id: '1', market_id: '1.OU25', selection_id: 47973, event_id: 'E9', event_name: 'Arsenal v Chelsea',
    market_name: 'Over/Under 2.5 Goals', selection_name: 'Under 2.5 Goals', side: 'LAY',
    price_matched: 1.6, size_matched: 8, size_remaining: 0, status: 'EXECUTION_COMPLETE',
    source: 'account', placed_at: '2026-10-08T14:31:02Z',
};

describe('faseEvento: fonte unica PartitaGiornata.stato, poi i dati del bot', () => {
    it('programma: live -> in gioco; pre -> pre-match; chiusa con mercato CLOSED -> conclusa; chiusa e aperto -> fischio passato', () => {
        expect(faseEvento(partita({ stato: 'live' }), null, [], ORA)).toMatchObject({ fase: 'gioco', nota: 'in-gioco', fonte: 'scanner' });
        expect(faseEvento(partita({ stato: 'pre' }), null, [], ORA)).toMatchObject({ fase: 'pre', nota: 'fischio-fra' });
        expect(faseEvento(partita({ stato: 'chiusa', statoMercato: 'CLOSED' }), null, [], ORA)).toMatchObject({ fase: 'gioco', nota: 'conclusa' });
        expect(faseEvento(partita({ stato: 'chiusa', statoMercato: 'OPEN' }), null, [], ORA)).toMatchObject({ fase: 'pre', nota: 'fischio-passato' });
        expect(faseEvento(partita({ stato: 'chiusa' }), null, [], ORA)).toMatchObject({ fase: 'pre', nota: 'fischio-passato' });
    });

    it('la scheda dello scanner VINCE sui dati di Mike (fonte unica)', () => {
        const m = mike({ live: { inplay: true } });
        expect(faseEvento(partita({ stato: 'pre' }), m, [], ORA).fase).toBe('pre');
    });

    it('fuori programma: Mike in gioco, Mike prima del fischio, Mike dopo il fischio non in gioco, senza live', () => {
        expect(faseEvento(null, mike({ live: { inplay: true } }), [], ORA)).toMatchObject({ fase: 'gioco', nota: 'in-gioco', fonte: 'mike' });
        const fra = new Date(ORA + 3600_000).toISOString();
        expect(faseEvento(null, mike({ ko_at: fra }), [], ORA)).toMatchObject({ fase: 'pre', nota: 'fischio-fra', koMs: ORA + 3600_000 });
        const passato = new Date(ORA - 60_000).toISOString();
        expect(faseEvento(null, mike({ ko_at: passato, live: { inplay: false } }), [], ORA).nota).toBe('fischio-passato');
        expect(faseEvento(null, mike({ ko_at: passato, live: null }), [], ORA).nota).toBe('orario-passato');
    });

    it('fuori programma senza Mike: l\'orario della riga del bot (Omega `kickoff`), altrimenti «orario non dichiarato»', () => {
        const ko = new Date(ORA + 1200_000).toISOString();
        expect(faseEvento(null, null, [{ koAt: null }, { koAt: ko }], ORA)).toMatchObject({ fase: 'pre', nota: 'fischio-fra', fonte: 'bot' });
        expect(faseEvento(null, null, [{ koAt: new Date(ORA - 1).toISOString() }], ORA).nota).toBe('orario-passato');
        expect(faseEvento(null, null, [{}], ORA)).toEqual({ fase: 'pre', nota: 'orario-non-dichiarato', koMs: null, fonte: null });
    });
});

describe('scatoleCashOut: una scatola per partita, nessuna sparisce', () => {
    const base = {
        giornata: [{ campionato: 'Serie A', primoKoMs: null, partite: [partita({ stato: 'live' })] }],
        posizioni: [pos({ bot: 'mike', id: 1, eventId: 'E1' }), pos({ bot: 'mike', id: 2, eventId: 'E1' }), pos({ bot: 'safe', id: 3, eventId: 'FX', partita: 'Fuori v Programma', modalita: 'paper' })],
        operazioni: new Map([['E1', [op({ bot: 'mike', id: 1 }), op({ bot: 'mike', id: 2 }), op({ bot: 'mike', id: 99, stato: 'won' })]]]),
        mikeEventi: new Map<string, MikeEvent>(),
        nowMs: ORA,
    };

    it('Mike 2 gambe = una scatola con 2 righe (le regolate restano nel cash out, non fra le gambe)', () => {
        const s = scatoleCashOut({ ...base, ordiniConto: ORDINI_CONTO_NON_LETTI });
        expect(s.map((x) => x.eventId)).toEqual(['E1', 'FX']);
        expect(s[0].righe.map((r) => r.id)).toEqual([1, 2]);
        expect(s[0].operazioni).toHaveLength(3);
        expect(s[0].live).toBe(true);
        // fuori programma: senza riga nella scheda resta come orfana, in pre-match, in prova
        expect(s[1]).toMatchObject({ partita: null, nome: 'Fuori v Programma', live: false, sport: 'calcio' });
        expect(s[1].orfane).toHaveLength(1);
        expect(s[1].fase.nota).toBe('orario-non-dichiarato');
    });

    it('una partita con SOLI ordini fuori dai bot compare (LIVE); ordini non letti = nessuna scatola inventata', () => {
        const s = scatoleCashOut({ ...base, ordiniConto: raggruppaOrdiniConto([SITO], '2026-10-08T14:59:50Z') });
        const e9 = s.find((x) => x.eventId === 'E9');
        expect(e9).toMatchObject({ nome: 'Arsenal v Chelsea', live: true, partita: null });
        expect(e9?.fuoriBot).toHaveLength(1);
        expect(scatoleCashOut({ ...base, ordiniConto: { ...ORDINI_CONTO_NON_LETTI } }).some((x) => x.eventId === 'E9')).toBe(false);
    });

    it('filtri: sport e fase, null = tutto; ordine: LIVE prima, poi per fischio', () => {
        const s = scatoleCashOut({ ...base, ordiniConto: ORDINI_CONTO_NON_LETTI });
        expect(filtraScatole(s, { sport: null, fase: null })).toHaveLength(2);
        expect(filtraScatole(s, { sport: null, fase: 'live' }).map((x) => x.eventId)).toEqual(['E1']);
        expect(filtraScatole(s, { sport: null, fase: 'pre' }).map((x) => x.eventId)).toEqual(['FX']);
        expect(filtraScatole(s, { sport: 'tennis', fase: null })).toHaveLength(0);
        expect(ordinaScatole([s[1], s[0]]).map((x) => x.eventId)).toEqual(['E1', 'FX']);
    });
});

describe('testoCashOutRiga: il pulsante dice quanto chiude il comando di oggi', () => {
    it('Mike: tutte le N gambe della stessa modalita\'; Omega/Safe: solo la riga; tennis: per mercato; scalper: sessione', () => {
        const righe = [op({ bot: 'mike', id: 1 }), op({ bot: 'mike', id: 2, marketId: '1.OU45' }), op({ bot: 'mike', id: 3, marketId: '1.MO' }),
            op({ bot: 'mike', id: 4, modalita: 'paper' })];
        expect(testoCashOutRiga(righe[0], righe)).toEqual({ etichetta: 'Cash out Mike', ambito: 'tutte le 3 gambe di Mike' });
        expect(testoCashOutRiga(righe[3], righe)).toEqual({ etichetta: 'Cash out Mike', ambito: 'la gamba di Mike: tutta la sua posizione' });
        expect(testoCashOutRiga(op({ bot: 'omega', id: 9 }), righe)).toEqual({ etichetta: 'Cash out', ambito: 'solo questa gamba' });
        expect(testoCashOutRiga(op({ bot: 'safe', id: 9 }), righe)).toEqual({ etichetta: 'Cash out', ambito: 'solo questa gamba' });
        const t = [op({ bot: 'tennis_pro', id: 1, marketId: '1.T' }), op({ bot: 'tennis_pro', id: 2, marketId: '1.T' }), op({ bot: 'tennis_pro', id: 3, marketId: '1.S' })];
        expect(testoCashOutRiga(t[0], t)).toEqual({ etichetta: 'Cash out Pro', ambito: 'tutte le 2 gambe di Pro su questo mercato' });
        expect(testoCashOutRiga(op({ bot: 'scalper', id: 5 }), []).etichetta).toBe('Cash out Scalper calcio');
    });
});

describe('ordini fuori dai bot: per selezione, solo l\'abbinato, sempre LIVE', () => {
    it('origine Sito/App dal `source`', () => {
        expect(origineFuoriBot({ source: 'account' })).toBe('Sito');
        expect(origineFuoriBot({ source: 'runner' })).toBe('App');
    });

    it('selezioni: una per (mercato, selezione), origini unite; senza abbinato = niente da chiudere', () => {
        const righe = [SITO, { ...SITO, bet_id: '2', source: 'runner' as const }, { ...SITO, bet_id: '3', selection_id: 1, price_matched: null, size_matched: 0, size_remaining: 4 }];
        const s = selezioniFuoriBot(righe);
        expect(s).toHaveLength(2);
        expect(s[0]).toMatchObject({ marketId: '1.OU25', selectionId: 47973, origini: ['Sito', 'App'], abbinato: true });
        expect(s[1]).toMatchObject({ selectionId: 1, abbinato: false });
    });

    it('gambe: solo abbinate, modalita live; la matematica UNICA da\' il green-up della selezione', () => {
        const g = gambeFuoriBot([SITO, { ...SITO, bet_id: '3', price_matched: null, size_matched: 0 }]);
        expect(g).toEqual([{
            id: 'conto 1', bot: 'Sito', modalita: 'live', marketId: '1.OU25', selectionId: 47973,
            selezione: 'Under 2.5 Goals', lato: 'lay', abbinato: 8, prezzoMedio: 1.6, aliquota: null, dueEsiti: false,
        }]);
        const r = cashOutPartita(g, {
            prezzo: () => ({ back: 1.5, backSize: 100, lay: 1.52, laySize: 100, istanteMs: ORA, fonte: 'canale', statoMercato: 'OPEN' }),
            nowMs: ORA,
        });
        // LAY 8 @ 1,60 chiuso puntando 8,53 @ 1,50: -0,53 sui due esiti, PROVA vuota
        expect(r.live.netto).toBe(-0.53);
        expect(r.paper.nGambe).toBe(0);
    });
});

// ---------------------------------------------------------- secondo giro
describe('secondo giro: filtro dei soldi, riepilogo per modalita\'', () => {
    const vuota: SintesiModalitaCashOut = { netto: 0, nGambe: 0, mancanti: [], etaPrezziS: null, etaIgnota: false };
    const sint = (live: Partial<SintesiModalitaCashOut>, paper: Partial<SintesiModalitaCashOut> = {}): SintesiCashOut => ({
        live: { ...vuota, ...live }, paper: { ...vuota, ...paper },
    });
    const S = [{ eventId: 'A', nome: 'Inter v Milan' }, { eventId: 'B', nome: 'Lazio v Torino' }];

    it('filtro soldi: LIVE = almeno una gamba non paper (o un ordine del conto), PROVA il resto', () => {
        const s = scatoleCashOut({
            giornata: [], nowMs: ORA, mikeEventi: new Map(), ordiniConto: ORDINI_CONTO_NON_LETTI,
            posizioni: [
                pos({ bot: 'mike', id: 1, eventId: 'L', modalita: 'live' }), pos({ bot: 'omega', id: 2, eventId: 'L', modalita: 'paper' }),
                pos({ bot: 'omega', id: 3, eventId: 'P', modalita: 'paper' }),
                pos({ bot: 'safe', id: 4, eventId: 'N', modalita: null }),
            ],
            operazioni: new Map(),
        });
        expect(filtraScatole(s, { sport: null, fase: null, soldi: 'live' }).map((x) => x.eventId)).toEqual(['L', 'N']);
        expect(filtraScatole(s, { sport: null, fase: null, soldi: 'prova' }).map((x) => x.eventId)).toEqual(['P']);
        expect(filtraScatole(s, { sport: null, fase: null, soldi: null })).toHaveLength(3);
        // gambe e partite per modalita': la partita L conta in tutte e due, mai sommate
        expect(contaPerModalita(s)).toEqual({ live: { gambe: 2, partite: 2 }, paper: { gambe: 2, partite: 2 } });
    });

    it('somma al centesimo con l\'eta\' piu\' vecchia; scatole senza gambe non contano', () => {
        const m = new Map<string, SintesiCashOut | null>([
            ['A', sint({ netto: -0.53, nGambe: 1, etaPrezziS: 2 })],
            ['B', sint({ netto: 0.37, nGambe: 1, etaPrezziS: 7 }, { netto: 0.5, nGambe: 1 })],
        ]);
        expect(totaleModalita(S, m, 'live')).toEqual({ stato: 'ok', netto: -0.16, motivi: [], etaPrezziS: 7, etaIgnota: false });
        expect(totaleModalita(S, m, 'paper')).toMatchObject({ stato: 'ok', netto: 0.5 });
        expect(totaleModalita(S, new Map([['A', null], ['B', sint({})]]), 'live').stato).toBe('nessuna');
    });

    it('fail-closed: una scatola non calcolabile = nessuna cifra, col motivo; una non ancora riportata = «in calcolo»', () => {
        const m = new Map<string, SintesiCashOut | null>([
            ['A', sint({ netto: -0.53, nGambe: 1 })],
            ['B', sint({ netto: null, nGambe: 1, mancanti: ['manca il prezzo di Lazio (banca)'] })],
        ]);
        expect(totaleModalita(S, m, 'live')).toMatchObject({
            stato: 'non-calcolabile', netto: null, motivi: ['Lazio v Torino: manca il prezzo di Lazio (banca)'],
        });
        // la prova non risente del live non calcolabile
        expect(totaleModalita(S, m, 'paper').stato).toBe('nessuna');
        expect(totaleModalita(S, new Map([['A', sint({ netto: 1, nGambe: 1 })]]), 'live').stato).toBe('calcolo');
    });
});

// ---------------------------------------------------------------------------
// 08/10 sera (D-6, decisione dell'utente): la sezione «Concluse»
// ---------------------------------------------------------------------------
describe('D-6: sezione Concluse (Match Odds CHIUSO, posizioni da regolare)', () => {
    const scatola = (p: PartitaGiornata) => scatoleCashOut({
        giornata: [{ campionato: 'Serie A', primoKoMs: p.koMs, partite: [p] }],
        posizioni: [pos({ bot: 'mike', id: 1, eventId: p.event_id })],
        operazioni: new Map([[p.event_id, [op({ bot: 'mike', id: 1, eventId: p.event_id })]]]),
        mikeEventi: new Map(), ordiniConto: null, nowMs: ORA,
    })[0];

    it('il Match Odds CHIUSO vince su ogni altra fase: TUTTE le partite col mercato chiuso sono concluse', () => {
        for (const stato of ['live', 'pre', 'chiusa'] as const) {
            const f = faseEvento(partita({ stato, statoMercato: 'CLOSED' }), null, [], ORA);
            expect(f, stato).toMatchObject({ nota: 'conclusa', fase: 'gioco', fonte: 'scanner' });
            expect(sezioneScatola({ fase: f }), stato).toBe('concluse');
        }
    });

    it('e SOLE: mercato aperto, sospeso o non dichiarato non sono mai concluse', () => {
        for (const statoMercato of ['OPEN', 'SUSPENDED', null, undefined]) {
            for (const stato of ['live', 'pre', 'chiusa'] as const) {
                const s = scatola(partita({ stato, statoMercato }));
                expect(sezioneScatola(s), `${stato}/${String(statoMercato)}`).not.toBe('concluse');
                expect(motivoCashOutConclusa(s), `${stato}/${String(statoMercato)}`).toBeNull();
            }
        }
        expect(sezioneScatola(scatola(partita({ stato: 'live' })))).toBe('gioco');
        expect(sezioneScatola(scatola(partita({ stato: 'pre' })))).toBe('pre');
        expect(sezioneScatola(scatola(partita({ stato: 'chiusa', statoMercato: 'OPEN' })))).toBe('pre');
        // fuori programma: nessun mercato letto, mai «conclusa»
        const fuori = scatoleCashOut({
            giornata: [], posizioni: [pos({ bot: 'mike', id: 1, eventId: 'F1' })],
            operazioni: new Map(), mikeEventi: new Map(), ordiniConto: null, nowMs: ORA,
        })[0];
        expect(sezioneScatola(fuori)).toBe('pre');
    });

    it('testo veritiero e motivo del cash out spento', () => {
        const s = scatola(partita({ stato: 'chiusa', statoMercato: 'CLOSED' }));
        expect(TESTO_CONCLUSA).toBe('conclusa · posizioni da regolare');
        expect(motivoCashOutConclusa(s)).toMatch(/Betfair ha CHIUSO il mercato, il cash out non e' possibile/);
    });

    it('i filtri valgono: «Live» tiene le concluse (gia\' entrate in gioco), «Pre-match» le toglie, lo sport conta', () => {
        const c = scatola(partita({ stato: 'chiusa', statoMercato: 'CLOSED' }));
        expect(filtraScatole([c], { sport: null, fase: 'live' })).toHaveLength(1);
        expect(filtraScatole([c], { sport: null, fase: 'pre' })).toHaveLength(0);
        expect(filtraScatole([c], { sport: 'tennis', fase: null })).toHaveLength(0);
        expect(filtraScatole([c], { sport: 'calcio', fase: null, soldi: 'live' })).toHaveLength(1);
        expect(filtraScatole([c], { sport: 'calcio', fase: null, soldi: 'prova' })).toHaveLength(0);
    });
});
