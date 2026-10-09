// Board.test.tsx - 09/10/2026: il «Programma del giorno» rifatto (ordine
// dell'utente). Il canale locale e' quello VERO (localChannel.ts + i suoi
// singleton) con un WebSocket finto che parla la busta del server
// (local_channel.py: push {"t","d"}, risposte {"id","ok","d","e"}). I push
// hanno le chiavi ESATTE del contratto
// (AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md §1-§4) e del runner
// (modo_ordini.stato_corrente / stato_tennis + `ts`, hello {sport, mode,
// modo_ordini}). Nessun database: il tabellone non ne legge.
// Allineati ai payload VERI del backend (esempio_payload_calcio/tennis.json del
// ramo backend, 09/10): ordine delle selezioni del Match Odds come Betfair
// (casa, ospite, «The Draw»), nomi dei tipi in italiano, `handicap: 0.0` nelle
// righe di `board_mercato`; in coda un test che monta quei payload tali e quali.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig() as object),
    followMission: vi.fn(async () => undefined),
    setFollowRecord: vi.fn(async () => undefined),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    sendLiveOrderCommand: vi.fn(),
}));
vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    sendTennisOrderCommand: vi.fn(),
    followTennisEvent: vi.fn(async () => undefined),
    setTennisFollowRecord: vi.fn(async () => undefined),
}));

import Board from './Board';
import { __resetLocalChannels } from '@/lib/localChannel';
import { __resetLocalTransport } from '@/lib/localTransport';
import { __resetBoardMemoria } from '@/components/board/useBoardCanale';
import { followMission } from '@/lib/omegaMissions';
import { sendLiveOrderCommand } from '@/lib/liveOrders';
import { sendTennisOrderCommand } from '@/lib/tennis';
import { leggiRitorno, salvaRitorno } from '@/lib/ritorno';

// ---------------------------------------------------------------- WebSocket finto
interface Richiesta { id: number; m: string; p: Record<string, unknown> }

class FintoWs {
    static tutti: FintoWs[] = [];
    url: string;
    inviati: Richiesta[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; FintoWs.tutti.push(this); }
    send(raw: string): void { this.inviati.push(JSON.parse(raw) as Richiesta); }
    close(): void { /* il server non chiude per primo nei test */ }
    apri(): void { this.onopen?.(); }
    cadi(): void { this.onclose?.(); }
    push(t: string, d: unknown): void { this.onmessage?.({ data: JSON.stringify({ t, d }) }); }
    rispondi(id: number, ok: boolean, d?: unknown, e?: string): void {
        this.onmessage?.({ data: JSON.stringify({ id, ok, ...(d !== undefined ? { d } : {}), ...(e ? { e } : {}) }) });
    }
    richieste(m: string): Richiesta[] { return this.inviati.filter((r) => r.m === m); }
}
const PORTA = { calcio: 47331, tennis: 47332 } as const;
const ws = (sport: 'calcio' | 'tennis') =>
    [...FintoWs.tutti].reverse().find((w) => w.url.includes(`:${PORTA[sport]}`))!;

// ------------------------------------------------------------------ dati veri
const ORA = Date.parse('2026-10-09T08:30:00Z');
const TOKEN = 'a'.repeat(64);

// selezione del push `board` (contratto §1: + back_size/lay_size)
const sel = (selection_id: number, name: string, back: number | null, lay: number | null,
    back_size: number | null, lay_size: number | null) =>
    ({ selection_id, name, back, lay, ltp: back, back_size, lay_size });

const INTER = {
    event_id: '34812001', event_name: 'Inter v Torino', open_date: '2026-10-09T07:30:00.000Z',
    market_id: '1.248120010', status: 'OPEN', inplay: true, total_matched: 1843210,
    selections: [
        sel(101, 'Inter', 1.38, 1.39, 1245.7, 310.2),
        sel(103, 'Torino', 11.5, 12, 20, 15),
        sel(58805, 'The Draw', 5.6, 5.7, 88, 41),
    ],
    score: { sport: 'calcio', minute: 63, home: 1, away: 2, red_home: 0, red_away: 1, ht: false },
    fixture_id: 1208891, bet_delay: 5, updated_ms: ORA - 1000,
};
const BOLOGNA = {
    event_id: '34812102', event_name: 'Bologna v Udinese', open_date: '2026-10-09T08:44:00.000Z',
    market_id: '1.248121020', status: 'OPEN', inplay: false, total_matched: 512330,
    selections: [
        sel(201, 'Bologna', 1.83, 1.84, null, 77),
        sel(203, 'Udinese', 4.9, 5, 12, 9),
        sel(58805, 'The Draw', 3.7, 3.75, 40, 40),
    ],
    score: null, fixture_id: null, bet_delay: null, updated_ms: ORA - 1000,
};
const GENOA = {
    event_id: '34812190', event_name: 'Atalanta v Genoa', open_date: '2026-10-09T10:14:00.000Z',
    market_id: '1.248121900', status: 'SUSPENDED', inplay: false, total_matched: null,
    selections: [sel(301, 'Atalanta', 1.52, 1.53, 10, 10), sel(303, 'Genoa', 7, 7.2, 2, 2),
        sel(58805, 'The Draw', 4.6, 4.7, 5, 5)],
    score: null, fixture_id: 1208999, bet_delay: null, updated_ms: ORA - 1000,
};
// contratto §2: MATCH_ODDS primo, correct score gia' esclusi dal backend
const TIPI_CALCIO = [
    { market_type: 'MATCH_ODDS', name: 'Esito finale (1X2)', count: 3 },
    { market_type: 'OVER_UNDER_25', name: 'Under/Over 2.5 gol', count: 2 },
    { market_type: 'BOTH_TEAMS_TO_SCORE', name: 'Goal / No goal', count: 3 },
    { market_type: 'ASIAN_HANDICAP', name: 'Handicap asiatico', count: 1 },
];
const boardCalcio = (rows: unknown[] = [INTER, BOLOGNA, GENOA], market_types: unknown = TIPI_CALCIO) =>
    ({ rows, market_types });

