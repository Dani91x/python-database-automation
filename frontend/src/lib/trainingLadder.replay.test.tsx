// ============================================================================
// F41 — REGRESSIONE "ladder solo su Match Odds": il Ladder TRAINING del replay
// deve renderizzare QUALSIASI mercato registrato, non solo MATCH_ODDS.
// Fixture = dati REALI dal DB (VPS-SJK): CORRECT_SCORE (19 selezioni → selettore
// una-alla-volta) e HALF_TIME (3 selezioni affiancate, ladder SENZA ltp/trd).
// Il wiring replica MatchReplay.tsx: frameToLadderRow + createTrainingApi.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/live', async () => {
    const actual = await vi.importActual<typeof import('@/lib/live')>('@/lib/live');
    return {
        ...actual,
        fetchLiveLadder: vi.fn(),
        subscribeLiveLadder: vi.fn(() => () => {}),
    };
});
vi.mock('@/lib/liveOrders', () => ({
    fetchLiveOrders: vi.fn(async () => []),
    fetchLivePositions: vi.fn(async () => []),
    sendLiveOrderCommand: vi.fn(),
    sendGreenup: vi.fn(),
    requestRiskRule: vi.fn(),
    subscribeLiveOrders: vi.fn(() => () => {}),
    subscribeLivePositions: vi.fn(() => () => {}),
}));

import { LadderView, type LadderSource } from '@/components/live/LadderView';
import { createTrainingApi, frameToLadderRow } from '@/lib/trainingLadder';
import type { BookSnapshot } from '@/lib/matching';
import type { Frame, Market, LiveLadderRow } from '@/lib/live';
import fixture from './__fixtures__/replay_nonmo_markets.json';

interface Fx { market: Market; frames: Frame[] }
const FX = fixture as unknown as Record<'CORRECT_SCORE' | 'HALF_TIME', Fx>;

// wiring identico a MatchReplay: snapshot per (mercato, selezione) dal frame reale
function buildHarness(fx: Fx) {
    const frames = [...fx.frames].sort((a, b) => (a.ts < b.ts ? -1 : 1));
    const lastTs = new Date(frames[frames.length - 1].ts).getTime();
    const getSnaps = (_mid: string, sid: number): BookSnapshot[] =>
        frames.map(f => {
            const e = f.ladder?.[String(sid)];
            return {
                ts: new Date(f.ts).getTime(),
                back: e?.back ?? [],
                lay: e?.lay ?? [],
                ltp: e?.ltp ?? null,
                tv: e?.tv ?? null,
                trd: e?.trd,
                status: f.status,
            };
        });
    const api = createTrainingApi({
        eventId: 'e-test',
        getSnaps,
        getNow: () => lastTs,
        isInplayAt: () => false,
    });
    const names = new Map<number, string>(
        (fx.market.selections ?? []).map(s => [s.selection_id, s.name ?? `#${s.selection_id}`]),
    );
    const row: LiveLadderRow = frameToLadderRow({
        eventId: 'e-test',
        marketId: fx.market.market_id,
        marketType: fx.market.market_type,
        marketName: fx.market.market_name,
        status: frames[frames.length - 1].status,
        nowMs: lastTs,
        ladder: frames[frames.length - 1].ladder,
        names,
    });
    const source: LadderSource = {
        fetch: async () => row,
        subscribe: () => () => {},
    };
    return { api, source, row };
}

describe('Ladder TRAINING su mercati NON Match Odds (dati reali)', () => {
    it('CORRECT_SCORE (19 selezioni): renderizza il ladder con righe di prezzo', async () => {
        const fx = FX.CORRECT_SCORE;
        const { api, source, row } = buildHarness(fx);
        expect(row.ladder?.selections.length).toBe(19);

        const { container } = render(
            <LadderView
                marketId={fx.market.market_id}
                orderMode="paper"
                sport="calcio"
                ladderSource={source}
                orderApi={api}
                fallbackSelections={(fx.market.selections ?? []).map(s => ({ selection_id: s.selection_id, name: s.name ?? '' }))}
            />,
        );
        await waitFor(() => expect(screen.getByText(fx.market.market_name!)).toBeTruthy());
        // con >3 selezioni compare il selettore e UNA ladder alla volta: devono
        // esserci righe di prezzo (celle back/lay renderizzate)
        await waitFor(() => {
            const priceCells = container.querySelectorAll('[title^="BACK"], [title^="LAY"]');
            expect(priceCells.length).toBeGreaterThan(0);
        });
    });

    it('HALF_TIME (senza ltp/trd): renderizza le 3 selezioni con i prezzi del book', async () => {
        const fx = FX.HALF_TIME;
        const { api, source, row } = buildHarness(fx);
        expect(row.ladder?.selections.length).toBe(3);
        // il fixture reale NON ha ltp per questo mercato: il centro-vista deve
        // ripiegare su best back/lay senza righe vuote
        expect(row.ladder?.selections.every(s => s.ltp == null)).toBe(true);

        const { container } = render(
            <LadderView
                marketId={fx.market.market_id}
                orderMode="paper"
                sport="calcio"
                ladderSource={source}
                orderApi={api}
                fallbackSelections={(fx.market.selections ?? []).map(s => ({ selection_id: s.selection_id, name: s.name ?? '' }))}
            />,
        );
        await waitFor(() => expect(screen.getByText(fx.market.market_name!)).toBeTruthy());
        for (const s of fx.market.selections) {
            expect(screen.getAllByText(s.name!).length).toBeGreaterThan(0);
        }
        await waitFor(() => {
            const priceCells = container.querySelectorAll('[title^="BACK"], [title^="LAY"]');
            expect(priceCells.length).toBeGreaterThan(0);
        });
    });
});
