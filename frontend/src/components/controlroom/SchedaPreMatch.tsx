// ============================================================================
// SchedaPreMatch.tsx — LE PARTITE CHE NON SONO ANCORA COMINCIATE.
//
// «pre-match, tutte le partite che non sono ancora nello stato live, divise
// per campionato e per ordine di orario, prendi lo stile di "omega sezione
// missione" che mi piace dato che ci sono i loghi e gli orari» (utente, 14/09).
//
// LO STILE È QUELLO DI OMEGA, non il codice: in `MissionPanel.tsx` la riga
// partita (`eventRow`) e il logo con fallback (`Logo`) sono funzioni LOCALI,
// non esportate. Riscriverle qui è l'unica strada che non richieda di
// smontare quella pagina — ma le regole restano identiche, loghi compresi
// (`leagueLogo` / `teamLogo` da `lib/sportsLogos.ts`, gli stessi URL).
//
// I LOGHI CI SONO SU CIRCA METÀ DELLE PARTITE: arrivano dall'arricchimento di
// Omega (27 su 55 il 14/09). Dove mancano NON si mette un segnaposto grigio
// che sembra un logo rotto: si mostrano solo i nomi, che è la verità.
//
// SECONDO GIRO (18/09, richiesta utente) — QUOTE PRE-MATCH VIVE, con età, e
// gli ORDINI/POSIZIONI pre-match già piazzati, STESSA riga (`RigaOperazione`,
// `DettaglioRigaView.tsx`) e STESSO ordine dei campi della scheda Live/Aperte
// (mai due scritture della stessa riga in due file, vedi il commento di
// `RigaOperazione`). `operazioni` è OPZIONALE: `ControlRoom.tsx` (fuori dal
// mio perimetro) oggi non la passa a questo componente — vedi il referto per
// la riga esatta da cambiare — ma la scheda è pronta a riceverla, e senza non
// si rompe (nessuna sezione ordini, non un errore).
// ============================================================================
//
// B1 (30/09) — «rendere le quote in tempo reale piu' visibili e da "trader"»
// e «nomi partita diversi [...] uniformare lo stile» (utente, sezioni 4-5):
// i nomi passano da `NomiPartita` e le quote da `QuoteMercato`, gli STESSI
// componenti della scheda in gioco/aperte (`SchedaPartita.tsx`). La funzione
// locale `Squadra` e' traslocata dentro `NomiPartita.tsx` con le stesse regole
// (logo dove c'e', mai un segnaposto che sembri un logo rotto).
// ============================================================================
import { Clock } from 'lucide-react';
import { fmtTime, fmtAge, DASH } from '@/lib/format';
import FlussoBadge, { FlussoLineeMikeBadge } from '@/components/controlroom/FlussoBadge';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import { NomiPartita } from '@/components/controlroom/NomiPartita';
import {
    QuoteMercato, EtaQuote, LineeOu, celleMatchOdds,
} from '@/components/controlroom/QuoteMercato';
import { RigaOperazione } from '@/components/controlroom/DettaglioRigaView';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';

export interface SchedaPreMatchProps {
    p: PartitaGiornata;
    /** la scheda aperta adesso, per tornare esattamente qui */
    scheda: string;
    /** quanto manca al fischio, in secondi; null = orario ignoto */
    mancaS: number | null;
    registra?: boolean | null;
    /** il registratore di questo sport e' vivo? Senza, REC mentirebbe. */
    registratoreVivo?: boolean | null;
    onRegistrazione?: (eventId: string, attiva: boolean) => void;
    /**
     * 18/09 (secondo giro) — ordini/posizioni GIÀ piazzati pre-match su
     * questa partita (ingresso pre-KO, stato dell'ordine). `undefined`/`[]` =
     * nessuna posizione ancora, la sezione non si monta: non è un errore, è
     * la verità di una partita non ancora cominciata. `ControlRoom.tsx` non
     * la passa ancora (fuori perimetro): vedi CHECKPOINT per la riga esatta.
     */
    operazioni?: OperazionePartita[];
}

