// ============================================================================
// SchedaPartita.test.tsx — Task 2/5 (18/09): il tennis vivo dentro la scheda,
// UNA sottoscrizione solo con posizione aperta, mercato SUSPENDED visibile,
// nessuna barra tennis sul calcio.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SchedaPartita } from './SchedaPartita';
import { SchedaPreMatch } from './SchedaPreMatch';
import type { PartitaGiornata, PartitaSoldi } from '@/lib/controlRoom';
import type { TennisLiveNowRow, TennisScoreState } from '@/lib/tennis';
import type { MikeEvent } from '@/lib/mike';

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

// ============================================================================
// B1 (30/09) — «Seychelles v Sri Lanka, nomi partita diversi dalla scheda
// "pre-match", uniformare lo stile»; «stessa visibilita' migliorata delle
// quote»; glossario: «liability», mai «responsabilità».
// ============================================================================
const ODDS_VIVE = { home: { back: 40, lay: 50 }, draw: { back: 15, lay: 18 }, away: { back: 1.08, lay: 1.1 } };

describe('SchedaPartita — B1: nomi uguali alla pre-partita', () => {
    it('i nomi passano dallo STESSO componente della scheda pre-partita (markup identico)', () => {
        const p = partitaCalcio({ nome: 'Seychelles v Sri Lanka' });
        const { unmount } = monta(p);
        const inGioco = screen.getByTestId('cr-nomi-partita').outerHTML;
        unmount();
        render(<MemoryRouter><SchedaPreMatch p={{ ...p, stato: 'pre' }} scheda="pre" mancaS={60} /></MemoryRouter>);
        expect(screen.getByTestId('cr-nomi-partita').outerHTML).toBe(inGioco);
        expect(screen.getAllByTestId('cr-nome-squadra').map((n) => n.textContent)).toEqual(['Seychelles', 'Sri Lanka']);
    });

    it('il nome intero resta leggibile una volta (title + testo accessibile)', () => {
        monta(partitaCalcio({ nome: 'Seychelles v Sri Lanka' }));
        expect(screen.getByTestId('cr-nomi-partita').getAttribute('title')).toBe('Seychelles v Sri Lanka');
        expect(screen.getAllByText('Seychelles v Sri Lanka')).toHaveLength(1);
    });

    it('tennis: stessi nomi su due righe', () => {
        monta(partita({ soldi: SOLDI_CHIUSI }));
        expect(screen.getAllByTestId('cr-nome-squadra').map((n) => n.textContent)).toEqual(['Federer R.', 'Nadal R.']);
    });
});

