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
    fetchScanRows, subscribeScanRows, fetchScanStatus, subscribeScanStatus,
    type ScanRow, type ScanStatusRow, type CalcioScanPayload,
} from '@/lib/safeStrategyScan';
import {
    fetchOmegaState, fetchOmegaTrades, fetchOmegaEvents,
    type OmegaState, type OmegaTrade, type OmegaStats, type OmegaEvent,
} from '@/lib/omega';
import {
    fetchSafeState, fetchRunnerState, requestSafe, tradeExposureNow,
    cashOutEvento as cashOutEventoSafe, riprendiEventoSafe,
    type SafeState, type SafeRiskStats, type RunnerState,
} from '@/lib/safeBot';
import {
    eventiChiusiDalleRighe, type StatoChiusuraEvento,
} from '@/lib/chiusuraUtente';
import {
    fetchProposteOmega, subscribeProposteOmega, approvaPropostaOmega,
    ignoraPropostaOmega, ordinaProposteOmega, type PropostaUscitaOmega,
} from '@/lib/omegaProposte';
import { hedgeSide, greenPrice, partialLockedPnl } from '@/components/trading/CashOutButton';
import { fetchMikeState, type MikeEvent, type MikeStateView } from '@/lib/mike';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';
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
    costruisciGiornata, soldiPerPartita, marca, totaliGiornata, coperturaControllo,
    etaSecondi, freschezza, freschezzaBattito, realizzatoGiornata, arricchimentoDa,
    type ArricchimentoPartita,
    BOT_TENNIS, isBotTennis,
    type Bot, type GruppoCampionato, type TotaliGiornata, type Freschezza, type PartitaFeedLike, type Sport,
    type Realizzato, type RigaRealizzato,
} from '@/lib/controlRoom';
import { fmtMoney } from '@/lib/format';
import { romeDay, fetchSafeDaily, type DailyRow, type DailyBreakdown } from '@/lib/dailyHistory';
import { isSettled, isErrorRow, type PnlTradeLike } from '@/lib/eventGroups';
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
    isPropostaOpportunita, type PropostaOpportunita,
} from '@/lib/safeBot';

/** una proposta di OPPORTUNITA' con i numeri vivi che la scheda mostra */
export interface PropostaOppVista {
    proposta: PropostaOpportunita;
    /** importo abbinabile ORA sul lato da operare (dal feed), null = ignoto */
    abbinabileOra: number | null;
    /** eta' del prezzo in secondi, null = ignota (fail-closed) */
    etaQuoteS: number | null;
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
    for (const r of righe) {
        const p = r.closes_trade_id;
        if (p == null) continue;
        const k = Number(p);
        const a = m.get(k);
        if (a) a.push(r); else m.set(k, [r]);
    }
    return m;
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
    };
    /** target per partita calcolato dal SERVIZIO (Omega). Se manca, la pagina lo dichiara. */
    targetServizio: number | null;

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
    piazzaOpportunita: (id: number) => Promise<void>;
    rifiutaOpportunita: (id: number) => Promise<void>;
    slippagePct: number;
    setSlippagePct: (v: number) => void;
    approva: (id: number) => Promise<void>;
    ignora: (id: number) => Promise<void>;
    /** chiusura MANUALE di una posizione, per intero: accoda una richiesta
     *  `cashout` sul percorso di sempre. Non passa dal cancelletto — una
     *  chiusura decisa dall'operatore non ha bisogno di essere approvata da
     *  lui stesso. */
    chiudi: (tradeId: number) => Promise<void>;

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

    ricarica: () => void;
}

