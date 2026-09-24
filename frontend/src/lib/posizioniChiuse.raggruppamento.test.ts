// ============================================================================
// posizioniChiuse.raggruppamento.test.ts - LA REGOLA DEL 24/09.
//
// "i dati sono mischiati per giornata, sono confusionari e il trader non
// capisce assolutamente nulla. IL TRADER DEVE FIDARSI DI QUELLO CHE VEDE"
// (utente, 24/09). Una regola per calcio e tennis:
//   giornata di REGOLAMENTO (Roma) -> bot -> partita -> ciclo
// con il netto e la fonte (Betfair / stimato / paper) a ogni livello.
//
// I finti hanno le chiavi delle tabelle vere (`omega_trades`,
// `safe_strategy_trades`, `mike_trades`, `tennis_live_orders`).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    posizioniChiuse, filtraChiuse, riepilogoChiuse, raggruppaGiornata, unisciRighe,
    rigaDaOrdineTennis, nettoOrdineTennis, giornataDi,
    type TradeChiudibile,
} from './posizioniChiuse';
import { romeDay } from './dailyHistory';
import { isBotTennis, type Bot } from './controlRoom';
import type { TennisBotOrderRow } from './tennis';

const G = '2026-09-24';

function t(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'safe', event_id: 'E1', event_name: 'Inter - Milan', sport: 'calcio',
        mode: 'live', status: 'won', pnl: 1, side: 'back', price: 2, size: 5,
        selection_name: 'Inter', market_type: 'MATCH_ODDS', placed_at: `${G}T10:00:00.000Z`,
        settled_at: `${G}T12:00:00.000Z`, closes_trade_id: null, strategy: 'base',
        bet_id: `B${over.id}`, origin: 'auto',
        ...over,
    };
}

/** una riga di `tennis_live_orders` con le chiavi e i tipi della tabella */
function ordine(over: Partial<TennisBotOrderRow> & { id: number }): TennisBotOrderRow {
    return {
        bet_id: `T${over.id}`, client_order_ref: `awtq${over.id}`, request_id: over.id,
        mode: 'live', source: 'tennis_scalper', event_id: 'T1', market_id: '1.234', selection_id: 111,
        handicap: 0, side: 'back', order_type: 'LIMIT', price: 1.8, size: 2,
        size_matched: 2, size_remaining: 0, size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        average_price_matched: 1.8, status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
        placed_at: `${G}T09:00:00.000Z`, matched_at: `${G}T09:00:01.000Z`, updated_at: `${G}T11:00:00.000Z`,
        pnl: 1.6, commission: 0.08, settled_at: `${G}T11:00:00.000Z`,
        pnl_betfair: null, pnl_betfair_settled_at: null,
        ...over,
    };
}

const eBot = (b: string) => isBotTennis(b as Bot);

describe('raggruppamento: giornata -> bot -> partita -> ciclo', () => {
    const righe: TradeChiudibile[] = [
        // Omega: un ciclo con green-up (A <- B) sulla partita E1
        t({ __bot: 'omega', id: 1, status: 'won', pnl: 3, runner_name: '1 - 0', selection_name: null, phase: 'ft_cs', market_type: null }),
        t({ __bot: 'omega', id: 2, status: 'lost', pnl: -2, closes_trade_id: 1, runner_name: '1 - 0', selection_name: null }),
        // Safe calcio: due cicli su due partite
        t({ id: 1, pnl: 0.5 }),
        t({ id: 3, pnl: -0.2, event_id: 'E2', event_name: 'Roma - Lazio' }),
        // Safe tennis: un ciclo
        t({ id: 4, pnl: 0.3, sport: 'tennis', event_id: 'T9', event_name: 'Sinner - Alcaraz' }),
        // Mike
        t({ __bot: 'mike', id: 7, pnl: -1 }),
    ];
    const pos = posizioniChiuse(righe);
    const giorno = raggruppaGiornata(G, filtraChiuse(pos, { giorno: G, modo: 'live' }));

    it('i bot sono gruppi, Safe si divide per sport come le voci della barra', () => {
        expect(giorno.bots.map((b) => b.chiave)).toEqual(['omega', 'safe_calcio', 'mike', 'safe_tennis']);
    });

    it('un ciclo e\' UNA operazione col suo netto (3 - 2 = +1), non due righe', () => {
        const omega = giorno.bots[0];
        expect(omega.riepilogo.n).toBe(1);
        expect(omega.partite[0].cicli[0].pnlGlobale).toBe(1);
        expect(omega.partite[0].cicli[0].righe).toHaveLength(2);
    });

    it('le partite sono gruppi dentro il bot', () => {
        const safe = giorno.bots.find((b) => b.chiave === 'safe_calcio');
        expect(safe?.partite.map((p) => p.partita).sort()).toEqual(['Inter - Milan', 'Roma - Lazio']);
    });

    it('la somma dei livelli e\' IDENTICA al totale della giornata', () => {
        const perBot = giorno.bots.reduce((s, b) => s + (b.riepilogo.totale ?? 0), 0);
        const perPartita = giorno.bots.flatMap((b) => b.partite).reduce((s, p) => s + (p.riepilogo.totale ?? 0), 0);
        expect(Math.round(perBot * 100) / 100).toBe(giorno.riepilogo.totale);
        expect(Math.round(perPartita * 100) / 100).toBe(giorno.riepilogo.totale);
        expect(giorno.riepilogo.totale).toBe(0.6);   // 1 + 0.5 - 0.2 - 1 + 0.3
    });

    it('Omega: selezione dal runner, mercato dalla fase (prima "selezione -" )', () => {
        const c = giorno.bots[0].partite[0].cicli[0];
        expect(c.selezione).toBe('1 - 0');
        expect(c.mercato).toBe('Risultato esatto');
    });
});

