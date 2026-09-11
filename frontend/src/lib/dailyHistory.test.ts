// Test delle ANALITICHE PURE dello storico per giornata (money-critical):
// normalizzazione righe, equity/drawdown/serie, riepiloghi, calendario,
// periodi, lettura delle uscite automatiche. Nessuna rete.
import { describe, it, expect } from 'vitest';
import {
    normalizeDailyRow, normalizeDailyRows, normalizeDayTrades,
    equityByDay, drawdown, streaks, profitFactor, expectancy, goalHitRate,
    monthSummary, summarizeRows, aggregateBreakdown, calendarGrid, shiftMonth,
    dayToMs, msToDay, addDays, isValidDay, romeDay, periodRange, filterRange,
    dayLabel, monthLabel, exitInfo, tradeExit,
    clampHistoryRange, attributionOf, summarizeDayTrades,
    type DailyRow,
} from './dailyHistory';

function row(day: string, pnl: number, over: Partial<DailyRow> = {}): DailyRow {
    const won = over.won ?? (pnl > 0 ? 1 : 0);
    const lost = over.lost ?? (pnl < 0 ? 1 : 0);
    return {
        day, pnl_realized: pnl, trades_placed: 1, settled: won + lost, won, lost, void: 0,
        hedged_closed: 0, win_rate: won + lost ? won / (won + lost) : null,
        avg_win: pnl > 0 ? pnl : null, avg_loss: pnl < 0 ? pnl : null,
        best_trade: pnl, worst_trade: pnl, max_liability: 10,
        gross_profit: pnl > 0 ? pnl : 0, gross_loss: pnl < 0 ? -pnl : 0,
        profit_factor: null, commission_paid: null, goal: null, goal_pct: null, goal_snapshot: true,
        by_strategy: {}, by_sport: {}, by_origin: {}, first_trade_at: null, last_trade_at: null,
        ...over,
    };
}

// ------------------------------------------------------------ normalizzazione
describe('normalizeDailyRow', () => {
    it('numeri come stringhe (numeric del DB) → number; breakdown sempre oggetti', () => {
        const r = normalizeDailyRow({
            day: '2026-09-10', pnl_realized: '12.5', trades_placed: '3', won: 2, lost: '1',
            gross_loss: '-4', profit_factor: '2.5', goal: '250', commission_paid: null,
            by_strategy: { base: { n: '2', pnl: '10', won: 1, lost: 0 } },
        });
        expect(r).not.toBeNull();
        expect(r!.pnl_realized).toBe(12.5);
        expect(r!.trades_placed).toBe(3);
        expect(r!.lost).toBe(1);
        expect(r!.gross_loss).toBe(4);           // sempre valore assoluto
        expect(r!.profit_factor).toBe(2.5);
        expect(r!.goal).toBe(250);
        expect(r!.commission_paid).toBeNull();
        expect(r!.by_strategy.base).toEqual({ n: 2, pnl: 10, won: 1, lost: 0 });
        expect(r!.by_sport).toEqual({});
        expect(r!.void).toBe(0);
    });
    it('riga senza giorno valido → null; lista ordinata per giorno', () => {
        expect(normalizeDailyRow({ pnl_realized: 1 })).toBeNull();
        expect(normalizeDailyRow({ day: 'oggi' })).toBeNull();
        const rows = normalizeDailyRows([{ day: '2026-09-10' }, { day: 'x' }, { day: '2026-09-01' }]);
        expect(rows.map((r) => r.day)).toEqual(['2026-09-01', '2026-09-10']);
        expect(normalizeDailyRows(null)).toEqual([]);
    });
    it('normalizeDayTrades: chiusure annidate e total_pnl', () => {
        const t = normalizeDayTrades([{
            id: '5', event_id: 'e', pnl: '3.2', price: '40', size: '2', status: 'won',
            placed_at: 'x', settled_at: null, meta: 'no', closes: [{ id: 6, pnl: '-1', meta: { locked_pnl: 2.2 } }],
            total_pnl: '2.2', placed_in_day: true,
        }]);
        expect(t).toHaveLength(1);
        expect(t[0].id).toBe(5);
        expect(t[0].pnl).toBe(3.2);
        expect(t[0].meta).toBeNull();
        expect(t[0].closes[0].pnl).toBe(-1);
        expect(t[0].total_pnl).toBe(2.2);
        expect(t[0].settled_in_day).toBe(false);
        expect(normalizeDayTrades(undefined)).toEqual([]);
    });
});

