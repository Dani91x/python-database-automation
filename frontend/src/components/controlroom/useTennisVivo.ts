// ============================================================================
// useTennisVivo.ts — IL TENNIS VIVO nella scheda partita della Control Room
// (Task 2, 18/09).
//
// PERCHÉ ESISTE. `useControlRoom.ts` non usa `tennis_live_now` (grep mirato,
// zero occorrenze, A2 §3 di ieri): la scheda di una partita di tennis eredita
// solo il minuto/punteggio CALCIO-CENTRICO del feed scanner condiviso — che
// per il tennis non vuol dire niente (A2 §5.4). La fonte vera esiste già ed è
// GIA' REALTIME: `tennis_live_now` (`lib/tennis.ts`), con `score`
// (set/game/punto/servizio/tie-break/pressione), `state.markets[].status`
// (OPEN/SUSPENDED/CLOSED) e `state.markets[].selections[].name` (per
// correlare il `selection_id` che le righe dei 4 bot tennis portano da sole,
// senza nome — A2 §4.2).
//
// REGOLA DI RISPARMIO DEL DB (13/09, il giorno in cui Supabase è andato giù
// per IO): UNA sottoscrizione per EVENTO, non per riga/posizione. Due bot
// tennis sulla stessa partita (o due posizioni dello stesso bot) condividono
// UN solo canale: un registro a livello di modulo tiene il conteggio dei
// listener e chiude il canale reale solo quando l'ultimo si stacca. Questo è
// lo stesso pattern di `components/mike/useMikeClock.ts` (un timer condiviso
// invece di uno per componente), applicato a un canale Supabase invece che a
// un `setInterval`.
//
// Nessuna lettura nuova: `fetchTennisNow`/`subscribeTennisNow` sono le stesse
// funzioni già usate da `TennisMatchStats.tsx`/`TennisTerminal.tsx`. Qui non
// si duplica la formula, si duplica solo l'hook (perché quello di
// `TennisMatchStats.tsx` non è esportato ed è per-istanza, un canale a
// componente: qui serve la variante CONDIVISA per evento).
//
// 25/09 (voce 5 dell'audit tempo reale) - IL CANALE PRIMA DEL DATABASE. Il
// runner tennis pubblica la STESSA riga di `tennis_live_now` sul suo canale
// locale (47332, topic `now`, `Betfair/stream/tennis_live/tennis_db.py:291`:
// push PRIMA della scrittura cloud), per le partite che SEGUE. La voce
// condivisa ascolta anche quel topic (stesso singleton `getLocalChannel`,
// nessun socket nuovo); il realtime Supabase resta il RIPIEGO. Fra le due
// fonti vince la riga col `updated_at` del produttore strettamente piu'
// recente (a parita' resta quella gia' mostrata: stessa scrittura). La fonte
// della riga mostrata si DICHIARA (`fonte`: canale / database).
// Il topic `scan_tennis` dello scanner (47336) NON si usa qui: porta la riga di
// `safe_strategy_scan` (altra forma), e tradurla sarebbe una seconda formula.
// ============================================================================
import { useEffect, useState } from 'react';
import {
    fetchTennisNow, subscribeTennisNow,
    type TennisLiveNowRow, type TennisNowMarket,
} from '@/lib/tennis';
import { marketStatusMeta, type MarketStatusMeta } from '@/lib/mike';
import { freschezza, type Freschezza } from '@/lib/controlRoom';
import { getLocalChannel } from '@/lib/localChannel';
import { istanteMicro, leggiPushNow } from '@/lib/canaleRunner';

/** da dove viene la riga mostrata: canale del runner tennis o database */
export type FonteTennisVivo = 'canale' | 'database';

// -------------------------------------------------------- registro condiviso
interface Voce {
    row: TennisLiveNowRow | null;
    loaded: boolean;
    /** fonte della riga mostrata; null finche' non c'e' una riga */
    fonte: FonteTennisVivo | null;
    listeners: Set<(row: TennisLiveNowRow | null, loaded: boolean, fonte: FonteTennisVivo | null) => void>;
    unsubscribe: () => void;
}

const registro = new Map<string, Voce>();

function avvisa(v: Voce) {
    for (const l of v.listeners) l(v.row, v.loaded, v.fonte);
}

