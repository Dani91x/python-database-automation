// ============================================================================
// ParamsSheetBase.tsx — pannello parametri SPEC-DRIVEN condiviso.
//
// I tre bot avevano tre pannelli con tre UI diverse: "Default" solo in Safe,
// validazione solo nel radar, nessun indicatore di modifiche non salvate.
// Qui la spec (gruppi + campi) descrive il pannello e il componente garantisce
// per tutti: clamp VISIBILE ("clampato a X"), indicatore `dirty`, bottone
// "Salva parametri" unico, "Default" per tornare ai valori di fabbrica.
//
// I pannelli esistenti (Omega/Safe/Mike) verranno migrati dagli agenti di
// sezione: questo file è la base, già testata.
// ============================================================================
import { useMemo, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
    Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger,
} from '@/components/ui/sheet';
import { Settings } from 'lucide-react';
import { fmtNum } from '@/lib/format';
import { T } from '@/lib/tradeStatus';

export interface ParamOption { value: string; label: string }

export interface ParamField {
    key: string;
    label: string;
    /** nota sotto il campo: testo o markup (es. "il servizio usa X") */
    hint?: ReactNode;
    /** 'text' = stringa libera (es. un percorso): nessun clamp, nessun cast */
    type: 'number' | 'boolean' | 'select' | 'text';
    min?: number;
    max?: number;
    step?: number;
    options?: ParamOption[];
}

export interface ParamGroup {
    label: string;
    /** testo introduttivo del gruppo (spiega COSA fa, non come) */
    note?: ReactNode;
    fields: ParamField[];
}

export type ParamValues = Record<string, number | boolean | string>;

/**
 * Applica i limiti di un campo numerico. Ritorna anche se ha clampato: la UI
 * DEVE dirlo (un valore silenziosamente cambiato su un bot di trading è un
 * bug di soldi, non un dettaglio estetico).
 */
export function clampField(f: ParamField, raw: number): { value: number; clamped: boolean } {
    let v = raw;
    if (f.min != null && v < f.min) v = f.min;
    if (f.max != null && v > f.max) v = f.max;
    return { value: v, clamped: v !== raw };
}

/** Applica il clamp a tutti i campi numerici della spec. */
export function clampValues(groups: ParamGroup[], values: ParamValues): { values: ParamValues; clamped: Record<string, number> } {
    const out: ParamValues = { ...values };
    const clamped: Record<string, number> = {};
    for (const g of groups) {
        for (const f of g.fields) {
            if (f.type !== 'number') continue;
            if (String(values[f.key] ?? '').trim() === '') continue;
            const raw = Number(values[f.key]);
            if (!Number.isFinite(raw)) continue;
            const r = clampField(f, raw);
            out[f.key] = r.value;
            if (r.clamped) clamped[f.key] = r.value;
        }
    }
    return { values: out, clamped };
}

