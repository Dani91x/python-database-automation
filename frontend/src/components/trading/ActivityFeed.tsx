// ============================================================================
// ActivityFeed.tsx — lista UNICA delle attività del servizio.
//
// Prima: Omega aveva una lista con badge, Mike una con colonne a larghezza
// fissa e nessun filtro, Safe non aveva niente. Qui: ora di Roma, badge del
// kind in italiano (activityMeta), testo della riga calcolato dal chiamante
// (ogni bot ha payload suoi), righe CRITICHE in rosso, filtro per evento
// opzionale, scroll con altezza massima.
// ============================================================================
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
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
}

export function ActivityFeed({
    rows, metaOf, lineOf, filterable = false, maxHeightCls = 'max-h-72',
    emptyText = T.noActivityToday, testId = 'activity-feed', rowTestId = 'activity-row',
    timeSeconds = false,
}: {
    rows: ActivityRow[];
    /** mappa kind → etichetta della sezione (default: quella condivisa) */
    metaOf?: (kind: string) => ActivityMeta;
    /** testo della riga (default: activityLineGeneric sul payload) */
    lineOf?: (row: ActivityRow) => string;
    /** mostra i bottoni di filtro per evento */
    filterable?: boolean;
    maxHeightCls?: string;
    emptyText?: string;
    testId?: string;
    rowTestId?: string;
    timeSeconds?: boolean;
}) {
    const [event, setEvent] = useState<string>('all');
    const events = useMemo(() => {
        const s = new Set<string>();
        for (const r of rows) if (r.event_name) s.add(r.event_name);
        return [...s].sort();
    }, [rows]);
    const shown = useMemo(
        () => (event === 'all' ? rows : rows.filter((r) => r.event_name === event)),
        [rows, event],
    );

    if (rows.length === 0) {
        return (
            <div className="px-5 py-6 text-center text-sm text-muted-foreground" data-testid={testId} data-empty="1">
                {emptyText}
            </div>
        );
    }

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
            <ul className={`divide-y divide-white/5 ${maxHeightCls} overflow-y-auto`}>
                {shown.map((r) => {
                    const m = metaOf ? metaOf(String(r.kind)) : baseActivityMeta(r.kind);
                    const line = lineOf
                        ? lineOf(r)
                        : (r.line ?? activityLineGeneric({ event_name: r.event_name, ...(r.payload ?? {}) }));
                    return (
                        <li
                            key={r.id}
                            className={`px-4 py-1.5 flex items-center gap-2 text-[12px] ${m.critical ? 'bg-red-500/5' : ''}`}
                            data-testid={rowTestId}
                            data-kind={r.kind}
                            data-critical={m.critical ? '1' : undefined}
                        >
                            <span className={`text-slate-500 tabular-nums shrink-0 ${timeSeconds ? 'w-16' : 'w-12'}`}>{fmtTime(r.ts, { seconds: timeSeconds })}</span>
                            <Badge variant="outline" className={`px-1.5 py-0 text-[10px] whitespace-nowrap ${m.cls}`}>{m.label}</Badge>
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
