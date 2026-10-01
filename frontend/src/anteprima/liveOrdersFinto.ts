// ============================================================================
// liveOrdersFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA degli screenshot.
//
// Non e' importato dall'app: il server di anteprima
// (AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs) sostituisce con
// un alias Vite ESATTO l'import '@/lib/liveOrders' con questo file. Qui si
// ri-esporta TUTTO il modulo vero (percorso RELATIVO, che l'alias non tocca) e
// si ridefiniscono solo le letture che vanno in rete, con le STESSE chiavi e
// gli stessi tipi del vero (`LiveSettings`, `LiveAccountRow`, ...).
// Le scritture restano quelle vere: dal client Supabase finto non partono.
//
// Orologio dell'anteprima: 2026-10-01T08:38:00Z (10:38 a Roma).
// ============================================================================
import type {
    LiveSettings, LiveAccountRow, LiveHeartbeatRow, LiveRiskState,
} from '../lib/liveOrders';

export * from '../lib/liveOrders';

const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
const fa = (s: number) => new Date(ORA_MS - s * 1000).toISOString();

/** impostazioni del runner: modo ordini LIVE scelto dalla UI, freno rilasciato */
const IMPOSTAZIONI: LiveSettings = {
    id: 1,
    kill_switch: false,
    max_exposure_per_selection: 60,
    max_orders_per_min: 30,
    order_poll_sec: 1,
    risk_poll_sec: 5,
    daily_loss_limit: 50,
    max_exposure_per_event: 120,
    max_exposure_per_league: null,
    updated_at: fa(3600),
    order_mode: 'live',
    order_mode_updated_at: fa(5400),
    order_mode_updated_by: 'daniele',
    order_mode_boot_id: 'anteprima',
    order_mode_tetto: 'live',
    order_mode_tetto_at: fa(7200),
};

/** saldo del conto: 1.842,37 EUR disponibili, esposizione 96,40 EUR */
const CONTO: LiveAccountRow = {
    id: 1,
    available: 1842.37,
    exposure: -96.4,
    updated_at: fa(3),
};

const BATTITO: LiveHeartbeatRow = {
    id: 1, ts: fa(1), pid: 4242, mode: 'LIVE', watchdog_ts: fa(2), watchdog_pid: 4243, updated_at: fa(1),
};

const RISCHIO: LiveRiskState = {
    id: 1, mode: 'live', day: '2026-10-01', realized: 8.12, open_mtm: 3.02, total: 11.14,
    limit_value: 50, stop_fired: false, detail: { reason: 'sotto_soglia' }, updated_at: fa(4),
};

export async function getLiveSettings(): Promise<LiveSettings | null> {
    return { ...IMPOSTAZIONI };
}

export async function fetchLiveAccount(): Promise<LiveAccountRow | null> {
    return { ...CONTO };
}

export function subscribeLiveAccount(cb: (row: LiveAccountRow | null) => void): () => void {
    // una sola notifica, come il primo push del realtime
    const t = setTimeout(() => cb({ ...CONTO }), 50);
    return () => clearTimeout(t);
}

export async function fetchLiveHeartbeat(): Promise<LiveHeartbeatRow | null> {
    return { ...BATTITO };
}

export function subscribeLiveHeartbeat(cb: (row: LiveHeartbeatRow | null) => void): () => void {
    const t = setTimeout(() => cb({ ...BATTITO }), 50);
    return () => clearTimeout(t);
}

export async function fetchLiveRiskState(): Promise<LiveRiskState | null> {
    return { ...RISCHIO };
}

export function subscribeLiveRiskState(cb: (row: LiveRiskState | null) => void): () => void {
    const t = setTimeout(() => cb({ ...RISCHIO }), 50);
    return () => clearTimeout(t);
}
