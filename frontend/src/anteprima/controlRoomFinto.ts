// ============================================================================
// controlRoomFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA della Control Room.
//
// Non e' importato dall'app. Il server di anteprima
// (AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs, ANTEPRIMA=popolata)
// sostituisce con un alias Vite ESATTO l'import
// '@/components/controlroom/useControlRoom' con questo file:
//   - qui sotto il modulo VERO si importa con percorso RELATIVO, che l'alias
//     non intercetta, e si ri-esporta tutto (`export *`);
//   - `useControlRoom` e' ridefinito qui (un export esplicito ha la
//     precedenza su `export *`) e restituisce un modello di vista FINTO ma
//     con le IDENTICHE chiavi e tipi del vero (`ReturnType<typeof useControlRoom>`
//     del modulo vero), costruito come `vm()` di `pages/ControlRoom.test.tsx`
//     e con le funzioni VERE dove il test le usa (`contoAdesso`,
//     `rischioBotLive`, `stopDelConto`, `stopDeiBot`, `raggruppaOrdiniConto`,
//     `posizioniChiuse`, `dettaglioDi`, `quotaViva`, `partiteConPosizione`).
//   - i comandi sono no-op asincroni: dall'anteprima non parte niente.
//
// La giornata e' quella del prototipo `AUDIT_2026-10-01/REDESIGN/prototipo/
// js/s_controlroom.js`: Inter-Torino 58' 1-0, Real Betis-Getafe 31' 0-0,
// Sinner-Draper in gioco; in attesa Bologna-Udinese, Musetti-Fritz,
// Brentford-Fulham, Lens-Nantes. Mike in LIVE, il resto in prova.
// Orologio: 2026-10-01T08:38:00Z (10:38 a Roma).
// ============================================================================
import type { useControlRoom as hookVero } from '../components/controlroom/useControlRoom';
import type {
    StatoBot, OperazionePartita, PosizioneAperta, PropostaVista, PropostaOppVista,
} from '../components/controlroom/useControlRoom';
import type { Bot, GruppoCampionato, PartitaGiornata, LineaOuScheda } from '../lib/controlRoom';
import type { PropostaUscitaOmega } from '../lib/omegaProposte';
import type { PrezzoVivo } from '../lib/controlRoomProposte';
import type { MikeEvent } from '../lib/mike';
import type { TradeChiudibile } from '../lib/posizioniChiuse';
import type { ProvaGiornata } from '../lib/provaGiornata';
import type { ComposizioneConto } from '../lib/composizioneConto';
import type { RigaOrdine } from '../lib/statoOrdine';
import type { MatchTradeLike } from '../lib/omegaMatches';
import type { PropostaFlusso } from '../lib/proposteUscite';
import { contoAdesso, rischioBotLive, scartoContoBot, partiteConPosizione } from '../components/controlroom/testata/soldiVeri';
import { stopDelConto, stopDeiBot } from '../components/controlroom/testata/stopPerdita';
import { raggruppaOrdiniConto } from '../components/controlroom/ordiniConto';
import { dettaglioDi, quotaViva } from '../components/controlroom/dettaglioRiga';
import { posizioniChiuse } from '../lib/posizioniChiuse';

export * from '../components/controlroom/useControlRoom';

type Vm = ReturnType<typeof hookVero>;

// ------------------------------------------------------------------ orologio

const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
/** istante ISO `s` secondi prima di adesso */
const fa = (s: number) => new Date(ORA_MS - s * 1000).toISOString();
/** istante ISO a un'ora UTC di oggi, 'HH:MM' */
const alle = (hhmm: string) => `2026-10-01T${hhmm}:00Z`;
const ms = (hhmm: string) => Date.parse(alle(hhmm));

/** comando dell'anteprima: non fa niente, come un servizio che non c'e' */
const nulla = async (): Promise<void> => { /* anteprima: nessun comando */ };

// ------------------------------------------------------------------ partite

const EV = {
    inter: '34812001', betis: '34812044', sinner: '34813501',
    bologna: '34812102', brentford: '34812130', lens: '34812177', musetti: '34813540',
} as const;

const MO = {
    inter: '1.248120010', betis: '1.248120440', sinner: '1.248135010',
    bologna: '1.248121020', brentford: '1.248121300', lens: '1.248121770', musetti: '1.248135400',
} as const;

function linea(marketId: string, l: number, u: [number, number], o: [number, number], perMike = false): LineaOuScheda {
    return {
        marketId, linea: l, stato: 'OPEN', decisa: false, perMike,
        under: { back: u[0], lay: u[1] }, over: { back: o[0], lay: o[1] }, etaCambioS: 2,
    };
}

function partita(over: Partial<PartitaGiornata> & Pick<PartitaGiornata, 'event_id' | 'nome' | 'campionato' | 'koMs' | 'stato'>): PartitaGiornata {
    return {
        sport: 'calcio',
        minuto: null, punteggio: null, controlloDisponibile: true,
        etaFeedS: 1, freschezza: 'fresca', latenzaQuoteS: 2, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        media: { video: true, viz: true }, marketId: null,
        soldi: null, target: null, avanzamento: null, extra: null,
        statoMercato: 'OPEN', volumeMercato: null, giocatori: null, flusso: null, flussoMike: null, lineeOu: [],
        ...over,
    };
}

const INTER = partita({
    event_id: EV.inter, nome: 'Inter v Torino', campionato: 'Serie A', koMs: ms('07:25'), stato: 'live',
    minuto: 58, punteggio: '1-0', marketId: MO.inter, volumeMercato: 1843210,
    odds: { home: { back: 1.38, lay: 1.39 }, draw: { back: 5.6, lay: 5.7 }, away: { back: 11.5, lay: 12 } },
    lineeOu: [linea('1.248120013', 3.5, [1.22, 1.23], [5.4, 5.6], true), linea('1.248120014', 4.5, [1.07, 1.08], [13.5, 14.5], true)],
    soldi: {
        live: { netPnl: null, liability: 96.4, investito: 70, aperta: true },
        paper: { netPnl: null, liability: 14.8, investito: 2, aperta: true },
        modi: ['live', 'paper'], bots: ['omega', 'mike'],
    },
    target: { valore: 4, fonte: 'servizio' }, avanzamento: 72,
});

