// Test COMPONENTE per DutchingPanel (jsdom + React Testing Library).
// @/lib/liveOrders è mockato (nessuna rete); bookPercentage da @/lib/riskMath è REALE,
// così l'anteprima book% è calcolata come in produzione.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/liveOrders', () => ({
    sendDutch: vi.fn(),
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
}));

import { DutchingPanel } from './DutchingPanel';
import { sendDutch } from '@/lib/liveOrders';

const mSend = vi.mocked(sendDutch);

const selections = [
    { selection_id: 1, name: 'A', back: 2.0, lay: 2.1 },
    { selection_id: 2, name: 'B', back: 3.0, lay: 3.2 },
    { selection_id: 3, name: 'C', back: 8.0, lay: 8.4 },
];

beforeEach(() => {
    vi.clearAllMocks();
    mSend.mockResolvedValue({ ok: true, action: 'dutch', mode: 'paper' });
});

describe('DutchingPanel', () => {
    it("l'anteprima book% si aggiorna al variare delle selezioni", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        // preselezionate le prime due: 1/2 + 1/3 = 83.33%
        expect(screen.getByText('83.33%')).toBeInTheDocument();
        const checks = screen.getAllByRole('checkbox');
        await user.click(checks[2]); // attiva C (back 8.0) → 1/2 + 1/3 + 1/8 = 95.83%
        expect(screen.getByText('95.83%')).toBeInTheDocument();
    });

    it('richiede ≥2 selezioni (con una sola il tasto è disabilitato)', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        const place = screen.getByRole('button', { name: /Piazza Dutch/ });
        expect(place).toBeEnabled();
        const checks = screen.getAllByRole('checkbox');
        await user.click(checks[1]); // deseleziona B → resta solo A
        expect(place).toBeDisabled();
    });

    it('in LIVE il piazzamento è bloccato finché non si conferma', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="live" selections={selections} />);
        const place = screen.getByRole('button', { name: /Piazza Dutch/ });
        expect(place).toBeDisabled();
        await user.click(screen.getByRole('checkbox', { name: /Confermo dutching REALE/ }));
        expect(place).toBeEnabled();
    });

    it('sendDutch riceve selections + total_stake (che il server annida in params)', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));

        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        const arg = mSend.mock.calls[0][0];
        expect(arg).toEqual(expect.objectContaining({
            marketId: '1.234',
            mode: 'paper',
            side: 'back',
            dutchMode: 'equal',
            totalStake: 10,
        }));
        expect(arg.selections).toHaveLength(2);
        expect(arg.selections).toEqual(expect.arrayContaining([
            expect.objectContaining({ selection_id: 1, price: 2.0 }),
            expect.objectContaining({ selection_id: 2, price: 3.0 }),
        ]));
    });

    // helper: i <select> non hanno label associata → li trovo per opzione contenuta.
    const selectWithOption = (name: RegExp) =>
        screen.getAllByRole('combobox').find(s => within(s).queryByRole('option', { name }))!;

    it("modalità TARGET invia dutchMode='target' con targetProfit e senza total_stake", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(selectWithOption(/Target/), 'target');
        // compare l'input Profitto obiettivo (default 5), sparisce la Puntata totale.
        expect(screen.getByPlaceholderText('es. 5')).toBeInTheDocument();
        expect(screen.queryByPlaceholderText('es. 10')).not.toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        const arg = mSend.mock.calls[0][0];
        expect(arg).toEqual(expect.objectContaining({
            marketId: '1.234',
            side: 'back',
            dutchMode: 'target',
            targetProfit: 5,
        }));
        expect(arg.totalStake).toBeUndefined();
        expect(arg.selections).toHaveLength(2);
    });

    it("il profitto obiettivo modifica il targetProfit inviato", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(selectWithOption(/Target/), 'target');
        const tp = screen.getByPlaceholderText('es. 5');
        await user.clear(tp);
        await user.type(tp, '12');
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({ targetProfit: 12 }));
    });

    it("pricing di default è 'as_given'", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({ pricing: 'as_given' }));
    });

    it("pricing 'nominated' mostra il prezzo nominato e lo passa a sendDutch", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(selectWithOption(/Nominato/), 'nominated');
        const np = screen.getByPlaceholderText('es. 2.50');
        await user.clear(np);
        await user.type(np, '2.5');

        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            pricing: 'nominated',
            nominatedPrice: 2.5,
        }));
    });

    it("con pricing 'nominated' senza prezzo il piazzamento è bloccato", async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(selectWithOption(/Nominato/), 'nominated');
        expect(screen.getByRole('button', { name: /Piazza Dutch/ })).toBeDisabled();
        expect(mSend).not.toHaveBeenCalled();
    });
});

// ===========================================================================
// FIX audit #14 (freschezza book) e #19 (Lay + Target bloccato client-side)
// ===========================================================================
describe('DutchingPanel — fix audit #14/#19', () => {
    it('#14: snapshot stantio (>10s) → Piazza DISABILITATO con avviso', async () => {
        const stale = new Date(Date.now() - 60_000).toISOString();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} updatedAt={stale} />);
        expect(screen.getByRole('button', { name: /Piazza Dutch/ })).toBeDisabled();
        expect(screen.getByText(/Quote stantie/)).toBeInTheDocument();
        expect(mSend).not.toHaveBeenCalled();
    });

    it('#14: snapshot fresco → Piazza abilitato (nessun avviso)', async () => {
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections}
            updatedAt={new Date().toISOString()} />);
        expect(screen.getByRole('button', { name: /Piazza Dutch/ })).toBeEnabled();
        expect(screen.queryByText(/Quote stantie/)).not.toBeInTheDocument();
    });

    it('#14: senza updatedAt (chiamante legacy) → nessun guardiano, bottone operabile', async () => {
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        expect(screen.getByRole('button', { name: /Piazza Dutch/ })).toBeEnabled();
    });

    it('#19: sul lato Lay la modalità Target è disabilitata e ripiega su Equal', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        // scegli Target sul lato Back, poi passa a Lay: il worker rifiuterebbe SEMPRE →
        // il client ripiega su Equal e l'opzione Target resta disabilitata.
        const modeSel = screen.getByDisplayValue('Equal (profitto pari)');
        await user.selectOptions(modeSel, 'target');
        const sideSel = screen.getByDisplayValue('Back (dutch)');
        await user.selectOptions(sideSel, 'lay');
        expect((screen.getByRole('option', { name: /Target/ }) as HTMLOptionElement).disabled).toBe(true);
        expect(screen.getByDisplayValue('Equal (profitto pari)')).toBeInTheDocument();
    });
});
