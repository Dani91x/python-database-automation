// Test COMPONENTE per XHedgePanel (jsdom + React Testing Library).
// @/lib/liveOrders è mockato: fetchXhedge/sendLiveOrderCommand NON toccano la rete.
// Copre rendering di riepilogo/matrice/suggerimento + F39: piazzamento 1-CLICK della
// copertura CS (guardie: ID esatti, freschezza, matrice completa, conferma LIVE).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { XhedgeRow } from '@/lib/liveOrders';

vi.mock('@/lib/liveOrders', () => ({
    fetchXhedge: vi.fn(),
    sendLiveOrderCommand: vi.fn(),
    fetchRiskRules: vi.fn(),
    requestRiskRule: vi.fn(),
    cancelRiskRule: vi.fn(),
    // one-shot in LIVE (fix audit #20: contratto ONESTO — reset solo su successo;
    // su rifiuto esplicito la spunta resta; su eccezione ambigua il pannello resetta a parte)
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
}));

import { XHedgePanel } from './XHedgePanel';
import {
    cancelRiskRule, fetchRiskRules, fetchXhedge, requestRiskRule, sendLiveOrderCommand,
} from '@/lib/liveOrders';

const mFetch = vi.mocked(fetchXhedge);
const mSend = vi.mocked(sendLiveOrderCommand);
const mRules = vi.mocked(fetchRiskRules);
const mArm = vi.mocked(requestRiskRule);
const mCancelRule = vi.mocked(cancelRiskRule);

function makeRow(overrides: Partial<XhedgeRow> = {}, mode: 'paper' | 'live' = 'paper'): XhedgeRow {
    return {
        event_id: 'evt-1',
        mode,
        updated_at: '2026-07-01T12:00:00Z',
        analysis: {
            n_positions: 3,
            summary: {
                worst: -8.5,
                best: 12.25,
                mean: 1.1,
                worst_scoreline: [2, 1],
                best_scoreline: [0, 0],
                n_scorelines: 9,
            },
            grid: [
                [0, 0, 12.25],
                [1, 0, 3.5],
                [0, 1, -2.0],
                [1, 1, -8.5],
                [2, 1, -8.5],
            ],
            suggestion: {
                actionable: true,
                scoreline: [1, 1],
                side: 'back',
                odds: 7.4,
                size: 5,
                new_worst: -3.2,
                new_best: 9.1,
                note: 'copre il caso peggiore 1-1',
            },
        },
        ...overrides,
    };
}

// F39: riga FRESCA (updated_at = adesso) con gli ID esatti della gamba CS dal worker.
function makeCoverRow(over: { size?: number; ignored?: number } = {}, mode: 'paper' | 'live' = 'paper'): XhedgeRow {
    const row = makeRow({}, mode);
    row.updated_at = new Date().toISOString();
    row.analysis.ignored_orders = over.ignored ?? 0;
    row.analysis.suggestion = {
        ...row.analysis.suggestion!,
        size: over.size ?? 5,
        market_id: '1.99',
        selection_id: 55,
    };
    return row;
}

beforeEach(() => {
    vi.clearAllMocks();
    mFetch.mockResolvedValue([makeRow()]);
    mSend.mockResolvedValue({ ok: true, action: 'place', mode: 'paper', bet_id: 'B1', size_matched: 5 });
    mRules.mockResolvedValue([]);
    mArm.mockResolvedValue(77);
    mCancelRule.mockResolvedValue(null);
});

afterEach(() => {
    cleanup();
});

