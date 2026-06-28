// ============================================================================
// TradesPanel — elenco di tutti gli ordini simulati (aperti + chiusi).
// Colonne: Min | Selezione | Tipo (Back/Lay) | Quota (media) | Stake | Return/Liab.
// Lo stake mostra la parte ABBINATA + lo stato di matching (in ritardo / in coda /
// parziale / annullato / lapsed). La X annulla il RESTO non abbinato (la parte già
// abbinata resta, come su Betfair). Le posizioni chiuse (cash-out) restano grigie.
//   Return/Liab = stake_abbinato*(quota-1) (profitto potenziale back / liability lay).
// ============================================================================
import { Card } from '@/components/ui/card';
import { X } from 'lucide-react';
import { formatGbp, type SimBet } from '@/lib/replay-pnl';

export function TradesPanel({ bets, onRemove }: { bets: SimBet[]; onRemove: (id: string) => void }) {
    const openCount = bets.filter(b => !b.closed).length;
    const closedCount = bets.length - openCount;

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/5 font-heading font-bold text-sm flex items-center gap-2">
                Trades
                {bets.length > 0 && (
                    <span className="text-muted-foreground font-normal">
                        ({openCount} aperte{closedCount > 0 ? ` · ${closedCount} chiuse` : ''})
                    </span>
                )}
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
                                const closed = !!b.closed;
                                const matched = b.stake > 1e-9;
                                const remaining = b.remaining ?? 0;
                                const hasRemaining = remaining > 1e-6;
                                const status = b.matchStatus;
                                // etichetta di stato per la parte NON ancora abbinata
                                const stateLabel =
                                    status === 'PENDING' ? 'in ritardo…'
                                        : status === 'CANCELLED' ? 'annullato'
                                            : status === 'LAPSED' ? 'annullato (sospensione)'
                                                : hasRemaining ? `£${remaining.toLocaleString('it', { maximumFractionDigits: 2 })} in coda`
                                                    : null;
                                const canCancel = !closed && (hasRemaining || status === 'PENDING');
                                return (
                                    <tr key={b.id} className={`border-b border-white/5 ${closed ? 'opacity-45' : ''}`}>
                                        <td className="px-3 py-2 tabular-nums text-muted-foreground">{b.minute != null ? `${b.minute}'` : '—'}</td>
                                        <td className="px-3 py-2 text-white truncate max-w-[140px]">
                                            <span className="flex items-center gap-1.5">
                                                <span className="truncate">{b.selectionName}</span>
                                                {closed && (
                                                    <span className="px-1 py-0.5 rounded text-[8px] font-black uppercase tracking-wider bg-white/10 text-muted-foreground border border-white/20 shrink-0">
                                                        Cash out
                                                    </span>
                                                )}
                                            </span>
                                            <span className="block text-[10px] text-muted-foreground truncate">
                                                {b.marketName}
                                                {closed && b.realizedPnl != null && (
                                                    <span className={`ml-1 font-bold ${b.realizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                        · {formatGbp(b.realizedPnl)}
                                                    </span>
                                                )}
                                            </span>
                                        </td>
                                        <td className="px-2 py-2 text-center">
                                            <span className={`uppercase text-[10px] font-bold ${b.side === 'lay' ? 'text-pink-300' : 'text-blue-300'}`}>{b.side}</span>
                                        </td>
                                        <td className="px-2 py-2 text-right tabular-nums text-white/80">{b.odds.toFixed(2)}</td>
                                        <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
                                            {matched ? (
                                                <>
                                                    {formatGbp(b.stake)}
                                                    {stateLabel && (
                                                        <span className="block text-[9px] text-amber-400" title={`Su £${b.requestedStake ?? b.stake} richiesti`}>
                                                            + {stateLabel}
                                                        </span>
                                                    )}
                                                </>
                                            ) : (
                                                <span className="text-amber-400" title="Parte non ancora abbinata">
                                                    {stateLabel ?? 'non abbinato'}
                                                </span>
                                            )}
                                        </td>
                                        <td className={`px-3 py-2 text-right tabular-nums ${b.side === 'lay' ? 'text-red-400' : 'text-emerald-400'}`}>
                                            {matched ? formatGbp(amount) : '—'}
                                        </td>
                                        <td className="px-2 py-2 text-right">
                                            {closed ? (
                                                <span className="text-[9px] uppercase tracking-wider text-muted-foreground font-bold">Chiusa</span>
                                            ) : canCancel ? (
                                                <button
                                                    onClick={() => onRemove(b.id)}
                                                    className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-500/15 text-red-300 hover:bg-red-500/30 transition-colors"
                                                    title={matched ? 'Annulla il resto non abbinato' : 'Annulla ordine'}
                                                >
                                                    <X className="w-3.5 h-3.5" />
                                                </button>
                                            ) : (
                                                <span className="text-[9px] uppercase tracking-wider text-emerald-400/70 font-bold" title="Interamente abbinato">abbinato</span>
                                            )}
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
