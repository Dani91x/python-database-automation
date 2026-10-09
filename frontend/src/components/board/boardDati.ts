// ============================================================================
// boardDati.ts - 09/10/2026 (Programma del giorno, ordine dell'utente).
//
// Le FORME dei push del tabellone e le regole pure che la pagina applica.
// Contratto backend/frontend: AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md
//   §1 push `board`          {rows, market_types?}   (righe MATCH_ODDS)
//   §2 `market_types`        [{market_type, name, count}]
//   §3 push `board_mercato`  {market_type, rows, updated_ms}
//
// Perche' un modulo nuovo: il tabellone e' l'UNICO consumatore di questi due
// push (prima la forma viveva dentro `pages/Board.tsx`); le regole qui sotto
// sono pure (nessuna rete, nessun React) cosi' i test le misurano da sole.
//
// REGOLE:
//  - un campo assente vale «non noto», MAI 0 (contratto §1): ogni numero
//    passa da `numero()` e resta `null` se non e' un numero finito;
//  - calcio e tennis non si mischiano: un `score` dell'altro sport e' scartato;
//  - sul calcio i correct score NON compaiono nel menu', anche se il backend
//    li mandasse (filtro difensivo, contratto §2);
//  - la modalita' ordini e' SEMPRE quella del runner (contratto §4): qui si
//    decide solo se e' nota e se un ordine puo' partire, mai la si sceglie.
// ============================================================================
import type { LocalSport } from '@/lib/localChannel';
import { MODO_CANALE_VALIDO_S, type ModoOrdiniCanale } from '@/lib/runnerCanale';

export type SportBoard = Extract<LocalSport, 'calcio' | 'tennis'>;

/** Il tipo di mercato del `board` di sempre (contratto §3: non si chiede). */
export const MATCH_ODDS = 'MATCH_ODDS';

/** Ogni quanto si RINNOVA la richiesta `board_mercato` (il worker dimentica a 75 s). */
export const RINNOVO_MERCATO_MS = 30_000;

export interface SelezioneBoard {
    selection_id: number;
    name: string | null;
    /** solo `board_mercato` (linee di handicap); assente = 0 nel comando, come il ladder */
    handicap: number | null;
    back: number | null;
    lay: number | null;
    ltp: number | null;
    /** importo disponibile al miglior prezzo; null = non noto */
    back_size: number | null;
    lay_size: number | null;
}

export interface PunteggioCalcio {
    sport: 'calcio';
    minute: number | null;
    home: number | null;
    away: number | null;
    red_home: number | null;
    red_away: number | null;
    ht: boolean | null;
}

export interface CoppiaNum { p1: number; p2: number }
export interface CoppiaStr { p1: string; p2: string }

export interface PunteggioTennis {
    sport: 'tennis';
    sets: CoppiaNum | null;
    games: CoppiaNum | null;
    points: CoppiaStr | null;
    server: 'p1' | 'p2' | null;
}

export type Punteggio = PunteggioCalcio | PunteggioTennis;

/** Una riga del push `board` (mercato MATCH_ODDS). */
export interface RigaBoard {
    event_id: string;
    event_name: string;
    open_date: string;
    market_id: string;
    status: string | null;
    inplay: boolean;
    total_matched: number | null;
    selections: SelezioneBoard[];
    score: Punteggio | null;
    fixture_id: number | null;
    bet_delay: number | null;
    updated_ms: number | null;
}

export interface TipoMercato {
    market_type: string;
    name: string;
    count: number | null;
}

/** Una riga del push `board_mercato` (un mercato di un evento). */
export interface RigaMercato {
    event_id: string;
    market_id: string;
    market_name: string | null;
    status: string | null;
    inplay: boolean;
    total_matched: number | null;
    selections: SelezioneBoard[];
}

export interface Tabellone {
    rows: RigaBoard[];
    /** null = il backend non dichiara i tipi (runner di prima del 09/10) */
    marketTypes: TipoMercato[] | null;
}

export interface MercatoScelto {
    market_type: string;
    rows: RigaMercato[];
    updated_ms: number | null;
}

// ------------------------------------------------------------------ lettura

function oggetto(v: unknown): Record<string, unknown> | null {
    return v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null;
}

/** numero finito o null: un dato assente non diventa mai 0 */
export function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function testo(v: unknown): string | null {
    return typeof v === 'string' && v.trim() ? v : null;
}