describe('XHedgePanel', () => {
    it('mostra il riepilogo cross-market (worst/mean/best + scoreline)', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        expect(mFetch).toHaveBeenCalledWith('evt-1');
        // worst appare nel riepilogo E nel suggerimento (worst→new_worst)
        await waitFor(() => expect(screen.getAllByText('−€8.50').length).toBeGreaterThanOrEqual(1));
        expect(screen.getByText('€12.25')).toBeInTheDocument();
        expect(screen.getByText('€1.10')).toBeInTheDocument();
        // scoreline peggiore 2-1 e migliore 0-0
        expect(screen.getByText('2-1')).toBeInTheDocument();
        expect(screen.getByText('0-0')).toBeInTheDocument();
    });

    it('renderizza la matrice P&L con le celle della griglia', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByLabelText(/Matrice P&L/i)).toBeInTheDocument());
        // valore di una cella (0-0 = 12.25)
        expect(screen.getByText('12.25')).toBeInTheDocument();
        expect(screen.getByText('3.50')).toBeInTheDocument();
    });

    it('mostra il suggerimento BACK Correct Score con worst→new_worst e la nota manuale', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText('BACK')).toBeInTheDocument());
        expect(screen.getAllByText(/Correct Score/).length).toBeGreaterThanOrEqual(1);
        // scoreline del suggerimento 1-1 e new_worst
        expect(screen.getByText('1-1')).toBeInTheDocument();
        expect(screen.getByText('−€3.20')).toBeInTheDocument();
        expect(screen.getByText(/Piazza manualmente sul mercato Correct Score/i)).toBeInTheDocument();
    });

    it('senza ID esatti dal worker → NESSUN bottone 1-click, nota manuale', async () => {
        // makeRow() non ha market_id/selection_id (riga pre-deploy)
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        await waitFor(() => expect(screen.getByText('BACK')).toBeInTheDocument());
        expect(screen.queryByRole('button', { name: /Copri \(1-click\)/ })).not.toBeInTheDocument();
        expect(screen.getByText(/piazza manualmente sul mercato Correct Score/i)).toBeInTheDocument();
    });

    it("in modalità 'off' mostra comunque l'analisi in sola lettura", async () => {
        render(<XHedgePanel eventId="evt-1" mode="off" pollMs={0} />);
        await waitFor(() => expect(screen.getAllByText('−€8.50').length).toBeGreaterThanOrEqual(1));
        expect(screen.getByText('OFF')).toBeInTheDocument();
    });

    it('preferisce la riga della modalità attiva (live vs paper)', async () => {
        const paperRow = makeRow({ analysis: { ...makeRow().analysis, summary: { ...makeRow().analysis.summary, worst: -1.0 } } }, 'paper');
        const liveRow = makeRow({ analysis: { ...makeRow().analysis, summary: { ...makeRow().analysis.summary, worst: -99.0 } } }, 'live');
        mFetch.mockResolvedValue([paperRow, liveRow]);
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        await waitFor(() => expect(screen.getAllByText('−€99.00').length).toBeGreaterThanOrEqual(1));
        expect(screen.queryByText('−€1.00')).not.toBeInTheDocument();
    });

    it('gestisce un suggerimento non azionabile', async () => {
        const row = makeRow();
        row.analysis.suggestion = {
            actionable: false, scoreline: null, side: null, odds: null, size: null,
            new_worst: -8.5, new_best: 12.25, note: 'nessuna gamba migliora',
        };
        mFetch.mockResolvedValue([row]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/Nessuna copertura utile/i)).toBeInTheDocument());
        expect(screen.queryByText('BACK')).not.toBeInTheDocument();
    });

    it('mostra un messaggio quando non ci sono righe', async () => {
        mFetch.mockResolvedValue([]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/Nessuna analisi x-hedge disponibile/i)).toBeInTheDocument());
    });

    it('mostra un errore se fetchXhedge rifiuta', async () => {
        mFetch.mockRejectedValue(new Error('boom'));
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
    });
});

// ===========================================================================
// F39 — piazzamento 1-CLICK della copertura CS
// ===========================================================================
describe('XHedgePanel — F39 copertura 1-click', () => {
    it('PAPER: click → place BACK con ID esatti, FoK 10s, persistence LAPSE', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow()]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        expect(btn).toBeEnabled();
        await user.click(btn);
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend).toHaveBeenCalledWith(expect.objectContaining({
            action: 'place', mode: 'paper',
            market_id: '1.99', selection_id: 55, side: 'back',
            price: 7.4, size: 5, persistence: 'LAPSE',
            params: { fok_ttl_sec: 10 },
        }));
    });

    it('size sotto il minimo .it (€2) → flusso place_submin SENZA FoK', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow({ size: 1.5 })]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await user.click(await screen.findByRole('button', { name: /Copri \(1-click\)/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        const cmd = mSend.mock.calls[0][0];
        expect(cmd.action).toBe('place_submin');
        expect(cmd.size).toBe(1.5);
        expect(cmd.params).toBeUndefined();
    });

    it('LIVE: bottone DISABILITATO senza conferma esplicita; conferma one-shot', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow({}, 'live')]);
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        expect(btn).toBeDisabled();                                    // niente click al buio in LIVE
        await user.click(screen.getByRole('checkbox'));
        expect(btn).toBeEnabled();
        await user.click(btn);
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend.mock.calls[0][0].mode).toBe('live');
        // one-shot: dopo il tentativo la conferma è resettata → bottone di nuovo disabilitato
        await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked());
    });

    it('analisi STANTIA → bottone disabilitato (mai coprire su quote vecchie)', async () => {
        const row = makeCoverRow();
        row.updated_at = new Date(Date.now() - 5 * 60_000).toISOString(); // 5 min fa
        mFetch.mockResolvedValue([row]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        expect(btn).toBeDisabled();
        expect(mSend).not.toHaveBeenCalled();
    });

    it('matrice INCOMPLETA (ignored_orders>0) → bottone disabilitato', async () => {
        mFetch.mockResolvedValue([makeCoverRow({ ignored: 2 })]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        expect(btn).toBeDisabled();
        expect(mSend).not.toHaveBeenCalled();
    });

    it('rifiuto del worker → errore esplicito, nessun secondo invio automatico', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow()]);
        mSend.mockResolvedValue({ ok: false, action: 'place', mode: 'paper', error: 'kill switch attivo' } as any);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await user.click(await screen.findByRole('button', { name: /Copri \(1-click\)/ }));
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        expect(mSend).toHaveBeenCalledTimes(1); // mai retry automatico
    });

    it('fix audit #20 — LIVE: rifiuto ESPLICITO (ordine NON piazzato) → la conferma RESTA', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow({}, 'live')]);
        mSend.mockResolvedValue({ ok: false, action: 'place', mode: 'live', error: 'rifiutato' } as any);
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        await user.click(screen.getByRole('checkbox'));
        await user.click(btn);
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        // contratto onesto: nessun ordine a mercato → l'utente può ritentare senza rispuntare.
        expect(screen.getByRole('checkbox')).toBeChecked();
    });

    it('fix audit #20 — LIVE: eccezione AMBIGUA (timeout) → la conferma si resetta', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeCoverRow({}, 'live')]);
        mSend.mockRejectedValue(new Error('timeout: NON reinviare'));
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        const btn = await screen.findByRole('button', { name: /Copri \(1-click\)/ });
        await user.click(screen.getByRole('checkbox'));
        await user.click(btn);
        await waitFor(() => expect(mSend).toHaveBeenCalledTimes(1));
        // la copertura POTREBBE essere stata piazzata: serve una NUOVA spunta esplicita.
        await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked());
    });
});

