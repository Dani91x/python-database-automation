// ============================================================================
// statoOrdine.ts — LO STATO DI UN ORDINE, uguale per TUTTI i bot (C.12b).
//
// Domanda dell'utente, 16/09/2026: «ordine x a prezzo y: abbinato? in che
// quantita'? tutto o parziale? In UI il trader ha queste informazioni?».
// Fino a oggi la risposta era NO per Omega, Safe e la Control Room: mostravano
// UN solo `size` (che dopo la conferma e' l'ABBINATO, non il chiesto) e nessun
// prezzo medio; un ordine solo APPOGGIATO sul book compariva come «APERTO».
//
// Qui si legge, in quest'ordine e senza inventare niente:
//   1. le COLONNE della migrazione `trades_consapevolezza_ordine_2026-09-16.sql`
//      (`size_requested`, `size_matched`, `size_remaining`, `avg_price_matched`,
//      `betfair_updated_at`) — la verita' scritta dal servizio;
//   2. se le colonne non ci sono (migrazione non applicata), le NOTE nel `meta`
//      che i tre servizi scrivono comunque (`requested_size` di Omega,
//      `size_capped_from` di Safe/Mike, `esecuzione.{size_richiesta,
//      size_abbinata,size_residua,price_medio,price_richiesto,scorrimento_tick}`,
//      `size_remaining` / `betfair_updated_at` nel meta di Omega) — e lo si
//      DICHIARA con `fonte: 'nota'`, cosi' il trader sa che e' un ripiego;
//   3. niente. In quel caso il valore e' `null` e la UI scrive «—»:
//      MAI «0,00 €», MAI il prezzo chiesto al posto del prezzo medio assente
//      (regola di `lib/format.ts:44-54`, reperto n. 5 della MATRICE).
//
// Cosa NON fa, di proposito:
//   · non deduce il RESIDUO da chiesto-abbinato (sarebbe un'ipotesi, non un
//     fatto: e' il reperto n. 15 della MATRICE su Mike);
//   · non deduce l'ABBINATO da `size` (dopo la conferma `size` E' l'abbinato,
//     ma su una riga `pending` non lo e' affatto);
//   · non ricalcola la soglia del «parziale»: la decide il backend quando
//     scrive `place_parziale`; qui si guardano solo i numeri che ha pubblicato.
//
// Tutto PURO: nessun React, nessuna chiamata di rete.
// ============================================================================
import { fmtMoney, fmtOdds, fmtTicks, DASH } from '@/lib/format';
import {
    RESTING_META, RECONCILING_META, STATUS_META, isReconcilingMeta, type Meta,
} from '@/lib/tradeStatus';

/** da dove arriva un numero: colonna del DB, nota nel `meta`, oppure niente */
export type FonteValore = 'colonna' | 'nota' | 'assente';

/** un numero con la sua PROVENIENZA dichiarata */
export interface ValoreOrdine {
    valore: number | null;
    fonte: FonteValore;
}

/** sempre un oggetto NUOVO: chi lo riceve puo' sovrascriverlo senza effetti a distanza */
const assente = (): ValoreOrdine => ({ valore: null, fonte: 'assente' });

/**
 * Esito dell'ordine secondo BETFAIR (non secondo lo stato della riga).
 * `appoggiato` e `abbinato` sono due cose diverse: la prima non copre niente.
 */
export type EsitoOrdine =
    | 'appoggiato' | 'parziale' | 'abbinato' | 'annullato'
    | 'rifiutato' | 'riconciliazione' | 'regolato' | 'ignoto';

export interface StatoOrdine {
    /** size CHIESTA a Betfair (prima del cap e del fill) */
    chiesto: ValoreOrdine;
    /** prezzo CHIESTO */
    prezzoChiesto: ValoreOrdine;
    /** size ABBINATA dichiarata da Betfair */
    abbinato: ValoreOrdine;
    /** prezzo MEDIO realmente abbinato (mai il prezzo chiesto travestito) */
    prezzoMedio: ValoreOrdine;
    /** residuo ANCORA VIVO sul book secondo Betfair */
    residuo: ValoreOrdine;
    /** scorrimento in tick fra prezzo chiesto e prezzo medio (meta.esecuzione) */
    scorrimento: ValoreOrdine;
    esito: EsitoOrdine;
    /** etichetta + colore dell'esito (mappe condivise, nessun doppione) */
    meta: Meta;
    /** codice di rifiuto di Betfair, in chiaro (INSUFFICIENT_FUNDS, ...) */
    errorCode: string | null;
    /** quando l'abbiamo saputo DA BETFAIR (ISO), non l'ora del nostro processo */
    aggiornatoAl: string | null;
    aggiornatoDa: FonteValore;
    /** true = almeno un numero viene dal `meta` e non da una colonna */
    dallaNota: boolean;
}

