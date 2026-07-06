// ============================================================================
// Report Personale — data layer per l'operatività reale dell'utente (trade
// pre-match + live, con coperture/hedge/cashout). Tutta la matematica (P&L,
// metriche di rischio, breakdown) vive in Postgres ed è certificata oracle==RPC.
//   add_personal_trade     → inserisce l'operazione (congela il contesto snapshot)
//   add_trade_leg          → aggiunge una copertura/hedge/cashout e ricalcola
//   settle_personal_trade  → chiude il trade (WON/LOST/VOID/PARTIAL) e ricalcola
//   get_personal_report    → KPI + equity curve + breakdown + consigli vs scelte
//   get_personal_trades    → drill-down righe trade + contesto snapshot
// NESSUNA UI qui.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------- Enum di dominio (specchiano i CHECK §1.2 / §1.3) ----------
export type TradeSide = 'back' | 'lay';
export type TradeTiming = 'prematch' | 'live';
export type TradeStatus = 'OPEN' | 'WON' | 'LOST' | 'VOID' | 'PARTIAL';
export type LegType = 'hedge' | 'cashout' | 'coverage' | 'adjust';
// Origine del P&L: 'model' = derivato dal modello (recompute); 'actual' = reale
// (memorizzato così com'è, manuale o import Betfair). Vedi personal_tracking_manual_entry.sql.
export type PnlSource = 'model' | 'actual';
// Provenienza della riga: app (watchlist), manuale (form Report), import (.bat Betfair).
export type EntrySource = 'app' | 'manual' | 'import';

// ---------- Leg (copertura/hedge/cashout aggiuntivo, §1.3) ----------
export interface TradeLeg {
    id: number;
    trade_id: number;
    leg_type: LegType;
    side: TradeSide | null;
    market: string | null;
    selection: string | null;
    odds: number | null;
    stake: number | null;
    liability: number | null;
    timing: TradeTiming | null;
    minute: number | null;
    net_pnl: number | null;
    note: string | null;
    created_at: string;
}

// ---------- Trade (specchia personal_trades §1.2) ----------
export interface PersonalTrade {
    id: number;
    watchlist_id: number | null;
    // identità match denormalizzata
    fixture_id: number | null;
    league_id: number | null;
    league_name: string | null;
    home_team: string | null;
    away_team: string | null;
    kickoff: string | null;
    // ingresso a mercato
    strategia: string;
    side: TradeSide;
    market: string | null;
    selection: string | null;
    line: number | null;
    entry_odds: number;
    stake: number;                  // backer stake
    liability: number | null;       // per lay = stake*(odds-1)
    exit_odds: number | null;       // cash-out (opz.)
    timing: TradeTiming;
    entry_minute: number | null;
    entry_score: string | null;
    exchange: string;
    commission: number;
    time_operative_min: number | null;
    // esito
    status: TradeStatus;
    result_ft: string | null;
    gross_pnl: number | null;
    net_pnl: number | null;         // "Gain Netto" (entry + legs)
    roi: number | null;             // net_pnl/stake (stored)
    hourly_yield: number | null;    // net_pnl/(time_min/60)
    // contesto congelato dallo snapshot per la selezione scelta
    edge_at_entry: number | null;
    model_prob: number | null;
    implied_prob: number | null;
    affidabilita: number | null;    // da get_direction
    concordi: number | null;
    motori_totali: number | null;
    followed_advice: boolean | null;
    // meta
    comment: string | null;
    tags: string[];
    trade_date: string;             // giorno operativo
    created_at: string;
    updated_at: string;
    legs?: TradeLeg[];              // popolato nel drill-down (get_personal_trades)
    // provenienza + P&L reale (manual entry / import Betfair)
    pnl_source: PnlSource;          // 'model' | 'actual'
    entry_source: EntrySource;      // 'app' | 'manual' | 'import'
    commission_amount: number | null;  // commissione REALE in € (se pnl_source='actual')
    betfair_market_id: string | null;  // riconciliazione import Betfair
    betfair_bet_id: string | null;
    // import Betfair (personal_tracking_import.sql)
    betfair_event_id: string | null;   // "ID Evento"
    country: string | null;            // "Nazione"
    season_year: number | null;        // "Stagione"
    coverage: number | null;           // "Copertura" (stake lato opposto/hedge)
    context: TradeContext | null;      // pronostici + direzioni motori + risultato (congelati)
}

