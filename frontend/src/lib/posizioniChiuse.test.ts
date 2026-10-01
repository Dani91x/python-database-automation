// ============================================================================
// posizioniChiuse.test.ts
//
// Il caso che conta davvero è il GREEN-UP: apertura che vince, copertura che
// perde, e la posizione in realtà guadagna. Guardare le righe da sole fa
// sembrare una copertura riuscita una sconfitta a metà — ed è successo per
// davvero il 14/09 (#287 +0,33 / #288 −0,30 = +0,03).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    posizioniChiuse, filtraChiuse, riepilogoChiuse, esitoDi, statoDaNetto, fuoriGiornata,
    unisciRighe, regolatoNelGiorno, aCavalloDellaMezzanotte, giornoDalDatabase, rigaDaOrdineTennis,
    type TradeChiudibile,
} from './posizioniChiuse';
import type { TennisBotOrderRow } from './tennis';

function t(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'safe', event_id: 'E1', event_name: 'Rossi – Bianchi', sport: 'tennis',
        mode: 'live', status: 'won', pnl: 0, side: 'back', price: 1.1, size: 3,
        selection_name: 'Rossi', placed_at: '2026-09-14T14:00:00Z',
        settled_at: '2026-09-14T15:00:00Z', closes_trade_id: null, strategy: 'tennis',
        ...over,
    };
}

describe('una posizione = apertura + le sue coperture', () => {
    it('GREEN-UP: apertura +0,33 e copertura −0,30 fanno UNA posizione da +0,03', () => {
        const p = posizioniChiuse([
            t({ id: 287, status: 'won', pnl: 0.33 }),
            t({ id: 288, status: 'lost', pnl: -0.30, closes_trade_id: 287, side: 'lay', price: 1.1, size: 3.03 }),
        ]);
        expect(p).toHaveLength(1);              // UNA posizione, non due
        expect(p[0].id).toBe(287);
        expect(p[0].pnlGlobale).toBe(0.03);
        expect(p[0].esito).toBe('vinta');       // e ha VINTO, anche se una gamba ha perso
        expect(p[0].righe).toHaveLength(2);
        expect(p[0].righe.filter((r) => r.chiusura)).toHaveLength(1);
    });

    it('le coperture NON diventano posizioni proprie: raddoppierebbero il conto', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 5 }),
            t({ id: 2, pnl: -4, closes_trade_id: 1 }),
        ]);
        expect(p.map((x) => x.id)).toEqual([1]);
    });

    it('una posizione ANCORA APERTA non è chiusa, e non compare', () => {
        expect(posizioniChiuse([t({ id: 1, status: 'open', pnl: null })])).toHaveLength(0);
        expect(posizioniChiuse([t({ id: 1, status: 'hedged', pnl: null })])).toHaveLength(0);
    });

    it('le righe in ERRORE non sono operazioni: non entrano in nessun conto', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 2 }),
            t({ id: 2, status: 'error', pnl: -100, closes_trade_id: 1 }),
        ]);
        expect(p[0].pnlGlobale).toBe(2);
        expect(p[0].righe).toHaveLength(1);
    });

    it('le più recenti stanno in cima', () => {
        const p = posizioniChiuse([
            t({ id: 1, settled_at: '2026-09-14T10:00:00Z' }),
            t({ id: 2, settled_at: '2026-09-14T16:00:00Z' }),
        ]);
        expect(p.map((x) => x.id)).toEqual([2, 1]);
    });

    // 18/09, certezza di chiusura — una gamba di chiusura ANNULLATA (rifiutata
    // da Betfair) non andrà MAI a won/lost/void: prima di questo fix bastava
    // UNA sola gamba `cancelled` a far sparire l'intera posizione da questa
    // tab per sempre, anche a fischio finale, con la sua stessa apertura
    // regolarmente vinta/persa — né aperta né chiusa, in un limbo.
    it('una gamba di chiusura ANNULLATA non impedisce più alla posizione di comparire', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 4.78, side: 'lay', price: 70 }),
            // tre back a chiudere, come Union Brescia-Treviso: due abbinati, uno annullato
            t({ id: 2, status: 'lost', pnl: -4.6, closes_trade_id: 1, side: 'back', price: 9.6, size: 9.6 }),
            t({ id: 3, status: 'lost', pnl: -4.6, closes_trade_id: 1, side: 'back', price: 9.6, size: 9.6 }),
            t({ id: 4, status: 'cancelled', pnl: null, closes_trade_id: 1, side: 'back', price: 12, size: 2.08 }),
        ]);
        expect(p).toHaveLength(1);
        expect(p[0].id).toBe(1);
        // la gamba annullata resta VISIBILE nel dettaglio (trasparenza sul
        // pezzo che non è andato a mercato), ma non conta nel P&L (pnl: null)
        expect(p[0].righe).toHaveLength(4);
        expect(p[0].righe.find((r) => r.id === 4)?.stato).toBe('cancelled');
        expect(p[0].pnlGlobale).toBeCloseTo(4.78 - 4.6 - 4.6, 5);
    });

    it('ma una gamba ANCORA VIVA (non annullata, non regolata) blocca ancora tutto', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 4.78, side: 'lay', price: 70 }),
            t({ id: 2, status: 'open', pnl: null, closes_trade_id: 1, side: 'back', price: 9.6, size: 9.6 }),
        ]);
        expect(p).toHaveLength(0);
    });
});

