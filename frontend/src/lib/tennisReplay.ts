// ============================================================================
// tennisReplay.ts — dati e logica PURA del «Replay Tennis» (07/10/2026).
//
// Sezione SEPARATA dal Match Replay del calcio (ordine dell'utente del 07/10:
// «TENNIS E CALCIO SONO DISTINTI»): RPC proprie (`list_replays_tennis`,
// `get_replay_tennis_meta`, `get_replay_tennis_frames`, migrazione
// `migrations/replay_tennis_2026-10-07.sql`) su tabelle proprie. Il caricamento a
// finestre e la conversione GBP->EUR alla fonte sono quelli del calcio
// (`fetchFramesAFinestre` di live.ts), sulle RPC del tennis.
//
// Qui solo funzioni pure e testate: timeline, punteggio all'istante, simboli
// della barra, categorie dei mercati tennis, esito dei mercati dal regolamento
// Betfair (runner WINNER nella marketDefinition), fasi per il motore opportunita'.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import {
    fetchFramesAFinestre,
    type Frame, type Market, type ReplayData, type ReplayProgress, type ReplaySelection,
} from '@/lib/live';
import type { TennisPointEvent, TennisScoreState } from '@/lib/tennis';
import {
    marketCashOut, positionIfWins, type LadderMap, type SimBet,
} from '@/lib/replay-pnl';
import { DEFAULT_DELAY_MS } from '@/lib/matching';
import type { Opportunity } from '@/lib/opportunities/types';

// ---------------------------------------------------------------------------
// tipi (forma delle RPC del tennis)
// ---------------------------------------------------------------------------
export interface TennisReplayItem {
    event_id: string;
    competition_name: string | null;
    player1_name: string;
    player2_name: string;
    open_date: string | null;
    n_markets: number | null;
    n_snapshots: number | null;
    n_score: number | null;
    ts_min: string | null;
    ts_max: string | null;
    fonte: 'import' | 'runner' | string;
}

export interface TennisReplaySelection extends ReplaySelection {
    /** esito finale nella marketDefinition: WINNER | LOSER | ACTIVE | REMOVED */
    status: string | null;
}

export interface TennisReplayMarket extends Market {
    selections: TennisReplaySelection[];
    /** betDelay registrato (secondi) */
    bet_delay: number | null;
    /** primo istante col mercato CLOSED (regolato da Betfair) */
    settled_ts: string | null;
}

export type TennisEventoGioco = 'BREAK' | 'SET_END' | 'SET_START' | 'TIEBREAK_START' | 'MATCH_END' | 'SALTO';

export interface TennisScoreRow {
    ts: string;
    source: string;
    score: TennisScoreState;
    event_types: string[];
    point: TennisPointEvent | null;
}

export interface TennisReplayEvent {
    event_id: string;
    competition_name: string | null;
    player1_name: string;
    player2_name: string;
    open_date: string | null;
    valuta: string;
}

export interface TennisReplayData {
    event: TennisReplayEvent;
    markets: TennisReplayMarket[];
    frames: Frame[];
    score_timeline: TennisScoreRow[];
}

interface TennisReplayMeta {
    event: TennisReplayEvent;
    markets: TennisReplayMarket[];
    score_timeline: TennisScoreRow[];
    ts_min: string | null;
    ts_max: string | null;
    inplay_from_ts: string | null;
}

/** Errore PostgREST "funzione non trovata": la migrazione non e' applicata. */
export function migrazioneMancante(e: { code?: string; message?: string } | null | undefined): boolean {
    return !!e && (e.code === 'PGRST202' || /replay_tennis|schema cache/i.test(e.message ?? ''));
}

export const MSG_MIGRAZIONE =
    'Replay Tennis non ancora attivo sul database: va applicata la migrazione '
    + 'migrations/replay_tennis_2026-10-07.sql (la applica l\'utente dal SQL Editor).';

// ---------------------------------------------------------------------------
// dati
// ---------------------------------------------------------------------------
export async function fetchTennisReplayList(limit = 100): Promise<TennisReplayItem[]> {
    const { data, error } = await supabase.rpc('list_replays_tennis', { p_limit: limit });
    if (error) throw new Error(migrazioneMancante(error) ? MSG_MIGRAZIONE : error.message);
    const raw = data as { rows?: TennisReplayItem[] } | null;
    return raw?.rows ?? [];
}

