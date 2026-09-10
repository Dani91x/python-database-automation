// ============================================================================
// BotParamsSheet.tsx — parametri del BOT Safe Strategy (fonte unica: il DB).
//
// Quando la riga safe_strategy_control esiste, i parametri veri sono i suoi:
// si leggono da lì e si salvano con safe_update_params (MAI localStorage). I
// parametri locali del radar restano validi solo finché il bot non esiste.
// Il minuto delle strategie calcio è una SOGLIA ("dal minuto X in poi").
//
// USCITE AUTOMATICHE (params.exits): il servizio chiude da solo le posizioni
// (profitto / tempo / perdita / rosso / tennis). mergeBotParams non conosce
// `exits`, quindi la sezione legge i valori VERI da `rawParams` (control.params)
// e al salvataggio li rimanda insieme al resto — safe_update_params sostituisce
// l'intero oggetto, un salvataggio senza `exits` li cancellerebbe.
// ============================================================================
import { useState } from 'react';
import { Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger,
} from '@/components/ui/sheet';
import { SAFE_BOT_DEFAULTS, type SafeBotParams } from '@/lib/safeBot';
import type { VariantId } from '@/lib/safeStrategy';

interface NumField { path: string; label: string; step: number; hint?: string }

const BOT_FIELDS: NumField[] = [
    { path: 'poll_interval_s', label: 'Cadenza loop (s)', step: 5, hint: 'ogni quanto il servizio valuta i segnali' },
    { path: 'commission_pct', label: 'Commissione %', step: 0.5, hint: 'aliquota Betfair sul P&L positivo' },
    { path: 'max_open_trades', label: 'Max trade aperti', step: 1, hint: '0 = illimitato' },
    { path: 'max_liability_per_trade', label: 'Liability max per trade €', step: 5 },
    { path: 'min_size_available_factor', label: 'Fattore size abbinabile', step: 0.5, hint: 'richiede abbinabile ≥ fattore × stake' },
    { path: 'stake.laySize', label: 'Stake LAY di default €', step: 0.5, hint: 'usato dal motore e proposto sui segnali LAY' },
    { path: 'stake.backSize', label: 'Stake BACK di default €', step: 0.5, hint: 'usato dal motore e proposto sui segnali BACK' },
];

const OPPS_FIELDS: NumField[] = [
    { path: 'opps_interval_s', label: 'Cadenza opportunità (s)', step: 5 },
    { path: 'opps_min_confidence', label: 'Confidenza minima (0-1)', step: 0.05 },
    { path: 'opps_min_edge', label: 'Edge minimo (0-1)', step: 0.01 },
    { path: 'opps_stake', label: 'Stake opportunità €', step: 0.5 },
];

const STRATEGY_FIELDS: NumField[] = [
    { path: 'base.minuteMin', label: 'BASE · dal minuto', step: 1 },
    { path: 'base.favLiveMin', label: 'BASE · quota live favorita MIN', step: 0.01 },
    { path: 'base.favLiveMax', label: 'BASE · quota live favorita MAX', step: 0.01 },
    { path: 'base.scoreConfirmSec', label: 'BASE · punteggio stabile (s)', step: 5 },
    { path: 'esatto.minuteMin', label: 'R. ESATTO · dal minuto', step: 1 },
    { path: 'esatto.entryMin', label: 'R. ESATTO · quota MIN', step: 1 },
    { path: 'esatto.entryMax', label: 'R. ESATTO · quota MAX', step: 1 },
    { path: 'esatto.maxGoalsLaySide', label: 'R. ESATTO · gol max lato bancato', step: 1 },
    { path: 'esatto.scoreConfirmSec', label: 'R. ESATTO · punteggio stabile (s)', step: 5 },
    { path: 'punta.minuteMin', label: 'PUNTA · dal minuto', step: 1 },
    { path: 'punta.entryMin', label: 'PUNTA · quota MIN', step: 0.01 },
    { path: 'punta.entryMax', label: 'PUNTA · quota MAX', step: 0.01 },
    { path: 'punta.minMinutesAfterGoal', label: 'PUNTA · minuti dopo il gol', step: 1 },
    { path: 'tennis.setsLeadMin', label: 'TENNIS · set di vantaggio', step: 1 },
    { path: 'tennis.gamesLeadMin', label: 'TENNIS · game di vantaggio', step: 1 },
    { path: 'tennis.backMin', label: 'TENNIS · quota leader MIN', step: 0.01 },
    { path: 'tennis.backMax', label: 'TENNIS · quota leader MAX', step: 0.01 },
    { path: 'tennis.scoreConfirmSec', label: 'TENNIS · punteggio stabile (s)', step: 5 },
];

