// ============================================================================
// CashOutPartita.tsx — «CASH OUT GLOBALE DELLA PARTITA» e «RIPRENDI».
//
// Ordine dell'utente del 16/09 sera: «se chiudo io il bot deve saperlo e non
// fare altro». Questo e' il gesto con cui glielo si dice, e il gesto opposto
// con cui gli si ridà la partita.
//
// COSA FA, esattamente:
//   · «Cash out globale della partita» → `safe_request('cashout_event',
//     {event_id})`. Il payload porta SOLO l'event_id: quali righe chiudere lo
//     decide il servizio leggendo le SUE tabelle (la pagina non sceglie cosa
//     chiudere, sceglie CHE si chiude tutto).
//   · «Riprendi» → `safe_request('riprendi_evento', {event_id})`.
//
// COSA NON FA: non apre una seconda strada verso Betfair (e' la coda di
// sempre), non deduce lo stato (lo legge da `meta.chiuso_dall_utente`, che
// scrive il servizio) e non nasconde un errore. Se la migrazione del 16/09 non
// e' applicata, la RPC risponde «kind non valido» e quella frase si legge qui.
//
// IN LIVE SERVE LA DOPPIA CONFERMA: chiudere tutta una partita con soldi veri
// non e' un clic solo. Stessa forma del cancelletto delle uscite
// (`SchedaChiusura`): primo clic arma, secondo manda.
// ============================================================================
import { useState } from 'react';
import { Loader2, Undo2, XOctagon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtTime } from '@/lib/format';
import {
    comeLabel, motivoCashoutSpento, motivoRiprendiSpento,
    type StatoChiusuraEvento,
} from '@/lib/chiusuraUtente';

export interface CashOutPartitaProps {
    eventId: string;
    /** con che soldi opera il bot su questa partita; null = non dichiarata */
    modalita: 'paper' | 'live' | null;
    /** quante posizioni del bot sono ancora vive qui */
    posizioniVive: number;
    stato: StatoChiusuraEvento;
    onCashOut: (eventId: string) => Promise<void>;
    onRiprendi: (eventId: string) => Promise<void>;
    /** riga compatta dentro la scheda partita della Control Room */
    compatto?: boolean;
}

export function CashOutPartita({
    eventId, modalita, posizioniVive, stato, onCashOut, onRiprendi, compatto = false,
}: CashOutPartitaProps) {
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);
    const [errore, setErrore] = useState<string | null>(null);

    // FAIL-CLOSED: una modalita' non dichiarata NON vale «paper». Ai soldi veri
    // si arriva scrivendolo, ma alla doppia conferma si arriva anche per dubbio:
    // chiedere una conferma di troppo non ha mai chiuso una posizione sbagliata.
    const chiedeConferma = modalita !== 'paper';

    const bloccoCashout = motivoCashoutSpento({
        eventId, posizioniVive, chiusa: stato.chiusa, inCorso,
    });
    const bloccoRiprendi = motivoRiprendiSpento({ eventId, chiusa: stato.chiusa, inCorso });

    const esegui = async (fn: (id: string) => Promise<void>) => {
        setInCorso(true);
        setErrore(null);
        try {
            await fn(eventId);
        } catch (e) {
            // NON si nasconde: se la migrazione non e' applicata la RPC dice
            // «kind non valido: cashout_event», ed e' esattamente l'informazione
            // che serve a chi guarda.
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setInCorso(false);
            setArmato(false);
        }
    };

    const dim = compatto ? 'h-6 text-[10px] px-2' : 'h-8 text-[11px] px-3';

    return (
        <div className="flex items-center gap-1.5 flex-wrap" data-testid="cr-cashout-partita"
            data-event-id={eventId} data-chiusa={stato.chiusa ? '1' : '0'}>
            {stato.chiusa && (
                <span
                    className="text-[9.5px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    data-testid="cr-badge-chiusa-da-te"
                    title={[
                        comeLabel(stato.marcatore?.come) ?? 'chiusa da te',
                        stato.marcatore?.quando ? `alle ${fmtTime(stato.marcatore.quando)}` : 'istante non dichiarato',
                        stato.fonte === 'servizio'
                            ? 'dichiarata dal servizio'
                            : 'marcatore scritto sulle righe dal servizio',
                    ].join(' · ')}
                >
                    chiusa da te
                </span>
            )}

            {!stato.chiusa && (
                armato ? (
                    <Button
                        onClick={() => void esegui(onCashOut)} disabled={inCorso}
                        className={`${dim} rounded bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider`}
                        data-testid="cr-cashout-partita-conferma"
                    >
                        {inCorso ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Confermo: chiudi tutta la partita'}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (chiedeConferma ? setArmato(true) : void esegui(onCashOut))}
                        disabled={!!bloccoCashout}
                        variant="outline"
                        className={`${dim} rounded border-rose-500/40 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20 font-semibold uppercase tracking-wider disabled:opacity-40`}
                        data-testid="cr-cashout-partita-avvia"
                        title={bloccoCashout ?? 'chiude TUTTE le posizioni del bot su questa partita e gli dice di non fare altro'}
                    >
                        {inCorso
                            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            : <><XOctagon className="w-3 h-3 mr-1" />Cash out globale della partita</>}
                    </Button>
                )
            )}

            {armato && (
                <span className="text-[10px] text-orange-300" data-testid="cr-cashout-partita-armato">
                    {modalita === 'live'
                        ? 'Sono soldi veri: conferma per chiudere tutta la partita.'
                        : 'Modalita’ non dichiarata: si chiede conferma comunque.'}
                    {' '}
                    <button type="button" className="underline" onClick={() => setArmato(false)}
                        data-testid="cr-cashout-partita-annulla">annulla</button>
                </span>
            )}

            {stato.chiusa && (
                <Button
                    onClick={() => void esegui(onRiprendi)} disabled={!!bloccoRiprendi}
                    variant="ghost"
                    className={`${dim} rounded text-white/70 hover:text-white uppercase tracking-wider disabled:opacity-40`}
                    data-testid="cr-riprendi-partita"
                    title={bloccoRiprendi ?? 'riporta la partita in carico al bot: e’ l’unico modo di togliere il marcatore'}
                >
                    {inCorso
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <><Undo2 className="w-3 h-3 mr-1" />Riprendi</>}
                </Button>
            )}

            {/* un pulsante spento dice PERCHE': mai un `disabled` muto */}
            {bloccoCashout && !stato.chiusa && !armato && (
                <span className="text-[10px] text-white/40" data-testid="cr-cashout-partita-bloccato">
                    {bloccoCashout}
                </span>
            )}

            {errore && (
                <span className="text-[10px] text-red-300 w-full" data-testid="cr-cashout-partita-errore">
                    ⛔ il servizio ha rifiutato: {errore}
                </span>
            )}
        </div>
    );
}

export default CashOutPartita;
