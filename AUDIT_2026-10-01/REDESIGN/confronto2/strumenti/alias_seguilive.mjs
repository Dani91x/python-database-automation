// Finti di Segui live (frontend/src/anteprima): alias Vite esatti.
// '@/lib/liveOrders' e' gia' in alias_controlroom.mjs (liveOrdersFinto.ts, esteso
// con ordini/posizioni/x-hedge/registro di Segui live): non va ripetuto qui.
export default [
    [/^@\/lib\/live$/, 'liveFeedFinto.ts'],
    [/^@\/lib\/scalper$/, 'scalperFinto.ts'],
];
