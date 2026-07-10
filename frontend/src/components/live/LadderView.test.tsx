// Test COMPONENTE per LadderView (jsdom + React Testing Library).
// @/lib/live e @/lib/liveOrders sono mockati (nessuna rete/realtime). @/lib/ladderConfig
// e @/lib/ladderMath restano REALI (pura logica), così colonne+PIQ sono calcolate come
// in produzione. Copre: rendering colonne di default, column-picker (toggle+persistenza),
// PIQ come STIMA (~) e non-regressione del one-click place.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));
vi.mock('@/lib/liveOrders', () => ({
    fetchLiveOrders: vi.fn(),
    fetchLivePositions: vi.fn(),
    sendLiveOrderCommand: vi.fn(),
    sendGreenup: vi.fn(),
    requestRiskRule: vi.fn(),
}));

import { LadderView } from './LadderView';
import { fetchLiveLadder } from '@/lib/live';
import {
    fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand, sendGreenup, requestRiskRule,
    type LiveOrderRow, type LivePositionRow,
} from '@/lib/liveOrders';

const mLadder = vi.mocked(fetchLiveLadder);
const mOrders = vi.mocked(fetchLiveOrders);
const mPositions = vi.mocked(fetchLivePositions);
const mSend = vi.mocked(sendLiveOrderCommand);
const mGreen = vi.mocked(sendGreenup);
const mArm = vi.mocked(requestRiskRule);

const LADDER_ROW = {
    event_id: 'evt1',
    market_id: '1.234',
    market_type: 'MATCH_ODDS',
    market_name: 'Match Odds',
    status: 'OPEN',
    ladder: {
        updated_ms: Date.now(),
        selections: [{
            selection_id: 1,
            name: 'Casa',
            ltp: 3.0,
            tv: 100,
            back: [[2.9, 10], [2.88, 5]] as [number, number][],
            lay: [[3.0, 20], [3.05, 8]] as [number, number][],
            trd: [[3.0, 50]] as [number, number][],
            wom: { back_pct: 60, lay_pct: 40 },
        }],
    },
    updated_at: new Date().toISOString(),
};

// un ordine BACK non abbinato a 3.0 (risiede sul lato LAY: coda ≈ layAvail − tuaSize).
function backOrderAt3(): LiveOrderRow {
    return {
        id: 1, bet_id: 'b1', client_order_ref: 'r1', request_id: null, mode: 'paper',
        event_id: 'evt1', market_id: '1.234', selection_id: 1, handicap: 0,
        side: 'back', order_type: 'LIMIT', price: 3.0, size: 5,
        size_matched: 0, size_remaining: 5, size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        average_price_matched: 0, status: 'EXECUTABLE', persistence: 'LAPSE',
        placed_at: null, matched_at: null, updated_at: null,
    };
}

// posizione aperta della selezione 1 (vinco di più se VINCE): P&L per livello attivo.
function openPositionSel1(): LivePositionRow {
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
    mLadder.mockResolvedValue(LADDER_ROW);
    mOrders.mockResolvedValue([]);
    mPositions.mockResolvedValue([]);
    mSend.mockResolvedValue({ ok: true, action: 'place', mode: 'paper', bet_id: 'B9' });
    mGreen.mockResolvedValue({ ok: true, action: 'greenup', mode: 'paper' });
    mArm.mockResolvedValue(1);
});

