// ============================================================================
// useControlRoom.ts — IL COLLEGAMENTO della Control Room ai tre bot.
//
// REGOLE CHE GOVERNANO QUESTO FILE, e che valgono più di qualunque comodità:
//
//  1. **Il socket è un'ACCELERAZIONE, mai l'unica fonte.** Tutto ciò che passa
//     dai canali locali (47333/47334/47335) è COMUNQUE scritto su Postgres. Se
//     un socket cade, i numeri non spariscono: si torna al database, più vecchi
//     di qualche secondo, mai assenti. Un P&L che diventa «—» perché è caduto
//     un WebSocket è peggio di un P&L in ritardo.
//  2. **Non si martella il database.** Il 13/09 il DB è andato giù per budget
//     IO esaurito. Qui: UNA lettura completa ogni `RICARICA_MS`, il feed delle
//     partite in realtime (push, non poll), e gli `stats` dai canali locali.
//  3. **Questa pagina non calcola segnali e non decide.** Legge quello che i
//     tre bot pubblicano. Ogni formula che esiste già altrove è una seconda
//     verità, e due verità sotto gli occhi del trader divergono sempre.
//  4. **Un'età assente è «non lo so», non zero.**
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    fetchScanRows, subscribeScanRows, fetchScanStatus, subscribeScanStatus, scanLocaleAccettabile,
    type ScanRow, type ScanStatusRow, type CalcioScanPayload, type ScanRowLocaleMsg,
} from '@/lib/safeStrategyScan';
import {
    fetchOmegaState, fetchOmegaTrades, fetchOmegaEvents,
    type OmegaState, type OmegaTrade, type OmegaStats, type OmegaEvent,
} from '@/lib/omega';
import {
    fetchSafeState, fetchRunnerState, tradeExposureNow,
    cashOutEvento as cashOutEventoSafe, riprendiEventoSafe,
    type SafeState, type SafeRiskStats, type RunnerState, type SafeTrade,
} from '@/lib/safeBot';
import {
    eventiChiusiDalleRighe, type StatoChiusuraEvento,
} from '@/lib/chiusuraUtente';
import {
    fetchProposteOmega, subscribeProposteOmega, approvaPropostaOmega,
    ignoraPropostaOmega, ordinaProposteOmega, type PropostaUscitaOmega,
} from '@/lib/omegaProposte';
import { hedgeSide, greenPrice, partialLockedPnl } from '@/components/trading/CashOutButton';
import { fetchMikeState, type MikeEvent, type MikeStateView, type MikeTrade } from '@/lib/mike';
import {
    mappaVuota, applicaBloccoDb, applicaMessaggioCanale, leggiMessaggioRiga,
    righeDi, etaRiga as etaRigaDi, ultimeNotizie,
    type MappaRighe, type FonteRiga,
} from '@/lib/righeCanale';
import { getLocalChannel, svegliaBot, type LocalStatus } from '@/lib/localChannel';
import {
    inviaChiusura, faseDaRichiesta, firmaRiga, cambiataPerChiusura, richiestaDaRileggere,
    statoConScadenza, LETTURA, type RigaDaChiudere, type StatoChiusuraRiga,
} from './chiudiRiga';
import { fetchMissions } from '@/lib/omegaMissions';
import {
    fetchTennisFollows, fetchTennisBotServices, fetchTennisBotDaily,
    fetchTennisBotOrdersToday,
    type TennisBotServiceRow, type TennisBotDailyRow, type TennisBotOrderRow,
    type TennisBotKey,
} from '@/lib/tennis';
import { fetchLiveFollows } from '@/lib/live';
import {
    posizioniChiuse, SOGLIA_PARI,
    type PosizioneChiusa, type TradeChiudibile,
} from '@/lib/posizioniChiuse';
import type { RigaOrdine } from '@/lib/statoOrdine';
import {
    dettaglioDi, eGambaDiChiusura, quotaViva,
    type DettaglioRiga, type QuotaViva, type RigaDettagliabile,
} from '@/components/controlroom/dettaglioRiga';
import {
    costruisciGiornata, soldiPerPartita, marca, marcaTennis, totaliGiornata, coperturaControllo,
    etaSecondi, freschezza, freschezzaBattito, realizzatoGiornata, arricchimentoDa,
    type ArricchimentoPartita, type RigaTennisPerSoldi,
    BOT_TENNIS, isBotTennis,
    type Bot, type GruppoCampionato, type TotaliGiornata, type Freschezza, type PartitaFeedLike, type Sport,
    type Realizzato, type RigaRealizzato,
} from '@/lib/controlRoom';
import { fmtMoney } from '@/lib/format';
import { romeDay, fetchSafeDaily, type DailyRow, type DailyBreakdown } from '@/lib/dailyHistory';
import { isSettled, isErrorRow, nettoCicloChiuso, type PnlTradeLike } from '@/lib/eventGroups';
import {
    catenaOperazione, catenaSchermo,
    type Salto, type CatenaSchermo, type TempiTrade, type EsecuzioneTrade,
} from '@/lib/controlRoomCatena';
import {
    fetchProposte, subscribeProposte, approvaProposta, ignoraProposta,
    prezzoVivo, ordinaProposte, SLIPPAGE_PCT_DEFAULT,
    type PropostaChiusura, type PrezzoVivo,
} from '@/lib/controlRoomProposte';
import {
    isPropostaOpportunita, approvaPropostaOpportunita,
    type PropostaOpportunita, type PrezziViviGambe,
} from '@/lib/safeBot';
import {
    componiObiettivo, righeRealizzatoPerCiclo,
    type ComposizioneObiettivo, type RigaComponente, type RigaTradeCiclo,
} from '@/lib/composizioneObiettivo';
import { leggiManualeSitoBetfair, type ManualeSitoBetfair } from '@/lib/manualeSitoBetfair';
import { prezzoVivoPerGamba } from '@/lib/comboPrezzoVivo';
import { updateOmegaParams } from '@/lib/omega';
import { applicaLottoScan, type ScanRowEvent } from '@/lib/scanEventBuffer';
import { fetchLiveAccount, subscribeLiveAccount, type LiveAccountRow } from '@/lib/liveOrders';

/** una proposta di OPPORTUNITA' con i numeri vivi che la scheda mostra */
export interface PropostaOppVista {
    proposta: PropostaOpportunita;
    /** importo abbinabile ORA sul lato da operare (dal feed), null = ignoto */
    abbinabileOra: number | null;
    /** eta' del prezzo in secondi, null = ignota (fail-closed) */
    etaQuoteS: number | null;
    /**
     * 18/09 — PREZZO VIVO PER GAMBA di una proposta COMBO (`payload.legs[]`,
     * contratto in arrivo da un altro costruttore). Calcolato dagli stessi
     * dati del feed scanner già in memoria (`lib/comboPrezzoVivo.ts`),
     * nessuna lettura nuova. `undefined` = la proposta non ha `legs` (il caso
     * di oggi, sempre): nessuna scheda esistente lo consuma ancora.
     */
    prezziGamba?: PrezzoVivo[];
    /**
     * 18/09 (raccordo) — LO STESSO prezzo vivo di una proposta A GAMBA SOLA
     * (`vivo.prezzo` sopra, riletto qui col nome che la scheda si aspetta):
     * è ESATTAMENTE il numero che `SchedaPropostaOpportunita` mostra in
     * grande e che PIAZZA manda all'approvazione. `null` = nessun prezzo
     * vivo trovato (mercato assente/sospeso, o proposta combo).
     */
    prezzoVivoGamba: number | null;
    /**
     * 18/09 (raccordo) — `prezziGamba` (sopra, array indicizzato per
     * posizione) RICONCILIATO nel tipo `PrezziViviGambe` (`lib/safeBot.ts`,
     * `Record<indice, prezzo>`) che la scheda/RPC si aspettano: UN
     * adattatore, non una seconda formula (nessun prezzo ricalcolato qui,
     * solo la stessa lista letta in un'altra forma). `undefined` = la
     * proposta non ha `legs`.
     */
    prezziViviGambe?: PrezziViviGambe;
}

/** L'adattatore fra i due tipi che F2 e la COMBO hanno dichiarato ciascuno
 *  per conto proprio (`PrezzoVivo[]` indicizzato per posizione vs
 *  `PrezziViviGambe` = `Record<indice, prezzo>`): stessa lista, stessa
 *  posizione, nessun secondo calcolo. */
function prezziViviGambeDa(prezziGamba: PrezzoVivo[] | undefined): PrezziViviGambe | undefined {
    if (!prezziGamba || !prezziGamba.length) return undefined;
    const out: PrezziViviGambe = {};
    prezziGamba.forEach((pv, i) => { out[i] = pv.prezzo; });
    return out;
}

/** UNA lettura completa ogni 30 s. Il resto arriva in push. */
export const RICARICA_MS = 30_000;

/**
 * I NOMI DELLE FONTI del giro di ricarica, **nell'ordine esatto** delle letture
 * di `Promise.allSettled`. Una lettura senza nome qui non spariva dal messaggio:
 * ci finiva come «undefined» (`['a','b'][14]` e' `undefined`, e `undefined !==
 * null` passa il filtro). Un guasto che si annuncia senza dire di che cosa e'
 * il guasto e' peggio di un guasto muto.
 *
 * Aggiungere una lettura SENZA aggiungere qui il suo nome fa comparire
 * «fonte #N»: e' il segnale, non un ripiego silenzioso.
 */
export const FONTI_RICARICA: readonly string[] = [
    'feed', 'stato feed', 'Omega', 'trade Omega', 'Safe', 'Mike', 'runner',
    'proposte di chiusura', 'giornata Safe (live)', 'giornata Safe (paper)',
    'campionati e loghi', 'missioni', 'registrazioni tennis',
    'registrazioni calcio',
    'servizi bot tennis', 'giornata bot tennis live',
    'giornata bot tennis paper', 'ordini bot tennis di oggi',
];
/** ritmo dell'orologio di pagina: le età devono crescere da sole */
const TICK_MS = 1_000;

// ------------------------------------------------------------------ modalità

export type Modalita = 'paper' | 'live';

export interface StatoBot {
    bot: Bot;
    /** la modalità la dichiara il SERVIZIO (riga di control), mai il browser */
    modalita: Modalita | null;
    inCorsa: boolean;
    battitoAt: string | null;
    /** stato del canale locale di questo bot */
    canale: LocalStatus;
    /** età dell'ultimo messaggio ricevuto dal canale; null = mai ricevuto */
    etaPushS: number | null;
    freschezzaPush: Freschezza;
    /**
     * Solo Safe: quali varianti possono APRIRE. Con il tennis in live e il
     * calcio in paper, scrivere «LIVE» e basta sarebbe fuorviante: la frase
     * vera è «LIVE · solo tennis».
     */
    varianti: string[] | null;
    /**
     * Solo Safe: **con che soldi** opera ciascuna strategia (`strategy_modes`).
     * NON è `varianti`: quella dice CHI PUÒ APRIRE, questa dice CON CHE SOLDI.
     * Confonderle scrive «LIVE» accanto al calcio mentre il calcio è in prova —
     * ed è successo.
     */
    modiStrategia: Record<string, 'paper' | 'live'> | null;

    /**
     * Lo stato ESATTO scritto dal servizio ('running', 'stopping', 'stopped',
     * 'idle', 'error'…). `inCorsa` è un sì/no e non basta al pannello di
     * comando: «stopping» e «stopped» vanno detti in modo diverso, e chi
     * preme un pulsante deve sapere se il servizio ha già recepito.
     */
    stato: string | null;
    /** i parametri grezzi dalla riga di control: il foglio parametri li vuole
     *  interi, comprese le chiavi che nessun tipo conosce */
    params: Record<string, unknown> | null;
    /** solo Omega: l'obiettivo del giorno vive fuori da `params` */
    obiettivoGiorno: number | null;

    /**
     * PERCHÉ il bot non sta aprendo, **dichiarato dal servizio**, non dedotto
     * qui (`stats.motivo_blocco`). null = nessun blocco in corso.
     *
     * ⚠️ 15/09 — il trader ha visto Mike «fermo» senza nessun motivo scritto da
     * nessuna parte: il tetto delle partite era pieno, e il tetto sommava paper
     * e live. Correggere il conto nel servizio non basta, se poi la pagina
     * continua a non dire niente.
     */
    motivoBlocco: string | null;
    /**
     * Il tetto delle partite e quante ne occupano un posto **nella modalità in
     * cui il bot sta operando**. Sono due conti separati, mai la somma: i soldi
     * finti non occupano il posto dei soldi veri.
     */
    tettoPartite: number | null;
    partiteEsposte: number | null;
    /**
     * FERMARE questo bot toglie le APERTURE, non le uscite: coperture,
     * green-up, cash-out e settlement continuano. Lo dichiara il servizio
     * (`stats.stop_ferma_solo_aperture`); il pulsante deve dirlo, o promette
     * una cosa che non fa.
     */
    stopFermaSoloAperture: boolean;
    /**
     * Quando questo bot è stato FERMATO ALL'AVVIO DELL'APP, dichiarato dal
     * servizio (`stats.fermato_all_avvio_at`). null = non è successo.
     *
     * «I bot li accendo solo io, in paper e in live. All'avvio dell'app nessun
     * bot opera.» Il servizio, al primo giro dopo un `APP_BOOT_ID` nuovo, si
     * porta a stopped/paper e scrive qui l'istante: senza, il trader vedrebbe
     * un bot spento senza sapere che a spegnerlo è stata la riapertura
     * dell'app, e lo crederebbe rotto. La pagina non lo deduce: se il servizio
     * non lo dichiara, non c'è.
     */
    fermatoAllAvvioAt: string | null;

    /**
     * IL P&L DI OGGI DI QUESTO BOT, nelle due modalita' TENUTE SEPARATE.
     *
     * Non si sommano mai: sono un numero vero e un'esercitazione. La riga
     * mostra quello della modalita' in cui il bot sta operando. `null` = niente
     * di regolato oggi, che non e' «0,00 €».
     *
     * Oggi lo dichiarano i quattro bot tennis (`get_tennis_bot_daily`, netto di
     * commissione); per Omega, Safe e Mike resta `null` qui e il loro conto sta
     * dove stava (`soldiGiornata`): due numeri per la stessa cosa sarebbero due
     * verita'.
     */
    pnlOggi: number | null;
    pnlOggiPaper: number | null;
}

// ------------------------------------------------ operazioni per partita

/** Una riga operativa su una partita, qualunque bot l'abbia fatta. Serve alla
 *  scheda: cliccando il simbolo del bot si vede **cosa ha fatto davvero**,
 *  non solo che «ha operato». */
export interface OperazionePartita {
    bot: Bot;
    id: number;
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    prezzo: number | null;
    size: number | null;
    stato: string;
    /** netto di commissione; null = non ancora regolata (≠ zero) */
    pnl: number | null;
    modalita: Modalita | null;
    at: string;
    /** strategia/gamba che l'ha prodotta, per capire QUALE regola ha operato */
    quale: string | null;
    /**
     * C.12b (16/09) — i campi grezzi dell'ORDINE. La Control Room mostrava
     * un solo `size` e nessun prezzo medio: alla domanda «abbinato tutto o in
     * parte?» non sapeva rispondere. A leggerli e' `lib/statoOrdine`.
     */
    ordine: RigaOrdine;
    /**
     * 17/09 — IL DETTAGLIO DELLA SCHEDA ORIGINALE (stato ricco, P&L vivo,
     * minuto/punteggio all'ingresso, green-up, modello). Calcolato dalle STESSE
     * funzioni delle pagine dei bot: `components/controlroom/dettaglioRiga.ts`.
     * `null` per i quattro bot tennis, le cui righe non portano questi campi.
     */
    dettaglio: DettaglioRiga | null;
    /**
     * 18/09 (raccordo, R1) — `market_id`/`selection_id` della riga, quando il
     * bot li pubblica (Omega/Safe/i 4 bot tennis con le loro chiavi vere;
     * Mike NON li ha per riga — dichiarato, `null`). Servono a calcolare la
     * quota di adesso e "se chiudo ora" con le STESSE `prezzoVivo()`/
     * `chiusuraViva()` già usate per `PosizioneAperta`: nessuna seconda formula.
     */
    marketId: string | null;
    selectionId: number | null;
    /** responsabilità di QUESTA riga (colonna quando c'è; aritmetica pura per
     *  il tennis, v. `liabilityTennis`). */
    liability: number | null;
    /**
     * 18/09 (raccordo, R1) — quota d'ingresso vs quota di ADESSO sullo stesso
     * lato, con i tick di distanza dall'ingresso: STESSA `quotaViva()` già
     * usata da `PosizioneAperta.vivo`. `null` = nessun prezzo vivo trovato
     * (Mike, o mercato/selezione assenti dal feed).
     */
    vivo: QuotaViva | null;
    /** età del prezzo su cui si basa `vivo`, in secondi: STESSA `etaSecondi()`
     *  già usata per `PartitaGiornata.etaFeedS`/le proposte di chiusura. */
    etaQuoteS: number | null;
    /**
     * 18/09 (raccordo, R1) — quanto varrebbe chiudere questa posizione ADESSO,
     * per intero: STESSA `chiusuraViva()` già usata per `PosizioneAperta.
     * chiusura` ("se chiudo ora"). `null`/prezzo assente per Mike o quando il
     * feed non porta quella selezione.
     */
    chiusura: PosizioneAperta['chiusura'];
    /**
     * 18/09 (raccordo, R3) — le righe GREZZE (`RigaOrdine`) delle chiusure
     * collegate (`closes_trade_id`), nello stesso ordine di `dettaglio.
     * chiusure` ma nel formato che `StrisciaEsitoChiusura`/`certezzaChiusura`
     * si aspettano (chiesto/abbinato/residuo/prezzo medio, non il riassunto
     * già tradotto). Vuoto per i 4 bot tennis (nessuna catena di chiusura).
     */
    chiusureOrdini: RigaOrdine[];
    /**
     * B16 (24/09) — la PARTITA della riga e la sua apertura se e' una gamba di
     * chiusura orfana (`closes_trade_id`). Servono al «Chiudi» per bot: Mike
     * chiude per partita, e una gamba di chiusura non si chiude a sua volta.
     * Opzionali: assenti sulle righe costruite a mano (test storici).
     */
    eventId?: string;
    chiudeId?: number | null;
}

