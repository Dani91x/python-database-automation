// ============================================================================
// LiveMarketBoard — griglia dei mercati live letti da live_now.state.markets.
// Ogni mercato = card con le selezioni e i prezzi back (azzurro) / lay (rosa) /
// ltp, secondo la convenzione Betfair. Si aggiorna in realtime (le props
// cambiano quando arriva un update dalla sottoscrizione).
// ============================================================================
import { Card } from '@/components/ui/card';
import type { LiveNowState } from '@/lib/live';

function priceCell(value: number | null, kind: 'back' | 'lay') {
    const tint = kind === 'back'
        ? 'bg-blue-500/15 text-blue-200'
        : 'bg-pink-500/15 text-pink-200';
    return (
        <div className={`rounded-md px-2 py-1 text-center text-xs font-bold tabular-nums ${tint}`}>
            {value != null && Number.isFinite(value) ? value.toFixed(2) : '—'}
        </div>
    );
}

export function LiveMarketBoard({ state, updatedAt }: { state: LiveNowState | null; updatedAt?: string | null }) {
    const markets = state?.markets ?? [];
    if (markets.length === 0) {
        return (
            <Card className="glass-card border-white/10 p-6 text-center text-sm text-muted-foreground">
                Nessun mercato live disponibile per questa partita al momento.
            </Card>
        );
    }
    return (
        <div className="space-y-4">
            {updatedAt && (
                <div className="text-[10px] text-muted-foreground text-right">
                    Aggiornato: {new Date(updatedAt).toLocaleTimeString('it')}
                </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {markets.map(m => (
                    <Card key={m.market_id} className="glass-card border-white/10 overflow-hidden">
                        <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
                            <span className="font-heading font-bold text-sm">{m.market_name || m.market_type}</span>
                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.market_type}</span>
                        </div>
                        <div className="p-3">
                            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 items-center text-[10px] uppercase tracking-wider text-muted-foreground px-1 pb-1">
                                <span>Selezione</span>
                                <span className="w-16 text-center">Back</span>
                                <span className="w-16 text-center">Lay</span>
                                <span className="w-14 text-center">LTP</span>
                            </div>
                            <div className="space-y-1.5">
                                {m.selections.map(s => (
                                    <div key={s.selection_id} className="grid grid-cols-[1fr_auto_auto_auto] gap-2 items-center">
                                        <span className="text-sm text-white truncate">{s.name}</span>
                                        <div className="w-16">{priceCell(s.back, 'back')}</div>
                                        <div className="w-16">{priceCell(s.lay, 'lay')}</div>
                                        <div className="w-14 text-center text-xs tabular-nums text-muted-foreground">
                                            {s.ltp != null && Number.isFinite(s.ltp) ? s.ltp.toFixed(2) : '—'}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </Card>
                ))}
            </div>
        </div>
    );
}
