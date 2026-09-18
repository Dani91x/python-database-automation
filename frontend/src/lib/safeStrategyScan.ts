// ============================================================================
// safeStrategyScan.ts — data layer dello SCANNER Safe Strategy.
//
// Lo scanner backend (Betfair/safe_strategy, service_role) scansiona TUTTI gli
// eventi in-play del momento e scrive i FATTI su safe_strategy_scan (1 riga per
// evento) + heartbeat su safe_strategy_status. Qui solo lettura/subscribe
// (SELECT consentita ad authenticated, pattern live_now). Richiede la
// migrazione migrations/safe_strategy_scan.sql.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export interface ScanOddsPair {
    /** id Betfair del runner a cui si riferisce la coppia (pubblicato dallo
     *  scanner per ogni lato del Match Odds: e' l'id con cui si piazza). */
    selection_id?: number | null;
    /** ultimo prezzo tradato sul runner (informativo) */
    ltp?: number | null;
    back: number | null;
    lay: number | null;
    /** EUR disponibili al miglior prezzo back/lay = importo abbinabile SUBITO a
     *  quella quota (best offers, livello 0 dello stream). Assenti nelle righe
     *  scritte da scanner precedenti. */
    back_size?: number | null;
    lay_size?: number | null;
}

/** Disponibilità media Betfair per l'evento (IPS scoresAndBroadcast, lo stesso
 *  dato che il sito usa per mostrare le icone): null = non ancora noto. */
export interface ScanMediaFlags {
    video: boolean | null;
    viz: boolean | null;
}

/** Blocco GENERICO di un mercato nel payload dello scanner
 *  (`scanner.build_market_block`): stato del mercato + elenco COMPLETO delle
 *  selezioni con best back/lay e size abbinabile. È la forma UNICA usata da
 *  Correct Score, Half Time Score e dai mercati a gol del motore opportunità
 *  (`ou[]`, `btts`, `ht_result`): un solo formato da leggere per prezzare il
 *  cash out di QUALSIASI posizione. */
export interface ScanMarketBlock {
    market_id: string | null;
    status: string | null;
    inplay?: boolean | null;
    total_matched?: number | null;
    selections?: ScanCsSelection[];
    /** 'OVER_UNDER_25' · 'BOTH_TEAMS_TO_SCORE' · 'HALF_TIME' (solo blocchi opportunità) */
    market_type?: string | null;
    /** linea Over/Under (0.5 … 5.5) */
    line?: number | null;
    ts_ms?: number | null;
    /** betDelay del marketDefinition (0 pre-match, ~5 s in-play) */
    bet_delay?: number | null;
    /**
     * LINEA GIÀ DECISA dal punteggio (Over vinto / Under perso). Lo scanner la
     * tiene nel feed SOLO perché una posizione di Mike ci sta ancora sopra
     * (`for_mike`): per Safe Strategy non è un'opportunità né una quota "viva",
     * e nemmeno un prezzo con cui chiudere — l'esito è già certo.
     */
    decided?: boolean | null;
    /** true = blocco mantenuto nel feed per una posizione Mike, non per Safe */
    for_mike?: boolean | null;
}

