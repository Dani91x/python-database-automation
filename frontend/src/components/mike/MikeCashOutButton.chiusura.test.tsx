// ============================================================================
// COLLAUDO DELLA CHIUSURA (12/09/2026) — regressioni del cash out di Mike.
//
// MIKE-01  Una richiesta di chiusura che va in ERRORE non può sparire: prima
//          `confirm()` non aveva `catch`, la promise veniva rigettata fuori dal
//          componente (il chiamante fa `void confirm()`) e il dialog restava
//          identico — il trader non sapeva se la chiusura fosse partita.
// MIKE-02  Il dialog resta aperto mentre il mondo cambia: se il feed muore, la
//          linea sparisce o parte una richiesta da un altro punto, la CONFERMA
//          deve spegnersi e dirlo (e l'eventuale arma LIVE deve cadere).
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeCashOutButton } from './MikeCashOutButton';

type Props = React.ComponentProps<typeof MikeCashOutButton>;

afterEach(() => { vi.useRealTimers(); });

function setup(over: Partial<Props> = {}) {
    const onCashOut = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    const props: Props = {
        eventName: 'Roma v Lazio', net: 0.47, pct: 3.8, targetPct: 5, base: 12.53,
        complete: true, mode: 'paper', onCashOut, ...over,
    };
    const view = render(<MikeCashOutButton {...props} />);
    const rerender = (next: Partial<Props> = {}) =>
        view.rerender(<MikeCashOutButton {...props} {...next} />);
    return { onCashOut, user, rerender };
}

describe('MIKE-01 — una chiusura che non parte si vede', () => {
    it('il servizio rifiuta: dialog APERTO, motivo a schermo, posizione dichiarata aperta', async () => {
        const onCashOut = vi.fn().mockRejectedValue(new Error('coda piena: richiesta non accettata'));
        const user = userEvent.setup();
        render(
            <MikeCashOutButton
                eventName="Roma v Lazio" net={0.47} complete mode="paper" onCashOut={onCashOut}
            />,
        );
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(await screen.findByTestId('mike-cashout-confirm'));

        const err = await screen.findByTestId('mike-cashout-error');
        expect(err).toHaveTextContent('Cash out NON riuscito');
        expect(err).toHaveTextContent('coda piena: richiesta non accettata');
        expect(err).toHaveTextContent(/ancora aperta/);
        // il dialog NON si chiude: sarebbe un "fatto" che non è successo
        expect(screen.getByTestId('mike-cashout-dialog')).toBeInTheDocument();
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });

    it('riaprendo il dialog l errore precedente non resta appiccicato', async () => {
        const onCashOut = vi.fn().mockRejectedValue(new Error('rete KO'));
        const user = userEvent.setup();
        render(
            <MikeCashOutButton
                eventName="Roma v Lazio" net={0.47} complete mode="paper" onCashOut={onCashOut}
            />,
        );
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(await screen.findByTestId('mike-cashout-confirm'));
        await screen.findByTestId('mike-cashout-error');
        await user.click(screen.getByRole('button', { name: 'Annulla' }));
        await user.click(screen.getByTestId('mike-cashout-btn'));
        expect(screen.queryByTestId('mike-cashout-error')).toBeNull();
    });
});

describe('MIKE-02 — condizioni decadute a dialog APERTO', () => {
    it('feed che si ferma: conferma spenta col motivo, nessuna richiesta inviata', async () => {
        const { onCashOut, user, rerender } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        expect(await screen.findByTestId('mike-cashout-confirm')).toBeEnabled();

        rerender({ disabledReason: 'Feed stantio (scanner fermo): il servizio rifiuterebbe la richiesta.' });

        const confirm = screen.getByTestId('mike-cashout-confirm');
        expect(confirm).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-blocked')).toHaveTextContent('Feed stantio');
        await user.click(confirm).catch(() => {});
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('prezzi incompleti sopraggiunti: nessuna chiusura su un netto non calcolabile', async () => {
        const { onCashOut, user, rerender } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await screen.findByTestId('mike-cashout-confirm');
        rerender({ complete: false });
        expect(screen.getByTestId('mike-cashout-confirm')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-blocked')).toHaveTextContent(/Prezzi incompleti/);
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('richiesta partita da un altro punto (pending): conferma spenta e dichiarata', async () => {
        const { onCashOut, user, rerender } = setup();
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await screen.findByTestId('mike-cashout-confirm');
        rerender({ pending: true });
        expect(screen.getByTestId('mike-cashout-confirm')).toBeDisabled();
        expect(screen.getByTestId('mike-cashout-blocked')).toHaveTextContent(/già inviata/);
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('LIVE: arma caduta quando le condizioni decadono, servono di nuovo due click', async () => {
        const { onCashOut, user, rerender } = setup({ mode: 'live' });
        await user.click(screen.getByTestId('mike-cashout-btn'));
        await user.click(await screen.findByTestId('mike-cashout-confirm'));
        expect(screen.getByTestId('mike-cashout-confirm')).toHaveTextContent('Confermi? soldi veri');

        rerender({ disabledReason: 'Feed di questa partita fermo.' });
        expect(screen.getByTestId('mike-cashout-confirm')).toBeDisabled();
        rerender({});
        expect(screen.getByTestId('mike-cashout-confirm')).not.toHaveTextContent('Confermi?');
        expect(onCashOut).not.toHaveBeenCalled();
    });
});
