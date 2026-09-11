// Test della SCHEDA di una partita Mike: zone sempre presenti (altezza stabile),
// numeri del servizio (mai ricalcolati in UI), frecce di variazione delle quote,
// dialog di cash out con il dettaglio per gamba.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeMatchCard } from './MikeMatchCard';
import { MIKE_PARAM_DEFAULTS, type MikeEvent, type MikeLeg } from '@/lib/mike';

const NOW = new Date().toISOString();

function leg(over: Partial<MikeLeg> = {}): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10,
        matched: 10, avg_price: 1.5, ref: 'r1', status: 'open', placed_at: 0, persistence: 'LAPSE',
        cycle_no: 0, final: false, archived: false, ...over,
    };
}

function ev(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() + 3600_000).toISOString(), mode: 'paper', markets: {}, state: 'WATCH',
        cycle_no: 0, entry_price_initial: null, dossier: null, live: null, positions: [], ctx: null,
        skipped: false, settled_pnl: null, updated_at: NOW, ...over,
    };
}

const params = { ...MIKE_PARAM_DEFAULTS };

describe('MikeMatchCard — altezza stabile', () => {
    it('senza dati ogni zona resta montata con il suo segnaposto', () => {
        render(<MikeMatchCard ev={ev()} params={params} />);
        const card = screen.getByTestId('mike-match-card');
        for (const id of ['mike-score', 'mike-alerts', 'mike-model', 'mike-goals-histogram',
                          'mike-quotes', 'mike-meta-line', 'mike-positions', 'mike-orders',
                          'mike-pnl-by-total', 'mike-cashout-smart', 'mike-loss-exit', 'mike-cover-wait']) {
            expect(within(card).getByTestId(id), id).toBeInTheDocument();
        }
        expect(within(card).getByTestId('mike-positions')).toHaveTextContent('nessuna posizione aperta');
        expect(within(card).getByTestId('mike-orders')).toHaveTextContent('Ordini sul book');
        expect(within(card).getByTestId('mike-orders')).toHaveTextContent('—');
        expect(within(card).getByTestId('mike-cashout-value')).toHaveTextContent('nessuna posizione');
        expect(within(card).getByTestId('mike-liability')).toHaveTextContent('—');
        expect(within(card).getByTestId('mike-goals-histogram')).toHaveTextContent('nessun modello per questa partita');
        // senza posizione non c'è cash out, ma c'è "Salta"
        expect(within(card).queryByTestId('mike-cashout-btn')).toBeNull();
        expect(within(card).getByTestId('mike-skip-btn')).toBeInTheDocument();
    });

    it('la comparsa di una copertura non fa sparire nessuna zona di dati', () => {
        // zone di DATI (i bottoni di azione cambiano per definizione: con una
        // posizione aperta compaiono Cash out e Flatten al posto di "Salta")
        const ZONES = ['mike-score', 'mike-alerts', 'mike-model', 'mike-goals-histogram',
                       'mike-quotes', 'mike-meta-line', 'mike-positions', 'mike-orders',
                       'mike-pnl-by-total', 'mike-liability', 'mike-locked',
                       'mike-cashout-value', 'mike-cashout-smart', 'mike-loss-exit', 'mike-cover-wait'];
        const { rerender } = render(<MikeMatchCard ev={ev()} params={params} />);
        const before = screen.getAllByTestId(/^mike-/)
            .map((n) => n.getAttribute('data-testid'))
            .filter((id) => ZONES.includes(String(id)));
        expect(before.length).toBe(ZONES.length);
        rerender(
            <MikeMatchCard
                ev={ev({
                    updated_at: new Date(Date.now() + 1000).toISOString(),
                    state: 'LIVE_COVERED',
                    positions: [leg(), leg({ role: 'over_cover', market: 'OU45', selection: 'OVER', price: 6.6, size: 2.26, matched: 2.26, avg_price: 6.6, ref: 'r2' })],
                    live: {
                        inplay: true, minute: 20, goals: 1, ht: false, hazard: 0.1, p4_market: 0.15, p4_model: 0.14,
                        liability: 12.26, locked: -0.4, pnl_by_total: { '4': -12.26 },
                        cashout: { net: 0.5, gross: 0.55, base: 12.26, complete: true, pct: 4.1, per: { 'OU35|UNDER': -1.28, 'OU45|OVER': 1.78 } },
                        books: { 'OU35|UNDER': { best_back: 1.7, back_size: 20, best_lay: 1.72, lay_size: 10, status: 'OPEN', inplay: true, bet_delay: 5 } },
                        cover_wait: null, feed_fresh: true,
                    },
                })}
                params={params}
            />,
        );
        const after = screen.getAllByTestId(/^mike-/).map((n) => n.getAttribute('data-testid'));
        for (const id of before) expect(after, String(id)).toContain(id);
    });
});