export function SchedaPreMatch({
    p, scheda, mancaS, registra, registratoreVivo = null, onRegistrazione, operazioni = [],
}: SchedaPreMatchProps) {
    const imminente = mancaS != null && mancaS <= 15 * 60;
    const celle = celleMatchOdds(p.sport, p.odds);
    const haQuote = celle != null;
    const linee = p.lineeOu ?? [];
    // B1bis: nessuna guardia qui, la regola delle linee vive in `LineeOu`
    const haLinee = linee.length > 0;

    return (
        <div
            data-testid="cr-pre-match" data-event-id={p.event_id}
            className={`rounded border border-white/10 border-l-[3px] bg-white/[0.02] px-2.5 py-2 transition-shadow ${
                imminente ? 'border-l-secondary' : 'border-l-white/12'
            }`}
        >
            <div className="flex items-center gap-2">
                {/* ORARIO — è la prima cosa che serve su una lista pre-match */}
                <span className="font-mono text-[12px] tabular-nums text-white/70 w-11 shrink-0"
                    data-testid="cr-pre-orario">
                    {p.koMs == null ? DASH : fmtTime(p.koMs)}
                </span>

                <NomiPartita nome={p.nome}
                    homeTeamId={p.extra?.homeTeamId ?? null} awayTeamId={p.extra?.awayTeamId ?? null} />

                {mancaS != null && (
                    <span className={`shrink-0 text-[10px] font-mono flex items-center gap-1 ${
                        imminente ? 'text-secondary' : 'text-white/35'
                    }`} data-testid="cr-pre-manca"
                        title="quanto manca al fischio d’inizio">
                        <Clock className="w-3 h-3" />fra {fmtAge(mancaS)}
                    </span>
                )}
            </div>

            {/* ── quote pre-match vive, con età (18/09, secondo giro) ── */}
            {(haQuote || haLinee || p.latenzaQuoteS != null || p.flussoMike?.stato === 'fermo') && (
                <div className="mt-1 pl-[52px] text-[10px] space-y-1" data-testid="cr-pre-quote">
                    <div className="flex items-center gap-2 flex-wrap">
                        {celle && (
                            <QuoteMercato testId="cr-pre-quote-mo" celle={celle}
                                titolo="Match Odds: miglior BACK / miglior LAY di adesso" />
                        )}
                        {/* l'età sta ACCANTO alle quote, sempre, e dice cosa misura */}
                        {(haQuote || p.latenzaQuoteS != null) && (
                            <EtaQuote testId="cr-pre-latenza" latenzaS={p.latenzaQuoteS} stato={p.statoQuote} />
                        )}
                        {/* cantiere J (28/09): il flusso dei prezzi della partita.
                            30/09: il Match Odds non ancora seguito prima del fischio
                            e' una nota grigia, non un rosso; le linee di Mike
                            (Under/Over 3,5 e 4,5) hanno il loro giudizio. */}
                        <FlussoBadge flusso={p.flusso} prePartita />
                        <FlussoLineeMikeBadge flusso={p.flussoMike} />
                    </div>
                    {haLinee && <LineeOu testId="cr-pre-quote-ou" linee={linee} />}
                </div>
            )}

            <div className="mt-1.5">
                <AzioniPartita p={p} scheda={scheda} registra={registra}
                    registratoreVivo={registratoreVivo} onRegistrazione={onRegistrazione} />
            </div>

            {/* ── ordini/posizioni GIÀ piazzati pre-match, stessa riga di Live/Aperte ── */}
            {operazioni.length > 0 && (
                <div className="mt-1.5 pt-1.5 border-t border-white/8 space-y-1" data-testid="cr-pre-operazioni">
                    {operazioni.map((o) => (
                        <RigaOperazione key={`${o.bot}-${o.id}`} o={o} />
                    ))}
                </div>
            )}
        </div>
    );
}

export default SchedaPreMatch;
