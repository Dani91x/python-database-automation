// ============================================================================
// liveFeedFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di Segui live (/segui-live).
//
// Non e' importato dall'app: il server di anteprima
// (AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs, alias in
// alias_seguilive.mjs) sostituisce con un alias Vite ESATTO l'import
// '@/lib/live' con questo file. Si ri-esporta TUTTO il modulo vero (percorso
// RELATIVO, che l'alias non tocca) e si ridefiniscono solo le letture che vanno
// in rete (partite seguite, live_now, segnali, ladder, avvisi), con le STESSE
// chiavi e gli stessi tipi del vero. I dati sono in seguiLiveDati.ts.
// Le sottoscrizioni realtime non emettono nulla (come un realtime senza
// cambiamenti): la pagina vive del fetch iniziale e, con CANALE_FINTO=1, dei
// push del canale locale finto (canaleFinto.mjs).
// ============================================================================
import type { Alert, LiveFollow, LiveLadderRow, LiveNowRow, LiveSignalsRow } from '../lib/live';
import {
    AVVISI, EV, FOLLOWS, MS_DB, SEGNALI_BETIS, SEGNALI_INTER, ladderDi, liveNowDi,
} from './seguiLiveDati';

export * from '../lib/live';

/** realtime finto: nessun cambiamento da notificare */
const nessunCambio = (): (() => void) => () => { /* niente da chiudere */ };

export async function fetchLiveFollows(): Promise<LiveFollow[]> {
    return FOLLOWS.map((f) => ({ ...f }));
}

export function subscribeLiveFollowEvent(
    _eventId: string, _cb: (row: LiveFollow | null) => void,
): () => void {
    return nessunCambio();
}

export async function fetchLiveNow(eventId: string): Promise<LiveNowRow | null> {
    return liveNowDi(eventId, MS_DB);
}

export function subscribeLiveNow(_eventId: string, _cb: (row: LiveNowRow | null) => void): () => void {
    return nessunCambio();
}

export async function fetchLiveSignals(eventId: string): Promise<LiveSignalsRow | null> {
    if (eventId === EV.inter) return SEGNALI_INTER;
    if (eventId === EV.betis) return SEGNALI_BETIS;
    return null;
}

export function subscribeLiveSignals(_eventId: string, _cb: (row: LiveSignalsRow | null) => void): () => void {
    return nessunCambio();
}

export async function fetchLiveLadder(marketId: string): Promise<LiveLadderRow | null> {
    return ladderDi(marketId, MS_DB);
}

export function subscribeLiveLadder(_marketId: string, _cb: (row: LiveLadderRow | null) => void): () => void {
    return nessunCambio();
}

export async function fetchLiveAlerts(): Promise<Alert[]> {
    return AVVISI.map((a) => ({ ...a }));
}

export function subscribeLiveAlerts(_cb: () => void): () => void {
    return nessunCambio();
}
