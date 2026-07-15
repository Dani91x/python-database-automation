// Test COMPONENTE per MissionCard (review 15/07 — MEDIUM). Data-layer e
// sonner mockati; gli helper PURI di omegaMissions restano REALI (il
// componente li usa per gap/size/advisor). Verifiche MONEY-CRITICAL:
//   1. il payload di requestManual è ESATTAMENTE lo snapshot della suggestion
//      mostrata (market_id/selection_id/price/size/phase — mai derivati);
//   2. se la suggestion cambia (mercato o prezzo) col dialog aperto, la bozza
//      congelata è STANTIA → il dialog si chiude;
//   3. l'advisor (blocco SOLO informativo) che cambia da solo NON chiude il
//      dialog e NON altera il payload;
//   4. la size dello scalp è cappata alla liquidità mostrata al best.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), {
        success: vi.fn(), error: vi.fn(), warning: vi.fn(),
    }),
}));

vi.mock('@/lib/omega', () => ({
    requestManual: vi.fn(async () => 1),
}));

vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(async () => ({})),
    stopScalper: vi.fn(async () => ({})),
    SCALPER_PARAM_DEFAULTS: { one_green_per_phase: true },
}));

// Solo le RPC sono mockate: gli helper puri (toNum, missionGap, splitEventName,
// formatAdvisorParts, advisorTooltip) sono quelli veri, già testati a parte.
vi.mock('@/lib/omegaMissions', async importOriginal => {
    const actual = await importOriginal<typeof import('@/lib/omegaMissions')>();
    return {
        ...actual,
        stopMission: vi.fn(async () => ({})),
        followMission: vi.fn(async () => ({ followed: true, already: false })),
    };
});

import MissionCard from './MissionCard';
import { requestManual } from '@/lib/omega';
import { toast } from 'sonner';
import type {
    MissionRow, MissionSuggestionLay, MissionSuggestionScalp,
} from '@/lib/omegaMissions';

const mRequest = vi.mocked(requestManual);

// ------------------------------------------------------------------ fixture
const SUGG_HT: MissionSuggestionLay = {
    market_id: '1.111',
    market_name: 'Risultato Corretto 1T',
    market_type: 'HALF_TIME_SCORE',
    selection_id: 55,
    runner_name: '1 - 1',
    lay_price: 8.4,
    lay_size: 120,
    advisor: null,
    updated_at: null,
};

const SUGG_SCALP: MissionSuggestionScalp = {
    market_id: '1.222',
    market_name: 'Over/Under 2.5 Goals',
    market_type: 'OVER_UNDER_25',
    selection_id: 77,
    runner_name: 'Under 2.5',
    back_price: 1.62,
    back_size: 60,      // liquidità al best: SOTTO il default €100 della UI
    line: 2.5,
    updated_at: null,
};

function makeMission(over: Partial<MissionRow> = {}): MissionRow {
    return {
        event_id: 'ev1',
        event_name: 'Roma v Lazio',
        kickoff: null,
        mission_date: null,
        target: 10,
        status: 'active',
        phase_now: 'pre',
        minute: null,
        score_home: null,
        score_away: null,
        score_status: null,
        suggestion_ht: SUGG_HT,
        suggestion_ft: null,
        suggestion_scalp: SUGG_SCALP,
        error: null,
        created_at: null,
        updated_at: null,
        legs: {},
        scalper: null,
        followed: true,
        ...over,
    };
}

function renderCard(mission: MissionRow) {
    return render(<MissionCard mission={mission} mode="paper" onChanged={() => {}} />);
}

// Apre il dialog dalla riga 1T e ne attende la comparsa.
async function openLayDialog(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /PIAZZA LAY/ }));
    expect(await screen.findByText('Conferma ordine (PAPER)')).toBeInTheDocument();
}

beforeEach(() => {
    vi.clearAllMocks();
});

