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
    anomalyRefLabel, comboLegStakes, comboLock, oppKind, oppScore,
    type SafeMode, type SafeOppKind, type SafeOpportunity, type SafeOpportunityRow, type SafeRequest,
} from '@/lib/safeBot';
import { sideBadgeClass } from './variantStyles';

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
    requests: SafeRequest[];
    minConfidence: number;
    sideFilter: 'all' | 'back' | 'lay';
    kindFilter?: OppKindFilter;
    /** timestamp corrente (dal chiamante) per l'eta' della riga */
    nowMs?: number;
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
function ComboBody({ o, stake, minStake, mode, requests, disabled, disabledReason, onPlace }: {
    o: SafeOpportunity; stake: number; minStake?: number; mode: SafeMode; requests: SafeRequest[];
    disabled: boolean; disabledReason?: string;
    onPlace: (size: number) => Promise<number | null>;
}) {
    // lo stake totale scelto nell'InvestAction non e' osservabile dall'esterno:
    // lo si specchia qui per scalare le gambe e il lock in tempo reale
    const [total, setTotal] = useState<number>(stake);
    const legs = useMemo(() => comboLegStakes(o, total), [o, total]);
    const lock = comboLock(o, total);
    // abbinabile della combinazione = gamba piu' stretta (in proporzione allo stake)
    const minAvail = legs.reduce<number | null>((acc, l) => {
        const a = Number(l.size_available);
        if (!Number.isFinite(a)) return acc;
        return acc == null ? a : Math.min(acc, a);
    }, null);
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
                        <span className="text-slate-500">{l.market_type}</span>
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
                minStake={minStake}
                requests={requests}
                disabled={disabled || legs.length === 0}
                disabledReason={legs.length === 0 ? 'combinazione senza gambe' : disabledReason}
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
    row, mode, stake, minStake, requests, minConfidence, sideFilter, kindFilter = 'all', nowMs,
    onPlace, players,
}: OpportunityGroupProps) {
    const p = row.payload ?? { opps: [] };
    const opps = filterOpps(row, minConfidence, sideFilter, kindFilter);

    if (opps.length === 0) return null;

    const now = nowMs ?? Date.now();
    const rowMs = row.updated_at ? Date.parse(row.updated_at) : NaN;
    const ageSec = Number.isFinite(rowMs) ? Math.max(0, Math.round((now - rowMs) / 1000)) : null;
    const stale = ageSec != null && ageSec * 1000 > OPP_ROW_STALE_MS;
    const staleMsg = stale ? `quote non aggiornate (${ageSec}s)` : undefined;

    const isTennis = row.sport === 'tennis';
    const score = isTennis
        ? (p.sets ? `set ${p.sets.p1}-${p.sets.p2}${p.games ? ` · game ${p.games.p1}-${p.games.p2}` : ''}` : 'set —')
        : (p.score_home != null && p.score_away != null ? `${p.score_home}-${p.score_away}` : '?-?');
    const lam = p.lambdas
        ? `λ ${fmtNum(p.lambdas.home ?? 0, 2)} / ${fmtNum(p.lambdas.away ?? 0, 2)}`
        : null;

    return (
        <div className="glass-card rounded-xl border border-white/10 p-4" data-testid="opp-group">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-display font-black text-base text-white truncate max-w-[280px]">
                    {p.event_name ?? row.event_id}
                </span>
                <span className="font-mono tabular-nums text-xs text-muted-foreground">
                    {isTennis ? score : `${p.minute != null ? `${p.minute}′` : '—′'} · ${score}`}
                </span>
                {lam && (
                    <Badge variant="outline" className="text-[10px] bg-white/5 text-muted-foreground border-white/10 font-mono">
                        {lam}
                    </Badge>
                )}
                {p.source && (
                    <Badge variant="outline" className="text-[10px] bg-white/5 text-muted-foreground border-white/10">
                        {p.source}
                    </Badge>
                )}
                {ageSec != null && (
                    <Badge
                        variant="outline"
                        data-testid="opp-age"
                        className={`text-[10px] font-mono tabular-nums ${stale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-muted-foreground border-white/10'}`}
                        title={staleMsg ?? 'eta’ dell’ultimo calcolo del modello'}
                    >
                        {ageSec}s fa
                    </Badge>
                )}
                <Badge variant="outline" className="ml-auto text-[10px] bg-secondary/15 text-secondary border-secondary/40 font-mono tabular-nums">
                    {opps.length} opp.
                </Badge>
            </div>

            {stale && (
                // M-21: la riga resta elencata come "attuale" per mezz'ora, ma
                // "Piazza" si spegne a 60 s: il motivo va DETTO, non subito
                <p className="mt-2 text-[11px] text-red-300" data-testid="opp-stale-note">
                    modello e quote non aggiornati da {ageSec}s: il bottone Piazza resta spento finché
                    il servizio non ricalcola (un'opportunità vale solo sul prezzo di adesso).
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
                                    {o.market_name ?? o.market_type}{o.line != null ? ` ${fmtNum(o.line, 1)}` : ''}
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
                                    <Cell label={calibrated ? 'Modello (calibrato)' : 'Modello'} title={calibrated ? `probabilità calibrata (${o.calibration?.family ?? 'famiglia'}${o.calibration?.n != null ? `, n=${o.calibration.n}` : ''})` : 'probabilità del modello'}>
                                        <span className="text-white font-bold">{pct(o.p_model)}</span>
                                        {calibrated && (
                                            <span className="ml-1 text-slate-500" data-testid="model-raw" title="probabilità grezza prima della calibrazione">
                                                grezza {pct(o.p_model_raw)}
                                            </span>
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
                                    o={o} stake={stake} minStake={minStake} mode={mode} requests={requests}
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
