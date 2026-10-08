// ============================================================================
// /tennis/replay — «REPLAY TENNIS» / Tennis Trading Simulator (07/10/2026).
//
// Sezione SEPARATA dal Match Replay del calcio (ordine dell'utente: «TENNIS E
// CALCIO SONO DISTINTI»): dati, RPC, rotta e logica di dominio del tennis propri
// (`lib/tennisReplay.ts`, migrazione `replay_tennis_2026-10-07.sql`); i componenti
// GENERICI del replay sono quelli del Match Replay, importati e non copiati
// (PlaybackControls, TimelineSlider, MarketPanel, TradesPanel, LadderView +
// training, TrainingTradesPanel, LadderBacktestPanel, OpportunitaPanel,
// ValidationCard, matching, replay-pnl).
//
// Cosa e' del tennis: punteggio (set, game, punti, servizio, tie-break) col
// tabellone del Tennis Terminal, simboli della barra (inizio set, break,
// tie-break, fine set, fine partita, buchi, passaggio in gioco; sospensioni dai
// frame), menu dei mercati per categoria tennis, esito dei mercati dal
// REGOLAMENTO Betfair registrato (runner WINNER), bet-delay dal betDelay del
// mercato, fasi per set nel motore opportunita', «Applica bot» coi soli bot tennis.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { AlertTriangle, Info, Sparkles, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { TennisNav } from '@/components/tennis/TennisNav';
import { TennisMatchStatsView } from '@/components/tennis/TennisMatchStats';
import { PlaybackControls } from '@/components/replay/PlaybackControls';
import { TimelineSlider } from '@/components/replay/TimelineSlider';
import { MarketPanel } from '@/components/replay/MarketPanel';
import { TradesPanel } from '@/components/replay/TradesPanel';
import { TrainingTradesPanel } from '@/components/replay/TrainingTradesPanel';
import { LadderBacktestPanel } from '@/components/replay/LadderBacktestPanel';
import { OpportunitaPanel } from '@/components/replay/OpportunitaPanel';
import { ValidationCard } from '@/components/replay/ValidationCard';
import { LegendaTennis, iconaTennis, markerTennis } from '@/components/tennis-replay/TennisTimelineSymbols';
import { TennisReplayList } from '@/components/tennis-replay/TennisReplayList';
import { ApplicaBotPanel } from '@/components/replay/ApplicaBotPanel';
import { EsitoBotPanel } from '@/components/replay/EsitoBotPanel';
import { AvvisoCoerenzaBarra } from '@/components/replay/AvvisoCoerenzaBarra';
import { useApplicaBot } from '@/lib/useApplicaBot';
import { useOperativitaBot } from '@/lib/useOperativitaBot';
import { indiceTimelineAl, istanteCursore, ladderBotAl } from '@/lib/replayOperazioni';
import type { PuntoSeek } from '@/components/replay/RegistroOperazioniBot';
import { verificaBarraTennis } from '@/lib/tennisReplayVerificaBarra';
import { LadderView, type BotLadderOverlay, type LadderSource } from '@/components/live/LadderView';
import type { Frame, LiveLadderRow, ReplayProgress } from '@/lib/live';
import { partitaTennisFinita } from '@/lib/tennis';
import { formatGbp, type BetSide, type SimBet } from '@/lib/replay-pnl';
import { simulateOrder, MIN_STAKE_GBP, type BookSnapshot, type OrderRequest, type Persistence } from '@/lib/matching';
import { createTrainingApi, frameToLadderRow, type TrainingApi } from '@/lib/trainingLadder';
import { buildSnapshots } from '@/lib/opportunities/snapshot';
import { runDetectors, DEFAULT_OPP_CONFIG } from '@/lib/opportunities/engine';
import { validateFromDetections } from '@/lib/opportunities/validate';
import { arbExecutableUnderDelay } from '@/lib/opportunities/arb_exec';
import { orderFlowImbalance, weightOfMoney, spreadScalp } from '@/lib/opportunities/tier2_micro';
import type { Detector, OppConfig, Opportunity } from '@/lib/opportunities/types';
import { faseTennisDaEtichetta } from '@/lib/replayFasi';
import {
    CLASSE_NOTA, notaNomeGiocatore,
    conFaseTennis, costruisciTimeline, delayMercatoMs, faseTennis, fetchTennisReplay, fetchTennisReplayList,
    framesPerMercato, indiceDiPasso, inizioInGioco, minutiDiGioco, ordinaPunteggio, perMotoreOpportunita,
    punteggioAl, puntiFinoA, etichettaPunteggio, raggruppaMercatiTennis, simboliTennis, sospesoPerPasso, ultimoAl,
    valutaMercatoTennis,
    type CatTennis, type TennisReplayData, type TennisReplayItem, type TennisReplayMarket,
} from '@/lib/tennisReplay';

// Ordine simulato (come il Match Replay): i fill li calcola il motore di matching.
interface SimOrder {
    id: string;
    marketId: string;
    selectionId: number;
    selectionName: string;
    marketName: string;
    side: BetSide;
    limitPrice: number;
    requested: number;
    placedTs: number;
    inPlay: boolean;
    delayMs: number;
    minute: number | null;
    persistence: Persistence;
    cancelledTs?: number | null;
    closedTs?: number | null;
    closed?: boolean;
    realizedPnl?: number;
}

const PLAY_NORMAL_MS = 1000;
const PLAY_FAST_MS = 300;
const SPEED_OPTIONS = [1, 2, 3, 4, 5] as const;
const TIMELINE_BUCKET_MS = 10_000;

