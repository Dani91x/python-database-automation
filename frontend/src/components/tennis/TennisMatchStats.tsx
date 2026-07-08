// ============================================================================
// TennisMatchStats.tsx — Colonna DESTRA del Tennis Trading Terminal (Screen 3).
//
// Statistiche live del match: scoreboard set/game/point, giocatore al servizio,
// punto-per-punto, pressione (break/set/game point) e probabilità di vittoria.
//
// DATA LAYER: legge ESCLUSIVAMENTE da '@/lib/tennis' (tennis_live_now):
//   - fetchTennisNow(eventId)     -> snapshot iniziale
//   - subscribeTennisNow(...)     -> realtime Supabase su tennis_live_now
// Nessun accesso diretto a Supabase qui: tutta la disciplina "tennis-only" resta
// centralizzata in lib/tennis.ts. Il componente è puramente presentazionale +
// gestione sottoscrizione/ciclo di vita.
//
// Mappatura: p1 = home (sortPriority 1) · p2 = away — coerente con TennisScoreState.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Circle, Zap, TrendingUp, Clock, Trophy } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
    fetchTennisNow,
    subscribeTennisNow,
    type TennisLiveNowRow,
    type TennisScoreState,
    type TennisPointEvent,
} from '@/lib/tennis';

export interface TennisMatchStatsProps {
    eventId: string;
    p1: string;
    p2: string;
}

// Numero massimo di punti mostrati nella cronologia punto-per-punto.
const MAX_POINTS = 40;
// Freschezza: oltre questa soglia (in-play) il dato è "vecchio" → rosso.
const STALE_MS = 15_000;

// --------------------------------------------------------------------------- utils
/** Timestamp più recente del row (updated_ms del punteggio o updated_at ISO). */
function rowUpdatedMs(row: TennisLiveNowRow | null): number | null {
    if (!row) return null;
    const scoreMs = row.score?.updated_ms ?? null;
    if (typeof scoreMs === 'number' && scoreMs > 0) return scoreMs;
    if (row.updated_at) {
        const t = Date.parse(row.updated_at);
        return Number.isNaN(t) ? null : t;
    }
    return null;
}

/** "agg. Xs fa" / "agg. Xm fa" a partire da un epoch ms. */
function freshnessLabel(ms: number | null, now: number): string {
    if (ms == null) return 'agg. —';
    const deltaS = Math.max(0, Math.round((now - ms) / 1000));
    if (deltaS < 60) return `agg. ${deltaS}s fa`;
    const m = Math.floor(deltaS / 60);
    const s = deltaS % 60;
    return `agg. ${m}m ${s}s fa`;
}

// --------------------------------------------------------------------------- hook
/** Sottoscrizione a tennis_live_now: snapshot iniziale + realtime, cleanup on unmount. */
function useTennisNow(eventId: string) {
    const [row, setRow] = useState<TennisLiveNowRow | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let alive = true;
        setLoading(true);
        setError(null);

        fetchTennisNow(eventId)
            .then((snap) => {
                if (!alive) return;
                setRow(snap);
            })
            .catch((e: unknown) => {
                if (!alive) return;
                setError(e instanceof Error ? e.message : 'Errore caricamento punteggio');
            })
            .finally(() => {
                if (alive) setLoading(false);
            });

        const unsub = subscribeTennisNow(eventId, (next) => {
            // Il realtime può inviare `null` su DELETE: in tal caso conserviamo
            // l'ultimo stato buono (evita flicker della UI).
            if (next) setRow(next);
        });

        return () => {
            alive = false;
            unsub();
        };
    }, [eventId]);

    return { row, loading, error };
}

/** Tick 1s per aggiornare la freschezza senza dipendere dal flusso realtime. */
function useNowTick(): number {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = window.setInterval(() => setNow(Date.now()), 1000);
        return () => window.clearInterval(id);
    }, []);
    return now;
}

// --------------------------------------------------------------------------- sub-components

/** Indicatore "pallina" del servizio (oro pieno se è il giocatore al servizio). */
function ServerDot({ active }: { active: boolean }) {
    return (
        <Circle
            className={cn(
                'w-2.5 h-2.5 shrink-0 transition-colors',
                active ? 'fill-secondary text-secondary drop-shadow-[0_0_4px_hsl(var(--secondary))]' : 'text-white/15',
            )}
            aria-hidden
        />
    );
}

