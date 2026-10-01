// ============================================================================
// supabaseFinto — client Supabase FINTO e DETERMINISTICO per la «fotografia».
//
// La fotografia (fotografia.test.tsx) rende OGNI pagina vera dentro <App/> e
// registra cosa c'e' a schermo. Per essere una prova deve dare lo stesso
// risultato a ogni giro, su ogni macchina, senza rete: qui c'e' un finto con la
// STESSA FORMA del client vero di supabase-js 2 (stesse chiavi e tipi delle
// risposte: `{ data, error, count, status, statusText }`), che risponde subito
// e sempre allo stesso modo:
//   - `rpc(...)`                 -> data null   (nessuna riga dal backend)
//   - `from(t).select()...`      -> data []     (tabella vuota)
//   - `.single() / .maybeSingle()` -> data null
//   - `channel(...).on().subscribe()` -> canale che non emette mai nulla
//   - `auth.getSession()`        -> la sessione dell'owner, o nessuna sessione
// Nessuna lettura in piu' rispetto alle pagine: il finto risponde solo a quello
// che le pagine chiedono gia'. Le richieste vengono contate (nome e tipo) per
// poter confrontare guscio acceso e spento.
// ============================================================================
import { OWNER_EMAIL } from '@/lib/auth-config';

export interface RispostaFinta {
    data: unknown;
    error: null;
    count: number | null;
    status: number;
    statusText: string;
}

export interface RegistroChiamate {
    rpc: string[];
    from: string[];
    channel: number;
}

// Stato su globalThis: `vi.resetModules()` crea istanze nuove di questo modulo,
// mentre il mock del client puo' restare legato alla prima. Registro e sessione
// devono essere UNO solo, chiunque li importi.
interface StatoFinto {
    registro: RegistroChiamate;
    conSessione: boolean;
}
const G = globalThis as unknown as { __supabaseFintoFotografia?: StatoFinto };
G.__supabaseFintoFotografia ??= { registro: { rpc: [], from: [], channel: 0 }, conSessione: true };
const STATO: StatoFinto = G.__supabaseFintoFotografia;

export const registro: RegistroChiamate = STATO.registro;

export function azzeraRegistro(): void {
    registro.rpc = [];
    registro.from = [];
    registro.channel = 0;
}

/** sessione dell'owner (true) o nessuna sessione (false) */
export function impostaSessione(conSessione: boolean): void {
    STATO.conSessione = conSessione;
}

function sessioneFinta() {
    if (!STATO.conSessione) return null;
    return {
        access_token: 'finto',
        refresh_token: 'finto',
        token_type: 'bearer',
        expires_in: 3600,
        expires_at: 4102444800,
        user: {
            id: '00000000-0000-0000-0000-00000000f070',
            email: OWNER_EMAIL,
            aud: 'authenticated',
            role: 'authenticated',
            app_metadata: {},
            user_metadata: {},
            created_at: '2026-01-01T00:00:00.000Z',
        },
    };
}

function risposta(data: unknown): RispostaFinta {
    return { data, error: null, count: null, status: 200, statusText: 'OK' };
}

type Catena = { [k: string]: unknown };

/** costruttore di query: ogni metodo restituisce la catena, `await` da' la risposta */
function catena(dataDiDefault: unknown): Catena {
    let singola = false;
    const proxy: Catena = new Proxy({} as Catena, {
        get(_t, prop) {
            if (prop === 'then') {
                return (ok: (r: RispostaFinta) => unknown, ko?: (e: unknown) => unknown) =>
                    Promise.resolve(risposta(singola ? null : dataDiDefault)).then(ok, ko);
            }
            if (prop === 'catch' || prop === 'finally') {
                return (f: (x: unknown) => unknown) => Promise.resolve(risposta(singola ? null : dataDiDefault))[prop as 'catch'](f);
            }
            if (prop === 'single' || prop === 'maybeSingle') {
                return () => { singola = true; return proxy; };
            }
            if (typeof prop === 'symbol') return undefined;
            return () => proxy;
        },
    });
    return proxy;
}

function canaleFinto(): Catena {
    const c: Catena = {};
    c.on = () => c;
    c.subscribe = (cb?: (s: string) => void) => { void cb; return c; };
    c.unsubscribe = () => Promise.resolve('ok');
    c.send = () => Promise.resolve('ok');
    c.track = () => Promise.resolve('ok');
    c.untrack = () => Promise.resolve('ok');
    c.presenceState = () => ({});
    return c;
}

export const supabaseFinto = {
    rpc(nome: string): Catena {
        registro.rpc.push(nome);
        return catena(null);
    },
    from(tabella: string): Catena {
        registro.from.push(tabella);
        return catena([]);
    },
    channel(): Catena {
        registro.channel += 1;
        return canaleFinto();
    },
    removeChannel(): Promise<'ok'> {
        return Promise.resolve('ok');
    },
    removeAllChannels(): Promise<'ok'[]> {
        return Promise.resolve([]);
    },
    getChannels(): unknown[] {
        return [];
    },
    auth: {
        getSession() {
            return Promise.resolve({ data: { session: sessioneFinta() }, error: null });
        },
        getUser() {
            const s = sessioneFinta();
            return Promise.resolve({ data: { user: s ? s.user : null }, error: null });
        },
        onAuthStateChange() {
            return { data: { subscription: { id: 'finto', callback: () => {}, unsubscribe: () => {} } } };
        },
        signOut() {
            return Promise.resolve({ error: null });
        },
        signInWithPassword() {
            return Promise.resolve({ data: { user: null, session: null }, error: null });
        },
        resetPasswordForEmail() {
            return Promise.resolve({ data: {}, error: null });
        },
        updateUser() {
            return Promise.resolve({ data: { user: null }, error: null });
        },
    },
};
