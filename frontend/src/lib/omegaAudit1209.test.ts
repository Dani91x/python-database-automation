// ============================================================================
// Test di REGRESSIONE dell'audit di chiarezza del 12/09/2026 su /omega.
//
// Difetti che questi test impediscono di riportare indietro:
//  - `no_runner_by_model` (e altri motivi del servizio) mostrati come chiave
//    inglese nuda nel feed "Attività del servizio";
//  - la lista partite che mostrava 73 eventi di tre giorni prima marcati
//    "FINITA" mentre il contatore diceva "Eventi oggi 0" (get_omega_events
//    restituisce tutta la cache SENZA filtro di data);
//  - il tetto dell'obiettivo giornaliero dichiarato dalla UI (1 000 000) più
//    alto del CHECK sul DB (100 000): il "Salva" falliva con un errore SQL;
//  - due toast contraddittori per UNA sola posizione chiusa in green-up.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    OMEGA_ERROR_REASON, omegaReasonText, OMEGA_DAILY_GOAL_MAX,
    eventIsOperable, filterEventsInWindow, eventsCacheUpdatedAt,
    settlementNotifications, activityLine,
    type OmegaActivityRow, type OmegaTrade,
} from './omega';

describe('OMEGA_DAILY_GOAL_MAX — lo stesso tetto del CHECK sul DB', () => {
    it('vale 100 000 (migrations/omega_bot.sql: daily_goal <= 100000)', () => {
        expect(OMEGA_DAILY_GOAL_MAX).toBe(100000);
    });
});

describe('motivi del servizio — mai una chiave inglese nuda sotto gli occhi del trader', () => {
    // vocabolario letto riga per riga in Betfair/omega/omega_service.py
    // (payload.reason dei kind `skip` / `error`) e safe_strategy/execution.py
    const REASONS = [
        'no_runner_by_model', 'no_runner_in_range', 'no_model_lambdas', 'no_live_state',
        'no_market', 'no_correct_score_market', 'no_legs_remaining', 'already_reserved',
        'insufficient_liquidity', 'max_open_liability', 'market_suspended', 'market_closed',
        'market_inactive', 'paper_no_fill', 'live_not_matched', 'reserve_no_id',
        'target_zero_goal_reached', 'scan_event_failed', 'book_error', 'catalogue_error',
        'fetch_failed', 'reconcile_orphan_old', 'request_missing', 'cycle_exception',
        'greenup_attempts_exhausted', 'greenup_candidates_failed', 'place_exception_reconciling',
        'chiusura_non_ancora_confermata',
    ];

    it('ogni motivo scritto dal servizio ha una frase italiana', () => {
        for (const k of REASONS) {
            const txt = OMEGA_ERROR_REASON[k];
            expect(txt, `motivo senza traduzione: ${k}`).toBeTruthy();
            expect(txt, `chiave nuda per ${k}`).not.toBe(k);
            expect(/^[a-z0-9_]+$/.test(txt ?? ''), `sembra ancora una chiave: ${k}`).toBe(false);
        }
    });

    it('no_runner_by_model (il più frequente nel feed) non è più una chiave', () => {
        expect(omegaReasonText('no_runner_by_model'))
            .toBe('nessun risultato sotto la P(modello) massima');
    });

    it('i motivi COSTRUITI con un numero dentro sono tradotti', () => {
        expect(omegaReasonText('market_gone_3h_consecutive'))
            .toBe('mercato sparito da Betfair da 3 h di fila');
    });

    it('un motivo sconosciuto resta leggibile (chiave nuda) e il vuoto è null', () => {
        expect(omegaReasonText('qualcosa_di_nuovo')).toBe('qualcosa_di_nuovo');
        expect(omegaReasonText('')).toBeNull();
        expect(omegaReasonText(null)).toBeNull();
    });

    it('la riga di attività usa la traduzione, non la chiave', () => {
        const row: OmegaActivityRow = {
            id: 1, ts: '2026-09-12T10:50:00Z', kind: 'skip',
            payload: {
                event_id: '36050104', leg: 'ft_cs', minute: 60, score: '1-1',
                reason: 'no_runner_by_model',
            },
        };
        const line = activityLine(row, 'Roma v Lazio');
        expect(line).toContain('nessun risultato sotto la P(modello) massima');
        expect(line).not.toContain('no_runner_by_model');
    });
});

