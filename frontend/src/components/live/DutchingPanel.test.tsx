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

import { toast } from 'sonner';
import { DutchingPanel } from './DutchingPanel';
import * as Panel from './DutchingPanel';
import { sendDutch, type LiveOrderResult } from '@/lib/liveOrders';

const mSend = vi.mocked(sendDutch);

// Esito REALE di una richiesta 'dutch' (chiavi di `_result(...)` in live_order_worker.py).
// Con ordini partiti il worker aggiunge `legs` (result["legs"] = placed); con un piano non
// azionabile (es. pesi irrealizzabili) risponde ok=True con `detail` e SENZA `legs`.
const dutchResult = (legs?: Record<string, unknown>[], detail = 'back dutching variabile 2 selezioni') =>
    ({
        ok: true, action: 'dutch', mode: 'paper',
        bet_id: null, status: null, size_matched: null, average_price_matched: null,
        size_remaining: null, market_id: '1.234', selection_id: null, side: 'back',
        price: null, size: null, customer_order_ref: 'awlq1', submin_step: null,
        error: null, detail,
        ...(legs ? { legs } : {}),
    }) as LiveOrderResult;
const LEGS = [
    { selection_id: 1, side: 'back', price: 2.0, size: 5, profit_if_wins: 1 },
    { selection_id: 2, side: 'back', price: 3.0, size: 5, profit_if_wins: 1 },
];

const selections = [
    { selection_id: 1, name: 'A', back: 2.0, lay: 2.1 },
    { selection_id: 2, name: 'B', back: 3.0, lay: 3.2 },
    { selection_id: 3, name: 'C', back: 8.0, lay: 8.4 },
];

beforeEach(() => {
    vi.clearAllMocks();
    mSend.mockResolvedValue(dutchResult(LEGS));
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

// ===========================================================================
// A1 (variable + Lay) / M11 (anteprima variable = server) / V3 (esito senza ordini)
// audit matematica ML, fase 2. I numeri attesi sono LETTERALI copiati dall'ESECUZIONE
// della vera `dutch_variable` (Betfair/stream/trading/dutching.py), vedi il referto.
// ===========================================================================
describe("DutchingPanel - A1: variable non e' disponibile sul lato Lay", () => {
    const modeSelect = () =>
        screen.getAllByRole('combobox').find(s => within(s).queryByRole('option', { name: /Variable/ }))!;
    const variableOption = () => within(modeSelect()).getByRole('option', { name: /Variable/ }) as HTMLOptionElement;

    it('sul lato Back Variable e selezionabile, sul lato Lay no', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        expect(variableOption().disabled).toBe(false);
        await user.selectOptions(screen.getByDisplayValue('Back (dutch)'), 'lay');
        expect(variableOption().disabled).toBe(true);
    });

    it('variable poi Lay: motivo leggibile, Piazza disabilitato, sendDutch mai chiamato', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(modeSelect(), 'variable');
        await user.selectOptions(screen.getByDisplayValue('Back (dutch)'), 'lay');
        expect(screen.getByText(/Variable non disponibile sul lato Lay/)).toBeInTheDocument();
        const place = screen.getByRole('button', { name: /Piazza Bookmaking/ });
        expect(place).toBeDisabled();
        await user.click(place);
        expect(mSend).not.toHaveBeenCalled();
    });

    it('variable sul lato Back resta inviabile e manda dutchMode=variable con i pesi', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.selectOptions(modeSelect(), 'variable');
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0]).toEqual(expect.objectContaining({
            side: 'back', dutchMode: 'variable', totalStake: 10,
        }));
        expect(mSend.mock.calls[0][0].selections.every(l => l.weight === 1)).toBe(true);
    });
});

