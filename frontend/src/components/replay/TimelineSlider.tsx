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
}

export function TimelineSlider({ min, max, value, minute, onChange }: TimelineSliderProps) {
    const span = Math.max(1, max - min);
    const pct = ((value - min) / span) * 100;

    return (
        <div className="relative w-full h-10 select-none">
            {/* track */}
            <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-2 rounded-full bg-white/10 overflow-hidden">
                {/* fill dorato */}
                <div className="h-full bg-secondary" style={{ width: `${pct}%` }} />
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
