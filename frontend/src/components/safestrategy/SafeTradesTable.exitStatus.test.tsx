// ============================================================================
// Test COMPONENTE — STATO DI USCITA (reperto 17/09, ordine dell'utente).
//
// Fra un punto e l'altro il book Betfair si svuota per qualche secondo (back o
// lay della nostra selezione assenti: `odds.p2.lay = null`); il bot resta in
// `exit_wait` / `exit_hold` e il trader vedeva una posizione in perdita SENZA
// SPIEGAZIONE. Qui si certifica che la tabella traduce `safe_strategy_activity`
// (kind `exit_wait` / `exit_hold` / `feed_blind`) in una frase italiana.
//
// I finti usano le STESSE chiavi dei payload veri, copiate da
// `Betfair/safe_strategy/bot_service.py`:
//   · `_exit_wait` (righe ~3798-3812): {trade_id, kind, reason, wait}
//   · `_model_gate` (righe ~3514-3519): {trade_id, event_id, kind, reason,
//     msg, p_lose, source, locked, ev_hold, hold_profit, loss_if_lose, back, lay}
//   · proposta in attesa di firma (riga ~4070): {reason:'in_attesa_di_approvazione', ...}
//   · `_dato_che_manca` (righe ~3608-3665): kind 'feed_blind', {trade_id, reason, ...}
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SafeTradesTable } from './SafeTradesTable';
import type { SafeActivityRow, SafeTrade } from '@/lib/safeBot';
import { safeActivityExitStatus, latestExitActivityFor } from '@/lib/safeExitStatus';
import type { CalcioScanPayload } from '@/lib/safeStrategyScan';

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'model',
        market_id: '1.9', market_type: 'OVER_UNDER_25', selection_id: 1, selection_name: 'Over 2.5',
        side: 'back', mode: 'paper', price: 2.1, size: 5, liability: 5, commission: 0.05,
        minute_at_entry: 60, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-10T10:00:00Z', settled_at: null, origin: 'auto',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

function activityRow(over: Partial<SafeActivityRow> & { kind: string; payload: Record<string, unknown> }): SafeActivityRow {
    return { id: 1, ts: '2026-09-17T10:00:00Z', ...over };
}

function renderTable(rows: SafeTrade[], activity: SafeActivityRow[] = []) {
    render(<SafeTradesTable trades={rows} commissionPct={5} liveFeed={{}} onCashOut={vi.fn()} activity={activity} />);
}

