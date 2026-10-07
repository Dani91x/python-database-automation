// ============================================================================
// 07/10 — LA BARRA DI AVANZAMENTO DI MATCH REPLAY E' COERENTE CON I SIMBOLI?
// Ordine dell'utente: «assicurati che la barra di avanzamento della partita sia
// perfettamente coerente con i simboli».
//
// Qui si monta la pagina VERA (`pages/MatchReplay.tsx`) con i dati VERI di due
// registrazioni (35797769 Spagna-Belgio con 2h30 di pre-match e buchi dello
// stream; 35760084 Liepaja-Ogre con 15 angoli e sospensione finale lunga), si
// muove la barra come l'utente e si legge dal DOM. Gli oracoli stanno in
// `__fixtures__/replayBarra.ts` e sono scritti dalla REGOLA, non dal codice
// sotto esame: la barra ha un passo per ogni bucket da 10 s di orologio con
// frame; un fatto accaduto all'istante t compare al PRIMO passo con ts >= t e il
// suo simbolo sta alla posizione indice/ultimo-indice.
//
// Non rifa' i controlli del 06/10 (`replayTimelineEvents.test.ts`: conteggi dei
// simboli, doppioni, ri-emissioni) ma controlla cio' che lì mancava: posizione
// per ogni simbolo, comparsa scorrendo, estremi, calcio d'inizio, sospensioni,
// ladder al cursore.
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
import {
    FIXTURE_BARRA, replayDaFixture, passiAttesi, passoDa, frameMatchOddsA, simboliAttesi, msDi,
    type EventoBarra, type PassoBarra,
} from './__fixtures__/replayBarra';
import { apriReplay, type PilotaPagina, type VistaBarra } from './__fixtures__/replayBarraPagina';

afterEach(() => { stato.dati = null; });

const vicino = (a: number, b: number) => Math.abs(a - b) < 1e-9;
const minutoDelCursore = (v: VistaBarra): number | null => {
    const m = /^(\d+)'/.exec(v.testoMinuto);
    return m ? Number(m[1]) : null;
};

async function monta(ev: EventoBarra): Promise<{ replay: ReplayData; passi: PassoBarra[]; p: PilotaPagina }> {
    const replay = replayDaFixture(FIXTURE_BARRA[ev]);
    stato.dati = replay;
    stato.casa = `Casa${ev}`;
    const p = await apriReplay(<MatchReplay />, stato.casa);
    return { replay, passi: passiAttesi(replay.frames), p };
}

// passi da campionare: estremi, calcio d'inizio, ogni simbolo (prima/sul/dopo) e
// un passo ogni 37 (la pagina intera si ridisegna a ogni passo)
function campione(passi: PassoBarra[], extra: number[]): number[] {
    const max = passi.length - 1;
    const s = new Set<number>([0, 1, max - 1, max]);
    for (let i = 0; i <= max; i += 37) s.add(i);
    for (const e of extra) for (const d of [-2, -1, 0, 1, 2]) if (e + d >= 0 && e + d <= max) s.add(e + d);
    return [...s].sort((a, b) => a - b);
}

