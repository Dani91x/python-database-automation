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
import { romeDay } from '@/lib/dailyHistory';
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import { certezzaChiusura, type RisultatoCertezzaChiusura } from '@/lib/certezzaChiusura';

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
    /**
     * C.12b (16/09) — i campi grezzi dell'ORDINE (chiesto/abbinato/residuo/
     * prezzo medio/ultimo aggiornamento da Betfair). Si passano cosi' come
     * arrivano dalla RPC: a leggerli e' `lib/statoOrdine`, uno per tutti i bot.
     */
    ordine: RigaOrdine;
    /** 18/09 — bet_id della gamba: prova che Betfair ha accettato un ordine
     *  reale (`lib/certezzaChiusura.ts`, mai dentro `RigaOrdine`). */
    betId: string | null;
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
    /** quando è stata PIAZZATA l'apertura (ISO); '' se il dato manca */
    piazzataAt: string;
    /**
     * GIORNATA OPERATIVA della posizione: 'YYYY-MM-DD' nel fuso Europe/Rome,
     * dal giorno di **PIAZZAMENTO** dell'apertura — la stessa attribuzione
     * dello storico dei tre bot (`p_day_by = 'placed'`, `attributionOf` in
     * `lib/dailyHistory`). Una posizione aperta alle 23:50 e regolata alle
     * 00:10 appartiene al giorno in cui è stata APERTA, non al successivo.
     *
     * Se il piazzamento manca si ripiega sul regolamento: una posizione senza
     * giornata sparirebbe dal filtro «oggi», e quelli sono soldi veri.
     * '' solo quando non c'è proprio nessuna data.
     */
    giorno: string;
}

/**
 * La giornata operativa (Europe/Rome) di un istante ISO. '' se non c'è o non
 * è leggibile: mai una data inventata.
 */
