// ============================================================================
// safeBotFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /safe-strategy.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/components/safestrategy/useSafeBot' con questo file:
//   - il modulo VERO si ri-esporta tutto (percorso RELATIVO);
//   - `useSafeBot` e' ridefinito qui e restituisce un `SafeBotView` (il tipo del
//     modulo vero) con le IDENTICHE chiavi e tipi, costruito come gli stati di
//     `pages/SafeStrategy.test.tsx` (CONTROL, OPEN_TRADE, TENNIS_TRADE,
//     OPP_ROW) e con le funzioni VERE di `lib/safeBot` dove l'hook vero le usa
//     (`mergeBotParams` per i parametri effettivi);
//   - i comandi sono no-op: dall'anteprima non parte nessun ordine.
//
// La giornata (prototipo `s_calcio.js`, SAFE in PAPER): un LAY del pareggio
// su Real Betis-Getafe (modello), il LAY "Altro risultato casa" su
// Inter-Torino (R. ESATTO, nato dal segnale), un BACK su Sinner (TENNIS);
// regolata in perdita la PUNTA su Feyenoord-AZ Alkmaar (finita 2-2).
// ============================================================================
import type { SafeBotHandlers, SafeBotView } from '../components/safestrategy/useSafeBot';
import {
    mergeBotParams,
    type SafeActivityRow, type SafeAggregates, type SafeControl, type SafeOpportunity,
    type SafeOpportunityRow, type SafeParamsEffective, type SafeTrade,
} from '../lib/safeBot';
import { EV, OGGI, alle, fa, nulla } from './giornataBot';

export * from '../components/safestrategy/useSafeBot';

// ------------------------------------------------------------------ parametri