/** gli id arrivano numerici o stringa: si confrontano sempre come stringa */
function id(v: unknown): string | null {
    if (typeof v === 'string' && v) return v;
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    return null;
}

function coppiaNum(v: unknown): CoppiaNum | null {
    const o = oggetto(v);
    const p1 = numero(o?.p1);
    const p2 = numero(o?.p2);
    return p1 == null || p2 == null ? null : { p1, p2 };
}

function coppiaStr(v: unknown): CoppiaStr | null {
    const o = oggetto(v);
    const p1 = o?.p1;
    const p2 = o?.p2;
    const s = (x: unknown) => (typeof x === 'string' ? x : typeof x === 'number' && Number.isFinite(x) ? String(x) : null);
    const a = s(p1);
    const b = s(p2);
    return a == null || b == null ? null : { p1: a, p2: b };
}

/** Il punteggio della riga, SOLO se e' dello sport della scheda (mai mischiati). */
export function leggiPunteggio(v: unknown, sport: SportBoard): Punteggio | null {
    const o = oggetto(v);
    if (!o || o.sport !== sport) return null;
    if (sport === 'calcio') {
        return {
            sport: 'calcio',
            minute: numero(o.minute),
            home: numero(o.home),
            away: numero(o.away),
            red_home: numero(o.red_home),
            red_away: numero(o.red_away),
            ht: typeof o.ht === 'boolean' ? o.ht : null,
        };
    }
    return {
        sport: 'tennis',
        sets: coppiaNum(o.sets),
        games: coppiaNum(o.games),
        points: coppiaStr(o.points),
        server: o.server === 'p1' || o.server === 'p2' ? o.server : null,
    };
}

export function leggiSelezione(v: unknown): SelezioneBoard | null {
    const o = oggetto(v);
    const sid = numero(o?.selection_id);
    if (!o || sid == null) return null;
    return {
        selection_id: sid,
        name: testo(o.name),
        handicap: numero(o.handicap),
        back: numero(o.back),
        lay: numero(o.lay),
        ltp: numero(o.ltp),
        back_size: numero(o.back_size),
        lay_size: numero(o.lay_size),
    };
}

function selezioni(v: unknown): SelezioneBoard[] {
    if (!Array.isArray(v)) return [];
    return v.map(leggiSelezione).filter((s): s is SelezioneBoard => s != null);
}

export function leggiRigaBoard(v: unknown, sport: SportBoard): RigaBoard | null {
    const o = oggetto(v);
    const eventId = id(o?.event_id);
    const marketId = id(o?.market_id);
    if (!o || !eventId || !marketId) return null;
    const fixture = numero(o.fixture_id);
    return {
        event_id: eventId,
        event_name: testo(o.event_name) ?? eventId,
        open_date: typeof o.open_date === 'string' ? o.open_date : '',
        market_id: marketId,
        status: testo(o.status),
        inplay: o.inplay === true,
        total_matched: numero(o.total_matched),
        selections: selezioni(o.selections),
        score: leggiPunteggio(o.score, sport),
        fixture_id: fixture != null && fixture > 0 ? fixture : null,
        bet_delay: numero(o.bet_delay),
        updated_ms: numero(o.updated_ms),
    };
}

function leggiTipi(v: unknown): TipoMercato[] | null {
    if (!Array.isArray(v)) return null;
    const out: TipoMercato[] = [];
    for (const x of v) {
        const o = oggetto(x);
        const t = testo(o?.market_type);
        if (!o || !t) continue;
        out.push({ market_type: t, name: testo(o.name) ?? t, count: numero(o.count) });
    }
    return out;
}

/** Il push `board` (contratto §1-§2). `null` = messaggio storto: si tiene il precedente. */
export function leggiBoard(d: unknown, sport: SportBoard): Tabellone | null {
    const o = oggetto(d);
    if (!o || !Array.isArray(o.rows)) return null;
    return {
        rows: o.rows.map((r) => leggiRigaBoard(r, sport)).filter((r): r is RigaBoard => r != null),
        marketTypes: leggiTipi(o.market_types),
    };
}

export function leggiRigaMercato(v: unknown): RigaMercato | null {
    const o = oggetto(v);
    const eventId = id(o?.event_id);
    const marketId = id(o?.market_id);
    if (!o || !eventId || !marketId) return null;
    return {
        event_id: eventId,
        market_id: marketId,
        market_name: testo(o.market_name),
        status: testo(o.status),
        inplay: o.inplay === true,
        total_matched: numero(o.total_matched),
        selections: selezioni(o.selections),
    };
}