/**
 * La riga nuova sostituisce quella mostrata? Si' se non ce n'e' una, se una
 * delle due non ha un `updated_at` leggibile (mai bloccarsi su un dato vecchio,
 * come prima), o se e' STRETTAMENTE piu' recente. A parita' no: e' la stessa
 * scrittura arrivata dall'altra strada, e la fonte resta quella che l'ha
 * portata per prima.
 */
function sostituisce(prev: TennisLiveNowRow | null, next: TennisLiveNowRow): boolean {
    if (prev == null) return true;
    const a = istanteMicro(prev.updated_at);
    const b = istanteMicro(next.updated_at);
    if (a == null || b == null) return true;
    return b > a;
}

/** Prende (o crea) la voce condivisa di un evento. Chi arriva DOPO trova già
 *  il canale aperto e l'ultimo snapshot: nessun secondo canale, nessuna
 *  seconda fetch. */
function ottieni(eventId: string): Voce {
    const esistente = registro.get(eventId);
    if (esistente) return esistente;
    const v: Voce = { row: null, loaded: false, fonte: null, listeners: new Set(), unsubscribe: () => {} };
    registro.set(eventId, v);
    const applica = (row: TennisLiveNowRow, fonte: FonteTennisVivo) => {
        if (!sostituisce(v.row, row)) return false;
        v.row = row;
        v.fonte = fonte;
        return true;
    };
    fetchTennisNow(eventId)
        .then((row) => { if (row) applica(row, 'database'); v.loaded = true; avvisa(v); })
        .catch(() => { v.loaded = true; avvisa(v); }); // errore = "non lo sappiamo", non un crash
    const offDb = subscribeTennisNow(eventId, (row) => {
        // il realtime manda `null` su DELETE: si conserva l'ultimo stato buono
        // (stesso comportamento di `TennisMatchStats.tsx`, mai un flicker).
        if (row) applica(row, 'database');
        v.loaded = true;
        avvisa(v);
    });
    // 25/09 (voce 5): la stessa riga dal canale del runner tennis (47332)
    const offCanale = getLocalChannel('tennis').subscribe('now', (d) => {
        const row = leggiPushNow<TennisLiveNowRow>(d);
        if (!row || row.event_id !== eventId) return;
        if (applica(row, 'canale') || !v.loaded) { v.loaded = true; avvisa(v); }
    });
    v.unsubscribe = () => { offDb(); offCanale(); };
    return v;
}

/** Un listener in meno. L'ULTIMO che se ne va chiude davvero il canale. */
function rilascia(eventId: string, cb: (row: TennisLiveNowRow | null, loaded: boolean, fonte: FonteTennisVivo | null) => void) {
    const v = registro.get(eventId);
    if (!v) return;
    v.listeners.delete(cb);
    if (v.listeners.size === 0) {
        v.unsubscribe();
        registro.delete(eventId);
    }
}

/** Quanti canali reali sono aperti ADESSO. Solo per i test (falsificazione di
 *  "un canale solo per evento, non uno a riga"): non è un dato di prodotto. */
export function canaliTennisViviApertiPerTest(): number {
    return registro.size;
}

// ----------------------------------------------------------- vista pura
export interface TennisVivo {
    /** l'ultima riga letta; `null` finché non è arrivato nulla */
    row: TennisLiveNowRow | null;
    /** il primo giro (fetch o realtime) è arrivato? evita di leggere "assente"
     *  come "zero" durante il caricamento */
    loaded: boolean;
    /** età del dato in secondi, ricalcolata ADESSO (non congelata) */
    etaS: number | null;
    /** giudizio sulla età, STESSE soglie 5s/20s di tutta la Control Room
     *  (`lib/controlRoom.ts`), mai una terza soglia per il tennis */
    freschezza: Freschezza;
    /** stato del mercato (OPEN/SUSPENDED/CLOSED/INACTIVE) tradotto con lo
     *  STESSO vocabolario di Mike (`lib/mike.ts::marketStatusMeta`): `null` =
     *  OPEN, cioè "nella norma", niente da segnalare (regola colore/segnale) */
    statoMercato: MarketStatusMeta | null;
    /** 25/09 (voce 5): da dove viene la riga (canale 47332 o realtime del
     *  database); null = nessuna riga */
    fonte: FonteTennisVivo | null;
}

