// Test degli helper PURI di omegaMissions (money-critical: mai NaN, gap
// corretto anche con legs/scalper mancanti) + render minimo di MissionPanel
// con data-layer mockato (stesso pattern di Omega.test.tsx).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createElement } from 'react';
import { render, screen } from '@testing-library/react';

// ---- mock hoisted: supabase (usato dalla lib), sonner, lib omega/scalper ----
vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

const { rpcMock } = vi.hoisted(() => ({ rpcMock: vi.fn() }));
vi.mock('@/integrations/supabase/client', () => {
    const channelStub: Record<string, unknown> = {};
    channelStub.on = () => channelStub;
    channelStub.subscribe = () => channelStub;
    return {
        supabase: {
            rpc: rpcMock,
            channel: () => channelStub,
            removeChannel: vi.fn(),
        },
    };
});

vi.mock('@/lib/omega', () => ({
    requestManual: vi.fn(async () => 1),
    fetchOmegaEvents: vi.fn(async () => []),
}));

vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(),
    stopScalper: vi.fn(),
    SCALPER_PARAM_DEFAULTS: {},
}));

import {
    toNum, splitEventName, missionLegsRealized, missionRealized, missionGap,
    formatAdvisorParts, advisorTooltip,
    type MissionAdvisor, type MissionRow,
} from './omegaMissions';
import MissionPanel from '@/components/omega/MissionPanel';

// ------------------------------------------------------------ helper puri
describe('toNum', () => {
    it('numeri validi passano, spazzatura → fallback (mai NaN)', () => {
        expect(toNum(3.5)).toBe(3.5);
        expect(toNum('2.5')).toBe(2.5);
        expect(toNum(undefined)).toBe(0);
        expect(toNum(null)).toBe(0);
        expect(toNum('abc')).toBe(0);
        expect(toNum(NaN, 7)).toBe(7);
        expect(toNum(Infinity)).toBe(0);
    });
});

describe('splitEventName', () => {
    it("split su ' v ' (Betfair)", () => {
        expect(splitEventName('Roma v Lazio')).toEqual({ home: 'Roma', away: 'Lazio' });
    });
    it("fallback ' vs ' — NON spezza dentro come farebbe split(' v ')", () => {
        expect(splitEventName('Roma vs Lazio')).toEqual({ home: 'Roma', away: 'Lazio' });
    });
    it('nome senza separatore → tutto in home, away vuoto', () => {
        expect(splitEventName('Finale Coppa')).toEqual({ home: 'Finale Coppa', away: '' });
    });
    it('null/undefined → stringhe vuote', () => {
        expect(splitEventName(null)).toEqual({ home: '', away: '' });
        expect(splitEventName(undefined)).toEqual({ home: '', away: '' });
    });
    it("squadre con la 'v' nel nome restano intere", () => {
        expect(splitEventName('Valencia v Villarreal')).toEqual({ home: 'Valencia', away: 'Villarreal' });
    });
});

describe('missionGap / missionRealized', () => {
    it('senza legs né scalper il gap è il target pieno', () => {
        expect(missionGap({ target: 10, legs: null, scalper: null })).toBe(10);
        expect(missionRealized({ legs: null, scalper: null })).toBe(0);
    });
    it('somma realized delle gambe + pnl_locked dello scalper REALE', () => {
        const m = {
            target: 10,
            legs: {
                ht_cs: { realized: 2, open_liability: 0, n_open: 0, n_settled: 1, trades: [] },
                scalp: { realized: 1.5, open_liability: 0, n_open: 0, n_settled: 1, trades: [] },
            },
            scalper: { status: 'done', dry_run: false, pnl_locked: 0.5 },
        };
        expect(missionLegsRealized(m)).toBe(3.5);
        expect(missionRealized(m)).toBe(4);
        expect(missionGap(m)).toBe(6);
    });
    it('scalper DRY-RUN = P&L simulato: MAI sommato al realizzato (audit H2)', () => {
        const m = {
            target: 10,
            legs: { ht_cs: { realized: 2, open_liability: 0, n_open: 0, n_settled: 1, trades: [] } },
            scalper: { status: 'done', dry_run: true, pnl_locked: 3 },
        };
        expect(missionRealized(m)).toBe(2);      // il +3 simulato non conta
        expect(missionGap(m)).toBe(8);           // il gap resta da coprire a soldi veri
        // dry_run assente/null = prudenza: trattato come simulato
        expect(missionRealized({ legs: null, scalper: { status: 'done', dry_run: null as unknown as boolean, pnl_locked: 3 } })).toBe(0);
    });
    it('gamba con realized mancante/spazzatura conta 0 (mai NaN)', () => {
        const m = {
            target: 8,
            legs: { ft_cs: { realized: 'x' as unknown as number, open_liability: null, n_open: null, n_settled: null, trades: [] } },
            scalper: { status: 'running', dry_run: true, pnl_locked: null },
        };
        expect(missionRealized(m)).toBe(0);
        expect(missionGap(m)).toBe(8);
    });
    it('target mancante → gap negativo del realizzato (0 − realized)', () => {
        const m = {
            target: null,
            legs: { ht_cs: { realized: 3, open_liability: 0, n_open: 0, n_settled: 1, trades: [] } },
            scalper: null,
        };
        expect(missionGap(m)).toBe(-3);
    });
});

