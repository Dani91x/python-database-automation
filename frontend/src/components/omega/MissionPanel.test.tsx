// Test COMPONENTE per MissionPanel — pulsanti per-partita "Statistiche" e
// "Trading" (richiesta 16/07): deep-link alla scheda Dashboard (?fixture=&from=omega)
// e al LIVE TRADING (?event=&from=omega, previa RPC follow). Data-layer mockato.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
    const actual = await importOriginal<typeof import('react-router-dom')>();
    return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/lib/omega', () => ({
    requestManual: vi.fn(),
    fetchOmegaEvents: vi.fn(async () => []),
    fetchManualRequests: vi.fn(async () => []),
}));

vi.mock('@/lib/omegaMissions', () => ({
    fetchMissions: vi.fn(),
    activateMission: vi.fn(),
    followMission: vi.fn(),
    stopMission: vi.fn(),
    subscribeOmegaMissions: vi.fn(() => () => {}),
    // helper PURI: stessa semantica del modulo reale (mock totale per non
    // importare il client supabase nel test, come in LadderView.test.tsx)
    toNum: (v: unknown, dflt = 0) => (Number.isFinite(Number(v)) ? Number(v) : dflt),
    splitEventName: (name: string | null) => {
        const m = String(name ?? '').split(/ vs? /i);
        return { home: (m[0] ?? '').trim(), away: (m[1] ?? '').trim() };
    },
    missionRealized: () => 0,
}));

vi.mock('@/components/omega/MissionCard', () => ({
    default: () => <div data-testid="mission-card-stub" />,
}));

vi.mock('@/lib/sportsLogos', () => ({
    leagueLogo: () => '',
    teamLogo: () => '',
}));

import MissionPanel from './MissionPanel';
import { fetchOmegaEvents } from '@/lib/omega';
import { fetchMissions, followMission } from '@/lib/omegaMissions';

const mEvents = vi.mocked(fetchOmegaEvents);
const mMissions = vi.mocked(fetchMissions);
const mFollow = vi.mocked(followMission);

const EVENT = {
    event_id: '34009000',
    name: 'Puskas Akademia v Basaksehir',
    open_date: '2026-07-16T18:00:00Z',
    markets: [],
    competition_id: 'c1',
    competition_name: 'Conference League',
    fixture_id: 987654,
    league_id: 848,
    home_team_id: 1001,
    away_team_id: 1002,
};

const MISSION = {
    event_id: '34009000',
    event_name: 'Puskas Akademia v Basaksehir',
    kickoff: '2026-07-16T18:00:00Z',
    mission_date: new Date().toLocaleDateString('sv-SE'),
    target: 10,
    status: 'active' as const,
    phase_now: '2t' as const,
    minute: 65,
    score_home: 0,
    score_away: 2,
    score_status: 'live',
    suggestion_ht: null,
    suggestion_ft: null,
    suggestion_scalp: null,
    error: null,
    created_at: null,
    updated_at: null,
    legs: null,
    scalper: null,
    followed: false,
};

beforeEach(() => {
    vi.clearAllMocks();
    mMissions.mockResolvedValue({ missions: [], summary: { missions_total: 0, missions_active: 0 } });
    mEvents.mockResolvedValue([EVENT as never]);
    mFollow.mockResolvedValue({ followed: true, already: false });
});

function renderPanel() {
    return render(
        <MemoryRouter>
            <MissionPanel mode="paper" />
        </MemoryRouter>,
    );
}

describe('MissionPanel — pulsanti Statistiche / Trading', () => {
    it('riga evento: "Statistiche" naviga alla scheda Dashboard con ?fixture=&from=omega', async () => {
        const user = userEvent.setup();
        renderPanel();
        await screen.findByText('Puskas Akademia');
        await user.click(screen.getByRole('button', { name: /Statistiche/ }));
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard?fixture=987654&from=omega');
    });

    it('riga evento: "Trading" registra il follow e naviga a /segui-live?event=&from=omega', async () => {
        const user = userEvent.setup();
        renderPanel();
        await screen.findByText('Puskas Akademia');
        await user.click(screen.getByRole('button', { name: /Trading/ }));
        await waitFor(() => expect(mFollow).toHaveBeenCalledTimes(1));
        expect(mFollow).toHaveBeenCalledWith(
            '34009000', 'Puskas Akademia', 'Basaksehir', '2026-07-16T18:00:00Z');
        await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/segui-live?event=34009000&from=omega'));
    });

    it('senza fixture_id il pulsante Statistiche è disabilitato (nessuna scheda da aprire)', async () => {
        mEvents.mockResolvedValue([{ ...EVENT, fixture_id: null } as never]);
        renderPanel();
        await screen.findByText('Puskas Akademia');
        expect(screen.getByRole('button', { name: /Statistiche/ })).toBeDisabled();
    });

    it('se il follow fallisce NON naviga e mostra errore', async () => {
        mFollow.mockRejectedValue(new Error('rete assente'));
        const user = userEvent.setup();
        renderPanel();
        await screen.findByText('Puskas Akademia');
        await user.click(screen.getByRole('button', { name: /Trading/ }));
        await waitFor(() => expect(mFollow).toHaveBeenCalledTimes(1));
        expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('riga MISSIONE ATTIVA: i pulsanti ci sono e il click NON richiude la scheda', async () => {
        mMissions.mockResolvedValue({
            missions: [MISSION as never],
            summary: { missions_total: 1, missions_active: 1 },
        });
        mEvents.mockResolvedValue([]);
        const user = userEvent.setup();
        renderPanel();
        // missione attiva espansa di default → MissionCard visibile
        await screen.findByTestId('mission-card-stub');
        const row = screen.getByTestId('mission-card-stub').closest('div.rounded-lg')! as HTMLElement;
        // NB: l'header della missione è un div role="button" il cui accessible name
        // include il testo dei pulsanti → si seleziona il <button> VERO per tag.
        const btnOf = (re: RegExp) => within(row)
            .getAllByRole('button', { name: re })
            .find(el => el.tagName === 'BUTTON')!;
        // Statistiche: nessun fixture (né evento in cache né advisor) → disabilitato
        expect(btnOf(/Statistiche/)).toBeDisabled();
        // Trading funziona dal titolo missione e NON collassa la scheda
        await user.click(btnOf(/Trading/));
        await waitFor(() => expect(mFollow).toHaveBeenCalledTimes(1));
        expect(screen.getByTestId('mission-card-stub')).toBeInTheDocument();
    });
});
