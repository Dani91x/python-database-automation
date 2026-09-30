// ============================================================================
// QuoteMercato.tsx — LE QUOTE «DA TRADER», uguali in ogni scheda (B1, 30/09).
//
// «1 40,00/50,00 · X 15,00/18,00 · 2 1,08/1,10, rendere le quote in tempo
// reale piu' visibili e da "trader"» (utente, sezione 4); «stessa visibilita'
// migliorata delle quote» (sezione 5, scheda in gioco); «uniformare la
// visibilita' delle schede» (sezione 6, aperte). Prima erano una riga di testo
// grigio da 10 px, scritta in tre modi diversi in tre punti.
//
// Adesso UN componente:
//   · una cella per selezione: etichetta, miglior BACK in `sky`, miglior LAY
//     in `rose` (DESIGN_SYSTEM §4, nessun altro colore per i lati), cifre
//     `font-mono tabular-nums` in corpo leggibile, `fmtOdds`;
//   · prezzo assente (o non valido: una quota Betfair e' sempre > 1) = `—`,
//     mai `0,00`, mai una cella vuota;
//   · il testo resta «1 1,90/1,92» (la barra fra BACK e LAY e' un carattere
//     vero): chi copia o cerca legge la stessa cosa di prima.
//
// L'ETA' (`EtaQuote`) dice COSA misura: e' l'ULTIMO CAMBIO del Match Odds
// (`odds_ts_ms`), non l'ultima lettura (vedi il commento di `odds_ts_ms` in
// `lib/controlRoom.ts`, con le righe del Python). Le quattro parole e i loro
// colori sono quelli di sempre (`QUOTE_CLS`/`QUOTE_TESTO`, qui spostati da
// `SchedaPartita.tsx` che li riesporta): «fermo» non e' un allarme, «vecchio» e
// «eta' ignota» si'.
//
// Nessuna lettura nuova: tutto arriva da `PartitaGiornata`, gia' in memoria.
// L'eta' cresce al secondo perche' la pagina ricostruisce la giornata a ogni
// tic del suo orologio (`useControlRoom.ts`, `TICK_MS = 1000`): nessun timer qui.
// ============================================================================
import { fmtOdds, fmtAge, fmtNum, DASH } from '@/lib/format';
import { marketStatusMeta } from '@/lib/mike';
import type { LineaOuScheda, PartitaFeedLike, Sport, StatoQuote } from '@/lib/controlRoom';

/** «fermo» NON è un allarme: è un mercato che non si muove, e quel prezzo è
 *  quello corrente. Solo «vecchio» e «ignoto» meritano l'arancione. */
export const QUOTE_CLS: Record<StatoQuote, string> = {
    fresco: 'text-emerald-400',
    fermo: 'text-white/50',
    vecchio: 'text-orange-400',
    ignoto: 'text-orange-400',
};
export const QUOTE_TESTO: Record<StatoQuote, (s: string) => string> = {
    fresco: (s) => s,
    fermo: (s) => `fermo ${s}`,
    vecchio: (s) => `vecchio ${s}`,
    ignoto: () => 'età ignota',
};

/** Il titolo dell'età del Match Odds: la verità su cosa misura. */
export const TITOLO_ETA_QUOTE: Record<StatoQuote, string> = {
    fresco: 'da quando lo scanner ha visto cambiare il Match Odds l’ultima volta (ultimo CAMBIO di prezzo o di importo al meglio, non l’ultima lettura)',
    fermo: 'il prezzo non cambia da questo tempo, ma lo scanner sta guardando: è il prezzo CORRENTE (ultimo CAMBIO, non l’ultima lettura)',
    vecchio: 'il prezzo non cambia da questo tempo e anche lo scanner è fermo: non sappiamo cosa fa il mercato (ultimo CAMBIO, non l’ultima lettura)',
    ignoto: 'lo scanner non ha dichiarato l’istante dell’ultimo cambio di prezzo: età sconosciuta, non è un prezzo su cui fidarsi (non l’ultima lettura)',
};

export interface CellaQuota {
    /** chiave stabile della selezione (home/draw/away, p1/p2, selection_id) */
    chiave: string;
    etichetta: string;
    back: number | null | undefined;
    lay: number | null | undefined;
    /** spiegazione dell'etichetta (es. cosa vuol dire P1) */
    titolo?: string;
}

