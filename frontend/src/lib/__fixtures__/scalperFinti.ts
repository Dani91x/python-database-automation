// ============================================================================
// scalperFinti.ts - i FINTI dello scalper calcio per i test (24/09).
//
// Parlano come il vero: una sessione ha le chiavi di `to_jsonb(scalper_control)`
// (migrations/scalper_bot.sql) + le quattro aggiunte da
// `get_scalper_control_room` (event_name, league_name, kickoff,
// ultima_attivita_at/kind); un ordine ha le colonne della SELECT della stessa
// RPC su `betfair_live_orders` (migrations/scalper_control_room_2026-09-24.sql).
// Solo per i test: nessun codice di produzione lo importa.
// ============================================================================
import type { SessioneScalper, OrdineScalper } from '@/lib/scalperControlRoom';

export function sessione(over: Partial<SessioneScalper> = {}): SessioneScalper {
    return {
        event_id: '35760084', status: 'running', mode: 'maker', dry_run: true, stake: 25,
        params: { scalp_ticks: 1 }, bias: null, bias_meta: { modalita: 'maker' },
        stats: { cycles: 2, pnl_locked: 0.4 }, error: null,
        requested_at: '2026-09-24T12:00:00.123456+00:00',
        started_at: '2026-09-24T12:00:04+00:00', stopped_at: null,
        heartbeat_at: '2026-09-24T12:10:00+00:00', updated_at: '2026-09-24T12:10:00+00:00',
        event_name: 'Inter v Milan', league_name: 'Serie A',
        kickoff: '2026-09-24T18:45:00+00:00',
        ultima_attivita_at: '2026-09-24T12:09:50+00:00', ultima_attivita_kind: 'fill',
        ...over,
    };
}

export function ordine(over: Partial<OrdineScalper> = {}): OrdineScalper {
    return {
        id: 1, bet_id: '100000000001', client_order_ref: 'a1b2c3d4e5f6-17', mode: 'paper',
        event_id: '35760084', market_id: '1.200', selection_id: 47972, side: 'back',
        order_type: 'LIMIT', price: 2.0, size: 10, size_matched: 10, size_remaining: 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 2.0,
        status: 'EXECUTION_COMPLETE', placed_at: '2026-09-24T12:01:00+00:00',
        matched_at: '2026-09-24T12:01:02+00:00', updated_at: '2026-09-24T12:01:02+00:00',
        source: 'runner', pnl_betfair: null, commissione_betfair: null,
        pnl_betfair_settled_at: null,
        ...over,
    };
}
