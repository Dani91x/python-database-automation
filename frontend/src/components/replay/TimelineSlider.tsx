// ============================================================================
// TimelineSlider — slider del replay con fill dorato e knob circolare che mostra
// il MINUTO corrente. La drag scorre il replay (index sui frame distinti).
// Implementato con una track custom + range input trasparente sopra (per la drag).
// Sopra la track vengono renderizzati i MARKER degli EVENTI della partita
// (gol ⚽, cartellini gialli/rossi, calci d'angolo 🚩) alla loro posizione %.
// ============================================================================
import { Flag } from 'lucide-react';

// Un evento posizionato lungo la track della timeline.
export interface TimelineEventMarker {
    pctLeft: number;            // 0..1 — posizione lungo la track
    kind: string;              // 'goal' | 'yellow' | 'red' | 'corner' | 'other'
    team?: string | null;      // 'home' | 'away' | null
    minute: number | null;
    label: string;             // descrizione (tooltip)
}

// Marker di un'OPPORTUNITÀ di arbitraggio lungo la track (rombo verde).
export interface TimelineArbMarker {
    pctLeft: number;        // 0..1 — posizione lungo la track
    minute: number | null;
    label: string;          // descrizione (tooltip)
}

export interface TimelineSliderProps {
    min: number;          // 0
    max: number;          // timeline.length - 1
    value: number;        // index corrente
    minute: number | null;
    onChange: (v: number) => void;
    suspended?: boolean[]; // allineato agli indici della timeline: true = mercato SOSPESO a quell'istante
    events?: TimelineEventMarker[]; // marker eventi (gol, cartellini, angoli, …)
    arbMarkers?: TimelineArbMarker[]; // istanti con un arbitraggio rilevato (rombi verdi)
}

// Render del singolo marker-icona (sopra la track, non blocca la drag).
function EventIcon({ kind }: { kind: string }) {
    if (kind === 'goal') {
        // pallone: emoji per chiarezza immediata
        return <span className="text-[13px] leading-none drop-shadow">⚽</span>;
    }
    if (kind === 'yellow') {
        return <span className="block w-[9px] h-[12px] rounded-[2px] bg-amber-400 border border-black/40 shadow" />;
    }
    if (kind === 'red') {
        return <span className="block w-[9px] h-[12px] rounded-[2px] bg-red-500 border border-black/40 shadow" />;
    }
    if (kind === 'corner') {
        return <Flag className="w-3.5 h-3.5 text-sky-400 fill-sky-400/30 drop-shadow" strokeWidth={2.5} />;
    }
    // altro: punto generico
    return <span className="block w-1.5 h-1.5 rounded-full bg-white/70" />;
}

export function TimelineSlider({ min, max, value, minute, onChange, suspended, events, arbMarkers }: TimelineSliderProps) {
    const span = Math.max(1, max - min);
    const pct = ((value - min) / span) * 100;
    const steps = (max - min) + 1; // numero di bucket della timeline
    const hasArb = !!arbMarkers?.length;

    const hasGoal = !!events?.some(e => e.kind === 'goal');
    const hasYellow = !!events?.some(e => e.kind === 'yellow');
    const hasRed = !!events?.some(e => e.kind === 'red');
    const hasCorner = !!events?.some(e => e.kind === 'corner');
    const hasLegend = hasGoal || hasYellow || hasRed || hasCorner;

    return (
        <div className="select-none">
            <div className="relative w-full h-10">
                {/* marker EVENTI sopra la track (non bloccano la drag) */}
                {events && events.map((ev, i) => (
                    <div
                        key={i}
                        className="absolute top-0 -translate-x-1/2 z-10 flex items-center justify-center pointer-events-none"
                        style={{ left: `${Math.min(Math.max(ev.pctLeft, 0), 1) * 100}%`, height: '14px' }}
                        title={`${ev.minute != null ? `${ev.minute}' ` : ''}${ev.label}`}
                    >
                        <EventIcon kind={ev.kind} />
                    </div>
                ))}

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

                {/* marker ARBITRAGGI sotto la track (rombi verdi, non bloccano la drag) */}
                {arbMarkers && arbMarkers.map((m, i) => (
                    <div
                        key={`arb-${i}`}
                        className="absolute -translate-x-1/2 z-10 pointer-events-none"
                        style={{ left: `${Math.min(Math.max(m.pctLeft, 0), 1) * 100}%`, bottom: '0px' }}
                        title={`${m.minute != null ? `${m.minute}' ` : ''}${m.label}`}
                    >
                        <span className="block w-2 h-2 rotate-45 bg-emerald-400 border border-emerald-200/60 shadow shadow-emerald-500/40" />
                    </div>
                ))}

                {/* knob circolare con minuto */}
                <div
                    className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-secondary text-black
                               flex items-center justify-center text-xs font-black font-display tabular-nums shadow-lg pointer-events-none
                               border-2 border-black/30 z-20"
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

            {/* legenda eventi (solo se presenti) */}
            {(hasLegend || hasArb) && (
                <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mt-1 text-[10px] text-muted-foreground">
                    {hasArb && (
                        <span className="inline-flex items-center gap-1">
                            <span className="inline-block w-2 h-2 rotate-45 bg-emerald-400 border border-emerald-200/60" /> Arbitraggio
                        </span>
                    )}
                    {hasGoal && <span className="inline-flex items-center gap-1">⚽ Gol</span>}
                    {hasYellow && (
                        <span className="inline-flex items-center gap-1">
                            <span className="inline-block w-[8px] h-[11px] rounded-[2px] bg-amber-400 border border-black/40" /> Giallo
                        </span>
                    )}
                    {hasRed && (
                        <span className="inline-flex items-center gap-1">
                            <span className="inline-block w-[8px] h-[11px] rounded-[2px] bg-red-500 border border-black/40" /> Rosso
                        </span>
                    )}
                    {hasCorner && (
                        <span className="inline-flex items-center gap-1">
                            <Flag className="w-3 h-3 text-sky-400 fill-sky-400/30" strokeWidth={2.5} /> Angolo
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}