describe('finestra operativa degli eventi (get_omega_events non filtra per data)', () => {
    const NOW = Date.parse('2026-09-12T12:00:00Z');
    const iso = (deltaH: number) => new Date(NOW + deltaH * 3600_000).toISOString();

    it('una partita finita (calcio d’inizio oltre 3 h fa) NON è operabile', () => {
        expect(eventIsOperable(iso(-4), NOW)).toBe(false);
        expect(eventIsOperable('2026-09-09T16:00:00Z', NOW)).toBe(false);
    });

    it('pre-partita e in corso sono operabili', () => {
        expect(eventIsOperable(iso(+2), NOW)).toBe(true);
        expect(eventIsOperable(iso(-1), NOW)).toBe(true);
        expect(eventIsOperable(iso(-3), NOW)).toBe(true);   // esattamente al limite
    });

    it('senza orario leggibile non si può escludere: resta in lista', () => {
        expect(eventIsOperable(null, NOW)).toBe(true);
        expect(eventIsOperable('non-una-data', NOW)).toBe(true);
    });

    it('la lista tiene SOLO le partite operabili (bug 12/09: 73 partite del 09/09)', () => {
        const events = [
            { event_id: 'a', open_date: '2026-09-09T16:00:00Z' },
            { event_id: 'b', open_date: iso(+1) },
            { event_id: 'c', open_date: iso(-1) },
            { event_id: 'd', open_date: '2026-09-09T21:00:00Z' },
        ];
        expect(filterEventsInWindow(events, NOW).map((e) => e.event_id)).toEqual(['b', 'c']);
    });

    it('età della cache = `updated_at` più recente (null se non c’è)', () => {
        expect(eventsCacheUpdatedAt([
            { updated_at: '2026-09-09T19:59:00Z' },
            { updated_at: '2026-09-09T20:10:00Z' },
            { updated_at: null },
        ])).toBe('2026-09-09T20:10:00Z');
        expect(eventsCacheUpdatedAt([])).toBeNull();
    });
});

describe('settlementNotifications — UN solo toast per POSIZIONE', () => {
    const base = {
        event_id: 'e1', event_name: 'Roma v Lazio', market_id: '1.1', selection_id: 1,
        runner_name: '3 - 2', side: 'lay', mode: 'paper', price: 40, size: 1,
        liability: 39, target: null, minute_at_entry: null, score_at_entry: null,
        kickoff: null, bet_id: 'b', placed_at: '2026-09-12T10:00:00Z', meta: {},
    };
    const t = (o: Record<string, unknown>): OmegaTrade => ({
        ...base, id: 1, status: 'won', pnl: 0, settled_at: '2026-09-12T12:00:00Z', ...o,
    } as unknown as OmegaTrade);

    it('apertura + chiusura regolate insieme: parla SOLO l’apertura, col P&L di posizione', () => {
        // prima: «💰 +24,24 €» e «⚠️ −22,00 €» per un +2,24 € reale
        const out = settlementNotifications([
            t({ id: 1, status: 'lost', pnl: -22, meta: { position_pnl: 2.24, position_id: 1 } }),
            t({ id: 2, status: 'won', pnl: 24.24, side: 'back', closes_trade_id: 1 }),
        ], new Set());
        expect(out).toHaveLength(1);
        expect(out[0].tradeId).toBe(1);
        expect(out[0].pnl).toBe(2.24);
    });

    it('senza position_pnl somma apertura + chiusure regolate', () => {
        const out = settlementNotifications([
            t({ id: 1, status: 'lost', pnl: -22 }),
            t({ id: 2, status: 'won', pnl: 24.24, side: 'back', closes_trade_id: 1 }),
        ], new Set());
        expect(out).toHaveLength(1);
        expect(out[0].pnl).toBe(2.24);
    });

    it('una riga già vista non notifica due volte', () => {
        const seen = new Set<number>();
        expect(settlementNotifications([t({ id: 9, pnl: 5 })], seen)).toHaveLength(1);
        expect(settlementNotifications([t({ id: 9, pnl: 5 })], seen)).toHaveLength(0);
    });

    it('chiusura la cui apertura era già regolata: notifica e si dichiara chiusura', () => {
        const seen = new Set<number>([1]);
        const out = settlementNotifications([
            t({ id: 2, status: 'won', pnl: 3, side: 'back', closes_trade_id: 1 }),
        ], seen);
        expect(out).toHaveLength(1);
        expect(out[0].closing).toBe(true);
        expect(out[0].pnl).toBe(3);
    });

    it('void: P&L 0 e nessun numero inventato', () => {
        const out = settlementNotifications([t({ id: 5, status: 'void', pnl: 0 })], new Set());
        expect(out[0].isVoid).toBe(true);
        expect(out[0].pnl).toBe(0);
    });

    it('le righe non regolate non notificano', () => {
        expect(settlementNotifications(
            [t({ id: 7, status: 'open', settled_at: null })], new Set(),
        )).toHaveLength(0);
    });
});

