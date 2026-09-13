// ============================================================================
// ActivityFeed.tsx — lista UNICA delle attività del servizio.
//
// Prima: Omega aveva una lista con badge, Mike una con colonne a larghezza
// fissa e nessun filtro, Safe non aveva niente. Qui: ora di Roma, badge del
// kind in italiano (activityMeta), testo della riga calcolato dal chiamante
// (ogni bot ha payload suoi), righe CRITICHE in rosso, filtro per evento
// opzionale, scroll con altezza massima.
//
// CERT. 13/09 — due cose che mancavano e che l'utente ha chiesto:
//   · MODALITÀ della riga (PAPER / LIVE): il servizio la scrive in
//     `payload.mode` su ogni riga, e senza mostrarla la stessa lista mescolava
//     decisioni prese con soldi veri e decisioni simulate;
//   · filtro per TIPO di riga (`kind`) con un chip rapido: prima l'unico filtro
//     era per evento e gli `skip` (le righe che rispondono a «perché BASE non
//     entra?») erano in tono MUTED e sparivano col toggle «solo da guardare»,
//     cioè la domanda più frequente del trader non aveva risposta raggiungibile.
// ============================================================================
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { ModeBadge } from '@/components/trading/ModeBadge';
import { fmtTime } from '@/lib/format';
import { activityMeta as baseActivityMeta, activityLineGeneric, T, type ActivityMeta } from '@/lib/tradeStatus';

export interface ActivityRow {
    id: number | string;
    ts: string | null;
    kind: string;
    /** nome dell'evento, per il filtro e il prefisso della riga */
    event_name?: string | null;
    /** testo già composto dal chiamante; se assente si usa `payload` */
    line?: string | null;
    payload?: Record<string, unknown> | null;
    /** modalità della riga; se assente si legge da `payload.mode` */
    mode?: string | null;
}

/** modalità dichiarata dalla riga (colonna o payload). null = non dichiarata. */
export function rowMode(r: ActivityRow): string | null {
    const direct = r.mode != null ? String(r.mode).trim() : '';
    if (direct) return direct.toLowerCase();
    const p = r.payload ?? {};
    const fromPayload = p['mode'] != null ? String(p['mode']).trim() : '';
    return fromPayload ? fromPayload.toLowerCase() : null;
}

/**
 * Certificazione 12/09 — l'ora dell'attività ha i SECONDI in tutte e tre le
 * sezioni. Prima `timeSeconds` era opt-in: Safe e Mike lo passavano, Omega no,
 * e la stessa lista mostrava «10:55» in una pagina e «10:55:45» nelle altre.
 * Su righe che arrivano a raffica (cinque «FEED CIECO» nello stesso minuto) il
 * minuto secco non permette nemmeno di dire quale è venuta prima.
 */
