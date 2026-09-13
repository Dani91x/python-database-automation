// ============================================================================
// COLLAUDO DELLA CHIUSURA (12/09/2026) — regressioni del CashOutButton.
//
// CHIUSURA-01  "se chiudo ora" deve essere il numero che il SERVIZIO bloccherà:
//              lo stake di copertura è arrotondato al centesimo
//              (`trading/greenup.py::_hedge_size`) e il bloccato è il PEGGIORE
//              dei due esiti (`execution.locked_pnl`). La formula ideale
//              `lockedPnlAt` = L + (W−L)/p prometteva fino a 0,60 € in più su
//              una posizione a quota alta.
// CHIUSURA-02  Il dialog resta aperto mentre il mondo cambia: se il feed muore
//              (o la posizione viene coperta altrove) la CONFERMA deve spegnersi
//              e dirlo, non restare un click a soldi veri su prezzi fantasma.
// CHIUSURA-03  Una conferma LIVE già armata non sopravvive alla decadenza.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TooltipProvider } from '@/components/ui/tooltip';
import { lockedPnlAt } from '@/lib/ladderMath';
import { CashOutButton, partialLockedPnl, type CashOutButtonProps } from './CashOutButton';

// posizione REALE di Omega: lay 5,26 @110 su un correct score → se il bancato
// esce si perdono 573,34 €, altrimenti si incassano 5,26 €. Il book offre
// back 200: la copertura costa 2,89 € di stake (2,893 arrotondati).
const LAY_ALTA_QUOTA = { win: -573.34, lose: 5.26, bestBack: 200, bestLay: 220 };

function renderBtn(over: Partial<CashOutButtonProps> = {}) {
    const onCashOut = vi.fn().mockResolvedValue(undefined);
    const props: CashOutButtonProps = {
        ...LAY_ALTA_QUOTA, mode: 'paper', onCashOut, ...over,
    };
    const view = render(<TooltipProvider><CashOutButton {...props} /></TooltipProvider>);
    const rerender = (next: Partial<CashOutButtonProps> = {}) => view.rerender(
        <TooltipProvider><CashOutButton {...props} {...next} /></TooltipProvider>,
    );
    return { onCashOut, rerender };
}

beforeEach(() => vi.clearAllMocks());

describe('CHIUSURA-01 — il numero mostrato è quello che il servizio blocca', () => {
    it('lo stake al centesimo sposta il bloccato: mostrato +1,77 €, non l ideale +2,37 €', () => {
        // la formula ideale e quella del servizio NON coincidono su quota alta
        const ideale = Math.round(lockedPnlAt(200, -573.34, 5.26) * 100) / 100;
        const servizio = partialLockedPnl(200, -573.34, 5.26, 1);
        expect(ideale).toBeCloseTo(2.37, 2);
        expect(servizio).toBeCloseTo(1.77, 2);
        expect(ideale - servizio).toBeGreaterThan(0.5);   // 60 centesimi di promessa in più

        renderBtn();
        const trigger = screen.getByTestId('cashout-trigger');
        expect(trigger).toHaveTextContent('1,77 €');
        expect(trigger).not.toHaveTextContent('2,37 €');
    });

    it('la commissione si applica al bloccato REALE (1,77 → 1,68)', () => {
        renderBtn({ commission: 5 });
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('1,68 €');
    });

    it('coerenza card ↔ dialog: il titolo del dialog al 100 % è lo stesso numero del bottone', async () => {
        const user = userEvent.setup();
        renderBtn({ commission: 5 });
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('1,68 €');
        await user.click(screen.getByTestId('cashout-trigger'));
        expect(await screen.findByTestId('cashout-locked')).toHaveTextContent('1,68 €');
    });
});

describe('CHIUSURA-02 — condizioni decadute a dialog APERTO', () => {
    it('feed che muore: conferma spenta, motivo a schermo, nessun ordine inviato', async () => {
        const user = userEvent.setup();
        const { onCashOut, rerender } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        expect(await screen.findByTestId('cashout-confirm')).toBeEnabled();

        // lo scanner si ferma: la pagina spegne il bottone col motivo
        rerender({ disabled: true, disabledReason: 'quote non aggiornate (48s)' });

        const confirm = screen.getByTestId('cashout-confirm');
        expect(confirm).toBeDisabled();
        expect(screen.getByTestId('cashout-blocked')).toHaveTextContent('quote non aggiornate (48s)');
        await user.click(confirm).catch(() => {});
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('posizione coperta da un altro ciclo (pending): conferma spenta e dichiarata', async () => {
        const user = userEvent.setup();
        const { onCashOut, rerender } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        rerender({ pending: true });
        expect(screen.getByTestId('cashout-confirm')).toBeDisabled();
        expect(screen.getByTestId('cashout-blocked')).toHaveTextContent(/già in corso/);
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('il book sparisce: nessun prezzo, nessun invio possibile', async () => {
        const user = userEvent.setup();
        const { onCashOut, rerender } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        rerender({ bestBack: null, bestLay: null });
        expect(screen.getByTestId('cashout-confirm')).toBeDisabled();
        expect(screen.getByTestId('cashout-blocked')).toHaveTextContent(/non disponibili/);
        expect(onCashOut).not.toHaveBeenCalled();
    });

    it('condizioni tornate valide: il bottone riparte (non resta spento per sempre)', async () => {
        const user = userEvent.setup();
        const { rerender } = renderBtn();
        await user.click(screen.getByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        rerender({ disabled: true, disabledReason: 'feed fermo' });
        expect(screen.getByTestId('cashout-confirm')).toBeDisabled();
        rerender({ disabled: false });
        expect(screen.getByTestId('cashout-confirm')).toBeEnabled();
        expect(screen.queryByTestId('cashout-blocked')).toBeNull();
    });
});

describe('CHIUSURA-03 — la conferma LIVE non sopravvive alla decadenza', () => {
    it('armata e poi feed fermo: l arma cade, servono di nuovo due click', async () => {
        const user = userEvent.setup();
        const { onCashOut, rerender } = renderBtn({ mode: 'live' });
        await user.click(screen.getByTestId('cashout-trigger'));
        await user.click(await screen.findByTestId('cashout-confirm'));
        expect(screen.getByTestId('cashout-confirm')).toHaveTextContent('Confermi? soldi veri');

        rerender({ disabled: true, disabledReason: 'feed fermo' });
        expect(screen.getByTestId('cashout-confirm')).toBeDisabled();
        rerender({ disabled: false });
        // l'arma NON è più in piedi: il testo è tornato quello neutro
        expect(screen.getByTestId('cashout-confirm')).not.toHaveTextContent('Confermi?');
        expect(onCashOut).not.toHaveBeenCalled();
    });
});
