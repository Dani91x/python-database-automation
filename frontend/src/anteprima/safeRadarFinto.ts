// ============================================================================
// safeRadarFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /safe-strategy.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/components/safestrategy/SafeStrategyProvider' con
// questo file:
//   - il modulo VERO si ri-esporta tutto (percorso RELATIVO): `App.tsx` monta
//     quindi il `SafeStrategyProvider` vero, e `ParamsSheet` (che importa
//     './SafeStrategyProvider' in relativo) legge il contesto vero;
//   - `useSafeStrategy` e' ridefinito qui e restituisce lo stesso valore del
//     contesto (`ReturnType<typeof useSafeStrategy>` del modulo vero): le
//     partite monitorate sono costruite dal feed della giornata
//     (`giornataBot.ts`) con le funzioni VERE del motore
//     (`buildFootballCtxFromScan`, `evaluateFootballAll`,
//     `buildTennisCtxFromScan`, `evaluateTennis`), come fa il provider; i
//     segnali sono quelli del prototipo (`s_calcio.js`, SIGNALS), con le
//     chiavi di `ActiveSignal`.
// ============================================================================
import type { useSafeStrategy as hookVero, FootballMonitor, TennisMonitor } from '../components/safestrategy/SafeStrategyProvider';
import {
    DEFAULT_PARAMS, buildFootballCtxFromScan, buildTennisCtxFromScan, evaluateFootballAll, evaluateTennis,
    type ActiveSignal,
} from '../lib/safeStrategy';
import type { CalcioScanPayload, TennisScanPayload } from '../lib/safeStrategyScan';
import { EV, ORA_MS, RIGHE_SCAN, STATO_SCANNER } from './giornataBot';

export * from '../components/safestrategy/SafeStrategyProvider';

type Valore = ReturnType<typeof hookVero>;

/** secondi da cui il punteggio corrente e' osservato, per partita (anti-blip) */
const STABILE: Record<string, { daMinuto: number; secondi: number }> = {
    [EV.inter]: { daMinuto: 44, secondi: 1260 },
    [EV.betis]: { daMinuto: 0, secondi: 1860 },
    [EV.sassuolo]: { daMinuto: 40, secondi: 1720 },
};

function monitorCalcio(): FootballMonitor[] {
    return RIGHE_SCAN.filter((r) => r.sport === 'calcio').map((r) => {
        const p = r.payload as CalcioScanPayload;
        const s = STABILE[r.event_id] ?? null;
        const ctx = buildFootballCtxFromScan(r.event_id, p, s?.daMinuto ?? null, s?.secondi ?? null);
        return {
            eventId: r.event_id, payload: p, updatedAt: r.updated_at ?? null, ctx,
            evaluations: evaluateFootballAll(ctx, DEFAULT_PARAMS),
            preMatchMissing: ctx.inplay && ctx.preMatch === null,
        };
    });
}

function monitorTennis(): TennisMonitor[] {
    return RIGHE_SCAN.filter((r) => r.sport === 'tennis').map((r) => {
        const p = r.payload as TennisScanPayload;
        const ctx = buildTennisCtxFromScan(r.event_id, p, 95);
        return { eventId: r.event_id, payload: p, updatedAt: r.updated_at ?? null, ctx, evaluation: evaluateTennis(ctx, DEFAULT_PARAMS.tennis) };
    });
}

/** segnali del radar: due attivi sul calcio, uno scaduto (storico della sessione) */
const SEGNALI: ActiveSignal[] = [
    {
        key: `${EV.sassuolo}:base:1-0`, sport: 'calcio', variant: 'base', eventId: EV.sassuolo,
        matchLabel: 'Sassuolo \u2013 Lecce', headline: 'BANCA Lecce', side: 'LAY', selection: 'Lecce',
        entryOdds: 22, entrySize: 84, contextAtTrigger: "62' \u00b7 1-0",
        triggeredAtMs: ORA_MS - 12_000, status: 'active', expiredAtMs: null,
    },
    {
        key: `${EV.inter}:esatto:home:1-0`, sport: 'calcio', variant: 'esatto', subId: 'home', eventId: EV.inter,
        matchLabel: 'Inter \u2013 Torino', headline: 'BANCA Altro risultato CASA (Inter)', side: 'LAY',
        selection: 'Any Other Home Win', entryOdds: 46, entrySize: 18, contextAtTrigger: "57' \u00b7 1-0",
        triggeredAtMs: ORA_MS - 41_000, status: 'active', expiredAtMs: null,
    },
    {
        key: `${EV.feyenoord}:punta:2-0`, sport: 'calcio', variant: 'punta', eventId: EV.feyenoord,
        matchLabel: 'Feyenoord \u2013 AZ Alkmaar', headline: 'PUNTA Feyenoord', side: 'BACK', selection: 'Feyenoord',
        entryOdds: 1.12, entrySize: 1420, contextAtTrigger: "70' \u00b7 2-0",
        triggeredAtMs: ORA_MS - 3 * 3600_000, status: 'expired', expiredAtMs: ORA_MS - 3 * 3600_000 + 180_000,
    },
];

let VALORE: Valore | null = null;

function valore(): Valore {
    return {
        params: DEFAULT_PARAMS,
        saveParams: () => { /* anteprima: nessun salvataggio */ },
        resetParams: () => { /* anteprima */ },
        football: monitorCalcio(),
        tennis: monitorTennis(),
        signals: SEGNALI,
        scanStatus: { ...STATO_SCANNER, payload: { ...STATO_SCANNER.payload } },
    };
}

export function useSafeStrategy(): Valore {
    VALORE ??= valore();
    return VALORE;
}