// ------------------------------------------------------------- posizioni

export interface PosizioneAperta {
    bot: Bot;
    id: number;
    eventId: string;
    partita: string;
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    prezzo: number | null;
    size: number | null;
    liability: number | null;
    modalita: Modalita | null;
    piazzataAt: string;
    /**
     * QUANTO VALE CHIUDERE ADESSO. Il bot propone un'uscita **solo quando la
     * regola del manuale scatta** — e fa bene. Ma una posizione può essere in
     * profitto molto prima, e il trader deve **vederlo in continuo** invece di
     * scoprirlo per caso. Questo non cambia la strategia: la mostra.
     *
     * La matematica è quella condivisa di `CashOutButton` (specchio del
     * `trading/greenup.py` del backend): qui non si ricalcola niente.
     */
    chiusura: {
        /** lato dell'ordine di copertura */
        lato: 'back' | 'lay';
        /** prezzo corrente a cui si chiuderebbe; null = non chiudibile ora */
        prezzo: number | null;
        /** EUR abbinabili a quel prezzo */
        abbinabile: number | null;
        /** P&L GARANTITO chiudendo per intero adesso; null = non calcolabile */
        bloccabile: number | null;
    } | null;
    /**
     * 17/09 — LO STATO DELL'ORDINE anche qui. La riga della colonna posizioni
     * mostrava un solo `size` (che dopo la conferma è l'ABBINATO): «chiesto
     * quanto? abbinato tutto? a che prezzo medio?» era leggibile solo aprendo
     * la scheda della partita. Sono gli stessi tre numeri, dalla stessa riga.
     */
    ordine: RigaOrdine;
    /** 17/09 — il dettaglio della scheda originale (v. `OperazionePartita`) */
    dettaglio: DettaglioRiga | null;
    /**
     * 17/09 — QUOTA DI ADESSO sulla stessa selezione, dal feed di scansione
     * già caricato per le partite: back, lay e i tick di movimento
     * dall'ingresso. `null` quando il feed non porta quella selezione (Mike non
     * pubblica `market_id`/`selection_id` sulle righe: per lui resta `null`).
     */
    vivo: QuotaViva | null;
}

/** Una riga è «a mercato» se non è regolata e non è un piazzamento mai
 *  avvenuto. `error` NON è un'operazione: non conta in nessun numero. */
function aMercato(t: { status: string }): boolean {
    return !isSettled(t.status) && !isErrorRow(t.status);
}

/**
 * 17/09 — LE CHIUSURE COLLEGATE a ogni apertura (`closes_trade_id`).
 * `legPnl` ne ha bisogno per dire «bloccato»: senza, una posizione già coperta
 * resterebbe «aperta» per sempre. È lo stesso legame che `groupTradesByMatch`
 * costruisce per la tabella di Omega — qui basta la mappa.
 */
function chiusureCollegate<T extends { id: number; closes_trade_id?: number | null }>(
    righe: readonly T[],
): Map<number, T[]> {
    const m = new Map<number, T[]>();
    const perId = new Map<number, T>();
    for (const r of righe) perId.set(Number(r.id), r);
    for (const r of righe) {
        const p = r.closes_trade_id;
        if (p == null) continue;
        // 23/09 - si risale alla RADICE presente (catena A <- B <- C): la terza
        // gamba sta sotto l'apertura, non sotto una chiusura che non e' una riga.
        let k = Number(p);
        const visti = new Set<number>([Number(r.id), k]);
        for (;;) {
            const padre = perId.get(k);
            const su = padre?.closes_trade_id;
            if (padre == null || su == null || visti.has(Number(su)) || !perId.has(Number(su))) break;
            k = Number(su);
            visti.add(k);
        }
        const a = m.get(k);
        if (a) a.push(r); else m.set(k, [r]);
    }
    return m;
}

/**
 * 23/09 - UNA GAMBA DI CHIUSURA NON E' UN'OPERAZIONE PROPRIA quando la sua
 * apertura e' fra le righe lette: vive annidata sotto di lei (`dettaglio.
 * chiusure`, `chiusureOrdini`) e il suo P&L entra nel netto del ciclo. Resta
 * una riga sua SOLO se ORFANA (apertura fuori dal set): euro veri, mai nascosti.
 */
function chiusuraConApertura<T extends { id: number; closes_trade_id?: number | null }>(
    t: T, ids: ReadonlySet<number>,
): boolean {
    return t.closes_trade_id != null && ids.has(Number(t.closes_trade_id));
}

/** I campi grezzi dell'ORDINE di una riga: gli stessi tre numeri che leggono
 *  Omega, Safe, Mike e la scheda partita (`lib/statoOrdine`). */
function ordineDi(t: {
    status: string; side?: string | null; price?: number | null; size?: number | null;
    size_requested?: number | null; size_matched?: number | null;
    size_remaining?: number | null; avg_price_matched?: number | null;
    betfair_updated_at?: string | null; meta?: Record<string, unknown> | null;
}): RigaOrdine {
    return {
        status: t.status, side: t.side ?? null,
        price: t.price ?? null, size: t.size ?? null,
        size_requested: t.size_requested ?? null,
        size_matched: t.size_matched ?? null,
        size_remaining: t.size_remaining ?? null,
        avg_price_matched: t.avg_price_matched ?? null,
        betfair_updated_at: t.betfair_updated_at ?? null,
        meta: t.meta ?? null,
    };
}

/**
 * LA RESPONSABILITÀ di un ordine tennis, calcolata dalla riga.
 *
 * `tennis_live_orders` non ha una colonna di responsabilità. Non è un dato che
 * manca: è l'aritmetica dell'exchange, la stessa che il design system usa
 * ovunque — su un BACK si rischia lo stake, su un LAY `(quota − 1) × stake`.
 * Senza prezzo o senza importo resta `null`: mai uno zero inventato.
 */
export function liabilityTennis(
    o: { side?: string | null; price?: number | null; size?: number | null },
): number | null {
    const size = typeof o.size === 'number' && Number.isFinite(o.size) ? o.size : null;
    if (size == null) return null;
    const lato = latoDi(o.side);
    if (lato === 'back') return Math.round(size * 100) / 100;
    if (lato !== 'lay') return null;
    const price = typeof o.price === 'number' && Number.isFinite(o.price) ? o.price : null;
    if (price == null || price <= 1) return null;
    return Math.round((price - 1) * size * 100) / 100;
}

/**
 * 18/09 (raccordo) — CHIAVE COMPOSTA bot+id, per `soldiPerPartita()`.
 *
 * `groupTradesIntoCicli` (`lib/eventGroups.ts`) raggruppa apertura↔chiusura
 * con un `Map<number, T>` GLOBALE sull'`id` grezzo: `omega_trades`,
 * `safe_strategy_trades`, `mike_trades` e `tennis_live_orders` hanno
 * sequenze PK **indipendenti**, quindi un id numerico che coincide fra due
 * tabelle diverse farebbe agganciare la chiusura del bot sbagliato come se
 * chiudesse un'altra posizione — rischio segnalato dal checkpoint F3 (§
 * "richieste fuori perimetro #1"). L'offset (1 miliardo per bot) e' enorme
 * rispetto a qualunque PK reale e NON cambia il raggruppamento apertura→
 * chiusura DENTRO lo stesso bot (stesso offset su entrambe le righe): serve
 * solo a impedire la collisione FRA bot diversi. Effetto contenuto: l'id
 * modificato qui vive SOLO dentro `soldiPerPartita` (che non lo espone,
 * `PartitaSoldi` non porta `id`), non nel resto della pagina.
 */
const OFFSET_BOT: Record<Bot, number> = {
    omega: 0, safe: 1_000_000_000, mike: 2_000_000_000,
    tennis_scalper: 3_000_000_000, tennis_pro: 4_000_000_000,
    tennis_flb: 5_000_000_000, tennis_swing: 6_000_000_000,
};

function chiaviComposte<T extends { id: number; closes_trade_id?: number | null }>(
    righe: readonly T[], bot: Bot,
): T[] {
    const off = OFFSET_BOT[bot];
    return righe.map((r) => ({
        ...r,
        id: r.id + off,
        closes_trade_id: r.closes_trade_id == null ? r.closes_trade_id : r.closes_trade_id + off,
    }));
}

// ------------------------------------------ C6 b: righe per riga dal canale

/** Una riga di posizione di Omega/Safe/Mike (la riga della SUA tabella). */
type RigaPosizioneBot = OmegaTrade | SafeTrade | MikeTrade;
/** Una proposta di Safe (`safe_strategy_requests`) o di Omega (`get_omega_proposte`). */
type RigaPropostaBot = PropostaChiusura | PropostaUscitaOmega;

/**
 * Una proposta e' ancora da mostrare? Le letture del database portano SOLO le
 * 'proposed' (Safe: filtro della SELECT; Omega: la RPC non porta nemmeno la
 * colonna `status`). Un messaggio del canale porta invece la riga intera, e
 * una proposta decaduta ('rejected') o approvata ('pending') deve sparire.
 */
function propostaViva(p: RigaPropostaBot): boolean {
    const st = (p as { status?: unknown }).status;
    return st === undefined || st === null || st === 'proposed';
}

/**
 * I topic per riga dei tre canali dei bot, copiati da
 * `Betfair/stream/canale_bot.py` (`TOPIC`). Safe ha DUE topic di posizione:
 * lo sport della riga deve coincidere con quello del topic (fail-closed).
 */
const TOPIC_POSIZIONI: readonly { bot: 'omega' | 'safe' | 'mike'; topic: string; sport?: 'calcio' | 'tennis' }[] = [
    { bot: 'omega', topic: 'omega_posizioni' },
    { bot: 'safe', topic: 'safe_posizioni_calcio', sport: 'calcio' },
    { bot: 'safe', topic: 'safe_posizioni_tennis', sport: 'tennis' },
    { bot: 'mike', topic: 'mike_posizioni' },
];
const TOPIC_PROPOSTE: readonly { bot: 'omega' | 'safe'; topic: string }[] = [
    { bot: 'omega', topic: 'omega_proposta' },
    { bot: 'safe', topic: 'safe_proposta' },
];

/** Una proposta con accanto il presente: prezzo e liquidità di ADESSO. */
export interface PropostaVista {
    proposta: PropostaChiusura;
    vivo: PrezzoVivo;
    /** età del prezzo su cui si piazzerebbe; null = non lo sappiamo */
    etaQuoteS: number | null;
    /**
     * Quanto si blocca chiudendo ADESSO, al prezzo corrente.
     *
     * ⚠️ REVIEW 15/09 — la scheda mostrava `locked_at_decision`, cioè il
     * valore calcolato dal bot alla FOTOGRAFIA, sotto l'etichetta «Chiudere
     * adesso». Nella colonna delle posizioni, nella stessa pagina, la stessa
     * posizione mostrava il valore vivo: due numeri diversi per la stessa
     * cosa. `null` = prezzo corrente o trade non disponibili, mai zero.
     */
    bloccabileOra: number | null;
}

// ------------------------------------------------------------------ il modello

export interface ControlRoomVM {
    caricamento: boolean;
    errore: string | null;
    /** istante di riferimento della pagina: un solo orologio per tutti i calcoli */
    nowMs: number;

    giornata: GruppoCampionato[];
    totali: TotaliGiornata;

    /** obiettivo del giorno: quello storicizzato di Omega, che è l'unico che esiste */
    obiettivo: number | null;
    obiettivoStoricizzato: boolean;
    realizzato: number | null;
    /**
     * IL REALIZZATO DI OGGI, diviso come serve davvero: **live e paper mai
     * sommati in un numero solo**, e diviso **per sport** — perché con il
     * tennis in live e il calcio in paper, «quanto ho guadagnato col tennis»
     * senza la divisione non ha risposta.
     *
     * È questo che fa muovere la barra quando una posizione si chiude: prima
     * leggeva solo il realizzato di OMEGA, quindi una vincita del tennis (che
     * è di Safe) non la spostava di un pixel.
     *
     * Tre conti sulle STESSE righe dei tre bot. Chi legge deve SCEGLIERE:
     * `live` sono soldi veri, `paper` è esercitazione, `tutto` è la somma delle
     * due e serve solo alle diagnosi — non si mostra mai a un trader.
     */
    realizzatoOggi: { tutto: Realizzato; live: Realizzato; paper: Realizzato };

    /**
     * IL REALIZZATO CHE FA MUOVERE LA BARRA — e **sono soldi veri, solo quelli**.
     *
     * Storia di due errori, entrambi visti a schermo:
     *  1. leggeva `realized_today` del solo OMEGA: una vincita del tennis (che
     *     è di Safe) non muoveva la barra per costruzione;
     *  2. poi sommava i tre servizi — ma ciascuno pubblica il realizzato NELLA
     *     PROPRIA modalità (`bot_service.py:5445`). Con Safe in live e gli
     *     altri due in prova, la somma metteva insieme un numero vero e due
     *     simulati: il 14/09 la barra diceva −4,83 € mentre il tennis con soldi
     *     veri aveva fatto +0,41 €, e andava all'indietro per perdite finte.
     */
    soldiGiornata: {
        /** SOLDI VERI realizzati oggi dai tre bot. È il numero della barra. */
        realizzato: number | null;
        /** lo stesso conto in PROVA, tenuto separato e mai sommato */
        realizzatoPaper: number | null;
        /** server e pagina non concordano sul realizzato live: si dichiara */
        discordanza: string | null;
        perBot: Record<Bot, number | null>;
        /** responsabilità aperta, sommata */
        liability: number | null;
        /** P&L per SPORT con i SOLDI VERI (`get_safe_daily` con `p_mode='live'`) */
        perSport: Record<string, DailyBreakdown> | null;
        /** P&L per SPORT in PROVA. Mai sommato al precedente. */
        perSportPaper: Record<string, DailyBreakdown> | null;
        operazioni: number | null;
        vinte: number | null;
        perse: number | null;
        operazioniPaper: number | null;
        /**
         * 18/09 (raccordo, R5) — dichiarazione onesta quando i contatori
         * V/P NON contano una o più fonti operazione per operazione (oggi:
         * le due voci manuali sito/app, un aggregato-giornata senza un
         * esito per singola giocata dal backend). `null` = nessuna
         * dichiarazione dovuta. I 4 bot tennis NON compaiono qui: la RPC
         * `get_tennis_bot_daily` porta `vinti`/`persi` REALI, quindi contano
         * per intero nei contatori sopra.
         */
        notaContatori: string | null;
    };
    /** target per partita calcolato dal SERVIZIO (Omega). Se manca, la pagina lo dichiara. */
    targetServizio: number | null;

    /**
     * 18/09 — SCOMPOSIZIONE dell'obiettivo (Task 2): Omega · Safe calcio ·
     * Safe tennis · Mike · bot tennis · manuale, SOLO soldi veri. Costruita
     * con `lib/composizioneObiettivo.ts` sulle STESSE righe già lette per
     * `realizzatoOggi`: nessuna lettura nuova.
     */
    composizioneOggi: ComposizioneObiettivo;
    /** punto d'aggancio isolato per le scommesse manuali dal SITO Betfair
     *  (fuori app): oggi sempre "non disponibile" (`lib/manualeSitoBetfair.ts`). */
    manualeSitoBetfair: ManualeSitoBetfair;
    /**
     * Salva l'obiettivo di oggi (`omega_update_params({ dailyGoal })`, RPC
     * già pronta): NON tocca `params`/`mode` di Omega (la RPC fa `coalesce`
     * per ciascuno, verificato in `migrations/omega_daily_v2.sql:107-113`).
     */
    salvaObiettivo: (valore: number) => Promise<void>;

    bots: StatoBot[];
    posizioni: PosizioneAperta[];
    /** posizioni GIA' CHIUSE: apertura + coperture, con il P&L della posizione
     *  intera. Le gambe di copertura non sono posizioni proprie. */
    chiuse: PosizioneChiusa[];
    /** event_id delle partite che stanno REGISTRANDO adesso */
    registrazioni: Set<string>;

    /** copertura del dato di «controllo del gioco» sulle partite di oggi */
    copertura: { conDato: number; senzaDato: number; totale: number; pct: number | null };