export async function fetchTennisReplay(
    eventId: string,
    onProgress?: (p: ReplayProgress) => void,
): Promise<TennisReplayData> {
    const { data, error } = await supabase.rpc('get_replay_tennis_meta', { p_event_id: eventId });
    if (error) throw new Error(migrazioneMancante(error) ? MSG_MIGRAZIONE : error.message);
    const meta = data as TennisReplayMeta;
    const base: TennisReplayData = {
        event: meta.event,
        markets: meta.markets ?? [],
        frames: [],
        score_timeline: meta.score_timeline ?? [],
    };
    if (!meta.ts_min || !meta.ts_max) return base;
    const frames = await fetchFramesAFinestre(eventId, {
        rpcFrames: 'get_replay_tennis_frames',
        tsMin: meta.ts_min,
        tsMax: meta.ts_max,
        inplayFromTs: meta.inplay_from_ts,
        nMercati: base.markets.length,
    }, onProgress);
    return { ...base, frames };
}

// ---------------------------------------------------------------------------
// timeline e ricerche per istante (bisezione)
// ---------------------------------------------------------------------------
export interface PassoTimeline { ts: string; minute: number | null }

const perTs = <T extends { ts: string }>(a: T, b: T) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0);

/** Griglia della barra: un passo per bucket di `bucketMs` (primo frame del
 *  bucket), ordinata. Copre tutta la registrazione (come il Match Replay). */
export function costruisciTimeline(frames: ReadonlyArray<Frame>, bucketMs: number): PassoTimeline[] {
    const perBucket = new Map<number, PassoTimeline>();
    for (const f of frames) {
        const b = Math.floor(new Date(f.ts).getTime() / bucketMs);
        const cur = perBucket.get(b);
        if (!cur || f.ts < cur.ts) perBucket.set(b, { ts: f.ts, minute: null });
    }
    return Array.from(perBucket.values()).sort(perTs);
}

/** PRIMO indice con ts >= dato (clampato): il passo in cui un istante diventa visibile. */
export function indiceDiPasso(timeline: ReadonlyArray<{ ts: string }>, ts: string): number {
    let lo = 0, hi = timeline.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (timeline[mid].ts < ts) lo = mid + 1; else hi = mid;
    }
    return Math.min(lo, Math.max(0, timeline.length - 1));
}

/** Ultimo elemento con ts <= dato (array ordinato), o undefined. */
export function ultimoAl<T extends { ts: string }>(arr: ReadonlyArray<T> | undefined, ts: string): T | undefined {
    if (!arr || arr.length === 0 || !ts) return undefined;
    let lo = 0, hi = arr.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (arr[mid].ts <= ts) lo = mid + 1; else hi = mid;
    }
    return lo > 0 ? arr[lo - 1] : undefined;
}

/** Frame raggruppati per mercato, ognuno ordinato per ts. */
export function framesPerMercato(frames: ReadonlyArray<Frame>): Map<string, Frame[]> {
    const map = new Map<string, Frame[]>();
    for (const f of frames) {
        const arr = map.get(f.market_id) ?? [];
        arr.push(f);
        map.set(f.market_id, arr);
    }
    for (const arr of map.values()) arr.sort(perTs);
    return map;
}

/** Primo istante IN GIOCO (flag di mercato Betfair), o il primo frame se nessuno lo e'. */
export function inizioInGioco(frames: ReadonlyArray<Frame>): string | null {
    let primo: string | null = null;
    let primoInGioco: string | null = null;
    for (const f of frames) {
        if (primo == null || f.ts < primo) primo = f.ts;
        if (f.inplay && (primoInGioco == null || f.ts < primoInGioco)) primoInGioco = f.ts;
    }
    return primoInGioco ?? primo;
}

/** Minuti trascorsi dall'inizio del gioco registrato (per il cursore), null prima. */
export function minutiDiGioco(ts: string, inGiocoTs: string | null): number | null {
    if (!ts || !inGiocoTs || ts < inGiocoTs) return null;
    return Math.floor((new Date(ts).getTime() - new Date(inGiocoTs).getTime()) / 60_000);
}

// ---------------------------------------------------------------------------
// punteggio all'istante del cursore
// ---------------------------------------------------------------------------
export function ordinaPunteggio(rows: ReadonlyArray<TennisScoreRow>): TennisScoreRow[] {
    return [...rows].sort(perTs);
}

/** La riga di punteggio valida all'istante (ultima con ts <= istante). */
export function punteggioAl(ordinate: ReadonlyArray<TennisScoreRow>, ts: string): TennisScoreRow | null {
    return ultimoAl(ordinate, ts) ?? null;
}

/** I punti giocati fino all'istante (dal piu' vecchio), per il punto-per-punto. */
export function puntiFinoA(ordinate: ReadonlyArray<TennisScoreRow>, ts: string): TennisPointEvent[] {
    const out: TennisPointEvent[] = [];
    for (const r of ordinate) {
        if (r.ts > ts) break;
        if (r.point) out.push(r.point);
    }
    return out;
}

