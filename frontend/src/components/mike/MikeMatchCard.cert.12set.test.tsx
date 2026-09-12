// ============================================================================
// CERTIFICAZIONE 12/09 — protezioni sui bottoni che muovono SOLDI VERI.
//
//   1. "Chiudi a mercato" (flatten) partiva con UN SOLO click, anche in LIVE,
//      mentre il "Cash out" accanto ne chiedeva due — ed è l'azione PIÙ
//      pericolosa: chiude ai prezzi che trova, senza guardare la soglia.
//   2. con l'età del feed SCONOSCIUTA (`feed_age_s` assente) il badge diceva
//      "FEED: NESSUN DATO" ma cash out e flatten restavano ACCESI: ordine
//      reale senza sapere di quando sono i prezzi.
//   3. "ciclo 11 di 10" (e "ciclo 1 di 0") su partite regolate o a cicli finiti.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeMatchCard, cycleText, MIKE_FLATTEN_ARM_TIMEOUT_MS } from './MikeMatchCard';
import { MIKE_PARAM_DEFAULTS, type MikeEvent, type MikeLeg } from '@/lib/mike';

const NOW = new Date().toISOString();

function leg(over: Partial<MikeLeg> = {}): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10,
        matched: 10, avg_price: 1.5, ref: 'r1', status: 'open', placed_at: 0, persistence: 'LAPSE',
        cycle_no: 0, final: false, archived: false, ...over,
    };
}

/** partita LIVE con una posizione aperta e il feed fresco */
function ev(over: Partial<MikeEvent> = {}, live: Record<string, unknown> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() - 3600_000).toISOString(), mode: 'paper', markets: {}, state: 'LIVE_COVERED',
        cycle_no: 0, entry_price_initial: 1.5, dossier: null, positions: [leg()], ctx: null,
        skipped: false, settled_pnl: null, updated_at: NOW,
        live: {
            inplay: true, minute: 20, goals: 1, ht: false, hazard: 0.1, p4_market: 0.15, p4_model: 0.14,
            liability: 10, locked: 0, pnl_by_total: {}, feed_age_s: 2, feed_fresh: true,
            cashout: { net: 0.5, gross: 0.55, base: 10, complete: true, pct: 5, per: {} },
            books: { 'OU35|UNDER': { best_back: 1.7, back_size: 20, best_lay: 1.72, lay_size: 10, status: 'OPEN', inplay: true, bet_delay: 0 } },
            cover_wait: null,
            ...live,
        } as MikeEvent['live'],
        ...over,
    } as MikeEvent;
}

const params = { ...MIKE_PARAM_DEFAULTS };