const SINNER = {
    event_id: '34813501', event_name: 'Sinner v Draper', open_date: '2026-10-09T07:50:00.000Z',
    market_id: '1.248135010', status: 'OPEN', inplay: true, total_matched: 2210450,
    selections: [sel(11, 'J. Sinner', 1.24, 1.25, 900, 650), sel(12, 'J. Draper', 5, 5.1, 120, 80)],
    score: { sport: 'tennis', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 }, points: { p1: '30', p2: '15' }, server: 'p2' },
    fixture_id: null, bet_delay: 3, updated_ms: ORA - 1000,
};
const MUSETTI = {
    event_id: '34813540', event_name: 'Musetti v Fritz', open_date: '2026-10-09T09:00:00.000Z',
    market_id: '1.248135400', status: 'OPEN', inplay: true, total_matched: 341800,
    selections: [sel(21, 'L. Musetti', 2.36, 2.4, 50, 60), sel(22, 'T. Fritz', 1.7, 1.72, 70, 80)],
    // un punteggio del CALCIO sul canale del tennis: si scarta (mai mischiati)
    score: { sport: 'calcio', minute: 10, home: 0, away: 0, red_home: null, red_away: null, ht: false },
    fixture_id: null, bet_delay: null, updated_ms: ORA - 1000,
};
const boardTennis = () => ({
    rows: [SINNER, MUSETTI],
    market_types: [{ market_type: 'MATCH_ODDS', name: 'Vincente incontro', count: 2 },
        { market_type: 'SET_BETTING', name: 'Risultato in set', count: 1 }],
});

// modo_ordini.stato_corrente() + ts (calcio, live_order_worker._pubblica_modo_ordini_se_cambiato)
const modoCalcio = (effettivo: 'OFF' | 'PAPER' | 'LIVE', ts = ORA - 5_000, kill_switch = false) => ({
    effettivo, tetto_ambiente: 'LIVE', scelto_ui: effettivo, motivo: 'ok',
    scelto_ui_at: '2026-10-09T08:00:00+00:00', scelto_ui_da: 'avvio_app', eta_lettura_s: 0.4,
    kill_switch, kill_switch_env: false, kill_switch_letto: true, ts,
});
// modo_ordini.stato_tennis() + ts (guardie_tennis.pubblica_modo_ordini_se_cambiato)
const modoTennis = (effettivo: 'OFF' | 'PAPER' | 'LIVE', ts = ORA - 5_000) => ({
    effettivo, tetto_ambiente: 'PAPER', scelto_ui: null, motivo: 'ok', sport: 'tennis',
    scelto_ui_at: null, scelto_ui_da: null, eta_lettura_s: 0.7, ts,
});

// --------------------------------------------------------------- montaggio
function Dove() {
    const l = useLocation();
    return <div data-testid="dove">{l.pathname + l.search}</div>;
}

async function scorri(ms = 0) {
    await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

async function monta() {
    render(
        <HelmetProvider>
            <MemoryRouter initialEntries={['/board']}>
                <Routes>
                    <Route path="/board" element={<Board />} />
                    <Route path="*" element={<Dove />} />
                </Routes>
            </MemoryRouter>
        </HelmetProvider>,
    );
    await scorri();
}

/** collega il canale dello sport, manda hello e tabellone */
async function collega(sport: 'calcio' | 'tennis', hello: Record<string, unknown>, board: unknown) {
    const w = ws(sport);
    act(() => { w.apri(); w.push('hello', hello); w.push('board', board); });
    await scorri();
    return w;
}

async function apriTennis() {
    fireEvent.click(screen.getByRole('button', { name: /Tennis/ }));
    await scorri();
}

const righe = () => screen.getAllByTestId('board-riga');
const riga = (eventId: string) => righe().find((r) => r.getAttribute('data-event-id') === eventId)!;

beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(ORA);
    FintoWs.tutti = [];
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = FintoWs;
    (globalThis as unknown as { alphascoreCanale?: unknown }).alphascoreCanale = { token: TOKEN };
    __resetLocalChannels();
    __resetLocalTransport();
    __resetBoardMemoria();
    sessionStorage.clear();
    vi.mocked(followMission).mockClear();
    vi.mocked(sendLiveOrderCommand).mockReset();
    vi.mocked(sendTennisOrderCommand).mockReset();
    Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
    __resetLocalChannels();
    __resetLocalTransport();
    __resetBoardMemoria();
    delete (globalThis as unknown as { alphascoreCanale?: unknown }).alphascoreCanale;
    vi.useRealTimers();
});

// =========================================================================
describe('Programma del giorno: canale', () => {
    it('canale spento: la scheda lo dice (mai un programma vuoto)', async () => {
        await monta();
        expect(screen.getByText(/Canale locale calcio non attivo/)).toBeTruthy();
        expect(screen.queryAllByTestId('board-riga')).toHaveLength(0);
    });

    it('caduta del canale: tabellone e modo ordini non valgono piu\'', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        expect(righe()).toHaveLength(3);
        expect(screen.getByTestId('board-modo').textContent).toBe('PAPER · SIMULATO');
        act(() => w.cadi());
        await scorri();
        expect(screen.getByText(/Canale locale calcio non attivo/)).toBeTruthy();
        // il canale si riconnette (backoff 1 s) SENZA modo ordini nell'hello: non noto
        await scorri(1_100);
        const w2 = ws('calcio');
        expect(w2).not.toBe(w);
        act(() => { w2.apri(); w2.push('hello', { sport: 'calcio', mode: 'LIVE' }); w2.push('board', boardCalcio()); });
        await scorri();
        expect(screen.getByTestId('board-modo').textContent).toBe('ORDINI: NON NOTA');
    });
});