// ------------------------------------------------------------------- giorni
describe('giorni come stringhe', () => {
    it('dayToMs/msToDay/addDays sono inverse e attraversano mese e anno', () => {
        expect(msToDay(dayToMs('2026-09-10'))).toBe('2026-09-10');
        expect(addDays('2026-09-30', 1)).toBe('2026-10-01');
        expect(addDays('2027-01-01', -1)).toBe('2026-12-31');
        expect(addDays('2024-02-28', 1)).toBe('2024-02-29');   // bisestile
    });
    it('isValidDay rifiuta formati e date inesistenti', () => {
        expect(isValidDay('2026-09-10')).toBe(true);
        expect(isValidDay('2026-02-30')).toBe(false);
        expect(isValidDay('10/09/2026')).toBe(false);
    });
    it('romeDay: la giornata operativa segue Europe/Rome, non UTC', () => {
        // 23:30 UTC del 9/9 = 01:30 del 10/9 a Roma (CEST)
        expect(romeDay(new Date('2026-09-09T23:30:00Z'))).toBe('2026-09-10');
        // 22:59 UTC dell'8/9 = 00:59 del 9/9 a Roma
        expect(romeDay(new Date('2026-09-08T22:59:00Z'))).toBe('2026-09-09');
        // inverno (CET, +1): 23:30 UTC del 10/1 = 00:30 dell'11/1
        expect(romeDay(new Date('2026-01-10T23:30:00Z'))).toBe('2026-01-11');
    });
    it('etichette italiane senza fuso del browser', () => {
        expect(dayLabel('2026-09-10')).toMatch(/10 settembre 2026/);
        expect(dayLabel('2026-09-10', { weekday: true, year: false })).toMatch(/giovedì 10 settembre/);
        expect(monthLabel(2026, 9)).toMatch(/settembre 2026/);
    });
});

describe('periodRange / filterRange', () => {
    it('mese corrente, 30/90 giorni, anno (inclusivi)', () => {
        expect(periodRange('month', '2026-09-10')).toEqual({ from: '2026-09-01', to: '2026-09-10' });
        expect(periodRange('30d', '2026-09-10')).toEqual({ from: '2026-08-12', to: '2026-09-10' });
        expect(periodRange('90d', '2026-09-10')).toEqual({ from: '2026-06-13', to: '2026-09-10' });
        expect(periodRange('year', '2026-09-10')).toEqual({ from: '2026-01-01', to: '2026-09-10' });
        expect(() => periodRange('month', 'boh')).toThrow(RangeError);
    });
    it('filterRange tiene solo i giorni dentro [from, to]', () => {
        const rows = [row('2026-08-31', 1), row('2026-09-01', 2), row('2026-09-10', 3), row('2026-09-11', 4)];
        expect(filterRange(rows, '2026-09-01', '2026-09-10').map((r) => r.day)).toEqual(['2026-09-01', '2026-09-10']);
    });
});

// --------------------------------------------------------------- analitiche
describe('equityByDay', () => {
    it('vuoto → []; un giorno → un punto; cumulato ordinato per giorno', () => {
        expect(equityByDay([])).toEqual([]);
        expect(equityByDay([row('2026-09-10', 5)])).toEqual([{ t: dayToMs('2026-09-10'), v: 5, iso: '2026-09-10' }]);
        const pts = equityByDay([row('2026-09-03', -2), row('2026-09-01', 10), row('2026-09-02', 0.1)]);
        expect(pts.map((p) => p.iso)).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
        expect(pts.map((p) => p.v)).toEqual([10, 10.1, 8.1]);
    });
});

