// ============================================================================
// StoricoSport.test.tsx — la dashboard dello storico per sport, dal vivo.
//
// Qui NON si mockano i fetcher: si mocka **solo il client Supabase**, cosi' il
// test attraversa davvero `lib/dailyHistory` → `lib/storicoSport` → pagina,
// compreso il ripiego su `get_omega_daily` a due argomenti.
//
// I finti parlano come il vero: le righe e i messaggi d'errore qui sotto sono
// copiati da una sonda IN SOLA LETTURA sul database del 17/09/2026
//   · get_safe_daily(p_from,p_to,p_sport,p_mode)  → 24 chiavi, riga reale del 14/09
//   · get_mike_daily(p_from,p_to,p_mode)          → le stesse + `mode`
//   · get_omega_daily(p_from,p_to,p_mode)         → PGRST202, la firma NON esiste
//   · get_storico_stake(...)                      → PGRST202, migrazione non applicata
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: (...args: unknown[]) => rpc(...args),
        channel: () => ({ on: () => ({ subscribe: () => ({}) }), subscribe: () => ({}) }),
        removeChannel: () => {},
        from: () => ({ select: () => ({ data: [], error: null }) }),
    },
}));

import { StoricoSport } from './StoricoSport';

const OGGI = '2026-09-17';

/** Una riga giornaliera con le IDENTICHE chiavi della RPC vera. */
function rigaRpc(day: string, pnl: number, over: Record<string, unknown> = {}) {
    const won = pnl > 0 ? 1 : 0;
    const lost = pnl < 0 ? 1 : 0;
    return {
        day, won, goal: null, lost, void: 0,
        avg_win: pnl > 0 ? pnl : null, settled: won + lost, avg_loss: pnl < 0 ? pnl : null,
        by_sport: { calcio: { n: 1, pnl, won, lost } },
        goal_pct: null, win_rate: won + lost > 0 ? won / (won + lost) : null,
        by_origin: { auto: { n: 1, pnl, won, lost } },
        best_trade: pnl, gross_loss: pnl < 0 ? -pnl : 0,
        by_strategy: { esatto: { n: 1, pnl, won, lost } },
        worst_trade: pnl, gross_profit: pnl > 0 ? pnl : 0,
        pnl_realized: pnl, hedged_closed: 0,
        last_trade_at: `${day}T15:15:14.791406+00:00`,
        max_liability: 118.0, profit_factor: null, trades_placed: 1,
        first_trade_at: `${day}T13:26:36.238817+00:00`,
        commission_paid: 0.02,
        ...over,
    };
}

/** L'errore vero di PostgREST quando una firma non esiste (PGRST202). */
function firmaMancante(nome: string, args: string) {
    return {
        data: null,
        error: {
            code: 'PGRST202',
            message: `Could not find the function public.${nome}(${args}) in the schema cache`,
            details: null, hint: null,
        },
    };
}

interface Piano {
    safeLive?: unknown[];
    safePaper?: unknown[];
    mikeLive?: unknown[];
    mikePaper?: unknown[];
    /** true = get_omega_daily accetta p_mode (migrazione applicata) */
    omegaConModo?: boolean;
    omegaRighe?: unknown[];
    /** true = get_storico_stake esiste */
    stake?: Record<string, number> | null;
    /** 01/10 (D-01): righe di `get_tennis_bot_daily` per moneta (chiavi della RPC vera) */
    tennisLive?: unknown[];
    tennisPaper?: unknown[];
    /** 01/10: righe di `get_mike_day_trades` / `get_safe_day_trades` per giorno */
    mikeDay?: Record<string, unknown[]>;
}

/** riga di `get_tennis_bot_daily` con le 12 chiavi della RPC (migrazione del 30/09) */
function rigaTennis(giorno: string, bot: string, netto: number, over: Record<string, unknown> = {}) {
    return {
        giorno, bot_key: bot, ordini: 2, vinti: netto > 0 ? 1 : 0, persi: netto < 0 ? 1 : 0,
        pnl_lordo: netto + 0.05, commissione: 0.05, pnl_netto: netto,
        pnl_reale: 0, pnl_stimato: netto, stimati: 2, volume: 4, ...over,
    };
}

