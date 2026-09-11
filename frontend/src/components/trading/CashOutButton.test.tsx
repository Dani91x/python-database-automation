// Test COMPONENTE di CashOutButton (jsdom + React Testing Library).
// Verifica la matematica mostrata (posizione lay e back), il parziale (i DUE
// esiti residui, titolo = peggiore), gli stati disabilitati, la conferma
// (doppia in LIVE, che decade) e la guardia anti doppio cash out.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
    CashOutButton, hedgeSide, greenPrice, fullGreenStake, partialLockedPnl, partialOutcomes,
    netAfterCommission, LIVE_ARM_TIMEOUT_MS,
    type CashOutButtonProps,
} from './CashOutButton';

function renderBtn(over: Partial<CashOutButtonProps> = {}) {
    const onCashOut = vi.fn();
    const props: CashOutButtonProps = {
        // posizione LAY 5 @ 3.00 -> vince -10 / perde +5
        win: -10, lose: 5, bestBack: 4, bestLay: 4.2,
        mode: 'paper', onCashOut,
        ...over,
    };
    render(<TooltipProvider><CashOutButton {...props} /></TooltipProvider>);
    return { onCashOut };
}

beforeEach(() => vi.clearAllMocks());

// ------------------------------------------------------------- helper puri
describe('matematica cash out', () => {
    it('hedgeSide: win>lose si copre bancando, altrimenti puntando', () => {
        expect(hedgeSide(15, -10)).toBe('lay');
        expect(hedgeSide(-10, 5)).toBe('back');
    });

    it('greenPrice usa il best del lato di copertura', () => {
        expect(greenPrice(-10, 5, 4, 4.2)).toBe(4);
        expect(greenPrice(15, -10, 1.9, 2)).toBe(2);
        expect(greenPrice(15, -10, 1.9, null)).toBeNull();
        expect(greenPrice(-10, 5, 1, 4.2)).toBeNull();
    });

    it('fullGreenStake = |win-lose| / prezzo', () => {
        expect(fullGreenStake(-10, 5, 4)).toBe(3.75);
        expect(fullGreenStake(15, -10, 2)).toBe(12.5);
        expect(fullGreenStake(15, -10, 1)).toBe(0);
    });

    it('partialOutcomes: copertura BACK di un LAY (win<lose) sposta i due esiti', () => {
        // LAY 10 @3 -> vince -20 / perde +10 ; back 5 @3 (50% del pieno 10)
        expect(partialOutcomes(3, -20, 10, 5)).toEqual({ win: -10, lose: 5 });
        // stake pieno: i due esiti coincidono (green)
        expect(partialOutcomes(3, -20, 10, 10)).toEqual({ win: 0, lose: 0 });
        // stake 0 o prezzo non valido: posizione invariata
        expect(partialOutcomes(3, -20, 10, 0)).toEqual({ win: -20, lose: 10 });
        expect(partialOutcomes(1, -20, 10, 5)).toEqual({ win: -20, lose: 10 });
    });

    it('partialOutcomes: copertura LAY di un BACK (win>lose)', () => {
        // BACK 10 @2.5 -> vince +15 / perde -10 ; lay 6.25 @2 (50% del pieno 12.5)
        expect(partialOutcomes(2, 15, -10, 6.25)).toEqual({ win: 8.75, lose: -3.75 });
    });

    it('partialLockedPnl = PEGGIORE dei due esiti residui (mai il ramo ottimistico), clampa 0..1', () => {
        expect(partialLockedPnl(4, -10, 5, 1)).toBe(1.25);
        // 50%: back 1.88 @4 -> vince -10+5.64 = -4.36 / perde 5-1.88 = 3.12 -> peggiore -4.36
        expect(partialLockedPnl(4, -10, 5, 0.5)).toBe(-4.36);
        // 0%: nessuna copertura -> resta il peggiore della posizione (-10)
        expect(partialLockedPnl(4, -10, 5, 0)).toBe(-10);
        expect(partialLockedPnl(4, -10, 5, 9)).toBe(1.25);
        // esempio di riferimento: LAY 10 @3, best back 3, 50% -> -10
        expect(partialLockedPnl(3, -20, 10, 0.5)).toBe(-10);
    });

    it('netAfterCommission taglia solo il positivo e legge frazione o percentuale', () => {
        expect(netAfterCommission(10, 0.05)).toBe(9.5);
        expect(netAfterCommission(10, 5)).toBe(9.5);
        expect(netAfterCommission(-10, 5)).toBe(-10);
        expect(netAfterCommission(10)).toBe(10);
    });
});

