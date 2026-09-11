// ============================================================================
// Attività del servizio Safe Strategy (audit H-16 · design §6).
// Ogni `kind` che il backend scrive DEVE avere un'etichetta italiana: un badge
// grigio con una parola inglese sotto gli occhi di un trader è un bug.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    SAFE_ACTIVITY_EXTRA, safeActivityMeta, safeActivityLine, safeReasonLabel, safeSourceLabel,
} from './safeActivity';

/** TUTTI i kind del contratto del servizio (bot_service.py, 11/09/2026). */
const KINDS = [
    'stop', 'error', 'params_invalid', 'params_clamped', 'place', 'place_pending',
    'place_retry', 'place_exhausted', 'place_exception', 'skip', 'risk_block',
    'confirm_failed', 'flumine_enqueue', 'reconcile_error', 'reconciled_open',
    'reconciled_free', 'reconciled_error', 'exit', 'exit_hold', 'exit_wait',
    'exit_retry', 'exit_failed', 'cashout', 'cashout_error', 'cancel',
    'cancel_rejected', 'combo_incomplete', 'settle', 'settle_position',
    'settle_wait', 'settle_error', 'settle_orphan_closing', 'market_missing',
    'feed_blind', 'feed_back', 'flumine_fill', 'flumine_no_fill',
    'flumine_cancel_timeout', 'flumine_recovered', 'flumine_live_freed',
    'flumine_live_orphan', 'flumine_poll_error',
];

/** kind che l'utente DEVE vedere (rossi, mai sepolti nella lista) */
const CRITICAL = [
    'error', 'params_invalid', 'place_exhausted', 'place_exception', 'confirm_failed',
    'risk_block', 'combo_incomplete', 'reconcile_error', 'reconciled_error',
    'exit_failed', 'cashout_error', 'cancel_rejected', 'settle_error',
    'settle_orphan_closing', 'market_missing', 'feed_blind',
    'flumine_cancel_timeout', 'flumine_live_orphan', 'flumine_poll_error',
];

describe('safeActivityMeta — ogni kind del servizio ha un nome italiano', () => {
    it('nessun kind resta senza etichetta o in inglese nudo', () => {
        for (const k of KINDS) {
            const m = safeActivityMeta(k);
            expect(SAFE_ACTIVITY_EXTRA[k], `kind non mappato: ${k}`).toBeTruthy();
            expect(m.label, k).not.toMatch(/kind sconosciuto/);
            expect(m.label, k).toBe(m.label.trim());
            expect(m.label.length, k).toBeGreaterThan(2);
            expect(m.cls, k).toMatch(/bg-/);
        }
    });

    it('i kind che richiedono attenzione sono marcati critical', () => {
        for (const k of CRITICAL) {
            expect(safeActivityMeta(k).critical, `manca critical: ${k}`).toBe(true);
        }
        // …e quelli informativi no
        for (const k of ['place', 'settle', 'feed_back', 'reconciled_free', 'skip']) {
            expect(safeActivityMeta(k).critical, k).not.toBe(true);
        }
    });

    it('etichette chiave, in italiano e senza ambiguità', () => {
        expect(safeActivityMeta('skip').label).toBe('NON ENTRATO');
        expect(safeActivityMeta('risk_block').label).toBe('BLOCCATO DAL RISCHIO');
        expect(safeActivityMeta('exit_failed').label).toBe('USCITA FALLITA');
        expect(safeActivityMeta('settle_position').label).toBe('POSIZIONE REGOLATA');
        expect(safeActivityMeta('market_missing').label).toBe('MERCATO SPARITO DAL FEED');
        expect(safeActivityMeta('params_invalid').label).toBe('PARAMETRI NON VALIDI');
    });

    it('un kind mai visto viene tradotto parola per parola, mai lasciato in inglese', () => {
        expect(safeActivityMeta('exit_cover_retry').label).toBe('USCITA · COPERTURA · RITENTO');
        expect(safeActivityMeta('zzz_qqq').label).toMatch(/kind sconosciuto/);
    });
});

describe('safeReasonLabel / safeSourceLabel', () => {
    it('i motivi tecnici del servizio diventano italiano leggibile', () => {
        expect(safeReasonLabel('place_exception_reconciling')).toBe('ordine a esito ignoto: in verifica su Betfair');
        expect(safeReasonLabel('daily_liability_cap')).toBe('cap di liability giornaliera raggiunto');
        expect(safeReasonLabel('quote_non_disponibili')).toMatch(/quote non disponibili/);
        expect(safeReasonLabel('un motivo scritto a mano')).toBe('un motivo scritto a mano');
        expect(safeReasonLabel(null)).toBeNull();
    });

    it('la sorgente delle quote è dichiarata in italiano', () => {
        expect(safeSourceLabel('feed')).toBe('quote dal feed dello scanner');
        expect(safeSourceLabel('rest')).toBe('quote dal book Betfair');
        expect(safeSourceLabel(null)).toBeNull();
    });
});

describe('safeActivityLine — la riga dice cosa è successo, coi formati unici', () => {
    it('non entrato: partita, mercato e MOTIVO', () => {
        expect(safeActivityLine({
            event_name: 'Roma vs Lazio', market_type: 'OVER_UNDER_25', side: 'back',
            selection_name: 'Under 2.5', size: 5, price: 2.1, reason: 'spread_troppo_ampio',
        })).toBe('Roma vs Lazio · BACK Under 2.5 · OVER_UNDER_25 · 5,00 € @ 2,10 · spread troppo ampio');
    });

    it('uscita che ritenta: tentativi e ora del prossimo tentativo (Roma)', () => {
        const line = safeActivityLine({
            event_name: 'Roma vs Lazio', exit_kind: 'loss', attempts: 2,
            next_retry_at: '2026-09-11T16:07:00Z', trade_id: 41,
        });
        expect(line).toContain('uscita: loss');
        expect(line).toContain('2° tentativo');
        expect(line).toContain('ritento alle 18:07');
        expect(line).toContain('#41');
    });

    it('combinazione incompleta: quali gambe restano in sospeso', () => {
        expect(safeActivityLine({ event_name: 'X vs Y', pending_ids: [51, 52] }))
            .toBe('X vs Y · gambe in sospeso #51 #52');
    });

    it('mercato sparito: quante volte di fila', () => {
        expect(safeActivityLine({ event_name: 'X vs Y', fails: 3 }))
            .toBe('X vs Y · 3 volte di fila senza mercato');
    });

    it('parametri corretti: salvato → in uso, chiave per chiave', () => {
        expect(safeActivityLine({ corrections: { commission_pct: { stored: 50, effective: 20 } } }))
            .toBe('commission_pct: salvato 50 → in uso 20');
    });

    it('parametri non validi: chiavi corrette DAVVERO sul database', () => {
        expect(safeActivityLine({ persisted: ['variants'] }))
            .toBe('corrette sul database: variants');
    });

    it('cash out: sorgente delle quote e P&L bloccato', () => {
        const line = safeActivityLine({ event_name: 'Roma vs Lazio', locked_pnl: -22.1, source: 'rest' });
        expect(line).toContain('−22,10 €');
        expect(line).toContain('quote dal book Betfair');
    });

    it('payload vuoto o sconosciuto: mai una riga muta', () => {
        expect(safeActivityLine(null)).toBe('');
        expect(safeActivityLine({})).toBe('');
        expect(safeActivityLine({ qualcosa: 1 })).toContain('qualcosa');
    });
});
