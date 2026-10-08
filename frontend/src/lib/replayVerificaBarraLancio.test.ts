// ============================================================================
// 08/10 - CANTIERE 12. Il comando del processo figlio `npx vite-node ...` e' portabile
// (Windows: `npx.cmd` con shell e argomenti tra virgolette; altrove: `npx` senza shell).
// La funzione e' PURA con la piattaforma come parametro, quindi questi test costruiscono
// il comando per `win32` anche su Linux. Un test non puo' lanciare cmd.exe qui: la prova
// che le virgolette tengono insieme un percorso con spazi passa da una shell vera (sh) con
// un piccolo programma node che stampa gli argomenti ricevuti.
// ============================================================================
import { afterEach, describe, expect, it } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { comandoViteNode, quotaArgomentoWin32 } from './replayVerificaBarraLancio';

const PERCORSO_WIN = 'C:\\Users\\Daniele\\PYTHON DATABASE\\frontend\\scripts\\verifica_barra_replay.ts';
const PERCORSO_LINUX = '/home/utente/PYTHON DATABASE/frontend/scripts/verifica_barra_replay.ts';

describe('comandoViteNode: Windows', () => {
    it('npx.cmd con shell, e il percorso con spazi tra virgolette doppie (UN solo argomento)', () => {
        const c = comandoViteNode([PERCORSO_WIN, '--evento', '35760084'], 'win32');
        expect(c.comando).toBe('npx.cmd');
        expect(c.shell).toBe(true);
        expect(c.argomenti).toEqual(['vite-node', `"${PERCORSO_WIN}"`, '--evento', '35760084']);
        // con shell Node incolla comando e argomenti con uno spazio: il percorso deve restare intero
        const riga = [c.comando, ...c.argomenti].join(' ');
        expect(riga).toContain(`"${PERCORSO_WIN}"`);
    });

    it('un percorso senza spazi non si tocca; un argomento vuoto o con caratteri speciali si quota', () => {
        expect(comandoViteNode(['scripts/verifica_barra_replay.ts', '--json'], 'win32').argomenti)
            .toEqual(['vite-node', 'scripts/verifica_barra_replay.ts', '--json']);
        expect(quotaArgomentoWin32('')).toBe('""');
        expect(quotaArgomentoWin32('a&b')).toBe('"a&b"');
        expect(quotaArgomentoWin32('a|b')).toBe('"a|b"');
        expect(quotaArgomentoWin32('x^y')).toBe('"x^y"');
        expect(quotaArgomentoWin32('(x)')).toBe('"(x)"');
    });

    it('le virgolette dentro un argomento si proteggono con il backslash', () => {
        expect(quotaArgomentoWin32('dice "ciao"')).toBe('"dice \\"ciao\\""');
        // backslash prima della virgoletta: raddoppiati; backslash finale (cartella): raddoppiato prima della chiusura
        expect(quotaArgomentoWin32('a\\"b')).toBe('"a\\\\\\"b"');
        expect(quotaArgomentoWin32('C:\\PYTHON DATABASE\\')).toBe('"C:\\PYTHON DATABASE\\\\"');
    });

    it('anche gli argomenti di valore con spazi (es. --env-file) restano interi', () => {
        const c = comandoViteNode([PERCORSO_WIN, '--env-file', 'C:\\PYTHON DATABASE\\.env'], 'win32');
        expect(c.argomenti.slice(-2)).toEqual(['--env-file', '"C:\\PYTHON DATABASE\\.env"']);
    });
});

describe('comandoViteNode: Linux e macOS', () => {
    it.each(['linux', 'darwin'])('%s: npx senza shell e argomenti cosi\' come sono (nessuna virgoletta)', (piattaforma) => {
        const c = comandoViteNode([PERCORSO_LINUX, '--evento', '1'], piattaforma);
        expect(c).toEqual({ comando: 'npx', argomenti: ['vite-node', PERCORSO_LINUX, '--evento', '1'], shell: false });
    });
});

describe('le virgolette tengono insieme un percorso con spazi attraverso una shell vera', () => {
    let cartella: string | null = null;
    afterEach(() => { if (cartella) rmSync(cartella, { recursive: true, force: true }); cartella = null; });

    it('node riceve il percorso con lo spazio come UN argomento quando e\' quotato, in DUE quando non lo e\'', () => {
        cartella = mkdtempSync(join(tmpdir(), 'lancio-barra-'));
        const eco = join(cartella, 'eco.js');
        writeFileSync(eco, 'process.stdout.write(JSON.stringify(process.argv.slice(2)));');
        const valore = 'cartella con spazio/verifica.ts';
        const lancia = (arg: string): string[] => {
            // shell: true come su Windows: Node incolla comando e argomenti con uno spazio
            const r = spawnSync(`"${process.execPath}"`, [`"${eco}"`, arg], { shell: true, encoding: 'utf-8' });
            expect(r.status, r.stderr).toBe(0);
            return JSON.parse(r.stdout) as string[];
        };
        expect(lancia(quotaArgomentoWin32(valore))).toEqual([valore]);
        expect(lancia(valore)).toEqual(['cartella', 'con', 'spazio/verifica.ts']);
    });
});
