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
        const arr = closesOf.get(parent) ?? [];
        arr.push(t);
        closesOf.set(parent, arr);
    }
    const mk = (open: T, orphan: boolean): CicloGroup<T> => {
        const closes = (closesOf.get(Number(open.id)) ?? [])
            .slice().sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at));
        const rows = [open, ...closes].filter((r) => isSettled(r.status));
        const netPnl = rows.length ? cent(rows.reduce((s, r) => s + (num(r.pnl) ?? 0), 0)) : null;
        return { open, closes, netPnl, orphan };
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
            ? cent(regolate.reduce((s, r) => s + (num(r.pnl) ?? 0), 0))
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