describe('esito — un centesimo di arrotondamento non è una vittoria', () => {
    it('sopra soglia vinta, sotto persa, in mezzo pari', () => {
        expect(esitoDi(0.03)).toBe('vinta');
        expect(esitoDi(-0.03)).toBe('persa');
        expect(esitoDi(0)).toBe('pari');
        expect(esitoDi(0.001)).toBe('pari');
    });
});

// C-05 (01/10, rilievi bassi): l'esito con la regola del DATABASE (zero esatto
// al centesimo: `total_pnl > 0` vinta, `< 0` persa). FALSIFICAZIONE: rimettendo
// la soglia di +/-0,005 (`pnl > 0.005`) i casi di mezzo centesimo diventano rossi.
describe('C-05: «pari» = zero esatto al centesimo, come il database', () => {
    it('mezzo centesimo si porta al centesimo, in modo simmetrico', () => {
        expect(esitoDi(0.005)).toBe('vinta');
        expect(esitoDi(-0.005)).toBe('persa');
        expect(esitoDi(0.004)).toBe('pari');
        expect(esitoDi(-0.004)).toBe('pari');
    });
    it('il residuo di un calcolo in virgola mobile non diventa una vinta', () => {
        expect(0.1 + 0.2 - 0.3).toBeGreaterThan(0);
        expect(esitoDi(0.1 + 0.2 - 0.3)).toBe('pari');
    });
    it('un centesimo basta per un esito; lo stato di una riga tennis segue la stessa regola', () => {
        expect(esitoDi(0.01)).toBe('vinta');
        expect(esitoDi(-0.01)).toBe('persa');
        expect(statoDaNetto(0.005)).toBe('won');
        expect(statoDaNetto(-0.005)).toBe('lost');
        expect(statoDaNetto(0)).toBe('void');
    });
});

describe('paper e live restano posizioni DIVERSE', () => {
    it('la modalità si legge dalla riga di apertura ed è fail-closed', () => {
        const p = posizioniChiuse([
            t({ id: 1, mode: 'live' }),
            t({ id: 2, mode: 'paper', event_id: 'E2' }),
            t({ id: 3, mode: undefined, event_id: 'E3' }),
        ]);
        expect(p.find((x) => x.id === 1)?.modo).toBe('live');
        expect(p.find((x) => x.id === 2)?.modo).toBe('paper');
        // non dichiarata = paper, mai soldi veri per distrazione
        expect(p.find((x) => x.id === 3)?.modo).toBe('paper');
    });

    it('il filtro per modalità tiene separati i due mondi', () => {
        const p = posizioniChiuse([
            t({ id: 1, mode: 'live', pnl: 1 }),
            t({ id: 2, mode: 'paper', pnl: -50, event_id: 'E2' }),
        ]);
        const soloVeri = filtraChiuse(p, { modo: 'live' });
        expect(soloVeri).toHaveLength(1);
        expect(riepilogoChiuse(soloVeri).totale).toBe(1);   // mai 1 − 50
    });
});

