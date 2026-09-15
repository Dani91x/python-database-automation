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
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    fetchScanRows, subscribeScanRows, fetchScanStatus,
    type ScanRow, type ScanStatusRow, type CalcioScanPayload,
} from '@/lib/safeStrategyScan';
import {
    fetchOmegaState, fetchOmegaTrades, fetchOmegaEvents,
    type OmegaState, type OmegaTrade, type OmegaStats, type OmegaEvent,
} from '@/lib/omega';
import {
    fetchSafeState, fetchRunnerState, requestSafe, tradeExposureNow,
    type SafeState, type SafeRiskStats, type RunnerState,
} from '@/lib/safeBot';
import { hedgeSide, greenPrice, partialLockedPnl } from '@/components/trading/CashOutButton';
import { fetchMikeState, type MikeStateView } from '@/lib/mike';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';
import { fetchMissions } from '@/lib/omegaMissions';
import { fetchTennisFollows } from '@/lib/tennis';
import { posizioniChiuse, type PosizioneChiusa, type TradeChiudibile } from '@/lib/posizioniChiuse';
import {
    costruisciGiornata, soldiPerPartita, marca, totaliGiornata, coperturaControllo,
    etaSecondi, freschezza, realizzatoGiornata, arricchimentoDa, type ArricchimentoPartita,
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

/** UNA lettura completa ogni 30 s. Il resto arriva in push. */
export const RICARICA_MS = 30_000;
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
}

/** Una riga è «a mercato» se non è regolata e non è un piazzamento mai
 *  avvenuto. `error` NON è un'operazione: non conta in nessun numero. */
function aMercato(t: { status: string }): boolean {
    return !isSettled(t.status) && !isErrorRow(t.status);
}

/** Una proposta con accanto il presente: prezzo e liquidità di ADESSO. */
export interface PropostaVista {
    proposta: PropostaChiusura;
    vivo: PrezzoVivo;
    /** età del prezzo su cui si piazzerebbe; null = non lo sappiamo */
    etaQuoteS: number | null;
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
    slippagePct: number;
    setSlippagePct: (v: number) => void;
    approva: (id: number) => Promise<void>;
    ignora: (id: number) => Promise<void>;
    /** chiusura MANUALE di una posizione, per intero: accoda una richiesta
     *  `cashout` sul percorso di sempre. Non passa dal cancelletto — una
     *  chiusura decisa dall'operatore non ha bisogno di essere approvata da
     *  lui stesso. */
    chiudi: (tradeId: number) => Promise<void>;

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
    const [canali, setCanali] = useState<Record<Bot, LocalStatus>>({ omega: 'off', safe: 'off', mike: 'off' });
    const [ultimoPush, setUltimoPush] = useState<Record<Bot, number | null>>({ omega: null, safe: null, mike: null });

