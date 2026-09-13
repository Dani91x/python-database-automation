import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        include: ['scripts/scalper_avgdown/**/*.test.ts'],
        environment: 'node',
    },
});
