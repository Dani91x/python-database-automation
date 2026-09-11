// ============================================================================
// ModeToggle.tsx — interruttore PAPER/LIVE unico. Accessibile: due bottoni con
// aria-pressed (prima erano tre div senza stato leggibile).
// Il passaggio a LIVE NON è mai immediato: la pagina apre LiveConfirmDialog.
// ============================================================================
export type TradingMode = 'paper' | 'live';

export function ModeToggle({ mode, onChange, disabled }: {
    mode: TradingMode;
    onChange: (next: TradingMode) => void;
    disabled?: boolean;
}) {
    return (
        <div
            className="flex items-center rounded-lg border border-white/10 overflow-hidden text-xs font-bold"
            role="group"
            aria-label="Modalità di trading"
            data-testid="mode-toggle"
        >
            <button
                type="button"
                onClick={() => onChange('paper')}
                aria-pressed={mode === 'paper'}
                disabled={disabled}
                className={`px-3 py-1.5 transition ${mode === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400 hover:text-white'}`}
            >PAPER</button>
            <button
                type="button"
                onClick={() => onChange('live')}
                aria-pressed={mode === 'live'}
                disabled={disabled}
                className={`px-3 py-1.5 transition ${mode === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400 hover:text-white'}`}
            >LIVE</button>
        </div>
    );
}

export default ModeToggle;
