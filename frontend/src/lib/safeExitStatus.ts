// ============================================================================
// safeExitStatus.ts — LO STATO DI USCITA di una posizione Safe, in italiano.
//
// Ordine dell'utente, 17/09/2026: «tutto ciò che non è visibile o spiegato
// confonde il trader». Reperto dal vivo (Safe tennis): fra un punto e l'altro
// il book Betfair si svuota per qualche secondo (back o lay della nostra
// selezione assenti, `odds.p2.lay = null`), il bot resta in attesa
// (`exit_wait` con `wait: prezzi_non_nel_feed` / `mercato_sospeso`, attività
// `exit_hold`) e il trader vede una posizione in perdita senza spiegazione.
//
// Qui si legge SOLO `safe_strategy_activity` (kind `exit_wait`, `exit_hold`,
// `feed_blind`), l'ultima riga per quel `trade_id`, e la si traduce in una
// frase breve. Nessuno stato nuovo: i valori di `wait`/`reason` mappati sotto
// sono ESATTAMENTE quelli scritti da `Betfair/safe_strategy/bot_service.py` e
// `exits.py` (grep 17/09, vedi le mappe sotto per i riferimenti). Un valore
// non in mappa mostra il proprio testo grezzo, mai un'invenzione.
//
// PURA: nessun React, nessuna chiamata di rete.
// ============================================================================
import { fmtMoney, fmtPct } from '@/lib/format';

/** provenienza della frase: serve alla UI per colore e per evitare doppioni
 *  con altri indicatori già presenti sulla riga (`meta.exit_hold`, `blindSince`). */
export type SafeExitStatusTone = 'wait' | 'hold' | 'proposal' | 'blind-data' | 'blind-market' | 'unknown';

export interface SafeExitStatusInfo {
    /** frase breve in italiano, con i numeri del payload quando ci sono */
    text: string;
    /** tooltip: il messaggio/motivo originale del servizio */
    tooltip: string;
    tone: SafeExitStatusTone;
}

/** riga minima di `safe_strategy_activity` (vedi `SafeActivityRow` in `safeBot.ts`) */
export interface ExitActivityRow {
    id: number;
    kind: string;
    payload: Record<string, unknown> | null;
}

/**
 * `wait` di `exit_wait` (`bot_service.py`, funzione `_exit_wait` e i suoi
 * chiamanti, righe ~2934-2979 e ~3063): motivi per cui l'uscita automatica
 * NON PUÒ girare in questo momento, senza consumare un tentativo.
 */
const WAIT_IT: Record<string, string> = {
    prezzi_non_nel_feed: "prezzo di chiusura assente nel book (capita per pochi secondi fra un punto e l'altro)",
    mercato_sospeso: 'mercato sospeso',
    feed_non_fresco: 'quote del feed non aggiornate di recente',
    assestamento_post_evento: "assestamento dopo l'ultimo punto, prima di decidere la chiusura",
    combo_prezzi_incompleti: 'prezzi non ancora completi per chiudere tutte le gambe della combinazione',
    niente_da_chiudere: 'nessuna quota disponibile per chiudere in questo momento',
    combo_solidale: "una gamba della combinazione è già in chiusura",
};

/**
 * `reason` di `feed_blind` quando il payload lo porta (`_dato_che_manca`,
 * `bot_service.py` righe ~3608-3665): manca un dato indispensabile alle
 * regole di uscita, non il mercato intero (quello è l'altra variante, senza
 * `reason`, con `blind_since`/`blind_for_s` — già mostrata da `blindSince`
 * in `lib/safeBot.ts` come «SENZA FEED da HH:MM:SS»).
 */
const BLIND_REASON_IT: Record<string, string> = {
    riga_senza_payload: 'nessun dato dal feed per questa partita',
    punteggio_assente: 'punteggio assente nel feed',
    minuto_assente: 'minuto di gioco assente nel feed',
    punteggio_tennis_assente: 'punteggio di set/game assente nel feed',
};

function testo(v: unknown): string | null {
    return v != null && String(v).trim() !== '' ? String(v) : null;
}
function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function waitLabel(wait: string | null): string {
    if (!wait) return 'motivo non dichiarato';
    return WAIT_IT[wait] ?? wait;
}
function blindLabel(reason: string | null): string {
    if (!reason) return 'dati della partita assenti dal feed';
    return BLIND_REASON_IT[reason] ?? reason;
}