describe('MikeMatchCard — "Chiudi a mercato" ha la stessa protezione del cash out', () => {
    it('PAPER: un click apre il DIALOG, non piazza nulla', async () => {
        const onRequest = vi.fn();
        const user = userEvent.setup();
        render(<MikeMatchCard ev={ev()} params={params} mode="paper" onRequest={onRequest} />);
        await user.click(screen.getByTestId('mike-flatten-btn'));
        expect(onRequest).not.toHaveBeenCalled();
        expect(screen.getByTestId('mike-flatten-dialog')).toBeInTheDocument();
        await user.click(screen.getByTestId('mike-flatten-confirm'));
        expect(onRequest).toHaveBeenCalledWith('flatten', 'E1');
    });

    it('LIVE: servono DUE conferme — il primo click sul dialog NON chiude', async () => {
        const onRequest = vi.fn();
        const user = userEvent.setup();
        render(<MikeMatchCard ev={ev()} params={params} mode="live" onRequest={onRequest} />);
        await user.click(screen.getByTestId('mike-flatten-btn'));
        await user.click(screen.getByTestId('mike-flatten-confirm'));
        expect(onRequest).not.toHaveBeenCalled();
        expect(screen.getByTestId('mike-flatten-confirm')).toHaveTextContent('Confermi? soldi veri');
        await user.click(screen.getByTestId('mike-flatten-confirm'));
        expect(onRequest).toHaveBeenCalledTimes(1);
    });

    it('LIVE: la conferma armata decade da sola', async () => {
        // l'orologio finto deve esistere PRIMA del render: il timer di
        // decadimento viene armato dentro il componente al primo click
        vi.useFakeTimers();
        try {
            const onRequest = vi.fn();
            render(<MikeMatchCard ev={ev()} params={params} mode="live" onRequest={onRequest} />);
            fireEvent.click(screen.getByTestId('mike-flatten-btn'));
            fireEvent.click(screen.getByTestId('mike-flatten-confirm'));
            expect(screen.getByTestId('mike-flatten-confirm')).toHaveTextContent('Confermi? soldi veri');
            act(() => { vi.advanceTimersByTime(MIKE_FLATTEN_ARM_TIMEOUT_MS + 50); });
            expect(screen.getByTestId('mike-flatten-confirm')).toHaveTextContent('Chiudi tutto a mercato');
            expect(onRequest).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });

    it('il dialog dice CHE COSA fa: chiude senza guardare la soglia', async () => {
        const user = userEvent.setup();
        render(<MikeMatchCard ev={ev()} params={params} mode="live" onRequest={vi.fn()} />);
        await user.click(screen.getByTestId('mike-flatten-btn'));
        expect(screen.getByTestId('mike-flatten-dialog'))
            .toHaveTextContent('senza guardare la soglia di profitto');
        expect(screen.getByTestId('mike-flatten-net')).toHaveTextContent('+0,50');
    });
});

describe('MikeMatchCard — età del feed SCONOSCIUTA: fail-closed', () => {
    it('senza feed_age_s i bottoni con soldi sono SPENTI e il motivo è scritto', () => {
        render(
            <MikeMatchCard
                ev={ev({}, { feed_age_s: null })}
                params={params} mode="live" onRequest={vi.fn()}
            />,
        );
        expect(screen.getByTestId('mike-feed-age')).toHaveTextContent('NESSUN DATO');
        expect(screen.getByTestId('mike-flatten-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent(/sconosciuta/i);
    });

    it('un click sul flatten spento non apre nemmeno il dialog', async () => {
        const onRequest = vi.fn();
        const user = userEvent.setup();
        render(<MikeMatchCard ev={ev({}, { feed_age_s: null })} params={params} mode="live" onRequest={onRequest} />);
        await user.click(screen.getByTestId('mike-flatten-btn'));
        expect(screen.queryByTestId('mike-flatten-dialog')).toBeNull();
        expect(onRequest).not.toHaveBeenCalled();
    });

    it('feed vecchio (oltre 20 s): spento come prima', () => {
        render(<MikeMatchCard ev={ev({}, { feed_age_s: 75 })} params={params} mode="paper" onRequest={vi.fn()} />);
        expect(screen.getByTestId('mike-flatten-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
    });

    it('feed fresco: acceso', () => {
        render(<MikeMatchCard ev={ev()} params={params} mode="paper" onRequest={vi.fn()} />);
        expect(screen.getByTestId('mike-flatten-btn')).toBeEnabled();
        expect(screen.getByTestId('mike-cashout-btn')).toBeEnabled();
    });
});

describe('cycleText — "ciclo N di M" senza numeri impossibili', () => {
    it('ciclo in corso: cicli chiusi + 1', () => {
        const t = cycleText(0, 10, false);
        expect(t.value).toBe('1');
        expect(t.of).toBe('di 10');
    });

    it('cicli ESAURITI: non inventa un ciclo che non esiste', () => {
        const t = cycleText(10, 10, false);
        expect(t.value).toBe('10');
        expect(t.of).toContain('esauriti');
    });

    it('partita REGOLATA: cicli completati, non uno in corso', () => {
        const t = cycleText(10, 10, true);
        expect(t.value).toBe('10');
        expect(t.of).toContain('usati');
        expect(t.title).toContain('partita chiusa');
    });

    it('massimo non configurato: lo dice invece di scrivere "di 0"', () => {
        expect(cycleText(0, null, false).of).toBe('(massimo non configurato)');
        expect(cycleText(0, 0, false).of).toBe('(massimo non configurato)');
    });

    it('a schermo: una partita a cicli finiti non mostra "11 di 10"', () => {
        render(
            <MikeMatchCard
                ev={ev({ cycle_no: 10 })}
                params={{ ...params, pre_max_cycles: 10 }}
                mode="paper" onRequest={vi.fn()}
            />,
        );
        expect(screen.getByTestId('mike-cycle')).toHaveTextContent('10');
        expect(screen.getByTestId('mike-meta-line')).not.toHaveTextContent('11 di 10');
    });
});

describe('MikeMatchCard — partita REGOLATA: niente posizione fantasma', () => {
    /** stessa forma della scheda "Regolate" del dump reale: stato terminale,
     *  P&L regolato, e il blob del feed CONGELATO all'ultimo aggiornamento */
    const settled = () => ev({
        state: 'SETTLED', settled_pnl: 3.99,
        positions: [leg({ status: 'settled' })],
    }, {
        liability: 10, locked: -0.41,
        cashout: { net: -0.41, gross: -0.43, base: 10, complete: true, pct: -4.1, per: { 'OU35|UNDER': -0.41 } },
        books: { 'OU35|UNDER': { best_back: 1.42, back_size: 50, best_lay: 1.48, lay_size: 30, status: 'OPEN', inplay: true, bet_delay: 0 } },
    });

    it('non mostra "Se chiudo tutto ora" su una partita gia chiusa', () => {
        render(<MikeMatchCard ev={settled()} params={params} mode="paper" onRequest={vi.fn()} />);
        const v = screen.getByTestId('mike-cashout-value');
        expect(v).toHaveTextContent('partita già chiusa');
        expect(v).toHaveTextContent('+3,99');
        expect(v).not.toHaveTextContent('−0,41');
    });

    it('nessuna "liability aperta" su una partita regolata: il rischio e chiuso', () => {
        render(<MikeMatchCard ev={settled()} params={params} mode="paper" onRequest={vi.fn()} />);
        const l = screen.getByTestId('mike-liability');
        expect(l).toHaveTextContent('rischio chiuso');
        expect(l).toHaveTextContent('+3,99');
        expect(l).not.toHaveTextContent('10,00');
    });

    it('nessun bottone che muove soldi su una partita chiusa', () => {
        render(<MikeMatchCard ev={settled()} params={params} mode="live" onRequest={vi.fn()} />);
        expect(screen.queryByTestId('mike-flatten-btn')).toBeNull();
        expect(screen.queryByTestId('mike-cashout-btn')).toBeNull();
    });

    it('le quote congelate sono dichiarate tali, non spacciate per il book di adesso', () => {
        render(<MikeMatchCard ev={settled()} params={params} mode="paper" onRequest={vi.fn()} />);
        expect(screen.getByTestId('mike-quotes')).toHaveTextContent('ultime quote viste');
        // "chiudo @1,48" su una partita finita e' un prezzo che non esiste piu'
        expect(screen.getByTestId('mike-positions')).toHaveTextContent('partita chiusa');
        expect(screen.getByTestId('mike-positions')).not.toHaveTextContent('chiudo @');
    });
});

describe('MikeMatchCard — ordini sul book: ingresso e chiusura non si sommano', () => {
    it('un green-up LAY appoggiato su una posizione BACK non gonfia l esposizione', () => {
        render(
            <MikeMatchCard
                ev={ev({
                    positions: [
                        leg({ size: 10, matched: 10 }),
                        // green-up: lato OPPOSTO, ancora sul book
                        leg({ role: 'greenup', side: 'lay', price: 1.51, size: 10.13, matched: 0, ref: 'r9', status: 'pending' }),
                    ],
                })}
                params={params} mode="paper" onRequest={vi.fn()}
            />,
        );
        const rest = screen.getByTestId('mike-pos-rest');
        expect(rest).toHaveTextContent('di chiusura appoggiata');
        expect(rest).not.toHaveTextContent('in ingresso sul book');
    });
});
