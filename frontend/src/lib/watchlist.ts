// ============================================================================
// Watchlist personale — data layer per il flusso "spunta partita → snapshot
// immutabile → decisione GIOCATA/SCARTATA". Tutta la matematica e lo snapshot
// vivono lato DB (RPC SECURITY DEFINER): il client congela e legge soltanto.
//   add_to_watchlist       → congela snapshot pre-match (motori + Betfair + edge + consigli)
//   get_watchlist          → lista righe (filtrabile per stato) + n_trades
//   set_watchlist_decision → registra la scelta dell'utente (GIOCATA/SCARTATA/DA_VALUTARE)
// NESSUNA UI qui.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------- Stato e motivi di scarto (enum §1.1 / §1.5) ----------
export type WatchlistStatus = 'DA_VALUTARE' | 'GIOCATA' | 'SCARTATA';

export type RejectReason =
    | 'quota_bassa'
    | 'edge_insufficiente'
    | 'formazioni'
    | 'infortuni'
    | 'non_mi_fido'
    | 'troppe_operazioni'
    | 'liquidita_scarsa'
    | 'gestione_rischio'
    | 'altro';

// Etichette IT per i motivi di scarto (per la UI scartate).
export const REJECT_REASON_LABELS: Record<RejectReason, string> = {
    quota_bassa: 'Quota troppo bassa',
    edge_insufficiente: 'Edge insufficiente',
    formazioni: 'Formazioni',
    infortuni: 'Infortuni',
    non_mi_fido: 'Non mi fido',
    troppe_operazioni: 'Troppe operazioni',
    liquidita_scarsa: 'Liquidità scarsa',
    gestione_rischio: 'Gestione del rischio',
    altro: 'Altro',
};

// ---------- Struttura snapshot JSONB (§1.4) ----------
// Una selezione consigliata dal sistema (1 per (market, selection)). `consigli`
// è il sottoinsieme degli `edges` ordinato per edge decrescente (top N).
export interface SnapshotEdge {
    market: string;
    selection: string;
    model_prob: number;
    best_back: number | null;
    best_lay: number | null;
    implied_prob: number;
    edge: number;                 // model_prob - 1/odds
    ev_back: number | null;       // model_prob*(odds-1)*(1-comm) - (1-model_prob)
    affidabilita: number | null;  // da get_direction
    lift: number | null;
    concordi: string[];           // motori concordi
    motori_totali: number;
}

// Snapshot completo, server-side e immutabile, congelato da add_to_watchlist.
// `direction` e `betfair` sono gli output integrali delle rispettive RPC (jsonb opachi).
export interface WatchlistSnapshot {
    generated_at: string;                       // ISO ts
    direction: unknown;                         // output integrale di get_direction(fixture_id)
    betfair: unknown;                           // output integrale di get_betfair_direction_odds(fixture_id)
    full_odds_markets: string[];                // elenco mercati Betfair disponibili
    edges: SnapshotEdge[];                      // 1 per (market, selection consigliata)
}

// ---------- Riga watchlist (specchia personal_watchlist §1.1 + n_trades §2.2) ----------
export interface WatchlistRow {
    id: number;
    fixture_id: number;
    league_id: number | null;
    league_name: string | null;
    season_year: number | null;
    country: string | null;
    round: string | null;
    home_team: string | null;
    away_team: string | null;
    kickoff: string | null;
    status: WatchlistStatus;
    snapshot: WatchlistSnapshot;
    consigli: SnapshotEdge[];                   // top selezioni consigliate (sottoinsieme di snapshot.edges)
    snapshot_at: string;
    user_note: string | null;
    strategia_ipotizzata: string | null;
    tags: string[];
    reject_reason: RejectReason | null;
    reject_note: string | null;
    decided_at: string | null;
    created_at: string;
    updated_at: string;
    n_trades: number;                           // conteggio trade collegati (da get_watchlist)
}

// ---------- Payload decisione (parametri di set_watchlist_decision §2.3) ----------
export interface WatchlistDecision {
    id: number;
    status: WatchlistStatus;
    rejectReason?: RejectReason | null;
    rejectNote?: string | null;
    note?: string | null;
    strategia?: string | null;
    tags?: string[] | null;
}

// ---------- Funzioni ----------

// §2.1 — congela lo snapshot pre-match e ritorna la riga watchlist completa.
export async function addToWatchlist(fixtureId: number): Promise<WatchlistRow> {
    const { data, error } = await supabase.rpc('add_to_watchlist', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    return data as WatchlistRow;
}

// §2.2 — lista righe watchlist (filtrabile per stato), ordinate per kickoff.
export async function getWatchlist(status?: WatchlistStatus | null): Promise<WatchlistRow[]> {
    const { data, error } = await supabase.rpc('get_watchlist', { p_status: status ?? null });
    if (error) throw new Error(error.message);
    return (data ?? []) as WatchlistRow[];
}

// §2.3 — registra la decisione dell'utente (GIOCATA / SCARTATA / DA_VALUTARE).
export async function setWatchlistDecision(d: WatchlistDecision): Promise<WatchlistRow> {
    const { data, error } = await supabase.rpc('set_watchlist_decision', {
        p_id: Number(d.id),
        p_status: d.status,
        p_reject_reason: d.rejectReason ?? null,
        p_reject_note: d.rejectNote ?? null,
        p_note: d.note ?? null,
        p_strategia: d.strategia ?? null,
        p_tags: d.tags && d.tags.length ? d.tags : null,
    });
    if (error) throw new Error(error.message);
    return data as WatchlistRow;
}