describe('drawdown', () => {
    it('senza dati: tutto a zero', () => {
        expect(drawdown([])).toEqual({ maxDrawdown: 0, currentDrawdown: 0, peak: 0, peakDay: null, troughDay: null });
    });
    it('solo giornate positive: nessun drawdown', () => {
        const d = drawdown([row('2026-09-01', 10), row('2026-09-02', 5)]);
        expect(d.maxDrawdown).toBe(0);
        expect(d.currentDrawdown).toBe(0);
        expect(d.peak).toBe(15);
        expect(d.peakDay).toBe('2026-09-02');
    });
    it('picco, discesa, recupero parziale: max DD dal picco, DD corrente dal picco', () => {
        // 10 → 30 → 12 → 20 : picco 30, fondo 12 (DD 18), corrente 10
        const d = drawdown([row('2026-09-01', 10), row('2026-09-02', 20), row('2026-09-03', -18), row('2026-09-04', 8)]);
        expect(d.maxDrawdown).toBe(18);
        expect(d.troughDay).toBe('2026-09-03');
        expect(d.currentDrawdown).toBe(10);
        expect(d.peak).toBe(30);
        expect(d.peakDay).toBe('2026-09-02');
    });
    it('prima giornata negativa: il picco resta 0 (si parte da zero)', () => {
        const d = drawdown([row('2026-09-01', -7)]);
        expect(d.peak).toBe(0);
        expect(d.maxDrawdown).toBe(7);
        expect(d.currentDrawdown).toBe(7);
    });
});

describe('streaks', () => {
    it('vuoto e singolo giorno', () => {
        expect(streaks([])).toEqual({ bestWin: 0, bestLoss: 0, current: 0 });
        expect(streaks([row('2026-09-01', 3)])).toEqual({ bestWin: 1, bestLoss: 0, current: 1 });
        expect(streaks([row('2026-09-01', -3)])).toEqual({ bestWin: 0, bestLoss: 1, current: -1 });
    });
    it('serie miste, ordinate per giorno; lo zero interrompe', () => {
        const s = streaks([
            row('2026-09-05', -1), row('2026-09-01', 1), row('2026-09-02', 2), row('2026-09-03', 3),
            row('2026-09-04', 0), row('2026-09-06', -1), row('2026-09-07', -1),
        ]);
        expect(s.bestWin).toBe(3);
        expect(s.bestLoss).toBe(3);
        expect(s.current).toBe(-3);
    });
});

describe('profitFactor / expectancy', () => {
    it('null senza perdite o senza regolati', () => {
        expect(profitFactor([])).toBeNull();
        expect(profitFactor([row('2026-09-01', 10)])).toBeNull();
        expect(expectancy([])).toBeNull();
        expect(expectancy([row('2026-09-01', 0, { settled: 0, won: 0, lost: 0 })])).toBeNull();
    });
    it('somma gross su più giornate; expectancy per apertura regolata', () => {
        const rows = [row('2026-09-01', 10), row('2026-09-02', -4), row('2026-09-03', 6, { settled: 3, won: 2, lost: 1 })];
        expect(profitFactor(rows)).toBe(4);           // (10+6)/4
        expect(expectancy(rows)).toBe(2.4);           // 12 / (1+1+3)
    });
});

describe('goalHitRate', () => {
    it('conta solo le giornate con obiettivo > 0; centrato se pnl ≥ goal', () => {
        expect(goalHitRate([])).toEqual({ total: 0, hit: 0, rate: null, notHistorized: 0 });
        const rows = [
            row('2026-09-01', 250, { goal: 250 }),
            row('2026-09-02', 100, { goal: 250 }),
            row('2026-09-03', 300, { goal: 0 }),
            row('2026-09-04', 5, { goal: null }),
        ];
        expect(goalHitRate(rows)).toEqual({ total: 2, hit: 1, rate: 0.5, notHistorized: 0 });
    });
});

