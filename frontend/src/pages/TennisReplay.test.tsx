// ============================================================================
// TennisReplay.test.tsx — la pagina «Replay Tennis» (07/10) con la partita VERA.
//
// Il finto e' il CLIENT supabase (come TennisTerminal.test.tsx): le funzioni vere
// di `lib/tennisReplay` e `lib/live` girano; le RPC del tennis rispondono con la
// fixture `replay_tennis_35790089.json` (uscita del convertitore Python sulla
// registrazione vera) e i frame sono filtrati per finestra [p_from_ts, p_to_ts)
// come fa `get_replay_tennis_frames`. Ogni RPC chiamata e' registrata: nessuna
// del Match Replay del calcio deve partire (calcio e tennis non si mischiano).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import fixture from '@/lib/__fixtures__/replay_tennis_35790089.json';

const registro = vi.hoisted(() => ({ rpc: [] as string[], lista: true }));

vi.mock('@/integrations/supabase/client', async () => {
    const fx = (await import('@/lib/__fixtures__/replay_tennis_35790089.json')).default as unknown as {
        event: Record<string, unknown>; markets: unknown[]; score_timeline: unknown[];
        frames: Array<{ ts: string }>;
    };
    const risposta = { data: null, error: null };
    const catena = (): unknown => {
        const self: unknown = new Proxy({}, {
            get(_t, k: string) {
                if (k === 'then') return (ok: (v: unknown) => void) => ok(risposta);
                return () => self;
            },
        });
        return self;
    };
    const canale = (): unknown => {
        const c: Record<string, unknown> = {};
        c.on = () => c;
        c.subscribe = () => c;
        c.unsubscribe = () => Promise.resolve('ok');
        return c;
    };
    const supabase = {
        rpc: vi.fn(async (nome: string, args?: Record<string, unknown>) => {
            registro.rpc.push(nome);
            if (nome === 'list_replays_tennis') {
                return {
                    data: {
                        rows: registro.lista ? [{
                            event_id: '35790089', competition_name: 'Challenger Prova',
                            player1_name: fx.event.player1_name, player2_name: fx.event.player2_name,
                            open_date: fx.event.open_date, n_markets: 1, n_snapshots: 3355, n_score: 104,
                            ts_min: fx.frames[0].ts, ts_max: fx.frames[fx.frames.length - 1].ts, fonte: 'import',
                        }] : [],
                    },
                    error: null,
                };
            }
            if (nome === 'get_replay_tennis_meta') {
                return {
                    data: {
                        event: { ...fx.event, competition_name: 'Challenger Prova' }, markets: fx.markets,
                        score_timeline: fx.score_timeline, ts_min: fx.frames[0].ts,
                        ts_max: fx.frames[fx.frames.length - 1].ts, inplay_from_ts: fx.frames[0].ts,
                    },
                    error: null,
                };
            }
            if (nome === 'get_replay_tennis_frames') {
                const da = new Date(String(args?.p_from_ts)).getTime();
                const a = new Date(String(args?.p_to_ts)).getTime();
                const frames = fx.frames.filter(f => {
                    const t = new Date(f.ts).getTime();
                    return t >= da && t < a;
                });
                return { data: { frames, n: frames.length }, error: null };
            }
            return risposta;
        }),
        from: () => catena(),
        channel: () => canale(),
        removeChannel: () => {},
        auth: {
            getSession: async () => ({ data: { session: null }, error: null }),
            getUser: async () => ({ data: { user: null }, error: null }),
            onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
            signOut: async () => ({ error: null }),
        },
    };
    return { supabase };
});

import TennisReplay from './TennisReplay';

const RPC_CALCIO = ['list_replays', 'get_replay', 'get_replay_meta', 'get_replay_frames'];
const P1 = (fixture as { event: { player1_name: string } }).event.player1_name;
const P2 = (fixture as { event: { player2_name: string } }).event.player2_name;

