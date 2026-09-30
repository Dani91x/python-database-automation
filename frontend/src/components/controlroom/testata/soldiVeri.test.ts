// ============================================================================
// soldiVeri.test.ts - P3 (30/09): la fascia "SOLDI VERI ADESSO", moduli puri.
//
// Finti con le chiavi e i tipi dei produttori veri:
//  - riga `betfair_live_account` (lib/liveOrders LiveAccountRow: available,
//    exposure, updated_at), exposure NEGATIVA come la scrive Betfair
//    (reconcile_worker.py:147-150, getAccountFunds);
//  - messaggio `account` del canale (reconcile_worker.py:161-167:
//    {available, exposure, checked_at}), letto da `leggiSaldoDalCanale`;
//  - aggregati SQL: Mike `mike_aggregates_sql` ('mode' = modalita' del bot,
//    open_liability netta, liability_stale), Omega `aggregates_by_mode`
//    {paper, live} (omega_state_per_modalita_2026-09-26.sql), Safe
//    `get_safe_state()` senza p_mode ('mode': null = tutte le modalita').
// Numeri di oggi (PROGETTO_UI_MONITOR_VERITIERO.md par. 0): conto -9,95;
// Mike 9,80 + 6,42 + 0 = 16,22; la lorda 39,15/37,04 non e' una di queste.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    contoAdesso, liabilityLiveDichiarata, rischioBotLive, scartoContoBot, partiteConPosizione,
} from './soldiVeri';
import { leggiSaldoDalCanale } from '@/lib/saldoBetfair';

const NOW = Date.parse('2026-09-30T14:05:00Z');
const RIGA = { available: 30.61, exposure: -9.95, updated_at: '2026-09-30T14:04:00+00:00' };

const mikeLive = { aggregates: { mode: 'live', open_liability: 16.22, liability_source: 'net_positions', liability_stale: false } };
const omegaPaper = {
    aggregates: { mode: 'paper', open_liability: 0 },
    aggregates_by_mode: { paper: { mode: 'paper', open_liability: 0 }, live: { mode: 'live', open_liability: 0 } },
};
const safeTutte = { aggregates: { mode: null, open_liability: 0 } };

const APERTE_OGGI = [
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Follo' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Follo' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Vsetin' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Vsetin' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Farul' },
];

describe('contoAdesso - la stessa catena di SaldoBetfairCard', () => {
    it('riga del database sola: esposizione e disponibile come li scrive Betfair, eta\' dell\'ultimo cambio', () => {
        const c = contoAdesso({ riga: RIGA, canale: null, etaRunnerS: 5, nowMs: NOW });
        expect(c.letto).toBe(true);
        expect(c.esposizione).toBe(-9.95);
        expect(c.disponibile).toBe(30.61);
        expect(c.fonte).toBe('database');
        expect(c.etaS).toBe(60);
        expect(c.attenzione).toBe(false);
    });

    it('il canale piu\' recente vince (checked_at contro updated_at)', () => {
        const canale = leggiSaldoDalCanale({ available: 30.41, exposure: -10.15, checked_at: '2026-09-30T14:04:57+00:00' });
        const c = contoAdesso({ riga: RIGA, canale, etaRunnerS: 5, nowMs: NOW });
        expect(c.esposizione).toBe(-10.15);
        expect(c.fonte).toBe('canale');
        expect(c.etaS).toBe(3);
    });

    it('conto MAI letto: nessuna cifra (null), mai 0', () => {
        const c = contoAdesso({ riga: null, canale: null, etaRunnerS: null, nowMs: NOW });
        expect(c.letto).toBe(false);
        expect(c.esposizione).toBeNull();
        expect(c.disponibile).toBeNull();
        expect(c.attenzione).toBe(true);
    });

    it('battito del runner vecchio: il valore c\'e\' ma e\' "non verificato di recente"', () => {
        const c = contoAdesso({ riga: RIGA, canale: null, etaRunnerS: 600, nowMs: NOW });
        expect(c.esposizione).toBe(-9.95);
        expect(c.attenzione).toBe(true);
    });
});

describe('liabilityLiveDichiarata - solo il rischio che il servizio dichiara LIVE', () => {
    it('Omega: aggregates_by_mode.live', () => {
        expect(liabilityLiveDichiarata({ ...omegaPaper, aggregates_by_mode: { paper: { open_liability: 7 }, live: { open_liability: 3.5 } } }, 4).valore).toBe(3.5);
    });
    it('Mike: aggregato con mode live', () => {
        expect(liabilityLiveDichiarata(mikeLive, 0).valore).toBe(16.22);
    });
    it('aggregato PAPER: mai rischio vero', () => {
        expect(liabilityLiveDichiarata({ aggregates: { mode: 'paper', open_liability: 25 } }, 0).valore).toBeNull();
    });
    it('aggregato di TUTTE le modalita\' (Safe): valido solo senza posizioni paper aperte', () => {
        expect(liabilityLiveDichiarata({ aggregates: { mode: null, open_liability: 12 } }, 0).valore).toBe(12);
        expect(liabilityLiveDichiarata({ aggregates: { mode: null, open_liability: 12 } }, 1).valore).toBeNull();
    });
    it('stantio dichiarato dal servizio (Mike liability_stale)', () => {
        expect(liabilityLiveDichiarata({ aggregates: { mode: 'live', open_liability: 1, liability_stale: true } }, 0).stantio).toBe(true);
    });
    it('stato non letto / open_liability non numerica: null', () => {
        expect(liabilityLiveDichiarata(null, 0).valore).toBeNull();
        expect(liabilityLiveDichiarata({ aggregates: { mode: 'live', open_liability: '16.22' } }, 0).valore).toBeNull();
    });
});