describe('DutchingPanel - M11: anteprima variable = numeri del server', () => {
    const rowOf = (name: string) => screen.getByText(name, { selector: 'td' }).closest('tr') as HTMLElement;
    const cells = (name: string) => within(rowOf(name)).getAllByRole('cell');
    // colonne in variable: [check, nome, quota, peso, stake, profitto]
    const stakeOf = (name: string) => cells(name)[4].textContent;
    const profitOf = (name: string) => cells(name)[5].textContent;

    async function setup(sels: { selection_id: number; name: string; back: number; lay: number }[],
                         weights: string[], total: string) {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={sels} />);
        for (let i = 2; i < sels.length; i++) await user.click(screen.getAllByRole('checkbox')[i]);
        await user.selectOptions(screen.getAllByRole('combobox').find(
            s => within(s).queryByRole('option', { name: /Variable/ }))!, 'variable');
        const w = screen.getAllByPlaceholderText('1');
        for (let i = 0; i < weights.length; i++) { await user.clear(w[i]); await user.type(w[i], weights[i]); }
        const t = screen.getByPlaceholderText('es. 10');
        await user.clear(t); await user.type(t, total);
        return user;
    }
    const mk = (prices: number[]) =>
        prices.map((p, i) => ({ selection_id: i + 1, name: 'ABCD'[i], back: p, lay: p + 0.1 }));

    it('caso A: quote 2.5/3/4, pesi 1/2/1, T=100 -> stake 40.51/34.18/25.32, profitti 1.26/2.53/1.27', async () => {
        await setup(mk([2.5, 3.0, 4.0]), ['1', '2', '1'], '100');
        expect([stakeOf('A'), stakeOf('B'), stakeOf('C')]).toEqual(['€40.51', '€34.18', '€25.32']);
        expect([profitOf('A'), profitOf('B'), profitOf('C')]).toEqual(['€1.26', '€2.53', '€1.27']);
        expect(screen.getByText('98.33%')).toBeInTheDocument();
        expect(screen.getByText('€100.01')).toBeInTheDocument(); // stake sommati (server: total_stake 100.01)
    });

    it('caso B: quote 2/5, pesi 1/3, T=50 -> stake 31.82/18.18, profitti 13.64/40.90', async () => {
        await setup(mk([2.0, 5.0]), ['1', '3'], '50');
        expect([stakeOf('A'), stakeOf('B')]).toEqual(['€31.82', '€18.18']);
        expect([profitOf('A'), profitOf('B')]).toEqual(['€13.64', '€40.90']);
    });

    it('caso C: quote fuori tick 2.01/3.03 (il server le porta a 2.02/3.05), pesi 1.5/1/2, T=37.5', async () => {
        const user = await setup(mk([2.01, 3.03, 4.5]), ['1.5', '1', '2'], '37.5');
        expect([stakeOf('A'), stakeOf('B'), stakeOf('C')]).toEqual(['€17.73', '€11.93', '€7.84']);
        expect([profitOf('A'), profitOf('B'), profitOf('C')]).toEqual(['−€1.69', '−€1.11', '−€2.22']);
        expect(screen.getByText('104.51%')).toBeInTheDocument(); // book del server (prezzi al tick)
        // al server va il prezzo digitato (lo porta al tick lui): nessuna alterazione di cio' che si invia
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0].selections.map(l => l.price)).toEqual([2.01, 3.03, 4.5]);
        expect(mSend.mock.calls[0][0].selections.map(l => l.weight)).toEqual([1.5, 1, 2]);
        expect(mSend.mock.calls[0][0].totalStake).toBe(37.5);
    });

    it('pesi irrealizzabili (stake negativo): messaggio, nessuno stake mostrato, invio bloccato', async () => {
        await setup(mk([1.5, 1.8, 10.0]), ['1', '1', '6'], '10');
        expect(screen.getByText(/Pesi irrealizzabili/)).toBeInTheDocument();
        expect([stakeOf('A'), stakeOf('B'), stakeOf('C')]).toEqual(['—', '—', '—']);
        expect(screen.getByRole('button', { name: /Piazza Dutch/ })).toBeDisabled();
        expect(mSend).not.toHaveBeenCalled();
    });

    it('book > 100% ma realizzabile: stessi numeri del server (quote 1.5/1.8/3, pesi 1/1/2, T=10)', async () => {
        await setup(mk([1.5, 1.8, 3.0]), ['1', '1', '2'], '10');
        expect([stakeOf('A'), stakeOf('B'), stakeOf('C')]).toEqual(['€4.71', '€3.92', '€1.37']);
        expect([profitOf('A'), profitOf('B'), profitOf('C')]).toEqual(['−€2.94', '−€2.94', '−€5.89']);
    });

    it('4 gambe, pesi decimali, T=123.45 (profitti negativi piccoli)', async () => {
        await setup(mk([2.2, 3.4, 6.2, 11.0]), ['1', '1.25', '0.5', '3'], '123.45');
        expect([stakeOf('A'), stakeOf('B'), stakeOf('C'), stakeOf('D')])
            .toEqual(['€56.07', '€36.28', '€19.90', '€11.20']);
        expect([profitOf('A'), profitOf('B'), profitOf('C'), profitOf('D')])
            .toEqual(['−€0.10', '−€0.10', '−€0.07', '−€0.25']);
    });

    it('il modo equal NON cambia: 2/3 con T=10 -> stake 6.00/4.00 (proporzionali a 1/quota)', () => {
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        // colonne in equal: [check, nome, quota, stake, profitto]
        expect(cells('A')[3].textContent).toBe('€6.00');
        expect(cells('B')[3].textContent).toBe('€4.00');
    });
});

