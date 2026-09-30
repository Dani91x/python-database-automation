// ============================================================================
// W_B2EsitiOmegaSafe.test.tsx - 30/09 sera (blocco W_B2, punto 1, M10 della
// review): gli esiti VERI anche per Omega e Safe. I `meta` qui sotto sono
// quelli che i servizi scrivono davvero (letti in sola lettura):
//   Omega  omega_service.py `_flumine_no_fill_error` (:3551-3572: reason
//          `flumine_<motivo>`, leg_failed, error_final, error_at, no_fill_at),
//          manuale (:5459-5463, :5499-5503, :5545-5549, :5586-5592)
//   Safe   bot_service.py `_place_fail` (:6017-6020: reason = nota
//          dell'esecuzione, error_final, place{...}), `_terminal_error`
//          (:1265-1272), chiusure execution.py:1865-1871 (error_code)
// ============================================================================
import { describe, it, expect } from 'vitest';
import { esitoOrdineMeta, motivoErroreTesto, statusMetaOf } from '@/lib/tradeStatus';
import { statoOrdine } from '@/lib/statoOrdine';
import { dettaglioDi } from './dettaglioRiga';

const AT = '2026-09-30T18:00:00+00:00';

/** meta di una riga Omega chiusa da `_flumine_no_fill_error` */
function omegaNoFill(motivo: string): Record<string, unknown> {
    return {
        flumine_request_id: 991, flumine_client_ref: 'omega-t55', model: { p: 0.1 },
        reason: `flumine_${motivo}`, leg_failed: true, error_final: true, error_at: AT, no_fill_at: AT,
    };
}

/** meta di una riga Safe chiusa da `_place_fail` */
function safePlaceFail(err: string): Record<string, unknown> {
    return {
        strategy: 'base', signal_key: 'k1', reason: err, error_final: true,
        place: { attempts: 1, last_error: err, last_ts: AT, final: false, next_retry_at: AT },
    };
}

function esito(meta: Record<string, unknown>): string | null {
    const riga = { status: 'error', meta };
    return esitoOrdineMeta(riga, statoOrdine(riga).errorCode)?.label ?? null;
}

function badge(meta: Record<string, unknown>): string {
    return dettaglioDi({ id: 1, event_id: 'E', side: 'lay', status: 'error', pnl: 0, placed_at: AT, meta }).stato.label;
}

describe('Omega: esiti dal motivo `flumine_<...>`', () => {
    it('verificato su Betfair: nessun ordine abbinato', () => {
        for (const m of ['live_rest_no_fill', 'live_rest_not_found', 'canale_rest_no_fill', 'canale_rest_not_found', 'canale_mai_visto_su_betfair']) {
            expect(esito(omegaNoFill(m))).toBe('NON ABBINATO (verificato su Betfair)');
        }
    });
    it('FOK ucciso da Betfair senza abbinato', () => {
        expect(esito(omegaNoFill('live_fok_expired'))).toBe('NON ABBINATO (tutto o niente)');
    });
    it('annullo nostro dopo il TTL, senza abbinato', () => {
        expect(esito(omegaNoFill('cancelled_no_fill'))).toBe('RITIRATO dal bot');
    });
    it('scaduto / violazione (paper) e fasi del canale', () => {
        expect(esito(omegaNoFill('terminal_expired'))).toBe('NON ABBINATO (scaduto su Betfair)');
        expect(esito(omegaNoFill('terminal_violation'))).toBe('RIFIUTATO da Betfair: VIOLATION');
        expect(esito(omegaNoFill('canale_scaduto'))).toBe('NON ABBINATO (scaduto su Betfair)');
        expect(esito(omegaNoFill('canale_annullato'))).toBe('ANNULLATO senza abbinamento');
        expect(esito(omegaNoFill('canale_rifiutato'))).toBe('RIFIUTATO dal runner');
    });
    it('mai inviato: revoca oltre la scadenza, freno, runner paper assente', () => {
        expect(esito(omegaNoFill('live_revoked_deadline'))).toBe('FERMATO dal bot (mai inviato)');
        expect(esito({ reason: 'kill_switch', motivo: 'live_kill_switch_attivo', percorso: 'rest', leg_failed: true, error_final: true, error_at: AT }))
            .toBe('FERMATO dal bot (mai inviato)');
        expect(esito({ reason: 'paper_runner_non_disponibile', motivo_runner: 'gate', percorso: 'paper', leg_failed: true, error_final: true, error_at: AT }))
            .toBe('FERMATO dal bot (mai inviato)');
    });
    it('non classificabile: resta ERRORE (definitivo) col motivo, mai un’etichetta tranquilla', () => {
        // manuale REST: `live_not_matched` NUDO, senza codice scritto (omega_service.py:5546)
        const manuale = { reason: 'live_not_matched', order_status: 'EXPIRED', leg_failed: true, error_final: true, error_at: AT };
        expect(esito(manuale)).toBeNull();
        expect(badge(manuale)).toBe('ERRORE (definitivo) · non abbinato o rifiutato da Betfair (codice non scritto sulla riga)');
        expect(esito(omegaNoFill('no_mirror_after_ttl'))).toBeNull();
        expect(badge(omegaNoFill('no_mirror_after_ttl'))).toBe('ERRORE (definitivo) · nessuna traccia dell’ordine dopo il tempo massimo');
        expect(badge(omegaNoFill('live_request_error:BAD_REQUEST'))).toBe('ERRORE (definitivo) · errore della richiesta prima dell’invio: BAD_REQUEST');
        // motivo sconosciuto: grezzo, senza inventare
        expect(badge(omegaNoFill('qualcosa_di_nuovo'))).toBe('ERRORE (definitivo) · qualcosa di nuovo');
    });
});

