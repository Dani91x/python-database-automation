import { describe, it, expect, vi } from 'vitest';
import { render, within } from '@testing-library/react';
import { UsciteColonna } from './UsciteColonna';
import type { useControlRoom } from './useControlRoom';

type Vm = ReturnType<typeof useControlRoom>;

function baseVm(over: Partial<Vm> = {}): Vm {
    return {
        bots: [], proposte: [], proposteOmega: [], proposteOpportunita: [],
        slippagePct: 2, setSlippagePct: vi.fn(),
        approva: vi.fn(), ignora: vi.fn(), approvaOmega: vi.fn(), ignoraOmega: vi.fn(),
        piazzaOpportunita: vi.fn(), rifiutaOpportunita: vi.fn(),
        erroreProposteOmega: null, feedEtaS: 1,
        ...over,
    } as unknown as Vm;
}

function propostaOpp(id: number, over: Record<string, unknown> = {}) {
    return {
        proposta: {
            id, kind: 'model', status: 'proposed',
            payload: { opp_key: `k${id}`, strategy: 'model', kind: 'model', event_id: `E${id}`, ...over },
        },
        abbinabileOra: 10, etaQuoteS: 1,
    };
}

describe('UsciteColonna', () => {
    it('IL CONTATORE non conta le opportunità', () => {
        const vm = baseVm({ proposte: [], proposteOmega: [], proposteOpportunita: [propostaOpp(1) as never, propostaOpp(2) as never] });
        const s = render(<UsciteColonna vm={vm} filtroSport={null} />);
        expect(s.getByTestId('cr-nastro-contatore').textContent).toMatch(/^0 in attesa/);
    });

    it('STATO VUOTO indipendente: nessuna uscita ma delle opportunità in coda NON mostra "nessuna opportunità"', () => {
        const vm = baseVm({ proposte: [], proposteOmega: [], proposteOpportunita: [propostaOpp(1) as never] });
        const s = render(<UsciteColonna vm={vm} filtroSport={null} />);
        expect(within(s.getByTestId('cr-nastro')).getByText(/Nessuna uscita da decidere/)).toBeTruthy();
    });

    it('il filtro sport NON nasconde un’uscita: la dichiarazione compare', () => {
        const vm = baseVm();
        const s = render(<UsciteColonna vm={vm} filtroSport="calcio" />);
        expect(s.getByTestId('cr-nastro-non-filtrato').textContent).toMatch(/entrambi gli sport/i);
    });

    it('senza filtro, la dichiarazione non compare', () => {
        const vm = baseVm();
        const s = render(<UsciteColonna vm={vm} filtroSport={null} />);
        expect(s.queryByTestId('cr-nastro-non-filtrato')).toBeNull();
    });
});