export interface CalcioScanPayload {
    media?: ScanMediaFlags | null;
    /** Istante (ms epoch) in cui lo scanner ha letto le quote di questa partita.
     *  Lo scrive `safe_strategy/service.py` ed e' il gate di freschezza del
     *  backend.
     *
     *  CERT. 14/09 — CORREZIONE A UNA MIA NOTA TROPPO RIGIDA. Qui c'era scritto
     *  che la UI non lo usa di proposito, perche' «due numeri per la stessa
     *  cosa sarebbero due verita' diverse». Non sono due numeri per la stessa
     *  cosa, sono DUE FATTI DIVERSI:
     *    · `updated_at` = quando il feed ha scritto l'ultimo CAMBIAMENTO;
     *    · `odds_ts_ms` = quanto e' vecchio il PREZZO su cui si sta per piazzare.
     *  Il secondo e' l'unico che conti nell'istante prima di un ordine, ed e'
     *  giusto mostrarlo. La regola vera non e' «uno solo», e' **etichette
     *  diverse in posti diversi**: «feed» in testata per la riga, «quote» sulla
     *  partita per il prezzo — cosi' non si leggono come lo stesso dato.
     *  Resta il punto aperto vero, che nessuno dei due risolve: l'eta' PER
     *  SINGOLO MERCATO non e' pubblicata. */
    odds_ts_ms?: number | null;
    event_name: string | null;
    home: string | null;
    away: string | null;
    competition: string | null;
    open_date: string | null;
    inplay: boolean;
    mo_market_id: string | null;
    mo_status: string | null;
    odds: { home: ScanOddsPair | null; draw: ScanOddsPair | null; away: ScanOddsPair | null } | null;
    /** OPZIONALE: elenco esplicito dei runner del Match Odds. Il feed odierno
     *  NON lo pubblica — gli id stanno in `odds.<lato>.selection_id` — resta
     *  come override se una versione futura dello scanner lo aggiunge. */
    mo_selections?: ScanCsSelection[];
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    red_home: number | null;
    red_away: number | null;
    /** CERT. 14/09 - indice di "controllo del gioco" in [-1, 1], orientato sulla
     *  squadra di CASA (negativo = preme l'ospite). Lo calcola lo SCANNER da
     *  corner (finestra mobile sulla timeline) e cartellini, cosi' la UI e il
     *  bot leggono lo STESSO numero. Assente sulle righe scritte prima. */
    pressure_index?: number | null;
    /** SPEC §2 «Selezione aggiuntiva» (16/09): i due numeri storici della voce
     *  — scontri diretti finiti 2-2/3-3 e gol subiti per partita — calcolati
     *  UNA volta sola dallo SCANNER (`safe_strategy/selezione.py`, atlante
     *  `hazard_atlas_v2`) e pubblicati qui, come `pressure_index`: i due motori
     *  devono leggere lo STESSO numero. Assente = dato non disponibile, mai zero. */
    selection_hint?: {
        fonte?: string;
        h2h_meetings: number | null;
        h2h_big_draws: number | null;
        conceded: { home: number | null; away: number | null } | null;
    } | null;
    pre_ko: { home: number; draw: number; away: number; captured_at?: string } | null;
    cs: {
        market_id: string | null;
        status: string | null;
        /** dal 09/09 sera: mercato CS COMPLETO (tutte le selezioni) per Omega */
        inplay?: boolean | null;
        total_matched?: number | null;
        selections?: ScanCsSelection[];
        any_other_home: ScanOddsPair | null;
        any_other_away: ScanOddsPair | null;
    } | null;
    /** Half Time Score COMPLETO (stessa forma di `cs`): serve alla gamba 1T di
     *  Omega per il cash out live. Assente nelle righe scritte da scanner
     *  precedenti → i consumatori devono trattarlo come opzionale. */
    ht?: {
        market_id: string | null;
        status: string | null;
        inplay?: boolean | null;
        total_matched?: number | null;
        selections?: ScanCsSelection[];
    } | null;
    /** MERCATI A GOL del motore opportunità (chiavi ADDITIVE: assenti nei
     *  payload scritti da scanner precedenti). `ou` è ordinato per linea.
     *  Sono i mercati su cui si piazza dalle Opportunità: senza leggerli la
     *  tabella non sapeva prezzare il cash out (audit R1). */
    ou?: ScanMarketBlock[] | null;
    btts?: ScanMarketBlock | null;
    ht_result?: ScanMarketBlock | null;
}

/** Selezione del Correct Score nel feed (id/nome/prezzi/size/stato runner). */
export interface ScanCsSelection extends ScanOddsPair {
    selection_id: number;
    name: string | null;
    runner_status?: string | null;
}

/** Selezione CS live per selection_id dal payload (null se assente). */
export function csSelection(p: CalcioScanPayload | null | undefined, selectionId: number): ScanCsSelection | null {
    const sels = p?.cs?.selections;
    if (!Array.isArray(sels)) return null;
    return sels.find((s) => Number(s.selection_id) === Number(selectionId)) ?? null;
}

/** Selezione Half Time Score live per selection_id (null se il feed non la espone). */
export function htSelection(p: CalcioScanPayload | null | undefined, selectionId: number): ScanCsSelection | null {
    const sels = p?.ht?.selections;
    if (!Array.isArray(sels)) return null;
    return sels.find((s) => Number(s.selection_id) === Number(selectionId)) ?? null;
}

