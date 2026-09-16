// ============================================================================
// SchedaChiusuraOmega.test.tsx — LA SCHEDA CHE DECIDE UN'USCITA DI OMEGA.
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · un clic solo in live manda l'ordine → rosso;
//   · «Chiudi ora» acceso su una proposta che il servizio non propone → rosso;
//   · un numero assente stampato come 0,00 € → rosso;
//   · l'errore della RPC nascosto → rosso.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SchedaChiusuraOmega } from './SchedaChiusuraOmega';
import type { PropostaUscitaOmega, PropostaUscitaOmegaPayload } from '@/lib/omegaProposte';

function proposta(over: Partial<PropostaUscitaOmegaPayload> = {}): PropostaUscitaOmega {
    return {
        id: 9, kind: 'cashout', created_at: '2026-09-16T21:00:00Z', updated_at: null,
        payload: {
            trade_id: 4821, event_id: '35760084', event_name: 'Trinec v Mlada Boleslav',
            market_id: '1.245', market_type: 'CORRECT_SCORE', selection_id: 77,
            selection_name: '0 - 2', side: 'back', entry_side: 'lay', entry_price: 65, size: 1,
            price_at_decision: 31, size_available_at_decision: 12.5,
            motivo_codice: 'blocca_il_profitto', profitto_bloccabile: 0.94,
            back_price: 31, back_size: 2.1, ev_tenere: 0.42, p_evento: 0.0123,
            meglio_aspettare: false, bloccabile_max_atteso: 0.88, minuto_del_massimo: 72,
            minute: 38, score: '0-1', mode: 'paper',
            decided_at: '2026-09-16T21:00:00Z', proposed_at: '2026-09-16T21:00:30Z',
            ...over,
        },
    };
}

function monta(p = proposta()) {
    const onApprova = vi.fn().mockResolvedValue(undefined);
    const onIgnora = vi.fn().mockResolvedValue(undefined);
    render(<SchedaChiusuraOmega proposta={p} onApprova={onApprova} onIgnora={onIgnora} />);
    return { onApprova, onIgnora };
}

describe('i tre numeri stanno insieme (memoria del 12/09)', () => {
    it('blocchi adesso, tenere vale, e la traiettoria', () => {
        monta();
        const t = screen.getByTestId('cr-proposta-omega').textContent ?? '';
        expect(t).toMatch(/Blocchi adesso/i);
        expect(t).toMatch(/Tenere vale/i);
        expect(t).toMatch(/Se il punteggio regge/i);
        expect(t).toMatch(/al 72′/);
    });

    it('un numero ASSENTE si scrive «—», mai 0,00 €', () => {
        monta(proposta({ ev_tenere: null, bloccabile_max_atteso: null, size_available_at_decision: null }));
        const t = screen.getByTestId('cr-proposta-omega').textContent ?? '';
        expect(t).toContain('—');
    });

    it('l istante della decisione, o «non dichiarato»', () => {
        monta(proposta({ decided_at: null }));
        expect(screen.getByTestId('cr-proposta-omega').textContent).toMatch(/istante non dichiarato/);
    });
});

describe('doppia conferma in live', () => {
    it('in paper un clic basta', async () => {
        const { onApprova } = monta(proposta({ mode: 'paper' }));
        fireEvent.click(screen.getByTestId('cr-omega-approva'));
        await waitFor(() => expect(onApprova).toHaveBeenCalledWith(9));
    });

    it('in live il primo clic ARMA e non manda niente', () => {
        const { onApprova } = monta(proposta({ mode: 'live' }));
        fireEvent.click(screen.getByTestId('cr-omega-approva'));
        expect(onApprova).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-omega-conferma-live')).toBeTruthy();
    });

    it('in live il secondo clic manda', async () => {
        const { onApprova } = monta(proposta({ mode: 'live' }));
        fireEvent.click(screen.getByTestId('cr-omega-approva'));
        fireEvent.click(screen.getByTestId('cr-omega-conferma-live'));
        await waitFor(() => expect(onApprova).toHaveBeenCalledWith(9));
    });

    it('«Ignora» non chiede conferma: non muove soldi', async () => {
        const { onIgnora } = monta(proposta({ mode: 'live' }));
        fireEvent.click(screen.getByTestId('cr-omega-ignora'));
        await waitFor(() => expect(onIgnora).toHaveBeenCalledWith(9));
    });
});

describe('un pulsante spento dice PERCHE', () => {
    it('il servizio non propone: spento, col motivo in italiano', () => {
        monta(proposta({ motivo_codice: 'aspettare_vale_di_piu', meglio_aspettare: true }));
        const b = screen.getByTestId('cr-omega-approva') as HTMLButtonElement;
        expect(b.disabled).toBe(true);
        expect(screen.getByTestId('cr-proposta-omega-bloccata').textContent)
            .toMatch(/se il punteggio regge/i);
    });

    it('senza prezzo di back: spento', () => {
        monta(proposta({ back_price: null }));
        expect((screen.getByTestId('cr-omega-approva') as HTMLButtonElement).disabled).toBe(true);
    });
});

describe('l errore del servizio si LEGGE', () => {
    it('migrazione non applicata: il messaggio finisce a schermo', async () => {
        const onApprova = vi.fn().mockRejectedValue(new Error('function omega_request_approve does not exist'));
        render(<SchedaChiusuraOmega proposta={proposta()} onApprova={onApprova} onIgnora={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-omega-approva'));
        await waitFor(() => {
            expect(screen.getByTestId('cr-proposta-omega-errore').textContent)
                .toMatch(/does not exist/);
        });
    });
});
