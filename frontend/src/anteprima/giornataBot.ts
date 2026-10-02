// ============================================================================
// giornataBot.ts - SOLO PER L'ANTEPRIMA POPOLATA delle pagine dei bot calcio
// (/mike, /safe-strategy, /omega). Non e' importato dall'app e non e' un alias:
// e' la giornata COMUNE ai finti `mikeFinto.ts`, `safeBotFinto.ts`,
// `safeRadarFinto.ts`, `omegaFinto.ts`, `omegaMissioniFinto.ts`,
// `scanFinto.ts` e `storicoFinto.ts`, cosi' le tre pagine raccontano la stessa
// mattina con gli stessi id, gli stessi punteggi e le stesse quote.
//
// La mattina e' quella del prototipo `AUDIT_2026-10-01/REDESIGN/prototipo/js/`
// (`s_calcio.js`, `data.js`): Inter-Torino 58' 1-0, Real Betis-Getafe 31' 0-0,
// Sassuolo-Lecce 62' 1-0 in gioco; in attesa Bologna-Udinese (10:52),
// Brentford-Fulham, Lens-Nantes; tennis Sinner-Draper e Swiatek-Paolini.
// Gli id evento sono gli stessi di `controlRoomFinto.ts`.
// Orologio: 2026-10-01T08:38:00Z (10:38 a Roma), lo stesso di scatta.mjs.
// ============================================================================
import type {
    CalcioScanPayload, ScanCsSelection, ScanMarketBlock, ScanRow, ScanStatusRow, TennisScanPayload,
} from '../lib/safeStrategyScan';

// ------------------------------------------------------------------ orologio

export const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
/** giornata operativa (Europe/Rome) */
export const OGGI = '2026-10-01';
/** istante ISO `s` secondi prima di adesso */
export const fa = (s: number): string => new Date(ORA_MS - s * 1000).toISOString();
/** istante ISO a un'ora UTC di oggi, 'HH:MM' oppure 'HH:MM:SS' */
export const alle = (hhmm: string): string => `${OGGI}T${hhmm.length === 5 ? `${hhmm}:00` : hhmm}Z`;
/** comando dell'anteprima: non fa niente, come un servizio che non c'e' */
export const nulla = async (): Promise<void> => { /* anteprima: nessun comando */ };

// ------------------------------------------------------------------ eventi

export const EV = {
    inter: '34812001', betis: '34812044', sassuolo: '34812031',
    bologna: '34812102', brentford: '34812130', lens: '34812177', getafe: '34812260',
    atalanta: '34812190', napoli: '34812262',
    feyenoord: '34811920', benfica: '34811990', shanghai: '34811870',
    sinner: '34813501', swiatek: '34813522',
} as const;

/** calcio d'inizio (UTC) */
export const KO = {
    inter: alle('07:25'), betis: alle('08:07'), sassuolo: alle('07:21'),
    bologna: alle('08:52'), brentford: alle('09:22'), lens: alle('09:52'), getafe: alle('10:00'),
    atalanta: alle('10:22'), napoli: alle('12:52'),
    feyenoord: alle('06:00'), benfica: alle('05:30'), shanghai: alle('05:35'),
    sinner: alle('07:56'), swiatek: alle('08:26'),
} as const;

// ------------------------------------------------------------------ feed scanner

function sel(selection_id: number, name: string, back: number, lay: number, back_size: number, lay_size: number): ScanCsSelection {
    return { selection_id, name, back, lay, back_size, lay_size };
}

function ou(market_id: string, line: number, under: [number, number], over: [number, number], forMike = false): ScanMarketBlock {
    const code = String(line * 10).padStart(2, '0');
    return {
        market_id, status: 'OPEN', inplay: true, total_matched: 180000 + line * 40000,
        market_type: `OVER_UNDER_${code}`, line, ts_ms: ORA_MS - 1000, bet_delay: 5, for_mike: forMike,
        selections: [
            sel(47972 + line * 2, `Under ${line} Goals`, under[0], under[1], 410, 380),
            sel(47973 + line * 2, `Over ${line} Goals`, over[0], over[1], 120, 96),
        ],
    };
}

const MEDIA = { video: true, viz: true };

