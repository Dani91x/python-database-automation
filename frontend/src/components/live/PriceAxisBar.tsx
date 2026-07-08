// ============================================================================
// PriceAxisBar — barra prezzo NAVIGABILE stile Geeks Toy (B18): l'intera scala
// tick Betfair 1.01→1000 compressa in una colonna; la heat (ramp ambra a tinta
// singola, skill dataviz: sequential = one hue) mostra DOVE si concentra il
// denaro (disponibilità back+lay+volumi tradati). Click/drag = sposta la vista
// del ladder su quel prezzo (il parent passa in navigazione manuale).
// ============================================================================
import { useCallback, useMemo, useRef, type PointerEvent } from 'react';
import { indexToPrice, priceToIndex, TOTAL_TICKS, moneyProfile } from '@/lib/priceAxis';

const ZONES = 70;   // celle heat (≈5 tick l'una): granularità percettiva, non per-tick
const W = 16;       // larghezza barra (px)

const fmtP = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(2));

export function PriceAxisBar({ back, lay, trd, center, onNavigate }: {
    back: [number, number][] | undefined;
    lay: [number, number][] | undefined;
    trd: [number, number][] | undefined;
    center: number | null;           // prezzo su cui la vista è centrata (marker)
    onNavigate: (price: number) => void;
}) {
    const zones = useMemo(() => moneyProfile([back, lay, trd], ZONES), [back, lay, trd]);
    const maxZone = useMemo(() => zones.reduce((m, v) => (v > m ? v : m), 0), [zones]);

    const barRef = useRef<HTMLDivElement | null>(null);
    const lastSentRef = useRef<number | null>(null);

    // Y (px dal top) → prezzo: il TOP della barra è l'indice più ALTO (1000), come il
    // ladder che mostra i prezzi alti in cima.
    const priceAtY = useCallback((clientY: number): number | null => {
        const el = barRef.current;
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        if (rect.height <= 0) return null;
        const frac = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
        return indexToPrice(Math.round((1 - frac) * (TOTAL_TICKS - 1)));
    }, []);

    const navigate = useCallback((clientY: number) => {
        const p = priceAtY(clientY);
        if (p == null || p === lastSentRef.current) return;
        lastSentRef.current = p;
        onNavigate(p);
    }, [priceAtY, onNavigate]);

    const onDown = useCallback((e: PointerEvent<HTMLDivElement>) => {
        e.preventDefault();
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        navigate(e.clientY);
    }, [navigate]);
    const onMove = useCallback((e: PointerEvent<HTMLDivElement>) => {
        if (e.buttons !== 1) return; // solo in drag col tasto premuto
        navigate(e.clientY);
    }, [navigate]);
    const onUp = useCallback(() => { lastSentRef.current = null; }, []);

    // marker del centro vista corrente (linea ambra) in % dal top.
    const centerPct = center != null
        ? (1 - priceToIndex(center) / (TOTAL_TICKS - 1)) * 100
        : null;

    return (
        <div
            ref={barRef}
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            title="Scala prezzi 1.01–1000 · heat = dove si concentra il denaro · clic/trascina per scorrere il ladder"
            className="relative shrink-0 border-r border-white/10 bg-black/40 cursor-ns-resize select-none touch-none"
            style={{ width: W }}
            role="slider"
            aria-label="Navigazione prezzo del ladder"
            aria-valuemin={1.01}
            aria-valuemax={1000}
            aria-valuenow={center ?? undefined}
            aria-valuetext={center != null ? fmtP(center) : undefined}
        >
            {/* heat: colonna di celle (top = prezzi alti), ramp ambra a tinta singola */}
            <div className="absolute inset-0 flex flex-col">
                {Array.from({ length: ZONES }, (_, i) => {
                    const v = zones[ZONES - 1 - i]; // inverti: la prima cella in alto = zona con indice alto
                    const alpha = maxZone > 0 && v > 0 ? 0.10 + 0.75 * Math.sqrt(v / maxZone) : 0;
                    return (
                        <div
                            key={i}
                            className="flex-1"
                            style={alpha > 0 ? { backgroundColor: `rgba(251, 191, 36, ${alpha.toFixed(3)})` } : undefined}
                        />
                    );
                })}
            </div>
            {/* marker del centro vista */}
            {centerPct != null && (
                <div
                    className="absolute left-0 right-0 h-[2px] bg-amber-300 shadow-[0_0_4px_rgba(251,191,36,0.9)] pointer-events-none"
                    style={{ top: `${centerPct}%` }}
                />
            )}
        </div>
    );
}

export default PriceAxisBar;
