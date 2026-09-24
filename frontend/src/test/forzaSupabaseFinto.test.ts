// ============================================================================
// forzaSupabaseFinto.test.ts — dimostra che sotto vitest il client Supabase
// punta SEMPRE a 127.0.0.1:9, ANCHE SE il '.env' dice altro (reperto 23/09).
//
// Il finto ".env dice altro" si simula con `vi.stubEnv` (chiavi identiche al
// vero: VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY) PRIMA di richiamare la
// guardia; se la guardia vince, il valore simulato sparisce.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { forzaSupabaseFinto, SUPABASE_URL_FINTO, SUPABASE_ANON_KEY_FINTO } from './forzaSupabaseFinto';

const URL_VERO_SIMULATO = 'https://progetto-vero.supabase.co';
const KEY_VERA_SIMULATA = 'eyJ-chiave-anon-vera-simulata';

afterEach(() => {
    vi.unstubAllEnvs();
    delete process.env.VITEST_DB_VERO;
    vi.resetModules();
});

describe('forzaSupabaseFinto — guardia DB vero sotto vitest', () => {
    it('il ".env" simulato con vi.stubEnv passa PRIMA della guardia (sanity: senza guardia vincerebbe il vero)', () => {
        vi.stubEnv('VITE_SUPABASE_URL', URL_VERO_SIMULATO);
        vi.stubEnv('VITE_SUPABASE_ANON_KEY', KEY_VERA_SIMULATA);
        expect(import.meta.env.VITE_SUPABASE_URL).toBe(URL_VERO_SIMULATO);
        expect(import.meta.env.VITE_SUPABASE_ANON_KEY).toBe(KEY_VERA_SIMULATA);
    });

    it('la guardia VINCE sul ".env" simulato: forza 127.0.0.1:9 / "finto" anche se il .env dice altro', () => {
        // simula il .env di frontend/ con un progetto REALE
        vi.stubEnv('VITE_SUPABASE_URL', URL_VERO_SIMULATO);
        vi.stubEnv('VITE_SUPABASE_ANON_KEY', KEY_VERA_SIMULATA);
        // la guardia (la STESSA funzione chiamata da src/test/setup.ts) interviene DOPO
        forzaSupabaseFinto();
        expect(import.meta.env.VITE_SUPABASE_URL).toBe(SUPABASE_URL_FINTO);
        expect(import.meta.env.VITE_SUPABASE_ANON_KEY).toBe(SUPABASE_ANON_KEY_FINTO);
        expect(import.meta.env.VITE_SUPABASE_URL).not.toBe(URL_VERO_SIMULATO);
    });

    it('il client Supabase creato DOPO la guardia usa l\'URL finto, non quello del ".env" simulato', async () => {
        vi.stubEnv('VITE_SUPABASE_URL', URL_VERO_SIMULATO);
        vi.stubEnv('VITE_SUPABASE_ANON_KEY', KEY_VERA_SIMULATA);
        forzaSupabaseFinto();
        vi.resetModules(); // il client e' un singleton: ricrealo per leggere l'env corrente
        const { supabase } = await import('@/integrations/supabase/client');
        // supabaseUrl e' 'protected' in TS ma un vero campo JS a runtime: e'
        // l'unico modo, senza fare una request di rete, di leggere a quale
        // endpoint il client si e' davvero agganciato.
        const urlUsato = (supabase as unknown as { supabaseUrl: string }).supabaseUrl;
        expect(urlUsato.replace(/\/$/, '')).toBe(SUPABASE_URL_FINTO);
        expect(urlUsato).not.toContain('progetto-vero');
    });

    it('via di fuga VITEST_DB_VERO=1: la guardia NON interviene (accesa a mano, mai di default)', () => {
        vi.stubEnv('VITE_SUPABASE_URL', URL_VERO_SIMULATO);
        vi.stubEnv('VITE_SUPABASE_ANON_KEY', KEY_VERA_SIMULATA);
        process.env.VITEST_DB_VERO = '1';
        forzaSupabaseFinto();
        expect(import.meta.env.VITE_SUPABASE_URL).toBe(URL_VERO_SIMULATO);
        expect(import.meta.env.VITE_SUPABASE_ANON_KEY).toBe(KEY_VERA_SIMULATA);
    });

    it('DI DEFAULT (senza VITEST_DB_VERO) la guardia e\' attiva: process.env.VITEST_DB_VERO e\' assente in questo run', () => {
        // certifica l'assunzione delle 4 prove sopra: nessuno ha esportato la
        // via di fuga nella shell che lancia questa suite.
        expect(process.env.VITEST_DB_VERO).toBeUndefined();
    });
});
