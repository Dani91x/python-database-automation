// ============================================================================
// storicoSport.ts — LO STORICO DI UNO SPORT, bot per bot.
//
// Ordine dell'utente (17/09): «in "posizioni chiuse" voglio vedere SOLO le
// posizioni della giornata; per i giorni precedenti uno STORICO dedicato che
// il trader può consultare, uno AL TENNIS e uno AL CALCIO, con la chiara
// distinzione dei profitti o loss per bot».
//
// QUESTO FILE NON INVENTA NIENTE E NON RICALCOLA NIENTE. Le giornate le
// producono le RPC già esistenti (`lib/dailyHistory`), che a loro volta
// passano dal motore condiviso `trading_daily_history`. Qui si fa solo:
//   · scegliere QUALI bot appartengono a uno sport (e dire quali non hanno
//     storico affatto, invece di far finta che il totale sia completo);
//   · sommare le giornate di più bot in una serie sola, per giorno;
//   · tenere PAPER e LIVE separati — e renderlo impossibile da sbagliare.
//
// ⚠️ LA REGOLA CHE GOVERNA TUTTO IL FILE (14/09, e prima ancora in
// `PosizioniChiuse`): **paper e live non si sommano mai.** Non è una
// preferenza di presentazione: sono due monete diverse. Perciò `totaleModo`
// LANCIA se le si passano aggregati di modalità diverse, e un bot la cui RPC
// non sa filtrare per modalità non entra in nessun totale — sta in un blocco a
// parte, dichiarato. Ai soldi veri si arriva solo scrivendolo.
// ============================================================================
import type { EquityPoint } from '@/components/trading/EquityCurve';
import {
    equityByDay, addDays, romeDay, MAX_HISTORY_DAYS,
    fetchSafeDaily, fetchMikeDaily, fetchOmegaDailyPerModo, fetchStakePerGiorno,
    fetchSafeDayTrades, fetchMikeDayTrades, fetchOmegaDayTradesPerModo,
    type DailyRow, type DayTrade, type HistoryVariant,
} from '@/lib/dailyHistory';

export type SportStorico = 'calcio' | 'tennis';
export type ModoStorico = 'paper' | 'live';
export type BotStorico = 'omega' | 'safe' | 'mike';

export const SPORT_LABEL: Record<SportStorico, string> = {
    calcio: 'Calcio',
    tennis: 'Tennis',
};
export const SPORT_ICONA: Record<SportStorico, string> = { calcio: '⚽', tennis: '🎾' };

/** Come si chiama una modalità sotto gli occhi del trader (glossario). */
export const MODO_LABEL: Record<ModoStorico, string> = { live: 'soldi veri', paper: 'prova' };

// ---------------------------------------------------------------- le fonti

/** Un bot che ha davvero uno storico giornaliero sul database. */
export interface FonteStorico {
    bot: BotStorico;
    etichetta: string;
    /** classe del colore d'accento (design system: Omega primary, Safe secondary, Mike teal) */
    accento: string;
    /** filtro sport da passare alla RPC: null = la RPC non ha quel parametro */
    sportRpc: SportStorico | null;
}

/**
 * Un bot che NON ha uno storico giornaliero: si DICHIARA, non si finge.
 * Verificato sul database reale il 17/09 (sonda in sola lettura), non dedotto.
 */
export interface FonteAssente {
    id: string;
    etichetta: string;
    perche: string;
}

export const FONTI_STORICO: Record<SportStorico, FonteStorico[]> = {
    calcio: [
        { bot: 'omega', etichetta: 'Omega', accento: 'text-primary', sportRpc: null },
        { bot: 'safe', etichetta: 'Safe Strategy', accento: 'text-secondary', sportRpc: 'calcio' },
        { bot: 'mike', etichetta: 'Mike', accento: 'text-teal-300', sportRpc: null },
    ],
    tennis: [
        { bot: 'safe', etichetta: 'Safe Strategy · tennis', accento: 'text-secondary', sportRpc: 'tennis' },
    ],
};