// ---- uscite automatiche (speculare a params.exits del servizio)
export interface ExitsParams {
    enabled: boolean;
    /** BASE: chiusura a mercato dal minuto (soglia) se ancora aperta */
    base_exit_minute: number;
    /** R. ESATTO: chiusura dal minuto */
    esatto_exit_minute: number;
    /** PUNTA: chiusura dal minuto */
    punta_exit_minute: number;
    /** perdita (gol contro / set perso): attesa prima di chiudere, in secondi */
    loss_settle_delay_s: number;
    /** rosso alla favorita: uscita immediata */
    red_card_fav_exit: boolean;
    /** tennis: incasso al game successivo vinto dal leader */
    tennis_take_profit_next_game: boolean;
    /** tennis: uscita se il leader perde due game o il set torna in parità */
    tennis_exit_on_lost_game: boolean;
    /** tentativi massimi di chiusura prima dell'uscita obbligatoria a mercato */
    exit_max_retries: number;
}

export const EXITS_DEFAULTS: ExitsParams = {
    enabled: true,
    base_exit_minute: 80,
    esatto_exit_minute: 72,
    punta_exit_minute: 83,
    loss_settle_delay_s: 30,
    red_card_fav_exit: true,
    tennis_take_profit_next_game: true,
    tennis_exit_on_lost_game: true,
    exit_max_retries: 3,
};

/** merge DIFENSIVO di params.exits: valori mancanti/malformati → default. */
export function mergeExits(raw: unknown): ExitsParams {
    const r = (raw ?? {}) as Record<string, unknown>;
    const n = (v: unknown, d: number) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
    const b = (v: unknown, d: boolean) => (typeof v === 'boolean' ? v : d);
    return {
        enabled: b(r.enabled, EXITS_DEFAULTS.enabled),
        base_exit_minute: n(r.base_exit_minute, EXITS_DEFAULTS.base_exit_minute),
        esatto_exit_minute: n(r.esatto_exit_minute, EXITS_DEFAULTS.esatto_exit_minute),
        punta_exit_minute: n(r.punta_exit_minute, EXITS_DEFAULTS.punta_exit_minute),
        loss_settle_delay_s: n(r.loss_settle_delay_s, EXITS_DEFAULTS.loss_settle_delay_s),
        red_card_fav_exit: b(r.red_card_fav_exit, EXITS_DEFAULTS.red_card_fav_exit),
        tennis_take_profit_next_game: b(r.tennis_take_profit_next_game, EXITS_DEFAULTS.tennis_take_profit_next_game),
        tennis_exit_on_lost_game: b(r.tennis_exit_on_lost_game, EXITS_DEFAULTS.tennis_exit_on_lost_game),
        exit_max_retries: n(r.exit_max_retries, EXITS_DEFAULTS.exit_max_retries),
    };
}

type ExitNumKey = 'base_exit_minute' | 'esatto_exit_minute' | 'punta_exit_minute' | 'loss_settle_delay_s' | 'exit_max_retries';
const EXIT_NUM_FIELDS: { key: ExitNumKey; label: string; step: number; hint: string }[] = [
    { key: 'base_exit_minute', label: 'BASE · uscita a tempo dal minuto', step: 1, hint: 'chiude a mercato (green/red) se il match arriva a questo minuto con la posizione ancora aperta' },
    { key: 'esatto_exit_minute', label: 'R. ESATTO · uscita a tempo dal minuto', step: 1, hint: 'lay sul risultato esatto: incassa il calo della quota prima del finale' },
    { key: 'punta_exit_minute', label: 'PUNTA · uscita a tempo dal minuto', step: 1, hint: 'back a quota bassissima: esce prima che una rimonta annulli il profitto' },
    { key: 'loss_settle_delay_s', label: 'Perdita · attesa prima di chiudere (s)', step: 5, hint: 'gol contro / set perso: aspetta che il punteggio sia confermato (VAR, correzioni) e poi chiude in perdita' },
    { key: 'exit_max_retries', label: 'Tentativi max di chiusura', step: 1, hint: "chiusure non abbinate: dopo questi tentativi l'uscita diventa OBBLIGATORIA al prezzo disponibile" },
];