describe('MikeMatchCard — numeri del servizio e quote', () => {
    const live = {
        inplay: false, minute: null, goals: null, ht: false, hazard: null, p4_market: 0.12, p4_model: 0.13,
        feed_age_s: 2, liability: 10, locked: 0.13, total_matched: 5000,
        cashout: { net: 0.35, gross: 0.4, base: 10, complete: true, pct: 3.5, target_pct: 5,
                   per: { 'OU35|UNDER': 0.35 }, per_gross: { 'OU35|UNDER': 0.4 } },
        cover_wait: null, pnl_by_total: { '4': -10 },
        books: { 'OU35|UNDER': { best_back: 1.47, back_size: 30, best_lay: 1.48, lay_size: 20, status: 'OPEN', inplay: false, bet_delay: 0 } },
        feed_fresh: true,
    };

    it('"se chiudo ora" viene SOLO da cashout.per; se manca si dichiara', () => {
        const base = ev({ positions: [leg()], live });
        const { rerender } = render(<MikeMatchCard ev={base} params={params} />);
        expect(within(screen.getByTestId('mike-pos-row')).getByTestId('mike-pos-locked')).toHaveTextContent('+0,35 €');
        rerender(
            <MikeMatchCard
                ev={{ ...base, updated_at: new Date(Date.now() + 1000).toISOString(),
                      live: { ...live, cashout: { ...live.cashout, per: {}, per_gross: {} } } }}
                params={params}
            />,
        );
        expect(within(screen.getByTestId('mike-pos-row')).getByTestId('mike-pos-locked')).toHaveTextContent('—');
    });

    it('le quote mostrano la freccia di variazione rispetto al tick precedente', () => {
        const base = ev({ positions: [leg()], live });
        const { rerender } = render(<MikeMatchCard ev={base} params={params} />);
        rerender(
            <MikeMatchCard
                ev={{ ...base, updated_at: new Date(Date.now() + 1000).toISOString(),
                      live: { ...live, books: { 'OU35|UNDER': { ...live.books['OU35|UNDER'], best_back: 1.52, best_lay: 1.54 } } } }}
                params={params}
            />,
        );
        expect(within(screen.getByTestId('mike-quote-ou35')).getAllByLabelText('in salita')).toHaveLength(2);
    });

    it('il dialog di cash out mostra netto, dettaglio per gamba e chiede conferma', async () => {
        const onRequest = vi.fn();
        render(<MikeMatchCard ev={ev({ positions: [leg()], live })} params={params} onRequest={onRequest} />);
        await userEvent.click(screen.getByTestId('mike-cashout-btn'));
        expect(screen.getByTestId('mike-cashout-dialog-net')).toHaveTextContent('+0,35 €');
        expect(screen.getByTestId('mike-cashout-breakdown')).toHaveTextContent('Under 3.5');
        await userEvent.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onRequest).toHaveBeenCalledWith('cashout', 'E1');
    });

    it('in LIVE il cash out chiede DUE conferme (soldi veri)', async () => {
        const onRequest = vi.fn();
        render(<MikeMatchCard ev={ev({ positions: [leg()], live })} params={params} mode="live" onRequest={onRequest} />);
        await userEvent.click(screen.getByTestId('mike-cashout-btn'));
        await userEvent.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onRequest).not.toHaveBeenCalled();
        expect(screen.getByTestId('mike-cashout-confirm')).toHaveTextContent('Confermi? soldi veri');
        await userEvent.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onRequest).toHaveBeenCalledWith('cashout', 'E1');
    });

    it('chiusura manuale ARMATA: badge, Cash out e Flatten spenti con motivo', () => {
        render(<MikeMatchCard ev={ev({ positions: [leg()], live, ctx: { flatten_pending: true } })} params={params} />);
        expect(screen.getByTestId('mike-flatten-pending')).toHaveTextContent('CHIUSURA IN CORSO');
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-flatten-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Chiusura manuale già in corso');
    });

    it('rientro bloccato: badge NESSUN RIENTRO e "Riprendi" anche senza ERROR/SKIPPED', () => {
        render(<MikeMatchCard ev={ev({ state: 'FLAT', ctx: { no_reentry: true } })} params={params} />);
        expect(screen.getByTestId('mike-no-reentry')).toHaveTextContent('NESSUN RIENTRO');
        expect(screen.getByTestId('mike-resume-btn')).toBeEnabled();
    });

    it('VOID per MERCATO: lo dichiara sulla linea annullata, non su tutta la partita', () => {
        render(
            <MikeMatchCard
                ev={ev({ state: 'SETTLED', settled_pnl: 0, positions: [leg()], live })}
                params={params}
                voidedMarkets={['OU35']}
            />,
        );
        expect(screen.getByTestId('mike-void')).toHaveTextContent('VOID (linea 3.5)');
        expect(screen.getByTestId('mike-pos-row')).toHaveTextContent('VOID (Under 3.5)');
    });

    it('esito ARMATO della richiesta: netto stimato in formato italiano nella riga', () => {
        render(
            <MikeMatchCard
                ev={ev({ positions: [leg()], live })}
                params={params}
                lastRequest={{
                    id: 9, kind: 'cashout', payload: { event_id: 'E1' }, status: 'done',
                    result: { code: 'ok', phase: 'armed', cancelled: 1, cashout_net: 0.47, complete: true,
                              message: 'Cash out: annullati 1 ordini sul book, chiusura in corso (netto stimato 0.47 EUR).' },
                    created_at: NOW, updated_at: NOW,
                }}
            />,
        );
        const row = screen.getByTestId('mike-request-outcome');
        expect(row).toHaveTextContent('Cash out armato: annullati 1 ordini sul book · chiusura in corso · netto stimato +0,47 €');
        expect(row).toHaveAttribute('title', expect.stringContaining('netto stimato 0.47 EUR'));
    });

    it('una richiesta in volo spegne il bottone e lo dice', () => {
        render(<MikeMatchCard ev={ev({ positions: [leg()], live })} params={params} pendingKinds="cashout" />);
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Richiesta già inviata');
    });

    it('cash out spento CON MOTIVO quando il feed di QUESTA partita è fermo', () => {
        render(<MikeMatchCard ev={ev({ positions: [leg()], live: { ...live, feed_age_s: 45 } })} params={params} />);
        expect(screen.getByTestId('mike-feed-age')).toHaveTextContent('FEED FERMO (45 s)');
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Feed di questa partita fermo');
        expect(screen.getByTestId('mike-flatten-btn')).toBeDisabled();
    });

    it('linea assente nel feed: allarme rosso e chiusura non calcolabile', () => {
        render(
            <MikeMatchCard
                ev={ev({ positions: [leg()], live: { ...live, lines_missing: ['OU45|OVER'] } })}
                params={params}
            />,
        );
        expect(screen.getByTestId('mike-lines-missing')).toHaveTextContent('linea Over 4.5 assente nel feed');
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Linea Over 4.5 assente nel feed');
    });
});

