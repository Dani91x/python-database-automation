// ============================================================================
// NomiPartita.tsx — I NOMI DELLA PARTITA, uguali in ogni scheda (B1, 30/09).
//
// «Seychelles v Sri Lanka, nomi partita diversi dalla scheda "pre-match",
// uniformare lo stile» (utente, sezione 5). Prima la pre-partita mostrava due
// righe con i loghi e la scheda in gioco/aperte il nome intero su una riga,
// con corpo e peso diversi: la stessa partita sembrava due cose.
//
// Adesso UN componente per pre-partita, in gioco e aperte:
//   · casa sopra, ospite sotto (`dividiNomi`, la stessa divisione dei pulsanti);
//   · il logo dove c'e' (`teamLogo`, gli URL di Omega). Dove manca, solo il
//     nome: nessun segnaposto che sembri un logo rotto. Lo spazio del logo e'
//     sempre riservato e invisibile (niente bordo, niente fondo), perche' i nomi
//     restino allineati anche fra partite con e senza loghi (B1bis);
//   · un logo che non carica sparisce (stessa regola di prima);
//   · il nome COMPLETO resta accessibile: `title` per chi passa col mouse sopra
//     un nome troncato, e un testo `sr-only` per i lettori di schermo (le due
//     righe visibili sono `aria-hidden`, cosi' il nome si legge una volta sola).
// ============================================================================
import { useState } from 'react';
import { teamLogo } from '@/lib/sportsLogos';
import { dividiNomi } from '@/components/controlroom/AzioniPartita';

export interface NomiPartitaProps {
    /** il nome intero della partita (`PartitaGiornata.nome`) */
    nome: string;
    /** id squadra per il logo (`PartitaGiornata.extra.homeTeamId`); null = nessun logo */
    homeTeamId?: number | null;
    awayTeamId?: number | null;
}

export function NomiPartita({ nome, homeTeamId = null, awayTeamId = null }: NomiPartitaProps) {
    const [casa, ospite] = dividiNomi(nome);
    const srcCasa = homeTeamId != null ? teamLogo(homeTeamId) : '';
    const srcOspite = ospite && awayTeamId != null ? teamLogo(awayTeamId) : '';
    return (
        <div className="flex-1 min-w-0" title={nome} data-testid="cr-nomi-partita">
            <span className="sr-only">{nome}</span>
            <div aria-hidden="true">
                <Squadra nome={casa} src={srcCasa} />
                {ospite && <Squadra nome={ospite} src={srcOspite} />}
            </div>
        </div>
    );
}

/** Una squadra: logo se c'e', nome sempre. B1bis (30/09): lo spazio del logo
 *  e' SEMPRE riservato (invisibile, niente bordo ne' fondo), anche quando
 *  nessuna delle due squadre ha il logo: in una lista mista i nomi partono
 *  tutti dallo stesso punto, come nella pre-partita prima di B1. */
function Squadra({ nome, src }: { nome: string; src: string }) {
    const [rotto, setRotto] = useState(false);
    return (
        <div className="flex items-center gap-1.5 leading-tight min-w-0">
            {src && !rotto ? (
                <img
                    src={src} alt="" width={16} height={16} loading="lazy"
                    onError={() => setRotto(true)}
                    className="w-4 h-4 object-contain shrink-0"
                />
            ) : (
                <span className="w-4 shrink-0" aria-hidden="true" data-testid="cr-logo-vuoto" />
            )}
            <span className="text-[13px] font-medium leading-tight truncate" data-testid="cr-nome-squadra">{nome}</span>
        </div>
    );
}

export default NomiPartita;
