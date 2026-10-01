// ============================================================================
// omegaMissioniFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /omega (Missione).
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/lib/omegaMissions' con questo file: si ri-esporta
// TUTTO il modulo vero (percorso RELATIVO) e si ridefiniscono solo la lettura
// `fetchMissions` e la sottoscrizione `subscribeOmegaMissions` (nessun
// evento), con le stesse chiavi e gli stessi tipi del vero (`MissionsPayload`,
// `MissionRow`). Le scritture (attiva, ferma, segui) restano quelle vere: dal
// client Supabase finto non partono.
//
// Missioni della giornata (prototipo `s_calcio.js`): Inter-Torino attiva in
// 2T (58' 1-0, gamba 1T regolata +0,95, gamba 2T aperta), Real Betis-Getafe
// attiva in 1T, Feyenoord-AZ Alkmaar finita. Obiettivo 14,70 EUR a partita.
// ============================================================================
import type { MissionLeg, MissionRow, MissionsPayload, MissionTrade } from '../lib/omegaMissions';
import { EV, KO, OGGI, alle, fa } from './giornataBot';

export * from '../lib/omegaMissions';

function gamba(realized: number | null, liability: number, open: number, settled: number, trades: MissionTrade[], locked: number | null = null): MissionLeg {
    return { realized, open_liability: liability, n_open: open, n_settled: settled, locked_pnl: locked, reconciling_liability: 0, trades };
}

function lay(id: number, runner: string, price: number, status: string, pnl: number | null, minute: number, score: string, placed: string): MissionTrade {
    return {
        id, runner_name: runner, side: 'lay', price, size: 1, liability: Math.round((price - 1) * 100) / 100,
        status, pnl, mode: 'paper', minute_at_entry: minute, score_at_entry: score, placed_at: placed,
        origin: 'auto', closes_trade_id: null, settled_at: status === 'open' ? null : placed, meta: {},
    };
}

const INTER: MissionRow = {
    event_id: EV.inter, event_name: 'Inter v Torino', kickoff: KO.inter, mission_date: OGGI, target: 14.7,
    status: 'active', phase_now: '2t', minute: 58, score_home: 1, score_away: 0, score_status: 'live',
    suggestion_ht: null,
    suggestion_ft: {
        market_id: '1.248120012', market_name: 'Risultato esatto', market_type: 'CORRECT_SCORE',
        selection_id: 5, runner_name: '2 - 1', lay_price: 24, lay_size: 38,
        advisor: {
            matched_fixture_id: 1208833, poisson_prob: 0.031, freq_league: { p: 0.044, n: 1520 },
            h2h: { n_meetings: 12, n_score: 1 }, sources: { poisson: 'fixture', lega: 'storico' },
        },
        updated_at: fa(2),
    },
    suggestion_scalp: {
        market_id: '1.248120016', market_name: 'Over/Under 3.5', market_type: 'OVER_UNDER_35',
        selection_id: 47979, runner_name: 'Under 3.5 Goals', back_price: 1.22, back_size: 412, line: 3.5,
        updated_at: fa(2),
    },
    error: null, created_at: alle('07:20'), updated_at: fa(2),
    legs: {
        ht_cs: gamba(0.95, 0, 0, 1, [lay(8301, '0 - 0', 8.4, 'won', 0.95, 22, '0-0', alle('07:47'))]),
        ft_cs: gamba(null, 11, 1, 0, [lay(8302, '1 - 1', 12, 'open', null, 51, '1-0', alle('08:31'))]),
    },
    scalper: null, followed: true, recording: true,
};

const BETIS: MissionRow = {
    event_id: EV.betis, event_name: 'Real Betis v Getafe', kickoff: KO.betis, mission_date: OGGI, target: 14.7,
    status: 'active', phase_now: '1t', minute: 31, score_home: 0, score_away: 0, score_status: 'live',
    suggestion_ht: {
        market_id: '1.248120443', market_name: 'Risultato esatto primo tempo', market_type: 'HALF_TIME_SCORE',
        selection_id: 6, runner_name: '2 - 0', lay_price: 34, lay_size: 22, advisor: null, updated_at: fa(3),
    },
    suggestion_ft: null, suggestion_scalp: null,
    error: null, created_at: alle('08:01'), updated_at: fa(3),
    legs: { ht_cs: gamba(null, 0, 0, 0, []), ft_cs: null },
    scalper: null, followed: true, recording: false,
};

const FEYENOORD: MissionRow = {
    event_id: EV.feyenoord, event_name: 'Feyenoord v AZ Alkmaar', kickoff: KO.feyenoord, mission_date: OGGI, target: 14.7,
    status: 'closed', phase_now: 'finita', minute: 90, score_home: 1, score_away: 1, score_status: 'finished',
    suggestion_ht: null, suggestion_ft: null, suggestion_scalp: null,
    error: null, created_at: alle('05:50'), updated_at: alle('07:52'),
    legs: {
        ht_cs: gamba(0.62, 0, 0, 1, [lay(8201, '2 - 0', 26, 'won', 0.95, 31, '0-0', alle('06:31'))]),
        ft_cs: gamba(0.95, 0, 0, 1, [lay(8203, '0 - 3', 34, 'won', 0.95, 62, '1-1', alle('07:17'))]),
    },
    scalper: null, followed: false, recording: false,
};

export async function fetchMissions(): Promise<MissionsPayload> {
    return {
        missions: [INTER, BETIS, FEYENOORD].map((m) => ({ ...m })),
        summary: { missions_total: 3, missions_active: 2 },
    };
}

export function subscribeOmegaMissions(_onChange: () => void): () => void {
    return () => { /* anteprima: nessun canale */ };
}
