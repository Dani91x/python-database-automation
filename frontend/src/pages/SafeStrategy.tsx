// ============================================================================
// SafeStrategy.tsx — pagina della sezione SAFE STRATEGY.
//
// Radar in sola lettura: mostra i SEGNALI delle 4 strategie sulle partite
// SEGUITE dagli stream esistenti (calcio: Segui Live · tennis: sezione Tennis).
// Layout pensato per la chiarezza con molti segnali contemporanei:
//   · vista divisa per sport (Calcio / Tennis), mai mescolata;
//   · segnali ATTIVI in alto, grandi, con colore fisso per strategia;
//   · sotto, le partite monitorate con un chip per strategia (pallino verde =
//     segnale, ambra = dato mancante, spento = condizioni non soddisfatte) e
//     checklist espandibile condizione-per-condizione;
//   · storico sessione in coda, attenuato.
// L'ingresso a mercato è SEMPRE una decisione manuale dell'utente.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useSafeStrategy, type FootballMonitor, type TennisMonitor } from '@/components/safestrategy/SafeStrategyProvider';
import { SignalCard } from '@/components/safestrategy/SignalCard';
import { MonitorCard } from '@/components/safestrategy/MonitorCard';
import { ParamsSheet } from '@/components/safestrategy/ParamsSheet';
import { VARIANT_STYLE } from '@/components/safestrategy/variantStyles';
import type { ActiveSignal, Sport } from '@/lib/safeStrategy';

function footballLiveLine(m: FootballMonitor): string {
    const { minute, scoreHome, scoreAway } = m.ctx;
    const min = minute !== null ? `${minute}′` : '—′';
    const score = scoreHome !== null && scoreAway !== null ? `${scoreHome}-${scoreAway}` : '?-?';
    return `${min} · ${score}${m.follow.league_name ? ` · ${m.follow.league_name}` : ''}`;
}

function tennisLiveLine(m: TennisMonitor): string {
    const sets = m.ctx.sets ? `set ${m.ctx.sets.p1}-${m.ctx.sets.p2}` : 'set —';
    const games = m.ctx.games ? ` · game ${m.ctx.games.p1}-${m.ctx.games.p2}` : '';
    const comp = m.follow.competition_name ? ` · ${m.follow.competition_name}` : '';
    return `${sets}${games}${comp}`;
}

/** intestazione di uno dei due blocchi sport, con conteggio segnali attivi. */
function SportHeader({ emoji, title, activeCount }: { emoji: string; title: string; activeCount: number }) {
    return (
        <div className="flex items-center gap-3 mb-4">
            <span className="text-2xl" aria-hidden>{emoji}</span>
            <h2 className="font-display font-black text-xl md:text-2xl tracking-tight text-white uppercase">{title}</h2>
            <Badge
                variant="outline"
                className={
                    activeCount > 0
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 font-mono tabular-nums'
                        : 'bg-white/5 text-muted-foreground border-white/10 font-mono tabular-nums'
                }
            >
                {activeCount} {activeCount === 1 ? 'segnale attivo' : 'segnali attivi'}
            </Badge>
        </div>
    );
}

function EmptyMonitor({ sport }: { sport: Sport }) {
    const isCalcio = sport === 'calcio';
    return (
        <div className="glass-card rounded-xl border border-dashed border-white/10 p-6 text-center">
            <p className="text-sm text-muted-foreground">
                Nessun {isCalcio ? 'match di calcio' : 'match di tennis'} monitorato: Safe Strategy lavora sulle
                partite <b className="text-white">seguite</b> dallo stream {isCalcio ? 'calcio' : 'tennis'}.
            </p>
            <Link to={isCalcio ? '/segui-live' : '/tennis'}>
                <Button variant="outline" size="sm" className="mt-3 border-white/10 text-muted-foreground hover:text-white">
                    {isCalcio ? 'Vai a Segui Live' : 'Vai alla sezione Tennis'}
                </Button>
            </Link>
        </div>
    );
}