// ---------------------------------------------------------------- rendering
describe('CashOutButton — posizione LAY', () => {
    it('il bottone mostra il P&L bloccato al best back', () => {
        renderBtn();
        // lay 5 @3 coperto back @4: locked = 5 + (-10-5)/4 = +1.25
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('+');
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('1,25 €');
    });

    it('il P&L bloccato riflette la commissione', () => {
        renderBtn({ commission: 5 });
        // 1.25 * 0.95 = 1.1875 -> 1.19
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('1,19 €');
    });
});

describe('CashOutButton — posizione BACK', () => {
    it('si copre bancando al best lay', () => {
        // back 10 @2.5 -> vince +15 / perde -10 ; lay @2.00: locked = -10 + 25/2 = +2.50
        renderBtn({ win: 15, lose: -10, bestBack: 1.9, bestLay: 2 });
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('2,50 €');
    });
});

describe('CashOutButton — stati disabilitati', () => {
    it('senza quote il bottone e disabilitato', () => {
        renderBtn({ bestBack: null, bestLay: null });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByTestId('cashout-disabled-wrap')).toBeInTheDocument();
    });

    it('posizione gia bilanciata: niente da chiudere', () => {
        renderBtn({ win: 3, lose: 3 });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
    });

    it('la prop disabled vince comunque', () => {
        renderBtn({ disabled: true });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
    });
});

