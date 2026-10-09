import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
// 09/10 (R-5): la voce di menu «Salute» segue la riga MONITOR_SALUTE del .env della
// radice (la stessa dei servizi Python): letta alla build, nessuna chiamata a runtime
const radice = loadEnv(mode, path.resolve(__dirname, '..'), 'MONITOR_SALUTE')
return {
    define: {
        'import.meta.env.VITE_MONITOR_SALUTE': JSON.stringify(radice.MONITOR_SALUTE === '1' ? '1' : '0'),
    },
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    build: {
        cssCodeSplit: false,
        chunkSizeWarningLimit: 1600,
        rollupOptions: {
            output: {
                manualChunks: undefined,
                chunkFileNames: 'assets/js/[name]-[hash].js',
                entryFileNames: 'assets/js/[name]-[hash].js',
            },
            onwarn(warning, warn) {
                return
            }
        }
    },
    // Fix for Windows build issues
    server: {
        fs: {
            strict: false,
        },
    },
    // Force single thread for stability
    worker: {
        format: 'es',
    },
}
})
