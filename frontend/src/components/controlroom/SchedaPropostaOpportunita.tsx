// ============================================================================
// SchedaPropostaOpportunita.tsx — LA SCHEDA CHE DECIDE UN'APERTURA.
//
// Ordine dell'utente (17/09): «Le opportunita' modello (SIA CALCIO CHE TENNIS)
// devono apparirmi come la card della chiusura, sotto e con card dedicata, con
// TUTTE LE INFORMAZIONI e i due tasti: PIAZZA parte l'ordine, RIFIUTA la
// scheda viene rifiutata.»
//
// Stessa forma della scheda della chiusura (`SchedaChiusura.tsx`), perché è lo
// stesso gesto: il bot ha visto qualcosa, lo mette per iscritto, decide una
// persona. Qui però si APRE una posizione, quindi cambiano i numeri che
// contano: non «chiudere o tenere» ma quanto vale entrare — p del modello
// contro p implicita del mercato, vantaggio, valore atteso, confidenza e il
// perché in parole.
//
// PIAZZA non apre una seconda strada verso Betfair: promuove la riga della
// coda da 'proposed' a 'pending' (RPC `safe_request_approve`) ed è il servizio
// a eseguirla, con le stesse barriere di ogni richiesta manuale. RIFIUTA la
// porta a 'rejected' (`safe_request_ignore`): finché la chiave resta uguale
// quella scheda non torna.
//
// In LIVE il primo clic ARMA e il secondo manda: sono soldi veri.
// ============================================================================
import { useState } from 'react';
import { Loader2, ShieldAlert, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtNum, fmtOdds, fmtPct, fmtAge, DASH } from '@/lib/format';
import type { PropostaOpportunita } from '@/lib/safeBot';

/** Oltre questa età le quote non si usano per piazzare: stessa soglia del
 *  resto della piattaforma (`safeBot.FEED_ROW_STALE_MS`). */
export const ETA_QUOTE_MAX_S = 20;

export interface SchedaPropostaOpportunitaProps {
    proposta: PropostaOpportunita;
    /** importo abbinabile CORRENTE sul lato da operare (dal feed vivo);
     *  null = la fonte non lo pubblica, e allora si dice, non si inventa */
    abbinabileOra?: number | null;
    /** età delle quote in secondi; null = non lo sappiamo (fail-closed) */
    etaQuoteS?: number | null;
    onPiazza: (id: number) => Promise<void>;
    onRifiuta: (id: number) => Promise<void>;
}

// I numeri si formattano da UN solo posto (`@/lib/format`): denaro, quote e
// percentuali hanno gia' la forma italiana decisa per tutta la piattaforma, e
// un `toFixed` scritto a mano qui vorrebbe dire una card che parla una lingua
// diversa dalle altre (`designGuard.test.ts` lo vieta).
const PCT = (v: unknown): string => fmtPct(v as number | null | undefined, 1);
const NUM = (v: unknown, cifre = 3): string => fmtNum(v as number | null | undefined, cifre);

const KIND_IT: Record<string, string> = {
    model: 'modello', tennis: 'modello tennis',
    anomaly: 'anomalia', combo: 'combinazione',
};

/** Perché NON si può firmare adesso. Mai un bottone spento e muto. */
export function motivoNonPiazzabile(p: {
    prezzo: unknown; size: unknown; abbinabileOra: number | null | undefined;
    etaQuoteS: number | null | undefined;
}): string | null {
    const prezzo = Number(p.prezzo);
    if (!Number.isFinite(prezzo) || prezzo <= 1) return 'prezzo della proposta non valido';
    const size = Number(p.size);
    if (!Number.isFinite(size) || size <= 0) return 'importo della proposta non valido';
    if (p.etaQuoteS == null) return 'età delle quote ignota: non si piazza al buio';
    if (p.etaQuoteS > ETA_QUOTE_MAX_S) {
        return `quote vecchie di ${Math.round(p.etaQuoteS)} s: non si piazza al buio`;
    }
    if (p.abbinabileOra != null && p.abbinabileOra <= 0) {
        return 'nessun importo abbinabile al miglior prezzo in questo momento';
    }
    if (p.abbinabileOra != null && size > p.abbinabileOra + 0.005) {
        return `abbinabili solo ${fmtMoney(p.abbinabileOra)}: in LIVE l'ordine è `
            + 'FILL_OR_KILL e verrebbe annullato per intero';
    }
    return null;
}

