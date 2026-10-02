// Finti delle pagine di analisi e trading (/report-personale, /watchlist,
// /analytics, /dashboard «Match Betfair», /multi-ladder) in frontend/src/anteprima:
// alias Vite esatti. '@/lib/live' e '@/lib/liveOrders' sono gia' in
// alias_seguilive.mjs / alias_controlroom.mjs e NON vanno ripetuti qui: i dati
// per Live P&L, Trade journal e Match replay sono in
// frontend/src/anteprima/analisiDati.ts, da ri-esportare da quei finti.
export default [
    [/^@\/lib\/personalReport$/, 'personalReportFinto.ts'],
    [/^@\/lib\/watchlist$/, 'watchlistFinto.ts'],
    [/^@\/lib\/betfair$/, 'betfairFinto.ts'],
    [/^@\/lib\/analytics$/, 'analyticsFinto.ts'],
    [/^@\/lib\/multiLadder$/, 'multiLadderFinto.ts'],
];
