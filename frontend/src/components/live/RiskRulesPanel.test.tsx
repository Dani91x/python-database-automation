// Test COMPONENTE per RiskRulesPanel (jsdom + React Testing Library).
// Il data layer @/lib/liveOrders è mockato: NESSUNA rete. shouldResetLiveConfirm è
// reimplementato (logica pura, money-critical) così l'arming LIVE si comporta come in prod.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/liveOrders', () => ({
    requestRiskRule: vi.fn(),
    cancelRiskRule: vi.fn(),
    fetchRiskRules: vi.fn(),
    // one-shot LIVE confirm: logica pura, la teniamo reale.
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
}));

import { RiskRulesPanel } from './RiskRulesPanel';
import { requestRiskRule, cancelRiskRule, fetchRiskRules } from '@/lib/liveOrders';

const mReq = vi.mocked(requestRiskRule);
const mCancel = vi.mocked(cancelRiskRule);
const mFetch = vi.mocked(fetchRiskRules);

const selections = [
    { selection_id: 47, name: 'Over 2.5' },
    { selection_id: 48, name: 'Under 2.5' },
];

beforeEach(() => {
    vi.clearAllMocks();
    mFetch.mockResolvedValue([]);
    mReq.mockResolvedValue(42);
    mCancel.mockResolvedValue(null);
});

