// ============================================================================
// 07/10 — CONTROLLO AGGIUNTIVO barra/simboli (funzioni pure): punteggio al
// cursore e casi limite, sulle due registrazioni VERE (35797769 Spagna-Belgio e
// 35760084 Liepaja-Ogre; vedi __fixtures__/replayBarra.ts per com'e' fatto il dato).
// Completa `replayTimelineEvents.test.ts` (06/10: conteggi e doppioni).
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { ScoreEvent } from '@/lib/live';
import { punteggioAlTs, timelineEventMarkers, type TimelineMarker } from './replayTimelineEvents';
import { buildSnapshots } from './opportunities/snapshot';
import {
    FIXTURE_BARRA, replayDaFixture, passiAttesi, passoDa, msDi, type EventoBarra, type PassoBarra,
} from './__fixtures__/replayBarra';

const EVENTI = ['35797769', '35760084'] as const;

function ordina(r: ScoreEvent[]): ScoreEvent[] {
    return [...r].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}
function carica(ev: EventoBarra) {
    const replay = replayDaFixture(FIXTURE_BARRA[ev]);
    return { replay, righe: ordina(replay.score_timeline), passi: passiAttesi(replay.frames) };
}
// oracolo del punteggio: l'ultima riga del punteggio con ts <= istante
// (le righe-evento della timeline NON portano il punteggio)
function punteggioVero(righe: ScoreEvent[], ts: string): { home: number; away: number } {
    let r: ScoreEvent | null = null;
    for (const x of righe) {
        if (x.ts > ts) break;
        if (x.score_home != null && x.score_away != null) r = x;
    }
    return r ? { home: r.score_home as number, away: r.score_away as number } : { home: 0, away: 0 };
}
const alMs = (ms: number) => new Date(ms).toISOString().replace('Z', '+00:00');
const marker = (righe: ScoreEvent[], passi: PassoPassi, casa = 'Casa', ospiti = 'Ospiti'): TimelineMarker[] =>
    timelineEventMarkers(righe, passi.map(p => ({ ts: p.ts })), casa, ospiti, Math.max(1, passi.length - 1));
type PassoPassi = PassoBarra[];
const sintetici = (m: TimelineMarker[]) => m.filter(x => x.kind !== 'corner');

describe.each(EVENTI)('punteggioAlTs — partita vera %s', (ev) => {
    const { righe } = carica(ev);
    const ultimaEvento = [...righe].reverse().find(r => r.event_type)!;

    it('coincide con il punteggio vero a ogni istante, anche subito dopo una riga-evento (gol, giallo, fine tempo)', () => {
        let verificati = 0;
        for (const r of righe) {
            for (const ts of [r.ts, alMs(msDi(r.ts) + 3000)]) {
                const p = punteggioAlTs(righe, ts);
                expect({ home: p.home, away: p.away }).toEqual(punteggioVero(righe, ts));
                verificati += 1;
            }
        }
        expect(verificati).toBeGreaterThan(200);
    });

    it('a fine partita (dopo l\'ultima riga-evento, SecondHalfEnd) mostra il risultato finale, non 0-0', () => {
        const fine = punteggioAlTs(righe, ultimaEvento.ts);
        const finale = punteggioVero(righe, ultimaEvento.ts);
        expect(finale.home + finale.away).toBeGreaterThan(0);
        expect({ home: fine.home, away: fine.away }).toEqual(finale);
    });

    it('prima della prima riga: 0-0 senza minuto; il minuto e\' quello dell\'ultima riga di qualunque tipo', () => {
        expect(punteggioAlTs(righe, '2000-01-01T00:00:00+00:00')).toEqual({ home: 0, away: 0, minute: null });
        expect(punteggioAlTs(righe, ultimaEvento.ts).minute).toBe(ultimaEvento.minute);
    });
});

describe('punteggioAlTs — il caso del gol con riga-evento che precede la riga del punteggio', () => {
    it('35760084: dopo il Goal delle 16:28:28 (riga-evento) il punteggio e\' 2-0 (riga del punteggio delle 16:28:27)', () => {
        const { righe } = carica('35760084');
        const g = righe.find(r => r.event_type === 'Goal' && r.minute === 28)!;
        expect(g.score_home).toBeNull();                    // la riga-evento non porta il punteggio
        const p = punteggioAlTs(righe, g.ts);
        expect({ home: p.home, away: p.away }).toEqual({ home: 2, away: 0 });
    });
});

