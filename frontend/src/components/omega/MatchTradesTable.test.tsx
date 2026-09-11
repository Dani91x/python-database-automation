// Test della TABELLA PARTITE di Omega: stati leggibili (H-02/M-05/M-06),
// quota live + freschezza del feed, "se chiudo ora" netto della commissione
// FISSATA sul trade (L-02) e badge del green-up (H-04).
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import {
    MatchTradesTable, legStatusBadge, closeNowPnl, FEED_STALE_S,
} from './MatchTradesTable';
import type { MatchTradeLike } from '@/lib/omegaMatches';

function t(over: Partial<MatchTradeLike> & { id: number }): MatchTradeLike {
    return {
        event_id: 'e1', event_name: 'Roma vs Lazio', phase: 'ft_cs', side: 'lay', status: 'open', pnl: 0,
        price: 110, size: 5.26, liability: 573.34, placed_at: '2026-09-11T14:00:00Z', settled_at: null,
        kickoff: '2026-09-11T13:30:00Z', closes_trade_id: null, meta: {}, runner_name: '3 - 2',
        minute_at_entry: 42, score_at_entry: '0-0', origin: 'auto', mode: 'paper',
        ...over,
    } as MatchTradeLike & { selection_id?: number };
}

const NOW = Date.parse('2026-09-11T16:00:00Z');
// il 3-2 si è allontanato: la quota è SALITA → chiudendo il lay si incassa
const FEED = {
    e1: {
        minute: 60, score_home: 0, score_away: 0,
        cs: { market_id: '1.1', status: 'OPEN', selections: [{ selection_id: 4, name: '3 - 2', back: 200, lay: 220 }] },
    },
} as never;

function renderTable(trades: MatchTradeLike[], over: Record<string, unknown> = {}) {
    return render(
        <MatchTradesTable
            trades={trades}
            liveFeed={FEED}
            feedUpdatedAt={{ e1: new Date(NOW - 3000).toISOString() }}
            nowMs={NOW}
            liveView
            commission={5}
            day="2026-09-11"
            {...over}
        />,
    );
}

// ------------------------------------------------------------------- puri
describe('legStatusBadge — una parola sola per ogni stato', () => {
    it('stati base in italiano', () => {
        expect(legStatusBadge({ status: 'pending' }).label).toBe('IN CORSO');
        expect(legStatusBadge({ status: 'open' }).label).toBe('APERTO');
        // glossario §3: lo stato nudo e' "CHIUSO"; "CHIUSO A MERCATO" solo
        // quando il servizio ha DETTO che l'uscita e' stata a mercato
        expect(legStatusBadge({ status: 'hedged' }).label).toBe('CHIUSO');
        expect(legStatusBadge({ status: 'hedged', exitKind: 'time' }).label).toBe('CHIUSO A MERCATO');
        expect(legStatusBadge({ status: 'hedged', exitKind: 'forced' }).label).toBe('CHIUSO A MERCATO');
        expect(legStatusBadge({ status: 'won' }).label).toBe('VINTO');
        expect(legStatusBadge({ status: 'lost' }).label).toBe('PERSO');
        expect(legStatusBadge({ status: 'void' }).label).toBe('VOID');
        expect(legStatusBadge({ status: 'boh' }).label).toBe('ERRORE');
    });

    it('H-02: la verifica su Betfair vince su "IN CORSO"', () => {
        expect(legStatusBadge({ status: 'pending', reconciling: true }).label).toBe('IN VERIFICA SU BETFAIR');
        // ma un esito già arrivato resta l'esito
        expect(legStatusBadge({ status: 'won', reconciling: true }).label).toBe('VINTO');
    });

    it('M-05: una riga terminale è un ERRORE DEFINITIVO', () => {
        expect(legStatusBadge({ status: 'pending', terminal: true }).label).toBe('ERRORE (definitivo)');
    });

    it('chiusure: green-up, cash out manuale, chiusura a mercato', () => {
        expect(legStatusBadge({ status: 'hedged', exitKind: 'greenup' }).label).toBe('CHIUSO IN GREEN-UP');
        expect(legStatusBadge({ status: 'hedged', exitKind: 'manual' }).label).toBe('CASH OUT MANUALE');
    });

    it('M-06: copertura parziale con la percentuale e quanto resta', () => {
        expect(legStatusBadge({
            status: 'open',
            hedge: { fraction: 0.4, remainingLiability: 315.78, hedgedSize: 2.1, size: 5.26, residualSize: 3.16, complete: false, at: null },
        }).label).toBe('COPERTA 40 % (restano 315,78 €)');
        // copertura COMPLETA: non è "coperta 100 %", è chiusa
        expect(legStatusBadge({
            status: 'hedged',
            hedge: { fraction: 1, remainingLiability: 0, hedgedSize: 5.26, size: 5.26, residualSize: 0, complete: true, at: null },
        }).label).toBe('CHIUSO');
    });
});