export function useControlRoom(): ControlRoomVM {
    const [scan, setScan] = useState<ScanRow[]>([]);
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [omega, setOmega] = useState<OmegaState | null>(null);
    const [omegaTrades, setOmegaTrades] = useState<OmegaTrade[]>([]);
    const [safe, setSafe] = useState<SafeState | null>(null);
    const [runner, setRunner] = useState<RunnerState | null>(null);
    const [proposte, setProposte] = useState<PropostaChiusura[]>([]);
    /** le proposte di uscita di OMEGA (migrazione `omega_proposte_uscita`):
     *  finche' non e' applicata la RPC non esiste e l'elenco resta vuoto,
     *  con il motivo dichiarato in `erroreProposteOmega`. */
    const [proposteOmega, setProposteOmega] = useState<PropostaUscitaOmega[]>([]);
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
    const [mike, setMike] = useState<MikeStateView | null>(null);

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

    // ---------------------------------------------------------------- lettura
    const ricarica = useCallback(() => {
        let vivo = true;
        // ⚠️ REVIEW 15/09 — due giri possono sovrapporsi (la ricarica manuale
        // mentre quella periodica e' in volo): vince l'ULTIMO a rispondere,
        // che non e' per forza il piu' recente. Il contatore fa sì che una
        // risposta vecchia non sovrascriva una nuova.
        giroCorrente.current += 1;
        const mioGiro = giroCorrente.current;
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
            if (rOmegaT.status === 'fulfilled') setOmegaTrades(rOmegaT.value);
            if (rSafe.status === 'fulfilled') setSafe(rSafe.value);
            if (rMike.status === 'fulfilled') setMike(rMike.value);
            if (rRunner.status === 'fulfilled') setRunner(rRunner.value);
            if (rProp.status === 'fulfilled') setProposte(rProp.value);
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
    useEffect(() => subscribeScanRows((ev) => {
        setScan((prev) => {
            if (ev.type === 'delete') return prev.filter((r) => r.event_id !== ev.eventId);
            const i = prev.findIndex((r) => r.event_id === ev.row.event_id);
            if (i < 0) return [...prev, ev.row];
            const next = prev.slice();
            next[i] = ev.row;
            return next;
        });
    }), []);

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

    // -------------------------------------------------- proposte in realtime
    // Una proposta di chiusura che comparisse 30 s dopo sarebbe inutile: il
    // prezzo su cui il bot ha deciso non c'e' piu'.
    useEffect(() => subscribeProposte(() => {
        fetchProposte().then(setProposte).catch(() => { /* il giro di ricarica riprova */ });
    }), []);

    // ------------------------------------------ proposte di OMEGA in realtime
    // Stessa regola della Safe: una proposta che comparisse 30 s dopo sarebbe
    // inutile. La prima lettura fallisce finche' la migrazione non e' applicata
    // (la RPC non esiste): il motivo si DICHIARA, non si nasconde.
    useEffect(() => {
        const leggi = () => {
            fetchProposteOmega()
                .then((r) => { setProposteOmega(r); setErroreProposteOmega(null); })
                .catch((e: unknown) => {
                    setProposteOmega([]);
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


    const soldi = useMemo(() => soldiPerPartita([
        ...marca(omegaTrades as unknown as PnlTradeLike[], 'omega'),
        ...marca((safe?.trades ?? []) as unknown as PnlTradeLike[], 'safe'),
        ...marca((mike?.trades ?? []) as unknown as PnlTradeLike[], 'mike'),
    ]), [omegaTrades, safe?.trades, mike?.trades]);

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

    // ── IL REALIZZATO DI OGGI, da TUTTI E TRE i bot ──────────────────────────
    // La barra leggeva `realized_today` di Omega: una vincita del tennis (Safe)
    // non la muoveva. Qui si sommano le righe REGOLATE dei tre bot, tenendo
    // separati soldi veri e simulati e dividendo per sport.
    const realizzatoOggi = useMemo(() => {
        const oggi = romeDay(new Date(nowMs));
        const delGiorno = (placedAt: string | null | undefined) =>
            !!placedAt && romeDay(new Date(placedAt)) === oggi;
        const righe: RigaRealizzato[] = [];
        for (const t of omegaTrades) {
            if (delGiorno(t.placed_at)) righe.push({ status: t.status, pnl: t.pnl, mode: t.mode, sport: 'calcio' });
        }
        for (const t of safe?.trades ?? []) {
            if (delGiorno(t.placed_at)) righe.push({ status: t.status, pnl: t.pnl, mode: t.mode, sport: t.sport });
        }
        for (const t of mike?.trades ?? []) {
            if (delGiorno(t.placed_at)) righe.push({ status: t.status, pnl: t.pnl, mode: t.mode, sport: 'calcio' });
        }
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
    }, [omegaTrades, safe?.trades, mike?.trades, nowMs]);

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
     * chiamata a Betfair. Mike non pubblica `market_id`/`selection_id` sulle
     * righe: per lui i due prezzi restano `null`, e la riga lo dice.
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
            out.push({
                bot: 'mike', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.selection_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: null,
                ordine: ordineDi(t),
                dettaglio: dettaglioDi(
                    { ...t, pnl: t.pnl ?? 0 } as RigaDettagliabile,
                    (closesMike.get(t.id) ?? []).map((c) => ({ ...c, pnl: c.pnl ?? 0 })) as RigaDettagliabile[],
                    { gamba: t.role ?? t.strategy ?? null },
                ),
                // `mike_trades` non porta `market_id`/`selection_id`: senza
                // selezione non esiste un prezzo vivo da mostrare, e non si
                // inventa quello di un'altra riga.
                vivo: null,
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
            return { proposta: pr, abbinabileOra: vivo.abbinabile, etaQuoteS };
        }), [proposte, feedPerEvento, nowMs]);

    const ricaricaProposte = useCallback(async () => {
        try { setProposte(await fetchProposte()); } catch { /* il giro riprova */ }
    }, []);

    const piazzaOpportunita = useCallback(async (id: number) => {
        // PIAZZA = la proposta passa a 'pending' e la esegue il servizio, con
        // le stesse barriere di ogni richiesta manuale. Nessuna seconda strada.
        await approvaProposta(id);
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const rifiutaOpportunita = useCallback(async (id: number) => {
        await ignoraProposta(id, 'opportunita rifiutata dall’operatore');
        await ricaricaProposte();
    }, [ricaricaProposte]);


    const approva = useCallback(async (id: number) => {
        await approvaProposta(id);
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const ignora = useCallback(async (id: number) => {
        await ignoraProposta(id);
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const ricaricaProposteOmega = useCallback(async () => {
        try {
            setProposteOmega(await fetchProposteOmega());
            setErroreProposteOmega(null);
        } catch (e) {
            setProposteOmega([]);
            setErroreProposteOmega(e instanceof Error ? e.message : String(e));
        }
    }, []);

    const approvaOmega = useCallback(async (id: number) => {
        await approvaPropostaOmega(id);
        await ricaricaProposteOmega();
    }, [ricaricaProposteOmega]);

    const ignoraOmega = useCallback(async (id: number) => {
        await ignoraPropostaOmega(id);
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
        }, closes: readonly { id: number }[] = []) => {
            if (isErrorRow(t.status)) return;           // non e' un'operazione
            const k = String(t.event_id);
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
                pnl: isSettled(String(t.status ?? '')) && typeof t.pnl === 'number'
                    ? t.pnl : null,
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
                    closes as RigaDettagliabile[],
                    { gamba: t.strategy ?? t.phase ?? t.role ?? null },
                ),
            };
            const arr = m.get(k);
            if (arr) arr.push(riga); else m.set(k, [riga]);
        };
        const closesOmega = chiusureCollegate(omegaTrades);
        const closesSafe = chiusureCollegate(safe?.trades ?? []);
        const closesMike = chiusureCollegate(mike?.trades ?? []);
        for (const t of omegaTrades) agg('omega', t, closesOmega.get(t.id) ?? []);
        for (const t of safe?.trades ?? []) agg('safe', t, closesSafe.get(t.id) ?? []);
        for (const t of mike?.trades ?? []) {
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
            };
            const arr = m.get(k);
            if (arr) arr.push(riga); else m.set(k, [riga]);
        }
        for (const arr of m.values()) arr.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
        return m;
    }, [omegaTrades, safe?.trades, mike?.trades, tennisOrdini]);

    const chiudi = useCallback(async (tradeId: number) => {
        // chiusura PIENA: il P&L diventa identico sui due esiti (green-up)
        await requestSafe('cashout', { trade_id: tradeId, fraction: 1 });
        await ricaricaProposte();
    }, [ricaricaProposte]);

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
            operazioni: realizzatoOggi.live.righe,
            vinte: realizzatoOggi.live.vinte,
            perse: realizzatoOggi.live.perse,
            operazioniPaper: realizzatoOggi.paper.righe || null,
        };
    }, [omega?.aggregates, safe?.aggregates, mike?.aggregates, safeOggi, safeOggiPaper,
        tennisOggi, realizzatoOggi]);

    const feedEtaS = etaSecondi(scanStatus?.updated_at, nowMs);

    return {
        caricamento, errore, nowMs,
        giornata, totali,
        obiettivo,
        obiettivoStoricizzato: omega?.goal_snapshot === true,
        realizzato,
        realizzatoOggi,
        soldiGiornata: giornataSoldi,
        targetServizio,
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
        rifiutaOpportunita,
        slippagePct, setSlippagePct, approva, ignora, chiudi,
        statoChiusura, cashOutEvento, riprendiEvento, eventiChiusiOmega,
        proposteOmega: ordinaProposteOmega(proposteOmega), erroreProposteOmega,
        approvaOmega, ignoraOmega,
        feedSorgente: scanStatus?.payload?.source ?? null,
        feedEtaS,
        feedFreschezza: freschezza(feedEtaS),
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
