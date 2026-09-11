import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// ============================================================================
// CONFIG DELLA CERTIFICAZIONE (NON tocca vitest.config.ts).
//
// Gira SOLO i test in src/certification/**/*.cert.test.tsx|ts: quelli montano
// le pagine /omega, /safe-strategy, /mike sui DATI REALI del DB Supabase
// (client con service role, letture SOLO). Stesso environment (jsdom), stesso
// alias '@' e stesso setup di jest-dom della config esistente, più la cattura
// di console.error/warn (un crash silenzioso è un KO).
//
//   npx vitest run --config vitest.cert.config.ts
// ============================================================================
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    test: {
        environment: 'jsdom',
        // marcatore: i file .cert.test.* si AUTO-SALTANO se non gira questa
        // config (il pattern 'src/**/*.test.ts' di vitest.config.ts li
        // pescherebbe, e `npm test` finirebbe a interrogare il DB reale).
        env: { CERT_RUN: '1' },
        include: ['src/certification/**/*.cert.test.ts', 'src/certification/**/*.cert.test.tsx'],
        setupFiles: ['./src/certification/setup.cert.ts'],
        globals: false,
        // rete reale: le pagine fanno più RPC su migliaia di righe
        testTimeout: 120_000,
        hookTimeout: 120_000,
        // un solo file per volta: i tre bot leggono le stesse tabelle e il
        // report deve restare leggibile in ordine
        fileParallelism: false,
        reporters: ['default'],
    },
});
