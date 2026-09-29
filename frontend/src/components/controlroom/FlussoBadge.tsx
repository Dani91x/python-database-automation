// Cantiere J (28/09/2026): la partita col FLUSSO PREZZI interrotto si vede
// accanto ai prezzi, in rosso, col motivo e da quanto. Componente proprio (il
// resto della scheda non cambia): lo montano Scheda partita e Scheda pre-match.
import type { GiudizioFlusso } from '../../lib/flussoPrezzi';

const CLS: Record<GiudizioFlusso['stato'], string> = {
    interrotto: 'bg-red-500/20 text-red-200 border-red-500/60 animate-pulse',
    senza_prezzi: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    vivo: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
    non_dichiarato: '',
};

/** Niente se i prezzi sono vivi su tutti i mercati o se il dato non c'e'. */
export default function FlussoBadge({ flusso }: { flusso: GiudizioFlusso | null | undefined }) {
    if (!flusso || flusso.stato === 'non_dichiarato') return null;
    if (flusso.stato === 'vivo' && flusso.mercatiFermi === 0) return null;
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