export function ParamsSheetBase({
    title, description, groups, values, onSave, onReset, busy, triggerLabel = 'Parametri',
    triggerTestId = 'params-trigger', footer, symbol,
}: {
    title: string;
    description?: ReactNode;
    groups: ParamGroup[];
    values: ParamValues;
    onSave: (v: ParamValues) => void | Promise<void>;
    /** ripristina i valori di fabbrica (mostra il bottone "Default") */
    onReset?: () => ParamValues;
    busy?: boolean;
    triggerLabel?: string;
    triggerTestId?: string;
    footer?: ReactNode;
    /** simbolo del bot nel titolo dello sheet */
    symbol?: ReactNode;
}) {
    const [draft, setDraft] = useState<ParamValues>(values);
    const [clamped, setClamped] = useState<Record<string, number>>({});
    const [touched, setTouched] = useState(false);

    // `values` cambia quando il servizio ripubblica i parametri: si riallinea
    // solo se l'utente non ha modifiche in corso (non si perde l'editing).
    const serverKey = useMemo(() => JSON.stringify(values), [values]);
    const [lastServerKey, setLastServerKey] = useState(serverKey);
    if (serverKey !== lastServerKey) {
        setLastServerKey(serverKey);
        if (!touched) setDraft(values);
    }

    const dirty = useMemo(
        () => groups.some((g) => g.fields.some((f) => String(draft[f.key] ?? '') !== String(values[f.key] ?? ''))),
        [groups, draft, values],
    );

    function setField(f: ParamField, raw: number | boolean | string) {
        setTouched(true);
        if (f.type === 'number') {
            const n = Number(raw);
            // campo svuotato o non numerico: nessun clamp (altrimenti l'utente
            // non riuscirebbe piu' a riscrivere il valore da zero)
            if (String(raw).trim() === '' || !Number.isFinite(n)) {
                setClamped((p) => { const next = { ...p }; delete next[f.key]; return next; });
                setDraft((p) => ({ ...p, [f.key]: raw }));
                return;
            }
            const r = clampField(f, n);
            setClamped((p) => {
                const next = { ...p };
                if (r.clamped) next[f.key] = r.value; else delete next[f.key];
                return next;
            });
            setDraft((p) => ({ ...p, [f.key]: r.value }));
            return;
        }
        setDraft((p) => ({ ...p, [f.key]: raw }));
    }

    async function save() {
        const r = clampValues(groups, draft);
        setClamped(r.clamped);
        setDraft(r.values);
        await onSave(r.values);
        setTouched(false);
    }

    return (
        <Sheet>
            <SheetTrigger asChild>
                <Button variant="outline" size="sm" data-testid={triggerTestId}>
                    <Settings className="w-4 h-4 mr-1" aria-hidden />{triggerLabel}
                    {dirty && <span className="ml-1 text-amber-300" aria-hidden>•</span>}
                </Button>
            </SheetTrigger>
            <SheetContent className="glass-card border-white/10 w-full sm:max-w-md overflow-y-auto" data-testid="params-sheet">
                <SheetHeader>
                    <SheetTitle className="font-display flex items-center gap-2">
                        {symbol}{title}
                    </SheetTitle>
                    {/* sempre presente: Radix richiede una descrizione accessibile */}
                    <SheetDescription>
                        {description ?? 'Modifica i parametri e premi «Salva parametri» per applicarli al servizio.'}
                    </SheetDescription>
                </SheetHeader>

                <div className="mt-5 space-y-5">
                    {groups.map((g) => (
                        <section key={g.label} className="space-y-3" data-testid="params-group" data-group={g.label}>
                            <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold">{g.label}</div>
                            {g.note && <p className="text-[11px] text-slate-500">{g.note}</p>}
                            {g.fields.map((f) => {
                                const v = draft[f.key];
                                const cl = clamped[f.key];
                                return (
                                    <label key={f.key} className={f.type === 'boolean' ? 'flex items-center gap-2 text-sm' : 'block'}>
                                        {f.type === 'boolean' ? (
                                            <>
                                                <input
                                                    type="checkbox"
                                                    checked={Boolean(v)}
                                                    aria-label={f.label}
                                                    onChange={(e) => setField(f, e.target.checked)}
                                                />
                                                <span>{f.label}</span>
                                            </>
                                        ) : f.type === 'text' ? (
                                            <>
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <input
                                                    type="text"
                                                    value={String(v ?? '')}
                                                    aria-label={f.label}
                                                    onChange={(e) => setField(f, e.target.value)}
                                                    className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm"
                                                />
                                            </>
                                        ) : f.type === 'select' ? (
                                            <>
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <select
                                                    value={String(v ?? '')}
                                                    aria-label={f.label}
                                                    onChange={(e) => setField(f, e.target.value)}
                                                    className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm"
                                                >
                                                    {(f.options ?? []).map((o) => (
                                                        <option key={o.value} value={o.value}>{o.label}</option>
                                                    ))}
                                                </select>
                                            </>
                                        ) : (
                                            <>
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <input
                                                    type="number"
                                                    value={String(v ?? '')}
                                                    min={f.min}
                                                    max={f.max}
                                                    step={f.step}
                                                    aria-label={f.label}
                                                    onChange={(e) => setField(f, e.target.value)}
                                                    className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                                                />
                                            </>
                                        )}
                                        {f.hint && <span className="text-[11px] text-slate-500 block">{f.hint}</span>}
                                        {cl != null && (
                                            <span className="text-[11px] text-amber-300 block" data-testid="params-clamped" data-field={f.key}>
                                                clampato a {fmtNum(cl, Number.isInteger(cl) ? 0 : 2)}
                                                {f.min != null || f.max != null
                                                    ? ` (ammesso ${f.min != null ? fmtNum(f.min, Number.isInteger(f.min) ? 0 : 2) : '−∞'} … ${f.max != null ? fmtNum(f.max, Number.isInteger(f.max) ? 0 : 2) : '+∞'})`
                                                    : ''}
                                            </span>
                                        )}
                                    </label>
                                );
                            })}
                        </section>
                    ))}

                    {dirty && (
                        <p className="text-[11px] text-amber-300" data-testid="params-dirty">
                            modifiche non salvate: premi «{T.saveParams}» per applicarle al servizio
                        </p>
                    )}
                    <div className="flex items-center gap-2">
                        <Button onClick={() => { void save(); }} disabled={busy} className="flex-1 bg-primary text-black hover:bg-primary/90" data-testid="params-save">
                            {T.saveParams}
                        </Button>
                        {onReset && (
                            <Button
                                variant="outline"
                                onClick={() => { setTouched(true); setClamped({}); setDraft(onReset()); }}
                                disabled={busy}
                                data-testid="params-reset"
                            >{T.resetParams}</Button>
                        )}
                    </div>
                    {footer && <div className="text-[11px] text-slate-500 pb-6">{footer}</div>}
                </div>
            </SheetContent>
        </Sheet>
    );
}

export default ParamsSheetBase;