describe('MikeMatchCard — ogni pulsante manda il suo comando', () => {
    const live = {
        inplay: true, minute: 30, goals: 1, ht: false, feed_age_s: 2, feed_fresh: true,
        liability: 10, locked: 0, pnl_by_total: { '4': -10 },
        cashout: { net: 0.3, gross: 0.32, base: 10, complete: true, pct: 3, target_pct: 5,
                   per: { 'OU35|UNDER': 0.3 } },
        cover_wait: null,
        books: { 'OU35|UNDER': { best_back: 1.47, back_size: 30, best_lay: 1.48, lay_size: 20, status: 'OPEN', inplay: true, bet_delay: 5 } },
    };
    const resting = leg({ role: 'under_green', side: 'lay', price: 1.44, size: 10.4, matched: 0,
                          avg_price: null, ref: 'r9', status: 'pending' });

    it('Annulla ordini → kind "cancel" (compare solo con ordini sul book)', async () => {
        const onRequest = vi.fn();
        const { rerender } = render(
            <MikeMatchCard ev={ev({ state: 'LIVE_COVERED', positions: [leg()], live })}
                           params={params} onRequest={onRequest} />,
        );
        expect(screen.queryByTestId('mike-cancel-btn')).toBeNull();
        rerender(
            <MikeMatchCard
                ev={ev({ state: 'LIVE_COVERED', positions: [leg(), resting], live,
                         updated_at: new Date(Date.now() + 1000).toISOString() })}
                params={params} onRequest={onRequest} />,
        );
        await userEvent.click(screen.getByTestId('mike-cancel-btn'));
        expect(onRequest).toHaveBeenCalledWith('cancel', 'E1');
    });

    it('Flatten → kind "flatten" (chiude a mercato, senza soglia)', async () => {
        const onRequest = vi.fn();
        render(
            <MikeMatchCard ev={ev({ state: 'LIVE_COVERED', positions: [leg()], live })}
                           params={params} onRequest={onRequest} />,
        );
        await userEvent.click(screen.getByTestId('mike-flatten-btn'));
        expect(onRequest).toHaveBeenCalledWith('flatten', 'E1');
    });

    it('Salta → kind "skip_event", e solo SENZA posizione aperta', async () => {
        const onRequest = vi.fn();
        const { rerender } = render(
            <MikeMatchCard ev={ev({ state: 'WATCH' })} params={params} onRequest={onRequest} />,
        );
        await userEvent.click(screen.getByTestId('mike-skip-btn'));
        expect(onRequest).toHaveBeenCalledWith('skip_event', 'E1');
        rerender(
            <MikeMatchCard ev={ev({ state: 'LIVE_COVERED', positions: [leg()], live,
                                    updated_at: new Date(Date.now() + 1000).toISOString() })}
                           params={params} onRequest={onRequest} />,
        );
        expect(screen.queryByTestId('mike-skip-btn')).toBeNull();
    });

    it('Riprendi → kind "resume_event" su SKIPPED ed ERROR', async () => {
        for (const st of ['SKIPPED', 'ERROR'] as const) {
            const onRequest = vi.fn();
            const { unmount } = render(
                <MikeMatchCard ev={ev({ state: st })} params={params} onRequest={onRequest} />,
            );
            await userEvent.click(screen.getByTestId('mike-resume-btn'));
            expect(onRequest, st).toHaveBeenCalledWith('resume_event', 'E1');
            unmount();
        }
    });

    it('una partita REGOLATA non ha nessuna azione (niente da fare)', () => {
        render(
            <MikeMatchCard ev={ev({ state: 'SETTLED', settled_pnl: 1.2, positions: [leg()], live })}
                           params={params} onRequest={vi.fn()} />,
        );
        for (const id of ['mike-cashout-btn', 'mike-flatten-btn', 'mike-cancel-btn', 'mike-skip-btn']) {
            expect(screen.queryByTestId(id), id).toBeNull();
        }
        expect(screen.getByTestId('mike-meta-line')).toHaveTextContent('regolato');
    });

    it('scanner fermo: ogni azione che tocca i soldi è spenta con il motivo', () => {
        render(
            <MikeMatchCard ev={ev({ state: 'LIVE_COVERED', positions: [leg()], live })}
                           params={params} stale staleReason="scanner fermo" onRequest={vi.fn()} />,
        );
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-flatten-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('scanner fermo');
    });
});

