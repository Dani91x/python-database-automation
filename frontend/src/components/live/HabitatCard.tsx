// ============================================================================
// HabitatCard — "Partite adatte oggi" per lo SCALPER.
// Il servizio scalper (avvia_scalper_service.bat, GIÀ in esecuzione per il
// bot) esegue ogni 30 min l'habitat scan (regola certificata sui replay:
// fascia media liquida che OSCILLA) e scrive la classifica in
// scalper_activity (event_id='habitat'). Questa card legge l'ULTIMO scan via
// get_scalper_state('habitat') e mostra i verdetti GO/NO: l'utente vede
// SUBITO dove accendere lo scalper, senza valutazioni a occhio.
// ============================================================================
import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Target, Loader2 } from 'lucide-react';
import { fetchScalperState } from '@/lib/scalper';

interface HabitatRow {
    market_id: string;
    event: string;
    ko: string;
    tv: number;
    depth: number;
    spread: number;
    osc: number;
    score: number;
    verdict: string;
}

export function HabitatCard({ pollMs = 60000 }: { pollMs?: number }) {
    const [rows, setRows] = useState<HabitatRow[] | null>(null);
    const [scannedAt, setScannedAt] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        const load = async () => {
            try {
                const st = await fetchScalperState('habitat', 1);
                const last = st.activity.find(a => a.kind === 'habitat_scan');
                if (alive && last) {
                    const payload = last.payload as { rows?: HabitatRow[] };
                    setRows(payload.rows ?? []);
                    setScannedAt(last.ts);
                }
            } catch {
                /* servizio non attivo: la card resta discreta */
            } finally {
                if (alive) setLoading(false);
            }
        };
        void load();
        const id = setInterval(() => void load(), pollMs);
        return () => { alive = false; clearInterval(id); };
    }, [pollMs]);

    if (loading) {
        return (
            <div className="rounded-xl border border-white/10 bg-white/5 p-3 flex items-center gap-2 text-white/40 text-xs">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Habitat scan…
            </div>
        );
    }
    if (!rows) {
        return (
            <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/40">
                <Target className="h-3.5 w-3.5 inline mr-1" />
                Habitat scan non disponibile: avvia il servizio scalper
                (avvia_scalper_service.bat) — la classifica appare qui da sola.
            </div>
        );
    }

    const good = rows.filter(r => r.verdict.startsWith('GO'));
    const rest = rows.filter(r => !r.verdict.startsWith('GO')).slice(0, 4);

    return (
        <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-bold text-white">
                    <Target className="h-4 w-4 text-emerald-400" />
                    Partite adatte allo scalper
                </div>
                {scannedAt && (
                    <span className="text-[10px] text-white/35">
                        scan {new Date(scannedAt).toLocaleTimeString('it-IT')}
                    </span>
                )}
            </div>
            {good.length === 0 && (
                <div className="text-xs text-white/45">
                    Nessun habitat GO nelle prossime ore — meglio non forzare.
                </div>
            )}
            {good.map(r => (
                <div key={r.market_id}
                     className="flex items-center justify-between rounded-lg bg-emerald-500/10 border border-emerald-400/20 px-2 py-1.5">
                    <div className="min-w-0">
                        <div className="text-sm font-bold text-white truncate">{r.event}</div>
                        <div className="text-[10px] text-white/50">
                            KO {r.ko.slice(11, 16)} · €{r.tv.toLocaleString('it-IT')} scambiati ·
                            best €{r.depth} · spread {r.spread}tk · osc {r.osc}
                        </div>
                    </div>
                    <Badge className="bg-emerald-500/20 text-emerald-300 border-transparent font-black shrink-0">
                        GO {r.score}
                    </Badge>
                </div>
            ))}
            {rest.length > 0 && (
                <div className="text-[10px] text-white/35 leading-relaxed">
                    Scartate: {rest.map(r => `${r.event} (${r.verdict.replace(' ✅', '')})`).join(' · ')}
                </div>
            )}
        </div>
    );
}
