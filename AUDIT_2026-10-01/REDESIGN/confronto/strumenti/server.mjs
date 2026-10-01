// Anteprima Vite dell'app con il client Supabase FINTO (nessun accesso al database).
// Uso, dalla radice del repo:  node AUDIT_2026-10-01/REDESIGN/confronto/strumenti/server.mjs
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const QUI = path.dirname(fileURLToPath(import.meta.url));
const FE = path.resolve(QUI, '../../../../frontend');
// PostCSS e Tailwind risolvono la loro configurazione dalla cartella corrente
process.chdir(FE);
const { createServer } = await import(path.join(FE, 'node_modules/vite/dist/node/index.js'));
const { default: react } = await import(path.join(FE, 'node_modules/@vitejs/plugin-react/dist/index.js'));
const server = await createServer({
    root: FE,
    configFile: false,
    plugins: [react()],
    resolve: {
        alias: [
            { find: /^@\/integrations\/supabase\/client$/, replacement: path.join(QUI, 'clientFinto.ts') },
            { find: '@', replacement: path.join(FE, 'src') },
        ],
    },
    server: { port: 5199, strictPort: true, host: '127.0.0.1', fs: { allow: [FE, QUI] } },
});
await server.listen();
console.log('anteprima su http://127.0.0.1:5199');
