// Test PURI del client Omega (lib/omega.ts): default allineati al servizio
// (H-07), patch dei parametri, spec del pannello (M-09/M-10), etichette delle
// attività (M-01), riga di attività che legge SOLO chiavi reali (M-02), stati
// del green-up (H-04), copertura (M-06), verifica su Betfair (H-02),
// commissione fissata sulla riga (L-02), esito della posizione (M-04).
import { describe, it, expect } from 'vitest';
import {
    OMEGA_PARAM_DEFAULTS, OMEGA_PARAM_GROUPS, OMEGA_PARAM_KEYS, omegaParamsPatch,
    OMEGA_ACTIVITY_EXTRA, activityMeta, activityLine,
    greenupInfo, greenupHold, greenupBadge, hedgeInfo, isHedging,
    isReconciling, reconcilingSince, terminalError, staleOpenAlerted,
    commissionPctOf, hasOwnCommission, positionInfo, tradeModelOf, phaseLabel, errorAt,
    type OmegaActivityRow,
} from './omega';

// ------------------------------------------------------------------- H-07
describe('OMEGA_PARAM_DEFAULTS — allineati alla whitelist del servizio (H-07)', () => {
    it('model_calibration OFF e greenup_risk_cap 0,15 come in omega_config.py', () => {
        expect(OMEGA_PARAM_DEFAULTS.model_calibration).toBe('off');
        expect(OMEGA_PARAM_DEFAULTS.greenup_risk_cap).toBe(0.15);
    });

    it('i default coprono tutte le chiavi con una UI e viceversa', () => {
        for (const k of OMEGA_PARAM_KEYS) {
            expect(OMEGA_PARAM_DEFAULTS, `default mancante per ${k}`)
                .toHaveProperty(k);
        }
        for (const k of Object.keys(OMEGA_PARAM_DEFAULTS)) {
            expect(OMEGA_PARAM_KEYS, `parametro senza UI: ${k}`).toContain(k);
        }
    });

    it('M-10: le chiavi prima invisibili hanno una UI', () => {
        for (const k of ['engine', 'execution_mode', 'paper_fill_ttl_s', 'omega_live_via_flumine',
            'live_fill_deadline_s', 'model_min_goal_distance', 'model_empirical',
            'model_empirical_max_minute', 'lambda_market_grid', 'lambda_live_fallback',
            'select_cost_aware', 'select_p_band_ratio', 'model_use_yellow_cards',
            'model_tail_factor', 'model_lambda_cv', 'select_k_se', 'select_p_hedge',
            'select_ev_kappa', 'model_calibration_path']) {
            expect(OMEGA_PARAM_KEYS).toContain(k);
        }
    });

    it('M-09: min/max/step sono quelli del servizio (ev_margin in EURO, attempts da 0)', () => {
        const field = (key: string) => OMEGA_PARAM_GROUPS.flatMap((g) => g.fields).find((f) => f.key === key);
        expect(field('greenup_ev_margin')).toMatchObject({ min: 0, max: 1000 });
        expect(field('greenup_ev_margin')?.label).toMatch(/€/);
        expect(field('greenup_max_attempts')).toMatchObject({ min: 0, max: 100 });
        expect(field('greenup_retry_s')).toMatchObject({ min: 2, max: 600 });
        expect(field('greenup_settle_delay_s')).toMatchObject({ min: 0, max: 600 });
        expect(field('greenup_trigger_distance')).toMatchObject({ min: 0, max: 3 });
        expect(field('greenup_take_profit_frac')).toMatchObject({ min: 0.1, max: 1 });
        expect(field('model_tail_factor')).toMatchObject({ min: 0.5, max: 5 });
    });

    it('ogni campo ha una etichetta italiana non vuota e nessuna chiave inglese nuda', () => {
        for (const g of OMEGA_PARAM_GROUPS) {
            for (const f of g.fields) {
                expect(f.label.trim().length, `etichetta vuota per ${f.key}`).toBeGreaterThan(0);
                expect(f.label, `etichetta = chiave per ${f.key}`).not.toBe(f.key);
            }
        }
    });
});

