// ============================================================================
// /match-replay — "Match Replay" / Football Trading Simulator.
// Riproduce i dati di mercato registrati e consente di piazzare back/lay simulate
// alle quote storiche, tracciando il P&L (semantica Betfair Exchange).
// È DATA-DRIVEN: rende TUTTI i mercati presenti nel replay (2, 3 o N selezioni).
// La matematica P&L vive in src/lib/replay-pnl.ts (funzioni pure, testabili).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, History, AlertTriangle, Radio, Square, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PlaybackControls } from '@/components/replay/PlaybackControls';
import { TimelineSlider } from '@/components/replay/TimelineSlider';
import { MarketPanel } from '@/components/replay/MarketPanel';
import { TradesPanel } from '@/components/replay/TradesPanel';
import { OpportunitaPanel } from '@/components/replay/OpportunitaPanel';
import { ValidationCard } from '@/components/replay/ValidationCard';
import {
    fetchReplayList, fetchReplay,
    type ReplayItem, type ReplayData, type Frame,
} from '@/lib/live';
import {
    formatGbp, settleOrCashOut, overallSettled,
    type SimBet, type BetSide, type LadderMap, type SettleCtx, type MarketSettleEval,
} from '@/lib/replay-pnl';
import { simulateOrder, type BookSnapshot, type OrderRequest, type Persistence } from '@/lib/matching';
import { buildSnapshots } from '@/lib/opportunities/snapshot';
import { runDetectors, DEFAULT_OPP_CONFIG } from '@/lib/opportunities/engine';
import { harnessDetectors, validateFromDetections } from '@/lib/opportunities/validate';
import { arbExecutableUnderDelay } from '@/lib/opportunities/arb_exec';
import type { Opportunity } from '@/lib/opportunities/types';

// Ordine simulato (richiesta immutabile dell'utente). I fill REALI vengono calcolati
// in modo deterministico dal motore di matching (matching.ts) contro gli snapshot del
// book fino all'istante corrente → lo stato (matched/quota media/resto) è derivato.
interface SimOrder {
    id: string;
    marketId: string;
    selectionId: number;
    selectionName: string;
    marketName: string;
    side: BetSide;
    limitPrice: number;      // quota cliccata (limite)
    requested: number;       // stake richiesto (£)
    placedTs: number;        // ms epoch di piazzamento
    inPlay: boolean;         // true → ritardo Betfair applicato dal motore
    minute: number | null;
    persistence: Persistence;
    cancelledTs?: number | null; // istante di cancellazione del resto non abbinato
    closedTs?: number | null;    // istante di cash-out (congela la simulazione)
    closed?: boolean;            // cash-out effettuato
    realizedPnl?: number;        // P&L bloccato del mercato (1 volta per gruppo)
}

const PLAY_NORMAL_MS = 1000;
const PLAY_FAST_MS = 300;
const SPEED_OPTIONS = [1, 2, 3, 4, 5] as const;

// URL logo lega (API-Football) dall'id; '' se mancante.
const leagueLogo = (id?: number | null) => (id ? `https://media.api-sports.io/football/leagues/${id}.png` : '');

// ---- categorie mercato (menu a tab) ----
type CatKey = 'MATCH_ODDS' | 'OVER_UNDER' | 'CORRECT_SCORE' | 'FIRST_HALF' | 'BTTS' | 'OTHER';
const CATEGORIES: { key: CatKey; label: string }[] = [
    { key: 'MATCH_ODDS', label: 'Match Odds' },
    { key: 'OVER_UNDER', label: 'Over/Under' },
    { key: 'CORRECT_SCORE', label: 'Correct Score' },
    { key: 'FIRST_HALF', label: 'First Half' },
    { key: 'BTTS', label: 'BTTS' },
    { key: 'OTHER', label: 'Squadre/Altri' },
];
function categoryOf(type: string | null): CatKey {
    const t = (type || '').toUpperCase();
    if (t === 'MATCH_ODDS' || t === 'DOUBLE_CHANCE' || t === 'HALF_TIME_FULL_TIME') return 'MATCH_ODDS';
    if (t.startsWith('FIRST_HALF_GOALS') || t === 'HALF_TIME') return 'FIRST_HALF';
    if (t.startsWith('OVER_UNDER')) return 'OVER_UNDER';
    if (t === 'CORRECT_SCORE' || t === 'HALF_TIME_SCORE') return 'CORRECT_SCORE';
    if (t === 'BOTH_TEAMS_TO_SCORE' || t === 'BTTS') return 'BTTS';
    return 'OTHER';
}
// linea numerica da un market_type tipo OVER_UNDER_25 -> 2.5 (per ordinamento ASC).
function lineOf(type: string | null): number {
    const m = /(\d)(\d)$/.exec((type || '').toUpperCase());
    return m ? Number(`${m[1]}.${m[2]}`) : Number.MAX_SAFE_INTEGER;
}

