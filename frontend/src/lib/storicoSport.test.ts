// ============================================================================
// storicoSport.test.ts — LO STORICO PER SPORT, la parte money-critical.
//
// Le righe finte di questo file hanno le IDENTICHE CHIAVI delle righe vere:
// sono copiate da una sonda IN SOLA LETTURA sul database del 17/09/2026
//   POST /rest/v1/rpc/get_safe_daily {p_from, p_to, p_sport:'tennis', p_mode:'live'}
//   → chiavi: avg_loss, avg_win, best_trade, by_origin, by_sport, by_strategy,
//     commission_paid, day, first_trade_at, goal, goal_pct, gross_loss,
//     gross_profit, hedged_closed, last_trade_at, lost, max_liability,
//     pnl_realized, profit_factor, settled, trades_placed, void, win_rate, won,
//     worst_trade
// (il 15/09 i finti scritti in camelCase hanno certificato un bug e sono usciti
// 32 ordini veri in loop: un finto che non parla come il vero non certifica.)
//
// IL TEST CHE CONTA DAVVERO è quello della FALSIFICAZIONE: la somma di paper e
// live deve dare un numero DIVERSO da entrambi i totali. Se non lo desse, i
// test qui sotto non saprebbero riconoscere il difetto che esistono per
// impedire.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    intervalloRange, aggregaBot, totaleModo, unisciGiornate, curvaCumulata,
    barrePerGiorno, FONTI_STORICO, FONTI_ASSENTI, rottaStorico, INTERVALLO_LABEL,
    rigaGiornalieraTennisBot,
    type SerieBot, type ModoStorico, type BotStorico,
} from './storicoSport';
import { normalizeDailyRow, periodRange, PERIOD_LABEL, coperturaTutto, type DailyRow } from './dailyHistory';
import { posizioniChiuse, riepilogoChiuse, rigaDaOrdineTennis, nettoOrdineTennis, type TradeChiudibile } from './posizioniChiuse';
import type { TennisBotDailyRow, TennisBotOrderRow } from './tennis';

// --------------------------------------------------------------- finti

/** Una riga giornaliera COME ARRIVA DALLA RPC (chiavi e tipi del vero). */
function rigaRpc(day: string, pnl: number, over: Record<string, unknown> = {}): Record<string, unknown> {
    const won = pnl > 0 ? 1 : 0;
    const lost = pnl < 0 ? 1 : 0;
    return {
        day,
        won,
        goal: null,
        lost,
        void: 0,
        avg_win: pnl > 0 ? pnl : null,
        settled: won + lost,
        avg_loss: pnl < 0 ? pnl : null,
        by_sport: { tennis: { n: 1, pnl, won, lost } },
        goal_pct: null,
        win_rate: won + lost > 0 ? won / (won + lost) : null,
        by_origin: { auto: { n: 1, pnl, won, lost } },
        best_trade: pnl,
        gross_loss: pnl < 0 ? -pnl : 0,
        by_strategy: { tennis: { n: 1, pnl, won, lost } },
        worst_trade: pnl,
        gross_profit: pnl > 0 ? pnl : 0,
        pnl_realized: pnl,
        hedged_closed: 0,
        last_trade_at: `${day}T15:20:48.075077+00:00`,
        max_liability: 3.0,
        profit_factor: null,
        trades_placed: 1,
        first_trade_at: `${day}T13:42:39.40554+00:00`,
        commission_paid: 0.02,
        ...over,
    };
}

function riga(day: string, pnl: number, over: Record<string, unknown> = {}): DailyRow {
    const r = normalizeDailyRow(rigaRpc(day, pnl, over));
    if (!r) throw new Error('finto non normalizzabile: le chiavi non parlano come il vero');
    return r;
}

function serie(
    bot: BotStorico, modo: ModoStorico, righe: DailyRow[],
    over: Partial<SerieBot> = {},
): SerieBot {
    return {
        bot, etichetta: bot, accento: 'text-primary', modo, righe,
        modoAttendibile: true, stakePerGiorno: null, errore: null, ...over,
    };
}