describe('LadderView', () => {
    it('renderizza il layout di default a 8 colonne (PIQ inclusa)', async () => {
        render(<LadderView marketId="1.234" orderMode="paper" />);
        expect(await screen.findByText('Casa')).toBeInTheDocument();
        // intestazioni delle 8 colonne di default
        for (const h of ['Back', 'Prezzo', 'Lay', 'P&L', 'Trd', 'PIQ']) {
            expect(screen.getByText(h)).toBeInTheDocument();
        }
    });

    it('il column-picker nasconde una colonna e la persiste per-sport', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" sport="calcio" />);
        await screen.findByText('Casa');

        await user.click(screen.getByRole('button', { name: /Configura colonne/ }));
        // nascondi la colonna TRD
        const trdToggle = screen.getByRole('checkbox', { name: /Mostra colonna TRD/ });
        expect(trdToggle).toBeChecked();
        await user.click(trdToggle);

        // header 'Trd' sparisce e la scelta è salvata in localStorage per lo sport
        await waitFor(() => expect(screen.queryByText('Trd')).not.toBeInTheDocument());
        const saved = JSON.parse(localStorage.getItem('ladderProfile:calcio') || '{}');
        const trdCol = saved.columns?.find((c: { key: string }) => c.key === 'trd');
        expect(trdCol?.visible).toBe(false);

        // la colonna quota è FISSA: il suo toggle è disabilitato
        expect(screen.getByRole('checkbox', { name: /Mostra colonna Quota/ })).toBeDisabled();
    });

    it('la colonna PIQ mostra una STIMA (~) quando hai un ordine non abbinato', async () => {
        mOrders.mockResolvedValue([backOrderAt3()]);
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        // coda ≈ layAvail(20) − tuaSize(5) = 15, mostrata come stima "~15"
        expect(await screen.findByText('~15')).toBeInTheDocument();
    });

    it('one-click BACK in PAPER invia il comando place (non-regressione)', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        // clic sulla size disponibile al BACK (2.9 → size 10)
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', mode: 'paper', market_id: '1.234',
            selection_id: 1, side: 'back', price: 2.9,
        }));
        // in modalità Stake il place invia size (non liability)
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({ size: 5 }));
        expect(mSend.mock.calls[0][0]).not.toHaveProperty('liability');
    });

    it('B11: il clic sulla colonna prezzo RICENTRA e non invia alcun ordine', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByTitle(/Ultimo prezzo tradato \(LTP\) · clic = ricentra/));
        expect(mSend).not.toHaveBeenCalled();
        expect(mGreen).not.toHaveBeenCalled();
    });

    it('B13: clic sul P&L di un livello = green-up A QUEL prezzo (greening column)', async () => {
        mPositions.mockResolvedValue([openPositionSel1()]);
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        // il P&L del livello 2.90 diventa cliccabile con posizione aperta
        const cell = await screen.findByTitle(/chiudendo a 2\.90/);
        await user.click(cell);
        await waitFor(() => expect(mGreen).toHaveBeenCalledTimes(1));
        expect(mGreen.mock.calls[0][0]).toEqual(expect.objectContaining({
            marketId: '1.234', selectionId: 1, mode: 'paper',
            fraction: 1, targetPrice: 2.9,
        }));
    });

    it('B14: clic sull\'intestazione dei tuoi ordini annulla TUTTO il lato', async () => {
        mOrders.mockResolvedValue([backOrderAt3()]);
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        const btn = await screen.findByTitle(/Annulla TUTTI i 1 ordini BACK/);
        await user.click(btn);
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'cancel', mode: 'paper', market_id: '1.234', bet_id: 'b1',
        }));
    });

    it('B15: in modalità Liab il LAY invia liability al posto di size', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: 'Liab' }));
        await user.click(screen.getByTitle(/LAY resp\. €5\.00 @ 3\.00/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', side: 'lay', price: 3.0, liability: 5,
        }));
        expect(mSend.mock.calls[0][0]).not.toHaveProperty('size');
        // i BACK non cambiano: sempre size
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(2));
        expect(mSend.mock.calls[1][0]).toEqual(expect.objectContaining({ side: 'back', size: 5 }));
    });

    it('B16: hotkey B piazza un BACK alla riga sotto il cursore', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        // punta la riga 2.90 col mouse, poi premi B
        await user.hover(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await user.keyboard('b');
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', side: 'back', price: 2.9, size: 5,
        }));
    });

    it('B16: le hotkey NON scattano mentre si digita in un input', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.hover(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        // digita 'b' dentro il campo stake custom: nessun ordine deve partire
        await user.type(screen.getByPlaceholderText('€'), 'b');
        expect(mSend).not.toHaveBeenCalled();
    });

    it('B15: il footer mostra il net-stake box con posizione aperta', async () => {
        mPositions.mockResolvedValue([openPositionSel1()]);
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        expect(await screen.findByText('Net')).toBeInTheDocument();
        expect(screen.getByText('Exp')).toBeInTheDocument();
    });


    // ================= SEZIONE C: strumenti armati al piazzamento =================

    it('C20: con Offset armato il place arma la regola offset on_fill sul bet piazzato', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: 'Offset' }));
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm.mock.calls[0][0]).toEqual(expect.objectContaining({
            ruleType: 'offset', entryBetId: 'B9', entrySide: 'back', entrySize: 5,
            params: expect.objectContaining({ offset_ticks: 3, greening: true, timing: 'on_fill' }),
        }));
    });

    it('C26: Offset + Stop (non trailing) = UNA regola bracket OCO', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: 'Offset' }));
        await user.click(screen.getByRole('button', { name: 'Stop' }));
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm.mock.calls[0][0]).toEqual(expect.objectContaining({
            ruleType: 'bracket',
            params: expect.objectContaining({ offset_ticks: 3, trigger_ticks: 5, timing: 'on_fill' }),
        }));
    });

    it('C20: ordine OK ma bet_id assente → avviso esplicito, nessuna regola armata', async () => {
        mSend.mockResolvedValue({ ok: true, action: 'place', mode: 'paper' }); // niente bet_id
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: 'Offset' }));
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mArm).not.toHaveBeenCalled();
        expect(await screen.findByText(/protezioni NON armate/)).toBeInTheDocument();
    });

    it('C22: con FoK armato il place porta params.fok_ttl_sec', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: /FoK/ }));
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            params: { fok_ttl_sec: 5 },
        }));
    });

    it('C24: con Scala 3×1t un click piazza 3 ordini a tick crescenti (back)', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: 'Scala' }));
        await user.click(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(3));
        const prices = mSend.mock.calls.map(c => (c[0] as { price?: number }).price);
        expect(prices).toEqual([2.9, 2.92, 2.94]);
        expect(mArm).not.toHaveBeenCalled(); // la scala non combina le protezioni
    });

    it('C23: con Entry armato il click ARMA uno stop_entry (nessun place)', async () => {
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.click(screen.getByRole('button', { name: /Entry/ }));
        // click su un livello SOPRA l'LTP (3.0) → direzione at_or_above
        await user.click(screen.getByTitle(/LAY €5\.00 @ 3\.05/));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm.mock.calls[0][0]).toEqual(expect.objectContaining({
            ruleType: 'stop_entry', entrySide: 'lay', entrySize: 5,
            params: expect.objectContaining({ trigger_price: 3.05, trigger_direction: 'at_or_above' }),
        }));
        expect(mSend).not.toHaveBeenCalled();
    });

    it('C27: il tasto 1 esegue la macro sulla selezione puntata', async () => {
        localStorage.setItem('servants:v1', JSON.stringify([{
            slot: 1, name: 'join', steps: [{ kind: 'place', side: 'back', price: 'best', stake: 'current' }],
        }]));
        const user = userEvent.setup();
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        await user.hover(screen.getByTitle(/BACK €5\.00 @ 2\.90/));
        await user.keyboard('1');
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            action: 'place', side: 'back', price: 2.9, size: 5, // best back del book mock
        }));
    });
});

