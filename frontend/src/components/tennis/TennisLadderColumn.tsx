// ============================================================================
// TennisLadderColumn.tsx — Colonna CENTRALE del Tennis Trading Terminal (Screen 3).
//
// Ladder di profondità realtime con one-click trading, drag-to-move (cancel→replace)
// e overlay ordini (manuali + bot). RIUSA il componente ladder del calcio (LadderView)
// via dependency-injection, ma lo alimenta con DATI ESCLUSIVAMENTE TENNIS: fetch/subscribe
// da `tennis_live_ladder` e ordini da `tennis_live_orders` (RPC `*_tennis_*`).
//
// Regola d'oro (richiesta esplicita utente): Tennis e Calcio NON condividono MAI dati.
// LadderView riceve qui sotto SOLO funzioni di '@/lib/tennis' → nessuna tabella calcio
// viene letta o scritta. Con LadderView di default (nessuna injection) il calcio resta
// byte-identico: qui iniettiamo tutto ciò che serve al tennis.
//
// order_mode (OFF/PAPER/LIVE) e le selezioni note arrivano da `tennis_live_now`
// (subscribeTennisNow): l'utente arma il runner tennis, la ladder si adegua.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Layers, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LadderView, type LadderSource, type LadderOrderApi } from '@/components/live/LadderView';
import {
    fetchTennisLadder,
    subscribeTennisLadder,
    sendTennisOrderCommand,
    fetchTennisOrders,
    fetchTennisPositions,
    fetchTennisNow,
    subscribeTennisNow,
    type TennisLiveNowRow,
} from '@/lib/tennis';

export interface TennisLadderColumnProps {
    eventId: string;
    marketId: string;
    marketName: string;
    p1: string;
    p2: string;
}

// Sorgente ladder TENNIS: legge/soscrive unicamente `tennis_live_ladder` (stessa
// SHAPE LiveLadderRow del calcio, ma dati tennis). Stabile a livello di modulo.
const TENNIS_LADDER_SOURCE: LadderSource = {
    fetch: fetchTennisLadder,
    subscribe: subscribeTennisLadder,
};

// API ordini TENNIS: coda comandi dedicata (`request_tennis_live_order`) + specchi
// `tennis_live_orders` / `tennis_live_positions`. Il green-up (cash-out) è supportato
// riusando l'action 'greenup' della coda tennis: il runner tennis deriva side/price/size
// dalle esposizioni MATCHED reali (nessun numero stantio), come nel calcio.
const TENNIS_ORDER_API: LadderOrderApi = {
    send: (cmd) => sendTennisOrderCommand(cmd),
    fetchOrders: (marketId, mode) => fetchTennisOrders(marketId, mode),
    fetchPositions: (marketId, mode) => fetchTennisPositions(marketId, mode),
    greenup: async ({ marketId, selectionId, mode, handicap, fraction, targetPrice }) => {
        // fraction<=0 è priva di senso: rifiutala (altrimenti il runner farebbe un
        // green-up TOTALE inatteso). 0<f<1 → cash-out parziale via params.
        if (fraction != null && fraction <= 0) throw new Error('greenup: fraction deve essere > 0');
        // target_price malformato = errore del chiamante, MAI inviato (il runner
        // chiuderebbe al best: prezzo diverso dal livello cliccato).
        if (targetPrice != null && !(Number.isFinite(targetPrice) && targetPrice > 1 && targetPrice <= 1000)) {
            throw new Error('greenup: targetPrice deve essere un prezzo in (1, 1000]');
        }
        const params: Record<string, number> = {};
        if (fraction != null && fraction > 0 && fraction < 1) params.fraction = Math.round(fraction * 1000) / 1000;
        if (targetPrice != null) params.target_price = targetPrice;
        return sendTennisOrderCommand({
            action: 'greenup',
            mode,
            market_id: marketId,
            selection_id: selectionId,
            handicap: handicap ?? 0,
            ...(Object.keys(params).length ? { params } : {}),
        });
    },
};

// Normalizza la modalità ordini letta da tennis_live_now.state.order_mode.
function normalizeMode(raw: string | undefined | null): 'OFF' | 'PAPER' | 'LIVE' {
    const m = (raw ?? 'off').toLowerCase();
    if (m === 'live') return 'LIVE';
    if (m === 'paper') return 'PAPER';
    return 'OFF';
}

export function TennisLadderColumn({ eventId, marketId, marketName, p1, p2 }: TennisLadderColumnProps) {
    const [now, setNow] = useState<TennisLiveNowRow | null>(null);

    // order_mode + selezioni note dallo stato live tennis (realtime). Snapshot + subscribe.
    useEffect(() => {
        if (!eventId) { setNow(null); return; }
        let alive = true;
        fetchTennisNow(eventId)
            .then((r) => { if (alive) setNow(r); })
            .catch((e: unknown) => { if (alive) console.warn('[TennisLadderColumn] fetchTennisNow:', e); });
        const unsub = subscribeTennisNow(eventId, (r) => { if (r) setNow(r); });
        return () => { alive = false; unsub(); };
    }, [eventId]);

    const orderMode = useMemo(() => normalizeMode(now?.state?.order_mode), [now]);

    // fallbackSelections: dalle selezioni del mercato che stiamo mostrando (per nome/ordine
    // finché la ladder full-depth non è ancora arrivata). Solo il mercato con questo marketId.
    const fallbackSelections = useMemo(() => {
        const market = now?.state?.markets?.find((m) => m.market_id === marketId);
        return (market?.selections ?? []).map((s) => ({ selection_id: s.selection_id, name: s.name }));
    }, [now, marketId]);

    return (
        <div className={cn(
            'glass-card border border-white/10 rounded-2xl overflow-hidden flex flex-col',
        )}>
            {/* header compatto: mercato + P1/P2 */}
            <div className="px-3 py-2 border-b border-white/10 bg-white/[0.03] flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                    <Layers className="w-4 h-4 text-primary shrink-0" />
                    <span className="font-heading font-bold text-sm text-white truncate" title={marketName}>
                        {marketName}
                    </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0 text-[10px] font-bold">
                    <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-200 truncate max-w-[120px]" title={p1}>{p1}</span>
                    <span className="text-muted-foreground/60">vs</span>
                    <span className="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-200 truncate max-w-[120px]" title={p2}>{p2}</span>
                </div>
            </div>

            {/* ladder riusabile alimentata SOLO con dati tennis (DI) + drag-to-move abilitato */}
            <div className="p-2">
                <LadderView
                    marketId={marketId}
                    marketName={marketName}
                    sport="tennis"
                    orderMode={orderMode}
                    fallbackSelections={fallbackSelections}
                    enableDragMove
                    ladderSource={TENNIS_LADDER_SOURCE}
                    orderApi={TENNIS_ORDER_API}
                />
            </div>

            {/* legenda overlay ordini: manuali + bot condividono `tennis_live_orders` (lo
                specchio ordini non distingue la sorgente) → sono mostrati in modo uniforme. */}
            <div className="px-3 py-1.5 border-t border-white/10 bg-black/30 flex items-center gap-1.5 text-[9px] text-muted-foreground/70">
                <Info className="w-3 h-3 shrink-0" />
                <span>
                    Gli ordini in overlay (colonne <span className="text-sky-300/80 font-bold">B</span>/<span className="text-rose-300/80 font-bold">L</span>) includono sia i tuoi ordini manuali sia quelli dei bot tennis. Trascina un ordine su un altro livello per spostarlo (annulla e ripiazza).
                </span>
            </div>
        </div>
    );
}

export default TennisLadderColumn;
