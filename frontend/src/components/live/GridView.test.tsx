// Test COMPONENTE per GridView (jsdom + React Testing Library) — roadmap D28.
// @/lib/live e @/lib/liveOrders sono MOCKATI (nessuna rete/realtime); @/lib/ladderMath
// resta REALE. Copre le regole MONEY-CRITICAL della griglia one-click:
// render (nomi + 6 celle prezzo per selezione + book%), place diretto in PAPER,
// conferma LIVE + scadenza TTL, fail-safe OFF, stake invalido, mercato SUSPENDED
// e anti-doppio-invio (inFlightRef, non solo disabled).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));
vi.mock('@/lib/liveOrders', () => ({
    fetchLiveOrders: vi.fn(),
    fetchLivePositions: vi.fn(),
    sendLiveOrderCommand: vi.fn(),
    // helper PURI: stessa matematica del modulo reale (mock totale del modulo per
    // non importare il client supabase nel test, come in LadderView.test.tsx).
    layLiabilityFromSize: (size: number, price: number) =>
        Math.round(size * (price - 1) * 100) / 100,
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
}));

import { GridView } from './GridView';
import { fetchLiveLadder } from '@/lib/live';
import {
    fetchLivePositions, sendLiveOrderCommand,
    type LiveOrderResult, type LivePositionRow,
} from '@/lib/liveOrders';

const mLadder = vi.mocked(fetchLiveLadder);
const mPositions = vi.mocked(fetchLivePositions);
const mSend = vi.mocked(sendLiveOrderCommand);

// 2 selezioni con 3 livelli back/lay ciascuna (best first, come live_ladder).
// book% BACK = 100/2.88 + 100/2.56 = 73.78; book% LAY = 100/2.90 + 100/2.60 = 72.94.
const GRID_ROW = {
    event_id: 'evt1',
    market_id: '1.234',
    market_type: 'MATCH_ODDS',
    market_name: 'Match Odds',
    status: 'OPEN',
    ladder: {
        updated_ms: Date.now(),
        selections: [
            {
                selection_id: 1, name: 'Casa', ltp: 2.9, tv: 1000,
                back: [[2.88, 10], [2.86, 5], [2.84, 3]] as [number, number][],
                lay: [[2.9, 20], [2.92, 8], [2.94, 4]] as [number, number][],
                trd: [] as [number, number][],
                wom: { back_pct: 60, lay_pct: 40 },
            },
            {
                selection_id: 2, name: 'Ospite', ltp: 2.6, tv: 800,
                back: [[2.56, 12], [2.54, 6], [2.52, 2]] as [number, number][],
                lay: [[2.6, 15], [2.62, 9], [2.64, 5]] as [number, number][],
                trd: [] as [number, number][],
                wom: { back_pct: 45, lay_pct: 55 },
            },
        ],
    },
    updated_at: new Date().toISOString(),
};

// posizione aperta della selezione 1: +10 se vince, −5 se perde.
function posSel1(): LivePositionRow {
    return {
        id: 1, mode: 'paper', event_id: 'evt1', market_id: '1.234', selection_id: 1, handicap: 0,
        matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
        selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
        net_position: 5, updated_at: null,
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mLadder.mockResolvedValue(GRID_ROW);
    mPositions.mockResolvedValue([]);
    mSend.mockResolvedValue({ ok: true, action: 'place', mode: 'paper', bet_id: 'B9' });
});
afterEach(() => {
    vi.useRealTimers();
});