const BETIS = partita({
    event_id: EV.betis, nome: 'Real Betis v Getafe', campionato: 'La Liga', koMs: ms('08:07'), stato: 'live',
    minuto: 31, punteggio: '0-0', marketId: MO.betis, volumeMercato: 512330,
    odds: { home: { back: 2.02, lay: 2.04 }, draw: { back: 3.25, lay: 3.3 }, away: { back: 5.9, lay: 6 } },
    lineeOu: [linea('1.248120443', 3.5, [1.36, 1.37], [3.7, 3.8]), linea('1.248120444', 4.5, [1.12, 1.13], [8.8, 9.4])],
    soldi: {
        live: { netPnl: null, liability: 0, investito: 0, aperta: false },
        paper: { netPnl: null, liability: 26, investito: 6, aperta: true },
        modi: ['paper'], bots: ['safe'],
    },
    target: { valore: 4, fonte: 'servizio' }, avanzamento: 0,
});

const SINNER = partita({
    event_id: EV.sinner, sport: 'tennis', nome: 'Jannik Sinner v Jack Draper', campionato: 'ATP Pechino',
    koMs: ms('07:30'), stato: 'live', punteggio: '1-0 \u00b7 2-1', marketId: MO.sinner, volumeMercato: 908440,
    controlloDisponibile: false, media: { video: true, viz: false },
    giocatori: { p1: 'Jannik Sinner', p2: 'Jack Draper' },
    odds: { p1: { back: 1.24, lay: 1.25 }, p2: { back: 5, lay: 5.1 } },
    soldi: {
        live: { netPnl: null, liability: 0, investito: 0, aperta: false },
        paper: { netPnl: null, liability: 8.1, investito: 12, aperta: true },
        modi: ['paper'], bots: ['tennis_scalper', 'tennis_pro'],
    },
    target: { valore: 3, fonte: 'ripiego' }, avanzamento: 0,
});

const BOLOGNA = partita({
    event_id: EV.bologna, nome: 'Bologna v Udinese', campionato: 'Serie A', koMs: ms('08:52'), stato: 'pre',
    marketId: MO.bologna, volumeMercato: 233410,
    odds: { home: { back: 1.83, lay: 1.84 }, draw: { back: 3.7, lay: 3.75 }, away: { back: 4.9, lay: 5 } },
    lineeOu: [linea('1.248121023', 3.5, [1.29, 1.3], [4.3, 4.4], true), linea('1.248121024', 4.5, [1.1, 1.11], [10, 11], true)],
    target: { valore: 4, fonte: 'servizio' },
});

const MUSETTI = partita({
    event_id: EV.musetti, sport: 'tennis', nome: 'Lorenzo Musetti v Taylor Fritz', campionato: 'ATP Pechino',
    koMs: ms('08:58'), stato: 'pre', marketId: MO.musetti, volumeMercato: 141020,
    controlloDisponibile: false, media: { video: true, viz: false },
    giocatori: { p1: 'Lorenzo Musetti', p2: 'Taylor Fritz' },
    odds: { p1: { back: 2.36, lay: 2.4 }, p2: { back: 1.7, lay: 1.72 } },
});

const BRENTFORD = partita({
    event_id: EV.brentford, nome: 'Brentford v Fulham', campionato: 'Premier League', koMs: ms('09:22'), stato: 'pre',
    marketId: MO.brentford, volumeMercato: 388120,
    odds: { home: { back: 2.3, lay: 2.32 }, draw: { back: 3.45, lay: 3.5 }, away: { back: 3.3, lay: 3.35 } },
    lineeOu: [linea('1.248121303', 3.5, [1.41, 1.42], [3.35, 3.45]), linea('1.248121304', 4.5, [1.16, 1.17], [7, 7.4])],
});

const LENS = partita({
    event_id: EV.lens, nome: 'Lens v Nantes', campionato: 'Ligue 1', koMs: ms('09:52'), stato: 'pre',
    marketId: MO.lens, volumeMercato: 97450,
    odds: { home: { back: 1.71, lay: 1.72 }, draw: { back: 3.9, lay: 3.95 }, away: { back: 5.5, lay: 5.6 } },
});

const GIORNATA: GruppoCampionato[] = [
    { campionato: 'Serie A', primoKoMs: INTER.koMs, partite: [INTER, BOLOGNA] },
    { campionato: 'ATP Pechino', primoKoMs: SINNER.koMs, partite: [SINNER, MUSETTI] },
    { campionato: 'La Liga', primoKoMs: BETIS.koMs, partite: [BETIS] },
    { campionato: 'Premier League', primoKoMs: BRENTFORD.koMs, partite: [BRENTFORD] },
    { campionato: 'Ligue 1', primoKoMs: LENS.koMs, partite: [LENS] },
];

// ------------------------------------------------------- righe dei bot (aperte)

interface Gamba {
    bot: Bot; id: number; eventId: string; partita: string; selezione: string; lato: 'back' | 'lay';
    prezzo: number; size: number; modalita: 'paper' | 'live'; piazzata: string;
    marketId: string; selectionId: number; quale: string | null;
    book: { back: number; lay: number }; abbinabile: number; bloccabile: number;
    minuto: number | null; punteggio: string | null; meta?: Record<string, unknown>;
}

const liabilityDi = (g: Gamba) => Math.round((g.lato === 'lay' ? (g.prezzo - 1) * g.size : g.size) * 100) / 100;

function ordineDi(g: Gamba): RigaOrdine {
    return {
        status: 'open', side: g.lato, price: g.prezzo, size: g.size,
        size_requested: g.size, size_matched: g.size, size_remaining: 0, avg_price_matched: g.prezzo,
        betfair_updated_at: g.piazzata, meta: g.meta ?? null,
    };
}