describe('closeNowPnl — P&L se chiudo ORA, netto della commissione', () => {
    it('lay 5,26 @110 chiuso con back @200 (quota salita): utile, netto della commissione', () => {
        // lay: win = −5.26*(110−1) = −573.34, lose = +5.26 → si copre con un BACK
        const r = closeNowPnl({ win: -573.34, lose: 5.26 }, { back: 200, lay: 220 }, 5);
        expect(r).not.toBeNull();
        expect(r!.price).toBe(200);
        expect(r!.gross).toBeCloseTo(1.77, 2);   // stake di copertura arrotondato ai centesimi
        expect(r!.net).toBeCloseTo(1.68, 2);     // 5 % di commissione sull'utile
        // commissione 0 → netto = lordo
        expect(closeNowPnl({ win: -573.34, lose: 5.26 }, { back: 200, lay: 220 }, 0)!.net)
            .toBe(r!.gross);
    });

    it('quota SCESA: chiudere costa, e la commissione non tocca una perdita', () => {
        const r = closeNowPnl({ win: -573.34, lose: 5.26 }, { back: 100, lay: 120 }, 5);
        expect(r!.gross).toBeLessThan(0);
        expect(r!.net).toBe(r!.gross);
    });

    it('nessun prezzo di chiusura: null (mai un numero inventato)', () => {
        expect(closeNowPnl({ win: -100, lose: 5 }, { back: null, lay: null }, 5)).toBeNull();
        expect(closeNowPnl({ win: 0, lose: 0 }, { back: 3, lay: 3.1 }, 5)).toBeNull();
    });
});

// -------------------------------------------------------------- rendering
describe('MatchTradesTable — vista live', () => {
    it('quota LIVE, età del feed e "se chiudo ora"', () => {
        renderTable([t({ id: 1, selection_id: 4 } as never)]);
        const live = screen.getByTestId('omega-leg-live');
        expect(live).toHaveTextContent('LAY 220,00');
        expect(live).toHaveTextContent('BACK 200,00');
        expect(within(live).getByTestId('omega-feed-age')).toHaveTextContent('feed 3 s');
        expect(within(live).getByTestId('omega-feed-age')).not.toHaveAttribute('data-stale');
        expect(within(live).getByTestId('omega-close-now')).toHaveTextContent(/se chiudo ora \+.* netti/);
    });

    it(`feed più vecchio di ${FEED_STALE_S} s: "FEED FERMO" in faccia`, () => {
        renderTable([t({ id: 1, selection_id: 4 } as never)], {
            feedUpdatedAt: { e1: new Date(NOW - 60_000).toISOString() },
        });
        const ages = screen.getAllByTestId('omega-feed-age');
        expect(ages[0]).toHaveAttribute('data-stale', '1');
        expect(ages[0]).toHaveTextContent('FEED FERMO da 1 min');
    });

    it('nessuna riga di feed per la partita: FEED ASSENTE (non un silenzio)', () => {
        renderTable([t({ id: 1, selection_id: 4 } as never)], { feedUpdatedAt: {} });
        expect(screen.getAllByTestId('omega-feed-age')[0]).toHaveTextContent('FEED ASSENTE');
    });

    it('L-02: la commissione della riga (2 %) batte il parametro del form (5 %)', () => {
        renderTable([t({ id: 1, selection_id: 4, meta: { commission: 0.02 } } as never)]);
        expect(screen.getByTestId('omega-close-now').getAttribute('title'))
            .toMatch(/commissione 2,0 % fissata sul trade/);
    });

    it('vista STORICO (liveView false): nessuna quota live, nessun "FEED ASSENTE"', () => {
        renderTable([t({ id: 1, selection_id: 4 } as never)], { liveView: false, feedUpdatedAt: {} });
        expect(screen.queryByTestId('omega-leg-live')).toBeNull();
        expect(screen.queryByTestId('omega-feed-age')).toBeNull();
    });

    it('ore in fuso Europe/Rome (L-02)', () => {
        renderTable([t({ id: 1, selection_id: 4 } as never)]);
        const row = screen.getByTestId('omega-match-row');
        expect(row).toHaveTextContent('16:00');       // 14:00Z = 16:00 a Roma
        expect(row).toHaveTextContent('KO 15:30');
    });

    it('H-04: il badge del green-up compare accanto allo stato', () => {
        renderTable([t({ id: 1, selection_id: 4, meta: { greenup: { state: 'hold', reason: 'margine ampio', p_lose: 0.004, ev: 1.8 } } } as never)]);
        const badge = screen.getByTestId('omega-greenup-badge');
        expect(badge).toHaveAttribute('data-greenup-state', 'hold');
        expect(badge).toHaveTextContent('TENGO');
        expect(screen.getByTestId('omega-greenup-reason')).toHaveTextContent('margine ampio');
    });

    it('vuoto: testo esplicito', () => {
        render(<MatchTradesTable trades={[]} emptyText="niente oggi" />);
        expect(screen.getByTestId('omega-matches-empty')).toHaveTextContent('niente oggi');
    });
});

