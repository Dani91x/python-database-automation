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
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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

// 24/09 — ORDINE DELL'UTENTE: «una scheda che ricalcola al ms tutto MA NON
// BLOCCA: me lo segnala e decido io». Fino al 23/09 questi due test si
// chiamavano «un pulsante spento dice PERCHE» e pretendevano il bottone SPENTO.
describe('il bottone resta ACCESO e l’avviso dice PERCHE', () => {
    it('il servizio non propone: acceso, col motivo in italiano come avviso', () => {
        monta(proposta({ motivo_codice: 'aspettare_vale_di_piu', meglio_aspettare: true }));
        const b = screen.getByTestId('cr-omega-approva') as HTMLButtonElement;
        expect(b.disabled).toBe(false);
        expect(screen.getByTestId('cr-proposta-omega-avviso').textContent)
            .toMatch(/se il punteggio regge/i);
    });

    it('senza prezzo di back: acceso, e dice che il prezzo vivo manca', () => {
        monta(proposta({ back_price: null }));
        expect((screen.getByTestId('cr-omega-approva') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-proposta-omega-avviso').textContent).toMatch(/prezzo vivo assente/);
    });
});

// ---------------------------------------------------------------- AL MS (24/09)
// Una finta della sorgente ladder con la FORMA di `LiveLadderRow` (lib/live.ts)
// e l'interfaccia di `LadderSource` (subscribe/fetch): il test spinge i tick.
function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    let staccate = 0;
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { staccate += 1; cbs.delete(mid); };
        },
        fonte: () => 'canale' as const,
    };
    const spingi = (mid: string, back: number, size: number, ms = Date.now()) => act(() => {
        cbs.get(mid)?.({
            event_id: '35760084', market_id: mid, market_type: 'CORRECT_SCORE', market_name: 'CS',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [{ selection_id: 77, name: '0 - 2', ltp: back,
                tv: 0, back: [[back, size]], lay: [[back + 1, size]], trd: [],
                wom: { back_pct: 50, lay_pct: 50 } }] },
        });
    });
    return { sorgente: () => src as never, spingi, iscritti: () => cbs.size, staccate: () => staccate };
}

// payload con gli INGREDIENTI del servizio (omega_proposte._ingredienti_del_payload)
const conIngredienti = (over: Partial<PropostaUscitaOmegaPayload> = {}) => proposta({
    entry_price: 4.0, size: 1, back_price: 6.0, back_size: 0.67, ev_tenere: 0.1, p_evento: 0.2,
    max_attesa: null, commissione: 0.05, margine_attesa: 0.02, p_lose_max: 0,
    profitto_bloccabile: 0.3167, ...over,
});

describe('scheda di Omega AL MS', () => {
    it('si iscrive al mercato, ricalcola «Blocchi adesso» a ogni tick e si stacca alla chiusura', () => {
        const f = sorgenteFinta();
        const { unmount } = render(<SchedaChiusuraOmega proposta={conIngredienti()}
            onApprova={vi.fn()} onIgnora={vi.fn()} sorgenteLadder={f.sorgente} />);
        expect(f.iscritti()).toBe(1);
        f.spingi('1.245', 10.0, 100);
        // lay 1 a 4.0, back a 10.0: (1 - 4/10) * 0.95 = 0.57
        expect(screen.getByTestId('cr-omega-back-price').textContent).toContain('10,00');
        expect(screen.getByTestId('cr-proposta-omega').textContent).toMatch(/0,57/);
        expect(screen.getByTestId('cr-omega-semaforo').getAttribute('data-semaforo')).toBe('SI');
        expect(screen.getByTestId('cr-omega-fonte').textContent).toMatch(/canale al ms/);
        // il prezzo scende: chiudere ora COSTA e tenere vale di piu' -> NO, ma il bottone resta acceso
        f.spingi('1.245', 3.5, 100);
        expect(screen.getByTestId('cr-omega-semaforo').getAttribute('data-semaforo')).toBe('NO');
        expect(screen.getByTestId('cr-proposta-omega-avviso').textContent).toMatch(/al prezzo di adesso/);
        expect((screen.getByTestId('cr-omega-approva') as HTMLButtonElement).disabled).toBe(false);
        unmount();
        expect(f.staccate()).toBe(1);
    });

    it('QUASI: regge adesso ma un tick piu\' basso la farebbe cadere', () => {
        const f = sorgenteFinta();
        // back 4.1 contro lay 4.0: profitto (1-4/4.1)*0.95 = 0.0232 > ev 0.02; a 4.0 = 0 -> cade
        render(<SchedaChiusuraOmega proposta={conIngredienti({ ev_tenere: 0.02 })}
            onApprova={vi.fn()} onIgnora={vi.fn()} sorgenteLadder={f.sorgente} />);
        f.spingi('1.245', 4.1, 100);
        expect(screen.getByTestId('cr-omega-semaforo').getAttribute('data-semaforo')).toBe('QUASI');
    });

    it('la valutazione del servizio «non piu\' valida» e\' un AVVISO', () => {
        render(<SchedaChiusuraOmega proposta={conIngredienti({
            valutazione: { valida: false, motivo_codice: 'tenere_vale_di_piu' } })}
            onApprova={vi.fn()} onIgnora={vi.fn()} />);
        expect(screen.getByTestId('cr-proposta-omega-avviso').textContent)
            .toMatch(/non la proporrebbe più: tenere vale di più/);
        expect((screen.getByTestId('cr-omega-approva') as HTMLButtonElement).disabled).toBe(false);
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