/** la riga nel formato del dettaglio (stesse funzioni della scheda vera); tennis = null */
function dettaglioDiGamba(g: Gamba) {
    if (g.bot.startsWith('tennis_')) return null;
    const riga: MatchTradeLike = {
        id: g.id, event_id: g.eventId, event_name: g.partita, side: g.lato, status: 'open', pnl: 0,
        price: g.prezzo, size: g.size, liability: liabilityDi(g), placed_at: g.piazzata,
        meta: g.meta ?? null, runner_name: g.selezione, minute_at_entry: g.minuto, score_at_entry: g.punteggio,
        origin: 'auto', mode: g.modalita, phase: g.quale,
    };
    return dettaglioDi(riga, [], { gamba: g.quale });
}

function chiusuraDi(g: Gamba): PosizioneAperta['chiusura'] {
    // esposizione sui due esiti (stessa aritmetica di `tradeExposureNow`)
    const vinta = Math.round(g.size * (g.prezzo - 1) * 100) / 100;
    return {
        lato: g.lato === 'lay' ? 'back' : 'lay',
        prezzo: g.lato === 'lay' ? g.book.back : g.book.lay,
        abbinabile: g.abbinabile, bloccabile: g.bloccabile,
        // i dati del "se chiudo ora" al ms, con lo scanner come ripiego dichiarato
        alMs: {
            win: g.lato === 'back' ? vinta : -vinta,
            lose: g.lato === 'back' ? -g.size : g.size,
            marketId: g.marketId, selectionId: g.selectionId,
            sport: g.bot.startsWith('tennis_') ? 'tennis' : 'calcio',
            istanteScannerMs: ORA_MS - 1000,
            scanner: { back: g.book.back, backSize: g.abbinabile, lay: g.book.lay, laySize: Math.round(g.abbinabile * 0.9) },
            aliquota: 0.05,
        },
    };
}

const GAMBE: Gamba[] = [
    // MIKE, soldi veri: Under 3,5 in due ingressi + la copertura sull'Under 4,5
    {
        bot: 'mike', id: 9101, eventId: EV.inter, partita: INTER.nome, selezione: 'Under 3.5 Goals', lato: 'back',
        prezzo: 1.5, size: 40, modalita: 'live', piazzata: alle('07:11'), marketId: '1.248120013', selectionId: 1222347,
        quale: 'entry', book: { back: 1.22, lay: 1.23 }, abbinabile: 412, bloccabile: 8.34, minuto: null, punteggio: null,
        meta: { role: 'entry', cycle_no: 1 },
    },
    {
        bot: 'mike', id: 9102, eventId: EV.inter, partita: INTER.nome, selezione: 'Under 3.5 Goals', lato: 'back',
        prezzo: 1.32, size: 30, modalita: 'live', piazzata: alle('07:55'), marketId: '1.248120013', selectionId: 1222347,
        quale: 'second_entry', book: { back: 1.22, lay: 1.23 }, abbinabile: 412, bloccabile: 2.09, minuto: 30, punteggio: '0-0',
        meta: { role: 'second_entry', cycle_no: 1 },
    },
    {
        bot: 'mike', id: 9107, eventId: EV.inter, partita: INTER.nome, selezione: 'Under 4.5 Goals', lato: 'lay',
        prezzo: 1.1, size: 264, modalita: 'live', piazzata: alle('08:02'), marketId: '1.248120014', selectionId: 1222344,
        quale: 'over_cover', book: { back: 1.07, lay: 1.08 }, abbinabile: 1630, bloccabile: -7.4, minuto: 37, punteggio: '1-0',
        meta: { role: 'over_cover', cycle_no: 1 },
    },
    // OMEGA, in prova: banca lo 0-0 (risultato esatto), primo tempo
    {
        bot: 'omega', id: 5501, eventId: EV.inter, partita: INTER.nome, selezione: '0 - 0', lato: 'lay',
        prezzo: 8.4, size: 2, modalita: 'paper', piazzata: alle('07:20'), marketId: '1.248120012', selectionId: 1,
        quale: '1T', book: { back: 990, lay: 1000 }, abbinabile: 12.5, bloccabile: 1.88, minuto: null, punteggio: null,
        meta: { model: { raw: 0.083, calibrated: 0.079, applied: true } },
    },
    // SAFE, in prova: base (banca il pareggio) ed esatto (banca l'1-1)
    {
        bot: 'safe', id: 7301, eventId: EV.betis, partita: BETIS.nome, selezione: 'The Draw', lato: 'lay',
        prezzo: 3.3, size: 4, modalita: 'paper', piazzata: alle('08:20'), marketId: MO.betis, selectionId: 58805,
        quale: 'base', book: { back: 3.25, lay: 3.3 }, abbinabile: 212, bloccabile: 0.06, minuto: 13, punteggio: '0-0',
        meta: { strategy: 'base' },
    },
    {
        bot: 'safe', id: 7302, eventId: EV.betis, partita: BETIS.nome, selezione: '1 - 1', lato: 'lay',
        prezzo: 9.4, size: 2, modalita: 'paper', piazzata: alle('08:24'), marketId: '1.248120442', selectionId: 7,
        quale: 'esatto', book: { back: 10.5, lay: 11 }, abbinabile: 38, bloccabile: 0.19, minuto: 17, punteggio: '0-0',
        meta: { strategy: 'esatto' },
    },
    // TENNIS, in prova: Pro (due gambe) e Scalper
    {
        bot: 'tennis_pro', id: 880001, eventId: EV.sinner, partita: SINNER.nome, selezione: 'Jannik Sinner', lato: 'lay',
        prezzo: 1.22, size: 5, modalita: 'paper', piazzata: alle('07:58'), marketId: MO.sinner, selectionId: 9876501,
        quale: null, book: { back: 1.24, lay: 1.25 }, abbinabile: 1240, bloccabile: 0.08, minuto: null, punteggio: '1-0',
    },
    {
        bot: 'tennis_pro', id: 880002, eventId: EV.sinner, partita: SINNER.nome, selezione: 'Jack Draper', lato: 'back',
        prezzo: 5.4, size: 2, modalita: 'paper', piazzata: alle('08:05'), marketId: MO.sinner, selectionId: 9876502,
        quale: null, book: { back: 5, lay: 5.1 }, abbinabile: 310, bloccabile: 0.12, minuto: null, punteggio: '1-0',
    },
    {
        bot: 'tennis_scalper', id: 880010, eventId: EV.sinner, partita: SINNER.nome, selezione: 'Jannik Sinner', lato: 'back',
        prezzo: 1.27, size: 5, modalita: 'paper', piazzata: alle('08:31'), marketId: MO.sinner, selectionId: 9876501,
        quale: null, book: { back: 1.24, lay: 1.25 }, abbinabile: 1240, bloccabile: 0.08, minuto: null, punteggio: '1-0 \u00b7 2-1',
    },
];