function montaRpc(p: Piano) {
    rpc.mockImplementation(async (nome: string, args: Record<string, unknown>) => {
        const modo = args?.p_mode as string | null;
        if (nome === 'get_omega_daily') {
            if (modo != null && !p.omegaConModo) {
                return firmaMancante('get_omega_daily', 'p_from, p_mode, p_to');
            }
            return { data: p.omegaRighe ?? [], error: null };
        }
        if (nome === 'get_safe_daily') {
            return { data: (modo === 'paper' ? p.safePaper : p.safeLive) ?? [], error: null };
        }
        if (nome === 'get_mike_daily') {
            return { data: (modo === 'paper' ? p.mikePaper : p.mikeLive) ?? [], error: null };
        }
        if (nome === 'get_tennis_bot_daily') {
            const righe = ((modo === 'paper' ? p.tennisPaper : p.tennisLive) ?? []) as Record<string, unknown>[];
            return { data: { rows: righe.filter((r) => r.bot_key === args.p_bot), mode: modo }, error: null };
        }
        if (nome === 'get_mike_day_trades') {
            return { data: p.mikeDay?.[String(args.p_day)] ?? [], error: null };
        }
        if (nome === 'get_storico_stake') {
            if (!p.stake) return firmaMancante('get_storico_stake', 'p_bot, p_from, p_mode, p_sport, p_to');
            return {
                data: Object.entries(p.stake).map(([day, v]) => ({
                    day, stake_placed: v, trades_placed: 1,
                })),
                error: null,
            };
        }
        // dettaglio del giorno e qualunque altra RPC: nessuna riga
        return { data: [], error: null };
    });
}

