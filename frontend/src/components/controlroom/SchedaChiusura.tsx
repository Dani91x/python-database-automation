// ============================================================================
// SchedaChiusura.tsx — LA SCHEDA CHE DECIDE UN'USCITA.
//
// Il bot tennis apre da solo; quando matura un'uscita NON la esegue: propone.
// Questa è la scheda su cui il trader dice sì o no, e ogni numero che mostra
// deve essere quello vero **in questo istante**, non quello di quando il bot
// ha deciso.
//
// COSA LA RENDE VIVA: il prezzo e l'importo abbinabile arrivano dal FEED, che
// alla pagina viaggia in push. La proposta conserva solo la FOTOGRAFIA, che
// serve a due cose: sapere su cosa il bot ha deciso, e misurare di quanto il
// mercato si è mosso da allora.
//
// COSA LA RENDE SICURA: non si approva mai al buio. Prezzo assente, età delle
// quote ignota, scostamento oltre la tolleranza, mercato che non abbina quanto
// serve → il bottone si spegne **e dice perché**. In live un ordine che non
// trova controparte viene annullato per intero, e il trader crederebbe di aver
// chiuso una posizione che è ancora aperta.
// ============================================================================
import { useState } from 'react';
import { Loader2, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, fmtAge, DASH } from '@/lib/format';
import { safeExitKindLabel, safeReasonLabel } from '@/components/safestrategy/safeActivity';
import {
    scostamento, motivoNonApprovabile, abbinabileSufficiente,
    type PropostaChiusura, type PrezzoVivo,
} from '@/lib/controlRoomProposte';

/** Oltre questa età le quote non si usano per piazzare. Stessa soglia del
 *  resto della piattaforma (`safeBot.FEED_ROW_STALE_MS`): non se ne inventano. */
export const ETA_QUOTE_MAX_S = 20;

export interface SchedaChiusuraProps {
    proposta: PropostaChiusura;
    /** prezzo e abbinabile CORRENTI, presi dal feed */
    vivo: PrezzoVivo;
    /** età delle quote in secondi; null = non lo sappiamo (fail-closed) */
    etaQuoteS: number | null;
    slippagePct: number;
    /** in LIVE serve la doppia conferma: sono soldi veri */
    onApprova: (id: number) => Promise<void>;
    onIgnora: (id: number) => Promise<void>;
}

