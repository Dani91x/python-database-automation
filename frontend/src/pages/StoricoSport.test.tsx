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

    it('Omega finisce nel blocco «modalita\' non separabile», con il motivo e la migrazione', async () => {
        monta();
        const blocco = await screen.findByTestId('storico-modo-non-separabile');
        expect(blocco).toHaveTextContent(/non separabili/i);
        expect(blocco).toHaveTextContent('storico_sport_2026-09-17.sql');
        expect(within(blocco).getByTestId('storico-misto-omega')).toHaveTextContent('0,95');
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

    it('l\'altra moneta si vede, ma dichiara di NON essere sommata', async () => {
        monta();
        const altra = await screen.findByTestId('storico-altra-modalita');
        // paper: -1,25 (Safe) + 10 (Mike) = 8,75
        expect(altra).toHaveTextContent('8,75');
        expect(altra).toHaveTextContent(/non è sommato/i);
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
            expect(screen.getByTestId('storico-bot-scelto-misto')).toHaveTextContent(/miste/i);
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
    it('senza get_storico_stake il ROI e\' assente e la pagina dice quale migrazione serve', async () => {
        montaRpc({ safeLive: [rigaRpc('2026-09-16', 3.5)], stake: null });
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toHaveTextContent('3,50'));
        expect(screen.getByTestId('storico-kpi-roi')).toHaveTextContent('—');
        expect(screen.getByTestId('storico-manca-stake')).toHaveTextContent('storico_sport_2026-09-17.sql');
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

describe('storico tennis: i quattro bot senza P&L sono dichiarati, non messi a zero', () => {
    beforeEach(() => {
        montaRpc({ safeLive: [rigaRpc('2026-09-14', 0.44, { by_sport: { tennis: { n: 1, pnl: 0.44, won: 1, lost: 0 } } })] });
    });

    it('elenca Tennis Scalper, Pro, FLB e Swing con il motivo', async () => {
        monta('tennis');
        const blocco = await screen.findByTestId('storico-senza-storico');
        for (const id of ['tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing']) {
            expect(within(blocco).getByTestId(`storico-assente-${id}`)).toBeTruthy();
        }
        expect(blocco).toHaveTextContent(/Non è uno zero/i);
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

    it('cambiando periodo la finestra chiesta alle RPC cambia davvero', async () => {
        const u = userEvent.setup();
        monta();
        await waitFor(() => expect(screen.getByTestId('storico-kpi-pnl')).toBeTruthy());
        rpc.mockClear();
        await u.click(screen.getByTestId('storico-periodo-oggi'));
        await waitFor(() => {
            const chiamate = rpc.mock.calls.filter(([n]) => n === 'get_safe_daily');
            expect(chiamate.length).toBeGreaterThan(0);
            expect(chiamate[0][1]).toMatchObject({ p_from: OGGI, p_to: OGGI });
        });
        expect(screen.getByTestId('storico-intervallo')).toHaveTextContent('17 settembre 2026');
    });

    it('il calendario riceve le giornate unite dei bot visibili', async () => {
        monta();
        expect(await screen.findByTestId('storico-calendario')).toBeTruthy();
    });
});
