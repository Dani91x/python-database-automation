// ============================================================================
// StoricoLink.tsx — IL PULSANTE «STORICO», uno solo per tutta la piattaforma.
//
// Ordine dell'utente (17/09): «usa tutte le tecniche di UI e UX per pulsanti
// "Storico" immediatamente capibili». Immediatamente capibile vuol dire tre
// cose, e tutte e tre stanno qui dentro una volta sola:
//   1. ICONA + PAROLA. L'icona da sola si impara, non si capisce; la parola da
//      sola si perde in mezzo al resto. Insieme si riconoscono da lontano.
//   2. SEMPRE NELLO STESSO POSTO. In ogni scheda è in fondo alla riga della
//      testata, allineato a destra: il trader non lo cerca, lo trova.
//   3. DICE DOVE PORTA. «Storico calcio» / «Storico tennis», mai «Storico» e
//      basta quando gli storici sono due: sapere dove si finisce PRIMA di
//      cliccare è metà dell'usabilità.
//
// Il titolo (`title`) aggiunge la frase intera per chi si ferma sopra, e
// l'`aria-label` la ripete per chi non vede il colore né l'icona.
// ============================================================================
import { Link } from 'react-router-dom';
import { History } from 'lucide-react';
import { SPORT_ICONA, SPORT_LABEL, rottaStorico, type SportStorico } from '@/lib/storicoSport';

export interface StoricoLinkProps {
    /** lo sport di questa scheda; null = si mostrano tutti e due i pulsanti */
    sport: SportStorico | null;
    /** compatto = dentro una testata di card; pieno = barra della pagina */
    compatto?: boolean;
    testId?: string;
}

const BASE = 'inline-flex items-center gap-1.5 rounded-md border transition-colors '
    + 'border-white/15 text-white/70 hover:text-white hover:border-white/35 hover:bg-white/[0.06]';

function Uno({ sport, compatto, testId }: { sport: SportStorico; compatto: boolean; testId: string }) {
    const frase = `Storico ${SPORT_LABEL[sport].toLowerCase()}: i giorni precedenti, con P&L per bot, `
        + 'curva globale e calendario. Qui sopra c’è solo la giornata di oggi.';
    return (
        <Link
            to={rottaStorico(sport)}
            data-testid={testId}
            title={frase}
            aria-label={frase}
            className={`${BASE} ${compatto ? 'text-[10.5px] px-1.5 py-0.5' : 'text-xs px-2.5 py-1.5'}`}
        >
            <History className={compatto ? 'w-3 h-3' : 'w-3.5 h-3.5'} aria-hidden />
            <span aria-hidden>{SPORT_ICONA[sport]}</span>
            <span className="font-semibold">Storico {SPORT_LABEL[sport].toLowerCase()}</span>
        </Link>
    );
}

export function StoricoLink({ sport, compatto = false, testId = 'storico-link' }: StoricoLinkProps) {
    if (sport) return <Uno sport={sport} compatto={compatto} testId={testId} />;
    // niente sport scelto = due storici, e si mostrano tutti e due. Un pulsante
    // «Storico» che porta a uno dei due a caso è peggio di due pulsanti.
    return (
        <span className="inline-flex items-center gap-1.5" data-testid={`${testId}-coppia`}>
            <Uno sport="calcio" compatto={compatto} testId={`${testId}-calcio`} />
            <Uno sport="tennis" compatto={compatto} testId={`${testId}-tennis`} />
        </span>
    );
}

export default StoricoLink;