describe('Safe: esiti dalla nota dell’esecuzione', () => {
    it('rifiuto di Betfair col codice', () => {
        expect(esito(safePlaceFail('live_rifiutato:INSUFFICIENT_FUNDS'))).toBe('RIFIUTATO da Betfair: INSUFFICIENT_FUNDS');
        expect(esito(safePlaceFail('live_not_matched:EXECUTION_COMPLETE:BET_TAKEN_OR_LAPSED'))).toBe('RIFIUTATO da Betfair: BET_TAKEN_OR_LAPSED');
        expect(esito(safePlaceFail('live_rifiutato:senza_codice'))).toBe('RIFIUTATO da Betfair (codice non dichiarato)');
    });
    it('FOK non abbinato (nota senza codice)', () => {
        expect(esito(safePlaceFail('live_not_matched:EXPIRED'))).toBe('NON ABBINATO (tutto o niente)');
    });
    it('rifiuto del runner (nostro): nessun ordine a Betfair', () => {
        expect(esito(safePlaceFail('canale_rifiutato:submin_non_percorribile'))).toBe('RIFIUTATO dal runner: submin non percorribile');
    });
    it('mai inviato: freno, modo ordini, canale giù, runner paper, controlli prima dell’invio', () => {
        for (const n of ['live_kill_switch_attivo', 'db_kill_switch_attivo', 'live_order_mode_non_live:PAPER',
            'canale_giu:apertura_non_inviata', 'paper_senza_runner:gate_chiuso', 'liquidita_insufficiente',
            'submin_non_disponibile:gate_chiuso']) {
            expect(esito(safePlaceFail(n))).toBe('FERMATO dal bot (mai inviato)');
        }
    });
    it('riconciliazione: ordine assente o morto senza abbinato', () => {
        expect(esito({ reason: 'reconcile_ordine_assente', error_final: true, error_at: AT, how: 'live' })).toBe('NON ABBINATO (verificato su Betfair)');
        expect(esito({ reason: 'reconcile_ordine_senza_fill', error_final: true, error_at: AT })).toBe('NON ABBINATO (verificato su Betfair)');
    });
    it('non classificabile: ERRORE (definitivo) col motivo', () => {
        const r = { reason: 'reconcile_orphan_old', error_final: true, error_at: AT };
        expect(esito(r)).toBeNull();
        expect(badge(r)).toBe('ERRORE (definitivo) · riga orfana da oltre 24 ore, nessun ordine trovato');
    });
});

describe('regole comuni', () => {
    it('solo righe in errore; statusMetaOf e il suo significato non cambiano', () => {
        expect(esitoOrdineMeta({ status: 'open', meta: safePlaceFail('live_rifiutato:X') })).toBeNull();
        expect(motivoErroreTesto({ status: 'open', meta: { reason: 'x' } })).toBeNull();
        expect(statusMetaOf({ status: 'error', meta: safePlaceFail('live_rifiutato:INSUFFICIENT_FUNDS') }).label).toBe('ERRORE (definitivo)');
        // riga in errore senza motivo: il badge di sempre, niente aggiunto
        expect(badge({})).toBe('ERRORE');
    });
});