describe('SchedaPartita — B1: quote da trader in gioco', () => {
    it('calcio in gioco: celle 1 · X · 2 con BACK sky / LAY rose, uguali alla pre-partita', () => {
        const p = partitaCalcio({ odds: ODDS_VIVE, latenzaQuoteS: 2, statoQuote: 'fresco' });
        const { unmount } = monta(p);
        const celle = within(screen.getByTestId('cr-calcio-vivo-quote')).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['1 40,00/50,00', 'X 15,00/18,00', '2 1,08/1,10']);
        const html = celle.map((c) => c.outerHTML);
        unmount();
        render(<MemoryRouter><SchedaPreMatch p={{ ...p, stato: 'pre' }} scheda="pre" mancaS={60} /></MemoryRouter>);
        expect(within(screen.getByTestId('cr-pre-quote')).getAllByTestId('cr-quota-cella').map((c) => c.outerHTML)).toEqual(html);
    });

    it('l’età delle quote sta ACCANTO alle quote, con l’etichetta di cosa misura', () => {
        monta(partitaCalcio({ odds: ODDS_VIVE, latenzaQuoteS: 40, statoQuote: 'fermo', etaFeedS: 3, freschezza: 'fresca' }));
        const vivo = screen.getByTestId('cr-calcio-vivo');
        const lat = within(vivo).getByTestId('cr-latenza');
        expect(lat).toHaveTextContent('ultimo cambio: fermo 40 s');
        // «fermo» non è un allarme; il punteggio ha la SUA età, distinta
        expect(lat.querySelector('.text-orange-400')).toBeNull();
        expect(within(vivo).getByTestId('cr-calcio-vivo-eta-punteggio')).toHaveTextContent('punteggio 3 s');
        expect(screen.getAllByTestId('cr-latenza')).toHaveLength(1);
    });

    it('prezzo vecchio ed età ignota restano arancioni', () => {
        const { unmount } = monta(partitaCalcio({ odds: ODDS_VIVE, latenzaQuoteS: 130, statoQuote: 'vecchio' }));
        expect(screen.getByTestId('cr-latenza')).toHaveTextContent('vecchio 2 min');
        expect(screen.getByTestId('cr-latenza-valore').className).toContain('text-orange-400');
        unmount();
        monta(partitaCalcio({ odds: ODDS_VIVE, latenzaQuoteS: null, statoQuote: 'ignoto' }));
        expect(screen.getByTestId('cr-latenza')).toHaveTextContent('ultimo cambio: età ignota');
    });

    it('mercato SOSPESO: badge e quote insieme', () => {
        monta(partitaCalcio({ odds: ODDS_VIVE, statoMercato: 'SUSPENDED' }));
        expect(screen.getByTestId('cr-calcio-vivo-mercato')).toHaveTextContent('SOSPESO');
        expect(within(screen.getByTestId('cr-calcio-vivo-quote')).getAllByTestId('cr-quota-cella')).toHaveLength(3);
    });

    it('senza quote l’età resta nella riga dei pulsanti, con la stessa etichetta', () => {
        monta(partitaCalcio({ latenzaQuoteS: 3, statoQuote: 'fresco' }));
        expect(screen.queryByTestId('cr-calcio-vivo')).toBeNull();
        expect(screen.getByTestId('cr-latenza')).toHaveTextContent('ultimo cambio: 3 s');
    });

    it('le linee Under/Over (anche quella decisa dai gol) si vedono nel blocco in gioco', () => {
        monta(partitaCalcio({
            lineeOu: [
                { marketId: '1.35', linea: 3.5, stato: 'OPEN', decisa: false, perMike: false,
                    under: { back: 1.5, lay: 1.52 }, over: { back: 2.6, lay: 2.7 }, etaCambioS: 1 },
                { marketId: '1.45', linea: 4.5, stato: 'SUSPENDED', decisa: true, perMike: true,
                    under: null, over: { back: 1.01, lay: null }, etaCambioS: null },
            ],
        }));
        const ou = within(screen.getByTestId('cr-calcio-vivo')).getByTestId('cr-calcio-vivo-ou');
        const righe = within(ou).getAllByTestId('cr-quote-ou-linea');
        expect(righe[0]).toHaveTextContent('Over 2,60/2,70');
        expect(righe[1]).toHaveTextContent('Under —/—');
        expect(righe[1]).toHaveTextContent('decisa dai gol');
        expect(righe[1]).toHaveTextContent('SOSPESO');
    });
});

describe('SchedaPartita — B1bis: linee oltre 4 in gioco', () => {
    it('sei linee a inizio partita: tutte nella scheda (nessuna guardia che le nasconda)', () => {
        monta(partitaCalcio({
            lineeOu: [0.5, 1.5, 2.5, 3.5, 4.5, 5.5].map((l) => ({
                marketId: `1.${l * 10}`, linea: l, stato: 'OPEN', decisa: false, perMike: false,
                under: { back: 1.5, lay: 1.52 }, over: { back: 2.6, lay: 2.7 }, etaCambioS: 1,
            })),
        }));
        const ou = screen.getByTestId('cr-calcio-vivo-ou');
        expect(within(ou).getAllByTestId('cr-quote-ou-linea')).toHaveLength(6);
        expect(within(within(ou).getByTestId('cr-quote-ou-altre')).getAllByTestId('cr-quote-ou-linea')).toHaveLength(4);
    });
});

