// Test COMPONENTE del dettaglio giornata: aperture con chiusure annidate,
// badge uscita automatica, P&L bloccato, link live per posizioni vive,
// totali, stati vuoto/errore. Include ExitBadge.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DayDetail } from './DayDetail';
import { ExitBadge } from './ExitBadge';
import type { DayTrade } from '@/lib/dailyHistory';

const OPEN: DayTrade = {
    id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'base', side: 'back', mode: 'paper',
    price: 1.3, size: 10, liability: 10, status: 'open', pnl: 0, placed_at: '2026-09-10T18:00:00Z', settled_at: null,
    origin: 'auto', closes_trade_id: null, meta: null, selection_name: 'Roma', closes: [], total_pnl: 0,
    placed_in_day: true, settled_in_day: false,
};
const HEDGED_WON: DayTrade = {
    ...OPEN, id: 2, event_name: 'Inter vs Milan', strategy: 'esatto', side: 'lay', price: 40, size: 5, liability: 195,
    status: 'won', pnl: 3.1, settled_at: '2026-09-10T20:00:00Z', mode: 'live',
    meta: { locked_pnl: 2.5, exit_kind: 'time', exit_reason: "72' raggiunto" },
    closes: [{
        id: 3, event_id: 'e1', event_name: 'Inter vs Milan', side: 'back', mode: 'live', price: 30, size: 6.5, liability: 6.5,
        status: 'won', pnl: -0.6, placed_at: '2026-09-10T19:30:00Z', settled_at: '2026-09-10T20:00:00Z',
        closes_trade_id: 2, meta: { size_capped_from: 8 }, selection_name: 'Any Other Home Win',
    }],
    total_pnl: 2.5, placed_in_day: false, settled_in_day: true,
};
const LOST: DayTrade = {
    ...OPEN, id: 4, event_name: 'Sinner v Alcaraz', sport: 'tennis', strategy: 'tennis', origin: 'manual',
    status: 'lost', pnl: -10, total_pnl: -10, settled_at: '2026-09-10T21:00:00Z', settled_in_day: true, meta: { exit_kind: 'loss' },
};

/**
 * CERT. 13/09 — badge di modalità ESPLICITO anche sulle righe PAPER.
 * Prima c'era solo sul LIVE: l'assenza di badge poteva voler dire «è paper»
 * oppure «il servizio non ha scritto la modalità», e su una tabella di soldi
 * veri quell'ambiguità si paga. Ora ogni riga lo dichiara.
 */
describe('DayDetail — modalità dichiarata su OGNI riga', () => {
    it('la riga PAPER ha il suo badge, non il vuoto', () => {
        render(<DayDetail day="2026-09-10" trades={[OPEN]} variant="safe" attribution="placed" />);
        const badge = screen.getByTestId('day-trade-mode');
        expect(badge).toHaveTextContent('PAPER');
        expect(badge.className).not.toMatch(/red/);
    });

    it('la riga LIVE resta in rosso e anche la chiusura dichiara la sua modalità', () => {
        render(<DayDetail day="2026-09-10" trades={[HEDGED_WON]} variant="safe" attribution="settled" />);
        const badges = screen.getAllByTestId('day-trade-mode');
        expect(badges[0]).toHaveTextContent('LIVE');
        expect(badges[0].className).toMatch(/red/);
        expect(screen.getByTestId('day-close-mode')).toHaveTextContent('LIVE');
    });
});

