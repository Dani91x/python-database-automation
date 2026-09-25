// ============================================================================
// Etichetta unica "aggiornato al ... (eta')" per tutte le tab della Dashboard
// (reperto R5, 25/09/2026). Verde se il dato e' entro la soglia, ROSSO se e'
// piu' vecchio o se manca. Logica in lib/etaDato.ts.
// ============================================================================
import { calcolaEta, formatEta } from '@/lib/etaDato';

interface Props {
    etichetta: string;                 // cosa e' il dato: "Previsione", "Pagella", ...
    at: string | null | undefined;     // timestamp ISO del dato materializzato
    sogliaOre: number;                 // oltre -> rosso
    testoAssente?: string;             // cosa dire quando il dato manca
    now?: Date;                        // solo per i test (default: adesso)
    testId?: string;
}

export function EtaDato({ etichetta, at, sogliaOre, testoAssente, now, testId }: Props) {
    const e = calcolaEta(at, sogliaOre, now);
    const colore = e.stato === 'fresco' ? 'text-emerald-400' : 'text-red-400 font-bold';
    return (
        <span data-testid={testId ?? 'eta-dato'} data-stato={e.stato} className={`text-[11px] ${colore}`}>
            {e.stato === 'assente'
                ? <>{etichetta}: {testoAssente ?? 'data non disponibile'}</>
                : <>
                    {etichetta}: aggiornato al {e.testoData} ({e.testoEta} fa)
                    {e.stato === 'vecchio' && <> &middot; oltre {formatEta(sogliaOre)}</>}
                </>}
        </span>
    );
}