describe('omegaParamsPatch (H-07)', () => {
    it('parte dai parametri del SERVIZIO e aggiunge solo le modifiche', () => {
        const server = { model_calibration: 'off', greenup_risk_cap: 0.15, greenup_mode: 'auto' };
        const draft = { ...OMEGA_PARAM_DEFAULTS, model_calibration: 'off', greenup_risk_cap: 0.15, greenup_mode: 'off' };
        const out = omegaParamsPatch(server, draft as unknown as Record<string, unknown>);
        expect(out.greenup_mode).toBe('off');
        expect(out.model_calibration).toBe('off');
        expect(out.greenup_risk_cap).toBe(0.15);
    });

    it('una chiave che il servizio NON ha e uguale al default della UI non viene inviata', () => {
        const out = omegaParamsPatch({}, { select_k_se: OMEGA_PARAM_DEFAULTS.select_k_se, price_min: 30 });
        expect(out).not.toHaveProperty('select_k_se');
        expect(out.price_min).toBe(30);
    });

    it('un default UI DIVERSO da quello del servizio non sovrascrive il servizio', () => {
        // scenario reale del bug: la UI aveva 'auto' e 0.10, il servizio 'off' e 0.15
        const server = { model_calibration: 'off', greenup_risk_cap: 0.15 };
        const out = omegaParamsPatch(server, { model_calibration: 'off', greenup_risk_cap: 0.15 });
        expect(out).toEqual(server);
    });

    it('numeri come stringhe (input HTML) non generano finte modifiche', () => {
        const out = omegaParamsPatch({ price_min: 20 }, { price_min: '20' });
        expect(out.price_min).toBe(20);
    });

    it('booleani: false ≠ true, e false non viene perso', () => {
        const out = omegaParamsPatch({ stop_on_goal: true }, { stop_on_goal: false });
        expect(out.stop_on_goal).toBe(false);
    });
});

// ------------------------------------------------------------------- M-01
// Contratto delle attività del servizio Omega (audit 11/09).
const CONTRACT_KINDS = [
    'place', 'skip', 'size_reduced', 'goal_stop', 'loss_stop', 'confirm_failed',
    'place_reconciling', 'manual_place', 'manual_place_exception', 'paper_fill_fallback',
    'live_fok_fallback',
    'flumine_enqueue', 'flumine_fill', 'flumine_no_fill', 'flumine_cancel',
    'flumine_cancel_timeout', 'flumine_recovered', 'flumine_live_freed',
    'flumine_live_orphan', 'flumine_poll_error',
    'reconciled_open', 'reconciled_free', 'reconciled_error', 'reconciled_paper',
    'reconcile_error', 'orphan_live_alert', 'stale_open_alert',
    'greenup', 'greenup_wait', 'greenup_hold', 'greenup_failed',
    'greenup_residual_dropped', 'greenup_blind', 'greenup_retry',
    'cashout_manual', 'cashout', 'cashout_error', 'place_exception',
    'settle', 'settle_hedged', 'hedged', 'settle_position', 'settle_wait',
    'settle_orphan', 'settle_orphan_closing', 'settle_error',
    'model_lambda_market', 'model_lambda_live', 'mission_error', 'mission_scores_error',
    'error', 'stop',
];

describe('attività del servizio (M-01)', () => {
    // parole identiche in italiano: "STOP" va bene così com'è
    const SAME_IN_ITALIAN = new Set(['stop']);

    it('OGNI kind del contratto ha una etichetta italiana ≠ dalla chiave', () => {
        for (const k of CONTRACT_KINDS) {
            const m = activityMeta(k);
            expect(m.label, `kind senza etichetta: ${k}`).toBeTruthy();
            expect(m.label, `etichetta = chiave per ${k}`).not.toBe(k);
            expect(m.label, `kind sconosciuto: ${k}`).not.toMatch(/kind sconosciuto/);
            if (!SAME_IN_ITALIAN.has(k)) {
                expect(m.label, `chiave inglese nuda per ${k}`).not.toBe(k.toUpperCase());
            }
        }
    });

    it('i kind che richiedono attenzione sono CRITICI (rosso)', () => {
        for (const k of ['place_reconciling', 'stale_open_alert', 'greenup_failed', 'greenup_blind',
            'greenup_residual_dropped', 'flumine_live_orphan', 'orphan_live_alert', 'reconcile_error',
            'settle_error', 'cashout_error', 'confirm_failed', 'loss_stop', 'error']) {
            expect(activityMeta(k).critical, `non critico: ${k}`).toBe(true);
        }
    });

    it('un kind mai visto non mostra la chiave inglese in maiuscolo nuda', () => {
        expect(activityMeta('greenup_qualcosa').label).toMatch(/GREEN-UP/);
        expect(OMEGA_ACTIVITY_EXTRA.greenup_hold.label).toBe('GREEN-UP · TENGO');
        expect(OMEGA_ACTIVITY_EXTRA.greenup_wait.label).toBe('GREEN-UP · attesa prezzi');
    });
});

// ------------------------------------------------------------------- M-02
function row(kind: string, payload: Record<string, unknown>): OmegaActivityRow {
    return { id: 1, ts: '2026-09-11T16:00:00Z', kind, payload };
}