describe('cambio di scheda sport', () => {
    it('il tabellone e il modo arrivati mentre si guardava l\'altra scheda non si perdono', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        // il tennis si collega e manda tutto MENTRE la scheda aperta e' il calcio
        const wt = ws('tennis');
        act(() => {
            wt.apri();
            wt.push('hello', { sport: 'tennis', mode: 'PAPER' });
            wt.push('board', boardTennis());
            // il modo ordini arriva SOLO al cambio: dopo, piu' niente
            wt.push('modo_ordini', modoTennis('PAPER', ORA - 2_000));
        });
        await scorri();
        await apriTennis();
        expect(righe()).toHaveLength(2);
        expect(screen.getByTestId('board-modo').textContent).toBe('PAPER · SIMULATO');
        // e si torna al calcio: idem
        fireEvent.click(screen.getByRole('button', { name: /Calcio/ }));
        await scorri();
        expect(righe()).toHaveLength(3);
        expect(screen.getByTestId('board-modo').textContent).toBe('PAPER · SIMULATO');
    });
});

describe('punteggio e minuto delle partite in gioco', () => {
    it('calcio: minuto, gol e rossi solo se ci sono; prima del via niente punteggio', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        const inter = within(riga('34812001'));
        expect(inter.getByTestId('board-minuto').textContent).toBe("63'");
        expect(inter.getByTestId('board-gol').textContent).toBe('1–2');
        // un solo rosso (ospiti): la casa con 0 non mostra niente
        const rossi = inter.getAllByTestId('board-rossi');
        expect(rossi).toHaveLength(1);
        expect(rossi[0].getAttribute('title')).toBe('espulsi ospiti: 1');
        // pre-match: niente punteggio, il conto alla rovescia all'off
        const bologna = within(riga('34812102'));
        expect(bologna.queryByTestId('board-punteggio')).toBeNull();
        expect(bologna.getByText(/OFF in 14:00/)).toBeTruthy();
    });

    it('calcio: intervallo = INT; in gioco senza punteggio = trattino, mai 0-0', async () => {
        await monta();
        const ht = { ...INTER, score: { ...INTER.score, minute: 45, ht: true } };
        const senza = { ...BOLOGNA, inplay: true, score: null };
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio([ht, senza]));
        expect(within(riga('34812001')).getByTestId('board-minuto').textContent).toBe('INT');
        expect(within(riga('34812102')).getByTestId('board-punteggio').textContent).toBe('—');
    });

    it('tennis: set, game, punti e chi batte; un punteggio di un altro sport si scarta', async () => {
        await monta();
        await apriTennis();
        await collega('tennis', { sport: 'tennis', mode: 'PAPER', modo_ordini: modoTennis('PAPER') }, boardTennis());
        const sinner = within(riga('34813501'));
        expect(sinner.getByTestId('board-set-game').textContent).toBe('Set 1–0 · Game 3–2 · 30–15');
        expect(sinner.getByTestId('board-batte').textContent).toBe('● batte Draper');
        // il punteggio "calcio" arrivato sul canale tennis si SCARTA: nessuna
        // vista punteggio (ne' tennis ne' calcio), solo il trattino del dato assente
        const musetti = within(riga('34813540'));
        expect(musetti.getByTestId('board-punteggio').textContent).toBe('—');
        expect(musetti.queryByTestId('board-set-game')).toBeNull();
        expect(musetti.queryByTestId('board-gol')).toBeNull();
    });
});

describe('liquidita\' del mercato', () => {
    it('abbinato in evidenza, barra relativa al piu\' scambiato, importo disponibile sotto ogni quota', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        const inter = within(riga('34812001'));
        expect(inter.getByTestId('board-abbinati').textContent).toBe('1.843.210 €');
        expect(inter.getByTestId('board-barra-liquidita').getAttribute('aria-valuenow')).toBe('100');
        const bologna = within(riga('34812102'));
        expect(bologna.getByTestId('board-abbinati').textContent).toBe('512.330 €');
        expect(bologna.getByTestId('board-barra-liquidita').getAttribute('aria-valuenow')).toBe('28');
        // sotto le quote di Inter: disponibile back 1.246 €, lay 310 €
        const sInter = inter.getAllByTestId('board-selezione')[0];
        expect(within(sInter).getByTestId('board-disp-back').textContent).toBe('1.246 €');
        expect(within(sInter).getByTestId('board-disp-lay').textContent).toBe('310 €');
        // assente = trattino, MAI 0
        const sBologna = bologna.getAllByTestId('board-selezione')[0];
        expect(within(sBologna).getByTestId('board-disp-back').textContent).toBe('—');
        const genoa = within(riga('34812190'));
        expect(genoa.getByTestId('board-abbinati').textContent).toBe('—');
        expect(genoa.queryByTestId('board-barra-liquidita')).toBeNull();
        expect(genoa.getByText('liquidità non nota')).toBeTruthy();
    });

    it('le quote e la liquidita\' si aggiornano a ogni push', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        const nuovo = { ...INTER, total_matched: 1900000, selections: [sel(101, 'Inter', 1.4, 1.41, 999, 111), ...INTER.selections.slice(1)] };
        act(() => w.push('board', boardCalcio([nuovo, BOLOGNA, GENOA])));
        await scorri();
        const inter = within(riga('34812001'));
        expect(inter.getByTestId('board-abbinati').textContent).toBe('1.900.000 €');
        expect(inter.getAllByTestId('board-quota-back')[0].textContent).toBe('1,40999 €');
    });
});