// ----------------------------------------------------------- intervalli

describe('intervalli: oggi, 7 giorni, 30 giorni, mese, tutto', () => {
    it('oggi è un giorno solo', () => {
        expect(intervalloRange('oggi', '2026-09-17')).toEqual({ from: '2026-09-17', to: '2026-09-17' });
    });
    it('7 giorni include oggi (6 indietro, non 7)', () => {
        expect(intervalloRange('7g', '2026-09-17')).toEqual({ from: '2026-09-11', to: '2026-09-17' });
    });
    it('30 giorni include oggi', () => {
        expect(intervalloRange('30g', '2026-09-17')).toEqual({ from: '2026-08-19', to: '2026-09-17' });
    });
    it('mese parte dal primo del mese in corso', () => {
        expect(intervalloRange('mese', '2026-09-17')).toEqual({ from: '2026-09-01', to: '2026-09-17' });
    });
    it('«tutto» resta dentro il tetto del motore condiviso (400 giorni)', () => {
        const r = intervalloRange('tutto', '2026-09-17');
        expect(r.to).toBe('2026-09-17');
        const giorni = (Date.parse(`${r.to}T00:00:00Z`) - Date.parse(`${r.from}T00:00:00Z`)) / 86_400_000;
        expect(giorni).toBe(399);   // 400 giornate, estremi inclusi
    });
    it('un giorno non valido non passa in silenzio', () => {
        expect(() => intervalloRange('7g', '17/09/2026')).toThrow();
    });
    it('ogni intervallo ha un\'etichetta in italiano', () => {
        for (const k of ['oggi', '7g', '30g', '90g', 'mese', 'tutto'] as const) {
            expect(INTERVALLO_LABEL[k]).toBeTruthy();
        }
    });
    // B-14 rivisto (rilievi bassi 01/10): l'etichetta «Ultimi 400 giorni» e'
    // diventata «Tutto», UGUALE agli storici dei bot; quanti giorni copre
    // davvero lo dice la riga sotto i filtri (`coperturaTutto`), non l'etichetta.
    it('B-14: STESSE etichette e STESSI intervalli degli storici dei bot', () => {
        expect(INTERVALLO_LABEL['7g']).toBe(PERIOD_LABEL['7d']);
        expect(INTERVALLO_LABEL['30g']).toBe(PERIOD_LABEL['30d']);
        expect(INTERVALLO_LABEL['90g']).toBe(PERIOD_LABEL['90d']);
        expect(INTERVALLO_LABEL.mese).toBe(PERIOD_LABEL.month);
        expect(INTERVALLO_LABEL.tutto).toBe('Tutto');
        expect(INTERVALLO_LABEL.tutto).toBe(PERIOD_LABEL.all);
        const oggi = '2026-10-01';
        expect(intervalloRange('7g', oggi)).toEqual(periodRange('7d', oggi));
        expect(intervalloRange('90g', oggi)).toEqual({ from: '2026-07-04', to: oggi });
        expect(intervalloRange('90g', oggi)).toEqual(periodRange('90d', oggi));
        expect(intervalloRange('tutto', oggi)).toEqual(periodRange('all', oggi));
    });
    it('B-14: «Tutto» dice quanti giorni copre davvero, e la finestra ridotta dal database', () => {
        const r = periodRange('all', '2026-10-01');
        const righe = [normalizeDailyRow(rigaRpc('2026-09-20', 1)), normalizeDailyRow(rigaRpc('2026-09-30', -1))]
            .filter((x): x is DailyRow => x != null);
        const t = coperturaTutto(righe, r);
        expect(t).toContain('al massimo gli ultimi 400 giorni');
        expect(t).toContain('primo giorno con operazioni: 20 settembre 2026, quindi 12 giorni coperti');
        expect(t).not.toContain('ridotto');
        const ridotte = [normalizeDailyRow(rigaRpc('2026-09-20', 1, { window_clamped: true, window_from: '2025-08-27' }))]
            .filter((x): x is DailyRow => x != null);
        expect(ridotte[0].window_clamped).toBe(true);
        expect(coperturaTutto(ridotte, r)).toContain('il database ha ridotto la finestra (dal 27 agosto 2025)');
        expect(coperturaTutto([], r)).toContain('nessun giorno con operazioni');
    });
});