describe('SchedaPartita — B1: tennis, quote della barra con lo stesso componente', () => {
    it('le selezioni del Match Odds col loro nome, BACK sky / LAY rose', async () => {
        hoisted.row = tennisRow({
            state: { markets: [{ market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [
                    { selection_id: 11, name: 'Federer R.', back: 1.5, lay: 1.52, ltp: 1.5 },
                    { selection_id: 22, name: 'Nadal R.', back: 2.94, lay: null, ltp: 2.9 },
                ] }], order_mode: 'LIVE', updated_ms: Date.now() },
        });
        monta(partita({ soldi: SOLDI_APERTI }));
        const q = await screen.findByTestId('cr-tennis-vivo-quote');
        const celle = within(q).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['Federer R. 1,50/1,52', 'Nadal R. 2,94/—']);
        expect(within(celle[0]).getByTestId('cr-quota-back').className).toMatch(/text-sky-/);
    });

    // B1bis: tennis in gioco SENZA posizione = celle P1/P2 dello scanner con la
    // loro età; CON posizione = solo la barra del runner (una fonte per scheda).
    it('tennis in gioco SENZA posizione: celle P1/P2 dello scanner e l’età accanto, nessuna sottoscrizione', () => {
        monta(partita({
            soldi: SOLDI_CHIUSI, latenzaQuoteS: 4, statoQuote: 'fresco',
            odds: { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.66 } },
        }));
        expect(hoisted.subCalls).toBe(0);
        const riga = screen.getByTestId('cr-tennis-quote');
        const celle = within(riga).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['P1 1,50/1,52', 'P2 2,60/2,66']);
        expect(within(riga).getByTestId('cr-latenza')).toHaveTextContent('ultimo cambio: 4 s');
        expect(screen.getAllByTestId('cr-latenza')).toHaveLength(1);
        expect(screen.queryByTestId('cr-tennis-vivo')).toBeNull();
    });

    it('W_B1: tennis in gioco senza posizione, coi nomi dello scanner le celle dicono il giocatore', () => {
        monta(partita({
            soldi: SOLDI_CHIUSI, latenzaQuoteS: 4, statoQuote: 'fresco',
            odds: { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.66 } },
            giocatori: { p1: 'Federer R.', p2: 'Nadal R.' },
        }));
        const celle = within(screen.getByTestId('cr-tennis-quote')).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['Federer R. 1,50/1,52', 'Nadal R. 2,60/2,66']);
        expect(celle[1].getAttribute('title')).toMatch(/sortPriority\) 2/);
    });

    it('tennis in gioco CON posizione: solo la barra del runner, MAI anche le quote dello scanner', async () => {
        hoisted.row = tennisRow();
        monta(partita({
            soldi: SOLDI_APERTI, latenzaQuoteS: 4, statoQuote: 'fresco',
            odds: { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.66 } },
        }));
        await screen.findByTestId('cr-tennis-vivo');
        expect(screen.queryByTestId('cr-tennis-quote')).toBeNull();
        expect(screen.queryByText('P1 1,50/1,52')).toBeNull();
    });

    it('tennis NON in gioco (conclusa) senza posizione: nessuna fila di quote dello scanner', () => {
        monta(partita({ soldi: SOLDI_CHIUSI, stato: 'chiusa', odds: { p1: { back: 1.5, lay: 1.52 }, p2: null } }));
        expect(screen.queryByTestId('cr-tennis-quote')).toBeNull();
    });

    // W_B1: accanto alle celle della barra, l'eta' delle QUOTE del runner
    it('accanto alle quote della barra: «ultimo aggiornamento del runner: N s» da state.updated_ms', async () => {
        hoisted.row = tennisRow({
            state: { markets: [{ market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [{ selection_id: 11, name: 'Federer R.', back: 1.5, lay: 1.52, ltp: 1.5 }] }],
            order_mode: 'LIVE', updated_ms: Date.now() - 7_000 },
        });
        monta(partita({ soldi: SOLDI_APERTI }));
        const e = await screen.findByTestId('cr-tennis-vivo-eta-quote');
        expect(e).toHaveTextContent(/^ultimo aggiornamento del runner: [78] s$/);
        expect(e.getAttribute('title')).toMatch(/LETTURA/);
        expect(e.getAttribute('title')).toMatch(/non .* cambio/);
        expect(within(e).getByTestId('cr-tennis-vivo-eta-quote-valore').className).toContain('text-white/50');
    });

    // una LETTURA recente del runner non prova che i prezzi siano freschi (la
    // cache puo' essere vecchia): mai il verde di «fresco», grigio neutro
    it('lettura recentissima (1 s): grigio neutro, mai il verde di «fresco»', async () => {
        hoisted.row = tennisRow({
            state: { markets: [{ market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [{ selection_id: 11, name: 'Federer R.', back: 1.5, lay: 1.52, ltp: 1.5 }] }],
            order_mode: 'LIVE', updated_ms: Date.now() - 1_000 },
        });
        monta(partita({ soldi: SOLDI_APERTI }));
        const v = within(await screen.findByTestId('cr-tennis-vivo-eta-quote')).getByTestId('cr-tennis-vivo-eta-quote-valore');
        expect(v.className).toContain('text-white/50');
        expect(v.className).not.toMatch(/emerald/);
    });

    it('stato senza updated_ms: «ultimo aggiornamento del runner: età ignota» in arancione', async () => {
        hoisted.row = tennisRow({
            state: { markets: [{ market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [{ selection_id: 11, name: 'Federer R.', back: 1.5, lay: 1.52, ltp: 1.5 }] }],
            order_mode: 'LIVE' },
        });
        monta(partita({ soldi: SOLDI_APERTI }));
        const e = await screen.findByTestId('cr-tennis-vivo-eta-quote');
        expect(e).toHaveTextContent('ultimo aggiornamento del runner: età ignota');
        expect(within(e).getByTestId('cr-tennis-vivo-eta-quote-valore').className).toContain('text-orange-400');
    });

    it('l’età della barra dice che è quella del PUNTEGGIO', async () => {
        hoisted.row = tennisRow();
        monta(partita({ soldi: SOLDI_APERTI }));
        expect(await screen.findByTestId('cr-tennis-vivo-eta')).toHaveTextContent(/^punteggio /);
    });
});

