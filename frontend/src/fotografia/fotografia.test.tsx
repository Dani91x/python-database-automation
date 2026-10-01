// ============================================================================
// FOTOGRAFIA — garanzia di parita' del redesign «guscio v2» (fase 0, 01/10/2026).
//
// Mandato: AUDIT_2026-10-01/REDESIGN/BRIEF_SESSIONE_CLOUD.md, fase 0.
// Rende OGNI pagina dell'app dentro il vero <App/> (rotte, ProtectedRoute,
// provider), in ENTRAMBI gli stati dell'interruttore `ui.shell` ('off' e 'v2'),
// e registra per pagina, nell'ordine del DOM:
//   - testi: il testo di ogni nodo di testo visibile al lettore (normalizzato);
//   - testid: ogni `data-testid`;
//   - comandi: bottoni, link, campi, tab, interruttori (ruolo + nome
//     accessibile + href/disabled e stato premuto/selezionato/spuntato).
// Le classi CSS NON entrano nella fotografia: il redesign cambia solo quelle.
//
// Le regole:
//   1. con 'off' la fotografia deve essere IDENTICA, byte per byte, a quella
//      salvata alla fase 0 in snapshot/<pagina>.off.json (= l'app di oggi);
//   2. con 'v2' il contenuto delle PAGINE deve essere identico a quello con
//      'off'. Cio' che il guscio aggiunge vive dentro elementi marcati
//      `data-shell-chrome` e viene registrato a parte (snapshot/<pagina>.<stato>.guscio.json),
//      con i soli data-testid della LISTA BIANCA qui sotto.
//
// Dati: client Supabase finto e deterministico (./supabaseFinto.ts, stessa
// forma delle risposte di supabase-js), canali locali spenti (src/test/setup.ts),
// orologio fermo al 2026-10-01 10:00 (Europe/Rome). I finti per pagina dei test
// esistenti (pages/*.test.tsx) non si possono riusare qui: `vi.mock` vale per
// file e quei finti si contraddicono fra loro; la fotografia usa quindi lo
// stato «backend vuoto» che e' lo stesso per tutte le pagine.
//
// Aggiornare le fotografie e' una DECISIONE, non una correzione:
//   FOTOGRAFIA_AGGIORNA=1 npx vitest run src/fotografia
// e il diff dei JSON va riletto riga per riga.
// ============================================================================
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { render, act, cleanup } from '@testing-library/react';
import { computeAccessibleName } from 'dom-accessibility-api';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

process.env.TZ = 'Europe/Rome';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./supabaseFinto');
    return { supabase: m.supabaseFinto };
});

// ---------------------------------------------------------------------------
// pagine fotografate
// ---------------------------------------------------------------------------
interface Pagina {
    nome: string;
    url: string;
    /** sessione dell'owner aperta (rotte protette) o nessuna sessione (pubbliche) */
    sessione: boolean;
}

export const PAGINE: Pagina[] = [
    { nome: 'board', url: '/board', sessione: true },
    { nome: 'control-room', url: '/control-room', sessione: true },
    { nome: 'dashboard', url: '/dashboard', sessione: true },
    { nome: 'omega', url: '/omega', sessione: true },
    { nome: 'safe-strategy', url: '/safe-strategy', sessione: true },
    { nome: 'mike', url: '/mike', sessione: true },
    { nome: 'segui-live', url: '/segui-live', sessione: true },
    { nome: 'multi-ladder', url: '/multi-ladder', sessione: true },
    { nome: 'market-watch', url: '/market-watch', sessione: true },
    { nome: 'live-pnl', url: '/live-pnl', sessione: true },
    { nome: 'storico-calcio', url: '/storico/calcio', sessione: true },
    { nome: 'storico-tennis', url: '/storico/tennis', sessione: true },
    { nome: 'tennis', url: '/tennis', sessione: true },
    { nome: 'tennis-terminal', url: '/tennis/terminal', sessione: true },
    {
        nome: 'tennis-terminal-match',
        url: '/tennis/terminal?event=34000001&market=1.250000001&name=Match%20Odds&p1=Giocatore%20Uno&p2=Giocatore%20Due',
        sessione: true,
    },
    { nome: 'trade-journal', url: '/trade-journal', sessione: true },
    { nome: 'report-personale', url: '/report-personale', sessione: true },
    { nome: 'watchlist', url: '/watchlist', sessione: true },
    { nome: 'analytics', url: '/analytics', sessione: true },
    { nome: 'match-replay', url: '/match-replay', sessione: true },
    { nome: 'select-sport', url: '/select-sport', sessione: true },
    // fuori dal guscio, sempre
    { nome: 'ladder-popout', url: '/ladder-popout?market=1.250000001&event=34000001&name=Match%20Odds', sessione: true },
    { nome: 'landing', url: '/', sessione: false },
    { nome: 'check-email', url: '/check-email', sessione: false },
    { nome: 'reset-password', url: '/reset-password', sessione: false },
    { nome: 'notfound', url: '/pagina-che-non-esiste', sessione: false },
];

