// ============================================================================
// safeBot.ts — client del BOT della sezione SAFE STRATEGY.
//
// Specchio esatto di lib/omega.ts (stesso pattern: la UI scrive stato/parametri
// e legge lo specchio DB, l'esecuzione vera è del servizio locale Betfair).
// Parla SOLO con le RPC owner-only della migrazione safe_strategy_bot.sql:
//   safe_activate / safe_stop / safe_update_params / get_safe_state /
//   get_safe_trades / safe_request.
//
// Tabelle lette in realtime: safe_strategy_control, safe_strategy_trades,
// safe_strategy_requests (UN canale 'safe-bot') e safe_strategy_opportunities
// (canale dedicato, come subscribeScanRows).
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import { fmtMoney, fmtOdds } from '@/lib/format';
import { payloadCashoutEvento, payloadRiprendiEvento } from '@/lib/chiusuraUtente';
import { DEFAULT_PARAMS, mergeParams, type SafeStrategyParams, type VariantId } from '@/lib/safeStrategy';
import {
    blockSelection, csSelection, htSelection, isUsableBlock, scanBlockByMarketId,
    usableMarketBlocks,
    type CalcioScanPayload, type ScanCsSelection, type ScanMarketBlock, type ScanOddsPair,
    type TennisScanPayload,
} from '@/lib/safeStrategyScan';

export type SafeBotStatus = 'idle' | 'running' | 'stopping' | 'stopped' | 'error';
export type SafeMode = 'paper' | 'live';
export type SafeSport = 'calcio' | 'tennis';
/** 'model' = opportunità dal modello (λ Poisson) · 'manual' = piazzato a mano */
export type SafeStrategyKind = 'base' | 'esatto' | 'punta' | 'tennis' | 'model' | 'manual';
export type SafeTradeStatus =
    | 'pending' | 'open' | 'hedged' | 'won' | 'lost' | 'void' | 'error';
export type SafeSide = 'back' | 'lay';

// ------------------------------------------------------------------- stato
export interface SafeStats {
    events_total?: number;
    signals_active?: number;
    trades_open?: number;
    open_liability?: number;
    /** liability delle riserve a esito IGNOTO (in verifica su Betfair) */
    reconciling_liability?: number;
    realized_today?: number;
    realized_total?: number;
    /** contatori della GIORNATA DI PIAZZAMENTO (Europe/Rome) */
    won_today?: number;
    lost_today?: number;
    legs_today?: number;
    events_today?: number;
    /** QUANTE posizioni vive sono CIECHE in questo ciclo (nessuna riga del feed
     *  per il loro evento). È un CONTATORE, non un flag: `check_feed_blind`
     *  ritorna un int (bot_service.py). 0 = tutte le posizioni sono viste.
     *  Il dettaglio per riga sta in `meta.blind_since` (vedi `blindSince`). */
    feed_blind?: number;
    last_cycle?: string;
}

/** stato del RISCHIO pubblicato dal servizio in control.stats.risk */
export interface SafeRiskStats {
    /** liability impegnata nella giornata operativa (€) — CONTO: bot + manuali */
    daily_liability?: number;
    /**
     * 16/09 — la stessa liability contata sulle SOLE posizioni del bot: e' su
     * QUESTA che i cap decidono (`bot_service.py:6647`). Se le due cifre
     * divergono, la differenza sono le operazioni fatte a mano dal trader:
     * misurati 32,80 € di responsabilita' manuale finiti dentro i cap del bot.
     * Assente = il servizio non la pubblica, e allora si scrive «—», non zero.
     */
    daily_liability_bot?: number;
    /** realizzato di oggi sulle sole posizioni del bot (€) */
    realized_today_bot?: number;
    /**
     * true = il servizio sta contando nei cap SOLO le posizioni automatiche
     * (la RPC `get_safe_aggregates` torna le chiavi `_auto`). false = ripiega
     * sui numeri completi, che sono piu' alti, cioe' piu' prudenti.
     */
    cap_solo_automatico?: boolean;
    /** cap giornaliero di liability (€) */
    daily_cap?: number;
    /** liability delle riserve in verifica su Betfair (€) */
    reconciling_liability?: number;
    /** true = stop per perdita giornaliera scattato: nessun nuovo ingresso */
    loss_stop_active?: boolean;
    /** soglia dello stop (€, negativa) */
    daily_loss_stop?: number;
}

/** Parametri EFFETTIVI pubblicati dal servizio (`bot_service.params_effective`):
 *  sono i valori con cui il bot gira DAVVERO, dopo clamp e normalizzazione.
 *  La UI li mostra e segnala quando differiscono dal form (audit H-14/H-15). */
export interface SafeParamsEffective {
    poll_interval_s?: number;
    commission_pct?: number;
    max_open_trades?: number;
    max_liability_per_trade?: number;
    min_size_available_factor?: number;
    opps_interval_s?: number;
    opps_stake?: number;
    skip_log_interval_s?: number;
    max_spread_ratio?: number;
    place_max_attempts?: number;
    opps_min_confidence?: number;
    opps_min_edge?: number;
    paper_fill_ttl_s?: number;
    live_fill_deadline_s?: number;
    /** size minima Betfair usata dal servizio (€): default 2 */
    min_stake?: number;
    variants?: VariantId[];
    execution_mode?: string;
    auto_trade_opportunities?: boolean;
    auto_trade_anomalies?: boolean;
    auto_trade_combos?: boolean;
    auto_trade_tennis?: boolean;
    omega_live_via_flumine?: boolean;
    exits?: Record<string, unknown> | null;
    risk?: Record<string, unknown> | null;
    /** CERT. 14/09 — modalita' PER STRATEGIA realmente in uso dal servizio.
     *  Mappa parziale: una strategia assente eredita `control.mode`. Il `mode`
     *  del servizio resta un TETTO — in paper nessuna voce qui puo' far uscire
     *  soldi veri. E' l'unica cosa che non si puo' lasciare dedurre a chi
     *  guarda lo schermo: dice DA QUALE strategia escono soldi veri. */
    strategy_modes?: Record<string, string> | null;
    /** CERT. 14/09 — cancelletto di approvazione sulle CHIUSURE del tennis.
     *  Se e' false la pagina DEVE dirlo: altrimenti l'utente crede di avere il
     *  controllo delle chiusure e non ce l'ha. */
    tennis_exit_approval?: boolean;
    /** CERT. 14/09 — stake REALE delle 4 strategie del manuale, normalizzato dal
     *  servizio. `backSize` entra su TENNIS e PUNTA (che puntano), `laySize` su
     *  BASE ed ESATTO (che bancano). NON e' `risk.model_stake`, che e' di un
     *  altro motore (le opportunita' di modello). Un valore scritto male
     *  ripiega in silenzio su 2,00 EUR: questo campo mostra quello VERO. */
    stake?: {
        laySize?: number; backSize?: number;
        /** B.5 (16/09) — stake per NOME di strategia. Nasce vuota: una chiave
         *  assente vuol dire "usa quella per lato", come sempre. Il motore la
         *  legge con `engine.stake_di_strategia`. */
        per_strategia?: Record<string, number>;
    } | null;
}

/** CERT. 14/09 — strategie che stanno operando a SOLDI VERI adesso.
 *  Vuoto = nessuna (servizio in paper, o tutte riportate a paper dalla mappa).
 *  `mode` del servizio = TETTO: in paper la risposta e' sempre vuota. */
export function liveStrategies(
    mode: string | null | undefined,
    variants: readonly string[] | null | undefined,
    strategyModes: Record<string, string> | null | undefined,
): string[] {
    if (String(mode ?? '').toLowerCase() !== 'live') return [];
    const mappa = strategyModes ?? {};
    // CERT. 14/09 — i soldi veri si raggiungono SOLO scrivendolo: una voce
    // assente o illeggibile vale PAPER anche a servizio armato in live.
    // Se questa riga ereditasse 'live' come faceva prima, la pagina
    // dichiarerebbe soldi veri su strategie che il servizio tiene in prova.
    // E solo le strategie ABILITATE a operare: una variante spenta non spende,
    // qualunque cosa dica la mappa.
    return (variants ?? []).filter((v) => String(mappa[v] ?? '').toLowerCase() === 'live')
        .map((v) => String(v));
}

/** conteggio opportunità per tipo (control.stats.opps) */
export type SafeOppCounts = Partial<Record<SafeOppKind, number>>;

export interface SafeStatsFull extends SafeStats {
    risk?: SafeRiskStats | null;
    opps?: SafeOppCounts | null;
    /** parametri REALMENTE in uso dal servizio (clampati/normalizzati): H-15 */
    params_effective?: SafeParamsEffective | null;
}

export interface SafeControl {
    id: number;
    status: SafeBotStatus;
    mode: SafeMode;
    params: Record<string, unknown> | null;
    stats: SafeStatsFull | null;
    error: string | null;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
    updated_at?: string | null;
}

export interface SafeTrade {
    id: number;
    event_id: string;
    event_name: string | null;
    sport: SafeSport;
    strategy: SafeStrategyKind;
    market_id: string | null;
    market_type: string | null;
    selection_id: number | null;
    selection_name: string | null;
    side: SafeSide;
    mode: SafeMode;
    price: number | null;
    size: number | null;
    liability: number | null;
    commission: number | null;
    minute_at_entry: number | null;
    score_at_entry: string | null;
    status: SafeTradeStatus;
    pnl: number;
    bet_id: string | null;
    placed_at: string;
    settled_at: string | null;
    origin: 'auto' | 'manual';
    /** id del trade CHIUSO da questa riga (gamba di copertura del cash out) */
    closes_trade_id: number | null;
    /** chiave del segnale che ha generato il trade (join con ActiveSignal.key) */
    signal_key: string | null;
    meta: Record<string, unknown> | null;
}

/** Aggregati della GIORNATA DI PIAZZAMENTO (Europe/Rome): fonte UNICA dei
 *  numeri della pagina. Le chiavi nuove arrivano con
 *  `migrations/safe_strategy_bot_v2.sql`: la UI deve funzionare anche senza
 *  (fallback ai campi vecchi / al calcolo lato client). */
export interface SafeAggregates {
    realized_today: number;
    realized_total: number;
    open_liability: number;
    open_count: number;
    won: number;
    lost: number;
    // ---- v2 (opzionali: migrazione non ancora applicata)
    /** liability delle riserve a esito IGNOTO (in verifica su Betfair) */
    reconciling_liability?: number;
    reconciling_count?: number;
    /** liability IMPEGNATA nella giornata (base dei cap di rischio) */
    day_liability?: number;
    day_liability_model?: number;
    day_trades?: number;
    legs_today?: number;
    events_today?: number;
    won_today?: number;
    lost_today?: number;
    /** 'YYYY-MM-DD' della giornata operativa secondo il DB */
    operating_day?: string;
}

