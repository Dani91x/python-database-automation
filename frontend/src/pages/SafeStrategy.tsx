// ============================================================================
// SafeStrategy.tsx — pagina della sezione SAFE STRATEGY.
//
// Radar in sola lettura alimentato dallo SCANNER AUTONOMO backend: monitora
// TUTTI gli eventi calcio+tennis in-play del momento (nessuna iscrizione
// manuale). Layout pensato per la chiarezza con molti segnali contemporanei:
//   · barra di stato dello scanner SEMPRE visibile (attivo/spento, conteggi);
//   · vista divisa per sport (Calcio / Tennis), mai mescolata;
//   · segnali ATTIVI in alto, grandi, con colore fisso per strategia;
//   · sotto, gli eventi monitorati con un chip per strategia e checklist
//     espandibile condizione-per-condizione;
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
import type { ScanStatusRow } from '@/lib/safeStrategyScan';

/** heartbeat scanner più vecchio di così = scanner considerato NON attivo */
const SCANNER_STALE_MS = 45_000;

function footballLiveLine(m: FootballMonitor): string {
    const { minute, scoreHome, scoreAway, inplay } = m.ctx;
    const min = minute !== null ? `${minute}′` : '—′';
    const score = scoreHome !== null && scoreAway !== null ? `${scoreHome}-${scoreAway}` : '?-?';
    const comp = m.payload.competition ? ` · ${m.payload.competition}` : '';
    return inplay ? `${min} · ${score}${comp}` : `pre-KO${comp}`;
}

function tennisLiveLine(m: TennisMonitor): string {
    const sets = m.ctx.sets ? `set ${m.ctx.sets.p1}-${m.ctx.sets.p2}` : 'set —';
    const games = m.ctx.games ? ` · game ${m.ctx.games.p1}-${m.ctx.games.p2}` : '';
    const comp = m.payload.competition ? ` · ${m.payload.competition}` : '';
    return m.ctx.inplay ? `${sets}${games}${comp}` : `pre-match${comp}`;
}

/** barra di stato dello scanner: l'utente deve SEMPRE sapere se il radar è vivo. */
function ScannerBar({ status, nowMs }: { status: ScanStatusRow | null; nowMs: number }) {
    const updatedMs = status?.updated_at ? Date.parse(status.updated_at) : null;
    const ageSec = updatedMs !== null ? Math.max(0, Math.round((nowMs - updatedMs) / 1000)) : null;
    const alive = ageSec !== null && ageSec * 1000 <= SCANNER_STALE_MS;
    const p = status?.payload ?? {};
    return (
        <div
            className={[
                'mb-6 glass-card rounded-xl border p-3 flex items-center gap-3 flex-wrap text-sm',
                alive ? 'border-emerald-500/30' : 'border-red-500/40',
            ].join(' ')}
        >
            <span
                className={`inline-block w-2.5 h-2.5 rounded-full ${
                    alive ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'
                }`}
                aria-hidden
            />
            <span className="font-heading font-bold text-white uppercase tracking-wide text-xs">
                Scanner {alive ? 'attivo' : 'non attivo'}
            </span>
            {alive ? (
                <>
                    <span className="font-mono tabular-nums text-muted-foreground text-xs">
                        ultimo giro {ageSec}s fa
                    </span>
                    <span className="text-xs text-muted-foreground">
                        ⚽ <b className="text-white font-mono tabular-nums">{p.calcio_inplay ?? 0}</b> in-play
                        <span className="mx-2 text-white/20">·</span>
                        🎾 <b className="text-white font-mono tabular-nums">{p.tennis_inplay ?? 0}</b> in-play
                        <span className="mx-2 text-white/20">·</span>
                        <b className="text-white font-mono tabular-nums">{p.monitored ?? 0}</b> monitorati
                    </span>
                    {p.dry && (
                        <Badge variant="outline" className="bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]">
                            DRY
                        </Badge>
                    )}
                    {p.last_error && (
                        <span className="text-[11px] text-amber-300/90" title={p.last_error}>
                            ⚠ ultimo errore: {p.last_error}
                        </span>
                    )}
                </>
            ) : (
                <span className="text-xs text-muted-foreground">
                    {status === null
                        ? 'nessun heartbeat: servizio scanner mai visto (migrazione safe_strategy_scan.sql applicata? app riavviata dopo l’aggiornamento?)'
                        : `ultimo heartbeat ${ageSec}s fa — il servizio scanner non sta girando: riavvia l’app desktop`}
                </span>
            )}
        </div>
    );
}

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
    return (
        <div className="glass-card rounded-xl border border-dashed border-white/10 p-6 text-center">
            <p className="text-sm text-muted-foreground">
                Nessun {sport === 'calcio' ? 'match di calcio' : 'match di tennis'} in-play in questo
                momento: lo scanner aggiunge gli eventi da solo appena vanno live (o a ridosso del kickoff).
            </p>
        </div>
    );
}

