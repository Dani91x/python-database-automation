// ============================================================================
// PosizioniChiuse.test.tsx — LA SCHEDA MOSTRA SOLO LA GIORNATA (17/09).
//
// «in "posizioni chiuse" voglio vedere SOLO le posizioni della giornata, non
// le precedenti; per i giorni precedenti deve esserci uno STORICO dedicato»
// (utente, 17/09).
//
// I finti sono costruiti dalla funzione VERA (`posizioniChiuse`) a partire da
// righe con le identiche chiavi delle RPC dei bot: la scheda riceve quello che
// riceve in produzione, non un oggetto scritto a mano.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PosizioniChiuse } from './PosizioniChiuse';
import { posizioniChiuse, type TradeChiudibile } from '@/lib/posizioniChiuse';

const OGGI = '2026-09-17';

function riga(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'safe', event_id: 'E1', event_name: 'Rossi - Bianchi', sport: 'tennis',
        mode: 'live', status: 'won', pnl: 0, side: 'back', price: 1.1, size: 3,
        selection_name: 'Rossi', placed_at: '2026-09-17T09:00:00.000Z',
        settled_at: '2026-09-17T12:00:00.000Z', closes_trade_id: null, strategy: 'tennis',
        ...over,
    };
}

function monta(trades: TradeChiudibile[], sport: 'calcio' | 'tennis' | null = null) {
    return render(
        <MemoryRouter>
            <PosizioniChiuse chiuse={posizioniChiuse(trades)} sport={sport} giorno={OGGI} />
        </MemoryRouter>,
    );
}

describe('posizioni chiuse: solo oggi', () => {
    const oggi = riga({ id: 1, pnl: 1.2, event_name: 'Partita di oggi' });
    const ieri = riga({
        id: 2, pnl: 9.9, event_name: 'Partita di ieri',
        placed_at: '2026-09-16T09:00:00.000Z', settled_at: '2026-09-16T12:00:00.000Z',
    });

    it('elenca la posizione di oggi e NON quella di ieri', () => {
        monta([oggi, ieri]);
        expect(screen.getByText('Partita di oggi')).toBeInTheDocument();
        expect(screen.queryByText('Partita di ieri')).toBeNull();
        expect(screen.getAllByTestId('cr-chiusa')).toHaveLength(1);
    });

    it('il totale in testa e\' quello di oggi, non della storia intera', () => {
        monta([oggi, ieri]);
        // 1,20 di oggi; 11,10 sarebbe la somma con ieri
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('1,20');
        expect(screen.getByTestId('cr-chiuse-totale')).not.toHaveTextContent('11,10');
    });

    it('l\'etichetta dice «Oggi · N chiuse»', () => {
        monta([oggi, ieri]);
        expect(screen.getByTestId('cr-chiuse-giornata')).toHaveTextContent('Oggi');
        expect(screen.getByTestId('cr-chiuse-giornata')).toHaveTextContent('1');
    });

    it('dichiara quante ne restano fuori e dove guardarle', () => {
        monta([oggi, ieri]);
        const nota = screen.getByTestId('cr-chiuse-fuori-giornata');
        expect(nota).toHaveTextContent('17 settembre 2026');
        expect(nota).toHaveTextContent(/1/);
        expect(nota).toHaveTextContent(/Storico/);
    });

    it('senza posizioni di altri giorni la nota non compare', () => {
        monta([oggi]);
        expect(screen.queryByTestId('cr-chiuse-fuori-giornata')).toBeNull();
    });
});

describe('il pulsante «Storico»', () => {
    const oggi = riga({ id: 1, pnl: 1 });

    it('con uno sport scelto porta allo storico di QUEL sport', () => {
        monta([oggi], 'tennis');
        const zona = screen.getByTestId('cr-chiuse-storico');
        expect(zona).toHaveAttribute('href', '/storico/tennis');
        expect(zona).toHaveTextContent(/Storico tennis/i);
    });

    it('senza sport scelto mostra tutti e due, mai uno a caso', () => {
        monta([oggi], null);
        const coppia = screen.getByTestId('cr-chiuse-storico-coppia');
        expect(within(coppia).getByTestId('cr-chiuse-storico-calcio'))
            .toHaveAttribute('href', '/storico/calcio');
        expect(within(coppia).getByTestId('cr-chiuse-storico-tennis'))
            .toHaveAttribute('href', '/storico/tennis');
    });

    it('ha icona E parola: si riconosce senza impararlo', () => {
        monta([oggi], 'calcio');
        const link = screen.getByTestId('cr-chiuse-storico');
        expect(link.querySelector('svg')).toBeTruthy();       // icona
        expect(link).toHaveTextContent(/Storico/);            // parola
        expect(link.getAttribute('aria-label') ?? '').toMatch(/giorni precedenti/i);
    });
});

describe('vuoto: si dice cosa manca e dove sta il resto', () => {
    it('con solo posizioni di ieri il vuoto rimanda allo Storico', () => {
        monta([riga({
            id: 2, pnl: 1,
            placed_at: '2026-09-16T09:00:00.000Z', settled_at: '2026-09-16T12:00:00.000Z',
        })]);
        expect(screen.getByText(/Le giornate precedenti sono nello Storico/i)).toBeInTheDocument();
    });

    it('senza nessuna posizione chiusa il testo resta quello di sempre', () => {
        monta([]);
        expect(screen.getByText(/Nessuna posizione ancora chiusa oggi/i)).toBeInTheDocument();
    });
});
