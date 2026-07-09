// ============================================================================
// /trade-journal — E37: review post-sessione del Trade Journal automatico.
// Fonti: get_live_journal (specchio DB, sola lettura) + get_live_settled
// (join P&L per mercato via journalStats.settledByMarket — matematica pura
// testata). Tag/nota editabili inline via set_live_journal_note, con feedback
// ESPLICITO ok/errore. In fondo: statistiche per pattern (groupJournal).
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { Card } from '@/components/ui/card';
import { ArrowLeft, BookOpen, Loader2 } from 'lucide-react';
import {
    fetchLiveJournal, fetchLiveSettled, setLiveJournalNote,
    type LiveJournalRow, type LiveSettledRow,
} from '@/lib/liveOrders';
import { groupJournal, settledByMarket, type PatternStat } from '@/lib/journalStats';

// ---------------------------------------------------------------- helper puri UI
function fmtEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function timeLabel(iso: string): string {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
// Mezzanotte locale di OGGI (per il filtro solo-oggi).
function todayStartMs(): number {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
}

function ModeBadge({ mode }: { mode: string }) {
    return mode === 'live' ? (
        <span className="px-1.5 py-0.5 rounded bg-red-600/80 text-white text-[10px] font-black">LIVE</span>
    ) : (
        <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 text-[10px] font-black">PAPER</span>
    );
}
function OriginBadge({ origin }: { origin: LiveJournalRow['origin'] }) {
    return origin === 'risk_rule' ? (
        <span className="px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 text-[10px] font-bold">regola</span>
    ) : (
        <span className="px-1.5 py-0.5 rounded bg-white/10 text-white/70 text-[10px] font-bold">manuale</span>
    );
}
function SideBadge({ side }: { side: LiveJournalRow['side'] }) {
    if (!side) return <span className="text-white/40">—</span>;
    return side === 'back' ? (
        <span className="px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 text-[10px] font-black">BACK</span>
    ) : (
        <span className="px-1.5 py-0.5 rounded bg-pink-500/20 text-pink-300 text-[10px] font-black">LAY</span>
    );
}

// Card statistiche per una dimensione (groupJournal → top pattern).
function PatternCard({ title, stats }: { title: string; stats: PatternStat[] }) {
    return (
        <Card className="glass-card border-white/10 p-3 min-w-[200px] flex-1">
            <div className="text-[11px] font-bold text-white mb-1.5">{title}</div>
            {stats.length === 0 ? (
                <div className="text-[11px] text-muted-foreground">Nessuna riga.</div>
            ) : (
                <table className="w-full text-[11px]">
                    <tbody>
                        {stats.slice(0, 6).map(s => (
                            <tr key={s.key} className="border-t border-white/5 first:border-t-0">
                                <td className="py-0.5 pr-2 text-white/85 truncate max-w-[120px]" title={s.key}>{s.key}</td>
                                <td className="py-0.5 pr-2 text-right text-slate-400 tabular-nums">{s.count}×</td>
                                <td className="py-0.5 text-right text-white/70 tabular-nums">€{s.stakeTotal.toFixed(2)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    );
}

type ModeFilter = 'all' | 'paper' | 'live';
type OriginFilter = 'all' | 'manual' | 'risk_rule';

export default function TradeJournal() {
    const [rows, setRows] = useState<LiveJournalRow[] | null>(null);
    const [settled, setSettled] = useState<LiveSettledRow[]>([]);
    // filtri
    const [modeF, setModeF] = useState<ModeFilter>('all');
    const [actionF, setActionF] = useState<string>('all');
    const [originF, setOriginF] = useState<OriginFilter>('all');
    const [tagF, setTagF] = useState('');
    const [todayOnly, setTodayOnly] = useState(true);
    // editing tag/nota per riga (id → bozza) + feedback esplicito per riga
    const [edits, setEdits] = useState<Record<number, { tag: string; note: string }>>({});
    const [savingId, setSavingId] = useState<number | null>(null);
    const [feedback, setFeedback] = useState<Record<number, { ok: boolean; msg: string }>>({});

    useEffect(() => {
        let alive = true;
        fetchLiveJournal({ limit: 500 })
            .then(r => { if (alive) setRows(r); })
            .catch(e => { console.warn('[TradeJournal] journal:', e); if (alive) setRows(prev => prev ?? []); });
        fetchLiveSettled()
            .then(r => { if (alive) setSettled(r); })
            .catch(e => console.warn('[TradeJournal] settled:', e));
        return () => { alive = false; };
    }, []);

    const settledMap = useMemo(
        () => settledByMarket(settled.map(s => ({ market_id: s.market_id, profit: s.profit }))),
        [settled],
    );

    const actions = useMemo(
        () => [...new Set((rows ?? []).map(r => r.action))].sort(),
        [rows],
    );

    const filtered = useMemo(() => {
        const start = todayStartMs();
        return (rows ?? []).filter(r =>
            (modeF === 'all' || r.mode === modeF) &&
            (actionF === 'all' || r.action === actionF) &&
            (originF === 'all' || r.origin === originF) &&
            (tagF.trim() === '' || (r.tag ?? '').toLowerCase().includes(tagF.trim().toLowerCase())) &&
            (!todayOnly || new Date(r.ts).getTime() >= start),
        );
    }, [rows, modeF, actionF, originF, tagF, todayOnly]);

    const getEdit = (r: LiveJournalRow) => edits[r.id] ?? { tag: r.tag ?? '', note: r.note ?? '' };

    const save = async (r: LiveJournalRow) => {
        const e = getEdit(r);
        setSavingId(r.id);
        try {
            const updated = await setLiveJournalNote(
                r.id,
                e.tag.trim() === '' ? null : e.tag.trim(),
                e.note.trim() === '' ? null : e.note.trim(),
            );
            setFeedback(p => ({ ...p, [r.id]: { ok: true, msg: 'Salvato ✓' } }));
            if (updated) setRows(prev => prev?.map(x => (x.id === r.id ? updated : x)) ?? prev);
        } catch (err) {
            setFeedback(p => ({
                ...p,
                [r.id]: { ok: false, msg: `Errore: ${err instanceof Error ? err.message : String(err)}` },
            }));
        } finally {
            setSavingId(null);
        }
    };

    // Segnale compatto: direction+edge se presenti nel jsonb (dettagli nel title).
    const signalLabel = (s: Record<string, unknown> | null): string | null => {
        if (!s) return null;
        const dir = typeof s.direction === 'string' ? s.direction : null;
        const edge = typeof s.edge === 'number' ? `${(s.edge * 100).toFixed(1)}%` : null;
        if (!dir && !edge) return 'seg.';
        return [dir, edge].filter(Boolean).join(' ');
    };

    return (
        <div className="min-h-screen bg-background text-foreground">
            <Helmet><title>Trade Journal | Alpha Score</title></Helmet>

            {/* top bar + filtri */}
            <div className="sticky top-0 z-40 px-3 py-2 border-b border-white/10 bg-black/80 backdrop-blur flex items-center gap-3 flex-wrap">
                <Link to="/segui-live" className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-white">
                    <ArrowLeft className="w-3.5 h-3.5" /> Terminal
                </Link>
                <span className="inline-flex items-center gap-1.5 font-heading font-bold text-sm text-white">
                    <BookOpen className="w-4 h-4 text-amber-400" /> Trade Journal
                </span>
                <div className="flex-1" />
                <select value={modeF} onChange={e => setModeF(e.target.value as ModeFilter)}
                    className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white" title="Filtro mode">
                    <option value="all">mode: tutte</option>
                    <option value="paper">paper</option>
                    <option value="live">live</option>
                </select>
                <select value={actionF} onChange={e => setActionF(e.target.value)}
                    className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white" title="Filtro azione">
                    <option value="all">azione: tutte</option>
                    {actions.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <select value={originF} onChange={e => setOriginF(e.target.value as OriginFilter)}
                    className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white" title="Filtro origine">
                    <option value="all">origine: tutte</option>
                    <option value="manual">manuale</option>
                    <option value="risk_rule">regola</option>
                </select>
                <input
                    value={tagF}
                    onChange={e => setTagF(e.target.value)}
                    placeholder="filtro tag…"
                    className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white w-28"
                />
                <label className="text-[11px] text-slate-400 inline-flex items-center gap-1.5 select-none">
                    <input type="checkbox" checked={todayOnly} onChange={e => setTodayOnly(e.target.checked)} />
                    solo oggi
                </label>
            </div>

            <div className="p-3 space-y-4 max-w-[1500px] mx-auto">
                {/* ---------------------------------------------------- tabella */}
                <Card className="glass-card border-white/10 p-3 overflow-x-auto">
                    {rows == null ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
                            <Loader2 className="w-4 h-4 animate-spin" /> Carico il journal…
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="text-sm text-muted-foreground py-4 text-center">Nessuna riga journal con i filtri correnti.</div>
                    ) : (
                        <table className="w-full text-[11px]">
                            <thead>
                                <tr className="text-slate-400 text-left">
                                    <th className="py-1 pr-2 font-normal">Ora</th>
                                    <th className="py-1 pr-2 font-normal">Mode</th>
                                    <th className="py-1 pr-2 font-normal">Azione</th>
                                    <th className="py-1 pr-2 font-normal">Origine</th>
                                    <th className="py-1 pr-2 font-normal">Evento / Mercato</th>
                                    <th className="py-1 pr-2 font-normal">Sel.</th>
                                    <th className="py-1 pr-2 font-normal">Side</th>
                                    <th className="py-1 pr-2 font-normal text-right">Prezzo@Size</th>
                                    <th className="py-1 pr-2 font-normal">Min/Score</th>
                                    <th className="py-1 pr-2 font-normal text-right">LTP · best</th>
                                    <th className="py-1 pr-2 font-normal">Segnale</th>
                                    <th className="py-1 pr-2 font-normal text-right">P&amp;L mercato</th>
                                    <th className="py-1 pr-2 font-normal">Tag</th>
                                    <th className="py-1 pr-2 font-normal">Nota</th>
                                    <th className="py-1 font-normal" />
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map(r => {
                                    const e = getEdit(r);
                                    const pnl = r.market_id ? settledMap.get(r.market_id) : undefined;
                                    const fb = feedback[r.id];
                                    const sig = signalLabel(r.signals);
                                    return (
                                        <tr key={r.id} className="border-t border-white/5 align-top">
                                            <td className="py-1 pr-2 text-slate-400 tabular-nums whitespace-nowrap">{timeLabel(r.ts)}</td>
                                            <td className="py-1 pr-2"><ModeBadge mode={r.mode} /></td>
                                            <td className="py-1 pr-2 text-white/85">{r.action}</td>
                                            <td className="py-1 pr-2"><OriginBadge origin={r.origin} /></td>
                                            <td className="py-1 pr-2">
                                                <div className="text-white/85" title={r.market_id ?? undefined}>{r.market_name ?? r.market_id ?? '—'}</div>
                                                <div className="text-[10px] text-slate-500 font-mono">{r.event_id ?? ''}</div>
                                            </td>
                                            <td className="py-1 pr-2 text-slate-400 tabular-nums">{r.selection_id ?? '—'}</td>
                                            <td className="py-1 pr-2"><SideBadge side={r.side} /></td>
                                            <td className="py-1 pr-2 text-right tabular-nums text-white/85 whitespace-nowrap">
                                                {r.price != null ? r.price.toFixed(2) : '—'}{r.size != null ? ` @ €${r.size.toFixed(2)}` : ''}
                                            </td>
                                            <td className="py-1 pr-2 text-white/70 whitespace-nowrap">
                                                {r.minute != null
                                                    ? `${r.minute}'${r.score_home != null && r.score_away != null ? ` ${r.score_home}–${r.score_away}` : ''}`
                                                    : r.inplay ? 'in-play' : 'pre-match'}
                                            </td>
                                            <td
                                                className="py-1 pr-2 text-right tabular-nums text-slate-400 whitespace-nowrap"
                                                title={r.book ? JSON.stringify(r.book) : 'book non registrato'}
                                            >
                                                {r.ltp != null ? r.ltp.toFixed(2) : '—'}
                                                {' · '}
                                                {r.best_back != null ? r.best_back.toFixed(2) : '—'}/{r.best_lay != null ? r.best_lay.toFixed(2) : '—'}
                                            </td>
                                            <td className="py-1 pr-2 text-white/70" title={r.signals ? JSON.stringify(r.signals) : undefined}>
                                                {sig ?? '—'}
                                            </td>
                                            <td className="py-1 pr-2 text-right tabular-nums font-semibold">
                                                {pnl != null ? (
                                                    <span className={pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtEur(pnl)}</span>
                                                ) : (
                                                    <span className="text-white/40" title="mercato non ancora regolato">—</span>
                                                )}
                                            </td>
                                            <td className="py-1 pr-2">
                                                <input
                                                    value={e.tag}
                                                    onChange={ev => setEdits(p => ({ ...p, [r.id]: { ...e, tag: ev.target.value } }))}
                                                    placeholder="tag"
                                                    className="bg-slate-900 border border-white/10 rounded px-1.5 py-0.5 text-[11px] text-white w-24"
                                                />
                                            </td>
                                            <td className="py-1 pr-2">
                                                <input
                                                    value={e.note}
                                                    onChange={ev => setEdits(p => ({ ...p, [r.id]: { ...e, note: ev.target.value } }))}
                                                    placeholder="nota"
                                                    className="bg-slate-900 border border-white/10 rounded px-1.5 py-0.5 text-[11px] text-white w-40"
                                                />
                                            </td>
                                            <td className="py-1 whitespace-nowrap">
                                                <button
                                                    type="button"
                                                    onClick={() => save(r)}
                                                    disabled={savingId === r.id}
                                                    className="px-2 py-0.5 rounded-md border border-amber-400/40 bg-amber-400/10 text-[11px] font-bold text-amber-200 hover:bg-amber-400/25 disabled:opacity-40"
                                                >
                                                    {savingId === r.id ? '…' : 'Salva'}
                                                </button>
                                                {fb && (
                                                    <div className={`text-[10px] mt-0.5 ${fb.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                                                        {fb.msg}
                                                    </div>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </Card>

                {/* ------------------------------------------ statistiche pattern */}
                <section className="space-y-2">
                    <h2 className="text-sm font-heading font-bold text-white">Statistiche per pattern</h2>
                    <div className="flex gap-3 flex-wrap items-start">
                        <PatternCard title="Per tag" stats={groupJournal(filtered, 'tag')} />
                        <PatternCard title="Per side" stats={groupJournal(filtered, 'side')} />
                        <PatternCard title="Per origine" stats={groupJournal(filtered, 'origin')} />
                        <PatternCard title="Per minuto" stats={groupJournal(filtered, 'minuteBucket')} />
                    </div>
                </section>
            </div>
        </div>
    );
}
