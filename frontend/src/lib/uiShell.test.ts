// Test dell'INTERRUTTORE del redesign (lib/uiShell.ts): spento di default, la
// chiave locale vince sulla variabile di build, un valore estraneo o un
// localStorage che lancia valgono come assenti (mai guscio acceso per errore).
import { describe, it, expect, vi, afterEach } from 'vitest';
import { CHIAVE_UI_SHELL, cambiaUiShell, leggiUiShell, rottaDopoAccesso, scriviUiShell } from './uiShell';

afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    localStorage.clear();
});

describe('interruttore ui.shell', () => {
    it("senza chiave e senza variabile di build e' spento ('off')", () => {
        vi.stubEnv('VITE_UI_SHELL', '');
        expect(leggiUiShell()).toBe('off');
    });

    it("la chiave locale 'v2' accende il guscio", () => {
        localStorage.setItem(CHIAVE_UI_SHELL, 'v2');
        expect(leggiUiShell()).toBe('v2');
    });

    it('un valore estraneo nella chiave vale come assente', () => {
        vi.stubEnv('VITE_UI_SHELL', '');
        localStorage.setItem(CHIAVE_UI_SHELL, 'V2');
        expect(leggiUiShell()).toBe('off');
        localStorage.setItem(CHIAVE_UI_SHELL, 'true');
        expect(leggiUiShell()).toBe('off');
    });

    it('la variabile di build vale se la chiave manca', () => {
        vi.stubEnv('VITE_UI_SHELL', 'v2');
        expect(leggiUiShell()).toBe('v2');
    });

    it('la chiave locale vince sulla variabile di build, in tutte e due le direzioni', () => {
        vi.stubEnv('VITE_UI_SHELL', 'v2');
        localStorage.setItem(CHIAVE_UI_SHELL, 'off');
        expect(leggiUiShell()).toBe('off');
        vi.stubEnv('VITE_UI_SHELL', 'off');
        localStorage.setItem(CHIAVE_UI_SHELL, 'v2');
        expect(leggiUiShell()).toBe('v2');
    });

    it('un localStorage che lancia non rompe nulla: si ripiega sulla build, poi su off', () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloccato'); });
        vi.stubEnv('VITE_UI_SHELL', '');
        expect(leggiUiShell()).toBe('off');
        vi.stubEnv('VITE_UI_SHELL', 'v2');
        expect(leggiUiShell()).toBe('v2');
    });

    it('scrivere con archiviazione bloccata ritorna false senza lanciare', () => {
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloccato'); });
        expect(scriviUiShell('v2')).toBe(false);
    });

    it('il clic scrive la scelta e ricarica (un clic, in tutte e due le direzioni)', () => {
        const ricarica = vi.fn();
        cambiaUiShell('v2', ricarica);
        expect(localStorage.getItem(CHIAVE_UI_SHELL)).toBe('v2');
        expect(ricarica).toHaveBeenCalledTimes(1);
        cambiaUiShell('off', ricarica);
        expect(localStorage.getItem(CHIAVE_UI_SHELL)).toBe('off');
        expect(ricarica).toHaveBeenCalledTimes(2);
    });

    it("dopo l'accesso: /select-sport col guscio spento (come oggi), /board col guscio acceso", () => {
        vi.stubEnv('VITE_UI_SHELL', '');
        expect(rottaDopoAccesso()).toBe('/select-sport');
        localStorage.setItem(CHIAVE_UI_SHELL, 'v2');
        expect(rottaDopoAccesso()).toBe('/board');
    });
});
