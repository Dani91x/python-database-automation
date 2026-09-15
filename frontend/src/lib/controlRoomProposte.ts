// ============================================================================
// controlRoomProposte.ts — LE PROPOSTE DI CHIUSURA che aspettano il sì.
//
// Il bot tennis apre da solo; quando matura un'uscita NON la esegue: scrive una
// riga `proposed` nella coda `safe_strategy_requests` e aspetta. Questo file è
// il ponte fra quella riga e la scheda che il trader legge.
//
// LA REGOLA CHE GOVERNA TUTTO IL FILE:
//   **La proposta conserva la FOTOGRAFIA, la scheda mostra il PREZZO VIVO.**
//   `price_at_decision` dice su cosa il bot ha deciso; il prezzo su cui si
//   piazza arriva dal FEED, che alla pagina viaggia in push. Così il numero si
//   muove da solo senza che il bot riscriva la riga — meno scritture sul
//   database (lezione del 13/09) e nessuna fotografia spacciata per presente.
//
// E la conseguenza pratica: **non si approva mai su una fotografia.** Se il
// prezzo si è mosso oltre la tolleranza, l'approvazione si spegne e dice perché.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import {
    scanBlockByMarketId, blockSelection,
    type CalcioScanPayload, type TennisScanPayload, type ScanOddsPair,
} from '@/lib/safeStrategyScan';

/** Il payload che il servizio scrive in una riga `proposed` (contratto
 *  concordato con il bot: i campi arrivano da `bot_service`). */
export interface PropostaPayload {
    trade_id: number;
    event_id: string;
    event_name?: string | null;
    sport?: string | null;
    strategy?: string | null;
    selection_name?: string | null;
    /** chiave con cui si pesca il prezzo VIVO dal feed */
    market_id?: string | null;
    selection_id?: number | null;
    /** lato dell'ORDINE DI CHIUSURA (non quello di ingresso) */
    side?: 'back' | 'lay' | null;
    entry_side?: 'back' | 'lay' | null;
    entry_price?: number | null;
    size?: number | null;
    /** FOTOGRAFIA al momento della decisione: NON è il prezzo su cui si piazza */
    price_at_decision?: number | null;
    size_available_at_decision?: number | null;
    /** quanto vale chiudere adesso (P&L bloccato) e quanto vale tenere */
    locked_at_decision?: number | null;
    hold_profit?: number | null;
    loss_if_lose?: number | null;
    /** in codice: la traduzione italiana vive in UN solo posto (`safeActivity`) */
    exit_kind?: string | null;
    exit_reason?: string | null;
    /** uscite in perdita, obbligatorie, da rosso: NON approvarle COSTA */
    urgente?: boolean | null;
    minute?: number | null;
    score?: string | null;
    mode?: 'paper' | 'live' | null;
    feed_updated_at?: string | null;
    odds_ts_ms?: number | null;
    decided_at?: string | null;
    proposed_at?: string | null;
}

export interface PropostaChiusura {
    id: number;
    kind: string;
    status: string;
    payload: PropostaPayload;
    created_at: string;
    updated_at?: string | null;
}

// -------------------------------------------------------------- prezzo vivo

export interface PrezzoVivo {
    /** prezzo corrente sul LATO con cui si chiude */
    prezzo: number | null;
    /** EUR abbinabili SUBITO a quel prezzo */
    abbinabile: number | null;
}

const VUOTO: PrezzoVivo = { prezzo: null, abbinabile: null };

/** Estrae prezzo e importo abbinabile dal lato giusto di una coppia del feed.
 *  Chiudere con un LAY vuol dire **prendere il lay**: si guarda `lay`/`lay_size`. */
function daCoppia(o: ScanOddsPair | null | undefined, lato: 'back' | 'lay'): PrezzoVivo {
    if (!o) return VUOTO;
    const prezzo = lato === 'lay' ? o.lay : o.back;
    const size = lato === 'lay' ? o.lay_size : o.back_size;
    return {
        prezzo: typeof prezzo === 'number' && Number.isFinite(prezzo) && prezzo > 1 ? prezzo : null,
        abbinabile: typeof size === 'number' && Number.isFinite(size) ? size : null,
    };
}