    /**
     * I FRENI di Safe. L'utente ha spento i cap («nessun cap alle operazioni»),
     * quindi lo stop di perdita giornaliera è l'ULTIMO freno rimasto: deve
     * stare in testata, sotto gli occhi, non dentro un pannello. Assente si
     * scrive assente — non zero.
     */
    freni: SafeRiskStats | null;

    /**
     * Stato del runner flumine. 14/09 — il battito diceva «2 settembre» mentre
     * il processo girava: `heartbeat_worker` vive dentro il framework e non
     * parte finché il runner è parcheggiato in attesa di eventi. Ora il runner
     * batte anche da fermo, quindi **battito fresco = processo vivo**, che è
     * l'unica cosa che un battito dovrebbe voler dire.
     */
    runner: RunnerState | null;

    /**
     * 🔴 L'UNICO INTERRUTTORE che può far divergere demo e live su Mike.
     * `live_resting_enabled = false` → in live l'uscita torna «taker» e Mike
     * esegue una strategia DIVERSA da quella provata in paper. Quando è spento
     * va gridato in testata, non sepolto in un pannello.
     */
    mikeRestingLive: boolean | null;

    /**
     * 17/09 — LE PARTITE DI MIKE come il servizio le pubblica, per `event_id`.
     * È lo STESSO `fetchMikeState()` già letto per i trade: nessuna lettura in
     * più. Serve alla scheda della partita per mostrare il modello (P(4 gol),
     * gol attesi, quote delle due linee, cicli, cash out) come fa la sua pagina.
     */
    mikeEventi: Map<string, MikeEvent>;

    /**
     * LE PROPOSTE DI CHIUSURA che aspettano il sì, le urgenti in cima.
     * Ognuna porta con sé il PREZZO VIVO preso dal feed — non quello congelato
     * nella proposta — e l'età di quel prezzo.
     */
    /**
     * LA CATENA FINO ALLO SCHERMO: quanto è vecchio quello che il trader sta
     * guardando ADESSO. Si prende il peggiore dei tre canali (feed · spinta dal
     * bot · ultima lettura dal database), non il migliore: la pagina è vecchia
     * quanto il suo pezzo più vecchio.
     */
    schermo: CatenaSchermo;
    /** la catena dell'ULTIMA operazione: da Betfair al fill, salto per salto */
    ultimaCatena: { salti: Salto[]; trade: number | null; evento: string | null };

    /** operazioni per partita: la scheda le apre al clic sul simbolo del bot */
    operazioni: Map<string, OperazionePartita[]>;

    proposte: PropostaVista[];
    /**
     * 17/09 — LE OPPORTUNITA' DI MODELLO SONO PROPOSTE, non ordini.
     * Vivono nella STESSA coda delle chiusure (`safe_strategy_requests`,
     * 'proposed') e si riconoscono da `payload.opp_key`: qui si separano, o la
     * scheda della chiusura proverebbe a leggerle come un'uscita (e mostrerebbe
     * numeri di un'altra cosa).
     */
    proposteOpportunita: PropostaOppVista[];
    /**
     * 18/09 (raccordo, R2) — PIAZZA manda ESATTAMENTE il prezzo che la scheda
     * sta mostrando in quell'istante (`SchedaPropostaOpportunita.onPiazza`),
     * non quello congelato nella proposta: `approvaPropostaOpportunita`
     * (`lib/safeBot.ts`) lo inoltra alla RPC `safe_request_approve` coi nuovi
     * parametri opzionali. Retrocompatibile: se la migrazione che li accetta
     * non è applicata, un SOLO ripiego automatico sul solo `p_id` (mai una
     * doppia approvazione), con `avvisoOpportunita` che lo dichiara.
     */
    piazzaOpportunita: (
        id: number, prezzoVisto?: number, legsPricesVisti?: PrezziViviGambe, slippagePct?: number,
    ) => Promise<void>;
    rifiutaOpportunita: (id: number) => Promise<void>;
    /** avviso onesto quando PIAZZA è dovuto ripiegare sul solo `p_id`
     *  (migrazione del prezzo visto non applicata): null = nessun ripiego. */
    avvisoOpportunita: string | null;
    slippagePct: number;
    setSlippagePct: (v: number) => void;
    approva: (id: number) => Promise<void>;
    ignora: (id: number) => Promise<void>;
    /** chiusura MANUALE di una posizione, per intero: accoda una richiesta
     *  `cashout` sulla coda DEL BOT DELLA RIGA (B16, 24/09: prima andava a
     *  Safe per qualunque bot). Non passa dal cancelletto — una chiusura
     *  decisa dall'operatore non ha bisogno di essere approvata da lui stesso. */
    chiudi: (riga: RigaDaChiudere) => Promise<void>;
    /** B16 — l'esito del «Chiudi» di una riga (inviata / presa in carico /
     *  eseguita / rifiutata col motivo), `null` = nessun clic su questa riga. */
    statoChiusuraRiga: (bot: Bot, id: number) => StatoChiusuraRiga | null;

    /**
     * «SE CHIUDO IO, IL BOT DEVE SAPERLO» (ordine dell'utente, 16/09 sera).
     * `statoChiusura` dice se una partita e' marcata «chiusa da te» e da che
     * cosa lo sappiamo; i due gesti accodano `cashout_event` e
     * `riprendi_evento` sulla coda richieste di sempre.
     */
    statoChiusura: (eventId: string) => StatoChiusuraEvento;
    cashOutEvento: (eventId: string) => Promise<void>;
    riprendiEvento: (eventId: string) => Promise<void>;
    /** event_id che OMEGA dichiara chiusi dall'utente (`stats`) */
    eventiChiusiOmega: string[];

    /**
     * LE PROPOSTE DI USCITA DI OMEGA (16/09). In v3 nessuna chiusura parte da
     * sola: il servizio scrive una riga `proposed` e aspetta. `erroreProposteOmega`
     * dice PERCHE' l'elenco e' vuoto quando lo e' per un guasto (tipicamente:
     * migrazione `omega_proposte_uscita_2026-09-16.sql` non applicata).
     */
    proposteOmega: PropostaUscitaOmega[];
    erroreProposteOmega: string | null;
    approvaOmega: (id: number) => Promise<void>;
    ignoraOmega: (id: number) => Promise<void>;

    /** sorgente del feed: fra `stream` e `rest` c'è un ordine di grandezza */
    feedSorgente: string | null;
    feedEtaS: number | null;
    feedFreschezza: Freschezza;
    /**
     * STADIO B2c (18/09, raccordo) — «canale locale» quando l'ultimo
     * messaggio scanner accettato dal canale 47336 è FRESCO (stessa soglia
     * `freschezza()` di tutta la pagina), altrimenti «database» (poll dei
     * 30 s / Supabase realtime, come oggi). Oggi il canale è muto: resta
     * sempre «database», nessuna differenza a schermo.
     */
    fonteScan: 'locale' | 'database';
    /**
     * C6 b (23/09) - per Omega, Safe e Mike: da dove arriva ADESSO l'ultima
     * notizia sulle loro righe (posizioni e proposte) e quanti secondi ha.
     * "locale" = un messaggio per riga del canale, piu' fresco dell'ultima
     * lettura del database, sta sovrapponendo almeno una riga; altrimenti
     * "database" con l'eta' dell'ultima lettura. `etaS` null = mai letto.
     * Con i canali muti (interruttori `*_CANALE_POSIZIONI` spenti) resta
     * sempre "database".
     */
    fonteRighe: Record<'omega' | 'safe' | 'mike', { fonte: FonteRiga; etaS: number | null }>;
    /**
     * C6 b - eta' e fonte di UNA posizione (chiave bot+id). `null` = riga
     * sconosciuta alla mappa (mai letta dal database).
     */
    etaRiga: (bot: 'omega' | 'safe' | 'mike', id: number) => { fonte: FonteRiga; etaS: number } | null;

    ricarica: () => void;
}