describe('filtri', () => {
    const p = posizioniChiuse([
        t({ id: 1, pnl: 3, sport: 'tennis', __bot: 'safe' }),
        t({ id: 2, pnl: -2, sport: 'calcio', event_id: 'E2', __bot: 'omega' }),
        t({ id: 3, pnl: 0, sport: 'calcio', event_id: 'E3', __bot: 'mike' }),
    ]);

    it('per esito', () => {
        expect(filtraChiuse(p, { esito: 'vinta' }).map((x) => x.id)).toEqual([1]);
        expect(filtraChiuse(p, { esito: 'persa' }).map((x) => x.id)).toEqual([2]);
        expect(filtraChiuse(p, { esito: 'pari' }).map((x) => x.id)).toEqual([3]);
    });

    it('per sport e per bot', () => {
        expect(filtraChiuse(p, { sport: 'calcio' })).toHaveLength(2);
        expect(filtraChiuse(p, { bot: 'mike' }).map((x) => x.id)).toEqual([3]);
    });

    it('«tutte» non filtra niente', () => {
        expect(filtraChiuse(p, { esito: 'tutte', sport: 'tutti', bot: 'tutti' })).toHaveLength(3);
        expect(filtraChiuse(p, {})).toHaveLength(3);
    });
});

describe('riepilogo — descrive QUELLO CHE SI VEDE, non tutto il resto', () => {
    it('conta esiti e somma i P&L globali delle righe che riceve', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 3 }),
            t({ id: 2, pnl: -2, event_id: 'E2' }),
            t({ id: 3, pnl: 0, event_id: 'E3' }),
        ]);
        const r = riepilogoChiuse(p);
        expect(r).toMatchObject({ n: 3, vinte: 1, perse: 1, pari: 1, totale: 1 });
        expect(r.percentualeVinte).toBeCloseTo(0.5, 5);
    });

    it('nessuna posizione: totale null, non 0,00 €', () => {
        const r = riepilogoChiuse([]);
        expect(r.totale).toBeNull();
        expect(r.percentualeVinte).toBeNull();
    });

    it('solo pareggi: nessuna percentuale inventata', () => {
        const p = posizioniChiuse([t({ id: 1, pnl: 0 })]);
        expect(riepilogoChiuse(p).percentualeVinte).toBeNull();
    });
});

// ===========================================================================
// REVIEW 14/09 — LE COPERTURE SI ATTACCANO ALLA RIGA GIUSTA.
// Gli id vengono da TRE tabelle diverse: il #288 di Safe e il #288 di Omega
// sono righe diverse.
// ===========================================================================

describe('collisione di id fra bot diversi', () => {
    it('la copertura di Safe NON si attacca all’apertura di Omega con lo stesso id', () => {
        const p = posizioniChiuse([
            t({ id: 288, __bot: 'omega', pnl: 10, event_id: 'O1', event_name: 'Partita Omega' }),
            t({ id: 900, __bot: 'safe', pnl: 1, event_id: 'S1', event_name: 'Partita Safe' }),
            // copertura di SAFE che chiude il 288 DI SAFE (che non esiste qui)
            t({ id: 901, __bot: 'safe', pnl: -0.5, closes_trade_id: 288, event_id: 'S1' }),
        ]);
        const omega = p.find((x) => x.bot === 'omega' && x.id === 288);
        // l'apertura di Omega resta intatta: 10, non 9,50
        expect(omega?.pnlGlobale).toBe(10);
        expect(omega?.righe).toHaveLength(1);
    });

    it('una copertura si attacca alla SUA apertura, stesso bot', () => {
        const p = posizioniChiuse([
            t({ id: 288, __bot: 'safe', pnl: 0.33 }),
            t({ id: 289, __bot: 'safe', pnl: -0.30, closes_trade_id: 288 }),
            t({ id: 288, __bot: 'omega', pnl: 99, event_id: 'O1' }),
        ]);
        const safe = p.find((x) => x.bot === 'safe');
        expect(safe?.pnlGlobale).toBe(0.03);
        expect(p.find((x) => x.bot === 'omega')?.pnlGlobale).toBe(99);
    });
});