const VARIANTI = ['base', 'esatto', 'punta', 'tennis'] as const;
const MODI = { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper', manual: 'paper' };

const PARAMS_GREZZI: Record<string, unknown> = {
    variants: [...VARIANTI], strategy_modes: MODI,
    stake: { laySize: 2, backSize: 2 }, commission_pct: 5, min_stake: 2,
    risk: { daily_liability_cap: 600, per_event_liability_cap: 150, per_event_max_trades: 3, daily_loss_stop: 20, model_stake: 3 },
};

const EFFETTIVI: SafeParamsEffective = {
    poll_interval_s: 2, commission_pct: 5, max_open_trades: 20, max_liability_per_trade: 300,
    min_size_available_factor: 1, opps_interval_s: 10, opps_stake: 5, max_spread_ratio: 1.6,
    opps_min_confidence: 0.7, opps_min_edge: 0.03, min_stake: 2, variants: [...VARIANTI],
    execution_mode: 'auto', auto_trade_opportunities: false, auto_trade_anomalies: false,
    auto_trade_combos: false, auto_trade_tennis: false,
    proponi_model: true, proponi_tennis: true, proponi_combo: true, proponi_anomaly: true,
    strategy_modes: MODI, tennis_exit_approval: true, stake: { laySize: 2, backSize: 2 },
};

// ------------------------------------------------------------------ trade

function trade(over: Partial<SafeTrade> & Pick<SafeTrade, 'id' | 'event_id' | 'event_name' | 'strategy' | 'market_id' | 'market_type' | 'selection_id' | 'selection_name' | 'side' | 'price' | 'size' | 'liability' | 'status' | 'placed_at'>): SafeTrade {
    return {
        sport: 'calcio', mode: 'paper', commission: 0.05, minute_at_entry: null, score_at_entry: null,
        pnl: 0, bet_id: `paper-${over.id}`, settled_at: null, origin: 'auto', closes_trade_id: null,
        signal_key: null,
        ...over,
        // esito dell'ordine come lo scrive il servizio (chiesto, abbinato, residuo, prezzo medio)
        meta: {
            size_matched: over.size, size_remaining: 0, avg_price_matched: over.price,
            betfair_updated_at: new Date(Date.parse(over.placed_at) + 2000).toISOString(),
            ...(over.meta ?? {}),
        },
    };
}

const TRADES: SafeTrade[] = [
    trade({ id: 7304, event_id: EV.sinner, event_name: 'Sinner v Draper', sport: 'tennis', strategy: 'tennis',
        market_id: '1.248135010', market_type: 'MATCH_ODDS', selection_id: 9020001, selection_name: 'J. Sinner',
        side: 'back', price: 1.31, size: 3, liability: 3, status: 'open', placed_at: alle('08:02'),
        score_at_entry: 'set 0-0 \u00b7 game 4-3', signal_key: `${EV.sinner}:tennis:set 0-0` }),
    trade({ id: 7302, event_id: EV.inter, event_name: 'Inter v Torino', strategy: 'esatto',
        market_id: '1.248120012', market_type: 'CORRECT_SCORE', selection_id: 8, selection_name: 'Any Other Home Win',
        side: 'lay', price: 46, size: 2, liability: 90, status: 'open', placed_at: alle('08:37:20'),
        minute_at_entry: 57, score_at_entry: '1-0', signal_key: `${EV.inter}:esatto:home:1-0`,
        meta: { idempotency_key: `sig:${EV.inter}:esatto:home:1-0`, p_lose_entry: 0.018 } }),
    trade({ id: 7301, event_id: EV.betis, event_name: 'Real Betis v Getafe', strategy: 'model',
        market_id: '1.248120440', market_type: 'MATCH_ODDS', selection_id: 58805, selection_name: 'The Draw',
        side: 'lay', price: 3.3, size: 4, liability: 9.2, status: 'open', placed_at: alle('08:25'),
        minute_at_entry: 18, score_at_entry: '0-0', meta: { kind: 'model', p_lose_entry: 0.21 } }),
    trade({ id: 7303, event_id: EV.feyenoord, event_name: 'Feyenoord v AZ Alkmaar', strategy: 'punta',
        market_id: '1.248119200', market_type: 'MATCH_ODDS', selection_id: 1003, selection_name: 'Feyenoord',
        side: 'back', price: 1.12, size: 2.2, liability: 2.2, status: 'lost', pnl: -2.2,
        placed_at: alle('07:25'), settled_at: alle('07:54'), minute_at_entry: 70, score_at_entry: '2-0',
        signal_key: `${EV.feyenoord}:punta:2-0` }),
];

const AGG_PAPER: SafeAggregates = {
    realized_today: -2.2, realized_total: 118.4, open_liability: 102.2, open_count: 3, won: 58, lost: 21,
    reconciling_liability: 0, reconciling_count: 0, day_liability: 104.4, day_liability_model: 9.2,
    day_trades: 4, legs_today: 4, events_today: 4, won_today: 0, lost_today: 1,
    operating_day: OGGI, mode: 'paper',
};

const CONTROL: SafeControl = {
    id: 1, status: 'running', mode: 'paper', params: PARAMS_GREZZI,
    stats: {
        events_total: 41, signals_active: 2, trades_open: 3, open_liability: 102.2, reconciling_liability: 0,
        realized_today: -2.2, realized_total: 118.4, won_today: 0, lost_today: 1, legs_today: 4, events_today: 4,
        feed_blind: 0, last_cycle: fa(1),
        risk: {
            daily_liability: 104.4, daily_liability_bot: 104.4, realized_today_bot: -2.2, cap_solo_automatico: true,
            daily_cap: 600, reconciling_liability: 0, loss_stop_active: false, daily_loss_stop: -20,
        },
        opps: { model: 3, anomaly: 1, combo: 1, tennis: 1 },
        params_effective: EFFETTIVI,
    },
    error: null, started_at: alle('04:58'), stopped_at: null, heartbeat_at: fa(1), updated_at: fa(1),
};

// ------------------------------------------------------------------ opportunita'

function opp(o: Partial<SafeOpportunity> & Pick<SafeOpportunity, 'market_type' | 'market_id' | 'selection_id' | 'selection_name' | 'side' | 'price' | 'p_model' | 'p_implied' | 'confidence'>): SafeOpportunity {
    const edge = Math.round((o.p_model - o.p_implied) * 1000) / 1000;
    return {
        kind: 'model', market_name: null, line: null, size_available: 74, edge,
        ev: Math.round(edge * o.price * 1000) / 1000, rationale: null,
        ...o,
    };
}

const OPPORTUNITA: SafeOpportunityRow[] = [
    {
        event_id: EV.betis, sport: 'calcio', updated_at: fa(4),
        payload: {
            minute: 31, score_home: 0, score_away: 0, event_name: 'Real Betis v Getafe',
            lambdas: { home: 1.21, away: 0.84 }, source: 'fixture', kinds: { model: 1, anomaly: 1 },
            opps: [
                opp({ market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5', line: 2.5, market_id: '1.248120445',
                    selection_id: 47977, selection_name: 'Under 2.5 Goals', side: 'back', price: 1.58,
                    p_model: 0.679, p_implied: 0.633, confidence: 0.74, size_available: 620,
                    calibration: { applied: true, family: 'ou', n: 1840 } }),
                opp({ kind: 'anomaly', market_type: 'OVER_UNDER_35', market_name: 'Over/Under 3.5', line: 3.5,
                    market_id: '1.248120446', selection_id: 47980, selection_name: 'Over 3.5 Goals', side: 'lay',
                    price: 4.4, p_model: 0.181, p_implied: 0.227, confidence: 0.81, size_available: 96,
                    rule: 'ou_ladder', gap: 0.041, p_source: 'modello',
                    ref: { market_name: 'Over/Under 4.5', selection_name: 'Over 4.5 Goals', line: 4.5, price: 13.5, side: 'back' } }),
            ],
        },
    },
    {
        event_id: EV.inter, sport: 'calcio', updated_at: fa(6),
        payload: {
            minute: 58, score_home: 1, score_away: 0, event_name: 'Inter v Torino',
            lambdas: { home: 0.62, away: 0.31 }, source: 'fixture', kinds: { combo: 1 },
            opps: [
                opp({ kind: 'combo', combo: 'under_stack', market_type: 'OVER_UNDER_35', market_name: 'scala Under',
                    market_id: '1.248120016', selection_id: 47979, selection_name: 'Under 3.5 Goals', side: 'back',
                    price: 1.22, p_model: 0.95, p_implied: 0.9, confidence: 0.77, size_available: 310,
                    locked_profit_per_eur: 0.031, best_case_per_eur: 0.05, total_stake: 6, min_total_stake: 4,
                    min_leg_stake: 2, executable_whole: true, book_supports_min: true, p_model_source: 'book',
                    legs: [
                        { market_type: 'OVER_UNDER_35', market_id: '1.248120016', selection_id: 47979, selection_name: 'Under 3.5 Goals',
                            side: 'back', price: 1.22, size_available: 310, stake_ratio: 0.7, stake: 4.2 },
                        { market_type: 'OVER_UNDER_45', market_id: '1.248120017', selection_id: 47981, selection_name: 'Under 4.5 Goals',
                            side: 'lay', price: 1.08, size_available: 120, stake_ratio: 0.3, stake: 1.8 },
                    ] }),
            ],
        },
    },
    {
        event_id: EV.sinner, sport: 'tennis', updated_at: fa(4),
        payload: {
            minute: null, score_home: null, score_away: null, event_name: 'Sinner v Draper',
            sets: { p1: 1, p2: 0 }, games: { p1: 2, p2: 1 }, kinds: { tennis: 2 },
            opps: [
                opp({ kind: 'tennis', market_type: 'MATCH_ODDS', market_name: 'Match Odds', market_id: '1.248135010',
                    selection_id: 9020001, selection_name: 'J. Sinner', side: 'back', price: 1.25,
                    p_model: 0.845, p_implied: 0.8, confidence: 0.74, size_available: 2200,
                    extra: { retire_risk: 0.02, best_of: 3, server: 'p1', momentum_against: false, sets: { p1: 1, p2: 0 }, games: { p1: 2, p2: 1 } } }),
                opp({ kind: 'tennis', market_type: 'MATCH_ODDS', market_name: 'Match Odds', market_id: '1.248135010',
                    selection_id: 9020002, selection_name: 'J. Draper', side: 'lay', price: 5.1,
                    p_model: 0.153, p_implied: 0.196, confidence: 0.81, size_available: 380,
                    extra: { retire_risk: 0.02, best_of: 3, server: 'p1', momentum_against: false, sets: { p1: 1, p2: 0 }, games: { p1: 2, p2: 1 } } }),
            ],
        },
    },
];

// ------------------------------------------------------------------ attivita'

const ATTIVITA: SafeActivityRow[] = [
    { id: 4812, ts: fa(55), kind: 'skip', payload: { event_id: EV.lens, event_name: 'Lens v Nantes', mode: 'paper', reason: 'pre_ko_assente' } },
    { id: 4811, ts: alle('08:37:20'), kind: 'place', payload: { event_id: EV.inter, event_name: 'Inter v Torino', mode: 'paper', strategy: 'esatto',
        selection_name: 'Any Other Home Win', side: 'lay', market_type: 'CORRECT_SCORE', size: 2, price: 46, trade_id: 7302 } },
    { id: 4810, ts: alle('08:37:21'), kind: 'flumine_fill', payload: { event_id: EV.inter, event_name: 'Inter v Torino', mode: 'paper', size: 2, price: 46, trade_id: 7302 } },
    { id: 4809, ts: alle('08:25:12'), kind: 'place', payload: { event_id: EV.betis, event_name: 'Real Betis v Getafe', mode: 'paper', strategy: 'model',
        selection_name: 'The Draw', side: 'lay', market_type: 'MATCH_ODDS', size: 4, price: 3.3, trade_id: 7301 } },
    { id: 4808, ts: alle('08:22:40'), kind: 'risk_block', payload: { event_id: EV.inter, event_name: 'Inter v Torino', mode: 'paper', reason: 'per_event_cap' } },
    { id: 4807, ts: alle('08:02:05'), kind: 'place', payload: { event_id: EV.sinner, event_name: 'Sinner v Draper', mode: 'paper', strategy: 'tennis',
        selection_name: 'J. Sinner', side: 'back', market_type: 'MATCH_ODDS', size: 3, price: 1.31, trade_id: 7304 } },
    { id: 4806, ts: alle('07:54:02'), kind: 'settle_position', payload: { event_id: EV.feyenoord, event_name: 'Feyenoord v AZ Alkmaar', mode: 'paper', pnl: -2.2, trade_id: 7303 } },
    { id: 4805, ts: alle('07:25:10'), kind: 'place', payload: { event_id: EV.feyenoord, event_name: 'Feyenoord v AZ Alkmaar', mode: 'paper', strategy: 'punta',
        selection_name: 'Feyenoord', side: 'back', market_type: 'MATCH_ODDS', size: 2.2, price: 1.12, trade_id: 7303 } },
];

// ------------------------------------------------------------------ vista

let VISTA: SafeBotView | null = null;

function vista(): SafeBotView {
    return {
        available: true, loading: false, busy: false, error: null,
        control: CONTROL,
        canaleLocale: 'connected',
        trades: TRADES,
        aggregates: AGG_PAPER,
        aggregatesByMode: { paper: AGG_PAPER, live: null },
        requests: [],
        opportunities: OPPORTUNITA,
        activity: [...ATTIVITA].sort((a, b) => String(b.ts).localeCompare(String(a.ts))),
        paramsEffective: EFFETTIVI,
        operatingDay: OGGI,
        params: mergeBotParams(PARAMS_GREZZI),
        mode: 'paper', desiredMode: 'paper', modeMismatch: false, liveConfirmed: false,
        reload: nulla, start: nulla, stop: nulla, setMode: nulla, saveParams: nulla,
        place: async () => null, cashout: async () => null, cancel: async () => null,
        isCashOutPending: () => false,
        freshSettlements: [],
        freshOutcomes: [],
    };
}

export function useSafeBot(_handlers: SafeBotHandlers = {}): SafeBotView {
    VISTA ??= vista();
    return VISTA;
}
