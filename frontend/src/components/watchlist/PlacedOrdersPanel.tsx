// ============================================================================
// PlacedOrdersPanel — "Ordini piazzati" di UNA fixture: cosa e' stato inviato a
// Betfair e lo stato di abbinamento reale (abbinato / parziale / non abbinato /
// in corso / errore), con betId e prezzo medio. Si AUTO-AGGIORNA: poll veloce (3s)
// finche' ci sono ordini in corso, lento (15s) quando tutti sono conclusi, cosi'
// ogni ordine nuovo (su questa o altre partite) compare da solo. Sola lettura.
// ============================================================================
import { useEffect, useRef, useState, useCallback } from 'react';
import { CheckCircle2, Loader2, Clock, AlertCircle, CircleDashed, CircleDot, RefreshCw, ExternalLink } from 'lucide-react';
import {
    fetchBetfairOrders, placedOrderState, type PlacedOrder, type PlacedOrderState,
} from '@/lib/betfair';

const FAST_MS = 3000;   // poll mentre ci sono ordini in corso
const SLOW_MS = 15000;  // poll quando tutti gli ordini sono conclusi

const fmtOdds = (n: number | null | undefined) => (n == null ? '—' : Number(n).toFixed(2));
const fmtEur = (n: number | null | undefined) => (n == null ? '—' : `€${Number(n).toFixed(2)}`);

// Link diretto al mercato specifico sull'Exchange .it (l'utente opera su Betfair Italia):
// così da ogni ordine si va su Betfair a controllare quel preciso mercato.
const BETFAIR_MARKET_BASE = 'https://www.betfair.it/exchange/plus/football/market/';

// Etichetta + colore + icona per ogni stato sintetico.
const STATE_META: Record<PlacedOrderState, { label: string; cls: string; Icon: typeof CheckCircle2 }> = {
    matched: { label: 'Abbinato', cls: 'text-emerald-300 border-emerald-400/40 bg-emerald-400/10', Icon: CheckCircle2 },
    partial: { label: 'Parziale', cls: 'text-amber-300 border-amber-400/40 bg-amber-400/10', Icon: CircleDot },
    unmatched: { label: 'Non abbinato', cls: 'text-sky-300 border-sky-400/40 bg-sky-400/10', Icon: CircleDashed },
    sending: { label: 'In invio', cls: 'text-blue-300 border-blue-400/40 bg-blue-400/10', Icon: Loader2 },
    queued: { label: 'In coda', cls: 'text-muted-foreground border-white/15 bg-white/[0.03]', Icon: Clock },
    error: { label: 'Errore', cls: 'text-red-300 border-destructive/40 bg-destructive/10', Icon: AlertCircle },
};

function OrderRow({ o }: { o: PlacedOrder }) {
    const st = placedOrderState(o);
    const meta = STATE_META[st];
    const res = o.result;
    const matched = res?.size_matched ?? 0;
    const avg = res?.average_price_matched ?? null;
    const betId = res?.bet_id ?? null;
    const marketId = res?.market_id ?? null;   // per il link diretto al mercato Betfair
    const sideLabel = o.side === 'back' ? 'Back' : 'Lay';
    const sideCls = o.side === 'back' ? 'text-sky-300' : 'text-rose-300';
    return (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-white/10 bg-white/[0.02] text-[11px]">
            <span className={`shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[10px] font-semibold ${meta.cls}`}>
                <meta.Icon className={`w-3 h-3 ${st === 'sending' ? 'animate-spin' : ''}`} />
                {meta.label}
            </span>
            <div className="min-w-0 flex-1">
                <div className="truncate">
                    <span className="font-bold text-white">{o.market}</span>
                    <span className="text-white/60"> · {o.selection}</span>
                    <span className={`ml-1.5 font-semibold ${sideCls}`}>{sideLabel}</span>
                    <span className="text-white/40"> @ {fmtOdds(o.price)}</span>
                    <span className="text-white/40"> · {fmtEur(o.size)}</span>
                </div>
                <div className="mt-0.5 text-[10px] text-muted-foreground/80 font-mono">
                    {st === 'error'
                        ? <span className="text-red-300">{o.error ?? res?.error ?? 'rifiutato'}</span>
                        : (st === 'queued' || st === 'sending')
                            ? <span>in attesa dal worker locale…</span>
                            : <>
                                abbinato {fmtEur(matched)}{avg ? ` @ ${fmtOdds(avg)}` : ''}
                                {betId ? <span className="text-white/40"> · betId {betId}</span> : null}
                            </>}
                </div>
            </div>
            {marketId && (
                <a
                    href={`${BETFAIR_MARKET_BASE}${marketId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    className="shrink-0 mt-0.5 text-muted-foreground/70 hover:text-primary transition-colors"
                    title="Apri questo mercato su Betfair"
                    aria-label="Apri questo mercato su Betfair"
                >
                    <ExternalLink className="w-3.5 h-3.5" />
                </a>
            )}
        </div>
    );
}

export function PlacedOrdersPanel({ fixtureId, refreshTrigger }: { fixtureId: number; refreshTrigger?: number }) {
    const [orders, setOrders] = useState<PlacedOrder[]>([]);
    const [loaded, setLoaded] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const load = useCallback((): Promise<PlacedOrder[]> => fetchBetfairOrders(fixtureId), [fixtureId]);

    useEffect(() => {
        // `cancelled` è LOCALE a questo effect: un re-run (fixtureId/refreshTrigger) non
        // deve lasciare vivo il timer del run precedente (niente polling doppio → I/O).
        let cancelled = false;
        const tick = async () => {
            try {
                const rows = await load();
                if (cancelled) return;
                setOrders(rows);
                setErr(null);
                setLoaded(true);
                const inFlight = rows.some(r => r.status === 'pending' || r.status === 'processing');
                timerRef.current = setTimeout(tick, inFlight ? FAST_MS : SLOW_MS);
            } catch (e) {
                if (cancelled) return;
                const msg = e instanceof Error ? e.message : 'errore lettura ordini';
                setErr(msg);
                setLoaded(true);
                // errori PERMANENTI (auth/owner) → STOP polling: inutile martellare il DB.
                const permanent = msg.includes('owner') || msg.includes('autorizzat');
                if (!permanent) timerRef.current = setTimeout(tick, SLOW_MS);
            }
        };
        tick();
        return () => {
            cancelled = true;
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [load, refreshTrigger]);

    // Non mostrare nulla finche' non sappiamo se ci sono ordini (evita flicker).
    if (!loaded) return null;
    if (orders.length === 0 && !err) return null;

    const inFlight = orders.some(o => o.status === 'pending' || o.status === 'processing');

    return (
        <div className="rounded-lg border border-white/10 bg-black/30 p-3 space-y-1.5">
            <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                    Ordini piazzati <span className="text-white/50">· {orders.length}</span>
                </div>
                <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/70">
                    {inFlight
                        ? <><Loader2 className="w-3 h-3 animate-spin" /> aggiornamento…</>
                        : <><RefreshCw className="w-3 h-3" /> live</>}
                </span>
            </div>
            {err && (
                <div className="text-[10px] text-red-300/90">
                    {err.includes('owner') ? 'Non autorizzato.' : `Lettura ordini KO: ${err}`}
                </div>
            )}
            {orders.map(o => <OrderRow key={o.id} o={o} />)}
        </div>
    );
}

export default PlacedOrdersPanel;
