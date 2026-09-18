// ============================================================================
// dettaglioRiga.ts — IL DETTAGLIO CHE LA SCHEDA ORIGINALE MOSTRA GIÀ,
// portato sulle righe della Control Room (17/09).
//
// PERCHÉ ESISTE QUESTO FILE
// La Control Room mostrava di ogni posizione quattro numeri (lato, selezione,
// quota, importo). La scheda originale di Omega — e quella di Safe — ne mostra
// dieci: quota d'ingresso E quota di adesso, minuto e punteggio all'ingresso,
// stato ricco («IN VERIFICA SU BETFAIR», «COPERTA 40%»), P&L VIVO (non solo a
// regolamento), green-up, P del modello contro quella del mercato. Erano tutti
// dati GIÀ IN MEMORIA nelle stesse righe RPC che la Control Room carica: una
// proiezione ridotta li buttava via.
//
// REGOLE, non negoziabili:
//  · **Nessuna formula nuova.** Ogni numero qui esce da una funzione che le
//    pagine originali usano già (`statusMetaOf`, `legPnl`, `hedgeInfo`,
//    `greenupBadge`, `tradeModelOf`, `ticksBetween`). Due formule per la stessa
//    cosa sono due verità, e sotto gli occhi di un trader divergono sempre.
//  · **Nessuna lettura nuova.** Questo modulo è PURO: riceve la riga e — quando
//    serve — il prezzo già estratto dal feed di scansione che la pagina carica
//    comunque. Non tocca il database (regola del respiro del DB, 13/09).
//  · **Un valore che non c'è è `null`, mai zero.** «Non ancora regolato» e
//    «pari» sono due cose diverse.
// ============================================================================
import { legPnl, type LegPnl, type MatchTradeLike } from '@/lib/omegaMatches';
import { greenupBadge, hedgeInfo, tradeModelOf, type GreenupBadge } from '@/lib/omega';
import { statusMetaOf, type Meta } from '@/lib/tradeStatus';
import { ticksBetween } from '@/lib/riskMath';
import { isSettled } from '@/lib/eventGroups';

/** La riga minima da cui si ricava il dettaglio: è il sottoinsieme che
 *  `omega_trades`, `safe_strategy_trades` e `mike_trades` hanno TUTTE. */
export type RigaDettagliabile = MatchTradeLike;

/** Quota d'ingresso contro quota di ADESSO, sulla stessa selezione. */
export interface QuotaViva {
    /** miglior BACK disponibile ora sulla selezione; null = non lo sappiamo */
    back: number | null;
    /** miglior LAY disponibile ora sulla selezione; null = non lo sappiamo */
    lay: number | null;
    /** quota di adesso sullo STESSO lato dell'ingresso (il confronto onesto) */
    ora: number | null;
    /** tick di movimento dall'ingresso, con segno: + = a FAVORE della posizione */
    tick: number | null;
}

export interface ModelloRiga {
    /** P(perdita) secondo il modello del bot (`meta.model`) */
    pModello: number | null;
    /** P(perdita) implicita nel mercato = 1 / quota LAY viva */
    pMercato: number | null;
    /** margine = mercato − modello: positivo = il mercato paga più del rischio */
    margine: number | null;
}

/**
 * UNA RIGA DI CHIUSURA, ANNIDATA sotto la posizione che chiude (Task 4, A2 §4.4).
 * Sono le stesse righe con `closes_trade_id` già caricate da
 * `chiusureCollegate()`/`fetchOmegaTrades`/`fetchSafeState().trades`/
 * `fetchMikeState().trades`: qui non si legge niente di nuovo, si SMONTANO —
 * prima finivano riassunte in un solo numero ("coperta X% · a rischio Y"),
 * senza dire con quale ordine (lato/prezzo/size/quando) la copertura è
 * avvenuta davvero.
 */
export interface ChiusuraRiga {
    lato: 'back' | 'lay' | null;
    prezzo: number | null;
    size: number | null;
    /** netto di commissione; `null` = questa gamba di chiusura non è ancora regolata */
    pnl: number | null;
    /** badge ricco della GAMBA DI CHIUSURA, stessa `statusMetaOf` della riga principale */
    stato: Meta;
    /** tipo di uscita dichiarato dal servizio su QUESTA gamba (`meta.exit_kind`) */
    uscita: string | null;
    at: string;
}

export interface DettaglioRiga {
    /** badge ricco: lo stesso di Omega/Safe (IN VERIFICA SU BETFAIR, ecc.) */
    stato: Meta;
    /** minuto e punteggio AL MOMENTO DELL'INGRESSO (colonne della riga) */
    ingresso: { minuto: number | null; punteggio: string | null };
    /** P&L VIVO: regolato / bloccato / copertura parziale / aperto */
    pnlVivo: { stato: LegPnl['state']; valore: number | null };
    /** copertura: frazione già coperta e liability ancora a rischio */
    copertura: { frazione: number | null; residua: number | null; completa: boolean } | null;
    /** badge green-up del servizio (`meta.greenup`) */
    greenup: GreenupBadge | null;
    /** tipo di uscita dichiarato dal servizio (`meta.exit_kind`) */
    uscita: string | null;
    /** P del modello contro quella del mercato (Omega); null se il bot non la scrive */
    modello: ModelloRiga | null;
    /** la gamba/strategia che ha operato (Omega: 1T/2T; Safe: strategia) */
    gamba: string | null;
    /** le gambe di chiusura collegate (`closes_trade_id`), dalla più vecchia.
     *  Vuoto = nessuna chiusura ancora, non «non lo sappiamo». */
    chiusure: ChiusuraRiga[];
}