describe('SchedaPartita — R_B1: il target calcolato dalla pagina lo dice in chiaro', () => {
    it('fonte ripiego: «target (media della pagina)», non solo un asterisco nel tooltip', () => {
        monta(partitaCalcio({ target: { valore: 4.17, fonte: 'ripiego' } }));
        const t = screen.getByTestId('cr-target');
        expect(t).toHaveTextContent('target (media della pagina) 4,17 €');
    });

    it('fonte servizio: resta «target», senza la dicitura della media', () => {
        monta(partitaCalcio({ target: { valore: 4.17, fonte: 'servizio' } }));
        const t = screen.getByTestId('cr-target');
        expect(t).toHaveTextContent('target 4,17 €');
        expect(t.textContent).not.toMatch(/media/);
    });
});

describe('SchedaPartita — B1: glossario, «liability» e mai «responsabilità»', () => {
    it('soldi veri e prova: «liability», nessun «resp.» ne’ «responsabilità»', () => {
        const { container } = monta(partitaCalcio({
            soldi: {
                live: { netPnl: null, liability: 9.8, investito: 5, aperta: true },
                paper: { netPnl: null, liability: 4, investito: 4, aperta: true },
                modi: ['live', 'paper'], bots: ['mike'],
            },
        }));
        const riga = screen.getByTestId('cr-liability-partita');
        // W_B2 (30/09, M1): cambiato di proposito - la somma delle righe si dice LORDA
        expect(riga).toHaveTextContent('liability delle righe (lorda) 9,80 €');
        expect(riga).toHaveTextContent('prova (lorda) 4,00 €');
        expect(container.innerHTML).not.toMatch(/resp\.|responsabilit/i);
        expect(riga.innerHTML).toContain('liability delle righe aperte con SOLDI VERI, sommate riga per riga senza compensare');
        expect(riga.innerHTML).toContain('non sono soldi veri e non si sommano');
    });
});

describe('SchedaPartita — W_B2 (M1): mai la stessa parola per due numeri diversi', () => {
    const SOLDI_FOLLO = {
        live: { netPnl: null, liability: 12.93, investito: 11.32, aperta: true },
        paper: { netPnl: null, liability: 0, investito: 0, aperta: false },
        modi: ['live'], bots: ['mike'],
    } as unknown as PartitaSoldi;
    function mikeEv(mode: 'live' | 'paper', liability: number | null): MikeEvent {
        return {
            event_id: 'C1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
            ko_at: new Date().toISOString(), mode, markets: {}, state: 'LIVE_COVERED', cycle_no: 0,
            entry_price_initial: 2.4, dossier: null,
            live: { liability, feed_age_s: 1 } as unknown as MikeEvent['live'],
            positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
        };
    }
    function montaConMike(ev: MikeEvent | null) {
        return render(<MemoryRouter><SchedaPartita p={partitaCalcio({ soldi: SOLDI_FOLLO })} operazioni={[]} mike={ev} /></MemoryRouter>);
    }

    it('Mike LIVE: «Liability aperta (netta, Mike)» dal servizio con marchio BOT, e la lorda delle righe detta tale', () => {
        montaConMike(mikeEv('live', 9.8));
        const netta = screen.getByTestId('cr-liability-netta-mike');
        expect(netta).toHaveTextContent('Liability aperta (netta, Mike) 9,80 €');
        expect(screen.getByTestId('cr-liability-netta-mike-fonte').getAttribute('data-fonte')).toBe('bot');
        const riga = screen.getByTestId('cr-liability-partita');
        expect(riga).toHaveTextContent('liability delle righe (lorda) 12,93 €');
        // nessuna cifra con la parola nuda «liability» senza dire quale
        expect(riga.textContent).not.toMatch(/(^|[^(])liability \d/);
    });

    it('Mike in PAPER o senza dato: nessuna netta accanto ai soldi veri', () => {
        const { unmount } = montaConMike(mikeEv('paper', 9.8));
        expect(screen.queryByTestId('cr-liability-netta-mike')).toBeNull();
        unmount();
        montaConMike(mikeEv('live', null));
        expect(screen.queryByTestId('cr-liability-netta-mike')).toBeNull();
        expect(screen.getByTestId('cr-liability-partita')).toHaveTextContent('liability delle righe (lorda) 12,93 €');
    });
});
