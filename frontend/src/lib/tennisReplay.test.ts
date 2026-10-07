// ============================================================================
// tennisReplay.test.ts — logica PURA del Replay Tennis (07/10).
//
// Dati: la fixture `__fixtures__/replay_tennis_35790089.json` e' l'uscita del
// convertitore Python sulla registrazione VERA (Barrios Vera - Simakin,
// 07/07/2026): stesso catalogo, punteggio completo e un estratto dei frame, nella
// forma delle RPC del tennis. Dove servono piu' mercati (la registrazione vera ne
// ha uno solo) i mercati sono costruiti con le stesse chiavi del vero.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import fixture from './__fixtures__/replay_tennis_35790089.json';
import type { Frame } from '@/lib/live';
import { frameToLadderRow } from '@/lib/trainingLadder';
import type { SimBet } from '@/lib/replay-pnl';
import type { Opportunity } from '@/lib/opportunities/types';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: (...a: unknown[]) => rpc(...a) } }));

import {
    CATEGORIE_TENNIS, categoriaTennis, conFaseTennis, costruisciTimeline, delayMercatoMs,
    etichettaPunteggio, faseTennis, fetchTennisReplay, fetchTennisReplayList, framesPerMercato,
    indiceDiPasso, inizioInGioco, minutiDiGioco, MSG_MIGRAZIONE, ordinaPunteggio, perMotoreOpportunita,
    punteggioAl, puntiFinoA, raggruppaMercatiTennis, raggruppaPerTorneo, simboliTennis, sospesoPerPasso,
    ultimoAl, valutaMercatoTennis, vincitoreRegolato,
    type TennisReplayData, type TennisReplayMarket, type TennisScoreRow,
} from './tennisReplay';

const DATI = fixture as unknown as TennisReplayData;
const ORDINATE = ordinaPunteggio(DATI.score_timeline);
const MO = DATI.markets[0];
const P1 = DATI.event.player1_name;
const P2 = DATI.event.player2_name;

beforeEach(() => rpc.mockReset());

describe('fixture vera 35790089', () => {
    it('e\' la registrazione attesa', () => {
        expect(DATI.event.event_id).toBe('35790089');
        expect(MO.market_type).toBe('MATCH_ODDS');
        expect(MO.bet_delay).toBe(3);
        expect(DATI.score_timeline).toHaveLength(104);
    });
});

describe('punteggio all\'istante del cursore', () => {
    it('prima della prima riga: nessun punteggio; poi l\'ultima riga <= istante', () => {
        const primo = ORDINATE[0].ts;
        expect(punteggioAl(ORDINATE, '2026-07-07T12:00:00Z')).toBeNull();
        expect(punteggioAl(ORDINATE, primo)?.ts).toBe(primo);
        // 12:35:48 = fine del 2o set (Simakin breakka sul 5-6) -> sets 1-1, games 0-0
        const r = punteggioAl(ORDINATE, '2026-07-07T12:35:50Z')!;
        expect(r.score.sets).toEqual({ p1: 1, p2: 1 });
        expect(r.score.games).toEqual({ p1: 0, p2: 0 });
        expect(r.score.game_sequence).toEqual({ p1: ['6', '5'], p2: ['4', '7'] });
        // un istante appena prima: ancora nel 2o set, 5-6, 15-40
        const prima = punteggioAl(ORDINATE, '2026-07-07T12:35:47Z')!;
        expect(prima.score.games).toEqual({ p1: 5, p2: 6 });
        expect(prima.score.points).toEqual({ p1: '15', p2: '40' });
        expect(prima.score.server).toBe(1);
    });

    it('fine partita: Finished, 6-4 5-7 6-7', () => {
        const fine = punteggioAl(ORDINATE, '2026-07-07T23:00:00Z')!;
        expect(fine.score.status).toBe('Finished');
        expect(fine.score.set_summary).toBe('6-4 5-7 6-7');
        expect(etichettaPunteggio(fine.score)).toBe('6-4 5-7 6-7 · 0-0');
        expect(etichettaPunteggio(null)).toBe('—');
    });

    it('punto per punto fino all\'istante (la prima riga non ha punto)', () => {
        const ts = ORDINATE[5].ts;
        const punti = puntiFinoA(ORDINATE, ts);
        expect(punti).toHaveLength(5);
        expect(punti[punti.length - 1].ts).toBe(ts);
        expect(puntiFinoA(ORDINATE, '2026-07-07T23:00:00Z')).toHaveLength(103);
    });
});

