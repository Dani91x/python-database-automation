// ============================================================================
// GUARDIA della veste delle pagine (redesign fasi 2-7).
// Le pagine ricevono classi `ds-v2-*`. Con ui.shell='off' devono essere INERTI,
// cioe' l'app di oggi resta identica anche a vista: ogni regola CSS che nomina
// una classe `.ds-v2-*` deve stare sotto `[data-shell="v2"]`. E ogni classe
// `ds-v2-*` scritta in una pagina deve esistere nel foglio (niente refusi muti).
// La fotografia non vede le classi: questa guardia sì.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';

const SRC = (() => {
    for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
        const p = join(base, 'src');
        if (existsSync(join(p, 'index.css'))) return p;
    }
    throw new Error('src/ non trovata');
})();

/** selettori (testo prima di `{`) del foglio, senza commenti */
function selettori(css: string): string[] {
    const senza = css.replace(/\/\*[\s\S]*?\*\//g, '');
    const out: string[] = [];
    const re = /([^{}]+)\{/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(senza))) {
        for (const s of m[1].split(',')) {
            const t = s.trim();
            if (t && !t.startsWith('@')) out.push(t);
        }
    }
    return out;
}

function sorgentiTsx(dir: string): string[] {
    const out: string[] = [];
    for (const n of readdirSync(dir)) {
        const p = join(dir, n);
        if (statSync(p).isDirectory()) out.push(...sorgentiTsx(p));
        else if (/\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n)) out.push(p);
    }
    return out;
}

const CSS = readFileSync(join(SRC, 'index.css'), 'utf-8');

describe('veste v2 delle pagine: inerte col guscio spento', () => {
    it('ogni regola su una classe .ds-v2-* vale solo dentro [data-shell="v2"]', () => {
        const fuori = selettori(CSS).filter((s) => s.includes('.ds-v2-') && !s.startsWith('[data-shell="v2"]'));
        expect(fuori, 'regole .ds-v2-* che varrebbero anche con ui.shell=off').toEqual([]);
    });

    it('ogni classe ds-v2-* usata nel codice e\' definita nel foglio', () => {
        const definite = new Set([...CSS.matchAll(/\.(ds-v2-[a-z0-9-]+)/g)].map((m) => m[1]));
        const mancanti: string[] = [];
        let usate = 0;
        for (const f of sorgentiTsx(SRC)) {
            for (const m of readFileSync(f, 'utf-8').matchAll(/\b(ds-v2-[a-z0-9-]+)/g)) {
                usate += 1;
                if (!definite.has(m[1])) mancanti.push(`${relative(SRC, f)}: ${m[1]}`);
            }
        }
        expect(usate).toBeGreaterThan(0);
        expect(mancanti).toEqual([]);
    });
});
