// ============================================================================
// omegaFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /omega.
//
// Non e' importato dall'app. La pagina Omega non ha un hook di pagina: legge
// lo stato direttamente da `lib/omega`. Il server di anteprima sostituisce
// quindi con un alias Vite ESATTO l'import '@/lib/omega' con questo file: si
// ri-esporta TUTTO il modulo vero (percorso RELATIVO, che l'alias non tocca) e
// si ridefiniscono solo le LETTURE di rete, con le stesse chiavi e gli stessi
// tipi del vero, come i mock di `pages/Omega.test.tsx`:
//   `fetchOmegaState`, `fetchOmegaTrades`, `subscribeOmega` (nessun evento),
//   `fetchOmegaEventiChiusi`, `fetchOmegaEvents`, `fetchManualRequests`,
//   `fetchOmegaMarket`.
// Le scritture (attiva, ferma, parametri, richieste manuali) restano quelle
// vere: dal client Supabase finto non partono.
//
// La giornata (prototipo `s_calcio.js`, OMEGA in PAPER, obiettivo 250 EUR):
// Inter-Torino gamba 1T vinta e gamba 2T (LAY 1-1 @12) aperta al 58' 1-0;
// Feyenoord-AZ Alkmaar regolata (green-up 1T + 2T vinta); Benfica B-Porto B
// chiusa a mano dall'utente.
// ============================================================================
import type {
    OmegaActivityRow, OmegaAggregates, OmegaControl, OmegaEvent, OmegaEventoChiuso,
    OmegaManualRequest, OmegaMarketSnapshot, OmegaState, OmegaTrade,
} from '../lib/omega';
import { EV, KO, OGGI, alle, fa } from './giornataBot';

export * from '../lib/omega';

// ------------------------------------------------------------------ trade

function trade(over: Partial<OmegaTrade> & Pick<OmegaTrade, 'id' | 'event_id' | 'event_name' | 'runner_name' | 'side' | 'price' | 'size' | 'liability' | 'status' | 'pnl' | 'placed_at'>): OmegaTrade {
    return {
        market_id: null, selection_id: null, mode: 'paper', origin: 'auto', phase: null,
        target: 0.95, minute_at_entry: null, score_at_entry: null, kickoff: null,
        bet_id: `paper-${over.id}`, settled_at: null, closes_trade_id: null,
        ...over,
        // esito dell'ordine come lo scrive il servizio (chiesto, abbinato, residuo, prezzo medio)
        meta: {
            requested_size: over.size, size_matched: over.size, size_remaining: 0, avg_price_matched: over.price,
            betfair_updated_at: new Date(Date.parse(over.placed_at) + 2000).toISOString(),
            ...(over.meta ?? {}),
        },
    };
}

const BENFICA = 'Benfica B v Porto B';
const FEYENOORD = 'Feyenoord v AZ Alkmaar';
const INTER = 'Inter v Torino';

const TRADES: OmegaTrade[] = [
    // Benfica B-Porto B: gamba 1T, chiusa a mano dall'utente (cash out)
    trade({ id: 8101, event_id: EV.benfica, event_name: BENFICA, market_id: '1.248119903', selection_id: 12,
        runner_name: '0 - 2', side: 'lay', phase: 'ht_cs', price: 22, size: 1, liability: 21,
        minute_at_entry: 28, score_at_entry: '0-0', kickoff: KO.benfica, status: 'won', pnl: 0.95,
        placed_at: alle('05:58'), settled_at: alle('06:47'),
        meta: { result_ht: '0-1', result_ft: '1-2', p_lose: 0.011, p_market: 0.045 } }),
    trade({ id: 8102, event_id: EV.benfica, event_name: BENFICA, market_id: '1.248119903', selection_id: 12,
        runner_name: '0 - 2', side: 'back', phase: 'ht_cs', price: 30, size: 0.73, liability: 0.73,
        kickoff: KO.benfica, status: 'lost', pnl: -0.73, origin: 'manual', closes_trade_id: 8101,
        placed_at: alle('06:55'), settled_at: alle('06:47'),
        meta: { cashout: true, exit_kind: 'manual', exit_reason: 'cash out dalla pagina' } }),
    // Feyenoord-AZ Alkmaar: green-up sulla 1T, 2T vinta
    trade({ id: 8201, event_id: EV.feyenoord, event_name: FEYENOORD, market_id: '1.248119203', selection_id: 3,
        runner_name: '2 - 0', side: 'lay', phase: 'ht_cs', price: 26, size: 1, liability: 25,
        minute_at_entry: 31, score_at_entry: '0-0', kickoff: KO.feyenoord, status: 'won', pnl: 0.95,
        placed_at: alle('06:31'), settled_at: alle('06:47'),
        meta: { result_ht: '0-0', result_ft: '1-1', p_lose: 0.009, p_market: 0.038, greenup: { state: 'done' } } }),
    trade({ id: 8202, event_id: EV.feyenoord, event_name: FEYENOORD, market_id: '1.248119203', selection_id: 3,
        runner_name: '2 - 0', side: 'back', phase: 'ht_cs', price: 80, size: 0.33, liability: 0.33,
        kickoff: KO.feyenoord, status: 'lost', pnl: -0.33, closes_trade_id: 8201,
        placed_at: alle('06:40'), settled_at: alle('06:47'),
        meta: { exit_kind: 'greenup', exit_reason: 'green-up: risultato bancato raggiungibile' } }),
    trade({ id: 8203, event_id: EV.feyenoord, event_name: FEYENOORD, market_id: '1.248119202', selection_id: 21,
        runner_name: '0 - 3', side: 'lay', phase: 'ft_cs', price: 34, size: 1, liability: 33,
        minute_at_entry: 62, score_at_entry: '1-1', kickoff: KO.feyenoord, status: 'won', pnl: 0.95,
        placed_at: alle('07:17'), settled_at: alle('07:52'),
        meta: { result_ht: '0-0', result_ft: '1-1', p_lose: 0.006, p_market: 0.029 } }),
    // Inter-Torino: 1T vinta (0-0 bancato, 1-0 all'intervallo), 2T aperta
    trade({ id: 8301, event_id: EV.inter, event_name: INTER, market_id: '1.248120013', selection_id: 1,
        runner_name: '0 - 0', side: 'lay', phase: 'ht_cs', price: 8.4, size: 1, liability: 7.4,
        minute_at_entry: 22, score_at_entry: '0-0', kickoff: KO.inter, status: 'won', pnl: 0.95,
        placed_at: alle('07:47'), settled_at: alle('08:12'),
        meta: { result_ht: '1-0', p_lose: 0.019, p_market: 0.119 } }),
    trade({ id: 8302, event_id: EV.inter, event_name: INTER, market_id: '1.248120012', selection_id: 4,
        runner_name: '1 - 1', side: 'lay', phase: 'ft_cs', price: 12, size: 1, liability: 11,
        minute_at_entry: 51, score_at_entry: '1-0', kickoff: KO.inter, status: 'open', pnl: 0,
        placed_at: alle('08:31'),
        meta: { result_ht: '1-0', p_lose: 0.014, p_market: 0.083 } }),
];