describe('CashOutButton — dialog e conferma', () => {
    it('apre il dialog col green pieno preimpostato', async () => {
        const user = userEvent.setup();
        renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        const input = await screen.findByLabelText('Importo cash out');
        expect(input).toHaveValue(3.75);
        expect(screen.getByTestId('cashout-locked')).toHaveTextContent('1,25 €');
    });

    it('i bottoni rapidi impostano la quota; il parziale mostra PEGGIORE (titolo) e migliore', async () => {
        const user = userEvent.setup();
        renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        await user.click(await screen.findByRole('button', { name: '50%' }));
        expect(screen.getByLabelText('Importo cash out')).toHaveValue(1.88);
        // back 1.88 @4: vince -4.36 / perde +3.12 -> titolo = peggiore
        expect(screen.getByTestId('cashout-locked')).toHaveTextContent('−4,36 €');
        expect(screen.getByTestId('cashout-best')).toHaveTextContent('+3,12 €');
        // parziale = resta esposizione aperta, dichiarata esplicitamente
        expect(screen.getByTestId('cashout-residual')).toHaveTextContent(/resta aperto/);
        expect(screen.getByText(/parziale 50%: resta esposto/)).toBeInTheDocument();
        expect(screen.queryByText(/P&L bloccato/)).toBeNull();
    });

    it('CRITICAL-1: LAY 10 @3, best back 3, 50% -> titolo −10,00 € (non il ramo ottimistico +5)', async () => {
        const user = userEvent.setup();
        renderBtn({ win: -20, lose: 10, bestBack: 3, bestLay: 3.1 });
        await user.click(screen.getByTestId('cashout-trigger'));
        await user.click(await screen.findByRole('button', { name: '50%' }));
        expect(screen.getByLabelText('Importo cash out')).toHaveValue(5);
        expect(screen.getByTestId('cashout-locked')).toHaveTextContent('−10,00 €');
        expect(screen.getByTestId('cashout-best')).toHaveTextContent('+5,00 €');
        // green pieno: un solo numero, etichetta "bloccato"
        await user.click(screen.getByRole('button', { name: '100%' }));
        expect(screen.getByTestId('cashout-locked')).toHaveTextContent('+0,00 €');
        expect(screen.getByText(/P&L bloccato \(green pieno\)/)).toBeInTheDocument();
        expect(screen.queryByTestId('cashout-best')).toBeNull();
    });

    it('conferma con frazione quando si usa un bottone rapido', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        await user.click(await screen.findByRole('button', { name: '50%' }));
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledWith({ fraction: 0.5 });
    });

    it('conferma con importo quando lo si digita a mano', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        const input = await screen.findByLabelText('Importo cash out');
        await user.clear(input);
        await user.type(input, '1.20');
        // back 1.20 @4: vince -6.40 / perde +3.80 -> titolo = peggiore
        expect(screen.getByTestId('cashout-locked')).toHaveTextContent('−6,40 €');
        expect(screen.getByTestId('cashout-best')).toHaveTextContent('+3,80 €');
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledWith({ amount: 1.2 });
    });

    it('avvisa sotto la soglia dei 2 EUR', async () => {
        const user = userEvent.setup();
        renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        const input = await screen.findByLabelText('Importo cash out');
        await user.clear(input);
        await user.type(input, '1.50');
        expect(screen.getByTestId('cashout-min-note')).toHaveTextContent(/metodo 1000/);
    });

    it('importo fuori range: conferma bloccata', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        const input = await screen.findByLabelText('Importo cash out');
        await user.clear(input);
        await user.type(input, '99');
        expect(screen.getByTestId('cashout-confirm')).toBeDisabled();
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('in LIVE serve la doppia conferma', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderBtn({ mode: 'live' });
        await user.click(screen.getByTestId('cashout-trigger'));
        const confirmBtn = await screen.findByTestId('cashout-confirm');
        await user.click(confirmBtn);
        expect(onCashOut).not.toHaveBeenCalled();
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledWith({ fraction: 1 });
    });

    it('MEDIUM-2: la conferma LIVE armata decade se cambia l importo', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderBtn({ mode: 'live' });
        await user.click(screen.getByTestId('cashout-trigger'));
        await user.click(await screen.findByTestId('cashout-confirm'));
        expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/Confermi/);
        await user.click(screen.getByRole('button', { name: '50%' }));
        expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/^Chiudi/);
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('MEDIUM-2: la conferma LIVE armata decade dopo 10 s', () => {
        vi.useFakeTimers();
        try {
            const { onCashOut } = renderBtn({ mode: 'live' });
            fireEvent.click(screen.getByTestId('cashout-trigger'));
            fireEvent.click(screen.getByTestId('cashout-confirm'));
            expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/Confermi/);
            act(() => { vi.advanceTimersByTime(LIVE_ARM_TIMEOUT_MS + 1); });
            expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/^Chiudi/);
            expect(onCashOut).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });
});

describe('CashOutButton — anti doppio cash out (HIGH-1)', () => {
    it('pending: bottone spento', () => {
        renderBtn({ pending: true });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByTestId('cashout-disabled-wrap')).toBeInTheDocument();
    });

    it('disabledReason: il motivo arriva nel tooltip (quote non aggiornate)', async () => {
        const user = userEvent.setup();
        renderBtn({ disabled: true, disabledReason: 'quote non aggiornate (31s)' });
        await user.hover(screen.getByTestId('cashout-disabled-wrap'));
        expect((await screen.findAllByText('quote non aggiornate (31s)')).length).toBeGreaterThan(0);
    });

    it('doppio click sulla conferma: UNA sola richiesta', async () => {
        let release: () => void = () => {};
        const onCashOut = vi.fn(() => new Promise<void>((r) => { release = r; }));
        render(
            <TooltipProvider>
                <CashOutButton win={-10} lose={5} bestBack={4} bestLay={4.2} mode="paper" onCashOut={onCashOut} />
            </TooltipProvider>,
        );
        fireEvent.click(screen.getByTestId('cashout-trigger'));
        const confirm = screen.getByTestId('cashout-confirm');
        fireEvent.click(confirm);
        fireEvent.click(confirm);
        fireEvent.click(confirm);
        expect(onCashOut).toHaveBeenCalledTimes(1);
        expect(confirm).toBeDisabled();
        await act(async () => { release(); });
    });
});