/**
 * true = gli aggregati portano i CONTATORI DELLA GIORNATA della v2
 * (`migrations/safe_strategy_bot_v2.sql`). Senza migrazione la RPC vecchia
 * torna solo i sei campi v1: la pagina funziona comunque, ma V/P, operazioni,
 * partite e capitale impegnato sono STIMATI dal client sulle righe caricate
 * (ultime N, non tutta la giornata) e NON sono gli stessi numeri dello Storico.
 * La UI deve dirlo, non spacciarli per numeri del servizio.
 */
export function aggregatesHaveDay(agg: SafeAggregates | null | undefined): boolean {
    if (!agg) return false;
    return agg.won_today != null || agg.lost_today != null
        || agg.legs_today != null || agg.events_today != null
        || agg.day_liability != null;
}

/** Riga del log del servizio (`safe_strategy_activity`). */
export interface SafeActivityRow {
    id: number;
    ts: string | null;
    kind: string;
    payload: Record<string, unknown> | null;
}

export interface SafeState {
    control: SafeControl | null;
    trades: SafeTrade[];
    aggregates: SafeAggregates | null;
    // Le tre chiavi sotto arrivano con safe_strategy_bot_v2.sql: sono OPZIONALI
    // di proposito, così la UI (e i test) funzionano anche senza migrazione.
    /** ultime righe di attività del servizio (v2) */
    activity?: SafeActivityRow[];
    /** parametri realmente in uso (v2, o da control.stats) */
    params_effective?: SafeParamsEffective | null;
    /** giornata operativa dichiarata dal DB ('YYYY-MM-DD'); assente = romeDay() */
    operating_day?: string | null;
}

/**
 * I kind della coda `safe_strategy_requests`.
 *
 * 16/09 — `cashout_event` (CASH OUT GLOBALE della partita) e `riprendi_evento`
 * arrivano con `migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql`:
 * finche' quella migrazione non e' applicata il CHECK della tabella ammette
 * solo i primi tre e la RPC `safe_request` RIFIUTA gli altri due con
 * «kind non valido». L'errore si mostra, non si nasconde.
 */
export type SafeRequestKind = 'place' | 'cashout' | 'cancel'
    | 'cashout_event' | 'riprendi_evento';
/** 'rejected' = il servizio ha RIFIUTATO la richiesta con un motivo leggibile
 *  (in riconciliazione, ordine già a mercato, mercato sospeso, feed non fresco) */
export type SafeRequestStatus = 'pending' | 'processing' | 'done' | 'error' | 'rejected';
export interface SafeRequest {
    id: number;
    kind: SafeRequestKind;
    payload: Record<string, unknown> | null;
    status: SafeRequestStatus;
    result: Record<string, unknown> | null;
    created_at: string;
    updated_at: string | null;
}

export interface SafePlacePayload {
    event_id: string;
    event_name?: string | null;
    sport: SafeSport;
    market_id: string;
    market_type?: string | null;
    selection_id: number;
    selection_name?: string | null;
    side: SafeSide;
    price: number;
    size: number;
    strategy: SafeStrategyKind;
    signal_key?: string | null;
}

// --------------------------------------------------- opportunità di modello
/** tipo di opportunità: modello (λ Poisson), anomalia di prezzo (regola),
 *  combinazione a profitto bloccato (più gambe), tennis (modello punto). */
export type SafeOppKind = 'model' | 'anomaly' | 'combo' | 'tennis';
export const SAFE_OPP_KINDS: SafeOppKind[] = ['model', 'anomaly', 'combo', 'tennis'];
export type SafeAnomalyRule = 'ou_ladder' | 'decided' | 'mo_cs' | 'ht_open';
export type SafeComboType = 'dutch' | 'under_stack' | 'over_stack' | 'ou_span' | 'cs_cover';

export interface SafeOppCalibration {
    applied: boolean;
    family?: string | null;
    n?: number | null;
}

/** gamba di una combinazione: stake_ratio = quota dello stake totale (0-1) */
export interface SafeComboLeg {
    market_type: string;
    market_id: string;
    selection_id: number;
    selection_name: string | null;
    side: SafeSide;
    price: number;
    size_available: number | null;
    stake_ratio: number | null;
    stake: number | null;
}

/** riferimento di un'anomalia: la quota "sorella" che rende evidente l'errore */
export interface SafeAnomalyRef {
    market_type?: string | null;
    market_name?: string | null;
    selection_name?: string | null;
    line?: number | null;
    price?: number | null;
    side?: SafeSide | null;
}

export interface SafeTennisExtra {
    p_model_raw?: number | null;
    /** rischio ritiro stimato (0-1) */
    retire_risk?: number | null;
    best_of?: number | null;
    /** chi serve: 'p1' | 'p2' | nome */
    server?: string | null;
    /** true = momentum contro la selezione proposta */
    momentum_against?: boolean | null;
    sets?: { p1: number; p2: number } | null;
    games?: { p1: number; p2: number } | null;
}

export interface SafeOpportunity {
    /** assente nei payload vecchi = 'model' */
    kind?: SafeOppKind;
    market_type: string;
    market_name: string | null;
    line: number | null;
    market_id: string;
    selection_id: number;
    selection_name: string | null;
    side: SafeSide;
    price: number;
    size_available: number | null;
    p_model: number;
    p_implied: number;
    edge: number;
    ev: number;
    confidence: number;
    rationale: string | null;
    // ---- model
    p_model_raw?: number | null;
    calibration?: SafeOppCalibration | null;
    // ---- anomaly
    rule?: SafeAnomalyRule | string | null;
    /** distanza dalla quota di riferimento (frazione) */
    gap?: number | null;
    ref?: SafeAnomalyRef | string | null;
    /** CERT. 12/09 — da dove viene `p_model` di un'anomalia: 'modello' (stima
     *  del modello, piu' prudente del limite di mercato), 'riferimento' (limite
     *  implicito nella quota sorella) o 'punteggio' (esito gia' deciso). */
    p_source?: 'modello' | 'riferimento' | 'punteggio' | string | null;
    // ---- combo
    combo?: SafeComboType | string | null;
    legs?: SafeComboLeg[] | null;
    /** profitto BLOCCATO per € di stake totale (caso peggiore) */
    locked_profit_per_eur?: number | null;
    /** profitto per € nel caso migliore */
    best_case_per_eur?: number | null;
    total_stake?: number | null;
    /** CERT. 12/09 — il minimo Betfair vale per OGNI GAMBA: sotto questo totale
     *  una gamba resterebbe sotto il minimo e verrebbe RIFIUTATA dall'exchange,
     *  lasciando una posizione nuda (l'opposto del "rischio zero"). */
    min_total_stake?: number | null;
    /** stake minimo per singola gamba usato per il calcolo sopra */
    min_leg_stake?: number | null;
    /** false = eseguibile agli stake PUBBLICATI (total_stake); con un totale
     *  piu' alto la combinazione puo' comunque essere piazzabile */
    executable_whole?: boolean | null;
    /** false = il book non regge le gambe nemmeno al totale MINIMO: mai piazzabile intera */
    book_supports_min?: boolean | null;
    /** da dove viene `p_model` di una combo: 'book' (modello) o 'implicita' (quota) */
    p_model_source?: 'book' | 'implicita' | string | null;
    // ---- tennis
    extra?: SafeTennisExtra | null;
}

export interface SafeOpportunityPayload {
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    event_name?: string | null;
    lambdas?: { home?: number; away?: number } | null;
    source?: string | null;
    /** conteggi per tipo (servizio) */
    kinds?: SafeOppCounts | null;
    /** tennis: punteggio set/game della riga */
    sets?: { p1: number; p2: number } | null;
    games?: { p1: number; p2: number } | null;
    opps: SafeOpportunity[];
}

/** tipo di un'opportunità (payload vecchi senza `kind` = modello). */
export function oppKind(o: { kind?: SafeOppKind | string | null }): SafeOppKind {
    const k = o.kind;
    return k === 'anomaly' || k === 'combo' || k === 'tennis' ? k : 'model';
}

/** conteggio per tipo su un insieme di righe (somma dei payload). */
export function oppKindCounts(rows: { payload: SafeOpportunityPayload | null }[]): Record<SafeOppKind, number> {
    const out: Record<SafeOppKind, number> = { model: 0, anomaly: 0, combo: 0, tennis: 0 };
    for (const r of rows) {
        for (const o of (Array.isArray(r.payload?.opps) ? r.payload!.opps : [])) out[oppKind(o)] += 1;
    }
    return out;
}

/** Stake per gamba di una combinazione, scalato allo stake TOTALE scelto:
 *  stake_ratio se presente, altrimenti stake/total_stake del servizio,
 *  altrimenti parti uguali. Arrotondato ai centesimi, mai < 0. */
export function comboLegStakes(o: SafeOpportunity, totalStake: number): (SafeComboLeg & { stake: number })[] {
    const legs = Array.isArray(o.legs) ? o.legs : [];
    if (legs.length === 0) return [];
    const total = Number.isFinite(totalStake) && totalStake > 0 ? totalStake : 0;
    const svcTotal = Number(o.total_stake);
    const ratios = legs.map((l) => {
        const r = Number(l.stake_ratio);
        if (Number.isFinite(r) && r > 0) return r;
        const s = Number(l.stake);
        if (Number.isFinite(s) && s > 0 && Number.isFinite(svcTotal) && svcTotal > 0) return s / svcTotal;
        return 1 / legs.length;
    });
    const sum = ratios.reduce((a, b) => a + b, 0) || 1;
    return legs.map((l, i) => ({ ...l, stake: Math.round((total * ratios[i] / sum) * 100) / 100 }));
}

/** Profitto bloccato (peggiore) e migliore, per € e in € sullo stake totale. */
export function comboLock(o: SafeOpportunity, totalStake: number): {
    worstPerEur: number | null; bestPerEur: number | null; worstEur: number | null; bestEur: number | null;
} {
    // null/undefined = dato assente (Number(null) sarebbe 0: un lock "zero" falso)
    const w = o.locked_profit_per_eur == null ? NaN : Number(o.locked_profit_per_eur);
    const b = o.best_case_per_eur == null ? NaN : Number(o.best_case_per_eur);
    const t = Number.isFinite(totalStake) && totalStake > 0 ? totalStake : 0;
    const r2 = (x: number) => Math.round(x * 100) / 100;
    return {
        worstPerEur: Number.isFinite(w) ? w : null,
        bestPerEur: Number.isFinite(b) ? b : null,
        worstEur: Number.isFinite(w) ? r2(w * t) : null,
        bestEur: Number.isFinite(b) ? r2(b * t) : null,
    };
}

/** "Under 6.5 @1.01 → Under 7.5 @1.10": riferimento di un'anomalia. */
export function anomalyRefLabel(o: SafeOpportunity): string | null {
    const ref = o.ref;
    if (ref == null) return null;
    const own = `${o.selection_name ?? `#${o.selection_id}`} @${fmtOdds(o.price as number)}`;
    if (typeof ref === 'string') return `${ref} → ${own}`;
    const name = ref.selection_name ?? ref.market_name ?? ref.market_type ?? null;
    if (!name && ref.price == null) return null;
    const price = ref.price != null && Number.isFinite(Number(ref.price)) ? ` @${fmtOdds(Number(ref.price))}` : '';
    return `${name ?? '?'}${price} → ${own}`;
}

