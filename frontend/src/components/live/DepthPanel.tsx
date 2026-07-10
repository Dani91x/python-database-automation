// ============================================================================
// DepthPanel — D31: pannello "profondità totale" (WOM esteso) + delta flusso.
//
// Per ogni selezione del mercato:
//   * depth CUMULATA back/lay su TUTTI i livelli pubblicati (segmenti ∝ size,
//     gap di 2px, tooltip prezzo/size/cumulata) + totali € per lato;
//   * ripartizione del denaro (WOM esteso su tutto il book, non solo il best);
//   * DELTA FLUSSO: denaro entrato/uscito per lato negli ultimi N secondi,
//     calcolato client-side dai sample del ladder (lib/depthFlow, matematica
//     PURA testata). Storia insufficiente → "—", MAI un delta inventato.
//
// Sport-agnostico via LadderSource injection (default = calcio, come LadderView).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    fetchLiveLadder, subscribeLiveLadder,
    type LiveLadderRow, type LiveLadderSelection,
} from '@/lib/live';
import type { LadderSource } from '@/components/live/LadderView';
import {
    cumulativeLevels, depthDelta, pushDepthSample, sideTotals, type DepthSample,
} from '@/lib/depthFlow';
import {
    detectPulledWalls, newFlowState, pushFlowSample, tradeSpike, womShift,
    SPIKE_MIN_EUR, SPIKE_MIN_RATIO, WOM_SHIFT_ALERT_PP, type FlowState,
} from '@/lib/orderFlow';

const DEFAULT_SOURCE: LadderSource = { fetch: fetchLiveLadder, subscribe: subscribeLiveLadder };
const WINDOWS = [10, 30, 60] as const;

interface Props {
    marketId: string;
    ladderSource?: LadderSource;
}

function fmtEur(v: number): string {
    return `€${Math.round(v).toLocaleString('it-IT')}`;
}

function fmtDelta(v: number): string {
    const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
    return `${sign}€${Math.abs(Math.round(v)).toLocaleString('it-IT')}`;
}

function DepthBar({ levels, tone }: {
    levels: ReadonlyArray<readonly [number, number]> | null | undefined;
    tone: 'back' | 'lay';
}) {
    const cum = cumulativeLevels(levels);
    const total = cum.length ? cum[cum.length - 1].cum : 0;
    if (!cum.length || total <= 0) {
        return <div className="h-3 rounded bg-white/5" title="nessuna liquidità pubblicata" />;
    }
    const color = tone === 'back' ? 'bg-sky-500/70' : 'bg-pink-500/70';
    return (
        <div className="flex h-3 w-full gap-[2px]">
            {cum.map((lv) => (
                <div
                    key={`${lv.price}`}
                    className={`${color} rounded-[2px] min-w-[2px]`}
                    style={{ width: `${(lv.size / total) * 100}%` }}
                    title={`@${lv.price}: €${Math.round(lv.size)} (cum €${Math.round(lv.cum)})`}
                />
            ))}
        </div>
    );
}

// F44: alert order-flow per selezione (muri finti / shift WOM / picco volume).
// ONESTÀ: sono INDIZI statistici su ciò che il book mostra, mai prove — presentati
// come "possibile", mai bloccanti. Nessuna anomalia → nessuna riga (zero rumore).
function OrderFlowAlerts({ flow, now }: { flow: FlowState | undefined; now: number }) {
    if (!flow) return null;
    const walls = detectPulledWalls(flow, now);
    const shift = womShift(flow, now);
    const spike = tradeSpike(flow, now);
    const shiftAlert = shift != null && Math.abs(shift) >= WOM_SHIFT_ALERT_PP;
    const spikeAlert = spike != null && spike.ratio >= SPIKE_MIN_RATIO && spike.recent >= SPIKE_MIN_EUR;
    if (walls.length === 0 && !shiftAlert && !spikeAlert) return null;
    return (
        <div className="space-y-0.5">
            {walls.map(w => (
                <div key={`${w.side}@${w.price}`}
                    className="text-[10px] text-fuchsia-300 tabular-nums"
                    title={'INDIZIO (non prova): size grossa sparita dal book senza essere consumata dai trade — '
                        + `picco €${Math.round(w.peak)}, sparita €${Math.round(w.dropped)}, tradati solo €${Math.round(w.traded)} in 15s.`}>
                    🎭 possibile muro finto {w.side.toUpperCase()} @ {w.price}: −{fmtEur(w.dropped)} non consumati
                </div>
            ))}
            {shiftAlert && (
                <div className="text-[10px] text-amber-300 tabular-nums"
                    title="Sbilanciamento del denaro vicino al best (top-3 livelli) cambiato bruscamente negli ultimi 30s.">
                    ⚖ shift WOM {shift! > 0 ? '+' : '−'}{Math.abs(shift!).toFixed(0)}pp in 30s ({shift! > 0 ? 'pressione BACK' : 'pressione LAY'})
                </div>
            )}
            {spikeAlert && (
                <div className="text-[10px] text-orange-300 tabular-nums"
                    title={`Volume tradato nell'ultimo minuto (€${Math.round(spike!.recent)}) ≥ ${SPIKE_MIN_RATIO}× il minuto precedente (€${Math.round(spike!.baseline)}).`}>
                    ⚡ picco volume: {fmtEur(spike!.recent)} nell'ultimo minuto
                    ({Number.isFinite(spike!.ratio) ? `${spike!.ratio.toFixed(1)}×` : 'da fermo'})
                </div>
            )}
        </div>
    );
}