// --------------------------------------------- CONSULENTE DATI (advisor)
describe('formatAdvisorParts / advisorTooltip', () => {
    const FULL: MissionAdvisor = {
        matched_fixture_id: 77,
        poisson_prob: 0.007,
        freq_league: { p: 0.008, n: 300 },
        h2h: { n_meetings: 6, n_score: 0 },
        sources: { poisson: 'fonte A', freq_league: 'fonte B' },
    };
    it('advisor completo → tre segnali formattati', () => {
        expect(formatAdvisorParts(FULL)).toEqual([
            'Poisson ~1/143',
            'Lega 0.8% (n=300)',
            'H2H mai in 6 scontri',
        ]);
    });
    it('H2H con occorrenze → "k/n scontri"', () => {
        expect(formatAdvisorParts({ ...FULL, h2h: { n_meetings: 14, n_score: 2 } }))
            .toContain('H2H 2/14 scontri');
    });
    it('advisor null/assente → nessuna riga (la UI non mostra nulla)', () => {
        expect(formatAdvisorParts(null)).toEqual([]);
        expect(formatAdvisorParts(undefined)).toEqual([]);
    });
    it('segnali mancanti spariscono senza NaN (best-effort dichiarato)', () => {
        expect(formatAdvisorParts({
            matched_fixture_id: 77, poisson_prob: null,
            freq_league: null, h2h: null, sources: null,
        })).toEqual([]);
        expect(formatAdvisorParts({ ...FULL, poisson_prob: 'x' as unknown as number }))
            .toEqual(['Lega 0.8% (n=300)', 'H2H mai in 6 scontri']);
    });
    it('tooltip = fonti una per riga; vuoto senza sources', () => {
        expect(advisorTooltip(FULL)).toBe('fonte A\nfonte B');
        expect(advisorTooltip(null)).toBe('');
        expect(advisorTooltip({ ...FULL, sources: null })).toBe('');
    });
});

// ------------------------------------------------- render minimo del panel
const MISSION: MissionRow = {
    event_id: 'ev1',
    event_name: 'Roma v Lazio',
    kickoff: new Date().toISOString(),
    // OGGI: la barra di giornata somma solo le missioni di oggi (review 16/07)
    mission_date: new Date().toLocaleDateString('sv-SE'),
    target: 10,
    status: 'active',
    phase_now: '1t',
    minute: 33,
    score_home: 1,
    score_away: 0,
    score_status: 'live',
    suggestion_ht: null,
    suggestion_ft: null,
    suggestion_scalp: null,
    error: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    legs: { ht_cs: { realized: 2, open_liability: 0, n_open: 0, n_settled: 1, trades: [] } },
    scalper: { status: 'done', dry_run: true, pnl_locked: 1.5 },
    followed: true,
};

describe('MissionPanel (render minimo)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        rpcMock.mockResolvedValue({
            data: { missions: [MISSION], summary: { missions_total: 1, missions_active: 1 } },
            error: null,
        });
    });

    it('mostra header giornata e la missione attiva con punteggio live', async () => {
        render(createElement(MissionPanel, { mode: 'paper' }));
        expect(await screen.findByText('Obiettivo giornata €')).toBeInTheDocument();
        expect(await screen.findByText('Roma v Lazio')).toBeInTheDocument();
        // punteggio LIVE grande e fase; la scheda attiva è AUTO-ESPANSA (16/07)
        // quindi '1T' appare sia come badge fase sia come riga della card
        expect(await screen.findByText('1 - 0')).toBeInTheDocument();
        expect((await screen.findAllByText('1T')).length).toBeGreaterThanOrEqual(1);
        // con la card espansa i pulsanti missione sono SUBITO visibili
        expect(await screen.findByText('Pausa')).toBeInTheDocument();
        expect(await screen.findByText('Chiudi missione')).toBeInTheDocument();
        // realized = 2 (gamba); l'1.5 dello scalper è DRY-RUN → simulato,
        // NON sommato (audit H2). Compare sia nella barra di giornata sia
        // nella riga della missione.
        expect((await screen.findAllByText('+€2.00')).length).toBeGreaterThanOrEqual(2);
        expect(screen.queryByText('+€3.50')).toBeNull();
    });
});