/** riga di trade di QUALSIASI bot: si guardano solo i campi che servono */
export interface RigaOrdine {
    status?: string | null;
    side?: string | null;
    price?: number | null;
    size?: number | null;
    // colonne della migrazione del 16/09 (assenti finche' non e' applicata)
    size_requested?: number | null;
    size_matched?: number | null;
    size_remaining?: number | null;
    avg_price_matched?: number | null;
    betfair_updated_at?: string | null;
    meta?: Record<string, unknown> | null;
}

/** numero finito e non negativo, altrimenti null (una stringa numerica va bene) */
function num(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/**
 * Una QUOTA vale almeno 1,01: Betfair (e lo specchio `betfair_live_orders`)
 * scrivono `averagePriceMatched = 0` quando il prezzo medio NON ESISTE, e uno
 * «0,00» sotto l'etichetta «prezzo medio» e' un numero falso, non un dato.
 */
function quota(v: unknown): number | null {
    const n = num(v);
    return n !== null && n > 1 ? n : null;
}

/** primo valore presente fra le colonne, poi fra le note. Mai un default. */
function scegli(colonna: unknown, note: readonly unknown[]): ValoreOrdine {
    const c = num(colonna);
    if (c !== null) return { valore: c, fonte: 'colonna' };
    for (const n of note) {
        const v = num(n);
        if (v !== null) return { valore: v, fonte: 'nota' };
    }
    return assente();
}

function testo(v: unknown): string | null {
    if (v === null || v === undefined) return null;
    const s = String(v).trim();
    return s === '' ? null : s;
}

function oggetto(v: unknown): Record<string, unknown> {
    return v && typeof v === 'object' && !Array.isArray(v)
        ? (v as Record<string, unknown>)
        : {};
}

/** esiti CERTI: una riga regolata non torna «appoggiata» */
const REGOLATI = new Set(['won', 'lost', 'void']);

/** tolleranza sui centesimi: sotto questa soglia un residuo non esiste */
const EPS = 0.005;

// ---------------------------------------------------------------- etichette
const M_PARZIALE: Meta = {
    label: 'ABBINATO IN PARTE',
    cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
};
const M_ABBINATO: Meta = {
    label: 'ABBINATO',
    cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
};
const M_ANNULLATO: Meta = {
    label: 'ANNULLATO',
    cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
};
const M_RIFIUTATO: Meta = {
    label: 'RIFIUTATO DA BETFAIR',
    cls: 'bg-red-500/15 text-red-300 border-red-500/40',
};
/**
 * Non sappiamo. NON e' «non abbinato»: il reperto n. 5 della MATRICE nasce
 * proprio dal trattare l'assenza di dato come uno zero.
 */
const M_IGNOTO: Meta = {
    label: 'ESITO NON DICHIARATO',
    cls: 'bg-white/5 text-slate-400 border-white/10',
};

/** codice di rifiuto scritto dal servizio, dovunque l'abbia messo */
function codiceRifiuto(meta: Record<string, unknown>): string | null {
    const diretto = testo(meta['error_code']);
    if (diretto) return diretto.toUpperCase();
    // `live_rifiutato:<CODICE>` / `live_not_matched:<stato>:<CODICE>`
    // (execution.py:562,585 — la nota finisce in `meta.fill` o `meta.reason`)
    for (const k of ['fill', 'reason', 'fill_note'] as const) {
        const s = testo(meta[k]);
        if (!s) continue;
        const m = /^live_(?:rifiutato|not_matched)[:.](?:[A-Za-z_]+[:.])?([A-Z][A-Z_]{3,})$/.exec(s);
        if (m && m[1] !== 'SENZA_CODICE') return m[1];
    }
    return null;
}

/**
 * Lo stato dell'ordine di UNA riga di trade, per qualunque bot.
 *
 * Nessun parametro «quale bot»: i tre servizi scrivono le stesse colonne e le
 * stesse note (`safe_strategy/execution.py` e' il layer condiviso), e una
 * regola sola e' l'unico modo perche' la stessa cosa si legga nello stesso
 * modo in Omega, in Safe, in Mike e nella Control Room.
 */
export function statoOrdine(riga: RigaOrdine | null | undefined): StatoOrdine {
    const r = riga ?? {};
    const meta = oggetto(r.meta);
    const esec = oggetto(meta['esecuzione']);

    const chiesto = scegli(r.size_requested, [
        meta['requested_size'],      // Omega (omega_service.py:1527)
        meta['size_capped_from'],    // Safe/Mike (execution.py:407)
        esec['size_richiesta'],      // catena dei tempi (execution.py:497,614)
    ]);
    const abbinato = scegli(r.size_matched, [
        meta['size_matched'],
        esec['size_abbinata'],
    ]);
    const residuo = scegli(r.size_remaining, [
        meta['size_remaining'],      // Omega lo mette nel meta (omega_service.py:1656)
        esec['size_residua'],
    ]);
    const prezzoMedio = scegli(quota(r.avg_price_matched), [
        quota(meta['avg_price_matched']),
        quota(esec['price_medio']),
    ]);
    // il prezzo CHIESTO: la nota lo conserva esatto; la colonna `price` dopo la
    // conferma porta il medio, e lo si dichiara nel tooltip di chi la mostra.
    const prezzoChiesto = scegli(undefined, [
        quota(esec['price_richiesto']),
        quota(meta['price_segnale']),
    ]);
    if (prezzoChiesto.valore === null) {
        const p = quota(r.price);
        if (p !== null) { prezzoChiesto.valore = p; prezzoChiesto.fonte = 'colonna'; }
    }
    const scorrimento = scegli(undefined, [esec['scorrimento_tick']]);

    const quandoColonna = testo(r.betfair_updated_at);
    const quandoNota = testo(meta['betfair_updated_at']) ?? testo(meta['aggiornato_al']);
    const aggiornatoAl = quandoColonna ?? quandoNota;
    const aggiornatoDa: FonteValore = quandoColonna ? 'colonna' : quandoNota ? 'nota' : 'assente';

    const errorCode = codiceRifiuto(meta);
    const stato = String(r.status ?? '').toLowerCase();
    const fill = testo(meta['fill']) ?? '';
    const phase = testo(meta['phase']) ?? '';

    const a = abbinato.valore;
    const res = residuo.valore;

    let esito: EsitoOrdine;
    let metaEsito: Meta;
    if (REGOLATI.has(stato)) {
        esito = 'regolato';
        metaEsito = STATUS_META[stato as 'won' | 'lost' | 'void'];
    } else if (errorCode) {
        esito = 'rifiutato';
        metaEsito = { ...M_RIFIUTATO, label: `${M_RIFIUTATO.label}: ${errorCode}` };
    } else if (isReconcilingMeta(r.status, meta)) {
        esito = 'riconciliazione';
        metaEsito = RECONCILING_META;
    } else if (phase === 'cancelled' || stato === 'cancelled') {
        esito = 'annullato';
        metaEsito = M_ANNULLATO;
    } else if (a !== null && a > EPS && res !== null && res > EPS) {
        esito = 'parziale';
        metaEsito = M_PARZIALE;
    } else if (a !== null && a > EPS && res !== null && res <= EPS) {
        esito = 'abbinato';
        metaEsito = M_ABBINATO;
    } else if ((a === null || a <= EPS) && res !== null && res > EPS) {
        esito = 'appoggiato';
        metaEsito = RESTING_META;
    } else if (a !== null && a > EPS) {
        // abbinato noto, residuo IGNOTO: e' comunque una posizione a mercato
        esito = 'abbinato';
        metaEsito = M_ABBINATO;
    } else if (/resting/.test(fill)) {
        // nessun numero, ma il servizio ha detto che l'ordine sta sul book
        esito = 'appoggiato';
        metaEsito = RESTING_META;
    } else {
        esito = 'ignoto';
        metaEsito = M_IGNOTO;
    }

    const dallaNota = [chiesto, abbinato, residuo, prezzoMedio, scorrimento]
        .some((v) => v.fonte === 'nota') || aggiornatoDa === 'nota';

    return {
        chiesto, prezzoChiesto, abbinato, prezzoMedio, residuo, scorrimento,
        esito, meta: metaEsito, errorCode, aggiornatoAl, aggiornatoDa, dallaNota,
    };
}

/**
 * true = l'ordine e' solo APPOGGIATO sul book. Serve a `statusMeta({resting})`:
 * una riga cosi' non e' «APERTA», non copre niente e il rischio e' ancora
 * tutto scoperto (certificazione 12/09, `RESTING_META`).
 */
export function ordineAppoggiato(riga: RigaOrdine | null | undefined): boolean {
    return statoOrdine(riga).esito === 'appoggiato';
}

/** eta' in secondi dell'ultima notizia da Betfair; null se non la sappiamo */
export function etaBetfairSec(s: StatoOrdine, nowMs: number): number | null {
    if (!s.aggiornatoAl) return null;
    const ms = Date.parse(s.aggiornatoAl);
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.round((nowMs - ms) / 1000));
}

