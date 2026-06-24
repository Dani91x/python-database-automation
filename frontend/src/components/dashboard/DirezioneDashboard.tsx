// ============================================================================
// Cruscotto DIREZIONE — pannello per-partita a fianco di "Modelli ML".
// Unisce i motori e mostra, mercato per mercato, la DIREZIONE migliore + quanto
// e' affidabile (hit-rate storico reale dalla pagella), banda di confidenza,
// lift sul base, concordanza motori, quota + segnale di valore, e il dettaglio
// "cosa dice ogni motore". Tutto calcolato in Postgres (RPC get_direction).
// Stesso guscio/stile degli altri pannelli (Sheet bottom, glass-card).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Compass, AlertTriangle, ChevronDown, CheckCircle2, Info } from 'lucide-react';
import {
    DirezioneData, DirMarket, fetchDirezione, marketLabel, selectionLabel,
    ENGINE_LABELS, strength, enginePick,
} from '@/lib/direzione';
import type { EngineProbs } from '@/lib/direzione';
import { pctFmt, numFmt, colorForSelection } from '@/lib/fixtureModels';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

// colore del semaforo per forza del segnale
const dotColor = (s: string) => (s === 'forte' ? 'bg-emerald-400' : s === 'medio' ? 'bg-amber-400' : 'bg-red-400');
const liftColor = (lift: number) => (lift >= 0.10 ? 'text-emerald-400' : lift > 0 ? 'text-amber-400' : 'text-red-400');
// lift in punti interi, segno esplicito, mai "-0"
const fmtLift = (lift: number) => { const v = Math.round(lift * 100); return v > 0 ? `+${v}` : `${v}`; };

// implied prob della quota; valore = anche l'estremo BASSO della banda batte la quota
const implied = (odds: number | null) => (odds && odds > 1 ? 1 / odds : null);
const hasValue = (m: DirMarket) => {
    const imp = implied(m.odds);
    return imp != null && m.wilson_low > imp;
};

function EngineRow({ market, name, probs, direction }: { market: string; name: string; probs?: EngineProbs | null; direction: string }) {
    const pick = enginePick(probs);
    if (!probs || pick == null) {
        return (
            <div className="flex items-center gap-2 text-xs py-1">
                <span className="w-20 shrink-0 text-muted-foreground uppercase text-[10px] font-bold">{ENGINE_LABELS[name]}</span>
                <span className="text-white/30">non disponibile per questa partita</span>
            </div>
        );
    }
    const agrees = pick === direction;
    const entries = Object.entries(probs).sort((a, b) => (b[1] as number) - (a[1] as number));
    return (
        <div className="flex items-center gap-2 text-xs py-1">
            <span className="w-20 shrink-0 text-muted-foreground uppercase text-[10px] font-bold">{ENGINE_LABELS[name]}</span>
            <div className="flex flex-wrap gap-1.5 items-center">
                {entries.map(([sel, p]) => {
                    const isPick = sel === pick;
                    return (
                        <span key={sel}
                            className={`px-2 py-0.5 rounded-md border text-[11px] ${isPick
                                ? 'bg-white/10 border-white/30 text-white font-bold'
                                : 'bg-white/[0.03] border-white/10 text-white/50'}`}>
                            {selectionLabel(market, sel)} <span className="font-mono">{pctFmt(p as number, 0)}</span>
                        </span>
                    );
                })}
            </div>
            {agrees
                ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto shrink-0" />
                : <span className="ml-auto text-[10px] text-amber-400/80 shrink-0">divergente</span>}
        </div>
    );
}

