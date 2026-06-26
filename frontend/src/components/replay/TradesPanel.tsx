// ============================================================================
// TradesPanel — elenco di tutte le bet simulate piazzate.
// Colonne: Min | Selezione | Tipo (Back/Lay) | Quota | Stake | Return/Liab.
// Ogni riga ha una X rossa per rimuovere la bet.
//   Return/Liab = stake*(quota-1) (potenziale profitto per back, liability per lay).
// ============================================================================
import { Card } from '@/components/ui/card';
import { X } from 'lucide-react';
import { formatGbp, type SimBet } from '@/lib/replay-pnl';

export function TradesPanel({ bets, onRemove }: { bets: SimBet[]; onRemove: (id: string) => void }) {
    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/5 font-heading font-bold text-sm">
                Trades {bets.length > 0 && <span className="text-muted-foreground font-normal">({bets.length})</span>}
            </div>
            {bets.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground text-sm">Nessuna scommessa piazzata.</div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                <th className="text-left px-3 py-2 font-medium">Min</th>
                                <th className="text-left px-3 py-2 font-medium">Selezione</th>
                                <th className="text-center px-2 py-2 font-medium">Tipo</th>
                                <th className="text-right px-2 py-2 font-medium">Quota</th>
                                <th className="text-right px-2 py-2 font-medium">Stake</th>
                                <th className="text-right px-3 py-2 font-medium">Return/Liab</th>
                                <th className="px-2 py-2"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {bets.map(b => {
                                const amount = b.stake * (b.odds - 1);
                                return (
                                    <tr key={b.id} className="border-b border-white/5">
                                        <td className="px-3 py-2 tabular-nums text-muted-foreground">{b.minute != null ? `${b.minute}'` : '—'}</td>
                                        <td className="px-3 py-2 text-white truncate max-w-[140px]">
                                            <span className="block">{b.selectionName}</span>
                                            <span className="block text-[10px] text-muted-foreground truncate">{b.marketName}</span>
                                        </td>
                                        <td className="px-2 py-2 text-center">
                                            <span className={`uppercase text-[10px] font-bold ${b.side === 'lay' ? 'text-pink-300' : 'text-blue-300'}`}>{b.side}</span>
                                        </td>
                                        <td className="px-2 py-2 text-right tabular-nums text-white/80">{b.odds.toFixed(2)}</td>
                                        <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">{formatGbp(b.stake)}</td>
                                        <td className={`px-3 py-2 text-right tabular-nums ${b.side === 'lay' ? 'text-red-400' : 'text-emerald-400'}`}>
                                            {formatGbp(amount)}
                                        </td>
                                        <td className="px-2 py-2 text-right">
                                            <button
                                                onClick={() => onRemove(b.id)}
                                                className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-500/15 text-red-300 hover:bg-red-500/30 transition-colors"
                                                title="Rimuovi"
                                            >
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}
