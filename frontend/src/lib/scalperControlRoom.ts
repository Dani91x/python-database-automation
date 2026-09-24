// ============================================================================
// scalperControlRoom.ts - LO SCALPER CALCIO NELLA CONTROL ROOM (24/09).
//
// Decisione dell'utente: "lo scalper deve essere in Control Room come tutti
// gli altri bot". Lo scalper pero' NON e' un servizio che sceglie le partite
// da solo: si ARMA PER PARTITA (una riga per evento in `scalper_control`,
// `migrations/scalper_bot.sql`), e il supervisore (`scalper_service.py`, poll
// ogni 3 s) lancia una sessione per ogni riga 'requested'. Quindi qui:
//
//   * LETTURA: `get_scalper_control_room` (migrations/
//     scalper_control_room_2026-09-24.sql) - le sessioni vive o toccate oggi
//     e gli ordini dello specchio della sessione (`betfair_live_orders`),
//     con il P&L reale di Betfair per bet_id quando c'e'.
//   * STOP DI UNA SESSIONE: `scalper_stop_sessione` - force-flat e attesa
//     flat (e' il 'stopping' che la sessione legge ogni 5 s), con la guardia
//     d'identita': stessa `requested_at` (la sessione vista dalla pagina, non
//     una riarmata nel frattempo) e stessa modalita'.
//
// FONTE E ETA'. Lo scalper NON pubblica su un canale locale: la sessione e' un
// processo suo, e `local_channel.publish` fuori dal runner e' un no-op (nessun
// canale nel processo). Tutto quello che si vede qui viene dal DATABASE, al
// giro di ricarica della pagina (30 s), e lo si DICHIARA con l'eta'.
//
// Tutto PURO tranne le due chiamate: nessun React.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import { hedgeSide, partialLockedPnl } from '@/components/trading/CashOutButton';
import { prezzoVivo } from '@/lib/controlRoomProposte';

export type ModalitaScalper = 'paper' | 'live';

/** Stati della riga `scalper_control` (CHECK di migrations/scalper_bot.sql). */
export type StatoSessioneScalper =
    | 'requested' | 'arming' | 'armed' | 'running'
    | 'stopping' | 'stopped' | 'done' | 'error';

/** Stati in cui dietro la riga c'e' (o sta per esserci) una sessione che opera. */
export const STATI_ATTIVI_SCALPER: readonly string[] = ['requested', 'arming', 'armed', 'running'];
/** Stati che la Control Room considera "vivi" (anche lo stop in corso). */
export const STATI_VIVI_SCALPER: readonly string[] = [...STATI_ATTIVI_SCALPER, 'stopping'];

/** Una riga `scalper_control` + partita e ultima attivita' (chiavi VERE della RPC). */
export interface SessioneScalper {
    event_id: string;
    status: string;
    mode: string | null;
    dry_run: boolean | null;
    stake: number | null;
    params: Record<string, unknown> | null;
    bias: Record<string, string> | null;
    bias_meta: Record<string, unknown> | null;
    stats: Record<string, unknown> | null;
    error: string | null;
    requested_at: string;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
    updated_at: string | null;
    event_name: string | null;
    league_name: string | null;
    kickoff: string | null;
    ultima_attivita_at: string | null;
    ultima_attivita_kind: string | null;
}

/** Una riga di `betfair_live_orders` dello specchio della sessione (chiavi VERE). */
export interface OrdineScalper {
    id: number;
    bet_id: string | null;
    client_order_ref: string;
    mode: string;
    event_id: string | null;
    market_id: string;
    selection_id: number;
    side: string;
    order_type: string | null;
    price: number | null;
    size: number | null;
    size_matched: number | null;
    size_remaining: number | null;
    size_cancelled: number | null;
    size_lapsed: number | null;
    size_voided: number | null;
    average_price_matched: number | null;
    status: string;
    placed_at: string | null;
    matched_at: string | null;
    updated_at: string | null;
    source: string | null;
    pnl_betfair: number | null;
    commissione_betfair: number | null;
    pnl_betfair_settled_at: string | null;
}

