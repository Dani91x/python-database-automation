// ============================================================================
// personalReportFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /report-personale.
//
// Non e' importato dall'app: il server di anteprima
// (AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs, alias in
// alias_analisi.mjs) sostituisce con un alias Vite ESATTO l'import
// '@/lib/personalReport' con questo file. Si ri-esporta TUTTO il modulo vero
// (percorso RELATIVO, che l'alias non tocca) e si ridefiniscono solo le tre
// letture (get_personal_report, get_personal_trades, get_cash_movements), con le
// STESSE chiavi e gli stessi tipi del vero. Le scritture restano quelle vere.
// Dati: il prototipo AUDIT_2026-10-01/REDESIGN/prototipo/js/s_storici.js
// (trade Inter-Torino, Getafe-Celta, Brentford-Everton, Palermo-Bari,
// Mainz-Freiburg; cassa +500 / -200). Le metriche sono CALCOLATE dalla serie
// giornaliera qui sotto, non scritte a mano: i numeri a schermo sono coerenti.
// Orologio dell'anteprima: 2026-10-01T08:38:00Z.
// ============================================================================
import type {
    ByLeague, ByStrategia, CashSummary, DailyPoint, Metrics, PersonalTrade, ReportData,
    ReportFilters, TradeContext,
} from '../lib/personalReport';

export * from '../lib/personalReport';

// ------------------------------------------------------------------ serie giornaliera

// [giorno, P&L netto, n. trade]: settembre 2026, 30 giornate operative
const GIORNI: [string, number, number][] = [
    ['2026-09-01', 4.2, 2], ['2026-09-02', -6.1, 3], ['2026-09-03', 7.9, 2], ['2026-09-04', 2.35, 1],
    ['2026-09-05', 11.4, 3], ['2026-09-06', -3.8, 2], ['2026-09-07', 5.05, 2], ['2026-09-08', -9.6, 3],
    ['2026-09-09', 1.2, 1], ['2026-09-10', 6.75, 2], ['2026-09-11', -2.4, 2], ['2026-09-12', 13.9, 4],
    ['2026-09-13', -14.5, 3], ['2026-09-14', 3.3, 2], ['2026-09-15', 0.85, 1], ['2026-09-16', 8.6, 3],
    ['2026-09-17', -5.2, 2], ['2026-09-18', -7.95, 3], ['2026-09-19', 27.1, 4], ['2026-09-20', 2.1, 2],
    ['2026-09-21', -1.6, 1], ['2026-09-22', 4.8, 2], ['2026-09-23', -11.3, 3], ['2026-09-24', 6.2, 2],
    ['2026-09-25', 1.95, 2], ['2026-09-26', 9.5, 2], ['2026-09-27', 6.4, 2], ['2026-09-28', -4.35, 2],
    ['2026-09-29', -23.0, 3], ['2026-09-30', 8.12, 2],
];

const r2 = (v: number) => Math.round(v * 100) / 100;

function serie(da: string | null | undefined, a: string | null | undefined): DailyPoint[] {
    let eq = 0;
    let peak = 0;
    return GIORNI
        .filter(([d]) => (!da || d >= da) && (!a || d <= a))
        .map(([day, pnl, n]) => {
            eq = r2(eq + pnl);
            peak = Math.max(peak, eq);
            return { day, pnl, equity: eq, peak: r2(peak), drawdown: r2(eq - peak), n_trades: n };
        });
}

function media(v: number[]): number {
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0;
}

