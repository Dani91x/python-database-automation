// ============================================================================
// scalperFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di Segui live (/segui-live).
//
// Non e' importato dall'app: il server di anteprima sostituisce con un alias
// Vite ESATTO (alias_seguilive.mjs) l'import '@/lib/scalper' con questo file.
// Si ri-esporta TUTTO il modulo vero (percorso RELATIVO) e si ridefinisce solo
// la lettura `fetchScalperState` (get_scalper_state), con le STESSE chiavi e
// tipi del vero (ScalperState): l'habitat scan delle partite adatte (card in
// cima alla lista) e l'ultima sessione dello scalper su Inter-Torino.
// I comandi (activateScalper/stopScalper) restano quelli veri: dal client
// Supabase finto non parte niente.
// ============================================================================
import type { ScalperState } from '../lib/scalper';
import { scalperDi } from './seguiLiveDati';

export * from '../lib/scalper';

export async function fetchScalperState(eventId: string, _activityLimit = 40): Promise<ScalperState> {
    return scalperDi(eventId);
}