/** Il timestamp più recente della riga: il punteggio (`score.updated_ms`) se
 *  c'è, altrimenti `updated_at` della riga. Stessa logica di
 *  `TennisMatchStats.tsx::rowUpdatedMs` (non esportata lì: ripetuta qui, mai
 *  una seconda formula — sono la stessa unica funzione scritta due volte per
 *  due moduli che non si importano a vicenda). */
function istantePiuRecenteMs(row: TennisLiveNowRow | null): number | null {
    if (!row) return null;
    const scoreMs = row.score?.updated_ms ?? null;
    if (typeof scoreMs === 'number' && scoreMs > 0) return scoreMs;
    if (row.updated_at) {
        const t = Date.parse(row.updated_at);
        return Number.isNaN(t) ? null : t;
    }
    return null;
}

/** Costruisce la vista pura da una riga + l'istante "adesso": funzione pura,
 *  testabile senza montare React né aprire un canale. */
export function vistaTennisVivo(
    row: TennisLiveNowRow | null, loaded: boolean, nowMs: number,
    fonte: FonteTennisVivo | null = null,
): TennisVivo {
    const ms = istantePiuRecenteMs(row);
    const etaS = ms == null ? null : Math.max(0, Math.round((nowMs - ms) / 1000));
    return {
        row, loaded, etaS,
        freschezza: freschezza(etaS),
        statoMercato: marketStatusMeta(row?.status ?? null),
        fonte: row == null ? null : fonte,
    };
}

/**
 * Il nome della selezione per `selectionId`, cercato in TUTTI i mercati
 * dell'evento (Match Odds e gli altri). `null` = il servizio non lo conosce
 * ancora (evento appena agganciato) o `selectionId` non c'è in nessun libro:
 * mai un nome inventato al posto del trattino.
 */
export function nomeSelezioneTennis(
    row: TennisLiveNowRow | null, selectionId: number | null | undefined,
): string | null {
    if (row == null || selectionId == null) return null;
    const mercati: readonly TennisNowMarket[] = row.state?.markets ?? [];
    for (const m of mercati) {
        const sel = m.selections?.find((s) => s.selection_id === selectionId);
        if (sel) return sel.name;
    }
    return null;
}

// ----------------------------------------------------------------- l'hook
/**
 * Il tennis vivo di UN evento, in tempo reale, con UNA sottoscrizione
 * condivisa. `eventId` nullo/vuoto = niente sottoscrizione (partita non
 * tennis, o senza posizione aperta: il chiamante decide QUANDO passare un id,
 * questo hook decide solo COME condividerlo).
 */
export function useTennisVivo(eventId: string | null | undefined): TennisVivo {
    const id = eventId || null;
    const [stato, setStato] = useState<{ row: TennisLiveNowRow | null; loaded: boolean; fonte: FonteTennisVivo | null }>(
        () => (id
            ? { row: registro.get(id)?.row ?? null, loaded: registro.get(id)?.loaded ?? false, fonte: registro.get(id)?.fonte ?? null }
            : { row: null, loaded: false, fonte: null }),
    );
    const [nowMs, setNowMs] = useState(() => Date.now());

    useEffect(() => {
        if (!id) { setStato({ row: null, loaded: false, fonte: null }); return; }
        const v = ottieni(id);
        setStato({ row: v.row, loaded: v.loaded, fonte: v.fonte });
        const cb = (row: TennisLiveNowRow | null, loaded: boolean, fonte: FonteTennisVivo | null) => setStato({ row, loaded, fonte });
        v.listeners.add(cb);
        return () => rilascia(id, cb);
    }, [id]);

    // l'età deve TICKARE anche senza un nuovo messaggio (stesso principio del
    // difetto Mike del 13/09: un'età congelata mente sempre di più col tempo)
    useEffect(() => {
        if (!id) return;
        const t = window.setInterval(() => setNowMs(Date.now()), 1000);
        return () => window.clearInterval(t);
    }, [id]);

    return vistaTennisVivo(stato.row, stato.loaded, nowMs, stato.fonte);
}

export default useTennisVivo;