/** prefisso della chiave di idempotenza condivisa dalle gambe di una combinazione */
export function comboIdempotencyPrefix(eventId: string, o: SafeOpportunity, nowMs = Date.now()): string {
    const rnd = Math.random().toString(36).slice(2, 8);
    return `combo:${eventId}:${o.combo ?? 'combo'}:${nowMs.toString(36)}:${rnd}`;
}

export interface SafeOpportunityRow {
    event_id: string;
    sport: SafeSport;
    payload: SafeOpportunityPayload;
    updated_at: string | null;
}

/** punteggio di ordinamento delle opportunità: EV pesato dalla confidenza. */
export function oppScore(o: SafeOpportunity): number {
    const ev = Number(o.ev);
    const c = Number(o.confidence);
    return (Number.isFinite(ev) ? ev : 0) * (Number.isFinite(c) ? c : 0);
}

// -------------------------------------------------------------- parametri
// I parametri del BOT vivono sul DB (safe_strategy_control.params): è la fonte
// unica quando la riga di controllo esiste. Il radar client-side continua a
// usare i suoi parametri locali (localStorage) finché il bot non c'è.
export interface SafeBotParams extends SafeStrategyParams {
    /** cadenza del loop del servizio (s) */
    poll_interval_s: number;
    /** aliquota Betfair applicata al P&L positivo (%) */
    commission_pct: number;
    /** strategie abilitate al trading automatico */
    variants: VariantId[];
    max_open_trades: number;
    max_liability_per_trade: number;
    /** size abbinabile minima richiesta = fattore × stake */
    min_size_available_factor: number;
    /** cadenza del calcolo opportunità di modello (s) */
    opps_interval_s: number;
    auto_trade_opportunities: boolean;
    opps_min_confidence: number;
    opps_min_edge: number;
    opps_stake: number;
    /** auto-trade delle ANOMALIE di prezzo (regole) */
    auto_trade_anomalies: boolean;
    /** auto-trade delle COMBINAZIONI a profitto bloccato (tutte le gambe) */
    auto_trade_combos: boolean;
    /** auto-trade delle opportunità TENNIS */
    auto_trade_tennis: boolean;
    /** limiti di rischio del servizio */
    risk: SafeRiskParams;
    /** stake di default usato dal motore e proposto dalla UI sui segnali */
    stake: {
        /** € da bancare sui segnali LAY (BASE ed ESATTO, se non hanno il loro) */
        laySize: number;
        /** € da puntare sui segnali BACK (PUNTA e TENNIS, se non hanno il loro) */
        backSize: number;
        /**
         * B.5 (16/09) — STAKE PER STRATEGIA. `backSize` valeva insieme per
         * TENNIS e PUNTA: cambiarlo per una lo cambiava all'altra, in silenzio.
         * Questa mappa e' per NOME. Nasce VUOTA, e una chiave assente vuol dire
         * "usa quella per lato" — quindi nessun importo cambia da solo.
         * Specchio di `engine.DEFAULT_PARAMS['stake']['per_strategia']`.
         */
        per_strategia: Record<string, number>;
    };
}

export interface SafeRiskParams {
    /** liability massima impegnabile nella giornata (€) */
    daily_liability_cap: number;
    /** liability massima per evento (€) */
    per_event_liability_cap: number;
    /** trade massimi per evento */
    per_event_max_trades: number;
    /** correlazione massima ammessa fra posizioni sullo stesso evento (0-1) */
    correlated_cap: number;
    /** stop giornaliero: sotto questa perdita (€, negativa) nessun nuovo ingresso */
    daily_loss_stop: number;
    /** stake dei trade automatici di modello / anomalia / tennis (€) */
    model_stake: number;
    /** liability giornaliera massima dei trade di modello (€) */
    model_daily_liability_cap: number;
}

export const SAFE_RISK_DEFAULTS: SafeRiskParams = {
    daily_liability_cap: 500,
    per_event_liability_cap: 150,
    per_event_max_trades: 3,
    correlated_cap: 0.7,
    daily_loss_stop: -50,
    model_stake: 5,
    model_daily_liability_cap: 150,
};

// STESSI default del servizio (Betfair/safe_strategy/bot_service.DEFAULT_PARAMS):
// una chiave assente sul DB deve mostrare il valore con cui il bot gira davvero,
// e "Salva" non deve cambiarne il comportamento in silenzio (review 11/09 M1)
export const SAFE_BOT_DEFAULTS: SafeBotParams = {
    ...DEFAULT_PARAMS,
    poll_interval_s: 2,
    commission_pct: 5,
    variants: ['base', 'esatto', 'punta', 'tennis'],
    max_open_trades: 20,
    max_liability_per_trade: 300,
    min_size_available_factor: 1,
    opps_interval_s: 10,
    auto_trade_opportunities: false,
    opps_min_confidence: 0.7,
    opps_min_edge: 0.03,
    opps_stake: 5,
    auto_trade_anomalies: false,
    auto_trade_combos: false,
    auto_trade_tennis: false,
    risk: { ...SAFE_RISK_DEFAULTS },
    stake: { laySize: 2, backSize: 2, per_strategia: {} },
};

const ALL_VARIANTS: VariantId[] = ['base', 'esatto', 'punta', 'tennis'];

/**
 * La mappa stake-per-strategia ripulita, con le STESSE regole del servizio
 * (`engine._stake_per_strategia`): solo le quattro varianti del manuale, solo
 * numeri finiti e positivi. Quello che non si capisce cade, e una chiave
 * caduta vuol dire "usa quella per lato" — non spegne niente.
 */
function stakePerStrategia(raw: unknown): Record<string, number> {
    if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return {};
    const out: Record<string, number> = {};
    for (const v of ALL_VARIANTS) {
        const n = (raw as Record<string, unknown>)[v];
        if (typeof n === 'number' && Number.isFinite(n) && n > 0) out[v] = n;
    }
    return out;
}

function num(v: unknown, fallback: number): number {
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
function bool(v: unknown, fallback: boolean): boolean {
    return typeof v === 'boolean' ? v : fallback;
}

/** merge DIFENSIVO di params.risk: valori mancanti/malformati → default. */
export function mergeRiskParams(raw: unknown): SafeRiskParams {
    const r = (raw ?? {}) as Record<string, unknown>;
    return (Object.keys(SAFE_RISK_DEFAULTS) as (keyof SafeRiskParams)[]).reduce((acc, k) => {
        acc[k] = num(r[k], SAFE_RISK_DEFAULTS[k]);
        return acc;
    }, {} as SafeRiskParams);
}

/** merge DIFENSIVO dei parametri bot: valori mancanti/malformati → default. */
export function mergeBotParams(raw: unknown): SafeBotParams {
    const r = (raw ?? {}) as Record<string, unknown>;
    const strategies = (['base', 'esatto', 'punta', 'tennis'] as const).reduce((acc, k) => {
        acc[k] = { ...DEFAULT_PARAMS[k], ...((r[k] ?? {}) as object) } as never;
        return acc;
    }, {} as SafeStrategyParams);
    const variants = Array.isArray(r.variants)
        ? (r.variants as unknown[]).filter((v): v is VariantId => ALL_VARIANTS.includes(v as VariantId))
        : SAFE_BOT_DEFAULTS.variants;
    return {
        ...strategies,
        poll_interval_s: num(r.poll_interval_s, SAFE_BOT_DEFAULTS.poll_interval_s),
        commission_pct: num(r.commission_pct, SAFE_BOT_DEFAULTS.commission_pct),
        variants: variants.length ? variants : SAFE_BOT_DEFAULTS.variants,
        max_open_trades: num(r.max_open_trades, SAFE_BOT_DEFAULTS.max_open_trades),
        max_liability_per_trade: num(r.max_liability_per_trade, SAFE_BOT_DEFAULTS.max_liability_per_trade),
        min_size_available_factor: num(r.min_size_available_factor, SAFE_BOT_DEFAULTS.min_size_available_factor),
        opps_interval_s: num(r.opps_interval_s, SAFE_BOT_DEFAULTS.opps_interval_s),
        auto_trade_opportunities: bool(r.auto_trade_opportunities, SAFE_BOT_DEFAULTS.auto_trade_opportunities),
        opps_min_confidence: num(r.opps_min_confidence, SAFE_BOT_DEFAULTS.opps_min_confidence),
        opps_min_edge: num(r.opps_min_edge, SAFE_BOT_DEFAULTS.opps_min_edge),
        opps_stake: num(r.opps_stake, SAFE_BOT_DEFAULTS.opps_stake),
        auto_trade_anomalies: bool(r.auto_trade_anomalies, SAFE_BOT_DEFAULTS.auto_trade_anomalies),
        auto_trade_combos: bool(r.auto_trade_combos, SAFE_BOT_DEFAULTS.auto_trade_combos),
        auto_trade_tennis: bool(r.auto_trade_tennis, SAFE_BOT_DEFAULTS.auto_trade_tennis),
        risk: mergeRiskParams(r.risk),
        stake: {
            laySize: num((r.stake as Record<string, unknown> | undefined)?.laySize, SAFE_BOT_DEFAULTS.stake.laySize),
            backSize: num((r.stake as Record<string, unknown> | undefined)?.backSize, SAFE_BOT_DEFAULTS.stake.backSize),
            per_strategia: stakePerStrategia((r.stake as Record<string, unknown> | undefined)?.per_strategia),
        },
    };
}

/** Le SOLE condizioni di strategia (base/esatto/punta/tennis) normalizzate con
 *  `mergeParams`: chiavi ignote/null sparite, default applicati. Serve a
 *  confrontare server e radar sullo stesso piano — senza normalizzazione un
 *  payload server con una chiave in piu' non coincide MAI col locale e la
 *  sincronizzazione salva a ogni render (loop). */
export function strategyParamsOf(p: unknown): SafeStrategyParams {
    const r = (p ?? {}) as Record<string, unknown>;
    return mergeParams({ base: r.base, esatto: r.esatto, punta: r.punta, tennis: r.tennis });
}

/** true = stesse condizioni di strategia (confronto normalizzato). */
export function sameStrategyParams(a: unknown, b: unknown): boolean {
    return JSON.stringify(strategyParamsOf(a)) === JSON.stringify(strategyParamsOf(b));
}

// ------------------------------------------------------ cash out in corso
/** Cash out gia' IN VOLO per un trade (audit C-02).
 *
 *  "In volo" = ancora nessuna conferma:
 *    · richiesta 'cashout' pending/processing con quel trade_id;
 *    · gamba di chiusura con stato `pending` (ordine non ancora abbinato);
 *    · marker del servizio: meta.hedging / hedge_pending_ids / closing_status.
 *
 *  NON è in volo una chiusura GIÀ CONFERMATA (open/hedged/won/lost/void):
 *  prima qualunque chiusura non in errore spegneva il bottone per sempre e
 *  dopo una chiusura PARZIALE il residuo diventava inchiudibile dalla UI —
 *  in live metà della liability restava scoperta. */
export function cashoutInFlight(
    tradeId: number,
    requests: Pick<SafeRequest, 'kind' | 'payload' | 'status'>[],
    trades: { id: number; closes_trade_id: number | null; status: string; meta: Record<string, unknown> | null }[],
): boolean {
    for (const r of requests) {
        if (r.kind !== 'cashout') continue;
        if (r.status !== 'pending' && r.status !== 'processing') continue;
        if (Number((r.payload ?? {})['trade_id']) === tradeId) return true;
    }
    for (const t of trades) {
        // gamba di chiusura ANCORA da confermare: un secondo ordine adesso
        // raddoppierebbe la copertura
        if (t.closes_trade_id === tradeId && t.status === 'pending') return true;
        if (t.id === tradeId) {
            const m = t.meta ?? {};
            // marker scritti DAVVERO dal servizio (execution.apply_hedge_state):
            // chiusure in volo → hedge_pending_ids / closing_status 'pending'
            if (Boolean(m['hedging'])) return true;
            if (Array.isArray(m['hedge_pending_ids']) && (m['hedge_pending_ids'] as unknown[]).length > 0) return true;
            if (m['closing_status'] === 'pending') return true;
        }
    }
    return false;
}

// -------------------------------------------------- stato letto dal `meta`
/** Copertura registrata dal servizio (`meta.hedge`). `complete = false` con
 *  `fraction < 1` = posizione COPERTA IN PARTE: resta liability viva e il
 *  residuo deve restare chiudibile a mano (audit C-02 / M-06). */
export interface HedgeState {
    /** quota della posizione coperta (0-1) */
    fraction: number | null;
    /**
     * Liability ancora A RISCHIO (€) secondo il servizio. ATTENZIONE al
     * contratto: mentre una chiusura è IN VOLO (`meta.hedging = true`) questo
     * valore è la liability PIENA — il rischio scende a 0 solo a copertura
     * COMPLETA e CONFERMATA. La UI non deve mai far credere che il rischio sia
     * già ridotto per un ordine che non si è ancora abbinato.
     */
    remainingLiability: number | null;
    hedgedSize: number | null;
    residualSize: number | null;
    complete: boolean;
    /** true = copertura NON confermata: rischio ancora pieno */
    inFlight: boolean;
}

export function hedgeState(trade: { size: number | null; meta: Record<string, unknown> | null }): HedgeState | null {
    const m = trade.meta ?? {};
    const h = m['hedge'];
    const inFlight = m['hedging'] === true
        || m['closing_status'] === 'pending'
        || (Array.isArray(m['hedge_pending_ids']) && (m['hedge_pending_ids'] as unknown[]).length > 0);
    const n = (v: unknown) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v) : null);
    if (h && typeof h === 'object') {
        const r = h as Record<string, unknown>;
        const fraction = n(r.fraction);
        const complete = !inFlight && (r.complete === true || (fraction != null && fraction >= 0.999));
        return {
            fraction,
            remainingLiability: n(r.remaining_liability),
            hedgedSize: n(r.hedged_size),
            residualSize: n(r.residual_size),
            complete,
            inFlight,
        };
    }
    // percorso REST/paper: solo hedged_size / residual_size sull'apertura
    const p = partialHedge(trade);
    if (!p) return inFlight
        ? { fraction: null, remainingLiability: null, hedgedSize: null, residualSize: null, complete: false, inFlight }
        : null;
    return {
        fraction: p.size > 0 ? Math.round((p.hedged / p.size) * 1000) / 1000 : null,
        remainingLiability: null,
        hedgedSize: p.hedged,
        residualSize: p.residual,
        complete: false,
        inFlight,
    };
}

