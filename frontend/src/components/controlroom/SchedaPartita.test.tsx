// ============================================================================
// SchedaPartita.test.tsx — Task 2/5 (18/09): il tennis vivo dentro la scheda,
// UNA sottoscrizione solo con posizione aperta, mercato SUSPENDED visibile,
// nessuna barra tennis sul calcio.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SchedaPartita } from './SchedaPartita';
import type { PartitaGiornata, PartitaSoldi } from '@/lib/controlRoom';
import type { TennisLiveNowRow, TennisScoreState } from '@/lib/tennis';

const hoisted = vi.hoisted(() => ({
    row: null as unknown,
    subCalls: 0,
}));

vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisNow: vi.fn(async () => hoisted.row),
    subscribeTennisNow: vi.fn(() => {
        hoisted.subCalls += 1;
        return () => { /* noop */ };
    }),
}));

function score(over: Partial<TennisScoreState> = {}): TennisScoreState {
    return {
        status: 'InPlay', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 },
        points: { p1: '40', p2: '30' }, server: 2, tiebreak: false,
        game_sequence: { p1: [], p2: [] }, service_breaks: { p1: 0, p2: 0 },
        current_set: 2, current_game: 6, set_summary: '6-4 3-2',
        pressure: { break_point: false, set_point: false, game_point: false },
        win_prob_p1: 0.5, source: 'ips', updated_ms: Date.now(), ...over,
    };
}

function tennisRow(over: Partial<TennisLiveNowRow> = {}): TennisLiveNowRow {
    return {
        event_id: 'T1', inplay: true, status: 'OPEN',
        state: { markets: [], order_mode: 'LIVE', updated_ms: Date.now() },
        score: score(), points: [], updated_at: new Date().toISOString(), ...over,
    };
}

const SOLDI_APERTI: PartitaSoldi = {
    live: { netPnl: null, liability: 5, investito: 5, aperta: true },
    paper: { netPnl: null, liability: 0, investito: 0, aperta: false },
    modi: ['live'], bots: ['tennis_scalper'],
};
const SOLDI_CHIUSI: PartitaSoldi = {
    live: { netPnl: 4, liability: 0, investito: 5, aperta: false },
    paper: { netPnl: null, liability: 0, investito: 0, aperta: false },
    modi: ['live'], bots: ['tennis_scalper'],
};

function partita(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'T1', sport: 'tennis', nome: 'Federer R. – Nadal R.', campionato: 'ATP',
        koMs: Date.now() - 3600_000, stato: 'live', minuto: null, punteggio: null,
        controlloDisponibile: false, etaFeedS: null, freschezza: 'ignota',
        latenzaQuoteS: null, freschezzaQuote: 'ignota', statoQuote: 'ignoto',
        media: null, extra: null, marketId: null,
        soldi: SOLDI_APERTI, target: null, avanzamento: null,
        ...over,
    };
}

function monta(p: PartitaGiornata) {
    return render(
        <MemoryRouter>
            <SchedaPartita p={p} operazioni={[]} />
        </MemoryRouter>,
    );
}

beforeEach(() => {
    hoisted.row = null;
    hoisted.subCalls = 0;
});