describe.each(['35797769', '35760084'] as const)('barra e simboli — partita vera %s', (ev) => {
    it('la griglia ha tanti passi quanti i bucket da 10 s con frame, e gli estremi sono primo e ultimo frame', async () => {
        const { replay, passi, p } = await monta(ev);
        expect(p.max).toBe(passi.length - 1);
        const tutti = replay.frames.map(f => msDi(f.ts));
        // il primo passo e' il primo frame della registrazione
        expect(passi[0].ms).toBe(Math.min(...tutti));
        // l'ultimo passo sta a meno di un bucket dall'ultimo frame
        expect(Math.max(...tutti) - passi[passi.length - 1].ms).toBeLessThan(10_000);
        await p.vai(0);
        const a = p.leggi();
        expect(a.indice).toBe(0);
        expect(a.knobLeft).toBe(0);
        expect(a.knobTesto).toBe('PRE');
        await p.vai(p.max);
        const z = p.leggi();
        expect(z.indice).toBe(p.max);
        expect(z.knobLeft).toBe(100);
        expect(z.testoMinuto).toMatch(/FT$/);
    });

    it('il calcio d\'inizio sta al primo passo con ts >= primo frame in-gioco; la pagina si apre li\'; PRE solo prima', async () => {
        const { replay, passi, p } = await monta(ev);
        const primoInGioco = Math.min(...replay.frames.filter(f => f.inplay).map(f => msDi(f.ts)));
        const ko = passoDa(passi, primoInGioco);
        expect(ko).toBeGreaterThan(0);
        expect(p.iniziale).toBe(ko);
        await p.vai(ko);
        const v = p.leggi();
        expect(v.kickoffLeft).not.toBeNull();
        expect(vicino(v.kickoffLeft ?? -1, ko / p.max * 100)).toBe(true);
        expect(vicino(v.knobLeft, v.kickoffLeft ?? -1)).toBe(true);   // il cursore e' sulla lineetta
        expect(v.knobTesto).not.toBe('PRE');
        expect(v.testoMinuto).not.toBe('PRE-MATCH');
        await p.vai(ko - 1);
        const prima = p.leggi();
        expect(prima.knobTesto).toBe('PRE');
        expect(prima.testoMinuto).toBe('PRE-MATCH');
        expect(prima.simboli).toHaveLength(0);                        // niente simboli prima del fischio
    });

    it('ogni simbolo sta alla posizione attesa e compare scorrendo proprio a quel passo', async () => {
        const { replay, passi, p } = await monta(ev);
        const attesi = simboliAttesi(replay.score_timeline).map(s => ({ ...s, passo: passoDa(passi, msDi(s.ts)) }));
        expect(attesi.every(s => s.passo >= 0)).toBe(true);
        await p.vai(p.max);
        const finali = p.leggi().simboli;
        // stessa lista: tipo, squadra e posizione di ciascun simbolo (nessuno in piu', nessuno in meno)
        const chiave = (k: string, t: string, left: number) => `${k}|${t}|${left.toFixed(6)}`;
        expect(finali.map(s => chiave(s.kind, s.team, s.left)).sort())
            .toEqual(attesi.map(s => chiave(s.kind, s.team, s.passo / p.max * 100)).sort());
        // posizioni crescenti nel tempo e dentro la barra
        for (const s of finali) { expect(s.left).toBeGreaterThanOrEqual(0); expect(s.left).toBeLessThanOrEqual(100); }
        // comparsa: assente al passo prima, presente al passo del simbolo, e il cursore e' sul simbolo
        for (const s of attesi) {
            const left = s.passo / p.max * 100;
            const c = (v: VistaBarra) => v.simboli.filter(x => x.kind === s.kind && x.team === s.team && vicino(x.left, left)).length;
            const molteplicita = attesi.filter(o => o.kind === s.kind && o.team === s.team && o.passo === s.passo).length;
            if (s.passo > 0) {
                await p.vai(s.passo - 1);
                expect(c(p.leggi())).toBe(0);
            }
            await p.vai(s.passo);
            const v = p.leggi();
            expect(c(v)).toBe(molteplicita);
            expect(vicino(v.knobLeft, left)).toBe(true);
            // il minuto del cursore sul simbolo e' quello del simbolo (a meno del
            // minuto di recupero 45+1 -> 46 e dello scarto fra i due feed)
            const mc = minutoDelCursore(v);
            if (mc != null && s.minute != null) expect(Math.abs(mc - s.minute)).toBeLessThanOrEqual(2);
        }
    });

    it('i segmenti di sospensione sono esattamente i passi in cui il Match Odds e\' SOSPESO, e il pannello concorda', async () => {
        const { replay, passi, p } = await monta(ev);
        const mercato = replay.markets.find(m => m.market_type === 'MATCH_ODDS')!.market_id;
        const attesi = new Set<number>();
        passi.forEach((s, i) => { if (frameMatchOddsA(replay, mercato, s.ms)?.status === 'SUSPENDED') attesi.add(i); });
        expect(attesi.size).toBeGreaterThan(0);                        // la partita ha davvero sospensioni visibili
        expect([...p.sospesi].sort((a, b) => a - b)).toEqual([...attesi].sort((a, b) => a - b));
        // geometria: il segmento del passo i parte dalla posizione del cursore su quel
        // passo (i/ultimo) ed e' largo un passo; l'ultimo non esce dalla barra
        for (const g of p.segmenti) {
            expect(vicino(g.left, Math.min(g.indice / p.max * 100, 100 - 100 / p.max))).toBe(true);
            expect(vicino(g.width, 100 / p.max)).toBe(true);
            expect(g.left + g.width).toBeLessThanOrEqual(100 + 1e-9);
        }
        // il badge "Sospeso" del pannello compare agli stessi passi (campione: bordi dei tratti)
        const bordi: number[] = [];
        for (const i of attesi) { if (!attesi.has(i - 1) || !attesi.has(i + 1)) bordi.push(i); }
        for (const i of campione(passi, bordi)) {
            await p.vai(i);
            expect(p.leggi().matchOddsSospeso).toBe(attesi.has(i));
        }
    });

    it('il ladder del Match Odds al cursore e\' l\'ultimo frame <= istante del passo (prima/dopo ogni gol)', async () => {
        const { replay, passi, p } = await monta(ev);
        const mercato = replay.markets.find(m => m.market_type === 'MATCH_ODDS')!;
        const gol = simboliAttesi(replay.score_timeline).filter(s => s.kind === 'goal').map(s => passoDa(passi, msDi(s.ts)));
        for (const i of campione(passi, gol)) {
            await p.vai(i);
            const v = p.leggi();
            const f = frameMatchOddsA(replay, mercato.market_id, passi[i].ms);
            const attese = mercato.selections.map(sel => {
                const e = f?.ladder[String(sel.selection_id)];
                return { nome: sel.name, back: e?.back[0] ? e.back[0][0].toFixed(2) : '—', lay: e?.lay[0] ? e.lay[0][0].toFixed(2) : '—' };
            });
            expect(v.matchOdds).toEqual(attese);
        }
    });

    it('dopo un gol il ladder si riprezza nel verso giusto (casa segna: il back della casa scende; ospite: sale)', async () => {
        const { replay, passi, p } = await monta(ev);
        const mercato = replay.markets.find(m => m.market_type === 'MATCH_ODDS')!;
        const casa = String(mercato.selections[0].selection_id);   // sort_priority 1 = squadra di casa
        const backCasa = (i: number) => frameMatchOddsA(replay, mercato.market_id, passi[i].ms)?.ladder[casa]?.back[0]?.[0] ?? null;
        const gol = simboliAttesi(replay.score_timeline).filter(s => s.kind === 'goal');
        let verificati = 0;
        for (const g of gol) {
            const i = passoDa(passi, msDi(g.ts));
            const prima = backCasa(Math.max(0, i - 3));
            const dopo = backCasa(Math.min(p.max, i + 6));
            if (prima == null || dopo == null || prima <= 1.05) continue;   // quota al minimo: non puo' scendere
            verificati += 1;
            if (g.team === 'home') expect(dopo).toBeLessThan(prima); else expect(dopo).toBeGreaterThan(prima);
        }
        expect(verificati).toBeGreaterThanOrEqual(2);
    });
});