describe('coperture orfane — i loro euro non spariscono', () => {
    it('una copertura senza apertura nota diventa una posizione a sé', () => {
        const p = posizioniChiuse([
            t({ id: 500, __bot: 'safe', pnl: -0.30, closes_trade_id: 499 }),
        ]);
        expect(p).toHaveLength(1);
        expect(p[0].pnlGlobale).toBe(-0.3);
    });
});

describe('catene di chiusure A - B - C', () => {
    it('il P&L della TERZA gamba entra nel conto', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 10 }),
            t({ id: 2, pnl: -4, closes_trade_id: 1 }),
            t({ id: 3, pnl: -1, closes_trade_id: 2 }),   // copre la copertura
        ]);
        expect(p).toHaveLength(1);
        expect(p[0].pnlGlobale).toBe(5);
        expect(p[0].righe).toHaveLength(3);
    });

    it('un ciclo nei dati non manda in loop infinito', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 1 }),
            t({ id: 2, pnl: 1, closes_trade_id: 1 }),
            t({ id: 3, pnl: 1, closes_trade_id: 2 }),
        ]);
        expect(p[0].righe.length).toBeLessThanOrEqual(3);
    });
});

describe('una gamba ancora viva = posizione NON chiusa', () => {
    it('apertura regolata ma copertura aperta: non compare fra le chiuse', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 3 }),
            t({ id: 2, status: 'open', pnl: null, closes_trade_id: 1 }),
        ]);
        // +3 sarebbe il profitto PIENO di una posizione che invece e' coperta
        expect(p).toHaveLength(0);
    });

    it('quando anche la copertura si regola, la posizione compare col netto', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 3 }),
            t({ id: 2, status: 'lost', pnl: -2.7, closes_trade_id: 1 }),
        ]);
        expect(p).toHaveLength(1);
        expect(p[0].pnlGlobale).toBe(0.3);
    });
});