/**
 * IL PREZZO SU CUI SI PIAZZA DAVVERO, preso dal FEED e non dalla proposta.
 *
 * È questa funzione che rende «viva» la scheda: il feed arriva alla pagina in
 * push, quindi il numero si muove da solo senza che il bot riscriva la riga.
 *
 * Cerca prima nel mercato indicato dalla proposta; per il **tennis** ripiega
 * sul Match Odds del payload (`odds.p1` / `odds.p2`), che è dove lo scanner
 * pubblica le quote di quello sport. Non trovato → `null`, **mai un ripiego
 * inventato**: senza prezzo corrente la proposta non è approvabile.
 */
export function prezzoVivo(
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
    marketId: string | null | undefined,
    selectionId: number | null | undefined,
    lato: 'back' | 'lay' | null | undefined,
): PrezzoVivo {
    if (!payload || !lato) return VUOTO;

    const blocco = scanBlockByMarketId(payload, marketId);
    const sel = blockSelection(blocco, { selectionId });
    if (sel) return daCoppia(sel, lato);

    // tennis (e Match Odds del calcio): le quote stanno in `odds`, non nei blocchi
    const odds = (payload as TennisScanPayload).odds as
        | { p1?: ScanOddsPair | null; p2?: ScanOddsPair | null; home?: ScanOddsPair | null; draw?: ScanOddsPair | null; away?: ScanOddsPair | null }
        | null | undefined;
    if (!odds || selectionId == null) return VUOTO;
    for (const o of [odds.p1, odds.p2, odds.home, odds.draw, odds.away]) {
        if (o && Number(o.selection_id) === Number(selectionId)) return daCoppia(o, lato);
    }
    return VUOTO;
}

// ----------------------------------------------------------------- tolleranza

/** Scostamento massimo del prezzo dalla fotografia oltre il quale non si
 *  approva. In percentuale: i tick cambiano dimensione lungo la scala delle
 *  quote, una percentuale no. Modificabile dalla pagina. */
export const SLIPPAGE_PCT_DEFAULT = 2;

export interface Scostamento {
    /** differenza assoluta fra prezzo corrente e prezzo alla decisione */
    delta: number | null;
    /** la stessa, in percentuale sulla fotografia */
    pct: number | null;
    /** il movimento ci danneggia? (chiudere con un LAY: prezzo che sale costa) */
    controDiNoi: boolean;
    /** oltre la tolleranza: l'approvazione si spegne */
    fuoriTolleranza: boolean;
}

/**
 * Confronto fra la fotografia e il presente.
 *
 * Il verso conta: la chiusura di una PUNTATA è una BANCATA, e su una bancata
 * **il prezzo che sale costa di più**. Sulla chiusura di una bancata (una
 * puntata) è il contrario. Sbagliare il verso vorrebbe dire colorare di verde
 * un movimento che ci sta togliendo soldi.
 *
 * Prezzi mancanti → nessun giudizio, ma **fuori tolleranza**: non si approva
 * un ordine di cui non conosciamo il prezzo corrente.
 */
export function scostamento(args: {
    prezzoDecisione: number | null | undefined;
    prezzoCorrente: number | null | undefined;
    /** lato dell'ordine di CHIUSURA */
    lato: 'back' | 'lay' | null | undefined;
    slippagePct?: number;
}): Scostamento {
    const { prezzoDecisione: p0, prezzoCorrente: p1, lato } = args;
    const soglia = args.slippagePct ?? SLIPPAGE_PCT_DEFAULT;

    const validi = typeof p0 === 'number' && Number.isFinite(p0) && p0 > 0
        && typeof p1 === 'number' && Number.isFinite(p1) && p1 > 0;
    if (!validi) {
        // fail-closed: senza il prezzo corrente non si piazza
        return { delta: null, pct: null, controDiNoi: false, fuoriTolleranza: true };
    }

    const delta = (p1 as number) - (p0 as number);
    const pct = (delta / (p0 as number)) * 100;
    // su un LAY (chiusura di una puntata) il prezzo che SALE costa
    const controDiNoi = lato === 'lay' ? delta > 0 : delta < 0;
    return { delta, pct, controDiNoi, fuoriTolleranza: Math.abs(pct) > soglia };
}

