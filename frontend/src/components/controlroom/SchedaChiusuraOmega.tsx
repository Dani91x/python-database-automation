// ============================================================================
// SchedaChiusuraOmega.tsx — LA SCHEDA CHE DECIDE UN'USCITA DI OMEGA.
//
// Stessa forma della scheda della Safe (`SchedaChiusura.tsx`), perché è lo
// stesso gesto: il bot propone, l'utente decide. Quello che cambia sono i
// numeri, perché Omega banca un risultato e non punta una squadra:
//   · **profitto bloccabile** — EUR netti, uguali in ogni esito, se si chiude ORA;
//   · **EV di tenere** — quanto vale portarla al settlement con la P di adesso;
//   · **la traiettoria** — se il punteggio regge, quanto si bloccherebbe più
//     avanti e a che minuto. È la ragione per cui una proposta può NON partire.
//
// LA MEMORIA (12/09): su un lay la liability è già impegnata. Chiudere sotto
// l'EV non riduce il rischio: lo trasforma in perdita certa. Per questo la
// scheda mostra i tre numeri insieme, e non solo quello che fa comodo.
//
// IN LIVE SERVE LA DOPPIA CONFERMA.
// ============================================================================
import { useState } from 'react';
import { Loader2, Hourglass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, fmtPctPoints, fmtTime, DASH } from '@/lib/format';
import {
    motivoNonApprovabileOmega, motivoUscitaOmegaLabel,
    type PropostaUscitaOmega,
} from '@/lib/omegaProposte';

export interface SchedaChiusuraOmegaProps {
    proposta: PropostaUscitaOmega;
    onApprova: (id: number) => Promise<void>;
    onIgnora: (id: number) => Promise<void>;
}

export function SchedaChiusuraOmega({ proposta, onApprova, onIgnora }: SchedaChiusuraOmegaProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);
    const [errore, setErrore] = useState<string | null>(null);

    const live = p.mode === 'live';
    const blocco = motivoNonApprovabileOmega(p);
    const bloccabile = p.profitto_bloccabile == null ? null : Number(p.profitto_bloccabile);
    const evTenere = p.ev_tenere == null ? null : Number(p.ev_tenere);
    const aspetta = p.meglio_aspettare === true;

    const azione = async (fn: (id: number) => Promise<void>) => {
        setInCorso(true);
        setErrore(null);
        try { await fn(proposta.id); } catch (e) {
            // migrazione non applicata → la RPC non esiste: si mostra, non si nasconde
            setErrore(e instanceof Error ? e.message : String(e));
        } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                blocco ? 'border-white/10' : 'border-primary/40'
            }`}
            data-testid="cr-proposta-omega"
            data-approvabile={blocco ? '0' : '1'}
        >
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-primary">
                    Omega · uscita
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300">soldi veri</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50">paper</span>}
                {aspetta && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300"
                        title="se il punteggio regge, piu’ avanti si bloccherebbe di piu’">
                        <Hourglass className="w-2.5 h-2.5 inline mr-0.5" />aspettare puo’ valere di piu’
                    </span>
                )}
                <span className="ml-auto text-[11px] text-white/50 text-right">
                    {p.event_name ?? p.event_id}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                    {p.minute != null && <> · <span className="font-mono">{Math.round(Number(p.minute))}′</span></>}
                </span>
            </div>

            <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded bg-sky-500/15 text-sky-300">
                    Punta per chiudere
                </span>
                <span className="text-[13px] font-semibold">{p.selection_name ?? DASH}</span>
                <span className="ml-auto text-right">
                    <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-omega-back-price">
                        {fmtOdds(p.back_price)}
                    </span>
                    <span className="block font-mono text-[11px] text-white/45" data-testid="cr-omega-back-size">
                        per {p.back_size == null ? DASH : fmtMoney(p.back_size)}
                        {p.price_at_decision != null && <> · bancata a {fmtOdds(p.entry_price)}</>}
                    </span>
                </span>
            </div>

            {/* ---- i tre numeri che decidono, insieme ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Blocchi adesso"
                    valore={bloccabile == null ? DASH : fmtMoney(bloccabile, { signed: true })}
                    tono={bloccabile == null ? undefined : bloccabile > 0 ? 'buono' : 'cattivo'} />
                <Cella etichetta="Tenere vale"
                    valore={evTenere == null ? DASH : fmtMoney(evTenere, { signed: true })}
                    nota={p.p_evento == null ? undefined
                        : `P che il risultato esca ${fmtPctPoints(Number(p.p_evento) * 100, 2)}`} />
                <Cella etichetta="Se il punteggio regge"
                    valore={p.bloccabile_max_atteso == null ? DASH : fmtMoney(Number(p.bloccabile_max_atteso), { signed: true })}
                    nota={p.minuto_del_massimo == null ? undefined
                        : `al ${Math.round(Number(p.minuto_del_massimo))}′`} />
                <Cella etichetta="Controparte alla decisione"
                    valore={p.size_available_at_decision == null ? DASH : fmtMoney(Number(p.size_available_at_decision))}
                    nota={p.decided_at ? `decisa alle ${fmtTime(p.decided_at)}` : 'istante non dichiarato'} />
            </div>

            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                {motivoUscitaOmegaLabel(p.motivo_codice) ?? 'motivo non dichiarato'}
                <span className="block text-[11px] text-white/40 mt-0.5">
                    aggiornata {p.proposed_at ? `alle ${fmtTime(p.proposed_at)}` : DASH}
                    {' · '}il prezzo su cui si piazza lo guardi tu, vivo, un istante prima
                </span>
            </div>

            {blocco && (
                <div className="px-3 py-2 bg-orange-500/10 text-orange-300 text-[12px] font-medium border-t border-orange-500/20"
                    data-testid="cr-proposta-omega-bloccata">
                    ⛔ {blocco}
                </div>
            )}

            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void azione(onApprova)} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-omega-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void azione(onApprova))}
                        disabled={!!blocco || inCorso}
                        className="rounded-none h-10 bg-emerald-600/80 text-white hover:bg-emerald-600 font-bold uppercase tracking-wider text-[12px] disabled:opacity-40"
                        data-testid="cr-omega-approva"
                        title={blocco ?? 'invia l’ordine di chiusura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Chiudi ora'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void azione(onIgnora)} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-omega-ignora"
                >
                    Ignora
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : <>Nessuna chiusura parte da sola: la proposta resta viva finché non decidi. Se la ignori, torna alla prossima occasione.</>}
            </div>

            {errore && (
                <div className="px-3 py-1.5 text-[11px] text-red-300 bg-red-500/10"
                    data-testid="cr-proposta-omega-errore">
                    ⛔ il servizio ha rifiutato: {errore}
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

export default SchedaChiusuraOmega;