export const FONTI_ASSENTI: Record<SportStorico, FonteAssente[]> = {
    calcio: [
        {
            id: 'scalper',
            etichetta: 'Scalper calcio',
            perche: 'non scrive operazioni regolate con P&L su nessuna tabella di trade: '
                + '`scalper_activity` è un diario di scansioni, non un registro di posizioni.',
        },
    ],
    tennis: [
        {
            id: 'tennis_scalper', etichetta: 'Tennis Scalper',
            perche: 'gli ordini finiscono in `tennis_live_orders`, che non ha né P&L né regolamento: '
                + 'nessuna giornata da sommare.',
        },
        {
            id: 'tennis_pro', etichetta: 'Tennis Pro',
            perche: 'stessa tabella ordini senza P&L; `tennis_bot_control.stats` è la fotografia '
                + 'della sessione in corso, non uno storico per giorno.',
        },
        {
            id: 'tennis_flb', etichetta: 'Tennis FLB',
            perche: 'stessa tabella ordini senza P&L; `tennis_bot_control.stats` è la fotografia '
                + 'della sessione in corso, non uno storico per giorno.',
        },
        {
            id: 'tennis_swing', etichetta: 'Tennis Swing',
            perche: 'stessa tabella ordini senza P&L; `tennis_bot_control.stats` è la fotografia '
                + 'della sessione in corso, non uno storico per giorno.',
        },
    ],
};

/** Rotta della dashboard di uno sport: una sola forma, usata da ogni pulsante. */
export function rottaStorico(sport: SportStorico): string {
    return `/storico/${sport}`;
}

// ------------------------------------------------------------- intervalli

export type IntervalloKind = 'oggi' | '7g' | '30g' | 'mese' | 'tutto';

export const INTERVALLO_LABEL: Record<IntervalloKind, string> = {
    oggi: 'Oggi',
    '7g': '7 giorni',
    '30g': '30 giorni',
    mese: 'Mese corrente',
    tutto: 'Tutto',
};

/** Intervallo [from, to] inclusivo di un ambito, rispetto alla giornata `oggi`. */
export function intervalloRange(kind: IntervalloKind, oggi: string): { from: string; to: string } {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(oggi)) throw new RangeError(`giorno non valido: ${oggi}`);
    switch (kind) {
        case 'oggi': return { from: oggi, to: oggi };
        case '7g': return { from: addDays(oggi, -6), to: oggi };
        case '30g': return { from: addDays(oggi, -29), to: oggi };
        case 'mese': return { from: `${oggi.slice(0, 7)}-01`, to: oggi };
        // «tutto» dentro il tetto del motore condiviso (M-17: oltre 400 giorni
        // la RPC restringe da sola e lo dichiara). Chiedere 10 anni per poi
        // riceverne uno sarebbe una promessa non mantenuta.
        case 'tutto': return { from: addDays(oggi, -(MAX_HISTORY_DAYS - 1)), to: oggi };
    }
}

// ------------------------------------------------------------- caricamento

export interface SerieBot {
    bot: BotStorico;
    etichetta: string;
    accento: string;
    modo: ModoStorico;
    righe: DailyRow[];
    /**
     * La RPC ha DAVVERO filtrato per modalità? `false` = le righe sono miste
     * (paper + live insieme) e non possono entrare in nessun totale di
     * modalità. Vale oggi per Omega finché non è applicata
     * `migrations/storico_sport_2026-09-17.sql`.
     */
    modoAttendibile: boolean;
    /** importo piazzato per giorno; null = `get_storico_stake` non applicata */
    stakePerGiorno: Record<string, number> | null;
    /** errore di lettura di QUESTO bot: gli altri restano leggibili */
    errore: string | null;
}