// ============================================================================
// SOLO LA GIORNATA (ordine dell'utente, 17/09)
//
// «in "posizioni chiuse" voglio vedere SOLO le posizioni della giornata, non
// le precedenti; per i giorni precedenti deve esserci uno STORICO dedicato».
//
// La giornata e' quella di REGOLAMENTO (24/09; fino al 23/09 era il
// piazzamento), nel fuso Europe/Rome. Il confine e'
// mezzanotte a ROMA, non a Londra e non nel fuso del browser: d'estate Roma e'
// UTC+2, quindi le 22:00 UTC sono gia' il giorno dopo.
// ============================================================================
describe('posizioni chiuse: SOLO la giornata operativa', () => {
    const oggi = t({
        id: 10, pnl: 1,
        placed_at: '2026-09-17T09:00:00.000Z',      // 11:00 a Roma, 17 settembre
        settled_at: '2026-09-17T12:00:00.000Z',
    });
    const ieri = t({
        id: 11, pnl: 5,
        placed_at: '2026-09-16T09:00:00.000Z',      // 16 settembre
        settled_at: '2026-09-16T12:00:00.000Z',
    });

    // 24/09 - REGOLA CAMBIATA su ordine dell'utente ("i dati sono mischiati
    // per giornata"): la giornata e' quella di REGOLAMENTO, come la barra di
    // giornata e il conto Betfair. Prima era il piazzamento (test del 17/09).
    it('la giornata viene dal REGOLAMENTO, non dal piazzamento', () => {
        // piazzata il 16 alle 23:30 di Roma, regolata il 17: giornata = 17
        const p = posizioniChiuse([t({
            id: 12, pnl: 1,
            placed_at: '2026-09-16T21:30:00.000Z',   // 23:30 a Roma del 16
            settled_at: '2026-09-17T06:00:00.000Z',
        })]);
        expect(p[0].giorno).toBe('2026-09-17');
        expect(p[0].giornoDa).toBe('regolamento');
    });

    it('il confine e\' mezzanotte a ROMA: d\'estate le 22:00 UTC sono gia\' il giorno dopo', () => {
        const prima = posizioniChiuse([t({ id: 20, pnl: 1, settled_at: '2026-09-16T21:59:59.000Z' })]);
        const dopo = posizioniChiuse([t({ id: 21, pnl: 1, settled_at: '2026-09-16T22:00:01.000Z' })]);
        expect(prima[0].giorno).toBe('2026-09-16');   // 23:59:59 a Roma
        expect(dopo[0].giorno).toBe('2026-09-17');    // 00:00:01 a Roma
    });

    it('d\'inverno Roma e\' UTC+1: il confine si sposta alle 23:00 UTC', () => {
        const prima = posizioniChiuse([t({ id: 22, pnl: 1, placed_at: '2026-01-14T10:00:00.000Z', settled_at: '2026-01-14T22:59:59.000Z' })]);
        const dopo = posizioniChiuse([t({ id: 23, pnl: 1, placed_at: '2026-01-14T10:00:00.000Z', settled_at: '2026-01-14T23:00:01.000Z' })]);
        expect(prima[0].giorno).toBe('2026-01-14');
        expect(dopo[0].giorno).toBe('2026-01-15');
    });

    it('senza nessun istante di regolamento ripiega sul piazzamento, e lo DICE', () => {
        const p = posizioniChiuse([t({ id: 24, pnl: 1, placed_at: '2026-09-17T09:00:00.000Z', settled_at: null })]);
        expect(p[0].giorno).toBe('2026-09-17');
        expect(p[0].giornoDa).toBe('piazzamento');
    });

    it('una riga PAPER non eredita mai la data di Betfair, anche se il campo risulta valorizzato (verifica del coordinatore 24/09)', () => {
        const p = posizioniChiuse([t({
            id: 26, pnl: 1, mode: 'paper', pnl_betfair: 0.95,
            settled_at: '2026-09-16T21:50:00.000Z',
            pnl_betfair_settled_at: '2026-09-16T22:20:00.000Z',
        })]);
        expect(p[0].giorno).toBe('2026-09-16');
        expect(p[0].modo).toBe('paper');
    });

    it('il reale di Betfair porta la SUA ora di regolamento (settledDate), non quella del bot', () => {
        // il bot ha chiuso alle 23:50 del 16, Betfair ha regolato alle 00:20 del 17
        const p = posizioniChiuse([t({
            id: 25, pnl: 1, pnl_betfair: 0.95,
            settled_at: '2026-09-16T21:50:00.000Z',
            pnl_betfair_settled_at: '2026-09-16T22:20:00.000Z',
        })]);
        expect(p[0].giorno).toBe('2026-09-17');
        expect(p[0].pnlGlobale).toBe(0.95);
    });

    it('il filtro di giornata tiene OGGI e lascia fuori IERI', () => {
        const tutte = posizioniChiuse([oggi, ieri]);
        expect(tutte).toHaveLength(2);
        const soloOggi = filtraChiuse(tutte, { giorno: '2026-09-17' });
        expect(soloOggi.map((p) => p.id)).toEqual([10]);
    });

    // ⚠️ FALSIFICAZIONE: senza il filtro il totale prende dentro anche ieri.
    // E' il difetto che il banco della giornata aveva fino al 17/09: le righe
    // dei tre bot arrivano dalle RPC di stato con un semplice `limit`
    // (`get_omega_trades(p_limit=2000)`), non filtrate per giorno.
    it('falsificazione: senza filtro il totale somma anche i giorni precedenti', () => {
        const tutte = posizioniChiuse([oggi, ieri]);
        expect(riepilogoChiuse(tutte).totale).toBe(6);                       // 1 + 5, sbagliato
        expect(riepilogoChiuse(filtraChiuse(tutte, { giorno: '2026-09-17' })).totale).toBe(1);
    });

    it('senza giornata il filtro non filtra (lo usa lo storico)', () => {
        const tutte = posizioniChiuse([oggi, ieri]);
        expect(filtraChiuse(tutte, {}).length).toBe(2);
        expect(filtraChiuse(tutte, { giorno: null }).length).toBe(2);
        expect(filtraChiuse(tutte, { giorno: '' }).length).toBe(2);
    });

    it('il filtro di giornata si combina con gli altri, non li sostituisce', () => {
        const tutte = posizioniChiuse([
            oggi,
            t({ id: 13, pnl: 2, mode: 'paper', placed_at: '2026-09-17T09:00:00.000Z' }),
        ]);
        const veri = filtraChiuse(tutte, { giorno: '2026-09-17', modo: 'live' });
        expect(veri.map((p) => p.id)).toEqual([10]);
    });

    it('una posizione senza data di piazzamento ripiega sul regolamento', () => {
        const p = posizioniChiuse([t({
            id: 30, pnl: 1, placed_at: null, settled_at: '2026-09-17T12:00:00.000Z',
        })]);
        expect(p[0].piazzataAt).toBe('');
        expect(p[0].giorno).toBe('2026-09-17');   // i suoi euro non spariscono dal giorno
    });

    it('quante restano fuori dalla giornata: si dice, non si fanno sparire', () => {
        const tutte = posizioniChiuse([oggi, ieri]);
        expect(fuoriGiornata(tutte, '2026-09-17')).toEqual({ altriGiorni: 1, senzaData: 0 });
    });
});

