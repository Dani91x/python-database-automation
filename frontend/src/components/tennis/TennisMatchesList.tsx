// ============================================================================
// TennisMatchesList — "Partite del Giorno" del Tennis (Screen 2).
//
// Adattamento fedele di dashboard/MatchesList.tsx (calcio) al tennis. STESSO
// design system (dark, verde primary, oro secondary, glass-card, accordion
// controllato, stagger framer-motion) ma su DATI ESCLUSIVAMENTE tennis: legge
// solo da '@/lib/tennis' (get_tennis_fixtures). Nessun dato calcio, nessuna
// watchlist calcio — i preferiti tennis sono self-contained in localStorage.
//
// Le celle prezzo back/lay riprendono il pattern di dashboard/BetfairOddsPanel
// (back = sky, lay = rose, prezzo mono bold, size €k-abbrev).
// ============================================================================
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { format, addDays, startOfToday } from 'date-fns';
import { Star, Trophy, Clock, Activity, ArrowRight } from 'lucide-react';
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    fetchTennisFixtures,
    TennisFixtureRow,
    TennisMoneylineRunner,
    TennisOddLevel,
} from '@/lib/tennis';

// ----------------------------------------------------------------------------
// Preferiti tennis: Set di event_id persistito in localStorage. Self-contained
// (nessun backend, nessuna watchlist calcio). Robusto a JSON corrotto/SSR.
// ----------------------------------------------------------------------------
const FAV_KEY = 'tennis.favorites';

function readFavorites(): Set<string> {
    if (typeof window === 'undefined') return new Set();
    try {
        const raw = window.localStorage.getItem(FAV_KEY);
        if (!raw) return new Set();
        const arr = JSON.parse(raw);
        return new Set(Array.isArray(arr) ? arr.map(String) : []);
    } catch {
        return new Set();
    }
}

function writeFavorites(favs: Set<string>) {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(FAV_KEY, JSON.stringify(Array.from(favs)));
    } catch {
        /* quota / private mode: ignora, i preferiti restano solo in memoria */
    }
}

// ----------------------------------------------------------------------------
// Format helpers
// ----------------------------------------------------------------------------
/** Prezzo a 2 decimali; "—" se assente. */
const fmtPrice = (p?: number | null): string =>
    p == null || !Number.isFinite(p) ? '—' : p.toFixed(2);

/** Size in € con abbreviazione k oltre 1000. */
const fmtSize = (s?: number | null): string => {
    if (s == null || !Number.isFinite(s)) return '';
    return s >= 1000 ? `€${(s / 1000).toFixed(1)}k` : `€${Math.round(s)}`;
};

/** Volume matchato in € con k-abbrev; "—" se nullo. */
const fmtMatched = (m?: number | null): string => {
    if (m == null || !Number.isFinite(m)) return '—';
    return m >= 1000 ? `€${(m / 1000).toFixed(1)}k` : `€${Math.round(m)}`;
};

/** Orario d'inizio it-IT HH:mm; "--:--" se non parsabile. */
const fmtTime = (iso?: string | null): string => {
    if (!iso) return '--:--';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '--:--';
    return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
};

const best = (levels?: TennisOddLevel[] | null): TennisOddLevel | undefined =>
    Array.isArray(levels) && levels.length > 0 ? levels[0] : undefined;

// ----------------------------------------------------------------------------
// PriceCell — cella prezzo stile Betfair (back = sky, lay = rose).
// Riprende dashboard/BetfairOddsPanel: prezzo mono bold + size €k sotto.
// ----------------------------------------------------------------------------
function PriceCell({ lvl, kind }: { lvl?: TennisOddLevel; kind: 'back' | 'lay' }) {
    const base =
        'w-[54px] h-11 rounded flex flex-col items-center justify-center border shrink-0';
    if (!lvl || lvl.price == null || !Number.isFinite(lvl.price)) {
        return (
            <div className={cn(base, 'bg-white/[0.02] border-white/5 text-white/25')}>
                <span className="text-xs font-mono font-bold leading-none">—</span>
            </div>
        );
    }
    const cls =
        kind === 'back'
            ? 'bg-sky-500/15 border-sky-500/30 text-sky-300'
            : 'bg-rose-500/15 border-rose-500/30 text-rose-300';
    return (
        <div className={cn(base, cls)}>
            <span className="text-xs font-mono font-bold leading-none">{fmtPrice(lvl.price)}</span>
            {lvl.size != null && Number.isFinite(lvl.size) && (
                <span className="text-[8px] text-white/40 leading-none mt-0.5">{fmtSize(lvl.size)}</span>
            )}
        </div>
    );
}