function SelectionDepth({ sel, buf, flow, windowSec, now }: {
    sel: LiveLadderSelection;
    buf: DepthSample[] | undefined;
    flow: FlowState | undefined;
    windowSec: number;
    now: number;
}) {
    const backTot = sideTotals(sel.back);
    const layTot = sideTotals(sel.lay);
    const tot = backTot + layTot;
    const backPct = tot > 0 ? (backTot / tot) * 100 : null;
    const delta = buf ? depthDelta(buf, now, windowSec * 1000) : null;

    return (
        <div className="rounded-lg border border-white/10 bg-black/40 p-2.5 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-white truncate" title={sel.name ?? undefined}>
                    {sel.name ?? `#${sel.selection_id}`}
                </span>
                <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                    {backPct != null
                        ? <>book {backPct.toFixed(0)}% back · {(100 - backPct).toFixed(0)}% lay</>
                        : 'book vuoto'}
                </span>
            </div>
            <div className="grid grid-cols-[44px_1fr_72px] items-center gap-2 text-[10px]">
                <span className="text-sky-300 font-semibold">BACK</span>
                <DepthBar levels={sel.back} tone="back" />
                <span className="text-right tabular-nums text-white/80">{fmtEur(backTot)}</span>
                <span className="text-pink-300 font-semibold">LAY</span>
                <DepthBar levels={sel.lay} tone="lay" />
                <span className="text-right tabular-nums text-white/80">{fmtEur(layTot)}</span>
            </div>
            <div className="flex items-center justify-between text-[10px] tabular-nums">
                <span className="text-muted-foreground">Flusso {windowSec}s</span>
                {delta == null ? (
                    <span className="text-muted-foreground" title="storia insufficiente: servono campioni più vecchi della finestra">—</span>
                ) : (
                    <span className="flex gap-2">
                        <span className={delta.back > 0 ? 'text-sky-300' : delta.back < 0 ? 'text-red-300' : 'text-white/60'}>
                            back {fmtDelta(delta.back)}
                        </span>
                        <span className={delta.lay > 0 ? 'text-pink-300' : delta.lay < 0 ? 'text-red-300' : 'text-white/60'}>
                            lay {fmtDelta(delta.lay)}
                        </span>
                    </span>
                )}
            </div>
            {/* F44: order-flow analytics (indizi, mai bloccanti) */}
            <OrderFlowAlerts flow={flow} now={now} />
        </div>
    );
}

export function DepthPanel({ marketId, ladderSource = DEFAULT_SOURCE }: Props) {
    const [row, setRow] = useState<LiveLadderRow | null>(null);
    const [windowSec, setWindowSec] = useState<number>(30);
    const [now, setNow] = useState(() => Date.now());
    // buffer campioni per selezione (mutati in place, azzerati al cambio mercato)
    const bufsRef = useRef<Map<number, DepthSample[]>>(new Map());
    // F44: stato order-flow per selezione (snapshot per-livello: muri/WOM/volume)
    const flowsRef = useRef<Map<number, FlowState>>(new Map());

    useEffect(() => {
        bufsRef.current = new Map();
        flowsRef.current = new Map();
        let alive = true;
        const ingest = (r: LiveLadderRow | null) => {
            if (!alive || !r) return;
            const t = r.ladder?.updated_ms ?? Date.now();
            for (const sel of r.ladder?.selections ?? []) {
                let buf = bufsRef.current.get(sel.selection_id);
                if (!buf) { buf = []; bufsRef.current.set(sel.selection_id, buf); }
                pushDepthSample(buf, t, sideTotals(sel.back), sideTotals(sel.lay));
                let flow = flowsRef.current.get(sel.selection_id);
                if (!flow) { flow = newFlowState(); flowsRef.current.set(sel.selection_id, flow); }
                pushFlowSample(flow, t, sel.back, sel.lay, sel.trd);
            }
            setRow(r);
        };
        ladderSource.fetch(marketId).then(ingest).catch(() => { /* fetch iniziale best-effort */ });
        const unsub = ladderSource.subscribe(marketId, ingest);
        return () => { alive = false; unsub(); };
    }, [marketId, ladderSource]);

    // il delta dipende da "adesso": tick 1s per tenerlo vivo anche senza update del book
    useEffect(() => {
        const t = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const selections = useMemo(() => row?.ladder?.selections ?? [], [row]);

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-white/90">Profondità totale</span>
                <div className="flex items-center gap-1" title="finestra del delta flusso">
                    {WINDOWS.map((w) => (
                        <button
                            key={w}
                            type="button"
                            onClick={() => setWindowSec(w)}
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                                windowSec === w
                                    ? 'bg-amber-400 text-black border-amber-400'
                                    : 'border-white/10 text-white/60 hover:border-amber-400/40'
                            }`}
                        >
                            {w}s
                        </button>
                    ))}
                </div>
            </div>
            {selections.length === 0 ? (
                <div className="text-[11px] text-muted-foreground p-2">nessun book disponibile</div>
            ) : (
                selections.map((sel) => (
                    <SelectionDepth
                        key={sel.selection_id}
                        sel={sel}
                        buf={bufsRef.current.get(sel.selection_id)}
                        flow={flowsRef.current.get(sel.selection_id)}
                        windowSec={windowSec}
                        now={now}
                    />
                ))
            )}
            <p className="text-[9px] text-muted-foreground/70">
                Flusso calcolato client-side dai sample del ladder da quando il pannello è aperto.
            </p>
        </div>
    );
}