describe('RiskRulesPanel', () => {
    it('rende il form di arming e il banner di avviso SOFTWARE-SIDE', async () => {
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);
        expect(screen.getByRole('heading', { name: /Automazione Rischio/ })).toBeInTheDocument();
        // warning money-critical sempre visibile
        expect(screen.getByText('SOFTWARE-SIDE')).toBeInTheDocument();
        await waitFor(() => expect(mFetch).toHaveBeenCalledWith('1.234'));
    });

    it("in modalità 'off' i controlli sono disabilitati e l'arming è bloccato", async () => {
        render(<RiskRulesPanel marketId="1.234" mode="off" selections={selections} pollMs={0} />);
        expect(screen.getByText(/arming disabilitato/)).toBeInTheDocument();
        // il fieldset disabled propaga ai controlli (jest-dom toBeDisabled riconosce il fieldset)
        expect(screen.getByPlaceholderText('es. 2.10')).toBeDisabled();
        expect(screen.getByRole('button', { name: /Arma/ })).toBeDisabled();
        await waitFor(() => expect(mFetch).toHaveBeenCalled());
    });

    it("in 'live' l'invio è bloccato finché non si spunta la conferma", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="live" selections={selections} pollMs={0} />);
        const arm = screen.getByRole('button', { name: /Arma/ });
        expect(arm).toBeDisabled();
        await user.click(screen.getByRole('checkbox', { name: /Confermo regola REALE/ }));
        expect(arm).toBeEnabled();
    });

    it('arma chiamando requestRiskRule con rule_type/entry_side/params corretti', async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="live" selections={selections} pollMs={0} />);

        // default: ruleType 'offset', unit 'ticks', entrySide 'back', selezione 47.
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '3' } });
        await user.click(screen.getByRole('checkbox', { name: /Confermo regola REALE/ }));
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        expect(mReq).toHaveBeenCalledWith(expect.objectContaining({
            mode: 'live',
            ruleType: 'offset',
            marketId: '1.234',
            selectionId: 47,
            entrySide: 'back',
            entryPrice: 2.1,
            params: expect.objectContaining({
                offset_ticks: 3, greening: true, persistence: 'LAPSE',
                timing: 'immediate', on_inplay: 'keep',
            }),
        }));
    });

    it("bracket (OCO): arma con entry_bet_id, entry_price e ENTRAMBE le gambe (fix audit #1/#4)", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'bracket');
        // per bracket il campo entry_bet_id compare ed è obbligatorio.
        const betField = screen.getByLabelText(/entry_bet_id/i);
        expect(betField).toBeInTheDocument();
        // help text money-critical.
        expect(screen.getByText(/niente gamba nuda/)).toBeInTheDocument();
        // fix audit #1: la gamba STOP ha il suo campo dedicato (obbligatorio).
        const stopField = screen.getByLabelText('Stop (tick)');
        expect(stopField).toBeInTheDocument();

        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '4' } });
        fireEvent.change(stopField, { target: { value: '5' } });
        fireEvent.change(betField, { target: { value: '3.55667788' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        expect(mReq).toHaveBeenCalledWith(expect.objectContaining({
            ruleType: 'bracket',
            entryBetId: '3.55667788',
            entryPrice: 2.1,   // fix audit #4: SEMPRE richiesto (contratto RPC v4)
            params: expect.objectContaining({
                offset_ticks: 4, trigger_ticks: 5,   // fix audit #1: OCO con ENTRAMBE le gambe
                greening: true, timing: 'immediate', on_inplay: 'keep',
            }),
        }));
    });

    it('bracket SENZA gamba stop: arming bloccato (fix audit #1, mai stop morto)', async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'bracket');
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '4' } });
        fireEvent.change(screen.getByLabelText(/entry_bet_id/i), { target: { value: '3.55667788' } });
        // NESSUN valore nel campo Stop → guard blocca prima della rete.
        await user.click(screen.getByRole('button', { name: /Arma/ }));
        await waitFor(() => expect(mReq).not.toHaveBeenCalled());
    });

    it('bracket senza entry_price: arming bloccato (fix audit #4, contratto RPC v4)', async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'bracket');
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '4' } });
        fireEvent.change(screen.getByLabelText('Stop (tick)'), { target: { value: '5' } });
        fireEvent.change(screen.getByLabelText(/entry_bet_id/i), { target: { value: '3.55667788' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));
        await waitFor(() => expect(mReq).not.toHaveBeenCalled());
    });

    it("bracket senza entry_bet_id: arming bloccato (nessuna chiamata)", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'bracket');
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '4' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        // niente entry_bet_id → guard blocca prima della rete.
        await waitFor(() => expect(mReq).not.toHaveBeenCalled());
    });

    it("timing 'on_fill': mostra il campo entry_bet_id e lo passa a requestRiskRule", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        // di default offset/immediate: nessun campo entry_bet_id.
        expect(screen.queryByLabelText(/entry_bet_id/i)).not.toBeInTheDocument();

        await user.selectOptions(screen.getByLabelText('Attivazione (timing)'), 'on_fill');
        const betField = screen.getByLabelText(/entry_bet_id/i);
        expect(betField).toBeInTheDocument();
        expect(screen.getByText(/attende il fill dell'ingresso/)).toBeInTheDocument();

        // fix audit #4: entry_price è richiesto ANCHE con timing on_fill (contratto RPC).
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '2' } });
        fireEvent.change(betField, { target: { value: '3.99001122' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        expect(mReq).toHaveBeenCalledWith(expect.objectContaining({
            ruleType: 'offset',
            entryBetId: '3.99001122',
            entryPrice: 2.1,
            params: expect.objectContaining({ timing: 'on_fill' }),
        }));
    });

    it("take_profit tick: invia offset_ticks (nome canonico backend, fix audit #2)", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'take_profit');
        await user.selectOptions(screen.getByLabelText('Unità parametro'), 'ticks');
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '7' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        const params = mReq.mock.calls[0][0].params;
        expect(params).toEqual(expect.objectContaining({ offset_ticks: 7 }));
        // MAI più trigger_* per il take_profit (il backend non li valuterebbe come canonici)
        expect(params).not.toHaveProperty('trigger_ticks');
    });

    it('la lista mostra anche regole di ALTRA modalità con badge + tipi non armabili (fix #15/#26)', async () => {
        // pannello in PAPER, regola LIVE auto_hedge armata da XHedge: deve comparire
        // (disarmabile) con etichetta leggibile e badge LIVE — mai "—" né riga nascosta.
        mFetch.mockResolvedValue([{
            id: 9, mode: 'live', rule_type: 'auto_hedge', market_id: '1.234',
            selection_id: 0, handicap: 0, entry_side: 'back', entry_price: null,
            entry_size: null, params: { floor: 20, event_id: 'evt1' }, trail_extreme: null,
            status: 'armed', enqueued_request_id: null, result: null, error: null,
            created_at: null, triggered_at: null,
        }] as never);
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);
        expect(await screen.findByText('Auto-hedge (floor worst-case)')).toBeInTheDocument();
        expect(screen.getByText('LIVE')).toBeInTheDocument();          // badge modalità
        expect(screen.getByText(/floor −€20\.00/)).toBeInTheDocument(); // parametri leggibili
        expect(screen.getByRole('button', { name: /Disarma/ })).toBeInTheDocument();
    });

    it("on_inplay: la policy scelta finisce nei params", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText(/Al calcio d'inizio/), 'rebaseline');
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '3' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        expect(mReq).toHaveBeenCalledWith(expect.objectContaining({
            params: expect.objectContaining({ on_inplay: 'rebaseline' }),
        }));
    });

    it("stop_loss: place_at_ticks ('tick oltre') confluisce nei params", async () => {
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);

        await user.selectOptions(screen.getByLabelText('Tipo regola'), 'stop_loss');
        const placeAt = screen.getByLabelText(/Piazza a/);
        expect(screen.getByText(/per fill sicuro/)).toBeInTheDocument();

        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '5' } });
        fireEvent.change(placeAt, { target: { value: '2' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        expect(mReq).toHaveBeenCalledWith(expect.objectContaining({
            ruleType: 'stop_loss',
            params: expect.objectContaining({ trigger_ticks: 5, place_at_ticks: 2 }),
        }));
    });

    it('LIVE: su errore ambiguo la conferma REALE si RESETTA (niente ri-arming duplicato)', async () => {
        // fix review: requestRiskRule fallisce → confirmLive deve tornare falso, così l'utente
        // deve rispuntare esplicitamente prima di un secondo arming (evita regola LIVE duplicata).
        mReq.mockRejectedValueOnce(new Error('timeout: NON reinviare'));
        const user = userEvent.setup();
        render(<RiskRulesPanel marketId="1.234" mode="live" selections={selections} pollMs={0} />);

        const confirm = screen.getByRole('checkbox', { name: /Confermo regola REALE/ });
        await user.click(confirm);
        expect(confirm).toBeChecked();
        fireEvent.change(screen.getByPlaceholderText('es. 2.10'), { target: { value: '2.1' } });
        fireEvent.change(screen.getByPlaceholderText('es. 3'), { target: { value: '3' } });
        await user.click(screen.getByRole('button', { name: /Arma/ }));

        await waitFor(() => expect(mReq).toHaveBeenCalledTimes(1));
        // la conferma è stata resettata → il bottone Arma torna disabilitato.
        await waitFor(() => expect(confirm).not.toBeChecked());
        expect(screen.getByRole('button', { name: /Arma/ })).toBeDisabled();
    });
});
