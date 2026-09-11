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
            { event: '*', schema: 'public', table: 'safe_strategy_status' },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as ScanStatusRow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}
