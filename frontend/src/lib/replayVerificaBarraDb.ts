// ============================================================================
// replayVerificaBarraDb - la verifica della barra su TUTTE le partite del database,
// in SOLA LETTURA. Lo usa `frontend/scripts/verifica_barra_replay.ts` (lanciabile con
// `npx vite-node`); lo prova `replayVerificaBarraDb.test.ts` con un finto delle RPC
// dalle identiche chiavi e tipi del vero.
//
// Carica le partite ESATTAMENTE come la pagina Match Replay (`lib/live.ts`):
//   list_replays(p_limit)            -> `fetchReplayList`
//   get_replay_meta(p_event_id)      -> estremi (ts_min, ts_max, inplay_from_ts)
//   get_replay_frames(...)           -> `fetchReplayChunked` (finestre da 10 minuti,
//                                       bucket adattivi, stessi parametri della pagina)
// poi passa ogni partita al verificatore (`verificaBarraReplayCalcio`).
//
// SOLA LETTURA GARANTITA DAL CODICE: `blindaSolaLettura` sostituisce `supabase.rpc`
// e `supabase.from` del client: ogni RPC fuori dall'elenco delle tre di lettura e ogni
// accesso diretto a una tabella lanciano un errore PRIMA di uscire dal processo.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import { fetchReplayChunked, fetchReplayList, type ReplayData, type ReplayItem, type ReplayMeta } from '@/lib/live';
import type { EsitoVerificaBarra, EstremiRegistrazione } from '@/lib/replayVerificaBarra';
import { verificaBarraReplayCalcio as verificaCalcio } from '@/lib/replayVerificaBarraCalcio';
import { esitoInUnaRiga, rigaRilievo } from '@/lib/replayVerificaBarraTesto';

/** le sole RPC che questo strumento puo' chiamare (tutte in lettura) */
export const RPC_PERMESSE: ReadonlySet<string> = new Set(['list_replays', 'get_replay_meta', 'get_replay_frames', 'get_replay']);

type ClienteRpc = { rpc: (nome: string, args?: unknown, ...resto: unknown[]) => unknown; from: (...a: unknown[]) => unknown };

/** Rende il client capace SOLO di leggere: RPC fuori elenco e `.from()` lanciano un errore. */
export function blindaSolaLettura(cliente: unknown): void {
    const c = cliente as ClienteRpc;
    const rpcOriginale = c.rpc.bind(cliente);
    c.rpc = (nome: string, args?: unknown, ...resto: unknown[]) => {
        if (!RPC_PERMESSE.has(nome)) throw new Error(`verifica barra: RPC "${nome}" NON permessa (strumento in sola lettura)`);
        return rpcOriginale(nome, args, ...resto);
    };
    c.from = () => { throw new Error('verifica barra: accesso diretto alle tabelle NON permesso (strumento in sola lettura)'); };
}

export interface DatiPartita {
    replay: ReplayData;
    estremi: EstremiRegistrazione;
}

/** Da dove vengono le partite (il database vero, o un finto nei test). */
export interface FontePartite {
    elenco(limite: number): Promise<ReplayItem[]>;
    carica(eventId: string): Promise<DatiPartita>;
}

/** La fonte vera: le STESSE funzioni della pagina (`fetchReplayList`, `fetchReplayChunked`)
 *  piu' `get_replay_meta` per gli estremi dichiarati dal server. */
export const fonteSupabase: FontePartite = {
    elenco: (limite) => fetchReplayList(limite),
    async carica(eventId) {
        const { data, error } = await supabase.rpc('get_replay_meta', { p_event_id: eventId });
        if (error) throw new Error(`get_replay_meta: ${error.message}`);
        const meta = data as ReplayMeta;
        const replay = await fetchReplayChunked(eventId);
        return { replay, estremi: { ts_min: meta.ts_min ?? null, ts_max: meta.ts_max ?? null, inplay_from_ts: meta.inplay_from_ts ?? null } };
    },
};

export interface RisultatoPartita {
    eventId: string;
    titolo: string;
    esito: EsitoVerificaBarra | null;
    /** errore di caricamento o di verifica (la partita NON e' stata verificata) */
    errore: string | null;
    ms: number;
}