describe('fonte del P&L: Betfair / stimato / paper, sempre dichiarata', () => {
    it('una gamba col netto di Betfair e una senza: il ciclo e\' stimato, con le due parti', () => {
        const [p] = posizioniChiuse([
            t({ id: 1, pnl: 3, pnl_betfair: 2.85, pnl_betfair_settled_at: `${G}T12:05:00.000Z` }),
            t({ id: 2, pnl: -2, closes_trade_id: 1 }),
        ]);
        expect(p.fontePnl).toBe('stimato');
        expect(p.pnlReale).toBe(2.85);
        expect(p.pnlStimato).toBe(-2);
        expect(p.pnlGlobale).toBe(0.85);
    });

    it('tutte le gambe regolate da Betfair: fonte betfair, stimato null', () => {
        const [p] = posizioniChiuse([
            t({ id: 1, pnl: 3, pnl_betfair: 2.85 }),
            t({ id: 2, pnl: -2, pnl_betfair: -2, closes_trade_id: 1 }),
        ]);
        expect(p.fontePnl).toBe('betfair');
        expect(p.pnlStimato).toBeNull();
        expect(p.pnlReale).toBe(0.85);
    });

    it('il riepilogo separa reale e stimato e la loro somma e\' il totale', () => {
        const pos = posizioniChiuse([
            t({ id: 1, pnl: 3, pnl_betfair: 2.85 }),
            t({ id: 2, pnl: -0.4, event_id: 'E2' }),
        ]);
        const r = riepilogoChiuse(pos);
        expect(r.reale).toBe(2.85);
        expect(r.stimato).toBe(-0.4);
        expect(r.totale).toBe(2.45);
    });

    it('filtro "solo Betfair": resta solo il ciclo interamente regolato', () => {
        const pos = posizioniChiuse([
            t({ id: 1, pnl: 3, pnl_betfair: 2.85 }),
            t({ id: 2, pnl: -0.4, event_id: 'E2' }),
        ]);
        expect(filtraChiuse(pos, { fonte: 'betfair' }).map((p) => p.id)).toEqual([1]);
        expect(filtraChiuse(pos, { fonte: 'tutte' })).toHaveLength(2);
    });

    it('paper: fonte paper, il pnl_betfair (che non puo\' esistere) e\' ignorato', () => {
        const [p] = posizioniChiuse([t({ id: 1, mode: 'paper', pnl: 1, pnl_betfair: 9 })]);
        expect(p.fontePnl).toBe('paper');
        expect(p.pnlGlobale).toBe(1);
        expect(p.pnlReale).toBeNull();
        expect(p.pnlStimato).toBeNull();
    });
});

describe('paper e live: mai nella stessa giornata mostrata', () => {
    const pos = posizioniChiuse([
        t({ id: 1, mode: 'live', pnl: 1 }),
        t({ id: 2, mode: 'paper', pnl: 50 }),
    ]);
    it('il filtro di modalita\' tiene fuori l\'altra', () => {
        expect(raggruppaGiornata(G, filtraChiuse(pos, { giorno: G, modo: 'live' })).riepilogo.totale).toBe(1);
        expect(raggruppaGiornata(G, filtraChiuse(pos, { giorno: G, modo: 'paper' })).riepilogo.totale).toBe(50);
    });
});

describe('orfane: dichiarate, e ricucite quando la giornata porta l\'apertura', () => {
    const chiusura = t({ id: 9, pnl: -2, closes_trade_id: 8, placed_at: `${G}T11:00:00.000Z` });
    const apertura = t({ id: 8, pnl: 3 });

    it('senza apertura la chiusura e\' una posizione ORFANA, contata nel riepilogo', () => {
        const pos = posizioniChiuse([chiusura]);
        expect(pos).toHaveLength(1);
        expect(pos[0].orfana).toBe(true);
        expect(riepilogoChiuse(pos).orfane).toBe(1);
    });

    it('unita alla giornata letta dal database torna UN ciclo intero (+1), non orfano', () => {
        const pos = posizioniChiuse(unisciRighe([chiusura], [apertura, chiusura]));
        expect(pos).toHaveLength(1);
        expect(pos[0].orfana).toBe(false);
        expect(pos[0].pnlGlobale).toBe(1);
    });

    it('nell\'unione vince la MEMORIA (piu\' fresca), mai due volte la stessa riga', () => {
        const memoria = [t({ id: 8, pnl: 3, status: 'won' })];
        const db = [t({ id: 8, pnl: 0, status: 'open' })];
        const u = unisciRighe(memoria, db);
        expect(u).toHaveLength(1);
        expect(u[0].status).toBe('won');
    });

    it('stesso id su due bot diversi NON si fonde (tabelle diverse)', () => {
        const u = unisciRighe([t({ id: 8 })], [t({ id: 8, __bot: 'omega' })]);
        expect(u).toHaveLength(2);
    });
});