describe('MikeMatchCard — stato del mercato Betfair in ITALIANO', () => {
    const live = {
        inplay: true, minute: 30, goals: 1, ht: false, feed_age_s: 2, feed_fresh: true,
        pnl_by_total: {}, cashout: null, cover_wait: null,
        books: {
            'OU35|UNDER': { best_back: 1.7, back_size: 5, best_lay: 1.75, lay_size: 5, status: 'SUSPENDED', inplay: true, bet_delay: 5 },
            'OU45|OVER': { best_back: 6, back_size: 5, best_lay: 6.4, lay_size: 5, status: 'CLOSED', inplay: true, bet_delay: 0 },
            'OU45|UNDER': { best_back: 1.2, back_size: 5, best_lay: 1.21, lay_size: 5, status: 'OPEN', inplay: true, bet_delay: 0 },
        },
    };

    it('SUSPENDED/CLOSED diventano SOSPESO/CHIUSO, OPEN non si dice', () => {
        render(<MikeMatchCard ev={ev({ state: 'LIVE_COVERED', live })} params={params} />);
        expect(within(screen.getByTestId('mike-quote-ou35')).getByTestId('mike-market-status'))
            .toHaveTextContent('SOSPESO');
        expect(within(screen.getByTestId('mike-quote-ou45')).getByTestId('mike-market-status'))
            .toHaveTextContent('CHIUSO');
        // la linea aperta non mostra nessuno stato (rumore inutile)
        expect(within(screen.getByTestId('mike-quote-ou45-under')).queryByTestId('mike-market-status')).toBeNull();
        // e non resta in pagina nessun codice inglese di Betfair
        const card = screen.getByTestId('mike-match-card');
        expect(card.textContent).not.toContain('SUSPENDED');
        expect(card.textContent).not.toContain('CLOSED');
    });

    it('lo stato che blocca l’operatività è ambra/rosso, non grigio', () => {
        render(<MikeMatchCard ev={ev({ state: 'LIVE_COVERED', live })} params={params} />);
        const sosp = within(screen.getByTestId('mike-quote-ou35')).getByTestId('mike-market-status');
        expect(sosp.className).toContain('amber');
        const chiuso = within(screen.getByTestId('mike-quote-ou45')).getByTestId('mike-market-status');
        expect(chiuso.className).toContain('red');
    });
});