describe('DayDetail', () => {
    it('senza giorno: invito a selezionare', () => {
        render(<DayDetail day={null} trades={null} variant="safe" />);
        expect(screen.getByTestId('day-detail-empty')).toBeInTheDocument();
    });

    it('elenca aperture e chiusure con badge uscita, P&L bloccato, totale e link live', async () => {
        const user = userEvent.setup();
        const onGoLive = vi.fn();
        render(<DayDetail day="2026-09-10" trades={[OPEN, HEDGED_WON, LOST]} variant="safe" attribution="settled" onGoLive={onGoLive} />);
        expect(screen.getByTestId('day-detail')).toHaveTextContent(/giovedì 10 settembre 2026/);
        expect(screen.getByTestId('day-detail')).toHaveTextContent('3 trade');
        expect(screen.getByText('1 ancora vivi')).toBeInTheDocument();
        // totale = solo regolati: 2.5 − 10
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('−7,50 €');
        // liability piazzata OGGI: OPEN (10) + LOST (10); HEDGED_WON è di ieri
        expect(screen.getByTestId('day-detail')).toHaveTextContent('liability piazzata 20,00 €');

        const rows = screen.getAllByTestId('day-trade-row');
        expect(rows).toHaveLength(3);
        const hedged = rows[1];
        expect(within(hedged).getByText('R. ESATTO')).toBeInTheDocument();
        expect(within(hedged).getByText('LIVE')).toBeInTheDocument();
        expect(within(hedged).getByText('(prec.)')).toBeInTheDocument();
        expect(within(hedged).getByTestId('exit-badge')).toHaveTextContent('Uscita: tempo');
        expect(within(hedged).getByTestId('exit-badge')).toHaveAttribute('title', "72' raggiunto");
        expect(within(hedged).getByText('bloccato +2,50 €')).toBeInTheDocument();
        expect(within(hedged).getByTestId('day-trade-pnl')).toHaveTextContent('+2,50 €');

        const close = screen.getAllByTestId('day-close-row');
        expect(close).toHaveLength(1);
        expect(close[0]).toHaveTextContent('chiusura #3 di #2');
        expect(close[0]).toHaveTextContent('parziale');
        expect(close[0]).toHaveTextContent('−0,60 €');

        const lost = rows[2];
        expect(within(lost).getByTestId('exit-badge')).toHaveTextContent('Uscita: perdita');
        expect(within(lost).getByText('✋')).toBeInTheDocument();
        expect(within(lost).getByTestId('day-trade-pnl')).toHaveTextContent('−10,00 €');

        // apertura viva: link al live
        const open = rows[0];
        expect(within(open).getByTestId('day-trade-pnl')).toHaveTextContent('—');
        await user.click(within(open).getByTestId('day-trade-live'));
        expect(onGoLive).toHaveBeenCalledWith(OPEN);
        expect(within(hedged).queryByTestId('day-trade-live')).toBeNull();
    });

    it('Omega: una riga per PARTITA con gamba 2T, risultati reali e P&L (chiusure attaccate)', () => {
        const ft: DayTrade = {
            ...OPEN, strategy: undefined, selection_name: undefined, runner_name: '3 - 2', phase: 'ft_cs', side: 'lay',
            status: 'won', pnl: 2.16, total_pnl: -22.08, meta: { result_ht: '1-0', result_ft: '2-1', exit_kind: 'greenup', locked_pnl: -22.1 },
            closes: [{
                id: 9, event_id: 'e1', event_name: 'Roma vs Lazio', side: 'back', mode: 'paper', price: 4.9, size: 24.24, liability: 24.24,
                status: 'lost', pnl: -24.24, placed_at: '2026-09-10T18:30:00Z', settled_at: '2026-09-10T20:00:00Z',
                closes_trade_id: 1, meta: { exit_kind: 'greenup' },
            }],
        };
        render(<DayDetail day="2026-09-10" trades={[ft]} variant="omega" />);
        const row = screen.getByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-leg-ht')).toHaveAttribute('data-empty', '1');
        const leg = within(row).getByTestId('omega-leg-ft');
        expect(within(leg).getByText('3 - 2')).toBeInTheDocument();
        expect(within(leg).getByTestId('omega-side')).toHaveTextContent('LAY');
        expect(within(leg).getByTestId('omega-leg-pnl')).toHaveTextContent('−22,08 €');
        expect(within(leg).getByTestId('omega-closing-line')).toHaveAttribute('data-closes', '1');
        expect(within(row).getByTestId('omega-result-ht')).toHaveTextContent('1-0');
        expect(within(row).getByTestId('omega-result-ft')).toHaveTextContent('2-1');
        expect(within(row).getByTestId('omega-match-pnl')).toHaveTextContent('−22,08 €');
        expect(within(row).getByTestId('omega-match-pnl').className).toMatch(/text-red-400/);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('−22,08 €');
    });

    it('nessun trade / errore / caricamento', () => {
        const { rerender } = render(<DayDetail day="2026-09-10" trades={[]} variant="safe" />);
        expect(screen.getByTestId('day-detail-none')).toBeInTheDocument();
        rerender(<DayDetail day="2026-09-10" trades={null} loading variant="safe" />);
        expect(screen.getByTestId('day-detail-loading')).toHaveTextContent('caricamento…');
        rerender(<DayDetail day="2026-09-10" trades={[]} error="RPC assente" variant="safe" />);
        expect(screen.getByTestId('day-detail-error')).toHaveTextContent('RPC assente');
    });
});