function SignalGrid({ signals, nowMs }: { signals: ActiveSignal[]; nowMs: number }) {
    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {signals.map((s) => (
                <SignalCard key={s.key} signal={s} nowMs={nowMs} />
            ))}
        </div>
    );
}

export default function SafeStrategy() {
    const { football, tennis, signals, scanStatus } = useSafeStrategy();

    // orologio a 10s: etichette "N s fa" + freschezza heartbeat scanner
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 10_000);
        return () => window.clearInterval(t);
    }, []);

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
                return (a.payload.open_date ?? '').localeCompare(b.payload.open_date ?? '');
            }),
        [football],
    );
    const tnSorted = useMemo(
        () =>
            [...tennis].sort((a, b) => {
                if (a.ctx.inplay !== b.ctx.inplay) return a.ctx.inplay ? -1 : 1;
                return (a.payload.open_date ?? '').localeCompare(b.payload.open_date ?? '');
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
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 relative z-10 max-w-6xl">
                <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
                    <div>
                        <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                            Safe <span className="text-secondary">Strategy</span>
                        </h1>
                        <p className="text-[12px] text-muted-foreground mt-1 max-w-2xl">
                            Scanner autonomo su TUTTI gli eventi in-play: segnali automatici sulle condizioni
                            oggettive (minuto, punteggio, quote) delle 4 strategie. Il controllo del gioco e
                            l'ingresso a mercato restano una tua decisione.
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

                <ScannerBar status={scanStatus} nowMs={nowMs} />

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
                            <SignalGrid signals={bySport.calcioActive} nowMs={nowMs} />
                        </div>
                    )}

                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold mb-2">
                        Eventi monitorati ({fbSorted.length})
                    </div>
                    {fbSorted.length === 0 ? (
                        <EmptyMonitor sport="calcio" />
                    ) : (
                        <div className="space-y-2">
                            {fbSorted.map((m) => (
                                <MonitorCard
                                    key={m.eventId}
                                    eventId={m.eventId}
                                    title={`${m.ctx.home} – ${m.ctx.away}`}
                                    liveLine={footballLiveLine(m)}
                                    inplay={m.ctx.inplay}
                                    evaluations={m.evaluations.map((evaluation) => ({ evaluation }))}
                                    dataNote={m.preMatchMissing ? 'riferimento pre-KO non catturato (scanner partito a match iniziato) — condizioni pre-match n/d' : null}
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
                                <SignalGrid signals={bySport.calcioExpired} nowMs={nowMs} />
                            </div>
                        </details>
                    )}
                </section>

                {/* ============================== TENNIS ============================== */}
                <section>
                    <SportHeader emoji="🎾" title="Tennis" activeCount={bySport.tennisActive.length} />

                    {bySport.tennisActive.length > 0 && (
                        <div className="mb-5">
                            <SignalGrid signals={bySport.tennisActive} nowMs={nowMs} />
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
                                    key={m.eventId}
                                    eventId={m.eventId}
                                    title={`${m.ctx.p1} – ${m.ctx.p2}`}
                                    liveLine={tennisLiveLine(m)}
                                    inplay={m.ctx.inplay}
                                    evaluations={[{ evaluation: m.evaluation }]}
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
                                <SignalGrid signals={bySport.tennisExpired} nowMs={nowMs} />
                            </div>
                        </details>
                    )}
                </section>

                <p className="mt-12 text-[11px] text-muted-foreground text-center max-w-3xl mx-auto">
                    Fonte dati: scanner autonomo Betfair (quote a lotti, punteggi in-play, riferimento
                    pre-KO congelato al kickoff) — cadenze adattive nei limiti API. Video e statistiche si
                    aprono sul popup ufficiale Betfair col tuo account. Nessun ordine viene mai piazzato
                    automaticamente da questa sezione.
                </p>
            </main>
        </div>
    );
}