/** TUTTI i blocchi di mercato presenti nel payload di un evento, in ordine
 *  stabile: Correct Score, Half Time Score, le linee Over/Under, Gol/NoGol e
 *  l'1X2 del primo tempo. Il tennis non ha blocchi (solo Match Odds). Serve a
 *  prezzare una posizione su QUALSIASI mercato che il feed espone. */
export function scanMarketBlocks(
    p: CalcioScanPayload | TennisScanPayload | null | undefined,
): ScanMarketBlock[] {
    if (!p || !('cs' in p)) return [];
    const c = p as CalcioScanPayload;
    const out: ScanMarketBlock[] = [];
    if (c.cs) out.push(c.cs as ScanMarketBlock);
    if (c.ht) out.push(c.ht as ScanMarketBlock);
    for (const b of (Array.isArray(c.ou) ? c.ou : [])) if (b) out.push(b);
    if (c.btts) out.push(c.btts);
    if (c.ht_result) out.push(c.ht_result);
    return out;
}

/**
 * true = blocco utilizzabile da Safe Strategy per prezzare/valutare qualcosa.
 * Scarta SOLO le linee `decided`: l'esito è già aritmetico e la quota non è un
 * prezzo di uscita reale.
 * `for_mike` NON basta a scartare un blocco: il marcatore dice solo che la
 * linea è tenuta nel feed anche perché una posizione Mike ci sta sopra — se la
 * linea è ancora viva è un mercato di chiusura legittimo anche per Safe.
 * Scartarla farebbe sparire il cash out su ogni partita tradata anche da Mike
 * (è la stessa classe di bug dell'audit R1).
 */
export function isUsableBlock(b: ScanMarketBlock | null | undefined): boolean {
    if (!b) return false;
    if (b.decided === true) return false;
    return true;
}

/** I soli blocchi utilizzabili da Safe (scarta le linee già DECISE). */
export function usableMarketBlocks(
    p: CalcioScanPayload | TennisScanPayload | null | undefined,
): ScanMarketBlock[] {
    return scanMarketBlocks(p).filter(isUsableBlock);
}

/** Blocco del feed con quel `market_id` (null = mercato non nel feed). */
export function scanBlockByMarketId(
    p: CalcioScanPayload | TennisScanPayload | null | undefined,
    marketId: string | null | undefined,
): ScanMarketBlock | null {
    if (!marketId) return null;
    const want = String(marketId);
    return scanMarketBlocks(p).find((b) => String(b.market_id ?? '') === want) ?? null;
}

/** Selezione dentro un blocco: per selection_id, altrimenti per NOME. */
export function blockSelection(
    block: ScanMarketBlock | null | undefined,
    by: { selectionId?: number | null; name?: string | null },
): ScanCsSelection | null {
    const sels = block?.selections;
    if (!Array.isArray(sels)) return null;
    if (by.selectionId != null) {
        const hit = sels.find((s) => Number(s.selection_id) === Number(by.selectionId));
        if (hit) return hit;
    }
    if (by.name != null && String(by.name).trim() !== '') {
        const n = String(by.name).trim().toLowerCase();
        const hit = sels.find((s) => String(s.name ?? '').trim().toLowerCase() === n);
        if (hit) return hit;
    }
    return null;
}

export interface TennisScanPayload {
    media?: ScanMediaFlags | null;
    /** vedi `CalcioScanPayload.odds_ts_ms` */
    odds_ts_ms?: number | null;
    event_name: string | null;
    p1: string | null;
    p2: string | null;
    competition: string | null;
    open_date: string | null;
    inplay: boolean;
    mo_market_id: string | null;
    mo_status: string | null;
    odds: { p1: ScanOddsPair | null; p2: ScanOddsPair | null } | null;
    /** OPZIONALE, come per il calcio: gli id stanno in `odds.p1|p2.selection_id` */
    mo_selections?: ScanCsSelection[];
    sets: { p1: number; p2: number } | null;
    games: { p1: number; p2: number } | null;
}

export interface ScanRow {
    event_id: string;
    sport: 'calcio' | 'tennis';
    payload: CalcioScanPayload | TennisScanPayload;
    updated_at: string | null;
}

/** un messaggio del canale locale scanner (47336): STESSA riga di
 *  `safe_strategy_scan` + i campi di consegna del canale (`_pubblicato_ms`,
 *  `_seq`, `fonte`) dichiarati nel contratto (F0/F1). */
export type ScanRowLocaleMsg = ScanRow & { _pubblicato_ms?: number; _seq?: number; fonte?: string };