const POSIZIONI: PosizioneAperta[] = GAMBE.map((g) => ({
    bot: g.bot, id: g.id, eventId: g.eventId, partita: g.partita, selezione: g.selezione, lato: g.lato,
    prezzo: g.prezzo, size: g.size, liability: liabilityDi(g), modalita: g.modalita, piazzataAt: g.piazzata,
    chiusura: chiusuraDi(g), ordine: ordineDi(g), dettaglio: dettaglioDiGamba(g),
    vivo: quotaViva(g.prezzo, g.lato, g.book),
}));

function operazioneDi(g: Gamba): OperazionePartita {
    return {
        bot: g.bot, id: g.id, selezione: g.selezione, lato: g.lato, prezzo: g.prezzo, size: g.size,
        stato: 'open', pnl: null, modalita: g.modalita, at: g.piazzata, quale: g.quale,
        ordine: ordineDi(g), dettaglio: dettaglioDiGamba(g), marketId: g.marketId, selectionId: g.selectionId,
        liability: liabilityDi(g), vivo: quotaViva(g.prezzo, g.lato, g.book), etaQuoteS: 1,
        chiusura: chiusuraDi(g), chiusureOrdini: [], eventId: g.eventId, chiudeId: null,
    };
}

const OPERAZIONI = new Map<string, OperazionePartita[]>();
for (const g of GAMBE) OPERAZIONI.set(g.eventId, [...(OPERAZIONI.get(g.eventId) ?? []), operazioneDi(g)]);

// ------------------------------------------------------------ posizioni chiuse

const RIGHE_CHIUSE: TradeChiudibile[] = [
    // Mike, soldi veri: Ulsan - Jeonbuk (K League, mattina), Under 3,5 chiuso in verde
    {
        __bot: 'mike', id: 9080, event_id: '34811920', event_name: 'Ulsan HD v Jeonbuk', sport: 'calcio', mode: 'live',
        status: 'won', pnl: 9.4, pnl_betfair: 9.4, pnl_betfair_settled_at: alle('07:58'), side: 'back', price: 1.58, size: 40,
        selection_name: 'Under 3.5 Goals', market_type: 'OVER_UNDER_35', market_id: '1.248119203', selection_id: 1222347,
        origin: 'auto', placed_at: alle('05:02'), settled_at: alle('07:58'), size_requested: 40, size_matched: 40,
        size_remaining: 0, avg_price_matched: 1.58, bet_id: '398112233001', giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true,
    },
    {
        __bot: 'mike', id: 9083, event_id: '34811920', event_name: 'Ulsan HD v Jeonbuk', sport: 'calcio', mode: 'live',
        status: 'lost', pnl: -1.28, pnl_betfair: -1.28, pnl_betfair_settled_at: alle('07:58'), side: 'lay', price: 1.1, size: 12.8,
        selection_name: 'Under 4.5 Goals', market_type: 'OVER_UNDER_45', market_id: '1.248119204', selection_id: 1222344,
        origin: 'auto', placed_at: alle('06:10'), settled_at: alle('07:58'), size_requested: 12.8, size_matched: 12.8,
        size_remaining: 0, avg_price_matched: 1.1, bet_id: '398112233007', closes_trade_id: 9080,
        giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true,
    },
    // in prova
    {
        __bot: 'omega', id: 5480, event_id: '34811944', event_name: 'Yokohama FM v Kashima', sport: 'calcio', mode: 'paper',
        status: 'won', pnl: 3.6, side: 'lay', price: 7.8, size: 2, runner_name: '0 - 0', phase: '1T',
        market_id: '1.248119441', selection_id: 1, origin: 'auto', placed_at: alle('05:10'), settled_at: alle('07:12'),
        giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true,
    },
    {
        __bot: 'safe', id: 7290, event_id: '34811960', event_name: 'Melbourne City v Sydney FC', sport: 'calcio', mode: 'paper',
        status: 'lost', pnl: -2.2, side: 'lay', price: 3.2, size: 1, selection_name: 'The Draw', strategy: 'base',
        market_id: '1.248119601', selection_id: 58805, origin: 'auto', placed_at: alle('06:20'), settled_at: alle('07:40'),
        giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true,
    },
    {
        __bot: 'tennis_pro', __senzaLegame: true, id: 879950, event_id: '34813480', event_name: 'Coco Gauff v Mirra Andreeva',
        sport: 'tennis', mode: 'paper', status: 'won', pnl: 1.1, side: 'back', price: 1.9, size: 2, selection_name: 'Coco Gauff',
        market_id: '1.248134801', selection_id: 9876433, origin: 'auto', placed_at: alle('05:40'), settled_at: alle('06:51'),
        giorno_partita: '2026-10-01', giorno_da: 'partita', in_day: true,
    },
];

const CHIUSE = posizioniChiuse(RIGHE_CHIUSE);

// ------------------------------------------------------------------- bot

