// ============================================================================
// StatoOrdine.test.tsx — C.12b: quello che il trader LEGGE su ogni riga ordine.
//
// «ordine x a prezzo y: abbinato? in che quantita'? tutto o parziale?»
// Qui si controlla che la risposta sia a schermo, con i formatter unici, e che
// un dato ASSENTE resti «—»: la falsificazione del 16/09 (rimettere «0,00 €»
// al posto di «—») deve rendere questi test ROSSI.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatoOrdineRiga, StatoOrdineCompatto } from './StatoOrdine';

/** parziale con le colonne della migrazione del 16/09 */
const PARZIALE = {
    status: 'pending', side: 'lay', price: 2.4, size: 2,
    size_requested: 5, size_matched: 2, size_remaining: 3,
    avg_price_matched: 2.38,
    betfair_updated_at: '2026-09-16T10:00:00.000Z',
    meta: null,
};
const ORA = Date.parse('2026-09-16T10:00:45.000Z');

describe('StatoOrdineRiga — i tre numeri e lo stato', () => {
    it('chiesto, abbinato col prezzo MEDIO, residuo e stato', () => {
        render(<StatoOrdineRiga riga={PARZIALE} nowMs={ORA} />);
        expect(screen.getByTestId('stato-ordine-chiesto')).toHaveTextContent('chiesto 5,00 € @2,40');
        expect(screen.getByTestId('stato-ordine-abbinato')).toHaveTextContent('abbinato 2,00 € @2,38');
        expect(screen.getByTestId('stato-ordine-residuo')).toHaveTextContent('residuo 3,00 €');
        expect(screen.getByTestId('stato-ordine-badge')).toHaveTextContent('ABBINATO IN PARTE');
        expect(screen.getByTestId('stato-ordine')).toHaveAttribute('data-esito', 'parziale');
    });

    it('«quando l ho saputo da Betfair»: eta col formatter unico', () => {
        render(<StatoOrdineRiga riga={PARZIALE} nowMs={ORA} />);
        expect(screen.getByTestId('stato-ordine-eta')).toHaveTextContent('da Betfair 45 s fa');
    });

    it('nessun badge «dalla nota» quando i numeri vengono dalle colonne', () => {
        render(<StatoOrdineRiga riga={PARZIALE} nowMs={ORA} />);
        expect(screen.queryByTestId('stato-ordine-badge-nota')).toBeNull();
    });

    it('col meta al posto delle colonne: gli stessi numeri, DICHIARATI come nota', () => {
        // safe_strategy/execution.py:614-620 — la catena dei tempi
        render(<StatoOrdineRiga
            riga={{
                status: 'open', side: 'back', price: 3.05, size: 0.8,
                meta: {
                    fill: 'live_submin:EXECUTION_COMPLETE', size_capped_from: 2,
                    esecuzione: {
                        price_richiesto: 3.1, price_medio: 3.05, scorrimento_tick: -1,
                        size_richiesta: 2, size_abbinata: 0.8, size_residua: 1.2,
                    },
                },
            }}
            nowMs={ORA}
        />);
        // l'asterisco accanto al numero e' il marcatore «viene dalla nota»
        expect(screen.getByTestId('stato-ordine-chiesto')).toHaveTextContent('chiesto 2,00 €*');
        expect(screen.getByTestId('stato-ordine-abbinato')).toHaveTextContent('abbinato 0,80 €* @3,05*');
        expect(screen.getByTestId('stato-ordine-residuo')).toHaveTextContent('residuo 1,20 €*');
        // §C.10: `scorrimento_tick` era salvato e non lo mostrava nessuno
        expect(screen.getByTestId('stato-ordine-scorrimento')).toHaveTextContent('scorrimento 1 tick');
        expect(screen.getByTestId('stato-ordine-badge-nota')).toHaveTextContent('dalla nota');
        expect(screen.getByTestId('stato-ordine')).toHaveAttribute('data-dalla-nota', '1');
    });

    it('⚠️ riga senza niente: «—» ovunque e MAI «0,00 €»', () => {
        render(<StatoOrdineRiga riga={{ status: 'pending', price: 2.2, size: 5 }} nowMs={ORA} />);
        const riga = screen.getByTestId('stato-ordine');
        expect(screen.getByTestId('stato-ordine-chiesto')).toHaveTextContent('chiesto —');
        expect(screen.getByTestId('stato-ordine-abbinato')).toHaveTextContent('abbinato — @—');
        expect(screen.getByTestId('stato-ordine-residuo')).toHaveTextContent('residuo —');
        expect(screen.getByTestId('stato-ordine-eta')).toHaveTextContent('da Betfair — fa');
        expect(riga.textContent).not.toMatch(/0,00/);
        expect(riga).toHaveAttribute('data-esito', 'ignoto');
    });

    it('APPOGGIATO ha un etichetta sua: non e «APERTO»', () => {
        render(<StatoOrdineRiga
            riga={{
                status: 'pending', side: 'lay', price: 2.14, size: 0,
                size_requested: 5, size_matched: 0, size_remaining: 5,
                meta: { phase: 'open', fill: 'live_resting' },
            }}
            nowMs={ORA}
        />);
        const badge = screen.getByTestId('stato-ordine-badge');
        expect(badge).toHaveTextContent('APPOGGIATA · NON ABBINATA');
        expect(badge.textContent).not.toBe('APERTO');
        expect(screen.getByTestId('stato-ordine')).toHaveAttribute('data-esito', 'appoggiato');
    });

    it('RIFIUTATO: il codice di Betfair a schermo, non sepolto in un log', () => {
        render(<StatoOrdineRiga
            riga={{ status: 'error', meta: { error_final: true, error_code: 'INSUFFICIENT_FUNDS' } }}
            nowMs={ORA}
        />);
        expect(screen.getByTestId('stato-ordine-badge'))
            .toHaveTextContent('RIFIUTATO DA BETFAIR: INSUFFICIENT_FUNDS');
    });
});

describe('StatoOrdineCompatto — una riga sola per le liste dense', () => {
    it('i tre numeri in una riga', () => {
        render(<StatoOrdineCompatto riga={PARZIALE} />);
        expect(screen.getByTestId('stato-ordine-compatto'))
            .toHaveTextContent('chiesti 5,00 € @2,40 · abbinati 2,00 € @2,38 · residuo 3,00 €');
    });

    it('⚠️ senza numeri lo DICE, non allinea zeri', () => {
        render(<StatoOrdineCompatto riga={{ status: 'open', price: 2, size: 3 }} />);
        const el = screen.getByTestId('stato-ordine-compatto');
        expect(el).toHaveTextContent('abbinamento non dichiarato dal servizio');
        expect(el.textContent).not.toMatch(/0,00/);
    });
});