export function SchedaPropostaOpportunita({
    proposta, abbinabileOra = null, etaQuoteS = null, onPiazza, onRifiuta,
}: SchedaPropostaOpportunitaProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);

    const live = p.mode === 'live';
    const lato = (p.side ?? null) as 'back' | 'lay' | null;
    const blocco = motivoNonPiazzabile({
        prezzo: p.price, size: p.size, abbinabileOra, etaQuoteS,
    });

    const azione = async (fn: (id: number) => Promise<void>) => {
        setInCorso(true);
        try { await fn(proposta.id); } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                live ? 'border-orange-500/40' : 'border-white/10'
            }`}
            data-testid="cr-proposta-opp"
            data-mode={p.mode ?? ''}
        >
            {/* ---- testata: che cos'è, su quale partita, con quali soldi ---- */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    Safe · opportunità {KIND_IT[String(p.kind)] ?? p.kind}
                </span>
                <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/60"
                    data-testid="cr-opp-sport">
                    {p.sport === 'tennis' ? 'tennis' : 'calcio'}
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300" data-testid="cr-opp-modalita">soldi veri · live</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50" data-testid="cr-opp-modalita">paper</span>}
                <span className="ml-auto text-[11px] text-white/50 text-right" data-testid="cr-opp-partita">
                    {p.event_name ?? p.event_id}
                    {p.minute != null && <> · <span className="font-mono">{p.minute}&apos;</span></>}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                </span>
            </div>

            {/* ---- l'operazione: lato, selezione, mercato, prezzo ---- */}
            <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                <span className={`text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                    lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                }`} data-testid="cr-opp-lato">
                    {lato === 'lay' ? 'Banca' : 'Punta'}
                </span>
                <span className="text-[13px] font-semibold" data-testid="cr-opp-selezione">
                    {p.selection_name ?? DASH}
                </span>
                <span className="text-[11px] text-white/45 font-mono" data-testid="cr-opp-mercato">
                    {p.market_type ?? DASH}
                </span>
                <span className="ml-auto text-right">
                    <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-opp-prezzo">
                        {fmtOdds(p.price)}
                    </span>
                    <span className="block font-mono text-[11px] text-white/40">
                        <TrendingUp className="w-3 h-3 inline mr-0.5" />
                        proposta a {fmtOdds(p.price_at_decision)}
                    </span>
                </span>
            </div>

            {p.riproposta_perche && (
                <div className="px-2.5 py-1.5 border-t border-secondary/30 bg-secondary/10 text-[11px] text-secondary"
                    data-testid="cr-opp-riproposta">
                    <strong>Torna:</strong> {p.riproposta_perche}
                </div>
            )}

            {/* ---- i numeri dei soldi ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Stake previsto" valore={fmtMoney(p.size)} testId="cr-opp-stake" />
                <Cella etichetta="Responsabilità"
                    valore={p.liability == null ? DASH : fmtMoney(p.liability)}
                    tono="cattivo" testId="cr-opp-liability" />
                <Cella etichetta="Abbinabile ora"
                    valore={abbinabileOra == null
                        ? (p.size_available == null ? DASH : `${fmtMoney(p.size_available)} (alla proposta)`)
                        : fmtMoney(abbinabileOra)}
                    tono={abbinabileOra != null && Number(p.size) <= abbinabileOra + 0.005 ? 'buono' : undefined}
                    testId="cr-opp-abbinabile" />
                <Cella etichetta="Valore atteso (EV)"
                    valore={NUM(p.ev)} tono={Number(p.ev) > 0 ? 'buono' : 'cattivo'}
                    testId="cr-opp-ev" />
            </div>

            {/* ---- i numeri del modello ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 border-t border-white/5">
                <Cella etichetta="P modello" valore={PCT(p.p_model)} testId="cr-opp-pmodel" />
                <Cella etichetta="P del mercato" valore={PCT(p.p_implied)} testId="cr-opp-pimplied" />
                <Cella etichetta="Vantaggio" valore={NUM(p.edge)} testId="cr-opp-edge" />
                <Cella etichetta="Confidenza" valore={PCT(p.confidence)} testId="cr-opp-confidence" />
            </div>

            {/* ---- perché, in italiano ---- */}
            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                <span data-testid="cr-opp-rationale">{p.rationale ?? 'nessuna spiegazione dal modello'}</span>
                <span className="block text-[11px] text-white/40 mt-0.5" data-testid="cr-opp-eta">
                    quote {etaQuoteS == null ? <span className="text-orange-400">età ignota</span> : fmtAge(etaQuoteS)}
                    {' · '}partirebbe in <b className={live ? 'text-orange-300' : 'text-white/60'}>{String(p.mode ?? 'paper').toUpperCase()}</b>
                </span>
            </div>

            {blocco && (
                <div className="px-3 py-2 bg-orange-500/10 text-orange-300 text-[12px] font-medium border-t border-orange-500/20"
                    data-testid="cr-opp-bloccata">
                    ⛔ {blocco}
                </div>
            )}

            {/* ---- le due azioni ---- */}
            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void azione(onPiazza)} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-opp-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void azione(onPiazza))}
                        disabled={!!blocco || inCorso}
                        className="rounded-none h-10 bg-emerald-600/80 text-white hover:bg-emerald-600 font-bold uppercase tracking-wider text-[12px] disabled:opacity-40"
                        data-testid="cr-opp-piazza"
                        title={blocco ?? 'invia l’ordine di apertura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Piazza'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void azione(onRifiuta)} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-opp-rifiuta"
                >
                    Rifiuta
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : <>Se rifiuti, questa opportunità non torna finché resta la stessa. Nessun ordine parte da solo.</>}
            </div>

            {live && !blocco && (
                <div className="px-3 py-1.5 flex items-start gap-2 text-[11px] text-orange-300 bg-orange-500/5">
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>Apertura con soldi veri: la responsabilità qui sopra è quella che rischi.</span>
                </div>
            )}
        </article>
    );
}

function Cella({ etichetta, valore, tono, testId }: {
    etichetta: string; valore: string; tono?: 'buono' | 'cattivo'; testId?: string;
}) {
    const cls = tono === 'buono' ? 'text-emerald-400' : tono === 'cattivo' ? 'text-orange-400' : '';
    return (
        <div className="bg-background/40 px-3 py-1.5">
            <div className="text-[9px] uppercase tracking-wider text-white/40">{etichetta}</div>
            <div className={`font-mono text-[13px] font-semibold tabular-nums ${cls}`} data-testid={testId}>
                {valore}
            </div>
        </div>
    );
}

export default SchedaPropostaOpportunita;