/** Coppia back/lay del miglior livello per un giocatore. */
function PlayerOdds({ runner }: { runner?: TennisMoneylineRunner }) {
    return (
        <div className="flex items-center gap-1">
            <PriceCell lvl={best(runner?.back)} kind="back" />
            <PriceCell lvl={best(runner?.lay)} kind="lay" />
        </div>
    );
}

// ----------------------------------------------------------------------------
// Selettore data (Ieri / Oggi / Domani)
// ----------------------------------------------------------------------------
type DayOffset = -1 | 0 | 1;
const DAY_TABS: { off: DayOffset; label: string }[] = [
    { off: -1, label: 'Ieri' },
    { off: 0, label: 'Oggi' },
    { off: 1, label: 'Domani' },
];

interface TennisGroup {
    competition_id: string | null;
    competition_name: string;
    competition_region: string | null;
    matches: TennisFixtureRow[];
}

export function TennisMatchesList() {
    const navigate = useNavigate();

    const [dayOffset, setDayOffset] = useState<DayOffset>(0);
    const [rows, setRows] = useState<TennisFixtureRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Accordion CONTROLLATO (come MatchesList: defaultValue si applica solo al mount).
    const [openItems, setOpenItems] = useState<string[]>([]);

    // Preferiti tennis (localStorage).
    const [favorites, setFavorites] = useState<Set<string>>(() => readFavorites());

    const toggleFavorite = useCallback((eventId: string) => {
        setFavorites((prev) => {
            const next = new Set(prev);
            if (next.has(eventId)) next.delete(eventId);
            else next.add(eventId);
            writeFavorites(next);
            return next;
        });
    }, []);

    // Data selezionata (default oggi, fuso locale) -> stringa yyyy-MM-dd per la RPC.
    const selectedDate = useMemo(() => addDays(startOfToday(), dayOffset), [dayOffset]);
    const dateKey = useMemo(() => format(selectedDate, 'yyyy-MM-dd'), [selectedDate]);
    const dateLabel = useMemo(
        () => selectedDate.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }),
        [selectedDate],
    );

    useEffect(() => {
        let active = true;
        setLoading(true);
        setError(null);
        fetchTennisFixtures(dateKey)
            .then((data) => {
                if (!active) return;
                setRows(Array.isArray(data) ? data : []);
            })
            .catch((e: unknown) => {
                if (!active) return;
                setError(e instanceof Error ? e.message : 'Errore di caricamento');
                setRows([]);
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, [dateKey]);

    // Raggruppa per competition_name; gruppi ordinati alfabeticamente; dentro il
    // gruppo per open_date asc.
    const groups = useMemo<TennisGroup[]>(() => {
        const map = new Map<string, TennisGroup>();
        for (const r of rows) {
            const name = r.competition_name || 'Altri tornei';
            const key = `${r.competition_id ?? ''}::${name}`;
            let g = map.get(key);
            if (!g) {
                g = {
                    competition_id: r.competition_id ?? null,
                    competition_name: name,
                    competition_region: r.competition_region ?? null,
                    matches: [],
                };
                map.set(key, g);
            }
            g.matches.push(r);
        }
        const out = Array.from(map.values());
        out.sort((a, b) => a.competition_name.localeCompare(b.competition_name, 'it'));
        for (const g of out) {
            g.matches.sort((a, b) => {
                const ta = new Date(a.open_date).getTime();
                const tb = new Date(b.open_date).getTime();
                return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb);
            });
        }
        return out;
    }, [rows]);

    // Chiave item accordion, stabile: `${competition_id ?? name}-${i}`.
    const itemValue = useCallback(
        (g: TennisGroup, i: number) => `${g.competition_id ?? g.competition_name}-${i}`,
        [],
    );

    // Al cambio dati, apri il primo gruppo per dare feedback immediato.
    useEffect(() => {
        setOpenItems(groups.length > 0 ? [itemValue(groups[0], 0)] : []);
    }, [groups, itemValue]);

    return (
        <div className="space-y-4 md:space-y-6 max-w-5xl mx-auto px-4">
            {/* Header */}
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6 md:mb-8">
                <div>
                    <h1 className="text-2xl md:text-4xl font-display font-black text-white">
                        Partite del Giorno <span className="text-primary">.</span>
                    </h1>
                    <p className="text-muted-foreground text-sm mt-1 capitalize">
                        Tennis · {dateLabel}
                    </p>
                </div>

                <div className="flex items-center gap-3 w-full md:w-auto">
                    {/* Selettore data */}
                    <div className="flex items-center gap-1 p-1 rounded-xl bg-black/40 border border-white/10">
                        {DAY_TABS.map((t) => (
                            <button
                                key={t.off}
                                onClick={() => setDayOffset(t.off)}
                                className={cn(
                                    'px-3 py-1.5 rounded-lg text-xs font-bold transition-colors',
                                    dayOffset === t.off
                                        ? 'bg-primary/20 text-primary'
                                        : 'text-white/50 hover:bg-white/5 hover:text-white',
                                )}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>

                    <div className="text-xs font-bold text-muted-foreground bg-white/5 px-3 py-2 rounded-lg border border-white/5 whitespace-nowrap hidden md:block">
                        {rows.length} Match
                    </div>
                </div>
            </div>

            {/* Loading: skeleton rows */}
            {loading ? (
                <div className="space-y-4">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="glass-card rounded-xl border border-white/5 p-4 md:p-6">
                            <div className="flex items-center gap-4 mb-4">
                                <Skeleton className="w-10 h-10 rounded-lg" />
                                <div className="flex flex-col gap-2">
                                    <Skeleton className="h-4 w-40" />
                                    <Skeleton className="h-3 w-20" />
                                </div>
                            </div>
                            <div className="space-y-3">
                                {Array.from({ length: 2 }).map((__, j) => (
                                    <div
                                        key={j}
                                        className="p-3 md:p-4 rounded-lg bg-white/5 border border-white/5 flex items-center gap-4"
                                    >
                                        <Skeleton className="w-5 h-5 rounded" />
                                        <Skeleton className="w-12 h-12 rounded-lg" />
                                        <Skeleton className="h-5 flex-1" />
                                        <Skeleton className="h-11 w-28 rounded" />
                                        <Skeleton className="h-9 w-28 rounded-lg" />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            ) : error ? (
                // Errore inline
                <div className="glass-card rounded-2xl border border-red-500/30 bg-red-500/5 px-4 py-8 text-center max-w-2xl mx-auto">
                    <Activity className="w-10 h-10 text-red-400 mx-auto mb-3" />
                    <h2 className="text-lg font-bold font-display text-white mb-1">Errore di caricamento</h2>
                    <p className="text-red-400/90 text-sm font-mono break-words">{error}</p>
                </div>
            ) : groups.length === 0 ? (
                // Empty state
                <div className="text-center py-12 md:py-20 glass-card rounded-2xl p-6 md:p-8 max-w-2xl mx-auto">
                    <Trophy className="w-12 h-12 md:w-16 md:h-16 text-muted-foreground mx-auto mb-4 opacity-50" />
                    <h2 className="text-xl md:text-2xl font-bold font-display text-white mb-2">
                        Nessun match di tennis
                    </h2>
                    <p className="text-muted-foreground text-sm md:text-base">
                        Non ci sono partite di tennis per {DAY_TABS.find((t) => t.off === dayOffset)?.label.toLowerCase()}.
                        Prova un altro giorno.
                    </p>
                </div>
            ) : (
                <Accordion
                    type="multiple"
                    className="space-y-4"
                    value={openItems}
                    onValueChange={setOpenItems}
                >
                    <AnimatePresence>
                        {groups.map((group, groupIndex) => {
                            const value = itemValue(group, groupIndex);
                            const count = group.matches.length;
                            return (
                                <motion.div
                                    key={value}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: groupIndex * 0.05 }}
                                >
                                    <AccordionItem value={value} className="border-none">
                                        <AccordionTrigger className="glass-card hover:no-underline px-4 md:px-6 py-4 rounded-xl border border-white/5 hover:border-primary/20 transition-all [&[data-state=open]]:rounded-b-none [&[data-state=open]]:border-primary/30">
                                            <div className="flex items-center gap-3 md:gap-4 text-left">
                                                <div className="w-8 h-8 md:w-10 md:h-10 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center flex-shrink-0">
                                                    <Trophy className="w-4 h-4 md:w-5 md:h-5 text-primary/60" />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="text-sm md:text-base font-bold text-white line-clamp-1">
                                                        {group.competition_name}
                                                    </span>
                                                    <span className="text-[10px] md:text-xs text-muted-foreground font-medium uppercase tracking-tight">
                                                        {group.competition_region ? `${group.competition_region} · ` : ''}
                                                        {count} {count === 1 ? 'partita' : 'partite'}
                                                    </span>
                                                </div>
                                                <Badge
                                                    variant="secondary"
                                                    className="ml-auto bg-primary/10 text-primary border-primary/20 font-bold"
                                                >
                                                    {count}
                                                </Badge>
                                            </div>
                                        </AccordionTrigger>
                                        <AccordionContent className="glass-card rounded-t-none rounded-b-xl border-x border-b border-white/5 bg-white/[0.02] p-2 md:p-4">
                                            <div className="space-y-3">
                                                {group.matches.map((m) => {
                                                    const p1 = m.player1;
                                                    const p2 = m.player2;
                                                    const isFav = favorites.has(m.event_id);
                                                    return (
                                                        <div
                                                            key={`${m.event_id}-${m.market_id}`}
                                                            className="p-3 md:p-4 rounded-lg bg-white/5 border border-white/5 hover:bg-white/10 transition-colors"
                                                        >
                                                            <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-3 lg:gap-4">
                                                                {/* Star + time + status (top row on mobile) */}
                                                                <div className="flex items-center gap-3 shrink-0">
                                                                    <button
                                                                        type="button"
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            toggleFavorite(m.event_id);
                                                                        }}
                                                                        aria-label={
                                                                            isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'
                                                                        }
                                                                        aria-pressed={isFav}
                                                                        title={isFav ? 'Preferito' : 'Aggiungi ai preferiti'}
                                                                        className="shrink-0 p-1 rounded-md hover:bg-white/10 transition-colors"
                                                                    >
                                                                        <Star
                                                                            className={cn(
                                                                                'w-5 h-5 transition-colors',
                                                                                isFav
                                                                                    ? 'text-amber-300 fill-amber-300'
                                                                                    : 'text-muted-foreground',
                                                                            )}
                                                                        />
                                                                    </button>

                                                                    <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-black/40 border border-white/10 flex-shrink-0 gap-0.5 flex-col">
                                                                        <Clock className="w-3 h-3 text-primary/60" />
                                                                        <span className="text-[11px] font-bold text-white leading-none">
                                                                            {fmtTime(m.open_date)}
                                                                        </span>
                                                                    </div>

                                                                    <StatusBadge inplay={m.inplay} />
                                                                </div>

                                                                {/* Players + moneyline */}
                                                                <div className="flex-1 flex items-center justify-center gap-2 md:gap-4 min-w-0">
                                                                    {/* P1 (right-aligned) */}
                                                                    <div className="flex-1 flex items-center justify-end gap-2 md:gap-3 min-w-0">
                                                                        <span className="text-sm md:text-base font-bold text-white text-right truncate">
                                                                            {p1?.name || 'Giocatore 1'}
                                                                        </span>
                                                                        <PlayerOdds runner={p1} />
                                                                    </div>

                                                                    <div className="text-muted-foreground font-display font-black text-xs md:text-sm shrink-0">
                                                                        VS
                                                                    </div>

                                                                    {/* P2 (left-aligned) */}
                                                                    <div className="flex-1 flex items-center justify-start gap-2 md:gap-3 min-w-0">
                                                                        <PlayerOdds runner={p2} />
                                                                        <span className="text-sm md:text-base font-bold text-white text-left truncate">
                                                                            {p2?.name || 'Giocatore 2'}
                                                                        </span>
                                                                    </div>
                                                                </div>

                                                                {/* Volume + APRI TERMINAL */}
                                                                <div className="flex items-center justify-between lg:justify-end gap-3 shrink-0">
                                                                    <div className="flex flex-col items-end">
                                                                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground leading-none">
                                                                            Volume
                                                                        </span>
                                                                        <span className="text-sm font-bold font-mono text-amber-300 leading-tight">
                                                                            {fmtMatched(m.total_matched)}
                                                                        </span>
                                                                    </div>
                                                                    <Button
                                                                        size="sm"
                                                                        onClick={() =>
                                                                            navigate(
                                                                                `/tennis/terminal?event=${m.event_id}&market=${m.market_id}&name=Match%20Odds&p1=${encodeURIComponent(
                                                                                    p1?.name ?? '',
                                                                                )}&p2=${encodeURIComponent(p2?.name ?? '')}`,
                                                                            )
                                                                        }
                                                                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90 h-9 md:h-10 px-3 md:px-4"
                                                                    >
                                                                        <span className="hidden sm:inline">APRI TERMINAL</span>
                                                                        <ArrowRight className="w-4 h-4 sm:ml-2" />
                                                                    </Button>
                                                                </div>
                                                            </div>

                                                            {/* Sotto-riga: mercati + ids */}
                                                            <div className="mt-2 pt-2 border-t border-white/5 flex items-center gap-3 flex-wrap">
                                                                <span className="text-[10px] text-muted-foreground font-medium">
                                                                    {(m.markets?.length ?? 0)} mercati
                                                                </span>
                                                                <span className="text-[10px] font-mono text-muted-foreground">
                                                                    evt {m.event_id}
                                                                </span>
                                                                <span className="text-[10px] font-mono text-muted-foreground">
                                                                    mkt {m.market_id}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </Accordion>
            )}
        </div>
    );
}

/** Badge stato: IN CORSO (verde, pulse) se inplay, altrimenti PRE-MATCH (muted). */
function StatusBadge({ inplay }: { inplay: boolean }) {
    if (inplay) {
        return (
            <span className="inline-flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 whitespace-nowrap">
                <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
                </span>
                IN CORSO
            </span>
        );
    }
    return (
        <span className="inline-flex items-center text-[10px] font-bold px-2 py-1 rounded-md bg-white/5 text-muted-foreground border border-white/10 whitespace-nowrap">
            PRE-MATCH
        </span>
    );
}