describe('SchedaPartita — tennis vivo (Task 2)', () => {
    it('tennis CON posizione aperta: mostra punto/server/eta, NON ripete set/game (già in testata)', async () => {
        hoisted.row = tennisRow();
        monta(partita({ soldi: SOLDI_APERTI }));
        await waitFor(() => expect(hoisted.subCalls).toBe(1));
        const bar = await screen.findByTestId('cr-tennis-vivo');
        expect(bar).toHaveTextContent('40');
        expect(bar).toHaveTextContent('30');
        // REPERTO 1: la barra non deve duplicare "1-0"/"3-2" (set/game), già in testata
        expect(bar).not.toHaveTextContent('1-0');
        expect(bar).not.toHaveTextContent('3-2');
        expect(screen.getByTestId('cr-tennis-vivo-server')).toHaveTextContent('P2');
        expect(screen.getByTestId('cr-tennis-vivo-eta')).toBeInTheDocument();
        // 25/09 (voce 5): canale spento nei test -> la riga e' del database, e lo dice
        expect(screen.getByTestId('cr-tennis-vivo-fonte')).toHaveTextContent('db');
    });

    // REPERTO 2 — nome del giocatore quando il feed lo dichiara
    it('col nome dei giocatori nel feed, il servizio mostra il NOME, non "P1/P2"', async () => {
        hoisted.row = tennisRow({ score: score({ server: 1 }) });
        monta(partita({
            soldi: SOLDI_APERTI,
            giocatori: { p1: 'Federer R.', p2: 'Nadal R.' },
        }));
        const riga = await screen.findByTestId('cr-tennis-vivo-server');
        expect(riga).toHaveTextContent('Federer R.');
        expect(riga).not.toHaveTextContent('P1');
    });

    // FALSIFICAZIONE del reperto 2: senza nomi nel feed, resta "P1"/"P2"
    // letterale (mai un nome indovinato)
    it('senza nomi nel feed (o senza correlazione dimostrata), resta "P1"/"P2"', async () => {
        hoisted.row = tennisRow({ score: score({ server: 1 }) });
        monta(partita({ soldi: SOLDI_APERTI, giocatori: null }));
        const riga = await screen.findByTestId('cr-tennis-vivo-server');
        expect(riga).toHaveTextContent('P1');
    });

    // REPERTO 1 — l'evento non e' seguito dal runner tennis: `tennis_live_now`
    // non arrivera' MAI. Testo VERO, breve, grigio (mai arancione: non e' un
    // guasto).
    it('evento NON seguito dal runner tennis: testo vero e grigio, mai arancione/allarmante', async () => {
        hoisted.row = null; // il runner non scrive mai questa riga
        monta(partita({ soldi: SOLDI_APERTI }));
        const msg = await screen.findByTestId('cr-tennis-vivo-punteggio');
        expect(msg).toHaveTextContent('evento non seguito dal runner tennis');
        expect(msg.className).not.toMatch(/orange|amber|red/);
    });

    it('riga presente ma senza punteggio ancora: testo diverso da "non seguito"', async () => {
        hoisted.row = tennisRow({ score: null });
        monta(partita({ soldi: SOLDI_APERTI }));
        const msg = await screen.findByTestId('cr-tennis-vivo-punteggio');
        expect(msg).toHaveTextContent('in attesa del primo aggiornamento');
        expect(msg).not.toHaveTextContent('non seguito');
    });

    it('tennis SENZA nessuna posizione aperta: NESSUNA sottoscrizione, nessuna barra', () => {
        hoisted.row = tennisRow();
        monta(partita({ soldi: SOLDI_CHIUSI }));
        expect(hoisted.subCalls).toBe(0);
        expect(screen.queryByTestId('cr-tennis-vivo')).toBeNull();
    });

    it('mercato SUSPENDED è VISIBILE nella scheda partita, non silenzioso', async () => {
        hoisted.row = tennisRow({ status: 'SUSPENDED' });
        monta(partita({ soldi: SOLDI_APERTI }));
        const badge = await screen.findByTestId('cr-tennis-vivo-mercato');
        expect(badge).toHaveTextContent('SOSPESO');
    });

    it('mercato OPEN: nessun badge di stato (colore solo come segnale)', async () => {
        hoisted.row = tennisRow({ status: 'OPEN' });
        monta(partita({ soldi: SOLDI_APERTI }));
        await screen.findByTestId('cr-tennis-vivo');
        expect(screen.queryByTestId('cr-tennis-vivo-mercato')).toBeNull();
    });

    it('CALCIO: mai la barra tennis-vivo, anche con posizioni aperte', () => {
        hoisted.row = tennisRow();
        monta(partita({ sport: 'calcio', event_id: 'C1', nome: 'Roma – Lazio', soldi: SOLDI_APERTI }));
        expect(hoisted.subCalls).toBe(0);
        expect(screen.queryByTestId('cr-tennis-vivo')).toBeNull();
    });

    it('due card della STESSA partita tennis (es. render multiplo) condividono un solo canale', async () => {
        hoisted.row = tennisRow();
        const p = partita({ soldi: SOLDI_APERTI });
        render(
            <MemoryRouter>
                <SchedaPartita p={p} operazioni={[]} />
                <SchedaPartita p={p} operazioni={[]} scheda="pre" />
            </MemoryRouter>,
        );
        await waitFor(() => expect(hoisted.subCalls).toBe(1));
    });
});