/** Il push `board_mercato` (contratto §3). `null` = storto o senza tipo. */
export function leggiBoardMercato(d: unknown): MercatoScelto | null {
    const o = oggetto(d);
    const tipo = testo(o?.market_type);
    if (!o || !tipo || !Array.isArray(o.rows)) return null;
    return {
        market_type: tipo,
        rows: o.rows.map(leggiRigaMercato).filter((r): r is RigaMercato => r != null),
        updated_ms: numero(o.updated_ms),
    };
}

// -------------------------------------------------------------- menu' mercati

/** Sul calcio i correct score non si offrono mai (contratto §2, utente 09/10). */
export function escluso(sport: SportBoard, marketType: string): boolean {
    if (sport !== 'calcio') return false;
    const t = marketType.toUpperCase();
    return t.includes('CORRECT_SCORE') || t.includes('HALF_TIME_SCORE');
}

/**
 * Le voci del menu': MATCH_ODDS sempre e per primo (e' il `board` di sempre),
 * poi i tipi dichiarati dal backend senza doppioni e, sul calcio, senza i
 * correct score.
 */
export function vociMenu(sport: SportBoard, tipi: TipoMercato[] | null): TipoMercato[] {
    const out: TipoMercato[] = [];
    const visti = new Set<string>();
    const mo = tipi?.find((t) => t.market_type === MATCH_ODDS);
    out.push(mo ?? { market_type: MATCH_ODDS, name: 'Match Odds', count: null });
    visti.add(MATCH_ODDS);
    for (const t of tipi ?? []) {
        if (visti.has(t.market_type) || escluso(sport, t.market_type)) continue;
        visti.add(t.market_type);
        out.push(t);
    }
    return out;
}

// ------------------------------------------------------------- righe a video

/** Una linea di quote a video: un mercato di un evento. */
export interface LineaQuote {
    market_id: string;
    /** null sul MATCH_ODDS (non serve dirlo); il nome della linea altrimenti */
    market_name: string | null;
    status: string | null;
    total_matched: number | null;
    selections: SelezioneBoard[];
}

/** Un evento del programma con le linee del mercato scelto. */
export interface EventoProgramma {
    riga: RigaBoard;
    linee: LineaQuote[];
}

const tempo = (iso: string): number => {
    const t = Date.parse(iso);
    return Number.isFinite(t) ? t : Number.MAX_SAFE_INTEGER;
};

/**
 * Le righe a video. MATCH_ODDS: le righe del `board`. Un altro tipo: le righe
 * del `board_mercato` di QUEL tipo unite per `event_id` alle righe del board
 * (orario, evento, punteggio restano del board). Un evento senza quel mercato
 * non si mostra (come la coupon di Betfair); un mercato di un evento che il
 * board non conosce nemmeno (non ha orario ne' nome): `orfani`.
 */
export function eventiDelMercato(
    rows: RigaBoard[], tipo: string, mercato: MercatoScelto | null,
): { eventi: EventoProgramma[]; senzaMercato: number; orfani: number; attesa: boolean } {
    const ordinati = [...rows].sort((a, b) => tempo(a.open_date) - tempo(b.open_date));
    if (tipo === MATCH_ODDS) {
        return {
            eventi: ordinati.map((r) => ({
                riga: r,
                linee: [{
                    market_id: r.market_id, market_name: null, status: r.status,
                    total_matched: r.total_matched, selections: r.selections,
                }],
            })),
            senzaMercato: 0, orfani: 0, attesa: false,
        };
    }
    if (!mercato || mercato.market_type !== tipo) {
        return { eventi: [], senzaMercato: 0, orfani: 0, attesa: true };
    }
    const perEvento = new Map<string, LineaQuote[]>();
    for (const m of mercato.rows) {
        const l = perEvento.get(m.event_id) ?? [];
        l.push({
            market_id: m.market_id, market_name: m.market_name, status: m.status,
            total_matched: m.total_matched, selections: m.selections,
        });
        perEvento.set(m.event_id, l);
    }
    const eventi: EventoProgramma[] = [];
    let senzaMercato = 0;
    const conosciuti = new Set<string>();
    for (const r of ordinati) {
        conosciuti.add(r.event_id);
        const linee = perEvento.get(r.event_id);
        if (!linee || linee.length === 0) { senzaMercato += 1; continue; }
        linee.sort((a, b) => (a.market_name ?? '').localeCompare(b.market_name ?? '', 'it'));
        eventi.push({ riga: r, linee });
    }
    let orfani = 0;
    for (const ev of perEvento.keys()) if (!conosciuti.has(ev)) orfani += 1;
    return { eventi, senzaMercato, orfani, attesa: false };
}

