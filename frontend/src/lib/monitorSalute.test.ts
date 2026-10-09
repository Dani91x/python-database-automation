// ============================================================================
// monitorSalute.test.ts - 09/10 (R-5): la voce «Salute» si accende solo con la
// build fatta a MONITOR_SALUTE=1; ogni altro valore, o nessuno, = spento.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { monitorSaluteAcceso } from './monitorSalute';

afterEach(() => { vi.unstubAllEnvs(); });

describe('monitorSaluteAcceso', () => {
    it('spento di serie (variabile assente)', () => {
        vi.stubEnv('VITE_MONITOR_SALUTE', undefined as unknown as string);
        expect(monitorSaluteAcceso()).toBe(false);
    });

    it("acceso solo con '1'", () => {
        vi.stubEnv('VITE_MONITOR_SALUTE', '1');
        expect(monitorSaluteAcceso()).toBe(true);
        for (const v of ['0', '', 'true', 'si', ' 1']) {
            vi.stubEnv('VITE_MONITOR_SALUTE', v);
            expect(monitorSaluteAcceso()).toBe(false);
        }
    });

    it('vite.config.ts passa MONITOR_SALUTE del .env della radice, solo 1 = acceso', () => {
        const cfg = readFileSync(join(__dirname, '..', '..', 'vite.config.ts'), 'utf-8');
        expect(cfg).toContain("loadEnv(mode, path.resolve(__dirname, '..'), 'MONITOR_SALUTE')");
        expect(cfg).toContain("'import.meta.env.VITE_MONITOR_SALUTE': JSON.stringify(radice.MONITOR_SALUTE === '1' ? '1' : '0')");
    });
});