export interface ScalperControlRoom {
    sessioni: SessioneScalper[];
    ordini: OrdineScalper[];
    /** istante della lettura dichiarato dal database */
    lettoAt: string | null;
}

// ------------------------------------------------------------------ chiamate

/** LETTURA owner-only: sessioni vive o di oggi + ordini dello specchio. */
export async function fetchScalperControlRoom(): Promise<ScalperControlRoom> {
    const { data, error } = await supabase.rpc('get_scalper_control_room', {});
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as { sessions?: SessioneScalper[]; orders?: OrdineScalper[]; letto_at?: string };
    return {
        sessioni: Array.isArray(d.sessions) ? d.sessions : [],
        ordini: Array.isArray(d.orders) ? d.orders : [],
        lettoAt: typeof d.letto_at === 'string' ? d.letto_at : null,
    };
}

/**
 * STOP DI UNA SESSIONE, con la guardia d'identita'. `requestedAt` va passato
 * ESATTAMENTE come l'ha scritto il database (stringa, microsecondi compresi):
 * mai ripassato da `Date`, che li perderebbe e farebbe rifiutare lo stop.
 */
export async function stopScalperSessione(
    eventId: string, requestedAt: string, modalita: ModalitaScalper,
): Promise<SessioneScalper> {
    const { data, error } = await supabase.rpc('scalper_stop_sessione', {
        p_event_id: eventId, p_requested_at: requestedAt, p_mode: modalita,
    });
    if (error) throw new Error(error.message);
    return data as unknown as SessioneScalper;
}

// ------------------------------------------------------------------ lettura