// ------------------------------------------------------------ aggregati

describe('aggregato di un bot', () => {
    it('somma P&L, operazioni ed esiti delle sue giornate', () => {
        const a = aggregaBot(serie('safe', 'live', [
            riga('2026-09-14', 0.44),
            riga('2026-09-15', -0.20),
            riga('2026-09-16', 1.10),
        ]));
        expect(a.pnl).toBe(1.34);
        expect(a.giorni).toBe(3);
        expect(a.operazioni).toBe(3);
        expect(a.regolate).toBe(3);
        expect(a.vinte).toBe(2);
        expect(a.perse).toBe(1);
        expect(a.winRate).toBeCloseTo(2 / 3, 4);
    });

    it('senza importo piazzato il ROI è ASSENTE, non zero', () => {
        const a = aggregaBot(serie('safe', 'live', [riga('2026-09-14', 1)]));
        expect(a.stake).toBeNull();
        expect(a.roi).toBeNull();          // «non lo so», non «0 %»
    });

    it('con l\'importo piazzato il ROI è P&L / stake, sui soli giorni mostrati', () => {
        const a = aggregaBot(serie('safe', 'live', [riga('2026-09-14', 2), riga('2026-09-15', -1)], {
            // il 13/09 NON è fra le righe: non deve entrare nel denominatore
            stakePerGiorno: { '2026-09-13': 100, '2026-09-14': 6, '2026-09-15': 4 },
        }));
        expect(a.stake).toBe(10);
        expect(a.roi).toBeCloseTo(0.1, 6);
    });

    it('un bot SENZA giornate ha importo piazzato zero, non quello di un altro', () => {
        // il difetto trovato dal test di pagina il 17/09: con la scorciatoia
        // «se non ho giornate sommo tutto», un bot vuoto portava dentro
        // l'importo di un altro e il ROI del totale dimezzava.
        const vuoto = aggregaBot(serie('mike', 'live', [], {
            stakePerGiorno: { '2026-09-16': 35 },
        }));
        expect(vuoto.stake).toBe(0);
        expect(vuoto.roi).toBeNull();

        const pieno = aggregaBot(serie('safe', 'live', [riga('2026-09-16', 3.5)], {
            stakePerGiorno: { '2026-09-16': 35 },
        }));
        const t = totaleModo([pieno, vuoto], 'live');
        expect(t.stake).toBe(35);
        expect(t.roi).toBeCloseTo(0.1, 6);
    });

    it('C-01/D-01 (01/10): un bot CON giornate e senza importo rende il ROI del totale non calcolabile', () => {
        const safe = aggregaBot(serie('safe', 'live', [riga('2026-09-16', 3.5)], { stakePerGiorno: { '2026-09-16': 35 } }));
        const swing = aggregaBot(serie('tennis_swing', 'live', [riga('2026-09-16', 1)]));
        const t = totaleModo([safe, swing], 'live');
        expect(t.pnl).toBe(4.5);
        // prima: 4,5 / 35 = 12,9 % (P&L di due bot diviso l'importo di uno)
        expect(t.stake).toBeNull();
        expect(t.roi).toBeNull();
    });

    it('stake a zero non produce un ROI infinito', () => {
        const a = aggregaBot(serie('safe', 'live', [riga('2026-09-14', 2)], {
            stakePerGiorno: { '2026-09-14': 0 },
        }));
        expect(a.stake).toBe(0);
        expect(a.roi).toBeNull();
    });
});

// ------------------------------------- 01/10: i 4 bot tennis nello Storico

