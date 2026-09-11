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

vi.mock('@/lib/useScanLiveFeed', () => ({ useScanLiveFeed: () => ({}), liveScoreLabel: () => null }));
vi.mock('@/lib/omega', () => ({
    requestManual: vi.fn(),
    fetchOmegaEvents: vi.fn(async () => []),
    fetchManualRequests: vi.fn(async () => []),
    updateOmegaParams: vi.fn(async () => ({})),
}));
// §18: il poll dello stato scalper e UNO, a livello di pannello. Mockato: senza,
// il client Supabase VERO aprirebbe una WebSocket dal test.
vi.mock('@/lib/scalper', () => ({
    fetchScalperState: vi.fn(async () => ({ control: null, activity: [] })),
}));

vi.mock('@/lib/omegaMissions', () => ({
    fetchMissions: vi.fn(),
    activateMission: vi.fn(),
    followMission: vi.fn(),
    setFollowRecord: vi.fn(),
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
    goalProgressPct: (r: unknown, g: unknown) => {
        const rr = Number(r), gg = Number(g);
        if (!Number.isFinite(rr) || !Number.isFinite(gg) || gg <= 0) return 0;
        return Math.max(0, Math.min(100, (rr / gg) * 100));
    },
}));

vi.mock('@/components/omega/MissionCard', () => ({
    default: () => <div data-testid="mission-card-stub" />,
}));

vi.mock('@/lib/sportsLogos', () => ({
    leagueLogo: () => '',
    teamLogo: () => '',
}));

import MissionPanel from './MissionPanel';
import { fetchOmegaEvents, updateOmegaParams } from '@/lib/omega';
import { fetchScalperState } from '@/lib/scalper';
import { fetchMissions, followMission, setFollowRecord } from '@/lib/omegaMissions';

const mEvents = vi.mocked(fetchOmegaEvents);
const mMissions = vi.mocked(fetchMissions);
const mFollow = vi.mocked(followMission);
const mSetRecord = vi.mocked(setFollowRecord);

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

    it('"Trading" NON attiva la registrazione (solo follow + navigazione)', async () => {
        const user = userEvent.setup();
        renderPanel();
        await screen.findByText('Puskas Akademia');
        await user.click(screen.getByRole('button', { name: /Trading/ }));
        await waitFor(() => expect(mFollow).toHaveBeenCalledTimes(1));
        expect(mSetRecord).not.toHaveBeenCalled();
    });

    it('"Segui live" attiva la registrazione: follow + set_follow_record(true) e badge REC', async () => {
        const user = userEvent.setup();
        renderPanel();
        await screen.findByText('Puskas Akademia');
        await user.click(screen.getByRole('button', { name: /Segui live/ }));
        await waitFor(() => expect(mSetRecord).toHaveBeenCalledWith('34009000', true));
        // il follow è prerequisito del flag (idempotente)
        expect(mFollow).toHaveBeenCalledWith(
            '34009000', 'Puskas Akademia', 'Basaksehir', '2026-07-16T18:00:00Z');
        // stato attivo visibile: il pulsante diventa REC
        await screen.findByRole('button', { name: /REC/ });
        // niente navigazione: la registrazione non apre il trading
        expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('REC attivo (recording=true dal DB): il click SPEGNE la registrazione', async () => {
        mMissions.mockResolvedValue({
            missions: [{ ...MISSION, followed: true, recording: true } as never],
            summary: { missions_total: 1, missions_active: 1 },
        });
        mEvents.mockResolvedValue([]);
        const user = userEvent.setup();
        renderPanel();
        await screen.findByTestId('mission-card-stub');
        const row = screen.getByTestId('mission-card-stub').closest('div.rounded-lg')! as HTMLElement;
        const rec = within(row).getAllByRole('button', { name: /REC/ })
            .find(el => el.tagName === 'BUTTON')!;
        await user.click(rec);
        await waitFor(() => expect(mSetRecord).toHaveBeenCalledWith('34009000', false));
        expect(mFollow).not.toHaveBeenCalled();   // spegnere non ricrea il follow
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

// ===========================================================================
// Certificazione 11/09: "Salva obiettivo" (M-08) e poll unico dello scalper
// ===========================================================================
describe('MissionPanel — obiettivo di giornata e poll dello scalper', () => {
    const mUpdate = vi.mocked(updateOmegaParams);
    const mScalper = vi.mocked(fetchScalperState);

    /** una missione ATTIVA e SEGUITA (ha un bot scalper da interrogare) */
    function missione(over: Record<string, unknown> = {}) {
        return {
            event_id: 'ev1', event_name: 'Roma vs Lazio', kickoff: null, mission_date: null,
            target: 10, status: 'active', phase_now: '1t', minute: 20,
            score_home: 0, score_away: 0, score_status: null,
            suggestion_ht: null, suggestion_ft: null, suggestion_scalp: null,
            error: null, created_at: null, updated_at: null, legs: {},
            scalper: null, followed: true, ...over,
        };
    }

    beforeEach(() => {
        vi.mocked(fetchMissions).mockResolvedValue({
            missions: [missione()], summary: { active: 1, total: 1 },
        } as never);
        vi.mocked(fetchOmegaEvents).mockResolvedValue([] as never);
    });

    function renderPanel(dailyGoal = 250) {
        return render(<MemoryRouter><MissionPanel mode="paper" dailyGoal={dailyGoal} /></MemoryRouter>);
    }

    it('M-08: l obiettivo modificato viene SCRITTO sul control (non solo mostrato)', async () => {
        const user = userEvent.setup();
        renderPanel(250);
        const input = await screen.findByDisplayValue('250');
        await user.clear(input);
        await user.type(input, '400');
        // finche non e salvato la UI DICHIARA che il servizio usa ancora il vecchio
        expect(await screen.findByText(/obiettivo non salvato/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Salva' }));
        await waitFor(() => expect(mUpdate).toHaveBeenCalledWith({ dailyGoal: 400 }));
    });

    it('obiettivo NON modificato: nessun avviso di "non salvato"', async () => {
        renderPanel(250);
        await screen.findByDisplayValue('250');
        expect(screen.queryByText(/obiettivo non salvato/i)).toBeNull();
    });

    it('§18: UN solo poll dello scalper per il pannello, in SERIE sulle missioni seguite', async () => {
        vi.mocked(fetchMissions).mockResolvedValue({
            missions: [missione(), missione({ event_id: 'ev2' }), missione({ event_id: 'ev3' })],
            summary: { active: 3, total: 3 },
        } as never);
        renderPanel();
        await waitFor(() => expect(mScalper).toHaveBeenCalledTimes(3));
        // una chiamata per evento, senza attivita (activityLimit 0: solo lo stato)
        expect(mScalper.mock.calls.map((c) => c[0]).sort()).toEqual(['ev1', 'ev2', 'ev3']);
        for (const c of mScalper.mock.calls) expect(c[1]).toBe(0);
    });

    it('§18: le missioni FINITE o non seguite non hanno un bot da interrogare', async () => {
        vi.mocked(fetchMissions).mockResolvedValue({
            missions: [
                missione({ event_id: 'finita', phase_now: 'finita' }),
                missione({ event_id: 'nonseguita', followed: false }),
                missione({ event_id: 'viva' }),
            ],
            summary: { active: 3, total: 3 },
        } as never);
        renderPanel();
        await waitFor(() => expect(mScalper).toHaveBeenCalledTimes(1));
        expect(mScalper.mock.calls[0][0]).toBe('viva');
    });
});
