// ============================================================================
// SchedaPreMatch.test.tsx — Secondo giro (18/09), richiesta utente: quote
// pre-match vive con età, e gli ordini pre-match con la STESSA riga di
// Live/Aperte (`RigaOperazione`).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SchedaPreMatch } from './SchedaPreMatch';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { OperazionePartita } from './useControlRoom';

function partita(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'C1', sport: 'calcio', nome: 'Roma – Lazio', campionato: 'Serie A',
        koMs: Date.now() + 3600_000, stato: 'pre', minuto: null, punteggio: null,
        controlloDisponibile: false, etaFeedS: null, freschezza: 'ignota',
        latenzaQuoteS: null, freschezzaQuote: 'ignota', statoQuote: 'ignoto',
        media: null, extra: null, marketId: null,
        soldi: null, target: null, avanzamento: null,
        ...over,
    };
}

function op(over: Partial<OperazionePartita> = {}): OperazionePartita {
    return {
        bot: 'omega', id: 1, selezione: 'Under 3.5', lato: 'back', prezzo: 2.1, size: 10,
        stato: 'pending', pnl: null, modalita: 'paper', at: '2026-09-18T10:00:00Z',
        quale: null,
        ordine: { status: 'pending', side: 'back', price: 2.1, size: 10, meta: null },
        dettaglio: null,
        marketId: null, selectionId: null, liability: null, vivo: null, etaQuoteS: null,
        chiusura: null, chiusureOrdini: [],
        ...over,
    };
}

function monta(p: PartitaGiornata, extra: Partial<React.ComponentProps<typeof SchedaPreMatch>> = {}) {
    return render(
        <MemoryRouter>
            <SchedaPreMatch p={p} scheda="pre" mancaS={3600} {...extra} />
        </MemoryRouter>,
    );
}

describe('SchedaPreMatch — quote pre-match vive (secondo giro)', () => {
    it('mostra le quote 1X2 con l’età, quando il feed le porta', () => {
        monta(partita({
            odds: { home: { back: 1.9, lay: 1.92 }, draw: { back: 3.4, lay: 3.5 }, away: { back: 4.2, lay: 4.3 } },
            latenzaQuoteS: 4, statoQuote: 'fresco',
        }));
        const riga = screen.getByTestId('cr-pre-quote');
        expect(riga).toHaveTextContent('1 1,90/1,92');
        expect(riga).toHaveTextContent('X 3,40/3,50');
        expect(riga).toHaveTextContent('2 4,20/4,30');
        expect(riga).toHaveTextContent('4 s');
    });

    it('tennis: quote P1/P2', () => {
        monta(partita({
            sport: 'tennis', odds: { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.65 } },
        }));
        const riga = screen.getByTestId('cr-pre-quote');
        expect(riga).toHaveTextContent('P1 1,50/1,52');
        expect(riga).toHaveTextContent('P2 2,60/2,65');
    });

    // FALSIFICAZIONE
    it('senza quote e senza età: nessun blocco montato', () => {
        monta(partita({ odds: null, latenzaQuoteS: null }));
        expect(screen.queryByTestId('cr-pre-quote')).toBeNull();
    });

    it('«fermo» non è un allarme (stesso vocabolario di SchedaPartita)', () => {
        monta(partita({ latenzaQuoteS: 40, statoQuote: 'fermo' }));
        const riga = screen.getByTestId('cr-pre-quote');
        expect(riga).toHaveTextContent('fermo');
        expect(riga.querySelector('.text-orange-400')).toBeNull();
    });
});

describe('SchedaPreMatch — ordini pre-match già piazzati (secondo giro)', () => {
    it('senza operazioni (default): nessuna sezione montata', () => {
        monta(partita());
        expect(screen.queryByTestId('cr-pre-operazioni')).toBeNull();
    });

    it('con operazioni: monta RigaOperazione, STESSA riga di Live/Aperte', () => {
        monta(partita(), { operazioni: [op()] });
        const sezione = screen.getByTestId('cr-pre-operazioni');
        expect(sezione).toBeInTheDocument();
        expect(screen.getByTestId('cr-op-riga')).toHaveTextContent('Under 3.5');
        expect(screen.getByTestId('cr-op-riga')).toHaveTextContent('2,10');
        // stessa StatoOrdineCompatto della scheda Live/Aperte
        expect(screen.getByTestId('cr-stato-ordine')).toBeInTheDocument();
    });

    // FALSIFICAZIONE
    it('array vuoto esplicito: nessuna sezione, non un contenitore vuoto', () => {
        monta(partita(), { operazioni: [] });
        expect(screen.queryByTestId('cr-pre-operazioni')).toBeNull();
    });
});
