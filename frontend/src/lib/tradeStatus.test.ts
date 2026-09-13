import { describe, it, expect } from 'vitest';
import {
    statusMeta, botStatusMeta, sideMeta, STATUS_META, ACTIVITY_BASE,
    activityMeta, activityLineGeneric, T,
    scalperStatusMeta, TERMINAL_ERROR_META,
    isReconcilingMeta, isTerminalErrorMeta, statusMetaOf, TIP,
} from './tradeStatus';

describe('statusMeta', () => {
    it('una etichetta italiana per ogni stato del DB', () => {
        expect(statusMeta('pending').label).toBe('IN CORSO');
        expect(statusMeta('open').label).toBe('APERTO');
        expect(statusMeta('hedged').label).toBe('CHIUSO');
        expect(statusMeta('won').label).toBe('VINTO');
        expect(statusMeta('lost').label).toBe('PERSO');
        expect(statusMeta('void').label).toBe('VOID');
        expect(statusMeta('error').label).toBe('ERRORE');
    });
    it('nessuno stato in inglese e nessuna chiave mancante', () => {
        for (const m of Object.values(STATUS_META)) {
            expect(m.label).toBe(m.label.toUpperCase());
            expect(m.cls).toMatch(/text-/);
        }
    });
    /**
     * CERT. 13/09 — SOSTITUISCE «stato sconosciuto o assente = ERRORE (mai una
     * schermata muta)», che certificava il comportamento SBAGLIATO: qualunque
     * stato non previsto dalla mappa veniva mostrato come «ERRORE».
     *
     * Perché era sbagliato: uno stato NUOVO scritto dal backend (o un refuso)
     * faceva dichiarare in errore posizioni sane, e su una tabella di trading
     * «ERRORE» è un invito a chiudere. La schermata non deve restare muta — e
     * non resta: dice la chiave e DICHIARA che non la conosce, come fa già
     * `activityMeta` per i kind sconosciuti.
     */
    it('stato sconosciuto: dichiarato SCONOSCIUTO, mai spacciato per ERRORE', () => {
        expect(statusMeta('boh').label).toBe('BOH (stato sconosciuto)');
        expect(statusMeta('boh').label).not.toBe('ERRORE');
        // l'errore VERO resta l'errore
        expect(statusMeta('error').label).toBe('ERRORE');
    });
    it('stato assente: dichiarato ASSENTE (mai una schermata muta)', () => {
        expect(statusMeta(null).label).toBe('STATO ASSENTE');
        expect(statusMeta('').label).toBe('STATO ASSENTE');
    });
    it('reconciling vince su tutto', () => {
        // §19: UNA sola parola per la riconciliazione, la stessa che usano
        // Omega, Safe e Mike nelle loro tabelle
        expect(statusMeta('pending', { reconciling: true }).label).toBe('IN VERIFICA SU BETFAIR');
        expect(statusMeta('won', { reconciling: false }).label).toBe('VINTO');
        // un esito GIA' ARRIVATO resta l'esito: non si nasconde un VINTO
        // dietro un flag di verifica
        expect(statusMeta('won', { reconciling: true }).label).toBe('VINTO');
        expect(statusMeta('lost', { terminal: true }).label).toBe('PERSO');
        // riga TERMINALE (nessun ordine reale): mai un 'IN CORSO' eterno
        expect(statusMeta('pending', { terminal: true }).label).toBe('ERRORE (definitivo)');
        // terminale VINCE sulla riconciliazione (esito certo negativo)
        expect(statusMeta('pending', { terminal: true, reconciling: true }).label)
            .toBe('ERRORE (definitivo)');
    });
});

describe('botStatusMeta', () => {
    it('etichette uniche per le tre sezioni', () => {
        expect(botStatusMeta('idle').label).toBe('INATTIVO');
        expect(botStatusMeta('running').label).toBe('IN CORSA');
        expect(botStatusMeta('stopping').label).toBe('IN ARRESTO');
        expect(botStatusMeta('stopped').label).toBe('FERMO');
        expect(botStatusMeta('error').label).toBe('ERRORE');
        expect(botStatusMeta(null).label).toBe('INATTIVO');
    });
    it('prefisso opzionale (compatibilita Safe/Mike)', () => {
        expect(botStatusMeta('running', 'BOT').label).toBe('BOT IN CORSA');
    });
    it('IN CORSA pulsa', () => {
        expect(botStatusMeta('running').cls).toMatch(/animate-pulse/);
    });
});

