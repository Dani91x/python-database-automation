// ============================================================================
// eventGroups.ts — RAGGRUPPAMENTO COMUNE delle operazioni: gamba → ciclo →
// PARTITA. Puro, senza React e senza I/O: è la matematica che sta sotto la
// tabella `components/trading/EventPnlTable.tsx`.
//
// PERCHÉ ESISTE (13/09). La stessa domanda — «quanto ho fatto su questa
// partita?» — aveva tre risposte diverse: Mike la calcolava in `lib/mike.ts`,
// Omega in `lib/omegaMatches.ts`, Safe non la calcolava affatto (elencava le
// gambe una per una, e chi voleva il netto della partita doveva sommarle con
// gli occhi — sbagliando, perché apertura e chiusura comparivano allo stesso
// livello). Tre implementazioni sono tre posti dove sbagliare sui soldi.
//
// REGOLE CHE NON SI TOCCANO:
//   1. Il P&L che si mostra è SEMPRE il NETTO di commissione scritto dal
//      servizio sulla riga. Il client non ricalcola mai una commissione.
//   2. Una riga NON REGOLATA non vale zero: vale «—». `netPnl === null`
//      significa «non c'è ancora un risultato», e chi stampa deve scrivere il
//      trattino, MAI «0,00 €» (che vorrebbe dire «ho chiuso in pari»).
//   3. Le righe in `error` non sono operazioni: sono piazzamenti mai avvenuti.
//      Non contano nel netto, nel capitale, nella responsabilità.
// ============================================================================

/** Il minimo che una riga di trade deve avere per essere raggruppata.
 *  Lo soddisfano `MikeTrade`, `SafeTrade` e `OmegaTrade` così come sono. */
export interface PnlTradeLike {
    id: number;
    event_id: string;
    event_name?: string | null;
    side?: string | null;
    mode?: string | null;
    price?: number | null;
    size?: number | null;
    liability?: number | null;
    status: string;
    /** NETTO di commissione; `null` = non ancora regolata (≠ zero) */
    pnl?: number | null;
    placed_at: string;
    /** id della riga di APERTURA che questa riga chiude */
    closes_trade_id?: number | null;
    /**
     * 24/09 - IL P&L REALE DI BETFAIR (migrazione `pnl_betfair_reale_2026-09-24.sql`,
     * scritto dal runner: `reconcile_worker._sync_manual_pnl`). NETTO: profit
     * dell'ordine su `listClearedOrders` meno la sua quota della commissione
     * del mercato. Assente/null = Betfair non ha ancora regolato (o riga
     * paper): vale `pnl`, il calcolo del bot, e si DICHIARA stimato.
     */
    pnl_betfair?: number | null;
    /** quando Betfair ha regolato (settledDate), ISO */
    pnl_betfair_settled_at?: string | null;
}

// --------------------------------------------------- P&L reale o stimato
/**
 * 24/09 - DA DOVE VIENE UN P&L (ordine dell'utente: "il P&L delle operazioni
 * va preso DIRETTAMENTE da Betfair e non stimato, al netto di tutto"):
 *   - `betfair` = il netto regolato da Betfair (`pnl_betfair`);
 *   - `stimato` = soldi veri, ma Betfair non ha ancora regolato: e' il calcolo
 *     del bot, e la pagina lo deve SCRIVERE ("stimato");
 *   - `paper`   = simulazione: Betfair non esiste, e' sempre il calcolo.
 */
export type FontePnl = 'betfair' | 'stimato' | 'paper';

export interface RigaPnlReale {
    pnl?: number | null;
    pnl_betfair?: number | null;
    mode?: string | null;
}

function ePaper(r: { mode?: string | null }): boolean {
    return String(r.mode ?? '').trim().toLowerCase() === 'paper';
}

/** Il P&L da MOSTRARE per una riga: quello di Betfair se c'e' (mai per una
 *  riga paper), altrimenti il calcolo del bot. */
export function pnlDiRiga(r: RigaPnlReale): number | null {
    if (!ePaper(r)) {
        const b = num(r.pnl_betfair);
        if (b != null) return b;
    }
    return num(r.pnl);
}

/** La fonte del P&L di UNA riga. */
export function fonteDiRiga(r: RigaPnlReale): FontePnl {
    if (ePaper(r)) return 'paper';
    return num(r.pnl_betfair) != null ? 'betfair' : 'stimato';
}

