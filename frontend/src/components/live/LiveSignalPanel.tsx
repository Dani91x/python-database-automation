// ============================================================================
// LiveSignalPanel — segnali del Motore Live (#2) per una partita seguita.
// Si sottoscrive alla riga `live_signals` dell'evento (Realtime) e mostra, per
// ogni mercato, una card con: direzione (BACK=emerald / LAY=gold / HOLD=muted),
// barra di confidenza (0..1), fair vs quota di mercato, edge %, Kelly stake (£).
// Stesso design system di LiveMarketBoard (glass-card, tabular-nums).
// ============================================================================
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Cpu, TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import {
    fetchLiveSignals, subscribeLiveSignals,
    type Signal, type SignalDirection, type LiveNowState,
} from '@/lib/live';

// soglia oltre cui i segnali sono considerati "non aggiornati" (motore fermo?).
const STALE_MS = 45_000;

const clamp01 = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);
const fmtOdds = (v: number | null) => (v != null && Number.isFinite(v) ? v.toFixed(2) : '—');
const fmtPct = (v: number | null) => (v != null && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '—');

// Chip direzione: BACK → emerald (primary), LAY → gold (secondary), HOLD → muted.
function DirectionChip({ dir }: { dir: SignalDirection }) {
    const cfg = {
        BACK: { cls: 'bg-primary/15 text-primary border-primary/30', Icon: TrendingUp, label: 'BACK' },
        LAY: { cls: 'bg-secondary/15 text-secondary border-secondary/30', Icon: TrendingDown, label: 'LAY' },
        HOLD: { cls: 'bg-white/5 text-muted-foreground border-white/10', Icon: Minus, label: 'HOLD' },
    }[dir];
    const { Icon } = cfg;
    return (
        <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cfg.cls}`}>
            <Icon className="w-3 h-3" /> {cfg.label}
        </span>
    );
}

// Barra di confidenza 0..1 (colorata in base alla direzione).
function ConfidenceBar({ value, dir }: { value: number; dir: SignalDirection }) {
    const w = clamp01(value) * 100;
    const fill = dir === 'BACK' ? 'bg-primary' : dir === 'LAY' ? 'bg-secondary' : 'bg-white/30';
    return (
        <div className="flex items-center gap-2">
            <div className="relative h-1.5 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div className={`absolute h-full ${fill}`} style={{ width: `${w}%` }} />
            </div>
            <span className="text-[10px] tabular-nums text-muted-foreground w-9 text-right">{w.toFixed(0)}%</span>
        </div>
    );
}

function SignalRow({ s }: { s: Signal }) {
    // Per i BACK conta la quota back (fair vs mercato), per i LAY la quota lay.
    const isLay = s.direction === 'LAY';
    const fair = isLay ? s.fair_lay : s.fair_back;
    const mkt = isLay ? s.market_lay : s.market_back;
    const edgePos = (s.edge ?? 0) > 0;
    return (
        <div className="grid grid-cols-[1fr_auto] gap-2 items-start py-2 border-b border-white/5 last:border-b-0">
            <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm text-white truncate">{s.selection_name ?? `#${s.selection_id}`}</span>
                    <DirectionChip dir={s.direction} />
                </div>
                <div className="mt-1.5 max-w-[220px]">
                    <ConfidenceBar value={s.confidence} dir={s.direction} />
                </div>
            </div>
            <div className="text-right shrink-0 space-y-0.5">
                <div className="text-[11px] text-muted-foreground tabular-nums">
                    fair <span className="text-white font-medium">{fmtOdds(fair)}</span>
                    {' '}· mkt <span className="text-white font-medium">{fmtOdds(mkt)}</span>
                </div>
                <div className="text-[11px] tabular-nums">
                    edge <span className={`font-bold ${s.edge == null ? 'text-muted-foreground' : edgePos ? 'text-primary' : 'text-red-400'}`}>
                        {s.edge == null ? '—' : (edgePos ? '+' : '') + fmtPct(s.edge)}
                    </span>
                </div>
                <div className="text-[11px] text-muted-foreground tabular-nums">
                    Kelly <span className="text-white font-medium">£{(s.kelly_stake ?? 0).toFixed(2)}</span>
                </div>
            </div>
        </div>
    );
}

