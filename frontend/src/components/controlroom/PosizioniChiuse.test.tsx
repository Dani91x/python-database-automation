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

// ============================================================================
// 18/09 — CERTEZZA DI CHIUSURA: ogni riga dice se la posizione e' DAVVERO senza
// esposizione, e la testata lo riassume. FALSIFICAZIONE nel referto
// `frontend/CHECKPOINT_F4_CERTEZZA_CHIUSURA_2026-09-18.md` §5.
// ============================================================================
describe('certezza di chiusura: badge per riga e riepilogo in testa', () => {
    const apertura = riga({ id: 1, pnl: 4.78, side: 'lay', price: 70, size: 2, status: 'won', bet_id: 'B1' });
    const back = (id: number, over: Partial<TradeChiudibile> = {}) => riga({
        id, closes_trade_id: 1, side: 'back', price: 9.6, size: 4.78, status: 'lost', pnl: -4.6, bet_id: `B${id}`, ...over,
    });

    it('posizione regolata: badge VERDE «REGOLATA DAL MERCATO» e riepilogo senza allarme', () => {
        monta([apertura, back(2)]);
        const badge = screen.getByTestId('cr-chiusa-certezza-1');
        expect(badge.dataset.stato).toBe('REGOLATA_DAL_MERCATO');
        expect(badge).toHaveTextContent(/REGOLATA DAL MERCATO/);
        expect(badge.className).toMatch(/emerald/);
        const riepilogo = screen.getByTestId('cr-chiuse-certezza');
        expect(riepilogo).toHaveTextContent(/1 chiusa confermata/);
        expect(riepilogo.dataset.allarme).toBeUndefined();
        expect(riepilogo).not.toHaveAttribute('role', 'alert');
    });

    it('una gamba di chiusura ANNULLATA si dichiara sulla riga, senza aprirla', () => {
        monta([apertura, back(2), back(3, { status: 'cancelled', pnl: null, price: 12, size: 2.08 })]);
        expect(screen.getByTestId('cr-chiusa-copertura-incompleta-1'))
            .toHaveTextContent(/1 gamba di chiusura annullata/);
    });

    it('senza gambe annullate la nota non compare', () => {
        monta([apertura, back(2)]);
        expect(screen.queryByTestId('cr-chiusa-copertura-incompleta-1')).toBeNull();
    });

    it('la riga porta ingresso e chiusura: quota, stake abbinato, ora', () => {
        monta([apertura, back(2), back(3, { size: 7.2 })]);
        const s = screen.getByTestId('cr-chiusa-sintesi-1');
        expect(s).toHaveTextContent('70,00');          // quota d'ingresso
        expect(s).toHaveTextContent('2,00');           // stake d'ingresso
        expect(s).toHaveTextContent('9,60');           // quota media di chiusura
        expect(s).toHaveTextContent('11,98');          // 4,78 + 7,20 abbinati in chiusura
        expect(s).toHaveTextContent('11:00');          // ingresso 09:00Z = 11:00 Europe/Rome
    });

    it('paper e live NON si sommano: il riepilogo conta solo la modalita\' mostrata', () => {
        monta([apertura, back(2), riga({ id: 9, mode: 'paper', event_id: 'E9', event_name: 'Finta', pnl: 1 })]);
        // filtro di default = soldi veri: 1 posizione, non 2
        expect(screen.getByTestId('cr-chiuse-certezza')).toHaveTextContent(/1 chiusa confermata/);
        expect(screen.getByTestId('cr-chiuse-certezza')).not.toHaveTextContent(/2 chiuse/);
    });

    it('esposizione residua: il riepilogo diventa un ALLARME con gli euro', () => {
        // posizione costruita a mano con l'identica forma di `PosizioneChiusa`:
        // l'apertura NON e' regolata e l'unica chiusura e' stata rifiutata.
        const ordineBase = {
            size_requested: null, size_matched: null, size_remaining: null,
            avg_price_matched: null, betfair_updated_at: null, meta: null,
        };
        render(
            <MemoryRouter>
                <PosizioniChiuse sport={null} giorno={OGGI} chiuse={[{
                    id: 50, eventId: 'E50', partita: 'Aperta per davvero', sport: 'calcio',
                    modo: 'live', bot: 'safe', pnlGlobale: 0, esito: 'pari',
                    chiusaAt: '2026-09-17T12:00:00.000Z', piazzataAt: '2026-09-17T09:00:00.000Z',
                    giorno: OGGI,
                    righe: [
                        {
                            id: 50, bot: 'safe', selezione: 'Rossi', lato: 'back', prezzo: 2, size: 10,
                            pnl: null, stato: 'hedged', at: '2026-09-17T09:00:00.000Z', chiusura: false,
                            quale: 'base', betId: 'B50',
                            ordine: {
                                ...ordineBase, status: 'hedged', side: 'back', price: 2, size: 10,
                                size_requested: 10, size_matched: 10, size_remaining: 0, avg_price_matched: 2,
                            },
                        },
                        {
                            id: 51, bot: 'safe', selezione: 'Rossi', lato: 'lay', prezzo: 2, size: 0,
                            pnl: null, stato: 'pending', at: '2026-09-17T10:00:00.000Z', chiusura: true,
                            quale: 'base', betId: null,
                            ordine: {
                                ...ordineBase, status: 'pending', side: 'lay', price: 2, size: 0,
                                size_matched: 0, size_remaining: 0, meta: { error_code: 'INSUFFICIENT_FUNDS' },
                            },
                        },
                    ],
                }]} />
            </MemoryRouter>,
        );
        const badge = screen.getByTestId('cr-chiusa-certezza-50');
        expect(badge.dataset.stato).toBe('CHIUSURA_FALLITA');
        expect(badge.className).toMatch(/red/);
        expect(screen.getByTestId('cr-chiusa-esposta-50')).toHaveTextContent('10,00');
        const riepilogo = screen.getByTestId('cr-chiuse-certezza');
        expect(riepilogo.dataset.allarme).toBe('1');
        expect(riepilogo).toHaveAttribute('role', 'alert');
        expect(riepilogo).toHaveTextContent(/1 con esposizione residua/);
        expect(riepilogo).toHaveTextContent('10,00');
    });
});
