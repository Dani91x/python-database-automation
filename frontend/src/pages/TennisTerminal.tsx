import { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { TennisNav } from '@/components/tennis/TennisNav';
import { TennisBotPanel } from '@/components/tennis/TennisBotPanel';
import {
    TennisLadderColumn, TENNIS_LADDER_SOURCE,
} from '@/components/tennis/TennisLadderColumn';
import { TennisMatchStats } from '@/components/tennis/TennisMatchStats';
import { SelectionChartPanel } from '@/components/live/SelectionChartPanel';
import { DepthPanel } from '@/components/live/DepthPanel';
import { countdownToOff } from '@/lib/matchClock';
import {
    followTennisEvent, fetchTennisFollows, fetchTennisNow, subscribeTennisNow,
    type TennisLiveNowRow,
} from '@/lib/tennis';

/**
 * SCREEN 3 — Tennis Trading Terminal (fullscreen, 3 colonne, stile trading pro).
 *
 * Layout speculare al terminal Football (SeguiLive → LiveTradingSection) ma dedicato
 * al tennis e riorganizzato secondo la specifica:
 *   SINISTRA  → Bot Panel (tutti i bot armabili in contemporanea) + equity chart
 *   CENTRO    → Ladder market-depth (LadderView sport='tennis') + trade dei bot + manuale
 *   DESTRA    → Match Stats live (punteggio set/game/point, server, punto-per-punto)
 *
 * Dati SOLO via Supabase Realtime sulle tabelle dedicate tennis (single source of truth
 * dallo stream flumine tennis). Nessuna chiamata diretta a Betfair dal browser.
 */
export default function TennisTerminal() {
    const [params] = useSearchParams();
    const navigate = useNavigate();

    const eventId = params.get('event') ?? '';
    const marketId = params.get('market') ?? '';
    const marketName = params.get('name') ?? 'Match Odds';
    const p1 = params.get('p1') ?? 'Giocatore 1';
    const p2 = params.get('p2') ?? 'Giocatore 2';

    const title = useMemo(() => `${p1} vs ${p2} · Terminal Tennis | Alpha Score`, [p1, p2]);

    // D32: score compatto in top bar (tennis_live_now.score, SOLO dati tennis) +
    // countdown all'off (open_date da tennis_live_follow) quando non in-play.
    const [now, setNow] = useState<TennisLiveNowRow | null>(null);
    const [openDate, setOpenDate] = useState<string | null>(null);
    const [nowTick, setNowTick] = useState(() => Date.now());
    useEffect(() => {
        if (!eventId) return undefined;
        let alive = true;
        fetchTennisNow(eventId).then(r => { if (alive) setNow(r); }).catch(() => {});
        const unsub = subscribeTennisNow(eventId, r => { if (r) setNow(r); });
        fetchTennisFollows()
            .then(rows => {
                if (!alive) return;
                const f = rows.find(r => r.event_id === eventId);
                setOpenDate(f?.open_date ?? null);
            })
            .catch(() => {});
        return () => { alive = false; unsub(); };
    }, [eventId]);
    useEffect(() => {
        const t = setInterval(() => setNowTick(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);
    const countdown = !now?.inplay ? countdownToOff(openDate, nowTick) : null;
    const setSummary = now?.score?.set_summary ?? null;
    const points = now?.score?.points ?? null;

    // D29/D31: tab della colonna destra (Stats / Chart / Depth) — injection SOLO tennis.
    const [rightTab, setRightTab] = useState<'stats' | 'chart' | 'depth'>('stats');

    // Modalità ordini GLOBALE del runner tennis (OFF/PAPER/LIVE, da tennis_live_now.state):
    // badge sempre visibile in top-bar — prima era invisibile e in OFF il ladder
    // sembrava "rotto" (nessun ordine, nemmeno simulato).
    const orderMode = useMemo(() => {
        const m = String(now?.state?.order_mode ?? 'OFF').trim().toUpperCase();
        return m === 'PAPER' || m === 'LIVE' ? m : 'OFF';
    }, [now]) as 'OFF' | 'PAPER' | 'LIVE';

    // Registra l'evento nello stream tennis (tennis_live_follow → PENDING) così il runner
    // inizia a pubblicare ladder + tabellone + punteggio su tennis_live_ladder/tennis_live_now.
    // Senza questo la ladder resterebbe vuota in una sessione manuale (nessun bot armato):
    // il bot-service auto-registra solo gli eventi con bot armati.
    useEffect(() => {
        if (!eventId || !marketId) return;
        followTennisEvent(eventId, marketId).catch(() => {
            /* best-effort: non blocca la UI se la registrazione fallisce (retry al prossimo mount) */
        });
    }, [eventId, marketId]);

    if (!eventId || !marketId) {
        return (
            <div className="min-h-screen bg-background relative">
                <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />
                <TennisNav sectionLabel="TERMINAL" onBack={() => navigate('/tennis')} />
                <main className="container mx-auto px-6 py-20 relative z-10 text-center">
                    <p className="text-muted-foreground">
                        Nessun match selezionato. Torna alle{' '}
                        <button className="text-primary underline" onClick={() => navigate('/tennis')}>
                            Partite del Giorno
                        </button>
                        .
                    </p>
                </main>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background relative flex flex-col">
            <Helmet>
                <title>{title}</title>
            </Helmet>

            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-20" />

            <TennisNav sectionLabel="TERMINAL" onBack={() => navigate('/tennis')} />

            {/* Header match compatto */}
            <div className="border-b border-white/5 bg-black/40 backdrop-blur-xl sticky top-16 z-40">
                <div className="w-full px-4 lg:px-6 h-12 flex items-center gap-3 text-sm">
                    <span className="font-display font-black tracking-tight text-white">
                        {p1} <span className="text-white/30 mx-1">vs</span> {p2}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">· {marketName}</span>
                    {/* D32: score live (set_summary + punti del game) o countdown all'off */}
                    {now?.inplay && setSummary && (
                        <span className="text-[11px] font-mono tabular-nums text-emerald-300 font-black"
                            title={`Punteggio set (tennis_live_now)${points ? ` · game: ${points.p1}–${points.p2}` : ''}`}>
                            {setSummary}{points ? ` · ${points.p1}–${points.p2}` : ''}
                        </span>
                    )}
                    {countdown && (
                        <span className="text-[11px] font-mono tabular-nums text-amber-300"
                            title="Countdown all'inizio del match (open_date)">
                            OFF in {countdown}
                        </span>
                    )}
                    {/* badge modalità ordini del runner (regola specchio: PAPER = demo
                        identica al vivo, cambia solo che i soldi non sono veri) */}
                    <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-black ${
                            orderMode === 'LIVE' ? 'bg-red-500 text-white'
                                : orderMode === 'PAPER' ? 'bg-amber-500 text-black'
                                    : 'bg-slate-700 text-slate-300'
                        }`}
                        title={orderMode === 'LIVE'
                            ? 'Runner in LIVE: gli ordini sono REALI (soldi veri).'
                            : orderMode === 'PAPER'
                                ? 'Runner in PAPER: ordini SIMULATI, visibili sul ladder come dal vivo.'
                                : 'Runner ordini SPENTO: nessun ordine possibile, nemmeno simulato. Imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia il runner tennis.'}
                    >
                        {orderMode === 'LIVE' ? 'LIVE · REALE' : orderMode === 'PAPER' ? 'PAPER · SIMULATO' : 'ORDINI OFF'}
                    </span>
                    <span className="ml-auto text-[10px] text-muted-foreground font-mono">
                        event {eventId} · market {marketId}
                    </span>
                </div>
            </div>

            {/* Griglia 3 colonne ad alta densità (stile SeguiLive: sinistra fissa | centro fluido | destra fissa) */}
            <main className="flex-1 w-full px-3 lg:px-4 py-3 relative z-10">
                <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)_360px] gap-3 items-start">
                    <section key={`bot:${eventId}:${marketId}`} className="min-w-0">
                        <TennisBotPanel eventId={eventId} marketId={marketId} orderMode={orderMode} />
                    </section>

                    <section key={`ladder:${eventId}:${marketId}`} className="min-w-0">
                        <TennisLadderColumn
                            eventId={eventId}
                            marketId={marketId}
                            marketName={marketName}
                            p1={p1}
                            p2={p2}
                        />
                    </section>

                    <section key={`stats:${eventId}:${marketId}`} className="min-w-0 space-y-2">
                        {/* tab colonna destra: Stats / Chart (D29) / Depth (D31) — dati SOLO tennis */}
                        <div className="flex items-stretch gap-1 border-b border-white/5">
                            {([['stats', 'Stats'], ['chart', 'Chart'], ['depth', 'Depth']] as const).map(([k, label]) => (
                                <button
                                    key={k}
                                    type="button"
                                    aria-pressed={rightTab === k}
                                    onClick={() => setRightTab(k)}
                                    className={`px-2.5 py-1 -mb-px rounded-t-lg text-[11px] font-bold border-b-2 transition-colors ${
                                        rightTab === k
                                            ? 'border-amber-400 text-white bg-white/[0.06]'
                                            : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                                    }`}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                        {rightTab === 'stats' && <TennisMatchStats eventId={eventId} p1={p1} p2={p2} />}
                        {rightTab === 'chart' && (
                            <SelectionChartPanel
                                key={`chart:${marketId}`}
                                marketId={marketId}
                                ladderSource={TENNIS_LADDER_SOURCE}
                                defaultBucketMs={5_000}
                            />
                        )}
                        {rightTab === 'depth' && (
                            <DepthPanel key={`depth:${marketId}`} marketId={marketId} ladderSource={TENNIS_LADDER_SOURCE} />
                        )}
                    </section>
                </div>
            </main>
        </div>
    );
}
