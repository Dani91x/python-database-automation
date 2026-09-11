// ============================================================================
// BotParamsSheet.tsx — parametri del BOT Safe Strategy (fonte unica: il DB).
//
// Costruito sul pannello condiviso `ParamsSheetBase` (design system §12): un
// solo bottone "Salva parametri", "Default", indicatore di modifiche non
// salvate e soprattutto CLAMP VISIBILE ("clampato a X (ammesso … )"). I limiti
// non sono inventati: sono gli stessi del servizio
//   · Betfair/safe_strategy/bot_service.py  → resolve_params
//   · Betfair/safe_strategy/risk.py         → merge_risk_params
//   · Betfair/safe_strategy/exits.py        → merge_exit_params
// Cambiare un numero in silenzio su un bot che muove denaro è un bug di soldi
// (audit H-15). Il DB NON viene riallineato sulle chiavi money-critical: la
// verità è `params_effective`, quindi la scheda mostra SEMPRE entrambi i valori
// - "salvato X / in uso Y" - campo per campo, e ripete le correzioni dichiarate
// dall'attività `params_clamped` del servizio.
//
// STRATEGIE ABILITATE (audit H-14): se sul DB `variants` è una lista vuota il
// servizio torna ai default e lo registra come `params_invalid`; la scheda
// mostra le varianti EFFETTIVE e non riattiva nulla in silenzio — salvare senza
// nessuna strategia selezionata viene RIFIUTATO con un avviso esplicito.
//
// `exits` non è noto a `mergeBotParams`: i valori veri si leggono da `rawParams`
// (control.params) e al salvataggio si rimandano insieme al resto, perché
// safe_update_params sostituisce l'intero oggetto.
// ============================================================================
import { useState } from 'react';
import { ParamsSheetBase, type ParamGroup, type ParamValues } from '@/components/trading/ParamsSheetBase';
import { fmtMoney, fmtNum } from '@/lib/format';
import { normalizeLossStop, SAFE_BOT_DEFAULTS, type SafeBotParams, type SafeParamsEffective } from '@/lib/safeBot';
import type { VariantId } from '@/lib/safeStrategy';

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
    // ---- uscite dei trade di MODELLO (modello / anomalia / combo / tennis)
    /** tiene la posizione se P(perdita) è sotto questa soglia (0-1) */
    hold_max_risk: number;
    /** oltre questa P(perdita) chiude comunque (0-1) */
    risk_cap: number;
    /** margine di EV richiesto per tenere invece di chiudere (0-1) */
    ev_margin: number;
    /** residuo non abbinato: attesa fra un tentativo e l'altro (s) */
    residual_retry_s: number;
    /** residuo non abbinato: tentativi massimi */
    residual_max_attempts: number;
    /** modello: uscita in perdita quando P(perdita) supera (0-1) */
    model_exit_p_lose: number;
    /** modello: incassa quando il profitto raggiunge questa frazione del massimo (0-1) */
    model_take_profit_frac: number;
    /** modello: cash out "gratis" sotto questa P(perdita) (0-1) */
    model_free_cashout_p_lose: number;
}

export const EXITS_DEFAULTS: ExitsParams = {
    enabled: true,
    base_exit_minute: 80,
    esatto_exit_minute: 72,
    punta_exit_minute: 83,
    loss_settle_delay_s: 30,
    red_card_fav_exit: true,
    tennis_take_profit_next_game: true,
    tennis_exit_on_lost_game: false,     // = exits.DEFAULT_EXIT_PARAMS del servizio (review M1)
    exit_max_retries: 3,
    hold_max_risk: 0.02,
    risk_cap: 0.10,
    ev_margin: 0.10,
    residual_retry_s: 20,
    residual_max_attempts: 15,
    model_exit_p_lose: 0.10,
    model_take_profit_frac: 0.8,
    model_free_cashout_p_lose: 0.005,
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
        hold_max_risk: n(r.hold_max_risk, EXITS_DEFAULTS.hold_max_risk),
        risk_cap: n(r.risk_cap, EXITS_DEFAULTS.risk_cap),
        ev_margin: n(r.ev_margin, EXITS_DEFAULTS.ev_margin),
        residual_retry_s: n(r.residual_retry_s, EXITS_DEFAULTS.residual_retry_s),
        residual_max_attempts: n(r.residual_max_attempts, EXITS_DEFAULTS.residual_max_attempts),
        model_exit_p_lose: n(r.model_exit_p_lose, EXITS_DEFAULTS.model_exit_p_lose),
        model_take_profit_frac: n(r.model_take_profit_frac, EXITS_DEFAULTS.model_take_profit_frac),
        model_free_cashout_p_lose: n(r.model_free_cashout_p_lose, EXITS_DEFAULTS.model_free_cashout_p_lose),
    };
}