describe('monthSummary', () => {
    it('mese vuoto → zeri e null', () => {
        const m = monthSummary([], 2026, 9);
        expect(m).toMatchObject({ pnl: 0, days: 0, positiveDays: 0, negativeDays: 0, winRate: null, bestDay: null, worstDay: null });
    });
    it('mese negativo: pnl < 0, giorni pos/neg, best/worst, solo righe del mese', () => {
        const rows = [
            row('2026-08-31', 100), row('2026-09-01', 5), row('2026-09-02', -20, { goal: 10 }),
            row('2026-09-03', -1.5), row('2026-10-01', 50),
        ];
        const m = monthSummary(rows, 2026, 9);
        expect(m.pnl).toBe(-16.5);
        expect(m.days).toBe(3);
        expect(m.positiveDays).toBe(1);
        expect(m.negativeDays).toBe(2);
        expect(m.bestDay?.day).toBe('2026-09-01');
        expect(m.worstDay?.day).toBe('2026-09-02');
        expect(m.won).toBe(1);
        expect(m.lost).toBe(2);
        expect(m.winRate).toBeCloseTo(0.3333, 3);
        expect(m.goalHit).toEqual({ total: 1, hit: 0, rate: 0, notHistorized: 0 });
    });
    it('mese fuori range → RangeError', () => {
        expect(() => monthSummary([], 2026, 0)).toThrow(RangeError);
        expect(() => monthSummary([], 2026, 13)).toThrow(RangeError);
        expect(() => monthSummary([], 2026, -3)).toThrow(RangeError);
    });
});

describe('summarizeRows', () => {
    it('vuoto → KPI neutri', () => {
        const s = summarizeRows([]);
        expect(s.pnl).toBe(0);
        expect(s.days).toBe(0);
        expect(s.winRate).toBeNull();
        expect(s.profitFactor).toBeNull();
        expect(s.expectancy).toBeNull();
        expect(s.commission).toBeNull();
        expect(s.maxLiability).toBeNull();
        expect(s.from).toBeNull();
        expect(s.streaks.current).toBe(0);
    });
    it('aggrega tutto: pnl, giorni, esiti, commissione, liability max, from/to', () => {
        const rows = [
            row('2026-09-02', -4, { commission_paid: null, max_liability: 80, hedged_closed: 1 }),
            row('2026-09-01', 10, { commission_paid: 0.53, max_liability: 20, void: 1 }),
        ];
        const s = summarizeRows(rows);
        expect(s.pnl).toBe(6);
        expect(s.days).toBe(2);
        expect(s.positiveDays).toBe(1);
        expect(s.negativeDays).toBe(1);
        expect(s.won).toBe(1);
        expect(s.lost).toBe(1);
        expect(s.void).toBe(1);
        expect(s.hedgedClosed).toBe(1);
        expect(s.winRate).toBe(0.5);
        expect(s.profitFactor).toBe(2.5);
        expect(s.expectancy).toBe(3);
        expect(s.commission).toBe(0.53);
        expect(s.maxLiability).toBe(80);
        expect(s.from).toBe('2026-09-01');
        expect(s.to).toBe('2026-09-02');
        expect(s.bestDay?.day).toBe('2026-09-01');
        expect(s.worstDay?.day).toBe('2026-09-02');
        expect(s.drawdown.maxDrawdown).toBe(4);
    });
});

describe('aggregateBreakdown', () => {
    it('somma per chiave su più giornate', () => {
        const rows = [
            row('2026-09-01', 1, { by_strategy: { base: { n: 2, pnl: 3, won: 1, lost: 1 }, tennis: { n: 1, pnl: -1, won: 0, lost: 1 } } }),
            row('2026-09-02', 1, { by_strategy: { base: { n: 1, pnl: 0.5, won: 1, lost: 0 } } }),
        ];
        expect(aggregateBreakdown(rows, 'by_strategy')).toEqual({
            base: { n: 3, pnl: 3.5, won: 2, lost: 1 },
            tennis: { n: 1, pnl: -1, won: 0, lost: 1 },
        });
        expect(aggregateBreakdown(rows, 'by_sport')).toEqual({});
    });
});

