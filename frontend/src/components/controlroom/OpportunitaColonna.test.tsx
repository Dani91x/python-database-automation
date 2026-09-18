import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { OpportunitaColonna } from './OpportunitaColonna';
import type { useControlRoom } from './useControlRoom';

type Vm = ReturnType<typeof useControlRoom>;

function baseVm(over: Partial<Vm> = {}): Vm {
    return {
        bots: [], proposte: [], proposteOmega: [], proposteOpportunita: [],
        piazzaOpportunita: vi.fn(), rifiutaOpportunita: vi.fn(),
        ...over,
    } as unknown as Vm;
}

function propostaOpp(id: number, over: Record<string, unknown> = {}) {
    return {
        proposta: {
            id, kind: 'model', status: 'proposed', created_at: `2026-09-18T10:0${id}:00Z`,
            payload: {
                opp_key: `k${id}`, strategy: 'model', kind: 'model', event_id: `E${id}`,
                market_id: '1.1', selection_id: 1, side: 'back', price: 2, size: 5, mode: 'paper',
                ...over,
            },
        },
        abbinabileOra: 10, etaQuoteS: 1,
    };
}

describe('OpportunitaColonna', () => {
    it('IL CONTATORE non conta le uscite', () => {
        const vm = baseVm({ proposte: [{ proposta: { id: 1 } }] as never, proposteOmega: [{ id: 2 }] as never, proposteOpportunita: [] });
        const s = render(<OpportunitaColonna vm={vm} filtroSport={null} />);
        expect(s.getByTestId('cr-opportunita-contatore').textContent).toBe('0');
    });

    it('STATO VUOTO indipendente dalla colonna delle uscite', () => {
        const vm = baseVm({ proposte: [{ proposta: { id: 1 } }] as never, proposteOpportunita: [] });
        const s = render(<OpportunitaColonna vm={vm} filtroSport={null} />);
        expect(s.getByText(/Nessuna opportunità in coda/)).toBeTruthy();
    });

    it('il filtro sport NON nasconde le opportunità (dichiarazione a schermo)', () => {
        const vm = baseVm({ proposteOpportunita: [propostaOpp(1) as never] });
        const s = render(<OpportunitaColonna vm={vm} filtroSport="tennis" />);
        expect(s.getByTestId('cr-opportunita-non-filtrata').textContent).toMatch(/entrambi gli sport/i);
    });

    it('raggruppa più proposte della stessa partita con un titolo di gruppo', () => {
        const vm = baseVm({
            proposteOpportunita: [propostaOpp(1, { event_id: 'E1' }) as never, propostaOpp(2, { event_id: 'E1' }) as never],
        });
        const s = render(<OpportunitaColonna vm={vm} filtroSport={null} />);
        expect(s.getByTestId('cr-opportunita-gruppo').textContent).toMatch(/2 proposte/);
    });

    it('conta correttamente il numero di opportunità in coda', () => {
        const vm = baseVm({ proposteOpportunita: [propostaOpp(1) as never, propostaOpp(2, { event_id: 'E2' }) as never] });
        const s = render(<OpportunitaColonna vm={vm} filtroSport={null} />);
        expect(s.getByTestId('cr-opportunita-contatore').textContent).toBe('2');
    });
});