/**
 * STADIO B2a (18/09, raccordo) — istante di UN messaggio scanner, per la
 * regola «vince il più recente»: `_pubblicato_ms` se il canale lo porta,
 * altrimenti `updated_at` (la stessa colonna, sia da Postgres sia dal canale
 * locale che rispecchia la stessa riga). `null` = non giudicabile.
 */
export function istanteScanMsg(r: { updated_at?: string | null; _pubblicato_ms?: number } | null | undefined): number | null {
    if (!r) return null;
    if (typeof r._pubblicato_ms === 'number' && Number.isFinite(r._pubblicato_ms)) return r._pubblicato_ms;
    if (r.updated_at) { const t = Date.parse(r.updated_at); return Number.isNaN(t) ? null : t; }
    return null;
}

/**
 * PURA: il messaggio del canale locale scanner va applicato? `null` = NO
 * (scartato: senza `event_id`/`payload`, o più vecchio della riga già in
 * `attuale`). Altrimenti la riga da mettere nel lotto (`applicaLottoScan`).
 * Un messaggio senza timestamp giudicabile passa comunque (si preferisce
 * applicare piuttosto che perdere un aggiornamento per un dato assente).
 */
export function scanLocaleAccettabile(
    attuale: readonly ScanRow[], msg: ScanRowLocaleMsg | null | undefined,
): ScanRow | null {
    if (!msg || !msg.event_id || !msg.payload) return null;
    const nuovo = istanteScanMsg(msg);
    const riga = attuale.find((r) => r.event_id === msg.event_id);
    if (riga) {
        const vecchio = istanteScanMsg(riga);
        if (nuovo != null && vecchio != null && nuovo < vecchio) return null;
    }
    return msg;
}

export interface ScanStatusPayload {
    calcio_inplay?: number;
    tennis_inplay?: number;
    monitored?: number;
    dry?: boolean;
    /** 'stream' = Exchange Stream API ufficiale (push) · 'rest' = fallback poll */
    source?: string;
    /** mercati coperti da connessioni stream VIVE (0 = REST puro); il resto dei rilevanti va in REST */
    stream_markets?: number;
    /** connessioni stream attive / capacità totale del pool (connessioni × mercati per connessione) */
    stream_connections?: number;
    stream_capacity?: number;
    last_error?: string | null;
    started_at?: string;
}
export interface ScanStatusRow {
    id: string;
    payload: ScanStatusPayload;
    updated_at: string | null;
}

export async function fetchScanRows(): Promise<ScanRow[]> {
    const { data, error } = await supabase.from('safe_strategy_scan').select('*');
    if (error) throw new Error(error.message);
    return (data ?? []) as ScanRow[];
}

export async function fetchScanStatus(): Promise<ScanStatusRow | null> {
    const { data, error } = await supabase
        .from('safe_strategy_status')
        .select('*')
        .eq('id', 'scanner')
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as ScanStatusRow | null) ?? null;
}

export type ScanEvent =
    | { type: 'upsert'; row: ScanRow }
    | { type: 'delete'; eventId: string };

/** UN solo canale per tutta la tabella scan (decine di eventi: mai N canali). */
export function subscribeScanRows(cb: (ev: ScanEvent) => void): () => void {
    const channel = supabase
        .channel(`safe_strategy_scan:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'safe_strategy_scan' },
            (payload) => {
                if (payload.eventType === 'DELETE') {
                    const old = payload.old as { event_id?: string } | null;
                    if (old?.event_id) cb({ type: 'delete', eventId: old.event_id });
                    return;
                }
                const next = payload.new as ScanRow | null;
                if (next && next.event_id) cb({ type: 'upsert', row: next });
            },
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}

export function subscribeScanStatus(cb: (row: ScanStatusRow | null) => void): () => void {
    const channel = supabase
        .channel(`safe_strategy_status:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            // CERT. 12/09 — SOLO la riga dello scanner: senza filtro qualunque
            // altra riga della tabella (altri id) sovrascriveva lo stato del
            // feed e la pagina dichiarava il radar morto (o vivo) a sproposito.
            { event: '*', schema: 'public', table: 'safe_strategy_status', filter: 'id=eq.scanner' },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as ScanStatusRow | null;
                if (next && String((next as { id?: string }).id ?? 'scanner') !== 'scanner') return;
                cb(next);
            },
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}
