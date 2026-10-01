// ============================================================================
// tennisFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /tennis e /tennis/terminal.
//
// Non e' importato dall'app: il server di anteprima
// (AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs, alias in
// alias_tennis.mjs) sostituisce con un alias Vite ESATTO l'import
// '@/lib/tennis' con questo file. Si ri-esporta TUTTO il modulo vero
// (percorso RELATIVO, che l'alias non tocca) e si ridefiniscono solo le
// letture che vanno in rete, con le STESSE chiavi e gli stessi tipi del vero.
// I dati sono in tennisDati.ts.
//
// Le letture dei bot della Control Room (servizi, giornata, ordini di oggi)
// NON sono ridefinite: restano quelle vere (vuote col client finto), cosi'
// le altre anteprime non cambiano. Attenzione: l'alias vale per tutto il
// server, quindi anche Market Watch e la Control Room (useTennisVivo) leggono
// le partite seguite e tennis_live_now di qui.
//
// Realtime finto: le notifiche "nulla da dire" restano mute; DUE eccezioni,
// dichiarate perche' senza di loro due pannelli non hanno storia da mostrare:
//   - subscribeTennisLadder consegna subito, alla sottoscrizione, gli ultimi
//     ~4 minuti del book (storiaLadder) -> candele del Chart, flusso del Depth;
//   - subscribeTennisBots notifica N_PASSI cambiamenti (uno ogni 300 ms) e
//     fetchTennisBotsState avanza di un passo a ogni lettura -> la curva
//     "Equity bot (live)" si disegna come nel vivo, poi resta ferma.
// Comandi (arma/disarma, segui, REC, ordini): mai eseguiti, esito negativo.
// ============================================================================
import type { LiveLadderRow } from '../lib/live';
import type { LiveOrderRow, LivePositionRow } from '../lib/liveOrders';
import type {
    TennisBotControl, TennisBotKey, TennisBotsState, TennisFixtureRow, TennisFollow, TennisLiveNowRow,
} from '../lib/tennis';
import {
    EV, FOLLOWS, N_PASSI, botsAlPasso, fixturesDel, ladderDi, liveNowDi, ordiniDi, posizioniDi, storiaLadder,
} from './tennisDati';

export * from '../lib/tennis';

const NESSUN_COMANDO = 'anteprima: nessun comando viene eseguito';
/** realtime finto: nessun cambiamento da notificare */
const nessunCambio = (): (() => void) => () => { /* niente da chiudere */ };

// ---------------------------------------------------------------- partite del giorno

// Preferiti tennis (TennisMatchesList, chiave 'tennis.favorites' di localStorage):
// Sinner-Draper e Musetti-Fritz, scritti SOLO se il browser non ne ha gia'
// (una scelta dell'utente non si sovrascrive mai).
try {
    if (typeof window !== 'undefined' && window.localStorage.getItem('tennis.favorites') == null) {
        window.localStorage.setItem('tennis.favorites', JSON.stringify([EV.sinner, EV.musetti]));
    }
} catch {
    /* storage non disponibile: nessun preferito */
}

export async function fetchTennisFixtures(date: string): Promise<TennisFixtureRow[]> {
    return fixturesDel(date);
}

export function subscribeTennisMarkets(_cb: () => void): () => void {
    return nessunCambio();
}

// ---------------------------------------------------------------- partite seguite / live_now

export async function fetchTennisFollows(): Promise<TennisFollow[]> {
    return FOLLOWS.map((f) => ({ ...f }));
}

export async function followTennisEvent(_eventId: string, _marketId: string): Promise<TennisFollow> {
    throw new Error(NESSUN_COMANDO);
}

export async function setTennisFollowRecord(
    _eventId: string, _record: boolean,
): Promise<{ event_id: string; record: boolean }> {
    throw new Error(NESSUN_COMANDO);
}

export async function fetchTennisNow(eventId: string): Promise<TennisLiveNowRow | null> {
    return liveNowDi(eventId);
}

export function subscribeTennisNow(_eventId: string, _cb: (row: TennisLiveNowRow | null) => void): () => void {
    return nessunCambio();
}

// ---------------------------------------------------------------- ladder

export async function fetchTennisLadder(marketId: string): Promise<LiveLadderRow | null> {
    return ladderDi(marketId);
}

export function subscribeTennisLadder(marketId: string, cb: (row: LiveLadderRow | null) => void): () => void {
    // la storia arriva SINCRONA: cosi' precede la risposta del fetch (piu' fresca),
    // e chi scarta i campioni fuori ordine (pushVolumeSample) li tiene tutti
    for (const riga of storiaLadder(marketId)) cb(riga);
    return nessunCambio();
}

// ---------------------------------------------------------------- ordini e posizioni

export async function fetchTennisOrders(marketId: string, mode: string): Promise<LiveOrderRow[]> {
    return ordiniDi(marketId, mode);
}

export async function fetchTennisPositions(marketId: string, mode: string): Promise<LivePositionRow[]> {
    return posizioniDi(marketId, mode);
}

export function subscribeTennisOrders(
    _marketId: string, _cb: () => void, onHealth?: (up: boolean) => void,
): () => void {
    onHealth?.(true);   // come il canale realtime vero a SUBSCRIBED
    return nessunCambio();
}

export function subscribeTennisPositions(
    _marketId: string, _cb: () => void, onHealth?: (up: boolean) => void,
): () => void {
    onHealth?.(true);
    return nessunCambio();
}

// ---------------------------------------------------------------- bot per evento

/** prossimo passo della giornata dei bot da restituire, per evento (avanza a ogni lettura) */
const passi = new Map<string, number>();

export async function fetchTennisBotsState(eventId: string, _activityLimit = 60): Promise<TennisBotsState> {
    const i = passi.get(eventId) ?? 0;
    passi.set(eventId, Math.min(N_PASSI, i + 1));
    return botsAlPasso(eventId, Math.min(i, N_PASSI - 1));
}

export function subscribeTennisBots(eventId: string, cb: () => void): () => void {
    let n = 0;
    const t = setInterval(() => {
        if ((passi.get(eventId) ?? 0) >= N_PASSI || ++n > N_PASSI) { clearInterval(t); return; }
        cb();
    }, 300);
    return () => clearInterval(t);
}

export async function armTennisBot(
    _eventId: string, _botKey: TennisBotKey, _dryRun: boolean, _stake: number,
    _params: Record<string, number | string | boolean>,
): Promise<TennisBotControl> {
    throw new Error(NESSUN_COMANDO);
}

export async function disarmTennisBot(_eventId: string, _botKey: TennisBotKey): Promise<TennisBotControl> {
    throw new Error(NESSUN_COMANDO);
}
