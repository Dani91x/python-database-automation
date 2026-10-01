// ============================================================================
// salvaStop.ts - 01/10: lo stop di perdita si modifica DALLA TESTATA.
//
// Ordine dell'utente (01/10): "stop perdita devo poterlo modificare
// direttamente da qui". Nessun punto di salvataggio nuovo: ogni stop si scrive
// con la STESSA funzione e le STESSE chiavi del posto dove si modificava ieri.
//
//   * CONTO -> `setLiveSettings({ daily_loss_limit })` (RPC `set_live_settings`,
//     la stessa di `LiveControlsPanel.handleSave`): la RPC aggiorna SOLO le
//     chiavi passate (`migrations/betfair_live_risk_limits_v4.sql`). Stessa
//     regola del pannello: valore > 0, vuoto = stop SPENTO (null).
//   * SAFE  -> `updateSafeParams(fromValues(...))` (RPC `safe_update_params`),
//     cioe' esattamente il percorso del foglio `BotParamsSheet.save`: si parte
//     da `toValues(mergeBotParams(raw), mergeExits(raw.exits), raw)`, si cambia
//     SOLO `risk.daily_loss_stop` e si ricompone con `fromValues` (chiavi
//     ignote preservate: la RPC SOSTITUISCE l'intero oggetto). Stesso rifiuto
//     del foglio se non c'e' nessuna strategia abilitata. Il servizio legge il
//     valore assoluto (`risk.py:84-88`): si scrive negativo, come il predefinito.
//   * MIKE  -> `updateMikeParams(mergeMikeParams({...mergeMikeParams(raw),
//     daily_loss_stop}))` (RPC `mike_update_params`), il percorso di
//     `MikeParamsSheet` (`onSave(mergeMikeParams(v))`). Positivo, 0 = spento,
//     tetto 100000 (`MIKE_PARAM_FIELDS`).
//   * OMEGA -> `updateOmegaParams({ params: omegaParamsPatch(raw, {chiave}) })`
//     (RPC `omega_update_params`), il percorso di `OmegaParamsSheet.save`:
//     stato del servizio + SOLO la chiave cambiata. La chiave e' quella che il
//     servizio applica (motore v3 -> `v3_daily_loss_cap`, v2 -> `daily_loss_cap`,
//     la stessa scelta di `stopDeiBot`). L'obiettivo NON si manda (la RPC fa
//     `coalesce(p_daily_goal, daily_goal)`): non si tocca.
//
// CANCELLO "parametri non letti" (ControlRoom.tsx `fogliParametri`): con i
// parametri di un bot non letti NON si salva (si sostituirebbero quelli veri
// con i predefiniti). Qui la funzione rifiuta, e il componente disabilita.
//
// La cifra di ritorno e' quella della riga RESTITUITA dal database dopo la
// scrittura, mai quella digitata.
// ============================================================================
import { setLiveSettings, type LiveSettings } from '@/lib/liveOrders';
import { mergeBotParams, updateSafeParams, normalizeLossStop, type SafeControl } from '@/lib/safeBot';
import { mergeMikeParams, updateMikeParams, type MikeControl, type MikeParams } from '@/lib/mike';
import { omegaParamsPatch, updateOmegaParams, OMEGA_PARAM_DEFAULTS, type OmegaControl, type OmegaParams } from '@/lib/omega';
import { toValues, fromValues, mergeExits } from '@/components/safestrategy/BotParamsSheet';
import type { BotConStop } from './stopPerdita';

export type ProprietarioStop = 'conto' | BotConStop;

/** Tetti dei campi dei fogli (gli stessi `max` delle loro spec). */
const TETTO: Record<ProprietarioStop, number> = {
    conto: 1_000_000, safe: 1_000_000, mike: 100_000, omega: 1_000_000,
};

export type LetturaImporto =
    | { ok: true; perdita: number | null }
    | { ok: false; errore: string };

/**
 * Il testo del campo -> perdita massima in euro (POSITIVA, al centesimo).
 * "-50", "-50,5", "50" sono la stessa perdita (il segno meno e' la convenzione
 * a schermo: negativo = perdita massima). `null` = stop SPENTO: per il conto
 * il campo vuoto (regola di `LiveControlsPanel`), per i bot lo 0 (regola dei
 * loro fogli: "0 = OFF").
 */