/** Riga di celle "game per-set" (game_sequence), evidenzia il set corrente. */
function SetCells({ cells, currentIdx, leading }: { cells: string[]; currentIdx: number; leading: boolean[] }) {
    if (!cells.length) return <span className="text-white/25 text-[11px] font-mono">—</span>;
    return (
        <div className="flex items-center gap-1">
            {cells.map((c, i) => {
                const isCurrent = i === currentIdx;
                const won = leading[i];
                return (
                    <span
                        key={i}
                        className={cn(
                            'inline-flex items-center justify-center min-w-[18px] h-5 px-1 rounded font-mono text-xs tabular-nums',
                            isCurrent
                                ? 'bg-primary/20 text-primary ring-1 ring-primary/40 font-bold'
                                : won
                                  ? 'bg-white/5 text-white/90 font-semibold'
                                  : 'bg-white/[0.02] text-white/45',
                        )}
                    >
                        {c}
                    </span>
                );
            })}
        </div>
    );
}

/** Una riga giocatore dello scoreboard. */
function ScoreRow({
    name,
    isServer,
    setsWon,
    setCells,
    currentSetIdx,
    setLeading,
    games,
    point,
    leadingMatch,
}: {
    name: string;
    isServer: boolean;
    setsWon: number;
    setCells: string[];
    currentSetIdx: number;
    setLeading: boolean[];
    games: number;
    point: string;
    leadingMatch: boolean;
}) {
    return (
        <div
            className={cn(
                'flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors',
                leadingMatch ? 'bg-primary/[0.06]' : 'bg-transparent',
            )}
        >
            <ServerDot active={isServer} />
            <div className="flex-1 min-w-0">
                <div
                    className={cn(
                        'truncate text-sm font-heading font-bold leading-tight',
                        leadingMatch ? 'text-white' : 'text-white/80',
                    )}
                    title={name}
                >
                    {name}
                </div>
            </div>

            {/* set vinti — grande */}
            <div className="w-6 text-center font-mono font-black text-lg tabular-nums text-secondary leading-none">
                {setsWon}
            </div>

            {/* game per-set */}
            <div className="hidden sm:flex items-center">
                <SetCells cells={setCells} currentIdx={currentSetIdx} leading={setLeading} />
            </div>

            {/* game del set corrente */}
            <div className="w-6 text-center font-mono font-bold text-base tabular-nums text-white/90 leading-none">
                {games}
            </div>

            {/* punto corrente / tie-break */}
            <div
                className={cn(
                    'w-8 text-center font-mono font-black text-lg tabular-nums leading-none',
                    isServer ? 'text-primary' : 'text-white',
                )}
            >
                {point}
            </div>
        </div>
    );
}

/** Chip tag per un punto (BREAK / SET / GAME). */
function PointTag({ tag }: { tag: string }) {
    const t = tag.toLowerCase();
    const map: Record<string, string> = {
        break: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
        set: 'bg-red-500/15 text-red-400 border-red-500/30',
        game: 'bg-white/5 text-white/60 border-white/10',
    };
    const cls = map[t] ?? 'bg-white/5 text-white/60 border-white/10';
    return (
        <span className={cn('inline-flex items-center rounded border px-1 py-0 text-[9px] font-bold uppercase tracking-wide', cls)}>
            {t === 'break' ? 'BREAK' : t === 'set' ? 'SET' : t === 'game' ? 'GAME' : tag}
        </span>
    );
}