// --------------------------------------------------------------------- spec
interface Num {
    key: string;
    label: string;
    step: number;
    min?: number;
    max?: number;
    hint?: string;
}

/** chiavi del bot (clamp da bot_service.resolve_params) */
const BOT_FIELDS: Num[] = [
    { key: 'poll_interval_s', label: 'Cadenza loop (s)', step: 1, min: 1, hint: 'ogni quanto il servizio valuta i segnali' },
    { key: 'commission_pct', label: 'Commissione %', step: 0.5, min: 0, max: 20, hint: 'aliquota Betfair sul P&L positivo' },
    { key: 'max_open_trades', label: 'Max trade aperti', step: 1, min: 0, hint: '0 = illimitato' },
    { key: 'max_liability_per_trade', label: 'Liability max per trade €', step: 5, min: 0 },
    { key: 'min_size_available_factor', label: 'Fattore size abbinabile', step: 0.5, min: 0, hint: 'richiede abbinabile ≥ fattore × stake' },
    { key: 'min_stake', label: 'Size minima Betfair €', step: 0.5, min: 0, max: 1000, hint: 'sotto questa cifra il servizio usa il metodo 1000→cancella→sposta' },
    { key: 'max_spread_ratio', label: 'Spread massimo (lay/back)', step: 0.1, min: 1, hint: 'oltre questo rapporto il mercato è troppo largo: non si entra' },
    { key: 'place_max_attempts', label: 'Tentativi max di piazzamento', step: 1, min: 1, max: 20 },
    { key: 'paper_fill_ttl_s', label: 'Paper · TTL abbinamento (s)', step: 5, min: 5, max: 600 },
    { key: 'live_fill_deadline_s', label: 'Live · attesa abbinamento (s)', step: 5, min: 5, max: 300 },
    { key: 'stake.laySize', label: 'Stake LAY di default €', step: 0.5, min: 0, hint: 'usato dal motore e proposto sui segnali LAY' },
    { key: 'stake.backSize', label: 'Stake BACK di default €', step: 0.5, min: 0, hint: 'usato dal motore e proposto sui segnali BACK' },
];

const OPPS_FIELDS: Num[] = [
    { key: 'opps_interval_s', label: 'Cadenza opportunità (s)', step: 5, min: 1 },
    { key: 'opps_min_confidence', label: 'Confidenza minima (0-1)', step: 0.05, min: 0, max: 1 },
    { key: 'opps_min_edge', label: 'Edge minimo (0-1)', step: 0.01, min: -1, max: 1 },
];

const RISK_FIELDS: Num[] = [
    { key: 'risk.daily_liability_cap', label: 'Cap liability giornaliera €', step: 50, min: 0, hint: 'raggiunto il cap nessun nuovo ingresso automatico fino a domani (0 = nessun cap)' },
    { key: 'risk.per_event_liability_cap', label: 'Cap liability per evento €', step: 10, min: 0, hint: 'somma delle liability aperte sulla stessa partita' },
    { key: 'risk.per_event_max_trades', label: 'Trade max per evento', step: 1, min: 0, hint: 'mai più di tanti trade sulla stessa partita' },
    { key: 'risk.correlated_cap', label: 'Correlazione max (0-1)', step: 0.05, min: 0, max: 1, hint: 'posizioni sullo stesso esito (es. Under 2.5 + Under 3.5): oltre questa correlazione la seconda non entra' },
    // il servizio legge il VALORE ASSOLUTO: 50 e -50 sono la stessa soglia
    // (-50 EUR), quindi nessun clamp sul segno - si scrive come si preferisce
    { key: 'risk.daily_loss_stop', label: 'Stop perdita giornaliera €', step: 5, hint: 'soglia di PERDITA: sotto questo P&L di giornata il bot smette di entrare. Il segno non conta (50 e −50 sono lo stesso stop); 0 = stop SPENTO' },
    { key: 'risk.model_daily_liability_cap', label: 'Cap liability giornaliera trade di modello €', step: 25, min: 0, hint: 'quota del cap riservata a modello/anomalie/combinazioni/tennis' },
];