function SignalGrid({ signals, marketIdByEvent, nowMs }: {
    signals: ActiveSignal[];
    marketIdByEvent: Map<string, string | null>;
    nowMs: number;
}) {
    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {signals.map((s) => (
                <SignalCard key={s.key} signal={s} marketId={marketIdByEvent.get(s.eventId) ?? null} nowMs={nowMs} />
            ))}
        </div>
    );
}

export default function SafeStrategy() {
    const { football, tennis, signals } = useSafeStrategy();

    // orologio a 15s per le etichette "N minuti fa" (nessun refetch: solo display)
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 15_000);
        return () => window.clearInterval(t);
    }, []);

    const marketIdByEvent = useMemo(() => {
        const map = new Map<string, string | null>();
        for (const m of football) map.set(m.follow.event_id, m.ctx.matchOddsMarketId);
        for (const m of tennis) map.set(m.follow.event_id, m.ctx.matchOddsMarketId);
        return map;
    }, [football, tennis]);

    const bySport = useMemo(() => {
        const pick = (sport: Sport, status: ActiveSignal['status']) =>
            signals.filter((s) => s.sport === sport && s.status === status);
        return {
            calcioActive: pick('calcio', 'active'),
            calcioExpired: pick('calcio', 'expired'),
            tennisActive: pick('tennis', 'active'),
            tennisExpired: pick('tennis', 'expired'),
        };
    }, [signals]);

    // in-play prima, poi per orario di inizio
    const fbSorted = useMemo(
        () =>
            [...football].sort((a, b) => {
                if (a.ctx.inplay !== b.ctx.inplay) return a.ctx.inplay ? -1 : 1;
                return a.follow.open_date.localeCompare(b.follow.open_date);
            }),
        [football],
    );
    const tnSorted = useMemo(
        () =>
            [...tennis].sort((a, b) => {
                if (a.ctx.inplay !== b.ctx.inplay) return a.ctx.inplay ? -1 : 1;
                return a.follow.open_date.localeCompare(b.follow.open_date);
            }),
        [tennis],
    );

    const totalActive = bySport.calcioActive.length + bySport.tennisActive.length;

    return (
        <div className="min-h-screen bg-background relative pb-16">
            <Helmet><title>Safe Strategy | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/select-sport" className="font-display font-black text-xl tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-secondary font-heading font-bold ml-4">
                            🛡️ SAFE STRATEGY
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <ParamsSheet />
                        <Link to="/board">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                Programma
                            </Button>
                        </Link>
                        <Link to="/segui-live">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                Segui Live
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 relative z-10 max-w-6xl">
                <div className="mb-8 flex items-end justify-between flex-wrap gap-3">
                    <div>
                        <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                            Safe <span className="text-secondary">Strategy</span>
                        </h1>
                        <p className="text-[12px] text-muted-foreground mt-1 max-w-2xl">
                            Segnali automatici sulle condizioni oggettive (minuto, punteggio, quote) delle 4 strategie.
                            Il controllo del gioco e l'ingresso a mercato restano una tua decisione.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {(['base', 'esatto', 'punta', 'tennis'] as const).map((v) => (
                            <Badge key={v} variant="outline" className={`text-[10px] font-heading ${VARIANT_STYLE[v].badge}`}>
                                {VARIANT_STYLE[v].chipLabel()}
                            </Badge>
                        ))}
                    </div>
                </div>

                {totalActive === 0 && (
                    <div className="mb-8 glass-card rounded-xl border border-white/10 p-4 text-center text-sm text-muted-foreground">
                        Nessun segnale attivo in questo momento — il radar sta osservando{' '}
                        <span className="font-mono tabular-nums text-white">{football.length}</span> match di calcio e{' '}
                        <span className="font-mono tabular-nums text-white">{tennis.length}</span> di tennis.
                        Quando le condizioni di una strategia si verificano, il segnale compare qui (e come avviso se sei su un'altra schermata).
                    </div>
                )}

                {/* ============================== CALCIO ============================== */}
                <section className="mb-12">
                    <SportHeader emoji="⚽" title="Calcio" activeCount={bySport.calcioActive.length} />

                    {bySport.calcioActive.length > 0 && (
                        <div className="mb-5">
                            <SignalGrid signals={bySport.calcioActive} marketIdByEvent={marketIdByEvent} nowMs={nowMs} />
                        </div>
                    )}

                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold mb-2">
                        Partite monitorate ({fbSorted.length})
                    </div>
                    {fbSorted.length === 0 ? (
                        <EmptyMonitor sport="calcio" />
                    ) : (
                        <div className="space-y-2">
                            {fbSorted.map((m) => (
                                <MonitorCard
                                    key={m.follow.event_id}
                                    eventId={m.follow.event_id}
                                    marketId={m.ctx.matchOddsMarketId}
                                    sport="calcio"
                                    title={`${m.follow.home_name} – ${m.follow.away_name}`}
                                    liveLine={footballLiveLine(m)}
                                    inplay={m.ctx.inplay}
                                    evaluations={m.evaluations.map((evaluation) => ({ evaluation }))}
                                    dataNote={[
                                        m.ctx.oddsNameMismatch ? 'nomi selezioni non riconosciuti nel mercato — quote n/d' : null,
                                        m.preMatchMissing ? 'riferimento pre-match non catturato prima del kickoff — condizioni pre-match n/d' : null,
                                    ].filter(Boolean).join(' · ') || null}
                                />
                            ))}
                        </div>
                    )}

                    {bySport.calcioExpired.length > 0 && (
                        <details className="mt-4">
                            <summary className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold cursor-pointer select-none">
                                Storico sessione calcio ({bySport.calcioExpired.length})
                            </summary>
                            <div className="mt-2">
                                <SignalGrid signals={bySport.calcioExpired} marketIdByEvent={marketIdByEvent} nowMs={nowMs} />
                            </div>
                        </details>
                    )}
                </section>

                {/* ============================== TENNIS ============================== */}
                <section>
                    <SportHeader emoji="🎾" title="Tennis" activeCount={bySport.tennisActive.length} />

                    {bySport.tennisActive.length > 0 && (
                        <div className="mb-5">
                            <SignalGrid signals={bySport.tennisActive} marketIdByEvent={marketIdByEvent} nowMs={nowMs} />
                        </div>
                    )}

                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold mb-2">
                        Match monitorati ({tnSorted.length})
                    </div>
                    {tnSorted.length === 0 ? (
                        <EmptyMonitor sport="tennis" />
                    ) : (
                        <div className="space-y-2">
                            {tnSorted.map((m) => (
                                <MonitorCard
                                    key={m.follow.event_id}
                                    eventId={m.follow.event_id}
                                    marketId={m.ctx.matchOddsMarketId}
                                    sport="tennis"
                                    title={`${m.follow.player1_name} – ${m.follow.player2_name}`}
                                    liveLine={tennisLiveLine(m)}
                                    inplay={m.ctx.inplay}
                                    evaluations={[{ evaluation: m.evaluation }]}
                                    dataNote={m.ctx.oddsNameMismatch ? 'nomi giocatori non riconosciuti nel mercato — quote n/d' : null}
                                />
                            ))}
                        </div>
                    )}

                    {bySport.tennisExpired.length > 0 && (
                        <details className="mt-4">
                            <summary className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold cursor-pointer select-none">
                                Storico sessione tennis ({bySport.tennisExpired.length})
                            </summary>
                            <div className="mt-2">
                                <SignalGrid signals={bySport.tennisExpired} marketIdByEvent={marketIdByEvent} nowMs={nowMs} />
                            </div>
                        </details>
                    )}
                </section>

                <p className="mt-12 text-[11px] text-muted-foreground text-center max-w-3xl mx-auto">
                    Fonti dati: stream Betfair già attivi (quote realtime, punteggi e minuto dai runner calcio/tennis) —
                    nessun flusso aggiuntivo. Video e statistiche match si aprono sul sito Betfair con il tuo account.
                    Nessun ordine viene mai piazzato automaticamente da questa sezione.
                </p>
            </main>
        </div>
    );
}
