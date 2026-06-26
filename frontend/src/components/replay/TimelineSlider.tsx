// ============================================================================
// TimelineSlider — slider del replay con fill dorato e knob circolare che mostra
// il MINUTO corrente. La drag scorre il replay (index sui frame distinti).
// Implementato con una track custom + range input trasparente sopra (per la drag).
// ============================================================================
export interface TimelineSliderProps {
    min: number;          // 0
    max: number;          // timeline.length - 1
    value: number;        // index corrente
    minute: number | null;
    onChange: (v: number) => void;
    suspended?: boolean[]; // allineato agli indici della timeline: true = mercato SOSPESO a quell'istante
}

export function TimelineSlider({ min, max, value, minute, onChange, suspended }: TimelineSliderProps) {
    const span = Math.max(1, max - min);
    const pct = ((value - min) / span) * 100;
    const steps = (max - min) + 1; // numero di bucket della timeline

    return (
        <div className="relative w-full h-10 select-none">
            {/* track */}
            <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-2 rounded-full bg-white/10 overflow-hidden">
                {/* fill dorato */}
                <div className="h-full bg-secondary" style={{ width: `${pct}%` }} />
                {/* segmenti SOSPENSIONE (rosso a strisce) sovrapposti alla track */}
                {suspended && steps > 1 && suspended.map((s, i) =>
                    s ? (
                        <div
                            key={i}
                            className="absolute top-0 bottom-0 bg-red-500/70"
                            style={{
                                // clamp: l'ultimo segmento non deve uscire dalla track (overflow-hidden lo taglierebbe)
                                left: `${Math.min((i / span) * 100, 100 - (1 / span) * 100)}%`,
                                width: `${(1 / span) * 100}%`,
                                backgroundImage:
                                    'repeating-linear-gradient(45deg, rgba(0,0,0,0.35) 0, rgba(0,0,0,0.35) 2px, transparent 2px, transparent 4px)',
                            }}
                        />
                    ) : null,
                )}
            </div>

            {/* knob circolare con minuto */}
            <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-secondary text-black
                           flex items-center justify-center text-xs font-black font-display tabular-nums shadow-lg pointer-events-none
                           border-2 border-black/30"
                style={{ left: `${pct}%` }}
            >
                {minute != null ? `${minute}` : '—'}
            </div>

            {/* range trasparente per la drag */}
            <input
                type="range"
                min={min}
                max={max}
                step={1}
                value={value}
                onChange={e => onChange(Number(e.target.value))}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                aria-label="Timeline replay"
            />
        </div>
    );
}
