// ============================================================================
// Pannello ML — previsioni per-partita dell'ensemble (model_predictions_json).
// Stesso guscio/stile di MarketFrequencyPanel, dati per-fixture (snapshot).
// MarketFrequencyPanel.tsx NON viene toccato.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, BrainCircuit, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { ProbBarChart, ProbBar } from './ProbBarChart';
import {
    MLData, fetchML, colorForSelection, pctFmt, numFmt,
    mlTargetLabel, mlClassLabel,
} from '@/lib/fixtureModels';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

const chipCls = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${active
        ? 'bg-primary/20 text-primary border-primary/40'
        : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10 hover:text-white'}`;

const gradeColor = (g?: string) => {
    const k = (g || '').toLowerCase();
    if (k === 'high') return 'text-emerald-400';
    if (k === 'medium' || k === 'mid') return 'text-amber-400';
    if (k === 'low') return 'text-red-400';
    return 'text-white/60';
};

export function MLPanel({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState<MLData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [target, setTarget] = useState<string>('');
    const reqRef = useRef(0);

    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setLoading(true);
        setError(null);
        fetchML(fixtureId)
            .then(d => { if (req === reqRef.current) setData(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setData(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    // target presenti con almeno una classe
    const targets = useMemo(() => {
        const t = data?.targets ?? {};
        return Object.keys(t).filter(k => t[k] && typeof t[k] === 'object' && Object.keys(t[k]).length > 0);
    }, [data]);

    useEffect(() => {
        if (targets.length === 0) return;
        if (!targets.includes(target)) setTarget(targets.includes('target_1x2') ? 'target_1x2' : targets[0]);
    }, [targets, target]);

    // raggruppa i target in categorie leggibili (solo gruppi non vuoti)
    const targetGroups = useMemo(() => {
        const defs: { label: string; test: (k: string) => boolean }[] = [
            { label: 'Esito', test: k => ['target_1x2', 'target_ft_1x2', 'target_ht_1x2', 'target_ht_ft'].includes(k) },
            { label: 'Gol totali', test: k => /^target_over_/.test(k) || k === 'target_btts' },
            { label: 'Squadre', test: k => /^target_(home|away)_over_/.test(k) || /clean_sheet/.test(k) },
            { label: '1°T / Timing', test: k => ['target_ht_over_0_5', 'target_goal_in_2h', 'target_first_goal_before_30'].includes(k) },
            { label: 'Statistiche', test: k => /^target_(total_goals|sot_total|corners_total|cards_total|home_cards|away_cards)$/.test(k) },
        ];
        const used = new Set<string>();
        const groups = defs.map(d => {
            const items = targets.filter(t => d.test(t));
            items.forEach(t => used.add(t));
            return { label: d.label, items };
        }).filter(g => g.items.length > 0);
        const rest = targets.filter(t => !used.has(t));
        if (rest.length) groups.push({ label: 'Altro', items: rest });
        return groups;
    }, [targets]);

    // barre della distribuzione del target selezionato (ordinate desc).
    // Per HT/FT scarta eventuali chiavi malformate (es. '_' nelle vecchie predizioni storiche):
    // non devono mai comparire come "previsione".
    const bars: ProbBar[] = useMemo(() => {
        const obj = data?.targets?.[target];
        if (!obj) return [];
        const validHtFt = /^[HDA]_[HDA]$/;
        return Object.entries(obj)
            .filter(([key]) => target !== 'target_ht_ft' || validHtFt.test(key))
            .map(([key, val]) => ({ label: mlClassLabel(key), value: Number(val) || 0, color: colorForSelection(key) }))
            .sort((a, b) => b.value - a.value);
    }, [data, target]);

    const topBar = bars[0] ?? null; // bars gia ordinate desc

    const agree = data?.ensemble_agreement?.[target] ?? null;
    const cal = data?.calibration_metrics?.[target] ?? null;
    const notReliable = data?.targets_not_reliable?.find(x => x.target === target) ?? null;
    const signal = data?.bet_signals?.find(s => s.market === target) ?? null;
    const rel = data?.reliability ?? null;
    const cov = data?.coverage ?? null;
    const genDate = data?.generated_at ? new Date(data.generated_at) : null;
    const valueBets = (data?.bet_signals ?? []).filter(s => s.gates_passed);

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <BrainCircuit className="w-5 h-5 text-primary" />
                    Modelli ML
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— ensemble</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Modelli ML <span className="text-primary">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Previsioni calibrate dell'ensemble (rf/lgb/xgb/logreg) per questa partita, mercato per mercato. {leagueName}.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-4xl mx-auto space-y-4">
                        {loading && (
                            <div className="flex items-center justify-center py-24"><Loader2 className="w-10 h-10 text-primary animate-spin" /></div>
                        )}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {!loading && !error && (!data || targets.length === 0) && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">ML non disponibile per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Le previsioni dell'ensemble vengono elaborate per le partite del giorno processate dal sistema. Per questa partita non sono ancora presenti.
                                </p>
                            </div>
                        )}

                        {!loading && !error && data && targets.length > 0 && (
                            <>
                                {/* meta bar */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                    <span className="text-sm font-bold text-white">{data.model_name ?? 'ensemble_v2'}</span>
                                    {rel?.grade && <span>affidabilità dati <span className={`font-bold ${gradeColor(rel.grade)}`}>{rel.grade}</span> {rel.score !== undefined && <span className="font-mono">({numFmt(rel.score)})</span>}</span>}
                                    {cov?.features_pct !== undefined && <span>feature <span className="font-mono">{pctFmt(cov.features_pct)}</span></span>}
                                    {(cov?.matches_home !== undefined || cov?.matches_away !== undefined) && <span>partite <span className="font-mono">{cov?.matches_home ?? '—'}</span> / <span className="font-mono">{cov?.matches_away ?? '—'}</span></span>}
                                    {genDate && <span className="text-[11px] text-muted-foreground/70">{genDate.toLocaleString('it-IT')}</span>}
                                </div>

                                {/* selettore target, raggruppato per categoria */}
                                <div className="space-y-2.5">
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Mercato ({targets.length})</div>
                                    {targetGroups.map(g => (
                                        <div key={g.label}>
                                            <div className="text-[9px] uppercase tracking-wider text-white/40 mb-1 font-bold">{g.label}</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {g.items.map(t => (
                                                    <button key={t} onClick={() => setTarget(t)} className={chipCls(t === target)}>{mlTargetLabel(t)}</button>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {/* grafico distribuzione */}
                                <div className="glass-card rounded-xl border border-white/10 p-3 md:p-5">
                                    {topBar && (
                                        <div className="flex items-baseline justify-between gap-2 mb-3 pb-3 border-b border-white/5">
                                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Previsione</span>
                                            <span className="text-right">
                                                <span className="text-base md:text-lg font-black text-white">{topBar.label}</span>
                                                <span className="ml-2 text-xl md:text-2xl font-black font-mono" style={{ color: topBar.color }}>{pctFmt(topBar.value, 0)}</span>
                                            </span>
                                        </div>
                                    )}
                                    <ProbBarChart bars={bars} />
                                    <div className="mt-2 text-[10px] text-muted-foreground/70 text-center">
                                        Probabilità calibrate del modello (non quote).
                                    </div>
                                </div>

                                {/* dettaglio target selezionato */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    {/* accordo ensemble */}
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Accordo ensemble</div>
                                        {agree ? (
                                            <div className="space-y-1.5 text-xs">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-muted-foreground">classe prevista</span>
                                                    <span className="text-white font-bold">{agree.predicted_class ? mlClassLabel(agree.predicted_class) : '—'}</span>
                                                    {agree.agreement_ratio !== undefined && <span className="ml-auto font-mono text-primary font-bold">{pctFmt(agree.agreement_ratio, 0)} accordo</span>}
                                                </div>
                                                {agree.votes && (
                                                    <div className="flex flex-wrap gap-1.5 pt-1">
                                                        {Object.entries(agree.votes).map(([model, vote]) => (
                                                            <span key={model} className="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[11px]">
                                                                <span className="text-muted-foreground uppercase">{model}</span> <span className="text-white font-bold">{mlClassLabel(vote)}</span>
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        ) : <p className="text-xs text-muted-foreground">Nessun dato di accordo.</p>}
                                    </div>

                                    {/* calibrazione + affidabilita */}
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Calibrazione</div>
                                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                                            <span className="text-muted-foreground">Brier <span className="font-mono text-white">{numFmt(cal?.brier, 3)}</span></span>
                                            <span className="text-muted-foreground">ECE <span className="font-mono text-white">{numFmt(cal?.ece, 3)}</span></span>
                                        </div>
                                        {notReliable ? (
                                            <div className="mt-2 flex items-start gap-2 text-[11px] text-red-400">
                                                <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                                                <span>{notReliable.reason}</span>
                                            </div>
                                        ) : (
                                            <div className="mt-2 flex items-center gap-2 text-[11px] text-emerald-400">
                                                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> modello affidabile per questo mercato
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* segnale di valore sul target selezionato */}
                                {signal && (
                                    <div className="glass-card rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-emerald-400 mb-2 font-bold">Segnale di valore — {mlClassLabel(signal.action || '')}</div>
                                        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
                                            <span className="text-muted-foreground">prob <span className="font-mono text-white">{pctFmt(signal.model_prob)}</span></span>
                                            <span className="text-muted-foreground">quota <span className="font-mono text-white">{numFmt(signal.decimal_odds)}</span></span>
                                            <span className="text-muted-foreground">edge <span className="font-mono text-emerald-400 font-bold">{pctFmt(signal.edge)}</span></span>
                                            <span className="text-muted-foreground">EV <span className="font-mono text-emerald-400 font-bold">{numFmt(signal.expected_value)}</span></span>
                                            <span className="text-muted-foreground">Kelly <span className="font-mono text-white">{numFmt(signal.kelly_stake)}</span></span>
                                            {signal.confidence_grade && <span className="text-muted-foreground">grado <span className={`font-bold ${gradeColor(signal.confidence_grade)}`}>{signal.confidence_grade}</span></span>}
                                        </div>
                                    </div>
                                )}

                                {/* riepilogo value bets dell'intera partita */}
                                {valueBets.length > 0 && (
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Tutti i segnali di valore ({valueBets.length})</div>
                                        <div className="space-y-1.5">
                                            {valueBets.map((s, i) => (
                                                <div key={i} className="flex flex-wrap items-center gap-x-3 text-[11px] border-b border-white/5 pb-1 last:border-0">
                                                    <span className="text-white font-bold">{mlTargetLabel(s.market || '')}</span>
                                                    <span className="text-primary font-bold">{mlClassLabel(s.action || '')}</span>
                                                    <span className="text-muted-foreground">@ <span className="font-mono text-white">{numFmt(s.decimal_odds)}</span></span>
                                                    <span className="text-muted-foreground">edge <span className="font-mono text-emerald-400">{pctFmt(s.edge)}</span></span>
                                                    <span className="text-muted-foreground">EV <span className="font-mono text-emerald-400">{numFmt(s.expected_value)}</span></span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
