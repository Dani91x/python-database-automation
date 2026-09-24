// 24/09 - P&L REALE DA BETFAIR e BARRA DI GIORNATA (ordini dell'utente 9 e 10).
// Righe finte con le STESSE chiavi delle tabelle vere (`omega_trades`/
// `safe_strategy_trades`/`mike_trades` + le colonne della migrazione
// `pnl_betfair_reale_2026-09-24.sql`) e del JSONB `pnl_reale_oggi` scritto dal
// runner (`reconcile_worker.componi_regolati`).
import { describe, expect, it } from 'vitest';
import {
    fonteDiRighe, nettoCicloChiuso, pnlDiRiga, groupTradesIntoCicli,
} from '@/lib/eventGroups';
import {
    componiObiettivo, differenzaContoRighe, leggiPnlRealeOggi, righeGiornataPerCiclo,
    rigaSintetica, type RigaTradeReale,
} from '@/lib/composizioneObiettivo';
import { posizioniChiuse, type TradeChiudibile } from '@/lib/posizioniChiuse';

const OGGI = '2026-09-24';
// giorno di Roma di un ISO, come `romeDay` (qui fisso sul fuso +02:00)
const giornoDi = (iso: string | null | undefined): string => {
    const ms = iso ? Date.parse(iso) : NaN;
    if (!Number.isFinite(ms)) return '';
    return new Date(ms + 2 * 3600 * 1000).toISOString().slice(0, 10);
};

function riga(p: Partial<RigaTradeReale> & { id: number }): RigaTradeReale {
    return {
        event_id: '35000001', status: 'won', mode: 'live', placed_at: '2026-09-24T10:00:00Z',
        settled_at: '2026-09-24T12:00:00Z', closes_trade_id: null, origin: 'auto',
        pnl: 0.45, bet_id: `b${p.id}`, ...p,
    } as RigaTradeReale;
}

const REALE = {
    day: OGGI, netto: 12.0, lordo: 12.7, commissione: 0.7, ordini: 5,
    senza_commissione: 0, sospetti_sito: 0,
    per_fonte: {
        omega: { netto: 0.43, ordini: 1 }, safe_calcio: { netto: 0, ordini: 0 },
        safe_tennis: { netto: 0, ordini: 0 }, mike: { netto: 0, ordini: 0 },
        bot_tennis: { netto: 1.57, ordini: 1 }, manuale_app: { netto: 0, ordini: 0 },
        manuale_sito: { netto: 10.0, ordini: 3 }, altri_bot: { netto: 0, ordini: 0 },
    },
    bet_ids: ['b1', 's1', 's2', 's3', 't1'],
    letto_at: '2026-09-24T12:00:05Z',
};

describe('P&L di una riga: Betfair se c e, altrimenti stimato', () => {
    it('vince il netto di Betfair, mai sulla riga paper', () => {
        expect(pnlDiRiga({ pnl: 0.45, pnl_betfair: 0.43, mode: 'live' })).toBe(0.43);
        expect(pnlDiRiga({ pnl: 0.45, pnl_betfair: null, mode: 'live' })).toBe(0.45);
        // paper: Betfair non esiste, un valore sulla riga non conta
        expect(pnlDiRiga({ pnl: 0.45, pnl_betfair: 9, mode: 'paper' })).toBe(0.45);
    });
    it('un insieme e da Betfair solo se TUTTE le gambe lo sono', () => {
        expect(fonteDiRighe([{ pnl_betfair: 1, mode: 'live' }, { pnl_betfair: null, mode: 'live' }]))
            .toBe('stimato');
        expect(fonteDiRighe([{ pnl_betfair: 1, mode: 'live' }])).toBe('betfair');
        expect(fonteDiRighe([{ pnl: 1, mode: 'paper' }])).toBe('paper');
    });
    it('il netto di un cash out usa il netto di Betfair di ogni gamba', () => {
        const open = { status: 'won', pnl: 0.45, pnl_betfair: 0.43, mode: 'live' };
        const close = { status: 'lost', pnl: -0.25, pnl_betfair: -0.25, mode: 'live' };
        expect(nettoCicloChiuso(open, [close])).toBe(0.18);
        const c = groupTradesIntoCicli([
            riga({ id: 1, pnl_betfair: 0.43 }),
            riga({ id: 2, pnl: -0.25, pnl_betfair: -0.25, status: 'lost', closes_trade_id: 1 }),
        ]);
        expect(c[0].netPnl).toBe(0.18);
        expect(c[0].fontePnl).toBe('betfair');
    });
});