describe('D-01 - bot tennis: stesso netto dello Storico e delle Posizioni chiuse', () => {
    /** riga di `get_tennis_bot_daily` (12 chiavi della RPC del 30/09) */
    const daily = (over: Partial<TennisBotDailyRow> = {}): TennisBotDailyRow => ({
        giorno: '2026-09-30', bot_key: 'tennis_swing', ordini: 3, vinti: 2, persi: 1,
        pnl_lordo: 1.9, commissione: 0.08, pnl_netto: 1.78, volume: 6,
        pnl_reale: 0.95, pnl_stimato: 0.83, stimati: 2, ...over,
    });
    /** ordine di `tennis_live_orders` (chiavi della tabella vera) */
    const ordine = (id: number, over: Record<string, unknown>) => ({
        id, bet_id: `T${id}`, client_order_ref: `awtq${id}`, request_id: id, mode: 'live',
        source: 'tennis_swing', event_id: 'T1', market_id: `1.${id}`, selection_id: 77, handicap: 0,
        side: 'back', order_type: 'LIMIT', price: 2, size: 2, size_matched: 2, size_remaining: 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 2,
        status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: '2026-09-30T09:00:00+00:00',
        matched_at: null, updated_at: '2026-09-30T11:00:00+00:00', pnl: 0, commission: 0,
        settled_at: '2026-09-30T11:00:00+00:00', pnl_betfair: null, pnl_betfair_settled_at: null,
        ...over,
    }) as unknown as TennisBotOrderRow;

    it('una giornata del bot diventa una riga del motore: ordini, esiti, netto', () => {
        const r = rigaGiornalieraTennisBot(daily())!;
        expect(r).toMatchObject({ day: '2026-09-30', pnl_realized: 1.78, trades_placed: 3, settled: 3, won: 2, lost: 1, void: 0 });
        expect(rigaGiornalieraTennisBot(daily({ pnl_netto: null }))).toBeNull();   // nessuna regolata: nessuna riga, mai 0
    });

    it('reale e stima separati dalla fonte, sommati per periodo', () => {
        const a = aggregaBot(serie('tennis_swing', 'live', [rigaGiornalieraTennisBot(daily())!], {
            fontePerGiorno: { '2026-09-30': { reale: 0.95, stimato: 0.83, stimati: 2 } },
        }));
        expect(a).toMatchObject({ pnl: 1.78, reale: 0.95, stimato: 0.83, stimati: 2 });
        const t = totaleModo([a], 'live');
        expect([t.reale, t.stimato]).toEqual([0.95, 0.83]);
    });

    it('stessi ordini: totale dello Storico == totale delle Posizioni chiuse (stessa definizione di netto)', () => {
        const ordini = [
            ordine(1, { pnl: 1.0, commission: 0.05, pnl_betfair: 0.95 }),     // regolato da Betfair
            ordine(2, { pnl: 0.9, commission: 0.03 }),                         // stimato: 0,87
            ordine(3, { pnl: -0.04, commission: 0 }),                          // stimato: -0,04
        ];
        // la RPC somma coalesce(pnl_betfair, pnl - commission): 0,95 + 0,87 - 0,04
        const nettoRpc = Math.round(ordini.reduce((s, o) => s + (nettoOrdineTennis(o) ?? 0), 0) * 100) / 100;
        const storico = totaleModo([aggregaBot(serie('tennis_swing', 'live',
            [rigaGiornalieraTennisBot(daily({ pnl_netto: nettoRpc }))!]))], 'live');
        const chiuse = riepilogoChiuse(posizioniChiuse(
            ordini.map((o) => rigaDaOrdineTennis(o, 'Sinner v Alcaraz', () => true) as TradeChiudibile)));
        expect(storico.pnl).toBe(1.78);
        expect(chiuse.totale).toBe(storico.pnl);
    });
});

// ---------------------------------------------- paper e live non si sommano