export function ActivityFeed({
    rows, metaOf, lineOf, filterable = false, kindFilterable = false, quickKinds,
    quickKindsLabel = 'solo NON ENTRATO', currentMode, maxHeightCls = 'max-h-72',
    emptyText = T.noActivityToday, testId = 'activity-feed', rowTestId = 'activity-row',
    timeSeconds = true,
}: {
    rows: ActivityRow[];
    /** mappa kind → etichetta della sezione (default: quella condivisa) */
    metaOf?: (kind: string) => ActivityMeta;
    /** testo della riga (default: activityLineGeneric sul payload) */
    lineOf?: (row: ActivityRow) => string;
    /** mostra i bottoni di filtro per evento */
    filterable?: boolean;
    /** mostra i bottoni di filtro per TIPO di riga (kind) */
    kindFilterable?: boolean;
    /** kind del chip rapido (es. gli `skip`: «perché NON è entrato») */
    quickKinds?: readonly string[];
    /** etichetta del chip rapido */
    quickKindsLabel?: string;
    /** modalità attiva sul servizio: le righe di un'altra modalità sono attenuate */
    currentMode?: string | null;
    maxHeightCls?: string;
    emptyText?: string;
    testId?: string;
    rowTestId?: string;
    timeSeconds?: boolean;
}) {
    const [event, setEvent] = useState<string>('all');
    const [kind, setKind] = useState<string>('all');
    const events = useMemo(() => {
        const s = new Set<string>();
        for (const r of rows) if (r.event_name) s.add(r.event_name);
        return [...s].sort();
    }, [rows]);
    const metaFor = useMemo(
        () => (k: string) => (metaOf ? metaOf(String(k)) : baseActivityMeta(String(k))),
        [metaOf],
    );
    // tipi PRESENTI nella lista, con quanti ce ne sono: un filtro che mostra
    // tipi inesistenti è rumore, e un tipo presente ma non filtrabile è un buco
    const kinds = useMemo(() => {
        const n = new Map<string, number>();
        for (const r of rows) {
            const k = String(r.kind);
            n.set(k, (n.get(k) ?? 0) + 1);
        }
        return [...n.entries()]
            .map(([k, count]) => ({ kind: k, count, label: metaFor(k).label }))
            .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
    }, [rows, metaFor]);
    // chip rapido: i kind richiesti dal chiamante e DAVVERO presenti
    const quickSet = useMemo(() => {
        const want = new Set((quickKinds ?? []).map((k) => String(k)));
        return new Set(kinds.filter((k) => want.has(k.kind)).map((k) => k.kind));
    }, [quickKinds, kinds]);
    const quickCount = useMemo(
        () => rows.filter((r) => quickSet.has(String(r.kind))).length,
        [rows, quickSet],
    );
    const shown = useMemo(
        () => rows.filter((r) => {
            if (event !== 'all' && r.event_name !== event) return false;
            if (kind === 'all') return true;
            if (kind === '__quick__') return quickSet.has(String(r.kind));
            return String(r.kind) === kind;
        }),
        [rows, event, kind, quickSet],
    );

    if (rows.length === 0) {
        return (
            <div className="px-5 py-6 text-center text-sm text-muted-foreground" data-testid={testId} data-empty="1">
                {emptyText}
            </div>
        );
    }

    const filterLabel = kind === '__quick__'
        ? quickKindsLabel
        : kind !== 'all'
            ? metaFor(kind).label
            : event !== 'all' ? event : null;

    return (
        <div data-testid={testId}>
            {filterable && events.length > 1 && (
                <div className="px-4 py-2 flex items-center gap-1.5 flex-wrap text-[11px] border-b border-white/5" data-testid="activity-filter">
                    <span className="text-muted-foreground uppercase tracking-wide">Evento</span>
                    <button
                        type="button"
                        onClick={() => setEvent('all')}
                        aria-pressed={event === 'all'}
                        className={`px-2 py-0.5 rounded-full border tabular-nums ${event === 'all' ? 'bg-white/15 text-white border-white/30' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                    >tutti {rows.length}</button>
                    {events.map((e) => (
                        <button
                            key={e}
                            type="button"
                            onClick={() => setEvent(e)}
                            aria-pressed={event === e}
                            className={`px-2 py-0.5 rounded-full border ${event === e ? 'bg-primary/20 text-primary border-primary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >{e}</button>
                    ))}
                </div>
            )}
            {kindFilterable && kinds.length > 1 && (
                <div className="px-4 py-2 flex items-center gap-1.5 flex-wrap text-[11px] border-b border-white/5" data-testid="activity-kind-filter">
                    <span className="text-muted-foreground uppercase tracking-wide">Tipo</span>
                    <button
                        type="button"
                        onClick={() => setKind('all')}
                        aria-pressed={kind === 'all'}
                        className={`px-2 py-0.5 rounded-full border tabular-nums ${kind === 'all' ? 'bg-white/15 text-white border-white/30' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                    >tutti {rows.length}</button>
                    {quickCount > 0 && (
                        // chip RAPIDO: risponde alla domanda «perché base non
                        // entra?» in un click, senza cercare il tipo giusto
                        <button
                            type="button"
                            data-testid="activity-kind-quick"
                            onClick={() => setKind('__quick__')}
                            aria-pressed={kind === '__quick__'}
                            title="solo le righe in cui il servizio ha deciso di NON entrare, col motivo"
                            className={`px-2 py-0.5 rounded-full border tabular-nums font-heading ${kind === '__quick__' ? 'bg-amber-500/20 text-amber-200 border-amber-500/50' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >{quickKindsLabel} {quickCount}</button>
                    )}
                    {kinds.map((k) => (
                        <button
                            key={k.kind}
                            type="button"
                            data-testid="activity-kind-option"
                            data-kind={k.kind}
                            onClick={() => setKind(k.kind)}
                            aria-pressed={kind === k.kind}
                            className={`px-2 py-0.5 rounded-full border tabular-nums ${kind === k.kind ? 'bg-primary/20 text-primary border-primary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >{k.label} {k.count}</button>
                    ))}
                </div>
            )}
            {shown.length === 0 && (
                <div className="px-5 py-6 text-center text-sm text-muted-foreground" data-testid="activity-filtered-empty">
                    nessuna attività per «{filterLabel ?? 'i filtri scelti'}» — premi «tutti» per rivedere l’intera lista
                </div>
            )}
            <ul className={`divide-y divide-white/5 ${maxHeightCls} overflow-y-auto`}>
                {shown.map((r) => {
                    const m = metaFor(String(r.kind));
                    const line = lineOf
                        ? lineOf(r)
                        : (r.line ?? activityLineGeneric({ event_name: r.event_name, ...(r.payload ?? {}) }));
                    const mode = rowMode(r);
                    // riga di un'ALTRA modalità rispetto a quella attiva sul
                    // servizio: resta (è successa davvero) ma in tono attenuato
                    const other = currentMode != null && mode != null && mode !== String(currentMode).toLowerCase();
                    return (
                        <li
                            key={r.id}
                            className={`px-4 py-1.5 flex items-center gap-2 text-[12px] ${m.critical ? 'bg-red-500/5' : ''} ${other ? 'opacity-60' : ''}`}
                            data-testid={rowTestId}
                            data-kind={r.kind}
                            data-mode={mode ?? undefined}
                            data-other-mode={other ? '1' : undefined}
                            data-critical={m.critical ? '1' : undefined}
                        >
                            <span className={`text-slate-500 tabular-nums shrink-0 ${timeSeconds ? 'w-16' : 'w-12'}`}>{fmtTime(r.ts, { seconds: timeSeconds })}</span>
                            <Badge variant="outline" className={`px-1.5 py-0 text-[10px] whitespace-nowrap ${m.cls}`}>{m.label}</Badge>
                            {/* il servizio scrive `payload.mode` su ogni riga: le righe
                                vecchie (prima della correzione) non ce l'hanno e non si
                                inventa un PAPER che nessuno ha dichiarato. */}
                            {mode && (
                                <ModeBadge
                                    mode={mode}
                                    compact
                                    testId="activity-mode"
                                    dimmed={other}
                                    title={other ? `il servizio è in ${String(currentMode).toUpperCase()}` : undefined}
                                />
                            )}
                            <span className={`truncate ${m.critical ? 'text-red-300 font-semibold' : 'text-slate-200'}`} title={line}>
                                {line || '—'}
                            </span>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
}

export default ActivityFeed;