// --------------------------------------------------------------- calendario
describe('calendarGrid', () => {
    it('settembre 2026: parte da lunedì 31/08, 5 settimane, righe agganciate', () => {
        const rows = [row('2026-09-10', 12.5)];
        const weeks = calendarGrid(2026, 9, rows);
        expect(weeks).toHaveLength(5);
        expect(weeks[0][0]).toMatchObject({ day: '2026-08-31', inMonth: false, dow: 0, dom: 31 });
        expect(weeks[0][1]).toMatchObject({ day: '2026-09-01', inMonth: true, dow: 1 });
        expect(weeks[4][6]).toMatchObject({ day: '2026-10-04', inMonth: false, dow: 6 });
        const cell = weeks.flat().find((c) => c.day === '2026-09-10');
        expect(cell?.row?.pnl_realized).toBe(12.5);
        expect(weeks.flat().filter((c) => c.inMonth)).toHaveLength(30);
        for (const w of weeks) expect(w).toHaveLength(7);
    });
    it('mese che inizia di lunedì (giugno 2026) non aggiunge celle prima', () => {
        const weeks = calendarGrid(2026, 6, []);
        expect(weeks[0][0]).toMatchObject({ day: '2026-06-01', inMonth: true });
    });
    it('febbraio 2027 (28 giorni, inizia lunedì): esattamente 4 settimane', () => {
        expect(calendarGrid(2027, 2, [])).toHaveLength(4);
    });
    it('mese non valido → RangeError', () => {
        expect(() => calendarGrid(2026, 0, [])).toThrow(RangeError);
        expect(() => calendarGrid(2026, -1, [])).toThrow(RangeError);
        expect(() => calendarGrid(2026.5, 1, [])).toThrow(RangeError);
    });
    it('shiftMonth attraversa gli anni in entrambe le direzioni', () => {
        expect(shiftMonth(2026, 12, 1)).toEqual({ year: 2027, month: 1 });
        expect(shiftMonth(2026, 1, -1)).toEqual({ year: 2025, month: 12 });
        expect(shiftMonth(2026, 9, -14)).toEqual({ year: 2025, month: 7 });
    });
});