describe('ExitBadge', () => {
    it('non renderizza senza uscita; mappa kind e tooltip', () => {
        const { container, rerender } = render(<ExitBadge meta={{ locked_pnl: 1 }} />);
        expect(container).toBeEmptyDOMElement();
        rerender(<ExitBadge meta={{ exit_kind: 'red_card', exit_reason: 'rosso alla favorita 61′' }} />);
        const b = screen.getByTestId('exit-badge');
        expect(b).toHaveTextContent('Uscita: rosso');
        expect(b).toHaveAttribute('data-exit-kind', 'red_card');
        expect(b).toHaveAttribute('title', 'rosso alla favorita 61′');
        rerender(<ExitBadge meta={{ exit_kind: 'forced' }} />);
        expect(screen.getByTestId('exit-badge')).toHaveTextContent('Uscita: obbligatoria');
        rerender(<ExitBadge meta={{ exit_kind: 'profit' }} />);
        expect(screen.getByTestId('exit-badge')).toHaveTextContent('Uscita: profitto');
    });
});

// ======================================= audit 11/09: H-11 / M-18 attribuzione
describe('DayDetail — attribuzione al giorno del calendario (H-11 / M-18)', () => {
    const base: DayTrade = {
        ...OPEN, status: 'won', pnl: 3, total_pnl: 3, settled_at: '2026-09-10T20:00:00Z', settled_in_day: true,
    };

    it("attribuzione 'settled' esplicita: NON somma un trade regolato in un ALTRO giorno", () => {
        const altro: DayTrade = { ...base, id: 11, total_pnl: -100, status: 'lost', placed_in_day: true, settled_in_day: false };
        render(<DayDetail day="2026-09-10" trades={[base, altro]} variant="safe" attribution="settled" />);
        // il calendario conta quel −100 in un'altra cella: qui NON entra
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+3,00 €');
        expect(screen.getByTestId('day-count')).toHaveTextContent('1 trade');
        expect(screen.getByTestId('day-other-days')).toHaveTextContent('+ 1 di altre giornate');
    });

    it("Omega ('placed'): somma le posizioni PIAZZATE oggi, non quelle regolate oggi", () => {
        const piazzataIeri: DayTrade = { ...base, id: 12, total_pnl: -50, status: 'lost', placed_in_day: false, settled_in_day: true };
        render(<DayDetail day="2026-09-10" trades={[base, piazzataIeri]} variant="omega" attribution="placed" />);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+3,00 €');
        expect(screen.getByTestId('day-other-days')).toHaveTextContent('+ 1 di altre giornate');
    });

    it("l'attribuzione si deduce dalla variante quando non è passata", () => {
        const piazzataIeri: DayTrade = { ...base, id: 13, total_pnl: -50, status: 'lost', placed_in_day: false, settled_in_day: true };
        const { rerender } = render(<DayDetail day="2026-09-10" trades={[piazzataIeri]} variant="omega" />);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('0,00 €');
        // giornata operativa = PIAZZAMENTO per tutti i bot (safe_strategy_bot_v2, mike_history_v2)
        rerender(<DayDetail day="2026-09-10" trades={[piazzataIeri]} variant="safe" />);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('0,00 €');
        rerender(<DayDetail day="2026-09-10" trades={[piazzataIeri]} variant="mike" />);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('0,00 €');
    });

    it('formati italiani anche nel dettaglio (€ dopo, virgola, ora di Roma)', () => {
        // attribuzione 'settled': la riga (piazzata ieri, regolata oggi) è
        // attribuita a questa giornata e quindi compare in tabella
        render(<DayDetail day="2026-09-10" trades={[HEDGED_WON]} variant="safe" attribution="settled" />);
        expect(screen.getByTestId('day-detail')).toHaveTextContent('liability piazzata 0,00 €');
        expect(screen.getAllByTestId('day-trade-row')[0]).toHaveTextContent('20:00');
    });
});

