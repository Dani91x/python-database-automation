// ============================================================================
// MikeParamsSheet — TUTTI i parametri del bot Mike, modificabili dall'utente.
// Guidato da MIKE_PARAM_FIELDS (specchio della whitelist backend), raggruppati
// per sezione. Salva l'oggetto INTERO via mike_update_params (come Safe/Omega).
// ============================================================================
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
    Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger,
} from '@/components/ui/sheet';
import { Settings } from 'lucide-react';
import {
    MIKE_PARAM_FIELDS, MIKE_PARAM_GROUP_LABEL, mergeMikeParams,
    type MikeParamGroup, type MikeParams,
} from '@/lib/mike';

const GROUPS: MikeParamGroup[] = ['generale', 'pre', 'cover', 'cashout', 'uscite', 'reentry', 'rischio'];

export interface MikeParamsSheetProps {
    params: MikeParams;
    busy: boolean;
    onSave: (p: MikeParams) => Promise<void> | void;
}

export function MikeParamsSheet({ params, busy, onSave }: MikeParamsSheetProps) {
    const [draft, setDraft] = useState<MikeParams>(() => ({ ...params }));
    const [open, setOpen] = useState(false);
    // ri-sincronizza il form quando arrivano parametri nuovi dal server e il pannello e' chiuso
    useEffect(() => { if (!open) setDraft({ ...params }); }, [params, open]);

    const set = (key: string, value: number | boolean | string) => setDraft((d) => ({ ...d, [key]: value }));

    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
                <Button variant="outline" size="sm" data-testid="mike-params-trigger">
                    <Settings className="w-4 h-4 mr-1" />Parametri
                </Button>
            </SheetTrigger>
            <SheetContent className="glass-card border-white/10 w-full sm:max-w-md overflow-y-auto">
                <SheetHeader>
                    <SheetTitle className="font-display flex items-center gap-2">
                        <span className="text-teal-300 text-xl">🎯</span> Parametri Mike
                    </SheetTitle>
                    <SheetDescription>
                        Tutto modificabile. Salva per applicare a caldo: il servizio rilegge i parametri a ogni ciclo.
                        Valori fuori dai limiti vengono riportati nei limiti dal backend.
                    </SheetDescription>
                </SheetHeader>

                <div className="mt-5 space-y-5">
                    {GROUPS.map((g) => (
                        <section key={g} data-testid={`mike-params-group-${g}`}>
                            <div className="text-[11px] uppercase tracking-wide text-teal-300 font-heading font-bold pb-1 border-b border-white/10">
                                {MIKE_PARAM_GROUP_LABEL[g]}
                            </div>
                            <div className="mt-2 space-y-3">
                                {MIKE_PARAM_FIELDS.filter((f) => f.group === g).map((f) => {
                                    if (f.kind === 'bool') {
                                        return (
                                            <label key={f.key} className="flex items-start gap-2 text-sm">
                                                <input
                                                    type="checkbox" className="mt-1" aria-label={f.label}
                                                    checked={Boolean(draft[f.key])}
                                                    onChange={(e) => set(f.key, e.target.checked)}
                                                />
                                                <span>
                                                    <span className="block">{f.label}</span>
                                                    {f.hint && <span className="block text-[11px] text-slate-500">{f.hint}</span>}
                                                </span>
                                            </label>
                                        );
                                    }
                                    if (f.kind === 'choice') {
                                        return (
                                            <label key={f.key} className="block">
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <select
                                                    aria-label={f.label}
                                                    value={String(draft[f.key])}
                                                    onChange={(e) => set(f.key, e.target.value)}
                                                    className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm"
                                                >
                                                    {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                                                </select>
                                                {f.hint && <span className="text-[11px] text-slate-500">{f.hint}</span>}
                                            </label>
                                        );
                                    }
                                    if (f.kind === 'text') {
                                        return (
                                            <label key={f.key} className="block">
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <input
                                                    type="text" aria-label={f.label}
                                                    value={String(draft[f.key] ?? '')}
                                                    onChange={(e) => set(f.key, e.target.value)}
                                                    className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm"
                                                />
                                                {f.hint && <span className="text-[11px] text-slate-500">{f.hint}</span>}
                                            </label>
                                        );
                                    }
                                    return (
                                        <label key={f.key} className="block">
                                            <span className="text-xs text-slate-400">{f.label}</span>
                                            <input
                                                type="number" step={f.step} min={f.min} max={f.max} aria-label={f.label}
                                                value={Number(draft[f.key])}
                                                onChange={(e) => set(f.key, Number(e.target.value))}
                                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                                            />
                                            {f.hint && <span className="text-[11px] text-slate-500">{f.hint}</span>}
                                        </label>
                                    );
                                })}
                            </div>
                        </section>
                    ))}

                    <Button
                        onClick={() => { void onSave(mergeMikeParams(draft)); setOpen(false); }}
                        disabled={busy}
                        className="w-full bg-teal-500 text-black hover:bg-teal-400"
                        data-testid="mike-params-save"
                    >
                        Salva parametri
                    </Button>
                    <p className="text-[11px] text-slate-500 pb-6">
                        La modalità (PAPER/LIVE) non è un parametro: si cambia solo dal toggle in alto con conferma.
                    </p>
                </div>
            </SheetContent>
        </Sheet>
    );
}
