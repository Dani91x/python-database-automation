// ============================================================================
// 07/10 - IL VERIFICATORE E LA PAGINA VERA DICONO LA STESSA COSA? (aderenza)
//
// `replayVerificaBarra*.ts` costruisce la barra con le stesse funzioni che la pagina
// `pages/MatchReplay.tsx` ha (o avra', dopo la patch del referto, in comune): i passi
// da 10 s, il calcio d'inizio, i segmenti di sospensione, i simboli, il tabellone.
// Finche' la pagina ha una copia in linea di qualcuna di queste logiche, questo test
// MONTA LA PAGINA VERA su ogni registrazione del repository (scoperte da sole, come in
// `replayVerificaBarra.partite.test.ts`) e confronta con il verificatore: numero di
// passi, passo di apertura, lineetta del calcio d'inizio, segmenti di sospensione,
// simboli (tipo, squadra, posizione) e tabellone a un campione di passi. Se la pagina
// cambia la sua barra senza il verificatore, o viceversa, questo test diventa rosso.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
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
import { punteggioAlTs, timelineEventMarkers } from '@/lib/replayTimelineEvents';
import { idMercatiSospensione, kickoffIndexSuPassi, kickoffTsDaFrame, passiBarra, sospesiPerPasso } from '@/lib/replayVerificaBarra';
import { apriReplay } from './__fixtures__/replayBarraPagina';
import { caricaPartita, eventiConFixture } from './__fixtures__/replayBarraTutte';

afterEach(() => { stato.dati = null; });

const ordTs = (a: { ts: string }, b: { ts: string }): number => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0);
const vicino = (a: number, b: number): boolean => Math.abs(a - b) < 1e-6;

describe.each(eventiConFixture())('pagina vera vs verificatore - partita %s', (ev) => {
    it('stessi passi, stessa apertura, stessa lineetta del calcio d\'inizio, stessi segmenti di sospensione, stessi simboli, stesso tabellone', async () => {
        const { replay } = caricaPartita(ev);
        const dati: ReplayData = replay;
        stato.dati = dati;
        stato.casa = `Casa${ev}`;
        const p = await apriReplay(<MatchReplay />, stato.casa);

        const passi = passiBarra(dati.frames);
        const kickoffTs = kickoffTsDaFrame(dati.frames);
        const kickoffIndex = kickoffIndexSuPassi(passi, kickoffTs);
        const sospesi = sospesiPerPasso(passi, dati.frames, dati.markets);
        const righe = [...dati.score_timeline].sort(ordTs);
        const span = Math.max(1, passi.length - 1);
        // la pagina chiama `timelineEventMarkers` con i nomi dell'evento (qui: quelli del finto elenco non contano)
        const simboli = timelineEventMarkers(righe, passi, dati.event.home_name || 'Casa', dati.event.away_name || 'Ospiti', span);

        expect(p.max, 'numero di passi della barra').toBe(passi.length - 1);
        expect(p.iniziale, 'la pagina si apre sul calcio d\'inizio').toBe(kickoffIndex);
        expect([...p.sospesi].sort((a, b) => a - b), 'segmenti di sospensione').toEqual(sospesi.map((s, i) => (s ? i : -1)).filter(i => i >= 0));
        expect(idMercatiSospensione(dati.markets).length).toBeGreaterThan(0);

        await p.vai(p.max);
        const v = p.leggi();
        if (kickoffIndex > 0) expect(vicino(v.kickoffLeft ?? -1, kickoffIndex / p.max * 100), 'lineetta del calcio d\'inizio').toBe(true);
        const chiave = (k: string, t: string | null | undefined, left: number) => `${k}|${t ?? ''}|${left.toFixed(6)}`;
        expect(v.simboli.map(s => chiave(s.kind, s.team, s.left)).sort(), 'simboli a fine replay').toEqual(
            simboli.map(s => chiave(s.kind, s.team, s.pctLeft * 100)).sort(),
        );

        // tabellone: campione di passi (estremi, calcio d'inizio, ogni 61, il passo di ogni gol e il successivo)
        const campione = new Set<number>([0, 1, kickoffIndex, p.max - 1, p.max]);
        for (let i = 0; i <= p.max; i += 61) campione.add(i);
        for (const s of simboli.filter(x => x.kind === 'goal')) {
            const i = Math.round(s.pctLeft * span);
            campione.add(i); campione.add(Math.min(p.max, i + 1));
        }
        for (const i of [...campione].filter(x => x >= 0 && x <= p.max).sort((a, b) => a - b)) {
            await p.vai(i);
            const m = punteggioAlTs(righe, passi[i].ts);
            expect(p.leggi().punteggio, `tabellone al passo ${i}`).toBe(`${m.home} - ${m.away}`);
        }
    }, 120_000);
});
