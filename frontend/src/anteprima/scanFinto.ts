// ============================================================================
// scanFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA delle pagine dei bot calcio.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/lib/safeStrategyScan' con questo file: si
// ri-esporta tutto il modulo VERO (percorso RELATIVO, che l'alias non tocca) e
// si ridefiniscono solo le due LETTURE di rete del feed dello scanner, con le
// stesse chiavi e gli stessi tipi del vero (`ScanRow`, `ScanStatusRow`):
//   - `fetchScanStatus`: battito dello scanner vivo (1 s), in stream;
//   - `fetchScanRows`: le righe del feed della giornata (`giornataBot.ts`).
// Le letture le usano, con il codice VERO, l'intestazione di Mike/Safe/Omega
// (salute del servizio), il provider del radar e `useScanLiveFeedRows`
// (minuto, punteggio e quote live della tabella di Omega e delle missioni).
// Le sottoscrizioni realtime restano quelle vere: dal client finto non
// arriva mai niente.
// ============================================================================
import type { ScanRow, ScanStatusRow } from '../lib/safeStrategyScan';
import { RIGHE_SCAN, STATO_SCANNER } from './giornataBot';

export * from '../lib/safeStrategyScan';

export async function fetchScanRows(): Promise<ScanRow[]> {
    return RIGHE_SCAN.map((r) => ({ ...r }));
}

export async function fetchScanStatus(): Promise<ScanStatusRow | null> {
    return { ...STATO_SCANNER, payload: { ...STATO_SCANNER.payload } };
}