// genera un id univoco per le bet simulate
function uid(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function MatchReplay() {
    // ---- selector vs simulatore ----
    const [list, setList] = useState<ReplayItem[]>([]);
    const [listLoading, setListLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [replay, setReplay] = useState<ReplayData | null>(null);
    const [replayLoading, setReplayLoading] = useState(false);

    // ---- stato simulatore ----
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playDir, setPlayDir] = useState<1 | -1>(1);
    const [playSpeed, setPlaySpeed] = useState(PLAY_NORMAL_MS); // base (normale/veloce); l'intervallo reale = playSpeed/speedMult
    const [speedMult, setSpeedMult] = useState(1);              // moltiplicatore x1..x5
    const [activeCategory, setActiveCategory] = useState<CatKey>('MATCH_ODDS');
    // vista del pannello sotto la timeline: 'markets' (tab mercati) | 'opps' (Opportunità).
    const [view, setView] = useState<'markets' | 'opps'>('markets');
    const [orders, setOrders] = useState<SimOrder[]>([]);
    const [stakes, setStakes] = useState<Record<string, number>>({});
    // P&L già REALIZZATO da cash-out precedenti (le bet vengono rimosse, ma il
    // valore bloccato al momento del cash-out resta nella posizione complessiva).
    const [realizedPnl, setRealizedPnl] = useState(0);

    // ---- caricamento lista replay ----
    useEffect(() => {
        let alive = true;
        fetchReplayList(50)
            .then(rows => { if (alive) setList(rows); })
            .catch(e => { if (alive) setError(e?.message ?? 'errore sconosciuto'); })
            .finally(() => { if (alive) setListLoading(false); });
        return () => { alive = false; };
    }, []);

    // ---- selezione di un replay ----
    const selectReplay = async (item: ReplayItem) => {
        setReplayLoading(true);
        setError(null);
        try {
            const data = await fetchReplay(item.event_id);
            setReplay(data);
            setCurrentIndex(0);
            setIsPlaying(false);
            setSpeedMult(1);
            setActiveCategory('MATCH_ODDS');
            setView('markets');
            setOrders([]);
            setStakes({});
            setRealizedPnl(0);
        } catch (e: any) {
            setError(e?.message ?? 'errore sconosciuto');
        } finally {
            setReplayLoading(false);
        }
    };

    const endSimulation = () => {
        setReplay(null);
        setIsPlaying(false);
        setSpeedMult(1);
        setActiveCategory('MATCH_ODDS');
        setView('markets');
        setOrders([]);
        setStakes({});
        setCurrentIndex(0);
        setRealizedPnl(0);
    };

    // ---- lista replay raggruppata per LEGA → ANNO (per la vista selettore) ----
    const groupedList = useMemo(() => {
        const byLeague = new Map<string, { league_id: number | null; league_name: string | null; years: Map<number, ReplayItem[]> }>();
        for (const it of list) {
            const key = it.league_name ?? (it.league_id != null ? `Lega ${it.league_id}` : 'Lega sconosciuta');
            let g = byLeague.get(key);
            if (!g) { g = { league_id: it.league_id ?? null, league_name: it.league_name ?? null, years: new Map() }; byLeague.set(key, g); }
            if (g.league_id == null && it.league_id != null) g.league_id = it.league_id;
            let y = 0;
            try { const yy = new Date(it.open_date).getFullYear(); if (Number.isFinite(yy)) y = yy; } catch { /* noop */ }
            const arr = g.years.get(y) ?? [];
            arr.push(it);
            g.years.set(y, arr);
        }
        return Array.from(byLeague.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([key, g]) => ({
                key,
                league_id: g.league_id,
                league_name: g.league_name ?? key,
                years: Array.from(g.years.entries())
                    .sort((a, b) => b[0] - a[0])
                    .map(([year, items]) => ({ year, items })),
            }));
    }, [list]);

    // ---- KICKOFF: la timeline parte dal calcio d'inizio (minuto 0), non dal pre-match.
    // kickoffTs = ts della prima voce score_timeline con minute===0;
    // fallback: primo frame con inplay===true; ultimo fallback: primo frame in assoluto.
    const kickoffTs = useMemo(() => {
        if (!replay) return null;
        const zero = replay.score_timeline.find(e => e.minute === 0);
        if (zero?.ts) return zero.ts;
        const sorted = [...replay.frames].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
        const ip = sorted.find(f => f.inplay === true);
        return ip?.ts ?? sorted[0]?.ts ?? null;
    }, [replay]);

    // ---- timeline: griglia temporale ~10s (scorribile), non ogni singolo tick ----
    // (i frame sono migliaia; raggruppiamo a bucket di 10s per un playback usabile;
    //  currentLadder usa comunque l'ultimo frame <= currentTs, quindi è preciso).
    // I bucket PRIMA del kickoff vengono scartati → index 0 = calcio d'inizio.
    const TIMELINE_BUCKET_MS = 10_000;
    const timeline = useMemo(() => {
        if (!replay) return [] as { ts: string; minute: number | null }[];
        const byBucket = new Map<number, { ts: string; minute: number | null }>();
        for (const f of replay.frames) {
            const b = Math.floor(new Date(f.ts).getTime() / TIMELINE_BUCKET_MS);
            const cur = byBucket.get(b);
            if (!cur) byBucket.set(b, { ts: f.ts, minute: f.minute });
            else if (cur.minute == null && f.minute != null) cur.minute = f.minute;
        }
        // scarta i bucket PRIMA del kickoff confrontando la CHIAVE-bucket (non il ts
        // del primo frame del bucket): così il bucket che contiene il kickoff resta
        // anche se include frame pre-match nello stesso intervallo di 10s.
        const kBucket = kickoffTs ? Math.floor(new Date(kickoffTs).getTime() / TIMELINE_BUCKET_MS) : null;
        return Array.from(byBucket.entries())
            .filter(([k]) => kBucket == null || k >= kBucket)
            .sort(([, a], [, b]) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0))
            .map(([, step]) => step);
    }, [replay, kickoffTs]);

    const maxIndex = Math.max(0, timeline.length - 1);
    const safeIndex = Math.min(currentIndex, maxIndex);
    const current = timeline[safeIndex] ?? { ts: '', minute: null };
    const currentTs = current.ts;
    const currentMinute = current.minute;
    const currentMs = currentTs ? new Date(currentTs).getTime() : 0;

    // ---- frame raggruppati per mercato (ordinati per ts) ----
    const framesByMarket = useMemo(() => {
        const map = new Map<string, Frame[]>();
        if (!replay) return map;
        for (const f of replay.frames) {
            const arr = map.get(f.market_id) ?? [];
            arr.push(f);
            map.set(f.market_id, arr);
        }
        for (const arr of map.values()) arr.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
        return map;
    }, [replay]);

    // ---- snapshot del book per (mercato, selezione) per il motore di matching ----
    // sequenza BookSnapshot ordinata per ts, costruita una volta e cache-ata: la usano
    // sia i fill reali degli ordini sia la validazione esecuzione degli arbitraggi.
    const selectionSnaps = useMemo(() => {
        const cache = new Map<string, BookSnapshot[]>();
        return (marketId: string, sid: number): BookSnapshot[] => {
            const key = `${marketId}:${sid}`;
            let s = cache.get(key);
            if (!s) {
                const arr = framesByMarket.get(marketId) ?? [];
                s = arr.map(f => {
                    const e = f.ladder?.[String(sid)];
                    return {
                        ts: new Date(f.ts).getTime(),
                        back: e?.back ?? [],
                        lay: e?.lay ?? [],
                        ltp: e?.ltp ?? null,
                        tv: e?.tv ?? null,
                        trd: e?.trd,
                        status: f.status,
                    };
                });
                cache.set(key, s);
            }
            return s;
        };
    }, [framesByMarket]);

    // ladder di un mercato a un dato ts = ultimo frame con frame.ts <= ts.
    // bisect-right sui frame ordinati per ts → O(log n).
    const ladderAtTs = (marketId: string, ts: string): LadderMap | undefined => {
        const arr = framesByMarket.get(marketId);
        if (!arr || arr.length === 0 || !ts) return undefined;
        let lo = 0, hi = arr.length; // primo indice con ts > target
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid].ts <= ts) lo = mid + 1; else hi = mid;
        }
        const found: Frame | undefined = lo > 0 ? arr[lo - 1] : undefined;
        return found?.ladder;
    };
    // ladder corrente di un mercato = ultimo frame con ts <= currentTs.
    const currentLadder = (marketId: string): LadderMap | undefined => ladderAtTs(marketId, currentTs);

    // status di un mercato a un dato ts = status dell'ultimo frame con ts <= ts (bisect).
    const statusAtTs = (arr: Frame[] | undefined, ts: string): string | null => {
        if (!arr || arr.length === 0 || !ts) return null;
        let lo = 0, hi = arr.length;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid].ts <= ts) lo = mid + 1; else hi = mid;
        }
        return lo > 0 ? arr[lo - 1].status : null;
    };
    // status corrente (frame <= currentTs) di un mercato — per il badge SOSPESO/CHIUSO.
    const currentStatus = (marketId: string): string | undefined =>
        statusAtTs(framesByMarket.get(marketId), currentTs) ?? undefined;

    // ---- score timeline pre-ordinata PER TIMESTAMP (non per minuto) ----
    const sortedScoreTimeline = useMemo(() => {
        if (!replay) return [];
        return [...replay.score_timeline].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    }, [replay]);

    // ---- EVENTI DELLA PARTITA sulla barra timeline (gol/cartellini/angoli) ----
    // Normalizza score_timeline in marker posizionati lungo la track:
    //  • usa event_type quando presente (Goal/YellowCard/RedCard/Corner/…);
    //  • DERIVA i gol dagli incrementi di punteggio quando event_type è null
    //    (registrazioni precedenti alla cattura eventi: solo i SCORE cambiano).
    // Dedup: se un'entry ha event_type 'Goal' la usiamo come gol e NON deriviamo
    // anche dal suo delta di punteggio (l'esplicito ha precedenza sul derivato).
    const timelineEvents = useMemo(() => {
        if (!replay || timeline.length === 0) return [];
        const homeName = replay.event.home_name || 'Casa';
        const awayName = replay.event.away_name || 'Ospiti';
        const firstTs = new Date(timeline[0].ts).getTime();
        const lastTs = new Date(timeline[maxIndex].ts).getTime();
        const span = lastTs - firstTs;
        const pctOf = (ts: string) => {
            if (!Number.isFinite(span) || span <= 0) return 0;
            const p = (new Date(ts).getTime() - firstTs) / span;
            return p < 0 ? 0 : p > 1 ? 1 : p;
        };
        type Marker = { ts: string; pctLeft: number; kind: string; team?: string | null; minute: number | null; label: string };
        const out: Marker[] = [];
        const teamName = (t: string | null | undefined) => (t === 'home' ? homeName : t === 'away' ? awayName : null);
        const numH = (p: any, k: string) => Number(p?.score?.home?.[k] ?? 0) || 0;
        const numA = (p: any, k: string) => Number(p?.score?.away?.[k] ?? 0) || 0;
        const add = (ev: typeof sortedScoreTimeline[number], kind: string, team: string | null, label: string) =>
            out.push({ ts: ev.ts, pctLeft: pctOf(ev.ts), kind, team, minute: ev.minute, label });

        // se ci sono eventi DISCRETI (get_event_timeline) usiamo SOLO quelli; altrimenti
        // deriviamo TUTTO dai delta (punteggio → gol; conteggi payload → cartellini/angoli).
        const hasDiscrete = sortedScoreTimeline.some(e => !!e.event_type);
        let prevHome = 0, prevAway = 0;
        let pYH = 0, pYA = 0, pRH = 0, pRA = 0, pCH = 0, pCA = 0;

        for (const ev of sortedScoreTimeline) {
            const ty = (ev.event_type || '').toLowerCase();
            const curHome = ev.score_home ?? prevHome;
            const curAway = ev.score_away ?? prevAway;
            const dHome = curHome - prevHome;
            const dAway = curAway - prevAway;

            if (hasDiscrete) {
                if (ty === 'goal') {
                    const team = ev.payload?.team ?? (dHome > 0 ? 'home' : dAway > 0 ? 'away' : null);
                    const who = teamName(team);
                    add(ev, 'goal', team, who ? `Gol ${who}` : 'Gol');
                } else if (ty === 'yellowcard' || ty === 'yellow_card') {
                    const who = teamName(ev.payload?.team);
                    add(ev, 'yellow', ev.payload?.team ?? null, who ? `Giallo ${who}` : 'Cartellino giallo');
                } else if (ty === 'redcard' || ty === 'red_card') {
                    const who = teamName(ev.payload?.team);
                    add(ev, 'red', ev.payload?.team ?? null, who ? `Rosso ${who}` : 'Cartellino rosso');
                } else if (ty === 'corner') {
                    const who = teamName(ev.payload?.team);
                    add(ev, 'corner', ev.payload?.team ?? null, who ? `Angolo ${who}` : "Calcio d'angolo");
                }
                // KickOff/HalfTime/... = fasi: non renderizzate.
            } else {
                // GOL dai delta di punteggio
                if (dHome > 0) add(ev, 'goal', 'home', `Gol ${homeName}`);
                if (dAway > 0) add(ev, 'goal', 'away', `Gol ${awayName}`);
                // CARTELLINI / ANGOLI dai conteggi cumulativi nel payload
                const yh = numH(ev.payload, 'numberOfYellowCards'), ya = numA(ev.payload, 'numberOfYellowCards');
                const rh = numH(ev.payload, 'numberOfRedCards'), ra = numA(ev.payload, 'numberOfRedCards');
                const ch = numH(ev.payload, 'numberOfCorners'), ca = numA(ev.payload, 'numberOfCorners');
                if (yh > pYH) add(ev, 'yellow', 'home', `Giallo ${homeName}`);
                if (ya > pYA) add(ev, 'yellow', 'away', `Giallo ${awayName}`);
                if (rh > pRH) add(ev, 'red', 'home', `Rosso ${homeName}`);
                if (ra > pRA) add(ev, 'red', 'away', `Rosso ${awayName}`);
                if (ch > pCH) add(ev, 'corner', 'home', `Angolo ${homeName}`);
                if (ca > pCA) add(ev, 'corner', 'away', `Angolo ${awayName}`);
                pYH = Math.max(pYH, yh); pYA = Math.max(pYA, ya);
                pRH = Math.max(pRH, rh); pRA = Math.max(pRA, ra);
                pCH = Math.max(pCH, ch); pCA = Math.max(pCA, ca);
            }
            if (ev.score_home != null) prevHome = ev.score_home;
            if (ev.score_away != null) prevAway = ev.score_away;
        }
        return out;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [replay, sortedScoreTimeline, timeline, maxIndex]);

    // ---- punteggio + minuto all'istante corrente: ultima voce con ts <= currentTs.
    // (FIX: prima usava il minuto con fallback +Infinity → in pre-match mostrava il
    //  punteggio finale; ora è ancorato al timestamp del replay.) ----
    const currentScoreEntry = useMemo(() => {
        if (!currentTs) return null;
        let best: typeof sortedScoreTimeline[number] | null = null;
        for (const ev of sortedScoreTimeline) {
            if (ev.ts <= currentTs) best = ev; else break;
        }
        return best;
    }, [sortedScoreTimeline, currentTs]);

    const currentScore = currentScoreEntry
        ? { home: currentScoreEntry.score_home ?? 0, away: currentScoreEntry.score_away ?? 0 }
        : { home: 0, away: 0 };
    const displayMinute = currentScoreEntry?.minute ?? currentMinute;

    // ---- mercati ordinati per sort_priority ----
    const markets = useMemo(() => {
        if (!replay) return [];
        return [...replay.markets].sort(
            (a, b) => (a.sort_priority ?? Number.MAX_SAFE_INTEGER) - (b.sort_priority ?? Number.MAX_SAFE_INTEGER),
        );
    }, [replay]);

    // ========================================================================
    // MOTORE OPPORTUNITÀ — snapshot a bucket 10s (stessa granularità della timeline),
    // detection completa per snapshot (memoizzata), marker arbitraggi sulla barra,
    // e Report di validazione su tutta la partita.
    // ========================================================================
    const OPP_CFG = DEFAULT_OPP_CONFIG; // stake 100, minProfitPct 0.5, comm 5%, delay 6s

    const snapshots = useMemo(
        () => (replay ? buildSnapshots(replay, TIMELINE_BUCKET_MS) : []),
        [replay],
    );

    // detection completa (Opportunity[]) per ogni snapshot; i factory tier1 ricevono
    // lo storico = snapshot precedenti. Una sola passata per replay (memoizzata),
    // con storico INCREMENTALE (push dopo la detection) → O(n), niente slice(0,i).
    const detectionsPerSnap = useMemo<Opportunity[][]>(
        () => {
            const history: typeof snapshots = [];
            const out: Opportunity[][] = [];
            for (const s of snapshots) {
                out.push(runDetectors(s, harnessDetectors(history), OPP_CFG));
                history.push(s);
            }
            return out;
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [snapshots],
    );

    // indice della snapshot corrispondente al ts corrente (ultima con ts <= currentTs).
    const curSnapIdx = useMemo(() => {
        if (!currentTs || snapshots.length === 0) return -1;
        const cur = new Date(currentTs).getTime();
        let idx = -1;
        for (let i = 0; i < snapshots.length; i++) {
            if (new Date(snapshots[i].ts).getTime() <= cur) idx = i; else break;
        }
        return idx;
    }, [snapshots, currentTs]);

    const rawOpps = curSnapIdx >= 0 ? (detectionsPerSnap[curSnapIdx] ?? []) : [];

    // GATE ESECUZIONE ARBITRAGGI: un arb (tier 'arb') è "garantito" solo se TUTTE le
    // gambe si abbinerebbero ai prezzi mostrati anche DOPO il ritardo Betfair. Lo
    // verifichiamo col motore di matching (selectionSnaps + ritardo in-play): se anche
    // una gamba non reggerebbe, l'arb non è affidabile e viene nascosto. Gli altri tier
    // (low/directional) passano invariati.
    const currentOpps = useMemo(() => {
        if (rawOpps.length === 0) return rawOpps;
        const inPlay = currentMinute != null && currentMinute >= 0;
        return rawOpps.filter(o =>
            o.tier !== 'arb'
            || arbExecutableUnderDelay(o, selectionSnaps, currentMs, inPlay, OPP_CFG.delaySec * 1000),
        );
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [rawOpps, selectionSnaps, currentMs, currentMinute]);

    // marker degli istanti con un arbitraggio rilevato (rombi verdi sulla barra).
    const arbMarkers = useMemo(() => {
        if (snapshots.length === 0 || timeline.length === 0) return [];
        const firstTs = new Date(timeline[0].ts).getTime();
        const lastTs = new Date(timeline[maxIndex].ts).getTime();
        const span = lastTs - firstTs;
        const out: { pctLeft: number; minute: number | null; label: string }[] = [];
        for (let i = 0; i < snapshots.length; i++) {
            const arb = detectionsPerSnap[i]?.find(o => o.tier === 'arb');
            if (!arb) continue;
            const t = new Date(snapshots[i].ts).getTime();
            if (span > 0 && t < firstTs) continue; // pre-kickoff
            const p = span > 0 ? (t - firstTs) / span : 0;
            out.push({ pctLeft: Math.min(Math.max(p, 0), 1), minute: snapshots[i].minute, label: arb.title });
        }
        return out;
    }, [snapshots, detectionsPerSnap, timeline, maxIndex]);

    // Report di validazione (eseguibili vs teoriche, % media, per fase).
    // Riusa snapshots + detectionsPerSnap già calcolati → nessuna seconda passata
    // di detection né ricostruzione delle snapshot.
    const validationReport = useMemo(
        () => (snapshots.length > 0 ? validateFromDetections(snapshots, detectionsPerSnap, OPP_CFG, TIMELINE_BUCKET_MS) : null),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [snapshots, detectionsPerSnap],
    );

    // ---- SOSPENSIONI sulla barra: per ogni step della timeline, MATCH_ODDS sospeso?
    // (ultimo frame MATCH_ODDS con ts <= step.ts === 'SUSPENDED'; se non c'è MATCH_ODDS,
    //  usa: QUALSIASI mercato sospeso a quell'istante). Allineato agli indici della timeline.
    const suspended = useMemo(() => {
        const matchOddsIds = markets.filter(m => (m.market_type || '').toUpperCase() === 'MATCH_ODDS').map(m => m.market_id);
        return timeline.map(step => {
            if (matchOddsIds.length > 0) {
                return matchOddsIds.some(id => statusAtTs(framesByMarket.get(id), step.ts) === 'SUSPENDED');
            }
            for (const arr of framesByMarket.values()) {
                if (statusAtTs(arr, step.ts) === 'SUSPENDED') return true;
            }
            return false;
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [timeline, framesByMarket, markets]);

    // ---- categorizzazione mercati in tab ----
    const categorized = useMemo(() => {
        const byCat = new Map<CatKey, typeof markets>();
        for (const m of markets) {
            const k = categoryOf(m.market_type);
            const arr = byCat.get(k) ?? [];
            arr.push(m);
            byCat.set(k, arr);
        }
        // ordinamento: Over/Under e First Half per linea ASC; gli altri restano per sort_priority.
        for (const [k, arr] of byCat) {
            if (k === 'OVER_UNDER' || k === 'FIRST_HALF') {
                arr.sort((a, b) => lineOf(a.market_type) - lineOf(b.market_type));
            }
        }
        return byCat;
    }, [markets]);

    // tab presenti, nell'ordine canonico, solo categorie con >=1 mercato.
    const presentCategories = useMemo(
        () => CATEGORIES.filter(c => (categorized.get(c.key)?.length ?? 0) > 0),
        [categorized],
    );
    // categoria attiva "sicura": se quella selezionata non è presente, ripiega sulla prima.
    const activeCat: CatKey = presentCategories.some(c => c.key === activeCategory)
        ? activeCategory
        : (presentCategories[0]?.key ?? 'MATCH_ODDS');
    const activeMarkets = categorized.get(activeCat) ?? [];

    // ---- contesto esito: partita finita = fine del replay (ultimo frame, mercati
    // chiusi). NON usiamo "minuto>=90": col recupero si settlerebbero in anticipo i
    // mercati a fine-gara (Match Odds/Under) mentre possono ancora entrare gol. ----
    const finished = safeIndex >= maxIndex;
    const ctx: SettleCtx = { home: currentScore.home, away: currentScore.away, finished };

    // ---- FILL REALI: ogni ordine viene risolto dal motore di matching (matching.ts)
    // contro la sequenza di snapshot del book fino all'istante corrente. È pura e
    // deterministica → lo scrubbing avanti/indietro è coerente. La `bets` derivata
    // (porzioni ABBINATE, quota = VWAP) alimenta posizioni, cash-out e Trades.
    const bets: SimBet[] = useMemo(() => {
        if (!replay) return [];
        return orders.map(o => {
            // un ordine chiuso (cash-out) congela la simulazione al suo istante di chiusura
            const upto = o.closed && o.closedTs != null ? Math.min(currentMs, o.closedTs) : currentMs;
            const req: OrderRequest = {
                side: o.side,
                limitPrice: o.limitPrice,
                stake: o.requested,
                placedTs: o.placedTs,
                inPlay: o.inPlay,
                delayMs: o.inPlay ? OPP_CFG.delaySec * 1000 : 0,
                persistence: o.persistence,
                cancelledTs: o.cancelledTs ?? null,
            };
            const res = simulateOrder(req, selectionSnaps(o.marketId, o.selectionId), upto);
            return {
                id: o.id,
                marketId: o.marketId,
                selectionId: o.selectionId,
                selectionName: o.selectionName,
                marketName: o.marketName,
                side: o.side,
                odds: res.avgPrice ?? o.limitPrice,
                stake: res.matched,
                requestedStake: o.requested,
                minute: o.minute,
                limitPrice: o.limitPrice,
                remaining: res.remaining,
                matchStatus: res.status,
                closed: o.closed,
                realizedPnl: o.realizedPnl,
            } satisfies SimBet;
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [replay, orders, selectionSnaps, currentMs]);

    // valutazione per-mercato: P&L DEFINITIVO se l'esito è deciso, altrimenti cash-out.
    const marketEval = (m: typeof markets[number]) => settleOrCashOut(
        {
            bets: bets.filter(b => b.marketId === m.market_id && !b.closed),
            ladder: currentLadder(m.market_id),
            selectionIds: m.selections.map(s => s.selection_id),
            market: { market_type: m.market_type, selections: m.selections },
        } as MarketSettleEval,
        ctx,
    );

    // ---- overall = P&L realizzato (cash-out passati) + settlement/cash-out dei mercati aperti ----
    const overall = useMemo(() => {
        if (!replay) return realizedPnl;
        const evals: MarketSettleEval[] = markets
            .map(m => ({
                bets: bets.filter(b => b.marketId === m.market_id && !b.closed),
                ladder: currentLadder(m.market_id),
                selectionIds: m.selections.map(s => s.selection_id),
                market: { market_type: m.market_type, selections: m.selections },
            }))
            .filter(e => e.bets.length > 0);
        return realizedPnl + overallSettled(evals, ctx);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [bets, markets, safeIndex, framesByMarket, realizedPnl, ctx.home, ctx.away, ctx.finished]);

    // ---- loop di riproduzione ----
    const idxRef = useRef(safeIndex);
    idxRef.current = safeIndex;
    useEffect(() => {
        if (!isPlaying) return;
        const interval = Math.max(50, Math.round(playSpeed / speedMult));
        const id = setInterval(() => {
            const next = idxRef.current + playDir;
            if (next < 0 || next > maxIndex) { setIsPlaying(false); return; }
            idxRef.current = next;
            setCurrentIndex(next);
        }, interval);
        return () => clearInterval(id);
    }, [isPlaying, playDir, playSpeed, speedMult, maxIndex]);

    // ---- controlli ----
    const togglePlay = () => { setPlayDir(1); setIsPlaying(p => !p); };
    const fastForward = () => { setPlayDir(1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const rewind = () => { setPlayDir(-1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const stepFwd = () => { setIsPlaying(false); setCurrentIndex(i => Math.min(maxIndex, i + 1)); };
    const stepBack = () => { setIsPlaying(false); setCurrentIndex(i => Math.max(0, i - 1)); };
    const skipStart = () => { setIsPlaying(false); setCurrentIndex(0); };
    const skipEnd = () => { setIsPlaying(false); setCurrentIndex(maxIndex); };

    // ---- gestione ordini ----
    const getStake = (marketId: string) => stakes[marketId] ?? 100;
    // Piazzamento REALE: l'utente clicca una quota O (il best back/lay visibile) con
    // stake S → si crea un ORDINE a quota limite O. Gli abbinamenti effettivi (quanto,
    // a quale quota media, quando) li calcola il motore di matching (matching.ts) contro
    // il book registrato, esattamente come farebbe Betfair: taker immediato col ritardo
    // in-play + resto a riposo che si riempie nel tempo. Lo stesso codice andrà in live.
    const placeBet = (m: { market_id: string; market_name: string | null; market_type: string | null }) =>
        (selectionId: number, selectionName: string, side: BetSide, price: number) => {
            const requested = getStake(m.market_id);
            if (requested <= 0 || price <= 1) return;
            const inPlay = currentMinute != null && currentMinute >= 0;
            setOrders(prev => [...prev, {
                id: uid(),
                marketId: m.market_id,
                selectionId,
                selectionName,
                marketName: m.market_name || m.market_type || 'Mercato',
                side,
                limitPrice: price,
                requested,
                placedTs: currentMs,
                inPlay,
                minute: currentMinute,
                persistence: 'LAPSE',
            }]);
        };
    // Annulla un ordine: se ha già una parte ABBINATA, resta (si annulla solo il resto a
    // riposo, come su Betfair); se non è abbinato nulla, sparisce dalla lista.
    const removeBet = (id: string) => setOrders(prev => prev.flatMap(o => {
        if (o.id !== id) return [o];
        const b = bets.find(x => x.id === id);
        if (b && b.stake > 1e-9) return [{ ...o, cancelledTs: currentMs }]; // tieni l'abbinato, annulla il resto
        return []; // niente abbinato → rimuovi
    }));
    // cash out: BLOCCA il valore corrente del mercato nel P&L realizzato e marca gli
    // ordini del mercato come chiusi (restano visibili nei Trades, congelati al cash-out).
    const cashOutMarket = (marketId: string) => {
        const m = markets.find(mk => mk.market_id === marketId);
        if (!m) return;
        if (bets.filter(b => b.marketId === marketId && !b.closed && b.stake > 1e-9).length === 0) return;
        const locked = marketEval(m).value;
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

    // ---- badge Overall Position ----
    const overallCls = overall > 0
        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
        : overall < 0
            ? 'bg-red-500/15 text-red-300 border-red-500/50'
            : 'bg-secondary/15 text-secondary border-secondary/40';

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Match Replay | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-secondary font-heading font-bold ml-4">
                            <History className="w-4 h-4" /> MATCH REPLAY
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/segui-live">
                            <Button variant="outline" size="sm" className="border-primary/30 text-primary hover:bg-primary/10">
                                <Radio className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Segui Live</span>
                            </Button>
                        </Link>
                        <Link to="/dashboard">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-4xl tracking-tight">
                        FOOTBALL TRADING <span className="text-secondary">SIMULATOR</span>
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Riproduci i dati di mercato registrati e piazza back/lay simulate alle quote storiche.
                    </p>
                </div>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {/* ============================ SELECTOR ============================ */}
                {!replay ? (
                    replayLoading || listLoading ? (
                        <div className="space-y-3">
                            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full bg-white/5" />)}
                        </div>
                    ) : list.length === 0 ? (
                        <Card className="glass-card border-white/10 p-10 text-center">
                            <History className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                            <p className="text-sm text-muted-foreground">Nessun replay registrato disponibile.</p>
                        </Card>
                    ) : (
                        <div className="space-y-6">
                            {groupedList.map(group => (
                                <div key={group.key} className="space-y-3">
                                    {/* header lega con logo */}
                                    <div className="flex items-center gap-3">
                                        <div className="relative w-8 h-8 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center overflow-hidden shrink-0">
                                            {/* fallback sempre presente dietro: se il logo manca/404 resta l'icona */}
                                            <History className="w-4 h-4 text-primary/60" />
                                            {group.league_id != null && (
                                                <img
                                                    src={leagueLogo(group.league_id)}
                                                    alt={group.league_name ?? ''}
                                                    loading="lazy"
                                                    decoding="async"
                                                    className="absolute inset-0 m-auto w-6 h-6 object-contain bg-black/40"
                                                    onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                                                />
                                            )}
                                        </div>
                                        <h2 className="font-heading font-bold text-sm md:text-base text-white truncate">{group.league_name}</h2>
                                    </div>

                                    {group.years.map(yg => (
                                        <div key={yg.year} className="space-y-2 pl-1">
                                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">
                                                {yg.year > 0 ? yg.year : '—'}
                                            </div>
                                            <div className="space-y-2">
                                                {yg.items.map(item => (
                                                    <Card key={item.event_id} onClick={() => selectReplay(item)}
                                                        className="glass-card border-white/10 p-4 cursor-pointer transition-colors hover:bg-white/[0.04]">
                                                        <div className="flex items-center justify-between gap-3">
                                                            <div className="min-w-0">
                                                                <div className="flex items-center gap-2 mt-0.5">
                                                                    <span className="text-emerald-400 font-bold truncate">{item.home_name}</span>
                                                                    <span className="text-white/30 text-xs">vs</span>
                                                                    <span className="text-amber-400 font-bold truncate">{item.away_name}</span>
                                                                </div>
                                                                <div className="text-[11px] text-muted-foreground mt-1">
                                                                    {(() => { try { return new Date(item.open_date).toLocaleString('it'); } catch { return item.open_date; } })()}
                                                                </div>
                                                            </div>
                                                            <div className="text-right shrink-0">
                                                                <div className="text-sm font-bold tabular-nums text-white">{item.n_markets ?? 0} mercati</div>
                                                                <div className="text-[11px] text-muted-foreground tabular-nums">{item.n_snapshots ?? 0} snapshot</div>
                                                            </div>
                                                        </div>
                                                    </Card>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ))}
                        </div>
                    )
                ) : (
                    /* ============================ SIMULATORE ============================ */
                    <div className="space-y-5">
                        {/* header: overall position + end simulation */}
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                            <span className={`inline-flex items-center px-3 py-1.5 rounded-lg border text-sm font-bold tabular-nums ${overallCls}`}>
                                Overall Position: {formatGbp(overall)}
                            </span>
                            <Button size="sm" onClick={endSimulation}
                                className="bg-secondary text-black font-bold hover:bg-secondary/90">
                                <Square className="w-4 h-4 mr-1.5" /> End Simulation
                            </Button>
                        </div>

                        {/* match header con score al minuto corrente */}
                        <Card className="glass-card border-white/10 p-4">
                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground text-center mb-1">
                                {replay.event.league_name ?? ''}
                            </div>
                            <div className="flex items-center justify-center gap-4">
                                <span className="text-emerald-400 font-bold text-lg truncate max-w-[36%] text-right">{replay.event.home_name}</span>
                                <span className="font-display font-black text-2xl md:text-3xl tabular-nums text-white">
                                    {currentScore.home} - {currentScore.away}
                                </span>
                                <span className="text-amber-400 font-bold text-lg truncate max-w-[36%]">{replay.event.away_name}</span>
                            </div>
                            <div className="text-center text-xs text-muted-foreground mt-1 tabular-nums">
                                {displayMinute != null ? `${displayMinute}'` : '—'}{finished ? ' · FT' : ''}
                            </div>
                        </Card>

                        {/* controlli + timeline */}
                        <Card className="glass-card border-white/10 p-4 space-y-4">
                            <PlaybackControls
                                isPlaying={isPlaying}
                                onSkipStart={skipStart}
                                onRewind={rewind}
                                onStepBack={stepBack}
                                onTogglePlay={togglePlay}
                                onStepForward={stepFwd}
                                onFastForward={fastForward}
                                onSkipEnd={skipEnd}
                            />
                            {/* moltiplicatore velocità x1..x5 */}
                            <div className="flex items-center justify-center gap-2">
                                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Velocità</span>
                                <div className="flex items-center gap-1">
                                    {SPEED_OPTIONS.map(s => (
                                        <button
                                            key={s}
                                            onClick={() => setSpeedMult(s)}
                                            className={`px-2.5 py-1 rounded-md text-xs font-bold tabular-nums border transition-colors ${
                                                speedMult === s
                                                    ? 'bg-primary text-black border-primary'
                                                    : 'border-white/10 text-muted-foreground hover:text-white'
                                            }`}
                                        >
                                            x{s}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <TimelineSlider
                                min={0} max={maxIndex} value={safeIndex} minute={displayMinute}
                                suspended={suspended}
                                events={timelineEvents.filter(m => !currentTs || m.ts <= currentTs)}
                                arbMarkers={arbMarkers}
                                onChange={(v) => { setIsPlaying(false); setCurrentIndex(v); }}
                            />
                        </Card>

                        {/* menu SOTTO LA TIMELINE: tab categorie mercato + pulsante Opportunità.
                            Clic su una categoria → vista mercati; clic su Opportunità → vista
                            opportunità divisa nelle 3 fasce di rischio (🟢/🟡/🟠). */}
                        <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
                            {presentCategories.map(c => (
                                <button
                                    key={c.key}
                                    onClick={() => { setView('markets'); setActiveCategory(c.key); }}
                                    className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                        view === 'markets' && activeCat === c.key
                                            ? 'bg-primary text-black border-primary'
                                            : 'border-white/10 text-muted-foreground hover:text-white'
                                    }`}
                                >
                                    {c.label}
                                    <span className="ml-1 opacity-60 tabular-nums">{categorized.get(c.key)?.length ?? 0}</span>
                                </button>
                            ))}
                            {/* separatore verticale tra mercati e Opportunità */}
                            <span className="shrink-0 w-px h-5 bg-white/10 mx-0.5" />
                            {/* pulsante OPPORTUNITÀ (fascia distinta, accento emerald) */}
                            <button
                                onClick={() => setView('opps')}
                                className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                                    view === 'opps'
                                        ? 'bg-emerald-500 text-black border-emerald-500'
                                        : 'border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10'
                                }`}
                            >
                                <Sparkles className="w-3.5 h-3.5" /> Opportunità
                                {currentOpps.length > 0 && (
                                    <span className="ml-0.5 opacity-70 tabular-nums">{currentOpps.length}</span>
                                )}
                            </button>
                        </div>

                        {view === 'opps' ? (
                            /* ===== VISTA OPPORTUNITÀ: card validazione + 3 fasce di rischio ===== */
                            <div className="space-y-4">
                                {validationReport && validationReport.totalOpportunities > 0 && (
                                    <ValidationCard report={validationReport} />
                                )}
                                <OpportunitaPanel opportunities={currentOpps} grouped />
                            </div>
                        ) : (
                            /* ===== VISTA MERCATI: griglia (categoria attiva) + trades + nota ===== */
                            <>
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {activeMarkets.map(m => {
                                        const ev = marketEval(m);
                                        return (
                                            <MarketPanel
                                                key={m.market_id}
                                                market={m}
                                                ladder={currentLadder(m.market_id)}
                                                stake={getStake(m.market_id)}
                                                onStakeChange={(n) => setStakes(prev => ({ ...prev, [m.market_id]: n }))}
                                                bets={bets.filter(b => b.marketId === m.market_id && !b.closed)}
                                                onPlaceBet={placeBet(m)}
                                                onCashOut={() => cashOutMarket(m.market_id)}
                                                marketValue={ev.value}
                                                settled={ev.settled}
                                                winnerId={ev.winnerId}
                                                status={currentStatus(m.market_id)}
                                            />
                                        );
                                    })}
                                </div>

                                {/* trades */}
                                <TradesPanel bets={bets} onRemove={removeBet} />

                                <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                                    <strong className="text-muted-foreground">Nota P&L.</strong> Semantica Betfair Exchange.
                                    BACK stake S a quota O: vince → +S·(O-1), perde → -S. LAY stake S a quota O: la selezione vince
                                    → -S·(O-1) (liability), perde → +S. <em>Position</em> di una selezione = P&L del mercato se quella
                                    selezione fosse l'esito vincente. <em>Cash out</em>/<em>Overall Position</em> = valore atteso del
                                    libro sotto le probabilità implicite normalizzate (overround rimosso) alle quote correnti.
                                    Simulazione didattica su dati storici.
                                </p>
                            </>
                        )}
                    </div>
                )}
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