const VARIANTS: { id: VariantId; label: string }[] = [
    { id: 'base', label: 'Base' },
    { id: 'esatto', label: 'Risultato Esatto' },
    { id: 'punta', label: 'Punta' },
    { id: 'tennis', label: 'Tennis' },
];

function getPath(obj: Record<string, unknown>, path: string): number {
    const v = path.split('.').reduce<unknown>((acc, k) => (acc as Record<string, unknown>)?.[k], obj);
    return Number(v ?? 0);
}
function setPath(obj: SafeBotParams, path: string, value: number): SafeBotParams {
    const keys = path.split('.');
    if (keys.length === 1) return { ...obj, [keys[0]]: value };
    const [g, k] = keys;
    const group = (obj as unknown as Record<string, Record<string, unknown>>)[g] ?? {};
    return { ...obj, [g]: { ...group, [k]: value } } as SafeBotParams;
}

export interface BotParamsSheetProps {
    params: SafeBotParams;
    /** control.params grezzi dal DB: sorgente di `exits` e di ogni chiave che
     *  mergeBotParams non conosce (vanno preservate al salvataggio) */
    rawParams?: Record<string, unknown> | null;
    busy?: boolean;
    onSave: (p: Partial<SafeBotParams>) => Promise<void> | void;
}

function FieldList({ fields, draft, setDraft }: {
    fields: NumField[]; draft: SafeBotParams; setDraft: (p: SafeBotParams) => void;
}) {
    return (
        <>
            {fields.map((f) => (
                <label key={f.path} className="block">
                    <span className="text-xs text-slate-400">{f.label}</span>
                    <input
                        type="number"
                        step={f.step}
                        aria-label={f.label}
                        value={getPath(draft as unknown as Record<string, unknown>, f.path)}
                        onChange={(e) => setDraft(setPath(draft, f.path, Number(e.target.value)))}
                        className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                    />
                    {f.hint && <span className="text-[11px] text-slate-500">{f.hint}</span>}
                </label>
            ))}
        </>
    );
}

