// ============================================================================
// MultiLadder — workspace MULTI-LADDER libero (B19): N ladder affiancati anche di
// MERCATI/EVENTI/SPORT diversi, layout persistito (lib/multiLadder). Ogni slot è
// uno StandaloneLadder autosufficiente (modalità ordini risolta per-evento,
// fail-safe OFF). Slot aggiungibili qui (picker eventi calcio seguiti) o dai
// terminal con il bottone "aggiungi al Multi-ladder" (LadderView multiSlot).
// ============================================================================
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { Card } from '@/components/ui/card';
import { Layers, Plus, X, ArrowLeft, Loader2 } from 'lucide-react';
import {
    loadSlots, saveSlots, addSlot, removeSlot, MAX_SLOTS, type LadderSlot,
} from '@/lib/multiLadder';
import {
    fetchLiveFollows, fetchLiveNow,
    type LiveFollow, type LiveNowMarket,
} from '@/lib/live';
import StandaloneLadder from '@/components/live/StandaloneLadder';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';

export default function MultiLadder() {
    const [slots, setSlots] = useState<LadderSlot[]>(() => loadSlots());
    const apply = useCallback((next: LadderSlot[]) => {
        setSlots(next);
        saveSlots(next);
    }, []);

    // ---- picker: eventi calcio seguiti → mercati dell'evento → aggiungi slot ----
    const [showPicker, setShowPicker] = useState(false);
    const [follows, setFollows] = useState<LiveFollow[] | null>(null);
    const [pickEvent, setPickEvent] = useState<LiveFollow | null>(null);
    const [pickMarkets, setPickMarkets] = useState<LiveNowMarket[] | null>(null);
    const [pickBusy, setPickBusy] = useState(false);

    useEffect(() => {
        if (!showPicker || follows != null) return;
        let alive = true;
        fetchLiveFollows()
            .then(rows => { if (alive) setFollows(rows.filter(f => f.status === 'STREAMING' || f.status === 'PENDING')); })
            .catch(e => { console.warn('[MultiLadder] follows:', e); if (alive) setFollows([]); });
        return () => { alive = false; };
    }, [showPicker, follows]);

    const openEvent = useCallback(async (f: LiveFollow) => {
        setPickEvent(f);
        setPickMarkets(null);
        setPickBusy(true);
        try {
            const now = await fetchLiveNow(f.event_id);
            setPickMarkets(now?.state?.markets ?? []);
        } catch (e) {
            console.warn('[MultiLadder] liveNow:', e);
            setPickMarkets([]);
        } finally {
            setPickBusy(false);
        }
    }, []);

    const addMarket = useCallback((f: LiveFollow, m: LiveNowMarket) => {
        apply(addSlot(slots, {
            sport: 'calcio',
            eventId: f.event_id,
            marketId: m.market_id,
            marketName: m.market_name || m.market_type,
            eventName: `${f.home_name} — ${f.away_name}`,
        }));
    }, [slots, apply]);

    const full = slots.length >= MAX_SLOTS;
    const slotIds = useMemo(() => new Set(slots.map(s => s.id)), [slots]);

    return (
        <div className="min-h-screen bg-background text-foreground">
            <Helmet><title>Multi-ladder</title></Helmet>

            {/* top bar */}
            <div className="sticky top-0 z-40 px-3 py-2 border-b border-white/10 bg-black/80 backdrop-blur flex items-center gap-2 flex-wrap">
                <Link
                    to="/segui-live"
                    className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-white"
                >
                    <ArrowLeft className="w-3.5 h-3.5" /> Segui live
                </Link>
                <span className="inline-flex items-center gap-1.5 font-heading font-bold text-sm text-white">
                    <Layers className="w-4 h-4 text-amber-400" /> Multi-ladder
                    <span className="text-[10px] text-muted-foreground font-normal">{slots.length}/{MAX_SLOTS}</span>
                </span>
                <div className="flex-1" />
                <button
                    type="button"
                    onClick={() => setShowPicker(s => !s)}
                    disabled={full}
                    title={full ? `Massimo ${MAX_SLOTS} ladder` : 'Aggiungi il ladder di un mercato (eventi calcio seguiti)'}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-amber-400/40 bg-amber-400/10 text-[11px] font-bold text-amber-200 hover:bg-amber-400/25 disabled:opacity-50"
                >
                    <Plus className="w-3.5 h-3.5" /> Aggiungi ladder
                </button>
            </div>

            {/* picker (calcio; i mercati tennis si aggiungono dal terminal tennis) */}
            {showPicker && (
                <Card className="glass-card border-white/10 m-3 p-3 space-y-2">
                    <div className="text-[11px] text-muted-foreground">
                        Eventi calcio seguiti (i mercati <span className="text-white/80">tennis</span> si aggiungono
                        dal Trading Terminal tennis col bottone <Layers className="w-3 h-3 inline" />).
                    </div>
                    {follows == null ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                            <Loader2 className="w-4 h-4 animate-spin" /> Carico gli eventi seguiti…
                        </div>
                    ) : follows.length === 0 ? (
                        <div className="text-sm text-muted-foreground py-2">Nessun evento seguito attivo.</div>
                    ) : (
                        <div className="flex items-center gap-1.5 flex-wrap">
                            {follows.map(f => (
                                <button
                                    key={f.event_id}
                                    type="button"
                                    onClick={() => openEvent(f)}
                                    className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-colors ${
                                        pickEvent?.event_id === f.event_id
                                            ? 'bg-primary text-black border-primary'
                                            : 'border-white/10 text-muted-foreground hover:text-white'
                                    }`}
                                >
                                    {f.home_name} — {f.away_name}
                                </button>
                            ))}
                        </div>
                    )}
                    {pickEvent && (
                        pickBusy ? (
                            <div className="flex items-center gap-2 text-sm text-muted-foreground py-1">
                                <Loader2 className="w-4 h-4 animate-spin" /> Carico i mercati…
                            </div>
                        ) : (
                            <div className="flex items-center gap-1.5 flex-wrap pt-1 border-t border-white/5">
                                {(pickMarkets ?? []).length === 0 ? (
                                    <span className="text-[11px] text-muted-foreground">Nessun mercato pubblicato per l'evento.</span>
                                ) : (pickMarkets ?? []).map(m => {
                                    const already = slotIds.has(`calcio:${m.market_id}`);
                                    return (
                                        <button
                                            key={m.market_id}
                                            type="button"
                                            disabled={already || full}
                                            onClick={() => addMarket(pickEvent, m)}
                                            title={already ? 'Già nel workspace' : `Aggiungi ${m.market_name || m.market_type}`}
                                            className="px-2 py-0.5 rounded-md text-[11px] border border-white/10 text-white/80 hover:border-amber-400/50 disabled:opacity-40"
                                        >
                                            {already ? '✓ ' : '+ '}{m.market_name || m.market_type}
                                        </button>
                                    );
                                })}
                            </div>
                        )
                    )}
                </Card>
            )}

            {/* griglia ladder */}
            {slots.length === 0 ? (
                <div className="p-10 text-center text-sm text-muted-foreground">
                    Workspace vuoto. Usa <span className="text-white/80">Aggiungi ladder</span> qui sopra, oppure il bottone{' '}
                    <Layers className="w-3.5 h-3.5 inline text-white/70" /> su un ladder di Segui live / Tennis terminal.
                </div>
            ) : (
                <div className="p-3 flex gap-3 flex-wrap items-start">
                    {slots.map(s => (
                        <div key={s.id} className="min-w-[400px] max-w-[560px] flex-1 space-y-1">
                            <div className="flex items-center justify-between gap-2 px-1">
                                <span className="text-[11px] font-bold text-white/85 truncate" title={`${s.eventName} · ${s.marketName}`}>
                                    {s.sport === 'tennis' ? '🎾 ' : '⚽ '}{s.eventName || s.eventId}
                                </span>
                                <span className="flex items-center gap-0.5">
                                    {/* video live + statistiche Betfair del match dello slot */}
                                    <BetfairMediaButtons
                                        compact
                                        eventId={s.eventId}
                                        marketId={s.marketId}
                                        sport={s.sport === 'tennis' ? 'tennis' : 'calcio'}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => apply(removeSlot(slots, s.id))}
                                        title="Rimuovi dal workspace"
                                        className="p-0.5 rounded text-white/40 hover:text-white hover:bg-white/10"
                                    >
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                </span>
                            </div>
                            <StandaloneLadder slot={s} />
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
