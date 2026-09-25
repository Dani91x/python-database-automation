// ============================================================================
// esitoAbbinamento.ts - B17 (25/09): «A CHE PREZZO SONO ENTRATO, E SONO
// ENTRATO DAVVERO?».
//
// Ordine dell'utente, 25/09 (punto 14): «una volta che clicco, devo sapere a
// che prezzo e' stato abbinato il mio ordine rispetto al segnale e soprattutto
// se e' stato realmente abbinato, con un messaggio». Paper e live IDENTICI nel
// comportamento della scheda: in paper il fill e' simulato, il messaggio e'
// lo stesso (la scheda aggiunge solo il cartellino «paper»).
//
// Modulo PURO (nessun React, nessuna rete). Tre pezzi:
//  1. `ClicOrdine`: cio' che la scheda sapeva all'istante del clic - bot, tipo
//     (apertura / chiusura), lato dell'ordine che parte, PREZZO VISTO (quello
//     a video, gia' mandato al servizio col suo contesto) e PREZZO DEL SEGNALE
//     (quello con cui la strategia ha generato la proposta), modalita';
//  2. `gambeDelClic`: QUALI righe del bot sono l'ordine di quel clic - per id
//     dichiarato dal servizio (`result.trade_id`/`trade_ids`/
//     `closing_trade_id`), altrimenti per le chiusure di QUELLA posizione
//     nate dopo il clic, altrimenti (Mike, i 4 bot tennis, che chiudono per
//     partita) le righe NUOVE del bot sulla partita. Senza un id del servizio
//     un'APERTURA non si indovina mai;
//  3. `esitoAbbinamento`: il messaggio. Si leggono SOLO i campi veri della
//     riga (`statoOrdine`: colonne della migrazione del 16/09, poi le note del
//     `meta`), mai il prezzo chiesto spacciato per il medio, mai uno zero al
//     posto di un numero assente.
//
// I messaggi (testi esatti, inchiodati da `esitoAbbinamento.test.ts`):
//   inviato: in attesa del servizio
//   in corso: <cosa sta facendo il servizio>
//   accettato da Betfair a X: in attesa di abbinamento, R sul book
//   ABBINATO TOTALMENTE a prezzo medio Y (Δ vs visto +z tick a favore, vs
//     segnale -w tick contro), size S
//   ABBINATO PARZIALMENTE: A su C a Y (Δ ...), resto R in attesa sul book
//   ABBINATO PARZIALMENTE: A su C a Y (Δ ...), resto annullato
//   NON abbinato (FOK): il book non copriva l'intera size, ordine ucciso
//   rifiutato: <motivo del servizio o codice di Betfair>
//
// La differenza in tick e' quella della LADDER BETFAIR (`riskMath.ticksBetween`,
// la stessa di tutta la piattaforma). Il segno e' quello del prezzo (medio
// meno riferimento); «a favore» dipende dal lato: per una PUNTA un prezzo piu'
// alto e' meglio, per una BANCA piu' basso.
// ============================================================================
import { ticksBetween } from '@/lib/riskMath';
import { fmtMoney, fmtOdds, fmtAge, DASH } from '@/lib/format';
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import type { Bot } from '@/lib/controlRoom';
import type { ContestoPrezzoVisto } from '@/lib/schedaAlMs';
import { chiaveRiga, vistaVoce, type MappaRighe } from '@/lib/righeCanale';

export type Lato = 'back' | 'lay';

/** Fase dell'esito come la legge il trader. */
export type FaseEsito =
    | 'inviato' | 'in_corso' | 'accettato' | 'parziale' | 'totale'
    | 'non_abbinato' | 'rifiutato' | 'ignoto';

/** Fase della RICHIESTA nella coda del bot (le stesse parole di `chiudiRiga.ts`). */
export type FaseRichiesta = 'inviata' | 'presa_in_carico' | 'eseguita' | 'rifiutata' | 'ignota';

/** Da dove arriva la riga dell'ordine: messaggio del canale del bot o blocco del DB. */
export type FonteGamba = 'canale' | 'database';

/** Oltre questo tempo senza un esito terminale, l'esito e' IGNOTO e lo si dice. */
export const SCADENZA_SEGUITO_MS = 180_000;

/** Quanti clic si seguono al massimo (i piu' recenti). */
export const MAX_SEGUITI = 8;

const EPS = 0.005;

/** Stati TERMINALI di un ordine flumine (righe `tennis_live_orders`), gli
 *  stessi di `Betfair/stream/esiti_ordini_canale.STATI_TERMINALI`. */
export const TERMINALI_FLUMINE: ReadonlySet<string> = new Set([
    'EXECUTION_COMPLETE', 'EXPIRED', 'LAPSED', 'VIOLATION', 'VOIDED', 'CANCELLED',
]);