function num(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
    return typeof v === 'string' && v.trim() !== '' ? v.trim() : null;
}

/**
 * Quota viva + Δ tick. I due prezzi arrivano GIÀ estratti dal feed con
 * `prezzoVivo()` (la stessa funzione che alimenta le proposte): qui si fa solo
 * il confronto con l'ingresso, con la scala dei tick di Betfair.
 *
 * Segno: su un LAY entrato a P si guadagna quando la quota SCENDE (si ricompra
 * il back più basso), su un BACK quando sale. È la stessa convenzione di
 * `SafeTradesTable` (`× −1` sul lay) e di `offsetTargetPrice` in riskMath.
 */
/**
 * UNA GAMBA DI CHIUSURA NON E' UNA POSIZIONE APERTA (approvato dall'utente,
 * 17/09 sera). Il back che chiude un lay (Safe «esatto», Union Brescia-Treviso:
 * 4,78 @9,6 + 7,20 @9,6 + 2,08 @12 su un lay 2 @70) porta `closes_trade_id`
 * e resta `open` finche' il mercato non regola: mostrarlo fra le posizioni con
 * «chiudi ora» e un P&L stimato vorrebbe dire proporre di chiudere una
 * chiusura. Vive gia' nella scheda della partita, sotto la sua apertura.
 */
export function eGambaDiChiusura(t: { closes_trade_id?: number | null }): boolean {
    return t.closes_trade_id != null;
}

export function quotaViva(
    entryPrice: number | null | undefined,
    lato: 'back' | 'lay' | null | undefined,
    book: { back: number | null; lay: number | null },
): QuotaViva | null {
    const back = num(book.back);
    const lay = num(book.lay);
    if (back == null && lay == null) return null;
    const ora = lato === 'lay' ? lay : lato === 'back' ? back : null;
    const entry = num(entryPrice);
    const tick = entry != null && entry > 1 && ora != null && ora > 1
        ? ticksBetween(entry, ora) * (lato === 'lay' ? -1 : 1)
        : null;
    return { back, lay, ora, tick };
}

/**
 * IL DETTAGLIO DI UNA RIGA. `closes` sono le righe di chiusura collegate
 * (`closes_trade_id`), che `legPnl` usa per dire se il P&L è bloccato: senza di
 * esse una posizione coperta resterebbe «aperta» per sempre.
 */
export function dettaglioDi<T extends RigaDettagliabile>(
    t: T,
    closes: T[] = [],
    opts: { pMercato?: number | null; gamba?: string | null } = {},
): DettaglioRiga {
    const meta = (t.meta ?? null) as Record<string, unknown> | null;
    const h = hedgeInfo(meta);
    const model = tradeModelOf({ meta });
    // stessa scelta di MatchTradesTable: si mostra la P CALIBRATA quando il
    // calibratore è stato applicato, altrimenti quella grezza.
    const pModello = model
        ? (model.applied ? model.calibrated : (model.calibrated ?? model.raw))
        : null;
    const pMercato = num(opts.pMercato);
    const modello = pModello == null && pMercato == null
        ? null
        : {
            pModello,
            pMercato,
            margine: pModello != null && pMercato != null
                ? Math.round((pMercato - pModello) * 10000) / 10000
                : null,
        };
    const pnl = legPnl(t, closes);
    return {
        stato: statusMetaOf({ status: t.status, meta }),
        ingresso: {
            minuto: num(t.minute_at_entry),
            punteggio: str(t.score_at_entry),
        },
        pnlVivo: { stato: pnl.state, valore: pnl.value },
        copertura: h == null ? null : {
            frazione: h.fraction,
            residua: h.remainingLiability,
            completa: h.complete,
        },
        greenup: greenupBadge(meta),
        uscita: str((meta ?? {})['exit_kind']),
        modello,
        gamba: str(opts.gamba) ?? str(t.phase),
        chiusure: chiusureDi(closes),
    };
}

function latoDiChiusura(v: unknown): 'back' | 'lay' | null {
    const s = String(v ?? '').toLowerCase();
    return s === 'back' || s === 'lay' ? s : null;
}

/**
 * Le gambe di chiusura SMONTATE, dalla più vecchia: lato/prezzo/size/quando,
 * col loro stesso badge ricco e il proprio `pnl` (null finché non regolate).
 * Nessuna formula nuova: `statusMetaOf` è la stessa della riga principale.
 */
function chiusureDi<T extends RigaDettagliabile>(closes: readonly T[]): ChiusuraRiga[] {
    return closes
        .slice()
        .sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at))
        .map((c) => {
            const cMeta = (c.meta ?? null) as Record<string, unknown> | null;
            return {
                lato: latoDiChiusura(c.side),
                prezzo: num(c.price),
                size: num(c.size),
                pnl: isSettled(c.status) ? num(c.pnl) : null,
                stato: statusMetaOf({ status: c.status, meta: cMeta }),
                uscita: str((cMeta ?? {})['exit_kind']),
                at: c.placed_at,
            };
        });
}
