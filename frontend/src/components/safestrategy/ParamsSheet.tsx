// ============================================================================
// ParamsSheet.tsx — pannello parametri SAFE STRATEGY (tutti modificabili).
//
// I default sono quelli operativi delle 4 strategie; ogni campo è editabile e
// persistito in localStorage (via provider). Validazione al salvataggio: niente
// valori malformati o range invertiti — in caso di errore NON si salva e si
// spiega il perché. "Ripristina default" torna ai valori originali.
// ============================================================================
import { useState, type ReactNode } from 'react';
import { Settings2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from '@/components/ui/sheet';
import {
    DEFAULT_PARAMS,
    parseScoreline,
    type SafeStrategyParams,
} from '@/lib/safeStrategy';
import { useSafeStrategy } from './SafeStrategyProvider';

// ---- bozza testuale (permette digitazione libera, validata al salvataggio) ----
interface Draft {
    base: { minuteMin: string; minuteMax: string; scores: string; favPreMin: string; favPreMax: string; dogPreMin: string; dogPreMax: string; favLiveMin: string; favLiveMax: string };
    esatto: { minuteMin: string; minuteMax: string; scores: string; maxGoalsLaySide: string; entryMin: string; entryMax: string };
    punta: { minuteMin: string; minuteMax: string; scores: string; entryMin: string; entryMax: string; minMinutesAfterGoal: string };
    tennis: { setsLeadMin: string; gamesLeadMin: string; backMax: string; layMin: string; layMax: string; excludeDoubles: boolean };
}

function toDraft(p: SafeStrategyParams): Draft {
    const s = (n: number) => String(n);
    return {
        base: {
            minuteMin: s(p.base.minuteMin), minuteMax: s(p.base.minuteMax), scores: p.base.scores.join(', '),
            favPreMin: s(p.base.favPreMin), favPreMax: s(p.base.favPreMax),
            dogPreMin: s(p.base.dogPreMin), dogPreMax: s(p.base.dogPreMax),
            favLiveMin: s(p.base.favLiveMin), favLiveMax: s(p.base.favLiveMax),
        },
        esatto: {
            minuteMin: s(p.esatto.minuteMin), minuteMax: s(p.esatto.minuteMax), scores: p.esatto.scores.join(', '),
            maxGoalsLaySide: s(p.esatto.maxGoalsLaySide), entryMin: s(p.esatto.entryMin), entryMax: s(p.esatto.entryMax),
        },
        punta: {
            minuteMin: s(p.punta.minuteMin), minuteMax: s(p.punta.minuteMax), scores: p.punta.scores.join(', '),
            entryMin: s(p.punta.entryMin), entryMax: s(p.punta.entryMax), minMinutesAfterGoal: s(p.punta.minMinutesAfterGoal),
        },
        tennis: {
            setsLeadMin: s(p.tennis.setsLeadMin), gamesLeadMin: s(p.tennis.gamesLeadMin),
            backMax: s(p.tennis.backMax), layMin: s(p.tennis.layMin), layMax: s(p.tennis.layMax),
            excludeDoubles: p.tennis.excludeDoubles,
        },
    };
}

function parseNum(label: string, raw: string, errors: string[]): number {
    const v = Number(raw.replace(',', '.'));
    if (!Number.isFinite(v)) errors.push(`${label}: valore non valido ("${raw}")`);
    return v;
}
function parseScores(label: string, raw: string, errors: string[]): string[] {
    const parts = raw.split(/[,;]+/).map((x) => x.trim()).filter(Boolean);
    const valid = parts.filter((x) => parseScoreline(x) !== null);
    if (valid.length === 0 || valid.length !== parts.length) {
        errors.push(`${label}: usa punteggi tipo "1-0, 2-1"`);
    }
    return valid;
}
function checkRange(label: string, min: number, max: number, errors: string[]): void {
    if (Number.isFinite(min) && Number.isFinite(max) && min > max) {
        errors.push(`${label}: minimo maggiore del massimo`);
    }
}

function fromDraft(d: Draft): { params: SafeStrategyParams | null; errors: string[] } {
    const errors: string[] = [];
    const params: SafeStrategyParams = {
        base: {
            minuteMin: parseNum('Base · minuto min', d.base.minuteMin, errors),
            minuteMax: parseNum('Base · minuto max', d.base.minuteMax, errors),
            scores: parseScores('Base · punteggi', d.base.scores, errors),
            favPreMin: parseNum('Base · favorita pre min', d.base.favPreMin, errors),
            favPreMax: parseNum('Base · favorita pre max', d.base.favPreMax, errors),
            dogPreMin: parseNum('Base · sfavorita pre min', d.base.dogPreMin, errors),
            dogPreMax: parseNum('Base · sfavorita pre max', d.base.dogPreMax, errors),
            favLiveMin: parseNum('Base · quota live min', d.base.favLiveMin, errors),
            favLiveMax: parseNum('Base · quota live max', d.base.favLiveMax, errors),
        },
        esatto: {
            minuteMin: parseNum('R.E. · minuto min', d.esatto.minuteMin, errors),
            minuteMax: parseNum('R.E. · minuto max', d.esatto.minuteMax, errors),
            scores: parseScores('R.E. · punteggi', d.esatto.scores, errors),
            maxGoalsLaySide: parseNum('R.E. · max gol lato bancato', d.esatto.maxGoalsLaySide, errors),
            entryMin: parseNum('R.E. · quota min', d.esatto.entryMin, errors),
            entryMax: parseNum('R.E. · quota max', d.esatto.entryMax, errors),
        },
        punta: {
            minuteMin: parseNum('Punta · minuto min', d.punta.minuteMin, errors),
            minuteMax: parseNum('Punta · minuto max', d.punta.minuteMax, errors),
            scores: parseScores('Punta · punteggi', d.punta.scores, errors),
            entryMin: parseNum('Punta · quota min', d.punta.entryMin, errors),
            entryMax: parseNum('Punta · quota max', d.punta.entryMax, errors),
            minMinutesAfterGoal: parseNum('Punta · minuti post-gol', d.punta.minMinutesAfterGoal, errors),
        },
        tennis: {
            setsLeadMin: parseNum('Tennis · set di vantaggio', d.tennis.setsLeadMin, errors),
            gamesLeadMin: parseNum('Tennis · game di vantaggio', d.tennis.gamesLeadMin, errors),
            backMax: parseNum('Tennis · back max', d.tennis.backMax, errors),
            layMin: parseNum('Tennis · lay min', d.tennis.layMin, errors),
            layMax: parseNum('Tennis · lay max', d.tennis.layMax, errors),
            excludeDoubles: d.tennis.excludeDoubles,
        },
    };
    checkRange('Base · minuto', params.base.minuteMin, params.base.minuteMax, errors);
    checkRange('Base · favorita pre-match', params.base.favPreMin, params.base.favPreMax, errors);
    checkRange('Base · sfavorita pre-match', params.base.dogPreMin, params.base.dogPreMax, errors);
    checkRange('Base · quota live', params.base.favLiveMin, params.base.favLiveMax, errors);
    checkRange('R.E. · minuto', params.esatto.minuteMin, params.esatto.minuteMax, errors);
    checkRange('R.E. · quota', params.esatto.entryMin, params.esatto.entryMax, errors);
    checkRange('Punta · minuto', params.punta.minuteMin, params.punta.minuteMax, errors);
    checkRange('Punta · quota', params.punta.entryMin, params.punta.entryMax, errors);
    checkRange('Tennis · lay', params.tennis.layMin, params.tennis.layMax, errors);
    if (Number.isFinite(params.punta.minMinutesAfterGoal) && params.punta.minMinutesAfterGoal < 0) {
        errors.push('Punta · minuti post-gol: deve essere ≥ 0');
    }
    if (Number.isFinite(params.tennis.setsLeadMin) && params.tennis.setsLeadMin < 1) {
        errors.push('Tennis · set di vantaggio: deve essere ≥ 1');
    }
    if (Number.isFinite(params.tennis.gamesLeadMin) && params.tennis.gamesLeadMin < 1) {
        errors.push('Tennis · game di vantaggio: deve essere ≥ 1');
    }
    return { params: errors.length === 0 ? params : null, errors };
}

// ------------------------------------------------------------ campi riusabili
function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div className="space-y-1">
            <Label className="text-[11px] text-muted-foreground">{label}</Label>
            <Input
                value={value}
                inputMode="decimal"
                onChange={(e) => onChange(e.target.value)}
                className="h-8 font-mono tabular-nums bg-black/40 border-white/10"
            />
        </div>
    );
}
function ScoresField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div className="space-y-1 col-span-2">
            <Label className="text-[11px] text-muted-foreground">{label}</Label>
            <Input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder="es. 1-0, 2-1"
                className="h-8 font-mono tabular-nums bg-black/40 border-white/10"
            />
        </div>
    );
}
function Section({ title, children }: { title: string; children: ReactNode }) {
    return (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="font-heading font-bold text-xs uppercase tracking-wide text-white mb-2">{title}</div>
            <div className="grid grid-cols-2 gap-2">{children}</div>
        </div>
    );
}