describe('menu\' del mercato', () => {
    it('calcio: Match Odds primo, nessun correct score anche se il backend lo mandasse', async () => {
        await monta();
        const tipi = [...TIPI_CALCIO,
            { market_type: 'CORRECT_SCORE', name: 'Risultato esatto', count: 3 },
            { market_type: 'CORRECT_SCORE2_A', name: 'Risultato esatto 2', count: 3 },
            { market_type: 'HALF_TIME_SCORE', name: 'Risultato esatto primo tempo', count: 3 }];
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio(undefined, tipi));
        const menu = screen.getByTestId('board-mercato') as HTMLSelectElement;
        const valori = [...menu.querySelectorAll('option')].map((o) => o.value);
        expect(valori[0]).toBe('MATCH_ODDS');
        expect(valori).toContain('OVER_UNDER_25');
        expect(valori.some((v) => v.includes('CORRECT_SCORE') || v.includes('HALF_TIME_SCORE'))).toBe(false);
        // raggruppate con le categorie di lib/market-categories
        expect([...menu.querySelectorAll('optgroup')].map((g) => g.label)).toEqual(['Match Odds', 'Over/Under', 'BTTS', 'Squadre/Altri']);
    });

    it('MATCH_ODDS non si chiede; un altro tipo si chiede, si rinnova ogni 30 s, e le righe arrivano dal push', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        await scorri(31_000);
        expect(w.richieste('board_mercato')).toHaveLength(0);

        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'OVER_UNDER_25' } });
        await scorri();
        expect(w.richieste('board_mercato')).toHaveLength(1);
        expect(w.richieste('board_mercato')[0].p).toEqual({ market_type: 'OVER_UNDER_25' });
        act(() => w.rispondi(w.richieste('board_mercato')[0].id, true, {}));
        expect(screen.getByTestId('board-mercato-attesa')).toBeTruthy();

        // push di un ALTRO tipo: si ignora
        act(() => w.push('board_mercato', { market_type: 'BOTH_TEAMS_TO_SCORE', rows: [], updated_ms: ORA }));
        await scorri();
        expect(screen.getByTestId('board-mercato-attesa')).toBeTruthy();

        const ou = (event_id: string, market_id: string, total_matched: number | null) => ({
            event_id, market_id, market_name: 'Over/Under 2.5 Goals', status: 'OPEN', inplay: event_id === '34812001',
            total_matched,
            selections: [
                { selection_id: 47972, name: 'Under 2.5 Goals', handicap: 0.0, back: 2.8, lay: 2.86, ltp: 2.8, back_size: 55, lay_size: 21 },
                { selection_id: 47973, name: 'Over 2.5 Goals', handicap: 0.0, back: 1.54, lay: 1.56, ltp: 1.55, back_size: 140, lay_size: 66 },
            ],
        });
        act(() => w.push('board_mercato', {
            market_type: 'OVER_UNDER_25',
            rows: [ou('34812001', '1.248120013', 99000), ou('34812102', '1.248121023', 33000)],
            updated_ms: ORA,
        }));
        await scorri();
        expect(righe()).toHaveLength(2);
        const inter = within(riga('34812001'));
        // orario, evento e punteggio restano del board
        expect(inter.getByText('Inter v Torino')).toBeTruthy();
        expect(inter.getByTestId('board-gol').textContent).toBe('1–2');
        expect(inter.getByTestId('board-linea').getAttribute('data-market-id')).toBe('1.248120013');
        expect(inter.getByText('Under 2.5 Goals')).toBeTruthy();
        expect(inter.getByTestId('board-abbinati').textContent).toBe('99.000 €');
        expect(screen.getByTestId('board-note-mercato').textContent).toContain('1 eventi del programma non hanno questo mercato');

        // rinnovo a 30 s finche' la scelta resta
        await scorri(30_000);
        expect(w.richieste('board_mercato')).toHaveLength(2);
        await scorri(30_000);
        expect(w.richieste('board_mercato')).toHaveLength(3);

        // si torna a Match Odds: niente piu' richieste
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'MATCH_ODDS' } });
        await scorri(61_000);
        expect(w.richieste('board_mercato')).toHaveLength(3);
        expect(righe()).toHaveLength(3);
        // «nessuna connessione nuova»: solo i due canali singleton dei runner
        expect(FintoWs.tutti.map((x) => x.url.replace(/\?.*$/, '')).sort())
            .toEqual(['ws://127.0.0.1:47331/', 'ws://127.0.0.1:47332/']);
    });

    it('richiesta rifiutata dal runner: il motivo in chiaro', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'ASIAN_HANDICAP' } });
        await scorri();
        act(() => w.rispondi(w.richieste('board_mercato')[0].id, false, undefined, 'tipo di mercato sconosciuto'));
        await scorri();
        expect(screen.getByTestId('board-mercato-errore').textContent).toContain('tipo di mercato sconosciuto');
    });

    it('la scelta resta per la scheda (ritorno da Statistiche/Trading)', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'OVER_UNDER_25' } });
        await scorri();
        expect(sessionStorage.getItem('board.mercato.calcio')).toBe('OVER_UNDER_25');
        expect(w.richieste('board_mercato')).toHaveLength(1);
    });
});