/**
 * L'importo che serve davvero a chiudere, e quanto se ne può abbinare ORA.
 * In live un ordine che non trova controparte parte tutto-o-niente e viene
 * **annullato per intero**: approvare una chiusura più grande di quanto il
 * mercato abbina lascerebbe la posizione aperta facendo credere il contrario.
 */
export function abbinabileSufficiente(
    daChiudere: number | null | undefined,
    abbinabileOra: number | null | undefined,
): boolean {
    if (typeof daChiudere !== 'number' || !Number.isFinite(daChiudere) || daChiudere <= 0) return false;
    if (typeof abbinabileOra !== 'number' || !Number.isFinite(abbinabileOra)) return false;
    // un centesimo di tolleranza sugli arrotondamenti del book
    return abbinabileOra + 0.005 >= daChiudere;
}

/** Perché questa proposta NON è approvabile adesso; `null` = si può approvare.
 *  L'ordine dei controlli è l'ordine in cui contano. */
/**
 * LO STAKE DELL'ORDINE DI CHIUSURA, che NON è la size di ingresso.
 *
 * ⚠️ REVIEW 15/09, CRITICO — il controllo di liquidità usava `payload.size`,
 * cioè quanto si era PUNTATO all'apertura. Ma per chiudere per intero si
 * piazza un importo diverso, e su una copertura a quota più bassa è più
 * GRANDE: il controllo passava su una liquidità che non basta, e in live un
 * ordine non abbinabile per intero viene annullato tutto.
 *
 * Formula del pieno green-up, identica nei due versi:
 *
 *     stake_chiusura = size_ingresso × prezzo_ingresso / prezzo_chiusura
 *
 * La commissione non entra: incide sul P&L, non sullo stake. Verificata sui
 * trade veri del 14/09 — #287: 3,00 × 1,11 / 1,10 = 3,03, e la gamba #288
 * piazzata da Betfair era esattamente 3,03; #290: 3,00 × 1,04 / 1,03 = 3,03,
 * come la gamba #292.
 *
 * `null` quando manca un ingrediente: meglio nessun numero che uno inventato.
 */
export function stakeDiChiusura(
    sizeIngresso: number | null | undefined,
    prezzoIngresso: number | null | undefined,
    prezzoChiusura: number | null | undefined,
): number | null {
    const s = typeof sizeIngresso === 'number' && Number.isFinite(sizeIngresso) && sizeIngresso > 0
        ? sizeIngresso : null;
    const pe = typeof prezzoIngresso === 'number' && Number.isFinite(prezzoIngresso) && prezzoIngresso > 1
        ? prezzoIngresso : null;
    const pc = typeof prezzoChiusura === 'number' && Number.isFinite(prezzoChiusura) && prezzoChiusura > 1
        ? prezzoChiusura : null;
    if (s == null || pe == null || pc == null) return null;
    return Math.round((s * pe / pc) * 100) / 100;
}