describe('rischioBotLive - i numeri di oggi', () => {
    it('Mike 16,22 (9,80 + 6,42 + 0), Omega 0, Safe 0: totale 16,22, completo', () => {
        const r = rischioBotLive({ letti: true, stati: { omega: omegaPaper, safe: safeTutte, mike: mikeLive }, aperte: APERTE_OGGI });
        expect(r.totale).toBe(16.22);
        expect(r.completo).toBe(true);
        expect(r.voci.find((v) => v.bot === 'mike')).toMatchObject({ valore: 16.22, aperteLive: 5 });
        // la somma LORDA delle righe non entra da nessuna parte
        expect(r.totale).not.toBe(39.15);
        expect(r.totale).not.toBe(37.04);
    });

    it('posizioni non ancora lette: nessuna cifra', () => {
        const r = rischioBotLive({ letti: false, stati: { mike: mikeLive }, aperte: [] });
        expect(r.totale).toBeNull();
        expect(r.completo).toBe(false);
    });

    it('Mike con aggregato PAPER ma posizioni LIVE: non incluso, somma parziale dichiarata', () => {
        const r = rischioBotLive({
            letti: true,
            stati: { omega: omegaPaper, safe: safeTutte, mike: { aggregates: { mode: 'paper', open_liability: 30 } } },
            aperte: APERTE_OGGI,
        });
        expect(r.completo).toBe(false);
        const mike = r.voci.find((v) => v.bot === 'mike');
        expect(mike?.valore).toBeNull();
        expect(mike?.nota).toMatch(/non dichiara/);
        expect(r.totale).toBe(0);
    });

    it('Safe con posizioni paper e live e aggregato misto: non separabile', () => {
        const r = rischioBotLive({
            letti: true,
            stati: { omega: omegaPaper, safe: { aggregates: { mode: null, open_liability: 40 } }, mike: mikeLive },
            aperte: [...APERTE_OGGI, { bot: 'safe', modalita: 'live' }, { bot: 'safe', modalita: 'paper' }],
        });
        expect(r.voci.find((v) => v.bot === 'safe')?.valore).toBeNull();
        expect(r.completo).toBe(false);
        expect(r.totale).toBe(16.22);
    });

    it('bot senza liability netta (tennis, scalper) con posizioni LIVE: dichiarato fuori dalla somma', () => {
        const r = rischioBotLive({
            letti: true,
            stati: { omega: omegaPaper, safe: safeTutte, mike: mikeLive },
            aperte: [...APERTE_OGGI, { bot: 'tennis_pro', modalita: 'live' }],
        });
        const t = r.voci.find((v) => v.bot === 'tennis_pro');
        expect(t).toMatchObject({ valore: null, aperteLive: 1 });
        expect(r.completo).toBe(false);
    });

    it('bot senza posizioni LIVE e senza aggregato: 0 (noto), non "mancante"', () => {
        const r = rischioBotLive({ letti: true, stati: {}, aperte: [] });
        expect(r.totale).toBe(0);
        expect(r.completo).toBe(true);
    });
});

describe('scartoContoBot', () => {
    const rOggi = rischioBotLive({ letti: true, stati: { omega: omegaPaper, safe: safeTutte, mike: mikeLive }, aperte: APERTE_OGGI });

    it('oggi: conto 9,95 contro bot 16,22 -> non tornano di 6,27, il conto rischia MENO', () => {
        expect(scartoContoBot(-9.95, rOggi)).toEqual({ differenza: 6.27, contoPiuAlto: false });
    });
    it('tornano al centesimo: nessuno scarto', () => {
        expect(scartoContoBot(-16.22, rOggi)).toBeNull();
        expect(scartoContoBot(-16.23, rOggi)).toBeNull();
    });
    it('conto che rischia piu\' dei bot', () => {
        expect(scartoContoBot(-20, rOggi)).toEqual({ differenza: 3.78, contoPiuAlto: true });
    });
    it('conto non letto o rischio incompleto: non si puo\' dire', () => {
        expect(scartoContoBot(null, rOggi)).toBeNull();
        expect(scartoContoBot(-9.95, { ...rOggi, completo: false })).toBeNull();
    });
});

describe('partiteConPosizione', () => {
    it('partite DISTINTE, live e prova separati', () => {
        expect(partiteConPosizione([
            ...APERTE_OGGI,
            { eventId: 'Z', modalita: 'paper' }, { eventId: 'Z', modalita: 'paper' },
            { eventId: 'W', modalita: null },
        // W_T/P15: in piu' le GAMBE live (5 righe su 3 partite)
        ])).toEqual({ live: 3, prova: 1, ignota: 1, gambeLive: 5 });
    });
});
