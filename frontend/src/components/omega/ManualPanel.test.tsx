// ============================================================================
// ManualPanel.test.tsx — certificazione 11/09 del PANNELLO MANUALE di Omega.
//
// Questo pannello piazza ordini REALI su Betfair con un click e non aveva UN
// SOLO test: è il punto più money-critical della sezione. Garanzie certificate:
//
//   1. il payload di `requestManual('place')` è ESATTAMENTE il runner scelto
//      (market_id + selection_id dallo snapshot, mai derivati da indici) e
//      porta `size` XOR `target` secondo la modalità scelta;
//   2. in LIVE si passa SEMPRE dal dialog di conferma (nessun ordine reale con
//      un click solo); in PAPER no;
//   3. quote del book STANTIE (> 20 s) → bottone SPENTO e motivo scritto:
//      un ordine manuale non si piazza su prezzi vecchi;
//   4. LAY e BACK hanno anteprime di rischio DIVERSE (liability vs stake);
//   5. gli esiti delle richieste in coda sono in ITALIANO, compreso uno stato
//      che la UI non conosce (mai la chiave del DB a schermo);
//   6. senza runner o con quota non valida non parte nessuna richiesta.
//
// Data-layer e sonner mockati: nessuna rete.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

const data = vi.hoisted(() => ({
    events: [] as unknown[],
    market: null as unknown,
    requests: [] as unknown[],
}));

vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig<typeof import('@/lib/omega')>()),
    requestManual: vi.fn(async () => 1),
    fetchOmegaEvents: vi.fn(async () => data.events),
    fetchOmegaMarket: vi.fn(async () => data.market),
    fetchManualRequests: vi.fn(async () => data.requests),
}));
vi.mock('@/lib/betfairMedia', () => ({ betfairMediaUrls: () => ({}) }));
// il pannello legge il feed dello scanner per il punteggio LIVE accanto
// all'evento: senza mock il client Supabase VERO apre una WebSocket
// (7 errori `undici` non gestiti a fine suite, e una dipendenza di rete)
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeedRows: () => ({}),
    useScanLiveFeed: () => ({}),
    liveScoreLabel: () => null,
}));

import ManualPanel, { manualRequestText, MANUAL_STATUS_LABEL, MANUAL_BOOK_STALE_S } from './ManualPanel';
import { requestManual, fetchOmegaMarket } from '@/lib/omega';
import { toast } from 'sonner';

const mRequest = vi.mocked(requestManual);
const mMarket = vi.mocked(fetchOmegaMarket);

/**
 * SOLO le richieste di PIAZZAMENTO. `requestManual` e' lo stesso canale per
 * tutto (refresh_events, load_markets, load_book, place, cashout): contare le
 * chiamate grezze conterebbe anche il caricamento delle quote.
 */
function placeCalls(): Record<string, unknown>[] {
    return mRequest.mock.calls
        .filter((c) => c[0] === 'place')
        .map((c) => (c[1] ?? {}) as Record<string, unknown>);
}

const EVENTO = {
    event_id: 'ev1', name: 'Roma v Lazio', open_date: '2026-09-11T18:00:00Z',
    updated_at: '2026-09-11T19:59:00Z',
    markets: [{ market_id: '1.777', market_name: 'Risultato Corretto', market_type: 'CORRECT_SCORE', total_matched: 5000 }],
};

/** snapshot del book: `updated_at` decide la FRESCHEZZA (punto 3) */
function snapshot(ageS = 2) {
    return {
        market_id: '1.777', event_id: 'ev1', event_name: 'Roma v Lazio',
        market_name: 'Risultato Corretto', inplay: true, minute: 55,
        updated_at: new Date(Date.now() - ageS * 1000).toISOString(),
        runners: [
            { selection_id: 11, name: '1 - 0', status: 'ACTIVE', lay_price: 4.2, lay_size: 200, back_price: 4.0, back_size: 150 },
            { selection_id: 22, name: '3 - 2', status: 'ACTIVE', lay_price: 110, lay_size: 8, back_price: 95, back_size: 5 },
            { selection_id: 33, name: '0 - 4', status: 'ACTIVE', lay_price: 300, lay_size: 2, back_price: 250, back_size: 1 },
        ],
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    data.events = [EVENTO];
    data.market = snapshot();
    data.requests = [];
    mMarket.mockImplementation(async () => data.market as never);
});

/**
 * Apre il pannello, sceglie evento + mercato e carica il book.
 *
 * `doLoadBook` accoda la richiesta al servizio e poi POLLA lo specchio DB
 * ogni 1,5 s (fino a 12 volte): il book non compare nello stesso tick, quindi
 * l'attesa deve essere più lunga di un ciclo di poll. I due `select` non hanno
 * un nome accessibile (niente <label>): si prendono per posizione.
 */
