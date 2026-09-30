// ============================================================================
// stopPerdita.ts - P4 (30/09): gli STOP DI PERDITA in testata, ciascuno col
// suo nome, la sua modalita' e il posto dove si modifica.
//
// Ordine dell'utente (30/09, sezione 1): "Stop perdita non modificabile". La
// testata scriveva "Stop perdita -50,00" senza dire di chi: era lo stop di
// SAFE (in paper), non quello del conto. Gli stop sono QUATTRO e diversi:
//   * CONTO  - `betfair_live_settings.daily_loss_limit`, applicato dal runner
//              (`Betfair/stream/daily_stop_worker.py:124-137`) che pubblica lo
//              stato in `betfair_live_risk_state` (`:318-354`): raggiunto, tira
//              il FRENO generale. Oggi `limit_value = null`, `reason = limit_off`.
//   * SAFE   - `risk.daily_loss_stop` (negativo, 0 = spento; `safe_strategy/
//              risk.py:43/:84-88`), dichiarato dal servizio in `stats.risk`.
//   * MIKE   - `daily_loss_stop` (positivo, 0 = spento; `mike/config.py:318`,
//              applicato in `mike/service.py:3916-3917`), stato in `stats.daily_stop`.
//   * OMEGA  - motore v3 (default): `v3_daily_loss_cap` (default 300); motore
//              v2: `daily_loss_cap` (default 0 = spento). `omega_service.py:
//              1847-1849`, `omega_config.py:221/:262/:434`.
// Funzioni PURE; la presentazione e' `StopPerdita.tsx`.
// ============================================================================
import type { LiveRiskState } from '@/lib/liveOrders';
import { normalizeLossStop, type SafeRiskStats } from '@/lib/safeBot';
import { mergeMikeParams } from '@/lib/mike';
import { OMEGA_PARAM_DEFAULTS } from '@/lib/omega';
import type { Modalita } from '../useControlRoom';

// ---------------------------------------------------------------- conto

export interface StopConto {
    /** false = riga `betfair_live_risk_state` mai letta */
    letto: boolean;
    /** soglia di perdita in EUR (positiva); null = stop SPENTO (o non letto) */
    soglia: number | null;
    /** P&L di giornata secondo il runner (regolato + aperto); null = ignoto */
    oggi: number | null;
    scattato: boolean;
    /** `detail.reason` del runner (es. 'limit_off') */
    motivo: string | null;
    /** true = il runner ha stimato il P&L in modo degradato (posizioni illeggibili) */
    degradato: boolean;
    /** eta' dell'ultimo CAMBIO della riga (scritta solo al cambio) */
    etaS: number | null;
}

export function stopDelConto(riga: LiveRiskState | null, nowMs: number): StopConto {
    if (riga == null) {
        return { letto: false, soglia: null, oggi: null, scattato: false, motivo: null, degradato: false, etaS: null };
    }
    const ms = Date.parse(riga.updated_at);
    const soglia = typeof riga.limit_value === 'number' && Number.isFinite(riga.limit_value) && riga.limit_value > 0
        ? riga.limit_value : null;
    const oggi = typeof riga.total === 'number' && Number.isFinite(riga.total) ? riga.total : null;
    return {
        letto: true,
        soglia,
        oggi,
        scattato: riga.stop_fired === true,
        motivo: typeof riga.detail?.reason === 'string' ? riga.detail.reason : null,
        degradato: riga.detail?.degraded === true,
        etaS: Number.isFinite(ms) ? Math.max(0, Math.round((nowMs - ms) / 1000)) : null,
    };
}

// ---------------------------------------------------------------- bot

export type BotConStop = 'safe' | 'mike' | 'omega';

export interface StopBot {
    bot: BotConStop;
    modalita: Modalita | null;
    /** false = il dato non c'e' (servizio non letto / stop non dichiarato) */
    letto: boolean;
    /** soglia di perdita in EUR (positiva); 0 = SPENTO; null = non letto */
    soglia: number | null;
    scattato: boolean;
    /** da dove viene il numero (per il tooltip) */
    fonte: string;
    /** dove si modifica (per il tooltip) */
    dove: string;
}

function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function letti(p: Record<string, unknown> | null | undefined): p is Record<string, unknown> {
    return p != null && Object.keys(p).length > 0;
}

export function stopDeiBot(input: {
    safe: { modalita: Modalita | null; risk: SafeRiskStats | null };
    mike: { modalita: Modalita | null; params: Record<string, unknown> | null; stats: Record<string, unknown> | null };
    omega: { modalita: Modalita | null; params: Record<string, unknown> | null };
}): StopBot[] {
    const out: StopBot[] = [];

    // SAFE: il valore EFFETTIVO dichiarato dal servizio (stats.risk)
    const s = input.safe.risk;
    const sStop = normalizeLossStop(numero(s?.daily_loss_stop));
    out.push({
        bot: 'safe', modalita: input.safe.modalita,
        letto: sStop != null,
        soglia: sStop == null ? null : Math.abs(sStop),
        scattato: s?.loss_stop_active === true,
        fonte: 'dichiarato dal servizio di Safe (stats.risk.daily_loss_stop)',
        dove: 'Comando dei bot, riga Safe: parametri, \u00abStop perdita giornaliera \u20ac\u00bb',
    });

    // MIKE: parametro della riga di control (default del servizio se assente)
    const mp = input.mike.params;
    const mikeLetto = letti(mp);
    const mStop = mikeLetto ? numero(mergeMikeParams(mp).daily_loss_stop) : null;
    out.push({
        bot: 'mike', modalita: input.mike.modalita,
        letto: mStop != null,
        soglia: mStop == null ? null : Math.max(0, mStop),
        scattato: input.mike.stats?.daily_stop === true,
        fonte: mikeLetto && mp.daily_loss_stop == null
            ? 'parametro daily_loss_stop non scritto: valore predefinito del servizio'
            : 'parametro daily_loss_stop di Mike',
        dove: 'Comando dei bot, riga Mike: parametri, gruppo rischio, \u00abStop perdita giornaliera (\u20ac)\u00bb',
    });

    // OMEGA: la stessa scelta del servizio (motore v3 -> v3_daily_loss_cap)
    const op = input.omega.params;
    const omegaLetto = letti(op);
    let oStop: number | null = null;
    let chiave = 'v3_daily_loss_cap';
    if (omegaLetto) {
        const versione = numero(op.strategy_version) ?? OMEGA_PARAM_DEFAULTS.strategy_version;
        if (versione >= 3) {
            oStop = numero(op.v3_daily_loss_cap) ?? OMEGA_PARAM_DEFAULTS.v3_daily_loss_cap;
        } else {
            chiave = 'daily_loss_cap';
            oStop = numero(op.daily_loss_cap) ?? OMEGA_PARAM_DEFAULTS.daily_loss_cap;
        }
    }
    out.push({
        bot: 'omega', modalita: input.omega.modalita,
        letto: oStop != null,
        soglia: oStop == null ? null : Math.max(0, oStop),
        scattato: false,
        fonte: `parametro ${chiave} di Omega (motore ${chiave === 'daily_loss_cap' ? 'v2' : 'v3'})`,
        dove: chiave === 'daily_loss_cap'
            ? 'Comando dei bot, riga Omega: parametri, \u00abStop-loss giornaliero (\u20ac)\u00bb'
            : 'Comando dei bot, riga Omega: parametri, \u00abv3: stop-loss giornaliero (\u20ac)\u00bb',
    });
    return out;
}

/** Il campo del modello di vista (additivo). */
export interface StopPerditaTestata {
    conto: StopConto;
    bot: StopBot[];
}
