// Anteprima Vite dell'app con il client Supabase FINTO (nessun accesso al database)
// e, con ANTEPRIMA=popolata (default), i moduli finti di frontend/src/anteprima al
// posto dei moduli veri che leggono la rete: la Control Room si vede POPOLATA.
// Uso, dalla radice del repo:
//   node AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs            (popolata)
//   ANTEPRIMA=vuota node AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs
// Porta 5198 (la 5199 resta all'anteprima vuota di confronto/strumenti).
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const QUI = path.dirname(fileURLToPath(import.meta.url));
const FE = path.resolve(QUI, '../../../../frontend');
const ANTE = path.join(FE, 'src', 'anteprima');
const MODO = (process.env.ANTEPRIMA || 'popolata').toLowerCase();
const PORTA = Number(process.env.PORTA || 5198);
// PostCSS e Tailwind risolvono la loro configurazione dalla cartella corrente
process.chdir(FE);
const { createServer } = await import(path.join(FE, 'node_modules/vite/dist/node/index.js'));
const { default: react } = await import(path.join(FE, 'node_modules/@vitejs/plugin-react/dist/index.js'));

// Alias ESATTI (regex ancorate): intercettano SOLO lo specificatore '@/...' usato
// dall'app; i finti importano il modulo vero con percorso RELATIVO, che qui non
// passa, quindi `export * from '../...'` dentro il finto arriva al vero.
// Ogni pagina registra i suoi finti in un file `alias_<pagina>.mjs` di questa
// cartella: `export default [[/^@\/percorso$/, 'fileDentroSrcAnteprima.ts'], ...]`.
const { readdirSync } = await import('node:fs');
const FINTI = [];
if (MODO === 'popolata') {
    for (const f of readdirSync(QUI).filter((n) => /^alias_.*\.mjs$/.test(n)).sort()) {
        for (const [find, file] of (await import(path.join(QUI, f))).default) {
            FINTI.push({ find, replacement: path.join(ANTE, file) });
        }
    }
}

const server = await createServer({
    root: FE,
    configFile: false,
    plugins: [react()],
    resolve: {
        alias: [
            { find: /^@\/integrations\/supabase\/client$/, replacement: path.join(QUI, 'clientFinto.ts') },
            ...FINTI,
            { find: '@', replacement: path.join(FE, 'src') },
        ],
    },
    server: { port: PORTA, strictPort: true, host: '127.0.0.1', fs: { allow: [FE, QUI] } },
});
await server.listen();
console.log(`anteprima (${MODO}) su http://127.0.0.1:${PORTA}`);
for (const f of FINTI) console.log('  alias', String(f.find), '->', path.relative(FE, f.replacement));
