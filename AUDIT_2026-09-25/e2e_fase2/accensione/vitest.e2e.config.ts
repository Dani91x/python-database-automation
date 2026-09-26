import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// E2E FASE 1 (25/09): componenti e funzioni VERI della UI contro il DB vero.
// Un file solo, un test per percorso, in sequenza (mai in parallelo).
//   npx vitest run --config e2e_fase1/vitest.e2e.config.ts -t "P01"
export default defineConfig({
    plugins: [react()],
    root: path.resolve(__dirname, '..'),
    resolve: { alias: { '@': path.resolve(__dirname, '../src') } },
    test: {
        environment: 'jsdom',
        include: ['e2e_fase2/**/*.e2e.test.tsx'],
        setupFiles: ['./src/test/setup.ts'],
        globals: false,
        testTimeout: 240_000,
        hookTimeout: 60_000,
        fileParallelism: false,
        // i comandi della plancia sono `void esegui(...)`: un rifiuto voluto
        // (es. SafeFermoPerStrumento) diventa un rifiuto non gestito. Il test
        // li raccoglie da se' (process.on) e li mette nel referto.
        dangerouslyIgnoreUnhandledErrors: true,
        sequence: { concurrent: false },
        reporters: ['verbose'],
    },
});
