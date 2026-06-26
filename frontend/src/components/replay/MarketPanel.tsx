// ============================================================================
// MarketPanel — pannello di UN mercato del replay (data-driven: funziona con 2,
// 3 o N selezioni). Tabella: Selezione | Win% | Back | Lay | Position.
// Back/Lay cliccabili → piazzano una bet allo stake del pannello. Toolbar con
// dropdown Stake, importo stake e pulsante "Cash out".
// ============================================================================
import { Card } from '@/components/ui/card';
import type { Market } from '@/lib/live';
import {
    bestBack, bestLay, winPercent, positionIfWins, marketCashOut, formatGbp,
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
}

export function MarketPanel({ market, ladder, stake, onStakeChange, bets, onPlaceBet, onCashOut }: MarketPanelProps) {
    const selectionIds = market.selections.map(s => s.selection_id);
    const cashOut = marketCashOut(bets, ladder, selectionIds);

    const fmtStake = (n: number) => `£${n.toLocaleString('it', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            {/* header + toolbar */}
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between gap-2 flex-wrap">
                <span className="font-heading font-bold text-sm">{market.market_name || market.market_type}</span>
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
                        className="px-2.5 py-1 rounded-md bg-secondary text-black text-xs font-bold hover:bg-secondary/90 disabled:opacity-40 disabled:cursor-not-allowed"
                        title="Chiude le posizioni di questo mercato alle quote correnti"
                    >
                        Cash out: {formatGbp(cashOut)}
                    </button>
                </div>
            </div>

            {/* tabella selezioni */}
            <div className="overflow-x-auto">
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
                            return (
                                <tr key={s.selection_id} className="border-b border-white/5">
                                    <td className="px-3 py-2 text-white truncate max-w-[160px]">{s.name}</td>
                                    <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">{wp != null ? `${wp}%` : '—'}</td>
                                    <td className="px-2 py-1.5">
                                        <button
                                            disabled={back == null}
                                            onClick={() => back != null && onPlaceBet(s.selection_id, s.name, 'back', back)}
                                            className="w-full rounded-md px-2 py-1.5 text-center text-xs font-bold tabular-nums bg-blue-500/15 text-blue-200 hover:bg-blue-500/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                        >
                                            {back != null ? back.toFixed(2) : '—'}
                                        </button>
                                    </td>
                                    <td className="px-2 py-1.5">
                                        <button
                                            disabled={lay == null}
                                            onClick={() => lay != null && onPlaceBet(s.selection_id, s.name, 'lay', lay)}
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