// ===========================================================================
// F39 — regola AUTO-HEDGE armabile (floor-keeper)
// ===========================================================================
function makeAhRow(mode: 'paper' | 'live' = 'paper'): XhedgeRow {
    const row = makeCoverRow({}, mode);
    row.analysis.cs_market_id = '1.99';
    return row;
}

describe('XHedgePanel — F39 auto-hedge armabile', () => {
    it('arma la regola con floor ed event_id ESATTI (paper: nessuna conferma extra)', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeAhRow()]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        const floorInput = await screen.findByLabelText(/Floor auto-hedge/);
        await user.type(floorInput, '20');
        await user.click(screen.getByRole('button', { name: /Arma auto-hedge/ }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm).toHaveBeenCalledWith(expect.objectContaining({
            mode: 'paper', ruleType: 'auto_hedge',
            marketId: '1.99', selectionId: 0, entrySide: 'back',
            params: expect.objectContaining({ floor: 20, event_id: 'evt-1' }),
        }));
    });

    it('floor invalido → NESSUN arm (errore esplicito)', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeAhRow()]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await screen.findByLabelText(/Floor auto-hedge/);
        await user.click(screen.getByRole('button', { name: /Arma auto-hedge/ }));
        expect(mArm).not.toHaveBeenCalled();
    });

    it('LIVE: arm DISABILITATO senza la conferma esplicita', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeAhRow('live')]);
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        const floorInput = await screen.findByLabelText(/Floor auto-hedge/);
        await user.type(floorInput, '15');
        const armBtn = screen.getByRole('button', { name: /Arma auto-hedge/ });
        expect(armBtn).toBeDisabled();
        // conferma esplicita → abilitato → arm in LIVE
        await user.click(screen.getByRole('checkbox', { name: /DENARO REALE senza ulteriore conferma/ }));
        expect(armBtn).toBeEnabled();
        await user.click(armBtn);
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm.mock.calls[0][0].mode).toBe('live');
    });

    it('regola già armata → stato ATTIVO + Disarma (cancel_live_risk_rule)', async () => {
        const user = userEvent.setup();
        mFetch.mockResolvedValue([makeAhRow()]);
        mRules.mockResolvedValue([{
            id: 42, mode: 'paper', rule_type: 'auto_hedge', market_id: '1.99', selection_id: 0,
            handicap: 0, entry_side: 'back', entry_price: null, entry_size: null,
            params: { floor: 20, event_id: 'evt-1' }, trail_extreme: null, status: 'armed',
            enqueued_request_id: null, result: { hedges_done: 1 }, error: null,
            created_at: null, triggered_at: null,
        } as any]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await screen.findByText(/ATTIVO: worst-case ≥ −€20\.00/);
        expect(screen.getByText(/coperture 1\/3/)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /Disarma/ }));
        await waitFor(() => expect(mCancelRule).toHaveBeenCalledWith(42));
    });

    it('senza cs_market_id in analisi → sezione auto-hedge ASSENTE (mai armare al buio)', async () => {
        mFetch.mockResolvedValue([makeCoverRow()]);  // nessun cs_market_id top-level
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await screen.findByText('BACK');
        expect(screen.queryByRole('button', { name: /Arma auto-hedge/ })).not.toBeInTheDocument();
    });
});