// ============================================================================
// SECONDO GIRO (18/09) — REPERTO 3: parità calcio (stato mercato, volume,
// età del punteggio distinta dall'età delle quote). Finti con le STESSE
// chiavi/tipi del payload vero (`mo_status`/`mo_total_matched` via
// `PartitaGiornata.statoMercato`/`.volumeMercato`, già popolati da
// `costruisciGiornata` — qui si testa solo il montaggio).
// ============================================================================
function partitaCalcio(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'C1', sport: 'calcio', nome: 'Roma – Lazio', campionato: 'Serie A',
        koMs: Date.now() - 3600_000, stato: 'live', minuto: 63, punteggio: '1-0',
        controlloDisponibile: false, etaFeedS: null, freschezza: 'ignota',
        latenzaQuoteS: null, freschezzaQuote: 'ignota', statoQuote: 'ignoto',
        media: null, extra: null, marketId: null,
        soldi: null, target: null, avanzamento: null,
        ...over,
    };
}

describe('SchedaPartita — calcio vivo (REPERTO 3, secondo giro)', () => {
    it('mercato SUSPENDED è visibile in testata, con lo stesso vocabolario del tennis', () => {
        monta(partitaCalcio({ statoMercato: 'SUSPENDED' }));
        const badge = screen.getByTestId('cr-calcio-vivo-mercato');
        expect(badge).toHaveTextContent('SOSPESO');
    });

    it('mercato OPEN: nessun badge (colore solo come segnale)', () => {
        monta(partitaCalcio({ statoMercato: 'OPEN', volumeMercato: null, etaFeedS: null }));
        expect(screen.queryByTestId('cr-calcio-vivo-mercato')).toBeNull();
    });

    it('volume abbinato mostrato in euro (fmtMoney), quando presente', () => {
        monta(partitaCalcio({ volumeMercato: 4250.5 }));
        expect(screen.getByTestId('cr-calcio-vivo-volume')).toHaveTextContent('4250,50');
    });

    it("l'età del PUNTEGGIO e' distinta da quella delle QUOTE (due testid diversi)", () => {
        monta(partitaCalcio({
            etaFeedS: 12, freschezza: 'lenta',
            latenzaQuoteS: 3, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        }));
        expect(screen.getByTestId('cr-calcio-vivo-eta-punteggio')).toHaveTextContent('12 s');
        expect(screen.getByTestId('cr-latenza')).toHaveTextContent('3 s');
    });

    // FALSIFICAZIONE: campi assenti/undefined (riga non ancora mappata da
    // useControlRoom.ts) non deve rompere la scheda ne' mostrare un blocco vuoto
    it('senza mo_status/mo_total_matched (campi opzionali non ancora mappati): nessun blocco, nessun crash', () => {
        const { container } = monta(partitaCalcio({ statoMercato: undefined, volumeMercato: undefined, etaFeedS: null }));
        expect(screen.queryByTestId('cr-calcio-vivo')).toBeNull();
        expect(container).toBeTruthy(); // montata comunque, nessun crash
    });

    it('su tennis non compare mai il blocco "calcio vivo"', () => {
        monta(partita({ soldi: SOLDI_CHIUSI, statoMercato: 'SUSPENDED' } as Partial<PartitaGiornata>));
        expect(screen.queryByTestId('cr-calcio-vivo')).toBeNull();
    });
});
