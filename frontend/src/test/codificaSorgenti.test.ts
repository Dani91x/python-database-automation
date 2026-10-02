// ============================================================================
// CODIFICA DEI SORGENTI (02/10/2026, FRONTEND MINORI A).
//
// `components/live/ScalperPanel.tsx` portava 85 sequenze di "mojibake": testo
// UTF-8 riletto come Windows-1252 e risalvato in UTF-8, cosi' a schermo si
// leggeva "\u00e2\u201a\u00ac0.71" invece di "\u20ac0.71" e "attivit\u00c3\u00a0" invece di
// "attivit\u00e0" (nei testi, nei toast, nel confirm dei soldi veri). Il file
// aveva anche il BOM. Qui si vieta PER SEMPRE, in ogni sorgente di src/:
//   - il BOM UTF-8 in testa al file;
//   - un carattere "di testa" di una sequenza UTF-8 multibyte letta in
//     cp1252 (\u00c2 \u00c3 per 2 byte, \u00e2 per 3, \u00f0 per 4) seguito da un carattere che
//     e' un byte di continuazione 0x80-0xBF letto in cp1252.
// Le sequenze qui sono scritte con gli escape \u, cosi' questo file non le
// contiene e non si accusa da solo.
// FALSIFICAZIONE: rimettendo una riga guasta di ScalperPanel (es. "Stake
// \u00e2\u201a\u00ac") o il BOM, il test diventa rosso e nomina file e riga.
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

/** i caratteri che cp1252 da' ai byte di continuazione UTF-8 0x80-0xBF
 *  (tabella scritta qui: il TextDecoder di Node senza ICU completo tratta
 *  windows-1252 come latin-1 e perderebbe 0x80-0x9F) */
const CP1252_80_9F = [
    0x20ac, 0x0081, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021,
    0x02c6, 0x2030, 0x0160, 0x2039, 0x0152, 0x008d, 0x017d, 0x008f,
    0x0090, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014,
    0x02dc, 0x2122, 0x0161, 0x203a, 0x0153, 0x009d, 0x017e, 0x0178,
];
const CONTINUAZIONE = String.fromCharCode(...CP1252_80_9F)
    + Array.from({ length: 0x20 }, (_, i) => String.fromCharCode(0xa0 + i)).join('');
const ESC = (s: string) => s.replace(/[\\\]^-]/g, '\\$&');
export const MOJIBAKE = new RegExp(`[\\u00c2\\u00c3\\u00e2\\u00f0][${ESC(CONTINUAZIONE)}]`, 'g');

function sorgenti(dir: string, out: string[] = []): string[] {
    for (const n of readdirSync(dir)) {
        const p = join(dir, n);
        if (statSync(p).isDirectory()) sorgenti(p, out);
        else if (/\.(tsx?|css|html|json)$/.test(n)) out.push(p);
    }
    return out;
}

describe('codifica dei sorgenti: UTF-8 pulito', () => {
    const FILE = sorgenti(SRC);

    it('controprova: la regola riconosce le sequenze guaste e lascia stare il testo buono', () => {
        const guasto = '\u00e2\u201a\u00ac0.71 attivit\u00c3\u00a0 \u00e2\u20ac\u201d \u00e2\u0161\u00a0\u00ef\u00b8\u008f \u00c2\u00b7 \u00f0\u0178\u017d\u00af';
        expect(guasto.match(MOJIBAKE)?.length).toBe(6);
        const buono = '\u20ac0.71 attivit\u00e0 \u2014 \u26a0\ufe0f \u00b7 \u2192 \u00e8\u2026 c\'\u00e8 \u00e0 \u00f9 perch\u00e9 \u00ab\u00bb \u2265 \u2212';
        expect(buono.match(MOJIBAKE)).toBeNull();
        expect(FILE.length).toBeGreaterThan(300);
    });

    it('nessun sorgente di src/ contiene mojibake (cp1252 al posto di UTF-8)', () => {
        const trovati: string[] = [];
        for (const p of FILE) {
            const righe = readFileSync(p, 'utf-8').split('\n');
            righe.forEach((r, i) => {
                const m = r.match(MOJIBAKE);
                if (m) trovati.push(`${relative(SRC, p)}:${i + 1} (${m.length}) ${r.trim().slice(0, 80)}`);
            });
        }
        expect(trovati).toEqual([]);
    });

    it('nessun sorgente di src/ comincia col BOM UTF-8', () => {
        const conBom = FILE.filter((p) => {
            const b = readFileSync(p);
            return b.length >= 3 && b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf;
        }).map((p) => relative(SRC, p));
        expect(conBom).toEqual([]);
    });
});
