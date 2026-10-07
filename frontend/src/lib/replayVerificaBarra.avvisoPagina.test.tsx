// ============================================================================
// 07/10 - L'AVVISO DI COERENZA E' NELLA PAGINA VERA (Match Replay).
//
// QUESTO TEST E' ROSSO FINCHE' `pages/MatchReplay.tsx` NON MONTA `AvvisoCoerenzaBarra`
// (patch nel referto `AUDIT_2026-10-07/REPLAY_BARRA_STANDARD.md` e in
// `AUDIT_2026-10-07/REPLAY_BARRA_STANDARD_pagina.patch`: la pagina e' di un altro
// delegato, non toccata qui). Verde con la patch applicata (provato su una copia della
// pagina, poi cancellata).
//   - partita coerente  -> nessun avviso;
//   - partita con una barra che non torna (due fonti discordanti sul punteggio) -> avviso.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import type { ReplayData } from '@/lib/live';

const stato = vi.hoisted(() => ({ dati: null as unknown, casa: '' }));
vi.mock('@/lib/live', async () => {
    const actual = await vi.importActual<typeof import('@/lib/live')>('@/lib/live');
    return {
        ...actual,
        fetchReplayList: vi.fn(async () => [{
            event_id: '1', fixture_id: null, league_id: null, league_name: 'Lega', home_name: stato.casa, away_name: 'Ospiti',
            open_date: '2026-07-10T19:00:00Z', status: 'UPLOADED', n_markets: 2, n_snapshots: 1, started_at: null, ended_at: null,
        }]),
        fetchReplayChunked: vi.fn(async () => stato.dati),
    };
});

import MatchReplay from '@/pages/MatchReplay';
import { apriReplay } from './__fixtures__/replayBarraPagina';
import { caricaPartita, eventiConFixture } from './__fixtures__/replayBarraTutte';

afterEach(() => { stato.dati = null; });

function conFonteInRitardo(replay: ReplayData): ReplayData {
    const g = replay.score_timeline.find(x => (x.score_home ?? 0) > 0);
    if (!g) throw new Error('la partita deve avere un gol');
    const tardi = new Date(Date.parse(g.ts) + 5000).toISOString().replace('Z', '+00:00');
    return { ...replay, score_timeline: [...replay.score_timeline, { ...g, ts: tardi, source: 'api_football', score_home: 0, score_away: 0 }] };
}

describe.each(eventiConFixture())('Match Replay - avviso di coerenza della barra, partita %s', (ev) => {
    it('barra coerente: nessun avviso nella pagina', async () => {
        stato.dati = caricaPartita(ev).replay;
        stato.casa = `Casa${ev}`;
        await apriReplay(<MatchReplay />, stato.casa);
        expect(screen.queryByTestId('avviso-coerenza-barra')).toBeNull();
    }, 60_000);

    it('barra che non torna: la pagina mostra l\'avviso con il motivo', async () => {
        stato.dati = conFonteInRitardo(caricaPartita(ev).replay);
        stato.casa = `Casa${ev}`;
        await apriReplay(<MatchReplay />, stato.casa);
        const a = screen.getByTestId('avviso-coerenza-barra');
        expect(within(a).getAllByTestId('avviso-coerenza-voce')[0]).toHaveTextContent('TABELLONE_SCENDE');
    }, 60_000);
});