/**
 * La fonte di un INSIEME di righe regolate (un'operazione, una partita):
 * `betfair` solo se TUTTE hanno il reale; basta una stimata e l'insieme e'
 * stimato (un totale mezzo reale e mezzo calcolato non e' "da Betfair").
 * Una qualunque riga paper -> paper. Nessuna riga -> null.
 */
export function fonteDiRighe(righe: readonly RigaPnlReale[]): FontePnl | null {
    if (!righe.length) return null;
    if (righe.some(ePaper)) return 'paper';
    return righe.every((r) => num(r.pnl_betfair) != null) ? 'betfair' : 'stimato';
}

/** Esiti CERTI: solo queste righe hanno un P&L da sommare. */
export const SETTLED_STATES: ReadonlySet<string> = new Set(['won', 'lost', 'void']);

export function isSettled(status: string | null | undefined): boolean {
    return SETTLED_STATES.has(String(status ?? '').toLowerCase());
}

/** Una riga in `error` non è un'operazione: nessun ordine reale è mai esistito. */
export function isErrorRow(status: string | null | undefined): boolean {
    return String(status ?? '').toLowerCase() === 'error';
}

function num(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

function cent(n: number): number {
    return Math.round(n * 100) / 100;
}

/**
 * La RADICE di una riga: si risale `closes_trade_id` finche' il padre e' fra
 * le righe caricate. Difesa contro un ciclo nei dati (A chiude B, B chiude A):
 * al primo nodo gia' visto ci si ferma, mai un giro infinito.
 */
function radiceDi<T extends PnlTradeLike>(t: T, byId: ReadonlyMap<number, T>): T {
    let nodo = t;
    const visti = new Set<number>([Number(t.id)]);
    for (;;) {
        const p = nodo.closes_trade_id == null ? null : Number(nodo.closes_trade_id);
        if (p == null) return nodo;
        const padre = byId.get(p);
        if (!padre || visti.has(p)) return nodo;
        visti.add(p);
        nodo = padre;
    }
}

/**
 * 23/09 - IL NETTO DI UN'OPERAZIONE CHIUSA: apertura + TUTTE le gambe di
 * chiusura regolate, ed e' il numero che la riga di un'operazione deve
 * mostrare. Prima la riga mostrava il P&L della sola gamba d'apertura: su un
 * cash out (back 3,00 @1,15 vinto +0,45, lay di chiusura 3,17 @1,08 perso
 * -0,25) si leggeva +0,45 invece di +0,20.
 *
 * `null` (= '-', mai zero) quando il risultato NON e' ancora definitivo:
 *  - l'apertura non e' regolata, o non porta un `pnl` numerico;
 *  - una gamba di chiusura e' ancora viva (non regolata, non annullata, non
 *    in errore): sommare solo le regolate darebbe un parziale mostrato come
 *    definitivo. Stesso criterio di `posizioniChiuse.ts`.
 * Le gambe `cancelled`/`error` non sono mai andate a mercato: non pesano.
 */
export function nettoCicloChiuso(
    open: { status: string } & RigaPnlReale,
    closes: readonly ({ status: string } & RigaPnlReale)[],
): number | null {
    if (!isSettled(open.status)) return null;
    // 24/09 - di ogni gamba il P&L di Betfair se c'e', altrimenti il calcolo
    const base = pnlDiRiga(open);
    if (base == null) return null;
    let v = base;
    for (const g of closes) {
        const s = String(g.status ?? '').toLowerCase();
        if (isSettled(s)) { v += pnlDiRiga(g) ?? 0; continue; }
        if (s === 'cancelled' || isErrorRow(s)) continue;
        return null;
    }
    return cent(v);
}

// ------------------------------------------------------------- livello CICLO
/** Un CICLO: l'apertura più le gambe che la chiudono. */
export interface CicloGroup<T extends PnlTradeLike> {
    open: T;
    /** chiusure che riferiscono questa apertura (`closes_trade_id`), dalla più vecchia */
    closes: T[];
    /** P&L NETTO del ciclo: somma delle righe GIÀ REGOLATE. `null` = nessuna. */
    netPnl: number | null;
    /** true = chiusura senza la sua apertura fra le righe caricate (mai nascosta) */
    orphan: boolean;
    /** 24/09 - da dove viene `netPnl` (Betfair / stimato / paper); null = nessuna riga regolata */
    fontePnl?: FontePnl | null;
}

/**
 * Righe piatte → cicli, con le chiusure ANNIDATE sotto la loro apertura.
 * Aperture dalla più recente, chiusure nell'ordine in cui sono avvenute.
 * Una chiusura la cui apertura non è nel set diventa un ciclo a sé, DICHIARATO
 * orfano: nasconderla significherebbe far sparire euro veri dalla pagina.
 */
export function groupTradesIntoCicli<T extends PnlTradeLike>(trades: readonly T[]): CicloGroup<T>[] {
    const byId = new Map<number, T>();
    for (const t of trades) byId.set(Number(t.id), t);
    const closesOf = new Map<number, T[]>();
    const opens: T[] = [];
    const orphans: T[] = [];
    for (const t of trades) {
        const parent = t.closes_trade_id == null ? null : Number(t.closes_trade_id);
        if (parent == null) { opens.push(t); continue; }
        if (!byId.has(parent)) { orphans.push(t); continue; }
        // 23/09 - CATENA A <- B <- C (una copertura a sua volta coperta:
        // place-and-trim, chiusura parziale richiusa). Prima C finiva sotto B,
        // che non e' un'apertura: C spariva da OGNI ciclo e il suo P&L dal
        // netto. Si risale fino alla RADICE presente nel set (stessa regola di
        // `posizioniChiuse.ts::gambeDi`); se la catena si spezza, la radice e'
        // la gamba piu' alta ancora presente, cioe' un'orfana dichiarata.
        const radice = radiceDi(t, byId);
        const arr = closesOf.get(Number(radice.id)) ?? [];
        arr.push(t);
        closesOf.set(Number(radice.id), arr);
    }
    const mk = (open: T, orphan: boolean): CicloGroup<T> => {
        const closes = (closesOf.get(Number(open.id)) ?? [])
            .slice().sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at));
        const rows = [open, ...closes].filter((r) => isSettled(r.status));
        const netPnl = rows.length ? cent(rows.reduce((s, r) => s + (pnlDiRiga(r) ?? 0), 0)) : null;
        return { open, closes, netPnl, orphan, fontePnl: fonteDiRighe(rows) };
    };
    return [
        ...opens.map((o) => mk(o, false)),
        ...orphans.map((o) => mk(o, true)),
    ].sort((a, b) => Date.parse(b.open.placed_at) - Date.parse(a.open.placed_at));
}

