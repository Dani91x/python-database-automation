// ============================================================================
// StrisciaEsitoChiusura.tsx — LA STRISCIA DI ESITO dopo un'approvazione.
//
// Ordine dell'utente, 18/09: dopo che il trader approva un'uscita o un cash
// out, la scheda deve seguire la chiusura FINO ALLA VERITÀ — «inviata → a
// mercato → abbinata X/Y → CHIUSA CONFERMATA» / «PARZIALE: restano X € esposti»
// / «FALLITA: posizione ancora aperta» — non fermarsi all'invio dell'ordine.
//
// COMPONENTE ADDITIVO: si monta in coda a `SchedaChiusura.tsx`,
// `SchedaChiusuraOmega.tsx` e `CashOutPartita.tsx` con una prop OPZIONALE
// (`esito`). Se il chiamante non la passa, il componente non renderizza
// NIENTE: nessuna modifica al testo, ai colori o alle azioni esistenti.
//
// NESSUNA LETTURA NUOVA, NESSUNA FORMULA NUOVA: prende `apertura`/`chiusure`
// così come sono GIÀ in memoria nella pagina chiamante (le stesse righe che
// alimentano `lib/posizioniChiuse.ts` o gli eventi realtime già sottoscritti
// dalla Control Room) e delega il giudizio a `lib/certezzaChiusura.ts` — la
// STESSA funzione usata dalla tab «Chiuse»: un'operazione ha lo stesso
// giudizio dovunque compaia.
// ============================================================================
import { Loader2 } from 'lucide-react';
import { fmtMoney, fmtAge, DASH } from '@/lib/format';
import { etaBetfairSec, statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import {
    certezzaChiusura, eCertezzaVerde, eCertezzaAllarme,
    type StatoCertezzaChiusura,
} from '@/lib/certezzaChiusura';

/** Etichetta di ogni PASSO del percorso, per la striscia: le stesse sei parole
 *  del badge di `PosizioniChiuse.tsx` (nessuna seconda traduzione). */
const PASSO: Record<StatoCertezzaChiusura, string> = {
    CHIUSA_CONFERMATA: 'CHIUSA · CONFERMATA',
    REGOLATA_DAL_MERCATO: 'REGOLATA DAL MERCATO',
    CHIUSA_PARZIALE: 'PARZIALE: resta esposizione',
    CHIUSURA_IN_ATTESA: 'A MERCATO: in attesa di abbinamento',
    CHIUSURA_FALLITA: 'FALLITA: posizione ANCORA APERTA',
    NON_VERIFICABILE: 'NON VERIFICABILE',
};

function classeDiStato(stato: StatoCertezzaChiusura): string {
    if (eCertezzaVerde(stato)) return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
    if (stato === 'CHIUSURA_FALLITA') return 'text-red-300 bg-red-500/10 border-red-500/30';
    return 'text-orange-300 bg-orange-500/10 border-orange-500/30'; // parziale/attesa/non verificabile
}

export interface StrisciaEsitoChiusuraProps {
    /** l'apertura che si sta chiudendo: side/size/prezzo di riferimento (già in memoria) */
    apertura: RigaOrdine | null | undefined;
    /** le gambe di chiusura nate da QUESTA azione, così come arrivano dalla
     *  pagina chiamante (righe già caricate o aggiornate da realtime) */
    chiusure: readonly RigaOrdine[];
    /** true = l'apertura (e tutte le sue chiusure) sono REGOLATE dal mercato */
    regolataDalMercato?: boolean;
    modo: 'paper' | 'live';
    /**
     * true = l'azione è stata appena mandata (clic su Approva/Cash out) ma
     * nessuna riga di chiusura è ancora arrivata: si dice "inviata", non
     * "non verificabile" — sono due cose diverse (attesa vs dati mancanti).
     */
    inviata?: boolean;
    nowMs?: number;
    testId?: string;
}

/**
 * La striscia. Non renderizza NIENTE se non c'è ancora nessuna gamba di
 * chiusura e l'azione non è stata dichiarata "appena inviata": un montaggio
 * senza dati non deve aggiungere una riga vuota alle schede esistenti.
 */
export function StrisciaEsitoChiusura({
    apertura, chiusure, regolataDalMercato = false, modo, inviata = false,
    nowMs, testId = 'striscia-esito-chiusura',
}: StrisciaEsitoChiusuraProps) {
    if (!apertura) return null;

    if (chiusure.length === 0 && !regolataDalMercato) {
        if (!inviata) return null;
        return (
            <div
                className="px-3 py-1.5 text-[10.5px] text-white/55 border-t border-white/10 flex items-center gap-1.5"
                data-testid={testId}
                data-passo="inviata"
            >
                <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                inviata → in attesa che il servizio scriva l&apos;ordine di chiusura…
            </div>
        );
    }

    const r = certezzaChiusura({ apertura, chiusure, regolataDalMercato, modo });

    // età dell'ultima notizia DA BETFAIR sulla gamba di chiusura più recente
    // (stesso strumento di `StatoOrdineRiga`: nessuna seconda formula per l'età)
    const ultima = chiusure[chiusure.length - 1];
    const eta = ultima && nowMs != null ? etaBetfairSec(statoOrdine(ultima), nowMs) : null;

    const esposta = r.esposizione.stake != null && r.esposizione.stake > 0.005;

    return (
        <div
            className={`px-3 py-1.5 text-[10.5px] border-t flex items-center gap-2 flex-wrap ${classeDiStato(r.stato)}`}
            data-testid={testId}
            data-stato={r.stato}
            data-allarme={eCertezzaAllarme(r.stato) ? '1' : undefined}
            role={r.stato === 'CHIUSURA_FALLITA' ? 'alert' : undefined}
            title={r.motivo}
        >
            <span className="font-bold uppercase tracking-wider" data-testid={`${testId}-badge`}>
                {PASSO[r.stato]}
            </span>
            {r.coperturaFrazione != null && r.coperturaFrazione < 1 && (
                <span className="font-mono tabular-nums">{Math.round(r.coperturaFrazione * 100)}% abbinato</span>
            )}
            {esposta && (
                <span className="font-mono tabular-nums font-bold" data-testid={`${testId}-esposizione`}>
                    ancora esposti {fmtMoney(r.esposizione.stake)}
                </span>
            )}
            <span className="text-white/40" data-testid={`${testId}-motivo`}>{r.motivo}</span>
            {eta != null && (
                <span className="ml-auto text-white/35 font-mono" data-testid={`${testId}-eta`}>
                    da Betfair {fmtAge(eta)} fa
                </span>
            )}
            {eta == null && ultima && (
                <span className="ml-auto text-white/35" data-testid={`${testId}-eta`}>{DASH}</span>
            )}
        </div>
    );
}

export default StrisciaEsitoChiusura;