// ------------------------------------------------------------------ stato

const REALIZZATO_OGGI = Math.round(
    TRADES.filter((t) => t.settled_at != null).reduce((s, t) => s + t.pnl, 0) * 100) / 100;

const AGG_PAPER: OmegaAggregates = {
    realized_profit: 412.6, realized_today: REALIZZATO_OGGI, open_liability: 11,
    matches_traded: 211, matches_traded_today: 5, legs_today: 5, events_today: 3,
    won_today: 4, lost_today: 0, matches_open: 1, matches_won: 160, matches_lost: 49,
    locked_pnl_open: 0, locked_pnl_open_today: 0, reconciling_liability: 0, live_now: 1,
    events_traded: 141, mode: 'paper',
};

const AGG_LIVE: OmegaAggregates = {
    realized_profit: -3.2, realized_today: 0, open_liability: 0, matches_traded: 4,
    matches_open: 0, matches_won: 1, matches_lost: 1, mode: 'live',
};

const CONTROL: OmegaControl = {
    id: 1, status: 'running', mode: 'paper', daily_goal: 250,
    params: { strategy_version: 3, v3_stake_eur: 1, price_min: 20, price_max: 120, commission_pct: 5 },
    stats: {
        events_total: 41, matches_traded: 211, matches_traded_today: 5, matches_open: 1,
        realized_profit: 412.6, realized_today: REALIZZATO_OGGI, open_liability: 11, open_liability_bot: 11,
        realized_today_bot: REALIZZATO_OGGI, events_today_bot: 3,
        matches_remaining: 2, legs_remaining: 3, target_match: 14.7, target_leg: 7.35,
        goal: 250, goal_pct: Math.round(REALIZZATO_OGGI / 250 * 1000) / 10, last_cycle: fa(3),
        locked_pnl_open: 0, locked_pnl_open_today: 0, degraded: null, reconciling_liability: 0,
        live_now: 1, legs_today: 5, events_today: 3, won_today: 4, lost_today: 0, bot_running: true,
        eventi_chiusi_dall_utente: [EV.benfica],
    },
    error: null, started_at: alle('04:58'), stopped_at: null, heartbeat_at: fa(3), updated_at: fa(3),
};

const ATTIVITA: OmegaActivityRow[] = [
    { id: 3307, ts: alle('08:31:22'), kind: 'flumine_fill', payload: { event_id: EV.inter, leg: 'ft_cs', side: 'lay', size: 1, price: 12 } },
    { id: 3306, ts: alle('08:31:20'), kind: 'place', payload: { event_id: EV.inter, leg: 'ft_cs', side: 'lay', size: 1, price: 12, minute: 51, score: '1-0', p_lose: 0.014 } },
    { id: 3305, ts: alle('08:12:03'), kind: 'settle_position', payload: { event_id: EV.inter, leg: 'ht_cs', locked_pnl: 0.95 } },
    { id: 3304, ts: alle('08:29:40'), kind: 'skip', payload: { event_id: EV.inter, leg: 'ft_cs', reason: 'p_model_sopra_tetto', p_lose: 0.026 } },
    { id: 3303, ts: alle('07:52:00'), kind: 'settle_position', payload: { event_id: EV.feyenoord, leg: 'ft_cs', locked_pnl: 0.95 } },
    { id: 3302, ts: alle('06:55:10'), kind: 'chiuso_dall_utente', payload: { event_id: EV.benfica, reason: 'cashout' } },
    { id: 3301, ts: alle('06:40:03'), kind: 'greenup', payload: { event_id: EV.feyenoord, leg: 'ht_cs', side: 'back', size: 0.33, price: 80, locked_pnl: 0.62 } },
];