/** Legge lo storico di UN bot per UNA modalità. Non lancia: l'errore è un dato. */
export async function caricaSerieBot(
    fonte: FonteStorico, modo: ModoStorico, from: string, to: string,
): Promise<SerieBot> {
    const base = {
        bot: fonte.bot, etichetta: fonte.etichetta, accento: fonte.accento, modo,
    };
    try {
        let righe: DailyRow[] = [];
        let modoAttendibile = true;
        if (fonte.bot === 'omega') {
            const r = await fetchOmegaDailyPerModo(from, to, modo);
            righe = r.rows;
            modoAttendibile = r.modoAttendibile;
        } else if (fonte.bot === 'safe') {
            righe = await fetchSafeDaily(from, to, fonte.sportRpc, modo);
        } else {
            righe = await fetchMikeDaily(from, to, modo);
        }
        // lo stake è un DI PIÙ: se manca, manca solo il ROI
        let stakePerGiorno: Record<string, number> | null = null;
        try {
            stakePerGiorno = await fetchStakePerGiorno(fonte.bot, from, to, fonte.sportRpc, modo);
        } catch { stakePerGiorno = null; }
        return { ...base, righe, modoAttendibile, stakePerGiorno, errore: null };
    } catch (e) {
        return {
            ...base, righe: [], modoAttendibile: false, stakePerGiorno: null,
            errore: String((e as Error)?.message ?? e),
        };
    }
}

/** Legge tutte le fonti di uno sport, per entrambe le modalità. */
export async function caricaStoricoSport(
    sport: SportStorico, from: string, to: string,
): Promise<SerieBot[]> {
    const lavori: Promise<SerieBot>[] = [];
    for (const fonte of FONTI_STORICO[sport]) {
        for (const modo of ['live', 'paper'] as ModoStorico[]) {
            lavori.push(caricaSerieBot(fonte, modo, from, to));
        }
    }
    return Promise.all(lavori);
}

// -------------------------------------------------------------- aggregati

function r2(x: number): number { return Math.round(x * 100) / 100; }

export interface AggregatoBot {
    bot: BotStorico;
    etichetta: string;
    accento: string;
    modo: ModoStorico;
    modoAttendibile: boolean;
    /** P&L realizzato nel periodo */
    pnl: number;
    /** giornate con attività */
    giorni: number;
    /** aperture PIAZZATE nel periodo */
    operazioni: number;
    /** aperture REGOLATE nel periodo */
    regolate: number;
    vinte: number;
    perse: number;
    /** vinte/(vinte+perse) in [0,1]; null senza esiti */
    winRate: number | null;
    /** somma degli importi piazzati; null = non disponibile (migrazione mancante) */
    stake: number | null;
    /** pnl/stake in [-1, …]; null se lo stake manca o è zero */
    roi: number | null;
    errore: string | null;
}

export function aggregaBot(s: SerieBot): AggregatoBot {
    let pnl = 0, operazioni = 0, regolate = 0, vinte = 0, perse = 0;
    for (const r of s.righe) {
        pnl += r.pnl_realized;
        operazioni += r.trades_placed;
        regolate += r.settled;
        vinte += r.won;
        perse += r.lost;
    }
    let stake: number | null = null;
    if (s.stakePerGiorno) {
        // SOLO i giorni che questo bot ha davvero nelle sue giornate. La mappa
        // degli importi arriva dalla stessa finestra ma con i suoi filtri, e
        // sommare chiavi che a schermo non ci sono darebbe un ROI che non
        // corrisponde al P&L scritto accanto.
        //
        // ⚠️ Nessuna scorciatoia «se non ho giornate sommo tutto»: un bot senza
        // giornate ha importo piazzato ZERO. La prima stesura aveva quella
        // scorciatoia e il test della pagina l'ha presa in flagrante — un bot
        // con zero righe portava dentro l'importo di un altro e il ROI del
        // totale dimezzava (10,0 % diventava 5,0 %).
        const giorniVisti = new Set(s.righe.map((r) => r.day));
        let acc = 0;
        for (const [day, v] of Object.entries(s.stakePerGiorno)) {
            if (!giorniVisti.has(day)) continue;
            acc += v;
        }
        stake = r2(acc);
    }
    return {
        bot: s.bot, etichetta: s.etichetta, accento: s.accento, modo: s.modo,
        modoAttendibile: s.modoAttendibile,
        pnl: r2(pnl), giorni: s.righe.length, operazioni, regolate, vinte, perse,
        winRate: vinte + perse > 0 ? Math.round((vinte / (vinte + perse)) * 10000) / 10000 : null,
        stake,
        roi: stake != null && stake > 0 ? Math.round((pnl / stake) * 10000) / 10000 : null,
        errore: s.errore,
    };
}

