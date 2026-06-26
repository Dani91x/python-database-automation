// ============================================================================
// MarketPanel — pannello di UN mercato del replay (data-driven: funziona con 2,
// 3 o N selezioni). Tabella: Selezione | Win% | Back | Lay | Position.
// Back/Lay cliccabili → piazzano una bet allo stake del pannello. Toolbar con
// dropdown Stake, importo stake e pulsante "Cash out".
// ============================================================================
import { Card } from '@/components/ui/card';
import type { Market } from '@/lib/live';
import {
    bestBack, bestLay, winPercent, positionIfWins, formatGbp,
    type LadderMap, type SimBet, type BetSide,
} from '@/lib/replay-pnl';

const STAKE_OPTIONS = [10, 25, 50, 100, 250, 500, 1000];

export interface MarketPanelProps {
    market: Market;
    ladder: LadderMap | undefined;     // ladder del frame corrente per questo mercato
    stake: number;
    onStakeChange: (n: number) => void;
    bets: SimBet[];                    // bet già piazzate su questo mercato
    onPlaceBet: (selectionId: number, selectionName: string, side: BetSide, price: number) => void;
    onCashOut: () => void;
    marketValue: number;              // P&L del mercato: definitivo se settled, altrimenti cash-out
    settled: boolean;                 // true = esito DECISO (P&L definitivo)
    winnerId: number | null;          // selezione vincente (se settled)
    status?: string;                  // stato del frame corrente per QUESTO mercato (OPEN/SUSPENDED/CLOSED)
}

export function MarketPanel({ market, ladder, stake, onStakeChange, bets, onPlaceBet, onCashOut, marketValue, settled, winnerId, status }: MarketPanelProps) {
    const fmtStake = (n: number) => `£${n.toLocaleString('it', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const isSuspended = status === 'SUSPENDED';
    const isClosed = status === 'CLOSED';
    const noBet = isSuspended || isClosed; // niente nuove giocate quando sospeso/chiuso

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            {/* header + toolbar */}
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between gap-2 flex-wrap">
                <span className="font-heading font-bold text-sm flex items-center gap-2">
                    {market.market_name || market.market_type}
                    {isSuspended && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider bg-red-500/20 text-red-300 border border-red-500/40">Sospeso</span>
                    )}
                    {isClosed && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider bg-white/10 text-muted-foreground border border-white/20">Chiuso</span>
                    )}
                </span>
                <div className="flex items-center gap-2">
                    <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Stake</label>
                    <select
                        value={STAKE_OPTIONS.includes(stake) ? stake : ''}
                        onChange={e => e.target.value && onStakeChange(Number(e.target.value))}
                        className="bg-black/60 border border-white/10 rounded-md px-2 py-1 text-xs text-white focus:outline-none focus:border-primary/60"
                    >
                        {!STAKE_OPTIONS.includes(stake) && <option value="">{fmtStake(stake)}</option>}
                        {STAKE_OPTIONS.map(o => <option key={o} value={o}>{fmtStake(o)}</option>)}
                    </select>
                    <input
                        type="number" min={0} step={1} value={stake}
                        onChange={e => onStakeChange(Math.max(0, Number(e.target.value)))}
                        className="w-20 bg-black/60 border border-white/10 rounded-md px-2 py-1 text-xs text-white tabular-nums focus:outline-none focus:border-primary/60"
                    />
                    <button
                        onClick={onCashOut}
                        disabled={bets.length === 0}
                        className={`px-2.5 py-1 rounded-md text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed ${
                            settled
                                ? (marketValue >= 0 ? 'bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/30' : 'bg-red-500/20 text-red-200 hover:bg-red-500/30')
                                : 'bg-secondary text-black hover:bg-secondary/90'
                        }`}
                        title={settled ? 'Esito deciso: P&L definitivo (clic per incassare)' : 'Chiude le posizioni di questo mercato alle quote correnti'}
                    >
                        {settled ? `Esito: ${formatGbp(marketValue)}` : `Cash out: ${formatGbp(marketValue)}`}
                    </button>
                </div>
            </div>

            {/* tabella selezioni */}
            <div className={`overflow-x-auto ${noBet ? 'opacity-50' : ''}`}>
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                            <th className="text-left px-3 py-2 font-medium">Selezione</th>
                            <th className="text-right px-2 py-2 font-medium">Win %</th>
                            <th className="text-center px-2 py-2 font-medium w-20">Back</th>
                            <th className="text-center px-2 py-2 font-medium w-20">Lay</th>
                            <th className="text-right px-3 py-2 font-medium w-24">Position</th>
                        </tr>
                    </thead>
                    <tbody>
                        {market.selections.map(s => {
                            const back = bestBack(ladder, s.selection_id);
                            const lay = bestLay(ladder, s.selection_id);
                            const wp = winPercent(back);
                            const pos = positionIfWins(bets, s.selection_id);
                            const posCls = pos > 0 ? 'text-emerald-400' : pos < 0 ? 'text-red-400' : 'text-muted-foreground';
                            const isWinner = settled && winnerId === s.selection_id;
                            return (
                                <tr key={s.selection_id} className={`border-b border-white/5 ${isWinner ? 'bg-emerald-500/10' : ''}`}>
                                    <td className="px-3 py-2 text-white truncate max-w-[160px]">
                                        {isWinner && <span className="text-emerald-400 mr-1">✓</span>}{s.name}
                                    </td>
                                    <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">{wp != null ? `${wp}%` : '—'}</td>
                                    <td className="px-2 py-1.5">
                                        <button
                                            disabled={back == null || noBet}
                                            onClick={() => back != null && !noBet && onPlaceBet(s.selection_id, s.name, 'back', back)}
                                            className="w-full rounded-md px-2 py-1.5 text-center text-xs font-bold tabular-nums bg-blue-500/15 text-blue-200 hover:bg-blue-500/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                        >
                                            {back != null ? back.toFixed(2) : '—'}
                                        </button>
                                    </td>
                                    <td className="px-2 py-1.5">
                                        <button
                                            disabled={lay == null || noBet}
                                            onClick={() => lay != null && !noBet && onPlaceBet(s.selection_id, s.name, 'lay', lay)}
                                            className="w-full rounded-md px-2 py-1.5 text-center text-xs font-bold tabular-nums bg-pink-500/15 text-pink-200 hover:bg-pink-500/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                        >
                                            {lay != null ? lay.toFixed(2) : '—'}
                                        </button>
                                    </td>
                                    <td className={`px-3 py-2 text-right tabular-nums font-bold ${posCls}`}>{formatGbp(pos)}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}
