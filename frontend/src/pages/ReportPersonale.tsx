// ============================================================================
// /report-personale — Report Personale: KPI + equity curve + underwater/drawdown
// + breakdown per strategia/lega + heatmap-calendario P&L giornaliero + consigli
// seguiti vs fuori-consiglio + tabella trade con drill-down (scheda + segnali
// snapshot + settle). Tutta la matematica è server-side (RPC get_personal_report
// / get_personal_trades, certificate oracle==RPC). Qui solo rendering + filtri.
// Stesso design system della Dashboard/Analytics.
// ============================================================================
import { Fragment, useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import {
    LineChart, Line, Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, ReferenceLine,
} from 'recharts';
import {
    ChevronLeft, Wallet, Bookmark, AlertTriangle, Filter, RotateCcw,
    ChevronDown, ChevronUp, TrendingUp, TrendingDown, Loader2, CheckCircle2, Trash2, Plus,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import {
    getPersonalReport, getPersonalTrades, settlePersonalTrade, resetPersonalReport,
    setTradeTimeOperative,
    type ReportData, type PersonalTrade, type ReportFilters, type Metrics,
    type TradeStatus,
} from '@/lib/personalReport';
import { ManualTradeForm } from '@/components/report/ManualTradeForm';

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const eur = (v: number | null | undefined, d = 2) =>
    v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '' : '-'}€${Math.abs(v).toFixed(d)}`;
const num = (v: number | null | undefined, d = 2) =>
    v == null || !Number.isFinite(v) ? '—' : v.toFixed(d);
const pct = (v: number | null | undefined, d = 1) =>
    v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`;
const signColor = (v: number | null | undefined) =>
    v == null ? 'text-white' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-white';

// ---- KPI card ----
function Kpi({ label, value, color, hint }: { label: string; value: string; color?: string; hint?: string }) {
    return (
        <Card className="glass-card border-white/10 p-4" title={hint}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
            <div className={`text-xl md:text-2xl font-black font-display tabular-nums ${color ?? 'text-white'}`}>{value}</div>
        </Card>
    );
}

// ---- tooltip equity/dd ----
function ChartTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;
    const p = payload[0]?.payload;
    if (!p) return null;
    return (
        <div className="glass-card border border-white/10 rounded-lg px-3 py-2 text-xs">
            <div className="font-bold text-white mb-1">{label}</div>
            <div className="space-y-0.5 font-mono">
                <div className={signColor(p.pnl)}>P&L giorno: {eur(p.pnl)}</div>
                <div className="text-white/80">Equity: {eur(p.equity)}</div>
                <div className="text-red-300">Drawdown: {eur(p.drawdown)}</div>
                <div className="text-muted-foreground">{p.n_trades} trade</div>
            </div>
        </div>
    );
}

