import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"

// https://vite.dev/config/
export default defineConfig({
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
})