function num(v: unknown): number | null {
    if (v == null || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

function ms(iso: string | null | undefined): number | null {
    if (!iso) return null;
    const t = Date.parse(iso);
    return Number.isFinite(t) ? t : null;
}

const r2 = (x: number) => Math.round(x * 100) / 100;

/** paper/live della SESSIONE: `dry_run` e' l'interruttore (scalper_session.py). */
export function modalitaSessione(s: Pick<SessioneScalper, 'dry_run'>): ModalitaScalper | null {
    if (s.dry_run === true) return 'paper';
    if (s.dry_run === false) return 'live';
    return null;
}

export function sessioneViva(s: Pick<SessioneScalper, 'status'>): boolean {
    return STATI_VIVI_SCALPER.includes(String(s.status ?? '').toLowerCase());
}

export function sessioneAttiva(s: Pick<SessioneScalper, 'status'>): boolean {
    return STATI_ATTIVI_SCALPER.includes(String(s.status ?? '').toLowerCase());
}

/**
 * LO STATO DEL "BOT" SCALPER per la plancia, dalle sue sessioni.
 *  - acceso   = almeno una sessione attiva (requested/arming/armed/running);
 *  - stato    = 'running' se ce n'e' una attiva, 'stopping' se ce n'e' solo
 *               una che si sta fermando, altrimenti 'stopped';
 *  - modalita = quella DICHIARATA dalle sessioni vive: basta una in live
 *               perche' la riga dica soldi veri (come il tetto di Safe);
 *               nessuna sessione viva = `null` (non c'e' niente che operi).
 *  - misto    = sessioni vive in paper E in live insieme (lo si dice).
 */
export function statoBotScalper(sessioni: readonly SessioneScalper[]): {
    inCorsa: boolean; stato: string; modalita: ModalitaScalper | null; misto: boolean;
    battitoAt: string | null; vive: number; attive: number;
} {
    const vive = sessioni.filter(sessioneViva);
    const attive = vive.filter(sessioneAttiva);
    const modi = new Set(vive.map(modalitaSessione).filter((m): m is ModalitaScalper => m != null));
    const modalita: ModalitaScalper | null = modi.has('live') ? 'live' : modi.has('paper') ? 'paper' : null;
    let battito: number | null = null;
    let battitoAt: string | null = null;
    for (const s of vive) {
        const t = ms(s.heartbeat_at);
        if (t != null && (battito == null || t > battito)) { battito = t; battitoAt = s.heartbeat_at; }
    }
    return {
        inCorsa: attive.length > 0,
        stato: attive.length > 0 ? 'running' : vive.length > 0 ? 'stopping' : 'stopped',
        modalita,
        misto: modi.size > 1,
        battitoAt,
        vive: vive.length,
        attive: attive.length,
    };
}

/**
 * Gli ordini della SESSIONE CORRENTE di una partita: stessa partita, stessa
 * modalita' della sessione (paper e live mai mischiati), piazzati dopo il suo
 * `requested_at` (un riarmo azzera la riga: gli ordini della sessione di prima
 * non sono di questa). Un ordine senza orario non si attribuisce.
 */
export function ordiniDellaSessione(
    s: SessioneScalper, ordini: readonly OrdineScalper[],
): OrdineScalper[] {
    const m = modalitaSessione(s);
    const dal = ms(s.requested_at);
    if (m == null || dal == null) return [];
    return ordini.filter((o) => {
        if (String(o.event_id ?? '') !== String(s.event_id)) return false;
        if (String(o.mode ?? '').toLowerCase() !== m) return false;
        const t = ms(o.placed_at ?? o.updated_at);
        return t != null && t >= dal;
    });
}

/** Una selezione con la sua esposizione: P&L se VINCE e se PERDE (solo l'abbinato). */
export interface EsposizioneSelezione {
    marketId: string;
    selectionId: number;
    /** P&L della selezione se vince (solo la parte abbinata) */
    win: number;
    /** P&L della selezione se perde */
    lose: number;
    /** abbinato netto: + = punta, - = banca */
    netto: number;
}

export interface EsposizioneScalper {
    selezioni: EsposizioneSelezione[];
    /** somma degli abbinati (volume), in EUR */
    abbinato: number;
    /** somma dei residui ancora sul book */
    residuo: number;
    /** somma dei chiesti */
    chiesto: number;
    /** ordini ancora vivi sul book (EXECUTABLE/PENDING con residuo) */
    inAttesa: number;
    /**
     * RESPONSABILITA' (caso peggiore) per mercato, sommata. Per ogni mercato
     * si guarda ogni selezione giocata che vince, piu' il caso "vince una che
     * non abbiamo giocato": e' prudente sui mercati a due esiti giocati da
     * entrambi i lati (conta un esito che non esiste), mai ottimista.
     */
    responsabilita: number;
}

const VIVI_BOOK = new Set(['EXECUTABLE', 'PENDING']);

/** L'esposizione ABBINATA di un insieme di ordini (aritmetica dell'exchange). */
export function esposizioneScalper(ordini: readonly OrdineScalper[]): EsposizioneScalper {
    const perSel = new Map<string, EsposizioneSelezione>();
    let abbinato = 0; let residuo = 0; let chiesto = 0; let inAttesa = 0;
    for (const o of ordini) {
        const m = num(o.size_matched) ?? 0;
        const p = num(o.average_price_matched) || num(o.price);
        const lato = String(o.side ?? '').toLowerCase();
        const res = num(o.size_remaining) ?? 0;
        chiesto += num(o.size) ?? 0;
        residuo += res;
        if (res > 0 && VIVI_BOOK.has(String(o.status ?? '').toUpperCase())) inAttesa += 1;
        if (m <= 0 || p == null || p <= 1 || (lato !== 'back' && lato !== 'lay')) continue;
        abbinato += m;
        const k = `${o.market_id}|${o.selection_id}`;
        const e = perSel.get(k) ?? {
            marketId: String(o.market_id), selectionId: Number(o.selection_id), win: 0, lose: 0, netto: 0,
        };
        if (lato === 'back') { e.win += m * (p - 1); e.lose -= m; e.netto += m; }
        else { e.win -= m * (p - 1); e.lose += m; e.netto -= m; }
        perSel.set(k, e);
    }
    const selezioni = Array.from(perSel.values()).map((e) => ({
        ...e, win: r2(e.win), lose: r2(e.lose), netto: r2(e.netto),
    }));
    // caso peggiore per mercato
    const perMercato = new Map<string, EsposizioneSelezione[]>();
    for (const e of selezioni) {
        const a = perMercato.get(e.marketId);
        if (a) a.push(e); else perMercato.set(e.marketId, [e]);
    }
    let responsabilita = 0;
    for (const sel of perMercato.values()) {
        const tuttePerse = sel.reduce((s, e) => s + e.lose, 0);
        let peggiore = tuttePerse; // vince una selezione non giocata
        for (const e of sel) peggiore = Math.min(peggiore, tuttePerse - e.lose + e.win);
        responsabilita += Math.max(0, -peggiore);
    }
    return {
        selezioni, abbinato: r2(abbinato), residuo: r2(residuo), chiesto: r2(chiesto),
        inAttesa, responsabilita: r2(responsabilita),
    };
}

/** "Se chiudo ora", nella forma di `PosizioneAperta.chiusura`. */
export interface ChiusuraScalper {
    lato: 'back' | 'lay';
    prezzo: number | null;
    abbinabile: number | null;
    bloccabile: number | null;
}

type PayloadFeed = Parameters<typeof prezzoVivo>[0];

/**
 * QUANTO VALE CHIUDERE ADESSO tutta la sessione: il green-up PIENO di ogni
 * selezione esposta, al prezzo di adesso del feed, con la STESSA matematica
 * del bottone di cash out (`partialLockedPnl`, frazione 1). Coprire ogni
 * selezione per conto suo rende costante il suo contributo in ogni esito,
 * quindi la somma e' il P&L bloccato della sessione intera.
 *
 * `lato`/`prezzo`/`abbinabile` sono quelli della selezione con lo sbilancio
 * piu' grande (quella che il trader guarda). `bloccabile` e `prezzo` sono
 * `null` se anche UNA selezione da coprire non ha un prezzo nel feed: mai un
 * numero parziale spacciato per il totale. `null` in tutto = niente di
 * abbinato (nessuna posizione).
 */
export function chiusuraScalper(
    esp: EsposizioneScalper, payload: PayloadFeed,
): ChiusuraScalper | null {
    if (esp.selezioni.length === 0) return null;
    let totale: number | null = 0;
    let guida: { e: EsposizioneSelezione; lato: 'back' | 'lay'; prezzo: number | null; abbinabile: number | null } | null = null;
    for (const e of esp.selezioni) {
        const sbilancio = Math.abs(e.win - e.lose);
        if (sbilancio < 0.005) {
            if (totale != null) totale = r2(totale + Math.min(e.win, e.lose));
            continue;
        }
        const lato = hedgeSide(e.win, e.lose);
        const v = prezzoVivo(payload, e.marketId, e.selectionId, lato);
        const prezzo = v.prezzo != null && v.prezzo > 1 ? v.prezzo : null;
        if (guida == null || sbilancio > Math.abs(guida.e.win - guida.e.lose)) {
            guida = { e, lato, prezzo, abbinabile: v.abbinabile ?? null };
        }
        if (prezzo == null) { totale = null; continue; }
        if (totale != null) totale = r2(totale + partialLockedPnl(prezzo, e.win, e.lose, 1));
    }
    if (guida == null) {
        // tutto gia' coperto: il bloccato e' certo, non serve un prezzo
        const prima = esp.selezioni[0];
        return { lato: hedgeSide(prima.win, prima.lose), prezzo: null, abbinabile: null, bloccabile: totale };
    }
    return {
        lato: guida.lato,
        prezzo: totale == null ? null : guida.prezzo,
        abbinabile: guida.abbinabile,
        bloccabile: totale,
    };
}

/**
 * IL P&L REALE DI BETFAIR di un insieme di ordini (netto di commissione, per
 * bet_id: `pnl_betfair`, scritto dal giro dei regolati del runner).
 *  - `reale`   = somma dei `pnl_betfair` presenti;
 *  - `completo`= ogni ordine con qualcosa di abbinato ha il suo `pnl_betfair`
 *                (solo allora la sessione ha un risultato certo);
 *  - `regolatiOggi` = somma dei soli regolati nel giorno `oggi` (Roma).
 * Il paper non ha mai un `pnl_betfair` (su Betfair non esiste).
 */
export function pnlRealeOrdini(
    ordini: readonly OrdineScalper[], giornoDi?: (iso: string) => string, oggi?: string,
): { reale: number | null; completo: boolean; regolatiOggi: number | null; betIds: string[] } {
    let reale: number | null = null;
    let regolatiOggi: number | null = null;
    let completo = true;
    let conAbbinato = 0;
    const betIds: string[] = [];
    for (const o of ordini) {
        const m = num(o.size_matched) ?? 0;
        const b = num(o.pnl_betfair);
        if (m > 0) conAbbinato += 1;
        if (b == null) { if (m > 0) completo = false; continue; }
        reale = r2((reale ?? 0) + b);
        if (o.bet_id) betIds.push(String(o.bet_id));
        const quando = o.pnl_betfair_settled_at;
        if (giornoDi && oggi && quando && giornoDi(quando) === oggi) {
            regolatiOggi = r2((regolatiOggi ?? 0) + b);
        }
    }
    return { reale, completo: completo && conAbbinato > 0, regolatiOggi, betIds };
}

/** Il P&L LORDO dichiarato dal bot (`stats.pnl_locked`): flumine NON detrae la
 *  commissione. Si mostra solo marcato "lordo, dal bot", mai come netto. */
export function pnlLordoBot(s: Pick<SessioneScalper, 'stats'>): number | null {
    const st = s.stats ?? {};
    const base = num((st as Record<string, unknown>).pnl_locked);
    if (base == null) return null;
    const sn = num((st as Record<string, unknown>).sniper_pnl_locked) ?? 0;
    const th = num((st as Record<string, unknown>).theta_pnl_locked) ?? 0;
    return r2(base + sn + th);
}

function etaS(iso: string | null | undefined, nowMs: number): number | null {
    const t = ms(iso);
    return t == null ? null : Math.max(0, Math.round((nowMs - t) / 1000));
}

/**
 * LA FRASE DELLA SESSIONE accanto alla riga: stato scritto dal servizio,
 * ultima attivita' (`scalper_activity`), battito, P&L LORDO dichiarato dal
 * bot (mai spacciato per netto), e sempre FONTE ed ETA' del dato. Lo stato
 * dello slot (IDLE/QUOTING/LOCKING...) il bot NON lo pubblica: lo si dice.
 */
export function notaSessioneScalper(
    s: SessioneScalper, nowMs: number, etaLetturaS: number | null,
): string {
    const parti: string[] = [`sessione ${s.status}`];
    if (s.ultima_attivita_kind) {
        const a = etaS(s.ultima_attivita_at, nowMs);
        parti.push(`ultima attivita' ${s.ultima_attivita_kind}${a == null ? '' : ` ${a} s fa`}`);
    }
    if (sessioneViva(s)) {
        const hb = etaS(s.heartbeat_at, nowMs);
        parti.push(hb == null ? 'battito assente' : `battito ${hb} s fa`);
    }
    const lordo = pnlLordoBot(s);
    if (lordo != null) parti.push(`bloccato dal bot ${lordo >= 0 ? '+' : ''}${lordo.toFixed(2)} EUR lordo`);
    parti.push('stato dello slot non pubblicato dal bot');
    parti.push(`fonte: database, letto ${etaLetturaS == null ? 'mai' : `${etaLetturaS} s fa`}`);
    return parti.join(' - ');
}

/** Id NUMERICO della riga di sessione in Control Room: l'event_id di Betfair
 *  (numerico). `null` se non lo e': una riga senza id non si comanda. */
export function idSessione(eventId: string): number | null {
    const s = String(eventId ?? '').trim();
    if (!/^\d{1,15}$/.test(s)) return null;
    return Number(s);
}
