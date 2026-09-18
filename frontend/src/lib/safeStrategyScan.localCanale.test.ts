// ============================================================================
// safeStrategyScan.localCanale.test.ts — STADIO B (18/09, raccordo): il
// canale locale scanner (47336) entra nello stesso lotto di `safe_strategy_scan`
// SOLO se «vince il più recente». Falsificazione (verificata a mano):
//   · togliere `nuovo < vecchio` (sempre accetta) → il test "più vecchio
//     scartato" torna rosso;
//   · togliere `!msg.payload` → il test "senza payload" torna rosso.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { scanLocaleAccettabile, type ScanRow, type ScanRowLocaleMsg } from './safeStrategyScan';

const PAYLOAD_CALCIO = {
    p1: 'Juventus', p2: 'Milan', mo_market_id: 'm1', mo_status: 'OPEN',
    odds: null, competition: null, open_date: null, inplay: true,
} as unknown as ScanRow['payload'];

function riga(over: Partial<ScanRow> = {}): ScanRow {
    return {
        event_id: 'e1', sport: 'calcio', payload: PAYLOAD_CALCIO,
        updated_at: '2026-09-18T10:00:00.000Z',
        ...over,
    };
}

describe('scanLocaleAccettabile: canale muto o messaggio assente', () => {
    it('nessun messaggio: nulla da applicare (stato identico a prima)', () => {
        expect(scanLocaleAccettabile([riga()], null)).toBeNull();
        expect(scanLocaleAccettabile([riga()], undefined)).toBeNull();
    });

    it('messaggio senza payload: scartato (non è una notizia, è un guasto)', () => {
        const msg = { event_id: 'e1', sport: 'calcio', payload: null, updated_at: '2026-09-18T10:10:00.000Z' } as unknown as ScanRowLocaleMsg;
        expect(scanLocaleAccettabile([riga()], msg)).toBeNull();
    });

    it('messaggio senza event_id: scartato', () => {
        const msg = { sport: 'calcio', payload: PAYLOAD_CALCIO, updated_at: '2026-09-18T10:10:00.000Z' } as unknown as ScanRowLocaleMsg;
        expect(scanLocaleAccettabile([riga()], msg)).toBeNull();
    });
});

describe('scanLocaleAccettabile: "vince il più recente"', () => {
    it('messaggio PIÙ RECENTE della riga già in memoria → sostituisce la riga', () => {
        const attuale = [riga({ updated_at: '2026-09-18T10:00:00.000Z' })];
        const msg: ScanRowLocaleMsg = riga({ updated_at: '2026-09-18T10:05:00.000Z' });
        expect(scanLocaleAccettabile(attuale, msg)).toEqual(msg);
    });

    it('messaggio PIÙ VECCHIO della riga già in memoria → scartato', () => {
        const attuale = [riga({ updated_at: '2026-09-18T10:10:00.000Z' })];
        const msg: ScanRowLocaleMsg = riga({ updated_at: '2026-09-18T10:00:00.000Z' });
        expect(scanLocaleAccettabile(attuale, msg)).toBeNull();
    });

    it('_pubblicato_ms vince su updated_at quando presente', () => {
        const attuale = [riga({ updated_at: '2026-09-18T10:10:00.000Z' })];
        // updated_at sembra più vecchio, ma _pubblicato_ms dice che è più recente
        const msg: ScanRowLocaleMsg = {
            ...riga({ updated_at: '2026-09-18T09:00:00.000Z' }),
            _pubblicato_ms: Date.parse('2026-09-18T10:20:00.000Z'),
        };
        expect(scanLocaleAccettabile(attuale, msg)).toEqual(msg);
    });

    it('evento nuovo (non ancora in memoria): sempre accettato', () => {
        const attuale = [riga({ event_id: 'altro' })];
        const msg: ScanRowLocaleMsg = riga({ event_id: 'e1' });
        expect(scanLocaleAccettabile(attuale, msg)).toEqual(msg);
    });
});
