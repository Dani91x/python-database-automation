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
import { fetchTennisBotDaily, type TennisBotDailyRow, type TennisBotKey } from '@/lib/tennis';

export type SportStorico = 'calcio' | 'tennis';
export type ModoStorico = 'paper' | 'live';
/** 01/10 (D-01): anche i 4 bot tennis, che dal 17/09 hanno P&L e regolamento */
export type BotStorico = 'omega' | 'safe' | 'mike' | TennisBotKey;

/** I 4 bot tennis dedicati: storico da `fetchTennisBotDaily`, per ordine. */
export function eBotTennisStorico(bot: BotStorico): bot is TennisBotKey {
    return bot === 'tennis_scalper' || bot === 'tennis_pro' || bot === 'tennis_flb' || bot === 'tennis_swing';
}

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
        // 01/10 (D-01): i 4 bot tennis hanno P&L e regolamento dal 17/09 e
        // netto di Betfair dal 24/09; la giornata e' quella della partita
        { bot: 'tennis_scalper', etichetta: 'Tennis Scalper', accento: 'text-lime-300', sportRpc: 'tennis' },
        { bot: 'tennis_pro', etichetta: 'Tennis Pro', accento: 'text-lime-300', sportRpc: 'tennis' },
        { bot: 'tennis_flb', etichetta: 'Tennis FLB', accento: 'text-lime-300', sportRpc: 'tennis' },
        { bot: 'tennis_swing', etichetta: 'Tennis Swing', accento: 'text-lime-300', sportRpc: 'tennis' },
    ],
};

export const FONTI_ASSENTI: Record<SportStorico, FonteAssente[]> = {
    calcio: [
        {
            // C-06 (01/10): lo scalper HA un P&L reale, ma solo della giornata
            // in corso (voce della barra, dal conto Betfair per ordine): non
            // scrive posizioni regolate per giornata, quindi qui non c'e' una
            // serie da sommare. Detto in parole, senza nomi di tabelle.
            id: 'scalper',
            etichetta: 'Scalper calcio',
            perche: 'il suo P&L reale esiste solo per la giornata in corso (voce «Scalper calcio» '
                + 'della barra di oggi, letta dal conto Betfair): non registra operazioni per giornata, '
                + 'quindi qui non ha uno storico da sommare.',
        },
    ],
    // 01/10 (D-01): i 4 bot tennis hanno uno storico; nessun bot tennis assente
    tennis: [],
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
    // B-14 (01/10): «Tutto» era in realta' il tetto di 400 giorni, senza dirlo
    tutto: `Ultimi ${MAX_HISTORY_DAYS} giorni`,
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
    /** importo piazzato per giorno; null = dato non disponibile */
    stakePerGiorno: Record<string, number> | null;
    /**
     * 01/10 (D-04) - di ogni giornata, la parte regolata dal CONTO Betfair e
     * quella STIMATA dal bot, quando la fonte le separa (oggi solo i 4 bot
     * tennis). null = la fonte non le separa: lo si dice, non si inventa.
     */
    fontePerGiorno?: Record<string, { reale: number | null; stimato: number | null; stimati: number | null }> | null;
    /** errore di lettura di QUESTO bot: gli altri restano leggibili */
    errore: string | null;
}

/**
 * Una giornata di un bot tennis nel formato del motore condiviso. Le
 * «operazioni» sono gli ORDINI regolati: il servizio non scrive il legame
 * ingresso-uscita (B13), quindi non esistono posizioni da contare.
 */
export function rigaGiornalieraTennisBot(r: TennisBotDailyRow): DailyRow | null {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.giorno) || r.pnl_netto == null) return null;
    const vuoti = Math.max(0, r.ordini - r.vinti - r.persi);
    return {
        day: r.giorno,
        pnl_realized: r.pnl_netto,
        trades_placed: r.ordini,
        settled: r.ordini,
        won: r.vinti,
        lost: r.persi,
        void: vuoti,
        hedged_closed: 0,
        win_rate: r.vinti + r.persi > 0 ? Math.round((r.vinti / (r.vinti + r.persi)) * 10000) / 10000 : null,
        avg_win: null, avg_loss: null, best_trade: null, worst_trade: null, max_liability: null,
        gross_profit: 0, gross_loss: 0, profit_factor: null,
        commission_paid: r.commissione,
        goal: null, goal_pct: null, goal_snapshot: false,
        by_strategy: {}, by_sport: {}, by_origin: {},
        first_trade_at: null, last_trade_at: null,
    };
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
        if (eBotTennisStorico(fonte.bot)) {
            // D-01: una moneta per lettura (p_mode obbligatoria), giorno della
            // partita dal database; niente importo piazzato per giornata
            const rows = await fetchTennisBotDaily(from, to, modo, fonte.bot);
            const fontePerGiorno: NonNullable<SerieBot['fontePerGiorno']> = {};
            for (const r of rows) {
                const g = rigaGiornalieraTennisBot(r);
                if (!g) continue;
                righe.push(g);
                fontePerGiorno[g.day] = r.pnl_stimato === undefined
                    // RPC senza la separazione: tutto il netto e' stima del bot
                    ? { reale: null, stimato: r.pnl_netto, stimati: null }
                    : { reale: r.pnl_reale ?? null, stimato: r.pnl_stimato ?? null, stimati: r.stimati ?? null };
            }
            righe = righe.sort((a, b) => a.day.localeCompare(b.day));
            return { ...base, righe, modoAttendibile: true, stakePerGiorno: null, fontePerGiorno, errore: null };
        }
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
            stakePerGiorno = await fetchStakePerGiorno(fonte.bot as 'omega' | 'safe' | 'mike', from, to, fonte.sportRpc, modo);
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
    /** C-05 (01/10): regolate né vinte né perse (P&L esattamente zero o annullate) */
    pari: number;
    /**
     * D-04 (01/10): di `pnl`, la parte regolata dal conto Betfair e la stima del
     * bot; null = la fonte non le separa (lo si dichiara a schermo).
     */
    reale: number | null;
    stimato: number | null;
    /** ordini ancora stimati nel periodo (bot tennis); null = non noto */
    stimati: number | null;
    /** vinte/(vinte+perse) in [0,1]; null senza esiti */
    winRate: number | null;
    /** somma degli importi piazzati; null = non disponibile (migrazione mancante) */
    stake: number | null;
    /** pnl/stake in [-1, …]; null se lo stake manca o è zero */
    roi: number | null;
    errore: string | null;
}