/** COMBINAZIONE rotta: una gamba non si è abbinata e il servizio sta chiudendo
 *  il resto (`meta.combo_incomplete`). Il profitto bloccato NON c'è più. */
export function comboIncomplete(trade: { meta: Record<string, unknown> | null }): boolean {
    return (trade.meta ?? {})['combo_incomplete'] === true;
}

/** Stop per perdita giornaliera: il servizio legge il VALORE ASSOLUTO come
 *  perdita, quindi 50 e −50 sono la stessa soglia (−50 €). La UI accetta
 *  entrambi i segni e mostra sempre quello vero. */
export function normalizeLossStop(v: number | null | undefined): number | null {
    if (v === null || v === undefined || (v as unknown) === '') return null;
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    return n === 0 ? 0 : -Math.abs(n);
}

/** Esposizione ATTUALE della posizione: se il servizio pubblica `meta.if_win` /
 *  `meta.if_lose` (o `best_case`/`worst_case`) sono già al netto della
 *  copertura parziale e vanno usati per l'anteprima del cash out, altrimenti
 *  si ricade sull'esposizione dell'ordine di apertura (M-06: mai proporre di
 *  chiudere l'esposizione PIENA di una posizione già coperta a metà). */
export function tradeExposureNow(
    trade: { side: string | null; price: number | null; size: number | null; meta: Record<string, unknown> | null },
): TradeExposure {
    const m = trade.meta ?? {};
    const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    const win = num(m['if_win']) ?? num(m['expected_if_win']);
    const lose = num(m['if_lose']) ?? num(m['expected_if_lose']);
    if (win != null && lose != null) {
        const r2 = (x: number) => Math.round(x * 100) / 100;
        return { win: r2(win), lose: r2(lose) };
    }
    return tradeExposure(trade);
}

/** Stato dell'USCITA AUTOMATICA (`meta.exit`): il servizio dichiara se sta
 *  ritentando, se aspetta un prezzo o se ha DEFINITIVAMENTE fallito (H-05:
 *  prima un'uscita fallita restava un normale "APERTO"). */
export interface ExitRunState {
    state: 'retrying' | 'failed' | 'waiting_price' | 'done' | null;
    attempts: number | null;
    residualAttempts: number | null;
    waitAttempts: number | null;
    kind: string | null;
    reason: string | null;
    lastError: string | null;
    nextRetryAt: string | null;
}

export function exitRunState(trade: { meta: Record<string, unknown> | null }): ExitRunState | null {
    const e = (trade.meta ?? {})['exit'];
    if (!e || typeof e !== 'object') return null;
    const r = e as Record<string, unknown>;
    const s = (v: unknown) => (v != null && String(v).trim() !== '' ? String(v) : null);
    const n = (v: unknown) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v) : null);
    const raw = String(r.state ?? '').trim().toLowerCase();
    const state = raw === 'retrying' || raw === 'failed' || raw === 'waiting_price' || raw === 'done'
        ? (raw as ExitRunState['state'])
        : null;
    if (state === null && r.kind == null && r.reason == null) return null;
    return {
        state,
        attempts: n(r.attempts),
        residualAttempts: n(r.residual_attempts),
        waitAttempts: n(r.wait_attempts),
        kind: s(r.kind),
        reason: s(r.reason),
        lastError: s(r.last_error),
        nextRetryAt: s(r.next_retry_at),
    };
}

/** Riserva a esito IGNOTO: l'ordine potrebbe essere VIVO su Betfair. Conta
 *  nella liability e non va mostrata come un normale "IN CORSO" (H-03). */
export function isReconciling(trade: { status: string; meta: Record<string, unknown> | null }): boolean {
    return trade.status === 'pending'
        && String((trade.meta ?? {})['reason'] ?? '') === 'place_exception_reconciling';
}

/** Errore DEFINITIVO dichiarato dal servizio (`meta.error_final`): la riga è
 *  terminale, non "in corso per sempre" (M-05). */
export function errorFinal(trade: { meta: Record<string, unknown> | null }): { at: string | null; detail: string | null } | null {
    const m = trade.meta ?? {};
    const flag = m['error_final'];
    if (!flag) return null;
    const at = m['error_at'] != null && String(m['error_at']).trim() !== '' ? String(m['error_at']) : null;
    const detail = typeof flag === 'string' && flag.trim() !== ''
        ? flag
        : (m['last_error'] != null ? String(m['last_error']) : null);
    return { at, detail };
}

/** Posizione VIVA che il servizio non vede più nel feed (`meta.blind_since`):
 *  nessuna uscita automatica possibile finché il feed non torna (H-18). */
export function blindSince(trade: { meta: Record<string, unknown> | null }): string | null {
    const v = (trade.meta ?? {})['blind_since'] ?? (trade.meta ?? {})['market_missing_since'];
    return v != null && String(v).trim() !== '' ? String(v) : null;
}

/** Esito della POSIZIONE (apertura + chiusure) dichiarato dal servizio:
 *  serve a NON mostrare "PERSO" sull'apertura di un green-up in utile e a non
 *  fare due toast per la stessa partita (M-04). */
export interface PositionOutcome {
    result: 'won' | 'lost' | 'flat' | 'void' | null;
    pnl: number | null;
    positionId: number | null;
}

export function positionOutcome(trade: { meta: Record<string, unknown> | null }): PositionOutcome | null {
    const m = trade.meta ?? {};
    const raw = String(m['position_result'] ?? '').trim().toLowerCase();
    const result = raw === 'won' || raw === 'lost' || raw === 'flat' || raw === 'void' ? raw : null;
    const pnlRaw = Number(m['position_pnl']);
    const pnl = Number.isFinite(pnlRaw) ? pnlRaw : null;
    const idRaw = Number(m['position_id']);
    const positionId = Number.isFinite(idRaw) ? idRaw : null;
    if (result === null && pnl === null) return null;
    return { result, pnl, positionId };
}

/** Tentativi di PIAZZAMENTO (`meta.place`): "3 tentativi, ritento alle 18:07". */
export interface PlaceState {
    attempts: number | null;
    lastError: string | null;
    lastTs: string | null;
    final: boolean;
    nextRetryAt: string | null;
}

export function placeState(trade: { meta: Record<string, unknown> | null }): PlaceState | null {
    const p = (trade.meta ?? {})['place'];
    if (!p || typeof p !== 'object') return null;
    const r = p as Record<string, unknown>;
    const s = (v: unknown) => (v != null && String(v).trim() !== '' ? String(v) : null);
    const n = (v: unknown) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v) : null);
    return {
        attempts: n(r.attempts), lastError: s(r.last_error), lastTs: s(r.last_ts),
        final: r.final === true, nextRetryAt: s(r.next_retry_at),
    };
}

/** Aliquota di commissione DEL TRADE (colonna `commission`, scritta al
 *  piazzamento): è quella con cui il P&L viene davvero tassato. Il parametro
 *  corrente del form può essere cambiato dopo (L-02). */