describe('tennis: i 4 bot nella stessa regola, legame mancante (B13) dichiarato', () => {
    it('netto: Betfair se c\'e\', altrimenti lordo - commissione; paper mai Betfair', () => {
        expect(nettoOrdineTennis(ordine({ id: 1 }))).toBe(1.52);
        expect(nettoOrdineTennis(ordine({ id: 1, pnl_betfair: 1.5 }))).toBe(1.5);
        expect(nettoOrdineTennis(ordine({ id: 1, mode: 'paper', pnl_betfair: 1.5 }))).toBe(1.52);
        expect(nettoOrdineTennis(ordine({ id: 1, pnl: null }))).toBeNull();
    });

    it('un ordine non regolato, in errore o non di un bot tennis non entra', () => {
        expect(rigaDaOrdineTennis(ordine({ id: 1, settled_at: null }), null, eBot)).toBeNull();
        expect(rigaDaOrdineTennis(ordine({ id: 1, status: 'error' }), null, eBot)).toBeNull();
        expect(rigaDaOrdineTennis(ordine({ id: 1, source: 'runner' }), null, eBot)).toBeNull();
        expect(rigaDaOrdineTennis(ordine({ id: 1, pnl: null }), null, eBot)).toBeNull();
    });

    it('ingresso e uscita sulla stessa selezione: UN gruppo a ripiego col netto esatto', () => {
        const righe = [
            ordine({ id: 10, side: 'back', pnl: 1.6, commission: 0.08 }),
            ordine({ id: 11, side: 'lay', pnl: -1.2, commission: 0 }),
        ].map((o) => rigaDaOrdineTennis(o, 'Sinner - Alcaraz', eBot) as TradeChiudibile);
        const pos = posizioniChiuse(righe);
        expect(pos).toHaveLength(1);
        expect(pos[0].legame).toBe('ripiego');
        expect(pos[0].pnlGlobale).toBe(0.32);          // 1.52 - 1.20
        expect(pos[0].esito).toBe('vinta');             // prima: 1 vinto + 1 perso
        expect(pos[0].righe).toHaveLength(2);
        expect(pos[0].righe.every((r) => !r.chiusura)).toBe(true);   // nessuna "copertura" inventata
        expect(riepilogoChiuse(pos).ripiego).toBe(1);
        expect(pos[0].partita).toBe('Sinner - Alcaraz');
        expect(pos[0].sport).toBe('tennis');
    });

    it('selezioni diverse, bot diversi o modalita\' diverse: gruppi DIVERSI', () => {
        const righe = [
            ordine({ id: 10 }),
            ordine({ id: 11, selection_id: 222 }),
            ordine({ id: 12, source: 'tennis_pro' }),
            ordine({ id: 13, mode: 'paper' }),
        ].map((o) => rigaDaOrdineTennis(o, null, eBot) as TradeChiudibile);
        expect(posizioniChiuse(righe)).toHaveLength(4);
    });

    it('la giornata e\' quella del regolamento anche per il tennis', () => {
        const r = rigaDaOrdineTennis(ordine({
            id: 10, placed_at: '2026-09-23T21:30:00.000Z', settled_at: '2026-09-23T22:30:00.000Z',
        }), null, eBot) as TradeChiudibile;
        expect(posizioniChiuse([r])[0].giorno).toBe('2026-09-24');
    });
});

describe('giornataDi: la memoria per ora da\' lo STESSO giorno del formattatore', () => {
    it('su istanti a caso e sui cambi d\'ora legale', () => {
        const istanti: number[] = [
            Date.parse('2026-03-29T00:59:59.000Z'), Date.parse('2026-03-29T01:00:00.000Z'),
            Date.parse('2026-03-28T22:59:59.999Z'), Date.parse('2026-03-28T23:00:00.000Z'),
            Date.parse('2026-10-25T00:59:59.000Z'), Date.parse('2026-10-24T21:59:59.999Z'),
            Date.parse('2026-10-24T22:00:00.000Z'), Date.parse('2026-10-25T22:59:59.999Z'),
            Date.parse('2026-10-25T23:00:00.000Z'),
        ];
        let seme = 7;
        for (let i = 0; i < 400; i++) {
            seme = (seme * 1103515245 + 12345) % 2147483648;
            istanti.push(Date.parse('2026-01-01T00:00:00.000Z') + (seme % (365 * 86400)) * 1000);
        }
        for (const ms of istanti) {
            const iso = new Date(ms).toISOString();
            expect(giornataDi(iso), iso).toBe(romeDay(new Date(ms)));
        }
    });
});