    // ---------------------------------------------------------------- lettura
    const ricarica = useCallback(() => {
        let vivo = true;
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
        ]).then((r) => {
            if (!vivo) return;
            const [rScan, rStatus, rOmega, rOmegaT, rSafe, rMike, rRunner, rProp,
                rDaily, rDailyPaper, rEventi, rMissioni, rFollowT] = r;
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
            setSoldiLetti((prev) => prev || (rOmegaT.status === 'fulfilled'
                && rSafe.status === 'fulfilled' && rMike.status === 'fulfilled'));
            if (rMissioni.status === 'fulfilled' || rFollowT.status === 'fulfilled') {
                const attive = new Set<string>();
                if (rMissioni.status === 'fulfilled') {
                    for (const m of rMissioni.value?.missions ?? []) {
                        if (m?.recording === true && m.event_id) attive.add(String(m.event_id));
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
                .map((x, i) => (x.status === 'rejected' ? ['feed', 'stato feed', 'Omega', 'trade Omega', 'Safe', 'Mike', 'runner', 'proposte di chiusura', 'giornata Safe (live)', 'giornata Safe (paper)',
                        'campionati e loghi', 'registrazioni calcio', 'registrazioni tennis'][i] : null))
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
            obiettivoGiorno: number | null = null,
        ): StatoBot => {
            const at = ultimoPush[bot];
            const eta = at == null ? null : Math.max(0, Math.round((nowMs - at) / 1000));
            return {
                bot, modalita, inCorsa, battitoAt,
                canale: canali[bot],
                etaPushS: eta,
                freschezzaPush: freschezza(eta),
                varianti: bot === 'safe' ? varianti : null,
                modiStrategia: bot === 'safe' ? modi : null,
                stato, params, obiettivoGiorno,
            };
        };
        const testo = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : null);
        const numero = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
        return [
            riga('omega', modalitaDi(omega?.control?.mode), inCorsaDi(omega?.control?.status),
                omega?.control?.heartbeat_at ?? null, testo(omega?.control?.status),
                (omega?.control?.params ?? null) as Record<string, unknown> | null,
                numero((omega?.control as { daily_goal?: unknown } | undefined)?.daily_goal)),
            riga('safe', modalitaDi(safe?.control?.mode), inCorsaDi(safe?.control?.status),
                safe?.control?.heartbeat_at ?? null, testo(safe?.control?.status),
                (safe?.control?.params ?? null) as Record<string, unknown> | null),
            riga('mike', modalitaDi(mike?.control?.mode), inCorsaDi(mike?.control?.status),
                mike?.control?.heartbeat_at ?? null, testo(mike?.control?.status),
                (mike?.control?.params ?? null) as Record<string, unknown> | null),
        ];
    }, [omega?.control, safe?.control, safe?.params_effective, mike?.control, canali, ultimoPush, nowMs]);

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
        return posizioniChiuse(righe);
    }, [omegaTrades, safe?.trades, mike?.trades]);

    const posizioni = useMemo<PosizioneAperta[]>(() => {
        const out: PosizioneAperta[] = [];

        /** Quanto vale chiudere ADESSO, con la matematica condivisa del green-up.
         *  `null` quando il prezzo corrente non c'e': non si inventa. */
        const chiusuraViva = (t: {
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
        };
        for (const t of omegaTrades) {
            if (!aMercato(t)) continue;
            out.push({
                bot: 'omega', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.runner_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: null,
            });
        }
        for (const t of safe?.trades ?? []) {
            if (!aMercato(t)) continue;
            out.push({
                bot: 'safe', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.selection_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: chiusuraViva(t),
            });
        }
        for (const t of mike?.trades ?? []) {
            if (!aMercato(t)) continue;
            out.push({
                bot: 'mike', id: t.id, eventId: t.event_id, partita: t.event_name ?? t.event_id,
                selezione: t.selection_name, lato: latoDi(t.side), prezzo: t.price, size: t.size,
                liability: t.liability, modalita: modalitaDi(t.mode), piazzataAt: t.placed_at,
                chiusura: null,
            });
        }
        // le più recenti in cima: è l'ordine in cui un trader le cerca
        out.sort((a, b) => Date.parse(b.piazzataAt) - Date.parse(a.piazzataAt));
        return out;
    }, [omegaTrades, safe?.trades, mike?.trades, feedPerEvento]);

    const proposteVista = useMemo<PropostaVista[]>(() => ordinaProposte(proposte).map((pr) => {
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
        return { proposta: pr, vivo, etaQuoteS };
    }), [proposte, feedPerEvento, nowMs]);

    const ricaricaProposte = useCallback(async () => {
        try { setProposte(await fetchProposte()); } catch { /* il giro riprova */ }
    }, []);

    const approva = useCallback(async (id: number) => {
        await approvaProposta(id);
        await ricaricaProposte();
    }, [ricaricaProposte]);

    const ignora = useCallback(async (id: number) => {
        await ignoraProposta(id);
        await ricaricaProposte();
    }, [ricaricaProposte]);

    // ── OPERAZIONI PER PARTITA ───────────────────────────────────────────────
    const operazioni = useMemo(() => {
        const m = new Map<string, OperazionePartita[]>();
        const agg = (bot: Bot, t: {
            id: number; event_id: string; selection_name?: string | null; runner_name?: string | null;
            side?: string | null; price?: number | null; size?: number | null; status: string;
            pnl?: number | null; mode?: string | null; placed_at: string;
            strategy?: string | null; phase?: string | null; role?: string | null;
        }) => {
            if (isErrorRow(t.status)) return;           // non e' un'operazione
            const k = String(t.event_id);
            const riga: OperazionePartita = {
                bot, id: t.id,
                selezione: t.selection_name ?? t.runner_name ?? null,
                lato: latoDi(t.side), prezzo: t.price ?? null, size: t.size ?? null,
                stato: t.status, pnl: typeof t.pnl === 'number' ? t.pnl : null,
                modalita: modalitaDi(t.mode), at: t.placed_at,
                quale: t.strategy ?? t.phase ?? t.role ?? null,
            };
            const arr = m.get(k);
            if (arr) arr.push(riga); else m.set(k, [riga]);
        };
        for (const t of omegaTrades) agg('omega', t);
        for (const t of safe?.trades ?? []) agg('safe', t);
        for (const t of mike?.trades ?? []) agg('mike', t);
        for (const arr of m.values()) arr.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
        return m;
    }, [omegaTrades, safe?.trades, mike?.trades]);

    const chiudi = useCallback(async (tradeId: number) => {
        // chiusura PIENA: il P&L diventa identico sui due esiti (green-up)
        await requestSafe('cashout', { trade_id: tradeId, fraction: 1 });
        await ricaricaProposte();
    }, [ricaricaProposte]);

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
        const serverLive = n(safeOggi?.pnl_realized);
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
        realizzatoOggi]);

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
        schermo, ultimaCatena,
        operazioni,
        proposte: proposteVista,
        slippagePct, setSlippagePct, approva, ignora, chiudi,
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