/** Etichetta compatta del punteggio: "6-4 5-7 · 2-4 · 15-40". */
export function etichettaPunteggio(s: TennisScoreState | null | undefined): string {
    if (!s) return '—';
    const set = s.set_summary ?? `${s.games.p1}-${s.games.p2}`;
    return `${set} · ${s.points.p1}-${s.points.p2}`;
}

// ---------------------------------------------------------------------------
// simboli della barra (tennis)
// ---------------------------------------------------------------------------
export type TipoSimbolo = 'inplay' | 'set_start' | 'break' | 'tiebreak' | 'set_end' | 'match_end' | 'salto';

export interface SimboloTennis {
    ts: string;
    pctLeft: number;
    tipo: TipoSimbolo;
    label: string;
}

const TIPO_DI_EVENTO: Record<string, TipoSimbolo> = {
    BREAK: 'break',
    SET_END: 'set_end',
    SET_START: 'set_start',
    TIEBREAK_START: 'tiebreak',
    MATCH_END: 'match_end',
    SALTO: 'salto',
};

export const NOME_SIMBOLO: Record<TipoSimbolo, string> = {
    inplay: 'Passaggio in gioco',
    set_start: 'Inizio set',
    break: 'Break',
    tiebreak: 'Tie-break',
    set_end: 'Fine set',
    match_end: 'Fine partita',
    salto: 'Buco di registrazione',
};

/** Chi ha vinto l'ultimo game/set (1|2) fra la riga precedente e questa. */
function vincitoreDelPassaggio(prev: TennisScoreState | null, cur: TennisScoreState): 1 | 2 | null {
    if (!prev) return null;
    if (cur.sets.p1 > prev.sets.p1) return 1;
    if (cur.sets.p2 > prev.sets.p2) return 2;
    if (cur.games.p1 > prev.games.p1) return 1;
    if (cur.games.p2 > prev.games.p2) return 2;
    return null;
}

/** I game del set in cui e' avvenuto il passaggio: a set chiuso quelli del set
 *  appena finito (ultima cella di game_sequence, o i game correnti se IPS non
 *  l'ha appesa: fine partita), altrimenti i game correnti. */
function gameDelPassaggio(prev: TennisScoreState | null, cur: TennisScoreState): string {
    const setChiuso = prev != null && cur.sets.p1 + cur.sets.p2 > prev.sets.p1 + prev.sets.p2;
    const seq1 = cur.game_sequence?.p1 ?? [];
    const seq2 = cur.game_sequence?.p2 ?? [];
    if (setChiuso && prev && seq1.length > (prev.game_sequence?.p1 ?? []).length) {
        return `${seq1[seq1.length - 1]}-${seq2[seq2.length - 1]}`;
    }
    return `${cur.games.p1}-${cur.games.p2}`;
}

/**
 * I simboli del tennis sulla barra: eventi di gioco delle righe di punteggio
 * (BREAK, SET_START, SET_END, TIEBREAK_START, MATCH_END, SALTO: derivati nel
 * backend, `convertitore.eventi_tennis`) e il passaggio in gioco dai frame di
 * mercato (se la registrazione parte prima). Posizione = INDICE del passo (la
 * barra avanza a passi, come il Match Replay). Le sospensioni non sono qui:
 * le disegna la barra dai frame (segmenti rossi).
 */
export function simboliTennis(
    ordinate: ReadonlyArray<TennisScoreRow>,
    timeline: ReadonlyArray<{ ts: string }>,
    p1: string,
    p2: string,
    inGiocoTs: string | null,
): SimboloTennis[] {
    if (timeline.length === 0) return [];
    const span = Math.max(1, timeline.length - 1);
    const out: SimboloTennis[] = [];
    const pct = (ts: string) => Math.min(Math.max(indiceDiPasso(timeline, ts) / span, 0), 1);
    const nome = (g: 1 | 2 | null) => (g === 1 ? p1 : g === 2 ? p2 : '');
    if (inGiocoTs && inGiocoTs > timeline[0].ts) {
        out.push({ ts: inGiocoTs, pctLeft: pct(inGiocoTs), tipo: 'inplay', label: NOME_SIMBOLO.inplay });
    }
    let prev: TennisScoreState | null = null;
    for (const r of ordinate) {
        const s = r.score;
        const vince = vincitoreDelPassaggio(prev, s);
        for (const ev of r.event_types ?? []) {
            const tipo = TIPO_DI_EVENTO[ev];
            if (!tipo) continue;
            let label: string = NOME_SIMBOLO[tipo];
            if (tipo === 'break') label = `Break di ${nome(vince)} (${gameDelPassaggio(prev, s)})`;
            else if (tipo === 'set_end') label = `Fine set: ${s.set_summary ?? `${s.sets.p1}-${s.sets.p2}`}${vince ? ` (${nome(vince)})` : ''}`;
            else if (tipo === 'set_start') label = `Inizio set ${s.current_set ?? s.sets.p1 + s.sets.p2 + 1}`;
            else if (tipo === 'tiebreak') label = 'Tie-break';
            else if (tipo === 'match_end') label = `Fine partita: ${s.set_summary ?? ''}`.trim();
            else if (tipo === 'salto') label = 'Buco di registrazione: piu\' game passati fra due righe';
            out.push({ ts: r.ts, pctLeft: pct(r.ts), tipo, label });
        }
        prev = s;
    }
    return out;
}