describe('box quote: piazzano davvero, con la modalita\' del runner', () => {
    async function apriBox(sport: 'calcio' | 'tennis', eventId: string, lato: 'back' | 'lay', indice = 0) {
        const s = within(riga(eventId)).getAllByTestId('board-selezione')[indice];
        fireEvent.click(within(s).getByTestId(`board-quota-${lato}`));
        await scorri();
        void sport;
        return screen.getByRole('dialog');
    }

    function scriviImporto(box: HTMLElement, v: string) {
        fireEvent.change(within(box).getByLabelText('Importo (€)'), { target: { value: v } });
    }

    it('clic su BACK: box con lato, selezione e quota; conferma -> place con i campi giusti e il modo del runner', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        const box = await apriBox('calcio', '34812001', 'back');
        expect(box.getAttribute('aria-label')).toBe('Conferma ordine BACK Inter');
        expect(within(box).getByText('SIMULATO')).toBeTruthy();
        expect((within(box).getByTestId('box-ordine-quota') as HTMLInputElement).value).toBe('1.38');
        const conferma = within(box).getByRole('button', { name: /Conferma/ });
        expect(conferma).toBeDisabled();   // importo vuoto: nessuno stake inventato
        scriviImporto(box, '10');
        expect(conferma).not.toBeDisabled();
        fireEvent.click(conferma);
        await scorri();
        const ordini = w.richieste('order');
        expect(ordini).toHaveLength(1);
        const { client_ref, ...cmd } = ordini[0].p;
        expect(typeof client_ref).toBe('string');
        expect(cmd).toEqual({
            action: 'place', mode: 'paper', market_id: '1.248120010', selection_id: 101, handicap: 0,
            side: 'back', order_type: 'LIMIT', price: 1.38, persistence: 'LAPSE', size: 10,
        });
        expect(sendLiveOrderCommand).not.toHaveBeenCalled();
        // durante l'attesa (aggancio al volo fino a ~7 s) lo stato lo dice
        expect(screen.getByTestId('board-esito').textContent).toContain('Invio in corso (aggancio della partita');
        expect(screen.queryByTestId('board-ripiego-db')).toBeNull();
        act(() => w.rispondi(ordini[0].id, true, {
            ok: true, action: 'place', mode: 'paper', bet_id: 'P-123', status: 'EXECUTABLE', size_matched: 0,
        }));
        await scorri();
        expect(screen.getByTestId('board-esito').textContent).toContain('BACK Inter @ 1.38');
        expect(screen.getByTestId('board-esito').textContent).toContain('bet P-123');
    });

    it('LIVE dal runner: il box dice REALE e il comando parte in live', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('LIVE') }, boardCalcio());
        const box = await apriBox('calcio', '34812102', 'lay', 1);
        expect(within(box).getByText('REALE')).toBeTruthy();
        scriviImporto(box, '4');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma REALE/ }));
        await scorri();
        expect(w.richieste('order')[0].p).toMatchObject({ mode: 'live', side: 'lay', selection_id: 203, price: 5, size: 4 });
    });

    it('modalita\' NON nota (solo il tetto nell\'hello): conferma spenta con la ragione, nessun ordine', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        expect(screen.getByTestId('board-modo').textContent).toBe('ORDINI: NON NOTA');
        const box = await apriBox('calcio', '34812001', 'back');
        expect(within(box).getByText('NON NOTA')).toBeTruthy();
        scriviImporto(box, '10');
        expect(within(box).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        expect(within(box).getByTestId('box-ordine-bloccato').textContent).toContain('Modalità ordini del runner non nota');
        fireEvent.keyDown(within(box).getByLabelText('Importo (€)'), { key: 'Enter' });
        await scorri();
        expect(w.richieste('order')).toHaveLength(0);
    });

    it('OFF dal runner: conferma spenta; il freno tirato idem', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('OFF') }, boardCalcio());
        let box = await apriBox('calcio', '34812001', 'back');
        scriviImporto(box, '10');
        expect(within(box).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        expect(within(box).getByTestId('box-ordine-bloccato').textContent).toContain('modalità OFF');
        fireEvent.click(within(box).getByRole('button', { name: /Annulla/ }));
        await scorri();
        act(() => w.push('modo_ordini', modoCalcio('PAPER', ORA - 1_000, true)));
        await scorri();
        box = await apriBox('calcio', '34812001', 'back');
        scriviImporto(box, '10');
        expect(within(box).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        expect(within(box).getByTestId('box-ordine-bloccato').textContent).toContain('Freno');
        expect(w.richieste('order')).toHaveLength(0);
    });

    it('il modo dal `now` (calcio) vale solo se fresco e piu\' recente', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        act(() => w.push('now', { event_id: '34812001', state: { order_mode: 'PAPER', updated_ms: ORA - 1_000 } }));
        await scorri();
        expect(screen.getByTestId('board-modo').textContent).toBe('PAPER · SIMULATO');
        await scorri(20_000);   // oltre i 15 s: il `now` non vale piu'
        expect(screen.getByTestId('board-modo').textContent).toBe('ORDINI: NON NOTA');
    });

    it('il modo cambia col box aperto: conferma spenta finche\' non si riapre', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        const box = await apriBox('calcio', '34812001', 'back');
        scriviImporto(box, '10');
        act(() => w.push('modo_ordini', modoCalcio('LIVE', ORA - 1_000)));
        await scorri();
        const b2 = screen.getByRole('dialog');
        expect(within(b2).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        expect(within(b2).getByTestId('box-ordine-bloccato').textContent).toContain('cambiata mentre il box era aperto');
        expect(w.richieste('order')).toHaveLength(0);
    });

    it('rifiuto del backend (tetto mercati pieno) mostrato in chiaro', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        const box = await apriBox('calcio', '34812001', 'lay');
        scriviImporto(box, '5');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        const o = w.richieste('order')[0];
        act(() => w.rispondi(o.id, true, {
            ok: false, action: 'place', mode: 'paper',
            error: 'market non sottoscritto: aggancio non possibile, tetto mercati pieno (25/25)',
        }));
        await scorri();
        expect(screen.getByTestId('board-esito').textContent).toContain('tetto mercati pieno (25/25)');
    });

    it('anti-doppio-invio: col primo ordine in volo il secondo box non conferma', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        let box = await apriBox('calcio', '34812001', 'back');
        scriviImporto(box, '10');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        box = await apriBox('calcio', '34812102', 'back');
        scriviImporto(box, '10');
        expect(within(box).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        expect(within(box).getByTestId('box-ordine-bloccato').textContent).toContain('già in invio');
        expect(w.richieste('order')).toHaveLength(1);
    });

    it('quota modificabile: fuori scala = spenta col motivo; un tick su = valida e usata nel comando', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        const box = await apriBox('calcio', '34812102', 'back', 1);   // Udinese 4.9
        scriviImporto(box, '2');
        const quota = within(box).getByTestId('box-ordine-quota');
        fireEvent.change(quota, { target: { value: '4,95' } });
        expect(within(box).getByTestId('box-ordine-quota-errore').textContent).toContain('scala Betfair');
        expect(within(box).getByRole('button', { name: /Conferma/ })).toBeDisabled();
        fireEvent.change(quota, { target: { value: '1001' } });
        expect(within(box).getByTestId('box-ordine-quota-errore').textContent).toContain('1,01 - 1000');
        fireEvent.change(quota, { target: { value: '4.9' } });
        fireEvent.click(within(box).getByRole('button', { name: 'Quota un tick più alta' }));
        expect((quota as HTMLInputElement).value).toBe('5.00');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        expect(w.richieste('order')[0].p).toMatchObject({ price: 5, selection_id: 203, size: 2 });
    });

    it('linea con handicap (board_mercato): l\'handicap della selezione nel comando', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, boardCalcio());
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'ASIAN_HANDICAP' } });
        await scorri();
        act(() => w.push('board_mercato', {
            market_type: 'ASIAN_HANDICAP', updated_ms: ORA,
            rows: [{
                event_id: '34812001', market_id: '1.248120099', market_name: 'Asian Handicap', status: 'OPEN',
                inplay: true, total_matched: 5000,
                selections: [
                    { selection_id: 101, name: 'Inter', handicap: -1.5, back: 2.1, lay: 2.14, ltp: 2.1, back_size: 30, lay_size: 12 },
                    { selection_id: 103, name: 'Torino', handicap: 1.5, back: 1.88, lay: 1.92, ltp: 1.9, back_size: 25, lay_size: 18 },
                ],
            }],
        }));
        await scorri();
        const box = await apriBox('calcio', '34812001', 'lay', 1);
        scriviImporto(box, '3');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        expect(w.richieste('order')[0].p).toMatchObject({
            market_id: '1.248120099', selection_id: 103, handicap: 1.5, side: 'lay', price: 1.92, size: 3,
        });
    });

    it('fuori dall\'app (senza token): stesso comando sulla coda DB del suo sport', async () => {
        delete (globalThis as unknown as { alphascoreCanale?: unknown }).alphascoreCanale;
        vi.mocked(sendTennisOrderCommand).mockResolvedValue({ ok: true, action: 'place', mode: 'paper', bet_id: 'T-1' });
        await monta();
        await apriTennis();
        const w = await collega('tennis', { sport: 'tennis', mode: 'PAPER', modo_ordini: modoTennis('PAPER') }, boardTennis());
        // il ripiego DB non aggancia le partite non seguite: la pagina lo dice
        expect(screen.getByTestId('board-ripiego-db')).toBeTruthy();
        const box = await apriBox('tennis', '34813501', 'back', 1);
        scriviImporto(box, '6');
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        expect(w.richieste('order')).toHaveLength(0);
        expect(sendLiveOrderCommand).not.toHaveBeenCalled();
        expect(sendTennisOrderCommand).toHaveBeenCalledWith({
            action: 'place', mode: 'paper', market_id: '1.248135010', selection_id: 12, handicap: 0,
            side: 'back', order_type: 'LIMIT', price: 5, persistence: 'LAPSE', size: 6,
        });
    });
});