export function LiveSignalPanel({ eventId, state }: { eventId: string; state?: LiveNowState | null }) {
    const [signals, setSignals] = useState<Signal[] | null>(null);
    const [updatedMs, setUpdatedMs] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        setLoading(true);
        setSignals(null);
        setUpdatedMs(null);

        fetchLiveSignals(eventId)
            .then(row => {
                if (!alive) return;
                setSignals(row?.signals?.signals ?? []);
                setUpdatedMs(row?.signals?.updated_ms ?? null);
            })
            .catch((e: any) => {
                // PGRST116 = nessuna riga (motore non ancora attivo): atteso.
                if (e?.code !== 'PGRST116') console.warn('[LiveSignalPanel] fetchLiveSignals:', e);
                if (alive) setSignals([]);
            })
            .finally(() => { if (alive) setLoading(false); });

        const unsub = subscribeLiveSignals(eventId, (row) => {
            if (!row) return;  // DELETE → mantieni l'ultimo stato noto
            setSignals(row.signals?.signals ?? []);
            setUpdatedMs(row.signals?.updated_ms ?? null);
        });

        return () => { alive = false; unsub(); };
    }, [eventId]);

    // stato per-mercato da live_now: per nascondere i segnali dei mercati CHIUSI.
    const statusByMarket = new Map<string, string>();
    for (const m of state?.markets ?? []) statusByMarket.set(m.market_id, (m.status ?? '').toUpperCase());
    const isStale = updatedMs != null && Date.now() - updatedMs > STALE_MS;

    // Segnali AZIONABILI: niente mercati CHIUSI, niente HOLD (nessuna azione).
    const actionable = (signals ?? []).filter(s =>
        statusByMarket.get(s.market_id) !== 'CLOSED' && s.direction !== 'HOLD',
    );
    const hiddenCount = (signals ?? []).length - actionable.length;

    // Raggruppa per mercato; righe ordinate per edge desc, mercati per edge max desc.
    const edgeOf = (s: Signal) => s.edge ?? -Infinity;
    const byMarket = new Map<string, { name: string; type: string | null; rows: Signal[] }>();
    for (const s of actionable) {
        const key = s.market_id;
        if (!byMarket.has(key)) {
            byMarket.set(key, { name: s.market_name || s.market_type || s.market_id, type: s.market_type, rows: [] });
        }
        byMarket.get(key)!.rows.push(s);
    }
    for (const m of byMarket.values()) m.rows.sort((a, b) => edgeOf(b) - edgeOf(a));
    const markets = Array.from(byMarket.entries())
        .sort((a, b) => Math.max(...b[1].rows.map(edgeOf)) - Math.max(...a[1].rows.map(edgeOf)));

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
                <span className="flex items-center gap-2 font-heading font-bold text-sm">
                    <Cpu className="w-4 h-4 text-primary" /> Segnali Motore Live
                </span>
                {updatedMs && (
                    <span className={`inline-flex items-center gap-1 text-[10px] tabular-nums ${isStale ? 'text-amber-400' : 'text-muted-foreground'}`}>
                        {isStale && <AlertTriangle className="w-3 h-3" />}
                        {isStale ? 'non aggiornato · ' : ''}{new Date(updatedMs).toLocaleTimeString('it')}
                    </span>
                )}
            </div>

            {loading && signals == null ? (
                <div className="p-3 space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 w-full bg-white/5" />)}
                </div>
            ) : markets.length === 0 ? (
                <div className="p-6 text-center text-sm text-muted-foreground">
                    Nessun segnale azionabile al momento{hiddenCount > 0 ? ` (${hiddenCount} in HOLD o su mercati chiusi)` : ''}.
                </div>
            ) : (
                <div className="p-3 space-y-3">
                    {markets.map(([id, m]) => (
                        <div key={id} className="rounded-lg border border-white/10 bg-black/30">
                            <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between">
                                <span className="text-xs font-heading font-bold text-white truncate">{m.name}</span>
                                {m.type && <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.type}</span>}
                            </div>
                            <div className="px-3">
                                {m.rows.map(s => <SignalRow key={`${id}:${s.selection_id}`} s={s} />)}
                            </div>
                        </div>
                    ))}
                    {hiddenCount > 0 && (
                        <div className="text-[10px] text-muted-foreground text-center pt-1">
                            {hiddenCount} segnali nascosti (HOLD o mercati chiusi)
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}
