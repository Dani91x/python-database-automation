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
// ============================================================================
import { useState } from 'react';
import { Clock } from 'lucide-react';
import { fmtTime, fmtAge, DASH } from '@/lib/format';
import { teamLogo } from '@/lib/sportsLogos';
import { dividiNomi } from '@/components/controlroom/AzioniPartita';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import type { PartitaGiornata } from '@/lib/controlRoom';

export interface SchedaPreMatchProps {
    p: PartitaGiornata;
    /** la scheda aperta adesso, per tornare esattamente qui */
    scheda: string;
    /** quanto manca al fischio, in secondi; null = orario ignoto */
    mancaS: number | null;
    registra?: boolean | null;
    onRegistrazione?: (eventId: string, attiva: boolean) => void;
}

export function SchedaPreMatch({ p, scheda, mancaS, registra, onRegistrazione }: SchedaPreMatchProps) {
    const [casa, ospite] = dividiNomi(p.nome);
    const imminente = mancaS != null && mancaS <= 15 * 60;

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

                <div className="flex-1 min-w-0">
                    <Squadra nome={casa} teamId={p.extra?.homeTeamId ?? null} />
                    {ospite && <Squadra nome={ospite} teamId={p.extra?.awayTeamId ?? null} />}
                </div>

                {mancaS != null && (
                    <span className={`shrink-0 text-[10px] font-mono flex items-center gap-1 ${
                        imminente ? 'text-secondary' : 'text-white/35'
                    }`} data-testid="cr-pre-manca"
                        title="quanto manca al fischio d’inizio">
                        <Clock className="w-3 h-3" />fra {fmtAge(mancaS)}
                    </span>
                )}
            </div>

            <div className="mt-1.5">
                <AzioniPartita p={p} scheda={scheda} registra={registra} onRegistrazione={onRegistrazione} />
            </div>
        </div>
    );
}

/** Una squadra: logo se c'è, nome sempre. Un logo che non carica sparisce —
 *  non lascia un quadrato grigio che sembra un errore della pagina. */
function Squadra({ nome, teamId }: { nome: string; teamId: number | null }) {
    const [rotto, setRotto] = useState(false);
    const src = teamId != null ? teamLogo(teamId) : '';
    return (
        <div className="flex items-center gap-1.5 leading-tight">
            {src && !rotto ? (
                <img
                    src={src} alt="" width={16} height={16} loading="lazy"
                    onError={() => setRotto(true)}
                    className="w-4 h-4 object-contain shrink-0"
                />
            ) : (
                <span className="w-4 shrink-0" aria-hidden="true" />
            )}
            <span className="text-[12.5px] truncate">{nome}</span>
        </div>
    );
}

export default SchedaPreMatch;