export function leggiImporto(testo: string, chi: ProprietarioStop): LetturaImporto {
    const t = String(testo ?? '').trim().replace(/\u2212/g, '-').replace(/\s|\u20ac/g, '').replace(',', '.');
    if (t === '') {
        return chi === 'conto'
            ? { ok: true, perdita: null }
            : { ok: false, errore: 'scrivi un importo (0 = stop spento)' };
    }
    if (!/^-?\d+(\.\d{1,2})?$/.test(t)) {
        return { ok: false, errore: 'importo non valido: euro al centesimo, es. \u221250 o \u221250,50' };
    }
    const v = Math.abs(Number(t));
    if (!Number.isFinite(v)) return { ok: false, errore: 'importo non valido' };
    if (v === 0) {
        return chi === 'conto'
            ? { ok: false, errore: 'per il conto 0 non vale: lascia vuoto per spegnere lo stop' }
            : { ok: true, perdita: null };
    }
    if (v > TETTO[chi]) return { ok: false, errore: `oltre il massimo ammesso (${TETTO[chi]})` };
    return { ok: true, perdita: Math.round(v * 100) / 100 };
}

/** La chiave dello stop di Omega che il servizio applica (stessa scelta di `stopDeiBot`). */
export function chiaveStopOmega(raw: Record<string, unknown>): 'v3_daily_loss_cap' | 'daily_loss_cap' {
    const v = typeof raw.strategy_version === 'number' && Number.isFinite(raw.strategy_version)
        ? raw.strategy_version : OMEGA_PARAM_DEFAULTS.strategy_version;
    return v >= 3 ? 'v3_daily_loss_cap' : 'daily_loss_cap';
}

function letti(p: Record<string, unknown> | null | undefined): p is Record<string, unknown> {
    return p != null && Object.keys(p).length > 0;
}

export class StopNonSalvabile extends Error {}

/**
 * Il payload ESATTO che il foglio del proprietario manderebbe cambiando solo
 * lo stop. `perdita` positiva, `null` = spento. Lancia `StopNonSalvabile` se
 * il cancello dei parametri non letti lo vieta.
 */
export function payloadStop(chi: ProprietarioStop, perdita: number | null, raw: Record<string, unknown> | null = null): Record<string, unknown> {
    if (chi === 'conto') return { daily_loss_limit: perdita };
    if (!letti(raw)) throw new StopNonSalvabile(`parametri di ${chi} non letti: salvare ora sostituirebbe quelli veri con i predefiniti`);
    const p = perdita ?? 0;
    if (chi === 'safe') {
        const params = mergeBotParams(raw);
        const v = toValues(params, mergeExits(raw.exits), raw);
        // il servizio legge il valore assoluto; si scrive negativo (come il predefinito -50)
        v['risk.daily_loss_stop'] = normalizeLossStop(p) ?? 0;
        // H-14 del foglio: mai una lista di strategie vuota
        if (params.variants.length === 0) {
            throw new StopNonSalvabile('nessuna strategia abilitata su Safe: il foglio rifiuta di salvare, aprilo e scegline almeno una');
        }
        return fromValues(v, params.variants, raw) as Record<string, unknown>;
    }
    if (chi === 'mike') {
        return mergeMikeParams({ ...mergeMikeParams(raw), daily_loss_stop: p } as Partial<MikeParams>) as unknown as Record<string, unknown>;
    }
    return omegaParamsPatch(raw, { [chiaveStopOmega(raw)]: p });
}

export interface DipendenzeSalvaStop {
    setLiveSettings: typeof setLiveSettings;
    updateSafeParams: typeof updateSafeParams;
    updateMikeParams: typeof updateMikeParams;
    updateOmegaParams: typeof updateOmegaParams;
}

const VERE: DipendenzeSalvaStop = { setLiveSettings, updateSafeParams, updateMikeParams, updateOmegaParams };

function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * Scrive lo stop e ritorna la perdita LETTA dalla riga restituita dal database
 * (positiva; null = spento; undefined = la riga non l'ha restituita).
 */
export async function salvaStop(
    chi: ProprietarioStop, perdita: number | null, raw: Record<string, unknown> | null,
    deps: DipendenzeSalvaStop = VERE,
): Promise<number | null | undefined> {
    if (chi === 'conto') {
        const r: LiveSettings | null = await deps.setLiveSettings({ daily_loss_limit: perdita });
        if (r == null) return undefined;
        const v = numero(r.daily_loss_limit);
        return v == null || v <= 0 ? null : v;
    }
    const payload = payloadStop(chi, perdita, raw);
    if (chi === 'safe') {
        const r: SafeControl = await deps.updateSafeParams(payload);
        const v = numero((r?.params?.risk as Record<string, unknown> | undefined)?.daily_loss_stop);
        return v == null ? undefined : v === 0 ? null : Math.abs(v);
    }
    if (chi === 'mike') {
        const r: MikeControl = await deps.updateMikeParams(payload as unknown as MikeParams);
        const v = numero(r?.params?.daily_loss_stop);
        return v == null ? undefined : v <= 0 ? null : v;
    }
    const r: OmegaControl = await deps.updateOmegaParams({ params: payload as Partial<OmegaParams> });
    const v = numero(r?.params?.[chiaveStopOmega(raw as Record<string, unknown>)]);
    return v == null ? undefined : v <= 0 ? null : v;
}