describe('Statistiche e Trading, con ritorno al punto esatto', () => {
    it('calcio Statistiche: dashboard della partita con from=board, punto salvato (scheda e partita)', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        // senza fixture_id: spento con la ragione
        const bologna = within(riga('34812102')).getByTestId('cr-statistiche');
        expect(bologna).toBeDisabled();
        expect(bologna.getAttribute('title')).toContain('non agganciata');
        fireEvent.click(within(riga('34812001')).getByTestId('cr-statistiche'));
        await scorri();
        expect(screen.getByTestId('dove').textContent).toBe('/dashboard?fixture=1208891&from=board');
        expect(leggiRitorno()).toMatchObject({ rotta: '/board', nome: 'Programma', scheda: 'calcio', eventId: '34812001' });
    });

    it('calcio Trading: prima il seguito, poi Segui live con from=board', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, boardCalcio());
        fireEvent.click(within(riga('34812001')).getByTestId('cr-trading'));
        await scorri();
        expect(followMission).toHaveBeenCalledWith('34812001', 'Inter', 'Torino', '2026-10-09T07:30:00.000Z');
        expect(screen.getByTestId('dove').textContent).toBe('/segui-live?event=34812001&from=board');
    });

    it('tennis Statistiche e Trading: il Tennis Terminal sulla partita, scheda tennis', async () => {
        await monta();
        await apriTennis();
        await collega('tennis', { sport: 'tennis', mode: 'PAPER' }, boardTennis());
        fireEvent.click(within(riga('34813501')).getByTestId('cr-statistiche'));
        await scorri();
        const atteso = '/tennis/terminal?event=34813501&market=1.248135010&name=Match+Odds&from=board&p1=Sinner&p2=Draper';
        expect(screen.getByTestId('dove').textContent).toBe(atteso);
        expect(leggiRitorno()).toMatchObject({ rotta: '/board', scheda: 'tennis', eventId: '34813501' });
    });

    it('il ritorno riapre la scheda giusta e riporta la partita in vista', async () => {
        salvaRitorno({ rotta: '/board', nome: 'Programma', scheda: 'tennis', eventId: '34813540', scorrimento: 0 });
        await monta();
        expect(screen.getByRole('button', { name: /Tennis/ }).getAttribute('aria-pressed')).toBe('true');
        await collega('tennis', { sport: 'tennis', mode: 'PAPER' }, boardTennis());
        await scorri(100);
        expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
        expect(riga('34813540').className).toContain('ring-2');
        expect(leggiRitorno()).toBeNull();
    });
});

