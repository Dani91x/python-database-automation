import { useEffect, useMemo } from 'react';
import { Helmet } from 'react-helmet-async';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { TennisNav } from '@/components/tennis/TennisNav';
import { TennisBotPanel } from '@/components/tennis/TennisBotPanel';
import { TennisLadderColumn } from '@/components/tennis/TennisLadderColumn';
import { TennisMatchStats } from '@/components/tennis/TennisMatchStats';
import { followTennisEvent } from '@/lib/tennis';

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
                    <span className="ml-auto text-[10px] text-muted-foreground font-mono">
                        event {eventId} · market {marketId}
                    </span>
                </div>
            </div>

            {/* Griglia 3 colonne ad alta densità (stile SeguiLive: sinistra fissa | centro fluido | destra fissa) */}
            <main className="flex-1 w-full px-3 lg:px-4 py-3 relative z-10">
                <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)_360px] gap-3 items-start">
                    <section key={`bot:${eventId}:${marketId}`} className="min-w-0">
                        <TennisBotPanel eventId={eventId} marketId={marketId} />
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

                    <section key={`stats:${eventId}:${marketId}`} className="min-w-0">
                        <TennisMatchStats eventId={eventId} p1={p1} p2={p2} />
                    </section>
                </div>
            </main>
        </div>
    );
}