export function SchedaChiusura({
    proposta, vivo, etaQuoteS, slippagePct, onApprova, onIgnora,
}: SchedaChiusuraProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);

    const live = p.mode === 'live';
    const lato = p.side ?? null;
    const scost = scostamento({
        prezzoDecisione: p.price_at_decision,
        prezzoCorrente: vivo.prezzo,
        lato, slippagePct,
    });
    const blocco = motivoNonApprovabile({
        scost, etaQuoteS, etaMassimaS: ETA_QUOTE_MAX_S,
        daChiudere: p.size, abbinabileOra: vivo.abbinabile,
    });
    const urgente = p.urgente === true;

    const azione = async (fn: (id: number) => Promise<void>) => {
        setInCorso(true);
        try { await fn(proposta.id); } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                urgente ? 'border-orange-500/50' : 'border-white/10'
            }`}
            data-testid="cr-proposta"
            data-urgente={urgente ? '1' : '0'}
        >
            {/* ---- testata: chi, dove, e se è urgente ---- */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    Safe · uscita {p.strategy ?? ''}
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300">soldi veri</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50">paper</span>}
                {urgente && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300"
                        title="uscita in perdita o obbligatoria: NON approvarla costa">
                        urgente
                    </span>
                )}
                <span className="ml-auto text-[11px] text-white/50 text-right">
                    {p.event_name ?? p.event_id}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                </span>
            </div>

            {/* ---- l'operazione: lato, selezione, prezzo VIVO ---- */}
            <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                <span className={`text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                    lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                }`}>
                    {lato === 'lay' ? 'Banca' : 'Punta'}
                </span>
                <span className="text-[13px] font-semibold">{p.selection_name ?? DASH}</span>
                <span className="ml-auto text-right">
                    <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-prezzo-vivo">
                        {fmtOdds(vivo.prezzo)}
                    </span>
                    <span className={`block font-mono text-[11px] ${
                        scost.delta == null ? 'text-white/40' : scost.controDiNoi ? 'text-orange-400' : 'text-emerald-400'
                    }`} data-testid="cr-scostamento">
                        {scost.delta == null
                            ? 'prezzo corrente non disponibile'
                            : <>
                                {scost.controDiNoi ? <TrendingDown className="w-3 h-3 inline mr-0.5" /> : <TrendingUp className="w-3 h-3 inline mr-0.5" />}
                                proposta a {fmtOdds(p.price_at_decision)}
                              </>}
                    </span>
                </span>
            </div>

            {/* ---- i numeri che decidono ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Da chiudere" valore={fmtMoney(p.size)} />
                <Cella
                    etichetta="Abbinabile ora"
                    valore={vivo.abbinabile == null ? DASH : fmtMoney(vivo.abbinabile)}
                    tono={abbinabileSufficiente(p.size, vivo.abbinabile) ? 'buono' : 'cattivo'}
                />
                <Cella
                    etichetta="Chiudere adesso"
                    valore={p.locked_at_decision == null ? DASH : fmtMoney(p.locked_at_decision)}
                    tono={(p.locked_at_decision ?? 0) >= 0 ? 'buono' : 'cattivo'}
                />
                <Cella
                    etichetta="Tenere"
                    valore={p.hold_profit == null ? DASH : fmtMoney(p.hold_profit)}
                    nota={p.loss_if_lose != null ? `se perde: ${fmtMoney(-Math.abs(p.loss_if_lose))}` : undefined}
                />
            </div>

            {/* ---- perché, in italiano, da UNA sola tabella di traduzione ---- */}
            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                {safeExitKindLabel(p.exit_kind) ?? 'uscita'}
                {p.exit_reason && <> — {safeReasonLabel(p.exit_reason) ?? p.exit_reason}</>}
                <span className="block text-[11px] text-white/40 mt-0.5">
                    ingresso {p.entry_side === 'lay' ? 'banca' : 'punta'} a {fmtOdds(p.entry_price)}
                    {' · '}quote {etaQuoteS == null ? <span className="text-orange-400">età ignota</span> : fmtAge(etaQuoteS)}
                </span>
            </div>

            {/* ---- il blocco, con la RAGIONE: mai un bottone spento e muto ---- */}
            {blocco && (
                <div className="px-3 py-2 bg-orange-500/10 text-orange-300 text-[12px] font-medium border-t border-orange-500/20"
                    data-testid="cr-proposta-bloccata">
                    ⛔ {blocco}
                </div>
            )}

            {/* ---- le due azioni ---- */}
            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void azione(onApprova)} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void azione(onApprova))}
                        disabled={!!blocco || inCorso}
                        className="rounded-none h-10 bg-emerald-600/80 text-white hover:bg-emerald-600 font-bold uppercase tracking-wider text-[12px] disabled:opacity-40"
                        data-testid="cr-approva"
                        title={blocco ?? 'invia l’ordine di chiusura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Chiudi ora'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void azione(onIgnora)} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-ignora"
                >
                    Ignora
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : <>La proposta resta viva finché non chiudi o la ignori. Se la ignori, torna alla prossima occasione.</>}
            </div>

            {urgente && !blocco && (
                <div className="px-3 py-1.5 flex items-start gap-2 text-[11px] text-orange-300 bg-orange-500/5">
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>Uscita del manuale: non approvarla ha un costo, non è una scelta neutra.</span>
                </div>
            )}
        </article>
    );
}

function Cella({ etichetta, valore, tono, nota }: {
    etichetta: string; valore: string; tono?: 'buono' | 'cattivo'; nota?: string;
}) {
    const cls = tono === 'buono' ? 'text-emerald-400' : tono === 'cattivo' ? 'text-orange-400' : '';
    return (
        <div className="bg-background/40 px-3 py-1.5">
            <div className="text-[9px] uppercase tracking-wider text-white/40">{etichetta}</div>
            <div className={`font-mono text-[13px] font-semibold tabular-nums ${cls}`}>{valore}</div>
            {nota && <div className="text-[10px] text-white/40">{nota}</div>}
        </div>
    );
}

export default SchedaChiusura;
