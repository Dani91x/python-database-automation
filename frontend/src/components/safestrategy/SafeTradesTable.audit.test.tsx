// ============================================================================
// Tabella trade Safe Strategy — quello che un TRADER deve vedere su ogni riga
// dopo l'indagine dell'11/09/2026:
//   R1    cash out anche sui mercati a gol (Over/Under, BTTS, 1X2 1T)
//   C-02  copertura parziale → "chiudi residuo"; copertura in volo → rischio pieno
//   H-01  "CHIUSO IN GREEN-UP" quando l'uscita è un green-up
//   H-05  "USCITA FALLITA, ritento alle HH:MM" / "in attesa di prezzo"
//   H-03  "IN VERIFICA SU BETFAIR" per le riserve a esito ignoto
//   M-05  errore DEFINITIVO come stato terminale
//   M-21  azione "Annulla" sulle riserve + esito della richiesta sulla riga
//   L-02  ora col fuso di Roma, commissione DEL TRADE
//   L-04  avviso onesto sulle chiusure orfane
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SafeTradesTable, safeRowStatus, exitRunLine } from './SafeTradesTable';
import type { SafeRequest, SafeTrade } from '@/lib/safeBot';
import type { CalcioScanPayload } from '@/lib/safeStrategyScan';

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 39, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'manual',
        market_id: '1.30', market_type: 'OVER_UNDER_35', selection_id: 47973, selection_name: 'Under 3.5',
        side: 'back', mode: 'paper', price: 1.38, size: 10, liability: 10, commission: 0.05,
        minute_at_entry: 62, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-11T18:00:00Z', settled_at: null, origin: 'manual',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

/** feed dello scanner con i mercati a gol (quello che il servizio scrive davvero) */
const FEED: Record<string, CalcioScanPayload> = {
    e1: {
        media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
        competition: 'Serie A', open_date: null, inplay: true,
        mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { selection_id: 11, back: 1.3, lay: 1.32 },
            draw: { selection_id: 58805, back: 5, lay: 5.2 },
            away: { selection_id: 12, back: 9, lay: 9.4 },
        },
        minute: 62, score_home: 2, score_away: 1, red_home: 0, red_away: 0, pre_ko: null,
        cs: { market_id: '1.5', status: 'OPEN', selections: [], any_other_home: null, any_other_away: null },
        ou: [{
            market_id: '1.30', status: 'OPEN', market_type: 'OVER_UNDER_35', line: 3.5,
            selections: [
                { selection_id: 47972, name: 'Over 3.5', runner_status: 'ACTIVE', back: 3.4, lay: 3.5, back_size: 40, lay_size: 30 },
                { selection_id: 47973, name: 'Under 3.5', runner_status: 'ACTIVE', back: 1.38, lay: 1.44, back_size: 80, lay_size: 60 },
            ],
        }],
    } as CalcioScanPayload,
};

function renderTable(rows: SafeTrade[], extra: Partial<React.ComponentProps<typeof SafeTradesTable>> = {}) {
    const onCashOut = vi.fn();
    const onCancel = vi.fn();
    render(
        <SafeTradesTable
            trades={rows}
            commissionPct={5}
            liveFeed={FEED}
            onCashOut={onCashOut}
            onCancel={onCancel}
            {...extra}
        />,
    );
    return { onCashOut, onCancel };
}

