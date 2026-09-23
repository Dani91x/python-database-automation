// ============================================================================
// DettaglioRigaView.test.tsx — colore del "se chiudo ora" (`o.chiusura.bloccabile`)
// nella riga condivisa `RigaOperazione` (Pre-match/Live/scheda partita).
//
// DIFETTO CORRETTO (referto audit UI 23/09): lo span che mostra
// `fmtMoney(o.chiusura.bloccabile, {signed:true})` non portava `pnlClass(...)`
// ed ereditava `text-white/40` dal contenitore padre — stesso peso visivo
// dell'etichetta neutra "chiudi ora", invisibile al trader. Il valore
// IDENTICO nella tab "Posizioni aperte" (`ControlRoom.tsx:1379`,
// `data-testid="cr-bloccabile"`) usa correttamente `pnlClass`: qui si
// allinea lo stesso trattamento, stesso pattern gia' usato 4 righe sotto
// per `o.pnl` (riga 340 di `DettaglioRigaView.tsx`).
//
// FALSIFICAZIONE (fatta a mano, patch salvata e ripristinata): tolto
// `pnlClass(o.chiusura.bloccabile)` dalla classe dello span → il test
// "verde per bloccabile positivo" e quello "rosso per bloccabile negativo"
// diventano rossi (la classe `text-white/40` del contenitore resta l'unica
// presente, nessuna `text-emerald-400`/`text-red-400` sullo span). Ripristinata
// la versione corretta subito dopo: v. referto SubagentHandback per il diff
// prima/dopo.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RigaOperazione } from './DettaglioRigaView';
import type { RigaOrdine } from '@/lib/statoOrdine';
import type { OperazionePartita } from './useControlRoom';

function ordine(): RigaOrdine {
    return {
        status: 'open', side: 'back', price: 2.0, size: 10,
        size_requested: 10, size_matched: 10, size_remaining: 0,
        avg_price_matched: 2.0, betfair_updated_at: '2026-09-18T10:00:00.000Z',
        meta: null,
    };
}

function riga(chiusura: OperazionePartita['chiusura'], over: Partial<OperazionePartita> = {}): OperazionePartita {
    return {
        bot: 'safe', id: 1, selezione: 'Juventus', lato: 'back', prezzo: 2.0,
        size: 10, stato: 'open', pnl: null, modalita: 'live',
        at: '2026-09-18T10:00:00.000Z', quale: null,
        ordine: ordine(),
        dettaglio: null, marketId: 'm1', selectionId: 123, liability: null,
        vivo: null, etaQuoteS: null, chiusura, chiusureOrdini: [],
        ...over,
    };
}

describe('RigaOperazione: colore di "se chiudo ora" (o.chiusura.bloccabile)', () => {
    it('bloccabile positivo: verde (pnlClass), come il P&L a fine riga', () => {
        render(<RigaOperazione o={riga({ lato: 'back', prezzo: 2.1, abbinabile: 10, bloccabile: 5.5 })} />);
        const cella = screen.getByTestId('cr-op-chiudo-ora');
        const span = cella.querySelector('span.font-mono.font-semibold');
        expect(span).not.toBeNull();
        expect(span).toHaveTextContent('+5,50');
        expect(span?.className).toMatch(/text-emerald-400/);
        expect(span?.className).not.toMatch(/text-red-400/);
    });

    it('bloccabile negativo: rosso (pnlClass)', () => {
        render(<RigaOperazione o={riga({ lato: 'back', prezzo: 1.9, abbinabile: 10, bloccabile: -3.2 })} />);
        const cella = screen.getByTestId('cr-op-chiudo-ora');
        const span = cella.querySelector('span.font-mono.font-semibold');
        expect(span).not.toBeNull();
        expect(span?.className).toMatch(/text-red-400/);
        expect(span?.className).not.toMatch(/text-emerald-400/);
    });

    it('prezzo assente: resta "—" arancione, nessuna classe pnlClass da applicare', () => {
        render(<RigaOperazione o={riga({ lato: 'back', prezzo: null, abbinabile: null, bloccabile: null })} />);
        const cella = screen.getByTestId('cr-op-chiudo-ora');
        expect(cella).toHaveTextContent('—');
        expect(cella.querySelector('span.font-mono.font-semibold')).toBeNull();
        expect(cella.querySelector('span.text-orange-400')).not.toBeNull();
    });

    it('o.chiusura assente (null): niente riga "chiudi ora" montata', () => {
        render(<RigaOperazione o={riga(null)} />);
        expect(screen.queryByTestId('cr-op-chiudo-ora')).not.toBeInTheDocument();
    });
});