describe('simboli del tennis sulla barra', () => {
    const timeline = ORDINATE.map(r => ({ ts: r.ts }));
    it('break, fine/inizio set, tie-break, fine partita: nell\'ordine vero e coi nomi giusti', () => {
        const s = simboliTennis(ORDINATE, timeline, P1, P2, null);
        expect(s.map(x => x.tipo)).toEqual([
            'break', 'set_end', 'set_start',
            'break', 'break', 'break', 'break',
            'tiebreak',
            'set_end', 'match_end',
        ]);
        expect(s[0].label).toBe('Break di Ilia Simakin (5-7)'); // il break che chiude il 2o set 7-5
        expect(s[1].label).toBe('Fine set: 6-4 5-7 (Ilia Simakin)');
        expect(s[2].label).toBe('Inizio set 3');
        expect(s[3].label).toBe('Break di Ilia Simakin (2-4)');
        expect(s[4].label).toBe('Break di Marcelo Tomas Barrios V (3-4)');
        expect(s[9].label).toBe('Fine partita: 6-4 5-7 6-7');
        // posizione = indice del passo / ultimo indice
        const iBreak = timeline.findIndex(t => t.ts === s[0].ts);
        expect(s[0].pctLeft).toBeCloseTo(iBreak / (timeline.length - 1), 9);
        expect(s.every(x => x.pctLeft >= 0 && x.pctLeft <= 1)).toBe(true);
    });

    it('passaggio in gioco solo se la registrazione parte PRIMA', () => {
        expect(simboliTennis(ORDINATE, timeline, P1, P2, ORDINATE[0].ts).some(x => x.tipo === 'inplay')).toBe(false);
        const conPre = simboliTennis(ORDINATE, timeline, P1, P2, ORDINATE[3].ts);
        expect(conPre[0]).toMatchObject({ tipo: 'inplay', ts: ORDINATE[3].ts, label: 'Passaggio in gioco' });
    });

    it('buco di registrazione = simbolo dedicato, timeline vuota = niente', () => {
        const r: TennisScoreRow = { ...ORDINATE[10], event_types: ['SALTO'] };
        expect(simboliTennis([r], timeline, P1, P2, null).map(x => x.tipo)).toEqual(['salto']);
        expect(simboliTennis(ORDINATE, [], P1, P2, null)).toEqual([]);
    });
});

describe('timeline e frame', () => {
    const frames = DATI.frames as Frame[];
    it('passi da 10 s, ordinati, e ricerca per istante', () => {
        const tl = costruisciTimeline(frames, 10_000);
        expect(tl.length).toBeGreaterThan(1);
        expect(tl.every((p, i) => i === 0 || tl[i - 1].ts < p.ts)).toBe(true);
        expect(indiceDiPasso(tl, tl[3].ts)).toBe(3);
        expect(indiceDiPasso(tl, '2030-01-01T00:00:00Z')).toBe(tl.length - 1);
        const per = framesPerMercato(frames);
        const arr = per.get(MO.market_id)!;
        expect(ultimoAl(arr, arr[5].ts)).toBe(arr[5]);
        expect(ultimoAl(arr, '2020-01-01T00:00:00Z')).toBeUndefined();
    });

    it('in gioco dal primo frame (registrazione partita a meta\' del 2o set)', () => {
        expect(inizioInGioco(frames)).toBe(frames[0].ts);
        expect(minutiDiGioco(frames[0].ts, frames[0].ts)).toBe(0);
        expect(minutiDiGioco('2026-07-07T12:40:16.127000+00:00', frames[0].ts)).toBe(12);
        expect(minutiDiGioco('2026-07-07T12:00:00Z', frames[0].ts)).toBeNull();
    });

    it('sospensione e chiusura del Match Odds sui passi', () => {
        const ultimi = frames.slice(-8);
        const tl = ultimi.map(f => ({ ts: f.ts }));
        const sosp = sospesoPerPasso(tl, framesPerMercato(ultimi), DATI.markets);
        expect(sosp).toEqual(ultimi.map(f => f.status === 'SUSPENDED'));
        expect(ultimi[ultimi.length - 1].status).toBe('CLOSED');
    });

    it('frame -> riga del ladder (training) coi nomi dei giocatori', () => {
        const f = frames[0];
        const names = new Map(MO.selections.map(s => [s.selection_id, s.name] as [number, string]));
        const row = frameToLadderRow({
            eventId: '35790089', marketId: MO.market_id, marketType: 'MATCH_ODDS', marketName: 'Match Odds',
            status: f.status, nowMs: new Date(f.ts).getTime(), ladder: f.ladder, names,
        });
        expect(row?.ladder).not.toBeNull();
        const sel = row?.ladder?.selections ?? [];
        expect(sel.map(s => s.name)).toEqual([P1, P2]);
        expect(sel[0].back[0]).toEqual(f.ladder['9633138'].back[0]);
    });
});

