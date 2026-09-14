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
import { fetchOmegaState, fetchOmegaTrades, type OmegaState, type OmegaTrade, type OmegaStats } from '@/lib/omega';
import {
    fetchSafeState, fetchRunnerState, requestSafe, tradeExposureNow,
    type SafeState, type SafeRiskStats, type RunnerState,
} from '@/lib/safeBot';
import { hedgeSide, greenPrice, partialLockedPnl } from '@/components/trading/CashOutButton';
import { fetchMikeState, type MikeStateView } from '@/lib/mike';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';
import {
    costruisciGiornata, soldiPerPartita, marca, totaliGiornata, coperturaControllo,
    etaSecondi, freschezza,
    type Bot, type GruppoCampionato, type TotaliGiornata, type Freschezza, type PartitaFeedLike, type Sport,
} from '@/lib/controlRoom';
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
    /** target per partita calcolato dal SERVIZIO (Omega). Se manca, la pagina lo dichiara. */
    targetServizio: number | null;

    bots: StatoBot[];
    posizioni: PosizioneAperta[];

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
        ]).then((r) => {
            if (!vivo) return;
            const [rScan, rStatus, rOmega, rOmegaT, rSafe, rMike, rRunner, rProp] = r;
            if (rScan.status === 'fulfilled') setScan(rScan.value);
            if (rStatus.status === 'fulfilled') setScanStatus(rStatus.value);
            if (rOmega.status === 'fulfilled') setOmega(rOmega.value);
            if (rOmegaT.status === 'fulfilled') setOmegaTrades(rOmegaT.value);
            if (rSafe.status === 'fulfilled') setSafe(rSafe.value);
            if (rMike.status === 'fulfilled') setMike(rMike.value);
            if (rRunner.status === 'fulfilled') setRunner(rRunner.value);
            if (rProp.status === 'fulfilled') setProposte(rProp.value);

            // Un errore su UNA fonte non deve svuotare la pagina: si mostra
            // quello che è arrivato e si dichiara che cosa manca.
            const caduti = r
                .map((x, i) => (x.status === 'rejected' ? ['feed', 'stato feed', 'Omega', 'trade Omega', 'Safe', 'Mike', 'runner', 'proposte di chiusura'][i] : null))
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

    const giornata = useMemo(() => costruisciGiornata({
        righe: righeFeed.map((r) => ({
            event_id: r.event_id,
            sport: r.sport as Sport,
            payload: r.payload as PartitaFeedLike,
            updated_at: r.updated_at,
        })),
        soldi, nowMs, obiettivo, realizzato, targetServizio,
        // serve a distinguere «prezzo fermo» da «prezzo vecchio»: lo scanner
        // scrive solo quando qualcosa cambia, quindi l'eta' della riga NON dice
        // «da quanto non guardiamo».
        etaScannerS: etaSecondi(scanStatus?.updated_at, nowMs),
    }), [righeFeed, soldi, nowMs, obiettivo, realizzato, targetServizio, scanStatus?.updated_at]);

    const totali = useMemo(() => totaliGiornata(giornata), [giornata]);

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
        const riga = (bot: Bot, modalita: Modalita | null, inCorsa: boolean, battitoAt: string | null): StatoBot => {
            const at = ultimoPush[bot];
            const eta = at == null ? null : Math.max(0, Math.round((nowMs - at) / 1000));
            return {
                bot, modalita, inCorsa, battitoAt,
                canale: canali[bot],
                etaPushS: eta,
                freschezzaPush: freschezza(eta),
                varianti: bot === 'safe' ? varianti : null,
            };
        };
        return [
            riga('omega', modalitaDi(omega?.control?.mode), inCorsaDi(omega?.control?.status), omega?.control?.heartbeat_at ?? null),
            riga('safe', modalitaDi(safe?.control?.mode), inCorsaDi(safe?.control?.status), safe?.control?.heartbeat_at ?? null),
            riga('mike', modalitaDi(mike?.control?.mode), inCorsaDi(mike?.control?.status), mike?.control?.heartbeat_at ?? null),
        ];
    }, [omega?.control, safe?.control, safe?.params_effective, mike?.control, canali, ultimoPush, nowMs]);

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

    const feedEtaS = etaSecondi(scanStatus?.updated_at, nowMs);

    return {
        caricamento, errore, nowMs,
        giornata, totali,
        obiettivo,
        obiettivoStoricizzato: omega?.goal_snapshot === true,
        realizzato,
        targetServizio,
        bots, posizioni, copertura,
        freni: safe?.control?.stats?.risk ?? null,
        runner,
        mikeRestingLive: leggiBool(mike?.control?.params, 'live_resting_enabled'),
        schermo, ultimaCatena,
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