function MarketCard({ m, expanded, onToggle }: { m: DirMarket; expanded: boolean; onToggle: () => void }) {
    const s = strength(m.lift);
    const imp = implied(m.odds);
    const value = hasValue(m);
    return (
        <div className="glass-card rounded-xl border border-white/10 overflow-hidden">
            <button onClick={onToggle} className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors text-left">
                <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotColor(s)}`} />
                <div className="min-w-0 flex-1">
                    <div className="text-sm font-bold text-white truncate">{marketLabel(m.market)}</div>
                    <div className="text-[11px] text-muted-foreground">
                        direzione <span className="font-bold" style={{ color: colorForSelection(m.direction) }}>{selectionLabel(m.market, m.direction)}</span>
                    </div>
                </div>
                {/* affidabilita + banda */}
                <div className="text-right shrink-0 w-24">
                    <div className="text-lg font-black font-mono text-white leading-none">{pctFmt(m.affidabilita, 0)}</div>
                    <div className="text-[10px] text-muted-foreground/70 font-mono">{pctFmt(m.wilson_low, 0)}–{pctFmt(m.wilson_high, 0)}</div>
                </div>
                {/* lift */}
                <div className={`text-right shrink-0 w-14 font-mono font-black ${liftColor(m.lift)}`}>
                    {fmtLift(m.lift)}
                    <div className="text-[9px] text-muted-foreground/60 font-sans font-normal uppercase">lift</div>
                </div>
                {/* quota / valore */}
                <div className="text-right shrink-0 w-16">
                    <div className="text-sm font-mono font-bold text-white">{m.odds ? numFmt(m.odds, 2) : '—'}</div>
                    {value
                        ? <div className="text-[9px] uppercase font-bold text-emerald-400">valore</div>
                        : <div className="text-[9px] uppercase text-muted-foreground/60">quota</div>}
                </div>
                {/* concordanza */}
                <div className="text-right shrink-0 w-12 hidden sm:block">
                    <div className="text-sm font-mono font-bold text-white">{m.motori_totali > 0 ? `${m.concordi.length}/${m.motori_totali}` : '—'}</div>
                    <div className="text-[9px] uppercase text-muted-foreground/60">motori</div>
                </div>
                <ChevronDown className={`w-4 h-4 text-muted-foreground shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>

            {expanded && (
                <div className="px-4 pb-4 pt-1 border-t border-white/5 space-y-3">
                    {/* spiegazione affidabilita */}
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                        Storicamente, quando i motori indicavano così, l'esito si è verificato il{' '}
                        <span className="text-white font-bold">{pctFmt(m.affidabilita, 0)}</span> delle volte
                        (banda 95%: {pctFmt(m.wilson_low, 0)}–{pctFmt(m.wilson_high, 0)}, su ~{m.n} partite{' '}
                        {m.scope === 'lega' ? 'della lega' : 'globali'}). Media del mercato: {pctFmt(m.base, 0)} →{' '}
                        <span className={`font-bold ${liftColor(m.lift)}`}>{fmtLift(m.lift)} punti</span>.
                        {m.odds && m.odds > 1 && (
                            <> Quota {numFmt(m.odds, 2)} (prob. implicita {pctFmt(imp, 0)}):{' '}
                                {hasValue(m)
                                    ? <span className="text-emerald-400 font-bold">l'affidabilità batte la quota → possibile valore.</span>
                                    : <span className="text-muted-foreground">la quota già copre l'affidabilità → niente valore.</span>}
                            </>
                        )}
                    </p>
                    {m.lift < 0 && (
                        <p className="text-[11px] text-red-400/80">
                            Attenzione: lo storico va nella direzione opposta per questo mercato — meglio evitarlo.
                        </p>
                    )}

                    {/* cosa dice ogni motore */}
                    <div>
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5 font-bold">Cosa dice ogni motore</div>
                        <div className="space-y-0.5">
                            <EngineRow market={m.market} name="poisson" probs={m.engines.poisson} direction={m.direction} />
                            <EngineRow market={m.market} name="ml" probs={m.engines.ml} direction={m.direction} />
                            <EngineRow market={m.market} name="tacticai" probs={m.engines.tacticai} direction={m.direction} />
                            {/* API: ha solo la direzione, non la prob per selezione */}
                            <div className="flex items-center gap-2 text-xs py-1">
                                <span className="w-20 shrink-0 text-muted-foreground uppercase text-[10px] font-bold">{ENGINE_LABELS.api}</span>
                                {m.engines.api?.dir
                                    ? <>
                                        <span className="px-2 py-0.5 rounded-md border bg-white/10 border-white/30 text-white font-bold text-[11px]">
                                            punta {selectionLabel(m.market, m.engines.api.dir)}
                                        </span>
                                        {m.engines.api.dir === m.direction
                                            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto shrink-0" />
                                            : <span className="ml-auto text-[10px] text-amber-400/80 shrink-0">divergente</span>}
                                    </>
                                    : <span className="text-white/30">non disponibile</span>}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export function DirezioneDashboard({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState<DirezioneData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [openMarket, setOpenMarket] = useState<string | null>(null);
    const reqRef = useRef(0);

    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setData(null);          // non mostrare i dati della partita precedente durante il caricamento
        setOpenMarket(null);    // chiudi eventuale mercato espanso di un'altra partita
        setLoading(true);
        setError(null);
        fetchDirezione(fixtureId)
            .then(d => { if (req === reqRef.current) setData(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setData(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    // mercati ordinati per lift (la RPC li manda gia' ordinati, ma restiamo robusti)
    const markets = useMemo(
        () => [...(data?.markets ?? [])].sort((a, b) => b.lift - a.lift),
        [data],
    );

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <Compass className="w-5 h-5 text-primary" />
                    Direzione
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— migliore per mercato</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Direzione <span className="text-primary">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            La direzione migliore per ogni mercato e quanto è affidabile, dallo storico reale dei motori. {leagueName}.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-3xl mx-auto space-y-4">
                        {loading && (
                            <div className="flex items-center justify-center py-24"><Loader2 className="w-10 h-10 text-primary animate-spin" /></div>
                        )}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {!loading && !error && markets.length === 0 && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Direzione non disponibile per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Serve la previsione Poisson della partita più la calibrazione storica del mercato. Per questa partita non sono ancora presenti.
                                </p>
                            </div>
                        )}

                        {!loading && !error && markets.length > 0 && (
                            <>
                                {/* legenda — capibile a colpo d'occhio */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3 text-[11px] text-muted-foreground space-y-1.5">
                                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-400" /> segnale forte</span>
                                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-400" /> discreto</span>
                                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-400" /> debole / contro</span>
                                    </div>
                                    <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/80 leading-relaxed">
                                        <Info className="w-3 h-3 mt-0.5 shrink-0" />
                                        <span>
                                            <b className="text-white/80">AFFIDABILITÀ</b> = quante volte è andata così nello storico ·
                                            <b className="text-white/80"> LIFT</b> = quanto batte la media (il vero segnale) ·
                                            <b className="text-white/80"> VALORE</b> = l'affidabilità (banda bassa) batte la quota.
                                            Direzione di partenza, non un segnale di profitto: guarda sempre la quota.
                                        </span>
                                    </div>
                                </div>

                                {/* righe mercati, ordinate per forza */}
                                <div className="space-y-2">
                                    {markets.map(m => (
                                        <MarketCard
                                            key={m.market}
                                            m={m}
                                            expanded={openMarket === m.market}
                                            onToggle={() => setOpenMarket(openMarket === m.market ? null : m.market)}
                                        />
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