function statoBot(over: Partial<StatoBot> & Pick<StatoBot, 'bot'>): StatoBot {
    return {
        modalita: 'paper', inCorsa: true, battitoAt: fa(2), canale: 'connected', etaPushS: 2, freschezzaPush: 'fresca',
        varianti: null, modiStrategia: null, stato: 'running', params: null, obiettivoGiorno: null,
        motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: true, fermatoAllAvvioAt: null,
        pnlOggi: null, pnlOggiPaper: null, fonteStato: 'canale', etaStatoS: 2,
        ...over,
    };
}

const PROPOSTA_PRO: PropostaFlusso = {
    chiave: 'tennis_pro|34813501|9876501', bot: 'tennis_pro', motivo: 'stop', urgente: true,
    eventId: EV.sinner, marketId: MO.sinner, selectionId: 9876501, latoIngresso: 'lay', prezzo: 1.26,
    latoChiusura: 'back', sizeChiusura: 5, seChiudi: -0.4, seVince: -1.1, sePerde: 5,
    frazione: 1, decidedAt: Math.round(ORA_MS / 1000) - 4,
};

const SAFE_PARAMS: Record<string, unknown> = {
    variants: ['base', 'esatto', 'tennis'],
    strategy_modes: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper', model: 'paper', manual: 'paper' },
    stake: { laySize: 2, backSize: 3, per_strategia: { base: 4, esatto: 2, punta: 3, tennis: 3 } },
    uscite_automatiche: { base: false, esatto: false, punta: true, tennis: true, model: true },
    tennis_exit_approval: true,
    daily_loss_stop: -20,
};

const BOTS: StatoBot[] = [
    statoBot({
        bot: 'omega', etaPushS: 3, battitoAt: fa(3), etaStatoS: 3, obiettivoGiorno: 12,
        params: { strategy_version: 3, min_stake: 2, v3_daily_loss_cap: 0, uscite_protezione: 'automatico' },
        pnlOggiPaper: 6.4, tettoPartite: 6, partiteEsposte: 1,
    }),
    statoBot({
        bot: 'safe', etaPushS: 1, battitoAt: fa(1), etaStatoS: 1,
        varianti: ['base', 'esatto', 'tennis'],
        modiStrategia: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper', model: 'paper', manual: 'paper' },
        params: SAFE_PARAMS,
        pnlOggiPerStrategia: {
            base: { live: null, paper: 3.1 }, esatto: { live: null, paper: -2.2 }, punta: { live: null, paper: null },
            tennis: { live: null, paper: 1.4 }, model: { live: null, paper: 0.9 }, manual: { live: null, paper: null },
        },
    }),
    statoBot({
        bot: 'mike', modalita: 'live', etaPushS: 1, battitoAt: fa(1), etaStatoS: 1,
        params: { stake: 40, daily_loss_stop: 30, uscite_automatiche: false, live_resting_enabled: true },
        pnlOggi: 8.12, fonteOggiLive: { fonte: 'conto', vuoto: false, etaS: 3 },
        tettoPartite: 4, partiteEsposte: 1,
    }),
    statoBot({
        bot: 'tennis_scalper', etaPushS: 6, battitoAt: fa(6), fonteStato: undefined, etaStatoS: undefined,
        params: { stake: 5 }, pnlOggiPaper: 2.05, usciteTennis: true, proposteUscite: [],
    }),
    statoBot({
        bot: 'tennis_pro', etaPushS: 6, battitoAt: fa(6), fonteStato: undefined, etaStatoS: undefined,
        params: { stake: 5 }, pnlOggiPaper: -0.8, usciteTennis: false, proposteUscite: [PROPOSTA_PRO],
    }),
    statoBot({
        bot: 'tennis_flb', inCorsa: false, stato: 'stopped', etaPushS: 6, battitoAt: fa(6),
        fonteStato: undefined, etaStatoS: undefined, params: { stake: 5 }, usciteTennis: true, proposteUscite: [],
    }),
    statoBot({
        bot: 'tennis_swing', inCorsa: false, stato: 'stopped', etaPushS: 6, battitoAt: fa(6),
        fonteStato: undefined, etaStatoS: undefined, params: { stake: 5 }, usciteTennis: true, proposteUscite: [],
    }),
    statoBot({
        bot: 'scalper', modalita: null, modalitaUltima: 'paper', inCorsa: false, stato: 'stopped', etaPushS: 4,
        battitoAt: fa(4), fonteStato: undefined, etaStatoS: undefined,
        params: { stake: 5, uscite_automatiche: true },
        nota: '0 sessioni attive \u00b7 dal database, giro dei 30 s, 4 s fa',
    }),
];

// ---------------------------------------------------------------- proposte

const PROPOSTA_SAFE: PropostaVista = {
    proposta: {
        id: 41207, kind: 'cashout', status: 'proposed', created_at: fa(40), updated_at: fa(2),
        payload: {
            trade_id: 7301, event_id: EV.betis, event_name: BETIS.nome, sport: 'calcio', strategy: 'base',
            selection_name: 'The Draw', market_id: MO.betis, selection_id: 58805, side: 'back', entry_side: 'lay',
            entry_price: 3.3, size: 4, size_requested: 4, size_matched: 4, size_remaining: 0, avg_price_matched: 3.3,
            price_at_decision: 3.3, size_available_at_decision: 190, locked_at_decision: 0, hold_profit: 4,
            loss_if_lose: -9.2, exit_kind: 'time', exit_reason: 'minuto limite della strategia', urgente: true,
            minute: 31, score: '0-0', mode: 'paper', feed_updated_at: fa(1), odds_ts_ms: ORA_MS - 1000,
            decided_at: fa(40), proposed_at: fa(2),
        },
    },
    vivo: { prezzo: 3.25, abbinabile: 212, statoMercato: 'OPEN' },
    etaQuoteS: 1,
    bloccabileOra: 0.06,
};