const MODEL_STAKE_FIELDS: Num[] = [
    { key: 'risk.model_stake', label: 'Stake auto-trade modello / anomalie / tennis €', step: 0.5, min: 0, hint: 'stake di ogni trade automatico di questi tipi (le combinazioni lo usano come stake TOTALE)' },
    { key: 'opps_stake', label: 'Stake proposto sulle card €', step: 0.5, min: 0, hint: 'precompilato nel campo Stake delle opportunità (manuale)' },
];

const MODEL_EXIT_FIELDS: Num[] = [
    { key: 'exits.hold_max_risk', label: 'Tieni se P(perdita) ≤ (0-1)', step: 0.005, min: 0, max: 1, hint: 'sotto questa probabilità di perdita il servizio TIENE la posizione ("In attesa" in tabella) invece di chiudere' },
    { key: 'exits.risk_cap', label: 'Chiudi comunque se P(perdita) ≥ (0-1)', step: 0.01, min: 0, max: 1, hint: 'oltre questa soglia si chiude a mercato anche con EV a favore' },
    { key: 'exits.ev_margin', label: 'Margine EV per tenere (€)', step: 0.01, min: 0, hint: 'tenere deve valere almeno questo margine rispetto al cash out immediato' },
    { key: 'exits.model_exit_p_lose', label: 'Modello · esci in perdita da P(perdita) (0-1)', step: 0.01, min: 0, max: 1, hint: 'il modello ricalcola P(perdita) a ogni ciclo: sopra questa soglia esce in perdita controllata' },
    { key: 'exits.model_take_profit_frac', label: 'Modello · incassa a frazione del max (0-1)', step: 0.05, min: 0, max: 1, hint: '0,8 = chiude quando ha in mano l’80 % del profitto massimo possibile' },
    { key: 'exits.model_free_cashout_p_lose', label: 'Modello · cash out gratis sotto P(perdita) (0-1)', step: 0.001, min: 0, max: 1, hint: 'rischio ormai trascurabile: incassa e libera la liability' },
    { key: 'exits.residual_retry_s', label: 'Residuo · attesa fra tentativi (s)', step: 5, min: 2, max: 600, hint: 'chiusura parziale (liquidità): riprova a chiudere il resto ogni tot secondi' },
    { key: 'exits.residual_max_attempts', label: 'Residuo · tentativi max', step: 1, min: 0, max: 100, hint: 'dopo questi tentativi il residuo si chiude al prezzo disponibile' },
];

const EXIT_NUM_FIELDS: Num[] = [
    { key: 'exits.base_exit_minute', label: 'BASE · uscita a tempo dal minuto', step: 1, min: 1, max: 120, hint: 'chiude a mercato (green/red) se il match arriva a questo minuto con la posizione ancora aperta' },
    { key: 'exits.esatto_exit_minute', label: 'R. ESATTO · uscita a tempo dal minuto', step: 1, min: 1, max: 120, hint: 'lay sul risultato esatto: incassa il calo della quota prima del finale' },
    { key: 'exits.punta_exit_minute', label: 'PUNTA · uscita a tempo dal minuto', step: 1, min: 1, max: 120, hint: 'back a quota bassissima: esce prima che una rimonta annulli il profitto' },
    { key: 'exits.loss_settle_delay_s', label: 'Perdita · attesa prima di chiudere (s)', step: 5, min: 0, max: 600, hint: 'gol contro / set perso: aspetta che il punteggio sia confermato (VAR, correzioni) e poi chiude in perdita' },
    { key: 'exits.exit_max_retries', label: 'Tentativi max di chiusura', step: 1, min: 1, max: 20, hint: "chiusure non abbinate: dopo questi tentativi l'uscita diventa OBBLIGATORIA al prezzo disponibile" },
];