/** Il volume piu' alto fra le linee a video (base della barra relativa); null = nessuno noto. */
export function volumeMassimo(eventi: EventoProgramma[]): number | null {
    let max: number | null = null;
    for (const e of eventi) {
        for (const l of e.linee) {
            if (l.total_matched != null && l.total_matched > 0 && (max == null || l.total_matched > max)) {
                max = l.total_matched;
            }
        }
    }
    return max;
}

/** Quota della barra di liquidita' (0-100) rispetto al piu' scambiato; null = non nota. */
export function quotaLiquidita(v: number | null, max: number | null): number | null {
    if (v == null || max == null || max <= 0 || v < 0) return null;
    return Math.max(0, Math.min(100, Math.round((v / max) * 100)));
}

// ------------------------------------------------------------ modalita' ordini

/** Il piu' recente (per `ts` del produttore): un oggetto intero, mai unione. */
export function piuRecente(p: ModoOrdiniCanale | null, m: ModoOrdiniCanale | null): ModoOrdiniCanale | null {
    if (m == null) return p;
    return p != null && p.ms >= m.ms ? p : m;
}

/**
 * Il modo ordini che il runner APPLICA, dal SOLO canale (nessuna lettura DB):
 *  - `modo_ordini` (topic o `hello.modo_ordini`), pubblicato AL CAMBIO dai due
 *    runner (calcio `live_order_worker`, tennis `guardie_tennis`): vale finche'
 *    il canale e' collegato;
 *  - `now.state.order_mode` (calcio, partite seguite) se fresco
 *    (`MODO_CANALE_VALIDO_S`) e piu' recente.
 * `hello.mode` NON basta: e' il TETTO del .env, non il modo effettivo (la
 * scelta dalla UI puo' essere piu' bassa, anche OFF).
 */
export function modoApplicato(
    alCambio: ModoOrdiniCanale | null, dalNow: ModoOrdiniCanale | null, nowMs: number,
): ModoOrdiniCanale | null {
    const nowValido = dalNow != null && (nowMs - dalNow.ms) / 1000 <= MODO_CANALE_VALIDO_S;
    let m = alCambio;
    if (nowValido && (m == null || dalNow.ms > m.ms)) m = dalNow;
    return m;
}

export interface ModoOrdiniBoard {
    /** il `mode` del comando; null = nessun ordine puo' partire */
    mode: 'paper' | 'live' | null;
    /** l'etichetta del chip: PAPER · SIMULATO, LIVE · REALE, ORDINI OFF, NON NOTA */
    etichetta: string;
    /** perche' non si puo' ordinare (null = si puo') */
    motivo: string | null;
}

/** Dal modo applicato (e dal freno) a cio' che il box puo' fare. */
export function modoOrdiniBoard(m: ModoOrdiniCanale | null, freno: boolean | null): ModoOrdiniBoard {
    if (m == null || m.effettivo == null) {
        return {
            mode: null, etichetta: 'ORDINI: NON NOTA',
            motivo: 'Modalità ordini del runner non nota: il runner non l\'ha ancora dichiarata sul canale. '
                + 'La conferma resta spenta finché non arriva.',
        };
    }
    if (m.effettivo === 'OFF') {
        return {
            mode: null, etichetta: 'ORDINI OFF',
            motivo: 'Il runner ha gli ordini spenti (modalità OFF): nessun ordine può partire. '
                + 'Si cambia dalla Control Room, riga «Ordini reali».',
        };
    }
    const mode = m.effettivo === 'LIVE' ? 'live' : 'paper';
    const etichetta = mode === 'live' ? 'LIVE · REALE' : 'PAPER · SIMULATO';
    if (freno === true) {
        return {
            mode, etichetta,
            motivo: 'Freno d\'emergenza tirato: il runner rifiuta gli ordini nuovi. Si rilascia dalla Control Room.',
        };
    }
    return { mode, etichetta, motivo: null };
}

/** Il freno dichiarato nello stesso messaggio del modo (`kill_switch`); null = non detto. */
export function frenoDa(d: unknown): boolean | null {
    const o = oggetto(d);
    return o && typeof o.kill_switch === 'boolean' ? o.kill_switch : null;
}