function monta(sport: 'calcio' | 'tennis' = 'calcio') {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <StoricoSport sport={sport} oggi={OGGI} />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

beforeEach(() => {
    vi.clearAllMocks();
});

// ---------------------------------------------------------------------------

describe('storico calcio: i profitti per bot, separati per moneta', () => {
    beforeEach(() => {
        montaRpc({
            safeLive: [rigaRpc('2026-09-16', 3.5)],
            safePaper: [rigaRpc('2026-09-16', -1.25)],
            mikeLive: [rigaRpc('2026-09-15', 1.5, { mode: 'live' })],
            mikePaper: [rigaRpc('2026-09-15', 10, { mode: 'paper' })],
            omegaConModo: false,
            omegaRighe: [rigaRpc('2026-09-14', 0.95)],
        });
    });

    it('la testata dichiara la moneta PRIMA dei numeri', async () => {
        monta();
        expect(await screen.findByTestId('storico-testata-modo')).toHaveTextContent('soldi veri');
    });

    it('il totale «soldi veri» somma SOLO safe e mike, mai Omega che e\' misto', async () => {
        monta();
        await waitFor(() => {
            expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('5,00');
        });
        // 3,50 (Safe live) + 1,50 (Mike live) = 5,00. Omega +0,95 NON entra.
        expect(screen.getByTestId('storico-kpi-pnl')).not.toHaveTextContent('5,95');
    });

    it('Omega finisce nel blocco «non separabile» SENZA cifre (sarebbero di due monete) e senza nomi tecnici', async () => {
        monta();
        const blocco = await screen.findByTestId('storico-modo-non-separabile');
        expect(blocco).toHaveTextContent(/storico per moneta non disponibile/i);
        expect(within(blocco).getByTestId('storico-misto-omega')).toHaveTextContent('non incluso nei totali');
        // A-02/A-03 (01/10): la cifra MISTA e i nomi di file/funzioni non ci sono piu'
        expect(blocco).not.toHaveTextContent('0,95');
        expect(blocco).not.toHaveTextContent(/\.sql|get_omega_daily|p_from|RPC/);
    });

    it('la tabella per bot elenca un rigo per bot, con il suo P&L', async () => {
        monta();
        await screen.findByTestId('storico-bot-riga-safe');
        expect(screen.getByTestId('storico-bot-pnl-safe')).toHaveTextContent('3,50');
        expect(screen.getByTestId('storico-bot-pnl-mike')).toHaveTextContent('1,50');
        // Omega non ha un rigo: e' nel blocco dei misti
        expect(screen.queryByTestId('storico-bot-riga-omega')).toBeNull();
    });

    it('il totale in fondo alla tabella e\' quello della moneta scelta', async () => {
        monta();
        const tot = await screen.findByTestId('storico-riga-totale');
        expect(tot).toHaveTextContent('Totale soldi veri');
        expect(tot).toHaveTextContent('5,00');
    });

    it('A-01 (01/10): NESSUNA cifra dell\'altra moneta, in nessuna delle due viste', async () => {
        const u = userEvent.setup();
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('5,00'));
        expect(screen.queryByTestId('storico-altra-modalita')).toBeNull();
        // vista soldi veri: niente prova (Safe −1,25, Mike +10,00, totale 8,75) e niente Omega misto
        const pagina = () => document.body.textContent ?? '';
        for (const c of ['8,75', '1,25', '10,00', '0,95']) expect(pagina()).not.toContain(c);
        // vista prova: niente soldi veri (Safe 3,50, Mike 1,50, totale 5,00). Il «+5,00 €»
        // della scala dell'asse della curva e' una tacca, non una cifra: si guarda
        // dove stanno le cifre (riepilogo e tabella)
        await u.click(screen.getByTestId('storico-testata-paper'));
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('8,75'));
        for (const c of ['3,50', '1,50', '0,95']) expect(pagina()).not.toContain(c);
        expect(screen.getByTestId('storico-per-bot')).not.toHaveTextContent('5,00');
        expect(screen.getByTestId('storico-kpi-pnl')).not.toHaveTextContent('5,00');
    });

    it('A-09: la moneta si sceglie in UN posto solo (la testata), niente pillole doppie', async () => {
        monta();
        await screen.findByTestId('storico-filtri');
        expect(screen.queryByTestId('storico-modo-live')).toBeNull();
        expect(screen.queryByTestId('storico-modo-paper')).toBeNull();
        expect(screen.getByTestId('storico-testata-live')).toBeInTheDocument();
    });

    it('B-01 / R-01: senza righe del giorno il piede NON afferma il giorno della PARTITA, e niente nomi di funzioni', async () => {
        monta();
        await screen.findByTestId('storico-filtri');
        const piede = document.body.textContent ?? '';
        expect(piede).toMatch(/Criterio della giornata non verificabile/);
        expect(piede).not.toMatch(/attribuita al giorno della PARTITA/);
        expect(piede).not.toMatch(/trading_daily_history|\.sql/);
    });

    it('D-04: il P&L in soldi veri dice la sua fonte', async () => {
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('5,00'));
        expect(screen.getByTestId('storico-kpi-pnl-fonte')).toHaveTextContent(/conto Betfair/);
    });

    it('C-05: le regolate né vinte né perse sono dette (pari/annullate)', async () => {
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-vp')).toHaveTextContent('pari/annullate'));
    });

    it('passando a «prova» i numeri cambiano: sono un\'altra moneta', async () => {
        const u = userEvent.setup();
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('5,00'));
        await u.click(screen.getByTestId('storico-testata-paper'));
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('8,75'));
        expect(screen.getByTestId('storico-testata-modo')).toHaveTextContent('prova');
    });

    it('scegliendo un bot MISTO la pagina dice perche\' i grafici restano vuoti', async () => {
        const u = userEvent.setup();
        monta();
        await screen.findByTestId('storico-bot-omega');
        expect(screen.queryByTestId('storico-bot-scelto-misto')).toBeNull();
        await u.click(screen.getByTestId('storico-bot-omega'));
        await waitFor(() => {
            expect(screen.getByTestId('storico-bot-scelto-misto')).toHaveTextContent(/non è separato per moneta/i);
        });
    });

    it('NON esiste un filtro «entrambi»: due monete non hanno un totale', async () => {
        monta();
        await screen.findByTestId('storico-filtri');
        expect(screen.queryByTestId('storico-modo-tutte')).toBeNull();
        expect(screen.queryByText(/entrambi/i)).toBeNull();
    });
});

describe('ROI: senza l\'importo piazzato non si inventa', () => {
    it('senza l\'importo piazzato il ROI e\' assente e la pagina lo dice IN PAROLE (C-02)', async () => {
        montaRpc({ safeLive: [rigaRpc('2026-09-16', 3.5)], stake: null });
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('3,50'));
        expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('—');
        expect(screen.getByTestId('storico-manca-stake')).toHaveTextContent(/serve un aggiornamento del database/);
        expect(screen.getByTestId('storico-manca-stake')).not.toHaveTextContent(/\.sql|migrations/);
        expect(screen.getByTestId('storico-kpi-stake')).not.toHaveTextContent(/migrazione/);
    });

    it('con l\'importo piazzato il ROI compare', async () => {
        montaRpc({
            safeLive: [rigaRpc('2026-09-16', 3.5)],
            stake: { '2026-09-16': 35 },
        });
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('10,0'));
        expect(screen.queryByTestId('storico-manca-stake')).toBeNull();
    });
});