/**
 * Traduce UNA riga di attività (`exit_wait` | `exit_hold` | `feed_blind`) in
 * una frase per il trader. `null` se il kind non è fra questi tre (chi chiama
 * filtra già con `latestExitActivityFor`, ma la funzione resta difensiva).
 */
export function safeActivityExitStatus(
    row: ExitActivityRow | null | undefined,
): SafeExitStatusInfo | null {
    if (!row) return null;
    const p = row.payload ?? {};

    if (row.kind === 'exit_wait') {
        const wait = testo(p['wait']);
        const reason = testo(p['reason']);
        if (wait === 'combo_solidale' || reason === 'combo_solidale') {
            return {
                text: `In attesa: ${WAIT_IT.combo_solidale}`,
                tooltip: wait ?? reason ?? 'combo_solidale',
                tone: 'wait',
            };
        }
        return { text: `In attesa: ${waitLabel(wait)}`, tooltip: wait ?? 'motivo non dichiarato', tone: 'wait' };
    }

    if (row.kind === 'exit_hold') {
        const reason = testo(p['reason']);
        if (reason === 'in_attesa_di_approvazione') {
            return {
                text: 'Proposta in attesa della tua firma',
                tooltip: "l'uscita è pronta ma resta ferma finché non la confermi (cancelletto di approvazione sulle chiusure)",
                tone: 'proposal',
            };
        }
        // `msg` è la frase italiana completa scritta dal servizio
        // (`exits.decide_time_exit` / `_write_model_hold`): e' il messaggio
        // ORIGINALE, non un codice — si mostra cosi' com'e', mai riscritto.
        const msg = testo(p['msg']) ?? reason ?? 'il servizio tiene la posizione';
        const pLose = numero(p['p_lose']);
        const locked = numero(p['locked']);
        const evHold = numero(p['ev_hold']);
        const dettagli = [
            pLose != null ? `P(perdita) ${fmtPct(pLose)}` : null,
            locked != null ? `bloccabile ora ${fmtMoney(locked, { signed: true })}` : null,
            evHold != null ? `EV tenere ${fmtMoney(evHold, { signed: true })}` : null,
        ].filter(Boolean).join(' · ');
        return { text: `Tenuta: ${msg}`, tooltip: dettagli || msg, tone: 'hold' };
    }

    if (row.kind === 'feed_blind') {
        const reason = testo(p['reason']);
        if (reason) {
            return {
                text: `In attesa: ${blindLabel(reason)}`,
                tooltip: testo(p['effetto']) ?? reason,
                tone: 'blind-data',
            };
        }
        const forS = numero(p['blind_for_s']);
        return {
            text: forS != null ? `Feed cieco da ${Math.round(forS)} s` : 'Feed cieco: mercato assente dal feed',
            tooltip: "nessuna regola di uscita automatica può girare su questa posizione finché il mercato non torna nel feed",
            tone: 'blind-market',
        };
    }

    // kind sconosciuto: non dovrebbe arrivare qui (si filtra a monte), ma
    // niente e' meglio di un errore silenzioso — si mostra il testo grezzo.
    return {
        text: testo(p['msg']) ?? testo(p['reason']) ?? String(row.kind),
        tooltip: JSON.stringify(p),
        tone: 'unknown',
    };
}

const EXIT_STATUS_KINDS = new Set(['exit_wait', 'exit_hold', 'feed_blind']);

/**
 * Ultima riga di attività di uscita per UN trade (id più alto = più recente,
 * stesso pattern di `lastRequestFor` in `safeBot.ts`). `null` = nessuna
 * attività di uscita registrata per questo trade.
 */
export function latestExitActivityFor(
    tradeId: number,
    activity: readonly ExitActivityRow[],
): ExitActivityRow | null {
    let best: ExitActivityRow | null = null;
    for (const row of activity) {
        if (!EXIT_STATUS_KINDS.has(row.kind)) continue;
        if (Number((row.payload ?? {})['trade_id']) !== tradeId) continue;
        if (!best || row.id > best.id) best = row;
    }
    return best;
}