export interface TotaleStorico {
    modo: ModoStorico;
    pnl: number;
    operazioni: number;
    regolate: number;
    vinte: number;
    perse: number;
    winRate: number | null;
    stake: number | null;
    roi: number | null;
    /** quanti bot hanno contribuito */
    bot: number;
}

/**
 * IL TOTALE DI UNA MODALITÀ.
 *
 * Somma **solo** gli aggregati di quella modalità e **solo** quelli in cui la
 * modalità è attendibile. Se le si passa un aggregato di un'altra modalità
 * LANCIA, invece di fare una somma che nessuno ha chiesto: il 14/09 la card
 * del tennis mostrava +0,25 € — un numero che non esisteva da nessuna parte,
 * perché era +0,41 € di live più −0,16 € di paper.
 */
export function totaleModo(
    aggregati: readonly AggregatoBot[], modo: ModoStorico,
): TotaleStorico {
    let pnl = 0, operazioni = 0, regolate = 0, vinte = 0, perse = 0, bot = 0;
    let stake: number | null = null;
    for (const a of aggregati) {
        if (a.modo !== modo) {
            throw new Error(
                `totaleModo(${modo}) ha ricevuto un aggregato in modalità ${a.modo} `
                + `(${a.etichetta}): paper e live non si sommano.`,
            );
        }
        if (!a.modoAttendibile) continue;   // fuori dai totali, dichiarato a parte
        bot += 1;
        pnl += a.pnl; operazioni += a.operazioni; regolate += a.regolate;
        vinte += a.vinte; perse += a.perse;
        if (a.stake != null) stake = r2((stake ?? 0) + a.stake);
    }
    return {
        modo, pnl: r2(pnl), operazioni, regolate, vinte, perse, bot,
        winRate: vinte + perse > 0 ? Math.round((vinte / (vinte + perse)) * 10000) / 10000 : null,
        stake,
        roi: stake != null && stake > 0 ? Math.round((pnl / stake) * 10000) / 10000 : null,
    };
}

// ------------------------------------------------------------------ serie

/**
 * Somma le giornate di più bot in UNA serie per giorno. I campi che non hanno
 * senso sommati (medie, obiettivo, profit factor, liability massima) restano
 * `null` o si ricalcolano dalle somme: mai una media di medie.
 */
export function unisciGiornate(serie: readonly DailyRow[][]): DailyRow[] {
    const per = new Map<string, DailyRow>();
    for (const righe of serie) {
        for (const r of righe) {
            const cur = per.get(r.day);
            if (!cur) {
                per.set(r.day, {
                    ...r,
                    // i campi non sommabili si azzerano subito: portarseli dietro
                    // dal PRIMO bot li farebbe passare per il totale
                    avg_win: null, avg_loss: null, profit_factor: null,
                    goal: null, goal_pct: null, goal_snapshot: false,
                    by_strategy: {}, by_sport: {}, by_origin: {},
                });
                continue;
            }
            per.set(r.day, {
                ...cur,
                pnl_realized: r2(cur.pnl_realized + r.pnl_realized),
                trades_placed: cur.trades_placed + r.trades_placed,
                settled: cur.settled + r.settled,
                won: cur.won + r.won,
                lost: cur.lost + r.lost,
                void: cur.void + r.void,
                hedged_closed: cur.hedged_closed + r.hedged_closed,
                gross_profit: r2(cur.gross_profit + r.gross_profit),
                gross_loss: r2(cur.gross_loss + r.gross_loss),
                win_rate: cur.won + r.won + cur.lost + r.lost > 0
                    ? Math.round(((cur.won + r.won) / (cur.won + r.won + cur.lost + r.lost)) * 10000) / 10000
                    : null,
                best_trade: maggiore(cur.best_trade, r.best_trade),
                worst_trade: minore(cur.worst_trade, r.worst_trade),
                max_liability: maggiore(cur.max_liability, r.max_liability),
                commission_paid: cur.commission_paid == null && r.commission_paid == null
                    ? null : r2((cur.commission_paid ?? 0) + (r.commission_paid ?? 0)),
                first_trade_at: primo(cur.first_trade_at, r.first_trade_at),
                last_trade_at: ultimo(cur.last_trade_at, r.last_trade_at),
            });
        }
    }
    return [...per.values()].sort((a, b) => a.day.localeCompare(b.day));
}