describe('activityLine (M-02)', () => {
    it('legge SOLO le chiavi che il servizio scrive, con i formatter unici', () => {
        const line = activityLine(row('greenup', {
            event_id: '1.234', leg: 'ft_cs', side: 'back', size: 24.24, price: 4.9,
            minute: 71, score: '2-1', p_lose: 0.004, locked_pnl: -22.1,
            exit_reason: 'gol al 29: 1-2 raggiungibile', attempt: 2, max_attempts: 15,
        }), 'Roma vs Lazio');
        expect(line).toBe('Roma vs Lazio · 2T · BACK 24,24 € @ 4,90 · 71′ · 2-1 · P(perdita) 0,4 % · bloccato −22,10 € · gol al 29: 1-2 raggiungibile · tentativo 2/15');
    });

    it('NON inventa niente da chiavi che il backend non scrive (msg, wait, attempts)', () => {
        expect(activityLine(row('greenup_hold', { msg: 'ignorato', attempts: 9, live_score: '1-1' }), null)).toBe('');
    });

    it('senza nome risolto usa l’event_id (mai una riga muta)', () => {
        expect(activityLine(row('place', { event_id: '1.234' }))).toBe('1.234');
    });

    it('traduce i motivi di errore del contratto in italiano', () => {
        expect(activityLine(row('error', { reason: 'greenup_attempts_exhausted' })))
            .toBe('green-up: tentativi esauriti, posizione SCOPERTA');
        expect(activityLine(row('greenup_wait', { wait: 'prezzi_non_disponibili' })))
            .toBe('prezzi di chiusura non disponibili');
    });

    it('next_retry_at → "ritento alle HH:MM" (ora di Roma)', () => {
        expect(activityLine(row('greenup_failed', { next_retry_at: '2026-09-11T16:35:00Z' })))
            .toBe('ritento alle 18:35');
    });
});

