// ============================================================================
// StatoOrdine.tsx — LA RIGA «stato dell'ordine», uguale in tutte le sezioni.
//
// Risponde alla domanda dell'utente del 16/09 su OGNI riga ordine di Omega,
// Safe, Mike e della Control Room: «ordine x a prezzo y: abbinato? in che
// quantita'? tutto o parziale?» — e aggiunge le due cose che mancavano
// dappertutto: il RESIDUO ancora vivo sul book e QUANDO l'abbiamo saputo da
// Betfair.
//
// La logica sta in `lib/statoOrdine.ts` (pura, testata a parte): qui c'e' solo
// la resa. Due forme:
//   · <StatoOrdineRiga>      griglia completa (Omega, Safe, Mike)
//   · <StatoOrdineCompatto>  una riga sola (Control Room, liste dense)
//
// REGOLE: solo `fmtMoney`/`fmtOdds`/`fmtAge` (mai `toFixed`), «—» per il dato
// assente (mai «0,00 €»), e il badge «dalla nota» quando un numero non viene
// dalle colonne ma dal `meta` del servizio: un ripiego dichiarato non e' un
// numero inventato.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { fmtAge, DASH } from '@/lib/format';
import {
    statoOrdine, etaBetfairSec, valoreMoney, valoreOdds, valoreTicks,
    statoOrdineTesto, statoOrdineTitolo,
    type RigaOrdine, type StatoOrdine, type ValoreOrdine,
} from '@/lib/statoOrdine';

/** badge «dalla nota»: il numero c'e', ma non arriva dalle colonne di Betfair */
const CLS_NOTA = 'bg-white/5 text-slate-400 border-white/10';

function Nota({ v }: { v: ValoreOrdine }) {
    if (v.fonte !== 'nota') return null;
    return (
        <span
            className="ml-0.5 text-[9px] text-slate-500"
            data-testid="stato-ordine-nota"
            title="numero preso dalla nota del servizio (meta), non dalle colonne di Betfair: la migrazione trades_consapevolezza_ordine_2026-09-16.sql non risulta applicata"
        >*</span>
    );
}

interface Props {
    riga: RigaOrdine | null | undefined;
    /** istante corrente in ms: serve per l'eta' dell'ultima notizia da Betfair */
    nowMs?: number;
    className?: string;
    testId?: string;
}

/**
 * Griglia completa: chiesto · abbinato · residuo · stato · ultimo aggiornamento.
 * Un ordine APPOGGIATO non e' «aperto»: l'etichetta lo dice con parole sue.
 */
export function StatoOrdineRiga({ riga, nowMs, className = '', testId = 'stato-ordine' }: Props) {
    const s = statoOrdine(riga);
    const eta = nowMs != null ? etaBetfairSec(s, nowMs) : null;
    const titolo = statoOrdineTitolo(s);
    return (
        <div
            className={`text-[11px] tabular-nums flex flex-wrap items-center gap-x-2 gap-y-0.5 ${className}`}
            data-testid={testId}
            data-esito={s.esito}
            data-dalla-nota={s.dallaNota ? '1' : undefined}
            title={titolo}
        >
            <Badge
                variant="outline"
                data-testid={`${testId}-badge`}
                className={`whitespace-nowrap px-1.5 py-0 text-[10px] ${s.meta.cls}`}
            >{s.meta.label}</Badge>
            <span className="text-slate-400" data-testid={`${testId}-chiesto`}>
                chiesto <b className="text-slate-200">{valoreMoney(s.chiesto)}</b><Nota v={s.chiesto} />
                {s.prezzoChiesto.valore !== null && (
                    <span className="text-slate-500"> @{valoreOdds(s.prezzoChiesto)}</span>
                )}
            </span>
            <span className="text-slate-400" data-testid={`${testId}-abbinato`}>
                abbinato <b className="text-emerald-300">{valoreMoney(s.abbinato)}</b><Nota v={s.abbinato} />
                <span className="text-slate-500"> @{valoreOdds(s.prezzoMedio)}</span><Nota v={s.prezzoMedio} />
            </span>
            <span className="text-slate-400" data-testid={`${testId}-residuo`}>
                residuo <b className="text-amber-200">{valoreMoney(s.residuo)}</b><Nota v={s.residuo} />
            </span>
            {s.scorrimento.valore !== null && (
                <span className="text-slate-500" data-testid={`${testId}-scorrimento`}
                    title="differenza fra il prezzo chiesto e il prezzo medio davvero abbinato">
                    scorrimento {valoreTicks(s.scorrimento)}
                </span>
            )}
            <span
                className="text-slate-500"
                data-testid={`${testId}-eta`}
                title="da quanto tempo non abbiamo notizie di questo ordine DA BETFAIR (non l'ora del nostro processo)"
            >
                da Betfair {eta != null ? fmtAge(eta) : DASH} fa
            </span>
            {s.dallaNota && (
                <Badge
                    variant="outline"
                    data-testid={`${testId}-badge-nota`}
                    className={`whitespace-nowrap px-1 py-0 text-[9px] ${CLS_NOTA}`}
                    title="almeno un numero viene dalla nota del servizio (meta) e non dalle colonne: e' un ripiego dichiarato, non un dato di Betfair"
                >dalla nota</Badge>
            )}
        </div>
    );
}

/** Una riga sola: «chiesti 5,00 € @2,40 · abbinati 2,00 € @2,38 · residuo 3,00 €». */
export function StatoOrdineCompatto({ riga, className = '', testId = 'stato-ordine-compatto' }: Props) {
    const s = statoOrdine(riga);
    return (
        <span
            className={`text-[10px] tabular-nums text-white/45 ${className}`}
            data-testid={testId}
            data-esito={s.esito}
            data-dalla-nota={s.dallaNota ? '1' : undefined}
            title={statoOrdineTitolo(s)}
        >
            {statoOrdineTesto(s)}
            {s.dallaNota && <span className="text-white/25" title="numeri dalla nota del servizio"> *</span>}
        </span>
    );
}

export type { StatoOrdine };
export default StatoOrdineRiga;