describe('PAPER E LIVE NON SI SOMMANO MAI', () => {
    const live = aggregaBot(serie('safe', 'live', [riga('2026-09-14', 0.41)]));
    const paper = aggregaBot(serie('safe', 'paper', [riga('2026-09-14', -0.16)]));

    it('il totale live somma solo il live', () => {
        expect(totaleModo([live], 'live').pnl).toBe(0.41);
    });

    it('il totale paper somma solo il paper', () => {
        expect(totaleModo([paper], 'paper').pnl).toBe(-0.16);
    });

    it('mescolare le due modalità LANCIA, non produce un numero', () => {
        expect(() => totaleModo([live, paper], 'live')).toThrow(/non si sommano/);
        expect(() => totaleModo([live, paper], 'paper')).toThrow(/non si sommano/);
    });

    // ⚠️ FALSIFICAZIONE — se la somma sbagliata desse lo stesso numero di quella
    // giusta, i tre test qui sopra non saprebbero riconoscere il difetto.
    // Questo è il caso VERO del 14/09: la card del tennis mostrava +0,25 €, che
    // non esisteva da nessuna parte — era +0,41 di live meno 0,16 di paper.
    it('falsificazione: la somma delle due modalità è un numero che non esiste', () => {
        const sommaSbagliata = Math.round((live.pnl + paper.pnl) * 100) / 100;
        expect(sommaSbagliata).toBe(0.25);
        expect(sommaSbagliata).not.toBe(totaleModo([live], 'live').pnl);
        expect(sommaSbagliata).not.toBe(totaleModo([paper], 'paper').pnl);
    });

    it('un bot che non sa separare la modalità resta FUORI dal totale', () => {
        const omegaMisto = aggregaBot(
            serie('omega', 'live', [riga('2026-09-14', 99)], { modoAttendibile: false }),
        );
        const t = totaleModo([live, omegaMisto], 'live');
        expect(t.pnl).toBe(0.41);          // i 99 € misti NON entrano
        expect(t.bot).toBe(1);
    });

    it('il ROI del totale nasce dalle somme, mai da una media di ROI', () => {
        const a = aggregaBot(serie('safe', 'live', [riga('2026-09-14', 2)], { stakePerGiorno: { '2026-09-14': 10 } }));
        const b = aggregaBot(serie('mike', 'live', [riga('2026-09-14', 2)], { stakePerGiorno: { '2026-09-14': 90 } }));
        const t = totaleModo([a, b], 'live');
        expect(t.stake).toBe(100);
        expect(t.roi).toBeCloseTo(0.04, 6);             // 4 / 100
        const mediaDiRoi = ((a.roi ?? 0) + (b.roi ?? 0)) / 2;
        expect(Math.round(mediaDiRoi * 10000) / 10000).not.toBe(t.roi);  // falsificazione
    });
});

// --------------------------------------------------------------- serie

describe('unione delle giornate di più bot', () => {
    it('somma per giorno e tiene i giorni distinti', () => {
        const u = unisciGiornate([
            [riga('2026-09-14', 1), riga('2026-09-15', 2)],
            [riga('2026-09-14', 0.5)],
        ]);
        expect(u.map((r) => r.day)).toEqual(['2026-09-14', '2026-09-15']);
        expect(u[0].pnl_realized).toBe(1.5);
        expect(u[0].trades_placed).toBe(2);
        expect(u[1].pnl_realized).toBe(2);
    });

    it('i campi non sommabili non vengono ereditati dal primo bot', () => {
        const u = unisciGiornate([
            [riga('2026-09-14', 1, { avg_win: 1, profit_factor: 3, goal: 100, goal_snapshot: true })],
            [riga('2026-09-14', 2)],
        ]);
        expect(u[0].avg_win).toBeNull();
        expect(u[0].profit_factor).toBeNull();
        expect(u[0].goal).toBeNull();
        expect(u[0].goal_snapshot).toBe(false);   // nessun giudizio «centrato» su un totale
    });

    it('il win rate del giorno si ricalcola dalle somme', () => {
        const u = unisciGiornate([
            [riga('2026-09-14', 1)],           // 1 vinta
            [riga('2026-09-14', -1)],          // 1 persa
            [riga('2026-09-14', 3)],           // 1 vinta
        ]);
        expect(u[0].won).toBe(2);
        expect(u[0].lost).toBe(1);
        expect(u[0].win_rate).toBeCloseTo(2 / 3, 4);
    });
});