export function tradeCommission(
    trade: { commission: number | null } | null | undefined, fallbackPct: number,
): number {
    const c = Number(trade?.commission);
    if (Number.isFinite(c) && c > 0) return c;
    return fallbackPct;
}

/** true = la posizione è VIVA (liability a rischio): aperta, riserva a mercato
 *  o coperta SOLO IN PARTE. `hedged` completo e `error` definitivo NON sono
 *  vivi (audit M-15 / L-04 / M-05). */
export function isLivePosition(
    trade: { status: string; size: number | null; meta: Record<string, unknown> | null; closes_trade_id?: number | null },
): boolean {
    if (trade.closes_trade_id != null) return false;      // è una gamba di chiusura
    if (trade.status === 'open') return true;
    if (trade.status === 'pending') return isReconciling(trade) || !errorFinal(trade);
    if (trade.status === 'hedged') {
        const h = hedgeState(trade);
        return h != null && !h.complete;
    }
    return false;
}

// ------------------------------------------------------- freschezza feed
// Le soglie devono essere le STESSE del servizio, altrimenti la UI accende un
// bottone che il servizio rifiuta (o viceversa):
//   FEED_ROW_STALE_MS  <-> exits.FEED_FRESH_S    (20 s)
//   FEED_HARD_MAX_MS   <-> exits.FEED_HARD_MAX_S (120 s)
// Il test `soglie di freschezza allineate al servizio` le difende.
/** riga del feed piu' vecchia di cosi' = quote potenzialmente non aggiornate */
export const FEED_ROW_STALE_MS = 20_000;
/** TETTO DURO (M-24, `exits.FEED_HARD_MAX_S`): oltre questa eta' la riga non
 *  vale MAI, nemmeno con l'heartbeat dello scanner vivo. Il servizio rifiuta
 *  di usarla: la UI non deve mostrarne il prezzo come "prezzo di ora". */
export const FEED_HARD_MAX_MS = 120_000;
/** heartbeat scanner piu' vecchio di cosi' = PROCESSO scanner considerato non
 *  attivo. E' una soglia di VITA del processo (piu' tollerante del salto di un
 *  battito), non di freschezza delle quote: quella e' FEED_ROW_STALE_MS. */
export const SCANNER_STALE_MS = 45_000;

export interface FeedFreshness {
    /** eta' della riga del feed (s); null = riga senza timestamp */
    ageSec: number | null;
    scannerAlive: boolean;
    /** true = riga oltre il TETTO DURO (`FEED_HARD_MAX_MS`): il servizio non la
     *  usa in nessun caso, nemmeno con lo scanner vivo. */
    hardOld: boolean;
    /** true = i bottoni con soldi vanno spenti: riga vecchia E scanner morto,
     *  oppure riga oltre il tetto duro.
     *  Riga vecchia con scanner vivo = write-on-change (nulla e' cambiato). */
    stale: boolean;
}

export function feedFreshness(
    rowUpdatedAt: string | null | undefined,
    scannerUpdatedAt: string | null | undefined,
    nowMs: number,
): FeedFreshness {
    const rowMs = rowUpdatedAt ? Date.parse(rowUpdatedAt) : NaN;
    const ageSec = Number.isFinite(rowMs) ? Math.max(0, Math.round((nowMs - rowMs) / 1000)) : null;
    const hbMs = scannerUpdatedAt ? Date.parse(scannerUpdatedAt) : NaN;
    const scannerAlive = Number.isFinite(hbMs) && nowMs - hbMs <= SCANNER_STALE_MS;
    const rowOld = ageSec == null || ageSec * 1000 > FEED_ROW_STALE_MS;
    // M-24: il tetto duro vince sullo heartbeat. Con lo scanner vivo e la riga
    // di dieci minuti prima, "write-on-change" non spiega piu' niente: quella
    // partita non e' seguita e il prezzo mostrato sarebbe una bugia.
    const hardOld = ageSec != null && ageSec * 1000 > FEED_HARD_MAX_MS;
    return { ageSec, scannerAlive, hardOld, stale: hardOld || (rowOld && !scannerAlive) };
}

/** motivo (tooltip) per cui i bottoni con soldi sono spenti su un feed stantio */
export function staleReason(f: FeedFreshness | null | undefined): string | undefined {
    if (!f?.stale) return undefined;
    const eta = f.ageSec != null ? `${f.ageSec}s` : 'n/d';
    if (f.hardOld) {
        return `quote troppo vecchie (${eta}): oltre ${Math.round(FEED_HARD_MAX_MS / 1000)}s `
            + 'il servizio non le usa: questa partita non risulta seguita';
    }
    return `quote non aggiornate (${eta})`;
}

// -------------------------------------------------------------------- RPC
export async function activateSafe(mode: SafeMode, params?: Partial<SafeBotParams>): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_activate', {
        p_mode: mode, p_params: (params ?? null) as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function stopSafe(): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_stop', {});
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function updateSafeParams(params: Partial<SafeBotParams>): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_update_params', { p_params: params as never });
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function fetchSafeState(): Promise<SafeState> {
    const { data, error } = await supabase.rpc('get_safe_state', {});
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<SafeState>;
    const control = d.control ?? null;
    const agg = d.aggregates ?? null;
    return {
        control,
        trades: Array.isArray(d.trades) ? d.trades : [],
        aggregates: agg,
        // le tre chiavi sotto esistono solo con safe_strategy_bot_v2.sql: senza
        // migrazione si ricade su control.stats (params_effective lo scrive il
        // servizio) e su romeDay() lato client.
        activity: Array.isArray(d.activity) ? d.activity : [],
        params_effective: d.params_effective ?? control?.stats?.params_effective ?? null,
        operating_day: d.operating_day ?? agg?.operating_day ?? null,
    };
}

/** Attività del servizio. Prima la RPC dedicata (`get_safe_activity`, v2); se
 *  non esiste ancora si legge la tabella in SELECT (owner via RLS). Mai un
 *  errore in faccia all'utente: senza log la sezione resta vuota. */
export async function fetchSafeActivity(limit = 100, kinds?: string[]): Promise<SafeActivityRow[]> {
    const rpc = await supabase.rpc('get_safe_activity', {
        p_limit: limit, p_kinds: (kinds ?? null) as never,
    });
    if (!rpc.error && Array.isArray(rpc.data)) return rpc.data as unknown as SafeActivityRow[];
    const sel = await supabase
        .from('safe_strategy_activity')
        .select('id,ts,kind,payload')
        .order('id', { ascending: false })
        .limit(limit);
    if (sel.error) throw new Error(sel.error.message);
    return (sel.data ?? []) as unknown as SafeActivityRow[];
}

export async function fetchSafeTrades(limit = 300): Promise<SafeTrade[]> {
    const { data, error } = await supabase.rpc('get_safe_trades', { p_limit: limit });
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as SafeTrade[];
}