describe('SafeTradesTable — stato di uscita da safe_strategy_activity', () => {
    it('exit_wait{wait:"prezzi_non_nel_feed"} -> "In attesa: prezzo di chiusura assente nel book..."', () => {
        renderTable(
            [trade({ id: 42 })],
            [activityRow({ id: 5, kind: 'exit_wait', payload: { trade_id: 42, kind: 'profit', reason: 'take_profit', wait: 'prezzi_non_nel_feed' } })],
        );
        const el = screen.getByTestId('safe-exit-status');
        expect(el).toHaveTextContent("In attesa: prezzo di chiusura assente nel book (capita per pochi secondi fra un punto e l'altro)");
        expect(el).toHaveAttribute('data-tone', 'wait');
        expect(el.title).toBe('prezzi_non_nel_feed');
    });

    it('exit_wait{wait:"mercato_sospeso"} -> "In attesa: mercato sospeso"', () => {
        renderTable(
            [trade({ id: 7 })],
            [activityRow({ id: 9, kind: 'exit_wait', payload: { trade_id: 7, kind: 'loss', reason: 'stop', wait: 'mercato_sospeso' } })],
        );
        expect(screen.getByTestId('safe-exit-status')).toHaveTextContent('In attesa: mercato sospeso');
    });

    // reperto letterale del brief: msg + locked:0 copiati dal payload vero
    // scritto da `_model_gate` / `_write_model_hold` (bot_service.py).
    it('exit_hold{msg:"incasso rifiutato...", locked:0} -> "Tenuta: incasso rifiutato..."', () => {
        renderTable(
            [trade({ id: 88, strategy: 'tennis' })],
            [activityRow({
                id: 3, kind: 'exit_hold',
                payload: {
                    trade_id: 88, event_id: 'e1', kind: 'profit', reason: 'time',
                    msg: 'incasso rifiutato: bloccherebbe +0,00 € invece di almeno +0,01 €',
                    p_lose: null, source: 'model', locked: 0, ev_hold: null,
                },
            })],
        );
        const el = screen.getByTestId('safe-exit-status');
        expect(el).toHaveTextContent('Tenuta: incasso rifiutato: bloccherebbe +0,00 € invece di almeno +0,01 €');
        expect(el).toHaveAttribute('data-tone', 'hold');
    });

    it('exit_hold{reason:"in_attesa_di_approvazione"} -> "Proposta in attesa della tua firma"', () => {
        renderTable(
            [trade({ id: 55, strategy: 'tennis' })],
            [activityRow({
                id: 4, kind: 'exit_hold',
                payload: { reason: 'in_attesa_di_approvazione', trade_id: 55, request_id: 9001, exit_kind: 'mandatory', exit_reason: 'obbligatoria', critical: true },
            })],
        );
        const el = screen.getByTestId('safe-exit-status');
        expect(el).toHaveTextContent('Proposta in attesa della tua firma');
        expect(el).toHaveAttribute('data-tone', 'proposal');
    });

    it('feed_blind{reason:"punteggio_assente"} (dato mancante, non mercato assente) -> "In attesa: punteggio assente nel feed"', () => {
        renderTable(
            [trade({ id: 12 })],
            [activityRow({
                id: 6, kind: 'feed_blind',
                payload: { trade_id: 12, event_id: 'e1', reason: 'punteggio_assente', critical: true, da_s: 12.3 },
            })],
        );
        const el = screen.getByTestId('safe-exit-status');
        expect(el).toHaveTextContent('In attesa: punteggio assente nel feed');
        expect(el).toHaveAttribute('data-tone', 'blind-data');
    });

    it('exit_hold GIA coperto da meta.exit_hold (trade-hold): niente riga duplicata', () => {
        renderTable(
            [trade({ id: 99, meta: { exit_hold: { reason: 'wide_margin', p_lose: 0.004 } } })],
            [activityRow({ id: 8, kind: 'exit_hold', payload: { trade_id: 99, msg: 'margine ampio: tengo', locked: 1.2 } })],
        );
        // "In attesa: margine ampio" resta l'UNICA riga: la seconda (Tenuta)
        // sarebbe la stessa informazione con parole diverse.
        expect(screen.getByTestId('trade-hold')).toBeInTheDocument();
        expect(screen.queryByTestId('safe-exit-status')).toBeNull();
    });

    it('nessuna attività di uscita per quel trade: niente riga (nessuna invenzione)', () => {
        renderTable([trade({ id: 1 })], [activityRow({ id: 1, kind: 'exit_wait', payload: { trade_id: 999, wait: 'mercato_sospeso' } })]);
        expect(screen.queryByTestId('safe-exit-status')).toBeNull();
    });

    // FALSIFICAZIONE — funzione pura: senza la mappatura del kind (return
    // null) o con una tabella wait/reason vuota, il test qui sotto deve
    // rompersi. Si dimostra rimuovendo l'implementazione e osservando il rosso.
    it('FALSIFICAZIONE: latestExitActivityFor + safeActivityExitStatus sul payload vero non tornano null', () => {
        const rows: SafeActivityRow[] = [
            activityRow({ id: 1, kind: 'exit_wait', payload: { trade_id: 42, wait: 'prezzi_non_nel_feed' } }),
            activityRow({ id: 2, kind: 'other_kind', payload: { trade_id: 42 } }),
        ];
        const latest = latestExitActivityFor(42, rows);
        expect(latest).not.toBeNull();
        const status = safeActivityExitStatus(latest);
        expect(status).not.toBeNull();
        expect(status?.text).toContain('In attesa');
    });
});

// reperto 17/09 — punto 3 del brief: `odds.p2.lay = null` (qui il caso
// speculare: il BACK della nostra selezione assente sul book) non deve
// mostrare un trattino muto sulla colonna "Quota ora".
describe('SafeTradesTable — quota assente dal feed sulla nostra selezione', () => {
    const FEED_BACK_ASSENTE: Record<string, CalcioScanPayload> = {
        e1: {
            media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
            competition: 'Serie A', open_date: null, inplay: true,
            mo_market_id: '1.1', mo_status: 'OPEN',
            odds: {
                home: { selection_id: 11, back: 1.3, lay: 1.32 },
                draw: { selection_id: 58805, back: 5, lay: 5.2 },
                away: { selection_id: 12, back: 9, lay: 9.4 },
            },
            minute: 60, score_home: 0, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
            cs: {
                market_id: '1.5', status: 'OPEN', any_other_home: null, any_other_away: null,
                selections: [{
                    selection_id: 4, name: '3 - 2', runner_status: 'ACTIVE',
                    // fra un punto e l'altro: il lato con cui SI CHIUDE (back, su un
                    // trade LAY) sparisce dal book per qualche secondo
                    back: null, lay: 220, back_size: null, lay_size: 30,
                }],
            },
            ou: [],
        } as unknown as CalcioScanPayload,
    };

    it('back assente sul lato di chiusura -> "quota momentaneamente assente" (mai un trattino muto)', () => {
        render(
            <SafeTradesTable
                trades={[trade({
                    id: 47, strategy: 'esatto', market_id: '1.5', market_type: 'CORRECT_SCORE',
                    selection_id: 4, selection_name: '3 - 2', side: 'lay', price: 110, size: 5.26, liability: 573.34,
                })]}
                commissionPct={5}
                liveFeed={FEED_BACK_ASSENTE}
                onCashOut={vi.fn()}
            />,
        );
        const cell = screen.getByTestId('safe-price-missing');
        expect(cell).toHaveTextContent('quota momentaneamente assente');
        expect(screen.getByTestId('safe-price-now')).not.toHaveTextContent('—');
    });
});