describe('GridView', () => {
    it('renderizza nomi selezioni, 6 celle prezzo per selezione, P&L e book%', async () => {
        mPositions.mockResolvedValue([posSel1()]);
        render(<GridView marketId="1.234" orderMode="paper" />);
        expect(await screen.findByText('Casa')).toBeInTheDocument();
        expect(screen.getByText('Ospite')).toBeInTheDocument();
        // 6 celle prezzo (3 back + 3 lay) per OGNI selezione
        for (const re of [
            /@ 2\.88/, /@ 2\.86/, /@ 2\.84/, /@ 2\.90/, /@ 2\.92/, /@ 2\.94/, // Casa
            /@ 2\.56/, /@ 2\.54/, /@ 2\.52/, /@ 2\.60/, /@ 2\.62/, /@ 2\.64/, // Ospite
        ]) {
            expect(screen.getByTitle(re)).toBeInTheDocument();
        }
        // P&L posizione: matched_if_win sopra, matched_if_lose sotto; Ospite senza posizione = —
        expect(await screen.findByText('+€10.00')).toBeInTheDocument();
        expect(screen.getByText('−€5.00')).toBeInTheDocument();
        // book% nel footer (2 decimali, MAI parziali)
        expect(screen.getByText(/73\.78%/)).toBeInTheDocument();
        expect(screen.getByText(/72\.94%/)).toBeInTheDocument();
    });

    it('PAPER: click sulla cella best BACK piazza SUBITO un LIMIT a quel prezzo', async () => {
        const user = userEvent.setup();
        render(<GridView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByTitle(/BACK €2\.00 @ 2\.88/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', mode: 'paper', market_id: '1.234', selection_id: 1,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.88, size: 2,
            persistence: 'LAPSE',
        }));
        // esito verde con bet_id
        expect(await screen.findByText(/bet B9/)).toBeInTheDocument();
    });

    it('LIVE non armato: il click NON piazza; "CONFERMA REALE" invia con mode live', async () => {
        const user = userEvent.setup();
        render(<GridView marketId="1.234" orderMode="live" />);
        await screen.findByText('Casa');
        await user.click(screen.getByTitle(/LAY €2\.00 @ 2\.90/));
        // primo click = SOLO conferma, nessun invio
        expect(mSend).not.toHaveBeenCalled();
        // la barra mostra i dettagli, inclusa la liability del LAY: 2×(2.90−1) = €3.80
        expect(screen.getByText(/€3\.80/)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /CONFERMA REALE/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', mode: 'live', side: 'lay', price: 2.9, size: 2,
            order_type: 'LIMIT',
        }));
        // successo → conferma resettata (shouldResetLiveConfirm)
        await waitFor(() =>
            expect(screen.queryByRole('button', { name: /CONFERMA REALE/ })).not.toBeInTheDocument());
    });

    it('LIVE: la conferma SCADE dopo 6s (CONFIRM_TTL_MS) senza inviare nulla', async () => {
        render(<GridView marketId="1.234" orderMode="live" />);
        await screen.findByText('Casa');
        vi.useFakeTimers();
        fireEvent.click(screen.getByTitle(/BACK €2\.00 @ 2\.88/));
        expect(screen.getByRole('button', { name: /CONFERMA REALE/ })).toBeInTheDocument();
        act(() => { vi.advanceTimersByTime(6001); });
        // barra chiusa, avviso di scadenza, send MAI chiamato
        expect(screen.queryByRole('button', { name: /CONFERMA REALE/ })).not.toBeInTheDocument();
        expect(screen.getByText(/scaduta/i)).toBeInTheDocument();
        expect(mSend).not.toHaveBeenCalled();
    });

    it("orderMode 'OFF': griglia in SOLA LETTURA, il click non invia nulla", async () => {
        render(<GridView marketId="1.234" orderMode="OFF" />);
        await screen.findByText('Casa');
        const cell = screen.getByTitle(/BACK @ 2\.88/);
        // in sola lettura le celle NON sono bottoni
        expect(cell.tagName).not.toBe('BUTTON');
        fireEvent.click(cell);
        expect(mSend).not.toHaveBeenCalled();
    });

    it('stake invalido (input svuotato): il click NON invia (guardia money-critical)', async () => {
        const user = userEvent.setup();
        render(<GridView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.clear(screen.getByLabelText('Stake Casa'));
        // fireEvent bypassa il disabled del bottone: deve reggere la guardia interna
        fireEvent.click(screen.getByTitle(/BACK @ 2\.88/));
        expect(mSend).not.toHaveBeenCalled();
    });

    it('mercato SUSPENDED: badge visibile e il click NON invia', async () => {
        mLadder.mockResolvedValue({ ...GRID_ROW, status: 'SUSPENDED' });
        render(<GridView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        expect(screen.getByText('SUSPENDED')).toBeInTheDocument();
        fireEvent.click(screen.getByTitle(/@ 2\.88/));
        expect(mSend).not.toHaveBeenCalled();
    });

    it('anti-doppio-invio: due click rapidi = UN solo send (inFlightRef)', async () => {
        let release!: (v: LiveOrderResult) => void;
        mSend.mockImplementation(() => new Promise<LiveOrderResult>(r => { release = r; }));
        render(<GridView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        const cell = screen.getByTitle(/BACK €2\.00 @ 2\.88/);
        // fireEvent dispatcha anche su bottone disabled: testa la guardia su ref
        fireEvent.click(cell);
        fireEvent.click(cell);
        expect(mSend).toHaveBeenCalledTimes(1);
        await act(async () => { release({ ok: true, action: 'place', mode: 'paper', bet_id: 'B1' }); });
        await waitFor(() => expect(screen.getByText(/bet B1/)).toBeInTheDocument());
    });
});
