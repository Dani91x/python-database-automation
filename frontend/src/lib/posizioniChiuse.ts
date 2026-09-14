// ============================================================================
// posizioniChiuse.ts — LE POSIZIONI GIÀ CHIUSE, vinte e perse.
//
// «scheda "Posizioni chiuse": qui ci andranno tutte le posizioni VINCENTI E
// PERDENTI, filtrabili chiaramente, PNL GLOBALE DELLA POSIZIONE, pnl
// dettaglio» (utente, 14/09).
//
// DUE LIVELLI DI P&L, e la differenza è tutto il punto:
//   · **globale** = quanto ha reso la POSIZIONE, apertura e chiusure sommate.
//     È il numero che dice se quell'operazione è andata bene.
//   · **dettaglio** = le singole righe. Su una posizione coperta l'apertura
//     vince e la copertura perde: guardare solo le righe fa sembrare un
//     green-up riuscito una sconfitta a metà.
//
// LA REGOLA DI SEMPRE: **paper e live non si sommano.** Una posizione è
// dell'una o dell'altra modalità; due modalità sulla stessa partita sono due
// posizioni diverse, e questa pagina non le mette mai nella stessa riga.
// ============================================================================
import { isSettled, isErrorRow } from '@/lib/eventGroups';
import type { Bot, Modo } from '@/lib/controlRoom';
import { modoDi } from '@/lib/controlRoom';

export type Esito = 'vinta' | 'persa' | 'pari';

/** Una riga di una posizione chiusa: l'apertura o una delle sue chiusure. */
export interface RigaChiusa {
    id: number;
    bot: Bot;
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    prezzo: number | null;
    size: number | null;
    /** netto di commissione; null = non regolata */
    pnl: number | null;
    stato: string;
    at: string;
    /** è la gamba di copertura di un'altra riga? */
    chiusura: boolean;
    quale: string | null;
}

export interface PosizioneChiusa {
    /** id della riga di APERTURA: identifica la posizione */
    id: number;
    eventId: string;
    partita: string;
    sport: 'calcio' | 'tennis';
    modo: Modo;
    bot: Bot;
    /** P&L della posizione INTERA: apertura + coperture */
    pnlGlobale: number;
    /** vinta / persa / pari, dal P&L globale */
    esito: Esito;
    /** le righe che la compongono, in ordine di tempo */
    righe: RigaChiusa[];
    /** quando si è chiusa (l'ultima riga regolata) */
    chiusaAt: string;
}

export interface TradeChiudibile {
    id: number;
    event_id?: string | null;
    event_name?: string | null;
    sport?: string | null;
    mode?: string | null;
    status?: string | null;
    pnl?: number | null;
    side?: string | null;
    price?: number | null;
    size?: number | null;
    selection_name?: string | null;
    placed_at?: string | null;
    settled_at?: string | null;
    closes_trade_id?: number | null;
    strategy?: string | null;
    __bot: Bot;
}

/** Sotto questa soglia in valore assoluto una posizione è «pari»: un centesimo
 *  di arrotondamento non è una vittoria né una sconfitta. */
export const SOGLIA_PARI = 0.005;

export function esitoDi(pnl: number): Esito {
    if (pnl > SOGLIA_PARI) return 'vinta';
    if (pnl < -SOGLIA_PARI) return 'persa';
    return 'pari';
}

function testo(v: unknown): string | null {
    return typeof v === 'string' && v.trim() ? v.trim() : null;
}
function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * Costruisce le posizioni chiuse dalle righe grezze dei bot.
 *
 * Una POSIZIONE è un'apertura (`closes_trade_id` vuoto) più le sue coperture.
 * Le coperture non sono posizioni proprie — è lo stesso errore che il 14/09
 * ha fatto contare due volte una chiusura a mano — ma il loro P&L entra
 * INTERAMENTE nel globale, perché sono soldi veri.
 *
 * Entra qui solo ciò che è DEFINITIVO: una posizione ancora aperta o coperta
 * ma non liquidata non è «chiusa», e metterla qui con un P&L parziale
 * direbbe una cosa che non è ancora vera.
 */
