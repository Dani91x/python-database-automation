// ============================================================================
// 08/10 (cantiere 13) - verifica su FIXTURE generate dal raw e PROVE di ogni incoerenza.
// La partita del database si riproduce dal suo raw sul PC (`tools/replay_barra_fixture.py
// --registrazioni _live_raw --uscita <cartella> <id>`) e si verifica con
// `scripts/verifica_barra_fixture.ts`; le prove (`--dettaglio`) sono le righe vere attorno a
// ogni incoerenza, il materiale della classificazione a/b/c. Qui con le fixture VERE del
// banco e con le stesse fixture modificate come le partite incoerenti del PC.
// ============================================================================
import { describe, it, expect, afterAll } from 'vitest';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import type { RigaScore } from './__fixtures__/replayBarraConversione';
import { caricaFixtureCompleta, eventiConFixture, percorsoFixture, type FixtureBarraCompleta } from './__fixtures__/replayBarraTutte';
import { verificaFixture } from './replayVerificaBarraFixture';
import { comandoViteNode } from './replayVerificaBarraLancio';

const EVENTI = eventiConFixture();
const FRONTEND = resolve(__dirname, '../..');
const TMP = mkdtempSync(join(tmpdir(), 'barra-fixture-'));
afterAll(() => rmSync(TMP, { recursive: true, force: true }));

const iso = (ms: number): string => new Date(ms).toISOString().replace('Z', '+00:00');
/** la stessa fixture con il KickOff del feed 6 minuti prima del primo frame in gioco (dato discorde) */
function conKickOffPrima(fx: FixtureBarraCompleta): FixtureBarraCompleta {
    const k = Math.min(...fx.frames.filter(r => r[3] === 1).map(r => Date.parse(r[1])));
    return { ...fx, score_timeline: fx.score_timeline.map(r => (r[5] === 'KickOff' ? [iso(k - 360_000), ...r.slice(1)] as RigaScore : r)) };
}
/** la stessa fixture con un gol annullato (VAR) 8 minuti prima di un gol vero: riga +1, Goal, correzione.
 *  Il gol scelto ha 10 minuti di punteggio fermo prima e nessuna riga di un'ALTRA fonte fra il gol annullato
 *  e la correzione (altrimenti e' una discesa fra due fonti, TABELLONE_SCENDE, non un VAR). */
function conVarPrimaDiUnGol(fx: FixtureBarraCompleta): FixtureBarraCompleta {
    const righe = [...fx.score_timeline].sort((a, b) => Date.parse(a[0]) - Date.parse(b[0]));
    const conPunteggio = righe.filter(r => r[3] != null && r[4] != null);
    const sale = (j: number): boolean => j > 0 && ((conPunteggio[j][3] as number) > (conPunteggio[j - 1][3] as number) || (conPunteggio[j][4] as number) > (conPunteggio[j - 1][4] as number));
    const adatto = (j: number): boolean => {
        if (!sale(j)) return false;
        const p = conPunteggio[j - 1], T = Date.parse(conPunteggio[j][0]);
        const stabile = conPunteggio.slice(0, j).filter(r => Date.parse(r[0]) >= T - 600_000).every(r => r[3] === p[3] && r[4] === p[4]);
        const altre = conPunteggio.some(r => r[1] !== p[1] && Date.parse(r[0]) >= T - 490_000 && Date.parse(r[0]) <= T - 350_000);
        return stabile && !altre;
    };
    const i = conPunteggio.findIndex((_, j) => adatto(j));
    if (i < 0) throw new Error('nessun gol adatto alla prova');
    const p = conPunteggio[i - 1], c = conPunteggio[i];
    const casa = (c[3] as number) > (p[3] as number);
    const T = Date.parse(c[0]);
    const goal = righe.find(r => r[5] === 'Goal' && Math.abs(Date.parse(r[0]) - T) <= 180_000) as RigaScore;
    const minuto = p[2];
    const nuove: RigaScore[] = [
        [iso(T - 482_000), goal[1], minuto, null, null, 'Goal', { ...(goal[6] as Record<string, unknown>), minute: minuto }],
        [iso(T - 480_000), p[1], minuto, (p[3] as number) + (casa ? 1 : 0), (p[4] as number) + (casa ? 0 : 1), null, p[6]],
        [iso(T - 360_000), p[1], minuto, p[3], p[4], null, p[6]],
    ];
    return { ...fx, score_timeline: [...fx.score_timeline, ...nuove] };
}