export function giornataDi(iso: string | null | undefined): string {
    if (!iso) return '';
    const ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return '';
    return romeDay(new Date(ms));
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
    // C.12b — colonne della migrazione `trades_consapevolezza_ordine_2026-09-16`
    // (assenti finche' non e' applicata) e il `meta`, che porta le stesse cose
    // sotto forma di nota. La pagina deve reggere con e senza.
    size_requested?: number | null;
    size_matched?: number | null;
    size_remaining?: number | null;
    avg_price_matched?: number | null;
    betfair_updated_at?: string | null;
    /** 18/09 — presente = un ordine reale è stato accettato da Betfair per
     *  questa gamba: la certezza di chiusura (`lib/certezzaChiusura.ts`) lo
     *  richiede in LIVE prima di dire «confermata». */
    bet_id?: string | null;
    meta?: Record<string, unknown> | null;
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
/**
 * La chiave di una riga: **bot + id**, mai l'id da solo.
 *
 * ⚠️ REVIEW 14/09, CRITICO — gli id vengono da TRE TABELLE DIVERSE
 * (`omega_trades`, `safe_strategy_trades`, `mike_trades`), ognuna con la sua
 * sequenza. Il trade #288 di Safe e il #288 di Omega sono righe diverse: con
 * l'id nudo la copertura di uno si attaccava all'apertura dell'altro, e il
 * P&L della posizione diventava la somma di due operazioni scollegate.
 */
function chiave(bot: Bot, id: unknown): string {
    return `${bot}:${String(id)}`;
}

export function posizioniChiuse(trades: readonly TradeChiudibile[]): PosizioneChiusa[] {
    // indice di TUTTE le righe, per riconoscere le coperture orfane
    const perChiave = new Map<string, TradeChiudibile>();
    for (const t of trades) {
        if (isErrorRow(String(t.status ?? ''))) continue;
        perChiave.set(chiave(t.__bot, t.id), t);
    }

    const coperture = new Map<string, TradeChiudibile[]>();
    const aperture: TradeChiudibile[] = [];

    for (const t of trades) {
        if (isErrorRow(String(t.status ?? ''))) continue;   // mai andata a mercato
        const chiude = numero(t.closes_trade_id);
        if (chiude == null) { aperture.push(t); continue; }

        const padre = chiave(t.__bot, chiude);
        if (!perChiave.has(padre)) {
            // COPERTURA ORFANA — il trade che chiudeva non è fra le righe
            // lette (paginazione, giorno diverso, riga cancellata). I suoi
            // euro sono comunque veri: si tratta come una posizione a sé,
            // marcata, invece di sparire in silenzio. È la stessa difesa di
            // `eventGroups.ts:88-91`.
            aperture.push(t);
            continue;
        }
        const lista = coperture.get(padre) ?? [];
        lista.push(t);
        coperture.set(padre, lista);
    }

    /**
     * Tutte le gambe di una posizione, seguendo la catena fino in fondo.
     *
     * Una copertura può essere a sua volta coperta (A ← B ← C: succede col
     * place-and-trim e con una chiusura parziale richiusa). Fermarsi al primo
     * livello lasciava fuori dal conto il P&L della terza gamba.
     */
    const gambeDi = (radice: TradeChiudibile): TradeChiudibile[] => {
        const fuori: TradeChiudibile[] = [];
        const daVisitare = [radice];
        const visti = new Set<string>([chiave(radice.__bot, radice.id)]);
        while (daVisitare.length) {
            const nodo = daVisitare.shift() as TradeChiudibile;
            for (const g of coperture.get(chiave(nodo.__bot, nodo.id)) ?? []) {
                const k = chiave(g.__bot, g.id);
                if (visti.has(k)) continue;      // difesa contro un ciclo nei dati
                visti.add(k);
                fuori.push(g);
                daVisitare.push(g);
            }
        }
        return fuori;
    };

    const out: PosizioneChiusa[] = [];
    for (const a of aperture) {
        if (!isSettled(String(a.status ?? ''))) continue;   // non ancora conclusa
        const gambe = gambeDi(a);

        // UNA GAMBA ANCORA VIVA = POSIZIONE NON CHIUSA. Sommare solo le righe
        // regolate darebbe un P&L parziale mostrato come definitivo: su un
        // green-up a metà è il numero dell'apertura da solo, cioè il profitto
        // pieno di una posizione che invece è coperta.
        //
        // ECCEZIONE (18/09, certezza di chiusura): una gamba `cancelled` NON
        // ANDRÀ MAI a `won`/`lost`/`void` — un ordine annullato non ha un
        // esito di mercato da attendere, è morto e basta, senza aver mai
        // portato rischio. Prima di questa riga, UNA SOLA gamba di chiusura
        // annullata (es. la terza di tre back a chiudere un lay, rifiutata da
        // Betfair) faceva sparire l'INTERA posizione da «Posizioni chiuse»
        // PER SEMPRE, anche dopo il fischio finale: né aperta né chiusa, in
        // un limbo. Le altre gambe morte senza rischio (`error`, mai andate a
        // mercato) sono già escluse a monte da `isErrorRow` in `aperture`/
        // `coperture`, quindi non arrivano nemmeno qui.
        if (gambe.some((g) => {
            const s = String(g.status ?? '').toLowerCase();
            return !isSettled(s) && s !== 'cancelled';
        })) continue;

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
                betId: testo(r.bet_id),
                ordine: {
                    status: String(r.status ?? ''), side: r.side ?? null,
                    price: numero(r.price), size: numero(r.size),
                    size_requested: numero(r.size_requested),
                    size_matched: numero(r.size_matched),
                    size_remaining: numero(r.size_remaining),
                    avg_price_matched: numero(r.avg_price_matched),
                    betfair_updated_at: testo(r.betfair_updated_at),
                    meta: r.meta ?? null,
                },
            }))
            .sort((x, y) => x.at.localeCompare(y.at));

        const chiusaAt = righe.reduce((m, r) => (r.at > m ? r.at : m), '');
        const piazzataAt = testo(a.placed_at) ?? '';

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
            piazzataAt,
            giorno: giornataDi(piazzataAt) || giornataDi(chiusaAt),
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
    /**
     * GIORNATA OPERATIVA da mostrare, 'YYYY-MM-DD' (Europe/Rome).
     *
     * Ordine dell'utente del 17/09: «in "posizioni chiuse" voglio vedere SOLO
     * le posizioni della giornata, non le precedenti; per i giorni precedenti
     * deve esserci uno STORICO dedicato». Le righe dei bot arrivano dalle RPC
     * di stato con un semplice `limit` (Omega: `get_omega_trades(p_limit)`),
     * quindi contengono ANCHE i giorni passati: senza questo filtro il banco
     * della giornata mostrava operazioni di settimane prima.
     *
     * `undefined` / `null` / '' = nessun filtro di giornata (lo usa lo storico).
     */
    giorno?: string | null;
}

export function filtraChiuse(
    righe: readonly PosizioneChiusa[], f: FiltroChiuse,
): PosizioneChiusa[] {
    const giorno = typeof f.giorno === 'string' && f.giorno.trim() ? f.giorno.trim() : null;
    return righe.filter((p) => {
        if (f.esito && f.esito !== 'tutte' && p.esito !== f.esito) return false;
        if (f.sport && f.sport !== 'tutti' && p.sport !== f.sport) return false;
        if (f.modo && f.modo !== 'tutte' && p.modo !== f.modo) return false;
        if (f.bot && f.bot !== 'tutti' && p.bot !== f.bot) return false;
        // una posizione SENZA giornata leggibile non è «di oggi»: lo dice la
        // scheda con un avviso, invece di finire nel totale del giorno
        if (giorno && p.giorno !== giorno) return false;
        return true;
    });
}

/**
 * Quante posizioni chiuse restano FUORI dalla giornata mostrata (e quante non
 * hanno proprio una data). Serve alla scheda per dire «ce ne sono altre, sono
 * nello Storico» invece di far sparire delle operazioni in silenzio.
 */