const PROPOSTA_OMEGA: PropostaUscitaOmega = {
    id: 63012, kind: 'omega_exit', created_at: fa(95), updated_at: fa(3),
    payload: {
        trade_id: 5501, event_id: EV.inter, event_name: INTER.nome, market_id: '1.248120012', market_type: 'CORRECT_SCORE',
        selection_id: 1, selection_name: '0 - 0', side: 'back', entry_side: 'lay', entry_price: 8.4, size: 2,
        price_at_decision: 990, size_available_at_decision: 12.5, motivo_codice: 'blocca_il_profitto',
        profitto_bloccabile: 1.88, back_price: 990, back_size: 0.02, ev_tenere: 1.6, p_evento: 0.002,
        meglio_aspettare: false, bloccabile_max_atteso: 1.9, minuto_del_massimo: 58, liability: 14.8, p_fonte: 'v3_lambda',
        minute: 58, score: '1-0', mode: 'paper', decided_at: fa(95), proposed_at: fa(3),
        commissione: 0.05, margine_attesa: 0.02, max_attesa: 1.9, p_lose_max: 0.05,
        valutazione: { valida: true, motivo_codice: 'blocca_il_profitto', testo: null, valutata_at: fa(3), dal: fa(95) },
    },
};

const VIVO_OMEGA: PrezzoVivo = { prezzo: 990, abbinabile: 12.5, statoMercato: 'OPEN' };

const OPPORTUNITA: PropostaOppVista = {
    proposta: {
        id: 41215, kind: 'model', status: 'proposed', created_at: fa(25), updated_at: fa(1),
        payload: {
            opp_key: 'model:34812044:ou25:under', strategy: 'model', kind: 'model', event_id: EV.betis,
            event_name: BETIS.nome, sport: 'calcio', market_id: '1.248120441', market_type: 'OVER_UNDER_25',
            selection_id: 47972, selection_name: 'Under 2.5 Goals', side: 'back', price: 1.6, size: 3, liability: 3,
            mode: 'paper', minute: 31, score: '0-0', signal_key: 'model_under25', price_at_decision: 1.6,
            size_available: 340, size_available_at_decision: 310, p_model: 0.679, p_implied: 0.633, edge: 0.046,
            ev: 0.14, confidence: 0.62, rationale: 'ritmo basso, xG cumulato 0,4 al 31\u2032', line: 2.5,
            odds_ts_ms: ORA_MS - 1000, feed_updated_at: fa(1), decided_at: fa(25), proposed_at: fa(1),
        },
    },
    abbinabileOra: 340,
    etaQuoteS: 1,
    prezzoVivoGamba: 1.58,
};

// ------------------------------------------------------------------ Mike

const MIKE_INTER: MikeEvent = {
    event_id: EV.inter, fixture_id: 1208833, event_name: INTER.nome, competition: 'Serie A', league_id: 135,
    ko_at: alle('07:25'), mode: 'live',
    markets: { OU35: { market_id: '1.248120013' }, OU45: { market_id: '1.248120014' } },
    state: 'LIVE_COVERED', cycle_no: 1, entry_price_initial: 1.5,
    dossier: { fixture_id: 1208833, league_id: 135, lambda_home: 1.45, lambda_away: 0.92, rho: -0.08, p4_pre: 0.27, p_under35_cal: 0.71, source: 'api_football' },
    live: {
        minute: 58, goals: 1, feed_age_s: 1, inplay: true, ht: false, score_home: 1, score_away: 0,
        liability: 96.4, locked: 3.02, total_matched: 1843210, p4_market: 0.18, p4_model: 0.15, hazard: 0.021,
        books: {
            'OU35|UNDER': { best_back: 1.22, back_size: 412, best_lay: 1.23, lay_size: 388, status: 'OPEN', inplay: true, bet_delay: 5 },
            'OU45|UNDER': { best_back: 1.07, back_size: 1630, best_lay: 1.08, lay_size: 1410, status: 'OPEN', inplay: true, bet_delay: 5 },
            'OU45|OVER': { best_back: 13.5, back_size: 120, best_lay: 14.5, lay_size: 96, status: 'OPEN', inplay: true, bet_delay: 5 },
        },
        cashout: { net: 3.02, gross: 3.57, base: 70, complete: true, pct: 4.3, commission: 0.05, target_pct: 12 },
        pnl_by_total: { '1': 13.1, '2': 13.1, '3': 13.1, '4': -14.6, '5': -70 },
        published_ts: ORA_MS / 1000 - 1, feed_fresh: true,
    },
    positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: fa(1),
};

const MIKE_BOLOGNA: MikeEvent = {
    event_id: EV.bologna, fixture_id: 1208840, event_name: BOLOGNA.nome, competition: 'Serie A', league_id: 135,
    ko_at: alle('08:52'), mode: 'live',
    markets: { OU35: { market_id: '1.248121023' }, OU45: { market_id: '1.248121024' } },
    state: 'WATCH', cycle_no: 0, entry_price_initial: null,
    dossier: { fixture_id: 1208840, league_id: 135, lambda_home: 1.31, lambda_away: 0.88, rho: -0.07, p4_pre: 0.22, p_under35_cal: 0.76, source: 'api_football' },
    live: null, positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: fa(4),
};

// ----------------------------------------------------------- soldi e prova

const CONTO = contoAdesso({
    riga: { available: 1842.37, exposure: -96.4, updated_at: fa(3) },
    canale: null, etaRunnerS: 1, nowMs: ORA_MS,
});
const RISCHIO_BOT = rischioBotLive({
    letti: true,
    stati: {
        mike: { aggregates: { mode: 'live', open_liability: 96.4, liability_stale: false } },
        omega: { aggregates_by_mode: { live: { open_liability: 0 }, paper: { open_liability: 14.8 } } },
        safe: { aggregates: { mode: 'paper', open_liability: 26 } },
    },
    aperte: POSIZIONI.map((p) => ({ bot: p.bot, modalita: p.modalita })),
});