// ============================================================================
// 01/10 - GIORNATA = GIORNO DELLA PARTITA (ordine dell'utente: «le chiusure
// devono essere assegnate alla giornata di riferimento»). Il giorno lo decide
// il DATABASE (`giorno_partita`, `giorno_da`, `in_day`); la memoria senza quel
// dato resta sul regolamento come PROVVISORIA, mai un giorno partita calcolato
// qui.
// ============================================================================
describe('01/10 - giorno della partita dal database', () => {
    // partita del 30/09 alle 23:30 di Roma, regolata il 01/10 alle 01:15 di Roma
    const mezzanotte = (over: Partial<TradeChiudibile> = {}) => t({
        id: 40, pnl: 2, placed_at: '2026-09-30T21:30:00.000Z', settled_at: '2026-09-30T23:15:00.000Z',
        giorno_partita: '2026-09-30', giorno_da: 'partita', in_day: true, ...over,
    });

    it('partita delle 23:30 regolata alle 01:15: e\' del giorno della PARTITA (30/09), non del regolamento (01/10)', () => {
        const [p] = posizioniChiuse([mezzanotte()]);
        expect(p.giorno).toBe('2026-09-30');
        expect(p.giornoDa).toBe('partita');
        expect(p.giornoConfermato).toBe(true);
        expect(filtraChiuse([p], { giorno: '2026-10-01' })).toHaveLength(0);
        expect(filtraChiuse([p], { giorno: '2026-09-30' })).toHaveLength(1);
    });

    it('FALSIFICAZIONE: la stessa riga SENZA il dato del database cade sul regolamento (01/10), provvisoria', () => {
        const [p] = posizioniChiuse([mezzanotte({ giorno_partita: undefined, giorno_da: undefined, in_day: undefined })]);
        expect(p.giorno).toBe('2026-10-01');
        expect(p.giornoDa).toBe('regolamento');
        expect(p.giornoConfermato).toBe(false);
    });

    it('inizio partita non noto (giorno_da=piazzamento): il giorno di piazzamento, dichiarato', () => {
        const [p] = posizioniChiuse([mezzanotte({ giorno_partita: null, giorno_da: 'piazzamento' })]);
        expect(p.giorno).toBe('2026-09-30');
        expect(p.giornoDa).toBe('piazzamento');
        expect(p.giornoConfermato).toBe(true);
        expect(giornoDalDatabase([t({ id: 1, giorno_da: null })], '')).toBeNull();
    });

    it('la memoria (senza il dato) EREDITA il giorno della partita dalla riga letta dal database', () => {
        const memoria = [mezzanotte({ giorno_partita: undefined, giorno_da: undefined, in_day: undefined, pnl: 2.5 })];
        const dalDb = [mezzanotte({ pnl: 2 })];
        const unite = unisciRighe(memoria, dalDb);
        expect(unite).toHaveLength(1);
        expect(unite[0].pnl).toBe(2.5);                 // vince la memoria (piu' fresca)
        expect(unite[0].giorno_partita).toBe('2026-09-30');
        expect(posizioniChiuse(unite)[0].giorno).toBe('2026-09-30');
    });

    it('bot tennis: il giorno della partita passa anche dalla traduzione dell\'ordine', () => {
        const o = {
            id: 50, bet_id: 'T50', client_order_ref: 'awtq50', request_id: 50, mode: 'live',
            source: 'tennis_swing', event_id: 'T1', market_id: '1.9', selection_id: 77, handicap: 0,
            side: 'back', order_type: 'LIMIT', price: 2, size: 1, size_matched: 1, size_remaining: 0,
            size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 2,
            status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: '2026-09-30T21:00:00+00:00',
            matched_at: null, updated_at: '2026-09-30T23:30:00+00:00', pnl: 1, commission: 0.05,
            settled_at: '2026-09-30T23:30:00+00:00', pnl_betfair: null, pnl_betfair_settled_at: null,
            event_name: 'Sinner v Alcaraz', giorno_partita: '2026-09-30', giorno_da: 'partita', in_day: true,
        } as unknown as TennisBotOrderRow;
        const r = rigaDaOrdineTennis(o, 'Sinner v Alcaraz', () => true) as TradeChiudibile;
        expect(r.giorno_partita).toBe('2026-09-30');
        expect(posizioniChiuse([r])[0].giorno).toBe('2026-09-30');
    });
});