describe('MikeMatchCard — KO passato ma partita non ancora iniziata', () => {
    it('resta in PRE-MATCH e lo DICE: "in attesa del fischio"', () => {
        render(
            <MikeMatchCard
                ev={ev({ state: 'HOLD', ko_at: new Date(Date.now() - 120_000).toISOString(), live: { inplay: false } })}
                params={params}
            />,
        );
        expect(screen.getByTestId('mike-awaiting-kickoff')).toHaveTextContent('in attesa del fischio');
        expect(screen.queryByTestId('mike-countdown')).toBeNull();
    });

    it('prima del KO mostra il countdown, non la nota', () => {
        render(
            <MikeMatchCard
                ev={ev({ state: 'WATCH', ko_at: new Date(Date.now() + 3600_000).toISOString() })}
                params={params}
            />,
        );
        expect(screen.getByTestId('mike-countdown')).toBeInTheDocument();
        expect(screen.queryByTestId('mike-awaiting-kickoff')).toBeNull();
    });

    it('una partita REGOLATA non aspetta nessun fischio', () => {
        render(
            <MikeMatchCard
                ev={ev({ state: 'SETTLED', settled_pnl: 1.2, ko_at: new Date(Date.now() - 7200_000).toISOString() })}
                params={params}
            />,
        );
        expect(screen.queryByTestId('mike-awaiting-kickoff')).toBeNull();
    });
});