async function setup(user: ReturnType<typeof userEvent.setup>) {
    render(<ManualPanel />);
    // l'elenco eventi arriva dall'RPC: il primo select si popola solo dopo
    await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Roma v Lazio'));
    const [evSel, mkSel] = screen.getAllByRole('combobox');
    await user.selectOptions(evSel, 'ev1');
    // i mercati vengono dall'evento scelto: nessun "Carica mercati" necessario
    await user.selectOptions(mkSel, '1.777');
    await user.click(screen.getByRole('button', { name: /Carica quote del mercato/i }));
    await waitFor(
        () => expect(screen.getAllByTestId('manual-runner')).toHaveLength(3),
        { timeout: 8000 },
    );
}

/** clicca "usa" sulla riga del runner col nome dato */
async function pickRunner(user: ReturnType<typeof userEvent.setup>, nome: string) {
    const riga = screen.getAllByTestId('manual-runner')
        .find((r) => r.textContent?.includes(nome));
    expect(riga, `runner non trovato: ${nome}`).toBeTruthy();
    await user.click(within(riga as HTMLElement).getByRole('button', { name: 'usa' }));
}

// ===================================================== 1. payload dell'ordine
describe('ManualPanel — il payload è ESATTAMENTE il runner scelto', () => {
    it('LAY a TARGET: market_id/selection_id/runner_name dallo snapshot, target e size=null', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');

        await user.click(screen.getByRole('button', { name: /Piazza LAY \(paper\)/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        expect(placeCalls()[0]).toMatchObject({
            event_id: 'ev1',
            event_name: 'Roma v Lazio',
            market_id: '1.777',
            selection_id: 22,          // NON l'indice della riga
            runner_name: '3 - 2',
            side: 'lay',
            mode: 'paper',
            price: 110,                // la quota lay dello snapshot
            size: null,                 // modalità TARGET
            target: 5,
        });
    });

    it('modalità STAKE: size valorizzato e target null (mai entrambi)', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '1 - 0');
        await user.click(screen.getByRole('button', { name: 'Stake €' }));

        await user.click(screen.getByRole('button', { name: /Piazza LAY \(paper\)/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        const payload = placeCalls()[0];
        expect(payload.size).toBe(1);
        expect(payload.target).toBeNull();
        expect(payload.selection_id).toBe(11);
    });

    it('BACK usa la quota BACK del runner, non quella lay', async () => {
        const user = userEvent.setup();
        await setup(user);
        await user.click(screen.getByRole('button', { name: 'BACK' }));
        await pickRunner(user, '3 - 2');

        await user.click(screen.getByRole('button', { name: /Piazza BACK \(paper\)/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        const payload = placeCalls()[0];
        expect(payload.side).toBe('back');
        expect(payload.price).toBe(95);
    });

    it('«suggerisci» sceglie il punteggio in fascia [20,120] con la quota più alta', async () => {
        const user = userEvent.setup();
        await setup(user);
        // 300 è FUORI fascia, 4.2 è troppo bassa → vince 110 (3 - 2)
        await user.click(screen.getByRole('button', { name: /suggerisci/i }));
        await user.click(screen.getByRole('button', { name: /Piazza LAY \(paper\)/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        const payload = placeCalls()[0];
        expect(payload.selection_id).toBe(22);
        expect(payload.price).toBe(110);
    });
});

// ===================================================== 2. conferma LIVE
describe('ManualPanel — in LIVE si passa SEMPRE dalla conferma', () => {
    it('LIVE: il click apre il dialog e NON piazza; la conferma piazza', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        await user.click(screen.getByRole('button', { name: 'LIVE' }));

        await user.click(screen.getByRole('button', { name: /Piazza LAY \(SOLDI VERI\)/i }));
        // il dialog c'è e NESSUN ordine è partito
        expect(await screen.findByText(/Ordine LIVE manuale \(soldi veri\)\?/i)).toBeInTheDocument();
        expect(placeCalls()).toEqual([]);

        await user.click(screen.getByRole('button', { name: /Sì, piazza/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        expect(placeCalls()[0].mode).toBe('live');
    });

    it('LIVE: «Annulla» chiude il dialog senza piazzare nulla', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        await user.click(screen.getByRole('button', { name: 'LIVE' }));
        await user.click(screen.getByRole('button', { name: /Piazza LAY \(SOLDI VERI\)/i }));
        await screen.findByText(/Ordine LIVE manuale \(soldi veri\)\?/i);
        await user.click(screen.getByRole('button', { name: 'Annulla' }));
        await waitFor(() => expect(screen.queryByText(/Ordine LIVE manuale \(soldi veri\)\?/i)).toBeNull());
        expect(placeCalls()).toEqual([]);
    });

    it('PAPER: nessun dialog, l’ordine va in coda subito', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        await user.click(screen.getByRole('button', { name: /Piazza LAY \(paper\)/i }));
        await waitFor(() => expect(placeCalls()).toHaveLength(1));
        expect(screen.queryByText(/Ordine LIVE manuale \(soldi veri\)\?/i)).toBeNull();
    });
});

// ===================================================== 3. quote stantie
describe('ManualPanel — mai un ordine su quote vecchie', () => {
    it(`book più vecchio di ${MANUAL_BOOK_STALE_S} s: bottone SPENTO e motivo scritto`, async () => {
        data.market = snapshot(MANUAL_BOOK_STALE_S + 10);
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');

        expect(screen.getByTestId('manual-book-stale')).toHaveTextContent(/ricarica le quote/i);
        const btn = screen.getByRole('button', { name: /Piazza LAY/i });
        expect(btn).toBeDisabled();
        expect(btn.getAttribute('title')).toMatch(/quote non aggiornate/i);
    });

    it('book fresco: nessun avviso e bottone attivo', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        expect(screen.queryByTestId('manual-book-stale')).toBeNull();
        expect(screen.getByRole('button', { name: /Piazza LAY/i })).toBeEnabled();
    });

    it("l'età del book è mostrata accanto alle quote", async () => {
        const user = userEvent.setup();
        await setup(user);
        expect(screen.getByTestId('manual-book-age')).toBeInTheDocument();
    });
});

// ===================================================== 4. anteprima rischio
describe('ManualPanel — anteprima del rischio: LAY ≠ BACK', () => {
    it('LAY dice «Liability aperta» (stake × (quota−1)), BACK dice «Rischio» (= stake)', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        // LAY a target 5 €, commissione indicativa 5 %: stake = 5/0,95 ≈ 5,26
        // liability = 5,26 × 109 ≈ 573,68
        expect(screen.getByText(/Liability aperta/)).toBeInTheDocument();
        expect(screen.getByText('5,26 €')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'BACK' }));
        expect(screen.getByText(/Rischio/)).toBeInTheDocument();
        expect(screen.queryByText(/Liability aperta/)).toBeNull();
    });

    it('i numeri dell’anteprima sono nel formato del design system', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        // virgola decimale e € DOPO il numero, mai "€5.26"
        const riga = screen.getByText(/Liability aperta/).closest('div') as HTMLElement;
        expect(riga.textContent).toMatch(/\d+,\d{2}\s€/);
        expect(riga.textContent).not.toMatch(/€\d/);
    });
});

// ===================================================== 5. esiti in italiano
describe('manualRequestText — gli esiti della coda sono in ITALIANO', () => {
    it('ogni stato noto ha la sua parola', () => {
        expect(MANUAL_STATUS_LABEL.pending).toBe('IN CODA');
        expect(MANUAL_STATUS_LABEL.processing).toBe('IN CORSO');
        expect(MANUAL_STATUS_LABEL.done).toBe('ESEGUITA');
        expect(MANUAL_STATUS_LABEL.error).toBe('FALLITA');
    });

    it('uno stato SCONOSCIUTO si dichiara, non mostra la chiave del DB', () => {
        const r = manualRequestText({ kind: 'place', status: 'weird_new_state', result: null });
        expect(r.status).toBe('STATO SCONOSCIUTO');
        expect(r.status).not.toBe('WEIRD_NEW_STATE');
    });

    it('il motivo del fallimento viene mostrato da error/err/reason', () => {
        expect(manualRequestText({ kind: 'place', status: 'error', result: { error: 'INSUFFICIENT_FUNDS' } }).detail)
            .toBe('INSUFFICIENT_FUNDS');
        expect(manualRequestText({ kind: 'cashout', status: 'error', result: { reason: 'prezzi_non_disponibili' } }).detail)
            .toBe('prezzi_non_disponibili');
        expect(manualRequestText({ kind: 'place', status: 'done', result: null }).detail).toBeNull();
    });

    it('il tipo di richiesta è in italiano (cash out compreso)', () => {
        expect(manualRequestText({ kind: 'cashout', status: 'done', result: null }).kind).toBe('cash out');
        expect(manualRequestText({ kind: 'place', status: 'done', result: null }).kind).toBe('piazza ordine');
        expect(manualRequestText({ kind: 'load_book', status: 'done', result: null }).kind).toBe('carica quote');
    });

    it('le richieste in coda compaiono nel pannello col loro esito', async () => {
        data.requests = [
            { id: 7, kind: 'place', payload: {}, status: 'error', result: { error: 'INVALID_ODDS' }, created_at: new Date().toISOString(), processed_at: null },
        ];
        const user = userEvent.setup();
        render(<ManualPanel />);
        const riga = await screen.findByTestId('manual-request');
        expect(riga).toHaveTextContent('FALLITA');
        expect(within(riga).getByTestId('manual-request-detail')).toHaveTextContent('INVALID_ODDS');
        void user;
    });
});

// ===================================================== 6. guardie d'ingresso
describe('ManualPanel — niente richiesta senza i dati minimi', () => {
    it('senza runner scelto il bottone è spento', async () => {
        const user = userEvent.setup();
        await setup(user);
        expect(screen.getByRole('button', { name: /Piazza LAY/i })).toBeDisabled();
        expect(placeCalls()).toEqual([]);
    });

    it('quota azzerata: errore esplicito e NESSUNA richiesta', async () => {
        const user = userEvent.setup();
        await setup(user);
        await pickRunner(user, '3 - 2');
        const quota = screen.getByRole('spinbutton', { name: /quota/i });
        await user.clear(quota);
        await user.click(screen.getByRole('button', { name: /Piazza LAY/i }));
        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Imposta una quota valida'));
        expect(placeCalls()).toEqual([]);
    });
});