function metriche(d: DailyPoint[]): Metrics {
    const p = d.map((x) => x.pnl);
    const n = p.length;
    const tot = p.reduce((s, x) => s + x, 0);
    const mean = n ? tot / n : 0;
    const win = p.filter((x) => x > 0);
    const loss = p.filter((x) => x < 0);
    const ord = [...p].sort((a, b) => a - b);
    const median = n ? (n % 2 ? ord[(n - 1) / 2] : (ord[n / 2 - 1] + ord[n / 2]) / 2) : 0;
    const vol = n > 1 ? Math.sqrt(p.reduce((s, x) => s + (x - mean) ** 2, 0) / (n - 1)) : 0;
    const neg = p.map((x) => Math.min(0, x));
    const downside = n > 1 ? Math.sqrt(neg.reduce((s, x) => s + x * x, 0) / (n - 1)) : 0;
    const maxDd = Math.min(0, ...d.map((x) => x.drawdown));
    const ulcer = Math.sqrt(media(d.map((x) => x.drawdown ** 2)));
    // durata massima sott'acqua, in giorni
    let durata = 0;
    let corrente = 0;
    for (const x of d) { corrente = x.drawdown < 0 ? corrente + 1 : 0; durata = Math.max(durata, corrente); }
    // curtosi in eccesso (formula KURT di Excel)
    const s4 = p.reduce((s, x) => s + ((x - mean) / (vol || 1)) ** 4, 0);
    const kurt = n > 3
        ? (n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))) * s4 - (3 * (n - 1) ** 2) / ((n - 2) * (n - 3))
        : 0;
    const nTrade = d.reduce((s, x) => s + x.n_trades, 0);
    const stake = nTrade * 11.4; // stake medio per trade del periodo
    const peggiori = ord.slice(0, Math.max(1, Math.round(n * 0.05)));
    const top5 = [...p].sort((a, b) => b - a).slice(0, 5).reduce((s, x) => s + x, 0);
    return {
        giorni: n,
        profit_days: win.length,
        loss_days: loss.length,
        pct_profit: n ? r2((win.length / n) * 100) : 0,
        tot: r2(tot),
        mean: r2(mean),
        max_day: n ? ord[n - 1] : 0,
        min_day: n ? ord[0] : 0,
        median: r2(median),
        avg_win: r2(media(win)),
        avg_loss: r2(media(loss)),
        wl_ratio: loss.length ? r2(media(win) / Math.abs(media(loss))) : 0,
        profit_factor: loss.length ? r2(win.reduce((s, x) => s + x, 0) / Math.abs(loss.reduce((s, x) => s + x, 0))) : 0,
        vol: r2(vol),
        sharpe: vol ? r2(mean / vol) : 0,
        kurtosis: r2(kurt),
        pct_top5: tot ? r2((top5 / tot) * 100) : 0,
        pct_worst: tot ? r2((ord[0] / tot) * 100) : 0,
        tempo_medio_giorno: 74,
        guadagno_orario_medio: r2(mean / (74 / 60)),
        profit_per_stake: stake ? tot / stake : 0,
        stake_medio_giorno: n ? r2(stake / n) : 0,
        media_trade_giorno: n ? nTrade / n : 0,
        giornate_perdita_gt_stake: 1,
        max_drawdown: r2(maxDd),
        recovery_factor: maxDd ? r2(tot / Math.abs(maxDd)) : 0,
        calmar: maxDd ? r2(tot / Math.abs(maxDd)) : 0,
        ulcer_index: r2(ulcer),
        upi: ulcer ? r2(mean / ulcer) : 0,
        downside_dev: r2(downside),
        sortino: downside ? r2(mean / downside) : 0,
        cvar_5: r2(media(peggiori)),
        max_dd_duration_days: durata,
    };
}

const PER_STRATEGIA: ByStrategia[] = [
    { strategia: 'Lay the Draw', n: 21, n_won: 13, win_rate: 0.619, stake: 260, net_pnl: 18.3, roi: 0.0704, profit_factor: 1.5 },
    { strategia: 'Back Under 2.5', n: 10, n_won: 5, win_rate: 0.5, stake: 120, net_pnl: -2.0, roi: -0.0167, profit_factor: 0.9 },
    { strategia: 'Lay Over 3.5', n: 7, n_won: 5, win_rate: 0.714, stake: 90, net_pnl: 9.9, roi: 0.11, profit_factor: 2.1 },
    { strategia: 'Back Over 2.5', n: 6, n_won: 3, win_rate: 0.5, stake: 66, net_pnl: 1.4, roi: 0.0212, profit_factor: 1.1 },
];

const PER_LEGA: ByLeague[] = [
    { league_id: 135, league_name: 'Serie A', n: 18, n_won: 11, win_rate: 0.611, stake: 210, net_pnl: 22.4, roi: 0.1067, profit_factor: 1.6 },
    { league_id: 140, league_name: 'La Liga', n: 9, n_won: 4, win_rate: 0.444, stake: 120, net_pnl: -14.2, roi: -0.1183, profit_factor: 0.7 },
    { league_id: 39, league_name: 'Premier League', n: 11, n_won: 6, win_rate: 0.545, stake: 140, net_pnl: 6.1, roi: 0.0436, profit_factor: 1.2 },
    { league_id: 78, league_name: 'Bundesliga', n: 6, n_won: 5, win_rate: 0.833, stake: 66, net_pnl: 11.3, roi: 0.1712, profit_factor: 2.4 },
];

// ------------------------------------------------------------------ trade