describe.each(EVENTI)('timelineEventMarkers — casi limite sulla partita vera %s', (ev) => {
    const { righe, passi } = carica(ev);
    const eventi = righe.filter(r => r.event_type && ['Goal', 'YellowCard', 'RedCard'].includes(r.event_type));
    const tutti = marker(righe, passi);

    it('base: un simbolo per ogni gol/cartellino della timeline, mai fuori dalla barra e in ordine di tempo', () => {
        expect(sintetici(tutti)).toHaveLength(eventi.length);
        for (const m of tutti) { expect(m.pctLeft).toBeGreaterThanOrEqual(0); expect(m.pctLeft).toBeLessThanOrEqual(1); }
        const ts = tutti.map(m => m.ts);
        expect([...ts].sort()).toEqual(ts);
    });

    it('registrazione che INIZIA a partita in corso: nessun simbolo per i fatti accaduti prima del primo frame', () => {
        const meta = passi[Math.floor(passi.length * 0.7)];
        const dopo = passi.filter(p => p.ms >= meta.ms);
        const m = marker(righe, dopo);
        const attesi = eventi.filter(e => msDi(e.ts) >= dopo[0].ms);
        expect(attesi.length).toBeLessThan(eventi.length);   // il caso e' davvero un taglio
        expect(sintetici(m)).toHaveLength(attesi.length);
        for (const x of m) expect(msDi(x.ts)).toBeGreaterThanOrEqual(dopo[0].ms);
    });

    it('registrazione che FINISCE prima della partita: nessun simbolo per i fatti dopo l\'ultimo frame (mai incollati al 100%)', () => {
        const meta = passi[Math.floor(passi.length * 0.7)];
        const prima = passi.filter(p => p.ms <= meta.ms);
        const m = marker(righe, prima);
        const attesi = eventi.filter(e => msDi(e.ts) <= prima[prima.length - 1].ms);
        expect(attesi.length).toBeLessThan(eventi.length);
        expect(sintetici(m)).toHaveLength(attesi.length);
        expect(m.filter(x => x.pctLeft === 1 && msDi(x.ts) > prima[prima.length - 1].ms)).toHaveLength(0);
    });

    it('BUCO dello stream: un fatto accaduto dentro il buco compare al primo passo dopo il buco', () => {
        const e = eventi[Math.floor(eventi.length / 2)];
        const t = msDi(e.ts);
        const conBuco = passi.filter(p => p.ms < t - 120_000 || p.ms > t + 120_000);
        expect(conBuco.length).toBeLessThan(passi.length);
        const m = marker(righe, conBuco).filter(x => x.ts === e.ts);
        expect(m).toHaveLength(1);
        const idx = passoDa(conBuco, t);
        expect(m[0].pctLeft).toBe(idx / (conBuco.length - 1));
    });
});

describe('timelineEventMarkers — gol nel punteggio ma assente dalla timeline discreta (35797769)', () => {
    it('il gol del Belgio al 41\' compare sulla barra anche se la riga-evento Goal manca (la timeline puo\' perdere un poll)', () => {
        const { righe, passi } = carica('35797769');
        const senza = righe.filter(r => !(r.event_type === 'Goal' && r.minute === 41));
        expect(senza.length).toBe(righe.length - 1);
        const gol = marker(senza, passi, 'Spain', 'Belgium').filter(m => m.kind === 'goal');
        expect(gol.map(m => m.team).sort()).toEqual(['away', 'home', 'home']);
        // e sta dove sta la riga del punteggio 1-1, non altrove
        const r11 = righe.find(r => r.score_home === 1 && r.score_away === 1)!;
        const g = gol.find(m => m.team === 'away')!;
        expect(g.pctLeft).toBe(passoDa(passi, msDi(r11.ts)) / (passi.length - 1));
    });

    it('con la riga-evento presente il gol non e\' disegnato due volte', () => {
        const { righe, passi } = carica('35797769');
        const gol = marker(righe, passi, 'Spain', 'Belgium').filter(m => m.kind === 'goal');
        expect(gol).toHaveLength(3);
    });
});

// ----------------------------------------------------------------------------
// STESSO DIFETTO NEL MOTORE OPPORTUNITA' (`lib/opportunities/snapshot.ts`, fuori
// dal perimetro di questo cantiere): lo snapshot prende il punteggio dall'ultima
// riga di qualunque tipo e legge `score_home ?? 0`, quindi dopo una riga-evento
// il motore vede 0-0. I test esistenti di snapshot.test.ts usano righe-evento CON
// punteggio (`event_type: 'GOAL', score_home: 1`), che nel vero non esistono.
// ROSSO finche' snapshot.ts non salta le righe senza punteggio (patch nel referto).
// ----------------------------------------------------------------------------
describe.each(EVENTI)('buildSnapshots (motore opportunita\') — punteggio sulla partita vera %s', (ev) => {
    const { replay, righe } = carica(ev);
    const snaps = buildSnapshots(replay, 10_000);
    it('lo snapshot ha il punteggio vero a ogni bucket, intervallo e fine partita compresi', () => {
        const errati: string[] = [];
        for (const s of snaps) {
            const fineBucket = alMs(msDi(s.ts) + 9_999);
            const v = punteggioVero(righe, fineBucket);
            if (s.scoreHome !== v.home || s.scoreAway !== v.away) errati.push(`${s.ts}: ${s.scoreHome}-${s.scoreAway} vero ${v.home}-${v.away}`);
        }
        expect(errati).toEqual([]);
    });
});
