// ============================================================================
// ObiettivoVoci.tsx - 30/09 (W_G/P6): le due voci di soldi del riquadro
// Obiettivo che la DayBar riceve come nodi (parametri opzionali):
//   * «aperto adesso (se chiudo tutto)»: somma PER PARTITA del cash out LIVE
//     (`lib/apertoAdesso.ts`), STIMA ai prezzi dello scanner; le partite non
//     calcolabili si dicono, mai una somma spacciata per completa;
//   * «rischio massimo»: l'esposizione del CONTO Betfair (una cifra sola, la
//     stessa della testata, `vm.soldiVeri.conto`), con l'eta' della lettura.
// ============================================================================
import type { ReactNode } from 'react';
import { fmtMoney, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { ApertoAdesso } from '@/lib/apertoAdesso';
import type { ContoAdesso } from './testata/soldiVeri';
import { MarchioSoldi } from './MarchioSoldi';

const partite = (n: number) => `${n} ${n === 1 ? 'partita' : 'partite'}`;

export function apertoNode(a: ApertoAdesso | null): ReactNode {
    if (a == null || (a.partite === 0 && a.nonCalcolabili === 0)) return undefined;
    return (
        <span className="inline-flex items-center gap-1 flex-wrap" data-testid="cr-giornata-aperto"
            title="se chiudo TUTTO adesso: somma per partita del cash out delle posizioni LIVE, netto commissione, ai prezzi dello scanner">
            aperto adesso (se chiudo tutto){' '}
            {a.netto != null ? (
                <b className={pnlClass(a.netto)} data-testid="cr-giornata-aperto-valore">{fmtMoney(a.netto, { signed: true })}</b>
            ) : (
                <b className="text-slate-400" data-testid="cr-giornata-aperto-valore">{DASH}</b>
            )}
            <MarchioSoldi fonte="pagina" dettaglio="prezzi dello scanner, cash out per partita" testId="cr-giornata-aperto-marchio" />
            {a.partite > 0 && <span className="text-slate-400">su {partite(a.partite)}</span>}
            {a.nonCalcolabili > 0 && (
                <span className="text-amber-300" data-testid="cr-giornata-aperto-non-calcolabili">
                    + {partite(a.nonCalcolabili)} non calcolabili
                </span>
            )}
        </span>
    );
}

export function rischioNode(c: ContoAdesso | null): ReactNode {
    if (c == null) return undefined;
    return (
        <span className="inline-flex items-center gap-1" data-testid="cr-giornata-rischio"
            title="rischio massimo del conto adesso, calcolato da Betfair (tutti i mercati: bot, sito e app)">
            rischio massimo{' '}
            {c.letto && c.esposizione != null ? (
                <b className="text-orange-400" data-testid="cr-giornata-rischio-valore">{fmtMoney(c.esposizione)}</b>
            ) : (
                <b className="text-slate-400" data-testid="cr-giornata-rischio-valore">{DASH}</b>
            )}
            <MarchioSoldi fonte="conto" etaS={c.etaS} testId="cr-giornata-rischio-marchio" />
            {!c.letto && <span className="text-amber-300">conto non letto</span>}
        </span>
    );
}
