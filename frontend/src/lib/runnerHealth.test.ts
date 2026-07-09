// Test di runnerHealth (A5) — mai un finto verde.
import { describe, expect, it } from 'vitest';
import { heartbeatAgeSec, heartbeatState } from './runnerHealth';

const NOW = Date.parse('2026-07-09T12:00:00Z');

describe('heartbeatAgeSec', () => {
    it('età corretta', () => {
        expect(heartbeatAgeSec('2026-07-09T11:59:50Z', NOW)).toBeCloseTo(10);
    });
    it('timestamp futuro entro tolleranza (clock skew lieve) → 0, mai negativo', () => {
        expect(heartbeatAgeSec('2026-07-09T12:00:05Z', NOW)).toBe(0);
    });
    it('timestamp troppo nel futuro (clock sballato) → null: mai un finto verde', () => {
        expect(heartbeatAgeSec('2026-07-09T12:05:00Z', NOW)).toBeNull();
        expect(heartbeatState('2026-07-09T12:05:00Z', NOW)).toBe('unknown');
    });
    it('assente/illeggibile → null', () => {
        expect(heartbeatAgeSec(null, NOW)).toBeNull();
        expect(heartbeatAgeSec(undefined, NOW)).toBeNull();
        expect(heartbeatAgeSec('boh', NOW)).toBeNull();
    });
});

describe('heartbeatState', () => {
    it('fresco → ok (soglia inclusa)', () => {
        expect(heartbeatState('2026-07-09T11:59:50Z', NOW)).toBe('ok');
        expect(heartbeatState('2026-07-09T11:59:30Z', NOW, 30)).toBe('ok'); // esattamente 30s
    });
    it('oltre soglia → stale', () => {
        expect(heartbeatState('2026-07-09T11:59:29Z', NOW, 30)).toBe('stale');
        expect(heartbeatState('2026-07-09T11:00:00Z', NOW)).toBe('stale');
    });
    it('mai visto/illeggibile → unknown (mai un finto verde)', () => {
        expect(heartbeatState(null, NOW)).toBe('unknown');
        expect(heartbeatState('garbage', NOW)).toBe('unknown');
    });
});