export function useControlRoom(): ControlRoomVM {
    const [scan, setScan] = useState<ScanRow[]>([]);
    // specchio SINCRONO dell'ultimo `scan` per il confronto «vince il più
    // recente» dei messaggi del canale locale scanner (v. sotto): un `useState`
    // letto dentro una callback resterebbe alla chiusura del render in cui la
    // callback è stata creata, non all'ultimo commit.
    const scanRef = useRef<ScanRow[]>(scan);
    useEffect(() => { scanRef.current = scan; }, [scan]);
    // istante dell'ultimo messaggio scanner ACCETTATO dal canale locale
    // 47336 (v. `fonteScan` nel VM): `null` finché il canale non parla.
    const [ultimoScanLocaleMs, setUltimoScanLocaleMs] = useState<number | null>(null);
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [omega, setOmega] = useState<OmegaState | null>(null);
    // C6 b (23/09) - LE RIGHE DEI BOT IN UNA MAPPA PER RIGA (`lib/righeCanale.ts`),
    // chiave composta bot+id. La alimentano i blocchi del database (come prima,
    // stesso giro di 30 s, nessuna lettura in piu') e i messaggi per riga dei
    // canali locali (`*_posizioni`, `*_proposta`), solo se piu' freschi. Con il
    // canale muto la mappa restituisce le STESSE righe del blocco: parita'.
    // `safeDb`/`mikeDb` restano il blocco intero (control, aggregati...): le
    // loro `trades` si leggono dalla mappa (v. `safe`/`mike` piu' sotto).
    const [righePos, setRighePos] = useState<MappaRighe<RigaPosizioneBot>>(() => mappaVuota());
    const [safeDb, setSafe] = useState<SafeState | null>(null);
    const [runner, setRunner] = useState<RunnerState | null>(null);
    /** le proposte di Safe (`safe_strategy_requests`) e di Omega
     *  (`get_omega_proposte`), nella stessa mappa per riga: chiave bot+id. */
    const [righeProp, setRigheProp] = useState<MappaRighe<RigaPropostaBot>>(() => mappaVuota());
    const [erroreProposteOmega, setErroreProposteOmega] = useState<string | null>(null);
    /** istante dell'ultima lettura completa dal database: serve a dire al
     *  trader quanto è vecchio quello che vede, non quanto è vecchio il feed. */
    const [lettoAlle, setLettoAlle] = useState<number | null>(null);
    /** riga di oggi dal server, con `by_sport` gia' calcolato: e' la fonte del
     *  «quanto ha reso il tennis» — non si riconta niente lato client. */
    /** la giornata di Safe con i SOLDI VERI (`p_mode='live'`) */
    const [safeOggi, setSafeOggi] = useState<DailyRow | null>(null);
    /** la stessa giornata in PROVA. Tenuta a parte: non si somma mai all'altra. */
    const [safeOggiPaper, setSafeOggiPaper] = useState<DailyRow | null>(null);
    /** eventi di Omega: campionato, loghi e `fixture_id` che il feed non ha */
    const [eventiOmega, setEventiOmega] = useState<OmegaEvent[]>([]);
    /**
     * I trade dei tre bot sono arrivati almeno una volta?
     *
     * Serve a non spacciare per «0,00 €» un'esposizione che non abbiamo
     * ancora letto. `prev ||`: una caduta successiva lascia in pagina
     * l'ultimo dato buono, e quello resta letto.
     */
    const [soldiLetti, setSoldiLetti] = useState(false);
    /** numero del giro di ricarica in corso: una risposta vecchia non
     *  sovrascrive una piu' nuova (review 15/09) */
    const giroCorrente = useRef(0);
    /** partite che stanno REGISTRANDO adesso. Senza questo il pulsante REC
     *  ripartirebbe spento dopo un ricaricamento su una partita che registra:
     *  una spia che mente e peggio di una spia assente. */
    const [registrazioni, setRegistrazioni] = useState<Set<string>>(new Set());
    const [slippagePct, setSlippagePct] = useState(SLIPPAGE_PCT_DEFAULT);
    const [mikeDb, setMike] = useState<MikeStateView | null>(null);

    // C6 b - LE VISTE DALLA MAPPA PER RIGA, con i nomi di sempre: tutto cio'
    // che sta sotto (soldi, posizioni, operazioni, chiuse, proposte) legge
    // queste, senza sapere se la riga e' arrivata dal database o dal canale.
    const omegaTrades = useMemo(
        () => righeDi(righePos, 'omega') as OmegaTrade[], [righePos]);
    const safe = useMemo<SafeState | null>(
        () => (safeDb ? { ...safeDb, trades: righeDi(righePos, 'safe') as SafeTrade[] } : null),
        [safeDb, righePos]);
    const mike = useMemo<MikeStateView | null>(
        () => (mikeDb ? { ...mikeDb, trades: righeDi(righePos, 'mike') as MikeTrade[] } : null),
        [mikeDb, righePos]);
    // una proposta resta in elenco finche' e' 'proposed': le righe del
    // database lo sono per costruzione (filtro della lettura; quelle di Omega
    // non portano `status`), un messaggio del canale con la proposta decaduta
    // o approvata la toglie subito, senza aspettare la rilettura.
    const proposte = useMemo(
        () => (righeDi(righeProp, 'safe') as PropostaChiusura[]).filter(propostaViva),
        [righeProp]);
    const proposteOmega = useMemo(
        () => (righeDi(righeProp, 'omega') as PropostaUscitaOmega[]).filter(propostaViva),
        [righeProp]);

    const [caricamento, setCaricamento] = useState(true);
    const [errore, setErrore] = useState<string | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());

    // `stats` spinti dai canali locali: SOVRAPPOSIZIONE sul dato del database,
    // mai sostituzione della pagina intera. Alla caduta si azzerano e si torna
    // al database (regola 1).
    const [omegaPush, setOmegaPush] = useState<{ stats: OmegaStats; at: number } | null>(null);
    const [canali, setCanali] = useState<Record<Bot, LocalStatus>>(() => perOgniBot<LocalStatus>('off'));
    const [ultimoPush, setUltimoPush] = useState<Record<Bot, number | null>>(() => perOgniBot<number | null>(null));

    // ── I QUATTRO BOT DEL TENNIS ────────────────────────────────────────────
    // Quattro righe indipendenti, con la LORO riga di control, il LORO P&L del
    // giorno e i LORO ordini. Finche' la migrazione del 17/09 non e' applicata
    // queste letture falliscono e le quattro righe restano «stato non letto»:
    // e' la verita', ed e' meglio di un «fermo» inventato.
    const [tennisServizi, setTennisServizi] = useState<TennisBotServiceRow[] | null>(null);
    /** P&L di oggi per bot, dal database. Live e paper MAI nello stesso conto. */
    const [tennisOggi, setTennisOggi] = useState<TennisBotDailyRow[]>([]);
    const [tennisOggiPaper, setTennisOggiPaper] = useState<TennisBotDailyRow[]>([]);
    /** gli ordini di oggi dei quattro bot: posizioni aperte + scheda partita */
    const [tennisOrdini, setTennisOrdini] = useState<TennisBotOrderRow[]>([]);
    /**
     * 18/09 (raccordo, R4) — la riga singleton `betfair_live_account`, GIA'
     * letta/sottoscritta da `SaldoBetfairCard` (autosufficiente, non passa da
     * qui): serve ANCHE qui per le due colonne manuali (`manual_pnl_*`/
     * `manual_app_pnl_*`) che entrano nella composizione dell'obiettivo.
     * Stesse funzioni di `lib/liveOrders.ts`, nessuna tabella nuova.
     */
    const [liveAccount, setLiveAccount] = useState<LiveAccountRow | null>(null);
    /** avviso onesto: PIAZZA ha dovuto ripiegare sul solo `p_id` perché la
     *  RPC non accetta ancora il prezzo visto (migrazione non applicata). */
    const [avvisoOpportunita, setAvvisoOpportunita] = useState<string | null>(null);

    // ---------------------------------------------------------------- lettura
    const ricarica = useCallback(() => {
        let vivo = true;
        // ⚠️ REVIEW 15/09 — due giri possono sovrapporsi (la ricarica manuale
        // mentre quella periodica e' in volo): vince l'ULTIMO a rispondere,
        // che non e' per forza il piu' recente. Il contatore fa sì che una
        // risposta vecchia non sovrascriva una nuova.
        giroCorrente.current += 1;
        const mioGiro = giroCorrente.current;
        // C6 b - l'istante in cui la lettura PARTE: un messaggio del canale
        // pubblicato prima e' gia' dentro il blocco (il bot pubblica DOPO la
        // scrittura), uno pubblicato dopo puo' essere piu' fresco del blocco.
        const lettoMs = Date.now();
        Promise.allSettled([
            fetchScanRows(), fetchScanStatus(),
            fetchOmegaState(1), fetchOmegaTrades(2000),
            fetchSafeState(), fetchMikeState(), fetchRunnerState(), fetchProposte(),
            // DUE letture, non una. La RPC accetta `p_mode` e senza di esso
            // somma soldi veri e simulati: il 14/09 la card del tennis diceva
            // +0,25 €, un numero che non esisteva (era +0,41 live -0,16 paper).
            (() => { const g = romeDay(new Date()); return fetchSafeDaily(g, g, null, 'live'); })(),
            (() => { const g = romeDay(new Date()); return fetchSafeDaily(g, g, null, 'paper'); })(),
            fetchOmegaEvents(),
            fetchMissions(),
            fetchTennisFollows(),
            // ⚠️ REVIEW 15/09 — `get_omega_missions` elenca solo le partite CON
            // missione Omega, ma il pulsante registra QUALSIASI partita del
            // feed: una partita senza missione spariva da `registrazioni` al
            // primo ricaricamento, la spia REC si spegneva e la registrazione
            // non si poteva piu' fermare. `get_live_follows` le ha tutte.
            fetchLiveFollows(),
            // ── i quattro bot tennis: stato, P&L del giorno, ordini di oggi ──
            // DUE letture per il P&L, mai una: `get_tennis_bot_daily` pretende
            // `p_mode` proprio perche' paper e live non si sommano.
            fetchTennisBotServices(),
            (() => { const g = romeDay(new Date()); return fetchTennisBotDaily(g, g, 'live'); })(),
            (() => { const g = romeDay(new Date()); return fetchTennisBotDaily(g, g, 'paper'); })(),
            fetchTennisBotOrdersToday(null),
        ]).then((r) => {
            if (!vivo || mioGiro !== giroCorrente.current) return;
            const [rScan, rStatus, rOmega, rOmegaT, rSafe, rMike, rRunner, rProp,
                rDaily, rDailyPaper, rEventi, rMissioni, rFollowT, rFollowC,
                rTennisSrv, rTennisDaily, rTennisDailyPaper, rTennisOrdini] = r;
            if (rScan.status === 'fulfilled') setScan(rScan.value);
            if (rStatus.status === 'fulfilled') setScanStatus(rStatus.value);
            if (rOmega.status === 'fulfilled') setOmega(rOmega.value);
            if (rOmegaT.status === 'fulfilled') {
                const v = rOmegaT.value;
                setRighePos((p) => applicaBloccoDb(p, 'omega', v ?? [], lettoMs));
            }
            if (rSafe.status === 'fulfilled') {
                const v = rSafe.value;
                setSafe(v);
                setRighePos((p) => applicaBloccoDb(p, 'safe', v.trades ?? [], lettoMs));
            }
            if (rMike.status === 'fulfilled') {
                const v = rMike.value;
                setMike(v);
                setRighePos((p) => applicaBloccoDb(p, 'mike', v.trades ?? [], lettoMs));
            }
            if (rRunner.status === 'fulfilled') setRunner(rRunner.value);
            if (rProp.status === 'fulfilled') {
                const v = rProp.value;
                setRigheProp((p) => applicaBloccoDb(p, 'safe', v ?? [], lettoMs));
            }
            if (rDaily.status === 'fulfilled') setSafeOggi((rDaily.value ?? [])[0] ?? null);
            if (rDailyPaper.status === 'fulfilled') setSafeOggiPaper((rDailyPaper.value ?? [])[0] ?? null);
            if (rEventi.status === 'fulfilled') setEventiOmega(rEventi.value ?? []);
            // `null` resta `null` se la lettura fallisce: una riga di control
            // non letta non e' una riga «ferma».
            if (rTennisSrv.status === 'fulfilled') setTennisServizi(rTennisSrv.value ?? []);
            if (rTennisDaily.status === 'fulfilled') setTennisOggi(rTennisDaily.value ?? []);
            if (rTennisDailyPaper.status === 'fulfilled') setTennisOggiPaper(rTennisDailyPaper.value ?? []);
            if (rTennisOrdini.status === 'fulfilled') setTennisOrdini(rTennisOrdini.value ?? []);
            setSoldiLetti((prev) => prev || (rOmegaT.status === 'fulfilled'
                && rSafe.status === 'fulfilled' && rMike.status === 'fulfilled'));
            if (rMissioni.status === 'fulfilled' || rFollowT.status === 'fulfilled'
                || rFollowC.status === 'fulfilled') {
                const attive = new Set<string>();
                if (rMissioni.status === 'fulfilled') {
                    for (const m of rMissioni.value?.missions ?? []) {
                        if (m?.recording === true && m.event_id) attive.add(String(m.event_id));
                    }
                }
                if (rFollowC.status === 'fulfilled') {
                    for (const f of rFollowC.value ?? []) {
                        if ((f as { record?: boolean }).record === true && f.event_id) {
                            attive.add(String(f.event_id));
                        }
                    }
                }
                if (rFollowT.status === 'fulfilled') {
                    for (const f of rFollowT.value ?? []) {
                        if (f?.record === true && f.event_id) attive.add(String(f.event_id));
                    }
                }
                setRegistrazioni(attive);
            }

            // Un errore su UNA fonte non deve svuotare la pagina: si mostra
            // quello che è arrivato e si dichiara che cosa manca.
            const caduti = r
                .map((x, i) => (x.status === 'rejected'
                    ? (FONTI_RICARICA[i] ?? `fonte #${i + 1}`) : null))
                .filter((x): x is string => x !== null);
            setErrore(caduti.length ? `fonti non raggiunte: ${caduti.join(', ')}` : null);
            setLettoAlle(Date.now());
            setCaricamento(false);
        });
        return () => { vivo = false; };
    }, []);

    useEffect(() => {
        const stop = ricarica();
        const t = window.setInterval(ricarica, RICARICA_MS);
        return () => { stop(); window.clearInterval(t); };
    }, [ricarica]);

    // ⚠️ REVIEW 15/09 — LO STATO DELLO SCANNER IN REALTIME.
    // Si scrive ogni 10 s ma si leggeva solo ogni 30: meta' del tempo il feed
    // risultava «vecchio», e con esso le quote FERME diventavano «vecchie» —
    // che e' la distinzione su cui si decide se una chiusura e' approvabile.
    // La sottoscrizione esisteva gia' e non la usava nessuno.
    useEffect(() => subscribeScanStatus((r) => { if (r) setScanStatus(r); }), []);

    // ------------------------------------------------- feed partite in realtime
    //
    // Task 6 (18/09) — COALESCENZA: su un mercato molto attivo (o 720
    // mercati insieme) più eventi possono arrivare nella stessa manciata di
    // millisecondi. Prima, ognuno faceva il suo `setScan` (un render per
    // messaggio); ora si accodano in un buffer e si applicano TUTTI INSIEME
    // al prossimo frame (`requestAnimationFrame`, con `setTimeout` come
    // ripiego fuori dal browser/jsdom): un commit per frame, non uno per
    // messaggio. Il RISULTATO è identico (`lib/scanEventBuffer.ts`,
    // `applicaLottoScan` == applicare gli eventi uno a uno, in ordine): non è
    // una lettura in meno dal database, è un render in meno sullo schermo.
    useEffect(() => {
        const programma = typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function'
            ? window.requestAnimationFrame.bind(window)
            : (cb: () => void) => window.setTimeout(cb, 16);
        const annulla = typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function'
            ? window.cancelAnimationFrame.bind(window)
            : window.clearTimeout.bind(window);

        let lotto: ScanRowEvent<ScanRow>[] = [];
        let programmato: number | null = null;

        const scarica = () => {
            programmato = null;
            if (!lotto.length) return;
            const daApplicare = lotto;
            lotto = [];
            setScan((prev) => applicaLottoScan(prev, daApplicare));
        };

        const off = subscribeScanRows((ev) => {
            lotto.push(ev);
            if (programmato == null) programmato = programma(scarica) as unknown as number;
        });

        // STADIO B1/B2a (18/09, raccordo) — CANALE LOCALE SCANNER (47336,
        // topic `scan_calcio`/`scan_tennis`): STESSA riga di
        // `safe_strategy_scan` (contratto in
        // `Betfair/safe_strategy/CHECKPOINT_AL_MS_F0_F1_2026-09-18.md`), quindi
        // entra nello STESSO lotto/coalescenza di sopra. Oggi il canale è muto
        // (porta chiusa lato backend): nessun messaggio arriva, quindi nessuna
        // differenza rispetto a prima. "Vince il più recente": un messaggio
        // più vecchio della riga già in `scan` si scarta; uno senza `payload`
        // pure (non è una notizia, è un guasto di pubblicazione).
        const localeScanner = getLocalChannel('scanner');
        const accodaSeFresco = (bruto: unknown) => {
            const row = scanLocaleAccettabile(scanRef.current, bruto as ScanRowLocaleMsg | null);
            if (!row) return; // senza payload, o più vecchio della riga già in memoria
            lotto.push({ type: 'upsert', row });
            setUltimoScanLocaleMs(Date.now());
            if (programmato == null) programmato = programma(scarica) as unknown as number;
        };
        const offScanCalcio = localeScanner.subscribe('scan_calcio', accodaSeFresco);
        const offScanTennis = localeScanner.subscribe('scan_tennis', accodaSeFresco);

        return () => {
            off();
            offScanCalcio();
            offScanTennis();
            if (programmato != null) annulla(programmato);
        };
    }, []);

    // ------------------------------------------------------- canali locali
    useEffect(() => {
        const chiusure: (() => void)[] = [];
        (['omega', 'safe', 'mike'] as const).forEach((bot) => {
            const ch = getLocalChannel(bot);
            setCanali((p) => ({ ...p, [bot]: ch.getStatus() }));
            chiusure.push(ch.onStatus((st) => {
                setCanali((p) => ({ ...p, [bot]: st }));
                if (st !== 'connected') {
                    // REGOLA 1: si buttano i numeri spinti e si torna al
                    // database. Meglio un dato vecchio DICHIARATO di una
                    // fotografia ferma di cui non sappiamo più l'età.
                    setUltimoPush((p) => ({ ...p, [bot]: null }));
                    if (bot === 'omega') setOmegaPush(null);
                }
            }));
            chiusure.push(ch.subscribe(`${bot}_stato`, (d) => {
                setUltimoPush((p) => ({ ...p, [bot]: Date.now() }));
                if (bot !== 'omega') return;
                const msg = d as { stats?: OmegaStats } | null;
                if (msg && typeof msg === 'object' && msg.stats && typeof msg.stats === 'object') {
                    setOmegaPush({ stats: msg.stats, at: Date.now() });
                }
            }));
        });
        return () => { for (const c of chiusure) c(); };
    }, []);

    // ------------------------------------------- C6 b: righe dai canali locali
    // I MESSAGGI PER RIGA di Omega (47334), Safe (47335) e Mike (47333): la
    // riga appena scritta dal bot, con la busta `fonte`/`_seq`/`_pubblicato_ms`
    // (`Betfair/stream/canale_bot.py`). Stesso singleton `getLocalChannel` gia'
    // usato sopra per `*_stato` e da `svegliaBot`: nessun socket nuovo. Un
    // messaggio si applica SOLO a una riga gia' nota al database e SOLO se piu'
    // fresco (`lib/righeCanale.ts`); scartato = stesso stato, nessun render.
    useEffect(() => {
        const chiusure: (() => void)[] = [];
        for (const { bot, topic, sport } of TOPIC_POSIZIONI) {
            chiusure.push(getLocalChannel(bot).subscribe(topic, (d) => {
                const msg = leggiMessaggioRiga(d);
                if (!msg) return;
                const ricevutoMs = Date.now();
                setRighePos((p) => applicaMessaggioCanale(p, bot, msg, ricevutoMs, sport));
            }));
        }
        for (const { bot, topic } of TOPIC_PROPOSTE) {
            chiusure.push(getLocalChannel(bot).subscribe(topic, (d) => {
                const msg = leggiMessaggioRiga(d);
                if (!msg) return;
                const ricevutoMs = Date.now();
                setRigheProp((p) => applicaMessaggioCanale(p, bot, msg, ricevutoMs));
            }));
        }
        return () => { for (const c of chiusure) c(); };
    }, []);

    // --------------------------------------------------- conto Betfair (R4)
    // NON entra nel poll dei 30 s (`FONTI_RICARICA`/`Promise.allSettled`): il
    // 13/09 il database e' andato giu' per budget IO esaurito, ed e' vietato
    // aggiungere una lettura al giro pieno. Si riusa lo STESSO schema di
    // `SaldoBetfairCard.tsx` (autosufficiente, gia' in pagina): UNA lettura
    // ONE-SHOT al montaggio + push Realtime sulla STESSA riga singleton
    // `betfair_live_account` — nessuna tabella nuova, nessun polling in piu'.
    useEffect(() => {
        let vivo = true;
        fetchLiveAccount().then((r) => { if (vivo) setLiveAccount(r); })
            .catch(() => { /* resta null: leggiManualeSitoBetfair dichiara "non disponibile" */ });
        const off = subscribeLiveAccount((r) => { if (vivo) setLiveAccount(r); });
        return () => { vivo = false; off(); };
    }, []);

    // -------------------------------------------------- proposte in realtime
    // Una proposta di chiusura che comparisse 30 s dopo sarebbe inutile: il
    // prezzo su cui il bot ha deciso non c'e' piu'.
    useEffect(() => subscribeProposte(() => {
        const lettoMs = Date.now();
        fetchProposte()
            .then((v) => setRigheProp((p) => applicaBloccoDb(p, 'safe', v ?? [], lettoMs)))
            .catch(() => { /* il giro di ricarica riprova */ });
    }), []);

    // ------------------------------------------ proposte di OMEGA in realtime
    // Stessa regola della Safe: una proposta che comparisse 30 s dopo sarebbe
    // inutile. La prima lettura fallisce finche' la migrazione non e' applicata
    // (la RPC non esiste): il motivo si DICHIARA, non si nasconde.
    useEffect(() => {
        const leggi = () => {
            const lettoMs = Date.now();
            fetchProposteOmega()
                .then((r) => {
                    setRigheProp((p) => applicaBloccoDb(p, 'omega', r ?? [], lettoMs));
                    setErroreProposteOmega(null);
                })
                .catch((e: unknown) => {
                    setRigheProp((p) => applicaBloccoDb(p, 'omega', [], lettoMs));
                    setErroreProposteOmega(e instanceof Error ? e.message : String(e));
                });
        };
        leggi();
        return subscribeProposteOmega(leggi);
    }, []);

    // --------------------------------------------------------------- orologio
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), TICK_MS);
        return () => window.clearInterval(t);
    }, []);

    // ------------------------------------------------------- il modello di vista
    // 14/09 — il TENNIS va in live oggi: la pagina deve mostrarlo. Prima
    // filtrava `sport === 'calcio'` e il tennis semplicemente non compariva.
    const righeFeed = useMemo(
        () => scan.filter((r) => r.sport === 'calcio' || r.sport === 'tennis'),
        [scan],
    );
    const calcioRows = useMemo(() => scan.filter((r) => r.sport === 'calcio'), [scan]);

    // Il prezzo della scheda viene dal FEED, non dalla proposta: e' questo che
    // la rende viva senza che il bot riscriva la riga.
    const feedPerEvento = useMemo(() => {
        const m = new Map<string, { payload: unknown; updated_at: string | null }>();
        for (const r of scan) m.set(String(r.event_id), { payload: r.payload, updated_at: r.updated_at });
        return m;
    }, [scan]);

    /** 18/09 — tutti i payload della giornata, per il prezzo vivo PER GAMBA
     *  delle proposte combo (`lib/comboPrezzoVivo.ts`): una gamba non porta
     *  un proprio event_id, quindi si cerca il suo mercato in TUTTI i payload
     *  già in memoria. Nessuna lettura nuova (stesso `scan` di sempre). */
    const tuttiIPayloadOggi = useMemo(
        () => Array.from(feedPerEvento.values()).map((v) => v.payload as Parameters<typeof prezzoVivo>[0]),
        [feedPerEvento],
    );


    const soldi = useMemo(() => soldiPerPartita([
        ...chiaviComposte(marca(omegaTrades as unknown as PnlTradeLike[], 'omega'), 'omega'),
        ...chiaviComposte(marca((safe?.trades ?? []) as unknown as PnlTradeLike[], 'safe'), 'safe'),
        ...chiaviComposte(marca((mike?.trades ?? []) as unknown as PnlTradeLike[], 'mike'), 'mike'),
        // 18/09 (raccordo, R1/Task 3 di F3) — i 4 bot tennis nei soldi per
        // partita: `marcaTennis`/`ORDINE_BOT` erano gia' pronti in
        // `lib/controlRoom.ts` (F3), non ancora collegati qui (richiesta
        // fuori perimetro #1 del suo referto). Chiave composta bot+id
        // (sotto): `omega_trades`/`safe_strategy_trades`/`mike_trades`/
        // `tennis_live_orders` hanno sequenze PK INDIPENDENTI — senza,
        // un id numerico coincidente fra due tabelle diverse farebbe
        // agganciare la chiusura del bot sbagliato (bug preesistente,
        // segnalato da F3, ora chiuso per tutti e 7 i bot).
        ...chiaviComposte(marcaTennis(
            tennisOrdini.filter((o) => o.source === 'tennis_scalper') as unknown as RigaTennisPerSoldi[], 'tennis_scalper',
        ), 'tennis_scalper'),
        ...chiaviComposte(marcaTennis(
            tennisOrdini.filter((o) => o.source === 'tennis_pro') as unknown as RigaTennisPerSoldi[], 'tennis_pro',
        ), 'tennis_pro'),
        ...chiaviComposte(marcaTennis(
            tennisOrdini.filter((o) => o.source === 'tennis_flb') as unknown as RigaTennisPerSoldi[], 'tennis_flb',
        ), 'tennis_flb'),
        ...chiaviComposte(marcaTennis(
            tennisOrdini.filter((o) => o.source === 'tennis_swing') as unknown as RigaTennisPerSoldi[], 'tennis_swing',
        ), 'tennis_swing'),
    ]), [omegaTrades, safe?.trades, mike?.trades, tennisOrdini]);

    // Omega è l'unico che pubblica obiettivo e target per partita, e li calcola
    // il SERVIZIO. La pagina li legge: non ne fa una seconda copia.
    const oStats = omegaPush?.stats ?? omega?.control?.stats ?? null;
    const obiettivo = omega?.goal_today ?? oStats?.goal ?? null;
    const realizzato = oStats?.realized_today ?? null;
    const targetServizio = oStats?.target_match ?? null;

    // CAMPIONATO, LOGHI E FIXTURE — il feed dello scanner non li ha (verificato
    // sui dati veri il 14/09: porta `mo_market_id` e `open_date`, e basta).
    // Esistono pero' gia' nel software, nella tabella eventi di Omega. Qui si
    // UNISCONO per event_id: quello che manca resta null e la scheda lo dice.
    const arricchimento = useMemo(() => {
        const m = new Map<string, ArricchimentoPartita>();
        for (const e of eventiOmega) {
            if (e?.event_id) m.set(String(e.event_id), arricchimentoDa(e));
        }
        return m;
    }, [eventiOmega]);

    /**
     * 18/09 (raccordo, R4) — le due voci manuali FUORI dai bot (sito Betfair
     * / terminale manuale della nostra app), dalla riga singleton
     * `betfair_live_account` (colonne `manual_pnl_*`/`manual_app_pnl_*`,
     * `Betfair/stream/reconcile_worker.py::_sync_manual_pnl`). Nessuna
     * lettura nuova (`liveAccount`, sopra). Assente/migrazione non applicata
     * → entrambe "non disponibile", comportamento IDENTICO a ieri.
     */
    const manualeSitoBetfair = useMemo<ManualeSitoBetfair>(
        () => leggiManualeSitoBetfair(liveAccount, romeDay(new Date(nowMs))),
        [liveAccount, nowMs],
    );

    // ── IL REALIZZATO DI OGGI, da TUTTI E TRE i bot ──────────────────────────
    // La barra leggeva `realized_today` di Omega: una vincita del tennis (Safe)
    // non la muoveva. Qui si sommano le righe REGOLATE dei tre bot, tenendo
    // separati soldi veri e simulati e dividendo per sport.
    // ── righe SORGENTE per bot, filtrate a OGGI: servono sia a `realizzatoOggi`
    // (barra, sommate) sia a `composizioneOggi` (Task 2, scomposte per bot) —
    // UNA sola volta il filtro "e' di oggi", nessuna seconda copia. ──────────
    const oggiRighe = useMemo(() => {
        const oggi = romeDay(new Date(nowMs));
        const delGiorno = (placedAt: string | null | undefined) =>
            !!placedAt && romeDay(new Date(placedAt)) === oggi;
        // 23/09 - UNA riga per OPERAZIONE (ciclo apertura + chiusure), non per
        // gamba: netto del ciclo, esito dal suo segno, giornata/origine/sport
        // dell'APERTURA (`righeRealizzatoPerCiclo`). Per gamba, un cash out
        // contava 1 vinta + 1 persa e la sua chiusura (origin 'manual') finiva
        // sotto 'Manuale', lasciando al bot l'apertura intera.
        const omegaRighe: RigaComponente[] = righeRealizzatoPerCiclo(
            omegaTrades as unknown as RigaTradeCiclo[], { delGiorno, sport: 'calcio' });
        const safeRighe: RigaComponente[] = righeRealizzatoPerCiclo(
            (safe?.trades ?? []) as unknown as RigaTradeCiclo[], { delGiorno });
        const mikeRighe: RigaComponente[] = righeRealizzatoPerCiclo(
            (mike?.trades ?? []) as unknown as RigaTradeCiclo[], { delGiorno, sport: 'calcio' });
        // I 4 BOT TENNIS DEDICATI — righe SINTETICHE (18/09, Task 2): la RPC
        // `get_tennis_bot_daily` da' gia' il netto PER BOT PER GIORNO (non le
        // singole operazioni), quindi qui si costruisce UNA riga per bot con
        // `status` dedotto dal segno del netto — l'unico modo di riusare
        // `realizzatoGiornata` (che conta righe REGOLATE) senza una seconda
        // formula di somma. Il costo dichiarato: `vinte`/`perse` su queste
        // righe contano "quanti bot hanno chiuso la giornata in utile", non
        // "quanti ordini": la RPC non da' le operazioni singole. Live e paper
        // restano SEMPRE due array separati (mai sommati).
        const tennisBotRiga = (r: TennisBotDailyRow, mode: 'live' | 'paper'): RigaComponente | null => {
            if (r.pnl_netto == null) return null;
            const status = r.pnl_netto > 0 ? 'won' : r.pnl_netto < 0 ? 'lost' : 'void';
            return { status, pnl: r.pnl_netto, mode, sport: 'tennis', origin: 'auto' };
        };
        const tennisBotRighe: RigaComponente[] = [
            ...tennisOggi.map((r) => tennisBotRiga(r, 'live')),
            ...tennisOggiPaper.map((r) => tennisBotRiga(r, 'paper')),
        ].filter((r): r is RigaComponente => r != null);
        // 18/09 (raccordo, R4) — le due voci MANUALI fuori dai bot (sito/app):
        // una riga sintetica per bucket, SOLO soldi veri (la RPC del conto
        // legge solo il LIVE), status dal segno del netto — stesso schema
        // dei bot tennis sopra, nessuna seconda formula di somma.
        const rigaManuale = (v: number | null): RigaComponente | null => (v == null ? null : {
            status: v > 0 ? 'won' : v < 0 ? 'lost' : 'void', pnl: v, mode: 'live', sport: 'calcio', origin: 'manual',
        });
        const manualeSitoRighe = [rigaManuale(manualeSitoBetfair.pnlOggi)].filter((r): r is RigaComponente => r != null);
        const manualeAppRighe = [rigaManuale(manualeSitoBetfair.app?.pnlOggi ?? null)].filter((r): r is RigaComponente => r != null);
        return { omegaRighe, safeRighe, mikeRighe, tennisBotRighe, manualeSitoRighe, manualeAppRighe };
    }, [omegaTrades, safe?.trades, mike?.trades, tennisOggi, tennisOggiPaper, nowMs, manualeSitoBetfair]);

    const realizzatoOggi = useMemo(() => {
        const { omegaRighe, safeRighe, mikeRighe, tennisBotRighe, manualeSitoRighe, manualeAppRighe } = oggiRighe;
        const righe: RigaRealizzato[] = [
            ...omegaRighe, ...safeRighe, ...mikeRighe, ...tennisBotRighe,
            ...manualeSitoRighe, ...manualeAppRighe,
        ];
        // DUE conti separati sulle STESSE righe. `realizzatoGiornata` sa gia'
        // dividere per modalita', ma il chiamante deve DECIDERE quale mostrare:
        // un numero che somma le due e' un numero che non esiste.
        const soloLive = righe.filter((x) => String(x.mode ?? '').toLowerCase() === 'live');
        const soloPaper = righe.filter((x) => String(x.mode ?? '').toLowerCase() === 'paper');
        return {
            tutto: realizzatoGiornata(righe),
            live: realizzatoGiornata(soloLive),
            paper: realizzatoGiornata(soloPaper),
        };
    }, [oggiRighe]);

    /** Task 2 — la SCOMPOSIZIONE dell'obiettivo: stesse righe di sopra,
     *  raggruppate per bot invece che sommate tutte insieme. */
    const composizioneOggi = useMemo<ComposizioneObiettivo>(() => componiObiettivo({
        omega: oggiRighe.omegaRighe,
        safe: oggiRighe.safeRighe,
        mike: oggiRighe.mikeRighe,
        tennisBot: oggiRighe.tennisBotRighe,
        manualeSito: oggiRighe.manualeSitoRighe,
        manualeApp: oggiRighe.manualeAppRighe,
    }), [oggiRighe]);

    /** Task 2 — salva l'obiettivo di oggi (RPC gia' pronta, verificata: fa
     *  `coalesce` su `params`/`mode`, non li tocca). */
    const salvaObiettivo = useCallback(async (valore: number) => {
        await updateOmegaParams({ dailyGoal: valore });
        ricarica();
    }, [ricarica]);

    // NOTA: questo blocco sta QUI, prima di `giornata`, perche' il target
    // di ripiego di ogni partita si calcola sottraendo all'obiettivo il
    // realizzato — e dev'essere quello con i SOLDI VERI.
    const giornata = useMemo(() => costruisciGiornata({
        righe: righeFeed.map((r) => ({
            event_id: r.event_id,
            sport: r.sport as Sport,
            payload: r.payload as PartitaFeedLike,
            updated_at: r.updated_at,
        })),
        soldi, nowMs, obiettivo, targetServizio, arricchimento,
        // ⚠️ REVIEW 15/09 — QUI C'ERA `realizzato`, cioè il realized_today di
        // Omega, che somma paper e live. `targetPartita` lo SOTTRAE a un
        // obiettivo in denaro reale per calcolare il target di ripiego di ogni
        // partita: una perdita simulata alzava il target di tutte le altre.
        realizzato: realizzatoOggi.live.totale,
        // serve a distinguere «prezzo fermo» da «prezzo vecchio»: lo scanner
        // scrive solo quando qualcosa cambia, quindi l'eta' della riga NON dice
        // «da quanto non guardiamo».
        etaScannerS: etaSecondi(scanStatus?.updated_at, nowMs),
    }), [righeFeed, soldi, nowMs, obiettivo, realizzatoOggi, targetServizio,
        scanStatus?.updated_at, arricchimento]);

    const totali = useMemo(() => totaliGiornata(giornata, soldiLetti), [giornata, soldiLetti]);

    const copertura = useMemo(
        () => coperturaControllo(
            calcioRows
                .filter((r) => (r.payload as CalcioScanPayload)?.inplay === true)
                .map((r) => r.payload as PartitaFeedLike),
        ),
        [calcioRows],
    );

    const bots = useMemo<StatoBot[]>(() => {
        const varianti = leggiVarianti(safe?.control?.params, safe?.params_effective as Record<string, unknown> | null);
        const modi = leggiModiStrategia(
            safe?.control?.stats?.params_effective as Record<string, unknown> | null | undefined,
            safe?.control?.params,
        );
        const riga = (
            bot: Bot, modalita: Modalita | null, inCorsa: boolean, battitoAt: string | null,
            stato: string | null, params: Record<string, unknown> | null,
            stats: Record<string, unknown> | null = null,
            obiettivoGiorno: number | null = null,
        ): StatoBot => {
            const at = ultimoPush[bot];
            const eta = at == null ? null : Math.max(0, Math.round((nowMs - at) / 1000));
            // ⚠️ REVIEW 15/09 — la CADENZA del battito la dichiara chi batte.
            // Prima stava scritta qui come costante: era una seconda verità, e
            // il 13/09 il servizio l'aveva allargata per far respirare il
            // database senza che la pagina lo sapesse.
            const cadenza = numero(stats?.cadenza_battito_s);
            return {
                bot, modalita, inCorsa, battitoAt,
                canale: canali[bot],
                etaPushS: eta,
                // ⚠️ REVIEW 15/09 — il battito si giudica con la cadenza del
                // CICLO, non con le soglie delle quote; e se il canale locale
                // (che e' opzionale) non ha mai parlato si ripiega sul
                // `heartbeat_at` del database, che c'e' sempre. Prima un bot
                // vivissimo senza WebSocket risultava muto.
                freschezzaPush: freschezzaBattito(eta ?? etaSecondi(battitoAt, nowMs), cadenza),
                varianti: bot === 'safe' ? varianti : null,
                modiStrategia: bot === 'safe' ? modi : null,
                stato, params, obiettivoGiorno,
                // ── quello che il SERVIZIO dichiara, non quello che deduciamo ──
                motivoBlocco: testo(stats?.motivo_blocco),
                tettoPartite: numero(stats?.tetto_partite),
                partiteEsposte: numero(stats?.partite_esposte),
                stopFermaSoloAperture: stats?.stop_ferma_solo_aperture === true,
                fermatoAllAvvioAt: testo(stats?.fermato_all_avvio_at),
                pnlOggi: isBotTennis(bot) ? pnlTennisDi(tennisOggi, bot as TennisBotKey) : null,
                pnlOggiPaper: isBotTennis(bot)
                    ? pnlTennisDi(tennisOggiPaper, bot as TennisBotKey) : null,
            };
        };
        const testo = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : null);
        const numero = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
        return [
            riga('omega', modalitaDi(omega?.control?.mode), inCorsaDi(omega?.control?.status),
                omega?.control?.heartbeat_at ?? null, testo(omega?.control?.status),
                (omega?.control?.params ?? null) as Record<string, unknown> | null,
                (omega?.control?.stats ?? null) as Record<string, unknown> | null,
                numero((omega?.control as { daily_goal?: unknown } | undefined)?.daily_goal)),
            riga('safe', modalitaDi(safe?.control?.mode), inCorsaDi(safe?.control?.status),
                safe?.control?.heartbeat_at ?? null, testo(safe?.control?.status),
                (safe?.control?.params ?? null) as Record<string, unknown> | null,
                (safe?.control?.stats ?? null) as Record<string, unknown> | null),
            riga('mike', modalitaDi(mike?.control?.mode), inCorsaDi(mike?.control?.status),
                mike?.control?.heartbeat_at ?? null, testo(mike?.control?.status),
                (mike?.control?.params ?? null) as Record<string, unknown> | null,
                (mike?.control?.stats ?? null) as Record<string, unknown> | null),
            // ── I QUATTRO DEL TENNIS, uno per uno ───────────────────────────
            // Nessuna deduzione e nessuna eredita': stato, modalita' e stake
            // escono dalla RIGA DI CONTROL di QUEL bot. Riga assente (o
            // migrazione non applicata) = `stato: null`, che il pannello scrive
            // «stato non letto» e NON comanda: fail-closed.
            ...BOT_TENNIS.map((k) => {
                const c = (tennisServizi ?? []).find((x) => x.bot_key === k) ?? null;
                // lo `stake` e' una COLONNA, non una voce di `params`: si
                // espone sotto la chiave 'stake' che l'interruttore legge, e
                // la colonna vince sempre su un'eventuale omonima nei params.
                const params = c == null ? null : { ...(c.params ?? {}), stake: c.stake };
                return riga(
                    k, modalitaDi(c?.mode), inCorsaDi(c?.status),
                    c?.heartbeat_at ?? null,
                    c == null ? null : testo(c.status),
                    params,
                    (c?.stats ?? null) as Record<string, unknown> | null,
                );
            }),
        ];
    }, [omega?.control, safe?.control, safe?.params_effective, mike?.control,
        tennisServizi, tennisOggi, tennisOggiPaper, canali, ultimoPush, nowMs]);

    // ── LE POSIZIONI GIA' CHIUSE, vinte e perse ──────────────────────────────
    // Una posizione e apertura + coperture: sul green-up del 14/09 le righe da
    // sole dicono «una vinta e una persa», la POSIZIONE ha guadagnato +0,03.
    const chiuse = useMemo<PosizioneChiusa[]>(() => {
        const righe: TradeChiudibile[] = [];
        const aggiungi = (lista: readonly Record<string, unknown>[] | undefined, bot: Bot, sport?: string) => {
            for (const t of lista ?? []) {
                if (typeof t?.id !== 'number') continue;
                righe.push({ ...(t as object), __bot: bot, sport: (t.sport as string) ?? sport } as TradeChiudibile);
            }
        };
        aggiungi(omegaTrades as unknown as Record<string, unknown>[], 'omega', 'calcio');
        aggiungi(safe?.trades as unknown as Record<string, unknown>[] | undefined, 'safe');
        aggiungi(mike?.trades as unknown as Record<string, unknown>[] | undefined, 'mike', 'calcio');
        // ── GLI ORDINI GIA' REGOLATI DEI QUATTRO BOT TENNIS ─────────────────
        // «Indipendenti come gli altri» (ordine dell'utente, 17/09): una
        // posizione chiusa di un bot tennis entra in questa scheda con lo
        // STESSO contratto delle righe di Omega/Safe/Mike, o il contatore
        // mentirebbe per omissione. La giornata la filtra il meccanismo
        // condiviso (`PosizioneChiusa.giorno`), qui non si filtra a mano.
        //
        // DUE TRADUZIONI OBBLIGATE, e nessuna inventata:
        //  1. LO STATO. `tennis_live_orders.status` e' lo stato flumine, e
        //     `EXECUTION_COMPLETE` vuol dire «abbinato tutto», non «regolato»:
        //     `isSettled` non lo riconoscerebbe mai. Il regolamento lo dichiara
        //     `settled_at` e l'esito lo dice il P&L.
        //  2. IL P&L. `tennis_live_orders.pnl` e' LORDO, con la commissione in
        //     una colonna sua; `RigaChiusa.pnl` e' NETTO per contratto. Si
        //     sottrae quella dichiarata, mai una commissione stimata.
        //
        // Una riga regolata SENZA `pnl` non entra: il suo risultato non lo
        // sappiamo ancora, e «0,00 €» sarebbe uno zero travestito da pareggio.
        // Resta visibile fra le posizioni aperte finche' il numero non arriva.
        for (const o of tennisOrdini) {
            const bot = o.source;
            if (bot == null || !isBotTennis(bot as Bot)) continue;
            if (isErrorRow(o.status)) continue;
            if (o.settled_at == null) continue;
            const netto = pnlNettoTennis(o);
            if (netto == null) continue;
            const eventId = String(o.event_id ?? '');
            const feed = feedPerEvento.get(eventId)?.payload as PartitaFeedLike | undefined;
            righe.push({
                id: o.id,
                event_id: eventId,
                event_name: feed?.event_name ?? null,
                sport: 'tennis',
                mode: o.mode,
                // won / lost / void: sono gli unici stati che la piattaforma
                // riconosce come regolati. Zero netto = niente si e' mosso.
                status: netto > SOGLIA_PARI ? 'won' : netto < -SOGLIA_PARI ? 'lost' : 'void',
                pnl: netto,
                side: o.side,
                price: o.price ?? null,
                size: o.size ?? null,
                // `tennis_live_orders` porta il `selection_id`, non il nome
                selection_name: null,
                placed_at: o.placed_at ?? null,
                settled_at: o.settled_at,
                // nessuna catena di coperture: ogni ordine e' una posizione sua
                closes_trade_id: null,
                strategy: null,
                size_requested: o.size ?? null,
                size_matched: o.size_matched ?? null,
                size_remaining: o.size_remaining ?? null,
                avg_price_matched: o.average_price_matched ?? null,
                betfair_updated_at: o.updated_at ?? null,
                meta: null,
                __bot: bot as Bot,
            });
        }
        return posizioniChiuse(righe);
    }, [omegaTrades, safe?.trades, mike?.trades, tennisOrdini, feedPerEvento]);

    /**
     * Quanto vale chiudere ADESSO, con la matematica condivisa del green-up.
     * `null` quando il prezzo corrente non c'e': non si inventa.
     *
     * ⚠️ REVIEW 15/09 — questa funzione stava DENTRO il `useMemo` delle
     * posizioni, quindi la scheda di chiusura non poteva usarla e stampava
     * `locked_at_decision`, cioe' il valore calcolato dal bot alla FOTOGRAFIA,
     * sotto un'etichetta che dice «adesso». Due numeri diversi per la stessa
     * posizione nella stessa pagina. Ora e' una sola, e la usano entrambe.
     */
    const chiusuraViva = useCallback((t: {
        side: string | null; price: number | null; size: number | null;
        meta: Record<string, unknown> | null;
        event_id: string; market_id?: string | null; selection_id?: number | null;
    }): PosizioneAperta['chiusura'] => {
        const { win, lose } = tradeExposureNow({
            side: t.side, price: t.price, size: t.size, meta: t.meta ?? null,
        });
        const lato = hedgeSide(win, lose);
        const riga = feedPerEvento.get(String(t.event_id));
        const payload = (riga?.payload ?? null) as Parameters<typeof prezzoVivo>[0];
        // il prezzo del lato su cui si CHIUDE, non quello di ingresso
        const vivo = prezzoVivo(payload, t.market_id ?? null, t.selection_id ?? null, lato);
        const prezzo = greenPrice(win, lose, lato === 'back' ? vivo.prezzo : null,
                                  lato === 'lay' ? vivo.prezzo : null);
        return {
            lato,
            prezzo,
            abbinabile: vivo.abbinabile,
                bloccabile: prezzo == null ? null : partialLockedPnl(prezzo, win, lose, 1),
        };
    }, [feedPerEvento]);

    /**
     * 17/09 — IL LIBRO DI ADESSO sulla selezione di una riga, dal feed di
     * scansione GIÀ caricato per le partite: nessuna lettura in più, nessuna
     * chiamata a Betfair. 23/09 — anche Mike porta `market_id`/`selection_id`
     * sulla riga (come Omega/Safe): una riga STORICA senza i due campi (scritta
     * prima dell'11/09, o di un bot che non li pubblica) torna `back`/`lay`
     * `null` da sola — `prezzoVivo` è fail-closed su id mancanti — mai un
     * prezzo indovinato.
     */
    const libroVivo = useCallback((t: {
        event_id: string; market_id?: string | null; selection_id?: number | null;
    }): { back: number | null; lay: number | null } => {
        const riga = feedPerEvento.get(String(t.event_id));
        const payload = (riga?.payload ?? null) as Parameters<typeof prezzoVivo>[0];
        return {
            back: prezzoVivo(payload, t.market_id ?? null, t.selection_id ?? null, 'back').prezzo,
            lay: prezzoVivo(payload, t.market_id ?? null, t.selection_id ?? null, 'lay').prezzo,
        };
    }, [feedPerEvento]);

    /** Le partite di Mike per `event_id`: una mappa sulla stessa lista gia' letta. */
    const mikeEventi = useMemo(() => {
        const m = new Map<string, MikeEvent>();
        for (const ev of mike?.events ?? []) m.set(String(ev.event_id), ev);
        return m;
    }, [mike?.events]);

    const posizioni = useMemo<PosizioneAperta[]>(() => {
        const out: PosizioneAperta[] = [];
        // le CHIUSURE collegate, una volta sola per bot: servono a `legPnl` per
        // distinguere «bloccato» da «ancora aperto».
        const closesOmega = chiusureCollegate(omegaTrades);
        const closesSafe = chiusureCollegate(safe?.trades ?? []);
        const closesMike = chiusureCollegate(mike?.trades ?? []);
        for (const t of omegaTrades) {
            // una gamba di CHIUSURA (`closes_trade_id`) non e' una posizione:
            // vive nella scheda della partita sotto la sua apertura (17/09, utente)
            if (!aMercato(t) || eGambaDiChiusura(t)) continue;
            const book = libroVivo(t);
            out.push({
                bot: 'omega', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.runner_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                // 17/09 — «se chiudo ora» anche per Omega: era scritto solo per
                // Safe, con la stessa matematica e lo stesso feed. Una posizione
                // in profitto va VISTA, non scoperta quando il bot propone.
                chiusura: chiusuraViva(t),
                ordine: ordineDi(t),
                dettaglio: dettaglioDi(t as RigaDettagliabile, closesOmega.get(t.id) ?? [], {
                    // P implicita del mercato = 1 / quota LAY viva, come in
                    // `MatchTradesTable` (mai una seconda formula)
                    pMercato: book.lay != null && book.lay > 1 ? 1 / book.lay : null,
                }),
                vivo: quotaViva(t.price, latoDi(t.side), book),
            });
        }
        for (const t of safe?.trades ?? []) {
            if (!aMercato(t) || eGambaDiChiusura(t)) continue;
            const book = libroVivo(t);
            out.push({
                bot: 'safe', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.selection_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: chiusuraViva(t),
                ordine: ordineDi(t),
                dettaglio: dettaglioDi(t as RigaDettagliabile, closesSafe.get(t.id) ?? [], {
                    pMercato: book.lay != null && book.lay > 1 ? 1 / book.lay : null,
                    gamba: t.strategy ?? null,
                }),
                vivo: quotaViva(t.price, latoDi(t.side), book),
            });
        }
        for (const t of mike?.trades ?? []) {
            if (!aMercato(t) || eGambaDiChiusura(t)) continue;
            // 23/09 — «se chiudo ora» anche per Mike, STESSO meccanismo di
            // Omega/Safe (`libroVivo`/`chiusuraViva`/`quotaViva`), nessuna
            // formula duplicata. Una riga STORICA senza `market_id`/
            // `selection_id` (scritta prima dell'11/09) torna qui `null` da
            // sola: `prezzoVivo` e' fail-closed su id mancanti, mai una quota
            // indovinata da un'altra selezione.
            const book = libroVivo(t);
            out.push({
                bot: 'mike', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.selection_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: chiusuraViva(t),
                ordine: ordineDi(t),
                dettaglio: dettaglioDi(
                    { ...t, pnl: t.pnl ?? 0 } as RigaDettagliabile,
                    (closesMike.get(t.id) ?? []).map((c) => ({ ...c, pnl: c.pnl ?? 0 })) as RigaDettagliabile[],
                    { gamba: t.role ?? t.strategy ?? null },
                ),
                vivo: quotaViva(t.price, latoDi(t.side), book),
            });
        }
        // ── LE POSIZIONI APERTE DEI QUATTRO BOT TENNIS ──────────────────────
        // Righe di `tennis_live_orders` con `source` = la chiave del bot. La
        // tabella NON ha una colonna di responsabilita' e NON si inventa qui:
        // una liability calcolata dal browser sarebbe una seconda verita'
        // accanto a quella del servizio. `null` = non lo sappiamo.
        for (const o of tennisOrdini) {
            if (!ordineTennisAperto(o)) continue;
            const bot = o.source;
            if (bot == null || !isBotTennis(bot as Bot)) continue;
            const eventId = String(o.event_id ?? '');
            if (!eventId) continue;
            const feed = feedPerEvento.get(eventId)?.payload as PartitaFeedLike | undefined;
            out.push({
                bot: bot as Bot, id: o.id, eventId,
                partita: feed?.event_name ?? eventId,
                // `tennis_live_orders` porta il `selection_id`, non il nome:
                // scriverne uno di fantasia sarebbe peggio di non scriverlo.
                selezione: null,
                lato: latoDi(o.side), prezzo: o.price ?? null, size: o.size ?? null,
                // 17/09 — la responsabilità c'era già nella riga: è `size` su un
                // BACK e `(quota − 1) × size` su un LAY. Non è una seconda
                // verità accanto a quella del servizio, è l'aritmetica
                // dell'exchange, la stessa di Omega, Safe e Mike.
                liability: liabilityTennis(o), modalita: modalitaDi(o.mode),
                piazzataAt: o.placed_at ?? o.updated_at ?? '',
                chiusura: null,
                ordine: ordineDi({
                    status: o.status, side: o.side, price: o.price ?? null, size: o.size ?? null,
                    size_requested: o.size ?? null, size_matched: o.size_matched ?? null,
                    size_remaining: o.size_remaining ?? null,
                    avg_price_matched: o.average_price_matched ?? null,
                    betfair_updated_at: o.updated_at ?? null, meta: null,
                }),
                // `tennis_live_orders` non porta né `meta`, né minuto/punteggio
                // all'ingresso, né il modello: il dettaglio dei tre bot calcio
                // qui NON esiste, e si dichiara assente invece di riempirlo.
                dettaglio: null,
                vivo: null,
            });
        }
        // le più recenti in cima: è l'ordine in cui un trader le cerca
        out.sort((a, b) => Date.parse(b.piazzataAt) - Date.parse(a.piazzataAt));
        return out;
    }, [omegaTrades, safe?.trades, mike?.trades, tennisOrdini, feedPerEvento, chiusuraViva, libroVivo]);

    const proposteVista = useMemo<PropostaVista[]>(() => ordinaProposte(
        // 17/09: le proposte di OPPORTUNITA' stanno nella stessa coda ma sono
        // un'altra cosa (un'apertura). Qui restano solo le CHIUSURE.
        proposte.filter((r) => !isPropostaOpportunita(r)),
    ).map((pr) => {
        const p = pr.payload;
        const riga = feedPerEvento.get(String(p.event_id));
        const payload = (riga?.payload ?? null) as Parameters<typeof prezzoVivo>[0];
        const vivo = prezzoVivo(payload, p.market_id, p.selection_id, p.side ?? null);
        // eta' del PREZZO: `odds_ts_ms` se c'e', altrimenti l'eta' della riga.
        // Mai zero per «non lo so».
        const odds = (payload as { odds_ts_ms?: number | null } | null)?.odds_ts_ms;
        const etaQuoteS = typeof odds === 'number' && Number.isFinite(odds) && odds > 0
            ? Math.max(0, Math.round((nowMs - odds) / 1000))
            : etaSecondi(riga?.updated_at ?? null, nowMs);
        // IL VALORE VIVO, non quello della fotografia: e' lo stesso numero che
        // la colonna delle posizioni mostra per la stessa posizione.
        const t = (safe?.trades ?? []).find((x) => Number(x.id) === Number(p.trade_id));
        const bloccabileOra = t ? (chiusuraViva({
            side: t.side, price: t.price, size: t.size,
            meta: (t.meta ?? null) as Record<string, unknown> | null,
            event_id: t.event_id, market_id: t.market_id, selection_id: t.selection_id,
        })?.bloccabile ?? null) : null;
        return { proposta: pr, vivo, etaQuoteS, bloccabileOra };
    }), [proposte, feedPerEvento, nowMs, safe?.trades, chiusuraViva]);

    /** le proposte di OPPORTUNITA' (apertura), con l'abbinabile e l'eta' del
     *  prezzo presi dal feed VIVO: la fotografia della proposta serve solo a
     *  sapere su cosa il bot ha deciso. */
    const proposteOpportunita = useMemo<PropostaOppVista[]>(() => (proposte as unknown as {
        id: number; kind: string; status: string; payload: Record<string, unknown>;
        created_at?: string | null; updated_at?: string | null;
    }[])
        .filter((r) => isPropostaOpportunita(r))
        .map((r) => {
            const pr = r as unknown as PropostaOpportunita;
            const p = pr.payload;
            const riga = feedPerEvento.get(String(p.event_id));
            const payload = (riga?.payload ?? null) as Parameters<typeof prezzoVivo>[0];
            const vivo = prezzoVivo(payload, p.market_id ?? null, p.selection_id ?? null,
                                    (p.side ?? null) as 'back' | 'lay' | null);
            const odds = (payload as { odds_ts_ms?: number | null } | null)?.odds_ts_ms;
            const etaQuoteS = typeof odds === 'number' && Number.isFinite(odds) && odds > 0
                ? Math.max(0, Math.round((nowMs - odds) / 1000))
                : etaSecondi(riga?.updated_at ?? null, nowMs);
            // 18/09 — COMBO: se il payload porta `legs[]` (contratto in arrivo
            // da un altro costruttore, campo opzionale), calcola il prezzo
            // vivo di OGNI gamba dagli stessi payload della giornata già in
            // memoria — nessuna lettura nuova. Nessun `legs` → `undefined`,
            // nessun effetto su nulla di quello che gira oggi.
            const legs = (p as { legs?: Parameters<typeof prezzoVivoPerGamba>[0] }).legs;
            const prezziGamba = legs && legs.length
                ? prezzoVivoPerGamba(legs, tuttiIPayloadOggi)
                : undefined;
            // 18/09 (raccordo, R2) — `prezzoVivoGamba` = LO STESSO `vivo.prezzo`
            // di sopra (gamba sola); `prezziViviGambe` = `prezziGamba`
            // riconciliato nel tipo che la scheda/RPC si aspettano (adattatore,
            // nessun ricalcolo).
            return {
                proposta: pr, abbinabileOra: vivo.abbinabile, etaQuoteS, prezziGamba,
                prezzoVivoGamba: vivo.prezzo, prezziViviGambe: prezziViviGambeDa(prezziGamba),
            };
        }), [proposte, feedPerEvento, nowMs, tuttiIPayloadOggi]);

    const ricaricaProposte = useCallback(async () => {
        const lettoMs = Date.now();
        try {
            const v = await fetchProposte();
            setRigheProp((p) => applicaBloccoDb(p, 'safe', v ?? [], lettoMs));
        } catch { /* il giro riprova */ }
    }, []);

    /**
     * 18/09 (raccordo, R2) — «il prezzo che l'utente vede è quello che
     * parte»: manda ESATTAMENTE `prezzoVisto`/`legsPricesVisti` che la
     * scheda mostrava al clic (`SchedaPropostaOpportunita.onPiazza`),
     * inoltrati tali e quali a `approvaPropostaOpportunita` (`lib/safeBot.ts`).
     * RETROCOMPATIBILE: se la migrazione `safe_request_approve_prezzo_
     * visto_2026-09-18.sql` non è applicata, la RPC rifiuta i parametri
     * nuovi (PostgREST "function ... does not exist" / PGRST202) — UN SOLO
     * ripiego automatico sul solo `p_id` (mai una doppia approvazione),
     * dichiarato in `avvisoOpportunita`.
     */
    const piazzaOpportunita = useCallback(async (
        id: number, prezzoVisto?: number, legsPricesVisti?: PrezziViviGambe, slippagePctVisto?: number,
    ) => {
        const opts = { prezzoVisto, legsPricesVisti, slippagePct: slippagePctVisto };
        const haOptsNuovi = prezzoVisto != null
            || (legsPricesVisti != null && Object.values(legsPricesVisti).some((v) => v != null));
        try {
            await approvaPropostaOpportunita(id, opts);
            setAvvisoOpportunita(null);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            if (haOptsNuovi && /PGRST202|schema cache|does not exist|not find the function/i.test(msg)) {
                await approvaPropostaOpportunita(id); // ripiego UNICO, solo p_id
                setAvvisoOpportunita('prezzo visto non inviato: migrazione non applicata');
            } else {
                throw e;
            }
        }
        svegliaBot('safe', 'approvazione'); // STADIO C — DOPO la scrittura riuscita, mai prima
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const rifiutaOpportunita = useCallback(async (id: number) => {
        await ignoraProposta(id, 'opportunita rifiutata dall’operatore');
        svegliaBot('safe', 'approvazione');
        await ricaricaProposte();
    }, [ricaricaProposte]);


    const approva = useCallback(async (id: number) => {
        await approvaProposta(id);
        svegliaBot('safe', 'approvazione');
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const ignora = useCallback(async (id: number) => {
        await ignoraProposta(id);
        svegliaBot('safe', 'approvazione');
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const ricaricaProposteOmega = useCallback(async () => {
        const lettoMs = Date.now();
        try {
            const v = await fetchProposteOmega();
            setRigheProp((p) => applicaBloccoDb(p, 'omega', v ?? [], lettoMs));
            setErroreProposteOmega(null);
        } catch (e) {
            setRigheProp((p) => applicaBloccoDb(p, 'omega', [], lettoMs));
            setErroreProposteOmega(e instanceof Error ? e.message : String(e));
        }
    }, []);

    const approvaOmega = useCallback(async (id: number) => {
        await approvaPropostaOmega(id);
        svegliaBot('omega', 'approvazione'); // STADIO C — DOPO la scrittura riuscita, mai prima
        await ricaricaProposteOmega();
    }, [ricaricaProposteOmega]);

    const ignoraOmega = useCallback(async (id: number) => {
        await ignoraPropostaOmega(id);
        svegliaBot('omega', 'approvazione');
        await ricaricaProposteOmega();
    }, [ricaricaProposteOmega]);

    // ── OPERAZIONI PER PARTITA ───────────────────────────────────────────────
    const operazioni = useMemo(() => {
        const m = new Map<string, OperazionePartita[]>();
        const agg = (bot: Bot, t: {
            id: number; event_id: string; selection_name?: string | null; runner_name?: string | null;
            side?: string | null; price?: number | null; size?: number | null; status: string;
            pnl?: number | null; mode?: string | null; placed_at: string;
            strategy?: string | null; phase?: string | null; role?: string | null;
            // C.12b — colonne della migrazione del 16/09 (assenti finche' non
            // e' applicata) e `meta`, che porta le stesse cose come nota
            size_requested?: number | null; size_matched?: number | null;
            size_remaining?: number | null; avg_price_matched?: number | null;
            betfair_updated_at?: string | null; meta?: Record<string, unknown> | null;
            // 17/09 — servono al dettaglio (stato ricco, P&L vivo, modello)
            minute_at_entry?: number | null; score_at_entry?: string | null;
            closes_trade_id?: number | null; market_id?: string | null;
            selection_id?: number | null;
            // 18/09 (raccordo, R1) — presente solo su Omega/Safe (colonna vera)
            liability?: number | null;
        }, closes: readonly (Parameters<typeof ordineDi>[0] & { id: number })[] = []) => {
            if (isErrorRow(t.status)) return;           // non e' un'operazione
            const k = String(t.event_id);
            // 18/09 (raccordo, R1) — quota di ADESSO sullo stesso lato
            // dell'ingresso e "se chiudo ora": STESSE `libroVivo()`/
            // `quotaViva()`/`chiusuraViva()` gia' usate per `PosizioneAperta`.
            // 23/09 — Mike porta `market_id`/`selection_id` come Omega/Safe;
            // su una riga STORICA senza i due campi queste tornano `null` da
            // sole (`prezzoVivo` fail-closed su id mancanti): nessuna seconda
            // condizione per bot, nessun numero inventato.
            const book = libroVivo({ event_id: t.event_id, market_id: t.market_id ?? null, selection_id: t.selection_id ?? null });
            const lato = latoDi(t.side);
            const vivo = quotaViva(t.price ?? null, lato, book);
            const chius = chiusuraViva({
                side: t.side ?? null, price: t.price ?? null, size: t.size ?? null,
                meta: t.meta ?? null, event_id: t.event_id,
                market_id: t.market_id ?? null, selection_id: t.selection_id ?? null,
            });
            const riga: OperazionePartita = {
                bot, id: t.id,
                selezione: t.selection_name ?? t.runner_name ?? null,
                lato: latoDi(t.side), prezzo: t.price ?? null, size: t.size ?? null,
                stato: t.status,
                // ⚠️ REVIEW 15/09 — un'operazione NON ANCORA REGOLATA ha
                // `pnl = 0` sulla riga, e la scheda lo mostrava come «0,00 €»
                // in verde: uno zero che sembra un pareggio, mentre il
                // risultato non esiste ancora. Prima della regolazione il P&L
                // e' IGNOTO, e si scrive «—».
                //
                // 23/09 - il numero della riga e' il NETTO DELL'OPERAZIONE:
                // apertura + tutte le gambe di chiusura regolate. Prima era il
                // P&L della sola apertura: su un cash out (+0,45 / -0,25) la
                // riga diceva +0,45 invece di +0,20. Una gamba ancora viva =
                // risultato non definitivo = '-' (`nettoCicloChiuso`).
                pnl: nettoCicloChiuso(t, closes),
                modalita: modalitaDi(t.mode), at: t.placed_at,
                quale: t.strategy ?? t.phase ?? t.role ?? null,
                ordine: {
                    status: t.status, side: t.side ?? null,
                    price: t.price ?? null, size: t.size ?? null,
                    size_requested: t.size_requested ?? null,
                    size_matched: t.size_matched ?? null,
                    size_remaining: t.size_remaining ?? null,
                    avg_price_matched: t.avg_price_matched ?? null,
                    betfair_updated_at: t.betfair_updated_at ?? null,
                    meta: t.meta ?? null,
                },
                // 17/09 — LO STESSO DETTAGLIO della scheda originale del bot,
                // dalla stessa riga già in memoria: stato ricco, P&L vivo,
                // minuto/punteggio all'ingresso, green-up, P del modello.
                dettaglio: dettaglioDi(
                    {
                        id: t.id, event_id: t.event_id, side: String(t.side ?? ''),
                        status: t.status, pnl: t.pnl ?? 0, price: t.price ?? null,
                        size: t.size ?? null, placed_at: t.placed_at,
                        phase: t.phase ?? null, meta: t.meta ?? null,
                        minute_at_entry: t.minute_at_entry ?? null,
                        score_at_entry: t.score_at_entry ?? null,
                        closes_trade_id: t.closes_trade_id ?? null,
                    },
                    closes as unknown as RigaDettagliabile[],
                    { gamba: t.strategy ?? t.phase ?? t.role ?? null },
                ),
                marketId: t.market_id ?? null,
                selectionId: t.selection_id ?? null,
                liability: t.liability ?? null,
                vivo, etaQuoteS: etaSecondi(feedPerEvento.get(k)?.updated_at ?? null, nowMs),
                chiusura: chius,
                chiusureOrdini: closes.map((c) => ordineDi(c)),
                eventId: k,
                chiudeId: t.closes_trade_id ?? null,
            };
            const arr = m.get(k);
            if (arr) arr.push(riga); else m.set(k, [riga]);
        };
        const closesOmega = chiusureCollegate(omegaTrades);
        const closesSafe = chiusureCollegate(safe?.trades ?? []);
        const closesMike = chiusureCollegate(mike?.trades ?? []);
        // 23/09 - una gamba di chiusura con la sua apertura presente NON e' una
        // riga propria (sta annidata sotto l'apertura, il suo P&L nel netto);
        // un'orfana resta visibile come riga sua (`chiusuraConApertura`).
        const idsOmega = new Set(omegaTrades.map((t) => Number(t.id)));
        const idsSafe = new Set((safe?.trades ?? []).map((t) => Number(t.id)));
        const idsMike = new Set((mike?.trades ?? []).map((t) => Number(t.id)));
        for (const t of omegaTrades) {
            if (chiusuraConApertura(t, idsOmega)) continue;
            agg('omega', t, closesOmega.get(t.id) ?? []);
        }
        for (const t of safe?.trades ?? []) {
            if (chiusuraConApertura(t, idsSafe)) continue;
            agg('safe', t, closesSafe.get(t.id) ?? []);
        }
        for (const t of mike?.trades ?? []) {
            if (chiusuraConApertura(t, idsMike)) continue;
            agg('mike', t, (closesMike.get(t.id) ?? []).map((c) => ({ ...c, pnl: c.pnl ?? 0 })));
        }
        // ── GLI ORDINI DEI QUATTRO BOT TENNIS SULLA PARTITA ─────────────────
        // Non passano da `agg`: per un ordine tennis il P&L NON si legge dallo
        // stato flumine (`EXECUTION_COMPLETE` vuol dire «abbinato tutto», non
        // «regolato») ma da `settled_at`. Prima del regolamento il risultato e'
        // IGNOTO e si scrive «—», mai «0,00 €».
        for (const o of tennisOrdini) {
            if (isErrorRow(o.status)) continue;
            const bot = o.source;
            if (bot == null || !isBotTennis(bot as Bot)) continue;
            const k = String(o.event_id ?? '');
            if (!k) continue;
            // 18/09 (raccordo, R1) — STESSE `libroVivo()`/`quotaViva()`/
            // `chiusuraViva()`: `tennis_live_orders` PORTA `market_id`/
            // `selection_id` (colonne NOT NULL, `lib/liveOrders.ts:78-79`),
            // quindi qui il prezzo vivo e' calcolabile per davvero (a
            // differenza di Mike). Nessuna seconda formula.
            const book = libroVivo({ event_id: k, market_id: o.market_id, selection_id: o.selection_id });
            const latoO = latoDi(o.side);
            const vivoO = quotaViva(o.price ?? null, latoO, book);
            const chiusO = chiusuraViva({
                side: o.side ?? null, price: o.price ?? null, size: o.size ?? null,
                meta: null, event_id: k, market_id: o.market_id, selection_id: o.selection_id,
            });
            const riga: OperazionePartita = {
                bot: bot as Bot, id: o.id, selezione: null,
                lato: latoDi(o.side), prezzo: o.price ?? null, size: o.size ?? null,
                stato: o.status,
                pnl: o.settled_at != null && typeof o.pnl === 'number' ? o.pnl : null,
                modalita: modalitaDi(o.mode),
                at: o.placed_at ?? o.updated_at ?? '',
                quale: null,
                ordine: {
                    status: o.status, side: o.side ?? null,
                    price: o.price ?? null, size: o.size ?? null,
                    size_requested: o.size ?? null,
                    size_matched: o.size_matched ?? null,
                    size_remaining: o.size_remaining ?? null,
                    avg_price_matched: o.average_price_matched ?? null,
                    betfair_updated_at: o.updated_at ?? null,
                    meta: null,
                },
                // v. `posizioni`: le righe tennis non portano `meta`, ingresso
                // né modello. Assente si scrive, non si riempie.
                dettaglio: null,
                marketId: o.market_id ?? null,
                selectionId: o.selection_id ?? null,
                liability: liabilityTennis(o),
                vivo: vivoO,
                etaQuoteS: etaSecondi(feedPerEvento.get(k)?.updated_at ?? null, nowMs),
                chiusura: chiusO,
                // nessuna catena di chiusura per un ordine tennis (audit F4,
                // PARTE 1): ogni riga e' la propria posizione.
                chiusureOrdini: [],
                eventId: k,
                chiudeId: null,
            };
            const arr = m.get(k);
            if (arr) arr.push(riga); else m.set(k, [riga]);
        }
        for (const arr of m.values()) arr.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
        return m;
    }, [omegaTrades, safe?.trades, mike?.trades, tennisOrdini, feedPerEvento, nowMs, libroVivo, chiusuraViva]);

    // ── B16 (24/09): IL «CHIUDI» DI UNA RIGA, PER SINGOLO BOT ───────────────
    // Prima: `requestSafe('cashout', {trade_id})` per QUALUNQUE bot - su una
    // riga di Omega o di Mike non chiudeva niente, o chiudeva la riga di Safe
    // con lo stesso id. Ora la richiesta va alla coda DEL BOT DELLA RIGA
    // (`chiudiRiga.ts`), e l'esito si segue in due modi:
    //   · dal CANALE del bot (`*_posizioni`, gia' sottoscritti qui sopra): la
    //     riga che cambia (gamba di chiusura nuova, coperta, regolata) = eseguita;
    //   · dalla coda del bot riletta per id (ripiego, SOLO mentre una richiesta
    //     e' aperta, ogni 2 s, mai piu' di 3 minuti): presa in carico,
    //     rifiutata col motivo scritto dal servizio.
    const [chiusureRighe, setChiusureRighe] = useState<Record<string, StatoChiusuraRiga & { firma: string }>>({});
    const chiusureRigheRef = useRef(chiusureRighe);
    chiusureRigheRef.current = chiusureRighe;

    const trovaOperazione = useCallback((bot: Bot, id: number, eventId: string | null) => {
        const cerca = (lista: readonly OperazionePartita[] | undefined) =>
            (lista ?? []).find((x) => x.bot === bot && x.id === id);
        const diretta = eventId ? cerca(operazioni.get(eventId)) : undefined;
        if (diretta) return diretta;
        for (const lista of operazioni.values()) {
            const o = cerca(lista);
            if (o) return o;
        }
        return undefined;
    }, [operazioni]);

    const chiudi = useCallback(async (riga: RigaDaChiudere) => {
        const chiave = `${riga.bot}:${riga.id}`;
        // un clic alla volta per riga: una seconda richiesta mentre la prima e'
        // aperta raddoppierebbe la chiusura (il servizio la rifiuterebbe, ma
        // non si manda nemmeno)
        const prima = chiusureRigheRef.current[chiave];
        if (prima && !prima.richiestaChiusa && prima.faseRichiesta !== 'rifiutata') return;
        const o = trovaOperazione(riga.bot, riga.id, riga.eventId);
        const firma = firmaRiga(o?.stato ?? riga.stato, o?.chiusureOrdini?.length ?? 0);
        const inviataMs = Date.now();
        try {
            const { bot, requestId } = await inviaChiusura(riga);
            setChiusureRighe((p) => ({
                ...p,
                [chiave]: {
                    bot, id: riga.id, requestId, faseRichiesta: 'inviata', richiestaChiusa: false,
                    motivo: null, rigaCambiata: false, inviataMs, firma,
                },
            }));
            svegliaBot(bot, 'comando'); // STADIO C — DOPO la scrittura riuscita, mai prima
        } catch (e) {
            setChiusureRighe((p) => ({
                ...p,
                [chiave]: {
                    bot: riga.bot, id: riga.id, requestId: null, faseRichiesta: 'rifiutata',
                    richiestaChiusa: true, rigaCambiata: false, inviataMs, firma,
                    motivo: `non inviata: ${e instanceof Error ? e.message : String(e)}`,
                },
            }));
        }
    }, [trovaOperazione]);

    // (a) il CANALE: la riga cambia nel senso di una chiusura -> eseguita
    useEffect(() => {
        const aperte = Object.entries(chiusureRigheRef.current).filter(([, s]) => !s.rigaCambiata);
        if (!aperte.length) return;
        const cambiate: string[] = [];
        for (const [k, s] of aperte) {
            const o = trovaOperazione(s.bot, s.id, null);
            if (o && cambiataPerChiusura(s.firma, o.stato, o.chiusureOrdini?.length ?? 0)) cambiate.push(k);
        }
        if (!cambiate.length) return;
        setChiusureRighe((p) => {
            const n = { ...p };
            for (const k of cambiate) if (n[k]) n[k] = { ...n[k], rigaCambiata: true };
            return n;
        });
    }, [trovaOperazione, chiusureRighe]);

    // (b) il RIPIEGO: la coda del bot riletta per id, solo mentre serve
    const daRileggere = useMemo(
        () => Object.entries(chiusureRighe)
            .filter(([, s]) => richiestaDaRileggere(s, nowMs)).map(([k]) => k).sort().join(','),
        [chiusureRighe, nowMs],
    );
    useEffect(() => {
        if (!daRileggere) return;
        let vivo = true;
        const giro = async () => {
            for (const k of daRileggere.split(',')) {
                const s = chiusureRigheRef.current[k];
                if (!s || s.requestId == null || isBotTennis(s.bot)) continue;
                const botC = s.bot as 'omega' | 'safe' | 'mike';
                try {
                    const r = await LETTURA[botC](s.requestId);
                    if (!vivo || !r) continue;
                    const f = faseDaRichiesta(botC, r);
                    setChiusureRighe((p) => (p[k] ? {
                        ...p,
                        [k]: { ...p[k], faseRichiesta: f.fase, richiestaChiusa: f.chiusa, motivo: f.motivo ?? p[k].motivo },
                    } : p));
                } catch { /* il giro dopo riprova: il comando vero e' gia' scritto */ }
            }
        };
        void giro();
        const t = window.setInterval(() => { void giro(); }, 2_000);
        return () => { vivo = false; window.clearInterval(t); };
    }, [daRileggere]);

    const statoChiusuraRiga = useCallback((bot: Bot, id: number): StatoChiusuraRiga | null => {
        const s = chiusureRighe[`${bot}:${id}`];
        if (!s) return null;
        return statoConScadenza(s, nowMs);
    }, [chiusureRighe, nowMs]);

    // ── «SE CHIUDO IO, IL BOT DEVE SAPERLO» (16/09) ─────────────────────────
    // Lo stato lo DICHIARA il servizio: Safe scrivendo `meta.chiuso_dall_utente`
    // sulle righe (sopravvive al riavvio), Omega pubblicando l'elenco degli
    // eventi in `stats.eventi_chiusi_dall_utente`. La pagina non lo deduce mai
    // da «non ci sono piu' righe vive», che vuol dire un'altra cosa.
    const eventiChiusiOmega = useMemo<string[]>(() => {
        const raw = (omega?.control?.stats as { eventi_chiusi_dall_utente?: unknown } | null | undefined)
            ?.eventi_chiusi_dall_utente;
        return Array.isArray(raw) ? raw.map((x) => String(x)).filter((x) => x.trim() !== '') : [];
    }, [omega?.control?.stats]);

    const chiusuraSafe = useMemo(
        () => eventiChiusiDalleRighe(safe?.trades ?? []),
        [safe?.trades],
    );

    const statoChiusura = useCallback((eventId: string): StatoChiusuraEvento => {
        const m = chiusuraSafe.get(String(eventId ?? ''));
        if (m) return { chiusa: true, fonte: 'righe', marcatore: m };
        return { chiusa: false, fonte: null, marcatore: null };
    }, [chiusuraSafe]);

    const cashOutEvento = useCallback(async (eventId: string) => {
        await cashOutEventoSafe(eventId);
        svegliaBot('safe', 'approvazione'); // STADIO C — DOPO la scrittura riuscita, mai prima
        ricarica();
    }, [ricarica]);

    const riprendiEvento = useCallback(async (eventId: string) => {
        await riprendiEventoSafe(eventId);
        ricarica();
    }, [ricarica]);

    // ── LA CATENA ────────────────────────────────────────────────────────────
    const schermo = useMemo(() => {
        const spinte = (['omega', 'safe', 'mike'] as const)
            .map((b) => ultimoPush[b]).filter((v): v is number => v != null);
        return catenaSchermo({
            feedMs: scanStatus?.updated_at ? nowMs - Date.parse(scanStatus.updated_at) : null,
            // la spinta PIÙ VECCHIA fra i bot vivi: se uno tace, la pagina è
            // vecchia quanto lui
            pushMs: spinte.length ? nowMs - Math.min(...spinte) : null,
            letturaMs: lettoAlle == null ? null : nowMs - lettoAlle,
        });
    }, [scanStatus?.updated_at, ultimoPush, lettoAlle, nowMs]);

    const ultimaCatena = useMemo(() => {
        const vivi = (safe?.trades ?? []).filter((t) => t.mode === 'live');
        // la più recente che PORTA i tempi: una senza non dice niente
        const conTempi = vivi.find((t) => {
            const m = (t.meta ?? {}) as Record<string, unknown>;
            return m.tempi != null || m.esecuzione != null;
        }) ?? vivi[0] ?? null;
        const m = (conTempi?.meta ?? {}) as Record<string, unknown>;
        return {
            salti: catenaOperazione(
                m.tempi as TempiTrade | null,
                m.esecuzione as EsecuzioneTrade | null,
                (m.t6_fill_ms as number | null) ?? null,
            ),
            trade: conTempi?.id ?? null,
            evento: conTempi?.event_name ?? null,
        };
    }, [safe?.trades]);

    // ── LA GIORNATA, dagli AGGREGATI dei tre servizi ─────────────────────────
    const giornataSoldi = useMemo(() => {
        const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
        const oA = omega?.aggregates ?? null;
        const sA = safe?.aggregates ?? null;
        const mA = mike?.aggregates ?? null;
        const perBot: Record<Bot, number | null> = {
            omega: n(oA?.realized_today),
            safe: n(sA?.realized_today),
            mike: n(mA?.realized_today),
            // TENNIS — il P&L del giorno lo da' il database
            // (`get_tennis_bot_daily`, p_mode='live'), NETTO di commissione e
            // per bot. Qui non si somma niente a mano e non si tocca il paper:
            // sono due conti separati, e separati restano.
            tennis_scalper: pnlTennisDi(tennisOggi, 'tennis_scalper'),
            tennis_pro: pnlTennisDi(tennisOggi, 'tennis_pro'),
            tennis_flb: pnlTennisDi(tennisOggi, 'tennis_flb'),
            tennis_swing: pnlTennisDi(tennisOggi, 'tennis_swing'),
        };
        const liab = [n(oA?.open_liability), n(sA?.open_liability), n(mA?.open_liability)]
            .filter((v): v is number => v != null);
        const r2 = (x: number) => Math.round(x * 100) / 100;

        // ⚠️ IL REALIZZATO DELLA BARRA E' QUELLO CON I SOLDI VERI, E BASTA.
        //
        // Prima si sommava `realized_today` dei tre servizi. Ma ogni servizio
        // pubblica il PROPRIO (`bot_service.py:5445`: `aggregates(mode=mode)`),
        // e oggi Safe e' in live mentre Omega e Mike sono in prova: la somma
        // metteva insieme un numero vero e due simulati. Il risultato non era
        // ne' live ne' paper — il 14/09 diceva -4,83 € mentre il tennis con
        // soldi veri aveva guadagnato +0,41 €, e la barra andava all'indietro
        // per colpa di perdite finte.
        const realizzato = realizzatoOggi.live.totale;
        const realizzatoPaper = realizzatoOggi.paper.totale;

        // CONTROPROVA sul tennis: il server (`get_safe_daily` con p_mode=live)
        // e il conto fatto qui sulle righe devono dire la stessa cosa. Se non
        // la dicono NON si sceglie il piu' bello: lo si DICHIARA.
        // ⚠️ REVIEW 15/09 — QUI SI CONFRONTAVANO DUE PERIMETRI DIVERSI: il
        // `pnl_realized` del server è di TUTTI gli sport di Safe, il nostro era
        // il solo tennis. Con il calcio che opera, l'allarme si sarebbe acceso
        // per una differenza che non è un errore. Si confronta tennis con
        // tennis, usando il `by_sport` che il server MANDA GIÀ.
        const serverLive = n((safeOggi?.by_sport as Record<string, { pnl?: number }> | null)
            ?.tennis?.pnl);
        const nostroSafeLive = realizzatoOggi.live.perSport.tennis;
        const discordanza = (serverLive != null && nostroSafeLive != null
            && Math.abs(serverLive - nostroSafeLive) > 0.01)
            ? `il servizio dice ${fmtMoney(serverLive)} e la pagina ${fmtMoney(nostroSafeLive)}`
            : null;

        return {
            realizzato,
            realizzatoPaper,
            discordanza,
            perBot,
            liability: liab.length ? r2(liab.reduce((a, b) => a + b, 0)) : null,
            /** per sport, SOLDI VERI (server, `p_mode='live'`) */
            perSport: safeOggi?.by_sport ?? null,
            /** per sport, in PROVA. Mai sommato al precedente. */
            perSportPaper: safeOggiPaper?.by_sport ?? null,
            // ⚠️ REVIEW 15/09 — QUI C'ERANO I CONTATORI DI `get_safe_daily`,
            // che legge la SOLA tabella di Safe, accanto a un realizzato
            // calcolato sulle righe dei TRE bot. Le operazioni di Omega e Mike
            // non erano assenti: valevano zero dentro un totale presentato
            // come quello della giornata. Adesso numeri e contatori nascono
            // dalle stesse righe e non possono divergere; `safeOggi` resta
            // dov'è utile — la controprova (`discordanza`) e il per-sport.
            //
            // 18/09 (raccordo, R5) — CONTATORI VERI. `realizzatoOggi.live.*`
            // conta le righe SINTETICHE (1 per bot tennis + 1 per voce
            // manuale) come UNA operazione ciascuna: falso per i bot tennis
            // (la RPC `get_tennis_bot_daily` porta `vinti`/`persi`/`ordini`
            // REALI) e per il manuale (nessun esito per singola giocata dal
            // backend: resta fuori dai contatori, mai finto). Si tolgono i
            // contributi sintetici e si sommano i conteggi veri, SENZA
            // toccare `realizzatoGiornata` (formula certificata, invariata).
            ...(() => {
                const sintTennisLive = oggiRighe.tennisBotRighe.filter((r) => r.mode === 'live');
                const sintTennisPaper = oggiRighe.tennisBotRighe.filter((r) => r.mode === 'paper');
                const sintManuale = [...oggiRighe.manualeSitoRighe, ...oggiRighe.manualeAppRighe];
                const conta = (righe: readonly RigaComponente[], esito: 'won' | 'lost') =>
                    righe.filter((r) => r.status === esito).length;
                const sommaVero = (righe: readonly TennisBotDailyRow[], chiave: 'vinti' | 'persi' | 'ordini') =>
                    righe.reduce((s, r) => s + (typeof r[chiave] === 'number' ? r[chiave] : 0), 0);
                return {
                    operazioni: realizzatoOggi.live.righe - sintTennisLive.length - sintManuale.length
                        + sommaVero(tennisOggi, 'ordini'),
                    vinte: realizzatoOggi.live.vinte - conta(sintTennisLive, 'won') - conta(sintManuale, 'won')
                        + sommaVero(tennisOggi, 'vinti'),
                    perse: realizzatoOggi.live.perse - conta(sintTennisLive, 'lost') - conta(sintManuale, 'lost')
                        + sommaVero(tennisOggi, 'persi'),
                    operazioniPaper: (realizzatoOggi.paper.righe - sintTennisPaper.length
                        + sommaVero(tennisOggiPaper, 'ordini')) || null,
                    notaContatori: sintManuale.length > 0
                        ? 'le due voci manuali (sito/app) entrano nel realizzato ma non nei contatori vinte/perse: il backend non da un esito per singola giocata'
                        : null,
                };
            })(),
        };
    }, [omega?.aggregates, safe?.aggregates, mike?.aggregates, safeOggi, safeOggiPaper,
        tennisOggi, tennisOggiPaper, realizzatoOggi, oggiRighe]);

    const feedEtaS = etaSecondi(scanStatus?.updated_at, nowMs);
    const fonteScanEtaS = ultimoScanLocaleMs == null
        ? null : Math.max(0, Math.round((nowMs - ultimoScanLocaleMs) / 1000));
    const fonteScan: 'locale' | 'database' = freschezza(fonteScanEtaS) === 'fresca' ? 'locale' : 'database';

    // C6 b - fonte ed eta' delle righe per bot (posizioni + proposte)
    const fonteRighe = useMemo(() => {
        const di = (bot: 'omega' | 'safe' | 'mike'): { fonte: FonteRiga; etaS: number | null } => {
            const { canaleMs, dbMs } = ultimeNotizie([righePos, righeProp], bot);
            const locale = canaleMs != null && (dbMs == null || canaleMs > dbMs);
            const at = locale ? canaleMs : dbMs;
            return {
                fonte: locale ? 'locale' : 'database',
                etaS: at == null ? null : Math.max(0, Math.round((nowMs - at) / 1000)),
            };
        };
        return { omega: di('omega'), safe: di('safe'), mike: di('mike') };
    }, [righePos, righeProp, nowMs]);
    const etaRiga = useCallback(
        (bot: 'omega' | 'safe' | 'mike', id: number) => etaRigaDi(righePos, bot, id, nowMs),
        [righePos, nowMs]);

    return {
        caricamento, errore, nowMs,
        giornata, totali,
        obiettivo,
        obiettivoStoricizzato: omega?.goal_snapshot === true,
        realizzato,
        realizzatoOggi,
        soldiGiornata: giornataSoldi,
        targetServizio,
        composizioneOggi, manualeSitoBetfair, salvaObiettivo,
        bots, posizioni, chiuse, registrazioni, copertura,
        freni: safe?.control?.stats?.risk ?? null,
        runner,
        mikeRestingLive: leggiBool(mike?.control?.params, 'live_resting_enabled'),
        mikeEventi,
        schermo, ultimaCatena,
        operazioni,
        proposte: proposteVista,
        proposteOpportunita,
        piazzaOpportunita,
        rifiutaOpportunita, avvisoOpportunita,
        slippagePct, setSlippagePct, approva, ignora, chiudi, statoChiusuraRiga,
        statoChiusura, cashOutEvento, riprendiEvento, eventiChiusiOmega,
        proposteOmega: ordinaProposteOmega(proposteOmega), erroreProposteOmega,
        approvaOmega, ignoraOmega,
        feedSorgente: scanStatus?.payload?.source ?? null,
        feedEtaS,
        feedFreschezza: freschezza(feedEtaS),
        fonteScan,
        fonteRighe,
        etaRiga,
        ricarica,
    };
}

// ------------------------------------------------------------------ utilità

/** Legge un booleano dai parametri di un bot. Assente → `null`, che NON è
 *  `false`: «non lo so» e «spento» sono due cose diverse, e solo una delle due
 *  merita un allarme. */
export function leggiBool(params: Record<string, unknown> | null | undefined, chiave: string): boolean | null {
    const v = params?.[chiave];
    return typeof v === 'boolean' ? v : null;
}

/**
 * `strategy_modes`: con che soldi opera ogni strategia. Si legge dai parametri
 * EFFETTIVI del servizio — sono quelli con cui il bot gira davvero — e solo in
 * ripiego da quelli salvati. Una voce illeggibile si scarta invece di
 * indovinarla: al denaro vero si arriva solo scrivendolo.
 */
export function leggiModiStrategia(
    effettivi: Record<string, unknown> | null | undefined,
    params: Record<string, unknown> | null | undefined,
): Record<string, 'paper' | 'live'> | null {
    for (const src of [effettivi, params]) {
        const v = src?.strategy_modes;
        if (v && typeof v === 'object' && !Array.isArray(v)) {
            const out: Record<string, 'paper' | 'live'> = {};
            for (const [k, m] of Object.entries(v as Record<string, unknown>)) {
                const s = String(m ?? '').toLowerCase();
                if (s === 'live' || s === 'paper') out[k] = s;
            }
            if (Object.keys(out).length) return out;
        }
    }
    return null;
}

/**
 * Lo stesso valore per OGNI bot. I canali locali (47333/47334/47335) esistono
 * solo per i tre servizi del calcio: i quattro bot tennis non ne hanno uno, e
 * «non ne ha» non vuol dire «e' rotto» — il loro battito si legge dal
 * `heartbeat_at` della riga di control, che c'e' sempre.
 */
function perOgniBot<T>(v: T): Record<Bot, T> {
    return {
        omega: v, safe: v, mike: v,
        tennis_scalper: v, tennis_pro: v, tennis_flb: v, tennis_swing: v,
    };
}

/**
 * UN ordine tennis e' ANCORA A MERCATO? Non si guarda lo stato flumine, che
 * dice un'altra cosa (`EXECUTION_COMPLETE` vuol dire «abbinato tutto», non
 * «regolato»): si guarda il REGOLAMENTO. Finche' `settled_at` e' nullo e c'e'
 * qualcosa abbinato o ancora in coda, quella posizione e' aperta.
 */
function ordineTennisAperto(o: TennisBotOrderRow): boolean {
    if (isErrorRow(o.status)) return false;
    if (o.settled_at != null) return false;
    const abbinato = Number(o.size_matched ?? 0);
    const residuo = Number(o.size_remaining ?? 0);
    return (Number.isFinite(abbinato) && abbinato > 0)
        || (Number.isFinite(residuo) && residuo > 0);
}

/**
 * Il P&L NETTO di UN ordine tennis: `pnl` e' lordo, la commissione sta nella
 * sua colonna. `null` = non ancora regolato, che non e' «0,00 €». Se la
 * commissione non e' dichiarata NON si stima: si prende il lordo com'e'.
 */
function pnlNettoTennis(o: TennisBotOrderRow): number | null {
    const lordo = o.pnl;
    if (typeof lordo !== 'number' || !Number.isFinite(lordo)) return null;
    const comm = o.commission;
    const c = typeof comm === 'number' && Number.isFinite(comm) ? comm : 0;
    return Math.round((lordo - c) * 100) / 100;
}

/** Il P&L NETTO di oggi di un bot tennis, dalle righe del database. `null` =
 *  niente di regolato oggi, che non e' «0,00 €». */
function pnlTennisDi(righe: readonly TennisBotDailyRow[], bot: TennisBotKey): number | null {
    let somma: number | null = null;
    for (const r of righe) {
        if (r.bot_key !== bot || r.pnl_netto == null) continue;
        somma = (somma ?? 0) + r.pnl_netto;
    }
    return somma;
}

function modalitaDi(v: unknown): Modalita | null {
    const s = String(v ?? '').toLowerCase();
    return s === 'live' || s === 'paper' ? s : null;
}

function inCorsaDi(v: unknown): boolean {
    return String(v ?? '').toLowerCase() === 'running';
}

function latoDi(v: unknown): 'back' | 'lay' | null {
    const s = String(v ?? '').toLowerCase();
    return s === 'back' || s === 'lay' ? s : null;
}

/**
 * Le varianti di Safe abilitate ad APRIRE. Conta perché oggi il tennis può
 * essere in live mentre il calcio è in paper: «LIVE» da solo mentirebbe.
 * Si legge dai parametri EFFETTIVI del servizio quando ci sono — sono quelli
 * che il bot sta davvero usando — e solo in ripiego da `control.params`.
 */
export function leggiVarianti(
    params: Record<string, unknown> | null | undefined,
    effettivi: Record<string, unknown> | null | undefined,
): string[] | null {
    for (const src of [effettivi, params]) {
        const v = src?.variants;
        if (Array.isArray(v)) {
            const out = v.map((x) => String(x)).filter(Boolean);
            if (out.length) return out;
        }
    }
    return null;
}
