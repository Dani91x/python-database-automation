// ============================================================================
// Attività del servizio Safe Strategy (audit H-16 · design §6).
// Ogni `kind` che il backend scrive DEVE avere un'etichetta italiana: un badge
// grigio con una parola inglese sotto gli occhi di un trader è un bug.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    SAFE_ACTIVITY_EXTRA, safeActivityMeta, safeActivityLine, safeExitKindLabel,
    safeMarketLabel, safeReasonLabel, safeSourceLabel,
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
        })).toBe('Roma vs Lazio · BACK Under 2.5 · Over/Under 2.5 · 5,00 € @ 2,10 · spread troppo largo fra back e lay');
    });

    // Il servizio scrive `spread_anomalo` (bot_service._log_skip), non
    // `spread_troppo_ampio`: senza la voce il trader leggeva la chiave inglese.
    it('motivi REALI del servizio: nessuna chiave tecnica a schermo', () => {
        expect(safeActivityLine({ event_id: '36050104', reason: 'spread_anomalo' }))
            .toBe('36050104 · spread troppo largo fra back e lay');
        expect(safeActivityLine({ event_id: '1', market_type: 'CORRECT_SCORE', liability: 62, reason: 'per_event_liability_cap' }))
            .toBe('1 · Risultato Esatto · liability 62,00 € · cap di liability per evento raggiunto');
        expect(safeActivityLine({ reason: 'daily_loss_stop' })).toContain('stop per perdita giornaliera');
        expect(safeActivityLine({ reason: 'model_daily_liability_cap' })).toContain('cap giornaliero');
        expect(safeActivityLine({ reason: 'open_count_failed' })).toContain('conteggio delle posizioni aperte');
    });

    // exit / exit_wait portano SIA `exit_reason` (frase italiana di
    // exits.reason_text) SIA `reason` (codice tecnico): vince la frase.
    it('uscita: vince la frase italiana, non il codice tecnico', () => {
        const line = safeActivityLine({
            event_name: 'Roma vs Lazio', exit_kind: 'loss',
            exit_reason: 'Il lato bancato ha segnato: chiusura in perdita',
            reason: 'lato_bancato_segna', trade_id: 47,
        });
        expect(line).toContain('Il lato bancato ha segnato: chiusura in perdita');
        expect(line).not.toContain('lato_bancato_segna');
        // solo il codice tecnico (exit_wait): tradotto lo stesso
        expect(safeActivityLine({ reason: 'lato_bancato_segna', trade_id: 48 }))
            .toBe('il lato bancato ha segnato: chiusura in perdita · #48');
        expect(safeActivityLine({ reason: 'minuto_77_lato_bancato_senza_gol' }))
            .toContain("uscita a tempo al 77′");
    });

    it('uscita che ritenta: tentativi e ora del prossimo tentativo (Roma)', () => {
        const line = safeActivityLine({
            event_name: 'Roma vs Lazio', exit_kind: 'loss', attempts: 2,
            next_retry_at: '2026-09-11T16:07:00Z', trade_id: 41,
        });
        expect(line).toContain('uscita: chiusura in perdita');
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

// ---------------------------------------------------------------------------
// Mercato e tipo di uscita in CHIARO: "CORRECT_SCORE" e "loss" sotto gli occhi
// di un trader italiano sono un bug (certificazione 12/09).
// ---------------------------------------------------------------------------
describe('safeMarketLabel — mercati Betfair in italiano', () => {
    it('i market_type che il servizio scrive davvero', () => {
        expect(safeMarketLabel('CORRECT_SCORE')).toBe('Risultato Esatto');
        expect(safeMarketLabel('HALF_TIME_SCORE')).toBe('Risultato Esatto 1º tempo');
        expect(safeMarketLabel('MATCH_ODDS')).toBe('1X2 finale');
        expect(safeMarketLabel('HALF_TIME')).toBe('1X2 primo tempo');
        expect(safeMarketLabel('BOTH_TEAMS_TO_SCORE')).toBe('Gol/NoGol');
        expect(safeMarketLabel('OVER_UNDER_45')).toBe('Over/Under 4.5');
        expect(safeMarketLabel('OVER_UNDER', 3.5)).toBe('Over/Under 3,5');
        expect(safeMarketLabel('COMBO')).toBe('Combinazione');
    });

    it('tipo sconosciuto: mai la costante inglese con gli underscore', () => {
        expect(safeMarketLabel('QUALCOSA_DI_NUOVO')).toBe('Qualcosa di nuovo');
        expect(safeMarketLabel(null)).toBeNull();
        expect(safeMarketLabel('')).toBeNull();
    });
});

describe('safeExitKindLabel — tipo di uscita in italiano', () => {
    it('vocabolario chiuso di exits.EXIT_KINDS', () => {
        expect(safeExitKindLabel('loss')).toBe('chiusura in perdita');
        expect(safeExitKindLabel('greenup')).toContain('green-up');
        expect(safeExitKindLabel('time')).toBe('uscita a tempo');
        expect(safeExitKindLabel('manual')).toBe('cash out manuale');
        expect(safeExitKindLabel('red_card')).toBe('cartellino rosso');
        expect(safeExitKindLabel(null)).toBeNull();
    });
});