// ============================================================================
// CERTIFICAZIONE UI 12/09 — lo storico deve dire quello che dice il live
// ============================================================================
describe('DayDetail — badge, V/P e dati assenti (12/09)', () => {
    const RECON: DayTrade = {
        ...OPEN, id: 10, status: 'pending', event_name: 'Riserva ignota',
        meta: { reason: 'place_exception_reconciling', phase: 'reserved' },
    };
    const TERMINAL: DayTrade = {
        ...OPEN, id: 11, status: 'error', event_name: 'Mai piazzato',
        meta: { error_final: true, error_at: '2026-09-10T18:01:00Z' },
    };

    it('riserva a esito IGNOTO: «IN VERIFICA SU BETFAIR», non un innocuo «IN CORSO»', () => {
        render(<DayDetail day="2026-09-10" trades={[RECON]} variant="safe" />);
        expect(screen.getByTestId('day-trade-row')).toHaveTextContent('IN VERIFICA SU BETFAIR');
    });

    it('riga terminale: «ERRORE (definitivo)», così si sa che non è più viva', () => {
        render(<DayDetail day="2026-09-10" trades={[TERMINAL]} variant="safe" />);
        expect(screen.getByTestId('day-trade-row')).toHaveTextContent('ERRORE (definitivo)');
    });

    it('V/P del piede tabella = SEGNO del P&L totale, come la cella del calendario', () => {
        // Certificazione 12/09: `trading_daily_history` e i tre *_aggregates_sql
        // contano per segno del P&L della POSIZIONE. Contando lo stato, il
        // 10/09 la cella Omega diceva «11V 2P» e questo piede «12V 1P».
        const wonNegative: DayTrade = {
            ...OPEN, id: 12, status: 'won', pnl: -1.2, total_pnl: -1.2,
            settled_at: '2026-09-10T20:00:00Z', settled_in_day: true,
        };
        const lostPositive: DayTrade = {
            ...OPEN, id: 15, status: 'lost', pnl: -9, total_pnl: 2.4,
            settled_at: '2026-09-10T20:00:00Z', settled_in_day: true,
        };
        const voided: DayTrade = {
            ...OPEN, id: 13, status: 'void', pnl: 0, total_pnl: 0,
            settled_at: '2026-09-10T20:00:00Z', settled_in_day: true,
        };
        render(<DayDetail day="2026-09-10" trades={[wonNegative, lostPositive, voided]} variant="safe" />);
        const foot = screen.getByTestId('day-detail').querySelector('tfoot') as HTMLElement;
        expect(foot).toHaveTextContent('1V 1P');
        expect(foot).toHaveTextContent('1 void');
    });

    it('stake/liability mai scritti: «—», non uno zero credibile', () => {
        const senzaImporti: DayTrade = { ...OPEN, id: 14, size: null, liability: null };
        render(<DayDetail day="2026-09-10" trades={[senzaImporti]} variant="safe" />);
        const cells = within(screen.getByTestId('day-trade-row')).getAllByRole('cell');
        // colonne: Ora, Match, Strategia, Selezione, Lato, Quota, Stake, Liability, ...
        expect(cells[6]).toHaveTextContent('—');
        expect(cells[7]).toHaveTextContent('—');
    });
});

describe('DayDetail — righe e totali dicono la stessa cosa (12/09)', () => {
    it("le righe di un'ALTRA giornata non entrano nella tabella (né nei totali)", () => {
        // attribuzione 'placed': HEDGED_WON è stata piazzata ieri
        render(<DayDetail day="2026-09-10" trades={[OPEN, HEDGED_WON, LOST]} variant="safe" attribution="placed" />);
        expect(screen.getByTestId('day-count')).toHaveTextContent('2 trade');
        expect(screen.getByTestId('day-other-days')).toHaveTextContent('+ 1 di altre giornate');
        expect(screen.getAllByTestId('day-trade-row')).toHaveLength(2);
        expect(screen.queryByText('Inter vs Milan')).toBeNull();
    });

    it('solo righe di altre giornate: lo dice, non una tabella vuota', () => {
        render(<DayDetail day="2026-09-10" trades={[HEDGED_WON]} variant="safe" attribution="placed" />);
        expect(screen.getByTestId('day-detail-none')).toHaveTextContent("un’altra giornata");
    });
});

