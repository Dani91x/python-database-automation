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
//
// 09/10 (Programma del giorno) - lo stesso box serve il tabellone, con prop
// OPZIONALI (il ladder non le passa e resta identico):
//   * `prezzoModificabile`: la quota si corregge nel box (campo + un tick su/giu'
//     sulla scala Betfair); valida solo fra 1,01 e 1000 E su un tick vero,
//     altrimenti la conferma e' spenta e il motivo e' scritto (mai arrotondare
//     in silenzio un prezzo che parte con dei soldi);
//   * `mode: null`: la modalita' del runner NON e' nota -> nessun colore di
//     modalita' inventato, chip «NON NOTA»;
//   * `bloccato`: la ragione per cui NON si puo' confermare (modalita' ignota,
//     ordini OFF, invio gia' in corso): conferma spenta, ragione in chiaro;
//   * `inline`: il box si apre SOTTO la riga cliccata (come la schedina di
//     Betfair) invece che in sovrimpressione sulla card del ladder;
//   * `contesto`: evento e mercato, una riga sotto il titolo.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, ChevronUp, ShieldCheck, X } from 'lucide-react';
import { placeProjection } from '@/lib/ladderMath';
import { isValidTick, roundToTick, tickDown, tickUp } from '@/lib/matching';

/** limiti di quota accettati da Betfair */
export const QUOTA_MIN = 1.01;
export const QUOTA_MAX = 1000;

/** `null` = quota valida; altrimenti il motivo, scritto per il trader. */
export function motivoQuotaNonValida(q: number): string | null {
    if (!Number.isFinite(q)) return 'quota non numerica';
    if (q < QUOTA_MIN || q > QUOTA_MAX) return 'quota fuori dai limiti Betfair (1,01 - 1000)';
    if (!isValidTick(q)) return `quota fuori dalla scala Betfair: la più vicina è ${roundToTick(q).toFixed(2)}`;
    return null;
}

interface Props {
    side: 'back' | 'lay';
    price: number;
    priceLabel: string;          // prezzo già formattato dal chiamante (fmtPrice)
    initialAmount: number;       // stake preset (o responsabilità in liability-mode)
    asLiability: boolean;        // true = l'importo del LAY è la responsabilità
    selName: string;
    /** null = modalita' del runner non nota (solo il tabellone lo passa) */
    mode: 'paper' | 'live' | null;
    extraLabel?: string;         // protezioni armate (offset/stop/chase/FoK), già formattate
    /** riceve l'importo e la quota (quella corretta nel box, se modificabile) */
    onConfirm: (amount: number, price: number) => void;
    onCancel: () => void;
    /** 09/10: la quota si corregge nel box (tabellone) */
    prezzoModificabile?: boolean;
    /** 09/10: perche' non si puo' confermare; null/assente = si puo' */
    bloccato?: string | null;
    /** 09/10: box sotto la riga invece che in sovrimpressione */
    inline?: boolean;
    /** 09/10: evento e mercato, una riga sotto il titolo */
    contesto?: string;
}