export const SCAN_INTER: CalcioScanPayload = {
    media: MEDIA, odds_ts_ms: ORA_MS - 1000,
    event_name: 'Inter v Torino', home: 'Inter', away: 'Torino', competition: 'Serie A',
    open_date: KO.inter, inplay: true, mo_market_id: '1.248120010', mo_status: 'OPEN',
    odds: {
        home: { selection_id: 44790, ltp: 1.38, back: 1.38, lay: 1.39, back_size: 1840, lay_size: 920 },
        draw: { selection_id: 58805, ltp: 5.6, back: 5.6, lay: 5.7, back_size: 310, lay_size: 240 },
        away: { selection_id: 44791, ltp: 11.5, back: 11.5, lay: 12, back_size: 95, lay_size: 70 },
    },
    minute: 58, score_home: 1, score_away: 0, red_home: 0, red_away: 0, pressure_index: 0.31,
    pre_ko: { home: 1.62, draw: 4.0, away: 5.6, captured_at: alle('07:24') },
    cs: {
        market_id: '1.248120012', status: 'OPEN', inplay: true, total_matched: 412000,
        selections: [
            sel(1, '0 - 0', 1000, 1000, 0, 0),
            sel(2, '1 - 0', 3.6, 3.7, 412, 230),
            sel(3, '2 - 0', 6.4, 6.6, 120, 88),
            sel(4, '1 - 1', 13, 13.5, 64, 52),
            sel(5, '2 - 1', 23, 24, 31, 38),
            sel(6, '3 - 0', 17, 18, 40, 33),
            sel(7, '2 - 2', 36, 38, 12, 22),
            sel(8, 'Any Other Home Win', 44, 46, 18, 25),
            sel(9, 'Any Other Away Win', 1000, 1000, 0, 0),
        ],
        any_other_home: { selection_id: 8, back: 44, lay: 46, back_size: 18, lay_size: 25 },
        any_other_away: { selection_id: 9, back: 1000, lay: 1000, back_size: 0, lay_size: 0 },
    },
    ht: { market_id: '1.248120013', status: 'CLOSED', inplay: true, total_matched: 98000, selections: [] },
    ou: [
        ou('1.248120015', 2.5, [1.7, 1.72], [2.36, 2.4]),
        ou('1.248120016', 3.5, [1.22, 1.23], [5.3, 5.5]),
        ou('1.248120017', 4.5, [1.07, 1.08], [13.5, 14.5], true),
    ],
};

export const SCAN_BETIS: CalcioScanPayload = {
    media: MEDIA, odds_ts_ms: ORA_MS - 1000,
    event_name: 'Real Betis v Getafe', home: 'Real Betis', away: 'Getafe', competition: 'La Liga',
    open_date: KO.betis, inplay: true, mo_market_id: '1.248120440', mo_status: 'OPEN',
    odds: {
        home: { selection_id: 62188, back: 2.02, lay: 2.04, back_size: 620, lay_size: 410 },
        draw: { selection_id: 58805, back: 3.25, lay: 3.3, back_size: 540, lay_size: 380 },
        away: { selection_id: 62190, back: 5.9, lay: 6, back_size: 150, lay_size: 120 },
    },
    minute: 31, score_home: 0, score_away: 0, red_home: 0, red_away: 0, pressure_index: 0.12,
    // scanner partito a partita iniziata: niente riferimento pre-KO (BASE e PUNTA n/d)
    pre_ko: null,
    cs: {
        market_id: '1.248120442', status: 'OPEN', inplay: true, total_matched: 96000,
        selections: [
            sel(1, '0 - 0', 5.4, 5.6, 140, 120),
            sel(2, '1 - 0', 5.8, 6, 130, 110),
            sel(4, '1 - 1', 7.6, 7.8, 90, 85),
        ],
        any_other_home: { selection_id: 8, back: 38, lay: 42, back_size: 14, lay_size: 20 },
        any_other_away: { selection_id: 9, back: 70, lay: 80, back_size: 6, lay_size: 9 },
    },
    ou: [
        ou('1.248120445', 2.5, [1.58, 1.6], [2.62, 2.66]),
        ou('1.248120446', 3.5, [1.22, 1.23], [5.2, 5.4]),
    ],
};

export const SCAN_SASSUOLO: CalcioScanPayload = {
    media: { video: false, viz: true }, odds_ts_ms: ORA_MS - 2000,
    event_name: 'Sassuolo v Lecce', home: 'Sassuolo', away: 'Lecce', competition: 'Serie A',
    open_date: KO.sassuolo, inplay: true, mo_market_id: '1.248120310', mo_status: 'OPEN',
    odds: {
        home: { selection_id: 70411, back: 1.29, lay: 1.3, back_size: 1420, lay_size: 760 },
        draw: { selection_id: 58805, back: 5.2, lay: 5.4, back_size: 210, lay_size: 160 },
        away: { selection_id: 70412, back: 21, lay: 22, back_size: 60, lay_size: 84 },
    },
    minute: 62, score_home: 1, score_away: 0, red_home: 0, red_away: 0, pressure_index: 0.22,
    pre_ko: { home: 1.66, draw: 4.0, away: 5.4, captured_at: alle('07:20') },
    cs: {
        market_id: '1.248120312', status: 'OPEN', inplay: true, total_matched: 54000,
        selections: [sel(2, '1 - 0', 2.9, 3, 210, 150), sel(8, 'Any Other Home Win', 30, 34, 10, 14)],
        any_other_home: { selection_id: 8, back: 30, lay: 34, back_size: 10, lay_size: 14 },
        any_other_away: null,
    },
};

