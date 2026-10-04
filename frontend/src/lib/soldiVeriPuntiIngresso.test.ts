// ============================================================================
// soldiVeriPuntiIngresso.test.ts — OGNI PUNTO D'INGRESSO AL LIVE PASSA DALLA
// VERIFICA CONDIVISA (04/10, ordine dell'utente «per tutti i bot»).
//
// Contratto sul SORGENTE: i punti che accendono un bot con la modalita' scelta
// senza passare da `creaInterruttori` (l'«Avvia» delle pagine dei singoli bot)
// devono chiamare la verifica di `@/lib/interruttori` PRIMA dell'RPC; quelli che
// passano da `creaInterruttori` devono dargli `catenaLive`. Un punto nuovo che
// chiama `activate*` senza verifica rompe questo test.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = resolve(__dirname, '..');
const leggi = (p: string) => readFileSync(resolve(SRC, p), 'utf8');

/** [file, chiamata RPC di accensione, verifica che deve precederla] */
const AVVII_DIRETTI: Array<[string, string, string]> = [
    ['pages/Omega.tsx', 'await activateOmega(mode, goalInput,', 'verificaSoldiVeri(interruttoreDi(\'omega\'), mode,'],
    ['components/mike/useMike.ts', 'return activateMike(desiredMode);', 'verificaSoldiVeri(interruttoreDi(\'mike\'), desiredMode,'],
    ['components/safestrategy/useSafeBot.ts', 'return activateSafe(desiredMode);', 'verificaSoldiVeriSafe('],
];

/** i file che costruiscono i comandi condivisi: devono passare `catenaLive` */
const CON_INTERRUTTORI = [
    'pages/Omega.tsx', 'pages/SafeStrategy.tsx', 'pages/ControlRoom.tsx',
    'components/mike/useMike.ts', 'components/safestrategy/useSafeBot.ts',
];

describe('punti d’ingresso al live', () => {
    for (const [file, rpc, verifica] of AVVII_DIRETTI) {
        it(`${file}: la verifica precede ${rpc.split('(')[0].replace('await ', '').replace('return ', '')}`, () => {
            const t = leggi(file);
            const iRpc = t.indexOf(rpc);
            const iVer = t.lastIndexOf(verifica, iRpc);
            expect(iRpc).toBeGreaterThan(0);
            expect(iVer).toBeGreaterThan(0);
            // nella stessa funzione: nessuna altra RPC di accensione fra le due
            expect(t.slice(iVer, iRpc)).not.toMatch(/activate(Omega|Mike|Safe)\(/);
            expect(iRpc - iVer).toBeLessThan(600);
        });
    }
    for (const file of CON_INTERRUTTORI) {
        it(`${file}: ogni creaInterruttori/creaComandiControlRoom riceve catenaLive`, () => {
            const t = leggi(file);
            const usi = [...t.matchAll(/crea(Interruttori|ComandiControlRoom)\(\{/g)];
            expect(usi.length).toBeGreaterThan(0);
            for (const u of usi) {
                const blocco = t.slice(u.index, (u.index ?? 0) + 900);
                expect(blocco).toContain('catenaLive:');
            }
        });
    }
    it('la strada di Safe tennis arriva dal SERVIZIO (stats) alla verifica della Control Room', () => {
        expect(leggi('components/controlroom/useControlRoom.ts'))
            .toContain("stradaTennis: bot === 'safe' ? leggiStradaOrdini(stats, 'tennis') : null");
        expect(leggi('pages/ControlRoom.tsx'))
            .toMatch(/stradaSafeTennis: \(\) => vm\.bots\.find\(\(x\) => x\.bot === 'safe'\)\?\.stradaTennis/);
    });
    it('nessun altro file chiama activateOmega/activateMike/activateSafe', () => {
        const noti = new Set(['pages/Omega.tsx', 'components/mike/useMike.ts',
            'components/safestrategy/useSafeBot.ts', 'lib/interruttori.ts',
            'lib/omega.ts', 'lib/mike.ts', 'lib/safeBot.ts']);
        const tutti = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as
            Record<string, string>;
        const fuori = Object.entries(tutti)
            .filter(([p]) => !/\.test\.tsx?$/.test(p) && !p.includes('/anteprima/'))
            .filter(([, t]) => /\bactivate(Omega|Mike|Safe)\(/.test(t))
            .map(([p]) => p.replace('/src/', ''))
            .filter((p) => !noti.has(p));
        expect(fuori).toEqual([]);
    });
});