export function ParamsSheet() {
    const { params, saveParams, resetParams } = useSafeStrategy();
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState<Draft>(() => toDraft(params));

    const set = <K extends keyof Draft>(group: K, patch: Partial<Draft[K]>) =>
        setDraft((prev) => ({ ...prev, [group]: { ...prev[group], ...patch } }));

    const onSave = () => {
        const { params: parsed, errors } = fromDraft(draft);
        if (!parsed) {
            toast.error('Parametri non validi', { description: errors[0] });
            return;
        }
        saveParams(parsed);
        toast.success('Parametri Safe Strategy salvati');
        setOpen(false);
    };

    return (
        <Sheet
            open={open}
            onOpenChange={(v) => {
                setOpen(v);
                if (v) setDraft(toDraft(params));
            }}
        >
            <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                    <Settings2 className="w-4 h-4 mr-1" /> Parametri
                </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto bg-background border-white/10">
                <SheetHeader>
                    <SheetTitle className="font-display">Parametri Safe Strategy</SheetTitle>
                    <SheetDescription>
                        Le condizioni dei segnali. Modifiche salvate su questo dispositivo.
                    </SheetDescription>
                </SheetHeader>

                <div className="mt-4 space-y-3">
                    <Section title="1 · Calcio — Base (banca chi perde)">
                        <NumField label="Minuto min" value={draft.base.minuteMin} onChange={(v) => set('base', { minuteMin: v })} />
                        <NumField label="Minuto max" value={draft.base.minuteMax} onChange={(v) => set('base', { minuteMax: v })} />
                        <ScoresField label="Punteggi (gol favorita per primi)" value={draft.base.scores} onChange={(v) => set('base', { scores: v })} />
                        <NumField label="Favorita pre-match min" value={draft.base.favPreMin} onChange={(v) => set('base', { favPreMin: v })} />
                        <NumField label="Favorita pre-match max" value={draft.base.favPreMax} onChange={(v) => set('base', { favPreMax: v })} />
                        <NumField label="Sfavorita pre-match min" value={draft.base.dogPreMin} onChange={(v) => set('base', { dogPreMin: v })} />
                        <NumField label="Sfavorita pre-match max" value={draft.base.dogPreMax} onChange={(v) => set('base', { dogPreMax: v })} />
                        <NumField label="Quota live favorita min" value={draft.base.favLiveMin} onChange={(v) => set('base', { favLiveMin: v })} />
                        <NumField label="Quota live favorita max" value={draft.base.favLiveMax} onChange={(v) => set('base', { favLiveMax: v })} />
                    </Section>

                    <Section title="2 · Calcio — Risultato Esatto (banca “Altro risultato”)">
                        <NumField label="Minuto min" value={draft.esatto.minuteMin} onChange={(v) => set('esatto', { minuteMin: v })} />
                        <NumField label="Minuto max" value={draft.esatto.minuteMax} onChange={(v) => set('esatto', { minuteMax: v })} />
                        <ScoresField label="Punteggi (qualsiasi ordine)" value={draft.esatto.scores} onChange={(v) => set('esatto', { scores: v })} />
                        <NumField label="Max gol lato bancato" value={draft.esatto.maxGoalsLaySide} onChange={(v) => set('esatto', { maxGoalsLaySide: v })} />
                        <div />
                        <NumField label="Quota min" value={draft.esatto.entryMin} onChange={(v) => set('esatto', { entryMin: v })} />
                        <NumField label="Quota max" value={draft.esatto.entryMax} onChange={(v) => set('esatto', { entryMax: v })} />
                    </Section>

                    <Section title="3 · Calcio — Punta (back chi vince di 2)">
                        <NumField label="Minuto min" value={draft.punta.minuteMin} onChange={(v) => set('punta', { minuteMin: v })} />
                        <NumField label="Minuto max" value={draft.punta.minuteMax} onChange={(v) => set('punta', { minuteMax: v })} />
                        <ScoresField label="Punteggi (gol di chi è avanti per primi)" value={draft.punta.scores} onChange={(v) => set('punta', { scores: v })} />
                        <NumField label="Quota min" value={draft.punta.entryMin} onChange={(v) => set('punta', { entryMin: v })} />
                        <NumField label="Quota max" value={draft.punta.entryMax} onChange={(v) => set('punta', { entryMax: v })} />
                        <NumField label="Minuti dopo l'ultimo gol" value={draft.punta.minMinutesAfterGoal} onChange={(v) => set('punta', { minMinutesAfterGoal: v })} />
                    </Section>

                    <Section title="4 · Tennis (punta chi è avanti / banca chi è sotto)">
                        <NumField label="Set di vantaggio min" value={draft.tennis.setsLeadMin} onChange={(v) => set('tennis', { setsLeadMin: v })} />
                        <NumField label="Game di vantaggio min" value={draft.tennis.gamesLeadMin} onChange={(v) => set('tennis', { gamesLeadMin: v })} />
                        <NumField label="Back max (chi è avanti)" value={draft.tennis.backMax} onChange={(v) => set('tennis', { backMax: v })} />
                        <div />
                        <NumField label="Lay min (chi è sotto)" value={draft.tennis.layMin} onChange={(v) => set('tennis', { layMin: v })} />
                        <NumField label="Lay max (chi è sotto)" value={draft.tennis.layMax} onChange={(v) => set('tennis', { layMax: v })} />
                        <div className="col-span-2 flex items-center gap-2 pt-1">
                            <Checkbox
                                id="ss-exclude-doubles"
                                checked={draft.tennis.excludeDoubles}
                                onCheckedChange={(v) => set('tennis', { excludeDoubles: v === true })}
                            />
                            <Label htmlFor="ss-exclude-doubles" className="text-xs text-muted-foreground">
                                Escludi i doppi
                            </Label>
                        </div>
                    </Section>
                </div>

                <div className="mt-4 flex items-center gap-2">
                    <Button onClick={onSave} className="flex-1">
                        Salva parametri
                    </Button>
                    <Button
                        variant="outline"
                        className="border-white/10 text-muted-foreground hover:text-white"
                        onClick={() => {
                            resetParams();
                            setDraft(toDraft(DEFAULT_PARAMS));
                            toast.success('Parametri riportati ai default');
                        }}
                    >
                        Ripristina default
                    </Button>
                </div>
            </SheetContent>
        </Sheet>
    );
}
