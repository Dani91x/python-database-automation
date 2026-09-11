// ============================================================================
// realClient.ts — CLIENT SUPABASE REALE per la certificazione.
//
// Le tre pagine (/omega, /safe-strategy, /mike) richiedono il login OWNER nel
// browser: per certificarle sui dati VERI si monta il componente in jsdom e si
// sostituisce `@/integrations/supabase/client` con un client creato dalla
// SERVICE ROLE KEY del `.env` nella RADICE del repo (non frontend/.env, che ha
// solo le chiavi VITE_ anon).
//
// `betfair_live_is_owner()` accetta il service role
// (migrations/betfair_live_order_queue.sql:176 → `auth.role() = 'service_role'`),
// quindi tutte le RPC owner-only rispondono come all'utente proprietario.
//
// DUE PROTEZIONI, perché questo client ha i pieni poteri sul DB di produzione:
//   1. `channel()` è uno STUB (on/subscribe/unsubscribe no-op) e `removeChannel`
//      non fa nulla: nessun websocket, nessuna connessione realtime dai test.
//   2. GUARDIA DI SCRITTURA: `rpc()` accetta solo le RPC di LETTURA
//      (`get_*`, `betfair_live_is_owner`); insert/update/upsert/delete su
//      qualsiasi tabella lanciano. Ogni tentativo viene registrato in
//      `writeAttempts` così il test lo trasforma in un finding CRITICAL.
// ============================================================================
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createClient } from '@supabase/supabase-js';

// --------------------------------------------------------------- .env (radice)
function parseEnv(text: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const raw of text.split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith('#') || !line.includes('=')) continue;
        const i = line.indexOf('=');
        const k = line.slice(0, i).trim();
        let v = line.slice(i + 1).trim();
        if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
        out[k] = v;
    }
    return out;
}

/** risale dalle cartelle correnti fino al `.env` che contiene la service role */
function findRootEnv(): { path: string; vars: Record<string, string> } {
    let dir = process.cwd();
    for (let i = 0; i < 6; i += 1) {
        const p = resolve(dir, '.env');
        if (existsSync(p)) {
            const vars = parseEnv(readFileSync(p, 'utf8'));
            if (vars.SUPABASE_URL && vars.SUPABASE_SERVICE_ROLE_KEY) return { path: p, vars };
        }
        const parent = dirname(dir);
        if (parent === dir) break;
        dir = parent;
    }
    throw new Error(
        'CERT: .env con SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY non trovato risalendo da ' + process.cwd(),
    );
}

/** true solo sotto vitest.cert.config.ts: fuori da lì i test si auto-saltano */
export const CERT_RUN = process.env.CERT_RUN === '1';

function loadEnv(): { path: string; vars: Record<string, string> } {
    try {
        return findRootEnv();
    } catch (e) {
        if (CERT_RUN) throw e;
        // `npm test` (config normale): nessun client reale, i test sono skippati
        return { path: '(non caricato)', vars: { SUPABASE_URL: 'http://cert.disabled', SUPABASE_SERVICE_ROLE_KEY: 'disabled' } };
    }
}

const { path: ENV_PATH, vars: ENV } = loadEnv();
export const CERT_ENV_PATH = ENV_PATH;
export const CERT_SUPABASE_URL = ENV.SUPABASE_URL;

// ------------------------------------------------------------- guardia scrittura
/** RPC ammesse: sola lettura. Tutto il resto è una scrittura o un comando. */
const READ_ONLY_RPC = /^(get_[a-z0-9_]+|betfair_live_is_owner|trading_[a-z0-9_]+)$/;
/** tentativi di scrittura intercettati (ognuno è un finding CRITICAL) */
export const writeAttempts: string[] = [];

function blockWrite(what: string): never {
    writeAttempts.push(what);
    throw new Error(`CERT: scrittura BLOCCATA sul DB reale → ${what}`);
}

// ------------------------------------------------------------------ il client
const raw = createClient(ENV.SUPABASE_URL, ENV.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
});

/** canale realtime FINTO: nessun websocket nei test */
function channelStub(topic: string) {
    const stub: Record<string, unknown> = {
        topic,
        state: 'closed',
        on: () => stub,
        subscribe: () => stub,
        unsubscribe: async () => 'ok',
        send: async () => 'ok',
        track: async () => 'ok',
        untrack: async () => 'ok',
        presenceState: () => ({}),
    };
    return stub;
}

const client = raw as unknown as Record<string, unknown> & {
    rpc: (...a: unknown[]) => unknown;
    from: (t: string) => unknown;
};

const realRpc = raw.rpc.bind(raw);
const realFrom = raw.from.bind(raw);

/** wrapper del query builder: le mutazioni non partono nemmeno */
function guardedFrom(table: string) {
    const builder = realFrom(table as never) as unknown as Record<string, unknown>;
    return new Proxy(builder, {
        get(target, prop, recv) {
            if (prop === 'insert' || prop === 'update' || prop === 'upsert' || prop === 'delete') {
                return () => blockWrite(`${String(prop)} su ${table}`);
            }
            const v = Reflect.get(target, prop, recv);
            return typeof v === 'function' ? v.bind(target) : v;
        },
    });
}

client.rpc = (name: unknown, ...rest: unknown[]) => {
    const n = String(name);
    if (!READ_ONLY_RPC.test(n)) blockWrite(`rpc('${n}')`);
    return (realRpc as (...a: unknown[]) => unknown)(name, ...rest);
};
client.from = (table: unknown) => guardedFrom(String(table));
client.channel = (topic: unknown) => channelStub(String(topic));
client.removeChannel = async () => 'ok';
client.removeAllChannels = async () => [];
client.getChannels = () => [];

/** client esportato al posto di `supabase` nei test (vi.mock) */
export const supabase = client as unknown as typeof raw;

/** verifica diretta che il service role sia riconosciuto come OWNER */
export async function assertOwner(): Promise<boolean> {
    const { data, error } = await raw.rpc('betfair_live_is_owner');
    if (error) throw new Error(`betfair_live_is_owner: ${error.message}`);
    return data === true;
}

/** RPC grezza per le sole sonde di forma/migrazione (sempre in lettura) */
export async function probeRpc(name: string, args: Record<string, unknown> = {}): Promise<{
    ok: boolean; data: unknown; error: string | null;
}> {
    const { data, error } = await raw.rpc(name, args as never);
    return { ok: !error, data, error: error ? `${error.code ?? ''} ${error.message}`.trim() : null };
}