// ---- calendar heatmap (P&L giornaliero) ----
function CalendarHeatmap({ daily }: { daily: ReportData['daily'] }) {
    const max = useMemo(() => Math.max(1, ...daily.map(d => Math.abs(d.pnl))), [daily]);
    const cellColor = (pnlV: number) => {
        const t = Math.min(1, Math.abs(pnlV) / max);
        if (pnlV > 0) return `hsla(155, 84%, 42%, ${0.15 + t * 0.7})`;
        if (pnlV < 0) return `hsla(0, 80%, 55%, ${0.15 + t * 0.7})`;
        return 'rgba(255,255,255,0.04)';
    };
    if (!daily.length) return <p className="text-xs text-muted-foreground">Nessun giorno operativo.</p>;
    return (
        <div className="flex flex-wrap gap-1.5">
            {daily.map(d => (
                <div key={d.day}
                    className="w-9 h-9 rounded-md flex items-center justify-center border border-white/5"
                    style={{ background: cellColor(d.pnl) }}
                    title={`${d.day} · ${eur(d.pnl)} · ${d.n_trades} trade`}
                >
                    <span className="text-[8px] font-mono text-white/70">
                        {(() => { try { return new Date(d.day).getDate(); } catch { return ''; } })()}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ---- settle dialog ----
function SettleDialog({ open, onOpenChange, trade, onSaved }: {
    open: boolean; onOpenChange: (o: boolean) => void; trade: PersonalTrade; onSaved?: () => void;
}) {
    const [status, setStatus] = useState<TradeStatus>('WON');
    const [resultFt, setResultFt] = useState('');
    const [exitOdds, setExitOdds] = useState('');
    const [timeMin, setTimeMin] = useState('');
    const [saving, setSaving] = useState(false);

    const handleSettle = async () => {
        setSaving(true);
        try {
            await settlePersonalTrade({
                id: trade.id,
                status,
                resultFt: resultFt.trim() || null,
                exitOdds: exitOdds.trim() === '' ? null : Number(exitOdds),
                timeMin: timeMin.trim() === '' ? null : Number(timeMin),
            });
            toast.success('Trade chiuso', { description: `Esito ${status}.` });
            onOpenChange(false);
            onSaved?.();
        } catch (e: any) {
            toast.error('Errore chiusura trade', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-lg text-white">Chiudi trade</DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {trade.home_team} vs {trade.away_team} · {trade.strategia}. Il P&L viene ricalcolato dal server.
                    </DialogDescription>
                </DialogHeader>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label className={LABEL_CLS}>Esito *</Label>
                        <select className={SELECT_CLS} value={status} onChange={e => setStatus(e.target.value as TradeStatus)}>
                            <option value="WON">Vinto</option>
                            <option value="LOST">Perso</option>
                            <option value="VOID">Annullato</option>
                            <option value="PARTIAL">Parziale (cash-out)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={LABEL_CLS}>Risultato FT</Label>
                        <Input value={resultFt} onChange={e => setResultFt(e.target.value)} placeholder="es. 2-1"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={LABEL_CLS}>Quota uscita</Label>
                        <Input type="number" step="0.01" value={exitOdds} onChange={e => setExitOdds(e.target.value)}
                            placeholder="cash-out" className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={LABEL_CLS}>Tempo operativo (min)</Label>
                        <Input type="number" value={timeMin} onChange={e => setTimeMin(e.target.value)}
                            placeholder="es. 45" className="bg-black/60 border-white/10" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">Annulla</Button>
                    <Button onClick={handleSettle} disabled={saving}
                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Chiudi trade
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

const N_COLS = 17; // colonne tabella (per il colSpan del drill-down)
const fmtDay = (s: string | null) => {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' }); }
    catch { return s.slice(0, 10); }
};

// ---- cella Tempo Operativo editabile (salva su DB + ricalcola resa oraria) ----
function TimeOperativeCell({ t, onChanged }: { t: PersonalTrade; onChanged?: () => void }) {
    const [val, setVal] = useState(t.time_operative_min == null ? '' : String(t.time_operative_min));
    const [saving, setSaving] = useState(false);
    useEffect(() => { setVal(t.time_operative_min == null ? '' : String(t.time_operative_min)); }, [t.time_operative_min]);

    const commit = async () => {
        const trimmed = val.trim();
        const next = trimmed === '' ? null : Number(trimmed);
        if (next != null && !Number.isFinite(next)) return;
        if ((t.time_operative_min ?? null) === (next ?? null)) return;
        setSaving(true);
        try {
            await setTradeTimeOperative(t.id, next);
            toast.success('Tempo operativo aggiornato');
            onChanged?.();
        } catch (e: any) {
            toast.error('Errore salvataggio tempo', { description: e?.message ?? 'errore' });
        } finally { setSaving(false); }
    };
    return (
        <input
            type="number" min="0" step="1" value={val} disabled={saving}
            onClick={e => e.stopPropagation()}
            onChange={e => setVal(e.target.value)}
            onBlur={commit}
            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
            placeholder="—"
            className="w-16 bg-black/60 border border-white/10 rounded px-1.5 py-1 text-right text-xs
                       text-white tabular-nums focus:outline-none focus:border-primary/60"
        />
    );
}

// ---- tabella direzioni motori (drill-down) ----
function DirectionsTable({ ctx }: { ctx: PersonalTrade['context'] }) {
    const markets = ctx?.directions?.markets ?? [];
    if (!markets.length) return <p className="text-[11px] text-muted-foreground">Nessuna direzione motori.</p>;
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
                <thead>
                    <tr className="text-[9px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                        <th className="text-left px-2 py-1">Mercato</th>
                        <th className="text-center px-2 py-1">Direzione</th>
                        <th className="text-left px-2 py-1">Motori concordi</th>
                        <th className="text-center px-2 py-1">N</th>
                        <th className="text-center px-2 py-1">Hit</th>
                    </tr>
                </thead>
                <tbody>
                    {markets.map((m, i) => {
                        const hit = ctx?.hits?.[m.market];
                        return (
                            <tr key={i} className="border-b border-white/5">
                                <td className="px-2 py-1 text-white/80">{m.market}</td>
                                <td className="px-2 py-1 text-center font-bold text-primary">{m.direction ?? '—'}</td>
                                <td className="px-2 py-1 text-muted-foreground">{(m.concordi ?? []).join(', ') || '—'}</td>
                                <td className="px-2 py-1 text-center text-muted-foreground">{m.motori_totali ?? '—'}</td>
                                <td className="px-2 py-1 text-center">
                                    {hit == null ? <span className="text-muted-foreground">—</span>
                                        : hit ? <span className="text-emerald-400 font-bold">✓</span>
                                        : <span className="text-red-400 font-bold">✗</span>}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

// ---- riga trade + drill-down ----
function TradeRow({ t, onChanged }: { t: PersonalTrade; onChanged?: () => void }) {
    const [open, setOpen] = useState(false);
    const [settleOpen, setSettleOpen] = useState(false);
    const pr = t.context?.predictions;
    const res = t.context?.result;
    const td = 'px-2.5 py-2.5 whitespace-nowrap';
    return (
        <Fragment>
            <tr className={`border-b border-white/5 cursor-pointer hover:bg-white/[0.04] ${open ? 'bg-white/[0.04]' : ''}`}
                onClick={() => setOpen(v => !v)}>
                <td className={td}>
                    <span className="inline-flex items-center gap-1.5">
                        {open ? <ChevronDown className="w-3 h-3 text-primary" /> : <ChevronUp className="w-3 h-3 opacity-30 rotate-180" />}
                        <span className="text-white tabular-nums">{fmtDay(t.trade_date)}</span>
                    </span>
                </td>
                <td className={`${td} text-muted-foreground tabular-nums text-[11px]`}>{t.betfair_event_id ?? '—'}</td>
                <td className={`${td} text-white/80`}>{t.league_name ?? '—'}</td>
                <td className={`${td} text-muted-foreground tabular-nums text-[11px]`}>{t.league_id ?? '—'}</td>
                <td className={`${td} text-muted-foreground`}>{t.country ?? '—'}</td>
                <td className={`${td} text-muted-foreground tabular-nums`}>{t.season_year ?? '—'}</td>
                <td className={`${td} text-white`}>{t.home_team ?? '—'}</td>
                <td className={`${td} text-white`}>{t.away_team ?? '—'}</td>
                <td className={`${td} text-center tabular-nums text-white/90`}>{t.result_ft ?? '—'}</td>
                <td className={`${td} text-muted-foreground`}>{t.strategia}</td>
                <td className={`${td} text-right tabular-nums text-white/80`}>{num(t.entry_odds)}</td>
                <td className={`${td} text-right tabular-nums text-muted-foreground`}>{eur(t.stake)}</td>
                <td className={`${td} text-right tabular-nums text-muted-foreground`}>{t.coverage != null ? eur(t.coverage) : '—'}</td>
                <td className={`${td} text-right tabular-nums font-bold ${signColor(t.net_pnl)}`}>{eur(t.net_pnl)}</td>
                <td className={`${td} text-right`} onClick={e => e.stopPropagation()}>
                    <TimeOperativeCell t={t} onChanged={onChanged} />
                </td>
                <td className={`${td} text-right tabular-nums ${signColor(t.hourly_yield)}`}>{t.hourly_yield != null ? eur(t.hourly_yield) : '—'}</td>
                <td className={`${td} text-center`}>
                    {(t.status === 'OPEN' || t.status === 'PARTIAL')
                        ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setSettleOpen(true); }}
                            className="h-7 px-2 text-[11px] text-primary hover:bg-primary/10 font-bold">
                            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Chiudi</Button>
                        : <span className="text-[10px] uppercase font-bold text-muted-foreground">{t.status}</span>}
                </td>
            </tr>
            {open && (
                <tr className="bg-black/40">
                    <td colSpan={N_COLS} className="px-4 py-3">
                        {/* Dettaglio operazione (tutti gli altri campi) */}
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 font-bold">Dettaglio operazione</div>
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 text-[11px]">
                            <div><span className="text-muted-foreground">Lato</span><div className={t.side === 'lay' ? 'text-rose-300 uppercase font-bold' : 'text-sky-300 uppercase font-bold'}>{t.side}</div></div>
                            <div><span className="text-muted-foreground">Mercato · Sel.</span><div className="text-white">{t.market ?? '—'} · {t.selection ?? '—'}</div></div>
                            <div><span className="text-muted-foreground">Linea</span><div className="text-white">{t.line ?? '—'}</div></div>
                            <div><span className="text-muted-foreground">Timing</span><div className="text-white">{t.timing}{t.entry_minute != null ? ` · ${t.entry_minute}'` : ''}</div></div>
                            <div><span className="text-muted-foreground">Stato</span><div className="text-white">{t.status}</div></div>
                            <div><span className="text-muted-foreground">ROI</span><div className={signColor(t.roi)}>{pct(t.roi)}</div></div>
                            <div><span className="text-muted-foreground">P&L lordo</span><div className={signColor(t.gross_pnl)}>{eur(t.gross_pnl)}</div></div>
                            <div><span className="text-muted-foreground">Commissione</span><div className="text-white">{t.commission_amount != null ? eur(t.commission_amount) : '—'}</div></div>
                            <div><span className="text-muted-foreground">Responsabilità</span><div className="text-white">{t.liability != null ? eur(t.liability) : '—'}</div></div>
                            <div><span className="text-muted-foreground">Provenienza</span><div className="text-white">{t.entry_source} · {t.pnl_source}</div></div>
                            <div><span className="text-muted-foreground">Betfair market</span><div className="text-white/70 font-mono text-[10px]">{t.betfair_market_id ?? '—'}</div></div>
                            <div><span className="text-muted-foreground">Kickoff</span><div className="text-white">{t.kickoff ? new Date(t.kickoff).toLocaleString('it-IT') : '—'}</div></div>
                            {t.comment && <div className="col-span-2 md:col-span-4 lg:col-span-6"><span className="text-muted-foreground">Nota</span><div className="text-white/80">{t.comment}</div></div>}
                        </div>

                        {/* Pronostici API-Football + Direzioni motori */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                            <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                                <div className="text-[10px] uppercase tracking-widest text-primary mb-2 font-bold">Pronostici (API-Football)</div>
                                {pr ? (
                                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                                        <div className="col-span-2"><span className="text-muted-foreground">Pronostico</span><div className="text-white">{pr.advice ?? '—'}</div></div>
                                        <div><span className="text-muted-foreground">Gol attesi casa</span><div className="text-white">{pr.goals_home_line ?? '—'}</div></div>
                                        <div><span className="text-muted-foreground">Gol attesi ospite</span><div className="text-white">{pr.goals_away_line ?? '—'}</div></div>
                                        <div><span className="text-muted-foreground">Under/Over</span><div className="text-white">{pr.under_over_line ?? '—'}</div></div>
                                        <div><span className="text-muted-foreground">Favorito</span><div className="text-white">{pr.winner_name ?? '—'}</div></div>
                                        <div className="col-span-2"><span className="text-muted-foreground">% 1X2 (H/D/A)</span>
                                            <div className="text-white tabular-nums">{num(pr.percent_home, 0)}% · {num(pr.percent_draw, 0)}% · {num(pr.percent_away, 0)}%</div></div>
                                    </div>
                                ) : <p className="text-[11px] text-muted-foreground">Nessun pronostico congelato.</p>}
                                {res && (
                                    <div className="mt-2 pt-2 border-t border-white/5 text-[11px]">
                                        <span className="text-muted-foreground">Risultato reale</span>{' '}
                                        <span className="text-white font-bold">{res.ft ?? '—'}</span>
                                        {res.status ? <span className="text-muted-foreground"> ({res.status})</span> : null}
                                    </div>
                                )}
                            </div>
                            <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                                <div className="text-[10px] uppercase tracking-widest text-primary mb-2 font-bold">Direzioni motori</div>
                                <DirectionsTable ctx={t.context} />
                            </div>
                        </div>

                        {/* legs (coperture) se presenti */}
                        {t.legs && t.legs.length > 0 && (
                            <div className="mt-3">
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 font-bold">Coperture / Hedge</div>
                                <div className="space-y-1">
                                    {t.legs.map(l => (
                                        <div key={l.id} className="flex items-center gap-3 text-[11px] text-white/80">
                                            <span className="uppercase font-bold text-white/60 w-20">{l.leg_type}</span>
                                            <span>{l.side ?? '—'} · {l.market ?? '—'} {l.selection ?? ''}</span>
                                            <span className="font-mono">q {num(l.odds)}</span>
                                            <span className="font-mono">{eur(l.stake)}</span>
                                            <span className={`font-mono ml-auto font-bold ${signColor(l.net_pnl)}`}>{eur(l.net_pnl)}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {(t.status === 'OPEN' || t.status === 'PARTIAL') && (
                            <div className="mt-3">
                                <Button size="sm" onClick={(e) => { e.stopPropagation(); setSettleOpen(true); }}
                                    className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                                    <CheckCircle2 className="w-4 h-4 mr-2" /> Chiudi trade
                                </Button>
                            </div>
                        )}
                    </td>
                </tr>
            )}
            <SettleDialog open={settleOpen} onOpenChange={setSettleOpen} trade={t} onSaved={onChanged} />
        </Fragment>
    );
}

// ---- breakdown table ----
function BreakdownTable<T extends Record<string, any>>({ title, rows, nameKey, nameLabel }: {
    title: string; rows: T[]; nameKey: keyof T; nameLabel: string;
}) {
    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 font-heading font-bold text-sm">{title}</div>
            {rows.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground text-sm">Nessun dato.</div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                <th className="text-left px-3 py-2 font-medium">{nameLabel}</th>
                                <th className="text-right px-3 py-2 font-medium">N</th>
                                <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Win%</th>
                                <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Stake</th>
                                <th className="text-right px-3 py-2 font-medium">P&L</th>
                                <th className="text-right px-3 py-2 font-medium">ROI</th>
                                <th className="text-right px-3 py-2 font-medium hidden md:table-cell">PF</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, i) => (
                                <tr key={i} className="border-b border-white/5">
                                    <td className="px-3 py-2 text-white truncate max-w-[180px]">{String(r[nameKey] ?? '—')}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{r.n}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden md:table-cell">{pct(r.win_rate, 0)}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden md:table-cell">{eur(r.stake, 0)}</td>
                                    <td className={`px-3 py-2 text-right tabular-nums font-bold ${signColor(r.net_pnl)}`}>{eur(r.net_pnl)}</td>
                                    <td className={`px-3 py-2 text-right tabular-nums ${signColor(r.roi)}`}>{pct(r.roi)}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden md:table-cell">{num(r.profit_factor, 2)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}

// ---- metriche di rischio (griglia) ----
function RiskGrid({ m }: { m: Metrics }) {
    const items: { label: string; value: string; hint?: string }[] = [
        { label: 'Volatilità', value: eur(m.vol), hint: 'Deviazione standard campionaria (n-1) del P&L giornaliero' },
        { label: 'Sharpe', value: num(m.sharpe), hint: 'mean / vol' },
        { label: 'Sortino', value: num(m.sortino), hint: 'mean / downside deviation' },
        { label: 'Calmar', value: num(m.calmar), hint: 'tot / |max drawdown|' },
        { label: 'Recovery factor', value: num(m.recovery_factor) },
        { label: 'Ulcer index', value: num(m.ulcer_index) },
        { label: 'UPI', value: num(m.upi), hint: 'mean / ulcer index' },
        { label: 'Downside dev', value: eur(m.downside_dev) },
        { label: 'CVaR 5%', value: eur(m.cvar_5), hint: 'media del 5% dei giorni peggiori' },
        { label: 'Max DD', value: eur(m.max_drawdown) },
        { label: 'DD max (gg)', value: num(m.max_dd_duration_days, 0) },
        { label: 'Kurtosis', value: num(m.kurtosis) },
        { label: 'Profit factor', value: num(m.profit_factor) },
        { label: 'Mediana giorno', value: eur(m.median) },
        { label: 'Miglior giorno', value: eur(m.max_day) },
        { label: 'Peggior giorno', value: eur(m.min_day) },
        { label: 'Profit/stake', value: pct(m.profit_per_stake) },
        { label: 'Trade/giorno', value: num(m.media_trade_giorno, 1) },
    ];
    return (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
            {items.map(it => (
                <div key={it.label} className="glass-card rounded-lg border border-white/10 px-3 py-2" title={it.hint}>
                    <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{it.label}</div>
                    <div className="text-sm font-bold font-mono tabular-nums text-white">{it.value}</div>
                </div>
            ))}
        </div>
    );
}

// ---- dialog SVUOTA REPORT (distruttivo: trade + leg + watchlist) ----
function PurgeDialog({ open, onOpenChange, onPurged }: {
    open: boolean; onOpenChange: (o: boolean) => void; onPurged?: () => void;
}) {
    const [confirm, setConfirm] = useState('');
    const [saving, setSaving] = useState(false);

    const handlePurge = async () => {
        setSaving(true);
        try {
            const r = await resetPersonalReport();
            toast.success('Report svuotato', {
                description: `Eliminati ${r.trades} trade, ${r.legs} coperture, ${r.watchlist} partite in watchlist.`,
            });
            setConfirm('');
            onOpenChange(false);
            onPurged?.();
        } catch (e: any) {
            toast.error('Errore svuotamento', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-red-500/30 backdrop-blur-2xl max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-lg text-red-400 flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5" /> Svuota Report
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        Elimina <span className="text-white font-semibold">definitivamente</span> tutta la reportistica
                        personale: tutti i <span className="text-white">trade</span>, le coperture/hedge e
                        l'intera <span className="text-white">watchlist</span> (Da valutare, Giocate, Scartate).
                        Non tocca nient'altro. Operazione <span className="text-red-300 font-semibold">non reversibile</span>.
                    </DialogDescription>
                </DialogHeader>
                <div>
                    <Label className={LABEL_CLS}>Scrivi <span className="text-red-300 font-mono">SVUOTA</span> per confermare</Label>
                    <Input value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="SVUOTA"
                        className="bg-black/60 border-white/10" autoFocus />
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">Annulla</Button>
                    <Button onClick={handlePurge} disabled={saving || confirm.trim().toUpperCase() !== 'SVUOTA'}
                        className="bg-destructive text-destructive-foreground font-bold hover:bg-destructive/90 disabled:opacity-40">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                        Svuota tutto
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default function ReportPersonale() {
    const [report, setReport] = useState<ReportData | null>(null);
    const [trades, setTrades] = useState<PersonalTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [filters, setFilters] = useState<ReportFilters>({});
    const [purgeOpen, setPurgeOpen] = useState(false);
    const [manualOpen, setManualOpen] = useState(false);
    const set = (patch: Partial<ReportFilters>) => setFilters(prev => ({ ...prev, ...patch }));
    const reset = () => setFilters({});

    const load = async (f: ReportFilters) => {
        setLoading(true);
        setError(null);
        try {
            // get_personal_report accetta solo stati CHIUSI (WON/LOST/VOID/PARTIAL):
            // se il filtro e' "Aperti", non lo passo al report (altrimenti la RPC
            // solleva "p_status invalido"); resta applicato alla tabella trade.
            const reportFilters = f.status === 'OPEN' ? { ...f, status: null } : f;
            const [r, t] = await Promise.all([
                getPersonalReport(reportFilters),
                getPersonalTrades({ ...f, limit: 200 }),
            ]);
            setReport(r);
            setTrades(t);
        } catch (e: any) {
            setError(e?.message ?? 'errore sconosciuto');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const id = setTimeout(() => load(filters), 250);
        return () => clearTimeout(id);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters]);

    const m = report?.metrics;
    const totColor = m ? signColor(m.tot) : 'text-white';
    const advice = report?.advice;
    // trade ancora aperti (status OPEN): vanno chiusi per entrare nel report.
    const openCount = trades.filter(t => t.status === 'OPEN').length;

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Report Personale | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-primary font-heading font-bold ml-4">
                            <Wallet className="w-4 h-4" /> REPORT PERSONALE
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/watchlist">
                            <Button variant="outline" size="sm" className="border-amber-400/30 text-amber-300 hover:bg-amber-400/10">
                                <Bookmark className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Watchlist</span>
                            </Button>
                        </Link>
                        <Link to="/dashboard">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10 space-y-6">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                            Report <span className="text-primary">Personale</span>
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            La tua operatività reale (pre-match + live). Metriche calcolate lato DB.
                        </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <Button size="sm" onClick={() => setManualOpen(true)}
                            className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                            <Plus className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Inserisci operazione</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setPurgeOpen(true)}
                            className="border-destructive/40 text-destructive hover:bg-destructive/10">
                            <Trash2 className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Svuota Report</span>
                        </Button>
                    </div>
                </div>

                {/* filtri */}
                <Card className="glass-card border-white/10 p-4">
                    <div className="flex items-center gap-2 mb-4">
                        <Filter className="w-4 h-4 text-primary" />
                        <span className="font-heading font-bold text-sm uppercase tracking-wide">Filtri</span>
                        <Button variant="ghost" size="sm" onClick={reset} className="ml-auto text-xs text-muted-foreground hover:text-white">
                            <RotateCcw className="w-3 h-3 mr-1" /> Reset
                        </Button>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div>
                            <label className={LABEL_CLS}>Dal</label>
                            <input type="date" className={SELECT_CLS} value={filters.from ?? ''}
                                onChange={e => set({ from: e.target.value || null })} />
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Al</label>
                            <input type="date" className={SELECT_CLS} value={filters.to ?? ''}
                                onChange={e => set({ to: e.target.value || null })} />
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Strategia</label>
                            <input className={SELECT_CLS} value={filters.strategia ?? ''} placeholder="tutte"
                                onChange={e => set({ strategia: e.target.value || null })} />
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Stato</label>
                            <select className={SELECT_CLS} value={filters.status ?? ''}
                                onChange={e => set({ status: e.target.value || null })}>
                                <option value="">Tutti (chiusi)</option>
                                <option value="WON">Vinti</option>
                                <option value="LOST">Persi</option>
                                <option value="VOID">Annullati</option>
                                <option value="PARTIAL">Parziali</option>
                                <option value="OPEN">Aperti</option>
                            </select>
                        </div>
                    </div>
                </Card>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {loading ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {Array.from({ length: 8 }).map((_, i) => (
                            <div key={i} className="glass-card rounded-xl border border-white/10 h-24 animate-pulse bg-white/[0.02]" />
                        ))}
                    </div>
                ) : (
                  <>
                    {(!m || m.giorni === 0) ? (
                        <Card className="glass-card border-white/10 p-10 text-center">
                            <Wallet className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                            <h3 className="text-lg font-bold font-display text-white mb-1">Nessun trade chiuso nel periodo</h3>
                            <p className="text-sm text-muted-foreground max-w-xl mx-auto">
                                Le metriche P&amp;L si calcolano sui trade <span className="text-white font-semibold">chiusi</span>.
                                Registra il trade dalla Watchlist ("Giocata"), poi <span className="text-white font-semibold">chiudilo
                                con l'esito</span> dalla tabella qui sotto (pulsante "Chiudi trade"): allora il report si popola.
                            </p>
                        </Card>
                    ) : (
                    <>
                        {/* KPI principali */}
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                            <Kpi label="P&L Totale" value={eur(m.tot)} color={totColor} />
                            <Kpi label="Giorni" value={String(m.giorni)} hint="giorni operativi" />
                            <Kpi label="% giorni positivi" value={pct(m.pct_profit / 100, 1)} color="text-emerald-400" />
                            <Kpi label="Media/giorno" value={eur(m.mean)} color={signColor(m.mean)} />
                            <Kpi label="Max Drawdown" value={eur(m.max_drawdown)} color="text-red-400" />
                            <Kpi label="Sharpe" value={num(m.sharpe)} hint="mean / volatilità" />
                        </div>

                        {/* equity curve */}
                        <Card className="glass-card border-white/10 p-4">
                            <div className="flex items-center gap-2 mb-3">
                                <TrendingUp className="w-4 h-4 text-primary" />
                                <span className="font-heading font-bold text-sm uppercase tracking-wide">Equity Curve</span>
                            </div>
                            <ResponsiveContainer width="100%" height={260}>
                                <LineChart data={report!.daily} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                    <XAxis dataKey="day" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} />
                                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} width={48} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                                    <Line type="monotone" dataKey="equity" stroke="hsl(155 84% 42%)" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </Card>

                        {/* underwater / drawdown */}
                        <Card className="glass-card border-white/10 p-4">
                            <div className="flex items-center gap-2 mb-3">
                                <TrendingDown className="w-4 h-4 text-red-400" />
                                <span className="font-heading font-bold text-sm uppercase tracking-wide">Underwater (Drawdown)</span>
                            </div>
                            <ResponsiveContainer width="100%" height={180}>
                                <AreaChart data={report!.daily} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor="hsl(0 80% 55%)" stopOpacity={0.05} />
                                            <stop offset="100%" stopColor="hsl(0 80% 55%)" stopOpacity={0.5} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                    <XAxis dataKey="day" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} />
                                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} width={48} />
                                    <Tooltip content={<ChartTooltip />} />
                                    <Area type="monotone" dataKey="drawdown" stroke="hsl(0 80% 55%)" strokeWidth={1.5} fill="url(#ddGrad)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </Card>

                        {/* metriche di rischio */}
                        <Card className="glass-card border-white/10 p-4">
                            <span className="font-heading font-bold text-sm uppercase tracking-wide block mb-3">Metriche di rischio</span>
                            <RiskGrid m={m} />
                        </Card>

                        {/* consigli seguiti vs fuori-consiglio + heatmap */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <Card className="glass-card border-white/10 p-4">
                                <span className="font-heading font-bold text-sm uppercase tracking-wide block mb-3">Consigli seguiti vs fuori-consiglio</span>
                                {advice ? (
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/5 px-4 py-3">
                                            <div className="text-[10px] uppercase text-emerald-300 font-bold">Consiglio seguito</div>
                                            <div className="text-2xl font-black font-display text-white">{advice.n_followed}</div>
                                            <div className={`text-sm font-mono ${signColor(advice.roi_followed)}`}>ROI {pct(advice.roi_followed)}</div>
                                        </div>
                                        <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 px-4 py-3">
                                            <div className="text-[10px] uppercase text-amber-300 font-bold">Fuori-consiglio</div>
                                            <div className="text-2xl font-black font-display text-white">{advice.n_off_advice}</div>
                                            <div className={`text-sm font-mono ${signColor(advice.roi_off_advice)}`}>ROI {pct(advice.roi_off_advice)}</div>
                                        </div>
                                    </div>
                                ) : <p className="text-xs text-muted-foreground">Nessun dato.</p>}
                                {report?.discarded && report.discarded.n > 0 && (
                                    <p className="text-[11px] text-muted-foreground mt-3">
                                        Partite scartate nel periodo: <span className="text-white font-bold">{report.discarded.n}</span>.
                                    </p>
                                )}
                            </Card>

                            <Card className="glass-card border-white/10 p-4">
                                <span className="font-heading font-bold text-sm uppercase tracking-wide block mb-3">Calendario P&L giornaliero</span>
                                <CalendarHeatmap daily={report!.daily} />
                                <div className="flex items-center gap-3 mt-3 text-[10px] text-muted-foreground">
                                    <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-400/70" /> profitto</span>
                                    <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-400/70" /> perdita</span>
                                </div>
                            </Card>
                        </div>

                        {/* breakdown */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <BreakdownTable title="Per strategia" rows={report!.by_strategia} nameKey="strategia" nameLabel="Strategia" />
                            <BreakdownTable title="Per lega" rows={report!.by_league} nameKey="league_name" nameLabel="Lega" />
                        </div>

                    </>
                    )}

                        {/* tabella trade con drill-down — SEMPRE visibile (anche con soli trade aperti),
                            cosi' puoi vedere lo storico e CHIUDERE i trade aperti per popolare il report. */}
                        <Card className="glass-card border-white/10 overflow-hidden">
                            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                                <span className="font-heading font-bold text-sm">
                                    Trade ({trades.length})
                                    {openCount > 0 && (
                                        <span className="text-amber-300 font-normal"> · {openCount} da chiudere</span>
                                    )}
                                </span>
                                <span className="text-[10px] text-muted-foreground uppercase tracking-wider hidden md:inline">clic = dettaglio + “Chiudi trade”</span>
                            </div>
                            {trades.length === 0 ? (
                                <div className="p-6 text-center text-muted-foreground text-sm">Nessun trade per questi filtri.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm min-w-[1400px]">
                                        <thead>
                                            <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5 whitespace-nowrap">
                                                <th className="text-left px-2.5 py-2 font-medium">Data</th>
                                                <th className="text-left px-2.5 py-2 font-medium">ID Evento</th>
                                                <th className="text-left px-2.5 py-2 font-medium">League</th>
                                                <th className="text-left px-2.5 py-2 font-medium">ID League</th>
                                                <th className="text-left px-2.5 py-2 font-medium">Nazione</th>
                                                <th className="text-left px-2.5 py-2 font-medium">Stagione</th>
                                                <th className="text-left px-2.5 py-2 font-medium">Home</th>
                                                <th className="text-left px-2.5 py-2 font-medium">Away</th>
                                                <th className="text-center px-2.5 py-2 font-medium">Risultato</th>
                                                <th className="text-left px-2.5 py-2 font-medium">Strategia</th>
                                                <th className="text-right px-2.5 py-2 font-medium">Quota Ingr.</th>
                                                <th className="text-right px-2.5 py-2 font-medium">Stake</th>
                                                <th className="text-right px-2.5 py-2 font-medium">Copertura</th>
                                                <th className="text-right px-2.5 py-2 font-medium">Gain Netto</th>
                                                <th className="text-right px-2.5 py-2 font-medium">T. Op. (min)</th>
                                                <th className="text-right px-2.5 py-2 font-medium">€/h</th>
                                                <th className="text-center px-2.5 py-2 font-medium">Stato</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {trades.map(t => <TradeRow key={t.id} t={t} onChanged={() => load(filters)} />)}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    </>
                )}
            </main>

            <ManualTradeForm open={manualOpen} onOpenChange={setManualOpen} onSaved={() => load(filters)} />

            <PurgeDialog open={purgeOpen} onOpenChange={setPurgeOpen} onPurged={() => load(filters)} />

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