const NOMI_ATTIVITA: Record<string, string> = {
    [EV.inter]: INTER, [EV.feyenoord]: FEYENOORD, [EV.benfica]: BENFICA,
};

export async function fetchOmegaState(activityLimit = 50): Promise<OmegaState> {
    const righe = [...ATTIVITA].sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, activityLimit).map((a) => ({
        ...a, payload: { ...a.payload, event_name: NOMI_ATTIVITA[String(a.payload.event_id)] ?? null },
    }));
    return {
        control: CONTROL,
        aggregates: AGG_PAPER,
        activity: righe,
        activity_more: Math.max(0, 60 - righe.length),
        activity_day: OGGI,
        goal_today: 250,
        goal_snapshot: true,
        aggregates_by_mode: { paper: AGG_PAPER, live: AGG_LIVE },
    };
}

export async function fetchOmegaTrades(limit = 2000): Promise<OmegaTrade[]> {
    return TRADES.slice(0, limit).map((t) => ({ ...t }));
}

export function subscribeOmega(_onChange: () => void): () => void {
    return () => { /* anteprima: nessun canale */ };
}

export async function fetchOmegaEventiChiusi(): Promise<OmegaEventoChiuso[]> {
    return [{ event_id: EV.benfica, name: BENFICA, stato_utente: { come: 'cashout', quando: alle('06:55') } }];
}

// ------------------------------------------------------------------ manuale e missioni

function evento(id: string, name: string, ko: string, comp: string, leagueId: number): OmegaEvent {
    return {
        event_id: id, name, open_date: ko, updated_at: fa(240),
        markets: [
            { market_id: `1.${id}2`, market_name: 'Risultato esatto', market_type: 'CORRECT_SCORE', total_matched: 98000 },
            { market_id: `1.${id}3`, market_name: 'Risultato esatto primo tempo', market_type: 'HALF_TIME_SCORE', total_matched: 31000 },
        ],
        country_code: comp === 'Serie A' ? 'IT' : 'ES', competition_name: comp, league_id: leagueId,
    };
}

const EVENTI: OmegaEvent[] = [
    evento(EV.inter, INTER, KO.inter, 'Serie A', 135),
    evento(EV.betis, 'Real Betis v Getafe', KO.betis, 'La Liga', 140),
    evento(EV.bologna, 'Bologna v Udinese', KO.bologna, 'Serie A', 135),
    evento(EV.atalanta, 'Atalanta v Genoa', KO.atalanta, 'Serie A', 135),
    evento(EV.napoli, 'Napoli v Lazio', KO.napoli, 'Serie A', 135),
    evento(EV.getafe, 'Getafe v Celta', KO.getafe, 'La Liga', 140),
];

export async function fetchOmegaEvents(): Promise<OmegaEvent[]> {
    return EVENTI.map((e) => ({ ...e }));
}

export async function fetchManualRequests(limit = 20): Promise<OmegaManualRequest[]> {
    const righe: OmegaManualRequest[] = [
        { id: 77, kind: 'load_book', payload: { market_id: '1.248120012' }, status: 'done', result: { ok: true }, created_at: fa(58), processed_at: fa(57) },
        { id: 76, kind: 'load_markets', payload: { event_id: EV.inter }, status: 'done', result: { ok: true }, created_at: fa(73), processed_at: fa(72) },
        { id: 75, kind: 'refresh_events', payload: {}, status: 'done', result: { events: 17 }, created_at: fa(240), processed_at: fa(238) },
    ];
    return righe.slice(0, limit);
}

export async function fetchOmegaMarket(marketId: string): Promise<OmegaMarketSnapshot | null> {
    return {
        market_id: marketId, event_id: EV.inter, event_name: INTER, market_name: 'Risultato esatto',
        inplay: true, minute: 58, updated_at: fa(3),
        runners: [
            { selection_id: 2, name: '1 - 0', lay_price: 3.7, lay_size: 230, back_price: 3.6, back_size: 412 },
            { selection_id: 3, name: '2 - 0', lay_price: 6.6, lay_size: 88, back_price: 6.4, back_size: 120 },
            { selection_id: 5, name: '2 - 1', lay_price: 24, lay_size: 38, back_price: 23, back_size: 31 },
            { selection_id: 7, name: '2 - 2', lay_price: 38, lay_size: 22, back_price: 36, back_size: 12 },
        ],
    };
}
