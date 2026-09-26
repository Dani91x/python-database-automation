// ============================================================================
// TennisTerminal.test.tsx - F-11 (e2e 26/09, U0361): aprire la pagina NON scrive.
//
// Il reperto: `pages/TennisTerminal.tsx` chiamava `followTennisEvent` (rpc
// `tennis_follow_event`) all'APERTURA: una lettura che scriveva, e che riportava
// a PENDING anche il follow di una partita finita (36118619, 1.262933523).
// Ora seguire e' un gesto dell'utente (bottone «Segui»).
//
// Il finto e' il CLIENT supabase (non `lib/tennis`): le funzioni vere di
// `lib/tennis` girano e ogni rpc/insert/update/upsert/delete viene registrata,
// anche quelle dei componenti figli montati con la pagina. Le righe restituite
// hanno le chiavi di `get_tennis_follows` (migrations/tennis_follow_record.sql).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

const registro = vi.hoisted(() => ({
    rpc: [] as Array<{ nome: string; args: unknown }>,
    scritture: [] as string[],
    follows: [] as Array<Record<string, unknown>>,
}));

vi.mock('@/integrations/supabase/client', () => {
    const risposta = { data: null, error: null };
    // catena `from(...).select().eq()...` che si risolve a {data:null}; i verbi
    // di scrittura vengono registrati
    const catena = (tabella: string): unknown => {
        const p: Record<string, unknown> = {};
        const self = new Proxy(p, {
            get(_t, k: string) {
                if (k === 'then') {
                    return (ok: (v: unknown) => void) => ok(risposta);
                }
                if (['insert', 'update', 'upsert', 'delete'].includes(k)) {
                    return () => { registro.scritture.push(`${tabella}.${k}`); return self; };
                }
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
        rpc: vi.fn(async (nome: string, args?: unknown) => {
            registro.rpc.push({ nome, args });
            if (nome === 'get_tennis_follows') return { data: { rows: registro.follows }, error: null };
            if (nome === 'tennis_follow_event') {
                return { data: { ...(registro.follows[0] ?? {}), status: 'PENDING' }, error: null };
            }
            return { data: null, error: null };
        }),
        from: (t: string) => catena(t),
        channel: () => canale(),
        removeChannel: () => Promise.resolve('ok'),
        auth: {
            getSession: async () => ({ data: { session: null }, error: null }),
            getUser: async () => ({ data: { user: null }, error: null }),
            onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
        },
    };
    return { supabase };
});

import TennisTerminal from './TennisTerminal';

const EV = '36118619';
const MID = '1.262933523';

/** riga di `get_tennis_follows` (chiavi della RPC vera) */
function follow(status: string): Record<string, unknown> {
    return {
        event_id: EV, competition_name: 'ITF', player1_name: 'Bondar',
        player2_name: 'Birrell', open_date: '2026-09-26T08:00:00+00:00', status,
        error_detail: null, record: false, inplay: false, score: null,
        live_status: 'SUSPENDED', updated_at: '2026-09-26T09:25:00+00:00',
    };
}

/** rpc che scrivono (tutte quelle di lib/tennis che non sono `get_*`) */
const RPC_DI_LETTURA = /^get_/;

function monta() {
    return render(
        <HelmetProvider>
            <MemoryRouter initialEntries={[`/tennis/terminal?event=${EV}&market=${MID}&p1=Bondar&p2=Birrell`]}>
                <TennisTerminal />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

describe('TennisTerminal - F-11: aprire la pagina non scrive', () => {
    beforeEach(() => {
        registro.rpc.length = 0;
        registro.scritture.length = 0;
        registro.follows = [];
    });

    it.each(['CLOSED', 'STREAMING', null])(
        'montata (follow %s) nessuna rpc di scrittura e nessun insert/update',
        async (stato) => {
            registro.follows = stato ? [follow(stato)] : [];
            monta();
            await waitFor(() => {
                expect(registro.rpc.some(r => r.nome === 'get_tennis_follows')).toBe(true);
            });
            // lascia girare gli effetti dei figli
            await new Promise(r => setTimeout(r, 50));
            const scritte = registro.rpc.filter(r => !RPC_DI_LETTURA.test(r.nome)).map(r => r.nome);
            expect(scritte).toEqual([]);
            expect(registro.scritture).toEqual([]);
        },
    );

    it('partita non seguita: la pagina lo dice e «Segui» la segue al clic', async () => {
        registro.follows = [follow('CLOSED')];
        monta();
        expect(await screen.findByText(/premi «Segui» per ladder e punteggio/)).toBeTruthy();
        await userEvent.click(screen.getByRole('button', { name: 'SEGUI' }));
        await waitFor(() => {
            expect(registro.rpc.filter(r => r.nome === 'tennis_follow_event')).toEqual([
                { nome: 'tennis_follow_event', args: { p_event_id: EV, p_market_id: MID } },
            ]);
        });
        expect(await screen.findByText('SEGUITA')).toBeTruthy();
    });

    it('partita gia seguita: nessun bottone «Segui», nessun avviso', async () => {
        registro.follows = [follow('STREAMING')];
        monta();
        expect(await screen.findByText('SEGUITA')).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'SEGUI' })).toBeNull();
        expect(screen.queryByText(/premi «Segui»/)).toBeNull();
    });
});