describe('curva cumulata', () => {
    it('è la somma PROGRESSIVA del P&L per giornata', () => {
        const c = curvaCumulata([riga('2026-09-14', 1), riga('2026-09-15', -0.5), riga('2026-09-16', 2)]);
        expect(c.map((p) => p.v)).toEqual([1, 0.5, 2.5]);
        expect(c.map((p) => p.iso)).toEqual(['2026-09-14', '2026-09-15', '2026-09-16']);
    });

    it('ordina per giorno anche se le righe arrivano al contrario', () => {
        const c = curvaCumulata([riga('2026-09-16', 2), riga('2026-09-14', 1)]);
        expect(c.map((p) => p.iso)).toEqual(['2026-09-14', '2026-09-16']);
        expect(c.map((p) => p.v)).toEqual([1, 3]);
    });

    it('falsificazione: la somma NON progressiva dà un\'altra curva', () => {
        const righe = [riga('2026-09-14', 1), riga('2026-09-15', -0.5), riga('2026-09-16', 2)];
        const c = curvaCumulata(righe);
        const nonCumulata = righe.map((r) => r.pnl_realized);
        expect(nonCumulata).toEqual([1, -0.5, 2]);
        expect(c.map((p) => p.v)).not.toEqual(nonCumulata);
    });
});

describe('barre per giornata', () => {
    it('una barra per giorno, con il contributo di ciascun bot', () => {
        const b = barrePerGiorno([
            { etichetta: 'Omega', righe: [riga('2026-09-14', 1), riga('2026-09-15', -2)] },
            { etichetta: 'Mike', righe: [riga('2026-09-14', 0.5)] },
        ]);
        expect(b.map((x) => x.day)).toEqual(['2026-09-14', '2026-09-15']);
        expect(b[0].pnl).toBe(1.5);
        expect(b[0].perBot).toEqual({ Omega: 1, Mike: 0.5 });
        expect(b[1].perBot).toEqual({ Omega: -2 });
    });

    it('un giorno senza operazioni NON diventa una barra a zero', () => {
        const b = barrePerGiorno([{ etichetta: 'Omega', righe: [riga('2026-09-14', 1), riga('2026-09-17', 1)] }]);
        expect(b.map((x) => x.day)).toEqual(['2026-09-14', '2026-09-17']);   // il 15 e il 16 non ci sono
    });
});

// ------------------------------------------------------------- le fonti

describe('chi entra nello storico di uno sport, e chi no', () => {
    it('il calcio ha Omega, Safe e Mike', () => {
        expect(FONTI_STORICO.calcio.map((f) => f.bot)).toEqual(['omega', 'safe', 'mike']);
    });

    it('D-01 (01/10): il tennis ha Safe E i quattro bot tennis (P&L a database dal 17/09); nessun assente', () => {
        expect(FONTI_STORICO.tennis.map((f) => f.bot)).toEqual([
            'safe', 'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing',
        ]);
        expect(FONTI_ASSENTI.tennis).toEqual([]);
    });

    it('lo scalper del calcio è dichiarato assente, non mostrato a zero, col motivo VERO (C-06)', () => {
        expect(FONTI_ASSENTI.calcio.map((f) => f.id)).toEqual(['scalper']);
        const perche = FONTI_ASSENTI.calcio[0].perche;
        expect(perche).toMatch(/P&L reale/);
        // niente nomi di tabelle davanti al trader
        expect(perche).not.toMatch(/`|scalper_activity|tennis_live_orders/);
    });

    it('la RPC di Safe riceve lo sport, quelle di Omega e Mike no', () => {
        expect(FONTI_STORICO.tennis[0].sportRpc).toBe('tennis');
        expect(FONTI_STORICO.calcio.find((f) => f.bot === 'safe')?.sportRpc).toBe('calcio');
        expect(FONTI_STORICO.calcio.find((f) => f.bot === 'omega')?.sportRpc).toBeNull();
    });

    it('le rotte sono quelle del router', () => {
        expect(rottaStorico('calcio')).toBe('/storico/calcio');
        expect(rottaStorico('tennis')).toBe('/storico/tennis');
    });
});