// ---------------------------------------------------------------------------
// sospensioni (segmenti rossi della barra)
// ---------------------------------------------------------------------------
/** Per ogni passo: il MATCH_ODDS e' sospeso? (senza MATCH_ODDS: un mercato qualunque). */
export function sospesoPerPasso(
    timeline: ReadonlyArray<{ ts: string }>,
    perMercato: Map<string, Frame[]>,
    markets: ReadonlyArray<Market>,
): boolean[] {
    const mo = markets.filter(m => (m.market_type || '').toUpperCase() === 'MATCH_ODDS').map(m => m.market_id);
    return timeline.map(step => {
        if (mo.length > 0) return mo.some(id => ultimoAl(perMercato.get(id), step.ts)?.status === 'SUSPENDED');
        for (const arr of perMercato.values()) if (ultimoAl(arr, step.ts)?.status === 'SUSPENDED') return true;
        return false;
    });
}

// ---------------------------------------------------------------------------
// categorie dei mercati tennis (menu)
// ---------------------------------------------------------------------------
export type CatTennis = 'MATCH_ODDS' | 'SET_BETTING' | 'SET_WINNER' | 'GAMES' | 'HANDICAP' | 'TIE_BREAK' | 'ALTRI';

export const CATEGORIE_TENNIS: ReadonlyArray<{ key: CatTennis; label: string }> = [
    { key: 'MATCH_ODDS', label: 'Match Odds' },
    { key: 'SET_BETTING', label: 'Set Betting' },
    { key: 'SET_WINNER', label: 'Vincente set' },
    { key: 'GAMES', label: 'Game totali' },
    { key: 'HANDICAP', label: 'Handicap' },
    { key: 'TIE_BREAK', label: 'Tie-break' },
    { key: 'ALTRI', label: 'Altri' },
];

export function categoriaTennis(tipo: string | null | undefined): CatTennis {
    const t = (tipo || '').toUpperCase();
    if (t === 'MATCH_ODDS') return 'MATCH_ODDS';
    if (t === 'SET_BETTING' || t === 'NUMBER_OF_SETS' || t.includes('SET_SCORE')) return 'SET_BETTING';
    if (t.includes('HANDICAP')) return 'HANDICAP';
    if (t.includes('TIE_BREAK') || t.includes('TIEBREAK')) return 'TIE_BREAK';
    if (t.includes('SET') && t.includes('WINNER')) return 'SET_WINNER';
    if (t.includes('GAMES') || t.includes('OVER_UNDER') || t.startsWith('TOTAL')) return 'GAMES';
    return 'ALTRI';
}

/** Mercati per categoria (ordine del catalogo), e le categorie presenti in ordine canonico. */
export function raggruppaMercatiTennis<T extends { market_type: string | null }>(markets: ReadonlyArray<T>): {
    perCategoria: Map<CatTennis, T[]>;
    presenti: { key: CatTennis; label: string }[];
} {
    const perCategoria = new Map<CatTennis, T[]>();
    for (const m of markets) {
        const k = categoriaTennis(m.market_type);
        const arr = perCategoria.get(k) ?? [];
        arr.push(m);
        perCategoria.set(k, arr);
    }
    return { perCategoria, presenti: CATEGORIE_TENNIS.filter(c => (perCategoria.get(c.key)?.length ?? 0) > 0) };
}

// ---------------------------------------------------------------------------
// esito dei mercati: il REGOLAMENTO di Betfair, non il punteggio
// ---------------------------------------------------------------------------
/** La selezione vincente se all'istante il mercato e' gia' regolato (CLOSED con
 *  un runner WINNER nella marketDefinition registrata), altrimenti null. Vale per
 *  OGNI mercato tennis (Match Odds, Set Betting, Handicap...): nessuna regola di
 *  punteggio inventata. */
