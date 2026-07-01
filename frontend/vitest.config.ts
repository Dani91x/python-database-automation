import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

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
        environment: 'jsdom',
        include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
        setupFiles: ['./src/test/setup.ts'],
        globals: false,
    },
});