export function fuoriGiornata(
    righe: readonly PosizioneChiusa[], giorno: string,
): { altriGiorni: number; senzaData: number } {
    let altriGiorni = 0, senzaData = 0;
    for (const p of righe) {
        if (!p.giorno) { senzaData += 1; continue; }
        if (p.giorno !== giorno) altriGiorni += 1;
    }
    return { altriGiorni, senzaData };
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

// ============================================================================
// 18/09 — CERTEZZA DI CHIUSURA di una posizione della scheda.
//
// Il GIUDIZIO non vive qui: e' `lib/certezzaChiusura.ts`, lo stesso della
// striscia di esito delle schede di uscita. Qui si fa solo il ponte fra una
// `PosizioneChiusa` e la sua forma d'ingresso, senza una seconda regola.
// ============================================================================

/** L'apertura di una posizione: la riga con l'id della posizione. Su una
 *  copertura ORFANA e' la copertura stessa (e' lei a identificare la riga). */
function aperturaDi(p: PosizioneChiusa): RigaChiusa | null {
    return p.righe.find((r) => r.id === p.id) ?? p.righe[0] ?? null;
}

function statoMorto(stato: string): boolean {
    return String(stato).toLowerCase() === 'cancelled';
}

/**
 * Il giudizio «effettivamente chiusa» di UNA posizione.
 *
 * `regolataDalMercato` si RICAVA dagli stati delle righe (apertura regolata e
 * ogni gamba regolata oppure annullata, cioe' morta senza rischio): non e' un
 * `true` cablato. Se un giorno il criterio d'ingresso della scheda cambiasse,
 * una posizione non regolata verrebbe giudicata per quello che e', non
 * dichiarata verde per costruzione.
 */
export function certezzaDiPosizione(p: PosizioneChiusa): RisultatoCertezzaChiusura {
    const a = aperturaDi(p);
    const chiusure = p.righe.filter((r) => r !== a);
    const regolata = a != null && isSettled(a.stato)
        && chiusure.every((r) => isSettled(r.stato) || statoMorto(r.stato));
    return certezzaChiusura({
        apertura: a?.ordine ?? {},
        chiusure: chiusure.map((r) => r.ordine),
        regolataDalMercato: regolata,
        modo: p.modo,
    });
}

/** Quante gambe di chiusura sono state ANNULLATE: la posizione e' regolata lo
 *  stesso, ma la copertura non e' stata quella chiesta e il trader lo deve
 *  vedere senza aprire il dettaglio. */
export function gambeAnnullate(p: PosizioneChiusa): number {
    const a = aperturaDi(p);
    return p.righe.filter((r) => r !== a && statoMorto(r.stato)).length;
}

export interface SintesiPosizione {
    ingresso: { lato: 'back' | 'lay' | null; prezzo: number | null; stake: number | null; at: string };
    /** quota media PESATA sull'abbinato e stake abbinato delle gambe di
     *  chiusura; `null` = nessuna gamba ha abbinato qualcosa (mai zero) */
    chiusura: { prezzoMedio: number | null; stake: number | null; at: string } | null;
}

/**
 * Ingresso e chiusura in una riga: quota, stake ABBINATO, ora.
 *
 * I numeri sono quelli di `statoOrdine` (colonna, poi nota). Solo se mancano
 * si ripiega su `size`/`price` della riga — e solo per righe REGOLATE, dove
 * per costruzione del servizio `size`/`price` portano l'abbinato
 * (`migrations/trades_consapevolezza_ordine_2026-09-16.sql:11-13`).
 */
export function sintesiPosizione(p: PosizioneChiusa): SintesiPosizione {
    const abbinatoDi = (r: RigaChiusa): { stake: number | null; prezzo: number | null } => {
        const s = statoOrdine(r.ordine);
        const regolata = isSettled(r.stato);
        return {
            stake: s.abbinato.valore ?? (regolata ? r.size : null),
            prezzo: s.prezzoMedio.valore ?? (regolata ? r.prezzo : null),
        };
    };
    const a = aperturaDi(p);
    const ing = a ? abbinatoDi(a) : { stake: null, prezzo: null };
    let stake = 0, pesato = 0, ultimo = '';
    for (const r of p.righe) {
        if (r === a || statoMorto(r.stato)) continue;
        const g = abbinatoDi(r);
        if (g.stake == null || g.stake <= 0 || g.prezzo == null) continue;
        stake += g.stake;
        pesato += g.stake * g.prezzo;
        if (r.at > ultimo) ultimo = r.at;
    }
    return {
        ingresso: { lato: a?.lato ?? null, prezzo: ing.prezzo, stake: ing.stake, at: p.piazzataAt },
        chiusura: stake > 0
            ? { prezzoMedio: pesato / stake, stake: Math.round(stake * 100) / 100, at: ultimo }
            : null,
    };
}
