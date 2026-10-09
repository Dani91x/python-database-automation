// boardDati.test.ts - 09/10: le regole pure del Programma del giorno sui
// casi che la pagina non raggiunge (righe storte, orfani, bordi della barra).
import { describe, it, expect } from 'vitest';
import {
    MATCH_ODDS, escluso, eventiDelMercato, leggiBoard, leggiBoardMercato, modoApplicato,
    modoOrdiniBoard, quotaLiquidita, vociMenu,
} from './boardDati';
import type { ModoOrdiniCanale } from '@/lib/runnerCanale';

const riga = (event_id: string | number, open_date: string) => ({
    event_id, event_name: `ev ${event_id}`, open_date, market_id: `1.${event_id}`, status: 'OPEN',
    inplay: false, total_matched: 10, selections: [],
});

describe('lettura dei push', () => {
    it('righe senza id si scartano, gli id numerici diventano stringhe, un assente resta null', () => {
        const t = leggiBoard({ rows: [riga(7, '2026-10-09T10:00:00Z'), { event_name: 'senza id' },
            { ...riga('8', '2026-10-09T09:00:00Z'), total_matched: 'tanti', fixture_id: 0 }] }, 'calcio');
        expect(t?.rows.map((r) => r.event_id)).toEqual(['7', '8']);
        expect(t?.rows[1].total_matched).toBeNull();
        expect(t?.rows[1].fixture_id).toBeNull();
        expect(t?.marketTypes).toBeNull();
        expect(leggiBoard({ righe: [] }, 'calcio')).toBeNull();
        expect(leggiBoardMercato({ rows: [] })).toBeNull();   // senza tipo: storto
    });
});

describe('menu\'', () => {
    it('il filtro dei correct score vale SOLO per il calcio', () => {
        expect(escluso('calcio', 'CORRECT_SCORE2_B')).toBe(true);
        expect(escluso('calcio', 'HALF_TIME_SCORE')).toBe(true);
        expect(escluso('calcio', 'OVER_UNDER_25')).toBe(false);
        expect(escluso('tennis', 'CORRECT_SCORE')).toBe(false);
    });

    it('MATCH_ODDS sempre primo anche se manca o arriva in coda; niente doppioni', () => {
        expect(vociMenu('tennis', null).map((v) => v.market_type)).toEqual([MATCH_ODDS]);
        const v = vociMenu('tennis', [
            { market_type: 'SET_BETTING', name: 'Set Betting', count: 1 },
            { market_type: 'MATCH_ODDS', name: 'Match Odds', count: 2 },
            { market_type: 'SET_BETTING', name: 'Set Betting', count: 1 },
        ]);
        expect(v.map((x) => x.market_type)).toEqual([MATCH_ODDS, 'SET_BETTING']);
    });
});

describe('unione per evento', () => {
    it('righe ordinate per orario; mercati di eventi fuori programma contati come orfani', () => {
        const rows = leggiBoard({ rows: [riga(2, '2026-10-09T11:00:00Z'), riga(1, '2026-10-09T10:00:00Z')] }, 'calcio')!.rows;
        expect(eventiDelMercato(rows, MATCH_ODDS, null).eventi.map((e) => e.riga.event_id)).toEqual(['1', '2']);
        const m = leggiBoardMercato({ market_type: 'OVER_UNDER_25', updated_ms: 1, rows: [
            { event_id: 2, market_id: '1.22', market_name: 'O/U 2.5', status: 'OPEN', inplay: false, total_matched: 3, selections: [] },
            { event_id: 99, market_id: '1.99', market_name: 'O/U 2.5', status: 'OPEN', inplay: false, total_matched: 3, selections: [] },
        ] });
        const v = eventiDelMercato(rows, 'OVER_UNDER_25', m);
        expect(v.eventi.map((e) => e.riga.event_id)).toEqual(['2']);
        expect(v.senzaMercato).toBe(1);
        expect(v.orfani).toBe(1);
        // il push di un altro tipo non vale: si aspetta
        expect(eventiDelMercato(rows, 'BOTH_TEAMS_TO_SCORE', m).attesa).toBe(true);
    });
});

describe('barra di liquidita\'', () => {
    it('relativa al massimo, limitata a 0-100; senza dati nessuna barra', () => {
        expect(quotaLiquidita(50, 200)).toBe(25);
        expect(quotaLiquidita(0, 200)).toBe(0);
        expect(quotaLiquidita(null, 200)).toBeNull();
        expect(quotaLiquidita(10, null)).toBeNull();
        expect(quotaLiquidita(300, 200)).toBe(100);
    });
});

describe('modalita\' ordini', () => {
    const m = (effettivo: 'OFF' | 'PAPER' | 'LIVE', ms: number, alCambio = true): ModoOrdiniCanale =>
        ({ effettivo, tetto: 'LIVE', scelto: effettivo, ms, alCambio });

    it('vince il piu\' recente; il `now` vale solo entro 15 s', () => {
        expect(modoApplicato(m('PAPER', 1_000), m('LIVE', 2_000, false), 10_000)?.effettivo).toBe('LIVE');
        expect(modoApplicato(m('PAPER', 1_000), m('LIVE', 2_000, false), 20_000)?.effettivo).toBe('PAPER');
        expect(modoApplicato(m('LIVE', 3_000), m('PAPER', 2_000, false), 4_000)?.effettivo).toBe('LIVE');
        expect(modoApplicato(null, null, 0)).toBeNull();
    });

    it('nessun modo = nessun ordine; OFF = nessun ordine; freno = modo noto ma bloccato', () => {
        expect(modoOrdiniBoard(null, null)).toMatchObject({ mode: null, etichetta: 'ORDINI: NON NOTA' });
        expect(modoOrdiniBoard(m('OFF', 1), null)).toMatchObject({ mode: null, etichetta: 'ORDINI OFF' });
        expect(modoOrdiniBoard(m('LIVE', 1), null)).toEqual({ mode: 'live', etichetta: 'LIVE · REALE', motivo: null });
        const f = modoOrdiniBoard(m('PAPER', 1), true);
        expect(f.mode).toBe('paper');
        expect(f.motivo).toContain('Freno');
    });
});