// CERT. 12/09 (review) — lo STESSO guadagno non puo' essere annunciato due
// volte: se la chiusura e' gia' stata notificata da sola in un giro
// precedente, il toast dell'apertura non deve risommarla.
describe('settlementNotifications — nessun doppio annuncio', () => {
    it('una chiusura gia annunciata non rientra nel P&L dell apertura', () => {
        const chiusura = {
            id: 2, closes_trade_id: 1, status: 'won', settled_at: '2026-09-12T10:00:00Z',
            pnl: 24.24, event_id: 'e1', event_name: 'A v B', side: 'back',
            selection_name: 'X', meta: {},
        } as unknown as Parameters<typeof settlementNotifications>[0][number];
        const apertura = {
            id: 1, closes_trade_id: null, status: 'lost', settled_at: '2026-09-12T10:01:00Z',
            pnl: -22, event_id: 'e1', event_name: 'A v B', side: 'lay',
            selection_name: 'X', meta: {},
        } as unknown as Parameters<typeof settlementNotifications>[0][number];
        const seen = new Set<number>();
        // giro 1: si regola solo la chiusura -> annunciata da sola
        const g1 = settlementNotifications([chiusura], seen);
        expect(g1).toHaveLength(1);
        expect(g1[0].pnl).toBeCloseTo(24.24, 2);
        // giro 2: si regola l'apertura -> annuncia SOLO il proprio P&L
        const g2 = settlementNotifications([chiusura, apertura], seen);
        expect(g2).toHaveLength(1);
        expect(g2[0].tradeId).toBe(1);
        expect(g2[0].pnl).toBeCloseTo(-22, 2);
    });

    it('apertura e chiusura regolate INSIEME: un solo toast col netto di posizione', () => {
        const chiusura = {
            id: 2, closes_trade_id: 1, status: 'won', settled_at: '2026-09-12T10:00:00Z',
            pnl: 24.24, event_id: 'e1', event_name: 'A v B', side: 'back',
            selection_name: 'X', meta: {},
        } as unknown as Parameters<typeof settlementNotifications>[0][number];
        const apertura = {
            id: 1, closes_trade_id: null, status: 'lost', settled_at: '2026-09-12T10:00:00Z',
            pnl: -22, event_id: 'e1', event_name: 'A v B', side: 'lay',
            selection_name: 'X', meta: {},
        } as unknown as Parameters<typeof settlementNotifications>[0][number];
        const out = settlementNotifications([apertura, chiusura], new Set<number>());
        expect(out).toHaveLength(1);
        expect(out[0].pnl).toBeCloseTo(2.24, 2);
    });
});