const fmtEur = (v: number) =>
    `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;

export function PlaceConfirmDialog({
    side, price, priceLabel, initialAmount, asLiability, selName, mode, extraLabel,
    onConfirm, onCancel, prezzoModificabile = false, bloccato = null, inline = false, contesto,
}: Props) {
    const [raw, setRaw] = useState(() =>
        Number.isFinite(initialAmount) && initialAmount > 0 ? String(initialAmount) : '');
    const [prezzoRaw, setPrezzoRaw] = useState(() => (Number.isFinite(price) ? price.toFixed(2) : ''));
    const inputRef = useRef<HTMLInputElement>(null);
    useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);

    const amount = Number(raw);
    const valid = Number.isFinite(amount) && amount > 0;
    // la quota dell'ordine: quella del box se modificabile, se no quella cliccata
    const prezzo = prezzoModificabile ? Number(prezzoRaw.replace(',', '.')) : price;
    const erroreQuota = prezzoModificabile ? motivoQuotaNonValida(prezzo) : null;
    const proj = valid && erroreQuota == null ? placeProjection(side, prezzo, amount, asLiability) : null;
    const puoConfermare = valid && erroreQuota == null && !bloccato;
    const conferma = () => { if (puoConfermare) onConfirm(amount, prezzo); };
    const muoviTick = (dir: 1 | -1) => {
        const base = Number.isFinite(prezzo) && prezzo > 0 ? prezzo : price;
        setPrezzoRaw((dir > 0 ? tickUp(base) : tickDown(base)).toFixed(2));
    };

    const isLive = mode === 'live';
    const accent = isLive
        ? { border: 'border-red-500/50', chip: 'bg-red-500 text-white', text: 'text-red-300', btn: 'bg-red-500 hover:bg-red-600' }
        : mode === 'paper'
            ? { border: 'border-amber-500/50', chip: 'bg-amber-500 text-black', text: 'text-amber-300', btn: 'bg-amber-500 hover:bg-amber-600 text-black' }
            // modalita' NON nota: nessun colore di modalita' inventato
            : { border: 'border-white/25', chip: 'bg-white/15 text-white', text: 'text-amber-300', btn: 'bg-white/15 hover:bg-white/25 text-white' };
    const sideCls = side === 'back' ? 'text-sky-300' : 'text-rose-300';
    const amountLabel = asLiability && side === 'lay' ? 'Responsabilità (€)' : 'Importo (€)';

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-label={`Conferma ordine ${side === 'back' ? 'BACK' : 'LAY'} ${selName}`}
            className={inline
                ? 'relative z-10 flex items-start justify-center px-2 py-2 ds-v2-box-ordine'
                : 'absolute inset-0 z-40 flex items-start justify-center bg-black/60 backdrop-blur-[2px] p-4 pt-16'}
            onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}
        >
            <div className={`w-full max-w-sm rounded-xl border ${accent.border} bg-black/95 shadow-2xl p-3 space-y-2.5`}>
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-black flex items-center gap-1.5 text-white">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span className={sideCls}>{side === 'back' ? 'BACK' : 'LAY'}</span>
                        <span className="font-mono">@ {prezzoModificabile
                            ? (erroreQuota == null ? prezzo.toFixed(2) : '—')
                            : priceLabel}</span>
                        <span className="truncate max-w-[120px]" title={selName}>{selName}</span>
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${accent.chip}`}>
                        {isLive ? 'REALE' : mode === 'paper' ? 'SIMULATO' : 'NON NOTA'}
                    </span>
                </div>
                {contesto && (
                    <div className="text-[10px] text-white/60 truncate" title={contesto}>{contesto}</div>
                )}

                {prezzoModificabile && (
                    <div className="block text-[10px] font-bold text-white/70">
                        <label htmlFor="box-ordine-quota">Quota</label>
                        <div className="mt-1 flex items-center gap-1">
                            <button
                                type="button"
                                onClick={() => muoviTick(-1)}
                                aria-label="Quota un tick più bassa"
                                className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-white/15 text-white/80 hover:bg-white/10"
                            ><ChevronDown className="w-3.5 h-3.5" /></button>
                            <input
                                id="box-ordine-quota"
                                type="text"
                                inputMode="decimal"
                                value={prezzoRaw}
                                onChange={(e) => setPrezzoRaw(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') conferma(); }}
                                data-testid="box-ordine-quota"
                                className={`flex-1 min-w-0 rounded-md border bg-white/5 px-2 py-1.5 text-sm font-bold text-white tabular-nums outline-none ${
                                    erroreQuota == null ? 'border-white/20 focus:border-white/50' : 'border-red-500 text-red-300'
                                }`}
                            />
                            <button
                                type="button"
                                onClick={() => muoviTick(1)}
                                aria-label="Quota un tick più alta"
                                className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-white/15 text-white/80 hover:bg-white/10"
                            ><ChevronUp className="w-3.5 h-3.5" /></button>
                        </div>
                        {erroreQuota && (
                            <div className="mt-1 text-[10px] font-semibold text-red-300" data-testid="box-ordine-quota-errore">{erroreQuota}</div>
                        )}
                    </div>
                )}

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
                        onKeyDown={(e) => { if (e.key === 'Enter') conferma(); }}
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
                        disabled={!puoConfermare}
                        onClick={conferma}
                        className={`flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-md text-[11px] font-black disabled:opacity-40 disabled:cursor-not-allowed ${accent.btn}`}
                    >
                        <Check className="w-3 h-3" /> Conferma {isLive ? 'REALE' : mode === 'paper' ? 'simulato' : ''}
                    </button>
                    <button
                        type="button"
                        onClick={onCancel}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-white/15 text-white/80 text-[11px] font-bold hover:bg-white/10"
                    >
                        <X className="w-3 h-3" /> Annulla
                    </button>
                </div>
                {bloccato ? (
                    <div className="text-[10px] font-semibold text-amber-300" role="status" data-testid="box-ordine-bloccato">
                        {bloccato}
                    </div>
                ) : (
                    <div className={`text-[9px] ${accent.text}`}>
                        {isLive
                            ? 'Ordine con SOLDI VERI: verrà inviato a Betfair alla conferma.'
                            : 'Ordine simulato (paper): identico al vivo, ma senza soldi veri.'}
                    </div>
                )}
            </div>
        </div>
    );
}

export default PlaceConfirmDialog;
