// ============================================================================
// runnerFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /safe-strategy.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/lib/safeBot' con questo file: si ri-esporta TUTTO il
// modulo vero (percorso RELATIVO, che l'alias non tocca) e si ridefinisce solo
// `fetchRunnerState`, l'unica lettura di rete che la pagina fa da sola (il
// resto passa da `useSafeBot`, finto in safeBotFinto.ts). Lo stato e'
// costruito con la funzione VERA `runnerStateFrom`: runner flumine vivo, in
// PAPER (come la striscia del prototipo `s_calcio.js`), 38 partite in stream.
// Le scritture restano quelle vere: dal client Supabase finto non partono.
// ============================================================================
import { runnerStateFrom, type RunnerState } from '../lib/safeBot';
import { ORA_MS, fa } from './giornataBot';

export * from '../lib/safeBot';

export async function fetchRunnerState(): Promise<RunnerState> {
    return runnerStateFrom({ ts: fa(1), mode: 'PAPER' }, ORA_MS, 38);
}