describe('storico tennis: i quattro bot tennis ENTRANO (D-01, 01/10)', () => {
    beforeEach(() => {
        montaRpc({
            safeLive: [rigaRpc('2026-09-14', 0.44, { by_sport: { tennis: { n: 1, pnl: 0.44, won: 1, lost: 0 } } })],
            tennisLive: [rigaTennis('2026-09-15', 'tennis_swing', 1.2, { pnl_reale: 1.0, pnl_stimato: 0.2, stimati: 1 })],
            tennisPaper: [rigaTennis('2026-09-15', 'tennis_pro', -3.3)],
        });
    });

    it('Tennis Swing ha il suo rigo e il suo P&L; nessun «non compaiono» per i bot tennis', async () => {
        monta('tennis');
        expect(await screen.findByTestId('storico-bot-pnl-tennis_swing')).toHaveTextContent('1,20');
        expect(screen.queryByTestId('storico-senza-storico')).toBeNull();
        // 0,44 (Safe tennis) + 1,20 (Swing) = 1,64, SOLO soldi veri (il Pro in prova non entra)
        expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('1,64');
        expect(document.body.textContent).not.toContain('3,30');
        // ROI non calcolabile: i bot tennis non registrano l'importo piazzato, detto
        expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('—');
        expect(screen.getByTestId('storico-manca-stake')).toHaveTextContent(/bot tennis/);
        // le «operazioni» di un bot tennis sono ordini, detto sul rigo
        expect(screen.getByTestId('storico-bot-riga-tennis_swing')).toHaveTextContent('ordini');
    });

    it('D-03/D-04: solo bot tennis con la fonte separata: «di cui conto Betfair · stima (N ordini stimati)»', async () => {
        montaRpc({ tennisLive: [rigaTennis('2026-09-15', 'tennis_swing', 1.2, { pnl_reale: 1.0, pnl_stimato: 0.2, stimati: 1 })] });
        monta('tennis');
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl-fonte'))
            .toHaveTextContent('di cui conto Betfair +1,00 € · stima +0,20 € (1 ordine ancora stimato)'));
    });

    it('la lettura chiede UNA moneta per bot (p_mode), mai le due insieme', async () => {
        monta('tennis');
        await screen.findByTestId('storico-bot-pnl-tennis_swing');
        const chiamate = rpc.mock.calls.filter(([n]) => n === 'get_tennis_bot_daily');
        expect(chiamate.length).toBe(8);      // 4 bot x 2 monete
        expect(chiamate.every(([, a]) => a.p_mode === 'live' || a.p_mode === 'paper')).toBe(true);
    });

    it('nel tennis non compare Omega ne\' Mike', async () => {
        monta('tennis');
        await screen.findByTestId('storico-bot-riga-safe');
        expect(screen.queryByTestId('storico-bot-riga-omega')).toBeNull();
        expect(screen.queryByTestId('storico-bot-riga-mike')).toBeNull();
    });

    it('il pulsante per passare all\'altro sport c\'e\' ed e\' esplicito', async () => {
        monta('tennis');
        const link = await screen.findByTestId('storico-testata-altro');
        expect(link).toHaveAttribute('href', '/storico/calcio');
    });
});

