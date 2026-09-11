// ============================================================================
// setup.cert.ts — setup della CERTIFICAZIONE.
// Stesso contenuto del setup normale (matcher jest-dom + cleanup) più:
//   * cattura di console.error / console.warn: una pagina money-critical che
//     stampa un errore in console durante il render è un KO, non un dettaglio;
//   * niente mock dei dati: i test parlano col DB vero (solo letture).
// ============================================================================
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

export interface ConsoleCapture {
    errors: string[];
    warns: string[];
}

/** messaggi raccolti nel test corrente (azzerati da beforeEach) */
export const consoleCapture: ConsoleCapture = { errors: [], warns: [] };

/** rumore noto dell'ambiente di test, non della pagina */
const IGNORE = [
    'Not implemented: HTMLCanvasElement',
    'Not implemented: navigation',
    'ReactDOMTestUtils.act',
    'react-helmet-async',
    'Warning: The current testing environment is not configured to support act',
];

function record(bucket: string[], args: unknown[]) {
    const line = args
        .map((a) => {
            if (a instanceof Error) return `${a.name}: ${a.message}`;
            if (typeof a === 'string') return a;
            try { return JSON.stringify(a); } catch { return String(a); }
        })
        .join(' ');
    if (IGNORE.some((s) => line.includes(s))) return;
    bucket.push(line);
}

beforeEach(() => {
    consoleCapture.errors = [];
    consoleCapture.warns = [];
    vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => { record(consoleCapture.errors, args); });
    vi.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => { record(consoleCapture.warns, args); });
});

afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
});