describe('posizioni chiuse: il reale e dichiarato, lo stimato pure', () => {
    it('pnlGlobale dal netto di Betfair; senza, stimato', () => {
        const t = (p: Partial<TradeChiudibile> & { id: number }): TradeChiudibile => ({
            event_id: '1', status: 'won', mode: 'live', pnl: 0.45, placed_at: '2026-09-24T10:00:00Z',
            settled_at: '2026-09-24T12:00:00Z', __bot: 'safe', ...p,
        });
        const [reale] = posizioniChiuse([t({ id: 1, pnl_betfair: 0.43 })]);
        expect(reale.pnlGlobale).toBe(0.43);
        expect(reale.fontePnl).toBe('betfair');
        const [stimata] = posizioniChiuse([t({ id: 2 })]);
        expect(stimata.pnlGlobale).toBe(0.45);
        expect(stimata.fontePnl).toBe('stimato');
    });
});

describe('il P&L reale del conto: solo quello di OGGI', () => {
    it('giorno diverso = non disponibile, mai il totale di ieri', () => {
        expect(leggiPnlRealeOggi(REALE, OGGI)?.netto).toBe(12.0);
        expect(leggiPnlRealeOggi({ ...REALE, day: '2026-09-23' }, OGGI)).toBeNull();
        expect(leggiPnlRealeOggi({ ...REALE, netto: 'x' }, OGGI)).toBeNull();
        expect(leggiPnlRealeOggi(null, OGGI)).toBeNull();
    });
});

describe('righe della barra: reale regolato oggi + stimato non ancora regolato', () => {
    it('il reale conta per giorno di REGOLAMENTO Betfair: regolato ieri non entra oggi', () => {
        const righe = righeGiornataPerCiclo([
            riga({ id: 1, pnl_betfair: 0.43, pnl_betfair_settled_at: '2026-09-24T12:00:00Z' }),
            riga({ id: 2, pnl_betfair: 5.0, pnl_betfair_settled_at: '2026-09-23T12:00:00Z' }),
        ], { oggi: OGGI, giornoDi });
        expect(righe).toHaveLength(1);
        expect(righe[0].pnlReale).toBe(0.43);
        expect(righe[0].pnlStimato).toBeNull();
    });
    it('una riga gia contata dal conto (bet_id) non e anche stimata', () => {
        const righe = righeGiornataPerCiclo([riga({ id: 1, bet_id: 'b1' }), riga({ id: 3, bet_id: 'b3' })],
            { oggi: OGGI, giornoDi, regolatiBetfair: new Set(['b1']) });
        expect(righe).toHaveLength(1);
        expect(righe[0].pnlStimato).toBe(0.45);
    });
    it('il paper resta calcolo, su riga paper, mai reale', () => {
        const righe = righeGiornataPerCiclo([riga({ id: 4, mode: 'paper', pnl_betfair: 9 })],
            { oggi: OGGI, giornoDi });
        expect(righe[0].mode).toBe('paper');
        expect(righe[0].pnl).toBe(0.45);
        expect(righe[0].pnlReale).toBeUndefined();
    });
});

describe('composizione: la somma e il conto + gli stimati, paper a parte', () => {
    it('invariante: totale = reale del conto + stimato; manuale sito dal conto', () => {
        const omega = righeGiornataPerCiclo([
            riga({ id: 1, bet_id: 'b1', pnl_betfair: 0.43, pnl_betfair_settled_at: '2026-09-24T12:00:00Z' }),
            riga({ id: 9, bet_id: 'b9', pnl: -1.0, status: 'lost' }),               // stimato
            riga({ id: 10, bet_id: 'p10', mode: 'paper', pnl: 7.0 }),               // paper
        ], { oggi: OGGI, giornoDi, sport: 'calcio', regolatiBetfair: new Set(REALE.bet_ids) });
        const diff = differenzaContoRighe(REALE, omega);
        expect(diff).toBe(0);
        const c = componiObiettivo({
            omega, safe: [], mike: [],
            tennisBot: [rigaSintetica(1.57, null, { sport: 'tennis' })!],
            manualeSito: [rigaSintetica(10.0, null, { origin: 'manual' })!],
            manualeApp: [],
        });
        expect(c.totale).toBe(Math.round((REALE.netto + -1.0) * 100) / 100);
        expect(c.reale).toBe(REALE.netto);
        expect(c.stimato).toBe(-1.0);
        const sito = c.righe.find((r) => r.chiave === 'manuale_sito')!;
        expect(sito.valore).toBe(10.0);
        expect(sito.stimato).toBeNull();
        const om = c.righe.find((r) => r.chiave === 'omega')!;
        expect(om.valore).toBe(-0.57);
        expect(om.stimato).toBe(-1.0);
        // il paper non entra MAI nel totale dei soldi veri
        expect(c.provaPaper).toBe(7.0);
    });
    it('la differenza col conto (righe non caricate) non sparisce', () => {
        expect(differenzaContoRighe(REALE, [])).toBe(0.43);
    });
});
