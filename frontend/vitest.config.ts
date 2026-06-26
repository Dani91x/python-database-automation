import { defineConfig } from 'vitest/config';
import path from 'path';

// Config dedicata ai test del motore (pure TS, ambiente node — niente jsdom).
// Rispecchia l'alias '@' di vite.config.ts / tsconfig paths.
export default defineConfig({
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    test: {
        environment: 'node',
        include: ['src/**/*.test.ts'],
        globals: false,
    },
});
