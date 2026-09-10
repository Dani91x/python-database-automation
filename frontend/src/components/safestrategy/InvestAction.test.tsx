// Test COMPONENTE di InvestAction: doppia conferma LIVE che decade (cambio
// stake/prezzo o 10 s) e guardia anti doppio click.
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InvestAction, LIVE_ARM_TIMEOUT_MS, type InvestActionProps } from './InvestAction';

function renderIt(over: Partial<InvestActionProps> = {}) {
    const onPlace = vi.fn(async () => 7);
    const props: InvestActionProps = {
        mode: 'live', side: 'back', price: 2.5, sizeAvailable: 100, defaultStake: 5,
        requests: [], onPlace, ...over,
    };
    const utils = render(<InvestAction {...props} />);
    return { onPlace, ...utils };
}

describe('InvestAction — conferma LIVE (MEDIUM-2)', () => {
    it('armata, decade se cambia lo stake', async () => {
        const user = userEvent.setup();
        const { onPlace } = renderIt();
        await user.click(screen.getByTestId('invest-place'));
        expect(screen.getByTestId('invest-place')).toHaveTextContent(/Confermi/);
        await user.clear(screen.getByLabelText('Stake'));
        await user.type(screen.getByLabelText('Stake'), '8');
        expect(screen.getByTestId('invest-place')).toHaveTextContent('Piazza (LIVE)');
        await user.click(screen.getByTestId('invest-place'));
        expect(onPlace).not.toHaveBeenCalled();
    });

    it('armata, decade se cambia il prezzo (tick del book)', () => {
        const { rerender } = renderIt();
        fireEvent.click(screen.getByTestId('invest-place'));
        expect(screen.getByTestId('invest-place')).toHaveTextContent(/Confermi/);
        rerender(<InvestAction mode="live" side="back" price={2.6} sizeAvailable={100} defaultStake={5} requests={[]} onPlace={vi.fn(async () => 1)} />);
        expect(screen.getByTestId('invest-place')).toHaveTextContent('Piazza (LIVE)');
    });

    it('armata, decade dopo 10 s', () => {
        vi.useFakeTimers();
        try {
            const { onPlace } = renderIt();
            fireEvent.click(screen.getByTestId('invest-place'));
            expect(screen.getByTestId('invest-place')).toHaveTextContent(/Confermi/);
            act(() => { vi.advanceTimersByTime(LIVE_ARM_TIMEOUT_MS + 1); });
            expect(screen.getByTestId('invest-place')).toHaveTextContent('Piazza (LIVE)');
            expect(onPlace).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });

    it('disabled con motivo: bottone spento e motivo visibile', () => {
        renderIt({ disabled: true, disabledReason: 'quote non aggiornate (40s)' });
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('invest-disabled-reason')).toHaveTextContent('quote non aggiornate (40s)');
    });

    it('doppio click in PAPER: UNA sola richiesta', async () => {
        let release: (v: number) => void = () => {};
        const onPlace = vi.fn(() => new Promise<number>((r) => { release = r; }));
        render(<InvestAction mode="paper" side="back" price={2.5} sizeAvailable={100} defaultStake={5} requests={[]} onPlace={onPlace} />);
        const btn = screen.getByTestId('invest-place');
        fireEvent.click(btn);
        fireEvent.click(btn);
        expect(onPlace).toHaveBeenCalledTimes(1);
        await act(async () => { release(1); });
    });
});
