// ============================================================================
// CashOutPartita.test.tsx — IL GESTO, non la funzione.
//
// Qui si prova quello che succede sotto il dito del trader: doppia conferma in
// live, badge acceso dallo STATO dichiarato dal servizio (mai dedotto), motivo
// scritto quando il pulsante e' spento, errore del servizio mostrato invece che
// nascosto.
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · un clic solo in live manda l'ordine → rosso;
//   · badge acceso senza marcatore → rosso;
//   · errore della RPC inghiottito → rosso.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CashOutPartita } from './CashOutPartita';
import type { StatoChiusuraEvento } from '@/lib/chiusuraUtente';

const APERTA: StatoChiusuraEvento = { chiusa: false, fonte: null, marcatore: null };
const CHIUSA: StatoChiusuraEvento = {
    chiusa: true, fonte: 'righe',
    marcatore: { quando: '2026-09-16T20:15:00Z', come: 'cashout_event', dettaglio: {} },
};

function monta(over: Partial<React.ComponentProps<typeof CashOutPartita>> = {}) {
    const onCashOut = vi.fn().mockResolvedValue(undefined);
    const onRiprendi = vi.fn().mockResolvedValue(undefined);
    render(
        <CashOutPartita
            eventId="35797769" modalita="paper" posizioniVive={2} stato={APERTA}
            onCashOut={onCashOut} onRiprendi={onRiprendi}
            {...over}
        />,
    );
    return { onCashOut, onRiprendi };
}

describe('cash out globale — il gesto', () => {
    it('in PAPER un clic basta, e passa l event_id della partita', async () => {
        const { onCashOut } = monta({ modalita: 'paper' });
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        await waitFor(() => expect(onCashOut).toHaveBeenCalledWith('35797769'));
    });

    it('in LIVE il primo clic ARMA e non manda niente', () => {
        const { onCashOut } = monta({ modalita: 'live' });
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        expect(onCashOut).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-cashout-partita-armato').textContent).toMatch(/soldi veri/i);
    });

    it('in LIVE il SECONDO clic manda', async () => {
        const { onCashOut } = monta({ modalita: 'live' });
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        fireEvent.click(screen.getByTestId('cr-cashout-partita-conferma'));
        await waitFor(() => expect(onCashOut).toHaveBeenCalledWith('35797769'));
    });

    it('modalita NON dichiarata = si chiede conferma comunque (fail-closed)', () => {
        const { onCashOut } = monta({ modalita: null });
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        expect(onCashOut).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-cashout-partita-armato')).toBeTruthy();
    });

    it('armato, si puo annullare senza mandare niente', () => {
        const { onCashOut } = monta({ modalita: 'live' });
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        fireEvent.click(screen.getByTestId('cr-cashout-partita-annulla'));
        expect(screen.queryByTestId('cr-cashout-partita-conferma')).toBeNull();
        expect(onCashOut).not.toHaveBeenCalled();
    });
});

describe('il badge lo accende il SERVIZIO, non la pagina', () => {
    it('senza marcatore nessun badge e nessun «Riprendi»', () => {
        monta({ stato: APERTA });
        expect(screen.queryByTestId('cr-badge-chiusa-da-te')).toBeNull();
        expect(screen.queryByTestId('cr-riprendi-partita')).toBeNull();
    });

    it('col marcatore: badge «chiusa da te», niente cash out, e il «Riprendi»', () => {
        monta({ stato: CHIUSA });
        expect(screen.getByTestId('cr-badge-chiusa-da-te').textContent).toMatch(/chiusa da te/i);
        expect(screen.queryByTestId('cr-cashout-partita-avvia')).toBeNull();
        expect(screen.getByTestId('cr-riprendi-partita')).toBeTruthy();
    });

    it('il badge racconta COME e QUANDO, dal marcatore del servizio', () => {
        monta({ stato: CHIUSA });
        const t = screen.getByTestId('cr-badge-chiusa-da-te').getAttribute('title') ?? '';
        expect(t).toMatch(/cash out globale/i);
        expect(t).toMatch(/alle /);
    });

    it('marcatore senza istante: si scrive «non dichiarato», mai un orario inventato', () => {
        monta({ stato: { chiusa: true, fonte: 'righe', marcatore: { quando: null, come: null, dettaglio: {} } } });
        expect(screen.getByTestId('cr-badge-chiusa-da-te').getAttribute('title'))
            .toMatch(/istante non dichiarato/);
    });

    it('«Riprendi» manda l event_id', async () => {
        const { onRiprendi } = monta({ stato: CHIUSA });
        fireEvent.click(screen.getByTestId('cr-riprendi-partita'));
        await waitFor(() => expect(onRiprendi).toHaveBeenCalledWith('35797769'));
    });
});

describe('un pulsante spento dice PERCHE', () => {
    it('nessuna posizione viva: spento, col motivo scritto', () => {
        monta({ posizioniVive: 0 });
        const b = screen.getByTestId('cr-cashout-partita-avvia') as HTMLButtonElement;
        expect(b.disabled).toBe(true);
        expect(screen.getByTestId('cr-cashout-partita-bloccato').textContent)
            .toMatch(/nessuna posizione viva/);
    });
});

describe('l errore del servizio si LEGGE, non si nasconde', () => {
    it('migrazione non applicata: il messaggio della RPC finisce a schermo', async () => {
        const onCashOut = vi.fn().mockRejectedValue(new Error('kind non valido: cashout_event'));
        render(
            <CashOutPartita eventId="e1" modalita="paper" posizioniVive={1} stato={APERTA}
                onCashOut={onCashOut} onRiprendi={vi.fn()} />,
        );
        fireEvent.click(screen.getByTestId('cr-cashout-partita-avvia'));
        await waitFor(() => {
            expect(screen.getByTestId('cr-cashout-partita-errore').textContent)
                .toMatch(/kind non valido: cashout_event/);
        });
    });
});