export interface OpzioniVerificaPartite {
    /** quante partite chiedere a list_replays (la RPC ne da' al massimo 500) */
    limite?: number;
    /** solo queste partite (event_id); vuoto = tutte quelle dell'elenco */
    eventi?: ReadonlyArray<string>;
    /** chiamata a fine di ogni partita (per stampare i referti man mano) */
    alRisultato?: (r: RisultatoPartita, i: number, totale: number) => void;
    /** il verificatore dello sport (default: calcio). Il tennis passa il suo, che riusa la parte generica. */
    verifica?: (replay: ReplayData, estremi: EstremiRegistrazione) => EsitoVerificaBarra;
}

const titoloDi = (it: ReplayItem): string =>
    `${it.event_id} ${it.home_name} - ${it.away_name} (${String(it.open_date ?? '').slice(0, 10) || 'data ignota'})`;

export async function verificaPartite(fonte: FontePartite, opz: OpzioniVerificaPartite = {}): Promise<RisultatoPartita[]> {
    const limite = opz.limite ?? 500;
    let elenco = await fonte.elenco(limite);
    if (opz.eventi && opz.eventi.length > 0) {
        const voluti = new Set(opz.eventi);
        elenco = elenco.filter(it => voluti.has(String(it.event_id)));
    }
    const out: RisultatoPartita[] = [];
    for (let i = 0; i < elenco.length; i++) {
        const it = elenco[i];
        const t0 = Date.now();
        let r: RisultatoPartita;
        try {
            const { replay, estremi } = await fonte.carica(String(it.event_id));
            r = { eventId: String(it.event_id), titolo: titoloDi(it), esito: (opz.verifica ?? ((r, e) => verificaCalcio(r, { estremi: e })))(replay, estremi), errore: null, ms: Date.now() - t0 };
        } catch (e) {
            r = { eventId: String(it.event_id), titolo: titoloDi(it), esito: null, errore: e instanceof Error ? e.message : String(e), ms: Date.now() - t0 };
        }
        out.push(r);
        opz.alRisultato?.(r, i, elenco.length);
    }
    return out;
}

export interface Riepilogo {
    partite: number;
    ok: number;
    incoerenti: number;
    nonVerificate: number;
    righe: string[];
    /** true = tutto verificato e coerente */
    tutteOk: boolean;
}

export function riepilogo(risultati: ReadonlyArray<RisultatoPartita>): Riepilogo {
    const ok = risultati.filter(r => r.esito?.ok).length;
    const incoerenti = risultati.filter(r => r.esito && !r.esito.ok).length;
    const nonVerificate = risultati.filter(r => !r.esito).length;
    const righe = [
        `RIEPILOGO: ${risultati.length} partite verificate: ${ok} OK, ${incoerenti} con incoerenze, ${nonVerificate} non verificabili (errore di caricamento).`,
    ];
    for (const r of risultati) {
        if (r.esito && !r.esito.ok) righe.push(`  INCOERENTE ${r.titolo}: ${r.esito.incoerenze.map(x => x.codice).join(', ')}`);
        if (!r.esito) righe.push(`  NON VERIFICATA ${r.titolo}: ${r.errore}`);
    }
    return { partite: risultati.length, ok, incoerenti, nonVerificate, righe, tutteOk: risultati.length > 0 && ok === risultati.length };
}

/** Referto di UNA partita: riga di esito + (se incoerente) i rilievi; le note solo con `conNote`. */
export function refertoPartita(r: RisultatoPartita, conNote: boolean, soloErrori: boolean): string {
    if (!r.esito) return `NON VERIFICATA ${r.titolo}: ${r.errore}`;
    if (soloErrori && r.esito.ok) return '';
    const righe = [esitoInUnaRiga(r.titolo, r.esito)];
    for (const x of r.esito.rilievi) {
        if (x.gravita === 'nota' && !conNote) continue;
        righe.push(rigaRilievo(x));
    }
    return righe.join('\n');
}

/** Accesso con un utente (solo se si usa la chiave anonima del frontend: le RPC sono per
 *  `authenticated` e `service_role`). Nessuna scrittura sul database. */
export async function accediConUtente(email: string, password: string): Promise<void> {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(`accesso: ${error.message}`);
}

export { supabase as clienteSupabase };
