// ============================================================================
// LadderBacktestPanel — F42: backtest del ladder-trading sul replay caricato.
// UI sottile sopra lib/ladderBacktest (matematica pura testata): parametri →
// run → riepilogo + trades. ONESTÀ dichiarata in testa al pannello: pre-match
// senza delay, in-play col bet-delay reale, fill SOLO dalla liquidità visibile,
// P&L = worst-case, trade non chiusi dichiarati.
// ============================================================================
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { FlaskConical, Loader2 } from 'lucide-react';
import type { BookSnapshot } from '@/lib/matching';
import type { Market } from '@/lib/live';
import {
    runLadderBacktest, type BacktestResult, type LadderBacktestParams,
} from '@/lib/ladderBacktest';

interface Props {
    markets: Market[];
    getSnaps: (marketId: string, selectionId: number) => ReadonlyArray<BookSnapshot>;
    isInplayAt: (marketId: string, tsMs: number) => boolean;
}

const DEFAULTS: LadderBacktestParams = {
    side: 'back', entryOffsetTicks: 1, tpTicks: 2, stopTicks: 3,
    stake: 10, entryTtlSec: 30, maxHoldSec: 120, everySec: 60, phase: 'both',
};

const money = (v: number) => `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;

export function LadderBacktestPanel({ markets, getSnaps, isInplayAt }: Props) {
    const [marketId, setMarketId] = useState<string>(() =>
        (markets.find(m => m.market_type === 'MATCH_ODDS') ?? markets[0])?.market_id ?? '');
    const market = useMemo(() => markets.find(m => m.market_id === marketId) ?? null, [markets, marketId]);
    const [selectionId, setSelectionId] = useState<number | null>(null);
    const effectiveSel = selectionId ?? market?.selections?.[0]?.selection_id ?? null;
    const [p, setP] = useState<LadderBacktestParams>(DEFAULTS);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState<BacktestResult | null>(null);

    const num = (key: keyof LadderBacktestParams, min: number) => (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = Number(e.target.value);
        setP(prev => ({ ...prev, [key]: Number.isFinite(v) ? Math.max(min, v) : prev[key] }));
    };

    const run = () => {
        if (!marketId || effectiveSel == null || running) return;
        setRunning(true);
        try {
            const snaps = getSnaps(marketId, effectiveSel);
            setResult(runLadderBacktest(snaps, p, (ts) => isInplayAt(marketId, ts)));
        } finally {
            setRunning(false);
        }
    };

    const inputCls = 'w-16 px-1.5 py-0.5 rounded-md bg-black/40 border border-white/15 text-white font-mono text-[11px]';
    const labelCls = 'text-[10px] text-muted-foreground flex items-center gap-1';

    return (
        <div className="space-y-3">
            <div className="rounded-xl border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-[11px] text-cyan-100 flex items-start gap-2">
                <FlaskConical className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                    <b>Backtest ONESTO</b>: pre-match senza delay · in-play col bet-delay reale (5s) ·
                    fill solo dalla liquidità VISIBILE del book registrato (code e slippage reali) ·
                    P&amp;L = worst-case dei due esiti · i trade non richiusi sono DICHIARATI. Una singola
                    partita non è un campione: servono molte partite prima di trarre conclusioni.
                </span>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/40 p-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                    <select value={marketId} onChange={e => { setMarketId(e.target.value); setSelectionId(null); setResult(null); }}
                        aria-label="Mercato del backtest"
                        className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]">
                        {markets.map(m => (
                            <option key={m.market_id} value={m.market_id}>{m.market_name || m.market_type || m.market_id}</option>
                        ))}
                    </select>
                    <select value={effectiveSel ?? ''} onChange={e => { setSelectionId(Number(e.target.value)); setResult(null); }}
                        aria-label="Selezione del backtest"
                        className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]">
                        {(market?.selections ?? []).map(s => (
                            <option key={s.selection_id} value={s.selection_id}>{s.name ?? `#${s.selection_id}`}</option>
                        ))}
                    </select>
                    <select value={p.side} onChange={e => setP(prev => ({ ...prev, side: e.target.value as 'back' | 'lay' }))}
                        aria-label="Lato entrata"
                        className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]">
                        <option value="back">Entrata BACK</option>
                        <option value="lay">Entrata LAY</option>
                    </select>
                    <select value={p.phase} onChange={e => setP(prev => ({ ...prev, phase: e.target.value as LadderBacktestParams['phase'] }))}
                        aria-label="Fase"
                        className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]">
                        <option value="both">Pre + in-play</option>
                        <option value="prematch">Solo pre-match</option>
                        <option value="inplay">Solo in-play</option>
                    </select>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                    <label className={labelCls}>offset<input type="number" value={p.entryOffsetTicks} onChange={num('entryOffsetTicks', 0)} className={inputCls} aria-label="Offset entrata (tick)" />t</label>
                    <label className={labelCls}>TP<input type="number" value={p.tpTicks} onChange={num('tpTicks', 1)} className={inputCls} aria-label="Take profit (tick)" />t</label>
                    <label className={labelCls}>stop<input type="number" value={p.stopTicks} onChange={num('stopTicks', 1)} className={inputCls} aria-label="Stop (tick)" />t</label>
                    <label className={labelCls}>stake €<input type="number" value={p.stake} onChange={num('stake', 2)} className={inputCls} aria-label="Stake (euro)" /></label>
                    <label className={labelCls}>TTL<input type="number" value={p.entryTtlSec} onChange={num('entryTtlSec', 5)} className={inputCls} aria-label="TTL entrata (secondi)" />s</label>
                    <label className={labelCls}>hold max<input type="number" value={p.maxHoldSec} onChange={num('maxHoldSec', 10)} className={inputCls} aria-label="Tenuta massima (secondi)" />s</label>
                    <label className={labelCls}>ogni<input type="number" value={p.everySec} onChange={num('everySec', 10)} className={inputCls} aria-label="Cadenza entrate (secondi)" />s</label>
                    <Button size="sm" onClick={run} disabled={running || !marketId || effectiveSel == null}
                        className="h-7 bg-cyan-500 hover:bg-cyan-400 text-black font-black">
                        {running ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5 mr-1.5" />}
                        Esegui backtest
                    </Button>
                </div>
            </div>

            {result && (
                <div className="rounded-xl border border-white/10 bg-black/40 p-3 space-y-2">
                    <div className="flex items-center gap-4 flex-wrap text-[11px] tabular-nums">
                        <span className={`font-display font-black text-xl ${result.totalPnl > 0 ? 'text-emerald-300' : result.totalPnl < 0 ? 'text-rose-300' : 'text-white/70'}`}>
                            {money(result.totalPnl)}
                        </span>
                        <span className="text-white/70">{result.trades.length} trade · <span className="text-emerald-300">{result.wins} win</span> / <span className="text-rose-300">{result.losses} loss</span></span>
                        <span className="text-white/50">{result.attempted} tentativi · {result.unfilled} mai abbinati</span>
                        {result.incomplete > 0 && (
                            <span className="text-amber-300 font-bold"
                                title="Trade che NON sono tornati flat (liquidità mancante all'uscita): il loro P&L è il worst-case.">
                                ⚠ {result.incomplete} non richiusi (worst-case)
                            </span>
                        )}
                    </div>
                    {result.trades.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-[10px] tabular-nums">
                                <thead>
                                    <tr className="text-muted-foreground text-left">
                                        <th className="pr-3 font-bold">entrata</th>
                                        <th className="pr-3 font-bold">size</th>
                                        <th className="pr-3 font-bold">uscita</th>
                                        <th className="pr-3 font-bold">esito</th>
                                        <th className="pr-3 font-bold text-right">P&amp;L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.trades.map((t, i) => (
                                        <tr key={i} className="border-t border-white/5">
                                            <td className="pr-3 font-mono">{t.entryPrice.toFixed(2)} · {new Date(t.entryTs).toLocaleTimeString('it-IT')}</td>
                                            <td className="pr-3 font-mono">€{t.size.toFixed(2)}</td>
                                            <td className="pr-3 font-mono">{t.exitPrice != null ? t.exitPrice.toFixed(2) : '—'}</td>
                                            <td className="pr-3">{t.exit}{t.incomplete ? ' ⚠' : ''}</td>
                                            <td className={`pr-3 font-mono text-right ${t.pnl > 0 ? 'text-emerald-300' : t.pnl < 0 ? 'text-rose-300' : 'text-white/60'}`}>{money(t.pnl)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                    {result.trades.length === 0 && (
                        <p className="text-[11px] text-muted-foreground">Nessun trade eseguito (entrate mai abbinate o fase filtrata).</p>
                    )}
                </div>
            )}
        </div>
    );
}

export default LadderBacktestPanel;