// ---------- Context congelato all'import (pronostici API-Football + direzioni motori) ----------
export interface EngineDirectionMarket {
    market: string;                 // '1x2' | 'btts' | 'over_2_5' | ...
    direction: string | null;       // selezione indicata (es. 'H', 'Over', 'Yes')
    concordi: string[];             // motori concordi (es. ['ml','api'])
    motori_totali: number | null;
    affidabilita: number | null;
    engines: Record<string, any>;   // {ml:{...}, api:{...}, poisson:..., tacticai:...}
}
export interface TradePredictions {
    advice: string | null;              // "pronostico" API-Football
    under_over_line: string | null;
    goals_home_line: string | null;     // possibili gol casa
    goals_away_line: string | null;     // possibili gol ospite
    percent_home: number | null;
    percent_draw: number | null;
    percent_away: number | null;
    winner_name: string | null;
}
export interface TradeResult {
    home_goals: number | null;
    away_goals: number | null;
    total_goals: number | null;
    outcome: string | null;             // 'H' | 'D' | 'A'
    status: string | null;              // 'FT' | ...
    ft: string | null;                  // "1-2"
}
export interface TradeContext {
    predictions?: TradePredictions;
    directions?: { markets?: EngineDirectionMarket[] } | null;
    result?: TradeResult;
    hits?: Record<string, boolean>;     // pronostico azzeccato o no (per mercato)
}

// ---------- Payload di scrittura ----------
// Input di add_personal_trade (§2.4): campi entry §1.2. Tutto opzionale tranne
// strategia/side/entry_odds/stake (i NOT NULL del DB); il resto lo calcola la RPC.
export interface AddTradePayload {
    watchlist_id?: number | null;
    fixture_id?: number | null;
    league_id?: number | null;
    league_name?: string | null;
    home_team?: string | null;
    away_team?: string | null;
    kickoff?: string | null;
    strategia: string;
    side: TradeSide;
    market?: string | null;
    selection?: string | null;
    line?: number | null;
    entry_odds: number;
    stake: number;
    liability?: number | null;
    exit_odds?: number | null;
    timing?: TradeTiming;
    entry_minute?: number | null;
    entry_score?: string | null;
    exchange?: string;
    commission?: number;            // ALIQUOTA commissione (modello), es. 0.05
    time_operative_min?: number | null;
    comment?: string | null;
    tags?: string[] | null;
    trade_date?: string | null;
    // ---- operazioni passate / P&L reale (personal_tracking_manual_entry.sql) ----
    status?: TradeStatus;           // per operazioni già chiuse (passate): WON/LOST/VOID/PARTIAL
    result_ft?: string | null;
    pnl_source?: PnlSource;         // default 'model'; 'actual' → usa net_pnl reale
    entry_source?: EntrySource;     // default 'app'; da UI manuale → 'manual'
    net_pnl?: number | null;        // P&L NETTO reale (obbligatorio se pnl_source='actual')
    gross_pnl?: number | null;      // P&L lordo reale (default net + commissione)
    commission_amount?: number | null;  // commissione REALE in €
    betfair_market_id?: string | null;
    betfair_bet_id?: string | null;
}

// Input di add_trade_leg (§2.5).
export interface AddLegPayload {
    trade_id: number;
    leg_type: LegType;
    side?: TradeSide | null;
    market?: string | null;
    selection?: string | null;
    odds?: number | null;
    stake?: number | null;
    liability?: number | null;
    timing?: TradeTiming | null;
    minute?: number | null;
    net_pnl?: number | null;
    note?: string | null;
}

// Parametri di settle_personal_trade (§2.5).
export interface SettlePayload {
    id: number;
    status: TradeStatus;
    resultFt?: string | null;
    exitOdds?: number | null;
    timeMin?: number | null;
}

// ---------- Report (output di get_personal_report §2.7) ----------

// 1 punto della serie giornaliera (equity cumulativa da 0).
export interface DailyPoint {
    day: string;
    pnl: number;
    equity: number;
    peak: number;
    drawdown: number;
    n_trades: number;
}

// Tutte le metriche §3 (ESATTE vs Excel + STANDARD di rischio).
export interface Metrics {
    // descrittive / esatte vs Excel
    giorni: number;
    profit_days: number;
    loss_days: number;
    pct_profit: number;
    tot: number;
    mean: number;
    max_day: number;
    min_day: number;
    median: number;
    avg_win: number;
    avg_loss: number;
    wl_ratio: number;
    profit_factor: number;
    vol: number;                    // stdev campionaria (n-1)
    sharpe: number;                 // mean/vol
    kurtosis: number;               // KURT Excel (excess, corretta)
    pct_top5: number;
    pct_worst: number;
    // operative
    tempo_medio_giorno: number;
    guadagno_orario_medio: number;
    profit_per_stake: number;       // tot/Σstake
    stake_medio_giorno: number;
    media_trade_giorno: number;     // #trade/n
    giornate_perdita_gt_stake: number;
    // STANDARD (rischio)
    max_drawdown: number;
    recovery_factor: number;
    calmar: number;
    ulcer_index: number;
    upi: number;                    // mean / ulcer_index
    downside_dev: number;
    sortino: number;                // mean/downside_dev
    cvar_5: number;
    max_dd_duration_days: number;
}