describe('MissionCard — piazzamento manuale (money-critical)', () => {
    it('PIAZZA LAY → payload requestManual con ESATTAMENTE i campi della suggestion', async () => {
        const user = userEvent.setup();
        renderCard(makeMission());
        await openLayDialog(user);

        await user.click(screen.getByRole('button', { name: 'Piazza (paper)' }));

        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(1));
        expect(mRequest).toHaveBeenCalledWith('place', {
            event_id: 'ev1',
            event_name: 'Roma v Lazio',
            market_id: SUGG_HT.market_id,          // '1.111'
            selection_id: SUGG_HT.selection_id,    // 55
            runner_name: SUGG_HT.runner_name,      // '1 - 1'
            side: 'lay',
            mode: 'paper',
            price: 8.4,                            // lay_price mostrato
            size: 1,                               // default €1 della riga 1T
            phase: 'ht_cs',
        });
    });

    it('suggestion che cambia MERCATO col dialog aperto → dialog chiuso (bozza stantia)', async () => {
        const user = userEvent.setup();
        const { rerender } = renderCard(makeMission());
        await openLayDialog(user);

        // il servizio propone un ALTRO mercato/selezione: la fotografia è superata
        rerender(<MissionCard
            mission={makeMission({
                suggestion_ht: { ...SUGG_HT, market_id: '1.999', selection_id: 88 },
            })}
            mode="paper" onChanged={() => {}}
        />);

        await waitFor(() => {
            expect(screen.queryByText('Conferma ordine (PAPER)')).not.toBeInTheDocument();
        });
        expect(toast.warning).toHaveBeenCalled();
        expect(mRequest).not.toHaveBeenCalled();
    });

    it('suggestion che cambia PREZZO col dialog aperto → dialog chiuso (bozza stantia)', async () => {
        const user = userEvent.setup();
        const { rerender } = renderCard(makeMission());
        await openLayDialog(user);

        rerender(<MissionCard
            mission={makeMission({ suggestion_ht: { ...SUGG_HT, lay_price: 9.2 } })}
            mode="paper" onChanged={() => {}}
        />);

        await waitFor(() => {
            expect(screen.queryByText('Conferma ordine (PAPER)')).not.toBeInTheDocument();
        });
        expect(toast.warning).toHaveBeenCalled();
        expect(mRequest).not.toHaveBeenCalled();
    });

    it('advisor che cambia da solo: dialog APERTO e payload INVARIATO (advisor solo display)', async () => {
        const user = userEvent.setup();
        const { rerender } = renderCard(makeMission());
        await openLayDialog(user);

        // arriva il consulente dati: stessi id/prezzo, cambia SOLO il blocco informativo
        rerender(<MissionCard
            mission={makeMission({
                suggestion_ht: {
                    ...SUGG_HT,
                    advisor: {
                        matched_fixture_id: 42,
                        poisson_prob: 0.05,
                        freq_league: { p: 0.08, n: 300 },
                        h2h: { n_meetings: 6, n_score: 0 },
                        sources: null,
                    },
                },
            })}
            mode="paper" onChanged={() => {}}
        />);

        // il dialog resta aperto: la bozza NON è stantia
        expect(screen.getByText('Conferma ordine (PAPER)')).toBeInTheDocument();
        expect(toast.warning).not.toHaveBeenCalled();

        await user.click(screen.getByRole('button', { name: 'Piazza (paper)' }));
        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(1));
        expect(mRequest).toHaveBeenCalledWith('place', expect.objectContaining({
            market_id: SUGG_HT.market_id,
            selection_id: SUGG_HT.selection_id,
            price: 8.4,
            size: 1,
            phase: 'ht_cs',
        }));
    });

    it('SCALPA: size cappata alla liquidità mostrata al best', async () => {
        const user = userEvent.setup();
        renderCard(makeMission());

        // default UI €100 > liq. €60 → avviso e cap
        expect(screen.getByText(/importo limitato a €60/)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /SCALPA/ }));
        expect(await screen.findByText('Conferma ordine (PAPER)')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Piazza (paper)' }));

        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(1));
        expect(mRequest).toHaveBeenCalledWith('place', {
            event_id: 'ev1',
            event_name: 'Roma v Lazio',
            market_id: SUGG_SCALP.market_id,        // '1.222'
            selection_id: SUGG_SCALP.selection_id,  // 77
            runner_name: SUGG_SCALP.runner_name,    // 'Under 2.5'
            side: 'back',
            mode: 'paper',
            price: 1.62,
            size: 60,                               // cap ≤ back_size (mai 100)
            phase: 'scalp',
        });
    });
});