/** Cio' che la scheda sapeva all'istante del clic. */
export interface ClicOrdine {
    /** chiave unica del seguito: `${bot}:${tipo}:${riferimento}` */
    chiave: string;
    bot: Bot;
    tipo: 'apertura' | 'chiusura';
    /** testo breve della scheda («Safe · opportunità #56») */
    etichetta: string;
    /** id della richiesta nella coda del bot (null = nessuna coda letta) */
    requestId: number | null;
    /** chiusura: la posizione che si chiude (Omega/Safe: `closes_trade_id`) */
    tradeIdApertura: number | null;
    /** partita (Mike e i bot tennis chiudono per partita) */
    eventId: string | null;
    /** lato dell'ordine che PARTE (per una chiusura: il lato opposto all'apertura) */
    lato: Lato | null;
    /** il prezzo A VIDEO al clic (quello mandato al servizio); null = nessuno */
    prezzoVisto: number | null;
    /** il prezzo con cui la strategia ha generato la proposta; null = nessun segnale */
    prezzoSegnale: number | null;
    /** eta'/fonte del prezzo visto (lo stesso contesto mandato al servizio) */
    contesto: ContestoPrezzoVisto | null;
    modo: 'paper' | 'live' | null;
    clicMs: number;
    /** righe del bot sulla partita GIA' note al clic: non sono l'ordine di questo clic */
    idsNotiAlClic: number[];
    /** Mike: i ruoli delle gambe proposte (una riga nuova d'altro ruolo non e' questa uscita) */
    ruoli: string[] | null;
    /**
     * 25/09 (residui B17) - SOLO gli id dichiarati dal servizio nel `result`
     * della richiesta, mai la correlazione per partita. Il cash out globale di
     * partita chiude N posizioni: una riga nuova del bot sulla partita puo'
     * essere un'altra cosa (una protezione, un'apertura) e non si indovina.
     */
    soloIdDichiarati?: boolean;
}

/** La riga della coda del bot, tradotta. */
export interface RichiestaSeguita {
    fase: FaseRichiesta;
    motivo: string | null;
    /** id delle righe d'ordine DICHIARATI dal servizio nel `result` */
    tradeIds: number[];
    /** quando la pagina l'ha letta (ms) */
    lettaMs: number | null;
    /**
     * 25/09 (residui B17) - cash out globale: le posizioni che il servizio NON
     * ha chiuso (`result.non_chiuse`), col motivo scritto da lui. Assente o
     * vuoto = il servizio non ne dichiara.
     */
    nonChiuse?: PosizioneNonChiusa[];
}

/** Una posizione che il cash out globale NON ha chiuso (`result.non_chiuse`). */
export interface PosizioneNonChiusa {
    tradeId: number | null;
    motivo: string;
    /** l'ordine di chiusura era partito prima del fallimento (`closing_trade_id`) */
    closingTradeId: number | null;
}

/**
 * Come sono state trovate le righe dell'ordine di un clic:
 *  - `id`: id dichiarati dal servizio nel `result` della richiesta;
 *  - `chiave`: Mike, la chiave dell'approvazione scritta dal servizio sulla
 *    riga (`meta.approvazione_id` = id della richiesta `approva_uscita`);
 *  - `posizione`: chiusure (`closes_trade_id`) della posizione cliccata;
 *  - `correlazione`: RIPIEGO, le righe nuove del bot sulla partita;
 *  - `nessuno`: nessuna regola applicabile (apertura senza id, cash out
 *    globale senza id dichiarati).
 */
export type ModoGambe = 'id' | 'chiave' | 'posizione' | 'correlazione' | 'nessuno';

/** Una riga d'ordine trovata per il clic, con la sua provenienza. */
export interface GambaSeguita {
    id: number;
    riga: RigaOrdine;
    fonte: FonteGamba;
    /** eta' della notizia (s): ricezione del messaggio del canale o inizio della lettura del DB */
    etaS: number | null;
    /** `_seq` del messaggio del canale del bot, se la riga viene da li' */
    seq: number | null;
}

/** Una riga candidata (qualunque bot) nella forma che serve a `gambeDelClic`. */
export interface RigaCandidata {
    bot: Bot;
    id: number;
    eventId: string | null;
    chiudeId: number | null;
    ruolo: string | null;
    /** Mike: `meta.approvazione_id` (id della richiesta `approva_uscita`) */
    approvazioneId?: number | null;
}

export interface DeltaTick {
    /** medio meno riferimento, in tick della ladder Betfair (con segno) */
    tick: number;
    /** true = a favore del trader; null = nessuna differenza o lato ignoto */
    aFavore: boolean | null;
}