// Breakdown per strategia (§2.7).
export interface ByStrategia {
    strategia: string;
    n: number;
    n_won: number;
    win_rate: number;
    stake: number;
    net_pnl: number;
    roi: number;
    profit_factor: number;
}

// Breakdown per lega (§2.7) — stessa forma con identità lega.
export interface ByLeague {
    league_id: number | null;
    league_name: string | null;
    n: number;
    n_won: number;
    win_rate: number;
    stake: number;
    net_pnl: number;
    roi: number;
    profit_factor: number;
}

// Consigli seguiti vs no (§2.7).
export interface AdviceSummary {
    n_followed: number;
    n_off_advice: number;
    roi_followed: number;
    roi_off_advice: number;
}

// Sintesi scartate (§2.7).
export interface DiscardedReason {
    reason: string;
    n: number;
}
export interface DiscardedSummary {
    n: number;
    by_reason: DiscardedReason[];
}

// Oggetto completo ritornato da get_personal_report.
export interface ReportData {
    daily: DailyPoint[];
    metrics: Metrics;
    by_strategia: ByStrategia[];
    by_league: ByLeague[];
    advice: AdviceSummary;
    discarded: DiscardedSummary;
}

// ---------- Filtri report / trades (§2.7 / §2.8) ----------
export interface ReportFilters {
    from?: string | null;
    to?: string | null;
    strategia?: string | null;
    leagueId?: number | null;
    status?: string | null;
    limit?: number | null;          // solo get_personal_trades
}

// ---------- Funzioni ----------

// §2.4 — inserisce l'operazione; congela il contesto snapshot e calcola followed_advice.
export async function addPersonalTrade(payload: AddTradePayload): Promise<PersonalTrade> {
    const { data, error } = await supabase.rpc('add_personal_trade', { p: payload });
    if (error) throw new Error(error.message);
    return data as PersonalTrade;
}

// §2.5 — aggiunge una leg (copertura/hedge/cashout/adjust) e ricalcola il trade.
// La RPC restituisce la RIGA LEG inserita (to_jsonb(l.*)), non il trade.
export async function addTradeLeg(payload: AddLegPayload): Promise<TradeLeg> {
    const { data, error } = await supabase.rpc('add_trade_leg', { p: payload });
    if (error) throw new Error(error.message);
    return data as TradeLeg;
}

// §2.5 — chiude il trade (status finale + result + exit + tempo) e ricalcola.
export async function settlePersonalTrade(s: SettlePayload): Promise<PersonalTrade> {
    const { data, error } = await supabase.rpc('settle_personal_trade', {
        p_id: Number(s.id),
        p_status: s.status,
        p_result_ft: s.resultFt ?? null,
        p_exit_odds: s.exitOdds ?? null,
        p_time_min: s.timeMin ?? null,
    });
    if (error) throw new Error(error.message);
    return data as PersonalTrade;
}

// Imposta il "Tempo Operativo (Min.)" a mano dalla dashboard e ricalcola la resa
// oraria lato DB (set_trade_time_operative). null = azzera il tempo.
export async function setTradeTimeOperative(id: number, minutes: number | null): Promise<PersonalTrade> {
    const { data, error } = await supabase.rpc('set_trade_time_operative', {
        p_id: Number(id),
        p_minutes: minutes,
    });
    if (error) throw new Error(error.message);
    return data as PersonalTrade;
}

// §2.7 — KPI + equity curve + breakdown + consigli vs scelte + scartate.
export async function getPersonalReport(filters: ReportFilters = {}): Promise<ReportData> {
    const { data, error } = await supabase.rpc('get_personal_report', {
        p_from: filters.from ?? null,
        p_to: filters.to ?? null,
        p_strategia: filters.strategia ?? null,
        p_league_id: filters.leagueId ?? null,
        p_status: filters.status ?? null,
    });
    if (error) throw new Error(error.message);
    return data as ReportData;
}

// §2.11 — SVUOTA tutta la reportistica personale (trade + leg + watchlist, ogni
// stato). Operazione distruttiva: tocca SOLO le tabelle personal_*. Ritorna i
// conteggi eliminati.
export async function resetPersonalReport(): Promise<{ legs: number; trades: number; watchlist: number }> {
    const { data, error } = await supabase.rpc('reset_personal_report');
    if (error) throw new Error(error.message);
    return data as { legs: number; trades: number; watchlist: number };
}

// §2.8 — drill-down righe trade (tutti i campi + contesto snapshot).
export async function getPersonalTrades(filters: ReportFilters = {}): Promise<PersonalTrade[]> {
    const { data, error } = await supabase.rpc('get_personal_trades', {
        p_from: filters.from ?? null,
        p_to: filters.to ?? null,
        p_strategia: filters.strategia ?? null,
        p_league_id: filters.leagueId ?? null,
        p_status: filters.status ?? null,
        p_limit: filters.limit ?? null,
    });
    if (error) throw new Error(error.message);
    return (data ?? []) as PersonalTrade[];
}