const CONTESTO_INTER: TradeContext = {
    predictions: {
        advice: 'Double chance : Inter or draw', under_over_line: '-2.5',
        goals_home_line: '-2.5', goals_away_line: '-1.5',
        percent_home: 58, percent_draw: 25, percent_away: 17, winner_name: 'Inter',
    },
    directions: {
        markets: [
            { market: '1x2', direction: 'H', concordi: ['ml', 'api', 'poisson'], motori_totali: 4, affidabilita: 0.58, engines: {} },
            { market: 'over_2_5', direction: 'Over', concordi: ['ml', 'poisson'], motori_totali: 4, affidabilita: 0.61, engines: {} },
        ],
    },
    result: { home_goals: 2, away_goals: 0, total_goals: 2, outcome: 'H', status: 'FT', ft: '2-0' },
    hits: { '1x2': true, over_2_5: false },
};

type Riga = Pick<PersonalTrade,
    'id' | 'trade_date' | 'betfair_event_id' | 'league_name' | 'league_id' | 'country' | 'home_team'
    | 'away_team' | 'result_ft' | 'strategia' | 'side' | 'entry_odds' | 'stake' | 'liability' | 'coverage'
    | 'net_pnl' | 'time_operative_min' | 'status' | 'market' | 'selection' | 'timing' | 'entry_minute'>;

function trade(r: Riga, context: TradeContext | null): PersonalTrade {
    const gross = r.net_pnl == null ? null : r2(r.net_pnl > 0 ? r.net_pnl / 0.95 : r.net_pnl);
    return {
        ...r,
        watchlist_id: null,
        fixture_id: 1290000 + r.id,
        kickoff: `${r.trade_date}T18:45:00Z`,
        line: r.market === 'over_2_5' ? 2.5 : r.market === 'over_3_5' ? 3.5 : null,
        exit_odds: null,
        entry_score: r.timing === 'live' ? '0-0' : null,
        exchange: 'betfair',
        commission: 0.05,
        gross_pnl: gross,
        roi: r.net_pnl == null ? null : r2(r.net_pnl / r.stake),
        hourly_yield: r.net_pnl != null && r.time_operative_min ? r2(r.net_pnl / (r.time_operative_min / 60)) : null,
        edge_at_entry: 0.041,
        model_prob: 0.561,
        implied_prob: 0.52,
        affidabilita: 0.58,
        concordi: 3,
        motori_totali: 4,
        followed_advice: r.id % 2 === 1,
        comment: null,
        tags: [],
        created_at: `${r.trade_date}T19:02:00Z`,
        updated_at: `${r.trade_date}T21:10:00Z`,
        legs: [],
        pnl_source: 'actual',
        entry_source: r.id === 4 ? 'manual' : 'import',
        commission_amount: gross != null && r.net_pnl != null ? r2(gross - r.net_pnl) : null,
        betfair_market_id: `1.24${r.id}00120`,
        betfair_bet_id: `3.22119${r.id}04`,
        season_year: 2026,
        context,
    };
}

