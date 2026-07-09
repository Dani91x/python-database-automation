// Test COMPONENTE leggero per TradeJournal (E37). Moduli data mockati; verifica:
// render con fixture, salvataggio tag → setLiveJournalNote con l'ID GIUSTO,
// feedback esplicito, presenza delle card statistiche pattern.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/liveOrders', () => ({
    fetchLiveJournal: vi.fn(),
    fetchLiveSettled: vi.fn(),
    setLiveJournalNote: vi.fn(),
}));

import TradeJournal from './TradeJournal';
import { fetchLiveJournal, fetchLiveSettled, setLiveJournalNote } from '@/lib/liveOrders';

const mJournal = vi.mocked(fetchLiveJournal);
const mSettled = vi.mocked(fetchLiveSettled);
const mSetNote = vi.mocked(setLiveJournalNote);

// riga journal di OGGI (il filtro solo-oggi è ON di default)
const ROW = {
    id: 42, ts: new Date().toISOString(), mode: 'paper', request_id: null,
    action: 'place', origin: 'manual',
    event_id: 'ev1', market_id: '1.234', market_name: 'Match Odds',
    selection_id: 7, side: 'back', price: 2.0, size: 5, persistence: 'LAPSE',
    bet_id: null, minute: 63, score_home: 1, score_away: 2, inplay: true,
    ltp: 2.0, best_back: 1.99, best_lay: 2.01, book: null, signals: null,
    params: null, tag: null, note: null,
};

beforeEach(() => {
    vi.clearAllMocks();
    mJournal.mockResolvedValue([ROW] as never);
    mSettled.mockResolvedValue([
        { id: 1, mode: 'paper', event_id: 'ev1', market_id: '1.234', market_name: 'Match Odds', profit: 3.5, orders: 1, source: 'simulated', settled_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ] as never);
    mSetNote.mockResolvedValue({ ...ROW, tag: 'scalp' } as never);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <TradeJournal />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

describe('TradeJournal', () => {
    it('renderizza la riga journal con mercato, side, minuto+score e P&L settled', async () => {
        renderPage();
        expect(await screen.findByText('Match Odds')).toBeInTheDocument();
        expect(screen.getByText('BACK')).toBeInTheDocument();
        expect(screen.getByText(/63' 1–2/)).toBeInTheDocument();
        // P&L del mercato dal join settled (+€3.50)
        expect(screen.getByText('+€3.50')).toBeInTheDocument();
        // card statistiche pattern
        expect(screen.getByText('Statistiche per pattern')).toBeInTheDocument();
        expect(screen.getByText('Per tag')).toBeInTheDocument();
        expect(screen.getByText('Per minuto')).toBeInTheDocument();
    });

    it('salvataggio tag chiama setLiveJournalNote con l\'id giusto e mostra feedback ok', async () => {
        const user = userEvent.setup();
        renderPage();
        const tagInput = await screen.findByPlaceholderText('tag');
        await user.type(tagInput, 'scalp');
        await user.click(screen.getByRole('button', { name: 'Salva' }));
        expect(mSetNote).toHaveBeenCalledTimes(1);
        expect(mSetNote).toHaveBeenCalledWith(42, 'scalp', null);
        expect(await screen.findByText('Salvato ✓')).toBeInTheDocument();
    });

    it('errore di salvataggio → feedback ESPLICITO di errore (mai silenzioso)', async () => {
        mSetNote.mockRejectedValueOnce(new Error('permesso negato'));
        const user = userEvent.setup();
        renderPage();
        const tagInput = await screen.findByPlaceholderText('tag');
        await user.type(tagInput, 'x');
        await user.click(screen.getByRole('button', { name: 'Salva' }));
        expect(await screen.findByText(/Errore: permesso negato/)).toBeInTheDocument();
    });
});
