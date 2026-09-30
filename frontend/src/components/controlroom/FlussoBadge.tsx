// Cantiere J (28/09/2026): la partita col FLUSSO PREZZI interrotto si vede
// accanto ai prezzi, in rosso, col motivo e da quanto. Componente proprio (il
// resto della scheda non cambia): lo montano Scheda partita e Scheda pre-match.
import {
    moNonAncoraRicevuto, type GiudizioFlusso, type GiudizioFlussoMike,
} from '../../lib/flussoPrezzi';

const CLS: Record<GiudizioFlusso['stato'], string> = {
    interrotto: 'bg-red-500/20 text-red-200 border-red-500/60 animate-pulse',
    senza_prezzi: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    vivo: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
    non_dichiarato: '',
};

/** Niente se i prezzi sono vivi su tutti i mercati o se il dato non c'e'.
 *  30/09 - `prePartita`: prima del fischio il Match Odds "mai ricevuto" non e'
 *  un flusso interrotto (lo scanner non lo segue ancora): nota grigia, niente
 *  rosso e niente contatore. Senza `prePartita` (scheda in gioco) identico. */
export default function FlussoBadge({ flusso, prePartita = false }: {
    flusso: GiudizioFlusso | null | undefined;
    prePartita?: boolean;
}) {
    if (!flusso || flusso.stato === 'non_dichiarato') return null;
    if (flusso.stato === 'vivo' && flusso.mercatiFermi === 0) return null;
    if (prePartita && moNonAncoraRicevuto(flusso)) {
        return (
            <span
                className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 text-white/40"
                data-testid="cr-flusso"
                data-stato="mo_non_ricevuto"
                title={'Prima del fischio lo scanner legge il Match Odds solo negli ultimi 20 minuti '
                    + '(o in gioco): finora nessun prezzo ricevuto. Non riguarda le linee Under/Over '
                    + 'di Mike, che hanno il loro flusso.'}
            >
                Match Odds: prezzi non ancora ricevuti
            </span>
        );
    }
    return (
        <span
            className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border ${CLS[flusso.stato]}`}
            data-testid="cr-flusso"
            data-stato={flusso.stato}
            title={flusso.testo}
        >
            {flusso.stato === 'interrotto' && '⚠ FLUSSO PREZZI INTERROTTO'}
            {flusso.stato === 'senza_prezzi' && 'SENZA PREZZI'}
            {flusso.stato === 'vivo' && `${flusso.mercatiFermi} mercati col flusso fermo`}
            {flusso.stato !== 'vivo' && flusso.daS != null && ` · ${Math.round(flusso.daS)} s`}
        </span>
    );
}

/** 30/09 - le LINEE DI MIKE (Under/Over 3,5 e 4,5) col flusso fermo: QUALE
 *  linea e l'eta' del suo ultimo book. Niente se sono vive o se la riga non le
 *  porta. */
export function FlussoLineeMikeBadge({ flusso }: { flusso: GiudizioFlussoMike | null | undefined }) {
    if (!flusso || flusso.stato !== 'fermo') return null;
    return (
        <span
            className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border ${CLS.interrotto}`}
            data-testid="cr-flusso-mike"
            data-stato="fermo"
            title={flusso.testo}
        >
            {'⚠ '}
            {flusso.linee.map((l) => `${l.nome} ferma`
                + (l.daS == null ? '' : (l.esatto ? ` · ultimo prezzo ${Math.round(l.daS)} s fa` : ` · riga scritta ${Math.round(l.daS)} s fa`))).join(' · ')}
        </span>
    );
}