describe('DutchingPanel - funzioni pure di allineamento al server', () => {
    // valori = round() di Python (pari sui pareggi esatti binari) e get_nearest_price di flumine
    it('pyRound2 = round(x, 2) di Python, anche sui pareggi esatti', () => {
        const casi: [number, number][] = [
            [0.125, 0.12], [0.375, 0.38], [0.625, 0.62], [0.875, 0.88], [2.675, 2.67], [1.005, 1.0],
            [1.125, 1.12], [3.375, 3.38], [0.135, 0.14], [1.115, 1.11], [-0.125, -0.12], [-0.375, -0.38],
            [100.125, 100.12], [0.005, 0.01], [0.015, 0.01], [0.045, 0.04], [1.345, 1.34], [2.345, 2.35],
            [2.5, 2.5],
        ];
        for (const [x, atteso] of casi) expect(Panel.pyRound2(x)).toBe(atteso);
    });

    it("nearestTickPrice = get_nearest_price di flumine (mezzo tick verso l'alto)", () => {
        const casi: [number, number][] = [
            [2.01, 2.02], [2.03, 2.04], [2.19, 2.2], [3.02, 3.0], [3.03, 3.05], [3.07, 3.05], [3.025, 3.05],
            [4.05, 4.1], [4.15, 4.2], [6.1, 6.2], [6.3, 6.4], [10.25, 10.5], [10.75, 11.0], [20.5, 21.0],
            [20.4, 20.0], [30.5, 30.0], [50.0, 50.0], [52.5, 55.0], [100.0, 100.0], [105, 110.0],
            [1.005, 1.01], [1.01, 1.01], [1.0, 1.01], [0.5, 1.01], [1000, 1000.0], [1500, 1000],
            [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [6.0, 6.0], [10.0, 10.0], [19.99, 20.0], [1.999, 2.0],
        ];
        for (const [x, atteso] of casi) expect(Panel.nearestTickPrice(x)).toBe(atteso);
    });
});

describe('DutchingPanel - V3: esito ok senza ordini piazzati', () => {
    it('ok=true SENZA legs (piano non azionabile): NON dice "inviato", mostra il motivo', async () => {
        mSend.mockResolvedValue(dutchResult(undefined, 'pesi irrealizzabili con book 132.22%: stake negativo'));
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled());
        expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
        expect(vi.mocked(toast.error).mock.calls[0][0]).toBe('Dutching NON piazzato');
        expect(vi.mocked(toast.error).mock.calls[0][1]).toEqual(expect.objectContaining({
            description: expect.stringContaining('pesi irrealizzabili'),
        }));
    });

    it('ok=true con legs vuoto: stesso trattamento (nessun ordine partito)', async () => {
        mSend.mockResolvedValue(dutchResult([], 'nessuna selezione valida'));
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled());
        expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
    });

    it('ok=true con legs (ordini partiti): "Dutching inviato" come prima', async () => {
        const user = userEvent.setup();
        render(<DutchingPanel marketId="1.234" mode="paper" selections={selections} />);
        await user.click(screen.getByRole('button', { name: /Piazza Dutch/ }));
        await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalled());
        expect(vi.mocked(toast.success).mock.calls[0][0]).toBe('Dutching inviato');
        expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
    });
});
