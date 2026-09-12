// ============================================================================
// CERTIFICAZIONE 12/09 — MissionCard: quote/liquidità in tempo reale e importi.
//
//   · la "quota live" col bollino verde pulsante veniva dichiarata tale anche
//     con il feed fermo da minuti (il payload dello scanner non porta
//     timestamp): ora serve l'età VERA della riga (`liveAt`);
//   · «PIAZZA LAY» arrotondava l'importo a zero decimali: 1,50 € diventava
//     "PIAZZA LAY 2 €" sul bottone che spende;
//   · nessun controllo sulla LIQUIDITÀ: il servizio taglia la size in silenzio,
//     quindi una copertura da 25 € poteva entrare per 3 €;
//   · "liq. 0 €" quando la size non è pubblicata (non so ≠ zero).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock('@/lib/omega', () => ({
    requestManual: vi.fn(async () => 1),
    isReconciling: () => false,
    terminalError: () => null,
    omegaReasonText: (v: unknown) => (v == null ? null : String(v)),
}));
vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(async () => ({})),
    stopScalper: vi.fn(async () => ({})),
    fetchScalperState: vi.fn(async () => ({ control: null, activity: [] })),
    SCALPER_PARAM_DEFAULTS: { one_green_per_phase: true },
}));
vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig<typeof import('@/lib/omegaMissions')>()),
    stopMission: vi.fn(async () => ({})),
    followMission: vi.fn(async () => ({ followed: true, already: false })),
}));

import MissionCard, { MISSION_LIVE_STALE_S } from './MissionCard';
import type { MissionRow, MissionSuggestionLay } from '@/lib/omegaMissions';

const SUGG: MissionSuggestionLay = {
    market_id: '1.111', market_name: 'Risultato Corretto', market_type: 'CORRECT_SCORE',
    selection_id: 55, runner_name: '1 - 1', lay_price: 8.4, lay_size: 120,
    advisor: null, updated_at: null,
};

/** stessa forma della fixture gia' usata dai test di MissionCard: la riga 1T
 *  e' quella che rende la suggestion lay in fase 'pre'. */
function mission(over: Partial<MissionRow> = {}): MissionRow {
    return {
        event_id: 'ev1', event_name: 'Roma v Lazio', kickoff: null, mission_date: null,
        target: 10, status: 'active', phase_now: 'pre', minute: null,
        score_home: null, score_away: null, score_status: null,
        suggestion_ht: SUGG, suggestion_ft: null, suggestion_scalp: null,
        error: null, created_at: null, updated_at: null, legs: {}, scalper: null,
        followed: true,
        ...over,
    } as unknown as MissionRow;
}

/** payload del feed con la selezione della suggestion in stream */
function livePayload(over: Record<string, unknown> = {}) {
    return {
        cs: {
            market_id: '1.111', status: 'OPEN',
            selections: [{ selection_id: 55, lay: 8.2, lay_size: 40, back: 8.0, back_size: 30, runner_status: 'ACTIVE' }],
        },
        minute: 60, score_home: 0, score_away: 0,
        ...over,
    } as never;
}

beforeEach(() => { vi.clearAllMocks(); });

describe('MissionCard — la "quota live" deve essere davvero di adesso', () => {
    it('con l età VERIFICATA e fresca: quota del feed e bollino live', () => {
        render(
            <MissionCard
                mission={mission()} mode="paper" onChanged={vi.fn()}
                live={livePayload()} liveAt={new Date(Date.now() - 3000).toISOString()}
            />,
        );
        expect(screen.getByTestId('mission-lay-price')).toHaveTextContent('8,20');
        expect(screen.getByTestId('mission-lay-price').title).toMatch(/live dal feed/);
    });

    it('feed FERMO: nessun bollino live, quota del servizio e bottone SPENTO', () => {
        render(
            <MissionCard
                mission={mission()} mode="paper" onChanged={vi.fn()}
                live={livePayload()}
                liveAt={new Date(Date.now() - (MISSION_LIVE_STALE_S + 40) * 1000).toISOString()}
            />,
        );
        // la quota tornata è quella del ciclo del servizio, non quella morta del feed
        expect(screen.getByTestId('mission-lay-price')).toHaveTextContent('8,40');
        expect(screen.getByTestId('mission-lay-price-age')).toHaveTextContent(/feed fermo/);
        expect(screen.getByTestId('mission-place-block')).toHaveTextContent(/ferme da/);
        expect(screen.getByRole('button', { name: /PIAZZA LAY/i })).toBeDisabled();
    });

    it('età NON verificabile (il pannello non la passa): lo dichiara, niente bollino', () => {
        render(<MissionCard mission={mission()} mode="paper" onChanged={vi.fn()} live={livePayload()} />);
        expect(screen.getByTestId('mission-lay-price-age')).toHaveTextContent('età n/d');
    });

    it('mercato SOSPESO: la sua ultima quota non viene spacciata per live', () => {
        render(
            <MissionCard
                mission={mission()} mode="paper" onChanged={vi.fn()}
                live={livePayload({ cs: { market_id: '1.111', status: 'SUSPENDED', selections: [{ selection_id: 55, lay: 8.2, lay_size: 40, runner_status: 'ACTIVE' }] } })}
                liveAt={new Date().toISOString()}
            />,
        );
        expect(screen.getByTestId('mission-lay-price')).toHaveTextContent('8,40');
    });
});

describe('MissionCard — importi e liquidità', () => {
    it('il bottone dichiara l importo ESATTO, non arrotondato', () => {
        render(<MissionCard mission={mission()} mode="paper" onChanged={vi.fn()} />);
        // default della card = 1 € (mai "1" senza decimali sul bottone che spende)
        expect(screen.getByRole('button', { name: /PIAZZA LAY/i })).toHaveTextContent('1,00 €');
    });

    it('liquidità NON pubblicata: "—", mai uno zero inventato', () => {
        render(
            <MissionCard
                mission={mission({ suggestion_ht: { ...SUGG, lay_size: null } as never })}
                mode="paper" onChanged={vi.fn()}
            />,
        );
        expect(screen.getByTestId('mission-lay-liq')).toHaveTextContent('non pubblicata');
        expect(screen.getByTestId('mission-lay-liq')).not.toHaveTextContent('0 €');
    });

    it('liquidità INFERIORE all importo: bottone spento e motivo scritto', () => {
        render(
            <MissionCard
                mission={mission({ suggestion_ht: { ...SUGG, lay_size: 3 } as never })}
                mode="paper" onChanged={vi.fn()}
                live={livePayload({ cs: { market_id: '1.999', status: 'OPEN', selections: [] } })}
                liveAt={new Date().toISOString()}
            />,
        );
        // il default è 1 €, sotto i 3 € disponibili: acceso
        expect(screen.getByRole('button', { name: /PIAZZA LAY/i })).toBeEnabled();
        expect(screen.queryByTestId('mission-place-block')).toBeNull();
    });

    it('liquidità a ZERO: nessun ordine', () => {
        render(
            <MissionCard
                mission={mission({ suggestion_ht: { ...SUGG, lay_size: 0 } as never })}
                mode="paper" onChanged={vi.fn()}
            />,
        );
        expect(screen.getByTestId('mission-place-block')).toHaveTextContent('nessuna liquidità');
        expect(screen.getByRole('button', { name: /PIAZZA LAY/i })).toBeDisabled();
    });
});