// ===========================================================================
// E36 — chip Kelly (position sizing assistito): mai auto, un click = stake
// ===========================================================================
describe('LadderView — chip Kelly (E36)', () => {
    function signalsRow(over: Record<string, unknown> = {}) {
        return {
            event_id: 'evt1',
            signals: {
                signals: [{
                    market_id: '1.234', market_type: 'MATCH_ODDS',
                    selection_id: 1, selection_name: 'Casa',
                    model_prob: 0.55, market_back: 2.9, market_lay: 3.0,
                    fair_back: 1.82, fair_lay: 1.84, edge: 0.06,
                    direction: 'BACK', confidence: 0.8, kelly_stake: 2.44,
                    ...over,
                }],
                updated_ms: null,
            },
            model_meta: null,
            updated_at: new Date().toISOString(),
        };
    }

    it('mostra il chip col suggerimento e UN click imposta lo stake (nessun ordine)', async () => {
        render(<LadderView marketId="1.234" orderMode="paper" signals={signalsRow() as never} />);
        const chip = await screen.findByText('K€2.44');
        await userEvent.click(chip);
        // nessun ordine inviato dal click sul chip
        expect(mSend).not.toHaveBeenCalled();
        // lo stake custom mostra il valore accettato
        expect(screen.getByDisplayValue('2.44')).toBeInTheDocument();
    });

    it('segnale stantio → nessun chip (mai suggerire su dati vecchi)', async () => {
        const stale = { ...signalsRow(), updated_at: new Date(Date.now() - 10 * 60_000).toISOString() };
        render(<LadderView marketId="1.234" orderMode="paper" signals={stale as never} />);
        await screen.findByText('Casa');
        expect(screen.queryByText('K€2.44')).not.toBeInTheDocument();
    });

    it('direction HOLD → nessun chip', async () => {
        render(<LadderView marketId="1.234" orderMode="paper" signals={signalsRow({ direction: 'HOLD' }) as never} />);
        await screen.findByText('Casa');
        expect(screen.queryByText(/K€/)).not.toBeInTheDocument();
    });

    it('senza prop signals → nessun chip (tennis/capability gating)', async () => {
        render(<LadderView marketId="1.234" orderMode="paper" />);
        await screen.findByText('Casa');
        expect(screen.queryByText(/K€/)).not.toBeInTheDocument();
    });
});

