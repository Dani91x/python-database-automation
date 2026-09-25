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
        expect(screen.getByTestId('cr-mike-proposta-ordini').textContent).toBe(
            'Chiusura Under 3.5 lay 22,90 € @ 1,31 (ora 1,30 / 1,31) + Chiusura Over 4.5 lay 2,56 € @ 12,50 (ora 12,00 / 12,50)');
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