// I payload VERI generati dal codice del backend (ramo worktree-agent-abb4efd85c1b43214,
// AUDIT_2026-10-09/programma_del_giorno/esempio_payload_{calcio,tennis}.json), copiati
// tali e quali: la pagina li deve leggere senza adattamenti.
const VERO_CALCIO = {
    board: {
        rows: [
            {
                event_id: '35000001', event_name: 'Casa v Ospite', open_date: '2026-10-09T18:00:00+00:00',
                market_id: '1.101', status: 'OPEN', inplay: true, total_matched: 15234.5,
                selections: [
                    { selection_id: 11, name: 'Casa', back: 1.5, lay: 1.52, ltp: 1.5, back_size: 100.0, lay_size: 50.0 },
                    { selection_id: 22, name: 'Ospite', back: 7.0, lay: 7.4, ltp: 7.0, back_size: 9.0, lay_size: 3.0 },
                    { selection_id: 58805, name: 'The Draw', back: 4.0, lay: 4.2, ltp: 4.0, back_size: 20.0, lay_size: 10.0 },
                ],
                bet_delay: 5,
                score: { sport: 'calcio', minute: 67, home: 2, away: 1, red_home: 0, red_away: 1, ht: false },
                fixture_id: 1234567, updated_ms: 1791545942143,
            },
            {
                event_id: '35000002', event_name: 'Nord v Sud', open_date: '2026-10-09T18:00:00+00:00',
                market_id: '1.102', status: 'OPEN', inplay: false, total_matched: 288.8,
                selections: [
                    { selection_id: 33, name: 'Nord', back: 3.05, lay: 3.2, ltp: 3.05, back_size: 96.59, lay_size: 15.0 },
                    { selection_id: 44, name: 'Sud', back: 2.46, lay: 2.56, ltp: 2.46, back_size: 5.0, lay_size: 17.0 },
                    { selection_id: 58805, name: 'The Draw', back: 3.4, lay: 3.6, ltp: 3.4, back_size: 56.76, lay_size: 3.0 },
                ],
                bet_delay: 0, score: null, fixture_id: null, updated_ms: 1791545942143,
            },
        ],
        market_types: [
            { market_type: 'MATCH_ODDS', name: 'Esito finale (1X2)', count: 2 },
            { market_type: 'BOTH_TEAMS_TO_SCORE', name: 'Goal / No goal', count: 5 },
            { market_type: 'OVER_UNDER_25', name: 'Under/Over 2.5 gol', count: 2 },
            { market_type: 'ASIAN_HANDICAP', name: 'Handicap asiatico', count: 1 },
        ],
    },
    board_mercato: {
        market_type: 'OVER_UNDER_25',
        rows: [
            {
                event_id: '35000001', market_id: '1.201', market_name: 'Over/Under 2.5 Goals', status: 'OPEN',
                inplay: true, total_matched: 5000.0,
                selections: [
                    { selection_id: 47972, name: 'Under 2.5 Goals', handicap: 0.0, back: 1.91, lay: 1.93, ltp: null, back_size: 250.0, lay_size: 120.0 },
                    { selection_id: 47973, name: 'Over 2.5 Goals', handicap: 0.0, back: 2.08, lay: 2.12, ltp: null, back_size: 80.0, lay_size: 60.0 },
                ],
            },
            {
                event_id: '35000002', market_id: '1.202', market_name: 'Over/Under 2.5 Goals', status: 'OPEN',
                inplay: false, total_matched: 77.0,
                selections: [
                    { selection_id: 47972, name: 'Under 2.5 Goals', handicap: 0.0, back: 2.2, lay: 2.3, ltp: 2.2, back_size: 30.0, lay_size: 12.0 },
                    { selection_id: 47973, name: 'Over 2.5 Goals', handicap: 0.0, back: 1.7, lay: 1.8, ltp: 1.7, back_size: 8.0, lay_size: 4.0 },
                ],
            },
        ],
        updated_ms: 1791545942144,
    },
};
const VERO_TENNIS = {
    board: {
        rows: [{
            event_id: '35790084', event_name: 'Barrios Vera v Simakin', open_date: '2026-10-09T18:00:00+00:00',
            market_id: '1.401', status: 'OPEN', inplay: true, total_matched: 43210.0,
            selections: [
                { selection_id: 9633138, name: 'Barrios Vera', back: 1.8, lay: 1.82, ltp: 1.81, back_size: 300.0, lay_size: 90.0 },
                { selection_id: 35635727, name: 'Simakin', back: 2.2, lay: 2.24, ltp: 2.22, back_size: 70.0, lay_size: 40.0 },
            ],
            bet_delay: 3,
            score: { sport: 'tennis', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 }, points: { p1: '40', p2: 'AD' }, server: 'p2' },
            fixture_id: null, updated_ms: 1791545942151,
        }],
        market_types: [
            { market_type: 'MATCH_ODDS', name: 'Vincente incontro', count: 1 },
            { market_type: 'SET_BETTING', name: 'Risultato in set', count: 1 },
        ],
    },
    board_mercato: {
        market_type: 'SET_BETTING',
        rows: [{
            event_id: '35790084', market_id: '1.402', market_name: 'Set Betting', status: 'OPEN', inplay: true, total_matched: 900.0,
            selections: [
                { selection_id: 1, name: '2 - 0', handicap: 0.0, back: 3.1, lay: 3.3, ltp: 3.1, back_size: 12.0, lay_size: 4.0 },
                { selection_id: 2, name: '2 - 1', handicap: 0.0, back: 4.5, lay: 4.9, ltp: 4.5, back_size: 6.0, lay_size: 2.0 },
            ],
        }],
        updated_ms: 1791545942152,
    },
};