/**
 * LISTA BIANCA di cio' che il guscio aggiunge (solo dentro `data-shell-chrome`).
 * Ogni data-testid trovato nella cornice deve stare qui: un testid nuovo nel
 * guscio e' una decisione da scrivere, non un effetto collaterale.
 */
export const LISTA_BIANCA_GUSCIO: readonly string[] = [];

// ---------------------------------------------------------------------------
// raccolta
// ---------------------------------------------------------------------------
interface Comando {
    ruolo: string;
    nome: string;
    href?: string;
    disabled?: true;
    premuto?: string;
    selezionato?: string;
    spuntato?: string;
}

interface Fotografia {
    pagina: string;
    url: string;
    titolo: string;
    testi: string[];
    testid: string[];
    comandi: Comando[];
}

const SALTA_TAG = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
const RUOLI_IMPLICITI: Record<string, string> = {
    BUTTON: 'button',
    SELECT: 'combobox',
    TEXTAREA: 'textbox',
};
const RUOLI_COMANDO = new Set([
    'button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'switch', 'tab',
    'menuitem', 'option', 'slider', 'spinbutton', 'searchbox', 'menuitemcheckbox', 'menuitemradio',
]);

function norm(s: string): string {
    return s.replace(/\s+/g, ' ').trim();
}

function ruoloDi(el: Element): string | null {
    const esplicito = el.getAttribute('role');
    if (esplicito) return esplicito.split(' ')[0];
    if (el.tagName === 'A' && el.hasAttribute('href')) return 'link';
    if (el.tagName === 'INPUT') {
        const t = (el.getAttribute('type') || 'text').toLowerCase();
        if (t === 'hidden') return null;
        if (t === 'checkbox') return 'checkbox';
        if (t === 'radio') return 'radio';
        if (t === 'range') return 'slider';
        if (t === 'number') return 'spinbutton';
        if (t === 'search') return 'searchbox';
        if (t === 'button' || t === 'submit' || t === 'reset') return 'button';
        return 'textbox';
    }
    return RUOLI_IMPLICITI[el.tagName] ?? null;
}

function comandoDi(el: Element): Comando | null {
    const ruolo = ruoloDi(el);
    if (!ruolo || !RUOLI_COMANDO.has(ruolo)) return null;
    const c: Comando = { ruolo, nome: norm(computeAccessibleName(el)) };
    if (el.tagName === 'A' && el.getAttribute('href') != null) c.href = el.getAttribute('href') as string;
    if ((el as HTMLButtonElement).disabled === true || el.getAttribute('aria-disabled') === 'true') c.disabled = true;
    const p = el.getAttribute('aria-pressed');
    if (p != null) c.premuto = p;
    const s = el.getAttribute('aria-selected');
    if (s != null) c.selezionato = s;
    const k = el.getAttribute('aria-checked');
    if (k != null) c.spuntato = k;
    else if (el.tagName === 'INPUT' && ['checkbox', 'radio'].includes((el as HTMLInputElement).type)) {
        c.spuntato = String((el as HTMLInputElement).checked);
    }
    return c;
}

interface Raccolta {
    testi: string[];
    testid: string[];
    comandi: Comando[];
}

function vuota(): Raccolta {
    return { testi: [], testid: [], comandi: [] };
}

/** visita il DOM in ordine; i sottoalberi `data-shell-chrome` vanno nella raccolta del guscio */
function raccogli(radice: Element): { pagina: Raccolta; guscio: Raccolta } {
    const pagina = vuota();
    const guscio = vuota();
    const visita = (n: Node, dest: Raccolta) => {
        if (n.nodeType === 3) {
            const t = norm(n.textContent || '');
            if (t) dest.testi.push(t);
            return;
        }
        if (n.nodeType !== 1) return;
        const el = n as Element;
        if (SALTA_TAG.has(el.tagName)) return;
        const qui = el.hasAttribute('data-shell-chrome') ? guscio : dest;
        const tid = el.getAttribute('data-testid');
        if (tid) qui.testid.push(tid);
        const c = comandoDi(el);
        if (c) qui.comandi.push(c);
        for (const figlio of Array.from(el.childNodes)) visita(figlio, qui);
    };
    visita(radice, pagina);
    return { pagina, guscio };
}

function scatta(p: Pagina): { pagina: Fotografia; guscio: Raccolta } {
    const { pagina, guscio } = raccogli(document.body);
    return {
        pagina: { pagina: p.nome, url: p.url, titolo: norm(document.title), ...pagina },
        guscio,
    };
}

function serializza(x: unknown): string {
    return JSON.stringify(x, null, 2) + '\n';
}

// ---------------------------------------------------------------------------
// ambiente deterministico
// ---------------------------------------------------------------------------
const CARTELLA = join(process.cwd().endsWith('frontend') ? process.cwd() : join(process.cwd(), 'frontend'), 'src', 'fotografia', 'snapshot');
const AGGIORNA = process.env.FOTOGRAFIA_AGGIORNA === '1';
const ORA_FERMA = new Date('2026-10-01T08:00:00.000Z'); // 10:00 a Roma

