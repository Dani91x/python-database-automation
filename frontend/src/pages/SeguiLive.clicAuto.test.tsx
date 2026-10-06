// 06/10 — la PAGINA: cliccare una partita seguita in automatico dai bot la
// APRE (RPC segui_live_apri_partita); una partita manuale no. Prima il clic
// faceva solo setSelected e l'attesa del ladder non finiva mai.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router-dom';
import type { LiveFollow } from '@/lib/live';

const { apriMock, righe } = vi.hoisted(() => ({
    apriMock: vi.fn(),
    righe: { lista: [] as LiveFollow[] },
}));

vi.mock('@/integrations/supabase/client', () => {
    const channelStub: Record<string, unknown> = {};
    channelStub.on = () => channelStub;
    channelStub.subscribe = () => channelStub;
    const q: Record<string, unknown> = {};
    for (const k of ['select', 'eq', 'in', 'order', 'limit', 'gte', 'lte', 'neq', 'is']) {
        q[k] = () => q;
    }
    q.maybeSingle = async () => ({ data: null, error: null });
    q.single = async () => ({ data: null, error: null });
    q.then = (res: (v: unknown) => unknown) => Promise.resolve({ data: [], error: null }).then(res);
    return {
        supabase: {
            rpc: vi.fn(async () => ({ data: { rows: [] }, error: null })),
            from: () => q,
            channel: () => channelStub,
            removeChannel: vi.fn(),
        },
    };
});

vi.mock('@/lib/live', async (importOriginal) => {
    const vero = await importOriginal<typeof import('@/lib/live')>();
    return {
        ...vero,
        fetchLiveFollows: vi.fn(async () => righe.lista),
        fetchLiveNow: vi.fn(async () => null),
        subscribeLiveNow: vi.fn(() => () => {}),
        subscribeLiveFollowEvent: vi.fn(() => () => {}),
        apriPartitaSeguiLive: apriMock,
    };
});

vi.mock('@/lib/liveOrders', async (importOriginal) => {
    const vero = await importOriginal<typeof import('@/lib/liveOrders')>();
    return {
        ...vero,
        fetchLiveHeartbeat: vi.fn(async () => null),
        subscribeLiveHeartbeat: vi.fn(() => () => {}),
    };
});

vi.mock('@/components/live/HabitatCard', () => ({ HabitatCard: () => null }));

import SeguiLive from './SeguiLive';

function riga(origine: LiveFollow['origine']): LiveFollow {
    // chiavi vere di get_live_follows (migrazione live_follow_origine_2026-09-25.sql)
    return {
        event_id: '35800001', fixture_id: null, league_name: 'Serie A',
        home_name: 'Casa', away_name: 'Ospiti', open_date: '2026-10-06T18:00:00Z',
        status: 'STREAMING', error_detail: null, inplay: false, minute: null,
        score_home: null, score_away: null, live_status: null, score_source: null,
        updated_at: null, origine,
    };
}

async function clicca(): Promise<void> {
    render(<HelmetProvider><MemoryRouter><SeguiLive /></MemoryRouter></HelmetProvider>);
    const nomi = await screen.findAllByText(/Casa/);
    fireEvent.click(nomi[0]);
}

beforeEach(() => {
    apriMock.mockReset();
    apriMock.mockResolvedValue({ promossa: true });
});

describe('Segui Live - clic su una partita', () => {
    it('partita dei bot (origine auto): la apre col runner', async () => {
        righe.lista = [riga('auto')];
        await clicca();
        await waitFor(() => expect(apriMock).toHaveBeenCalledWith('35800001'));
        expect(await screen.findByText(/Partita seguita in automatico dai bot/)).toBeTruthy();
    });

    it('partita manuale: nessuna apertura (e\' gia\' del terminale)', async () => {
        righe.lista = [riga('manuale')];
        await clicca();
        await screen.findByText('Primo dato ladder');
        expect(apriMock).not.toHaveBeenCalled();
    });
});
