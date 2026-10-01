// Finti del tennis (/tennis, /tennis/terminal) in frontend/src/anteprima: alias Vite esatti.
// '@/lib/tennis' non e' aliasato da nessun altro alias_*.mjs. Vale per tutto il
// server: anche Market Watch e la Control Room (useTennisVivo) leggono da qui le
// partite seguite e tennis_live_now (le letture dei servizi bot restano vere).
export default [
    [/^@\/lib\/tennis$/, 'tennisFinto.ts'],
];