beforeAll(() => {
    vi.useFakeTimers({ toFake: ['Date'], now: ORA_FERMA });
    const w = window as unknown as Record<string, unknown>;
    if (typeof w.matchMedia !== 'function') {
        w.matchMedia = (q: string) => ({
            matches: false, media: q, onchange: null,
            addListener: () => {}, removeListener: () => {},
            addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
        });
    }
    class Osservatore { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } }
    if (typeof w.ResizeObserver !== 'function') w.ResizeObserver = Osservatore;
    if (typeof w.IntersectionObserver !== 'function') w.IntersectionObserver = Osservatore;
    w.scrollTo = () => {};
    Element.prototype.scrollIntoView = function () {};
    if (!existsSync(CARTELLA)) mkdirSync(CARTELLA, { recursive: true });
});

afterAll(() => {
    vi.useRealTimers();
});

async function attendi(ms: number) {
    await act(async () => {
        await new Promise((r) => setTimeout(r, ms));
    });
}

/** attende che la pagina smetta di cambiare (5 letture uguali di fila, ~400 ms), al massimo 6 s */
async function attendiStabile(p: Pagina): Promise<{ pagina: Fotografia; guscio: Raccolta }> {
    await attendi(300);
    let prima = serializza(scatta(p));
    let uguali = 0;
    for (let i = 0; i < 75 && uguali < 5; i++) {
        await attendi(80);
        const ora = serializza(scatta(p));
        if (ora === prima) uguali += 1;
        else { uguali = 0; prima = ora; }
    }
    return scatta(p);
}

async function fotografa(p: Pagina, stato: 'off' | 'v2') {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
    if (stato === 'v2') localStorage.setItem('ui.shell', 'v2');
    else localStorage.setItem('ui.shell', 'off');
    const finto = await import('./supabaseFinto');
    finto.impostaSessione(p.sessione);
    finto.azzeraRegistro();
    window.history.replaceState(null, '', p.url);
    document.title = '';
    const { default: App } = await import('@/App');
    render(<App />);
    const foto = await attendiStabile(p);
    const chiamate = {
        // nomi distinti: il NUMERO di giri dei poll dipende da quanto dura l'attesa
        rpc: [...new Set(finto.registro.rpc)].sort(),
        from: [...new Set(finto.registro.from)].sort(),
        channel: finto.registro.channel,
    };
    cleanup();
    return { ...foto, chiamate };
}

function confronta(file: string, attuale: string) {
    const percorso = join(CARTELLA, file);
    if (AGGIORNA) {
        writeFileSync(percorso, attuale, 'utf-8');
        return;
    }
    expect(existsSync(percorso), `manca la fotografia ${file}: va scattata con FOTOGRAFIA_AGGIORNA=1 e committata`).toBe(true);
    const salvata = readFileSync(percorso, 'utf-8').replace(/\r\n/g, '\n');
    expect(attuale, `la fotografia ${file} e' cambiata`).toBe(salvata);
}

function confrontaGuscio(file: string, guscio: Raccolta) {
    const percorso = join(CARTELLA, file);
    const vuoto = guscio.testi.length === 0 && guscio.testid.length === 0 && guscio.comandi.length === 0;
    if (AGGIORNA) {
        if (!vuoto) writeFileSync(percorso, serializza(guscio), 'utf-8');
        return;
    }
    if (vuoto) {
        expect(existsSync(percorso), `il guscio di ${file} e' sparito ma la fotografia esiste`).toBe(false);
        return;
    }
    confronta(file, serializza(guscio));
}

describe('fotografia di parita\' (guscio v2)', () => {
    for (const p of PAGINE) {
        it(`${p.nome}: 'off' identica alla fase 0, 'v2' con le stesse pagine`, async () => {
            const off = await fotografa(p, 'off');
            const v2 = await fotografa(p, 'v2');

            // 1. con l'interruttore spento l'app e' quella di oggi, byte per byte
            confronta(`${p.nome}.off.json`, serializza(off.pagina));
            confrontaGuscio(`${p.nome}.off.guscio.json`, off.guscio);

            // 2. col guscio acceso il contenuto delle PAGINE non cambia di un testo,
            //    di un testid o di un comando: cambia solo la cornice
            expect(serializza(v2.pagina), `${p.nome}: col guscio acceso la pagina e' diversa`).toBe(serializza(off.pagina));
            confronta(`${p.nome}.v2.json`, serializza(v2.pagina));
            confrontaGuscio(`${p.nome}.v2.guscio.json`, v2.guscio);

            // 3. la cornice porta solo testid della lista bianca
            for (const g of [off.guscio, v2.guscio]) {
                const estranei = g.testid.filter((t) => !LISTA_BIANCA_GUSCIO.includes(t));
                expect(estranei, `${p.nome}: testid del guscio fuori dalla lista bianca`).toEqual([]);
            }

            // 4. il guscio non fa letture: stesse RPC, tabelle e canali realtime
            expect(v2.chiamate, `${p.nome}: col guscio acceso cambiano le chiamate al backend`).toEqual(off.chiamate);
        }, 60_000);
    }
});