describe('DayDetail — nessuno zero prima dei dati (12/09)', () => {
    it('trades null: «caricamento…» e trattini, mai «0 trade · realizzato +0,00 €»', () => {
        render(<DayDetail day="2026-09-12" trades={null} loading variant="mike" />);
        const head = screen.getByTestId('day-detail');
        expect(screen.getByTestId('day-count')).toHaveTextContent('caricamento');
        expect(screen.getByTestId('day-count')).not.toHaveTextContent('0 trade');
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('—');
        expect(head).not.toHaveTextContent('+0,00 €');
        expect(head).toHaveTextContent('liability piazzata —');
        expect(screen.getByTestId('day-detail-loading')).toBeInTheDocument();
        expect(screen.queryByTestId('day-detail-none')).toBeNull();
    });

    it('giornata davvero vuota (lista caricata): allora lo zero si può dire', () => {
        render(<DayDetail day="2026-09-12" trades={[]} variant="mike" />);
        expect(screen.getByTestId('day-count')).toHaveTextContent('0 trade');
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('+0,00 €');
        expect(screen.getByTestId('day-detail-none')).toBeInTheDocument();
    });
});

// ============================================================================
// CERTIFICAZIONE REPORTISTICA 12/09 — testata del dettaglio = cella del
// calendario (numeri ricostruiti dai dati reali del 12/09/2026).
// ============================================================================
describe('DayDetail — la testata dice gli stessi numeri del calendario (12/09)', () => {
    const OPEN_HEDGED: DayTrade = {
        ...OPEN, id: 20, status: 'open', pnl: 0, total_pnl: -2.67, liability: 100,
        closes: [{
            id: 21, event_id: 'e1', event_name: 'Roma vs Lazio', side: 'lay', mode: 'paper',
            price: 3, size: 4, liability: 8, status: 'lost', pnl: -2.67,
            placed_at: '2026-09-12T09:00:00Z', settled_at: '2026-09-12T09:30:00Z',
            closes_trade_id: 20, meta: null,
        }],
    };
    const WON_190: DayTrade = {
        ...OPEN, id: 22, status: 'won', pnl: 1.9, total_pnl: 1.9, liability: 66,
        settled_at: '2026-09-12T08:45:00Z', settled_in_day: true,
    };

    it('copertura già incassata su posizione viva: realizzato −0,77 €, non +1,90 €', () => {
        render(<DayDetail day="2026-09-12" trades={[WON_190, OPEN_HEDGED]} variant="safe" attribution="placed" />);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('−0,77 €');
        expect(screen.getByTestId('day-realized-on-open')).toHaveTextContent('−2,67 €');
        // la riga viva mostra quanto ha già incassato, non un «—» muto
        const rows = screen.getAllByTestId('day-trade-row');
        expect(within(rows[1]).getByTestId('day-trade-pnl')).toHaveTextContent('−2,67 €');
    });

    it('ordini mai arrivati a mercato: visibili ma fuori da conteggio e liability', () => {
        const failed: DayTrade = { ...OPEN, id: 23, status: 'error', pnl: 0, total_pnl: 0, liability: 10, bet_id: null };
        render(<DayDetail day="2026-09-12" trades={[WON_190, failed]} variant="safe" attribution="placed" />);
        expect(screen.getByTestId('day-count')).toHaveTextContent('1 trade');
        expect(screen.getByTestId('day-not-placed')).toHaveTextContent('1 non piazzati');
        expect(screen.getByTestId('day-detail')).toHaveTextContent('liability piazzata 66,00 €');
        // la riga fallita resta in tabella: un ordine perso è un'informazione
        expect(screen.getAllByTestId('day-trade-row')).toHaveLength(2);
    });
});