export function motivoNonApprovabile(args: {
    scost: Scostamento;
    etaQuoteS: number | null;
    etaMassimaS: number;
    daChiudere: number | null | undefined;
    abbinabileOra: number | null | undefined;
    /**
     * Da quanto lo SCANNER non scrive nulla (secondi). `null` = non lo
     * sappiamo, e allora si resta prudenti come prima.
     *
     * ⚠️ REVIEW 15/09, CRITICO — senza questo, il cancello chiamava «quote
     * vecchie» un prezzo semplicemente FERMO. `odds_ts_ms` è l'istante
     * dell'ultimo CAMBIO di prezzo, non «da quando non guardiamo»: su un
     * mercato poco scambiato un prezzo immobile da 40 s è corrente e
     * correttissimo. Il risultato era APPROVA spento su un'uscita URGENTE in
     * live — cioè il caso in cui non approvare costa davvero.
     *
     * La distinzione è la stessa già usata dalle schede partita
     * (`statoQuote` in `lib/controlRoom.ts`): «fermo» e «vecchio» sono due
     * cose diverse, e si distinguono solo incrociando con la vitalità dello
     * scanner. Qui la si porta dove decide un ordine vero.
     */
    etaScannerS?: number | null;
}): string | null {
    const { scost, etaQuoteS, etaMassimaS, daChiudere, abbinabileOra, etaScannerS } = args;

    if (scost.delta == null) return 'prezzo corrente non disponibile: non si piazza al buio';
    if (etaQuoteS == null) return 'età delle quote sconosciuta: non si piazza su un prezzo di cui non sappiamo l’età';

    // lo scanner sta guardando? Allora un prezzo fermo è il prezzo CORRENTE.
    const scannerVivo = typeof etaScannerS === 'number'
        && Number.isFinite(etaScannerS) && etaScannerS <= etaMassimaS;
    if (etaQuoteS > etaMassimaS && !scannerVivo) {
        return `quote vecchie di ${Math.round(etaQuoteS)} s: oltre il limite di ${etaMassimaS} s`;
    }
    if (scost.fuoriTolleranza) return 'il prezzo si è mosso oltre la tolleranza dalla proposta';
    if (!abbinabileSufficiente(daChiudere, abbinabileOra)) {
        return 'il mercato non abbina abbastanza a questo prezzo: in live l’ordine verrebbe annullato per intero';
    }
    return null;
}

/** Le urgenti in cima: non approvarle costa. A parità, la più vecchia prima. */
export function ordinaProposte(p: readonly PropostaChiusura[]): PropostaChiusura[] {
    return [...p].sort((a, b) => {
        const ua = a.payload?.urgente === true ? 0 : 1;
        const ub = b.payload?.urgente === true ? 0 : 1;
        if (ua !== ub) return ua - ub;
        return Date.parse(a.created_at) - Date.parse(b.created_at);
    });
}

// --------------------------------------------------------------------- I/O

/** Le proposte in attesa. Solo `proposed`: nessun worker le drena, esistono
 *  soltanto per essere approvate o ignorate da una persona. */
export async function fetchProposte(limit = 50): Promise<PropostaChiusura[]> {
    const { data, error } = await supabase
        .from('safe_strategy_requests')
        .select('*')
        .eq('status', 'proposed')
        .order('created_at', { ascending: false })
        .limit(limit);
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as PropostaChiusura[];
}

/** APPROVA: `proposed → pending`. Da lì in poi il percorso è quello di sempre —
 *  nessuna seconda strada verso Betfair. */
export async function approvaProposta(id: number): Promise<void> {
    const { error } = await supabase.rpc('safe_request_approve', { p_id: id });
    if (error) throw new Error(error.message);
}

/** IGNORA: `proposed → rejected`, con il motivo. Se la condizione di uscita
 *  regge ancora, al ciclo successivo il bot ne propone una nuova: «torna alla
 *  prossima occasione». */
export async function ignoraProposta(id: number, motivo = 'ignorata dall’operatore'): Promise<void> {
    const { error } = await supabase.rpc('safe_request_ignore', { p_id: id, p_reason: motivo });
    if (error) throw new Error(error.message);
}

/** Realtime sulla coda: una proposta nuova deve comparire senza aspettare il
 *  giro di ricarica. UN solo canale. */
export function subscribeProposte(onChange: () => void): () => void {
    const ch = supabase
        .channel('control-room-proposte')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_requests' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(ch); };
}