// ------------------------------------------------------------------- H-04
describe('green-up: stato sulla riga (H-04)', () => {
    it('meta.greenup letto in tutti i suoi stati', () => {
        expect(greenupInfo(null)).toBeNull();
        expect(greenupInfo({ greenup: {} })).toBeNull();
        const g = greenupInfo({ greenup: { state: 'failed', reason: 'tentativi esauriti', attempts: 15, next_retry_at: '2026-09-11T16:35:00Z', p_lose: 0.2, ev: -1 } });
        expect(g).toMatchObject({ state: 'failed', attempts: 15, pLose: 0.2, ev: -1 });
        // uno state fuori contratto NON si mostra: resta null (mai una parola inventata)
        expect(greenupInfo({ greenup: { state: 'inventato', reason: 'x' } })?.state).toBeNull();
        expect(greenupInfo({ greenup: { state: 'inventato' } })).toBeNull();
    });

    it('badge: una etichetta ITALIANA per ogni state', () => {
        const label = (greenup: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
            greenupBadge({ greenup, ...extra })?.label ?? null;
        expect(label({ state: 'pending', reason: 'x' })).toBe('GREEN-UP in attesa');
        expect(label({ state: 'hold', reason: 'margine ampio', p_lose: 0.004, ev: 1.8 }))
            .toBe('TENGO · P(perdita) 0,4 % · EV +1,80 €');
        expect(label({ state: 'failed', reason: 'x', next_retry_at: '2026-09-11T16:35:00Z' }))
            .toBe('GREEN-UP fallito, ritento alle 18:35');
        expect(label({ state: 'failed', reason: 'x' })).toBe('GREEN-UP FALLITO');
        expect(label({ state: 'blind', reason: 'x' })).toBe('GREEN-UP CIECO (senza feed)');
        expect(label({ state: 'residual_dropped', reason: 'x' })).toBe('residuo abbandonato');
        expect(label({ state: 'done', reason: 'x' })).toBe('GREEN-UP fatto');
        expect(greenupBadge(null)).toBeNull();
        expect(greenupBadge({ greenup: { sent: true } })).toBeNull();
    });

    it('il TENGO prende P(perdita) ed EV anche da meta.greenup_hold', () => {
        const b = greenupBadge({
            greenup: { state: 'hold', reason: 'margine ampio' },
            greenup_hold: { p_lose: 0.012, ev_hold: 2.5, reason: 'margine ampio', locked_pnl: -3 },
        });
        expect(b?.label).toBe('TENGO · P(perdita) 1,2 % · EV +2,50 €');
        expect(greenupHold({ greenup_hold: { p_lose: 0.012, locked_pnl: -3, minute: 71, score: '1-1', laid_score: '1-2' } }))
            .toMatchObject({ pLose: 0.012, lockedPnl: -3, minute: 71, score: '1-1', laidScore: '1-2' });
    });
});

// --------------------------------------------------------------- M-06 / L-01
describe('copertura (M-06) e hedging (L-01)', () => {
    it('meta.hedge: frazione, liability residua, completezza', () => {
        const h = hedgeInfo({ hedge: { fraction: 0.4, remaining_liability: 315.78, hedged_size: 2.1, size: 5.26, complete: false, residual_size: 3.16 } });
        expect(h).toMatchObject({ fraction: 0.4, remainingLiability: 315.78, complete: false, residualSize: 3.16 });
    });

    it('ripiego su hedged_size/residual_size quando meta.hedge non c’è', () => {
        expect(hedgeInfo({ hedged_size: 2, size: 4, residual_size: 2 })?.fraction).toBe(0.5);
        // residuo ancora vivo: la copertura NON è completa nemmeno con locked_pnl
        expect(hedgeInfo({ hedged_size: 2, size: 4, residual_size: 2, locked_pnl: 1 })?.complete).toBe(false);
        expect(hedgeInfo({ hedged_size: 4, size: 4, residual_size: 0, locked_pnl: 1 })?.complete).toBe(true);
        // senza la size nel meta la frazione è IGNOTA: non si inventa
        expect(hedgeInfo({ hedged_size: 2, residual_size: 2 })?.fraction).toBeNull();
        expect(hedgeInfo({})).toBeNull();
    });

    it('meta.hedging: copertura in corso', () => {
        expect(isHedging({ hedging: true })).toBe(true);
        expect(isHedging({ hedging: false })).toBe(false);
        expect(isHedging(null)).toBe(false);
    });
});

// --------------------------------------------------- H-02 / M-05 / L-02 / M-04
describe('verifica su Betfair, righe terminali, commissione, posizione', () => {
    it('H-02: reconciling da meta.reconciling o dall’eccezione di piazzamento', () => {
        expect(isReconciling({ reconciling: true })).toBe(true);
        expect(isReconciling({ reason: 'place_exception_reconciling' })).toBe(true);
        expect(isReconciling({ reconciling: 'true' })).toBe(true);
        expect(isReconciling({})).toBe(false);
        expect(reconcilingSince({ reconciling_since: '2026-09-11T16:00:00Z' })).toBe('2026-09-11T16:00:00Z');
    });

    it('M-05: riga terminale da leg_failed / error_final / no_fill_at', () => {
        expect(terminalError({ leg_failed: true, reason: 'FOK ucciso' })).toMatchObject({ reason: 'FOK ucciso' });
        expect(terminalError({ error_final: true })).not.toBeNull();
        expect(terminalError({ no_fill_at: '2026-09-11T16:00:00Z' })?.at).toBe('2026-09-11T16:00:00Z');
        expect(terminalError({ reconciling: true })).toBeNull();
        expect(staleOpenAlerted({ stale_open_alerted: '2026-09-11T16:00:00Z' })).toBe('2026-09-11T16:00:00Z');
    });

    it('L-02: la commissione è quella FISSATA sulla riga (frazione → punti %)', () => {
        expect(commissionPctOf({ commission: 0.05 }, 2)).toBe(5);
        expect(commissionPctOf({ commission: 0.02 }, 5)).toBe(2);
        expect(commissionPctOf({}, 5)).toBe(5);           // ripiego: parametro corrente
        expect(commissionPctOf(null, 7)).toBe(7);
        expect(hasOwnCommission({ commission: 0.05 })).toBe(true);
        expect(hasOwnCommission({})).toBe(false);
    });

    it('M-04: esito della POSIZIONE, non della gamba', () => {
        expect(positionInfo({ position_id: 9, position_pnl: 4.2, position_result: 'won' }))
            .toEqual({ id: 9, pnl: 4.2, result: 'won' });
        // un esito fuori contratto non diventa una parola inventata
        expect(positionInfo({ position_result: 'strano' })).toBeNull();
        expect(positionInfo({ position_id: 9, position_result: 'strano' })).toEqual({ id: 9, pnl: null, result: null });
        expect(positionInfo({})).toBeNull();
    });
});

describe('modello e fasi (invariati)', () => {
    it('tradeModelOf: calibrata vs grezza', () => {
        expect(tradeModelOf({ meta: { model: { p_model_raw: 0.018, p_model: 0.012 } } }))
            .toEqual({ raw: 0.018, calibrated: 0.012, applied: true });
        expect(tradeModelOf({ meta: {} })).toBeNull();
    });
    it('phaseLabel', () => {
        expect(phaseLabel('ht_cs')).toBe('1T');
        expect(phaseLabel('ft_cs')).toBe('2T');
        expect(phaseLabel(null)).toBe('—');
    });
});

// ====================== contratto 11/09 (seconda passata): 1, 2, 5, 6
describe('contratto aggiornato — meta.hedge senza size/at (1)', () => {
    it('legge il blocco nella forma nuova {fraction, remaining_liability, hedged_size, residual_size, complete}', () => {
        const h = hedgeInfo({
            hedge: { fraction: 0.4, remaining_liability: 573.34, hedged_size: 2.1, residual_size: 3.16, complete: false },
        });
        expect(h).toMatchObject({
            fraction: 0.4, remainingLiability: 573.34, hedgedSize: 2.1, residualSize: 3.16, complete: false,
        });
        // i campi non più scritti non vengono inventati
        expect(h?.size).toBeNull();
        expect(h?.at).toBeNull();
    });

    it('mentre una chiusura è in VOLO la liability residua è quella PIENA (non scalata)', () => {
        const h = hedgeInfo({
            hedging: true,
            hedge: { fraction: 0.4, remaining_liability: 573.34, hedged_size: 2.1, residual_size: 3.16, complete: false },
        });
        // 573,34 = liability piena: fino al fill l'esposizione è intera
        expect(h?.remainingLiability).toBe(573.34);
        expect(isHedging({ hedging: true })).toBe(true);
    });

    it('a copertura COMPLETA confermata la liability residua è 0', () => {
        const h = hedgeInfo({
            hedge: { fraction: 1, remaining_liability: 0, hedged_size: 5.26, residual_size: 0, complete: true },
        });
        expect(h?.complete).toBe(true);
        expect(h?.remainingLiability).toBe(0);
    });
});

describe('contratto aggiornato — istante dell’errore in meta.error_at (5)', () => {
    it('terminalError usa error_at (le righe error non hanno settled_at)', () => {
        expect(terminalError({ error_final: true, error_at: '2026-09-11T16:00:00Z' })?.at)
            .toBe('2026-09-11T16:00:00Z');
        // error_at da solo è già una riga terminale
        expect(terminalError({ error_at: '2026-09-11T16:00:00Z' })).not.toBeNull();
        // ripiego storico su no_fill_at
        expect(terminalError({ leg_failed: true, no_fill_at: '2026-09-11T15:00:00Z' })?.at)
            .toBe('2026-09-11T15:00:00Z');
        // error_at VINCE sul vecchio no_fill_at
        expect(terminalError({ error_at: '2026-09-11T16:00:00Z', no_fill_at: '2026-09-11T15:00:00Z' })?.at)
            .toBe('2026-09-11T16:00:00Z');
    });

    it('errorAt come lettore puro', () => {
        expect(errorAt({ error_at: '2026-09-11T16:00:00Z' })).toBe('2026-09-11T16:00:00Z');
        expect(errorAt({ no_fill_at: '2026-09-11T15:00:00Z' })).toBe('2026-09-11T15:00:00Z');
        expect(errorAt({})).toBeNull();
        expect(errorAt(null)).toBeNull();
    });
});

describe('contratto aggiornato — kind condivisi dallo strato comune (6)', () => {
    const SHARED_KINDS = [
        'settle_position', 'market_missing', 'feed_blind', 'feed_back', 'place_exhausted',
        'combo_incomplete', 'params_clamped', 'params_invalid', 'exit_wait', 'exit_retry',
        'exit_failed', 'cancel_rejected',
    ];
    it('ognuno ha una etichetta italiana (mai la chiave inglese nuda)', () => {
        for (const k of SHARED_KINDS) {
            const m = activityMeta(k);
            expect(m.label, `kind senza etichetta: ${k}`).toBeTruthy();
            expect(m.label, `etichetta = chiave per ${k}`).not.toBe(k);
            expect(m.label, `chiave inglese nuda per ${k}`).not.toBe(k.toUpperCase());
            expect(m.label, `kind sconosciuto: ${k}`).not.toMatch(/kind sconosciuto/);
        }
    });
    it('i più gravi sono CRITICI', () => {
        for (const k of ['market_missing', 'feed_blind', 'place_exhausted', 'combo_incomplete',
            'params_invalid', 'exit_failed', 'cancel_rejected']) {
            expect(activityMeta(k).critical, `non critico: ${k}`).toBe(true);
        }
        // il feed che TORNA è una buona notizia, non un allarme
        expect(activityMeta('feed_back').critical).toBeFalsy();
    });
});
