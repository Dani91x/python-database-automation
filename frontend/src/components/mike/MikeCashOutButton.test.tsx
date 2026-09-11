// Test COMPONENTE del cash out di Mike (chiusura per EVENTO, non frazionabile):
// dialog con il netto DEL SERVIZIO, dettaglio per gamba, doppia conferma in
// LIVE con decadenza dell'arma, bottone spento CON MOTIVO (feed stantio, linea
// assente, richiesta in volo, prezzi incompleti) e nessun doppio invio.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeCashOutButton, MIKE_LIVE_ARM_TIMEOUT_MS } from './MikeCashOutButton';

afterEach(() => { vi.useRealTimers(); });

function setup(over: Partial<React.ComponentProps<typeof MikeCashOutButton>> = {}) {
    const onCashOut = vi.fn();
    const user = userEvent.setup();
    render(
        <MikeCashOutButton
            eventName="Roma v Lazio"
            net={0.47}
            pct={3.8}
            targetPct={5}
            base={12.53}
            complete
            mode="paper"
            breakdown={[{ label: 'Under 3.5', value: -1.28 }, { label: 'Over 4.5', value: 1.75 }]}
            onCashOut={onCashOut}
            {...over}
        />,
    );
    return { onCashOut, user };
}

describe('MikeCashOutButton — bottone e dialog', () => {
    it('il bottone porta il NETTO del servizio in formato italiano', () => {
        setup();
        expect(screen.getByTestId('mike-cashout-btn')).toHaveTextContent('+0,47 €');
        expect(screen.getByTestId('mike-cashout-btn')).toBeEnabled();
    });

    it('il dialog mostra netto, % sulla base, soglia automatica e dettaglio per GAMBA', async () => {
        const { user } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        const dialog = screen.getByTestId('mike-cashout-dialog');
        expect(screen.getByTestId('mike-cashout-dialog-net')).toHaveTextContent('+0,47 €');
        expect(dialog).toHaveTextContent('Roma v Lazio');
        expect(dialog).toHaveTextContent(/3,8\s*%/);
        expect(dialog).toHaveTextContent('12,53 €');
        expect(dialog).toHaveTextContent(/soglia automatica 5,0\s*%/);
        // la chiusura è INTERA: va detto (Mike non accetta cash out parziali)
        expect(dialog).toHaveTextContent('Mike non accetta cash out parziali');
        const rows = screen.getByTestId('mike-cashout-breakdown');
        expect(rows).toHaveTextContent('Under 3.5');
        expect(rows).toHaveTextContent(/[-−]1,28 €/);
        expect(rows).toHaveTextContent('Over 4.5');
        expect(rows).toHaveTextContent('+1,75 €');
    });

    it('in PAPER una sola conferma chiude', async () => {
        const { onCashOut, user } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });

    it('"Annulla" non invia nulla', async () => {
        const { onCashOut, user } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(screen.getByText('Annulla'));
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('mostra l’esito dell’ultima richiesta (M1)', async () => {
        const { user } = setup({ lastOutcome: 'Cash out rifiutato: feed stantio' });
        await user.click(screen.getByTestId('mike-cashout-btn'));
        expect(screen.getByTestId('mike-cashout-last')).toHaveTextContent('feed stantio');
    });
});

describe('MikeCashOutButton — LIVE: soldi veri, doppia conferma', () => {
    it('il primo click ARMA, il secondo invia', async () => {
        const { onCashOut, user } = setup({ mode: 'live' });
        await user.click(screen.getByTestId('mike-cashout-btn'));
        expect(screen.getByTestId('mike-cashout-dialog')).toHaveTextContent('soldi veri');
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onCashOut).not.toHaveBeenCalled();
        expect(screen.getByTestId('mike-cashout-confirm')).toHaveTextContent('Confermi? soldi veri');
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });

    it('l’arma DECADE da sola: non resta un click a soldi veri in sospeso', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
        const onCashOut = vi.fn();
        render(
            <MikeCashOutButton eventName="Roma v Lazio" net={0.47} complete mode="live"
                               onCashOut={onCashOut} />,
        );
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(screen.getByTestId('mike-cashout-confirm')).toHaveTextContent('Confermi?');
        await act(async () => { await vi.advanceTimersByTimeAsync(MIKE_LIVE_ARM_TIMEOUT_MS + 100); });
        expect(screen.getByTestId('mike-cashout-confirm')).not.toHaveTextContent('Confermi?');
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(onCashOut).not.toHaveBeenCalled();       // serve di nuovo la doppia conferma
    });

    it('se il netto CAMBIA l’arma decade (non si conferma un numero vecchio)', async () => {
        const onCashOut = vi.fn();
        const user = userEvent.setup();
        const { rerender } = render(
            <MikeCashOutButton eventName="Roma v Lazio" net={0.47} complete mode="live"
                               onCashOut={onCashOut} />,
        );
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(screen.getByTestId('mike-cashout-confirm')).toHaveTextContent('Confermi?');
        rerender(
            <MikeCashOutButton eventName="Roma v Lazio" net={-3.2} complete mode="live"
                               onCashOut={onCashOut} />,
        );
        expect(screen.getByTestId('mike-cashout-confirm')).not.toHaveTextContent('Confermi?');
    });
});

describe('MikeCashOutButton — spento CON MOTIVO', () => {
    it('feed stantio: bottone spento e motivo scritto accanto', () => {
        setup({ disabledReason: 'Feed stantio (scanner fermo): il servizio rifiuterebbe la richiesta.' });
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Feed stantio');
        expect(screen.getByTestId('mike-cashout-disabled')).toBeInTheDocument();
    });

    it('richiesta già in volo: il motivo lo dice e vince sugli altri', () => {
        setup({ pending: true, disabledReason: 'Feed stantio' });
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Richiesta già inviata');
    });

    it('netto non calcolabile: "n/d" e motivo del servizio', () => {
        setup({ net: null });
        expect(screen.getByTestId('mike-cashout-btn')).toHaveTextContent('n/d');
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason'))
            .toHaveTextContent('non ha ancora un valore di chiusura');
    });

    it('prezzi incompleti su una selezione viva: spento e dichiarato', () => {
        setup({ complete: false });
        expect(screen.getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-off-reason')).toHaveTextContent('Prezzi incompleti');
    });

    it('nessun doppio invio: il secondo click a richiesta in volo non parte', async () => {
        const hold: { release: (() => void) | null } = { release: null };
        const onCashOut = vi.fn(() => new Promise<void>((res) => { hold.release = res; }));
        const user = userEvent.setup();
        render(
            <MikeCashOutButton eventName="Roma v Lazio" net={0.47} complete mode="paper"
                               onCashOut={onCashOut} />,
        );
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(screen.getByTestId('mike-cashout-confirm'));
        expect(screen.getByTestId('mike-cashout-confirm')).toBeDisabled();
        hold.release?.();
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });
});
