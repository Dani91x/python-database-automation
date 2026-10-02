// ============================================================================
// GUARDIA dei componenti base `components/ui/*` (shadcn) — redesign veste completa.
//
// Le pagine con guscio SPENTO usano questi componenti: il loro aspetto di
// default non deve cambiare mai per ragioni di redesign. La veste v2 si
// applica solo da fuori (classi .ds-v2-* sotto [data-shell="v2"]).
//
// Prova: le stringhe letterali di ogni file ui/* (classi di default, varianti
// cva, nomi) sono confrontate con l'istantanea presa da master alla partenza
// (`snapshot/ui-default.json`). Una classe tolta, aggiunta o cambiata = rosso.
// Rigenerare l'istantanea e' una decisione: UI_DEFAULT_AGGIORNA=1.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const SRC = (() => {
    for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
        const p = join(base, 'src');
        if (existsSync(join(p, 'index.css'))) return p;
    }
    throw new Error('src/ non trovata');
})();
const UI = join(SRC, 'components', 'ui');
const ISTANTANEA = join(SRC, 'fotografia', 'snapshot', 'ui-default.json');

/** stringhe letterali (doppi apici, apici singoli, backtick senza ${}) in ordine */
export function letterali(sorgente: string): string[] {
    const senzaCommenti = sorgente.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
    const out: string[] = [];
    for (const m of senzaCommenti.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`([^`$]*)`/g)) {
        out.push(m[1] ?? m[2] ?? m[3] ?? '');
    }
    return out;
}

function leggiTutti(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    for (const n of readdirSync(UI).filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f)).sort()) {
        out[n] = letterali(readFileSync(join(UI, n), 'utf-8').replace(/\r\n/g, '\n'));
    }
    return out;
}

describe('componenti ui/*: aspetto di default invariato', () => {
    it('le stringhe di classi e varianti di ogni file ui/* sono quelle di master', () => {
        const ora = leggiTutti();
        if (process.env.UI_DEFAULT_AGGIORNA === '1' || !existsSync(ISTANTANEA)) {
            writeFileSync(ISTANTANEA, JSON.stringify(ora, null, 1) + '\n');
        }
        const salvata = JSON.parse(readFileSync(ISTANTANEA, 'utf-8')) as Record<string, string[]>;
        expect(Object.keys(ora)).toEqual(Object.keys(salvata));
        for (const f of Object.keys(salvata)) {
            expect(ora[f], `components/ui/${f}: classi di default cambiate`).toEqual(salvata[f]);
        }
    });

    it('l\'estrattore vede davvero le classi (controprova)', () => {
        const l = letterali('const a = cn("rounded-md border", x); // "commento"\nconst b = cva(\'inline-flex\', {});');
        expect(l).toEqual(['rounded-md border', 'inline-flex']);
    });
});
