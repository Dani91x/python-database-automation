import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// ============================================================================
// FUSO ORARIO FISSO: I TEST GIRANO SEMPRE IN UTC (08/10/2026)
// ============================================================================
// Reperto: l'istantanea del DOM di `LadderView.botReplay.test.tsx` contiene
// «Aggiornato: hh:mm:ss» (toLocaleTimeString). Scritta nel cloud (UTC) diceva
// 16:13:20; sul PC (Europe/Rome) usciva 18:13:20 e il test era rosso con lo
// STESSO codice. Un verdetto che dipende dal fuso della macchina non e' una
// misura: si fissa qui, PRIMA che vitest avvii i worker (che ereditano l'ambiente),
// cosi' ogni istantanea e ogni calcolo di data vale identico su cloud e PC.
// Guardia: `src/test/fusoOrarioUTC.test.ts` diventa rossa se questa riga sparisce.
process.env.TZ = 'UTC';

// Config dei test. I test del motore (pure TS) girerebbero anche in node, ma jsdom
// è un superset compatibile: lo usiamo globalmente così i test COMPONENTE (.tsx) hanno
// DOM + React Testing Library senza rompere i test .ts esistenti (nessuna regressione).
// Rispecchia l'alias '@' di vite.config.ts / tsconfig paths.
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    test: {
        // userEvent su pagine intere sotto carico supera i 5 s di default: falsi rossi
        testTimeout: 20_000,
        environment: 'jsdom',
        include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
        setupFiles: ['./src/test/setup.ts'],
        globals: false,
    },
});