describe('payload VERI del backend (09/10)', () => {
    it('calcio: board e board_mercato tali e quali', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE', modo_ordini: modoCalcio('PAPER') }, VERO_CALCIO.board);
        const casa = within(riga('35000001'));
        expect(casa.getByTestId('board-minuto').textContent).toBe("67'");
        expect(casa.getByTestId('board-gol').textContent).toBe('2\u20131');
        expect(casa.getByTestId('board-abbinati').textContent).toBe('15.235 €');
        expect(casa.getAllByTestId('board-selezione').map((x) => x.getAttribute('title'))).toEqual(['Casa', 'Ospite', 'The Draw']);
        const menu = screen.getByTestId('board-mercato') as HTMLSelectElement;
        expect([...menu.querySelectorAll('option')].map((o) => o.textContent))
            .toEqual(['Esito finale (1X2) (2)', 'Under/Over 2.5 gol (2)', 'Goal / No goal (5)', 'Handicap asiatico (1)']);
        fireEvent.change(menu, { target: { value: 'OVER_UNDER_25' } });
        await scorri();
        act(() => w.rispondi(w.richieste('board_mercato')[0].id, true, {}));
        act(() => w.push('board_mercato', VERO_CALCIO.board_mercato));
        await scorri();
        expect(righe()).toHaveLength(2);
        expect(within(riga('35000002')).getByTestId('board-abbinati').textContent).toBe('77 €');
        const box = (() => {
            fireEvent.click(within(within(riga('35000001')).getAllByTestId('board-selezione')[1]).getByTestId('board-quota-lay'));
            return screen.getByRole('dialog');
        })();
        fireEvent.change(within(box).getByLabelText('Importo (€)'), { target: { value: '2' } });
        fireEvent.click(within(box).getByRole('button', { name: /Conferma/ }));
        await scorri();
        expect(w.richieste('order')[0].p).toMatchObject({
            action: 'place', mode: 'paper', market_id: '1.201', selection_id: 47973, handicap: 0,
            side: 'lay', order_type: 'LIMIT', price: 2.12, persistence: 'LAPSE', size: 2,
        });
        // rifiuto VERO del motore (aggancio al volo fallito): per intero
        act(() => w.rispondi(w.richieste('order')[0].id, true, {
            ok: false, action: 'place', mode: 'paper',
            error: 'in_aggancio: mercato 1.201 non sottoscritto entro 7000 ms - ordine NON piazzato (aggancio chiesto al runner: riprova fra qualche secondo)',
        }));
        await scorri();
        expect(screen.getByTestId('board-esito').textContent)
            .toContain('in_aggancio: mercato 1.201 non sottoscritto entro 7000 ms - ordine NON piazzato (aggancio chiesto al runner: riprova fra qualche secondo)');
    });

    it('calcio: market_types ASSENTE = tipi non ancora letti, menu\' col solo Match Odds e nota', async () => {
        await monta();
        await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, { rows: VERO_CALCIO.board.rows });
        const menu = screen.getByTestId('board-mercato') as HTMLSelectElement;
        expect([...menu.querySelectorAll('option')].map((o) => o.value)).toEqual(['MATCH_ODDS']);
        expect(screen.getByTestId('board-tipi-assenti').textContent).toContain('non ancora letti');
    });

    it('calcio: rifiuto leggibile della richiesta (tetto dei tipi) in chiaro, rinnovo solo ogni 30 s', async () => {
        await monta();
        const w = await collega('calcio', { sport: 'calcio', mode: 'LIVE' }, VERO_CALCIO.board);
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'ASIAN_HANDICAP' } });
        await scorri();
        act(() => w.rispondi(w.richieste('board_mercato')[0].id, false, undefined,
            'tetto di 3 tipi di mercato contemporanei raggiunto: riprova fra poco'));
        await scorri(1_000);
        expect(screen.getByTestId('board-mercato-errore').textContent).toContain('tetto di 3 tipi di mercato contemporanei raggiunto');
        expect(screen.getByTestId('board-mercato-attesa').textContent).toContain('non l\'ha servito');
        expect(w.richieste('board_mercato')).toHaveLength(1);   // nessuna insistenza prima dei 30 s
    });

    it('tennis: punteggio con vantaggio e Risultato in set', async () => {
        await monta();
        await apriTennis();
        const w = await collega('tennis', { sport: 'tennis', mode: 'PAPER', modo_ordini: modoTennis('PAPER') }, VERO_TENNIS.board);
        const r = within(riga('35790084'));
        expect(r.getByTestId('board-set-game').textContent).toBe('Set 1\u20130 · Game 3\u20132 · 40\u2013AD');
        expect(r.getByTestId('board-batte').textContent).toBe('● batte Simakin');
        fireEvent.change(screen.getByTestId('board-mercato'), { target: { value: 'SET_BETTING' } });
        await scorri();
        expect(w.richieste('board_mercato')[0].p).toEqual({ market_type: 'SET_BETTING' });
        act(() => w.push('board_mercato', VERO_TENNIS.board_mercato));
        await scorri();
        expect(within(riga('35790084')).getByText('2 - 0')).toBeTruthy();
        expect(within(riga('35790084')).getByTestId('board-abbinati').textContent).toBe('900 €');
    });
});