const TRADE: PersonalTrade[] = [
    trade({
        id: 1, trade_date: '2026-09-30', betfair_event_id: '34790012', league_name: 'Serie A', league_id: 135,
        country: 'Italia', home_team: 'Inter', away_team: 'Torino', result_ft: '2-0', strategia: 'Lay the Draw',
        side: 'lay', entry_odds: 3.6, stake: 10, liability: 26, coverage: 12, net_pnl: 8.12, time_operative_min: 45,
        status: 'WON', market: '1x2', selection: 'D', timing: 'live', entry_minute: 22,
    }, CONTESTO_INTER),
    trade({
        id: 2, trade_date: '2026-09-29', betfair_event_id: '34784455', league_name: 'La Liga', league_id: 140,
        country: 'Spagna', home_team: 'Getafe', away_team: 'Celta', result_ft: '1-1', strategia: 'Lay the Draw',
        side: 'lay', entry_odds: 3.3, stake: 10, liability: 23, coverage: null, net_pnl: -23.0, time_operative_min: 90,
        status: 'LOST', market: '1x2', selection: 'D', timing: 'prematch', entry_minute: null,
    }, null),
    trade({
        id: 3, trade_date: '2026-09-28', betfair_event_id: '34779001', league_name: 'Premier League', league_id: 39,
        country: 'Inghilterra', home_team: 'Brentford', away_team: 'Everton', result_ft: null, strategia: 'Back Over 2.5',
        side: 'back', entry_odds: 1.92, stake: 10, liability: null, coverage: null, net_pnl: null, time_operative_min: null,
        status: 'OPEN', market: 'over_2_5', selection: 'Over', timing: 'prematch', entry_minute: null,
    }, null),
    trade({
        id: 4, trade_date: '2026-09-27', betfair_event_id: '34778730', league_name: 'Serie B', league_id: 136,
        country: 'Italia', home_team: 'Palermo', away_team: 'Bari', result_ft: '1-0', strategia: 'Back Under 2.5',
        side: 'back', entry_odds: 1.74, stake: 12, liability: null, coverage: 4, net_pnl: 6.4, time_operative_min: 30,
        status: 'PARTIAL', market: 'over_2_5', selection: 'Under', timing: 'live', entry_minute: 61,
    }, null),
    trade({
        id: 5, trade_date: '2026-09-26', betfair_event_id: '34778112', league_name: 'Bundesliga', league_id: 78,
        country: 'Germania', home_team: 'Mainz', away_team: 'Freiburg', result_ft: '0-0', strategia: 'Lay Over 3.5',
        side: 'lay', entry_odds: 4.4, stake: 10, liability: 34, coverage: null, net_pnl: 9.5, time_operative_min: 90,
        status: 'WON', market: 'over_3_5', selection: 'Over', timing: 'prematch', entry_minute: null,
    }, null),
    trade({
        id: 6, trade_date: '2026-09-26', betfair_event_id: '34778140', league_name: 'Serie A', league_id: 135,
        country: 'Italia', home_team: 'Atalanta', away_team: 'Genoa', result_ft: '3-1', strategia: 'Back Over 2.5',
        side: 'back', entry_odds: 1.88, stake: 10, liability: null, coverage: null, net_pnl: 8.36, time_operative_min: 55,
        status: 'WON', market: 'over_2_5', selection: 'Over', timing: 'prematch', entry_minute: null,
    }, null),
    trade({
        id: 7, trade_date: '2026-09-25', betfair_event_id: '34776610', league_name: 'Premier League', league_id: 39,
        country: 'Inghilterra', home_team: 'Brighton', away_team: 'Wolves', result_ft: '2-2', strategia: 'Back Under 2.5',
        side: 'back', entry_odds: 2.06, stake: 12, liability: null, coverage: null, net_pnl: -12.0, time_operative_min: 80,
        status: 'LOST', market: 'over_2_5', selection: 'Under', timing: 'live', entry_minute: 35,
    }, null),
    trade({
        id: 8, trade_date: '2026-09-24', betfair_event_id: '34775530', league_name: 'Serie A', league_id: 135,
        country: 'Italia', home_team: 'Napoli', away_team: 'Lazio', result_ft: '1-0', strategia: 'Lay the Draw',
        side: 'lay', entry_odds: 3.45, stake: 8, liability: 19.6, coverage: 8, net_pnl: 6.2, time_operative_min: 38,
        status: 'WON', market: '1x2', selection: 'D', timing: 'live', entry_minute: 18,
    }, null),
];

const CASSA: CashSummary = {
    movements: [
        { id: 2, transaction_id: '41892237', ts: '2026-09-21T09:14:00Z', move_date: '2026-09-21', type: 'WITHDRAWAL', amount: -200, balance: 1642.37, description: 'Prelievo su conto bancario' },
        { id: 1, transaction_id: '41790012', ts: '2026-09-02T07:30:00Z', move_date: '2026-09-02', type: 'DEPOSIT', amount: 500, balance: 1842.37, description: 'Deposito con carta' },
    ],
    deposits: 500,
    withdrawals: -200,
    net_cash: 300,
    n: 2,
};

// ------------------------------------------------------------------ letture

export async function getPersonalReport(filters: ReportFilters = {}): Promise<ReportData> {
    const daily = serie(filters.from, filters.to);
    return {
        daily,
        metrics: metriche(daily),
        by_strategia: PER_STRATEGIA.map((r) => ({ ...r })),
        by_league: PER_LEGA.map((r) => ({ ...r })),
        advice: { n_followed: 34, n_off_advice: 12, roi_followed: 0.062, roi_off_advice: -0.038 },
        discarded: {
            n: 19,
            by_reason: [
                { reason: 'quota_bassa', n: 8 }, { reason: 'edge_insufficiente', n: 6 }, { reason: 'formazioni', n: 5 },
            ],
        },
    };
}

export async function getPersonalTrades(filters: ReportFilters = {}): Promise<PersonalTrade[]> {
    return TRADE
        .filter((t) => (!filters.from || t.trade_date >= filters.from) && (!filters.to || t.trade_date <= filters.to))
        .filter((t) => !filters.status || t.status === filters.status)
        .filter((t) => !filters.strategia || t.strategia.toLowerCase().includes(filters.strategia.toLowerCase()))
        .slice(0, filters.limit ?? 200)
        .map((t) => ({ ...t }));
}

export async function getCashMovements(_from?: string | null, _to?: string | null): Promise<CashSummary> {
    return { ...CASSA, movements: CASSA.movements.map((m) => ({ ...m })) };
}
