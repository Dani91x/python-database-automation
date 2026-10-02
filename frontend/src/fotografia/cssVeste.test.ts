// ============================================================================
// GUARDIA della VESTE COMPLETA (brief 2, redesign 01/10/2026).
//
// Tutta la veste nuova vive in fondo a index.css, dopo il marcatore
// «VESTE COMPLETA (brief 2». Qui si prova che:
//  1. OGNI selettore di quella sezione e' condizionato dal guscio acceso
//     ([data-shell="v2"], :where([data-shell="v2"]) o, solo per i portali
//     Radix, :where(body:has([data-shell="v2"])) con classi .ds-portale-v2-*);
//  2. nessun selettore nomina una classe di default di components/ui/*
//     (l'aspetto di default dei componenti base non cambia mai);
//  3. ogni classe ds-portale-v2-* usata nel codice e' definita;
//  4. contrasto testo/sfondo >= 4,5:1 (>= 3:1 per i testi grandi) per ogni
//     regola che dichiara un colore di testo, sul fondo dichiarato o sul
//     peggiore dei fondi del prototipo (background, card, muted, glass);
//  5. nessuna dimensione di carattere sotto i 10 px.
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

const CSS = readFileSync(join(SRC, 'index.css'), 'utf-8');
const MARCATORE = 'VESTE COMPLETA (brief 2';

export interface Regola { selettori: string[]; corpo: string }

/** regole (selettori + dichiarazioni) di un foglio, senza commenti; le @media si attraversano */
export function regole(css: string): Regola[] {
    const senza = css.replace(/\/\*[\s\S]*?\*\//g, '');
    const out: Regola[] = [];
    const re = /([^{}]+)\{([^{}]*)\}/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(senza))) {
        const testa = m[1].trim().replace(/^@media[^{]*\{/, '').trim();
        const sel = testa.split(',').map((s) => s.trim()).filter((s) => s && !s.startsWith('@'));
        if (sel.length) out.push({ selettori: sel, corpo: m[2] });
    }
    return out;
}

export function sezioneVeste(css: string): string {
    const i = css.indexOf(MARCATORE);
    if (i < 0) throw new Error('marcatore della veste non trovato');
    // dal commento che contiene il marcatore in poi
    return css.slice(css.lastIndexOf('/*', i));
}

const PREFISSI = ['[data-shell="v2"]', ':where([data-shell="v2"])', ':where(body:has([data-shell="v2"]))'];

export function condizionato(sel: string): boolean {
    return PREFISSI.some((p) => sel.startsWith(p));
}

/** classi nominate in un selettore, con gli escape di Tailwind tolti */
export function classiDi(sel: string): string[] {
    return [...sel.matchAll(/\.((?:\\.|[A-Za-z0-9_-])+)/g)].map((m) => m[1].replace(/\\(.)/g, '$1'));
}

function classiUi(): Set<string> {
    const s = new Set<string>();
    const UI = join(SRC, 'components', 'ui');
    for (const n of readdirSync(UI).filter((f) => /\.tsx?$/.test(f))) {
        const src = readFileSync(join(UI, n), 'utf-8');
        for (const m of src.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`$]*)`/g)) {
            for (const t of (m[1] ?? m[2] ?? m[3] ?? '').split(/\s+/)) {
                // si guarda la classe base (senza varianti hover:, data-[...]:)
                const base = t.split(':').pop() ?? '';
                if (base && !base.startsWith('ds-v2-')) s.add(base);
            }
        }
    }
    return s;
}

// ---- colori e contrasto (WCAG 2.x) -----------------------------------------
type RGBA = [number, number, number, number];

function tokens(css: string): Record<string, string> {
    const root = css.match(/:root\s*\{([\s\S]*?)\}/);
    const out: Record<string, string> = {};
    for (const m of (root ? root[1] : '').matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
    return out;
}
const TOK = tokens(CSS);

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
    s /= 100; l /= 100;
    const k = (n: number) => (n + h / 30) % 12;
    const a = s * Math.min(l, 1 - l);
    const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return [f(0) * 255, f(8) * 255, f(4) * 255];
}

/** interpreta un colore CSS del foglio; null se non e' un colore pieno interpretabile */
export function colore(v: string): RGBA | null {
    v = v.replace(/!important/, '').trim();
    let m = v.match(/^hsl\(var\(--([a-z0-9-]+)\)(?:\s*\/\s*([\d.]+))?\)$/);
    if (m) {
        const t = TOK[m[1]];
        if (!t) return null;
        const [h, s, l] = t.split(/\s+/).map((x) => parseFloat(x));
        return [...hslToRgb(h, s, l), m[2] ? parseFloat(m[2]) : 1];
    }
    m = v.match(/^#([0-9a-f]{6})$/i);
    if (m) return [parseInt(m[1].slice(0, 2), 16), parseInt(m[1].slice(2, 4), 16), parseInt(m[1].slice(4, 6), 16), 1];
    m = v.match(/^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:\s*[,/]\s*([\d.]+))?\s*\)$/);
    if (m) return [+m[1], +m[2], +m[3], m[4] ? parseFloat(m[4]) : 1];
    return null;
}