/** Riga singola della cronologia punto-per-punto. */
function PointRow({ pt, p1, p2 }: { pt: TennisPointEvent; p1: string; p2: string }) {
    const winnerName = pt.winner === 1 ? p1 : pt.winner === 2 ? p2 : '—';
    return (
        <div className="flex items-center gap-2 py-1 px-2 border-b border-white/[0.04] last:border-0 text-xs">
            {/* set/game index */}
            <span className="font-mono text-[10px] text-white/35 w-9 shrink-0 tabular-nums">
                {pt.set_no != null ? `S${pt.set_no}` : 'S–'}
                {pt.game_no != null ? `·G${pt.game_no}` : ''}
            </span>

            {/* dot vincitore */}
            <Circle
                className={cn(
                    'w-2 h-2 shrink-0',
                    pt.winner === 1
                        ? 'fill-primary text-primary'
                        : pt.winner === 2
                          ? 'fill-secondary text-secondary'
                          : 'text-white/20',
                )}
                aria-hidden
            />

            {/* vincitore */}
            <span
                className={cn(
                    'truncate flex-1 min-w-0 font-medium',
                    pt.winner === 1 ? 'text-primary/90' : pt.winner === 2 ? 'text-secondary/90' : 'text-white/50',
                )}
                title={winnerName}
            >
                {winnerName}
            </span>

            {/* tag */}
            {pt.tags && pt.tags.length > 0 && (
                <span className="flex items-center gap-0.5 shrink-0">
                    {pt.tags.slice(0, 3).map((t, i) => (
                        <PointTag key={i} tag={t} />
                    ))}
                </span>
            )}

            {/* server */}
            {pt.server != null && (
                <span className="font-mono text-[9px] text-white/30 shrink-0" title="servizio">
                    sv{pt.server}
                </span>
            )}

            {/* score dopo il punto */}
            <span className="font-mono text-[11px] text-white/70 tabular-nums w-12 text-right shrink-0">
                {pt.score_after ?? ''}
            </span>
        </div>
    );
}

// --------------------------------------------------------------------------- main

/**
 * Widget live-score professionale per la colonna destra del terminal tennis.
 * Alta densità informativa in ~360px: scoreboard, status, pressione, win-prob,
 * break di servizio e punto-per-punto scrollabile.
 */