export function aggregaBot(s: SerieBot): AggregatoBot {
    let pnl = 0, operazioni = 0, regolate = 0, vinte = 0, perse = 0, pari = 0;
    // reale/stimato SOLO se la fonte li separa per OGNI giornata mostrata
    let reale: number | null = s.fontePerGiorno ? 0 : null;
    let stimato: number | null = s.fontePerGiorno ? 0 : null;
    let stimati: number | null = s.fontePerGiorno ? 0 : null;
    for (const r of s.righe) {
        pnl += r.pnl_realized;
        operazioni += r.trades_placed;
        regolate += r.settled;
        vinte += r.won;
        perse += r.lost;
        pari += r.void;
        const f = s.fontePerGiorno?.[r.day];
        if (!f) { reale = null; stimato = null; stimati = null; continue; }
        if (reale != null) reale += f.reale ?? 0;
        if (stimato != null) stimato += f.stimato ?? 0;
        if (stimati != null) stimati = f.stimati == null ? null : stimati + f.stimati;
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
        pnl: r2(pnl), giorni: s.righe.length, operazioni, regolate, vinte, perse, pari,
        reale: reale == null ? null : r2(reale),
        stimato: stimato == null ? null : r2(stimato),
        stimati,
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
    /** C-05: regolate né vinte né perse */
    pari: number;
    /** D-04: parte del conto Betfair e stima; null = almeno un bot non le separa */
    reale: number | null;
    stimato: number | null;
    /** D-03: ordini ancora stimati (bot tennis); null = non noto */
    stimati: number | null;
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
    let pnl = 0, operazioni = 0, regolate = 0, vinte = 0, perse = 0, pari = 0, bot = 0;
    let stake: number | null = null;
    // C-01/D-01 (01/10): se un bot CON giornate non ha l'importo piazzato, il
    // ROI del totale non si calcola: P&L di tutti diviso l'importo di alcuni
    // sarebbe un numero falso
    let stakeIncompleto = false;
    let reale: number | null = 0;
    let stimato: number | null = 0;
    let stimati: number | null = 0;
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
        vinte += a.vinte; perse += a.perse; pari += a.pari ?? 0;
        if (a.stake != null) stake = r2((stake ?? 0) + a.stake);
        else if (a.giorni > 0) stakeIncompleto = true;
        if (a.giorni > 0) {
            if (a.reale === undefined || a.reale === null || a.stimato === undefined || a.stimato === null) {
                reale = null; stimato = null;
            } else if (reale != null && stimato != null) {
                reale += a.reale; stimato += a.stimato;
            }
            stimati = a.stimati == null || stimati == null ? null : stimati + a.stimati;
        }
    }
    if (stakeIncompleto) stake = null;
    return {
        modo, pnl: r2(pnl), operazioni, regolate, vinte, perse, pari, bot,
        reale: bot > 0 && reale != null ? r2(reale) : null,
        stimato: bot > 0 && stimato != null ? r2(stimato) : null,
        stimati: bot > 0 && reale != null ? stimati : null,
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
    /** la variante che `DayDetail` usa per le etichette (fase/strategia/ruolo); null = bot tennis */
    variante: HistoryVariant | null;
    trades: DayTrade[];
    modoAttendibile: boolean;
    errore: string | null;
    /** 01/10 - il dettaglio per riga non esiste per questo bot: perche' (detto in parole) */
    senzaDettaglio?: string | null;
}

/** Le operazioni di UN giorno, bot per bot, per UNA modalità. Non lancia. */
export async function caricaTradeGiorno(
    sport: SportStorico, modo: ModoStorico, day: string,
): Promise<TradeGiornoBot[]> {
    return Promise.all(FONTI_STORICO[sport].map(async (fonte): Promise<TradeGiornoBot> => {
        const base = {
            bot: fonte.bot, etichetta: fonte.etichetta,
            variante: eBotTennisStorico(fonte.bot) ? null : fonte.bot as HistoryVariant,
        };
        if (eBotTennisStorico(fonte.bot)) {
            // nessuna lettura in piu': il dettaglio per ordine e' nelle Chiuse
            return {
                ...base, trades: [], modoAttendibile: true, errore: null,
                senzaDettaglio: 'il dettaglio per ordine di questo bot è nella scheda «Posizioni chiuse» di quella giornata',
            };
        }
        try {
            if (fonte.bot === 'omega') {
                const r = await fetchOmegaDayTradesPerModo(day, modo);
                // A-02 (01/10): righe MISTE (paper + live) non si mostrano mai
                // sotto una moneta: il bot resta dichiarato, senza righe
                return { ...base, trades: r.modoAttendibile ? r.trades : [], modoAttendibile: r.modoAttendibile, errore: null };
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