describe('categorie dei mercati tennis', () => {
    it('tipi Betfair -> categoria', () => {
        expect(categoriaTennis('MATCH_ODDS')).toBe('MATCH_ODDS');
        expect(categoriaTennis('SET_BETTING')).toBe('SET_BETTING');
        expect(categoriaTennis('NUMBER_OF_SETS')).toBe('SET_BETTING');
        expect(categoriaTennis('SET_WINNER')).toBe('SET_WINNER');
        expect(categoriaTennis('FIRST_SET_WINNER')).toBe('SET_WINNER');
        expect(categoriaTennis('TOTAL_GAMES')).toBe('GAMES');
        expect(categoriaTennis('GAME_HANDICAP')).toBe('HANDICAP');
        expect(categoriaTennis('SET_HANDICAP')).toBe('HANDICAP');
        expect(categoriaTennis('TIE_BREAK_IN_MATCH')).toBe('TIE_BREAK');
        expect(categoriaTennis(null)).toBe('ALTRI');
        expect(categoriaTennis('QUALCOSA_DI_NUOVO')).toBe('ALTRI');
    });

    it('raggruppa e tiene solo le categorie presenti, in ordine canonico', () => {
        const m = (market_type: string) => ({ market_type });
        const { perCategoria, presenti } = raggruppaMercatiTennis([m('TOTAL_GAMES'), m('MATCH_ODDS'), m('SET_BETTING'), m('GAME_HANDICAP')]);
        expect(presenti.map(c => c.key)).toEqual(['MATCH_ODDS', 'SET_BETTING', 'GAMES', 'HANDICAP']);
        expect(perCategoria.get('GAMES')).toEqual([m('TOTAL_GAMES')]);
        expect(CATEGORIE_TENNIS.map(c => c.key)).toContain('ALTRI');
    });
});

describe('esito dal regolamento Betfair', () => {
    const settledMs = new Date(MO.settled_ts!).getTime();
    const bet = (side: 'back' | 'lay', selectionId: number, odds: number, stake: number): SimBet => ({
        id: `${side}${selectionId}`, marketId: MO.market_id, selectionId, selectionName: '', marketName: 'Match Odds',
        side, odds, stake, minute: null,
    });

    it('vincitore solo dopo la chiusura e solo col runner WINNER', () => {
        expect(vincitoreRegolato(MO, settledMs - 1)).toBeNull();
        expect(vincitoreRegolato(MO, settledMs)).toBe(35635727);
        expect(vincitoreRegolato({ ...MO, settled_ts: null }, settledMs)).toBeNull();
        const senzaWinner: TennisReplayMarket = { ...MO, selections: MO.selections.map(s => ({ ...s, status: 'ACTIVE' })) };
        expect(vincitoreRegolato(senzaWinner, settledMs)).toBeNull();
    });

    it('P&L definitivo a mercato regolato, cash-out prima', () => {
        const bets = [bet('back', 35635727, 6.0, 10)];
        const ladder = DATI.frames[0].ladder;
        const prima = valutaMercatoTennis(bets, ladder, MO, settledMs - 1);
        expect(prima.settled).toBe(false);
        const dopo = valutaMercatoTennis(bets, ladder, MO, settledMs);
        expect(dopo).toEqual({ value: 50, settled: true, winnerId: 35635727 });
        expect(valutaMercatoTennis([], ladder, MO, settledMs)).toEqual({ value: 0, settled: false, winnerId: null });
    });

    it('bet-delay del mercato dal betDelay registrato', () => {
        expect(delayMercatoMs(MO)).toBe(3000);
        expect(delayMercatoMs({ bet_delay: null })).toBe(5000);
        expect(delayMercatoMs(undefined)).toBe(5000);
    });
});