describe('01/10 (B-12) - controprova con la barra sullo STESSO perimetro', () => {
    const oggi = t({ id: 1, pnl: 1, settled_at: '2026-10-01T10:00:00.000Z', placed_at: '2026-10-01T09:00:00.000Z',
        giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true });
    const ieriRegolataOggi = t({ id: 2, pnl: 2, event_id: 'E2', placed_at: '2026-09-30T21:30:00.000Z',
        settled_at: '2026-09-30T23:15:00.000Z', giorno_partita: '2026-09-30', giorno_da: 'partita', in_day: false });

    it('regolato oggi sul conto = gambe regolate oggi, qualunque sia la partita (come la barra)', () => {
        const pos = posizioniChiuse([oggi, ieriRegolataOggi]);
        expect(regolatoNelGiorno(pos, '2026-10-01').totale).toBe(3);
        // la scheda di oggi (giorno partita) ne mostra solo 1,00
        expect(riepilogoChiuse(filtraChiuse(pos, { giorno: '2026-10-01' })).totale).toBe(1);
    });

    it('la posizione a cavallo della mezzanotte si ELENCA, da entrambe le giornate', () => {
        const pos = posizioniChiuse([oggi, ieriRegolataOggi]);
        expect(aCavalloDellaMezzanotte(pos, '2026-10-01').map((x) => x.p.id)).toEqual([2]);
        expect(aCavalloDellaMezzanotte(pos, '2026-09-30').map((x) => [x.p.id, x.regolata])).toEqual([[2, '2026-10-01']]);
    });

    it('netto di Betfair con la SUA data di regolamento; paper fuori', () => {
        const bf = t({ id: 3, pnl: 5, pnl_betfair: 4.8, settled_at: '2026-09-30T21:50:00.000Z',
            pnl_betfair_settled_at: '2026-09-30T22:20:00.000Z' });
        const paper = t({ id: 4, pnl: 9, mode: 'paper', settled_at: '2026-10-01T10:00:00.000Z' });
        const r = regolatoNelGiorno(posizioniChiuse([bf, paper]), '2026-10-01');
        expect(r).toEqual({ totale: 4.8, reale: 4.8, stimato: null });
    });
});
