// ============================================================================
// 07/10 — IL PUNTEGGIO MOSTRATO AL CURSORE DELLA BARRA E' QUELLO VERO?
// Pagina VERA `pages/MatchReplay.tsx` con i dati VERI di due registrazioni
// (35797769 Spagna-Belgio 2-1; 35760084 Liepaja-Ogre 4-0), barra mossa come
// l'utente, tabellone letto dal DOM. Oracolo: l'ultima riga del punteggio con ts
// <= istante del passo (le righe-evento della timeline non portano il punteggio).
//
// DIFETTO TROVATO: `MatchReplay.tsx` prendeva «l'ultima riga <= ts» di QUALUNQUE
// tipo e leggeva `score_home ?? 0`: dopo ogni riga-evento (Goal, YellowCard,
// FirstHalfEnd, SecondHalfEnd) il tabellone tornava 0-0 — per tutto l'intervallo
// (50+ passi) e a fine partita («98' · FT» con 0 - 0 invece di 2 - 1), e quel
// punteggio entra anche nel regolamento dei mercati a fine replay (SettleCtx).
//
// QUESTI TEST SONO ROSSI FINCHE' `MatchReplay.tsx` NON USA `punteggioAlTs`
// (patch nel referto `AUDIT_2026-10-07/REPLAY_BARRA_SIMBOLI.md`, file di un altro
// delegato: non toccato qui). Verdi con la patch applicata.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import type { ReplayData, ScoreEvent } from '@/lib/live';

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
import {
    FIXTURE_BARRA, replayDaFixture, passiAttesi, passoDa, simboliAttesi, msDi,
    type EventoBarra, type PassoBarra,
} from './__fixtures__/replayBarra';
import { apriReplay, type PilotaPagina } from './__fixtures__/replayBarraPagina';

afterEach(() => { stato.dati = null; });

async function monta(ev: EventoBarra): Promise<{ replay: ReplayData; passi: PassoBarra[]; p: PilotaPagina; righe: ScoreEvent[] }> {
    const replay = replayDaFixture(FIXTURE_BARRA[ev]);
    stato.dati = replay;
    stato.casa = `Casa${ev}`;
    const p = await apriReplay(<MatchReplay />, stato.casa);
    const righe = [...replay.score_timeline].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    return { replay, passi: passiAttesi(replay.frames), p, righe };
}
function punteggioVero(righe: ScoreEvent[], ts: string): string {
    let r: ScoreEvent | null = null;
    for (const x of righe) {
        if (x.ts > ts) break;
        if (x.score_home != null && x.score_away != null) r = x;
    }
    return r ? `${r.score_home} - ${r.score_away}` : '0 - 0';
}

const FINALE: Record<EventoBarra, string> = { '35797769': '2 - 1', '35760084': '4 - 0' };

describe.each(['35797769', '35760084'] as const)('punteggio al cursore — partita vera %s', (ev) => {
    it('a OGNI passo della barra il tabellone e\' il punteggio vero (intervallo e righe-evento compresi)', async () => {
        const { passi, p, righe } = await monta(ev);
        const errati: string[] = [];
        // tutti i passi dal calcio d'inizio: ogni passo costa un ridisegno della pagina
        for (let i = p.iniziale; i <= p.max; i += 1) {
            await p.vai(i);
            const atteso = punteggioVero(righe, passi[i].ts);
            const visto = p.leggi().punteggio;
            if (visto !== atteso) errati.push(`passo ${i} (${passi[i].ts.slice(11, 19)}): mostra ${visto}, vero ${atteso}`);
        }
        expect(errati).toEqual([]);
    }, 120_000);

    it('a fine replay («FT») mostra il risultato finale', async () => {
        const { p } = await monta(ev);
        await p.vai(p.max);
        const v = p.leggi();
        expect(v.testoMinuto).toMatch(/FT$/);
        expect(v.punteggio).toBe(FINALE[ev]);
    });

    it('lungo l\'intervallo il tabellone resta quello del primo tempo (mai 0-0 per via della riga FirstHalfEnd)', async () => {
        const { replay, passi, p, righe } = await monta(ev);
        const fineTempo = replay.score_timeline.find(r => r.event_type === 'FirstHalfEnd')!;
        const secondoTempo = replay.score_timeline.find(r => r.event_type === 'SecondHalfKickOff')!;
        const i0 = passoDa(passi, msDi(fineTempo.ts));
        const i1 = passoDa(passi, msDi(secondoTempo.ts));
        expect(i1 - i0).toBeGreaterThan(3);                           // l'intervallo occupa passi della barra
        const atteso = punteggioVero(righe, fineTempo.ts);
        expect(atteso).not.toBe('0 - 0');                             // la partita non e' 0-0 all'intervallo
        for (const i of [i0, i0 + 1, Math.floor((i0 + i1) / 2), i1 - 1]) {
            await p.vai(i);
            expect(p.leggi().punteggio).toBe(atteso);
        }
    });

    it('ogni gol: il tabellone passa dal punteggio di prima a quello di dopo entro 2 passi dal simbolo, mai per 0-0', async () => {
        const { replay, passi, p, righe } = await monta(ev);
        const gol = simboliAttesi(replay.score_timeline).filter(s => s.kind === 'goal');
        for (const g of gol) {
            const i = passoDa(passi, msDi(g.ts));
            const prima = punteggioVero(righe, new Date(msDi(g.ts) - 30_000).toISOString().replace('Z', '+00:00'));
            // dopo = punteggio della prima riga che cambia rispetto a prima, entro 5 minuti
            const rigaDopo = righe.find(r => r.score_home != null && msDi(r.ts) >= msDi(g.ts) - 30_000
                && msDi(r.ts) <= msDi(g.ts) + 300_000 && `${r.score_home} - ${r.score_away}` !== prima);
            expect(rigaDopo).toBeTruthy();
            const dopo = `${rigaDopo!.score_home} - ${rigaDopo!.score_away}`;
            await p.vai(Math.max(0, i - 1));
            expect(p.leggi().punteggio).toBe(prima);
            const visti: string[] = [];
            for (const d of [0, 1, 2]) { await p.vai(Math.min(p.max, i + d)); visti.push(p.leggi().punteggio); }
            expect(visti.every(v => v === prima || v === dopo)).toBe(true);
            expect(visti[2]).toBe(dopo);
        }
    });
});