/** Una quota Betfair valida è > 1: tutto il resto è «assente», mai `0,00`. */
function quota(v: number | null | undefined): string {
    return typeof v === 'number' && Number.isFinite(v) && v > 1 ? fmtOdds(v) : DASH;
}

export function QuoteMercato({ celle, testId, titolo }: {
    celle: readonly CellaQuota[];
    testId: string;
    titolo?: string;
}) {
    return (
        <span className="inline-flex items-center gap-1 flex-wrap" data-testid={testId} title={titolo}>
            {celle.map((c) => (
                <span key={c.chiave} data-testid="cr-quota-cella" title={c.titolo}
                    className="inline-flex items-baseline gap-1 rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5">
                    <span className="text-[11px] font-semibold text-white/60 max-w-[9rem] truncate">{c.etichetta}</span>{' '}
                    <span className="font-mono tabular-nums text-[12.5px] font-semibold text-sky-300"
                        data-testid="cr-quota-back" title="miglior BACK (punta)">{quota(c.back)}</span>
                    <span className="text-white/25 text-[11px]">/</span>
                    <span className="font-mono tabular-nums text-[12.5px] font-semibold text-rose-300"
                        data-testid="cr-quota-lay" title="miglior LAY (banca)">{quota(c.lay)}</span>
                </span>
            ))}
        </span>
    );
}

type Lato = { back: number | null; lay: number | null } | null | undefined;

function haPrezzo(l: Lato): boolean {
    return Boolean(l && (l.back != null || l.lay != null));
}

/**
 * Le celle del Match Odds dalla riga dello scanner (`PartitaGiornata.odds`).
 * Calcio: sempre 1 · X · 2 (un lato assente è `—`, non una cella che manca).
 * Tennis: P1 · P2. P1/P2 sono le selezioni con `sortPriority` 1 e 2 del Match
 * Odds (`scanner.tennis_sides`): nessun codice lega quell'ordine all'ordine dei
 * nomi nell'`event_name`, quindi qui non si scrive un nome che potrebbe essere
 * quello sbagliato. `null` = nessun prezzo nel blocco: la fila non si monta.
 */
export function celleMatchOdds(sport: Sport, odds: PartitaFeedLike['odds'] | undefined): CellaQuota[] | null {
    if (!odds) return null;
    if (sport === 'tennis') {
        if (!haPrezzo(odds.p1) && !haPrezzo(odds.p2)) return null;
        const t = 'selezione del Match Odds con ordine Betfair (sortPriority)';
        return [
            { chiave: 'p1', etichetta: 'P1', back: odds.p1?.back ?? null, lay: odds.p1?.lay ?? null, titolo: `P1 = ${t} 1` },
            { chiave: 'p2', etichetta: 'P2', back: odds.p2?.back ?? null, lay: odds.p2?.lay ?? null, titolo: `P2 = ${t} 2` },
        ];
    }
    if (!haPrezzo(odds.home) && !haPrezzo(odds.draw) && !haPrezzo(odds.away)) return null;
    return [
        { chiave: 'home', etichetta: '1', back: odds.home?.back ?? null, lay: odds.home?.lay ?? null, titolo: '1 = vittoria della squadra di casa' },
        { chiave: 'draw', etichetta: 'X', back: odds.draw?.back ?? null, lay: odds.draw?.lay ?? null, titolo: 'X = pareggio' },
        { chiave: 'away', etichetta: '2', back: odds.away?.back ?? null, lay: odds.away?.lay ?? null, titolo: '2 = vittoria della squadra ospite' },
    ];
}

/** L'età del Match Odds, con l'etichetta di COSA misura. */
export function EtaQuote({ latenzaS, stato, testId }: {
    latenzaS: number | null;
    stato: StatoQuote;
    testId: string;
}) {
    return (
        <span className="font-mono text-[11px] whitespace-nowrap" data-testid={testId} title={TITOLO_ETA_QUOTE[stato]}>
            <span className="text-white/35">ultimo cambio: </span>
            <span className={QUOTE_CLS[stato]} data-testid={`${testId}-valore`}>
                {QUOTE_TESTO[stato](latenzaS == null ? '' : fmtAge(latenzaS))}
            </span>
        </span>
    );
}

/** Fino a questo numero di linee sono TUTTE in vista. Oltre (B1bis, decisione
 *  del coordinatore del 30/09) restano in vista solo quelle di `lineaInVista`,
 *  e tutte le altre stanno nel riquadro chiuso «altre N linee»: nessuna linea
 *  del payload resta fuori dalla scheda. La regola vive SOLO qui. */
