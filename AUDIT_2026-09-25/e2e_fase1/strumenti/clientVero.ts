// ============================================================================
// clientVero.ts — E2E FASE 1 (25/09): il client Supabase VERO al posto di
// `@/integrations/supabase/client`, per far girare i componenti e le funzioni
// della UI contro il DB di produzione con l'app SPENTA.
//
// Chiave: SERVICE ROLE del `.env` della radice (la UI servita da vite preview
// richiederebbe il login del proprietario, che questo delegato non ha).
// `betfair_live_is_owner()` / `tennis_is_owner()` accettano il service role
// (migrations/betfair_live_order_queue.sql:176-190, tennis_orders.sql:30-40):
// le RPC owner-only rispondono come al proprietario. Differenza dichiarata:
// `auth.jwt()->>'email'` e' vuoto, quindi `order_mode_updated_by` NON sara'
// l'email del proprietario.
//
// GUARDIE (il client ha pieni poteri sul DB vero):
//   * rpc(): SOLO le RPC del piano (elenco esplicito) + letture `get_*`;
//     qualunque altra RPC lancia e viene registrata (reperto).
//   * from(): SOLO select; insert/update/upsert/delete lanciano (la UI non
//     deve scrivere tabelle direttamente: sarebbe un reperto).
//   * channel(): stub, nessun websocket realtime.
// Ogni chiamata RPC e' registrata con i suoi argomenti (`chiamate`).
// ============================================================================
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createClient } from '@supabase/supabase-js';

const ENV_PATH = resolve(__dirname, '../../../../../.env');
function parseEnv(p: string): Record<string, string> {
    if (!existsSync(p)) throw new Error(`E2E: .env non trovato: ${p}`);
    const out: Record<string, string> = {};
    for (const raw of readFileSync(p, 'utf8').split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith('#') || !line.includes('=')) continue;
        const i = line.indexOf('=');
        let v = line.slice(i + 1).trim();
        if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
        out[line.slice(0, i).trim()] = v;
    }
    return out;
}
const ENV = parseEnv(ENV_PATH);
export const E2E_ENV_PATH = ENV_PATH;

/** client SENZA guardie: solo per le letture di verifica del test */
export const raw = createClient(ENV.SUPABASE_URL, ENV.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
});

/** le RPC di comando che il piano E2E fa chiamare alla UI */
export const RPC_DEL_PIANO = new Set([
    'omega_activate', 'omega_update_params', 'omega_stop',
    'mike_activate', 'mike_update_params', 'mike_stop', 'mike_request',
    'safe_activate', 'safe_update_params', 'safe_stop', 'safe_request', 'safe_request_approve',
    'tennis_bot_service_activate', 'tennis_bot_service_update_params', 'tennis_bot_service_stop',
    'tennis_bot_service_set_uscite', 'tennis_bot_arm', 'tennis_bot_disarm', 'request_tennis_live_order',
    'scalper_auto_activate', 'scalper_auto_stop', 'scalper_auto_update', 'scalper_uscite_automatiche',
    'scalper_activate',
    'set_live_order_mode', 'set_live_kill_switch',
    'omega_request_approve',
]);
const LETTURA = /^(get_[a-z0-9_]+|betfair_live_is_owner|trading_[a-z0-9_]+)$/;

export const chiamate: { rpc: string; args: unknown; esito: 'ok' | 'errore'; errore?: string; ms: number }[] = [];
export const bloccate: string[] = [];

function channelStub(topic: string) {
    const stub: Record<string, unknown> = {
        topic, state: 'closed',
        on: () => stub, subscribe: () => stub,
        unsubscribe: async () => 'ok', send: async () => 'ok',
        track: async () => 'ok', untrack: async () => 'ok', presenceState: () => ({}),
    };
    return stub;
}

const client = createClient(ENV.SUPABASE_URL, ENV.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
}) as unknown as Record<string, unknown> & { rpc: (...a: unknown[]) => unknown; from: (t: string) => unknown };
const realRpc = (client.rpc as (...a: unknown[]) => unknown).bind(client);
const realFrom = (client.from as (t: string) => unknown).bind(client);

client.rpc = (name: unknown, args?: unknown, ...rest: unknown[]) => {
    const n = String(name);
    if (!RPC_DEL_PIANO.has(n) && !LETTURA.test(n)) {
        bloccate.push(`rpc('${n}')`);
        throw new Error(`E2E: RPC fuori dal piano BLOCCATA: ${n}`);
    }
    const t0 = Date.now();
    const p = realRpc(name, args, ...rest) as PromiseLike<{ error: { message: string } | null }>;
    // registra l'esito senza cambiare il builder restituito
    return {
        then(res: (v: unknown) => unknown, rej?: (e: unknown) => unknown) {
            return Promise.resolve(p).then((v) => {
                if (!LETTURA.test(n)) {
                    chiamate.push({
                        rpc: n, args, esito: v?.error ? 'errore' : 'ok',
                        ...(v?.error ? { errore: v.error.message } : {}), ms: Date.now() - t0,
                    });
                }
                return v;
            }).then(res, rej);
        },
    };
};
client.from = (table: unknown) => {
    const b = realFrom(String(table)) as Record<string, unknown>;
    return new Proxy(b, {
        get(target, prop, recv) {
            if (prop === 'insert' || prop === 'update' || prop === 'upsert' || prop === 'delete') {
                return () => {
                    bloccate.push(`${String(prop)} su ${String(table)}`);
                    throw new Error(`E2E: scrittura diretta BLOCCATA: ${String(prop)} su ${String(table)}`);
                };
            }
            const v = Reflect.get(target, prop, recv);
            return typeof v === 'function' ? v.bind(target) : v;
        },
    });
};
client.channel = (topic: unknown) => channelStub(String(topic));
client.removeChannel = async () => 'ok';
client.removeAllChannels = async () => [];
client.getChannels = () => [];

export const supabase = client as unknown as typeof raw;