describe('sideMeta', () => {
    it('BACK sky, LAY rose', () => {
        expect(sideMeta('back').label).toBe('BACK');
        expect(sideMeta('back').cls).toMatch(/sky/);
        expect(sideMeta('LAY').label).toBe('LAY');
        expect(sideMeta('lay').cls).toMatch(/rose/);
        expect(sideMeta(null).label).toBe('BACK');
    });
});

describe('glossario T', () => {
    it('le parole imposte dal design system', () => {
        expect(T.openLiability).toBe('Liability aperta');
        expect(T.lockedPnl).toBe('P&L bloccato');
        expect(T.cashOut).toBe('Cash out');
        expect(T.goalHit).toBe('CENTRATO');
        expect(T.operatingDay).toBe('giornata operativa');
        expect(T.liveConfirmTitle).toBe('Passare a LIVE (soldi veri)?');
    });
    it('nessun "Cash-out" col trattino ne "Capitale a rischio"', () => {
        const all = Object.values(T).join(' | ');
        expect(all).not.toMatch(/Cash-out/);
        expect(all).not.toMatch(/Capitale a rischio/);
    });
});

describe('activityMeta', () => {
    it('kind comuni ai tre bot in italiano', () => {
        expect(activityMeta('place').label).toBe('ORDINE');
        expect(activityMeta('would_place').label).toBe('ORDINE (dry)');
        expect(activityMeta('no_fill').label).toBe('NON ABBINATO');
        expect(activityMeta('cashout_done').label).toBe('CASH OUT ESEGUITO');
        expect(activityMeta('settled').label).toBe('REGOLATA');
    });
    it('i kind critici sono rossi e marcati', () => {
        for (const k of ['error', 'feed_blind', 'daily_stop', 'cashout_failed', 'close_retries_exhausted']) {
            const m = ACTIVITY_BASE[k];
            expect(m.critical, k).toBe(true);
            expect(m.cls, k).toMatch(/red/);
        }
    });
    it('extra della sezione ha la precedenza', () => {
        expect(activityMeta('place', { place: { label: 'PIAZZATO', cls: 'x' } }).label).toBe('PIAZZATO');
    });
    it('kind ignoto ma componibile: tradotto parola per parola', () => {
        expect(activityMeta('cashout_retry').label).toBe('CASH OUT · RITENTO');
        expect(activityMeta('order_failed').label).toBe('ORDINE · FALLITO');
        expect(activityMeta('order_failed').critical).toBe(true);
        expect(activityMeta('order_failed').cls).toMatch(/red/);
    });
    it('kind del tutto ignoto: dichiarato, non travestito da inglese', () => {
        const m = activityMeta('zorblax');
        expect(m.label).toBe('zorblax (kind sconosciuto)');
        expect(m.cls).toMatch(/slate-400/);
        expect(activityMeta('').label).toBe('ATTIVITÀ');
        expect(activityMeta(null).label).toBe('ATTIVITÀ');
    });
});

describe('activityLineGeneric', () => {
    it('rende leggibile un payload qualsiasi con i formatter unici', () => {
        expect(activityLineGeneric({ event_name: 'Roma v Lazio', side: 'lay', selection_name: '3 - 2', size: 5.26, price: 110 }))
            .toBe('Roma v Lazio · lay 3 - 2 · 5,26 € @ 110,00');
        expect(activityLineGeneric({ pnl: -22.1, reason: 'margine ampio' })).toBe('−22,10 € · margine ampio');
        expect(activityLineGeneric({ err: 'INVALID_BET_SIZE' })).toBe('INVALID_BET_SIZE');
        expect(activityLineGeneric({ msg: 'ok' })).toBe('ok');
        expect(activityLineGeneric({})).toBe('');
        expect(activityLineGeneric(null)).toBe('');
    });
    it('payload senza campi noti: JSON troncato, mai una riga vuota muta', () => {
        expect(activityLineGeneric({ foo: 1 })).toBe('{"foo":1}');
    });
    it('solo prezzo o solo size', () => {
        expect(activityLineGeneric({ price: 2.04 })).toBe('2,04');
        expect(activityLineGeneric({ size: 10 })).toBe('10,00 €');
    });
});

