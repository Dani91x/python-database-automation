// ============================================================================
// provaGiornata.test.ts - P8 (30/09): la PROVA «oggi» e' per partite di OGGI;
// le partite di giorni precedenti regolate oggi sono ARRETRATI, a parte.
//
// Righe finte con le chiavi di `safe_strategy_trades` / `mike_trades` /
// `omega_trades` (lette sul DB il 30/09): id, event_id, event_name, sport,
// mode, status, pnl, placed_at, settled_at, closes_trade_id (+ `kickoff` di
// Omega, `ko_at` degli arretrati di Mike dal backend).
//
// Caso vero di oggi (progetto §0): 4 righe paper di Safe del 26/09 regolate
// oggi alle 12:41 UTC, +1,90 l'una = +7,60; 5 righe paper di Mike (2 partite
// del 26/09) regolate alla stessa ora = -18,29, che `get_mike_state` non porta.
// ============================================================================
import { describe, expect, it } from 'vitest';
import {
    etichettaArretrati, leggiArretratiProva, provaGiornata, provaPerGiornoPartita,
    type RigaTradeProva,
} from './provaGiornata';

const OGGI = '2026-09-30';
const giornoDi = (iso: string | null | undefined): string => {
    const ms = iso ? Date.parse(iso) : NaN;
    if (!Number.isFinite(ms)) return '';
    return new Date(ms + 2 * 3600 * 1000).toISOString().slice(0, 10);   // Roma, ora legale
};

const safe = (id: number, event_id: string, event_name: string, placed_at: string): RigaTradeProva => ({
    id, event_id, event_name, sport: 'calcio', mode: 'paper', status: 'won', pnl: 1.9,
    placed_at, settled_at: '2026-09-30T12:41:11.195408+00:00', closes_trade_id: null,
} as RigaTradeProva);

const SAFE_26 = [
    safe(363, '35925583', 'Iceland – Estonia', '2026-09-26T17:25:20Z'),
    safe(359, '35926090', 'Bulgaria – Luxembourg', '2026-09-26T16:50:55Z'),
    safe(361, '36090836', 'Faroe Islands – Kazakhstan', '2026-09-26T16:57:23Z'),
    safe(362, '36114311', 'Kuwait – Iraq', '2026-09-26T17:23:18Z'),
];

const mike = (id: number, event_id: string, event_name: string, status: string, pnl: number,
    placed_at: string, ko_at: string): RigaTradeProva & { ko_at: string } => ({
    id, event_id, event_name, mode: 'paper', status, pnl, placed_at,
    settled_at: '2026-09-30T12:41:20.434352+00:00', closes_trade_id: null, ko_at,
});
const MIKE_26 = [
    mike(5077, '36109477', 'Latvia U21 v Germany U21', 'lost', -5.0, '2026-09-26T15:18:51Z', '2026-09-26T15:00:00Z'),
    mike(5078, '36109477', 'Latvia U21 v Germany U21', 'lost', -2.5, '2026-09-26T16:03:18Z', '2026-09-26T15:00:00Z'),
    mike(5080, '36109477', 'Latvia U21 v Germany U21', 'lost', -6.4, '2026-09-26T16:05:17Z', '2026-09-26T15:00:00Z'),
    mike(5081, '36109477', 'Latvia U21 v Germany U21', 'lost', -6.67, '2026-09-26T16:08:24Z', '2026-09-26T15:00:00Z'),
    mike(5082, '36093027', 'MVV Maastricht v Helmond Sport', 'won', 2.28, '2026-09-26T17:21:06Z', '2026-09-26T16:00:00Z'),
];
// la chiave del backend, forma concordata il 30/09
const ARRETRATI_MIKE = { day: OGGI, righe: MIKE_26.map((r) => ({ ...r, bot: 'mike' })) };

describe('provaPerGiornoPartita - oggi contro arretrati', () => {
    it('Safe: 4 partite del 26/09 regolate oggi sono ARRETRATI, oggi resta vuoto', () => {
        const r = provaPerGiornoPartita(SAFE_26, { oggi: OGGI, giornoDi });
        expect(r.oggi).toEqual([]);
        expect(r.arretrati).toHaveLength(4);
        expect(r.arretrati.every((x) => x.giornoPartita === '2026-09-26' && x.origineGiorno === 'apertura')).toBe(true);
    });

    it('una partita di oggi regolata oggi e\' «oggi»; una aperta non entra; il live mai', () => {
        const oggi = safe(400, 'E1', 'A – B', '2026-09-30T10:00:00Z');
        const aperta = { ...safe(401, 'E2', 'C – D', '2026-09-30T10:00:00Z'), status: 'open', pnl: null, settled_at: null };
        const live = { ...safe(402, 'E3', 'E – F', '2026-09-30T10:00:00Z'), mode: 'live' };
        const r = provaPerGiornoPartita([oggi, aperta, live, ...SAFE_26], { oggi: OGGI, giornoDi });
        expect(r.oggi.map((x) => x.eventId)).toEqual(['E1']);
        expect(r.arretrati).toHaveLength(4);
    });

    it('Omega: il giorno viene dal FISCHIO (kickoff), non dal piazzamento', () => {
        // piazzata oggi alle 00:10 Roma per una partita del 29/09 alle 23:30 Roma
        const o = { ...safe(116, 'E9', 'G – H', '2026-09-29T22:10:00Z'), kickoff: '2026-09-29T21:30:00Z' };
        const r = provaPerGiornoPartita([o], { oggi: OGGI, giornoDi });
        expect(r.oggi).toEqual([]);
        expect(r.arretrati[0]).toMatchObject({ giornoPartita: '2026-09-29', origineGiorno: 'fischio' });
    });
});