/** Accoda una richiesta operativa al servizio (place / cashout / cancel). */
export async function requestSafe(
    kind: SafeRequestKind, payload: Record<string, unknown> = {},
): Promise<number> {
    const { data, error } = await supabase.rpc('safe_request', {
        p_kind: kind, p_payload: payload as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as number;
}

/**
 * CASH OUT GLOBALE DELLA PARTITA (16/09).
 *
 * Accoda `cashout_event` con il SOLO `event_id`: quali righe chiudere lo
 * decide il servizio leggendo le sue tabelle, non il browser. Da quel momento
 * la partita e' marcata «chiusa dall'utente» e il bot non apre, non copre, non
 * esce e non piazza gambe di combo su di essa (`bot_service.segna_chiuso_dall_utente`).
 *
 * Nessuna seconda strada verso Betfair: e' la coda di sempre.
 */
export async function cashOutEvento(eventId: string): Promise<number> {
    return requestSafe('cashout_event', payloadCashoutEvento(eventId));
}

/** RIPRENDI: la partita torna in carico al bot. E' l'UNICO modo di spegnere il
 *  marcatore — niente scadenze, niente deduzioni automatiche. */
export async function riprendiEventoSafe(eventId: string): Promise<number> {
    return requestSafe('riprendi_evento', payloadRiprendiEvento(eventId));
}

/** Ultime richieste (feedback pending/done/error sui bottoni "Investi"). */
export async function fetchSafeRequests(limit = 30): Promise<SafeRequest[]> {
    const { data, error } = await supabase
        .from('safe_strategy_requests')
        .select('*')
        .order('id', { ascending: false })
        .limit(limit);
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as SafeRequest[];
}

// --------------------------------------------------------------- realtime
/** UN solo canale per control + trades + requests (mai N canali). */
export function subscribeSafeBot(onChange: () => void): () => void {
    const channel = supabase
        .channel('safe-bot')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_control' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_trades' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_requests' }, onChange)
        // H-16: il log del servizio va visto in tempo reale come i trade
        .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'safe_strategy_activity' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

/** Riga di safe_strategy_opportunities nel CONTRATTO della UI.
 *  Il servizio (bot_service.py) scrive ``payload.opportunities`` e ``lambdas``
 *  come lista ``[casa, trasferta]``; la UI legge ``payload.opps`` e
 *  ``lambdas.{home,away}``. Senza questa normalizzazione il dettaglio delle
 *  opportunità restava VUOTO mentre il pannello rischio (stats del servizio)
 *  le contava (11/09/2026). Idempotente: una riga già normalizzata resta uguale. */
export function normalizeOppRow<T extends { payload: unknown }>(row: T): T {
    const raw = (row.payload ?? {}) as Record<string, unknown>;
    const opps = Array.isArray(raw.opps) ? raw.opps
        : Array.isArray(raw.opportunities) ? raw.opportunities : [];
    let lambdas: unknown = raw.lambdas ?? null;
    if (Array.isArray(lambdas)) {
        const [home, away] = lambdas as unknown[];
        lambdas = { home: Number(home), away: Number(away) };
    }
    return { ...row, payload: { ...raw, opps, lambdas } };
}

/** Una riga di opportunità è ATTUALE se riscritta oggi (giornata operativa
 *  Europe/Rome) e da non più di OPP_ROW_MAX_AGE_MS: le partite finite (righe mai
 *  più riscritte) e i giorni passati NON sono opportunità — il passato sta nello
 *  Storico. Senza timestamp valido → non attuale. */
export const OPP_ROW_MAX_AGE_MS = 30 * 60_000;
export function isCurrentOppRow(row: { updated_at?: string | null }, nowMs: number, today: string): boolean {
    const iso = row.updated_at ?? null;
    if (!iso) return false;
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return false;
    if (nowMs - t > OPP_ROW_MAX_AGE_MS) return false;
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(t));
    const get = (k: string) => parts.find((p) => p.type === k)?.value ?? '';
    return `${get('year')}-${get('month')}-${get('day')}` === today;
}

export async function fetchOpportunities(): Promise<SafeOpportunityRow[]> {
    const { data, error } = await supabase.from('safe_strategy_opportunities').select('*');
    if (error) throw new Error(error.message);
    return ((data ?? []) as unknown as SafeOpportunityRow[]).map(normalizeOppRow);
}

export type SafeOppEvent =
    | { type: 'upsert'; row: SafeOpportunityRow }
    | { type: 'delete'; eventId: string };

export function subscribeOpportunities(cb: (ev: SafeOppEvent) => void): () => void {
    const channel = supabase
        .channel(`safe_strategy_opportunities:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'safe_strategy_opportunities' },
            (payload) => {
                if (payload.eventType === 'DELETE') {
                    const old = payload.old as { event_id?: string } | null;
                    if (old?.event_id) cb({ type: 'delete', eventId: old.event_id });
                    return;
                }
                const next = payload.new as SafeOpportunityRow | null;
                if (next && next.event_id) cb({ type: 'upsert', row: normalizeOppRow(next) });
            },
        )
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

// ------------------------------------------------------------- matematica
/** Equity curve: cumulato del P&L sui trade REGOLATI, ordinati per settled_at.
 *  (stessa funzione di omega.ts, generica sul tipo di trade) */
export function buildEquitySeries(
    trades: { settled_at: string | null; status: string; pnl: number }[],
): { t: number; v: number; iso: string }[] {
    const settled = trades
        .filter((t) => t.settled_at && ['won', 'lost', 'void', 'hedged'].includes(t.status))
        .sort((a, b) => new Date(a.settled_at as string).getTime() - new Date(b.settled_at as string).getTime());
    let cum = 0;
    return settled.map((t) => {
        cum += Number(t.pnl) || 0;
        return { t: new Date(t.settled_at as string).getTime(), v: cum, iso: t.settled_at as string };
    });
}

/** POSIZIONI regolate NUOVE rispetto a `seen` (aggiornato in place).
 *  Al primo caricamento memorizza lo storico e ritorna [] (niente toast).
 *
 *  Solo APERTURE (`closes_trade_id == null`): una gamba di chiusura non è una
 *  posizione a sé e faceva scattare un SECONDO toast per la stessa partita —
 *  con l'apertura di un green-up in utile mostrata come "PERSO" (audit M-04). */
export function detectSettlements(
    trades: SafeTrade[], seen: Set<number>, firstLoad: boolean,
): SafeTrade[] {
    const settled = trades.filter(
        (t) => t.closes_trade_id == null
            && t.settled_at && ['won', 'lost', 'void', 'hedged'].includes(t.status),
    );
    if (firstLoad) {
        settled.forEach((t) => seen.add(t.id));
        return [];
    }
    const fresh: SafeTrade[] = [];
    for (const t of settled) {
        if (seen.has(t.id)) continue;
        seen.add(t.id);
        fresh.push(t);
    }
    return fresh;
}

// ------------------------------------------- esito delle richieste operative
export type RequestTone = 'pending' | 'ok' | 'rejected' | 'error';

export interface RequestOutcome {
    tone: RequestTone;
    /** etichetta corta in ITALIANO per il badge */
    label: string;
    /** messaggio del servizio (già in italiano) o motivo/dettaglio */
    message: string | null;
    /** true = esito definitivo (la UI può notificarlo una volta sola) */
    settled: boolean;
    tradeId: number | null;
    /** da dove venivano le quote usate per chiudere ('feed' | 'rest') */
    source: string | null;
    /** testo italiano della sorgente, da mostrare accanto all'esito */
    sourceLabel: string | null;
}

const REQUEST_LABEL: Record<RequestTone, string> = {
    pending: 'in coda', ok: 'eseguito', rejected: 'rifiutato', error: 'errore',
};

/** Esito di UNA richiesta operativa, sempre con un messaggio leggibile.
 *  Il servizio scrive `result.message` in italiano più `reason`/`detail`:
 *  prima la UI mostrava solo "errore" senza dire perché (audit L-07/M-21). */
export function requestOutcome(req: SafeRequest | null | undefined): RequestOutcome | null {
    if (!req) return null;
    const res = (req.result ?? {}) as Record<string, unknown>;
    const txt = (v: unknown) => (v != null && String(v).trim() !== '' ? String(v).trim() : null);
    const message = txt(res['message']) ?? txt(res['error']) ?? txt(res['detail']) ?? txt(res['reason']);
    const tradeRaw = Number(res['trade_id'] ?? (req.payload ?? {})['trade_id']);
    const tradeId = Number.isFinite(tradeRaw) ? tradeRaw : null;
    // il servizio può marcare il rifiuto nello stato OPPURE nel result
    const rejected = req.status === 'rejected' || res['rejected'] != null
        || String(res['status'] ?? '').toLowerCase() === 'rejected';
    const tone: RequestTone = req.status === 'pending' || req.status === 'processing'
        ? 'pending'
        : rejected ? 'rejected'
            : req.status === 'error' || res['error'] != null ? 'error' : 'ok';
    const source = txt(res['source']);
    const sourceLabel = source === 'feed' ? 'quote dal feed dello scanner'
        : source === 'rest' ? 'quote dal book Betfair'
            : null;
    return {
        tone,
        label: REQUEST_LABEL[tone],
        message: message && sourceLabel ? `${message} (${sourceLabel})` : message,
        settled: tone !== 'pending',
        tradeId,
        source,
        sourceLabel,
    };
}

/** Ultima richiesta (di qualsiasi tipo, o del solo `kind`) su un trade. */
export function lastRequestFor(
    tradeId: number, requests: SafeRequest[], kind?: SafeRequestKind,
): SafeRequest | null {
    let best: SafeRequest | null = null;
    for (const r of requests) {
        if (kind && r.kind !== kind) continue;
        if (Number((r.payload ?? {})['trade_id']) !== tradeId) continue;
        if (!best || r.id > best.id) best = r;
    }
    return best;
}

export interface TradeExposure {
    /** P&L se la SELEZIONE vince */
    win: number;
    /** P&L se la SELEZIONE perde */
    lose: number;
}

/** Esposizione di un trade sulla SUA selezione (arrotondata ai centesimi):
 *    LAY  €S @L → vince: −S×(L−1) · perde: +S
 *    BACK €S @B → vince: +S×(B−1) · perde: −S
 *  Prezzo/size non validi → {0,0} (nessuna esposizione mostrabile). */
export function tradeExposure(
    trade: { side: string | null; price: number | null; size: number | null },
): TradeExposure {
    const price = Number(trade.price);
    const size = Number(trade.size);
    if (!Number.isFinite(price) || price <= 1 || !Number.isFinite(size) || size <= 0) {
        return { win: 0, lose: 0 };
    }
    const r2 = (x: number) => Math.round(x * 100) / 100;
    if (trade.side === 'lay') return { win: r2(-size * (price - 1)), lose: r2(size) };
    return { win: r2(size * (price - 1)), lose: r2(-size) };
}

// ------------------------------------------------ trade di modello: meta
/** stato di ATTESA di un trade di modello: il servizio tiene la posizione
 *  perché il margine è ampio (meta.exit_hold scritto a ogni ciclo). */
export interface TradeHold {
    reason: string | null;
    /** probabilità di perdita stimata (0-1) */
    pLose: number | null;
    source: string | null;
    /** P&L bloccabile ora, se il servizio lo pubblica */
    locked: number | null;
    /** EV del tenere la posizione */
    evHold: number | null;
    ts: string | null;
}

export function tradeHold(trade: { meta: Record<string, unknown> | null }): TradeHold | null {
    const h = (trade.meta ?? {})['exit_hold'];
    if (!h || typeof h !== 'object') return null;
    const r = h as Record<string, unknown>;
    const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    const s = (v: unknown) => (v != null && String(v).trim() !== '' ? String(v) : null);
    return {
        reason: s(r.reason), pLose: n(r.p_lose), source: s(r.source),
        locked: n(r.locked), evHold: n(r.ev_hold), ts: s(r.ts),
    };
}

/**
 * Motivo di attesa in italiano.
 *
 * CONTRATTO REALE (certificato 11/09): `exits.decide_time_exit` e
 * `_write_model_hold` scrivono FRASI ITALIANE COMPLETE, non codici brevi
 * (es. "margine ampio: P(perdita)=0.4%, tengo fino al settlement",
 * "tenere non rende: EV(tengo)=+1,50 € vs bloccato -0,20 €, ...",
 * "modello: tengo"). Il fallback `?? reason` e' quindi la via NORMALE.
 * La mappa qui sotto resta come ALIAS DIFENSIVO per i codici brevi usati in
 * passato (e da eventuali altri produttori): non deve far credere che il
 * servizio scriva quelle chiavi.
 */
const HOLD_REASON_IT: Record<string, string> = {
    wide_margin: 'margine ampio', margin: 'margine ampio', ev_positive: 'EV a favore',
    low_risk: 'rischio basso', no_liquidity: 'liquidità assente', residual: 'residuo da chiudere',
    waiting_settle: 'attesa conferma punteggio', take_profit_wait: 'attesa incasso',
};
export function holdReasonLabel(reason: string | null): string {
    if (!reason) return 'in attesa';
    return HOLD_REASON_IT[reason.trim().toLowerCase()] ?? reason;
}
/** true se il motivo è una frase libera del servizio che già contiene la P(perdita):
 *  la tabella non deve accodarla una seconda volta. */
export function holdReasonHasP(reason: string | null): boolean {
    return !!reason && /p\(perdita\)/i.test(reason);
}

/** P(perdita) all'ingresso di un trade di modello (meta.p_lose_entry) */
export function pLoseEntry(trade: { meta: Record<string, unknown> | null }): number | null {
    const v = Number((trade.meta ?? {})['p_lose_entry']);
    return Number.isFinite(v) ? v : null;
}

/** tipo di opportunità che ha generato un trade di modello (meta.kind) */
export function tradeOppKind(trade: { strategy: string; meta: Record<string, unknown> | null }): SafeOppKind | null {
    if (trade.strategy !== 'model') return null;
    return oppKind({ kind: (trade.meta ?? {})['kind'] as string | undefined });
}

// ------------------------------------------- gambe di chiusura (sub-righe)
export interface TradeGroup<T> {
    trade: T;
    /** gambe che CHIUDONO questo trade (closes_trade_id = trade.id), in ordine di id */
    closes: T[];
}

/** Raggruppa le gambe di chiusura sotto il trade che chiudono: la tabella
 *  mostra la chiusura come sub-riga "↳" attaccata all'apertura, MAI come un
 *  trade a sé (un back a 4.90 accanto a un lay a 55 confonde). Una chiusura
 *  il cui trade aperto non è nella lista resta in coda, da sola. */
export function groupClosingLegs<T extends { id: number; closes_trade_id?: number | null }>(trades: T[]): TradeGroup<T>[] {
    const byParent = new Map<number, T[]>();
    const orphans: T[] = [];
    const ids = new Set(trades.map((t) => t.id));
    for (const t of trades) {
        const p = t.closes_trade_id ?? null;
        if (p == null) continue;
        if (!ids.has(p)) { orphans.push(t); continue; }
        const list = byParent.get(p) ?? [];
        list.push(t);
        byParent.set(p, list);
    }
    const out: TradeGroup<T>[] = [];
    for (const t of trades) {
        if (t.closes_trade_id != null) continue;
        out.push({ trade: t, closes: (byParent.get(t.id) ?? []).sort((a, b) => a.id - b.id) });
    }
    for (const o of orphans) out.push({ trade: o, closes: [] });
    return out;
}

/** ALIAS storico di `fmtMoney` (lib/format.ts): "−22,10 €".
 *  Unica differenza conservata per i chiamanti esistenti: un valore assente
 *  viene letto come 0 invece di "—". Per i componenti NUOVI usa `fmtMoney`. */
export function fmtEurIt(v: number | null | undefined, signed = false): string {
    return fmtMoney(v ?? 0, { signed });
}
/** ALIAS storico di `fmtOdds` (lib/format.ts): "4,90" / "—". */
export const fmtOddsIt = fmtOdds;

/** Tooltip della copertura: spiega in una riga cosa e' successo. */
export function hedgeTooltip(
    open: { side: string; price: number | null },
    close: { side: string; price: number | null } | null | undefined,
): string {
    const os = open.side === 'lay' ? 'lay' : 'back';
    const cs = close ? (close.side === 'lay' ? 'lay' : 'back') : (os === 'lay' ? 'back' : 'lay');
    const op = fmtOddsIt(open.price);
    const cp = close ? fmtOddsIt(close.price) : 'mercato';
    return `il ${os} a ${op} è stato coperto con un ${cs} a ${cp} sulla stessa selezione: esito identico su ogni risultato`;
}

/** Cash out limitato dalla liquidità: la gamba di chiusura è stata ridotta.
 *  Il servizio scrive meta.size_capped_from (stake richiesto) sulla riga di
 *  chiusura → la UI deve dire "parziale", mai far credere a un green pieno. */
export function cappedFrom(trade: { meta: Record<string, unknown> | null }): number | null {
    const v = Number((trade.meta ?? {})['size_capped_from']);
    return Number.isFinite(v) && v > 0 ? v : null;
}

/** Copertura PARZIALE letta dall'APERTURA (meta.hedged_size / residual_size, che il
 *  servizio aggiorna SEMPRE, anche nel percorso REST/paper dove size_capped_from
 *  non arriva sulla chiusura — review 11/09 M4). null = copertura completa o
 *  nessuna copertura; altrimenti {hedged, residual, size}. */
export function partialHedge(opening: { size: number | null; meta: Record<string, unknown> | null }): { hedged: number; residual: number; size: number } | null {
    const m = opening.meta ?? {};
    const hedged = Number(m['hedged_size']);
    const residual = Number(m['residual_size']);
    const size = Number(opening.size ?? 0);
    if (!Number.isFinite(hedged) || hedged <= 0) return null;
    if (!Number.isFinite(residual) || residual <= 0.01) return null;
    return { hedged, residual, size };
}

// ------------------------------------------------------------ book LIVE
/** Ruolo Match Odds di un NOME selezione dentro il payload dello scanner.
 *  Calcio: casa / pareggio / ospite · Tennis: p1 / p2. null = nome ignoto. */
function moRole(
    payload: CalcioScanPayload | TennisScanPayload, name: string,
): ScanOddsPair | null {
    const n = norm(name);
    if (!n) return null;
    const o = payload.odds as Record<string, ScanOddsPair | null> | null;
    if (!o) return null;
    if ('home' in payload) {
        const p = payload as CalcioScanPayload;
        if (n === norm(p.home)) return o.home ?? null;
        if (n === norm(p.away)) return o.away ?? null;
        if (n === 'the draw' || n === 'draw' || n === 'pareggio') return o.draw ?? null;
        return null;
    }
    const p = payload as TennisScanPayload;
    if (n === norm(p.p1)) return o.p1 ?? null;
    if (n === norm(p.p2)) return o.p2 ?? null;
    return null;
}

/** Runner Match Odds (id + prezzi) di una selezione: prima l'override
 *  `mo_selections` se lo scanner lo pubblica, poi `odds.<lato>.selection_id`
 *  che e' quello che il feed odierno espone per calcio e tennis. */
function moRunner(
    payload: CalcioScanPayload | TennisScanPayload,
    by: { name?: string | null; selectionId?: number | null },
): ScanCsSelection | null {
    const sels = payload.mo_selections;
    if (Array.isArray(sels)) {
        const hit = sels.find((s) =>
            (by.selectionId != null && Number(s.selection_id) === Number(by.selectionId))
            || (by.name != null && norm(s.name) === norm(by.name)));
        if (hit) return hit;
    }
    if (by.name != null) {
        const pair = moRole(payload, by.name);
        if (pair) return { ...pair, selection_id: Number(pair.selection_id ?? 0), name: by.name };
    }
    if (by.selectionId != null) {
        const o = payload.odds as Record<string, ScanOddsPair | null> | null;
        for (const pair of Object.values(o ?? {})) {
            if (pair && Number(pair.selection_id) === Number(by.selectionId)) {
                return { ...pair, selection_id: Number(by.selectionId), name: null };
            }
        }
    }
    return null;
}

/** Book LIVE della selezione di un trade, letto dal feed dello scanner. */
export interface TradeBook {
    back: number | null;
    lay: number | null;
    /** EUR abbinabili al miglior prezzo (assenti nei payload vecchi) */
    backSize?: number | null;
    laySize?: number | null;
    /** mercato da cui arriva il prezzo (tooltip: corrisponde a Betfair) */
    marketId?: string | null;
    /** stato del mercato: 'OPEN' · 'SUSPENDED' · 'CLOSED' */
    status?: string | null;
    /** stato del runner ('ACTIVE', 'REMOVED', 'WINNER'…) */
    runnerStatus?: string | null;
    /** blocco del feed usato ('match_odds' | 'ou' | 'btts' | 'cs' | …) */
    source?: string;
}

/** linea Over/Under dal market_type Betfair: 'OVER_UNDER_35' → 3.5 */
function ouLineOf(marketType: string | null | undefined): number | null {
    const m = /^OVER_UNDER_(\d)(\d)$/.exec(String(marketType ?? '').toUpperCase().trim());
    return m ? Number(`${m[1]}.${m[2]}`) : null;
}

function bookOf(sel: ScanCsSelection, block: ScanMarketBlock | null, source: string): TradeBook {
    return {
        back: sel.back ?? null,
        lay: sel.lay ?? null,
        backSize: sel.back_size ?? null,
        laySize: sel.lay_size ?? null,
        marketId: block?.market_id ?? null,
        status: block?.status ?? null,
        runnerStatus: sel.runner_status ?? null,
        source,
    };
}

/** nome del blocco dal suo market_type (per il tooltip) */
function blockSource(block: ScanMarketBlock): string {
    const mt = String(block.market_type ?? '').toUpperCase();
    if (mt.startsWith('OVER_UNDER')) return 'ou';
    if (mt === 'BOTH_TEAMS_TO_SCORE') return 'btts';
    if (mt === 'HALF_TIME') return 'ht_result';
    return mt ? mt.toLowerCase() : 'feed';
}

/**
 * Miglior back/lay della selezione di un trade dal feed dello scanner, su
 * QUALSIASI mercato che il feed pubblica (audit R1).
 *
 * Ordine di risoluzione, dal più affidabile:
 *   1. `market_id` del trade = `market_id` di un blocco del payload — vale per
 *      Correct Score, Half Time Score, Over/Under (ogni linea è un mercato a
 *      sé), Gol/NoGol, 1X2 primo tempo e ogni blocco futuro;
 *   2. Match Odds (calcio e tennis: gli id stanno in `odds.<lato>.selection_id`);
 *   3. per TIPO di mercato: CS / HT score / la linea O/U giusta / BTTS / HALF_TIME;
 *   4. ultimo tentativo, solo se il trade NON porta un market_id: la selezione
 *      compare in UN SOLO blocco del feed (ambiguo se in più di uno → niente).
 *
 * null = il feed non ha quel mercato → il cash out resta disabilitato. Mai
 * "n/d" quando il prezzo c'è: i trade manuali su Over/Under (#39, #40) non
 * avevano cash out pur avendo il mercato nel feed con quote di 2 secondi.
 */
export function safeTradeBook(
    trade: { market_id?: string | null; market_type: string | null; selection_id: number | null; selection_name: string | null },
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
): TradeBook | null {
    if (!payload) return null;
    const type = (trade.market_type ?? '').toUpperCase();
    const by = { selectionId: trade.selection_id, name: trade.selection_name };

    // 1. per market_id: il legame più forte fra riga del DB e feed.
    //    Una linea O/U già DECISA dal punteggio (tenuta nel feed solo per una
    //    posizione Mike) non è un prezzo di uscita: si scarta.
    const byId = scanBlockByMarketId(payload, trade.market_id ?? null);
    if (byId && isUsableBlock(byId)) {
        const sel = blockSelection(byId, by);
        if (sel) return bookOf(sel, byId, blockSource(byId));
    }
    if (trade.market_id && payload.mo_market_id
        && String(payload.mo_market_id) === String(trade.market_id)) {
        const r = moRunner(payload, by);
        if (r) return bookOf(r, { market_id: payload.mo_market_id, status: payload.mo_status ?? null }, 'match_odds');
    }

    // 2. Match Odds per tipo (calcio e tennis)
    if (type.includes('MATCH_ODDS') || type === '1X2') {
        const r = moRunner(payload, by);
        if (r) return bookOf(r, { market_id: payload.mo_market_id, status: payload.mo_status ?? null }, 'match_odds');
    }

    // 3. per TIPO di mercato dentro i blocchi del calcio
    if ('cs' in payload) {
        const p = payload as CalcioScanPayload;
        if (trade.selection_id != null && (type.includes('HALF_TIME_SCORE') || type === 'HT_CS')) {
            const s = htSelection(p, trade.selection_id);
            if (s) return bookOf(s, p.ht as ScanMarketBlock | null, 'ht');
        }
        if (trade.selection_id != null && (type.includes('CORRECT_SCORE') || type === 'CS')) {
            const s = csSelection(p, trade.selection_id);
            if (s) return bookOf(s, p.cs as ScanMarketBlock | null, 'cs');
        }
        if (type.startsWith('OVER_UNDER')) {
            const line = ouLineOf(type);
            const blocks = (Array.isArray(p.ou) ? p.ou : []).filter(Boolean) as ScanMarketBlock[];
            const wanted = (line != null
                ? blocks.filter((b) => Number(b.line) === line)
                : blocks).filter(isUsableBlock);
            for (const b of wanted) {
                const sel = blockSelection(b, by);
                if (sel) return bookOf(sel, b, 'ou');
            }
        }
        if (type === 'BOTH_TEAMS_TO_SCORE' || type === 'BTTS') {
            const sel = blockSelection(p.btts, by);
            if (sel) return bookOf(sel, p.btts ?? null, 'btts');
        }
        if (type === 'HALF_TIME' || type === 'HT_1X2' || type === 'HALF_TIME_RESULT') {
            const sel = blockSelection(p.ht_result, by);
            if (sel) return bookOf(sel, p.ht_result ?? null, 'ht_result');
        }
    }

    // 4. senza market_id: la selezione in UN SOLO blocco (mai indovinare)
    if (!trade.market_id && trade.selection_id != null) {
        const hits = usableMarketBlocks(payload)
            .map((b) => ({ b, sel: blockSelection(b, { selectionId: trade.selection_id }) }))
            .filter((x) => x.sel !== null);
        if (hits.length === 1) {
            return bookOf(hits[0].sel as ScanCsSelection, hits[0].b, blockSource(hits[0].b));
        }
    }
    return null;
}

/** true = mercato NON operabile adesso (sospeso/chiuso o runner rimosso):
 *  il servizio rifiuterebbe la chiusura con "mercato sospeso" (M-23). */
export function marketBlocked(book: TradeBook | null | undefined): string | null {
    if (!book) return null;
    const st = String(book.status ?? '').toUpperCase();
    if (st === 'SUSPENDED') return 'mercato sospeso';
    if (st === 'CLOSED' || st === 'INACTIVE') return 'mercato chiuso';
    const rs = String(book.runnerStatus ?? '').toUpperCase();
    if (rs === 'REMOVED' || rs === 'REMOVED_VACANT') return 'selezione rimossa';
    return null;
}

// -------------------------------------------------- risoluzione mercato segnale
/** Coordinate di mercato con cui piazzare un segnale del radar. */
export interface SignalPlacement {
    market_id: string;
    market_type: string;
    selection_id: number;
    selection_name: string | null;
    /** best price e size ABBINABILE sul lato da operare (live) */
    price: number | null;
    size_available: number | null;
}

function norm(s: string | null | undefined): string {
    return (s ?? '').trim().toLowerCase();
}

/** Risolve market_id/selection_id di un segnale usando il feed dello scanner.
 *  · variante 'esatto' → Correct Score, selezione "Any Other Home/Away Win"
 *  · base / punta / tennis → Match Odds, id dal lato corrispondente al NOME
 *  null = il feed non espone ancora l'id: la UI mostra l'azione disabilitata,
 *  mai indovina. */
export function resolveSignalPlacement(
    signal: {
        variant: string; subId?: string; side: 'BACK' | 'LAY' | null; selection?: string | null;
    },
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
): SignalPlacement | null {
    if (!payload) return null;
    const lay = signal.side === 'LAY';
    const pick = (sel: ScanCsSelection, marketId: string, type: string): SignalPlacement | null => {
        const selectionId = Number(sel.selection_id);
        if (!Number.isFinite(selectionId) || selectionId <= 0) return null;
        return {
            market_id: marketId,
            market_type: type,
            selection_id: selectionId,
            selection_name: sel.name ?? null,
            price: (lay ? sel.lay : sel.back) ?? null,
            size_available: (lay ? sel.lay_size : sel.back_size) ?? null,
        };
    };

    if (signal.variant === 'esatto') {
        const cs = (payload as CalcioScanPayload).cs;
        const sels = cs?.selections;
        if (!cs?.market_id || !Array.isArray(sels)) return null;
        const want = signal.subId === 'away' ? /any other away/i : /any other home/i;
        const byName = signal.selection
            ? sels.find((s) => norm(s.name) === norm(signal.selection))
            : undefined;
        const sel = byName ?? sels.find((s) => want.test(s.name ?? ''));
        return sel ? pick(sel, cs.market_id, 'CORRECT_SCORE') : null;
    }

    const marketId = payload.mo_market_id;
    if (!marketId || !signal.selection) return null;
    const runner = moRunner(payload, { name: signal.selection });
    return runner ? pick(runner, marketId, 'MATCH_ODDS') : null;
}


// ---------------------------------------------------------------------------
// CERT. 14/09 — PERCORSO DI ESECUZIONE: come esce davvero l'ordine
// Due percorsi diversi, e il trader deve sapere quale sta guidando:
//   · CODA (stream): l'ordine passa dal runner flumine. E' l'unico che sa
//     lasciare un ordine A RIPOSO sul book (place-and-trim per gli importi
//     sotto il minimo) e l'unico che riceve il fill spinto dall'order stream.
//   · REST: chiamata diretta a Betfair, FILL OR KILL. Immediato o annullato.
// Le quattro strategie del manuale sono TAKER su ingresso e uscita, quindi su
// REST eseguono identiche. Cambia solo il place-and-trim, che su REST usa la
// sequenza sincrona a tre chiamate invece della coda.
// ---------------------------------------------------------------------------

/** oltre questa eta' il runner e' considerato GIU' (stesso numero del backend:
 *  `omega_service.RUNNER_HB_MAX_AGE_S`). Se i due divergono, la pagina dice una
 *  cosa e il servizio ne fa un'altra. */
export const RUNNER_HB_MAX_AGE_S = 90;

export interface RunnerState {
    /** ultimo battito del runner flumine (ISO) o null se non ha mai battuto */
    ts: string | null;
    /** modalita' ordini del runner: 'PAPER' | 'LIVE' | null */
    mode: string | null;
    /** eta' del battito in secondi; null = mai battuto */
    ageS: number | null;
    /**
     * true = il PROCESSO e' vivo (battito fresco).
     *
     * ⚠️ NON vuol dire che la coda ordini funzioni. Dal 14/09 il runner scrive
     * il battito anche mentre e' parcheggiato nel loop idle, e in quello stato
     * `live_order_worker` — che nasce dentro il framework, come il battito
     * prima — NON esiste: la coda non ha nessuno dall'altro capo. Per sapere
     * se la coda e' utilizzabile serve `streaming`, non questo.
     */
    up: boolean;
    /**
     * quante partite sono davvero agganciate allo stream (`live_follow` in
     * STREAMING). 0 con `up` true = runner VIVO MA IN ATTESA.
     *
     * OPZIONALE di proposito: chi costruisce uno stato senza questo campo non
     * deve rompersi, e l'assenza vale ATTESA (`runnerPhase`), mai streaming.
     * Il verso del ripiego e' quello prudente: un campo dimenticato non puo'
     * far credere che la coda ordini sia utilizzabile quando non lo e'.
     */
    streaming?: number | null;
}

/** I tre stati del runner, che non sono due. */
export type RunnerPhase = 'off' | 'idle' | 'streaming';

export function runnerPhase(r: RunnerState): RunnerPhase {
    if (!r.up) return 'off';
    // `null` = non l'abbiamo letto: si assume ATTESA, non streaming. Fail-closed
    // come il gate del backend: un dubbio non puo' concedere la coda.
    return (r.streaming ?? 0) > 0 ? 'streaming' : 'idle';
}

export function runnerStateFrom(
    row: { ts?: string | null; mode?: string | null } | null | undefined,
    nowMs: number = Date.now(),
    streaming: number | null = null,
): RunnerState {
    const ts = row?.ts ?? null;
    const t = ts ? Date.parse(ts) : NaN;
    const ageS = Number.isFinite(t) ? Math.max(0, (nowMs - t) / 1000) : null;
    return {
        ts,
        mode: row?.mode ? String(row.mode).toUpperCase() : null,
        ageS,
        // null = mai battuto: GIU', non "non lo so". Un runner che non ha mai
        // dato segno di vita non sta eseguendo niente.
        up: ageS !== null && ageS <= RUNNER_HB_MAX_AGE_S,
        streaming,
    };
}

export async function fetchRunnerState(): Promise<RunnerState> {
    const { data, error } = await supabase
        .from('betfair_live_heartbeat')
        .select('ts,mode')
        .eq('id', 1)
        .maybeSingle();
    if (error) throw error;
    // quante partite sono agganciate allo stream: senza nessuna, il runner e'
    // vivo ma PARCHEGGIATO e la coda ordini non ha nessuno dall'altro capo.
    // Un errore qui lascia `streaming` a null, che `runnerPhase` legge come
    // ATTESA: il dubbio non concede mai la coda.
    let streaming: number | null = null;
    try {
        const res = await supabase
            .from('live_follow')
            .select('event_id', { count: 'exact', head: true })
            .eq('status', 'STREAMING');
        if (!res.error) streaming = res.count ?? 0;
    } catch {
        streaming = null;
    }
    return runnerStateFrom(
        data as { ts?: string | null; mode?: string | null } | null,
        Date.now(), streaming,
    );
}

export interface ExecutionRoute {
    /** 'queue' = coda del runner (stream) · 'rest' = chiamata diretta FOK */
    route: 'queue' | 'rest';
    /** true = un ordine puo' restare A RIPOSO sul book (serve al place-and-trim) */
    restingOrders: boolean;
    /** etichetta breve da mostrare */
    label: string;
    /** motivo per cui NON si usa la coda; null quando la si usa */
    why: string | null;
}

/**
 * Percorso che il servizio usera' davvero, con le STESSE condizioni del gate del
 * backend (`omega_service._flumine_gate`): runner vivo, in modalita' ordini
 * coerente con quella del bot, ed evento in follow STREAMING.
 * Qualunque dubbio -> REST, come il gate, che e' fail-closed.
 */
export function executionRoute(
    runner: RunnerState,
    botMode: string | null | undefined,
    followStatus?: string | null,
): ExecutionRoute {
    const rest = (why: string): ExecutionRoute => ({
        route: 'rest', restingOrders: false, label: 'REST (fill or kill)', why,
    });
    const fase = runnerPhase(runner);
    if (fase === 'off') {
        return rest(runner.ageS === null
            ? 'runner flumine mai avviato'
            : `runner flumine spento (ultimo battito ${Math.round(runner.ageS)} s fa)`);
    }
    // CERT. 14/09 — IL BATTITO FRESCO NON BASTA. Il runner scrive il battito
    // anche mentre e' parcheggiato nel loop idle, e in quello stato
    // `live_order_worker` non esiste: la coda non ha nessuno dall'altro capo.
    // «processo vivo» e «coda utilizzabile» sono due cose diverse, e usare la
    // prima per rispondere alla seconda direbbe al trader che gli ordini
    // passano da una strada che non c'e'.
    if (fase === 'idle') {
        return rest('runner flumine vivo ma IN ATTESA: nessuna partita agganciata allo stream');
    }
    const atteso = String(botMode ?? '').toLowerCase() === 'live' ? 'LIVE' : 'PAPER';
    if (runner.mode !== atteso) {
        return rest(`runner in modalita' ${runner.mode ?? 'ignota'}, il bot chiede ${atteso}`);
    }
    if (followStatus !== undefined && String(followStatus ?? '').toUpperCase() !== 'STREAMING') {
        return rest(`partita non in streaming (${String(followStatus ?? 'assente').toLowerCase()})`);
    }
    return { route: 'queue', restingOrders: true, label: 'coda (stream)', why: null };
}