export function posizioniChiuse(trades: readonly TradeChiudibile[]): PosizioneChiusa[] {
    const coperture = new Map<number, TradeChiudibile[]>();
    const aperture: TradeChiudibile[] = [];

    for (const t of trades) {
        if (isErrorRow(String(t.status ?? ''))) continue;   // mai andata a mercato
        const chiude = numero(t.closes_trade_id);
        if (chiude != null) {
            const lista = coperture.get(chiude) ?? [];
            lista.push(t);
            coperture.set(chiude, lista);
        } else {
            aperture.push(t);
        }
    }

    const out: PosizioneChiusa[] = [];
    for (const a of aperture) {
        if (!isSettled(String(a.status ?? ''))) continue;   // non ancora conclusa
        const gambe = coperture.get(a.id) ?? [];
        const tutte = [a, ...gambe];

        // il P&L globale somma TUTTE le gambe regolate: su un green-up
        // l'apertura vince e la copertura perde, e solo la somma dice il vero.
        let globale = 0;
        for (const r of tutte) {
            if (!isSettled(String(r.status ?? ''))) continue;
            globale += numero(r.pnl) ?? 0;
        }
        globale = Math.round(globale * 100) / 100;

        const righe: RigaChiusa[] = tutte
            .map((r) => ({
                id: r.id, bot: r.__bot,
                selezione: testo(r.selection_name),
                lato: r.side === 'lay' ? 'lay' as const : r.side === 'back' ? 'back' as const : null,
                prezzo: numero(r.price), size: numero(r.size),
                pnl: numero(r.pnl), stato: String(r.status ?? ''),
                at: testo(r.settled_at) ?? testo(r.placed_at) ?? '',
                chiusura: numero(r.closes_trade_id) != null,
                quale: testo(r.strategy),
            }))
            .sort((x, y) => x.at.localeCompare(y.at));

        const chiusaAt = righe.reduce((m, r) => (r.at > m ? r.at : m), '');

        out.push({
            id: a.id,
            eventId: String(a.event_id ?? ''),
            partita: testo(a.event_name) ?? `evento ${a.event_id ?? '?'}`,
            sport: String(a.sport ?? '').toLowerCase() === 'tennis' ? 'tennis' : 'calcio',
            modo: modoDi(a),
            bot: a.__bot,
            pnlGlobale: globale,
            esito: esitoDi(globale),
            righe,
            chiusaAt,
        });
    }

    // le più recenti in cima: su un banco si guarda l'ultima cosa successa
    return out.sort((x, y) => y.chiusaAt.localeCompare(x.chiusaAt));
}

export interface FiltroChiuse {
    esito?: Esito | 'tutte';
    sport?: 'calcio' | 'tennis' | 'tutti';
    modo?: Modo | 'tutte';
    bot?: Bot | 'tutti';
}

export function filtraChiuse(
    righe: readonly PosizioneChiusa[], f: FiltroChiuse,
): PosizioneChiusa[] {
    return righe.filter((p) => {
        if (f.esito && f.esito !== 'tutte' && p.esito !== f.esito) return false;
        if (f.sport && f.sport !== 'tutti' && p.sport !== f.sport) return false;
        if (f.modo && f.modo !== 'tutte' && p.modo !== f.modo) return false;
        if (f.bot && f.bot !== 'tutti' && p.bot !== f.bot) return false;
        return true;
    });
}

export interface RiepilogoChiuse {
    n: number;
    vinte: number;
    perse: number;
    pari: number;
    /** somma dei P&L globali; `null` se non c'è nessuna posizione */
    totale: number | null;
    /** vinte su vinte+perse; `null` senza esiti */
    percentualeVinte: number | null;
}

/** Il riepilogo di un insieme di posizioni **già filtrate**: quello che si
 *  vede in alto deve descrivere quello che si vede sotto, non tutto il resto. */
export function riepilogoChiuse(righe: readonly PosizioneChiusa[]): RiepilogoChiuse {
    let vinte = 0, perse = 0, pari = 0, totale = 0;
    for (const p of righe) {
        if (p.esito === 'vinta') vinte += 1;
        else if (p.esito === 'persa') perse += 1;
        else pari += 1;
        totale += p.pnlGlobale;
    }
    const conEsito = vinte + perse;
    return {
        n: righe.length, vinte, perse, pari,
        totale: righe.length ? Math.round(totale * 100) / 100 : null,
        percentualeVinte: conEsito > 0 ? vinte / conEsito : null,
    };
}