describe('motore opportunita\' sul tennis', () => {
    it('nessuna score_timeline del calcio, mercati e frame del tennis', () => {
        const r = perMotoreOpportunita(DATI);
        expect(r.score_timeline).toEqual([]);
        expect(r.markets).toBe(DATI.markets);
        expect(r.event.home_name).toBe(P1);
    });

    it('fase per set al posto dei minuti del calcio', () => {
        const inizio = ORDINATE[0].ts;
        expect(faseTennis(ORDINATE, '2026-07-07T12:00:00Z', inizio)).toBe('pre');
        expect(faseTennis(ORDINATE, '2026-07-07T12:30:00Z', inizio)).toBe('Set 2');
        expect(faseTennis(ORDINATE, '2026-07-07T13:20:00Z', inizio)).toBe('Set 3');
        const o = { phase: '2T' } as Opportunity;
        expect(conFaseTennis([o], 'Set 3')[0].phase).toBe('Set 3');
    });
});

describe('elenco per torneo e anno', () => {
    it('raggruppa', () => {
        const it = (event_id: string, competition_name: string | null, open_date: string) => ({
            event_id, competition_name, player1_name: 'A', player2_name: 'B', open_date,
            n_markets: 1, n_snapshots: 1, n_score: 0, ts_min: null, ts_max: null, fonte: 'import',
        });
        const g = raggruppaPerTorneo([it('1', 'Wimbledon', '2026-07-07T10:00:00Z'), it('2', null, '2025-01-01T10:00:00Z'),
            it('3', 'Wimbledon', '2025-07-07T10:00:00Z')]);
        expect(g.map(x => x.torneo)).toEqual(['Torneo sconosciuto', 'Wimbledon']);
        expect(g[1].anni.map(a => a.anno)).toEqual([2026, 2025]);
    });
});

describe('dati: RPC del TENNIS (mai quelle del calcio)', () => {
    it('lista e replay a finestre su list_replays_tennis / get_replay_tennis_*', async () => {
        rpc.mockImplementation(async (nome: string) => {
            if (nome === 'list_replays_tennis') return { data: { rows: [{ event_id: '35790089' }] }, error: null };
            if (nome === 'get_replay_tennis_meta') {
                return {
                    data: {
                        event: DATI.event, markets: DATI.markets, score_timeline: DATI.score_timeline,
                        ts_min: DATI.frames[0].ts, ts_max: DATI.frames[3].ts, inplay_from_ts: DATI.frames[0].ts,
                    }, error: null,
                };
            }
            if (nome === 'get_replay_tennis_frames') return { data: { frames: DATI.frames.slice(0, 4) }, error: null };
            return { data: null, error: { message: `rpc inattesa ${nome}` } };
        });
        expect(await fetchTennisReplayList(10)).toEqual([{ event_id: '35790089' }]);
        const d = await fetchTennisReplay('35790089');
        const nomi = rpc.mock.calls.map(c => c[0]);
        expect(new Set(nomi)).toEqual(new Set(['list_replays_tennis', 'get_replay_tennis_meta', 'get_replay_tennis_frames']));
        expect(d.frames).toHaveLength(4);
        // GBP storiche -> EUR alla fonte, come il calcio
        const g = DATI.frames[0].ladder['9633138'].back[0][1];
        expect(d.frames[0].ladder['9633138'].back[0][1]).toBeCloseTo(g * 1.164687, 6);
    });

    it('migrazione non applicata: messaggio chiaro', async () => {
        rpc.mockResolvedValue({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.list_replays_tennis' } });
        await expect(fetchTennisReplayList()).rejects.toThrow(MSG_MIGRAZIONE);
    });
});