function preMatch(nome: string, home: string, away: string, comp: string, ko: string, mo: string,
    o: [number, number, number]): CalcioScanPayload {
    return {
        media: MEDIA, odds_ts_ms: ORA_MS - 3000,
        event_name: nome, home, away, competition: comp, open_date: ko, inplay: false,
        mo_market_id: mo, mo_status: 'OPEN',
        odds: {
            home: { selection_id: 1001, back: o[0], lay: Math.round((o[0] + 0.01) * 100) / 100, back_size: 900, lay_size: 640 },
            draw: { selection_id: 58805, back: o[1], lay: Math.round((o[1] + 0.05) * 100) / 100, back_size: 410, lay_size: 300 },
            away: { selection_id: 1002, back: o[2], lay: Math.round((o[2] + 0.1) * 100) / 100, back_size: 260, lay_size: 190 },
        },
        minute: null, score_home: null, score_away: null, red_home: null, red_away: null,
        pre_ko: null, cs: null,
    };
}

export const SCAN_BOLOGNA = preMatch('Bologna v Udinese', 'Bologna', 'Udinese', 'Serie A', KO.bologna, '1.248121020', [1.83, 3.7, 4.9]);
export const SCAN_BRENTFORD = preMatch('Brentford v Fulham', 'Brentford', 'Fulham', 'Premier League', KO.brentford, '1.248121300', [2.3, 3.45, 3.3]);
export const SCAN_LENS = preMatch('Lens v Nantes', 'Lens', 'Nantes', 'Ligue 1', KO.lens, '1.248121770', [1.71, 3.9, 5.5]);

export const SCAN_SINNER: TennisScanPayload = {
    media: MEDIA, odds_ts_ms: ORA_MS - 1000,
    event_name: 'Sinner v Draper', p1: 'J. Sinner', p2: 'J. Draper', competition: 'ATP Pechino',
    open_date: KO.sinner, inplay: true, mo_market_id: '1.248135010', mo_status: 'OPEN',
    odds: {
        p1: { selection_id: 9020001, back: 1.24, lay: 1.25, back_size: 3100, lay_size: 2200 },
        p2: { selection_id: 9020002, back: 5, lay: 5.1, back_size: 410, lay_size: 380 },
    },
    sets: { p1: 1, p2: 0 }, games: { p1: 2, p2: 1 },
    pre_ko: { p1: 1.3, p2: 3.9, captured_at: alle('07:55') },
};

export const SCAN_SWIATEK: TennisScanPayload = {
    media: { video: true, viz: false }, odds_ts_ms: ORA_MS - 2000,
    event_name: 'Swiatek v Paolini', p1: 'I. Swiatek', p2: 'J. Paolini', competition: 'WTA Pechino',
    open_date: KO.swiatek, inplay: true, mo_market_id: '1.248135220', mo_status: 'OPEN',
    odds: {
        p1: { selection_id: 9030001, back: 1.46, lay: 1.47, back_size: 1200, lay_size: 900 },
        p2: { selection_id: 9030002, back: 3.1, lay: 3.15, back_size: 340, lay_size: 290 },
    },
    sets: { p1: 0, p2: 0 }, games: { p1: 3, p2: 3 },
    pre_ko: { p1: 1.42, p2: 3.2, captured_at: alle('08:25') },
};

/** righe di `safe_strategy_scan` (fonte unica del feed) */
export const RIGHE_SCAN: ScanRow[] = [
    { event_id: EV.inter, sport: 'calcio', payload: SCAN_INTER, updated_at: fa(1) },
    { event_id: EV.betis, sport: 'calcio', payload: SCAN_BETIS, updated_at: fa(1) },
    { event_id: EV.sassuolo, sport: 'calcio', payload: SCAN_SASSUOLO, updated_at: fa(2) },
    { event_id: EV.bologna, sport: 'calcio', payload: SCAN_BOLOGNA, updated_at: fa(3) },
    { event_id: EV.brentford, sport: 'calcio', payload: SCAN_BRENTFORD, updated_at: fa(4) },
    { event_id: EV.lens, sport: 'calcio', payload: SCAN_LENS, updated_at: fa(5) },
    { event_id: EV.sinner, sport: 'tennis', payload: SCAN_SINNER, updated_at: fa(1) },
    { event_id: EV.swiatek, sport: 'tennis', payload: SCAN_SWIATEK, updated_at: fa(2) },
];

/** battito dello scanner: vivo, in stream */
export const STATO_SCANNER: ScanStatusRow = {
    id: 'scanner',
    payload: {
        calcio_inplay: 33, tennis_inplay: 8, monitored: 41, dry: false, source: 'stream',
        stream_markets: 152, stream_connections: 2, stream_capacity: 400, last_error: null,
        started_at: alle('04:58'),
    },
    updated_at: fa(1),
};