const PROVA: ProvaGiornata = {
    voci: [
        { chiave: 'omega', etichetta: 'Omega', sport: 'calcio', oggi: { pnl: 6.4, operazioni: 3, vinte: 2, perse: 1, partite: 2 }, arretrati: [], nota: null },
        { chiave: 'mike', etichetta: 'Mike', sport: 'calcio', oggi: { pnl: 0, operazioni: 0, vinte: 0, perse: 0, partite: 0 }, arretrati: [], nota: null },
        {
            chiave: 'safe_calcio', etichetta: 'Safe calcio', sport: 'calcio',
            oggi: { pnl: 1.8, operazioni: 6, vinte: 4, perse: 2, partite: 3 },
            arretrati: [{ giorno: '2026-09-30', origine: 'fischio', pnl: 1.2, operazioni: 2, vinte: 2, perse: 0, partite: 2 }],
            nota: null,
        },
        {
            chiave: 'safe_tennis', etichetta: 'Safe tennis', sport: 'tennis',
            oggi: { pnl: 1.4, operazioni: 2, vinte: 2, perse: 0, partite: 1 }, arretrati: [], perRegolamento: true, nota: null,
        },
        {
            chiave: 'bot_tennis', etichetta: 'Bot tennis (Scalper \u00b7 Pro \u00b7 FLB \u00b7 Swing)', sport: 'tennis',
            oggi: { pnl: 1.25, operazioni: 2, vinte: 1, perse: 1, partite: 2 }, arretrati: [], perRegolamento: true, nota: null,
        },
    ],
    oggiPerSport: {
        calcio: { pnl: 8.2, operazioni: 9, vinte: 6, perse: 3, partite: 5 },
        tennis: { pnl: 2.65, operazioni: 4, vinte: 3, perse: 1, partite: 3 },
    },
    arretratiPerSport: {
        calcio: [{ giorno: '2026-09-30', origine: 'fischio', pnl: 1.2, operazioni: 2, vinte: 2, perse: 0, partite: 2 }],
        tennis: [],
    },
    arretratiNonLetti: { calcio: [], tennis: [] },
    perRegolamento: { calcio: [], tennis: ['Safe tennis', 'Bot tennis (Scalper \u00b7 Pro \u00b7 FLB \u00b7 Swing)'] },
};

const COMPOSIZIONE: ComposizioneConto = {
    righe: [
        { chiave: 'omega', etichetta: 'Omega', valore: null, fonte: 'bot' },
        { chiave: 'safe_calcio', etichetta: 'Safe calcio', valore: null, fonte: 'bot' },
        { chiave: 'safe_tennis', etichetta: 'Safe tennis', valore: null, fonte: 'bot' },
        { chiave: 'mike', etichetta: 'Mike', valore: 8.12, reale: 8.12, stimato: null, fonte: 'conto' },
        { chiave: 'scalper', etichetta: 'Scalper calcio', valore: null, fonte: 'bot' },
        { chiave: 'bot_tennis', etichetta: 'Bot tennis (Scalper \u00b7 Pro \u00b7 FLB \u00b7 Swing)', valore: null, fonte: 'bot' },
        { chiave: 'manuale', etichetta: 'Manuale (app + sito Betfair)', valore: 0, reale: 0, fonte: 'conto' },
        { chiave: 'manuale_sito', etichetta: 'Manuale \u00b7 sito Betfair', valore: 0, reale: 0, fonte: 'conto' },
        { chiave: 'manuale_app', etichetta: 'Manuale \u00b7 app', valore: 0, reale: 0, fonte: 'conto' },
        { chiave: 'altro', etichetta: 'Altro sul conto Betfair', valore: 0, reale: 0, fonte: 'conto' },
    ],
    totale: 8.12, provaPaper: 10.85, reale: 8.12, stimato: 0, dalConto: true,
};

const STATO_RISCHIO_CONTO = {
    id: 1, mode: 'live', day: '2026-10-01', realized: 8.12, open_mtm: 3.02, total: 11.14,
    limit_value: 50, stop_fired: false, detail: { reason: 'sotto_soglia' }, updated_at: fa(4),
};

// ------------------------------------------------------------------ il vm