export interface EsitoGamba {
    fase: FaseEsito;
    chiesto: number | null;
    abbinato: number | null;
    residuo: number | null;
    /** prezzo MEDIO abbinato dichiarato (colonna/nota), mai il chiesto */
    prezzoMedio: number | null;
    /** prezzo chiesto (nota `esecuzione.price_richiesto` / `price_segnale` / colonna) */
    prezzoChiesto: number | null;
    motivo: string | null;
    /** parziale: il resto NON e' piu' sul book (FOK / annullato / scaduto) */
    restoAnnullato: boolean;
    /** non abbinato per il FILL OR KILL (il book non copriva la size) */
    fok: boolean;
    /** il servizio dichiara la riga abbinata ma non ha scritto i numeri dell'abbinamento */
    numeriDallaRiga: boolean;
    terminale: boolean;
}

export type TonoEsito = 'attesa' | 'ok' | 'parziale' | 'ko' | 'ignoto';

export interface EsitoAbbinamento {
    fase: FaseEsito;
    /** il messaggio principale */
    testo: string;
    /** con piu' gambe (combo, Mike): una riga per gamba */
    righe: string[];
    tono: TonoEsito;
    terminale: boolean;
    /** paper: abbinamento SIMULATO sul book vero (stesso messaggio del live) */
    simulato: boolean;
    prezzoMedio: number | null;
    abbinato: number | null;
    chiesto: number | null;
    residuo: number | null;
    deltaVisto: DeltaTick | null;
    deltaSegnale: DeltaTick | null;
    /** da dove viene l'esito, con l'eta' (regola dell'utente: eta' e fonte a video) */
    fonte: string;
}

