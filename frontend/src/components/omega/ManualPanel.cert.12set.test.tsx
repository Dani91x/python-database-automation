// ============================================================================
// CERTIFICAZIONE 12/09 — ManualPanel: il pannello che piazza ordini REALI.
//
//   · "Liability aperta ≈ −5,26 €" (dump reale delle 17:00): con la quota
//     vuota (pPrice=0) l'anteprima mostrava un rischio NEGATIVO;
//   · "ESEGUITA" verde anche quando l'ordine è solo ACCODATO (pending_fill) o
//     quando la size è stata tagliata alla liquidità;
//   · nessun blocco su liquidità insufficiente né sul minimo Betfair del BACK
//     (2,00 €: `min_stake` di Omega vale 0,50 e non distingue il lato);
//   · una sola colonna "Liq. lay": in BACK si dimensionava sul lato sbagliato;
//   · cambiando BACK/LAY il prezzo restava quello dell'altro lato.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

const data = vi.hoisted(() => ({ events: [] as unknown[], market: null as unknown, requests: [] as unknown[] }));

vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig<typeof import('@/lib/omega')>()),
    requestManual: vi.fn(async () => 1),
    fetchOmegaEvents: vi.fn(async () => data.events),
    fetchOmegaMarket: vi.fn(async () => data.market),
    fetchManualRequests: vi.fn(async () => data.requests),
}));
vi.mock('@/lib/betfairMedia', () => ({ betfairMediaUrls: () => ({}) }));
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeedRows: () => ({}), useScanLiveFeed: () => ({}), liveScoreLabel: () => null,
}));

import ManualPanel, { manualRequestText, OMEGA_MIN_STAKE, runnerStatusLabel } from './ManualPanel';
import { requestManual } from '@/lib/omega';

const mRequest = vi.mocked(requestManual);

const EVENTO = {
    event_id: 'ev1', name: 'Roma v Lazio',
    open_date: new Date(Date.now() + 30 * 60_000).toISOString(),
    updated_at: new Date().toISOString(),
    markets: [{ market_id: '1.777', market_name: 'Risultato Corretto', market_type: 'CORRECT_SCORE', total_matched: 5000 }],
};

function snapshot() {
    return {
        market_id: '1.777', event_id: 'ev1', event_name: 'Roma v Lazio',
        market_name: 'Risultato Corretto', inplay: true, minute: 55,
        updated_at: new Date(Date.now() - 2000).toISOString(),
        runners: [
            // liquidità ASIMMETRICA fra i due lati: è il punto del test
            { selection_id: 11, name: '1 - 0', status: 'ACTIVE', lay_price: 4.2, lay_size: 200, back_price: 4.0, back_size: 3 },
            { selection_id: 22, name: '3 - 2', status: 'REMOVED', lay_price: 110, lay_size: 8, back_price: 95, back_size: 5 },
        ],
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    data.events = [EVENTO];
    data.market = snapshot();
    data.requests = [];
});

async function setup(user: ReturnType<typeof userEvent.setup>) {
    render(<ManualPanel />);
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Roma v Lazio'));
    const [evSel, mkSel] = screen.getAllByRole('combobox');
    await user.selectOptions(evSel, 'ev1');
    await user.selectOptions(mkSel, '1.777');
    await user.click(screen.getByRole('button', { name: /Carica quote del mercato/i }));
    await waitFor(() => expect(screen.getAllByTestId('manual-runner')).toHaveLength(2), { timeout: 8000 });
}

async function pick(user: ReturnType<typeof userEvent.setup>, nome: string) {
    const riga = screen.getAllByTestId('manual-runner').find((r) => r.textContent?.includes(nome))!;
    await user.click(within(riga).getByRole('button', { name: 'usa' }));
}