/** I rilevatori del motore opportunita' che hanno senso sul tennis: la
 *  microstruttura del book (flusso, peso del denaro, spread). Gli arbitraggi
 *  tier 0 e le strategie tier 1 sono del calcio (pareggio, doppia chance,
 *  correct score, BTTS, over/under, gol): sul tennis non esistono. */
const RILEVATORI_TENNIS: Detector[] = [orderFlowImbalance, weightOfMoney, spreadScalp];
export const NOTA_OPPORTUNITA_TENNIS =
    'Sul tennis girano i rilevatori di microstruttura del book (flusso degli ordini, peso del denaro, '
    + 'scalp sullo spread). Gli arbitraggi e le strategie del calcio (pareggio, doppia chance, correct score, '
    + 'BTTS, over/under, gol) non esistono nel tennis e non sono applicati.';

function uid(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function oraLocale(ts: string): string {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function TennisReplay() {
    // ---- elenco vs simulatore ----
    const [list, setList] = useState<TennisReplayItem[]>([]);
    const [listLoading, setListLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [replay, setReplay] = useState<TennisReplayData | null>(null);
    const [replayLoading, setReplayLoading] = useState(false);
    const [replayProgress, setReplayProgress] = useState<ReplayProgress | null>(null);

    // ---- stato del simulatore ----
    const [currentIndex, setCurrentIndex] = useState(0);
    // 07/10 sera: il cursore ESATTO (clic su un'operazione del bot nel registro)
    const [cursoreEsatto, setCursoreEsatto] = useState<{ index: number; ms: number } | null>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playDir, setPlayDir] = useState<1 | -1>(1);
    const [playSpeed, setPlaySpeed] = useState(PLAY_NORMAL_MS);
    const [speedMult, setSpeedMult] = useState(1);
    const [activeCategory, setActiveCategory] = useState<CatTennis>('MATCH_ODDS');
    const [view, setView] = useState<'markets' | 'opps' | 'ladder' | 'backtest'>('markets');
    const [trainingMarketId, setTrainingMarketId] = useState<string | null>(null);
    const [trainingResetTick, setTrainingResetTick] = useState(0);
    const [replayEventId, setReplayEventId] = useState('');
    const [orders, setOrders] = useState<SimOrder[]>([]);
    const [stakes, setStakes] = useState<Record<string, number>>({});
    const [realizedPnl, setRealizedPnl] = useState(0);

    useEffect(() => {
        let alive = true;
        fetchTennisReplayList(100)
            .then(rows => { if (alive) setList(rows); })
            .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : String(e)); })
            .finally(() => { if (alive) setListLoading(false); });
        return () => { alive = false; };
    }, []);

    const azzeraSimulazione = () => {
        setIsPlaying(false);
        setPlayDir(1);
        setPlaySpeed(PLAY_NORMAL_MS);
        setSpeedMult(1);
        setActiveCategory('MATCH_ODDS');
        setView('markets');
        setOrders([]);
        setStakes({});
        setRealizedPnl(0);
        trainApiRef.current = null;
        setTrainingMarketId(null);
        setTrainingResetTick(0);
    };

    const selectReplay = async (item: TennisReplayItem) => {
        setReplayLoading(true);
        setReplayProgress(null);
        setError(null);
        try {
            const data = await fetchTennisReplay(item.event_id, p => setReplayProgress(p));
            azzeraSimulazione();
            setReplay(data);
            setCurrentIndex(0);
            setReplayEventId(item.event_id);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setReplayLoading(false);
            setReplayProgress(null);
        }
    };

    const endSimulation = () => {
        azzeraSimulazione();
        setReplay(null);
        setCurrentIndex(0);
        setReplayEventId('');
    };

    // ---- timeline: griglia a 10 s su tutta la registrazione ----
    const frames: Frame[] = useMemo(() => replay?.frames ?? [], [replay]);
    const inGiocoTs = useMemo(() => inizioInGioco(frames), [frames]);
    const timeline = useMemo(() => costruisciTimeline(frames, TIMELINE_BUCKET_MS), [frames]);
    const maxIndex = Math.max(0, timeline.length - 1);
    const kickoffIndex = useMemo(
        () => (inGiocoTs && timeline.length > 0 ? indiceDiPasso(timeline, inGiocoTs) : 0),
        [timeline, inGiocoTs],
    );
    // al caricamento il cursore va sul passaggio in gioco (il pre-match resta raggiungibile)
    const loadedEventRef = useRef<string | null>(null);
    useEffect(() => {
        const eid = replay?.event?.event_id ?? null;
        if (eid && loadedEventRef.current !== eid) {
            loadedEventRef.current = eid;
            setCurrentIndex(kickoffIndex);
        }
        if (!eid) loadedEventRef.current = null;
    }, [replay, kickoffIndex]);
    const safeIndex = Math.min(currentIndex, maxIndex);
    const cursore = istanteCursore(timeline, safeIndex, cursoreEsatto);
    const currentTs = cursore.ts;
    const currentMs = cursore.ms;
    // muovere la barra (o il play) annulla il cursore esatto
    useEffect(() => {
        if (cursoreEsatto && cursoreEsatto.index !== safeIndex) setCursoreEsatto(null);
    }, [safeIndex, cursoreEsatto]);
    const minutoGioco = minutiDiGioco(currentTs, inGiocoTs);
    const preGioco = safeIndex < kickoffIndex;

    const nowMsRef = useRef(0);
    nowMsRef.current = currentMs;
    const trainApiRef = useRef<TrainingApi | null>(null);

    // ---- frame per mercato, book per selezione (motore di matching) ----
    const framesByMarket = useMemo(() => framesPerMercato(frames), [frames]);
    const selectionSnaps = useMemo(() => {
        const cache = new Map<string, BookSnapshot[]>();
        return (marketId: string, sid: number): BookSnapshot[] => {
            const key = `${marketId}:${sid}`;
            let s = cache.get(key);
            if (!s) {
                s = (framesByMarket.get(marketId) ?? []).map(f => {
                    const e = f.ladder?.[String(sid)];
                    return {
                        ts: new Date(f.ts).getTime(), back: e?.back ?? [], lay: e?.lay ?? [],
                        ltp: e?.ltp ?? null, tv: e?.tv ?? null, trd: e?.trd, status: f.status,
                    };
                });
                cache.set(key, s);
            }
            return s;
        };
    }, [framesByMarket]);
    const currentLadder = (marketId: string) => ultimoAl(framesByMarket.get(marketId), currentTs)?.ladder;
    const currentStatus = (marketId: string) => ultimoAl(framesByMarket.get(marketId), currentTs)?.status;

    const markets: TennisReplayMarket[] = useMemo(
        () => (replay ? [...replay.markets].sort(
            (a, b) => (a.sort_priority ?? Number.MAX_SAFE_INTEGER) - (b.sort_priority ?? Number.MAX_SAFE_INTEGER)) : []),
        [replay],
    );
    const marketById = useMemo(() => new Map(markets.map(m => [m.market_id, m])), [markets]);
    const delayMsAt = (marketId: string) => delayMercatoMs(marketById.get(marketId));
    const delayMsAtRef = useRef(delayMsAt);
    delayMsAtRef.current = delayMsAt;

    // ---- TRAINING sul ladder: api simulata + sorgente dal frame corrente ----
    const snapsRef = useRef(selectionSnaps);
    snapsRef.current = selectionSnaps;
    const framesRef = useRef(framesByMarket);
    framesRef.current = framesByMarket;
    const trainingInplayAt = (marketId: string, tsMs: number): boolean => {
        const f = ultimoAl(framesRef.current.get(marketId), new Date(tsMs).toISOString());
        return f ? (f.inplay ?? true) : true; // prudente: delay applicato se ignoto
    };
    if (replay && replayEventId && !trainApiRef.current) {
        trainApiRef.current = createTrainingApi({
            eventId: replayEventId,
            getSnaps: (m, s) => snapsRef.current(m, s),
            getNow: () => nowMsRef.current,
            isInplayAt: trainingInplayAt,
            delayMsAt: m => delayMsAtRef.current(m),
        });
    }
    const buildTrainingRow = (mid: string): LiveLadderRow | null => {
        const m = marketById.get(mid);
        if (!m) return null;
        const names = new Map<number, string>(m.selections.map(s => [s.selection_id, s.name ?? `#${s.selection_id}`]));
        return frameToLadderRow({
            eventId: replayEventId, marketId: mid, marketType: m.market_type ?? null, marketName: m.market_name ?? null,
            status: currentStatus(mid) ?? null, nowMs: currentMs, ladder: currentLadder(mid), names,
        });
    };
    const buildTrainingRowRef = useRef(buildTrainingRow);
    buildTrainingRowRef.current = buildTrainingRow;
    const trainSubRef = useRef<{ mid: string; cb: (row: LiveLadderRow | null) => void } | null>(null);
    const trainingSource = useMemo<LadderSource>(() => ({
        fetch: async (mid: string) => buildTrainingRowRef.current(mid),
        subscribe: (mid: string, cb: (row: LiveLadderRow | null) => void) => {
            trainSubRef.current = { mid, cb };
            return () => { if (trainSubRef.current?.mid === mid) trainSubRef.current = null; };
        },
    }), []);
    useEffect(() => {
        const s = trainSubRef.current;
        if (s && view === 'ladder') s.cb(buildTrainingRowRef.current(s.mid));
    }, [currentTs, view]);
    // ---- APPLICA BOT (FASE 2, 07/10): i SOLI bot tennis col codice di produzione
    // sul banco comune; i loro ordini sul ladder del training all'istante corrente
    // 07/10 sera (REPLAY PROFESSIONALE): stessi componenti del calcio, dati del tennis
    const applica = useApplicaBot();
    const punteggiRef = useRef<ReturnType<typeof ordinaPunteggio>>([]);
    const etichettaTennis = (ms: number) => {
        const r = punteggioAl(punteggiRef.current, new Date(ms).toISOString());
        return r ? etichettaPunteggio(r.score) : 'pre-gioco';
    };
    const runnerTennis = (mid: string) => marketById.get(mid)?.selections.map(x => x.selection_id);
    const operativita = useOperativitaBot(applica.esito, etichettaTennis, runnerTennis);
    const botLadder: BotLadderOverlay | undefined = operativita && applica.esito && trainingMarketId
        ? {
            etichetta: applica.esito.etichetta,
            perSelezione: ladderBotAl(operativita.ordini, currentMs, trainingMarketId,
                applica.esito.esiti_mercati ?? null, runnerTennis(trainingMarketId)),
        }
        : undefined;
    const [avvisoSeek, setAvvisoSeek] = useState<string | null>(null);
    const vaiAllOperazione = (p: PuntoSeek) => {
        setIsPlaying(false);
        const idx = indiceTimelineAl(timeline, p.ms);
        setCurrentIndex(idx);
        setCursoreEsatto({ index: idx, ms: p.ms });
        const inizio = timeline[0]?.ts ? Date.parse(timeline[0].ts) : null;
        const presente = p.marketId ? marketById.has(p.marketId) : true;
        if (p.marketId && presente) setTrainingMarketId(p.marketId);
        setAvvisoSeek(!presente
            ? 'il mercato di questa operazione non è fra i mercati registrati nel replay caricato: il ladder resta sul mercato scelto'
            : (inizio != null && p.ms < inizio
                ? 'l’operazione è PRIMA del primo istante caricato nel replay: il book mostrato è il primo disponibile'
                : null));
        setView('ladder');
    };
    useEffect(() => {
        if (view !== 'ladder' || trainingMarketId || !replay) return;
        const mo = markets.find(m => m.market_type === 'MATCH_ODDS');
        setTrainingMarketId((mo ?? markets[0])?.market_id ?? null);
    }, [view, trainingMarketId, replay, markets]);

    // ---- punteggio tennis all'istante del cursore ----
    const punteggiOrdinati = useMemo(() => ordinaPunteggio(replay?.score_timeline ?? []), [replay]);
    punteggiRef.current = punteggiOrdinati;
    // 08/10 (cantiere 10): la FASE (PRE-PARTITA / SET n) per il registro e il P&L del
    // bot, dalla fase che il replay gia' calcola (`faseTennis`); funzione stabile
    const faseTennisIstante = useMemo(
        () => (ms: number) => faseTennisDaEtichetta(faseTennis(punteggiOrdinati, new Date(ms).toISOString(), inGiocoTs)),
        [punteggiOrdinati, inGiocoTs],
    );
    const rigaPunteggio = currentTs ? punteggioAl(punteggiOrdinati, currentTs) : null;
    const puntiAlCursore = useMemo(
        () => (currentTs ? puntiFinoA(punteggiOrdinati, currentTs) : []),
        [punteggiOrdinati, currentTs],
    );
    const p1 = replay?.event.player1_name || 'Giocatore 1';
    const p2 = replay?.event.player2_name || 'Giocatore 2';
    const nota1 = notaNomeGiocatore(replay?.event.nomi_fonte, 1);   // 08/10: «nome dall'IPS, troncato»
    const nota2 = notaNomeGiocatore(replay?.event.nomi_fonte, 2);
    const mo = markets.find(m => (m.market_type || '').toUpperCase() === 'MATCH_ODDS') ?? markets[0];
    const statoMo = mo ? currentStatus(mo.market_id) : undefined;
    const inGiocoAlCursore = mo ? (ultimoAl(framesByMarket.get(mo.market_id), currentTs)?.inplay ?? false) : false;
    const finita = partitaTennisFinita(rigaPunteggio?.score.status, statoMo);

    // ---- simboli, sospensioni, categorie ----
    const simboli = useMemo(
        () => simboliTennis(punteggiOrdinati, timeline, p1, p2, inGiocoTs),
        [punteggiOrdinati, timeline, p1, p2, inGiocoTs],
    );
    // sulla barra solo i fatti gia' avvenuti all'istante del cursore
    const simboliVisti = useMemo(() => simboli.filter(x => !currentTs || x.ts <= currentTs), [simboli, currentTs]);
    const suspended = useMemo(() => sospesoPerPasso(timeline, framesByMarket, markets), [timeline, framesByMarket, markets]);
    const { perCategoria, presenti } = useMemo(() => raggruppaMercatiTennis(markets), [markets]);
    const activeCat: CatTennis = presenti.some(c => c.key === activeCategory)
        ? activeCategory : (presenti[0]?.key ?? 'MATCH_ODDS');
    const activeMarkets = perCategoria.get(activeCat) ?? [];

    // ---- MOTORE OPPORTUNITA' (rilevatori del tennis, fasi per set, delay del mercato) ----
    const oppCfg: OppConfig = useMemo(
        () => ({ ...DEFAULT_OPP_CONFIG, delaySec: delayMercatoMs(mo) / 1000 }),
        [mo],
    );
    const perMotore = useMemo(() => (replay ? perMotoreOpportunita(replay) : null), [replay]);
    const snapshots = useMemo(
        () => (perMotore ? buildSnapshots(perMotore, TIMELINE_BUCKET_MS) : []),
        [perMotore],
    );
    // verificatore della barra col dato tennis (punteggio e simboli tennis), stabile per replay
    const verificaTennis = useMemo(
        () => () => verificaBarraTennis(replay ?? { event: { event_id: '', competition_name: null, player1_name: '',
            player2_name: '', open_date: null, valuta: 'GBP' }, markets: [], frames: [], score_timeline: [] }),
        [replay],
    );
    const detectionsPerSnap = useMemo<Opportunity[][]>(
        () => snapshots.map(s => conFaseTennis(
            runDetectors(s, RILEVATORI_TENNIS, oppCfg), faseTennis(punteggiOrdinati, s.ts, inGiocoTs))),
        [snapshots, oppCfg, punteggiOrdinati, inGiocoTs],
    );
    const curSnapIdx = useMemo(() => {
        if (!currentTs) return -1;
        let idx = -1;
        for (let i = 0; i < snapshots.length; i++) {
            if (new Date(snapshots[i].ts).getTime() <= currentMs) idx = i; else break;
        }
        return idx;
    }, [snapshots, currentTs, currentMs]);
    const rawOpps = useMemo(() => (curSnapIdx >= 0 ? (detectionsPerSnap[curSnapIdx] ?? []) : []), [curSnapIdx, detectionsPerSnap]);
    const isInplayTs = (ts: string): boolean => inGiocoTs != null && ts >= inGiocoTs;
    const currentOpps = useMemo(() => rawOpps.filter(o =>
        o.tier !== 'arb' || arbExecutableUnderDelay(o, selectionSnaps, currentMs, isInplayTs(currentTs), oppCfg.delaySec * 1000)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rawOpps, selectionSnaps, currentMs, currentTs, inGiocoTs, oppCfg]);
    const arbMarkers = useMemo(() => {
        if (snapshots.length === 0 || timeline.length === 0) return [];
        const span = Math.max(1, timeline.length - 1);
        const out: { pctLeft: number; minute: number | null; label: string }[] = [];
        for (let i = 0; i < snapshots.length; i++) {
            const arbs = (detectionsPerSnap[i] ?? []).filter(o => o.tier === 'arb');
            if (arbs.length === 0) continue;
            const idx = indiceDiPasso(timeline, snapshots[i].ts);
            const stepTs = timeline[idx].ts;
            const exec = arbs.find(o => arbExecutableUnderDelay(
                o, selectionSnaps, new Date(stepTs).getTime(), isInplayTs(stepTs), oppCfg.delaySec * 1000));
            if (exec) out.push({ pctLeft: Math.min(Math.max(idx / span, 0), 1), minute: null, label: exec.title });
        }
        return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [snapshots, detectionsPerSnap, timeline, selectionSnaps, inGiocoTs, oppCfg]);
    const validationReport = useMemo(
        () => (snapshots.length > 0 ? validateFromDetections(snapshots, detectionsPerSnap, oppCfg, TIMELINE_BUCKET_MS) : null),
        [snapshots, detectionsPerSnap, oppCfg],
    );

    // ---- FILL dal motore di matching, col bet-delay del mercato ----
    const bets: SimBet[] = useMemo(() => {
        if (!replay) return [];
        return orders.map(o => {
            const upto = o.closed && o.closedTs != null ? Math.min(currentMs, o.closedTs) : currentMs;
            const req: OrderRequest = {
                side: o.side, limitPrice: o.limitPrice, stake: o.requested, placedTs: o.placedTs,
                inPlay: o.inPlay, delayMs: o.inPlay ? o.delayMs : 0, persistence: o.persistence,
                cancelledTs: o.cancelledTs ?? null,
            };
            const res = simulateOrder(req, selectionSnaps(o.marketId, o.selectionId), upto);
            return {
                id: o.id, marketId: o.marketId, selectionId: o.selectionId, selectionName: o.selectionName,
                marketName: o.marketName, side: o.side, odds: res.avgPrice ?? o.limitPrice, stake: res.matched,
                requestedStake: o.requested, minute: o.minute, limitPrice: o.limitPrice, remaining: res.remaining,
                matchStatus: res.status, closed: o.closed, realizedPnl: o.realizedPnl,
            } satisfies SimBet;
        });
    }, [replay, orders, selectionSnaps, currentMs]);

    const marketEval = (m: TennisReplayMarket) => valutaMercatoTennis(
        bets.filter(b => b.marketId === m.market_id && !b.closed), currentLadder(m.market_id), m, currentMs);
    const overall = useMemo(() => {
        let v = realizedPnl;
        for (const m of markets) {
            const own = bets.filter(b => b.marketId === m.market_id && !b.closed);
            if (own.length > 0) v += valutaMercatoTennis(own, ultimoAl(framesByMarket.get(m.market_id), currentTs)?.ladder, m, currentMs).value;
        }
        return v;
    }, [bets, markets, framesByMarket, currentTs, currentMs, realizedPnl]);

    // ---- riproduzione ----
    const idxRef = useRef(safeIndex);
    idxRef.current = safeIndex;
    useEffect(() => {
        if (!isPlaying) return undefined;
        const interval = Math.max(50, Math.round(playSpeed / speedMult));
        const id = setInterval(() => {
            const next = idxRef.current + playDir;
            if (next < 0 || next > maxIndex) { setIsPlaying(false); return; }
            idxRef.current = next;
            setCurrentIndex(next);
        }, interval);
        return () => clearInterval(id);
    }, [isPlaying, playDir, playSpeed, speedMult, maxIndex]);
    const togglePlay = () => { setPlayDir(1); setPlaySpeed(PLAY_NORMAL_MS); setIsPlaying(p => !p); };
    const fastForward = () => { setPlayDir(1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const rewind = () => { setPlayDir(-1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const stepFwd = () => { setIsPlaying(false); setCurrentIndex(i => Math.min(maxIndex, i + 1)); };
    const stepBack = () => { setIsPlaying(false); setCurrentIndex(i => Math.max(0, i - 1)); };
    const skipStart = () => { setIsPlaying(false); setCurrentIndex(0); };
    const skipEnd = () => { setIsPlaying(false); setCurrentIndex(maxIndex); };

    // ---- ordini simulati ----
    const getStake = (marketId: string) => stakes[marketId] ?? 100;
    const placeBet = (m: TennisReplayMarket) =>
        (selectionId: number, selectionName: string, side: BetSide, price: number) => {
            const requested = getStake(m.market_id);
            if (requested < MIN_STAKE_GBP || price <= 1) return; // minimo Betfair: come dal vivo
            const inPlay = trainingInplayAt(m.market_id, currentMs) && isInplayTs(currentTs);
            setOrders(prev => [...prev, {
                id: uid(), marketId: m.market_id, selectionId, selectionName,
                marketName: m.market_name || m.market_type || 'Mercato', side, limitPrice: price, requested,
                placedTs: currentMs, inPlay, delayMs: delayMercatoMs(m), minute: minutoGioco, persistence: 'LAPSE',
            }]);
        };
    const removeBet = (id: string) => setOrders(prev => prev.flatMap(o => {
        if (o.id !== id) return [o];
        const b = bets.find(x => x.id === id);
        if (b && b.stake > 1e-9) return [{ ...o, cancelledTs: currentMs }];
        return [];
    }));
    const cashOutMarket = (marketId: string) => {
        const m = marketById.get(marketId);
        if (!m) return;
        if (bets.filter(b => b.marketId === marketId && !b.closed && b.stake > 1e-9).length === 0) return;
        const ev = marketEval(m);
        const st = (currentStatus(marketId) ?? 'OPEN').toUpperCase();
        if (!ev.settled && st !== 'OPEN') return; // sospeso/chiuso e non regolato: su Betfair non si chiude
        const locked = ev.value;
        setRealizedPnl(p => p + locked);
        setOrders(prev => {
            let first = true;
            return prev.map(o => {
                if (o.marketId === marketId && !o.closed) {
                    const rp = first ? locked : undefined;
                    first = false;
                    return { ...o, closed: true, closedTs: currentMs, realizedPnl: rp };
                }
                return o;
            });
        });
    };
    const nomeMercato = (mid: string) => {
        const m = marketById.get(mid);
        return m?.market_name || m?.market_type || mid;
    };
    const nomeSelezione = (mid: string, sid: number) =>
        marketById.get(mid)?.selections.find(s => s.selection_id === sid)?.name ?? `#${sid}`;

    const overallCls = overall > 0
        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
        : overall < 0
            ? 'bg-red-500/15 text-red-300 border-red-500/50'
            : 'bg-secondary/15 text-secondary border-secondary/40';
    const s = rigaPunteggio?.score ?? null;
    const statoPartita = finita ? 'FINE' : statoMo === 'SUSPENDED' ? 'SOSPESO' : preGioco ? 'PRE-MATCH' : 'IN GIOCO';

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Replay Tennis | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30 ds-v2-nascondi" />
            <TennisNav sectionLabel="REPLAY TENNIS" />

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10 ds-v2-pagina-larga ds-v2-main">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-4xl tracking-tight ds-v2-titolo">
                        TENNIS TRADING <span className="text-secondary">SIMULATOR</span>
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Riproduci le partite di tennis registrate e piazza back/lay simulate alle quote storiche.
                    </p>
                </div>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm" data-testid="tennis-replay-errore">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {!replay ? (
                    replayLoading || listLoading ? (
                        <div className="space-y-3">
                            {replayLoading && (
                                <Card className="glass-card border-white/10 p-5 space-y-3">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-white font-bold">Caricamento replay…</span>
                                        <span className="text-muted-foreground tabular-nums text-xs">
                                            {replayProgress
                                                ? `finestra ${replayProgress.done}/${replayProgress.total} · ${replayProgress.frames.toLocaleString('it')} frame`
                                                : 'preparazione…'}
                                        </span>
                                    </div>
                                    <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                                        <div className="h-full bg-secondary transition-all duration-300"
                                            style={{ width: `${replayProgress ? Math.round((replayProgress.done / Math.max(1, replayProgress.total)) * 100) : 5}%` }} />
                                    </div>
                                </Card>
                            )}
                            {Array.from({ length: replayLoading ? 2 : 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full bg-white/5" />)}
                        </div>
                    ) : (
                        <TennisReplayList items={list} onSelect={selectReplay} />
                    )
                ) : (
                    <div className="space-y-5" data-testid="tennis-replay-simulatore">
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                            <span className={`inline-flex items-center px-3 py-1.5 rounded-lg border text-sm font-bold tabular-nums ${overallCls}`}>
                                Overall Position: {formatGbp(overall)}
                            </span>
                            <Button size="sm" onClick={endSimulation} className="bg-secondary text-black font-bold hover:bg-secondary/90">
                                <Square className="w-4 h-4 mr-1.5" /> End Simulation
                            </Button>
                        </div>

                        {/* testata partita col punteggio all'istante del cursore */}
                        <Card className="glass-card border-white/10 p-4" data-testid="tennis-replay-testata">
                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground text-center mb-1">
                                {replay.event.competition_name ?? ''}
                            </div>
                            <div className="flex items-center justify-center gap-4">
                                <span className={`text-emerald-400 font-bold text-lg truncate max-w-[34%] text-right${nota1 ? CLASSE_NOTA : ''}`}
                                    title={nota1}>{p1}</span>
                                <span className="font-display font-black text-2xl md:text-3xl tabular-nums text-white" data-testid="tennis-replay-set">
                                    {s ? `${s.sets.p1} - ${s.sets.p2}` : '—'}
                                </span>
                                <span className={`text-amber-400 font-bold text-lg truncate max-w-[34%]${nota2 ? CLASSE_NOTA : ''}`}
                                    title={nota2}>{p2}</span>
                            </div>
                            <div className="text-center text-xs text-muted-foreground mt-1 tabular-nums" data-testid="tennis-replay-stato">
                                {statoPartita}
                                {s ? ` · ${s.set_summary ?? `${s.games.p1}-${s.games.p2}`} · ${s.tiebreak ? 'tie-break ' : ''}${s.points.p1}-${s.points.p2}` : ''}
                                {currentTs ? ` · ${oraLocale(currentTs)}` : ''}
                            </div>
                        </Card>

                        {/* avviso discreto: barra, simboli e tabellone tennis non tornano coi dati registrati */}
                        <AvvisoCoerenzaBarra replay={perMotore} verifica={verificaTennis} />

                        {/* controlli + barra */}
                        <Card className="glass-card border-white/10 p-4 space-y-4">
                            <PlaybackControls
                                isPlaying={isPlaying} onSkipStart={skipStart} onRewind={rewind} onStepBack={stepBack}
                                onTogglePlay={togglePlay} onStepForward={stepFwd} onFastForward={fastForward} onSkipEnd={skipEnd}
                            />
                            <div className="flex items-center justify-center gap-2">
                                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Velocità</span>
                                <div className="flex items-center gap-1">
                                    {SPEED_OPTIONS.map(x => (
                                        <button key={x} onClick={() => setSpeedMult(x)} aria-pressed={speedMult === x} aria-label={`Velocità x${x}`}
                                            className={`px-2.5 py-1 rounded-md text-xs font-bold tabular-nums border transition-colors ${
                                                speedMult === x ? 'bg-primary text-black border-primary' : 'border-white/10 text-muted-foreground hover:text-white'}`}>
                                            x{x}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div>
                                <TimelineSlider
                                    min={0} max={maxIndex} value={safeIndex} minute={minutoGioco}
                                    pre={preGioco}
                                    suspended={suspended}
                                    events={markerTennis(simboliVisti)}
                                    iconaEvento={iconaTennis}
                                    legenda={<LegendaTennis simboli={simboliVisti} arbitraggi={arbMarkers.length > 0} />}
                                    titoloInizio="Passaggio in gioco"
                                    kickoffPct={maxIndex > 0 ? kickoffIndex / maxIndex : 0}
                                    arbMarkers={arbMarkers}
                                    onChange={v => { setIsPlaying(false); setCurrentIndex(v); }}
                                />
                                <p className="text-[10px] text-muted-foreground/70 mt-1">
                                    Il numero sul cursore sono i minuti dall&apos;inizio del gioco registrato
                                    {kickoffIndex === 0 ? ' (questa registrazione parte a partita gia\' in corso)' : ''};
                                    i tratti rossi sono le sospensioni del Match Odds.
                                </p>
                            </div>
                        </Card>

                        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-5 items-start">
                            <div className="space-y-5 min-w-0">
                                {/* menu sotto la barra: categorie tennis + opportunita' + training + backtest */}
                                <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
                                    {presenti.map(c => (
                                        <button key={c.key} onClick={() => { setView('markets'); setActiveCategory(c.key); }}
                                            className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                                view === 'markets' && activeCat === c.key
                                                    ? 'bg-primary text-black border-primary'
                                                    : 'border-white/10 text-muted-foreground hover:text-white'}`}>
                                            {c.label}
                                            <span className="ml-1 opacity-60 tabular-nums">{perCategoria.get(c.key)?.length ?? 0}</span>
                                        </button>
                                    ))}
                                    <span className="shrink-0 w-px h-5 bg-white/10 mx-0.5" />
                                    <button onClick={() => setView('opps')}
                                        className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                            view === 'opps' ? 'bg-emerald-500 text-black border-emerald-500' : 'border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10'}`}>
                                        <Sparkles className="w-3.5 h-3.5" /> Opportunità
                                        {currentOpps.length > 0 && <span className="ml-0.5 opacity-70 tabular-nums">{currentOpps.length}</span>}
                                    </button>
                                    <button onClick={() => setView('ladder')}
                                        className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                            view === 'ladder' ? 'bg-violet-500 text-white border-violet-500' : 'border-violet-500/40 text-violet-300 hover:bg-violet-500/10'}`}>
                                        🎓 Ladder TRAINING
                                    </button>
                                    <button onClick={() => setView('backtest')}
                                        className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                            view === 'backtest' ? 'bg-cyan-500 text-black border-cyan-500' : 'border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10'}`}>
                                        ⚗ Backtest
                                    </button>
                                </div>

                                {view === 'backtest' ? (
                                    <LadderBacktestPanel markets={markets} getSnaps={(m, sid) => selectionSnaps(m, sid)}
                                        isInplayAt={trainingInplayAt} delayMsAt={delayMsAt} />
                                ) : view === 'ladder' ? (
                                    <div className="space-y-3">
                                        <div className="rounded-xl border border-violet-400/50 bg-violet-500/10 px-3 py-2 flex items-center gap-3 flex-wrap">
                                            <span className="px-2 py-0.5 rounded-md bg-violet-500 text-white text-[10px] font-black">🎓 TRAINING</span>
                                            <span className="text-[11px] text-violet-200">
                                                ordini SIMULATI sul book storico — nessun denaro reale · bet-delay del mercato
                                                {trainingMarketId ? ` (${Math.round(delayMsAt(trainingMarketId) / 1000)}s)` : ''} in gioco
                                            </span>
                                            <span className="flex-1" />
                                            <select value={trainingMarketId ?? ''} onChange={e => setTrainingMarketId(e.target.value || null)}
                                                aria-label="Mercato del ladder training" title={`${markets.length} mercati registrati`}
                                                style={{ colorScheme: 'dark' }}
                                                className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]">
                                                {markets.map(m => (
                                                    <option key={m.market_id} value={m.market_id} className="bg-neutral-900 text-white">
                                                        {m.market_name || m.market_type || m.market_id}
                                                    </option>
                                                ))}
                                            </select>
                                            <Button size="sm" variant="outline"
                                                onClick={() => { trainApiRef.current?.reset(); setTrainingResetTick(t => t + 1); }}
                                                className="h-7 border-white/20 text-white/80 hover:bg-white/10 text-[11px] font-bold"
                                                title="Azzera TUTTI gli ordini simulati di questa sessione di training">
                                                Azzera ordini
                                            </Button>
                                        </div>
                                        <ApplicaBotPanel
                                            sport="tennis"
                                            eventId={replayEventId}
                                            cursoreMs={currentMs}
                                            applica={applica}
                                            etichettaIstante={ms => oraLocale(new Date(ms).toISOString())}
                                            mercatiRegistrati={replay ? markets.map(m => m.market_type) : null}
                                        />
                                        {trainingMarketId && trainApiRef.current && (
                                            <LadderView
                                                key={`train:${trainingMarketId}:${trainingResetTick}`}
                                                marketId={trainingMarketId}
                                                orderMode="paper"
                                                sport="tennis"
                                                flussoRunner={false}
                                                ladderSource={trainingSource}
                                                orderApi={trainApiRef.current}
                                                botReplay={botLadder}
                                                fallbackSelections={(marketById.get(trainingMarketId)?.selections ?? [])
                                                    .map(x => ({ selection_id: x.selection_id, name: x.name ?? `#${x.selection_id}` }))}
                                            />
                                        )}
                                        {avvisoSeek && (
                                            <div className="rounded-lg border border-amber-400/50 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100"
                                                data-testid="avviso-seek">{avvisoSeek}</div>
                                        )}
                                        {cursore.esatto && (
                                            <div className="text-[11px] text-amber-200" data-testid="cursore-esatto">
                                                cursore all’istante esatto dell’operazione: {oraLocale(currentTs)}.{String(currentMs % 1000).padStart(3, '0')} · {etichettaTennis(currentMs)}
                                            </div>
                                        )}
                                        {applica.esito && operativita && (
                                            <EsitoBotPanel esito={applica.esito} analisi={operativita} inviato={applica.inviato}
                                                nowMs={currentMs} etichettaIstante={etichettaTennis} runnerDi={runnerTennis}
                                                faseIstante={faseTennisIstante}
                                                onSeek={vaiAllOperazione}
                                                nomeMercato={nomeMercato} nomeSelezione={nomeSelezione} />
                                        )}
                                        {trainApiRef.current && (
                                            <TrainingTradesPanel key={`trade:${trainingResetTick}`} api={trainApiRef.current}
                                                nowMs={currentMs} nomeMercato={nomeMercato} nomeSelezione={nomeSelezione} />
                                        )}
                                    </div>
                                ) : view === 'opps' ? (
                                    <div className="space-y-4">
                                        <div className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-[11px] text-muted-foreground flex items-start gap-2"
                                            data-testid="tennis-replay-nota-opportunita">
                                            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {NOTA_OPPORTUNITA_TENNIS}
                                        </div>
                                        {validationReport && validationReport.totalOpportunities > 0 && (
                                            <ValidationCard report={validationReport} />
                                        )}
                                        <OpportunitaPanel opportunities={currentOpps} grouped />
                                    </div>
                                ) : (
                                    <>
                                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                                            {activeMarkets.map(m => {
                                                const ev = marketEval(m);
                                                return (
                                                    <MarketPanel key={m.market_id} market={m} ladder={currentLadder(m.market_id)}
                                                        stake={getStake(m.market_id)}
                                                        onStakeChange={n => setStakes(prev => ({ ...prev, [m.market_id]: n }))}
                                                        bets={bets.filter(b => b.marketId === m.market_id && !b.closed)}
                                                        onPlaceBet={placeBet(m)} onCashOut={() => cashOutMarket(m.market_id)}
                                                        marketValue={ev.value} settled={ev.settled} winnerId={ev.winnerId}
                                                        status={currentStatus(m.market_id)} />
                                                );
                                            })}
                                        </div>
                                        <TradesPanel bets={bets} onRemove={removeBet} />
                                        <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                                            <strong className="text-muted-foreground">Nota P&L.</strong> Semantica Betfair Exchange.
                                            BACK stake S a quota O: vince → +S·(O-1), perde → -S. LAY stake S a quota O: la selezione vince
                                            → -S·(O-1) (liability), perde → +S. <em>Esito</em> = regolamento di Betfair registrato (runner
                                            vincente alla chiusura del mercato); prima, <em>Cash out</em>/<em>Overall Position</em> = valore
                                            atteso del libro alle quote correnti (overround rimosso). Size del book in euro (sterline
                                            storiche convertite). Simulazione didattica su dati storici.
                                        </p>
                                    </>
                                )}
                            </div>

                            {/* tabellone del tennis all'istante del cursore (lo stesso del Tennis Terminal) */}
                            <Card className="glass-card border-white/10 p-3" data-testid="tennis-replay-tabellone">
                                <TennisMatchStatsView
                                    p1={p1} p2={p2}
                                    score={s}
                                    points={puntiAlCursore}
                                    inplay={inGiocoAlCursore && !finita}
                                    suspended={statoMo === 'SUSPENDED'}
                                    updatedMs={s?.updated_ms ?? null}
                                    now={currentMs}
                                    freschezza={false}
                                />
                            </Card>
                        </div>
                    </div>
                )}
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
