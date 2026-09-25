// ============================================================================
// PropostaUscitaMike.test.tsx — 25/09: la proposta d'uscita di Mike a
// interruttore spento. Chiavi del finto = quelle che scrive
// `engine.gate_uscite` in `mike_events.ctx.uscita_proposta`.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import type { MikeEvent } from '@/lib/mike';

const requestMike = vi.fn(async () => 1);
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    requestMike: (...a: unknown[]) => requestMike(...a as []),
}));

import { PropostaUscitaMike, propostaDi } from './PropostaUscitaMike';
import { SchedaMike } from './SchedaMike';

const ORA_S = Math.floor(Date.now() / 1000);

function proposta(over: Record<string, unknown> = {}) {
    return {
        chiave: 'chiusura|c0', categoria: 'chiusura', ciclo: 0, stato: 'LIVE_COVERED',
        stato_voluto: 'LIVE_CLOSING', motivo: 'profit: 1.31 >= 5% di 24.00', close_reason: 'profit',
        ordini: [
            { ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.31, size: 22.9 },
            { ruolo: 'over_close', mercato: 'OU45', selezione: 'OVER', lato: 'lay', prezzo: 12.5, size: 2.56 },
        ],
        bloccabile: 1.31, urgente: false, minuto: 30, gol: 0,
        decided_at: ORA_S - 12, proposed_at: ORA_S - 12,
        sostanza: ['chiusura|c0', [['under_close', 'lay'], ['over_close', 'lay']], 'profit'],
        ...over,
    };
}

function ev(ctx: Record<string, unknown> | null, feedAge = 2): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date().toISOString(), mode: 'live', markets: {}, state: 'LIVE_COVERED',
        cycle_no: 0, entry_price_initial: 1.5, dossier: null,
        live: {
            feed_age_s: feedAge,
            cashout: { net: 1.28 },
            books: {
                'OU35|UNDER': { best_back: 1.30, best_lay: 1.31 },
                'OU45|OVER': { best_back: 12.0, best_lay: 12.5 },
            },
        } as unknown as MikeEvent['live'],
        positions: [], ctx, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    };
}

beforeEach(() => { requestMike.mockClear(); });

describe('25/09 proposta d’uscita di Mike', () => {
    it('nessuna proposta viva: non si mostra niente', () => {
        const { container } = render(<PropostaUscitaMike ev={ev({ uscita_proposta: null })} />);
        expect(container.textContent).toBe('');
        expect(propostaDi(ev(null))).toBeNull();
    });

    it('mostra categoria, motivo, ordini con il prezzo di adesso e i due P&L', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta() })} />);
        expect(screen.getByTestId('cr-mike-proposta-titolo').textContent)
            .toBe('Mike vorrebbe uscire: cash out della posizione');
        expect(screen.getByTestId('cr-mike-proposta-motivo').textContent).toBe('profit: 1.31 >= 5% di 24.00');
        // D7 (25/09): la riga dice da dove viene il prezzo di adesso (qui:
        // nessun id vero sulla riga -> il feed della partita, dichiarato)
        expect(screen.getByTestId('cr-mike-proposta-ordini').textContent).toBe(
            'Chiusura Under 3.5 lay 22,90 € @ 1,31 (ora 1,30 / 1,31, feed della partita)'
            + ' + Chiusura Over 4.5 lay 2,56 € @ 12,50 (ora 12,00 / 12,50, feed della partita)');
        const numeri = screen.getByTestId('cr-mike-proposta-numeri').textContent ?? '';
        expect(numeri).toMatch(/^chiudendo ora \+1,28 €/);
        expect(numeri).toContain('alla decisione +1,31 €');
        expect(numeri).toMatch(/deciso 1[2-4] s fa/);
        expect(numeri).toContain('30′');
    });

    it('uscita in perdita: marcata', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta({ urgente: true }) })} />);
        expect(screen.getByTestId('cr-mike-proposta-titolo').textContent)
            .toBe('Mike vorrebbe uscire: cash out della posizione (in perdita)');
    });

    it('APPROVA manda approva_uscita con la chiave e il contesto del clic', async () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta() })} />);
        await act(async () => { fireEvent.click(screen.getByTestId('cr-mike-proposta-approva')); });
        expect(requestMike).toHaveBeenCalledTimes(1);
        const [kind, payload] = requestMike.mock.calls[0] as unknown as [string, Record<string, unknown>];
        expect(kind).toBe('approva_uscita');
        expect(payload.event_id).toBe('E1');
        expect(payload.chiave).toBe('chiusura|c0');
        expect(payload.bot).toBe('mike');
        expect(payload.mode).toBe('live');
        const ctx = payload.contesto as Record<string, unknown>;
        expect(ctx.prezzo_visto).toBe(1.31);
        expect(typeof ctx.eta_ms).toBe('number');
        expect(ctx.fonte).toBe('mike_events.live (get_mike_state)');
        expect(screen.getByTestId('cr-mike-proposta-esito').textContent)
            .toBe('approvazione inviata: parte al prossimo giro del bot');
    });

    it('feed FERMO: il bottone si spegne (regola della scheda di Mike)', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta() }, 45)} />);
        expect(screen.getByTestId('cr-mike-proposta-approva')).toHaveProperty('disabled', true);
    });

    it('montata dentro SchedaMike', () => {
        render(<SchedaMike ev={ev({ uscita_proposta: proposta() })} />);
        expect(screen.getByTestId('cr-mike-proposta')).toBeTruthy();
    });
});