// -------------------------------------------------------------- uscite auto
describe('exitInfo / tradeExit', () => {
    it('null senza meta o senza chiavi di uscita', () => {
        expect(exitInfo(null)).toBeNull();
        expect(exitInfo({})).toBeNull();
        expect(exitInfo({ locked_pnl: 1 })).toBeNull();
    });
    it('mappa i kind (e gli alias) sulle etichette italiane', () => {
        expect(exitInfo({ exit_kind: 'profit' })).toMatchObject({ kind: 'profit', label: 'Uscita: profitto' });
        expect(exitInfo({ exit_kind: 'take_profit' })?.kind).toBe('profit');
        expect(exitInfo({ exit_kind: 'loss', exit_reason: 'gol subito' })).toMatchObject({ kind: 'loss', label: 'Uscita: perdita', reason: 'gol subito' });
        expect(exitInfo({ exit_kind: 'time' })?.label).toBe('Uscita: tempo');
        expect(exitInfo({ exit_kind: 'RED_CARD' })?.label).toBe('Uscita: rosso');
        expect(exitInfo({ exit_kind: 'forced' })?.label).toBe('Uscita: obbligatoria');
        expect(exitInfo({ exit_kind: 'manual' })?.label).toBe('Cash out manuale');
        // green-up Omega: kind dedicato (non piu' un alias di profit)
        expect(exitInfo({ exit_kind: 'greenup', exit_reason: 'distanza 1 gol' })).toMatchObject({ kind: 'greenup', label: 'Green-up', reason: 'distanza 1 gol' });
        expect(exitInfo({ exit_kind: 'green_up' })?.kind).toBe('greenup');
        expect(exitInfo({ exit_kind: 'green' })?.kind).toBe('profit');
    });
    it('kind sconosciuto → etichetta grezza; solo reason → kind other', () => {
        expect(exitInfo({ exit_kind: 'boh' })).toMatchObject({ kind: 'other', label: 'Uscita: boh', raw: 'boh' });
        expect(exitInfo({ exit_reason: 'set pari' })).toMatchObject({ kind: 'other', label: 'Uscita', reason: 'set pari' });
    });
    it('forma annidata meta.exit.{kind,reason}', () => {
        expect(exitInfo({ exit: { kind: 'time', reason: "80'" } })).toMatchObject({ kind: 'time', reason: "80'" });
    });
    it('tradeExit: cash out MANUALE (meta.cashout sulla chiusura, nessun exit_kind) = Cash out manuale', () => {
        expect(tradeExit({ meta: {}, closes: [{ meta: { cashout: true } } as never] })).toMatchObject({ kind: 'manual', label: 'Cash out manuale' });
        // un exit_kind esplicito ha la precedenza
        expect(tradeExit({ meta: {}, closes: [{ meta: { cashout: true, exit_kind: 'greenup' } } as never] })?.kind).toBe('greenup');
    });
    it('tradeExit: prima l apertura, poi le chiusure', () => {
        expect(tradeExit({ meta: null, closes: [] })).toBeNull();
        expect(tradeExit({ meta: { exit_kind: 'profit' }, closes: [{ meta: { exit_kind: 'loss' } } as never] })?.kind).toBe('profit');
        expect(tradeExit({ meta: {}, closes: [{ meta: null } as never, { meta: { exit_kind: 'time' } } as never] })?.kind).toBe('time');
    });
});

// ============================================== audit 11/09: M-17 / H-10 / H-11
describe('clampHistoryRange (M-17)', () => {
    it('finestra dentro il limite: invariata', () => {
        expect(clampHistoryRange('2026-09-01', '2026-09-30'))
            .toEqual({ from: '2026-09-01', to: '2026-09-30', clamped: false, days: 30 });
    });

    it('oltre 400 giorni: accorcia tenendo la CODA recente e lo dichiara', () => {
        const r = clampHistoryRange('2024-01-01', '2026-09-11');
        expect(r.clamped).toBe(true);
        expect(r.to).toBe('2026-09-11');
        expect(r.from).toBe(addDays('2026-09-11', -400));
        expect(r.days).toBe(401);
    });

    it('esattamente 400 giorni: nessun clamp (il DB accetta <= 400)', () => {
        const from = addDays('2026-09-11', -400);
        expect(clampHistoryRange(from, '2026-09-11').clamped).toBe(false);
    });

    it('estremi invertiti: li rimette in ordine invece di sparire', () => {
        const r = clampHistoryRange('2026-09-30', '2026-09-01');
        expect(r).toMatchObject({ from: '2026-09-01', to: '2026-09-30', clamped: true });
    });

    it('giorni non validi: nessuna eccezione', () => {
        expect(clampHistoryRange('boh', '2026-09-01').clamped).toBe(false);
    });
});

describe('goalHitRate — solo obiettivi STORICIZZATI (H-10)', () => {
    it('un obiettivo di RIPIEGO non viene giudicato, ma si conta a parte', () => {
        const rows = [
            row('2026-09-01', 250, { goal: 250, goal_snapshot: true }),
            row('2026-09-02', 100, { goal: 250, goal_snapshot: true }),
            row('2026-09-03', 300, { goal: 250, goal_snapshot: false }),
            row('2026-09-04', 5, { goal: null, goal_snapshot: false }),
        ];
        expect(goalHitRate(rows)).toEqual({ total: 2, hit: 1, rate: 0.5, notHistorized: 1 });
    });

    it('nessuna giornata storicizzata → rate null (mai un 100 % inventato)', () => {
        const rows = [row('2026-09-01', 300, { goal: 250, goal_snapshot: false })];
        expect(goalHitRate(rows)).toEqual({ total: 0, hit: 0, rate: null, notHistorized: 1 });
    });
});

