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
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
    Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger,
} from '@/components/ui/sheet';
import { Settings } from 'lucide-react';
import { fmtNum, fmtTime } from '@/lib/format';
import { T } from '@/lib/tradeStatus';
// 28/09 (CANTIERE N): l'interruttore delle uscite e' UNO per tutta l'app
import { InterruttoreUscite } from '@/components/controlroom/InterruttoreUscite';

export interface ParamOption { value: string; label: string }

export interface ParamField {
    key: string;
    label: string;
    /** nota sotto il campo: testo o markup (es. "il servizio usa X") */
    hint?: ReactNode;
    /** 'text' = stringa libera (es. un percorso): nessun clamp, nessun cast;
     *  'choice' = uno fra `options`, mostrati come PULSANTI affiancati */
    type: 'number' | 'boolean' | 'select' | 'text' | 'choice' | 'uscite';
    min?: number;
    max?: number;
    step?: number;
    options?: ParamOption[];
    /** 28/09 (CANTIERE N) - `type: 'uscite'`: l'interruttore delle uscite del
     *  bot. Si cambia SOLO col componente comune `InterruttoreUscite` (stesse
     *  parole della Control Room, conferma per passare ad automatiche): qui i
     *  due valori che il servizio legge per "automatiche" e "manuali". */
    uscite?: { automatico: string | boolean; manuale: string | boolean };
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
    triggerTestId = 'params-trigger', footer, symbol, riscontroSalvataggio = false,
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
    /**
     * 30/09 (Mike, «il feedback visivo del pulsante non funziona»): con `true`
     * il pannello DICE l'esito del salvataggio sotto il pulsante («Parametri
     * salvati alle HH:MM:SS» oppure l'errore testuale di `onSave`, che per
     * questo deve RIGETTARE in caso di errore), il pulsante scrive
     * «Salvataggio…» mentre aspetta e, dopo un salvataggio riuscito, la bozza
     * si riallinea ai valori del servizio (il pallino "modifiche non salvate"
     * si spegne). Assente/false = comportamento di prima, identico (Safe,
     * Omega, tennis).
     */
    riscontroSalvataggio?: boolean;
}) {
    const [draft, setDraft] = useState<ParamValues>(values);
    const [clamped, setClamped] = useState<Record<string, number>>({});
    const [touched, setTouched] = useState(false);
    // solo con `riscontroSalvataggio`: l'attesa e l'esito dell'ultimo salvataggio
    const [salvando, setSalvando] = useState(false);
    const [esito, setEsito] = useState<{ ok: true; ms: number } | { ok: false; errore: string } | null>(null);

    // `values` cambia quando il servizio ripubblica i parametri: si riallinea
    // solo se l'utente non ha modifiche in corso (non si perde l'editing).
    const serverKey = useMemo(() => JSON.stringify(values), [values]);
    const [lastServerKey, setLastServerKey] = useState(serverKey);
    // ultimi valori del servizio, leggibili DOPO un `await` (la chiusura di
    // `save` vedrebbe quelli del render in cui e' partita)
    const ultimiDelServizio = useRef({ key: serverKey, values });
    ultimiDelServizio.current = { key: serverKey, values };
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
        if (!riscontroSalvataggio) {
            await onSave(r.values);
            setTouched(false);
            return;
        }
        setSalvando(true);
        setEsito(null);
        const keyPrima = ultimiDelServizio.current.key;
        try {
            await onSave(r.values);
            setEsito({ ok: true, ms: Date.now() });
            setTouched(false);
            // review incrociata 30/09 (M1): la bozza resta sui valori SALVATI.
            // Prima si forzava il riallineo (`setLastServerKey('')`) e, dove la
            // rilettura non e' aspettata (Control Room: `vm.ricarica()` non
            // attesa), la bozza tornava ai valori VECCHI finche' non arrivava
            // la rilettura; se falliva restavano i vecchi e un secondo «Salva»
            // li riscriveva nel servizio. Ora si riallinea SOLO quando il
            // servizio ripubblica (`serverKey` cambia, touched falso), o subito
            // se e' gia' cambiato durante il salvataggio.
            const dopo = ultimiDelServizio.current;
            setDraft(dopo.key !== keyPrima ? dopo.values : r.values);
        } catch (e) {
            // la bozza resta: le modifiche NON sono salvate e il pallino lo dice
            setEsito({ ok: false, errore: String((e as Error)?.message ?? e) });
        } finally {
            setSalvando(false);
        }
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
                                // 24/09 - 'choice': una scelta fra POCHI valori mostrati
                                // come pulsanti affiancati. Dentro un <label> il clic sul
                                // testo premerebbe il primo pulsante: qui il contenitore e'
                                // un <div role="group">.
                                const Wrap = f.type === 'choice' || f.type === 'uscite' ? 'div' : 'label';
                                return (
                                    <Wrap key={f.key} className={f.type === 'boolean' ? 'flex items-center gap-2 text-sm' : 'block'}
                                        {...(f.type === 'choice' || f.type === 'uscite' ? { role: 'group', 'aria-label': f.label } : {})}>
                                        {f.type === 'uscite' && f.uscite ? (
                                            <>
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <InterruttoreUscite
                                                    id={`params-${f.key}`}
                                                    uscite={{ automatiche: String(v ?? '') === String(f.uscite.automatico) }}
                                                    cambia={(a) => setField(f, a ? f.uscite!.automatico : f.uscite!.manuale)}
                                                />
                                                <span className="text-[11px] text-slate-500 block">
                                                    si applica al bot con "Salva parametri"
                                                </span>
                                            </>
                                        ) : f.type === 'choice' ? (
                                            <>
                                                <span className="text-xs text-slate-400">{f.label}</span>
                                                <div className="mt-1 grid grid-cols-2 gap-2">
                                                    {(f.options ?? []).map((o) => {
                                                        const scelto = String(v ?? '') === o.value;
                                                        return (
                                                            <button
                                                                key={o.value}
                                                                type="button"
                                                                aria-pressed={scelto}
                                                                data-testid="params-choice"
                                                                data-field={f.key}
                                                                data-value={o.value}
                                                                onClick={() => setField(f, o.value)}
                                                                className={`rounded-md border px-3 py-2 text-xs text-left ${scelto
                                                                    ? 'border-sky-400/70 bg-sky-500/20 text-sky-100'
                                                                    : 'border-white/10 bg-black/50 text-slate-300'}`}
                                                            >
                                                                {o.label}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </>
                                        ) : f.type === 'boolean' ? (
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
                                    </Wrap>
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
                        <Button onClick={() => { void save(); }} disabled={busy || salvando} className="flex-1 bg-primary text-black hover:bg-primary/90" data-testid="params-save">
                            {salvando ? 'Salvataggio…' : T.saveParams}
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
                    {riscontroSalvataggio && esito && (
                        <p className={`text-[11px] ${esito.ok ? 'text-emerald-300' : 'text-red-300'}`}
                            data-testid="params-esito" data-esito={esito.ok ? 'ok' : 'errore'} role="status">
                            {esito.ok
                                ? `Parametri salvati alle ${fmtTime(esito.ms, { seconds: true })}`
                                : `Salvataggio NON riuscito: ${esito.errore}`}
                        </p>
                    )}
                    {footer && <div className="text-[11px] text-slate-500 pb-6">{footer}</div>}
                </div>
            </SheetContent>
        </Sheet>
    );
}

export default ParamsSheetBase;