describe('manualRequestText — "done" non significa "eseguita"', () => {
    it('ordine solo ACCODATO (pending_fill): IN ATTESA DI ABBINAMENTO, non ESEGUITA', () => {
        const r = manualRequestText({ kind: 'place', status: 'done', result: { ok: true, pending_fill: true } });
        expect(r.status).toBe('IN ATTESA DI ABBINAMENTO');
        expect(r.status).not.toBe('ESEGUITA');
        expect(r.detail).toMatch(/non e' ancora confermato/);
    });

    it('size TAGLIATA alla liquidità: ABBINATA IN PARTE con i due importi', () => {
        const r = manualRequestText({
            kind: 'place', status: 'done',
            result: { ok: true, requested_size: 25, size: 3, reduced: true },
        });
        expect(r.status).toBe('ABBINATA IN PARTE');
        expect(r.detail).toContain('3,00 €');
        expect(r.detail).toContain('25,00 €');
    });

    it('ordine pieno: ESEGUITA', () => {
        const r = manualRequestText({ kind: 'place', status: 'done', result: { ok: true, requested_size: 5, size: 5 } });
        expect(r.status).toBe('ESEGUITA');
    });

    it('un cash out "done" resta ESEGUITA (la regola vale sui piazzamenti)', () => {
        expect(manualRequestText({ kind: 'cashout', status: 'done', result: { ok: true } }).status).toBe('ESEGUITA');
    });
});

describe('ManualPanel — anteprima del rischio mai negativa', () => {
    it('senza quota valida: "—", non un rischio negativo', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pick(user, '1 - 0');
        const quota = screen.getByRole('spinbutton', { name: /quota/i });
        await user.clear(quota);
        expect(screen.getByTestId('manual-preview-liability')).toHaveTextContent('—');
        expect(screen.getByTestId('manual-preview-liability')).not.toHaveTextContent('−');
        expect(screen.getByTestId('manual-preview-stake')).toHaveTextContent('—');
    });
});

describe('ManualPanel — liquidità dei DUE lati e guardie di ingresso', () => {
    it('la tabella mostra la liquidità BACK oltre a quella LAY', async () => {
        const user = userEvent.setup();
        await setup(user);
        const riga = screen.getAllByTestId('manual-runner')[0];
        expect(within(riga).getByTestId('manual-liq-back')).toHaveTextContent('3');
        expect(within(riga).getByTestId('manual-liq-lay')).toHaveTextContent('200');
    });

    it('BACK con liquidità 3 € e stake 10 €: bottone SPENTO col motivo', async () => {
        const user = userEvent.setup();
        await setup(user);
        await user.click(screen.getByRole('button', { name: 'BACK' }));
        await pick(user, '1 - 0');
        await user.click(screen.getByRole('button', { name: /Stake €/i }));
        const importo = screen.getByRole('spinbutton', { name: /stake/i });
        await user.clear(importo);
        await user.type(importo, '10');
        expect(screen.getByTestId('manual-place-block')).toHaveTextContent('abbinabili solo 3,00 €');
        expect(screen.getByRole('button', { name: /Piazza BACK/i })).toBeDisabled();
        expect(mRequest.mock.calls.filter((c) => c[0] === 'place')).toHaveLength(0);
    });

    it('BACK sotto il minimo Betfair (2 €): bottone SPENTO', async () => {
        const user = userEvent.setup();
        await setup(user);
        await user.click(screen.getByRole('button', { name: 'BACK' }));
        await pick(user, '1 - 0');
        await user.click(screen.getByRole('button', { name: /Stake €/i }));
        const importo = screen.getByRole('spinbutton', { name: /stake/i });
        await user.clear(importo);
        await user.type(importo, '1');
        expect(screen.getByTestId('manual-place-block')).toHaveTextContent('minimo Betfair');
        expect(screen.getByRole('button', { name: /Piazza BACK/i })).toBeDisabled();
    });

    it('il minimo dichiarato è per LATO (back 2 €, lay 0,50 €)', () => {
        expect(OMEGA_MIN_STAKE.back).toBe(2);
        expect(OMEGA_MIN_STAKE.lay).toBe(0.5);
    });
});

describe('ManualPanel — la quota segue il LATO scelto', () => {
    it('scegliendo il runner in LAY e poi passando a BACK, la quota diventa quella back', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pick(user, '1 - 0');                       // lay 4.2
        const quota = screen.getByRole('spinbutton', { name: /quota/i }) as HTMLInputElement;
        expect(quota.value).toBe('4.2');
        await user.click(screen.getByRole('button', { name: 'BACK' }));
        expect((screen.getByRole('spinbutton', { name: /quota/i }) as HTMLInputElement).value).toBe('4');
    });
});

describe('ManualPanel — selezione non ATTIVA dichiarata', () => {
    it('un runner RITIRATO porta il suo badge in italiano', async () => {
        const user = userEvent.setup();
        await setup(user);
        const riga = screen.getAllByTestId('manual-runner').find((r) => r.textContent?.includes('3 - 2'))!;
        expect(within(riga).getByTestId('manual-runner-status')).toHaveTextContent('RITIRATA');
    });

    it('le costanti Betfair non arrivano mai in inglese', () => {
        expect(runnerStatusLabel('REMOVED')).toBe('RITIRATA');
        expect(runnerStatusLabel('WINNER')).toBe('VINCENTE');
        expect(runnerStatusLabel('ACTIVE')).toBe('ATTIVA');
        expect(runnerStatusLabel('QUALCOSA_DI_NUOVO')).toBe('NON ATTIVA');
    });
});
