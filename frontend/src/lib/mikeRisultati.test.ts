// ============================================================================
// Le operazioni raggruppate per PARTITA, e la divisione pre-match / live.
//
// È la base delle schede «Operazioni», «Risultati Pre-Match» e «Risultati Live».
// Se questi conti sbagliano, il trader legge un P&L che non esiste: sono i test
// che contano di più di tutta la pagina.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    groupMikeTrades, groupMikeTradesByEvent, fasePerCiclo, totaleRisultati,
    etaPubblicazioneS, type MikeTrade, type MikeLive,
} from './mike';

let seq = 0;
function t(over: Partial<MikeTrade> = {}): MikeTrade {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'under_entry',
        role: 'under_entry', cycle_no: 0, market_type: 'OVER_UNDER_35', market_id: '1.1',
        selection_id: 1222344, side: 'back', price: 1.5, size: 10, liability: 10,
        commission: 5, mode: 'paper', status: 'won', pnl: 0, bet_id: null,
        placed_at: '2026-09-13T10:00:00Z', day_placed_at: '2026-09-13T10:00:00Z',
        settled_at: null, signal_key: `k${seq}`, meta: {}, closes_trade_id: null,
        origin: 'auto',
        ...over,
    } as MikeTrade;
}

/** un ciclo completo: apertura + chiusura, col loro P&L netto */
function ciclo(over: Partial<MikeTrade>, pnlApre: number, pnlChiude: number, chiusuraRole: string) {
    const apre = t({ ...over, pnl: pnlApre });
    const chiude = t({
        ...over, role: chiusuraRole, side: 'lay', pnl: pnlChiude,
        closes_trade_id: apre.id, placed_at: '2026-09-13T10:05:00Z',
    });
    return [apre, chiude];
}

describe('a quale fase appartiene un ciclo', () => {
    it("l'ingresso pre-match apre un ciclo PRE-MATCH", () => {
        const g = groupMikeTrades(ciclo({ role: 'under_entry' }, -10, 10.13, 'under_green'));
        expect(g).toHaveLength(1);
        expect(fasePerCiclo(g[0])).toBe('pre');
    });

    it("l'ultimo ingresso in PERSIST è LIVE: è la posizione che va in gioco", () => {
        const g = groupMikeTrades(ciclo({ role: 'under_last' }, -10, 12, 'under_close'));
        expect(fasePerCiclo(g[0])).toBe('live');
    });

    it('copertura, seconda puntata e re-ingresso sono live', () => {
        for (const role of ['over_cover', 'under_second', 'reentry']) {
            const g = groupMikeTrades([t({ role })]);
            expect(fasePerCiclo(g[0]), role).toBe('live');
        }
    });

    it('una chiusura orfana eredita la fase dal proprio ruolo', () => {
        const orfana = groupMikeTrades([t({ role: 'under_green', closes_trade_id: 9999 })]);
        expect(orfana[0].orphan).toBe(true);
        expect(fasePerCiclo(orfana[0])).toBe('pre');
        const orfanaLive = groupMikeTrades([t({ role: 'over_close', closes_trade_id: 9999 })]);
        expect(fasePerCiclo(orfanaLive[0])).toBe('live');
    });
});

describe('il P&L netto per PARTITA', () => {
    it('somma le righe regolate della partita, apertura e chiusure', () => {
        // ciclo pre-match chiuso in green: -10 sull'apertura, +10,13 sulla chiusura
        const righe = ciclo({ role: 'under_entry' }, -10, 10.13, 'under_green');
        const ev = groupMikeTradesByEvent(groupMikeTrades(righe));
        expect(ev).toHaveLength(1);
        expect(ev[0].event_name).toBe('Roma v Lazio');
        expect(ev[0].netPnl).toBeCloseTo(0.13, 2);
        expect(ev[0].apertaAncora).toBe(false);
        expect(ev[0].righeRegolate).toBe(2);
    });

    it('mette insieme più cicli della STESSA partita in una riga sola', () => {
        const righe = [
            ...ciclo({ role: 'under_entry', cycle_no: 0 }, -10, 10.13, 'under_green'),
            ...ciclo({ role: 'under_entry', cycle_no: 1 }, -10, 10.20, 'under_green'),
        ];
        const ev = groupMikeTradesByEvent(groupMikeTrades(righe));
        expect(ev).toHaveLength(1);
        expect(ev[0].cicli).toHaveLength(2);
        expect(ev[0].netPnl).toBeCloseTo(0.33, 2);
    });

    it('tiene separate partite diverse', () => {
        const righe = [
            ...ciclo({ event_id: 'E1', event_name: 'Roma v Lazio' }, -10, 10.13, 'under_green'),
            ...ciclo({ event_id: 'E2', event_name: 'Inter v Milan' }, 8.75, -9.20, 'under_close'),
        ];
        const ev = groupMikeTradesByEvent(groupMikeTrades(righe));
        expect(ev.map((e) => e.event_id).sort()).toEqual(['E1', 'E2']);
        expect(ev.find((e) => e.event_id === 'E2')!.netPnl).toBeCloseTo(-0.45, 2);
    });

    it("le righe in errore NON sono operazioni: non contano e non si mostrano", () => {
        const apre = t({ pnl: -10 });
        const fallita = t({ status: 'error', pnl: 0, role: 'over_cover' });
        const chiude = t({ role: 'under_green', pnl: 10.13, closes_trade_id: apre.id });
        const ev = groupMikeTradesByEvent(groupMikeTrades([apre, fallita, chiude]));
        expect(ev[0].netPnl).toBeCloseTo(0.13, 2);
        expect(ev[0].righeRegolate).toBe(2);
        expect(ev[0].righeAperte).toBe(0);
    });

    it('niente ancora regolato = «—», MAI «0,00»', () => {
        const ev = groupMikeTradesByEvent(groupMikeTrades([t({ status: 'open', pnl: null })]));
        expect(ev[0].netPnl).toBeNull();
        expect(ev[0].apertaAncora).toBe(true);
        expect(ev[0].righeAperte).toBe(1);
    });

    it('una partita a metà dichiara che il netto è ancora parziale', () => {
        const apre = t({ pnl: -10, status: 'lost' });
        const viva = t({ role: 'over_cover', status: 'open', pnl: null });
        const ev = groupMikeTradesByEvent(groupMikeTrades([apre, viva]));
        expect(ev[0].netPnl).toBeCloseTo(-10, 2);
        expect(ev[0].apertaAncora).toBe(true);
    });

    it('dichiara la modalità, e segnala se una partita le mescola', () => {
        const soloPaper = groupMikeTradesByEvent(groupMikeTrades([t({ mode: 'paper' })]));
        expect(soloPaper[0].mode).toBe('paper');
        const mista = groupMikeTradesByEvent(groupMikeTrades([
            t({ mode: 'paper' }), t({ mode: 'live', role: 'over_cover' }),
        ]));
        expect(mista[0].mode).toBe('mista');
    });

    it('ordina dalla partita con l\'operazione più recente', () => {
        const ev = groupMikeTradesByEvent(groupMikeTrades([
            t({ event_id: 'VECCHIA', placed_at: '2026-09-13T08:00:00Z' }),
            t({ event_id: 'NUOVA', placed_at: '2026-09-13T20:00:00Z' }),
        ]));
        expect(ev[0].event_id).toBe('NUOVA');
    });
});