function maggiore(a: number | null, b: number | null): number | null {
    if (a == null) return b;
    if (b == null) return a;
    return a >= b ? a : b;
}
function minore(a: number | null, b: number | null): number | null {
    if (a == null) return b;
    if (b == null) return a;
    return a <= b ? a : b;
}
function primo(a: string | null, b: string | null): string | null {
    if (!a) return b;
    if (!b) return a;
    return a <= b ? a : b;
}
function ultimo(a: string | null, b: string | null): string | null {
    if (!a) return b;
    if (!b) return a;
    return a >= b ? a : b;
}

/** Curva del P&L cumulato: la stessa di tutte le altre pagine. */
export function curvaCumulata(righe: DailyRow[]): EquityPoint[] {
    return equityByDay(righe);
}

export interface BarraGiorno {
    day: string;
    /** P&L del giorno, somma dei bot passati */
    pnl: number;
    /** contributo di ciascun bot, per la legenda e il tooltip */
    perBot: Record<string, number>;
}

/**
 * Barre per giorno (una per giornata dell'intervallo con attività), con il
 * dettaglio per bot. I giorni SENZA attività non diventano barre a zero: un
 * giorno in cui non si è operato non è un giorno chiuso in pari.
 */
export function barrePerGiorno(
    serie: readonly { etichetta: string; righe: DailyRow[] }[],
): BarraGiorno[] {
    const per = new Map<string, BarraGiorno>();
    for (const s of serie) {
        for (const r of s.righe) {
            const cur = per.get(r.day) ?? { day: r.day, pnl: 0, perBot: {} };
            cur.pnl = r2(cur.pnl + r.pnl_realized);
            cur.perBot[s.etichetta] = r2((cur.perBot[s.etichetta] ?? 0) + r.pnl_realized);
            per.set(r.day, cur);
        }
    }
    return [...per.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** La giornata operativa corrente (Europe/Rome): una sola fonte, quella dello storico. */
export function oggiOperativo(now: Date = new Date()): string {
    return romeDay(now);
}

// ----------------------------------------------------- dettaglio di un giorno

export interface TradeGiornoBot {
    bot: BotStorico;
    etichetta: string;
    /** la variante che `DayDetail` usa per le etichette (fase/strategia/ruolo) */
    variante: HistoryVariant;
    trades: DayTrade[];
    modoAttendibile: boolean;
    errore: string | null;
}

/** Le operazioni di UN giorno, bot per bot, per UNA modalità. Non lancia. */
export async function caricaTradeGiorno(
    sport: SportStorico, modo: ModoStorico, day: string,
): Promise<TradeGiornoBot[]> {
    return Promise.all(FONTI_STORICO[sport].map(async (fonte): Promise<TradeGiornoBot> => {
        const base = {
            bot: fonte.bot, etichetta: fonte.etichetta,
            variante: fonte.bot as HistoryVariant,
        };
        try {
            if (fonte.bot === 'omega') {
                const r = await fetchOmegaDayTradesPerModo(day, modo);
                return { ...base, trades: r.trades, modoAttendibile: r.modoAttendibile, errore: null };
            }
            if (fonte.bot === 'safe') {
                const t = await fetchSafeDayTrades(day, fonte.sportRpc, modo);
                return { ...base, trades: t, modoAttendibile: true, errore: null };
            }
            const t = await fetchMikeDayTrades(day, modo);
            return { ...base, trades: t, modoAttendibile: true, errore: null };
        } catch (e) {
            return {
                ...base, trades: [], modoAttendibile: false,
                errore: String((e as Error)?.message ?? e),
            };
        }
    }));
}
