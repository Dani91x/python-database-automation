// ============================================================================
// LiveAlertBanner — banner in-app per gli avvisi limiti Betfair / sistema (#5).
// Si sottoscrive a `live_alerts` (Realtime) e mostra gli avvisi NON gestiti,
// impilati in alto: WARN=ambra, CRITICAL=rosso. Dismiss → ack_alert (acknowledged).
// Si nasconde quando non ci sono avvisi. Nessuna dipendenza esterna.
// ============================================================================
import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import {
    fetchLiveAlerts, subscribeLiveAlerts, ackAlert,
    type Alert,
} from '@/lib/live';

const LEVEL_CLS: Record<Alert['level'], string> = {
    INFO: 'border-white/15 bg-white/[0.06] text-muted-foreground',
    WARN: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
    CRITICAL: 'border-red-500/40 bg-red-500/10 text-red-400',
};

export function LiveAlertBanner() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    // id in fase di ack (evita doppi click / flicker prima del realtime).
    const [acking, setAcking] = useState<Set<number>>(new Set());

    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLiveAlerts()
                .then(rows => { if (alive) setAlerts(rows); })
                .catch(e => console.warn('[LiveAlertBanner] fetchLiveAlerts:', e));
        };
        load();
        const unsub = subscribeLiveAlerts(load);  // ricarica gli unacked a ogni cambiamento
        return () => { alive = false; unsub(); };
    }, []);

    async function dismiss(id: number) {
        setAcking(prev => new Set(prev).add(id));
        // rimozione ottimistica: l'avviso sparisce subito; il realtime conferma.
        const removed = alerts.find(a => a.id === id) ?? null;
        setAlerts(prev => prev.filter(a => a.id !== id));
        try { await ackAlert(id); }
        catch (e) {
            console.warn('[LiveAlertBanner] ackAlert:', e);
            // fix audit #24: ack FALLITO → l'avviso NON è gestito lato server. Ripristinalo
            // (mai far sparire in silenzio un alert money-critical con un ack mai avvenuto).
            if (removed) {
                setAlerts(prev => (prev.some(a => a.id === id) ? prev : [removed, ...prev]));
            }
        }
        finally { setAcking(prev => { const n = new Set(prev); n.delete(id); return n; }); }
    }

    const visible = alerts.filter(a => !a.acknowledged);
    if (visible.length === 0) return null;

    return (
        <div className="space-y-2 mb-4">
            {visible.map(a => (
                <div key={a.id}
                    className={`flex items-start gap-2 rounded-lg border px-4 py-2.5 text-sm ${LEVEL_CLS[a.level]}`}>
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <span className="font-bold uppercase tracking-wider text-[10px] mr-2">{a.level}</span>
                        {a.code && <span className="text-[10px] opacity-70 mr-2">[{a.code}]</span>}
                        <span className="align-middle">{a.message}</span>
                    </div>
                    <button
                        onClick={() => dismiss(a.id)}
                        disabled={acking.has(a.id)}
                        aria-label="Ignora avviso"
                        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity disabled:opacity-30">
                        <X className="w-4 h-4" />
                    </button>
                </div>
            ))}
        </div>
    );
}