/** denaro di un `ValoreOrdine`: assente = «—», mai «0,00 €» */
export function valoreMoney(v: ValoreOrdine): string {
    return v.valore === null ? DASH : fmtMoney(v.valore);
}

/** quota di un `ValoreOrdine`: assente = «—», mai il prezzo chiesto al suo posto */
export function valoreOdds(v: ValoreOrdine): string {
    return v.valore === null ? DASH : fmtOdds(v.valore);
}

/** scorrimento in tick: assente = «—» */
export function valoreTicks(v: ValoreOrdine): string {
    return v.valore === null ? DASH : fmtTicks(v.valore);
}

/**
 * Riga di testo compatta: «chiesti 5,00 € @2,40 · abbinati 2,00 € @2,38 ·
 * residuo 3,00 €». Serve dove non c'e' spazio per la griglia (Control Room).
 */
export function statoOrdineTesto(s: StatoOrdine): string {
    // nessuno dei tre numeri esiste: lo si DICE una volta, invece di allineare
    // tre «—» che sembrano un guasto della pagina. Non e' mai uno zero.
    if (s.chiesto.valore === null && s.abbinato.valore === null && s.residuo.valore === null) {
        return 'abbinamento non dichiarato dal servizio';
    }
    const parti: string[] = [];
    parti.push(`chiesti ${valoreMoney(s.chiesto)}${s.prezzoChiesto.valore !== null ? ` @${valoreOdds(s.prezzoChiesto)}` : ''}`);
    parti.push(`abbinati ${valoreMoney(s.abbinato)}${s.prezzoMedio.valore !== null ? ` @${valoreOdds(s.prezzoMedio)}` : ''}`);
    parti.push(`residuo ${valoreMoney(s.residuo)}`);
    return parti.join(' · ');
}

/** tooltip unico: cosa significano i tre numeri e da dove vengono */
export function statoOrdineTitolo(s: StatoOrdine): string {
    const fonte = (v: ValoreOrdine) => (v.fonte === 'colonna' ? 'da Betfair'
        : v.fonte === 'nota' ? 'dalla nota del servizio' : 'non dichiarato');
    return [
        `chiesto: ${valoreMoney(s.chiesto)} (${fonte(s.chiesto)})`,
        `abbinato: ${valoreMoney(s.abbinato)} (${fonte(s.abbinato)})`,
        `residuo vivo sul book: ${valoreMoney(s.residuo)} (${fonte(s.residuo)})`,
        `prezzo medio abbinato: ${valoreOdds(s.prezzoMedio)} (${fonte(s.prezzoMedio)})`,
        s.scorrimento.valore !== null ? `scorrimento: ${valoreTicks(s.scorrimento)}` : null,
        s.errorCode ? `codice di rifiuto di Betfair: ${s.errorCode}` : null,
        s.dallaNota ? 'almeno un numero viene dalla nota del servizio, non dalle colonne' : null,
    ].filter(Boolean).join(' · ');
}