// ---------------------------------------------------------------- utilita'
function num(v: unknown): number | null {
    if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/** una quota vale almeno 1,01: 0 (Betfair: «nessun medio») non e' un prezzo */
export function quotaValida(v: unknown): number | null {
    const n = num(v);
    return n !== null && n > 1 ? n : null;
}

function testo(v: unknown): string | null {
    if (v === null || v === undefined) return null;
    const s = String(v).trim();
    return s === '' ? null : s;
}

function oggetto(v: unknown): Record<string, unknown> {
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

// ------------------------------------------------------------------ tick
/** Differenza in tick fra il riferimento (visto/segnale) e il medio abbinato. */
export function deltaTick(riferimento: unknown, medio: unknown, lato: Lato | null): DeltaTick | null {
    const r = quotaValida(riferimento);
    const m = quotaValida(medio);
    if (r === null || m === null) return null;
    const tick = ticksBetween(r, m);
    const aFavore = tick === 0 || lato === null ? null : lato === 'back' ? tick > 0 : tick < 0;
    return { tick, aFavore };
}

/** «+2 tick a favore» / «−1 tick contro» / «0 tick» / «—». */
export function testoDelta(d: DeltaTick | null): string {
    if (!d) return DASH;
    if (d.tick === 0) return '0 tick';
    const segno = d.tick > 0 ? '+' : '−';
    const giudizio = d.aFavore === null ? '' : d.aFavore ? ' a favore' : ' contro';
    return `${segno}${Math.abs(d.tick)} tick${giudizio}`;
}

// ------------------------------------------------------------- la coda
/**
 * Gli id delle righe d'ordine dichiarati dal servizio nel `result` della
 * richiesta. APERTURA: `trade_id` / `trade_ids` (Safe `_request_place`,
 * `_request_place_combo`). CHIUSURA: `closing_trade_id` (`execution.
 * close_trade`, Safe e Omega) - il `trade_id` di una chiusura e' la
 * POSIZIONE chiusa, non l'ordine, e non si prende.
 */
export function idsDaRisultato(result: unknown, tipo: 'apertura' | 'chiusura'): number[] {
    const r = oggetto(result);
    const out: number[] = [];
    const metti = (v: unknown) => {
        const n = num(v);
        if (n !== null && Number.isInteger(n) && n > 0 && !out.includes(n)) out.push(n);
    };
    if (tipo === 'chiusura') {
        metti(r.closing_trade_id);
        if (Array.isArray(r.closing_trade_ids)) r.closing_trade_ids.forEach(metti);
        return out;
    }
    metti(r.trade_id);
    if (Array.isArray(r.trade_ids)) r.trade_ids.forEach(metti);
    return out;
}

/**
 * 25/09 (residui B17) - le posizioni NON chiuse da un cash out globale, dal
 * `result.non_chiuse` del servizio (Safe `_request_cashout_event`): ogni voce
 * e' `{trade_id, motivo, closing_trade_id?}`. Mai inventate: niente voce = [].
 */
export function nonChiuseDaRisultato(result: unknown): PosizioneNonChiusa[] {
    const r = oggetto(result);
    if (!Array.isArray(r.non_chiuse)) return [];
    return r.non_chiuse.map((v) => {
        const o = oggetto(v);
        const tid = num(o.trade_id);
        const cid = num(o.closing_trade_id);
        return {
            tradeId: tid !== null && Number.isInteger(tid) ? tid : null,
            motivo: (testo(o.motivo) ?? testo(o.message) ?? 'motivo non dichiarato dal servizio').replace(/_/g, ' '),
            closingTradeId: cid !== null && Number.isInteger(cid) && cid > 0 ? cid : null,
        };
    });
}

/** La chiave del seguito del CASH OUT GLOBALE di una partita (un clic = N ordini). */
export function chiaveCashOutPartita(bot: Bot, eventId: string): string {
    return `${bot}:cashout-partita:${eventId}`;
}

/** Come sono state trovate le gambe, a parole (a video accanto all'esito). */
export function testoModoGambe(m: ModoGambe): string {
    switch (m) {
    case 'id': return 'ordini dichiarati dal servizio (id nel risultato della richiesta)';
    case 'chiave': return 'ordini con la chiave dell\'approvazione, scritta dal servizio sulla riga';
    case 'posizione': return 'chiusure della posizione cliccata';
    case 'correlazione':
        return 'RIPIEGO: righe nuove del bot sulla partita dopo il clic (nessuna riga porta '
            + 'la chiave della richiesta)';
    default: return 'nessun ordine dichiarato dal servizio';
    }
}

// ---------------------------------------------------------- quali righe
/**
 * Le righe che SONO l'ordine di questo clic (id). Regole, in quest'ordine:
 *  1. id dichiarati dal servizio (`richiesta.tradeIds`), se la riga e' nota;
 *  2. un'APERTURA senza id del servizio: nessuna riga (non si indovina);
 *     idem un clic `soloIdDichiarati` (cash out globale di partita);
 *  3. chiusura di una posizione Omega/Safe: le gambe con `closes_trade_id`
 *     = quella posizione, nate DOPO il clic (non note al clic);
 *  4. per CHIAVE: le righe che portano `meta.approvazione_id` = id della
 *     richiesta del clic (Mike, uscita approvata: scritta dal servizio
 *     all'esecuzione, `Betfair/mike/service.py`);
 *  5. RIPIEGO dichiarato (Mike senza chiave, bot tennis che chiudono per
 *     partita): le righe NUOVE del bot su quella partita (non note al clic),
 *     del ruolo proposto se dichiarato, mai una riga con la chiave di
 *     un'ALTRA approvazione.
 */
export function gambeDelClicDettaglio(
    clic: ClicOrdine, richiesta: RichiestaSeguita | null, candidate: readonly RigaCandidata[],
): { ids: number[]; modo: ModoGambe } {
    const delBot = candidate.filter((c) => c.bot === clic.bot);
    const ids = richiesta?.tradeIds ?? [];
    if (ids.length) return { ids: ids.filter((id) => delBot.some((c) => c.id === id)), modo: 'id' };
    if (clic.tipo === 'apertura' || clic.soloIdDichiarati) return { ids: [], modo: 'nessuno' };
    const noti = new Set(clic.idsNotiAlClic);
    if (clic.tradeIdApertura !== null && (clic.bot === 'omega' || clic.bot === 'safe')) {
        return {
            ids: delBot
                .filter((c) => c.chiudeId === clic.tradeIdApertura && !noti.has(c.id))
                .map((c) => c.id),
            modo: 'posizione',
        };
    }
    if (clic.requestId !== null) {
        const conChiave = delBot.filter((c) => c.approvazioneId === clic.requestId);
        if (conChiave.length) return { ids: conChiave.map((c) => c.id), modo: 'chiave' };
    }
    if (clic.eventId === null) return { ids: [], modo: 'nessuno' };
    const ruoli = clic.ruoli && clic.ruoli.length ? new Set(clic.ruoli) : null;
    return {
        ids: delBot
            .filter((c) => c.eventId === clic.eventId && !noti.has(c.id)
                && c.approvazioneId == null
                && (ruoli === null || (c.ruolo !== null && ruoli.has(c.ruolo))))
            .map((c) => c.id),
        modo: 'correlazione',
    };
}

/** Solo gli id (la firma di prima, per i chiamanti che non guardano il modo). */
export function gambeDelClic(
    clic: ClicOrdine, richiesta: RichiestaSeguita | null, candidate: readonly RigaCandidata[],
): number[] {
    return gambeDelClicDettaglio(clic, richiesta, candidate).ids;
}

// ----------------------------------------------------- dalla mappa righe
/**
 * Una riga GREZZA di qualunque bot nella forma di `RigaOrdine`. Le righe dei
 * 4 bot tennis (`tennis_live_orders`) hanno `average_price_matched` e
 * `updated_at` (nomi dello specchio flumine) al posto di `avg_price_matched`
 * e `betfair_updated_at`: stesso numero, altro nome.
 */
export function comeRigaOrdine(r: Record<string, unknown>): RigaOrdine {
    const tennis = r.average_price_matched !== undefined && r.avg_price_matched === undefined;
    return {
        status: testo(r.status),
        side: testo(r.side),
        price: num(r.price),
        size: num(r.size),
        size_requested: tennis ? num(r.size) : num(r.size_requested),
        size_matched: num(r.size_matched),
        size_remaining: num(r.size_remaining),
        avg_price_matched: tennis ? num(r.average_price_matched) : num(r.avg_price_matched),
        betfair_updated_at: tennis ? testo(r.updated_at) : testo(r.betfair_updated_at),
        meta: (r.meta && typeof r.meta === 'object' && !Array.isArray(r.meta))
            ? (r.meta as Record<string, unknown>) : null,
    };
}

/** Le righe della mappa (posizioni dei bot) come candidate di `gambeDelClic`. */
export function candidateDallaMappa(mappa: MappaRighe<unknown>): RigaCandidata[] {
    const out: RigaCandidata[] = [];
    for (const v of mappa.voci.values()) {
        const r = vistaVoce(v) as Record<string, unknown>;
        const id = num(r.id);
        if (id === null) continue;
        const meta = oggetto(r.meta);
        const chiude = num(r.closes_trade_id) ?? num(meta.closes_trade_id);
        const appr = num(meta.approvazione_id);
        out.push({
            bot: v.bot, id,
            eventId: testo(r.event_id),
            chiudeId: chiude,
            ruolo: testo(r.role),
            // la chiave c'e' solo sulle righe che la portano (Mike, uscita approvata)
            ...(appr !== null && Number.isInteger(appr) && appr > 0 ? { approvazioneId: appr } : {}),
        });
    }
    return out;
}

/** La riga `id` del bot dalla mappa, con fonte, eta' e `_seq` del canale. */
export function gambaDallaMappa(
    mappa: MappaRighe<unknown>, bot: Bot, id: number, nowMs: number,
): GambaSeguita | null {
    const v = mappa.voci.get(chiaveRiga(bot, id));
    if (!v) return null;
    const riga = comeRigaOrdine(vistaVoce(v) as Record<string, unknown>);
    const dalCanale = v.canale !== null && v.ricevutoMs !== null;
    const at = dalCanale ? (v.ricevutoMs as number) : v.dbMs;
    return {
        id, riga,
        fonte: dalCanale ? 'canale' : 'database',
        etaS: Math.max(0, Math.round((nowMs - at) / 1000)),
        seq: dalCanale ? v.canaleSeq : null,
    };
}

// ------------------------------------------------------------- una gamba
const NOTA_FOK = /fok|not_matched|no_fill|nessun_fill|lapsed|expired/i;
const STATO_FOK_UCCISO = /^live_not_matched[:.](EXPIRED|LAPSED|EXECUTION_COMPLETE|CANCELLED)$/;

/** L'esito di UNA riga d'ordine, dai suoi campi veri. */
export function esitoGamba(r: RigaOrdine): EsitoGamba {
    const s = statoOrdine(r);
    const meta = oggetto(r.meta);
    const stato = String(r.status ?? '');
    const stL = stato.toLowerCase();
    const stU = stato.toUpperCase();
    const nota = testo(meta.fill) ?? testo(meta.reason) ?? testo(meta.fill_note);
    const a = s.abbinato.valore;
    const res = s.residuo.valore;
    // il CHIESTO: dichiarato; su una riga ancora 'pending' la `size` e' il chiesto
    const chiesto = s.chiesto.valore ?? (stL === 'pending' ? num(r.size) : null);
    const base = {
        chiesto, abbinato: a, residuo: res,
        prezzoMedio: s.prezzoMedio.valore, prezzoChiesto: s.prezzoChiesto.valore,
        motivo: null as string | null, restoAnnullato: false, fok: false,
        numeriDallaRiga: false,
    };
    const conAbbinato = (annullatoIlResto: boolean): EsitoGamba => {
        const manca = chiesto !== null && a !== null && a + EPS < chiesto;
        if (manca && (annullatoIlResto || res === null || res <= EPS)) {
            return { ...base, fase: 'parziale', restoAnnullato: true, terminale: true };
        }
        if (res !== null && res > EPS) return { ...base, fase: 'parziale', terminale: false };
        return { ...base, fase: 'totale', terminale: true };
    };

    // FOK ucciso da Betfair: `live_not_matched:EXPIRED` (execution.py:833) NON e'
    // un rifiuto (lo stato dell'ordine non e' un codice d'errore): la regola dei
    // codici di `statoOrdine` lo leggerebbe come «RIFIUTATO: EXPIRED».
    if (nota && STATO_FOK_UCCISO.test(nota) && !testo(meta.error_code)) {
        return { ...base, fase: 'non_abbinato', fok: true, motivo: nota, terminale: true };
    }
    if (s.esito === 'rifiutato') {
        return { ...base, fase: 'rifiutato', motivo: `Betfair: ${s.errorCode}`, terminale: true };
    }
    if (stL === 'error') {
        if (nota && NOTA_FOK.test(nota)) {
            return { ...base, fase: 'non_abbinato', fok: true, motivo: nota, terminale: true };
        }
        return { ...base, fase: 'rifiutato', motivo: nota ?? 'errore del servizio (motivo non scritto)', terminale: true };
    }
    if (s.esito === 'riconciliazione') {
        return { ...base, fase: 'ignoto', motivo: 'esito IGNOTO: in riconciliazione con Betfair', terminale: false };
    }
    if (TERMINALI_FLUMINE.has(stU)) {
        if (a !== null && a > EPS) return conAbbinato(true);
        return { ...base, fase: 'non_abbinato', motivo: `stato Betfair ${stU}`, terminale: true };
    }
    if (s.esito === 'annullato') {
        if (a !== null && a > EPS) return conAbbinato(true);
        return { ...base, fase: 'non_abbinato', motivo: 'ordine annullato', terminale: true };
    }
    if (s.esito === 'parziale' || s.esito === 'abbinato') return conAbbinato(false);
    if (s.esito === 'appoggiato') return { ...base, fase: 'accettato', terminale: false };
    if (s.esito === 'regolato' || ['open', 'hedged', 'closed', 'matched'].includes(stL)) {
        // il servizio dichiara la riga ABBINATA (Safe/Omega/Mike: 'open' = fill
        // confermato) ma non ha scritto i numeri: si dice, non si inventa
        return {
            ...base, fase: 'totale', abbinato: a ?? num(r.size), numeriDallaRiga: a === null,
            terminale: true,
        };
    }
    if (stL === 'pending' || stL === 'reserved' || stU === 'EXECUTABLE' || stU === 'PENDING') {
        return { ...base, fase: 'in_corso', motivo: 'in attesa dell’esito da Betfair', terminale: false };
    }
    return { ...base, fase: 'ignoto', motivo: 'la riga non porta i numeri dell’abbinamento', terminale: false };
}

// ------------------------------------------------------------- i testi
function testoGamba(g: EsitoGamba, riga: RigaOrdine, clic: ClicOrdine, lato: Lato | null): string {
    const dv = deltaTick(clic.prezzoVisto, g.prezzoMedio, lato);
    const ds = deltaTick(clic.prezzoSegnale, g.prezzoMedio, lato);
    const delta = `(Δ vs visto ${testoDelta(dv)}, vs segnale ${testoDelta(ds)})`;
    switch (g.fase) {
    case 'totale':
        if (g.prezzoMedio === null) {
            return `ABBINATO TOTALMENTE (prezzo medio non dichiarato dal servizio; prezzo della riga `
                + `${fmtOdds(riga.price)}), size ${fmtMoney(g.abbinato)}`;
        }
        return `ABBINATO TOTALMENTE a prezzo medio ${fmtOdds(g.prezzoMedio)} ${delta}, size ${fmtMoney(g.abbinato)}`;
    case 'parziale':
        return `ABBINATO PARZIALMENTE: ${fmtMoney(g.abbinato)} su ${fmtMoney(g.chiesto)} a `
            + `${fmtOdds(g.prezzoMedio)} ${delta}, `
            + (g.restoAnnullato ? 'resto annullato' : `resto ${fmtMoney(g.residuo)} in attesa sul book`);
    case 'accettato':
        return `accettato da Betfair a ${fmtOdds(g.prezzoChiesto)}: in attesa di abbinamento`
            + (g.residuo !== null ? `, ${fmtMoney(g.residuo)} sul book` : '');
    case 'non_abbinato':
        return g.fok
            ? 'NON abbinato (FOK): il book non copriva l’intera size, ordine ucciso senza abbinamento'
            : `NON abbinato: ${g.motivo ?? 'ordine chiuso senza abbinamento'}`;
    case 'rifiutato':
        return `rifiutato: ${g.motivo ?? 'motivo non dichiarato'}`;
    case 'in_corso':
        return `inviato: ${g.motivo ?? 'in attesa dell’esito da Betfair'}`;
    default:
        return `esito non ancora dichiarato: ${g.motivo ?? 'la riga non porta i numeri dell’abbinamento'}`;
    }
}

const TONO: Record<FaseEsito, TonoEsito> = {
    inviato: 'attesa', in_corso: 'attesa', accettato: 'attesa', parziale: 'parziale',
    totale: 'ok', non_abbinato: 'ko', rifiutato: 'ko', ignoto: 'ignoto',
};

function latoDi(v: unknown): Lato | null {
    const s = String(v ?? '').toLowerCase();
    return s === 'back' || s === 'lay' ? s : null;
}

/** Fonte ed eta' di una gamba, a parole. */
export function fonteGamba(g: GambaSeguita): string {
    const meta = oggetto(g.riga.meta);
    const seqRunner = num(meta.canale_seq);
    const faseRunner = testo(meta.canale_fase);
    const base = g.fonte === 'canale'
        ? `canale del bot al ms${g.seq !== null ? ` (seq ${g.seq})` : ''}`
        : 'database (ripiego: lettura del blocco del bot)';
    const eta = g.etaS === null ? '' : ` · ${fmtAge(g.etaS)} fa`;
    const runner = seqRunner !== null
        ? ` · esito Betfair dal canale ordini del runner (seq ${seqRunner}${faseRunner ? `, ${faseRunner}` : ''})`
        : '';
    return `${base}${eta}${runner}`;
}

/** Fonte ed eta' della sola coda (nessuna riga d'ordine ancora). */
export function fonteRichiesta(r: RichiestaSeguita | null, nowMs: number): string {
    if (!r || r.lettaMs === null) return 'coda del bot: non ancora letta';
    return `coda del bot (riletta ogni 2 s) · ${fmtAge((nowMs - r.lettaMs) / 1000)} fa`;
}

/**
 * IL MESSAGGIO del clic. `gambe` = le righe d'ordine trovate (`gambeDelClic` +
 * `gambaDallaMappa`), `richiesta` = la riga della coda del bot.
 */
export function esitoAbbinamento(
    clic: ClicOrdine, richiesta: RichiestaSeguita | null,
    gambe: readonly GambaSeguita[], nowMs: number,
): EsitoAbbinamento {
    const simulato = clic.modo === 'paper';
    const vuoto = {
        righe: [] as string[], simulato, prezzoMedio: null, abbinato: null, chiesto: null,
        residuo: null, deltaVisto: null, deltaSegnale: null,
    };
    const scaduto = nowMs - clic.clicMs >= SCADENZA_SEGUITO_MS;

    if (gambe.length === 0) {
        const fonte = fonteRichiesta(richiesta, nowMs);
        const f = richiesta?.fase ?? 'inviata';
        if (f === 'rifiutata' && richiesta?.motivo && NOTA_FOK.test(richiesta.motivo)
            && !/rifiutato|INSUFFICIENT|INVALID/.test(richiesta.motivo)) {
            // il servizio ha piazzato ma il FOK non si e' abbinato (Safe:
            // «non eseguito: non_eseguito (paper_fok_parziale:0.43/5)»)
            return { ...vuoto, fase: 'non_abbinato', tono: 'ko', terminale: true, fonte,
                testo: 'NON abbinato (FOK): il book non copriva l’intera size, ordine ucciso senza abbinamento'
                    + ` [${richiesta.motivo}]` };
        }
        if (f === 'rifiutata') {
            return { ...vuoto, fase: 'rifiutato', tono: 'ko', terminale: true, fonte,
                testo: `rifiutato: ${richiesta?.motivo ?? 'motivo non dichiarato dal servizio'}` };
        }
        if (f === 'ignota') {
            return { ...vuoto, fase: 'ignoto', tono: 'ignoto', terminale: true, fonte,
                testo: `esito ignoto: ${richiesta?.motivo ?? 'stato della richiesta non riconosciuto'}` };
        }
        if (f === 'eseguita' && clic.soloIdDichiarati && richiesta && richiesta.tradeIds.length === 0) {
            // 25/09 (residui B17) - cash out globale eseguito SENZA nessun
            // ordine di chiusura dichiarato: non c'e' niente da aspettare
            const nc = richiesta.nonChiuse ?? [];
            return { ...vuoto, fase: nc.length ? 'rifiutato' : 'ignoto', tono: nc.length ? 'ko' : 'ignoto',
                terminale: true, fonte,
                testo: `nessun ordine di chiusura partito: ${richiesta.motivo ?? 'il servizio non ne dichiara'}` };
        }
        if (scaduto) {
            return { ...vuoto, fase: 'ignoto', tono: 'ignoto', terminale: true, fonte,
                testo: 'esito ignoto: nessuna riga d’ordine da 3 minuti, controlla la riga prima di riprovare' };
        }
        if (f === 'eseguita') {
            return { ...vuoto, fase: 'in_corso', tono: 'attesa', terminale: false, fonte,
                testo: `in corso: ${richiesta?.motivo ?? 'il servizio ha eseguito la richiesta'}`
                    + ' · in attesa della riga dell’ordine' };
        }
        if (f === 'presa_in_carico') {
            return { ...vuoto, fase: 'in_corso', tono: 'attesa', terminale: false, fonte,
                testo: 'in corso: il bot sta eseguendo la richiesta' };
        }
        return { ...vuoto, fase: 'inviato', tono: 'attesa', terminale: false, fonte,
            testo: 'inviato: in attesa del servizio' };
    }

    const esiti = gambe.map((g) => esitoGamba(g.riga));
    const lati = gambe.map((g) => clic.lato ?? latoDi(g.riga.side));
    const righe = esiti.map((e, i) => testoGamba(e, gambe[i].riga, clic, lati[i]));

    // la fase complessiva: la prima NON terminale (il clic non e' finito),
    // altrimenti tutte uguali -> quella; miste -> parziale
    let fase: FaseEsito;
    const aperta = esiti.find((e) => !e.terminale);
    if (aperta) fase = aperta.fase;
    else if (esiti.every((e) => e.fase === esiti[0].fase)) fase = esiti[0].fase;
    else if (esiti.some((e) => e.fase === 'totale' || e.fase === 'parziale')) fase = 'parziale';
    else fase = esiti[0].fase;
    let terminale = esiti.every((e) => e.terminale);

    // numeri complessivi: somme solo se TUTTI dichiarati; medio pesato sull'abbinato
    const somma = (k: 'abbinato' | 'chiesto' | 'residuo'): number | null =>
        (esiti.every((e) => e[k] !== null) ? esiti.reduce((t, e) => t + (e[k] as number), 0) : null);
    const abbinato = somma('abbinato');
    const pesati = esiti.filter((e) => e.prezzoMedio !== null && e.abbinato !== null && e.abbinato > EPS);
    const pesoTot = pesati.reduce((t, e) => t + (e.abbinato as number), 0);
    const prezzoMedio = pesati.length === esiti.filter((e) => (e.abbinato ?? 0) > EPS).length && pesoTot > EPS
        ? pesati.reduce((t, e) => t + (e.prezzoMedio as number) * (e.abbinato as number), 0) / pesoTot
        : null;
    const latoUnico = lati.every((l) => l === lati[0]) ? lati[0] : null;

    let testoPrincipale = righe.length === 1
        ? righe[0]
        : `${righe.length} gambe: ${righe.map((t, i) => `gamba ${i + 1} ${t}`).join(' | ')}`;
    if (!terminale && scaduto) {
        terminale = true;
        fase = 'ignoto';
        testoPrincipale += ' · nessun esito finale da 3 minuti: controlla la riga prima di riprovare';
    }
    // la gamba piu' fresca da' fonte ed eta'
    const fresca = [...gambe].sort((x, y) => (x.etaS ?? Infinity) - (y.etaS ?? Infinity))[0];

    return {
        fase, testo: testoPrincipale, righe, tono: TONO[fase], terminale, simulato,
        prezzoMedio, abbinato, chiesto: somma('chiesto'), residuo: somma('residuo'),
        deltaVisto: deltaTick(clic.prezzoVisto, prezzoMedio, latoUnico),
        deltaSegnale: deltaTick(clic.prezzoSegnale, prezzoMedio, latoUnico),
        fonte: fonteGamba(fresca),
    };
}

/** Tutto insieme: dalla mappa delle righe e dalla coda al messaggio. */
export function esitoDelClic(
    clic: ClicOrdine, richiesta: RichiestaSeguita | null,
    mappa: MappaRighe<unknown>, nowMs: number,
): { esito: EsitoAbbinamento; gambe: GambaSeguita[]; modoGambe: ModoGambe } {
    const { ids, modo } = gambeDelClicDettaglio(clic, richiesta, candidateDallaMappa(mappa));
    const gambe = ids
        .map((id) => gambaDallaMappa(mappa, clic.bot, id, nowMs))
        .filter((g): g is GambaSeguita => g !== null);
    return { esito: esitoAbbinamento(clic, richiesta, gambe, nowMs), gambe, modoGambe: modo };
}

/** Le righe del bot sulla partita note ADESSO (da salvare nel clic). */
export function idsNotiSullaPartita(mappa: MappaRighe<unknown>, bot: Bot, eventId: string | null): number[] {
    if (eventId === null) return [];
    return candidateDallaMappa(mappa)
        .filter((c) => c.bot === bot && (c.eventId === eventId))
        .map((c) => c.id);
}

/** Aggiunge un clic in testa (sostituisce quello con la stessa chiave), al massimo `MAX_SEGUITI`. */
export function aggiungiSeguito(prima: readonly ClicOrdine[], clic: ClicOrdine): ClicOrdine[] {
    return [clic, ...prima.filter((c) => c.chiave !== clic.chiave)].slice(0, MAX_SEGUITI);
}