const STRATEGY_FIELDS: Num[] = [
    { key: 'base.minuteMin', label: 'BASE · dal minuto', step: 1, min: 0, max: 120 },
    { key: 'base.favLiveMin', label: 'BASE · quota live favorita MIN', step: 0.01, min: 1 },
    { key: 'base.favLiveMax', label: 'BASE · quota live favorita MAX', step: 0.01, min: 1 },
    { key: 'base.scoreConfirmSec', label: 'BASE · punteggio stabile (s)', step: 5, min: 0 },
    { key: 'esatto.minuteMin', label: 'R. ESATTO · dal minuto', step: 1, min: 0, max: 120 },
    { key: 'esatto.entryMin', label: 'R. ESATTO · quota MIN', step: 1, min: 1 },
    { key: 'esatto.entryMax', label: 'R. ESATTO · quota MAX', step: 1, min: 1 },
    { key: 'esatto.maxGoalsLaySide', label: 'R. ESATTO · gol max lato bancato', step: 1, min: 0 },
    { key: 'esatto.scoreConfirmSec', label: 'R. ESATTO · punteggio stabile (s)', step: 5, min: 0 },
    { key: 'punta.minuteMin', label: 'PUNTA · dal minuto', step: 1, min: 0, max: 120 },
    { key: 'punta.entryMin', label: 'PUNTA · quota MIN', step: 0.01, min: 1 },
    { key: 'punta.entryMax', label: 'PUNTA · quota MAX', step: 0.01, min: 1 },
    { key: 'punta.minMinutesAfterGoal', label: 'PUNTA · minuti dopo il gol', step: 1, min: 0 },
    { key: 'tennis.setsLeadMin', label: 'TENNIS · set di vantaggio', step: 1, min: 0 },
    { key: 'tennis.gamesLeadMin', label: 'TENNIS · game di vantaggio', step: 1, min: 0 },
    { key: 'tennis.backMin', label: 'TENNIS · quota leader MIN', step: 0.01, min: 1 },
    { key: 'tennis.backMax', label: 'TENNIS · quota leader MAX', step: 0.01, min: 1 },
    { key: 'tennis.scoreConfirmSec', label: 'TENNIS · punteggio stabile (s)', step: 5, min: 0 },
];

const AUTO_TRADE_TOGGLES: { key: string; label: string; note: string }[] = [
    { key: 'auto_trade_opportunities', label: 'Trada le opportunità di MODELLO in automatico', note: 'rischio: il modello può essere calibrato male sulle leghe minori — stake piccolo, cap giornaliero attivo' },
    { key: 'auto_trade_anomalies', label: 'Trada le ANOMALIE di prezzo in automatico', note: 'rischio: una quota "sbagliata" può essere un punteggio in ritardo sul feed — attesa conferma consigliata' },
    { key: 'auto_trade_combos', label: 'Trada le COMBINAZIONI in automatico', note: 'rischio: se una gamba non si abbina il profitto bloccato salta e resta una posizione scoperta' },
    { key: 'auto_trade_tennis', label: 'Trada le opportunità TENNIS in automatico', note: 'rischio: ritiri e cali di momentum improvvisi — il rischio ritiro è mostrato sulla card' },
];

const VARIANTS: { id: VariantId; label: string }[] = [
    { id: 'base', label: 'Base' },
    { id: 'esatto', label: 'Risultato Esatto' },
    { id: 'punta', label: 'Punta' },
    { id: 'tennis', label: 'Tennis' },
];
const VARIANT_KEY = (id: VariantId) => `variants.${id}`;

// ----------------------------------------------------------------- helpers
function getPath(obj: Record<string, unknown>, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, k) => (acc as Record<string, unknown> | undefined)?.[k], obj);
}

function setPath(target: Record<string, unknown>, path: string, value: unknown): void {
    const keys = path.split('.');
    let node = target;
    for (let i = 0; i < keys.length - 1; i++) {
        const k = keys[i];
        const cur = node[k];
        node[k] = (cur && typeof cur === 'object' ? { ...(cur as object) } : {}) as Record<string, unknown>;
        node = node[k] as Record<string, unknown>;
    }
    node[keys[keys.length - 1]] = value;
}