describe('il filtro per fase alimenta le due schede Risultati', () => {
    const righe = [
        ...ciclo({ event_id: 'E1', role: 'under_entry' }, -10, 10.13, 'under_green'),
        ...ciclo({ event_id: 'E1', role: 'under_last' }, 8.75, -9.20, 'under_close'),
        ...ciclo({ event_id: 'E2', role: 'under_entry' }, -10, 10.40, 'under_green'),
    ];
    const gruppi = groupMikeTrades(righe);

    it('Risultati Pre-Match vede solo i cicli chiusi prima del fischio', () => {
        const pre = groupMikeTradesByEvent(gruppi, 'pre');
        expect(pre.map((e) => e.event_id).sort()).toEqual(['E1', 'E2']);
        expect(pre.find((e) => e.event_id === 'E1')!.netPnl).toBeCloseTo(0.13, 2);
        expect(pre.find((e) => e.event_id === 'E2')!.netPnl).toBeCloseTo(0.40, 2);
    });

    it('Risultati Live vede solo quello che è successo in gioco', () => {
        const live = groupMikeTradesByEvent(gruppi, 'live');
        expect(live.map((e) => e.event_id)).toEqual(['E1']);
        expect(live[0].netPnl).toBeCloseTo(-0.45, 2);
    });

    it('la stessa partita compare in ENTRAMBE se ha operato in entrambe le fasi', () => {
        const pre = groupMikeTradesByEvent(gruppi, 'pre').map((e) => e.event_id);
        const live = groupMikeTradesByEvent(gruppi, 'live').map((e) => e.event_id);
        expect(pre).toContain('E1');
        expect(live).toContain('E1');
    });

    it('senza filtro il netto della partita è la somma delle due fasi', () => {
        const tutte = groupMikeTradesByEvent(gruppi);
        const e1 = tutte.find((e) => e.event_id === 'E1')!;
        expect(e1.netPnl).toBeCloseTo(0.13 - 0.45, 2);
        expect(e1.fasi).toEqual(['live', 'pre']);
    });
});

describe('il totale mostrato in cima alle schede Risultati', () => {
    it('somma solo quello che ha già un risultato, e dichiara le aperte', () => {
        const righe = [
            ...ciclo({ event_id: 'A' }, -10, 10.13, 'under_green'),
            ...ciclo({ event_id: 'B' }, -10, 9.00, 'under_green'),
            t({ event_id: 'C', status: 'open', pnl: null }),
        ];
        const tot = totaleRisultati(groupMikeTradesByEvent(groupMikeTrades(righe)));
        expect(tot.netto).toBeCloseTo(0.13 - 1.00, 2);
        expect(tot.conRisultato).toBe(2);
        expect(tot.vinte).toBe(1);
        expect(tot.perse).toBe(1);
        expect(tot.aperte).toBe(1);
    });

    it('nessuna partita = tutto a zero, senza esplodere', () => {
        expect(totaleRisultati([])).toEqual({ netto: 0, conRisultato: 0, aperte: 0, vinte: 0, perse: 0 });
    });
});

describe("l'età della riga pubblicata deve CRESCERE da sola", () => {
    const live = (over: Partial<MikeLive> = {}) => ({ published_ts: 1_800_000_000, ...over } as MikeLive);

    it('cresce con il passare del tempo, anche se il servizio è fermo', () => {
        expect(etaPubblicazioneS(live(), 1_800_000_000_000)).toBe(0);
        expect(etaPubblicazioneS(live(), 1_800_000_003_000)).toBe(3);
        expect(etaPubblicazioneS(live(), 1_800_000_120_000)).toBe(120);
    });

    it('mai negativa se gli orologi non sono allineati', () => {
        expect(etaPubblicazioneS(live(), 1_799_999_990_000)).toBe(0);
    });

    it('null se il servizio non pubblica l\'istante: non si finge che sia fresca', () => {
        expect(etaPubblicazioneS({} as MikeLive, Date.now())).toBeNull();
        expect(etaPubblicazioneS(null, Date.now())).toBeNull();
        expect(etaPubblicazioneS(live({ published_ts: null }), Date.now())).toBeNull();
    });
});
