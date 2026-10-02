// Finti delle pagine dei bot calcio (/mike, /safe-strategy, /omega) in
// frontend/src/anteprima: alias Vite esatti. La giornata comune e' in
// frontend/src/anteprima/giornataBot.ts (non e' un alias).
export default [
    [/^@\/components\/mike\/useMike$/, 'mikeFinto.ts'],
    [/^@\/components\/safestrategy\/useSafeBot$/, 'safeBotFinto.ts'],
    [/^@\/components\/safestrategy\/SafeStrategyProvider$/, 'safeRadarFinto.ts'],
    [/^@\/lib\/safeBot$/, 'runnerFinto.ts'],
    [/^@\/lib\/safeStrategyScan$/, 'scanFinto.ts'],
    [/^@\/lib\/omega$/, 'omegaFinto.ts'],
    [/^@\/lib\/omegaMissions$/, 'omegaMissioniFinto.ts'],
    [/^@\/lib\/dailyHistory$/, 'storicoFinto.ts'],
];