// ------------------------------------------------------------ livello PARTITA
/** Una PARTITA: il netto che il trader incassa e i cicli che lo compongono. */
export interface EventGroup<T extends PnlTradeLike> {
    event_id: string;
    event_name: string;
    /** cicli della partita, dal più recente */
    cicli: CicloGroup<T>[];
    /** P&L NETTO delle sole righe REGOLATE. `null` = niente ancora regolato →
     *  si stampa «—», MAI «0,00 €». */
    netPnl: number | null;
    /** c'è ancora almeno una riga non regolata: il netto qui sopra è PARZIALE */
    apertaAncora: boolean;
    righeRegolate: number;
    righeAperte: number;
    /** capitale impegnato nelle APERTURE (lo stake, non la responsabilità) */
    investito: number;
    /** quanto è ancora a rischio: liability delle righe NON regolate */
    liability: number;
    /** istante dell'operazione più recente (ms), per l'ordinamento */
    ultimaMs: number;
    /** 'paper', 'live', o 'mista' (una partita che mescola le due contabilità) */
    mode: string;
}

/** Opzioni di raggruppamento: un filtro sui cicli deciso dal chiamante. */
export interface GroupByEventOpts<T extends PnlTradeLike> {
    /** true = il ciclo entra. Serve alle schede «Risultati Pre-Match / Live». */
    filtro?: (c: CicloGroup<T>) => boolean;
}

/**
 * I cicli raggruppati per PARTITA: UNA riga per partita col suo netto.
 *
 * Il netto si ottiene sommando i `pnl` delle righe regolate, che il servizio
 * scrive già NETTI di commissione. Apertura e chiusura sono due scommesse
 * distinte, ognuna col suo esito: sommarle NON è un doppio conteggio.
 */
