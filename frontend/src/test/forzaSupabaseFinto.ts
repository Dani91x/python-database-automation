// ============================================================================
// forzaSupabaseFinto — GUARDIA DB VERO SOTTO VITEST (reperto 23/09/2026).
//
// Il 23/09 `npx vitest run` lanciato SENZA esportare in shell
// VITE_SUPABASE_URL=http://127.0.0.1:9 e VITE_SUPABASE_ANON_KEY=finto ha letto
// il DB VERO con la chiave anon (3 raffiche sui log API di Supabase:
// safe_strategy_status, betfair_live_heartbeat, get_safe_activity,
// omega_eventi_chiusi_dall_utente). Causa: `@/integrations/supabase/client.ts`
// legge `import.meta.env.VITE_SUPABASE_URL/_ANON_KEY` dal `.env` di
// `frontend/`, ed è un singleton creato al primo import — la sandbox non deve
// dipendere dalla disciplina di chi lancia i test.
//
// Richiamata da `src/test/setup.ts` (setupFiles di vitest.config.ts), PRIMA
// che il file di test — e quindi qualunque modulo che importa il client
// Supabase (`@/lib/tennis`, `@/lib/liveOrders`, `@/lib/safeBot`, ...) — venga
// caricato. `vi.stubEnv` sovrascrive sia `process.env` sia `import.meta.env`:
// vince SEMPRE su ciò che il `.env` di `frontend/` ha già iniettato in
// `import.meta.env` all'avvio di Vite, qualunque cosa dica.
//
// Via di fuga ESPLICITA (mai di default, va accesa a mano in shell):
// VITEST_DB_VERO=1.
// ============================================================================
import { vi } from 'vitest';

export const SUPABASE_URL_FINTO = 'http://127.0.0.1:9';
export const SUPABASE_ANON_KEY_FINTO = 'finto';

export function forzaSupabaseFinto(): void {
    if (process.env.VITEST_DB_VERO === '1') return;
    vi.stubEnv('VITE_SUPABASE_URL', SUPABASE_URL_FINTO);
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', SUPABASE_ANON_KEY_FINTO);
}