describe('R1 — cash out sui mercati a gol, non solo Match Odds/Correct Score', () => {
    it('trade manuale su Under 3.5: quota ORA, Δ tick, "se chiudo ora" e cash out ATTIVO', () => {
        renderTable([trade()]);
        const row = screen.getByTestId('safe-trade-row');
        // best LAY della stessa selezione (si chiude bancando): 1,44
        expect(within(row).getByTestId('safe-price-now')).toHaveTextContent('1,44');
        expect(within(row).getByTestId('safe-tick-delta')).toHaveTextContent('+6');
        // back 10 @1,38 → vince +3,80 / perde −10,00 ; chiusura lay @1,44
        expect(within(row).getByTestId('safe-close-now')).toHaveTextContent('−0,42 €');
        const trigger = within(row).getByTestId('cashout-trigger');
        expect(trigger).toBeEnabled();
        expect(trigger).not.toHaveAttribute('data-residual');
    });

    it('mercato non nel feed: nessun prezzo inventato, cash out spento', () => {
        renderTable([trade({ market_id: '9.99', market_type: 'ASIAN_HANDICAP' })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-price-now')).toHaveTextContent('—');
        expect(within(row).getByTestId('cashout-trigger')).toBeDisabled();
    });

    it('ora di piazzamento con il fuso di Roma (L-02)', () => {
        renderTable([trade()]);
        // 18:00 UTC = 20:00 a Roma
        expect(screen.getByTestId('safe-trade-row')).toHaveTextContent('20:00');
        expect(screen.getByText('Ora (Roma)')).toBeInTheDocument();
    });
});

describe('C-02 / M-06 — copertura parziale e copertura in volo', () => {
    it('COPERTA 40 %: stato, liability residua e bottone "chiudi residuo"', () => {
        renderTable([trade({
            status: 'open',
            meta: { hedge: { fraction: 0.4, complete: false, remaining_liability: 6, hedged_size: 4, residual_size: 6 } },
        })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('COPERTA 40 %');
        const trigger = within(row).getByTestId('cashout-trigger');
        expect(trigger).toBeEnabled();
        expect(trigger).toHaveAttribute('data-residual', '1');
        expect(trigger).toHaveTextContent('residuo');
    });

    it('una posizione hedged coperta solo in parte resta chiudibile', () => {
        renderTable([trade({ status: 'hedged', meta: { hedge: { fraction: 0.4, complete: false, remaining_liability: 6 } } })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('COPERTA 40 %');
        expect(within(row).getByTestId('cashout-trigger')).toBeEnabled();
    });

    // contratto backend 11/09: con la chiusura IN VOLO il rischio è ancora pieno
    it('copertura IN VOLO: "rischio ancora pieno" e nessun importo residuo', () => {
        renderTable([trade({
            status: 'open',
            meta: { hedging: true, hedge: { fraction: 1, complete: true, remaining_liability: 10 } },
        })], { isCashOutPending: () => true });
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-hedge-inflight'))
            .toHaveTextContent('rischio ancora pieno: copertura in volo');
        expect(within(row).getByTestId('cashout-trigger')).not.toHaveAttribute('data-residual');
    });

    it('copertura COMPLETA e confermata: nessun cash out, P&L bloccato', () => {
        renderTable([trade({ status: 'hedged', pnl: 1.2, meta: { locked_pnl: 1.2, hedge: { fraction: 1, complete: true } } })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('CHIUSO');
        expect(within(row).getByTestId('safe-locked-pnl')).toHaveTextContent('+1,20 € bloccato');
        expect(within(row).queryByTestId('cashout-trigger')).toBeNull();
    });
});

describe('stati che richiedono una decisione', () => {
    it('H-03: riserva a esito ignoto = IN VERIFICA SU BETFAIR (non "IN CORSO")', () => {
        renderTable([trade({ status: 'pending', meta: { reason: 'place_exception_reconciling' } })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('IN VERIFICA SU BETFAIR');
        expect(within(row).getByTestId('safe-reason')).toHaveTextContent('in verifica su Betfair');
        // non annullabile: il servizio rifiuterebbe
        expect(within(row).getByTestId('safe-cancel')).toBeDisabled();
    });

    it('H-05: uscita fallita definitivamente, con l ora del prossimo tentativo', () => {
        renderTable([trade({
            meta: { exit: { state: 'failed', kind: 'loss', attempts: 3, next_retry_at: '2026-09-11T18:07:00Z', last_error: 'INSUFFICIENT_FUNDS' } },
        })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('USCITA FALLITA');
        expect(within(row).getByTestId('safe-exit-run')).toHaveTextContent('USCITA FALLITA, ritento alle 20:07');
    });

    it('H-05: uscita in attesa di prezzo', () => {
        renderTable([trade({ meta: { exit: { state: 'waiting_price', kind: 'profit' } } })]);
        expect(screen.getByTestId('safe-exit-run')).toHaveTextContent('in attesa di prezzo');
    });

    it('H-18: posizione viva senza riga nel feed', () => {
        renderTable([trade({ meta: { blind_since: '2026-09-11T17:45:00Z' } })]);
        expect(screen.getByTestId('safe-status')).toHaveTextContent('SENZA FEED da 19:45');
    });

    it('M-05: errore DEFINITIVO è uno stato terminale, non "in corso"', () => {
        renderTable([trade({ status: 'pending', meta: { error_final: true, error_at: '2026-09-11T18:01:00Z', last_error: 'INVALID_ODDS' } })]);
        const badge = screen.getByTestId('safe-status');
        expect(badge).toHaveTextContent('ERRORE DEFINITIVO');
        expect(badge.title).toMatch(/INVALID_ODDS/);
    });

    it('combinazione rotta: "COMBO INCOMPLETA: in chiusura"', () => {
        renderTable([trade({ strategy: 'model', meta: { kind: 'combo', combo_incomplete: true } })]);
        expect(screen.getByTestId('safe-status')).toHaveTextContent('COMBO INCOMPLETA: in chiusura');
    });

    it('H-01: chiusura in green-up dichiarata sullo stato', () => {
        renderTable([
            trade({ id: 70, side: 'lay', price: 55, size: 2.16, liability: 116.64, status: 'hedged', pnl: -22.1, meta: { locked_pnl: -22.1, exit_kind: 'greenup', exit_reason: 'gol al 29' } }),
            trade({ id: 71, side: 'back', price: 4.9, size: 24.24, status: 'open', closes_trade_id: 70, meta: { exit_kind: 'greenup' } }),
        ]);
        expect(screen.getByTestId('safe-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(screen.getByTestId('safe-closing-row')).toHaveTextContent('Green-up di #70');
    });

    it('cash out MANUALE riconosciuto come tale', () => {
        renderTable([
            trade({ id: 70, status: 'hedged', pnl: 0.5, meta: { locked_pnl: 0.5 } }),
            trade({ id: 71, status: 'open', closes_trade_id: 70, origin: 'manual', meta: { cashout: true } }),
        ]);
        expect(screen.getByTestId('safe-status')).toHaveTextContent('CASH OUT MANUALE');
    });
});

describe('M-21 / L-07 — Annulla le riserve e vedi l esito di ogni richiesta', () => {
    it('riserva pending: bottone Annulla che chiama la coda', async () => {
        const user = userEvent.setup();
        const { onCancel } = renderTable([trade({ status: 'pending' })]);
        await user.click(screen.getByTestId('safe-cancel'));
        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(onCancel.mock.calls[0][0]).toMatchObject({ id: 39 });
    });

    it('senza onCancel non compare nessun bottone (contratto opzionale)', () => {
        render(<SafeTradesTable trades={[trade({ status: 'pending' })]} commissionPct={5} liveFeed={FEED} onCashOut={vi.fn()} />);
        expect(screen.queryByTestId('safe-cancel')).toBeNull();
    });

    it('richiesta RIFIUTATA dal servizio: motivo visibile sulla riga', () => {
        const requests: SafeRequest[] = [{
            id: 5, kind: 'cancel', payload: { trade_id: 39 }, status: 'rejected',
            result: { rejected: true, message: "ordine gia' a mercato" },
            created_at: 'x', updated_at: null,
        }];
        renderTable([trade({ status: 'pending' })], { requests });
        const out = screen.getByTestId('safe-request-outcome');
        expect(out).toHaveAttribute('data-tone', 'rejected');
        expect(out).toHaveTextContent("rifiutato: ordine gia' a mercato");
    });

    it('cash out eseguito: esito e sorgente delle quote', () => {
        const requests: SafeRequest[] = [{
            id: 6, kind: 'cashout', payload: { trade_id: 39 }, status: 'done',
            result: { ok: true, message: 'chiusura inviata', source: 'rest' },
            created_at: 'x', updated_at: null,
        }];
        renderTable([trade()], { requests });
        expect(screen.getByTestId('safe-request-outcome'))
            .toHaveTextContent('eseguito: chiusura inviata (quote dal book Betfair)');
    });
});

describe('L-02 / L-04 — commissione del trade, risultato reale, chiusure orfane', () => {
    it('la commissione della CHIUSURA è quella della chiusura, non il parametro', () => {
        renderTable([
            trade({ id: 70, status: 'hedged', pnl: 1 }),
            trade({ id: 71, status: 'hedged', closes_trade_id: 70, commission: 0.02, pnl: 1 }),
        ]);
        expect(screen.getByTestId('safe-closing-row')).toHaveTextContent('commissione 2,0 %');
    });

    it('posizione regolata: mostra il risultato REALE della partita dal feed', () => {
        renderTable([trade({ status: 'won', pnl: 3.8, settled_at: '2026-09-11T19:00:00Z' })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(within(row).getByTestId('safe-real-score')).toHaveTextContent('2-1');
        expect(within(row).getByTestId('safe-status')).toHaveTextContent('VINTO');
    });

    it('chiusura senza la sua apertura: avviso onesto, non una riga muta', () => {
        renderTable([trade({ id: 71, closes_trade_id: 70 })]);
        expect(screen.getByTestId('safe-orphan-note'))
            .toHaveTextContent(/senza la loro apertura|senza la sua apertura/);
        expect(screen.getByText('chiude #70')).toBeInTheDocument();
    });

    it('tabella vuota: testo che dice cosa fare', () => {
        renderTable([]);
        expect(screen.getByTestId('safe-trades-empty')).toHaveTextContent(/piazza da un segnale/);
    });
});

describe('funzioni PURE dello stato di riga', () => {
    it('safeRowStatus: ordine di gravità (errore → verifica → combo → esito)', () => {
        expect(safeRowStatus(trade({ status: 'pending', meta: { error_final: true } })).label).toBe('ERRORE DEFINITIVO');
        expect(safeRowStatus(trade({ status: 'pending', meta: { reason: 'place_exception_reconciling' } })).label).toBe('IN VERIFICA SU BETFAIR');
        expect(safeRowStatus(trade({ meta: { combo_incomplete: true } })).label).toMatch(/COMBO INCOMPLETA/);
        expect(safeRowStatus(trade({ status: 'won' })).label).toBe('VINTO');
        expect(safeRowStatus(trade({ status: 'lost' })).label).toBe('PERSO');
        expect(safeRowStatus(trade({ status: 'void' })).label).toBe('VOID');
        expect(safeRowStatus(trade({ status: 'open' })).label).toBe('APERTO');
        expect(safeRowStatus(trade({ status: 'pending' })).label).toBe('IN CORSO');
    });

    it('safeRowStatus: bordo colorato per esito (si legge a colpo d occhio)', () => {
        expect(safeRowStatus(trade({ status: 'won' })).edge).toMatch(/emerald/);
        expect(safeRowStatus(trade({ status: 'lost' })).edge).toMatch(/red/);
        expect(safeRowStatus(trade({ status: 'open' })).edge).toMatch(/sky/);
    });

    it('exitRunLine: testo italiano, con l ora di Roma', () => {
        expect(exitRunLine(trade({ meta: null }))).toBeNull();
        expect(exitRunLine(trade({ meta: { exit: { state: 'retrying', attempts: 2, next_retry_at: '2026-09-11T18:07:00Z' } } })))
            .toBe('uscita: ritento alle 20:07 (2°)');
        expect(exitRunLine(trade({ meta: { exit: { state: 'failed', attempts: 3 } } })))
            .toBe('USCITA FALLITA dopo 3 tentativi');
    });
});