export function vincitoreRegolato(market: Pick<TennisReplayMarket, 'selections' | 'settled_ts'>, tsMs: number): number | null {
    if (!market.settled_ts || !Number.isFinite(tsMs)) return null;
    if (tsMs < new Date(market.settled_ts).getTime()) return null;
    const vincenti = market.selections.filter(s => (s.status || '').toUpperCase() === 'WINNER');
    return vincenti.length === 1 ? vincenti[0].selection_id : null;
}

/** Valore di un mercato: P&L DEFINITIVO se regolato, altrimenti cash-out (stesse
 *  primitive del calcio: `positionIfWins` / `marketCashOut`). */
export function valutaMercatoTennis(
    bets: SimBet[],
    ladder: LadderMap | undefined,
    market: Pick<TennisReplayMarket, 'selections' | 'settled_ts'>,
    tsMs: number,
): { value: number; settled: boolean; winnerId: number | null } {
    if (bets.length === 0) return { value: 0, settled: false, winnerId: null };
    const vince = vincitoreRegolato(market, tsMs);
    if (vince != null) return { value: positionIfWins(bets, vince), settled: true, winnerId: vince };
    return {
        value: marketCashOut(bets, ladder, market.selections.map(s => s.selection_id)),
        settled: false,
        winnerId: null,
    };
}

/** Bet-delay in-play del mercato (ms): il betDelay registrato; ignoto = quello di sempre. */
export function delayMercatoMs(market: Pick<TennisReplayMarket, 'bet_delay'> | undefined): number {
    const s = market?.bet_delay;
    return typeof s === 'number' && Number.isFinite(s) && s >= 0 ? s * 1000 : DEFAULT_DELAY_MS;
}

// ---------------------------------------------------------------------------
// motore opportunita' (generico) sul tennis
// ---------------------------------------------------------------------------
/** Il replay nella forma del motore opportunita' (`ReplayData`): mercati e frame
 *  del tennis, NESSUNA score_timeline del calcio (gol/minuti non esistono). */
export function perMotoreOpportunita(d: TennisReplayData): ReplayData {
    return {
        event: {
            event_id: d.event.event_id, fixture_id: null, league_name: d.event.competition_name,
            home_name: d.event.player1_name, away_name: d.event.player2_name,
            open_date: d.event.open_date ?? '', status: 'UPLOADED',
        },
        markets: d.markets,
        frames: d.frames,
        score_timeline: [],
    };
}

/** Fase tennis di un istante per il motore: "Pre-partita" prima del gioco,
 *  poi "Set N" dal punteggio registrato. */
export function faseTennis(ordinate: ReadonlyArray<TennisScoreRow>, ts: string, inGiocoTs: string | null): string {
    if (!inGiocoTs || ts < inGiocoTs) return 'pre';
    const r = punteggioAl(ordinate, ts);
    if (!r) return 'In gioco';
    const n = r.score.current_set ?? (r.score.sets.p1 + r.score.sets.p2 + 1);
    return `Set ${n}`;
}

/** Le opportunita' con la fase del TENNIS al posto di quella del calcio (minuti). */
export function conFaseTennis(opps: ReadonlyArray<Opportunity>, fase: string): Opportunity[] {
    return opps.map(o => (o.phase === fase ? o : { ...o, phase: fase }));
}

// ---------------------------------------------------------------------------
// elenco delle partite: per torneo, poi per anno
// ---------------------------------------------------------------------------
export function raggruppaPerTorneo(list: ReadonlyArray<TennisReplayItem>): {
    key: string; torneo: string; anni: { anno: number; items: TennisReplayItem[] }[];
}[] {
    const perTorneo = new Map<string, Map<number, TennisReplayItem[]>>();
    for (const it of list) {
        const t = it.competition_name || 'Torneo sconosciuto';
        const anni = perTorneo.get(t) ?? new Map<number, TennisReplayItem[]>();
        const y = it.open_date ? new Date(it.open_date).getFullYear() : 0;
        const anno = Number.isFinite(y) ? y : 0;
        const arr = anni.get(anno) ?? [];
        arr.push(it);
        anni.set(anno, arr);
        perTorneo.set(t, anni);
    }
    return Array.from(perTorneo.entries())
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([t, anni]) => ({
            key: t,
            torneo: t,
            anni: Array.from(anni.entries()).sort((a, b) => b[0] - a[0]).map(([anno, items]) => ({ anno, items })),
        }));
}
