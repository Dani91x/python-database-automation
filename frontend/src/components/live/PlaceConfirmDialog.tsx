// ============================================================================
// PlaceConfirmDialog — popup di conferma di un PLACE dal ladder (stile Bet
// Angel/Fairbot) quando la modalità 1-CLICK NON è armata. Mostra importo
// EDITABILE (precompilato con lo stake preset) e la PROIEZIONE P&L (se vince /
// se perde, con responsabilità dei LAY), poi conferma → l'ordine parte davvero.
//
// REGOLA UNIVERSALE PAPER/LIVE: stesso identico flusso in demo e dal vivo —
// cambia solo il colore/copy (LIVE rosso "REALE", PAPER ambra "SIMULATO").
// Overlay assoluto dentro la card del ladder: funziona anche nel popout,
// nessun cambio di layout della pagina.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Check, ShieldCheck, X } from 'lucide-react';
import { placeProjection } from '@/lib/ladderMath';

interface Props {
    side: 'back' | 'lay';
    price: number;
    priceLabel: string;          // prezzo già formattato dal chiamante (fmtPrice)
    initialAmount: number;       // stake preset (o responsabilità in liability-mode)
    asLiability: boolean;        // true = l'importo del LAY è la responsabilità
    selName: string;
    mode: 'paper' | 'live';
    extraLabel?: string;         // protezioni armate (offset/stop/chase/FoK), già formattate
    onConfirm: (amount: number) => void;
    onCancel: () => void;
}

const fmtEur = (v: number) =>
    `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;

export function PlaceConfirmDialog({
    side, price, priceLabel, initialAmount, asLiability, selName, mode, extraLabel,
    onConfirm, onCancel,
}: Props) {
    const [raw, setRaw] = useState(() =>
        Number.isFinite(initialAmount) && initialAmount > 0 ? String(initialAmount) : '');
    const inputRef = useRef<HTMLInputElement>(null);
    useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);

    const amount = Number(raw);
    const valid = Number.isFinite(amount) && amount > 0;
    const proj = valid ? placeProjection(side, price, amount, asLiability) : null;

    const isLive = mode === 'live';
    const accent = isLive
        ? { border: 'border-red-500/50', chip: 'bg-red-500 text-white', text: 'text-red-300', btn: 'bg-red-500 hover:bg-red-600' }
        : { border: 'border-amber-500/50', chip: 'bg-amber-500 text-black', text: 'text-amber-300', btn: 'bg-amber-500 hover:bg-amber-600 text-black' };
    const sideCls = side === 'back' ? 'text-sky-300' : 'text-rose-300';
    const amountLabel = asLiability && side === 'lay' ? 'Responsabilità (€)' : 'Importo (€)';

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-label={`Conferma ordine ${side === 'back' ? 'BACK' : 'LAY'} ${selName}`}
            className="absolute inset-0 z-40 flex items-start justify-center bg-black/60 backdrop-blur-[2px] p-4 pt-16"
            onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}
        >
            <div className={`w-full max-w-sm rounded-xl border ${accent.border} bg-black/95 shadow-2xl p-3 space-y-2.5`}>
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-black flex items-center gap-1.5 text-white">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span className={sideCls}>{side === 'back' ? 'BACK' : 'LAY'}</span>
                        <span className="font-mono">@ {priceLabel}</span>
                        <span className="truncate max-w-[120px]" title={selName}>{selName}</span>
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${accent.chip}`}>
                        {isLive ? 'REALE' : 'SIMULATO'}
                    </span>
                </div>

                <label className="block text-[10px] font-bold text-white/70">
                    {amountLabel}
                    <input
                        ref={inputRef}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step={0.5}
                        value={raw}
                        onChange={(e) => setRaw(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter' && valid) onConfirm(amount); }}
                        aria-label={amountLabel}
                        className={`mt-1 w-full rounded-md border bg-white/5 px-2 py-1.5 text-sm font-bold text-white tabular-nums outline-none ${
                            valid ? 'border-white/20 focus:border-white/50' : 'border-red-500 text-red-300'
                        }`}
                    />
                </label>

                {/* proiezione P&L: cosa succede se la selezione vince/perde (come nei tool pro) */}
                <div className="grid grid-cols-2 gap-1.5 text-[11px] tabular-nums">
                    <div className="rounded-md bg-white/5 px-2 py-1.5">
                        <div className="text-[9px] uppercase tracking-wider text-white/50 font-bold">Se vince</div>
                        <div className={`font-black ${proj && proj.ifWin >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                            {proj ? fmtEur(proj.ifWin) : '—'}
                        </div>
                    </div>
                    <div className="rounded-md bg-white/5 px-2 py-1.5">
                        <div className="text-[9px] uppercase tracking-wider text-white/50 font-bold">Se perde</div>
                        <div className={`font-black ${proj && proj.ifLose >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                            {proj ? fmtEur(proj.ifLose) : '—'}
                        </div>
                    </div>
                </div>
                <div className="flex items-center justify-between text-[10px] text-white/60">
                    <span>Responsabilità: <span className="font-bold text-white/85">{proj ? `€${proj.liability.toFixed(2)}` : '—'}</span></span>
                    {side === 'lay' && asLiability && proj && (
                        <span>Size: <span className="font-bold text-white/85">€{proj.stake.toFixed(2)}</span></span>
                    )}
                </div>
                {extraLabel && (
                    <div className="text-[10px] text-white/50">Protezioni: <span className="font-mono">{extraLabel}</span></div>
                )}

                <div className="flex items-center gap-1.5 pt-0.5">
                    <button
                        type="button"
                        disabled={!valid}
                        onClick={() => { if (valid) onConfirm(amount); }}
                        className={`flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-md text-[11px] font-black disabled:opacity-40 disabled:cursor-not-allowed ${accent.btn}`}
                    >
                        <Check className="w-3 h-3" /> Conferma {isLive ? 'REALE' : 'simulato'}
                    </button>
                    <button
                        type="button"
                        onClick={onCancel}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-white/15 text-white/80 text-[11px] font-bold hover:bg-white/10"
                    >
                        <X className="w-3 h-3" /> Annulla
                    </button>
                </div>
                <div className={`text-[9px] ${accent.text}`}>
                    {isLive
                        ? 'Ordine con SOLDI VERI: verrà inviato a Betfair alla conferma.'
                        : 'Ordine simulato (paper): identico al vivo, ma senza soldi veri.'}
                </div>
            </div>
        </div>
    );
}

export default PlaceConfirmDialog;
