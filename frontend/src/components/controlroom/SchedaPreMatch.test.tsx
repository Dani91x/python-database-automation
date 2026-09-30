// ============================================================================
// SchedaPreMatch.test.tsx — Secondo giro (18/09), richiesta utente: quote
// pre-match vive con età, e gli ordini pre-match con la STESSA riga di
// Live/Aperte (`RigaOperazione`).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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

// ============================================================================
// B1 (30/09) — nomi e quote «da trader», uguali alla scheda in gioco.
// ============================================================================
function lineaOu(linea: number, over: Partial<NonNullable<PartitaGiornata['lineeOu']>[number]> = {}) {
    return {
        marketId: `1.${linea * 10}`, linea, stato: 'OPEN', decisa: false, perMike: false,
        under: { back: 1.5, lay: 1.52 }, over: { back: 2.6, lay: 2.7 }, etaCambioS: 2, ...over,
    };
}

describe('SchedaPreMatch — B1: nomi e quote da trader', () => {
    it('i nomi passano dal componente condiviso, col nome intero nel title', () => {
        monta(partita({ extra: { campionato: 'Serie A', leagueId: 135, homeTeamId: 497, awayTeamId: 487, fixtureId: 1 } }));
        const nomi = screen.getByTestId('cr-nomi-partita');
        expect(nomi.getAttribute('title')).toBe('Roma – Lazio');
        expect(screen.getAllByTestId('cr-nome-squadra').map((n) => n.textContent)).toEqual(['Roma', 'Lazio']);
        expect(nomi.querySelectorAll('img')).toHaveLength(2);
    });

    it('le quote sono celle: BACK sky, LAY rose, non più il testo grigio da 10 px', () => {
        monta(partita({
            odds: { home: { back: 40, lay: 50 }, draw: { back: 15, lay: 18 }, away: { back: 1.08, lay: 1.1 } },
            latenzaQuoteS: 2, statoQuote: 'fresco',
        }));
        const riga = screen.getByTestId('cr-pre-quote');
        const celle = within(riga).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['1 40,00/50,00', 'X 15,00/18,00', '2 1,08/1,10']);
        expect(within(celle[2]).getByTestId('cr-quota-back').className).toMatch(/text-sky-/);
        expect(within(celle[2]).getByTestId('cr-quota-lay').className).toMatch(/text-rose-/);
    });

    it('un lato del 1X2 assente: la cella c’è e dice «—»', () => {
        monta(partita({ odds: { home: { back: 1.9, lay: 1.92 }, draw: null, away: { back: 4.2, lay: null } } }));
        const celle = within(screen.getByTestId('cr-pre-quote')).getAllByTestId('cr-quota-cella');
        expect(celle.map((c) => c.textContent)).toEqual(['1 1,90/1,92', 'X —/—', '2 4,20/—']);
    });

    it('accanto alle quote l’età c’è SEMPRE, con cosa misura (anche quando è ignota)', () => {
        monta(partita({ odds: { home: { back: 1.9, lay: 1.92 } }, latenzaQuoteS: null, statoQuote: 'ignoto' }));
        const eta = within(screen.getByTestId('cr-pre-quote')).getByTestId('cr-pre-latenza');
        expect(eta).toHaveTextContent('ultimo cambio: età ignota');
        expect(within(eta).getByTestId('cr-pre-latenza-valore').className).toContain('text-orange-400');
    });

    it('le linee Under/Over della riga si vedono con lo stesso componente', () => {
        monta(partita({ lineeOu: [lineaOu(3.5), lineaOu(4.5, { etaCambioS: 7 })] }));
        const ou = within(screen.getByTestId('cr-pre-quote')).getByTestId('cr-pre-quote-ou');
        const righe = within(ou).getAllByTestId('cr-quote-ou-linea');
        expect(righe).toHaveLength(2);
        expect(righe[0]).toHaveTextContent('U/O 3,5');
        expect(righe[0]).toHaveTextContent('Under 1,50/1,52');
        expect(righe[1]).toHaveTextContent('ultimo cambio: 7 s');
    });

    // B1bis (decisione del coordinatore): sostituisce il test B1 «più di quattro
    // linee: non si mostrano». Nessuna linea del payload resta fuori.
    it('più di quattro linee: si mostrano tutte, 3,5 e 4,5 in vista, le altre nel riquadro', () => {
        monta(partita({ lineeOu: [0.5, 1.5, 2.5, 3.5, 4.5].map((l) => lineaOu(l)) }));
        const ou = screen.getByTestId('cr-pre-quote-ou');
        expect(within(ou).getAllByTestId('cr-quote-ou-linea')).toHaveLength(5);
        expect(within(within(ou).getByTestId('cr-quote-ou-altre')).getAllByTestId('cr-quote-ou-linea')).toHaveLength(3);
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