// ============================= certificazione 11/09: stati del bot scalper
describe('scalperStatusMeta — il theta ha un ciclo di armamento suo', () => {
    it('gli stati PROPRI dello scalper hanno una parola italiana', () => {
        expect(scalperStatusMeta('requested').label).toBe('RICHIESTO');
        expect(scalperStatusMeta('arming').label).toBe('IN ARMAMENTO');
        expect(scalperStatusMeta('armed').label).toBe('ARMATO');
    });

    it('gli stati COMUNI restano quelli del bot (una sola mappa)', () => {
        expect(scalperStatusMeta('running').label).toBe('IN CORSA');
        expect(scalperStatusMeta('stopping').label).toBe('IN ARRESTO');
        expect(scalperStatusMeta('stopped').label).toBe('FERMO');
        expect(scalperStatusMeta('error').label).toBe('ERRORE');
    });

    it('nessuno stato mostra la chiave inglese in maiuscolo', () => {
        for (const s of ['requested', 'arming', 'armed', 'running', 'stopping', 'stopped', 'idle', 'error']) {
            expect(scalperStatusMeta(s).label, s).not.toBe(s.toUpperCase());
        }
        // stato mai visto: si ripiega su INATTIVO, non sulla chiave
        expect(scalperStatusMeta('boh').label).toBe('INATTIVO');
        expect(scalperStatusMeta(null).label).toBe('INATTIVO');
    });

    it('la riga TERMINALE ha una etichetta sua, condivisa dalle tre sezioni', () => {
        expect(TERMINAL_ERROR_META.label).toBe('ERRORE (definitivo)');
        expect(TERMINAL_ERROR_META.cls).toMatch(/orange/);
    });
});

// ============================================================================
// CERTIFICAZIONE UI 12/09 — una sola regola di "in verifica"/"terminale"
// ============================================================================
describe('isReconcilingMeta / isTerminalErrorMeta / statusMetaOf (12/09)', () => {
    it('Omega marca con `meta.reconciling`, Safe e Mike solo con `meta.reason`: entrambi valgono', () => {
        expect(isReconcilingMeta('pending', { reconciling: true })).toBe(true);
        expect(isReconcilingMeta('pending', { reason: 'place_exception_reconciling' })).toBe(true);
        expect(isReconcilingMeta('pending', { reason: 'altro' })).toBe(false);
        expect(isReconcilingMeta('pending', null)).toBe(false);
    });

    it('un ESITO arrivato vince sempre sulla riconciliazione', () => {
        expect(isReconcilingMeta('won', { reconciling: true })).toBe(false);
        expect(isReconcilingMeta('open', { reconciling: true })).toBe(false);
    });

    it('terminale = nessun ordine reale esiste (flag di Omega e di Safe)', () => {
        expect(isTerminalErrorMeta({ error_final: true })).toBe(true);
        expect(isTerminalErrorMeta({ leg_failed: true })).toBe(true);
        expect(isTerminalErrorMeta({ no_fill_at: '2026-09-12T10:00:00Z' })).toBe(true);
        expect(isTerminalErrorMeta({ error_at: '2026-09-12T10:00:00Z' })).toBe(true);
        expect(isTerminalErrorMeta({ reason: 'orphan_paper' })).toBe(false);   // Mike: nessun flag
        expect(isTerminalErrorMeta(null)).toBe(false);
    });

    it('statusMetaOf: lo STORICO dice la stessa parola del LIVE', () => {
        expect(statusMetaOf({ status: 'pending', meta: { reason: 'place_exception_reconciling' } }).label)
            .toBe('IN VERIFICA SU BETFAIR');
        expect(statusMetaOf({ status: 'error', meta: { error_final: true } }).label)
            .toBe('ERRORE (definitivo)');
        expect(statusMetaOf({ status: 'pending', meta: null }).label).toBe('IN CORSO');
        expect(statusMetaOf({ status: 'won', meta: { error_final: true } }).label).toBe('VINTO');
    });
});