// ===========================================================================
// F38 — fair del motore nel ladder: colonna EV + marker fair
// ===========================================================================
import type { LiveSignalsRow } from '@/lib/live';

function signalsRowFair(fair: number, prob: number): LiveSignalsRow {
    return {
        event_id: 'evt1',
        signals: {
            updated_ms: Date.now(),
            commission: 0.05,
            signals: [{
                market_id: '1.234', market_type: 'MATCH_ODDS', selection_id: 1,
                selection_name: 'Casa', model_prob: prob, market_back: 2.9, market_lay: 3.0,
                fair_back: fair, fair_lay: fair, edge: 0.02, direction: 'HOLD',
                confidence: 0.5, kelly_stake: 0,
            }],
        },
        model_meta: null,
        updated_at: new Date().toISOString(),
    };
}

describe('LadderView — F38 fair/EV', () => {
    it('con segnale valido mostra la colonna EV con valori B/L e il marker FAIR', async () => {
        // fair 3.0 (prob 1/3): sotto il fair il LAY ha EV>0, sopra (fuori spread) il BACK.
        render(<LadderView marketId="1.234" orderMode="paper" sport="calcio"
            signals={signalsRowFair(3.0, 1 / 3)} />);
        await screen.findByText('Casa');
        expect(screen.getByText('EV')).toBeInTheDocument();          // header colonna (calcio default)
        const evCells = screen.getAllByText(/^[BL] \+\d+\.\d%$/);    // livelli con valore
        expect(evCells.length).toBeGreaterThan(0);
        // marker fair sulla cella prezzo (tooltip esplicito col valore del fair)
        expect(screen.getByTitle(/FAIR del motore: 3\.00/)).toBeInTheDocument();
    });

    it('segnale STANTIO → nessuna EV e nessun marker (mai un fair vecchio)', async () => {
        const stale = signalsRowFair(3.0, 1 / 3);
        stale.updated_at = new Date(Date.now() - 10 * 60_000).toISOString(); // 10 min fa
        render(<LadderView marketId="1.234" orderMode="paper" sport="calcio" signals={stale} />);
        await screen.findByText('Casa');
        expect(screen.queryByText(/^[BL] \+\d+\.\d%$/)).not.toBeInTheDocument();
        expect(screen.queryByTitle(/FAIR del motore: 3\.00/)).not.toBeInTheDocument();
    });

    it('senza segnali (tennis/nessun motore) la colonna EV non è nel layout di default', async () => {
        render(<LadderView marketId="1.234" orderMode="paper" sport="tennis" />);
        await screen.findByText('Casa');
        expect(screen.queryByText('EV')).not.toBeInTheDocument();
    });
});
