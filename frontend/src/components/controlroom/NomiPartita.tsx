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
//     nome: nessun segnaposto che sembri un logo rotto. Se UNA sola squadra ha
//     il logo, l'altra riga ha uno spazio vuoto invisibile (niente bordo, niente
//     fondo) perche' i due nomi restino allineati;
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
    // lo spazio del logo esiste solo se almeno UNA squadra ha un logo
    const conLoghi = Boolean(srcCasa || srcOspite);
    return (
        <div className="flex-1 min-w-0" title={nome} data-testid="cr-nomi-partita">
            <span className="sr-only">{nome}</span>
            <div aria-hidden="true">
                <Squadra nome={casa} src={srcCasa} conLoghi={conLoghi} />
                {ospite && <Squadra nome={ospite} src={srcOspite} conLoghi={conLoghi} />}
            </div>
        </div>
    );
}

/** Una squadra: logo se c'e', nome sempre. */
function Squadra({ nome, src, conLoghi }: { nome: string; src: string; conLoghi: boolean }) {
    const [rotto, setRotto] = useState(false);
    return (
        <div className="flex items-center gap-1.5 leading-tight min-w-0">
            {src && !rotto ? (
                <img
                    src={src} alt="" width={16} height={16} loading="lazy"
                    onError={() => setRotto(true)}
                    className="w-4 h-4 object-contain shrink-0"
                />
            ) : conLoghi ? (
                <span className="w-4 shrink-0" aria-hidden="true" data-testid="cr-logo-vuoto" />
            ) : null}
            <span className="text-[13px] font-medium leading-tight truncate" data-testid="cr-nome-squadra">{nome}</span>
        </div>
    );
}

export default NomiPartita;