describe('ACTIVITY_BASE — i kind che i servizi scrivono davvero (12/09)', () => {
    // fonte: omega_service.py / safe_strategy bot_service.py+execution.py / mike service.py
    const SCRITTI_DAI_SERVIZI = [
        'place_pending', 'place_retry', 'place_reconciling', 'place_exception', 'place_resting',
        'fill_resting', 'confirm_failed', 'size_reduced', 'size_legalized',
        'flumine_enqueue', 'flumine_fill', 'flumine_no_fill', 'flumine_cancel', 'flumine_poll_error',
        'cashout_error', 'greenup_blind', 'hedged',
        'settle_error', 'settle_wait', 'settle_hedged', 'settle_orphan', 'settle_fallback',
        'reconcile_error', 'reconcile_pending', 'reconciled_open', 'reconciled_free', 'reconciled_error',
        'orphan_live_alert', 'stale_open_alert', 'risk_block', 'goal_stop', 'loss_stop',
        'manual_place', 'model_lambda_market', 'model_lambda_live', 'feed_line_missing',
        'resume_event', 'skip_event', 'schema_warn',
    ];
    it('nessuno di questi cade su "kind sconosciuto" o resta in inglese', () => {
        for (const k of SCRITTI_DAI_SERVIZI) {
            const m = activityMeta(k);
            expect(m.label, k).not.toMatch(/kind sconosciuto/);
            expect(m.label, k).toBe(ACTIVITY_BASE[k].label);
        }
    });
    it('i guasti che costano soldi sono CRITICI (rossi, mai sepolti)', () => {
        for (const k of ['place_reconciling', 'confirm_failed', 'orphan_live_alert', 'stale_open_alert',
            'settle_error', 'reconcile_error', 'greenup_blind', 'flumine_poll_error', 'schema_warn']) {
            expect(activityMeta(k).critical, k).toBe(true);
        }
    });
});

describe('TIP — un tooltip solo per le grandezze condivise (12/09)', () => {
    it('ogni voce del glossario monetario ha la sua riga di spiegazione', () => {
        for (const k of ['openLiability', 'lockedPnl', 'realizedToday', 'winLoss'] as const) {
            expect(TIP[k].length, k).toBeGreaterThan(20);
        }
        // "Liability aperta" = rischio ADESSO, non capitale impegnato oggi:
        // era esattamente la confusione fra il KPI e il dettaglio giornata
        expect(TIP.openLiability).toMatch(/ADESSO/);
        // cert. 12/09: V/P si contano per SEGNO del P&L di posizione, non per stato
        expect(TIP.winLoss).toMatch(/segno|positivo/i);
        expect(TIP.winLoss).not.toMatch(/conta lo stato/);
    });
});

describe('certificazione 12/09 — ordine appoggiato e non abbinato', () => {
    it('una lay di green-up solo APPOGGIATA non ha il badge di una posizione abbinata', () => {
        const appoggiata = { status: 'open', meta: { fill: 'paper_resting', phase: 'open' } };
        const abbinata = { status: 'open', meta: { fill: 'paper_fill' } };
        expect(statusMetaOf(appoggiata).label).toBe('APPOGGIATA · NON ABBINATA');
        expect(statusMetaOf(abbinata).label).not.toBe('APPOGGIATA · NON ABBINATA');
        expect(statusMetaOf(appoggiata).cls).not.toBe(statusMetaOf(abbinata).cls);
    });

    it("un esito gia' arrivato vince sempre sul flag di appoggiata", () => {
        for (const st of ['won', 'lost', 'void']) {
            const r = { status: st, meta: { fill: 'paper_resting' } };
            expect(statusMetaOf(r).label).not.toBe('APPOGGIATA · NON ABBINATA');
        }
    });

    it('la riconciliazione ha la precedenza: non si sa nemmeno se esiste', () => {
        const r = { status: 'pending', meta: { fill: 'paper_resting', reconciling: true } };
        expect(statusMetaOf(r).label).toBe('IN VERIFICA SU BETFAIR');
    });

    it('senza meta.fill il comportamento non cambia', () => {
        expect(statusMetaOf({ status: 'open' })).toEqual(statusMeta('open'));
    });
});