export function BotParamsSheet({ params, rawParams = null, busy = false, onSave }: BotParamsSheetProps) {
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState<SafeBotParams>(params);
    const [exits, setExits] = useState<ExitsParams>(() => mergeExits(rawParams?.exits));

    function payload(): Partial<SafeBotParams> {
        // chiavi ignote del servizio preservate; exits sempre esplicito
        return { ...(rawParams ?? {}), ...draft, exits } as Partial<SafeBotParams>;
    }

    function toggleVariant(id: VariantId, on: boolean) {
        const next = on
            ? [...new Set([...draft.variants, id])]
            : draft.variants.filter((v) => v !== id);
        setDraft({ ...draft, variants: next });
    }

    return (
        <Sheet
            open={open}
            onOpenChange={(v) => { setOpen(v); if (v) { setDraft(params); setExits(mergeExits(rawParams?.exits)); } }}
        >
            <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                    <Settings2 className="w-4 h-4 mr-1" /> Parametri
                </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto bg-background border-white/10">
                <SheetHeader>
                    <SheetTitle className="font-display">Parametri bot Safe Strategy</SheetTitle>
                    <SheetDescription>
                        Salvati sul database (safe_update_params): valgono per il servizio e per questa
                        schermata. Il minuto delle strategie calcio è una soglia "dal minuto in poi".
                    </SheetDescription>
                </SheetHeader>

                <div className="mt-4 space-y-4">
                    <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold">Bot</div>
                    <FieldList fields={BOT_FIELDS} draft={draft} setDraft={setDraft} />

                    <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold pt-2">
                        Strategie abilitate
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        {VARIANTS.map((v) => (
                            <label key={v.id} className="flex items-center gap-2 text-sm">
                                <Checkbox
                                    checked={draft.variants.includes(v.id)}
                                    onCheckedChange={(c) => toggleVariant(v.id, c === true)}
                                    aria-label={v.label}
                                />
                                {v.label}
                            </label>
                        ))}
                    </div>

                    <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold pt-2">
                        Opportunità di modello
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            checked={draft.auto_trade_opportunities}
                            onCheckedChange={(c) => setDraft({ ...draft, auto_trade_opportunities: c === true })}
                            aria-label="Trada le opportunità in automatico"
                        />
                        Trada le opportunità in automatico
                    </label>
                    <FieldList fields={OPPS_FIELDS} draft={draft} setDraft={setDraft} />

                    <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold pt-2">
                        Condizioni delle strategie
                    </div>
                    <FieldList fields={STRATEGY_FIELDS} draft={draft} setDraft={setDraft} />

                    <div className="text-[11px] uppercase tracking-wide text-secondary font-heading font-bold pt-2" data-testid="exits-section">
                        Uscite automatiche
                    </div>
                    <p className="text-[11px] text-slate-500">
                        Il servizio chiude da solo le posizioni aperte: a <b>profitto</b> quando la quota ha
                        fatto il suo lavoro, a <b>tempo</b> al minuto di soglia, in <b>perdita</b> dopo un gol
                        contro / set perso (attesa di conferma), su <b>rosso</b> alla favorita; nel tennis
                        incassa al game successivo o esce dopo due game persi / set tornato in parità.
                        Quando la chiusura non si abbina, l'uscita diventa <b>obbligatoria</b> a mercato.
                        Il motivo compare nella tabella trade e nello storico ("Uscita: …").
                    </p>
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            checked={exits.enabled}
                            onCheckedChange={(c) => setExits({ ...exits, enabled: c === true })}
                            aria-label="Uscite automatiche attive"
                        />
                        Uscite automatiche attive
                    </label>
                    {EXIT_NUM_FIELDS.map((f) => (
                        <label key={f.key} className="block">
                            <span className="text-xs text-slate-400">{f.label}</span>
                            <input
                                type="number"
                                step={f.step}
                                aria-label={f.label}
                                value={exits[f.key]}
                                onChange={(e) => setExits({ ...exits, [f.key]: Number(e.target.value) })}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                            />
                            <span className="text-[11px] text-slate-500">{f.hint}</span>
                        </label>
                    ))}
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            checked={exits.red_card_fav_exit}
                            onCheckedChange={(c) => setExits({ ...exits, red_card_fav_exit: c === true })}
                            aria-label="Rosso alla favorita: esci subito"
                        />
                        <span>Rosso alla favorita: esci subito <span className="text-[11px] text-slate-500">(la quota si muove contro prima del gol)</span></span>
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            checked={exits.tennis_take_profit_next_game}
                            onCheckedChange={(c) => setExits({ ...exits, tennis_take_profit_next_game: c === true })}
                            aria-label="Tennis: incassa al game successivo"
                        />
                        <span>Tennis: incassa al game successivo <span className="text-[11px] text-slate-500">(il leader tiene il servizio → profitto bloccato)</span></span>
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            checked={exits.tennis_exit_on_lost_game}
                            onCheckedChange={(c) => setExits({ ...exits, tennis_exit_on_lost_game: c === true })}
                            aria-label="Tennis: esci dopo due game persi o set in parità"
                        />
                        <span>Tennis: esci dopo due game persi o set in parità <span className="text-[11px] text-slate-500">(perdita contenuta prima del ribaltone)</span></span>
                    </label>

                    <div className="flex gap-2 pb-8">
                        <Button
                            className="flex-1"
                            disabled={busy}
                            onClick={() => { void Promise.resolve(onSave(payload())).then(() => setOpen(false)); }}
                        >
                            Salva parametri
                        </Button>
                        <Button variant="ghost" onClick={() => { setDraft(SAFE_BOT_DEFAULTS); setExits(EXITS_DEFAULTS); }}>Default</Button>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    );
}

export default BotParamsSheet;