describe('normalizeDailyRow — goal_snapshot (H-10)', () => {
    it('senza il flag (RPC vecchia) il giorno NON è storicizzato', () => {
        expect(normalizeDailyRow({ day: '2026-09-10', goal: 250 })?.goal_snapshot).toBe(false);
        expect(normalizeDailyRow({ day: '2026-09-10', goal: 250, goal_snapshot: true })?.goal_snapshot).toBe(true);
        expect(normalizeDailyRow({ day: '2026-09-10', goal_snapshot: 'true' })?.goal_snapshot).toBe(false);
    });
});

describe('attributionOf / summarizeDayTrades (M-18 / H-11)', () => {
    const leg = (over: Record<string, unknown>) => ({
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', side: 'lay', mode: 'paper' as const,
        price: 40, size: 5, liability: 195, status: 'won', pnl: 3, placed_at: '2026-09-10T18:00:00Z',
        settled_at: '2026-09-10T20:00:00Z', meta: null, closes: [], total_pnl: 3,
        placed_in_day: true, settled_in_day: true, ...over,
    }) as never;

    it('Omega e Mike attribuiscono per PIAZZAMENTO, Safe per REGOLAZIONE', () => {
        expect(attributionOf('omega')).toBe('placed');
        expect(attributionOf('mike')).toBe('placed');
        expect(attributionOf('safe')).toBe('placed');   // safe_strategy_bot_v2: giorno di piazzamento
    });

    it("'placed': somma solo le posizioni piazzate nel giorno (le altre sono di un'altra cella)", () => {
        const s = summarizeDayTrades([
            leg({ id: 1, total_pnl: 3, placed_in_day: true, settled_in_day: true }),
            leg({ id: 2, total_pnl: -10, status: 'lost', placed_in_day: false, settled_in_day: true }),
        ], 'placed');
        expect(s.pnl).toBe(3);
        expect(s.attributed).toHaveLength(1);
        expect(s.others).toHaveLength(1);
        expect(s.settled).toBe(1);
        expect(s.won).toBe(1);
        expect(s.liability).toBe(195);
    });

    it("'settled': somma solo quelle REGOLATE nel giorno (più le vive piazzate oggi)", () => {
        const s = summarizeDayTrades([
            leg({ id: 1, total_pnl: 3, placed_in_day: false, settled_in_day: true }),
            leg({ id: 2, total_pnl: -10, status: 'lost', placed_in_day: true, settled_in_day: false }),
            leg({ id: 3, status: 'open', settled_at: null, total_pnl: 0, placed_in_day: true, settled_in_day: false }),
        ], 'settled');
        expect(s.pnl).toBe(3);
        expect(s.open).toBe(1);            // la viva piazzata oggi si vede
        expect(s.others.map((t) => t.id)).toEqual([2]);
    });

    it('P&L bloccato dalle coperture vive, liability solo di quelle piazzate oggi', () => {
        const s = summarizeDayTrades([
            leg({ id: 1, status: 'hedged', settled_at: null, total_pnl: 0, meta: { locked_pnl: -22.1 }, placed_in_day: true, settled_in_day: false }),
        ], 'placed');
        expect(s.lockedPnl).toBe(-22.1);
        expect(s.pnl).toBe(0);
        expect(s.open).toBe(1);
        expect(s.liability).toBe(195);
    });

    it('lista vuota/null: zero, mai NaN', () => {
        expect(summarizeDayTrades(null, 'placed')).toMatchObject({ pnl: 0, settled: 0, open: 0, lockedPnl: null });
    });
});