export function groupCicliByEvent<T extends PnlTradeLike>(
    cicli: readonly CicloGroup<T>[],
    opts: GroupByEventOpts<T> = {},
): EventGroup<T>[] {
    const perEvento = new Map<string, CicloGroup<T>[]>();
    for (const g of cicli) {
        if (opts.filtro && !opts.filtro(g)) continue;
        const eid = String(g.open.event_id ?? '');
        if (!eid) continue;
        const arr = perEvento.get(eid) ?? [];
        arr.push(g);
        perEvento.set(eid, arr);
    }
    const out: EventGroup<T>[] = [];
    for (const [eid, gruppi] of perEvento) {
        const righe = gruppi.flatMap((g) => [g.open, ...g.closes]);
        const vere = righe.filter((r) => !isErrorRow(r.status));
        const regolate = vere.filter((r) => isSettled(r.status));
        const aperte = vere.filter((r) => !isSettled(r.status));
        const netPnl = regolate.length
            ? cent(regolate.reduce((s, r) => s + (pnlDiRiga(r) ?? 0), 0))
            : null;
        // capitale: SOLO le aperture (una chiusura non impegna capitale nuovo,
        // svolge quello già impegnato) e SOLO quelle non in errore
        const investito = cent(gruppi.reduce((s, g) => (
            isErrorRow(g.open.status) || g.orphan ? s : s + (num(g.open.size) ?? 0)
        ), 0));
        // rischio: la responsabilità delle righe ANCORA VIVE. Una riga regolata
        // non rischia più niente, una in errore non ha mai rischiato niente.
        const liability = cent(aperte.reduce((s, r) => s + (num(r.liability) ?? 0), 0));
        const modi = new Set(vere.map((r) => String(r.mode ?? '')).filter(Boolean));
        out.push({
            event_id: eid,
            event_name: String(gruppi[0]?.open.event_name ?? eid),
            cicli: gruppi.slice().sort((a, b) => Date.parse(b.open.placed_at) - Date.parse(a.open.placed_at)),
            netPnl,
            apertaAncora: aperte.length > 0,
            righeRegolate: regolate.length,
            righeAperte: aperte.length,
            investito,
            liability,
            ultimaMs: Math.max(...righe.map((r) => Date.parse(r.placed_at) || 0), 0),
            mode: modi.size === 1 ? [...modi][0] : (modi.size === 0 ? '' : 'mista'),
        });
    }
    return out.sort((a, b) => b.ultimaMs - a.ultimaMs);
}

// ------------------------------------------------------------------- TOTALI
/** I cinque numeri della barra dei totali, più i conteggi di contorno. */
export interface TotaliOperazioni {
    /** posizioni = cicli (le chiusure stanno dentro il loro ciclo) */
    operazioni: number;
    partite: number;
    /** somma dei netti GIÀ REGOLATI. `null` = nessuna partita ha un risultato */
    realizzato: number | null;
    /** capitale impegnato nelle aperture */
    investito: number;
    /** responsabilità ancora a rischio */
    liability: number;
    partiteConRisultato: number;
    partiteAperte: number;
    vinte: number;
    perse: number;
}

/**
 * Quanto ha reso davvero un insieme di partite.
 *
 * `realizzato` è `null` — non zero — quando NESSUNA partita ha ancora un
 * risultato: la barra deve scrivere «—». Uno «0,00 €» lì dentro significa «ho
 * operato e sono in pari», che è una cosa completamente diversa da «non ho
 * ancora incassato niente», ed è la bugia più pericolosa della pagina.
 */
export function totaliOperazioni<T extends PnlTradeLike>(
    eventi: readonly EventGroup<T>[],
): TotaliOperazioni {
    let realizzato = 0, partiteConRisultato = 0, partiteAperte = 0, vinte = 0, perse = 0;
    let operazioni = 0, investito = 0, liability = 0;
    for (const e of eventi) {
        operazioni += e.cicli.length;
        investito += e.investito;
        liability += e.liability;
        if (e.apertaAncora) partiteAperte += 1;
        if (e.netPnl == null) continue;
        realizzato += e.netPnl;
        partiteConRisultato += 1;
        if (e.netPnl > 0) vinte += 1;
        else if (e.netPnl < 0) perse += 1;
    }
    return {
        operazioni,
        partite: eventi.length,
        realizzato: partiteConRisultato > 0 ? cent(realizzato) : null,
        investito: cent(investito),
        liability: cent(liability),
        partiteConRisultato,
        partiteAperte,
        vinte,
        perse,
    };
}

/**
 * Solo le righe di UNA modalità (paper / live).
 *
 * Un totale che somma euro veri ed euro simulati è una bugia: il backend tiene
 * le due contabilità separate e la UI deve fare lo stesso. `mode` assente =
 * nessun filtro (si mostra tutto e l'etichetta NON dichiara una modalità).
 */
export function tradesOfMode<T extends PnlTradeLike>(
    trades: readonly T[], mode: string | null | undefined,
): T[] {
    const m = String(mode ?? '').trim().toLowerCase();
    if (!m) return [...trades];
    return trades.filter((t) => String(t.mode ?? '').trim().toLowerCase() === m);
}
