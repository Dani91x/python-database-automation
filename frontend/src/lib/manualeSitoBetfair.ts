// ============================================================================
// manualeSitoBetfair.ts — LE SCOMMESSE PIAZZATE FUORI DAI BOT: sul SITO
// Betfair (fuori app) e sul terminale MANUALE della nostra app (ladder
// calcio+tennis).
//
// 18/09 (raccordo) — il contratto backend e' pronto (`CHECKPOINT_B1_SALDO_E_
// MANUALI_2026-09-18.md`, TERZO GIRO): il runner scrive `manual_pnl_*` (sito)
// e `manual_app_pnl_*` (app) come colonne ADDITIVE sulla STESSA riga singola
// `betfair_live_account` (id=1) gia' sottoscritta da `SaldoBetfairCard`/
// `useControlRoom.ts` — NESSUNA lettura nuova, si leggono le chiavi in piu'
// che quella riga porta gia'.
//
// La migrazione (`migrations/betfair_live_account_manual_pnl.sql`) potrebbe
// NON essere ancora applicata: allora quelle chiavi sono assenti dalla riga
// (`undefined`), non `null` — e questa funzione dichiara "non disponibile",
// MAI un valore inventato o un ereditato zero.
//
// Il giorno conta: `manual_pnl_day`/`manual_app_pnl_day` sono il giorno Rome
// a cui il totale si riferisce. Se non coincide con OGGI (calcolato dal
// chiamante, mai qui: questo file resta puro) il numero e' vecchio e non
// entra — mostrare il P&L di ieri come se fosse quello di oggi sarebbe un
// numero sbagliato travestito da uno buono.
// ============================================================================

export type FonteManualeSito = 'non-disponibile' | 'backend';

export interface BucketManuale {
    /** P&L netto (o lordo, v. `netto`) di oggi; null = non disponibile: NON
     *  entra in nessuna somma. */
    pnlOggi: number | null;
    fonte: FonteManualeSito;
    /** true = netto di commissione, false = LORDO (dichiarato), null/undefined = ignoto */
    netto?: boolean | null;
    /** quanti ordini sono entrati nel totale (diagnostico) */
    ordini?: number | null;
}

export interface ManualeSitoBetfair {
    // ── nomi storici del campo (SITO Betfair): invariati per compatibilità
    //    con chi già li legge (`ObiettivoHero.tsx`, i test esistenti) ──
    pnlOggi: number | null;
    fonte: FonteManualeSito;
    netto?: boolean | null;
    ordini?: number | null;
    /**
     * 18/09 — APP nostra (ladder manuale calcio+tennis): bucket SEPARATO dal
     * sito. `undefined` non compare mai da questa funzione (sempre un
     * oggetto, eventualmente "non-disponibile"): opzionale nel TIPO solo per
     * restare compatibile con i fixture di test scritti prima di questo
     * campo (`{ pnlOggi, fonte }` senza `app`).
     */
    app?: BucketManuale;
    /** ordini esclusi/ambigui (ref irriconoscibile): diagnostico, condiviso
     *  fra i due bucket. null = non noto (migrazione non applicata). */
    esclusi?: number | null;
}

/** Il sottoinsieme di `LiveAccountRow` (`lib/liveOrders.ts`) che serve qui:
 *  stesse chiavi del vero, tutte opzionali (assenti = migrazione non applicata). */
export interface RigaContoManuale {
    manual_pnl_eur?: number | null;
    manual_pnl_is_net?: boolean | null;
    manual_pnl_orders?: number | null;
    manual_pnl_excluded?: number | null;
    manual_pnl_day?: string | null;
    manual_app_pnl_eur?: number | null;
    manual_app_pnl_is_net?: boolean | null;
    manual_app_pnl_orders?: number | null;
    manual_app_pnl_day?: string | null;
}

function bucket(eur: unknown, isNet: unknown, ordini: unknown, day: unknown, oggi: string): BucketManuale {
    if (typeof eur !== 'number' || !Number.isFinite(eur)) {
        return { pnlOggi: null, fonte: 'non-disponibile' };
    }
    if (typeof day !== 'string' || day !== oggi) {
        // il backend ha scritto un giorno diverso da oggi (o non l'ha scritto
        // affatto): il numero non e' quello di OGGI, quindi non e' quello che
        // questa pagina promette di mostrare.
        return { pnlOggi: null, fonte: 'non-disponibile' };
    }
    return {
        pnlOggi: Math.round(eur * 100) / 100,
        fonte: 'backend',
        netto: isNet === true,
        ordini: typeof ordini === 'number' && Number.isFinite(ordini) ? ordini : null,
    };
}

/**
 * Legge le due voci manuali dalla riga singleton `betfair_live_account` GIA'
 * in memoria (nessuna lettura nuova) e dal giorno operativo di OGGI (calcolato
 * dal chiamante con `romeDay`, mai qui). `riga` assente/null = migrazione non
 * applicata o riga non ancora letta: entrambi i bucket "non-disponibile".
 */
export function leggiManualeSitoBetfair(
    riga: RigaContoManuale | null | undefined,
    oggi: string,
): ManualeSitoBetfair {
    const sito = bucket(riga?.manual_pnl_eur, riga?.manual_pnl_is_net, riga?.manual_pnl_orders, riga?.manual_pnl_day, oggi);
    const app = bucket(riga?.manual_app_pnl_eur, riga?.manual_app_pnl_is_net, riga?.manual_app_pnl_orders, riga?.manual_app_pnl_day, oggi);
    const esclusi = typeof riga?.manual_pnl_excluded === 'number' && Number.isFinite(riga.manual_pnl_excluded)
        ? riga.manual_pnl_excluded : null;
    return {
        pnlOggi: sito.pnlOggi, fonte: sito.fonte, netto: sito.netto, ordini: sito.ordini,
        app,
        esclusi,
    };
}