function monta() {
    return render(
        <HelmetProvider>
            <MemoryRouter initialEntries={['/tennis/replay']}>
                <TennisReplay />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

async function apriPartita() {
    const u = userEvent.setup();
    monta();
    await u.click(await screen.findByTestId('tennis-replay-partita-35790089'));
    await screen.findByTestId('tennis-replay-simulatore');
    return u;
}

beforeEach(() => {
    registro.rpc = [];
    registro.lista = true;
});

describe('Replay Tennis — elenco', () => {
    it('mostra le partite del tennis per torneo, con le sole RPC del tennis', async () => {
        monta();
        const carta = await screen.findByTestId('tennis-replay-partita-35790089');
        expect(within(carta).getByText(P1)).toBeInTheDocument();
        expect(within(carta).getByText(P2)).toBeInTheDocument();
        expect(screen.getByText('Challenger Prova')).toBeInTheDocument();
        expect(registro.rpc).toEqual(['list_replays_tennis']);
    });

    it('nessuna partita: dice come caricarle', async () => {
        registro.lista = false;
        monta();
        expect(await screen.findByTestId('tennis-replay-vuoto')).toHaveTextContent('tennis_replay.importa');
    });
});

describe('Replay Tennis — simulatore sulla partita vera', () => {
    it('punteggio tennis al cursore, mercati per categoria, nessuna RPC del calcio', async () => {
        await apriPartita();
        // cursore sul primo frame in gioco: 2o set, Barrios avanti 1 set a 0
        expect(screen.getByTestId('tennis-replay-set')).toHaveTextContent('1 - 0');
        expect(screen.getByTestId('tennis-replay-stato')).toHaveTextContent('IN GIOCO');
        expect(screen.getByTestId('tennis-replay-stato')).toHaveTextContent('5-5');
        // menu dei mercati tennis e pannello del Match Odds coi nomi dei giocatori
        expect(screen.getByRole('button', { name: /Match Odds/ })).toBeInTheDocument();
        expect(screen.getAllByText(P1).length).toBeGreaterThan(1);
        expect(registro.rpc.filter(n => RPC_CALCIO.includes(n))).toEqual([]);
        expect(registro.rpc).toContain('get_replay_tennis_meta');
        expect(registro.rpc).toContain('get_replay_tennis_frames');
    });

    it('a fine registrazione: fine partita, tabellone 6-4 5-7 6-7, simboli del tennis sulla barra', async () => {
        const u = await apriPartita();
        await u.click(screen.getByRole('button', { name: 'Salta alla fine' }));
        await waitFor(() => expect(screen.getByTestId('tennis-replay-stato')).toHaveTextContent('FINE'));
        expect(screen.getByTestId('tennis-replay-set')).toHaveTextContent('1 - 2');
        const tabellone = screen.getByTestId('tennis-replay-tabellone');
        expect(within(tabellone).getByText('6-4 5-7 6-7')).toBeInTheDocument();
        // un punteggio registrato non e' «vecchio»: niente «agg. Xs fa» del live, l'ora del punteggio
        expect(tabellone).not.toHaveTextContent(/agg\./);
        const simboli = screen.getByTestId('tennis-simboli-barra');
        const tipi = Array.from(simboli.querySelectorAll('[data-tipo]')).map(e => e.getAttribute('data-tipo'));
        expect(tipi).toEqual(['break', 'set_end', 'set_start', 'break', 'break', 'break', 'break', 'tiebreak', 'set_end', 'match_end']);
        expect(simboli).toHaveTextContent('Fine partita');
    });

    it('opportunita\': nota sui rilevatori del tennis', async () => {
        const u = await apriPartita();
        await u.click(screen.getByRole('button', { name: /Opportunità/ }));
        expect(screen.getByTestId('tennis-replay-nota-opportunita')).toHaveTextContent('microstruttura del book');
    });

    it('ladder training: «Applica bot» coi SOLI bot tennis, spento con la ragione (fase 1)', async () => {
        const u = await apriPartita();
        await u.click(screen.getByRole('button', { name: /Ladder TRAINING/ }));
        const sezione = await screen.findByTestId('tennis-applica-bot');
        const opzioni = Array.from(within(sezione).getByLabelText('Bot tennis da applicare al replay').querySelectorAll('option'))
            .map(o => o.getAttribute('value'));
        expect(opzioni).toEqual(['', 'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing', 'safe_tennis']);
        expect(opzioni.some(v => (v ?? '').includes('calcio'))).toBe(false);
        expect(within(sezione).getByRole('button', { name: /Accendi all'istante del cursore/ })).toBeDisabled();
        expect(screen.getByTestId('tennis-applica-bot-motivo')).toHaveTextContent('In arrivo');
        expect(screen.getByText(/bet-delay del mercato \(3s\)/)).toBeInTheDocument();
    });

    it('backtest col bet-delay registrato del mercato (3 s, non i 5 s del calcio)', async () => {
        const u = await apriPartita();
        await u.click(screen.getByRole('button', { name: /Backtest/ }));
        expect(await screen.findByText(/in-play col bet-delay reale \(3s\)/)).toBeInTheDocument();
    });
});