function sopra(c: RGBA, fondo: [number, number, number]): [number, number, number] {
    return [0, 1, 2].map((i) => c[i] * c[3] + fondo[i] * (1 - c[3])) as [number, number, number];
}

function luminanza([r, g, b]: [number, number, number]): number {
    const f = (x: number) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrasto(a: [number, number, number], b: [number, number, number]): number {
    const [x, y] = [luminanza(a), luminanza(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
}

const FONDI_PAGINA = ['background', 'card', 'muted', 'glass'].map((t) => {
    const c = colore(`hsl(var(--${t}))`);
    if (!c) throw new Error(`token --${t} mancante`);
    return [c[0], c[1], c[2]] as [number, number, number];
});

function dichiarazione(corpo: string, prop: string): string | null {
    const m = corpo.match(new RegExp(`(?:^|;|\\s)${prop}\\s*:\\s*([^;]+)`));
    return m ? m[1].trim() : null;
}

const VESTE = sezioneVeste(CSS);
const REGOLE = regole(VESTE);

describe('veste completa: confinata al guscio acceso', () => {
    it('la sezione esiste e ha regole', () => {
        expect(REGOLE.length).toBeGreaterThan(10);
    });

    it('ogni selettore della sezione e\' condizionato da [data-shell="v2"]', () => {
        const fuori = REGOLE.flatMap((r) => r.selettori).filter((s) => !condizionato(s));
        expect(fuori, 'selettori che varrebbero anche con ui.shell=off').toEqual([]);
    });

    it('la forma dei portali (body:has) si usa solo con classi .ds-portale-v2-*', () => {
        const male = REGOLE.flatMap((r) => r.selettori)
            .filter((s) => s.startsWith(PREFISSI[2]))
            .filter((s) => !classiDi(s).some((c) => c.startsWith('ds-portale-v2-')));
        expect(male).toEqual([]);
    });

    it('nessun selettore nomina una classe di default di components/ui/*', () => {
        const ui = classiUi();
        const tocca = REGOLE.flatMap((r) => r.selettori)
            .flatMap((s) => classiDi(s).filter((c) => ui.has(c)).map((c) => `${s}  ->  .${c}`));
        expect(tocca).toEqual([]);
    });

    it('ogni classe ds-portale-v2-* usata nel codice e\' definita nella sezione', () => {
        const definite = new Set(REGOLE.flatMap((r) => r.selettori).flatMap(classiDi));
        const mancanti: string[] = [];
        const visita = (dir: string) => {
            for (const n of readdirSync(dir)) {
                const p = join(dir, n);
                if (statSync(p).isDirectory()) visita(p);
                else if (/\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n)) {
                    for (const m of readFileSync(p, 'utf-8').matchAll(/\b(ds-portale-v2-[a-z0-9-]+)/g)) {
                        if (!definite.has(m[1])) mancanti.push(`${relative(SRC, p)}: ${m[1]}`);
                    }
                }
            }
        };
        visita(SRC);
        expect(mancanti).toEqual([]);
    });
});

describe('veste completa: leggibilita\'', () => {
    it('contrasto del testo >= 4,5:1 (>= 3:1 se grande) su fondo dichiarato o sui fondi del prototipo', () => {
        const scarsi: string[] = [];
        let misurate = 0;
        for (const r of REGOLE) {
            const c = dichiarazione(r.corpo, 'color');
            if (!c) continue;
            const fg = colore(c);
            if (!fg) continue;
            const bgDich = dichiarazione(r.corpo, 'background-color') ?? dichiarazione(r.corpo, 'background');
            const bgCol = bgDich ? colore(bgDich) : null;
            const fondi = bgCol ? FONDI_PAGINA.map((f) => sopra(bgCol, f)) : FONDI_PAGINA;
            const px = parseFloat(dichiarazione(r.corpo, 'font-size') ?? '13');
            const peso = parseFloat(dichiarazione(r.corpo, 'font-weight') ?? '400');
            const grande = px >= 18 || (px >= 14 && peso >= 700);
            const soglia = grande ? 3 : 4.5;
            const minimo = Math.min(...fondi.map((f) => contrasto(sopra(fg, f), f)));
            misurate += 1;
            if (minimo < soglia) scarsi.push(`${r.selettori[0]}: ${minimo.toFixed(2)} < ${soglia}`);
        }
        expect(misurate).toBeGreaterThan(5);
        expect(scarsi).toEqual([]);
    });

    it('nessuna dimensione di carattere sotto i 10 px', () => {
        const piccole = REGOLE.flatMap((r) => {
            const fs = dichiarazione(r.corpo, 'font-size');
            return fs && /px$/.test(fs) && parseFloat(fs) < 10 ? [`${r.selettori[0]}: ${fs}`] : [];
        });
        expect(piccole).toEqual([]);
    });

    // 02/10 (FRONTEND MINORI C): a guscio acceso "LIVE · REALE" del Tennis
    // Terminal passava dal rosso PIENO di oggi (bg-red-500 text-white) alla
    // tinta chiara di `.ds-v2-chip--live`: l'avviso dei soldi veri MENO
    // vistoso. Qui, per OGNI marcatore `ds-v2-chip--live` del codice, si
    // calcola la resa a guscio acceso (regole della veste che si applicano
    // alle sue classi, in ordine di specificita' e di foglio) e si pretende:
    // colore d'allarme (rosso), contrasto >= 4,5:1 e, dove oggi lo sfondo e'
    // rosso pieno, sfondo rosso pieno anche col guscio.
    // FALSIFICAZIONE: togliendo la regola `.ds-v2-chip--live.bg-red-500` il
    // Tennis Terminal torna a sfondo al 14 % -> rosso.
    it('ogni marcatore LIVE resta d\'allarme a guscio acceso: rosso, contrasto >= 4,5:1, pieno dove oggi e\' pieno', () => {
        const marcatori = new Map<string, string>();
        const visita = (dir: string) => {
            for (const n of readdirSync(dir)) {
                const p = join(dir, n);
                if (statSync(p).isDirectory()) visita(p);
                else if (/\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n)) {
                    const src = readFileSync(p, 'utf-8');
                    for (const m of src.matchAll(/'([^'\n]*)'|"([^"\n]*)"/g)) {
                        const testo = m[1] ?? m[2] ?? '';
                        if (/(^|\s)ds-v2-chip--live(\s|$)/.test(testo)) marcatori.set(`${relative(SRC, p)}: ${testo}`, testo);
                    }
                }
            }
        };
        visita(SRC);
        // PannelloBot (modalita' del bot), FasciaStop (stop LIVE), TennisTerminal (LIVE · REALE)
        expect(marcatori.size).toBeGreaterThanOrEqual(3);

        const COMPOSTO = /^\[data-shell="v2"\]\s+((?:\.(?:\\.|[A-Za-z0-9_-])+)+)$/;
        const ROSSO_TW: Record<string, string> = { 'red-500': '#ef4444', 'red-600': '#dc2626', 'red-700': '#b91c1c' };
        const rosso = (c: RGBA | [number, number, number]) => c[0] >= 150 && c[0] > 1.5 * c[1] && c[0] > 1.5 * c[2];
        const male: string[] = [];
        for (const [dove, testo] of marcatori) {
            const classi = new Set([...testo.split(/\s+/).filter(Boolean), 'ds-v2-chip']);
            // regole della veste che valgono per queste classi, nell'ordine della cascata
            const valide: { spec: number; ordine: number; corpo: string }[] = [];
            REGOLE.forEach((r, ordine) => {
                for (const s of r.selettori) {
                    const m = s.match(COMPOSTO);
                    if (!m) continue;
                    const cl = classiDi(m[1]);
                    if (cl.every((c) => classi.has(c))) valide.push({ spec: cl.length, ordine, corpo: r.corpo });
                }
            });
            valide.sort((a, b) => a.spec - b.spec || a.ordine - b.ordine);
            let bg: RGBA | null = null;
            let fg: RGBA | null = null;
            for (const v of valide) {
                const b = dichiarazione(v.corpo, 'background-color');
                const f = dichiarazione(v.corpo, 'color');
                if (b && colore(b)) bg = colore(b);
                if (f && colore(f)) fg = colore(f);
            }
            if (!bg || !fg) { male.push(`${dove}: colori a guscio acceso non dichiarati`); continue; }
            const fondi = FONDI_PAGINA.map((f) => sopra(bg as RGBA, f));
            const minimo = Math.min(...fondi.map((f) => contrasto(sopra(fg as RGBA, f), f)));
            if (minimo < 4.5) male.push(`${dove}: contrasto ${minimo.toFixed(2)} < 4,5`);
            // il rosso si giudica su quello che si VEDE: sfondo e testo composti sui fondi della pagina
            // (una tinta al 14 % su fondo scuro non e' "rossa": lo deve essere il testo)
            if (!fondi.every((f) => rosso(f) || rosso(sopra(fg as RGBA, f)))) {
                male.push(`${dove}: ne' sfondo ne' testo rossi a schermo`);
            }
            const oggi = testo.match(/(?:^|\s)bg-(red-\d00)(\/\d+)?(?=\s|$)/);
            if (oggi && !oggi[2]) {
                const pieno = colore(ROSSO_TW[oggi[1]] ?? '');
                if (pieno && (bg[3] < 1 || !rosso(bg))) {
                    male.push(`${dove}: oggi sfondo ${oggi[1]} PIENO, a guscio acceso alfa ${bg[3]} (${bg.slice(0, 3).join(',')})`);
                }
            }
        }
        expect(male).toEqual([]);
    });

    it('la funzione di contrasto e\' quella WCAG (controprova)', () => {
        expect(contrasto([255, 255, 255], [0, 0, 0])).toBeCloseTo(21, 0);
        expect(contrasto([119, 119, 119], [255, 255, 255])).toBeCloseTo(4.48, 1);
    });
});