function vmPopolato(): Vm {
    const bot = (b: Bot) => BOTS.find((x) => x.bot === b) ?? null;
    return {
        caricamento: false, errore: null, nowMs: ORA_MS,
        giornata: GIORNATA,
        totali: {
            letti: true,
            partite: 7, live: 3, pre: 4, conPosizione: 3, conPosizioneLive: 1,
            liability: 96.4, liabilityPaper: 48.9, netPnl: 8.12, netPnlPaper: 10.85,
        },
        obiettivo: 12, obiettivoStoricizzato: true, omegaLetto: true,
        realizzato: 8.12,
        realizzatoOggi: {
            tutto: { totale: 18.97, live: 8.12, paper: 10.85, perSport: { calcio: 16.32, tennis: 2.65, ignoto: null }, righe: 14, vinte: 10, perse: 4 },
            live: { totale: 8.12, live: 8.12, paper: null, perSport: { calcio: 8.12, tennis: null, ignoto: null }, righe: 1, vinte: 1, perse: 0 },
            paper: { totale: 10.85, live: null, paper: 10.85, perSport: { calcio: 8.2, tennis: 2.65, ignoto: null }, righe: 13, vinte: 9, perse: 4 },
        },
        soldiGiornata: {
            realizzato: 8.12, realizzatoReale: 8.12, realizzatoStimato: 0, fonteReale: 'conto', inCorso: null,
            realizzatoPaper: 10.85, discordanza: null,
            perBot: {
                omega: null, safe: null, mike: 8.12, scalper: null,
                tennis_scalper: null, tennis_pro: null, tennis_flb: null, tennis_swing: null,
            },
            liability: 96.4,
            perSport: { calcio: { n: 1, pnl: 8.12, won: 1, lost: 0 } },
            perSportPaper: { calcio: { n: 9, pnl: 8.2, won: 6, lost: 3 }, tennis: { n: 4, pnl: 2.65, won: 3, lost: 1 } },
            perSportConto: { calcio: { pnl: 8.12, ordini: 2 }, tennis: { pnl: 0, ordini: 0 } },
            operazioni: 1, vinte: 1, perse: 0, operazioniPaper: 13,
            notaContatori: null,
        },
        targetServizio: 4,
        composizioneOggi: COMPOSIZIONE,
        manualeSitoBetfair: {
            pnlOggi: 0, fonte: 'backend', netto: true, ordini: 0,
            app: { pnlOggi: 0, fonte: 'backend', netto: true, ordini: 0 }, esclusi: 0,
        },
        salvaObiettivo: nulla,
        provaGiornata: PROVA,
        contoLettoAt: fa(3),
        apertoAdesso: {
            netto: 3.02, partite: 1, nonCalcolabili: 0,
            perBot: { mike: { netto: 3.02, partite: 1, nonCalcolabili: 0 } },
            etaPrezziS: 1, calcolatoAlMs: ORA_MS,
        },
        bots: BOTS,
        posizioni: POSIZIONI,
        chiuse: CHIUSE,
        righeChiuse: RIGHE_CHIUSE,
        registrazioni: new Set<string>([EV.inter, EV.betis, EV.sinner]),
        copertura: { conDato: 2, senzaDato: 0, totale: 2, pct: 100 },
        freni: { daily_loss_stop: -20, loss_stop_active: false, daily_liability: 26, daily_liability_bot: 26, cap_solo_automatico: true },
        soldiVeri: {
            conto: CONTO, rischioBot: RISCHIO_BOT, etaBotS: 4,
            scarto: scartoContoBot(CONTO.esposizione, RISCHIO_BOT),
            partite: partiteConPosizione(POSIZIONI.map((p) => ({ eventId: p.eventId, modalita: p.modalita }))),
            programmaScanner: 7,
            ordiniFuori: { letto: true, n: 0, nomi: [], senzaPartita: 0, motivo: null },
        },
        stopPerdita: {
            conto: stopDelConto(STATO_RISCHIO_CONTO, ORA_MS),
            bot: stopDeiBot({
                safe: { modalita: 'paper', risk: { daily_loss_stop: -20, loss_stop_active: false } },
                mike: { modalita: 'live', params: bot('mike')?.params ?? null, stats: { daily_stop: false } },
                omega: { modalita: 'paper', params: bot('omega')?.params ?? null },
            }),
        },
        ordiniConto: raggruppaOrdiniConto([], fa(6)),
        runner: { ts: fa(1), mode: 'LIVE', ageS: 1, up: true, streaming: 3 },
        fonteRunner: { fonte: 'canale', etaS: 1 },
        runnerTennis: { ts: fa(2), mode: 'PAPER', ageS: 2, up: true, streaming: 1 },
        fonteRunnerTennis: { fonte: 'canale', etaS: 2 },
        fonteStatoScanner: 'canale',
        mikeRestingLive: true,
        mikeEventi: new Map<string, MikeEvent>([[EV.inter, MIKE_INTER], [EV.bologna, MIKE_BOLOGNA]]),
        schermo: { feedMs: 180, pushMs: 40, letturaMs: 1400, schermoMs: 1400 },
        ultimaCatena: {
            salti: [
                { id: 'segnale', nome: 'segnale', ms: 12, spiega: 'dal prezzo al segnale del bot', nostro: true, latenza: true },
                { id: 'decisione', nome: 'decisione', ms: 4, spiega: 'il bot decide di operare', nostro: true, latenza: true },
                { id: 'coda', nome: 'coda', ms: 150, spiega: 'la richiesta attraversa la coda ordini', nostro: true, latenza: true },
                { id: 'betfair', nome: 'Betfair', ms: 1020, spiega: 'Betfair accetta e abbina (ritardo in gioco)', nostro: false, latenza: true },
                { id: 'conferma', nome: 'conferma', ms: 60, spiega: 'la conferma torna alla pagina', nostro: true, latenza: true },
            ],
            trade: 9107, evento: EV.inter,
        },
        operazioni: OPERAZIONI,
        proposte: [PROPOSTA_SAFE],
        proposteOpportunita: [OPPORTUNITA],
        piazzaOpportunita: nulla, rifiutaOpportunita: nulla,
        avvisoOpportunita: null, esitiOpportunita: [],
        slippagePct: 2, setSlippagePct: () => { /* anteprima */ },
        approva: nulla, ignora: nulla, chiudi: nulla,
        statoChiusuraRiga: () => null,
        esitiOrdini: [], esitoOrdine: () => null, esitoChiusuraRiga: () => null, seguiClic: () => { /* anteprima */ },
        statoChiusura: () => ({ chiusa: false, fonte: null, marcatore: null }),
        cashOutEvento: nulla, riprendiEvento: nulla, eventiChiusiOmega: [],
        proposteOmega: [PROPOSTA_OMEGA],
        vivoOmegaScanner: new Map([[PROPOSTA_OMEGA.id, { vivo: VIVO_OMEGA, etaQuoteS: 1 }]]),
        erroreProposteOmega: null,
        approvaOmega: nulla, ignoraOmega: nulla,
        feedSorgente: 'stream', feedEtaS: 1, feedFreschezza: 'fresca',
        fonteScan: 'locale',
        fonteRighe: {
            omega: { fonte: 'locale', etaS: 3 },
            safe: { fonte: 'locale', etaS: 1 },
            mike: { fonte: 'locale', etaS: 1 },
            tennis: { fonte: 'locale', etaS: 6 },
        },
        etaRiga: () => ({ fonte: 'locale', etaS: 1 }),
        ricarica: () => { /* anteprima */ },
    };
}

/** UN modello di vista per tutta la vita della pagina: stessi oggetti a ogni
 *  render, come un hook vero che non riceve aggiornamenti. */
let VM: Vm | null = null;

export function useControlRoom(): Vm {
    VM ??= vmPopolato();
    return VM;
}