export function TennisMatchStats({ eventId, p1, p2 }: TennisMatchStatsProps) {
    const { row, loading, error } = useTennisNow(eventId);
    const now = useNowTick();

    const score: TennisScoreState | null = row?.score ?? null;
    const inplay = !!row?.inplay;
    const suspended = (row?.status ?? '').toUpperCase() === 'SUSPENDED';

    const updatedMs = rowUpdatedMs(row);
    const staleAgeMs = updatedMs != null ? now - updatedMs : null;
    const isStale = inplay && staleAgeMs != null && staleAgeMs > STALE_MS;

    // Cronologia punti: più recente in cima, capata.
    const points = useMemo(() => {
        const src = row?.points ?? [];
        return src.slice(-MAX_POINTS).reverse();
    }, [row?.points]);

    // Riferimento per auto-scroll in cima quando arrivano nuovi punti.
    const listRef = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        if (listRef.current) listRef.current.scrollTop = 0;
    }, [points.length]);

    // ---- Derivazioni scoreboard ------------------------------------------------
    const setsP1 = score?.sets.p1 ?? 0;
    const setsP2 = score?.sets.p2 ?? 0;
    const gamesP1 = score?.games.p1 ?? 0;
    const gamesP2 = score?.games.p2 ?? 0;
    const pointP1 = score?.points.p1 ?? '0';
    const pointP2 = score?.points.p2 ?? '0';
    const server = score?.server ?? null;
    const tiebreak = !!score?.tiebreak;

    const seqP1 = score?.game_sequence.p1 ?? [];
    const seqP2 = score?.game_sequence.p2 ?? [];
    // Indice del set corrente all'interno della sequenza (ultima colonna in gioco).
    const currentSetIdx = Math.max(seqP1.length, seqP2.length) - 1;
    // Per ogni colonna, chi conduce (per l'evidenza sottile).
    const setLen = Math.max(seqP1.length, seqP2.length);
    const leadingP1: boolean[] = [];
    const leadingP2: boolean[] = [];
    for (let i = 0; i < setLen; i++) {
        const a = Number(seqP1[i] ?? -1);
        const b = Number(seqP2[i] ?? -1);
        leadingP1.push(a > b);
        leadingP2.push(b > a);
    }

    // Chi conduce il match (per l'highlight di riga): set → game → punto numerico.
    let matchLeader: 1 | 2 | 0 = 0;
    if (setsP1 !== setsP2) matchLeader = setsP1 > setsP2 ? 1 : 2;
    else if (gamesP1 !== gamesP2) matchLeader = gamesP1 > gamesP2 ? 1 : 2;

    const winProb = score?.win_prob_p1 ?? null;
    const winP1Pct = winProb != null ? Math.round(winProb * 100) : null;
    const winP2Pct = winP1Pct != null ? 100 - winP1Pct : null;

    const pressure = score?.pressure ?? { break_point: false, set_point: false, game_point: false };
    const breaksP1 = score?.service_breaks.p1 ?? 0;
    const breaksP2 = score?.service_breaks.p2 ?? 0;

    // ---- Render ----------------------------------------------------------------
    return (
        <div className="flex flex-col gap-3 w-full">
            {/* ====================== HEADER + STATUS STRIP ====================== */}
            <div className="flex items-center justify-between gap-2">
                <h3 className="font-display font-black text-sm uppercase tracking-wider text-white flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-primary" />
                    Match Stats
                </h3>
                <div className="flex items-center gap-1.5">
                    {suspended ? (
                        <Badge variant="outline" className="border-amber-400/40 text-amber-300 text-[10px] px-1.5 py-0">
                            SOSPESO
                        </Badge>
                    ) : inplay ? (
                        <Badge className="bg-primary/15 text-primary border border-primary/30 text-[10px] px-1.5 py-0 gap-1">
                            <span className="relative flex h-1.5 w-1.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary" />
                            </span>
                            IN CORSO
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="border-white/15 text-white/50 text-[10px] px-1.5 py-0">
                            PRE-MATCH
                        </Badge>
                    )}
                    {tiebreak && (
                        <Badge variant="outline" className="border-secondary/40 text-secondary text-[10px] px-1.5 py-0">
                            TIE-BREAK
                        </Badge>
                    )}
                </div>
            </div>

            {/* ====================== SCOREBOARD ====================== */}
            <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm overflow-hidden">
                {/* intestazione colonne */}
                <div className="flex items-center gap-2 px-2 pt-2 pb-1 text-[9px] uppercase tracking-wider text-white/30 font-heading font-bold">
                    <span className="w-2.5" />
                    <span className="flex-1">Giocatore</span>
                    <span className="w-6 text-center">Set</span>
                    <span className="hidden sm:inline">Set-by-set</span>
                    <span className="w-6 text-center">Gm</span>
                    <span className="w-8 text-center">Pt</span>
                </div>

                {score ? (
                    <div className="px-1 pb-1.5">
                        <ScoreRow
                            name={p1}
                            isServer={server === 1}
                            setsWon={setsP1}
                            setCells={seqP1}
                            currentSetIdx={currentSetIdx}
                            setLeading={leadingP1}
                            games={gamesP1}
                            point={pointP1}
                            leadingMatch={matchLeader === 1}
                        />
                        <ScoreRow
                            name={p2}
                            isServer={server === 2}
                            setsWon={setsP2}
                            setCells={seqP2}
                            currentSetIdx={currentSetIdx}
                            setLeading={leadingP2}
                            games={gamesP2}
                            point={pointP2}
                            leadingMatch={matchLeader === 2}
                        />

                        {/* riga freschezza + set summary */}
                        <div className="flex items-center justify-between gap-2 px-2 pt-1.5 mt-0.5 border-t border-white/[0.04]">
                            {score.set_summary && (
                                <span className="font-mono text-[10px] text-white/40 tabular-nums truncate">
                                    {score.set_summary}
                                </span>
                            )}
                            <span
                                className={cn(
                                    'flex items-center gap-1 text-[10px] font-mono ml-auto shrink-0',
                                    isStale ? 'text-red-400 font-bold' : 'text-white/35',
                                )}
                                title={score.source ? `sorgente: ${score.source}` : undefined}
                            >
                                <Clock className="w-2.5 h-2.5" />
                                {freshnessLabel(updatedMs, now)}
                            </span>
                        </div>
                    </div>
                ) : (
                    // stato PRE-MATCH / attesa dati
                    <div className="px-4 py-6 text-center">
                        <div className="flex flex-col items-center gap-1.5">
                            <span className="font-heading font-bold text-sm text-white/70 truncate max-w-full" title={p1}>
                                {p1}
                            </span>
                            <span className="text-[10px] uppercase tracking-widest text-white/25 font-bold">vs</span>
                            <span className="font-heading font-bold text-sm text-white/70 truncate max-w-full" title={p2}>
                                {p2}
                            </span>
                        </div>
                        <p className="mt-3 text-xs text-white/40">
                            {loading
                                ? 'Caricamento punteggio…'
                                : error
                                  ? `Errore: ${error}`
                                  : 'In attesa dei dati punteggio (inizio match)…'}
                        </p>
                    </div>
                )}
            </Card>

            {/* ====================== PRESSIONE ====================== */}
            {score && (pressure.break_point || pressure.set_point || pressure.game_point) && (
                <div className="flex flex-wrap items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-amber-300" />
                    {pressure.break_point && (
                        <Badge className="bg-amber-400/15 text-amber-300 border border-amber-400/40 text-[10px] px-2 py-0 font-bold">
                            BREAK POINT
                        </Badge>
                    )}
                    {pressure.set_point && (
                        <Badge className="bg-red-500/15 text-red-400 border border-red-500/40 text-[10px] px-2 py-0 font-bold">
                            SET POINT
                        </Badge>
                    )}
                    {pressure.game_point && (
                        <Badge variant="outline" className="border-white/20 text-white/70 text-[10px] px-2 py-0 font-bold">
                            GAME POINT
                        </Badge>
                    )}
                </div>
            )}

            {/* ====================== WIN PROBABILITY ====================== */}
            {winP1Pct != null && winP2Pct != null && (
                <Card className="bg-white/[0.02] border-white/5 p-2.5">
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[10px] uppercase tracking-wider text-white/40 font-heading font-bold">
                            Win Probability
                        </span>
                        <Trophy className="w-3 h-3 text-secondary/60" />
                    </div>
                    <div className="flex items-center justify-between mb-1 text-xs font-mono font-bold tabular-nums">
                        <span className="text-primary">{winP1Pct}%</span>
                        <span className="text-secondary">{winP2Pct}%</span>
                    </div>
                    <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/5">
                        <div
                            className="h-full bg-primary transition-all duration-500 ease-out"
                            style={{ width: `${winP1Pct}%` }}
                        />
                        <div
                            className="h-full bg-secondary transition-all duration-500 ease-out"
                            style={{ width: `${winP2Pct}%` }}
                        />
                    </div>
                    <div className="flex items-center justify-between mt-1 text-[9px] text-white/35 font-heading truncate gap-2">
                        <span className="truncate" title={p1}>
                            {p1}
                        </span>
                        <span className="truncate text-right" title={p2}>
                            {p2}
                        </span>
                    </div>
                </Card>
            )}

            {/* ====================== SERVICE BREAKS ====================== */}
            {score && (
                <div className="flex items-center gap-2 text-[11px]">
                    <span className="uppercase tracking-wider text-white/35 font-heading font-bold text-[10px]">
                        Break servizio
                    </span>
                    <div className="flex items-center gap-2 ml-auto font-mono tabular-nums">
                        <span className="flex items-center gap-1">
                            <span className="text-white/50 truncate max-w-[90px]" title={p1}>
                                {p1}
                            </span>
                            <span className="text-primary font-bold">{breaksP1}</span>
                        </span>
                        <span className="text-white/15">·</span>
                        <span className="flex items-center gap-1">
                            <span className="text-white/50 truncate max-w-[90px]" title={p2}>
                                {p2}
                            </span>
                            <span className="text-secondary font-bold">{breaksP2}</span>
                        </span>
                    </div>
                </div>
            )}

            {/* ====================== PUNTO-PER-PUNTO ====================== */}
            <Card className="bg-white/[0.02] border-white/5 overflow-hidden flex flex-col">
                <div className="flex items-center justify-between px-2 py-1.5 border-b border-white/5">
                    <span className="text-[10px] uppercase tracking-wider text-white/40 font-heading font-bold">
                        Punto per punto
                    </span>
                    {points.length > 0 && (
                        <span className="text-[9px] font-mono text-white/25 tabular-nums">{points.length}</span>
                    )}
                </div>
                {points.length > 0 ? (
                    <div ref={listRef} className="max-h-64 overflow-y-auto overscroll-contain">
                        {points.map((pt, i) => (
                            <PointRow key={`${pt.ts}-${i}`} pt={pt} p1={p1} p2={p2} />
                        ))}
                    </div>
                ) : (
                    <p className="px-3 py-4 text-center text-xs text-white/30">
                        Nessun dettaglio punto-per-punto disponibile
                    </p>
                )}
            </Card>
        </div>
    );
}

export default TennisMatchStats;
