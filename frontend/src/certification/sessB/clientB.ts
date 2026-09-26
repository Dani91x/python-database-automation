// clientB.ts — E2E FASE 3 sessione B (26/09): client Supabase VERO in SOLA LETTURA.
// Service role del .env della radice. Guardie:
//  * rpc(): solo funzioni NON volatili (verificate in pg_proc il 26/09: tutte le get_/list_/trading_
//    sono STABLE, piu' run_strategy, run_strategy_rows, backtest_strategy, omega_eventi_chiusi_dall_utente);
//    qualunque altra RPC viene BLOCCATA e registrata.
//  * from(): insert/update/upsert/delete bloccati.
//  * channel(): stub (nessun realtime).
//  * ogni risposta RPC/select viene registrata (evidenza del «valore alla fonte»).
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createClient } from '@supabase/supabase-js';

function parseEnv(text: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const raw of text.split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith('#') || !line.includes('=')) continue;
        const i = line.indexOf('=');
        let v = line.slice(i + 1).trim();
        if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
        out[line.slice(0, i).trim()] = v;
    }
    return out;
}
function findEnv(): Record<string, string> {
    let dir = process.cwd();
    for (let i = 0; i < 7; i += 1) {
        const p = resolve(dir, '.env');
        if (existsSync(p)) {
            const v = parseEnv(readFileSync(p, 'utf8'));
            if (v.SUPABASE_URL && v.SUPABASE_SERVICE_ROLE_KEY) return v;
        }
        const up = dirname(dir);
        if (up === dir) break;
        dir = up;
    }
    throw new Error('.env con service role non trovato');
}
/** true solo sotto vitest.cert.config.ts: fuori da lì nessun client reale e i test si saltano */
export const CERT_RUN = process.env.CERT_RUN === '1';
const ENV = CERT_RUN ? findEnv() : { SUPABASE_URL: 'http://cert.disabled', SUPABASE_SERVICE_ROLE_KEY: 'disabled' };

const READ_RPC = /^(get_[a-z0-9_]+|list_[a-z0-9_]+|trading_[a-z0-9_]+|betfair_live_is_owner|run_strategy|run_strategy_rows|backtest_strategy|omega_eventi_chiusi_dall_utente)$/;
export const blocked: string[] = [];
export const log: { kind: string; name: string; args: unknown; data: unknown; error: string | null }[] = [];

const raw = createClient(ENV.SUPABASE_URL, ENV.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
});

function channelStub(topic: string) {
    const s: Record<string, unknown> = {
        topic, state: 'closed', on: () => s, subscribe: () => s,
        unsubscribe: async () => 'ok', send: async () => 'ok', track: async () => 'ok',
        untrack: async () => 'ok', presenceState: () => ({}),
    };
    return s;
}
function block(what: string): never {
    blocked.push(what);
    throw new Error(`SESS-B: scrittura/comando BLOCCATO -> ${what}`);
}
const WRITE = new Set(['insert', 'update', 'upsert', 'delete']);
function recording<T extends object>(b: T, kind: string, name: string, args: unknown): T {
    return new Proxy(b, {
        get(t, prop, r) {
            if (prop === 'then') {
                return (ok?: (v: unknown) => unknown, ko?: (e: unknown) => unknown) =>
                    (t as unknown as PromiseLike<{ data: unknown; error: { message: string } | null }>).then((res) => {
                        log.push({ kind, name, args, data: res?.data, error: res?.error ? res.error.message : null });
                        return ok ? ok(res) : res;
                    }, ko);
            }
            const v = Reflect.get(t, prop, r);
            if (typeof v !== 'function') return v;
            return (...a: unknown[]) => {
                if (WRITE.has(String(prop))) block(`${String(prop)} su ${name}`);
                const out = (v as (...x: unknown[]) => unknown).apply(t, a);
                const chained = kind === 'from' ? [...(args as unknown[]), [String(prop), a]] : args;
                return out && typeof out === 'object' && 'then' in (out as object)
                    ? recording(out as object, kind, name, chained)
                    : out;
            };
        },
    });
}
const c = raw as unknown as Record<string, unknown>;
const realRpc = raw.rpc.bind(raw) as unknown as (...a: unknown[]) => object;
const realFrom = raw.from.bind(raw) as unknown as (t: string) => object;
c.rpc = (name: unknown, args?: unknown, opts?: unknown) => {
    const n = String(name);
    if (!READ_RPC.test(n)) block(`rpc('${n}')`);
    return recording(realRpc(name, args, opts), 'rpc', n, args ?? null);
};
c.from = (t: unknown) => recording(realFrom(String(t)), 'from', String(t), []);
c.channel = (t: unknown) => channelStub(String(t));
c.removeChannel = async () => 'ok';
c.removeAllChannels = async () => [];
c.getChannels = () => [];
export const supabase = raw;
