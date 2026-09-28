// ============================================================================
// useControlRoom.effettiviStantii.test.ts — CANTIERE G, voce 1 (28/09).
//
// R-E2E-1 / R-F2-17: «pulsante avvia assente al primo clic». Subito dopo
// un'accensione di Safe (es. «solo tennis» dalla scheda tennis), la scheda
// calcio non offriva «avvia» su Safe base: la plancia leggeva `variants` dagli
// EFFETTIVI (`control.stats.params_effective`), che il servizio pubblica solo
// al SUO giro — quindi erano ancora quelli della sessione PRECEDENTE.
//
// Il finto: `SafeControl.started_at`/`heartbeat_at` con le IDENTICHE chiavi
// del vero (`frontend/src/lib/safeBot.ts::SafeControl`); il vero contratto
// delle due colonne e' nella migrazione (`safe_activate` scrive SOLO
// `started_at`, il loop del servizio scrive SOLO `heartbeat_at` insieme a
// `stats`, vedi `Betfair/safe_strategy/bot_service.py:9363` e
// `migrations/safe_strategy_bot.sql:190`).
//
// FALSIFICAZIONE (mutazione provata a mano): tolto il ramo `effettiviStantiiFlag`
// da `leggiVarianti`/`leggiModiStrategia` (sempre `[effettivi, params]`), i test
// «al primo clic» sotto diventano rossi (tornano le varianti stantie).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    effettiviStantii, leggiVarianti, leggiModiStrategia,
} from '@/components/controlroom/useControlRoom';

describe('effettiviStantii — il servizio non ha ancora pubblicato un battito dopo questa accensione', () => {
    it('mai acceso (started_at nullo) -> non stantii: niente da confrontare', () => {
        expect(effettiviStantii(null)).toBe(false);
        expect(effettiviStantii({ started_at: null, heartbeat_at: null })).toBe(false);
    });

    it('acceso ma nessun battito mai arrivato -> stantii', () => {
        expect(effettiviStantii({ started_at: '2026-09-28T10:00:00Z', heartbeat_at: null })).toBe(true);
    });

    it('battito PRIMA dell\'accensione (sessione precedente) -> stantii', () => {
        expect(effettiviStantii({
            started_at: '2026-09-28T10:00:05Z', heartbeat_at: '2026-09-28T09:58:00Z',
        })).toBe(true);
    });

    it('battito DOPO l\'accensione (il servizio ha gia\' pubblicato con lo stato nuovo) -> non stantii', () => {
        expect(effettiviStantii({
            started_at: '2026-09-28T10:00:05Z', heartbeat_at: '2026-09-28T10:00:09Z',
        })).toBe(false);
    });
});

describe('leggiVarianti — al primo clic si leggono i parametri scritti, non gli effettivi stantii', () => {
    it('senza il flag (comportamento di sempre): effettivi non vuoti vincono su params', () => {
        const effettivi = { variants: ['base', 'esatto', 'punta', 'tennis'] }; // sessione precedente
        const params = { variants: ['tennis'] }; // appena scritto: «solo tennis»
        expect(leggiVarianti(params, effettivi)).toEqual(['base', 'esatto', 'punta', 'tennis']);
    });

    it('con il flag (effettivi stantii): si legge SOLO quanto appena scritto in params', () => {
        const effettivi = { variants: ['base', 'esatto', 'punta', 'tennis'] }; // sessione precedente
        const params = { variants: ['tennis'] }; // «solo tennis», appena scritto
        expect(leggiVarianti(params, effettivi, true)).toEqual(['tennis']);
    });

    it('con il flag ma senza effettivi: params resta l\'unica fonte, come prima', () => {
        expect(leggiVarianti({ variants: ['base'] }, null, true)).toEqual(['base']);
    });
});

describe('leggiModiStrategia — stessa regola, sulla mappa strategy_modes', () => {
    it('con il flag: si scarta la mappa stantia degli effettivi', () => {
        const effettivi = { strategy_modes: { base: 'live', esatto: 'live', punta: 'paper', tennis: 'paper' } };
        const params = { strategy_modes: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper' } };
        expect(leggiModiStrategia(effettivi, params, true)).toEqual({
            base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper',
        });
    });

    it('senza il flag: gli effettivi restano la fonte preferita (nessuna regressione)', () => {
        const effettivi = { strategy_modes: { tennis: 'live' } };
        const params = { strategy_modes: { tennis: 'paper' } };
        expect(leggiModiStrategia(effettivi, params)).toEqual({ tennis: 'live' });
    });
});