// ---------------------------------------------------------------- D7 (25/09) AL MS
// La proposta parla per simboli (OU35/UNDER); gli id veri sono sulla STESSA
// riga della partita: `markets[mercato].market_id` e `ctx.selections` (chiavi
// del servizio, `Betfair/mike/service.py`). Finta della sorgente con la FORMA
// di `LiveLadderRow` (lib/live.ts), come in SchedaChiusuraOmega.test.tsx.
function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    let staccate = 0;
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { staccate += 1; cbs.delete(mid); };
        },
        fonte: () => 'canale' as const,
    };
    const spingi = (mid: string, sid: number, back: number, lay: number, ms = Date.now()) => act(() => {
        cbs.get(mid)?.({
            event_id: 'E1', market_id: mid, market_type: 'OVER_UNDER_35', market_name: 'O/U 3.5',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [{ selection_id: sid, name: 'Under 3.5 Goals', ltp: back,
                tv: 0, back: [[back, 100]], lay: [[lay, 80]], trd: [],
                wom: { back_pct: 50, lay_pct: 50 } }] },
        });
    });
    return { sorgente: () => src as never, spingi, iscritti: () => [...cbs.keys()], staccate: () => staccate };
}

function evConId(ctxExtra: Record<string, unknown> = {}): MikeEvent {
    const e = ev({ uscita_proposta: proposta(), selections: { 'OU35|UNDER': 47972, 'OU45|OVER': 1222347 },
        ...ctxExtra });
    return { ...e, markets: { OU35: { market_id: '1.35' }, OU45: { market_id: '1.45' } } };
}

describe('D7 (25/09) la proposta di Mike al ms, coi mercati veri', () => {
    it('gli id veri vengono dalla riga della partita; la proposta, se li porta, vince', async () => {
        const { idsOrdineMike } = await import('./PropostaUscitaMike');
        const e = evConId();
        expect(idsOrdineMike(e, { mercato: 'OU35', selezione: 'UNDER' }))
            .toEqual({ marketId: '1.35', selectionId: 47972 });
        expect(idsOrdineMike(e, { mercato: 'OU45', selezione: 'OVER' }))
            .toEqual({ marketId: '1.45', selectionId: 1222347 });
        expect(idsOrdineMike(e, { mercato: 'OU35', selezione: 'UNDER', market_id: '1.99', selection_id: 5 }))
            .toEqual({ marketId: '1.99', selectionId: 5 });
        // mai un id inventato
        expect(idsOrdineMike(ev({}), { mercato: 'OU35', selezione: 'UNDER' }))
            .toEqual({ marketId: null, selectionId: null });
        expect(idsOrdineMike(e, null)).toEqual({ marketId: null, selectionId: null });
    });

    it('il prezzo di adesso si aggiorna al tick del ladder e la fonte lo dice', () => {
        const f = sorgenteFinta();
        const { unmount } = render(<PropostaUscitaMike ev={evConId()} sorgenteLadder={f.sorgente} />);
        expect(f.iscritti().sort()).toEqual(['1.35', '1.45']);
        const riga0 = () => screen.getByTestId('cr-mike-proposta-ordine-al-ms-0');
        // prima del tick: il feed della partita
        expect(riga0().textContent).toContain('(ora 1,30 / 1,31, feed della partita)');
        f.spingi('1.35', 47972, 1.28, 1.29);
        expect(riga0().textContent).toContain('(ora 1,28 / 1,29, al ms)');
        expect(riga0().getAttribute('data-fonte')).toBe('canale');
        f.spingi('1.35', 47972, 1.27, 1.28);
        expect(riga0().textContent).toContain('(ora 1,27 / 1,28, al ms)');
        // il secondo ordine (Over 4.5) segue il SUO mercato
        f.spingi('1.45', 1222347, 11.5, 12.0);
        expect(screen.getByTestId('cr-mike-proposta-ordine-al-ms-1').textContent)
            .toContain('(ora 11,50 / 12,00, al ms)');
        // selezione diversa sulla stessa riga: non e' la nostra, si resta sul feed
        f.spingi('1.35', 999, 5.0, 5.1);
        expect(riga0().textContent).toContain('feed della partita');
        unmount();
        expect(f.iscritti()).toEqual([]);
        expect(f.staccate()).toBeGreaterThanOrEqual(2);
    });

    it('APPROVA manda il prezzo AL MS del lato proposto (lay), la fonte ladder e gli id', async () => {
        const f = sorgenteFinta();
        render(<PropostaUscitaMike ev={evConId()} sorgenteLadder={f.sorgente} />);
        f.spingi('1.35', 47972, 1.28, 1.29);
        await act(async () => { fireEvent.click(screen.getByTestId('cr-mike-proposta-approva')); });
        const [, payload] = requestMike.mock.calls[0] as unknown as [string, Record<string, unknown>];
        const ctx = payload.contesto as Record<string, unknown>;
        expect(ctx.prezzo_visto).toBe(1.29);
        expect(ctx.fonte).toBe('ladder al ms (canale)');
        expect(ctx.market_id).toBe('1.35');
        expect(ctx.selection_id).toBe(47972);
        expect(ctx.prezzo_segnale).toBe(1.31);
        expect(typeof ctx.eta_ms).toBe('number');
    });

    it('dice come parte l’uscita al clic', () => {
        render(<PropostaUscitaMike ev={evConId()} sorgenteLadder={null} />);
        expect(screen.getByTestId('cr-mike-proposta-esecuzione').textContent)
            .toMatch(/^al clic: il bot esce a mercato con la sua macchina d’uscita/);
    });
});