describe('B-04 (01/10): il dettaglio del giorno di Mike usa il criterio della CELLA, mai uno cablato', () => {
    const rigaMike = (over: Record<string, unknown>) => ({
        id: 31, event_id: 'm1', event_name: 'Roma v Lazio', side: 'back', mode: 'live',
        price: 1.5, size: 10, liability: 10, status: 'won', pnl: 4.75, bet_id: 'b31', strategy: 'under_entry',
        placed_at: '2026-09-16T21:30:00Z', settled_at: '2026-09-16T23:15:00Z',
        meta: null, closes: [], total_pnl: 4.75, placed_in_day: false, settled_in_day: true, ...over,
    });

    it('RPC vecchia (senza in_day): Mike per regolamento come la cella, e la pagina lo DICHIARA', async () => {
        montaRpc({
            mikeLive: [rigaRpc(OGGI, 4.75, { mode: 'live' })],
            mikeDay: { [OGGI]: [rigaMike({})] },
            stake: { [OGGI]: 10 },
        });
        monta();
        const det = await screen.findByTestId('storico-dettaglio-mike');
        await waitFor(() => expect(within(det).getByTestId('day-total-pnl')).toHaveTextContent('+4,75'));
        expect(screen.getByTestId('storico-bot-pnl-mike')).toHaveTextContent('4,75');
        expect(screen.getByTestId('storico-giornata-ripiego')).toHaveTextContent(/non manda ancora il giorno della partita/);
        // C-01: col criterio di prima P&L (regolamento) e importo (piazzamento) non stanno sullo stesso giorno
        expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('—');
        // R-01 (review 01/10): il piede dice il criterio VERO, non il giorno della partita
        const piede = screen.getByTestId('page-footer');
        expect(piede).not.toHaveTextContent(/attribuita al giorno della PARTITA/);
        expect(piede).toHaveTextContent(/Omega e Safe attribuiscono ogni operazione al giorno di PIAZZAMENTO, Mike al giorno di REGOLAMENTO/);
        expect(piede).toHaveTextContent(/manca il suo aggiornamento/);
    });

    it('contratto nuovo (in_day): nessun ripiego dichiarato, dettaglio = cella', async () => {
        montaRpc({
            mikeLive: [rigaRpc(OGGI, 4.75, { mode: 'live' })],
            mikeDay: { [OGGI]: [rigaMike({ in_day: true, giorno_partita: OGGI, giorno_da: 'partita', placed_at: '2026-09-17T18:00:00Z', settled_at: '2026-09-17T20:00:00Z', placed_in_day: true })] },
            stake: { [OGGI]: 10 },
        });
        monta();
        const det = await screen.findByTestId('storico-dettaglio-mike');
        await waitFor(() => expect(within(det).getByTestId('day-total-pnl')).toHaveTextContent('+4,75'));
        expect(screen.queryByTestId('storico-giornata-ripiego')).toBeNull();
        expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('47,5');
        // R-01 (review 01/10): con in_day dal database il piede dice il giorno della PARTITA
        expect(screen.getByTestId('page-footer')).toHaveTextContent(/attribuita al giorno della PARTITA/);
    });
});

describe('periodo e curve', () => {
    beforeEach(() => {
        montaRpc({ safeLive: [rigaRpc('2026-09-15', 2), rigaRpc('2026-09-16', -0.5)] });
    });

    it('la curva cumulata e le barre per giornata ci sono entrambe', async () => {
        monta();
        expect(await screen.findByTestId('storico-curva')).toBeTruthy();
        expect(screen.getByTestId('storico-barre-grafico')).toBeTruthy();
    });

    it('le barre dicono il totale e le giornate migliore e peggiore (accessibilita\')', async () => {
        monta();
        const svg = await screen.findByTestId('storico-barre-grafico');
        const aria = svg.getAttribute('aria-label') ?? '';
        expect(aria).toMatch(/2 giornate/);
        expect(aria).toMatch(/migliore/);
        expect(aria).toMatch(/peggiore/);
    });

    it('cambiando periodo i NUMERI seguono il periodo; la lettura copre anche la griglia del mese (B-15)', async () => {
        const u = userEvent.setup();
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('1,50'));
        await u.click(screen.getByTestId('storico-periodo-oggi'));
        // il 17/09 non ha giornate: P&L del periodo 0,00 (le giornate del 15 e 16 restano nel calendario)
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('0,00'));
        const chiamate = rpc.mock.calls.filter(([n]) => n === 'get_safe_daily');
        // griglia di settembre 2026: lunedi' 31 agosto -> domenica 4 ottobre
        expect(chiamate[chiamate.length - 1][1]).toMatchObject({ p_from: '2026-08-31', p_to: '2026-10-04' });
        expect(screen.getByTestId('storico-intervallo')).toHaveTextContent('17 settembre 2026');
    });

    it('B-15: il mese precedente si LEGGE (mai «nessuna operazione» su giornate non lette)', async () => {
        const u = userEvent.setup();
        monta();
        await screen.findByTestId('storico-calendario');
        await u.click(screen.getByRole('button', { name: 'Mese precedente' }));
        await waitFor(() => {
            const chiamate = rpc.mock.calls.filter(([n]) => n === 'get_safe_daily');
            // agosto 2026: griglia da lunedi' 27 luglio; il periodo (30 giorni) arriva al 17/09
            expect(chiamate[chiamate.length - 1][1]).toMatchObject({ p_from: '2026-07-27', p_to: '2026-09-17' });
        });
    });

    it('il calendario riceve le giornate unite dei bot visibili', async () => {
        monta();
        expect(await screen.findByTestId('storico-calendario')).toBeTruthy();
    });
});