export const MAX_LINEE_OU = 4;

/** Le linee su cui operano i bot (Mike: Under/Over 3,5 e 4,5). */
export const LINEE_BOT_OU: readonly number[] = [3.5, 4.5];

/** Regola fissa, scritta: 3,5 e 4,5, piu' ogni linea che il blocco marca
 *  `for_mike` (tenuta per una posizione di Mike) o `decided` (decisa dai gol). */
export function lineaInVista(l: LineaOuScheda): boolean {
    return LINEE_BOT_OU.includes(l.linea) || l.perMike || l.decisa;
}

const REGOLA_LINEE = 'in vista le linee 3,5 e 4,5 (quelle su cui operano i bot: Mike) e ogni linea che lo scanner '
    + 'marca per una posizione di Mike o come decisa dai gol; tutte le altre linee del feed sono in «altre N linee»';

/**
 * Le linee Under/Over della riga (`PartitaGiornata.lineeOu`), con lo stesso
 * componente delle quote. Lo stato del mercato si traduce con
 * `marketStatusMeta` (lo stesso vocabolario del Match Odds); la linea decisa
 * dai gol si dichiara. L'età è quella dell'ultimo CAMBIO della linea
 * (`ts_ms`, R_B1: `seen_ms` è fuori dalla firma della riga e non arriva a
 * ogni book), grigia: da sola non distingue un mercato fermo da uno non più
 * osservato (quel giudizio lo dà il badge del flusso).
 */
export function LineeOu({ linee, testId }: { linee: readonly LineaOuScheda[]; testId: string }) {
    if (linee.length === 0) return null;
    const tutteInVista = linee.length <= MAX_LINEE_OU;
    const inVista = tutteInVista ? linee : linee.filter(lineaInVista);
    const altre = tutteInVista ? [] : linee.filter((l) => !lineaInVista(l));
    return (
        <div className="space-y-1" data-testid={testId} title={tutteInVista ? undefined : REGOLA_LINEE}>
            {inVista.map((l) => <RigaLineaOu key={l.marketId} l={l} />)}
            {altre.length > 0 && (
                <details data-testid="cr-quote-ou-altre">
                    <summary className="cursor-pointer text-[11px] text-white/45 select-none">
                        {altre.length === 1 ? 'altra 1 linea' : `altre ${altre.length} linee`}
                    </summary>
                    <div className="space-y-1 mt-1">
                        {altre.map((l) => <RigaLineaOu key={l.marketId} l={l} />)}
                    </div>
                </details>
            )}
        </div>
    );
}

function RigaLineaOu({ l }: { l: LineaOuScheda }) {
    const stato = marketStatusMeta(l.stato);
    const nome = fmtNum(l.linea, 1);
    return (
        <div className="flex items-center gap-2 flex-wrap" data-testid="cr-quote-ou-linea">
            <span className="text-[11px] font-semibold text-white/50 w-12 shrink-0"
                title={`mercato Under/Over ${nome} gol`}>U/O {nome}</span>
            {stato && (
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${stato.cls} border-current/40`}
                    data-testid="cr-quote-ou-mercato" title="stato del mercato Under/Over, da Betfair">
                    {stato.label}
                </span>
            )}
            {l.decisa && (
                <span className="text-[10px] text-amber-300" data-testid="cr-quote-ou-decisa"
                    title="i gol hanno già superato la linea: esito certo, è nel feed solo per una posizione di Mike">
                    decisa dai gol
                </span>
            )}
            <QuoteMercato testId="cr-quote-ou-prezzi" celle={[
                { chiave: 'under', etichetta: 'Under', back: l.under?.back, lay: l.under?.lay },
                { chiave: 'over', etichetta: 'Over', back: l.over?.back, lay: l.over?.lay },
            ]} />
            {/* R_B1: ultimo CAMBIO (`ts_ms`), stesso testo dell'età del Match
                Odds, grigio neutro: per la linea non c'è il giudizio dello scanner */}
            <span className="font-mono text-[11px] text-white/40 whitespace-nowrap" data-testid="cr-quote-ou-eta"
                title="ultimo cambio di prezzo o di importo di questa linea: non è l’ultima lettura (ts_ms del blocco)">
                ultimo cambio: {l.etaCambioS == null ? 'età ignota' : fmtAge(l.etaCambioS)}
            </span>
        </div>
    );
}

export default QuoteMercato;
