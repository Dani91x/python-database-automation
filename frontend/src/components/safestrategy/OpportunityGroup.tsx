// ============================================================================
// OpportunityGroup.tsx — card delle OPPORTUNITÀ di una partita (calcio/tennis).
//
// Quattro TIPI, ognuno col suo colore fisso e le sue informazioni chiave:
//   · MODELLO     λ Poisson vs quota: probabilità grezza/calibrata, edge, EV;
//   · ANOMALIA    regola di prezzo violata: la quota di riferimento rende
//                 evidente l'errore ("Under 6.5 @1.01 → Under 7.5 @1.10");
//   · COMBINAZ.   più gambe con profitto BLOCCATO: stake per gamba scalato
//                 allo stake totale scelto, peggiore/migliore per € e in €;
//   · TENNIS      modello punto: set/game, rischio ritiro, momentum contro.
// Ordinate per EV × confidenza — il numero grande è l'EV, perché è quello
// che decide — e si investe con un click (le combinazioni piazzano TUTTE
// le gambe, una richiesta per gamba con chiave di idempotenza condivisa).
// ============================================================================
import { useMemo, useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { fmtMoney, fmtNum, fmtOdds, fmtPct, DASH, MINUS } from '@/lib/format';
import { InvestAction } from './InvestAction';
import {
    anomalyRefLabel, comboLegStakes, comboLock, oppKind, oppScore, staleReason,
    type FeedFreshness, type SafeMode, type SafeOppKind, type SafeOpportunity,
    type SafeOpportunityRow, type SafeRequest,
} from '@/lib/safeBot';
import { sideBadgeClass } from './variantStyles';
import { safeMarketLabel } from './safeActivity';

// formati UNICI del design system: percentuali "12,5 %", denaro "12,50 €"
function pct(v: number | null | undefined, digits = 1): string {
    return fmtPct(v, digits);
}
function signedPct(v: number | null | undefined): string {
    const n = Number(v);
    if (!Number.isFinite(n)) return DASH;
    return `${n < 0 ? MINUS : '+'}${fmtPct(Math.abs(n))}`;
}
function eur(v: number | null | undefined): string {
    return fmtMoney(v);
}
function signedEur(v: number | null | undefined): string {
    return fmtMoney(v, { signed: true });
}

/** stile FISSO per tipo: l'occhio lo riconosce anche con tante card insieme */
export const OPP_KIND_META: Record<SafeOppKind, { label: string; badge: string; title: string }> = {
    model: {
        label: 'MODELLO', badge: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
        title: 'probabilità del modello (λ Poisson) contro la quota',
    },
    anomaly: {
        label: 'ANOMALIA', badge: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
        title: 'regola di prezzo violata: la quota è incoerente con una quota sorella',
    },
    combo: {
        label: 'COMBINAZIONE', badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
        title: 'più gambe insieme: profitto bloccato qualunque sia l’esito',
    },
    tennis: {
        label: 'TENNIS', badge: 'bg-secondary/15 text-secondary border-secondary/40',
        title: 'modello a punti del tennis (servizio, set, momentum)',
    },
};

/** `payload.source` del servizio = da dove arrivano i λ (gol attesi).
 *  CERT. 12/09 — mancava `default`, che è il valore di RIPIEGO scritto da
 *  `resolve_event_lambdas` quando la catena fallisce: a schermo arrivava il
 *  codice nudo "default" (visto nel dump live delle 17:00, Wofoo Tai Po v
 *  Hong Kong FC) e il trader non poteva sapere che quella probabilità NON
 *  guarda la partita. */
const LAMBDA_SOURCE_LABEL: Record<string, string> = {
    fixture: 'λ dal motore della partita',
    pre_ko: 'λ dalle quote pre-partita',
    default: 'λ generici di ripiego (nessun dato su questa partita)',
    none: 'λ non disponibili',
};
/** true = i λ NON vengono dalla partita: la probabilità del modello è debole */
export function lambdaSourceIsWeak(source: unknown): boolean {
    const s = String(source ?? '').trim().toLowerCase();
    return s === 'default' || s === 'none' || s === '';
}
/** etichetta italiana della sorgente λ: mai un codice tecnico nudo a schermo */
export function lambdaSourceLabel(source: unknown): string {
    const s = String(source ?? '').trim();
    if (!s) return LAMBDA_SOURCE_LABEL.none;
    return LAMBDA_SOURCE_LABEL[s.toLowerCase()] ?? `λ da ${s.replace(/_/g, ' ')}`;
}

const RULE_LABEL: Record<string, string> = {
    ou_ladder: 'scala Under/Over incoerente',
    decided: 'esito già deciso dal punteggio',
    mo_cs: 'Match Odds vs Risultato Esatto',
    ht_open: 'Half Time aperto oltre il tempo',
};
export function anomalyRuleLabel(rule: string | null | undefined): string {
    if (!rule) return 'regola';
    return RULE_LABEL[rule] ?? rule;
}

/**
 * SOLO la quota di RIFERIMENTO di un'anomalia ("Under 7.5 back 1,11"), senza
 * la quota anomala. Il servizio la scrive come stringa (`anomaly.py`
 * `ref="Under 7.5 back 1.11"`) oppure come oggetto. Serve a DICHIARARE da dove
 * viene la probabilità mostrata: su un riferimento illiquido il numero è aria.
 */
export function anomalyRefText(o: { ref?: unknown }): string | null {
    const ref = o.ref;
    if (ref == null) return null;
    if (typeof ref === 'string') {
        const s = ref.trim();
        // il backend scrive la QUOTA in coda col punto ("Under 6.5 back 1.01"):
        // solo quella va nella forma italiana, la LINEA (6.5) resta com'e'
        return s === '' ? null : s.replace(/(\d+)\.(\d+)\s*$/, '$1,$2');
    }
    if (typeof ref !== 'object') return null;
    const r = ref as { selection_name?: string | null; market_name?: string | null; market_type?: string | null; price?: number | null; side?: string | null };
    const name = r.selection_name ?? r.market_name ?? r.market_type ?? null;
    const price = r.price != null && Number.isFinite(Number(r.price)) ? fmtOdds(Number(r.price)) : null;
    if (!name && !price) return null;
    const side = r.side ? ` ${String(r.side).toLowerCase()}` : '';
    return `${name ?? '?'}${side}${price ? ` ${price}` : ''}`;
}

const COMBO_LABEL: Record<string, string> = {
    dutch: 'dutching', under_stack: 'scala Under', over_stack: 'scala Over',
    ou_span: 'forbice Under/Over', cs_cover: 'copertura Risultato Esatto',
};
export function comboTypeLabel(combo: string | null | undefined): string {
    if (!combo) return 'combinazione';
    return COMBO_LABEL[combo] ?? combo;
}

/** riga di opportunita' piu' vecchia di cosi' = quote/probabilita' stantie:
 *  si mostra l'eta' e si spegne "Investi" (il modello non e' piu' quello) */
export const OPP_ROW_STALE_MS = 60_000;

export type OppKindFilter = 'all' | SafeOppKind;

/** Etichetta del mercato SENZA ripetere la linea.
 *  CERT. 12/09 — `safeMarketLabel('OVER_UNDER', 5.5)` restituisce già
 *  "Over/Under 5,5" e la UI ci appiccicava di nuovo la linea: a schermo
 *  usciva "Over/Under 5.5 5,5" (visto nel dump live delle 17:00). La linea si
 *  aggiunge SOLO se l'etichetta scelta non la contiene già. */
export function marketLabelOf(o: { market_name: string | null; market_type: string; line: number | null }): string {
    const base = o.market_name ?? safeMarketLabel(o.market_type, o.line) ?? o.market_type;
    if (o.line == null || !Number.isFinite(Number(o.line))) return base;
    const n = Number(o.line);
    const already = base.includes(String(n)) || base.includes(String(n).replace('.', ','));
    return already ? base : `${base} ${fmtNum(n, 1)}`;
}

/** Opportunita' della riga che superano i filtri, ordinate per EV × confidenza.
 *  Esportata perche' la pagina sappia se i filtri hanno svuotato tutto. */
export function filterOpps(
    row: SafeOpportunityRow, minConfidence: number, sideFilter: 'all' | 'back' | 'lay',
    kindFilter: OppKindFilter = 'all',
): SafeOpportunity[] {
    const p = row.payload ?? { opps: [] };
    return (Array.isArray(p.opps) ? p.opps : [])
        .filter((o) => Number(o.confidence) >= minConfidence)
        .filter((o) => sideFilter === 'all' || o.side === sideFilter)
        .filter((o) => kindFilter === 'all' || oppKind(o) === kindFilter)
        .sort((a, b) => oppScore(b) - oppScore(a));
}

export interface OpportunityGroupProps {
    row: SafeOpportunityRow;
    mode: SafeMode;
    stake: number;
    /** size minima Betfair in uso dal servizio (params_effective.min_stake) */
    minStake?: number;
    /** cap di responsabilità per operazione (params.max_liability_per_trade) */
    maxLiability?: number | null;
    requests: SafeRequest[];
    minConfidence: number;
    sideFilter: 'all' | 'back' | 'lay';
    kindFilter?: OppKindFilter;
    /** timestamp corrente (dal chiamante) per l'eta' della riga */
    nowMs?: number;
    /** freschezza della riga del FEED dell'evento (`safe_strategy_scan`): è
     *  l'unica età VERA delle quote. Assente = età delle quote non verificabile
     *  (il payload delle opportunità non pubblica timestamp del book). */
    freshness?: FeedFreshness | null;
    /** size = stake della gamba (modello/anomalia/tennis) o stake TOTALE (combo) */
    onPlace: (opp: SafeOpportunity, size: number) => Promise<number | null>;
    /** tennis: nomi dei giocatori dal feed (la riga opportunità porta solo 'p1'/'p2') */
    players?: { p1?: string | null; p2?: string | null } | null;
}

function KindBadge({ kind }: { kind: SafeOppKind }) {
    const m = OPP_KIND_META[kind];
    return (
        <Badge
            variant="outline"
            data-testid="opp-kind"
            data-kind={kind}
            className={`text-[10px] font-heading font-bold ${m.badge}`}
            title={m.title}
        >
            {m.label}
        </Badge>
    );
}

function Cell({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
    return (
        <div title={title}>
            <div className="text-slate-500 uppercase tracking-wide text-[10px]">{label}</div>
            <div className="tabular-nums">{children}</div>
        </div>
    );
}

/** blocco COMBINAZIONE: gambe con stake scalato e lock garantito */
/**
 * Stake TOTALE massimo che entra davvero su TUTTE le gambe.
 *
 * CERT. 12/09 — prima si mostrava come "abbinabile subito" il minimo fra le
 * size delle gambe, confrontandolo di fatto con lo stake TOTALE: numeri di due
 * grandezze diverse. Quello che conta per una combinazione è il totale oltre
 * il quale la gamba più stretta non entra: min_i (abbinabile_i / quota_i dello
 * stake). Se una gamba non pubblica la size, il totale non è verificabile
 * (null) — meglio "n/d" di un numero inventato.
 */
export function comboMatchableTotal(
    legs: { size_available: number | null; stake: number }[], total: number,
): number | null {
    if (legs.length === 0 || !(total > 0)) return null;
    let cap: number | null = null;
    for (const l of legs) {
        // `Number(null)` è 0, non NaN: una gamba senza size diventerebbe una
        // gamba "a zero" e il totale crollerebbe a 0 € invece di dire "non so".
        if (l.size_available == null) return null;
        const avail = Number(l.size_available);
        const st = Number(l.stake);
        if (!Number.isFinite(avail)) return null;      // una gamba cieca = totale non verificabile
        if (!(st > 0)) continue;
        const maxTotal = (avail * total) / st;
        cap = cap == null ? maxTotal : Math.min(cap, maxTotal);
    }
    return cap == null ? null : Math.floor(cap * 100) / 100;
}

function ComboBody({ o, stake, minStake, maxLiability, mode, requests, disabled, disabledReason, onPlace }: {
    o: SafeOpportunity; stake: number; minStake?: number; maxLiability?: number | null;
    mode: SafeMode; requests: SafeRequest[];
    disabled: boolean; disabledReason?: string;
    onPlace: (size: number) => Promise<number | null>;
}) {
    // lo stake totale scelto nell'InvestAction non e' osservabile dall'esterno:
    // lo si specchia qui per scalare le gambe e il lock in tempo reale
    const [total, setTotal] = useState<number>(stake);
    const legs = useMemo(() => comboLegStakes(o, total), [o, total]);
    const lock = comboLock(o, total);
    const minAvail = comboMatchableTotal(legs, total);
    return (
        <>
            <div className="mt-2 text-[11px] text-muted-foreground">
                <span className="text-white font-bold">{comboTypeLabel(o.combo)}</span> · {legs.length} gambe ·
                stake totale <b className="text-white tabular-nums">{eur(total)}</b>
            </div>
            <ul className="mt-1.5 space-y-1" data-testid="combo-legs">
                {legs.map((l, i) => (
                    <li
                        key={`${l.market_id}:${l.selection_id}:${l.side}:${i}`}
                        data-testid="combo-leg"
                        className="flex items-center gap-2 flex-wrap rounded-md border border-white/5 bg-white/[0.03] px-2 py-1 text-[11px]"
                    >
                        <Badge variant="outline" className={`text-[10px] font-heading font-bold ${sideBadgeClass(l.side === 'lay' ? 'LAY' : 'BACK')}`}>
                            {l.side.toUpperCase()}
                        </Badge>
                        <span className="text-white font-semibold">{l.selection_name ?? `#${l.selection_id}`}</span>
                        <span className="text-slate-500" title={l.market_type}>{safeMarketLabel(l.market_type) ?? l.market_type}</span>
                        <span className="ml-auto tabular-nums text-primary font-bold">@{fmtOdds(l.price)}</span>
                        <span className="tabular-nums text-white font-bold w-16 text-right" title="stake di questa gamba (scalato allo stake totale)">
                            {eur(l.stake)}
                        </span>
                        <span className="tabular-nums text-slate-400 w-20 text-right" title="abbinabile subito su questa gamba">
                            abb. {l.size_available != null ? eur(l.size_available) : 'n/d'}
                        </span>
                    </li>
                ))}
            </ul>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]" data-testid="combo-lock">
                <Cell label="Bloccato / €" title="profitto garantito per ogni € di stake totale, nel caso peggiore">
                    <span className={`font-bold ${(lock.worstPerEur ?? 0) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                        {lock.worstPerEur != null ? signedEur(lock.worstPerEur) : '—'}
                    </span>
                </Cell>
                <Cell label="Bloccato in €" title="profitto garantito sullo stake totale scelto">
                    <span className={`font-bold ${(lock.worstEur ?? 0) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                        {lock.worstEur != null ? signedEur(lock.worstEur) : '—'}
                    </span>
                </Cell>
                <Cell label="Migliore / €" title="profitto per € nel caso migliore">
                    <span className="text-slate-300">{lock.bestPerEur != null ? signedEur(lock.bestPerEur) : '—'}</span>
                </Cell>
                <Cell label="Migliore in €" title="profitto nel caso migliore sullo stake totale">
                    <span className="text-slate-300">{lock.bestEur != null ? signedEur(lock.bestEur) : '—'}</span>
                </Cell>
            </div>
            <InvestAction
                mode={mode}
                side={o.side}
                price={Number(o.price)}
                sizeAvailable={minAvail}
                defaultStake={stake}
                /* CERT. 12/09 — il minimo Betfair vale per OGNI GAMBA, non per
                   il totale: con gambe sbilanciate (es. 9,66 € e 0,34 €) la
                   gamba piccola viene RIFIUTATA dall'exchange e resta una
                   posizione nuda, cioe' l'opposto del "rischio zero".
                   ``min_total_stake`` e' il totale sotto il quale questo
                   accade, calcolato da combos.py sulla combinazione reale. */
                minStake={Math.max(Number(minStake) || 0, Number(o.min_total_stake) || 0) || undefined}
                maxLiability={maxLiability}
                sizeLabel="stake totale abbinabile"
                requests={requests}
                /* si spegne SOLO se il book non regge la combinazione nemmeno
                   al totale minimo: con uno stake piu' alto di quello pubblicato
                   la combinazione resta eseguibile, e il minimo lo dichiara gia'
                   ``minStake`` qui sopra. */
                disabled={disabled || legs.length === 0 || o.book_supports_min === false}
                disabledReason={
                    legs.length === 0 ? 'combinazione senza gambe'
                        : o.book_supports_min === false
                            ? 'il book non regge tutte le gambe al minimo Betfair: combinazione non piazzabile intera'
                            : disabledReason}
                onStakeChange={setTotal}
                onPlace={onPlace}
            />
            <p className="mt-1 text-[10px] text-slate-500">
                Piazza <b>tutte le {legs.length} gambe</b> in un colpo (una richiesta per gamba, stessa chiave).
                Lo stake € è quello TOTALE della combinazione.
            </p>
        </>
    );
}

export function OpportunityGroup({
    row, mode, stake, minStake, maxLiability, requests, minConfidence, sideFilter,
    kindFilter = 'all', nowMs, freshness = null, onPlace, players,
}: OpportunityGroupProps) {
    const p = row.payload ?? { opps: [] };
    const opps = filterOpps(row, minConfidence, sideFilter, kindFilter);

    if (opps.length === 0) return null;

    const now = nowMs ?? Date.now();
    const rowMs = row.updated_at ? Date.parse(row.updated_at) : NaN;
    const ageSec = Number.isFinite(rowMs) ? Math.max(0, Math.round((now - rowMs) / 1000)) : null;
    const calcStale = ageSec != null && ageSec * 1000 > OPP_ROW_STALE_MS;
    // CERT. 12/09 — `updated_at` della riga di opportunità è l'età dell'ULTIMO
    // CALCOLO del servizio, NON l'età della quota: il payload delle opportunità
    // non pubblica alcun timestamp del book (`opportunity.Opportunity` non ha
    // un campo età) e il servizio riscrive la riga a ogni ciclo perché la
    // confidenza decade col tempo. Risultato: una quota vecchia poteva
    // comparire come "3 s fa". L'unica età VERA del book è quella della riga
    // del feed (`safe_strategy_scan`), che arriva da fuori come `freshness`.
    const feedStale = staleReason(freshness);
    const stale = calcStale || feedStale != null;
    const staleMsg = feedStale ?? (calcStale ? `modello non ricalcolato da ${ageSec}s` : undefined);

    const isTennis = row.sport === 'tennis';
    const score = isTennis
        ? (p.sets ? `set ${p.sets.p1}-${p.sets.p2}${p.games ? ` · game ${p.games.p1}-${p.games.p2}` : ''}` : 'set —')
        : (p.score_home != null && p.score_away != null ? `${p.score_home}-${p.score_away}` : '?-?');
    // CERT. 13/09 — una λ non calcolata NON è «λ 0,00»: zero gol attesi è una
    // previsione fortissima, e il trader la leggeva al posto di «non lo so».
    // Il modello può pubblicare `lambdas` con un solo lato valorizzato.
    const lamTxt = (v: number | null | undefined) =>
        (v == null || !Number.isFinite(Number(v)) ? 'n/d' : fmtNum(Number(v), 2));
    const lam = p.lambdas
        ? `λ ${lamTxt(p.lambdas.home)} / ${lamTxt(p.lambdas.away)}`
        : null;

    return (
        <div className="glass-card rounded-xl border border-white/10 p-4" data-testid="opp-group">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-display font-black text-base text-white truncate max-w-[280px]">
                    {p.event_name ?? row.event_id}
                </span>
                <span
                    className="font-mono tabular-nums text-xs text-muted-foreground"
                    data-testid="opp-score"
                    /* il punteggio del feed Betfair arriva con 2-3 s di ritardo:
                       un gol appena segnato può non essere ancora qui, e
                       l'opportunità sarebbe calcolata su una situazione superata */
                    title="minuto e punteggio dal feed Betfair: arrivano con 2-3 s di ritardo sul campo"
                >
                    {isTennis ? score : `${p.minute != null ? `${p.minute}′` : '—′'} · ${score}`}
                    <span className="ml-1 text-slate-600" aria-hidden>(−2/3 s)</span>
                </span>
                {lam && (
                    <Badge variant="outline" className="text-[10px] bg-white/5 text-muted-foreground border-white/10 font-mono">
                        {lam}
                    </Badge>
                )}
                {p.source && (
                    // da dove vengono i λ (`opportunity.resolve_lambdas`): "fixture" e
                    // "pre_ko" sono codici del servizio, non parole per un trader
                    <Badge
                        variant="outline"
                        data-testid="opp-lambda-source"
                        data-weak={lambdaSourceIsWeak(p.source) ? 'true' : undefined}
                        className={`text-[10px] ${lambdaSourceIsWeak(p.source)
                            ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                            : 'bg-white/5 text-muted-foreground border-white/10'}`}
                        title={lambdaSourceIsWeak(p.source)
                            ? 'il motore non ha dati su questa partita: il modello sta usando gol attesi generici, quindi probabilità, edge ed EV valgono poco'
                            : 'da dove arrivano i λ (gol attesi) usati dal modello'}
                    >
                        {lambdaSourceLabel(p.source)}
                    </Badge>
                )}
                {ageSec != null && (
                    <Badge
                        variant="outline"
                        data-testid="opp-age"
                        className={`text-[10px] font-mono tabular-nums ${calcStale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-muted-foreground border-white/10'}`}
                        title="da quanto il servizio non ricalcola questa partita. NON è l’età della quota: quella è nel chip del feed."
                    >
                        calcolo {ageSec}s fa
                    </Badge>
                )}
                {freshness?.ageSec != null && (
                    <Badge
                        variant="outline"
                        data-testid="opp-feed-age"
                        className={`text-[10px] font-mono tabular-nums ${feedStale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-muted-foreground border-white/10'}`}
                        title={feedStale ?? 'età della riga del feed: è l’età VERA delle quote mostrate qui sotto'}
                    >
                        feed {freshness.ageSec}s
                    </Badge>
                )}
                {freshness == null && (
                    <Badge
                        variant="outline"
                        data-testid="opp-feed-unknown"
                        className="text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40"
                        title="l’età delle quote di questa partita non è disponibile: i prezzi qui sotto potrebbero non essere quelli di adesso"
                    >
                        età quote n/d
                    </Badge>
                )}
                <Badge variant="outline" className="ml-auto text-[10px] bg-secondary/15 text-secondary border-secondary/40 font-mono tabular-nums">
                    {opps.length} opp.
                </Badge>
            </div>

            {stale && (
                // M-21: la riga resta elencata come "attuale" per mezz'ora, ma
                // "Piazza" si spegne: il motivo va DETTO, non subito
                <p className="mt-2 text-[11px] text-red-300" data-testid="opp-stale-note">
                    {feedStale
                        ? `${feedStale}: il bottone Piazza resta spento finché il feed non torna ad aggiornarsi (un'opportunità vale solo sul prezzo di adesso).`
                        : `modello non ricalcolato da ${ageSec}s: il bottone Piazza resta spento finché `
                          + "il servizio non ricalcola (un'opportunità vale solo sul prezzo di adesso)."}
                </p>
            )}

            <div className="mt-3 space-y-3">
                {opps.map((o) => {
                    const kind = oppKind(o);
                    const calibrated = kind === 'model' && o.calibration?.applied === true;
                    const refLabel = kind === 'anomaly' ? anomalyRefLabel(o) : null;
                    const extra = kind === 'tennis' ? (o.extra ?? null) : null;
                    const retire = extra?.retire_risk == null ? NaN : Number(extra.retire_risk);
                    return (
                        <div
                            key={`${kind}:${o.market_id}:${o.selection_id}:${o.side}:${o.combo ?? ''}`}
                            className="rounded-lg border border-white/10 bg-black/30 p-3"
                            data-testid="opp-row"
                            data-kind={kind}
                        >
                            <div className="flex items-center gap-2 flex-wrap">
                                <KindBadge kind={kind} />
                                <Badge variant="outline" className={`text-[10px] font-heading font-bold ${sideBadgeClass(o.side === 'lay' ? 'LAY' : 'BACK')}`}>
                                    {o.side.toUpperCase()}
                                </Badge>
                                <span
                                    className="font-bold text-white text-sm"
                                    title={`selezione ${o.selection_id} · mercato ${o.market_id} (${o.market_type})`}
                                >
                                    {o.selection_name ?? `#${o.selection_id}`}
                                </span>
                                <span
                                    className="text-[11px] text-muted-foreground"
                                    title={`mercato Betfair ${o.market_id}`}
                                >
                                    {marketLabelOf(o)}
                                </span>
                                <span className="ml-auto font-mono tabular-nums text-xl font-bold text-primary">
                                    @{fmtOdds(o.price)}
                                </span>
                            </div>

                            {kind === 'anomaly' && (
                                <div className="mt-2 rounded-md border border-amber-500/20 bg-amber-500/5 px-2 py-1.5 text-[11px]" data-testid="anomaly-rule">
                                    <span className="uppercase tracking-wide text-[10px] text-amber-300/90">Regola</span>{' '}
                                    <span className="text-white font-semibold">{anomalyRuleLabel(o.rule)}</span>
                                    {o.gap != null && Number.isFinite(Number(o.gap)) && (o.rule === 'ou_ladder' || o.rule === 'mo_cs') && (
                                        // solo per le regole in cui gap È uno scarto relativo dalla quota
                                        // di riferimento (per 'decided' il servizio scrive back−1 / 1/lay)
                                        <span className="ml-2 text-amber-200 tabular-nums" title="distanza dalla quota di riferimento">
                                            scarto {signedPct(o.gap)}
                                        </span>
                                    )}
                                    {refLabel && (
                                        <div className="mt-0.5 font-mono tabular-nums text-amber-100" data-testid="anomaly-ref" title="quota di riferimento → quota anomala">
                                            {refLabel}
                                        </div>
                                    )}
                                </div>
                            )}

                            {kind === 'tennis' && (
                                <div className="mt-2 flex items-center gap-2 flex-wrap text-[11px]" data-testid="tennis-extra">
                                    <span className="font-mono tabular-nums text-white">
                                        {extra?.sets ? `set ${extra.sets.p1}-${extra.sets.p2}` : score}
                                        {extra?.games ? ` · game ${extra.games.p1}-${extra.games.p2}` : ''}
                                    </span>
                                    {extra?.best_of != null && (
                                        <span className="text-slate-400">al meglio di {extra.best_of}</span>
                                    )}
                                    {extra?.server && (
                                        <span className="text-slate-400" title="chi è al servizio">serve: <b className="text-slate-200">{(extra.server === 'p1' ? players?.p1 : extra.server === 'p2' ? players?.p2 : null) ?? extra.server}</b></span>
                                    )}
                                    {Number.isFinite(retire) && (
                                        <Badge
                                            variant="outline"
                                            data-testid="tennis-retire"
                                            className={`text-[10px] tabular-nums ${retire >= 0.1 ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-slate-300 border-white/10'}`}
                                            title="probabilità stimata di ritiro (match void o perso)"
                                        >
                                            ritiro {pct(retire, 0)}
                                        </Badge>
                                    )}
                                    {extra?.momentum_against && (
                                        <Badge
                                            variant="outline"
                                            data-testid="tennis-momentum"
                                            className="text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40"
                                            title="gli ultimi punti/game vanno contro la selezione proposta"
                                        >
                                            ⚠ momentum contro
                                        </Badge>
                                    )}
                                </div>
                            )}

                            {kind !== 'combo' && (
                                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
                                    {/* ANOMALIA: `p_model` NON è un modello — è il limite
                                        implicito dalla QUOTA SORELLA di riferimento
                                        (anomaly.py: p_model = 1/quota di riferimento). Chiamarlo
                                        "Modello" faceva leggere "90,1 %" come una stima del
                                        modello Poisson su un riferimento illiquido. Il valore è
                                        quello del payload, mai ricalcolato qui. */}
                                    <Cell
                                        label={kind === 'anomaly'
                                            ? (o.p_source === 'modello' ? 'Modello (prudente)' : 'Limite dal riferimento')
                                            : calibrated ? 'Modello (calibrato)' : 'Modello'}
                                        title={kind === 'anomaly'
                                            ? (o.p_source === 'modello'
                                                ? `stima del MODELLO: piu' prudente del limite implicito nella quota sorella (${anomalyRefText(o) ?? 'riferimento non dichiarato'}), quindi e' quella che conta per edge ed EV.`
                                                : `probabilità implicita nella quota SORELLA di riferimento (${anomalyRefText(o) ?? 'riferimento non dichiarato'}): non è una stima del modello Poisson. Se quella quota è poco liquida, il numero è inaffidabile.`)
                                            : calibrated ? `probabilità calibrata (${o.calibration?.family ?? 'famiglia'}${o.calibration?.n != null ? `, n=${o.calibration.n}` : ''})` : 'probabilità del modello'}
                                    >
                                        <span
                                            className={kind === 'anomaly' ? 'text-amber-200 font-bold' : 'text-white font-bold'}
                                            data-testid={kind === 'anomaly' ? 'anomaly-ref-prob' : undefined}
                                        >
                                            {pct(o.p_model)}
                                        </span>
                                        {calibrated && (
                                            <span className="ml-1 text-slate-500" data-testid="model-raw" title="probabilità grezza prima della calibrazione">
                                                grezza {pct(o.p_model_raw)}
                                            </span>
                                        )}
                                        {kind === 'anomaly' && anomalyRefText(o) && (
                                            <div className="text-[10px] text-slate-500 font-normal truncate" data-testid="anomaly-ref-source">
                                                da {anomalyRefText(o)}
                                            </div>
                                        )}
                                    </Cell>
                                    <Cell label="Implicita" title="probabilità implicita nella quota">
                                        <span className="text-slate-300">{pct(o.p_implied)}</span>
                                    </Cell>
                                    <Cell label="Edge">
                                        <span className={`font-bold ${Number(o.edge) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{signedPct(o.edge)}</span>
                                    </Cell>
                                    <Cell label="EV">
                                        <span className={`font-bold ${Number(o.ev) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{fmtNum(o.ev, 3)}</span>
                                    </Cell>
                                </div>
                            )}

                            <div className="mt-2 flex items-center gap-2">
                                <span className="text-[10px] uppercase tracking-wide text-slate-500 w-20">Confidenza</span>
                                <Progress value={Math.max(0, Math.min(100, Number(o.confidence) * 100))} className="h-1.5 flex-1" />
                                <span className="text-[11px] tabular-nums text-slate-300 w-12 text-right">{pct(o.confidence, 0)}</span>
                            </div>

                            {o.rationale && (
                                <p className="mt-2 text-[11px] text-muted-foreground italic">{o.rationale}</p>
                            )}

                            {kind === 'combo' ? (
                                <ComboBody
                                    o={o} stake={stake} minStake={minStake} maxLiability={maxLiability}
                                    mode={mode} requests={requests}
                                    disabled={stale} disabledReason={staleMsg}
                                    onPlace={(size) => onPlace(o, size)}
                                />
                            ) : (
                                <InvestAction
                                    mode={mode}
                                    side={o.side}
                                    price={Number(o.price)}
                                    sizeAvailable={o.size_available ?? null}
                                    defaultStake={stake}
                                    minStake={minStake}
                                    maxLiability={maxLiability}
                                    requests={requests}
                                    disabled={stale}
                                    disabledReason={staleMsg}
                                    onPlace={(size) => onPlace(o, size)}
                                />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default OpportunityGroup;