/** Valore EFFETTIVO (in uso dal servizio) di un campo, se pubblicato. */
function effectiveOf(eff: SafeParamsEffective | null | undefined, key: string): number | null {
    if (!eff) return null;
    const v = getPath(eff as unknown as Record<string, unknown>, key);
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

const numShown = (v: number) => fmtNum(v, Number.isInteger(v) ? 0 : 3);

/**
 * H-15: il valore SALVATO e quello IN USO vanno mostrati entrambi. Il servizio
 * non riallinea il DB, quindi la divergenza non è un errore transitorio: è lo
 * stato normale e va letto (con la correzione dichiarata dall'attività
 * `params_clamped`, quando c'è).
 */
function hintWithEffective(
    f: Num,
    stored: unknown,
    eff: SafeParamsEffective | null | undefined,
    corrections?: ParamCorrections | null,
) {
    const e = effectiveOf(eff, f.key);
    const s = typeof stored === 'number' ? stored : Number(stored);
    const corr = corrections?.[f.key] ?? null;
    const diff = e != null && Number.isFinite(s) && Math.abs(e - s) > 1e-9;
    if (!diff && !corr) return f.hint;
    const effShown = e != null ? numShown(e)
        : corr?.effective != null ? String(corr.effective) : '?';
    const storedShown = Number.isFinite(s) ? numShown(s)
        : corr?.stored != null ? String(corr.stored) : '?';
    return (
        <>
            {f.hint}
            {f.hint ? ' ' : ''}
            <b className="text-amber-300" data-testid="params-effective" data-field={f.key}>
                salvato {storedShown} · il servizio usa {effShown}
                {corr ? ' (correzione dichiarata dal servizio)' : ' (valore clampato/normalizzato)'}
            </b>
        </>
    );
}

function numFields(
    fields: Num[], values: ParamValues, eff: SafeParamsEffective | null | undefined,
    corrections?: ParamCorrections | null,
) {
    return fields.map((f) => ({
        key: f.key,
        label: f.label,
        type: 'number' as const,
        min: f.min,
        max: f.max,
        step: f.step,
        hint: hintWithEffective(f, values[f.key], eff, corrections),
    }));
}

/** {chiave: {stored, effective}} - payload di `params_clamped` del servizio */
export type ParamCorrections = Record<string, { stored?: unknown; effective?: unknown }>;

export interface BotParamsSheetProps {
    params: SafeBotParams;
    /** control.params grezzi dal DB: sorgente di `exits` e di ogni chiave che
     *  mergeBotParams non conosce (vanno preservate al salvataggio) */
    rawParams?: Record<string, unknown> | null;
    /** parametri REALMENTE in uso dal servizio (control.stats.params_effective) */
    effective?: SafeParamsEffective | null;
    /** correzioni dichiarate dall'attività `params_clamped` del servizio */
    corrections?: ParamCorrections | null;
    /** chiavi che il servizio ha corretto DAVVERO sul DB (`params_invalid.persisted`) */
    persisted?: string[] | null;
    busy?: boolean;
    onSave: (p: Partial<SafeBotParams>) => Promise<void> | void;
}

export function BotParamsSheet({
    params, rawParams = null, effective = null, corrections = null, persisted = null,
    busy = false, onSave,
}: BotParamsSheetProps) {
    const [refused, setRefused] = useState<string | null>(null);

    const exits = mergeExits(rawParams?.exits);
    const flat = toValues(params, exits, rawParams);
    const effVariants = effective?.variants;
    // H-14: la scheda mostra le varianti EFFETTIVE; se sul DB sono vuote/ignote
    // il servizio ha già ripiegato sui default e lo dichiara — non si riattiva
    // nulla in silenzio.
    const storedVariants = Array.isArray(rawParams?.variants) ? (rawParams?.variants as unknown[]) : null;
    const variantsMissing = storedVariants != null
        && storedVariants.filter((v) => VARIANTS.some((x) => x.id === v)).length === 0;
    const variantsDiffer = Array.isArray(effVariants)
        && JSON.stringify([...effVariants].sort()) !== JSON.stringify([...params.variants].sort());

    // il segno dello stop non conta per il servizio: si mostra quello vero
    const lossStopShown = normalizeLossStop(
        ((effective?.risk as Record<string, unknown> | null | undefined)?.daily_loss_stop as number | undefined)
        ?? params.risk.daily_loss_stop,
    );

    const groups: ParamGroup[] = [
        {
            label: 'Bot',
            note: 'Limiti applicati dal servizio: i valori fuori range vengono clampati e dichiarati qui sotto.',
            fields: numFields(BOT_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Strategie abilitate',
            note: (
                <>
                    Le strategie che il bot trada in automatico. <b>Almeno una</b> deve essere attiva:
                    una lista vuota sul DB fa ripiegare il servizio sui default e viene registrata
                    come <code>params_invalid</code>.
                    {variantsMissing && (
                        <b className="block text-red-300" data-testid="variants-invalid">
                            ⚠ Sul database non c'è nessuna strategia valida: il servizio sta girando con
                            quelle di fabbrica ({(effVariants ?? params.variants).join(', ')}). Scegli
                            esplicitamente quali vuoi e salva.
                        </b>
                    )}
                    {!variantsMissing && variantsDiffer && (
                        <b className="block text-amber-300" data-testid="variants-differ">
                            ⚠ Il servizio sta tradando {(effVariants ?? []).join(', ') || 'nessuna strategia'},
                            diverso da quanto salvato: salva per allineare.
                        </b>
                    )}
                </>
            ),
            fields: VARIANTS.map((v) => ({
                key: VARIANT_KEY(v.id),
                label: v.label,
                type: 'boolean' as const,
            })),
        },
        {
            label: 'Rischio',
            note: (
                <>
                    Limiti del servizio su TUTTI i trade automatici. Lo stato corrente (capitale
                    impegnato, stop perdita) è nel pannello <b>Rischio giornaliero</b> in alto.
                    {lossStopShown != null && (
                        <b className="block text-slate-300" data-testid="params-loss-stop">
                            stop in uso: {fmtMoney(lossStopShown)}
                        </b>
                    )}
                </>
            ),
            fields: numFields(RISK_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Auto-trade',
            note: 'Ogni tipo di opportunità si accende da solo. Spento = le card restano manuali («Piazza»). Ogni riga dice qual è il suo rischio specifico.',
            fields: AUTO_TRADE_TOGGLES.map((t) => ({
                key: t.key,
                label: t.label,
                type: 'boolean' as const,
                hint: t.note,
            })),
        },
        {
            label: 'Opportunità di modello',
            fields: numFields(OPPS_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Tennis / Anomalie',
            note: 'Stake dei trade di modello, anomalia, combinazione e tennis. Tennis e anomalie entrano con lo stesso stake del modello; la liability giornaliera dedicata è nel blocco Rischio.',
            fields: numFields(MODEL_STAKE_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Uscite modello',
            note: (
                <>
                    Per i trade di modello/anomalia/combinazione/tennis il servizio ricalcola a ogni
                    ciclo la <b>P(perdita)</b>: se è bassa e l'EV del tenere supera il margine, la
                    posizione resta aperta («In attesa» in tabella); altrimenti chiude. Un residuo
                    non abbinato viene ritentato a intervalli.
                </>
            ),
            fields: numFields(MODEL_EXIT_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Condizioni delle strategie',
            note: 'Il minuto delle strategie calcio è una SOGLIA: "dal minuto X in poi".',
            fields: numFields(STRATEGY_FIELDS, flat, effective, corrections),
        },
        {
            label: 'Uscite automatiche',
            note: (
                <>
                    Il servizio chiude da solo le posizioni aperte: a <b>profitto</b> quando la quota ha
                    fatto il suo lavoro, a <b>tempo</b> al minuto di soglia, in <b>perdita</b> dopo un gol
                    contro / set perso (attesa di conferma), su <b>rosso</b> alla favorita; nel tennis
                    incassa al game successivo o esce dopo due game persi / set tornato in parità.
                    Quando la chiusura non si abbina, l'uscita diventa <b>obbligatoria</b> a mercato.
                    Il motivo compare nella tabella trade e nello storico («Uscita: …»).
                </>
            ),
            fields: [
                { key: 'exits.enabled', label: 'Uscite automatiche attive', type: 'boolean' as const },
                ...numFields(EXIT_NUM_FIELDS, flat, effective, corrections),
                { key: 'exits.red_card_fav_exit', label: 'Rosso alla favorita: esci subito', type: 'boolean' as const, hint: 'la quota si muove contro prima del gol' },
                { key: 'exits.tennis_take_profit_next_game', label: 'Tennis: incassa al game successivo', type: 'boolean' as const, hint: 'il leader tiene il servizio → profitto bloccato' },
                { key: 'exits.tennis_exit_on_lost_game', label: 'Tennis: esci dopo due game persi o set in parità', type: 'boolean' as const, hint: 'perdita contenuta prima del ribaltone' },
            ],
        },
    ];

    async function save(v: ParamValues) {
        const variants = VARIANTS.filter((x) => v[VARIANT_KEY(x.id)] === true).map((x) => x.id);
        if (variants.length === 0) {
            // H-14: mai riattivare le strategie in silenzio, ma mai nemmeno
            // salvare una lista vuota (il servizio ripiegherebbe sui default)
            setRefused('Nessuna strategia selezionata: scegline almeno una. Salvare una lista vuota farebbe girare il servizio con le strategie di fabbrica senza dirlo.');
            return;
        }
        setRefused(null);
        await onSave(fromValues(v, variants, rawParams));
    }

    return (
        <ParamsSheetBase
            title="Parametri bot Safe Strategy"
            symbol={<span aria-hidden>🛡️</span>}
            description="Salvati sul database (safe_update_params): valgono per il servizio e per questa schermata. I limiti mostrati sono quelli applicati dal servizio."
            groups={groups}
            values={flat}
            busy={busy}
            onSave={save}
            onReset={() => toValues(SAFE_BOT_DEFAULTS, EXITS_DEFAULTS, null)}
            footer={
                <>
                    {refused && (
                        <p className="text-red-300" data-testid="params-refused">⚠ {refused}</p>
                    )}
                    {effective == null ? (
                        // Senza `control.stats.params_effective` (servizio mai avviato
                        // o migrazione safe_strategy_bot_v2.sql assente) NON si sa cosa
                        // stia usando il servizio: mostrare i valori locali come
                        // "in uso" era una bugia (il servizio clampa in memoria).
                        <p className="text-amber-300" data-testid="params-effective-missing">
                            ⚠ valori in uso non disponibili: servizio mai avviato o
                            migrazione assente (applica safe_strategy_bot_v2.sql). Qui sotto
                            ci sono i valori SALVATI, non quelli con cui il bot gira.
                        </p>
                    ) : (
                        <p>
                            Strategie in uso dal servizio:{' '}
                            <b data-testid="params-variants-effective">
                                {(effVariants ?? params.variants).join(', ') || 'nessuna'}
                            </b>
                        </p>
                    )}
                    {persisted && persisted.length > 0 && (
                        <p className="text-amber-300" data-testid="params-persisted">
                            chiavi corrette dal servizio SUL DATABASE: <b>{persisted.join(', ')}</b>
                        </p>
                    )}
                    <p className="text-slate-500">
                        Il database NON viene riallineato sugli altri parametri: dove il valore
                        salvato e quello in uso differiscono, vale sempre quello in uso.
                    </p>
                </>
            }
        />
    );
}

/** parametri + exits → valori piatti del pannello (chiavi con il punto) */
export function toValues(
    p: SafeBotParams, exits: ExitsParams, raw: Record<string, unknown> | null,
): ParamValues {
    const src = { ...(raw ?? {}), ...(p as unknown as Record<string, unknown>) };
    const out: ParamValues = {};
    const num = (key: string, fallback = 0) => {
        const v = getPath(src, key);
        const n = Number(v);
        out[key] = Number.isFinite(n) ? n : fallback;
    };
    for (const f of [...BOT_FIELDS, ...OPPS_FIELDS, ...RISK_FIELDS, ...MODEL_STAKE_FIELDS, ...STRATEGY_FIELDS]) {
        num(f.key);
    }
    // min_stake / max_spread_ratio / place_max_attempts / TTL non sono in
    // SafeBotParams: vengono dai params grezzi, con i default del servizio
    const svcDefaults: Record<string, number> = {
        min_stake: 2, max_spread_ratio: 1.6, place_max_attempts: 3,
        paper_fill_ttl_s: 45, live_fill_deadline_s: 20,
    };
    for (const [k, d] of Object.entries(svcDefaults)) {
        const v = Number(getPath(src, k));
        out[k] = k in src && Number.isFinite(v) ? v : d;
    }
    for (const t of AUTO_TRADE_TOGGLES) out[t.key] = Boolean(getPath(src, t.key));
    for (const v of VARIANTS) out[VARIANT_KEY(v.id)] = p.variants.includes(v.id);
    for (const [k, v] of Object.entries(exits)) out[`exits.${k}`] = v as number | boolean;
    return out;
}

/** valori piatti del pannello → payload per safe_update_params */
export function fromValues(
    v: ParamValues, variants: VariantId[], raw: Record<string, unknown> | null,
): Partial<SafeBotParams> {
    // chiavi ignote del servizio preservate: safe_update_params SOSTITUISCE
    // l'intero oggetto, un salvataggio parziale le cancellerebbe
    const out: Record<string, unknown> = { ...(raw ?? {}) };
    for (const [key, value] of Object.entries(v)) {
        if (key.startsWith('variants.')) continue;
        setPath(out, key, value);
    }
    out.variants = variants;
    return out as Partial<SafeBotParams>;
}

export default BotParamsSheet;