// ======================= contratto 11/09 (seconda passata): 1, 2, 5
describe('legStatusBadge — exit_kind con la semantica nuova (2)', () => {
    it('un green-up chiuso in PERDITA non è un badge verde', () => {
        expect(legStatusBadge({ status: 'hedged', exitKind: 'loss' }))
            .toMatchObject({ label: 'CHIUSO IN PERDITA' });
        expect(legStatusBadge({ status: 'hedged', exitKind: 'loss' }).cls).toMatch(/red/);
    });

    it('chiusura in UTILE parziale: exit_kind profit (verde)', () => {
        expect(legStatusBadge({ status: 'hedged', exitKind: 'profit' }))
            .toMatchObject({ label: 'CHIUSO IN UTILE' });
        expect(legStatusBadge({ status: 'hedged', exitKind: 'profit' }).cls).toMatch(/emerald/);
    });

    it('meta.exit_profit decide anche senza exit_kind (affidabile sul parziale)', () => {
        expect(legStatusBadge({ status: 'hedged', exitProfit: false }).label).toBe('CHIUSO IN PERDITA');
        expect(legStatusBadge({ status: 'hedged', exitProfit: true }).label).toBe('CHIUSO IN UTILE');
    });

    it("'greenup' resta riservato alla chiusura integrale in verde", () => {
        expect(legStatusBadge({ status: 'hedged', exitKind: 'greenup', exitProfit: true }).label)
            .toBe('CHIUSO IN GREEN-UP');
    });
});

describe('MatchTradesTable — contratto aggiornato', () => {
    it('(1) chiusura IN VOLO: il rischio mostrato è la liability PIENA', () => {
        renderTable([t({
            id: 1, selection_id: 4, status: 'open',
            meta: {
                hedging: true,
                hedge: { fraction: 0.4, remaining_liability: 573.34, hedged_size: 2.1, residual_size: 3.16, complete: false },
            },
        } as never)]);
        const row = screen.getByTestId('omega-match-row');
        expect(row).toHaveTextContent('rischio 573,34 €');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('COPERTA 40 % (restano 573,34 €)');
    });

    it('(5) riga in errore: "ERRORE alle HH:MM" da meta.error_at (non da settled_at)', () => {
        renderTable([t({
            id: 1, selection_id: 4, status: 'error', settled_at: null,
            meta: { error_final: true, reason: 'FOK ucciso', error_at: '2026-09-11T15:45:00Z' },
        } as never)]);
        const err = screen.getByTestId('omega-terminal-error');
        expect(err).toHaveTextContent('ERRORE alle 17:45');
        expect(screen.getByTestId('omega-status')).toHaveTextContent('ERRORE (definitivo)');
    });

    it('(2) la riga di una posizione chiusa in perdita lo dice in rosso', () => {
        renderTable([t({
            id: 1, selection_id: 4, status: 'hedged',
            meta: { exit_kind: 'loss', exit_profit: false, exit_reason: 'uscita in perdita controllata', locked_pnl: -22.1 },
        } as never)]);
        const badge = screen.getByTestId('omega-status');
        expect(badge).toHaveTextContent('CHIUSO IN PERDITA');
        expect(badge.className).toMatch(/red/);
        expect(screen.getByTestId('omega-locked-pnl')).toHaveTextContent('−22,10 € bloccato');
    });
});