describe.each(EVENTI)('verificaFixture sulla fixture vera %s', (ev) => {
    it('coerente, nessuna prova da stampare', () => {
        const r = verificaFixture(caricaFixtureCompleta(ev), { dettaglio: true });
        expect(r.esito.incoerenze, r.testo).toEqual([]);
        expect(r.testo).toMatch(/^OK +\d+ .*fixture dal raw/);
        expect(r.testo).not.toContain('>> prove di');
    });

    it('KickOff discorde: "INCOERENTE PER DATI" e le prove (KickOff del feed, primo frame in gioco, passi attorno alla lineetta)', () => {
        const r = verificaFixture(conKickOffPrima(caricaFixtureCompleta(ev)), { dettaglio: true });
        expect(r.testo).toMatch(/^INCOERENTE PER DATI /);
        expect(r.testo).toContain('>> prove di KICKOFF_DISCORDANTE');
        expect(r.testo).toMatch(/evento {5}\S+ {2}KickOff/);
        expect(r.testo).toContain('primo frame in gioco');
        expect(r.testo).toContain('(lineetta)');
        // senza --dettaglio niente prove
        expect(verificaFixture(conKickOffPrima(caricaFixtureCompleta(ev))).testo).not.toContain('>> prove di');
    });

    it('gol annullato prima di un gol vero: coerente (cantiere 13, classe a) anche dalla fixture', () => {
        const r = verificaFixture(conVarPrimaDiUnGol(caricaFixtureCompleta(ev)), { dettaglio: true });
        expect(r.esito.incoerenze, r.testo).toEqual([]);
        expect(r.esito.note.map(x => x.codice)).toContain('TABELLONE_CORREZIONE_FEED');
    });
});

describe('prove di un difetto sui gol: tutti i cambi del punteggio e i Goal della timeline', () => {
    it('una seconda fonte in ritardo (TABELLONE_SCENDE): le prove elencano le righe delle due fonti attorno all\'istante', () => {
        const ev = EVENTI[0];
        const fx = caricaFixtureCompleta(ev);
        const g = fx.score_timeline.find(r => (r[3] ?? 0) > 0) as RigaScore;
        const tardi: RigaScore = [iso(Date.parse(g[0]) + 5000), 'api_football', g[2], 0, 0, null, g[6]];
        const r = verificaFixture({ ...fx, score_timeline: [...fx.score_timeline, tardi] }, { dettaglio: true });
        expect(r.testo).toMatch(/^INCOERENTE \d/);
        expect(r.testo).toContain('>> prove di TABELLONE_SCENDE');
        expect(r.testo).toContain('fonte=api_football');
        expect(r.testo).toContain('-- ogni cambio del punteggio (per fonte) e ogni Goal della timeline --');
    });
});

describe('script verifica_barra_fixture.ts lanciato davvero', () => {
    function lancia(args: string[]): Promise<{ codice: number; out: string; err: string }> {
        const cmd = comandoViteNode(['scripts/verifica_barra_fixture.ts', ...args], process.platform);
        return new Promise((ok) => {
            const p = spawn(cmd.comando, cmd.argomenti, { cwd: FRONTEND, shell: cmd.shell });
            let out = '', err = '';
            p.stdout.on('data', d => { out += String(d); });
            p.stderr.on('data', d => { err += String(d); });
            p.on('error', e => ok({ codice: -1, out, err: `${err}\nil processo figlio non e' partito: ${e.message}` }));
            p.on('close', c => ok({ codice: c ?? -1, out, err }));
        });
    }

    it('fixture vere: esce con 0; una fixture con il KickOff discorde: esce con 1 e la dice "solo per dati"; senza file: 2', async () => {
        const vere = EVENTI.map(percorsoFixture);
        const a = await lancia(vere);
        expect(a.codice, `${a.out}\n${a.err}`).toBe(0);
        expect(a.out).toContain(`RIEPILOGO FIXTURE: ${EVENTI.length} verificate: ${EVENTI.length} OK, 0 solo per dati, 0 da correggere, 0 illeggibili.`);
        const p = join(TMP, `replay_barra_${EVENTI[0]}.json`);
        writeFileSync(p, JSON.stringify(conKickOffPrima(caricaFixtureCompleta(EVENTI[0]))));
        const b = await lancia([p, '--dettaglio']);
        expect(b.codice, `${b.out}\n${b.err}`).toBe(1);
        expect(b.out).toContain('INCOERENTE PER DATI');
        expect(b.out).toContain('>> prove di KICKOFF_DISCORDANTE');
        expect(b.out).toContain('1 verificate: 0 OK, 1 solo per dati, 0 da correggere, 0 illeggibili.');
        const c = await lancia([]);
        expect(c.codice).toBe(2);
    }, 90_000);
});
