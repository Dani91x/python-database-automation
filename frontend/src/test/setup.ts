// Setup globale dei test COMPONENTE (jsdom). Registra i matcher di jest-dom
// (toBeInTheDocument, toBeDisabled, ...) sull'`expect` di vitest e smonta l'albero
// React dopo ogni test (globals:false → cleanup non è automatico).
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
    cleanup();
});