describe('provaGiornata - il caso vero del 30/09', () => {
    const base = { oggi: OGGI, giornoDi, omega: [], safe: SAFE_26, mike: [], tennisPaper: [] };

    it('con gli arretrati di Mike dal backend: oggi 0,00; arretrati Safe +7,60 e Mike -18,29, separati', () => {
        const p = provaGiornata({ ...base, mikeArretrati: leggiArretratiProva(ARRETRATI_MIKE, OGGI) });
        expect(p.oggiPerSport.calcio).toMatchObject({ pnl: 0, operazioni: 0 });
        const safeV = p.voci.find((v) => v.chiave === 'safe_calcio')!;
        expect(safeV.oggi!.pnl).toBe(0);
        expect(safeV.arretrati).toEqual([
            { giorno: '2026-09-26', origine: 'apertura', pnl: 7.6, operazioni: 4, vinte: 4, perse: 0, partite: 4 },
        ]);
        const mikeV = p.voci.find((v) => v.chiave === 'mike')!;
        expect(mikeV.arretrati).toEqual([
            { giorno: '2026-09-26', origine: 'fischio', pnl: -18.29, operazioni: 5, vinte: 1, perse: 4, partite: 2 },
        ]);
        // per sport: DUE gruppi (stessa data, origini diverse): mai fusi in -10,69
        expect(p.arretratiPerSport.calcio.map((g) => [g.origine, g.pnl])).toEqual([['apertura', 7.6], ['fischio', -18.29]]);
        expect(p.arretratiNonLetti.calcio).toEqual([]);
        expect(etichettaArretrati(mikeV.arretrati![0])).toBe('2 partite del 26/09');
        expect(etichettaArretrati(safeV.arretrati![0])).toBe('4 operazioni aperte il 26/09');
    });

    it('SENZA la chiave del backend: gli arretrati di Mike sono «non letti», mai 0,00 e mai taciuti', () => {
        const p = provaGiornata({ ...base, mikeArretrati: leggiArretratiProva(undefined, OGGI) });
        const mikeV = p.voci.find((v) => v.chiave === 'mike')!;
        expect(mikeV.arretrati).toBeNull();
        expect(mikeV.nota).toBe('arretrati di Mike: non letti');
        expect(p.arretratiNonLetti.calcio).toEqual(['Mike']);
        // quelli di Safe restano visibili
        expect(p.arretratiPerSport.calcio.map((g) => g.pnl)).toEqual([7.6]);
    });

    it('chiave del backend con righe: [] = NESSUN arretrato (letto e vuoto), non «non letti»', () => {
        const p = provaGiornata({ ...base, mikeArretrati: leggiArretratiProva({ day: OGGI, righe: [] }, OGGI) });
        const mikeV = p.voci.find((v) => v.chiave === 'mike')!;
        expect(mikeV.arretrati).toEqual([]);
        expect(mikeV.nota).toBeNull();
        expect(p.arretratiNonLetti.calcio).toEqual([]);
    });

    it('chiave del backend di un altro giorno o malformata = non letti', () => {
        expect(leggiArretratiProva({ day: '2026-09-29', righe: [] }, OGGI)).toBeNull();
        expect(leggiArretratiProva({ day: OGGI, righe: [{ id: 'x' }] }, OGGI)).toBeNull();
        expect(leggiArretratiProva({ day: OGGI, righe: [] }, OGGI)).toEqual([]);
    });

    it('bot tennis: per giorno di regolamento, dichiarato; arretrati non separabili ma non «non letti»', () => {
        const p = provaGiornata({ ...base, mikeArretrati: [], tennisPaper: [{ pnl_netto: 1.13, ordini: 5, vinti: 4, persi: 1 }] });
        expect(p.oggiPerSport.tennis).toMatchObject({ pnl: 1.13, operazioni: 5 });
        expect(p.perRegolamento.tennis).toEqual(['Bot tennis (Scalper · Pro · FLB · Swing)']);
    });

    it('righe di un bot non lette: «oggi» null, mai zero', () => {
        const p = provaGiornata({ ...base, safe: null, mikeArretrati: [] });
        expect(p.voci.find((v) => v.chiave === 'safe_calcio')!.oggi).toBeNull();
        expect(p.voci.find((v) => v.chiave === 'safe_calcio')!.arretrati).toBeNull();
    });
});
