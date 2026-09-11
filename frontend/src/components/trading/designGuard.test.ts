// ============================================================================
// designGuard.test.ts — GUARDIA MECCANICA del design system di trading.
//
// I test dei componenti provano che UNA vista sia giusta oggi. Questo legge i
// SORGENTI delle tre sezioni (Omega, Safe Strategy, Mike) e dei componenti
// condivisi e verifica le regole del DESIGN_SYSTEM.md che nessun test di
// rendering può difendere:
//
//   §1  un solo formato monetario: niente `toFixed` su denaro, niente `€${…}`
//   §2  le quote passano da fmtOdds (mai `price.toFixed(2)`)
//   §3  nessuno stato in INGLESE sotto gli occhi del trader
//   §19 nessuna mappa di etichette duplicata: la parola la dice lib/tradeStatus
//
// Perché serve: l'audit dell'11/09 ha contato 38 formatter duplicati e stati
// inglesi in quattro componenti. Un fix a mano si riapre alla prossima PR; una
// guardia che legge i file no. Ogni eccezione è ELENCATA qui sotto con il suo
// motivo: aggiungerne una è una decisione, non una dimenticanza.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';

// vitest gira con cwd = frontend/ (vite.config.ts). Si risale comunque, per
// non dipendere da dove è stato lanciato il comando.
const SRC = (() => {
    for (const base of [process.cwd(), join(process.cwd(), 'frontend'), join(process.cwd(), '..')]) {
        const p = join(base, 'src');
        if (existsSync(join(p, 'lib', 'format.ts'))) return p;
    }
    throw new Error('cartella src/ non trovata: la guardia di design non può leggere i sorgenti');
})();

/** cartelle delle tre sezioni + il guscio condiviso */
const AREE = [
    'components/trading',
    'components/omega',
    'components/safestrategy',
    'components/mike',
];
/** file singoli del guscio condiviso (fondamenta pure) */
const LIB = ['lib/format.ts', 'lib/tradeStatus.ts', 'lib/toasts.ts'];

function sorgenti(): { path: string; text: string }[] {
    const out: { path: string; text: string }[] = [];
    const visita = (dir: string) => {
        for (const name of readdirSync(dir)) {
            const p = join(dir, name);
            if (statSync(p).isDirectory()) { visita(p); continue; }
            if (!/\.(ts|tsx)$/.test(name)) continue;
            if (/\.test\.(ts|tsx)$/.test(name)) continue;   // i test possono asserire qualunque stringa
            out.push({ path: relative(SRC, p).replace(/\\/g, '/'), text: readFileSync(p, 'utf-8') });
        }
    };
    for (const a of AREE) visita(join(SRC, a));
    for (const f of LIB) out.push({ path: f, text: readFileSync(join(SRC, f), 'utf-8') });
    return out;
}

const FILES = sorgenti();

/** righe di un file con il loro numero, senza commenti di riga */
function righe(text: string): { n: number; line: string }[] {
    return text.split(/\r?\n/).map((line, i) => ({ n: i + 1, line }))
        .filter(({ line }) => !/^\s*(\/\/|\*|\/\*)/.test(line));
}

/** `file:riga` di ogni riga (non commento) che matcha */
function violazioni(re: RegExp, salta: (f: string, line: string) => boolean = () => false): string[] {
    const out: string[] = [];
    for (const { path, text } of FILES) {
        for (const { n, line } of righe(text)) {
            if (!re.test(line)) continue;
            if (salta(path, line)) continue;
            out.push(`${path}:${n} → ${line.trim().slice(0, 120)}`);
        }
    }
    return out;
}

describe('design system — un solo formato per i numeri (§1, §2)', () => {
    it('nessun sorgente costruisce denaro a mano (toFixed / €${…})', () => {
        const found = violazioni(
            /toFixed\(\s*[012]\s*\)|€\$\{|\$\{[^}]*\}\s*€/,
            (path, line) => (
                // `format.ts` È il formatter: è l'unico che può usare toFixed
                path === 'lib/format.ts'
                // valore di un campo di INPUT (non è testo mostrato): l'utente
                // digita "12.50" nella casella, non "12,50 €"
                || /setStakeStr|setAmountStr|value=\{|defaultValue|\.toFixed\(2\)\);\s*$/.test(line)
                // chiavi/id tecnici e arrotondamenti di CALCOLO (non display)
                || /Math\.round|parseFloat|Number\(/.test(line)
            ),
        );
        expect(found, `denaro/quote formattati a mano:\n${found.join('\n')}`).toEqual([]);
    });

    it('nessuna percentuale costruita con un replace locale', () => {
        const found = violazioni(
            /toFixed\([0-9]\)\s*\.replace\(\s*'\.'\s*,\s*','\s*\)/,
            (path) => path === 'lib/format.ts',
        );
        expect(found, `percentuali fatte a mano:\n${found.join('\n')}`).toEqual([]);
    });

    it('i formatter locali, se esistono, DELEGANO a lib/format', () => {
        /**
         * DEBITO NOTO fuori dal perimetro Omega/condiviso (certificazione
         * 11/09): formatter che duplicano lib/format in file di ALTRE sezioni.
         * Vanno corretti da chi presidia quella sezione — elencarli qui li
         * tiene visibili invece di allargare la regola.
         *   · safestrategy/SignalCard.tsx `fmtAgo()` → duplica `fmtAge()`
         *     (`"3m fa"` invece di `"3 min"`): §1 dell'audit.
         */
        const DEBITO_ALTRE_SEZIONI = new Set(['components/safestrategy/SignalCard.tsx']);
        for (const { path, text } of FILES) {
            if (path === 'lib/format.ts' || DEBITO_ALTRE_SEZIONI.has(path)) continue;
            const decl = text.match(/function\s+(fmt[A-Za-z]*)\s*\([^)]*\)\s*:\s*string\s*\{([\s\S]*?)\n\}/g) ?? [];
            for (const body of decl) {
                const nome = /function\s+(fmt[A-Za-z]*)/.exec(body)?.[1] ?? '?';
                const delega = /fmtMoney|fmtOdds|fmtPct|fmtNum|fmtTime|fmtDateTime|fmtAge|fmtTicks|DASH/.test(body);
                expect(delega, `${path}: ${nome}() non delega a lib/format`).toBe(true);
            }
        }
    });
});

