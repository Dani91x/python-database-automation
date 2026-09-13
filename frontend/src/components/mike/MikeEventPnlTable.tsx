// ============================================================================
// MikeEventPnlTable — UNA RIGA PER PARTITA, col netto davanti e il dettaglio
// sotto, da aprire solo se lo vuoi.
//
// Richiesta dell'utente (13/09), testuale: «il P&L deve essere il netto delle
// operazioni di quella partita, con a cascata il dettaglio delle operazioni
// (deve essere nascosto e apribile da me), in verde i risultati positivi e in
// rosso quelli negativi».
//
// Prima la scheda "Operazioni" era un elenco piatto di CICLI, ordinati per ora:
// i due o tre cicli della stessa partita finivano sparsi fra partite diverse, e
// la colonna P&L mostrava il netto del ciclo sull'apertura E il netto della
// singola gamba sulle chiusure — gli stessi euro due volte, a due livelli, senza
// che niente lo dicesse. Chi sommava con gli occhi otteneva il doppio.
//
// Adesso ci sono tre livelli, e a colpo d'occhio se ne vede uno solo:
//   1. PARTITA   il netto che conta, grande e colorato;
//   2. CICLO     ingresso, uscita, quanto ha reso quel ciclo;
//   3. GAMBA     l'ordine vero: ora, lato, selezione, size, quota, esito.
//
// CERT. 13/09 — QUESTO FILE ORA È UN ADATTATORE, non più una tabella.
// La tabella vera è `components/trading/EventPnlTable.tsx`, condivisa con Safe
// Strategy e Omega: la stessa domanda («quanto ho fatto su questa partita?»)
// non può avere tre risposte con tre estetiche diverse. Qui restano solo le
// cose che sono DI MIKE: il nome italiano dei ruoli, le linee 3.5/4.5, il
// tooltip lordo/commissione, il filtro di fase pre-match/live.
// ============================================================================
import { useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { EventPnlTable, type RigheLabels } from '@/components/trading/EventPnlTable';
import { fmtMoney } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import { exitInfo } from '@/lib/dailyHistory';
import {
    fasePerCiclo, marketLabel, roleLabel, isManualTrade,
    type MikeFase, type MikeTradeGroup, type MikeTrade,
} from '@/lib/mike';

/**
 * Colore del P&L. Vive in `lib/tradeStatus.ts` da quando la regola è UNA per
 * tutte e tre le sezioni; qui resta ri-esportato perché il resto della sezione
 * Mike (e i suoi test) lo importa da questo modulo.
 */
export { pnlClass };

/** lordo e commissione stanno nel tooltip: il numero in pagina è sempre il netto */
function pnlTitle(t: MikeTrade): string {
    const meta = t.meta ?? {};
    const gross = Number(meta.pnl_gross);
    const comm = Number(meta.commission_paid);
    const parts: string[] = [];
    if (Number.isFinite(gross)) parts.push(`lordo ${fmtMoney(gross, { signed: true })}`);
    if (Number.isFinite(comm)) parts.push(`commissione ${fmtMoney(comm)}`);
    return parts.length
        ? `${parts.join(' · ')} — in pagina il NETTO`
        : 'P&L netto della commissione';
}

/** Etichette ITALIANE delle righe di Mike: ruoli, linee, badge manuale/uscita. */
const ETICHETTE_MIKE: RigheLabels<MikeTrade> = {
    ruolo: (t) => roleLabel(t.role),
    selezione: (t) => t.selection_name ?? marketLabel(t.market_type),
    badge: (t) => (isManualTrade(t)
        ? <Badge variant="outline" className="ml-1 px-1 py-0 text-[9px]">manuale</Badge>
        : null),
    statoExtra: (t) => {
        const uscita = exitInfo(t.meta ?? {});
        return uscita ? <ExitBadge info={uscita} className="ml-1" /> : null;
    },
    pnlTitle,
};

export interface MikeEventPnlTableProps {
    /** cicli già filtrati (giornata, fase…) dal chiamante */
    gruppi: readonly MikeTradeGroup[];
    /** solo i cicli di questa fase; assente = tutte */
    fase?: MikeFase;
    titolo: string;
    icona?: React.ReactNode;
    /** riga di spiegazione sotto la tabella */
    nota?: React.ReactNode;
    /** mostrato quando non c'è niente */
    vuoto: React.ReactNode;
    /** avviso (per esempio il tetto di righe della RPC) */
    avviso?: React.ReactNode;
    /** clic sul nome della partita: porta alla sua scheda */
    onApriScheda?: (eventId: string) => void;
    /** modalità a cui si riferiscono i totali (dichiarata in etichetta) */
    modalita?: string | null;
    /** P&L già bloccato sulle posizioni ancora vive: «se chiudo ora» */
    apertoOra?: number | null;
    testId?: string;
}

export function MikeEventPnlTable({
    gruppi, fase, titolo, icona, nota, vuoto, avviso, onApriScheda,
    modalita, apertoOra, testId = 'mike-event-pnl',
}: MikeEventPnlTableProps) {
    // il filtro di fase è l'unica cosa che la tabella condivisa non può sapere:
    // dipende dal RUOLO della gamba che apre il ciclo, che è vocabolario di Mike
    const filtro = useMemo(
        () => (fase ? (c: { open: MikeTrade; closes: MikeTrade[]; netPnl: number | null; orphan: boolean }) => fasePerCiclo(c) === fase : undefined),
        [fase],
    );
    return (
        <EventPnlTable<MikeTrade>
            cicli={gruppi}
            filtro={filtro}
            titolo={titolo}
            icona={icona}
            nota={nota ?? 'Clicca una partita per aprire i suoi cicli e gli ordini che li compongono.'}
            vuoto={vuoto}
            avviso={avviso}
            onApriScheda={onApriScheda}
            modalita={modalita}
            apertoOra={apertoOra}
            unita={{ uno: 'ciclo', molti: 'cicli' }}
            etichette={ETICHETTE_MIKE}
            testId={testId}
        />
    );
}

export default MikeEventPnlTable;