describe('design system — nessuno stato in inglese (§3)', () => {
    // Parole che il DB usa come CHIAVI e che non devono mai arrivare a schermo
    // come etichetta. Si cerca la forma "etichetta": una stringa maiuscola
    // uguale alla chiave del DB.
    // NOTA: 'VOID' NON è in lista — è il termine Betfair che il trader usa
    // ("mercato void"), non una chiave inglese da tradurre. Lo dice il
    // glossario del DESIGN_SYSTEM (§ tabella stati).
    const CHIAVI_DB = [
        'PENDING', 'OPEN', 'HEDGED', 'WON', 'LOST', 'ERROR',
        'IDLE', 'RUNNING', 'STOPPING', 'STOPPED', 'ARMING', 'ARMED', 'REQUESTED',
        'PROCESSING', 'DONE', 'FAILED', 'SKIPPED', 'CANCELLED',
    ];

    it('nessuna label è la chiave del DB in maiuscolo', () => {
        const re = new RegExp(`label:\\s*'(${CHIAVI_DB.join('|')})'`);
        const found = violazioni(re);
        expect(found, `stati in inglese come etichetta:\n${found.join('\n')}`).toEqual([]);
    });

    it('nessuno `.status.toUpperCase()` mostrato senza mappa', () => {
        // `status.toUpperCase()` dentro JSX = la chiave del DB a schermo
        const found = violazioni(
            /\{[^}]*\bstatus\b[^}]*\.toUpperCase\(\)[^}]*\}/,
            // `mode.toUpperCase()` è legittimo: PAPER/LIVE sono già le parole giuste
            (_p, line) => /\bmode\b/.test(line),
        );
        expect(found, `stato del DB mostrato grezzo:\n${found.join('\n')}`).toEqual([]);
    });

    it('nessun fallback `?? x.status` che finisce a schermo', () => {
        const found = violazioni(/\?\?\s*[a-z]+\.status(?:\.toUpperCase\(\))?\s*[,;)]/);
        expect(found, `fallback sulla chiave del DB:\n${found.join('\n')}`).toEqual([]);
    });
});

describe('design system — una sola mappa per le etichette (§19)', () => {
    it('nessun componente ridefinisce la mappa degli stati dei trade', () => {
        // una mappa locale si riconosce dal set di etichette: se un file
        // contiene VINTO+PERSO+APERTO senza importare tradeStatus, è un doppione
        const colpevoli: string[] = [];
        for (const { path, text } of FILES) {
            if (path === 'lib/tradeStatus.ts') continue;
            const ha = ['VINTO', 'PERSO', 'APERTO'].every((w) => text.includes(`'${w}'`));
            if (ha && !/from '@\/lib\/tradeStatus'/.test(text)) colpevoli.push(path);
        }
        expect(colpevoli, `mappa degli stati duplicata in:\n${colpevoli.join('\n')}`).toEqual([]);
    });

    it('il glossario è UNO: nessun sinonimo vietato nei sorgenti', () => {
        // §4 dell'audit: "Capitale a rischio"/"responsabilità"/"Cash-out" sono
        // i tre sinonimi che il glossario ha sostituito
        const found = violazioni(/'Capitale a rischio'|'Cash-out'|"Cash-out"|>Cash-out</);
        expect(found, `sinonimi fuori glossario:\n${found.join('\n')}`).toEqual([]);
    });
});

describe('la guardia guarda davvero', () => {
    it('ha raccolto i sorgenti delle tre sezioni e del guscio', () => {
        expect(FILES.length).toBeGreaterThan(30);
        for (const atteso of [
            'components/trading/CashOutButton.tsx',
            'components/trading/DayBar.tsx',
            'components/omega/MatchTradesTable.tsx',
            'components/omega/MissionCard.tsx',
            'lib/tradeStatus.ts',
        ]) {
            expect(FILES.some((f) => f.path === atteso), `sorgente non letto: ${atteso}`).toBe(true);
        }
    });

    it('riconosce una violazione di prova', () => {
        // la regex del denaro deve agganciare la forma tipica del bug
        expect(/toFixed\(\s*[012]\s*\)|€\$\{/.test('`€${v.toFixed(2)}`')).toBe(true);
        expect(/toFixed\(\s*[012]\s*\)|€\$\{/.test('fmtMoney(v)')).toBe(false);
    });
});
