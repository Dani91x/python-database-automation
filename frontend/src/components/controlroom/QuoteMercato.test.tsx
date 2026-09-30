// ============================================================================
// QuoteMercato.test.tsx — B1 (30/09), «rendere le quote in tempo reale piu'
// visibili e da trader» (utente, sezioni 4-5-6). Un solo componente per le
// schede pre-partita, in gioco e aperte: BACK sky, LAY rose, cifre mono, `—`
// per un prezzo assente, e l'eta' con l'etichetta di COSA misura.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import {
    QuoteMercato, EtaQuote, LineeOu, celleMatchOdds, MAX_LINEE_OU, QUOTE_CLS, QUOTE_TESTO,
} from './QuoteMercato';
import type { LineaOuScheda } from '@/lib/controlRoom';

describe('QuoteMercato — una cella per selezione, BACK e LAY distinti', () => {
    it('etichetta, BACK sky, LAY rose, cifre mono e tabulari, formato «1 1,90/1,92»', () => {
        render(<QuoteMercato testId="q" celle={[{ chiave: 'home', etichetta: '1', back: 1.9, lay: 1.92 }]} />);
        const cella = screen.getByTestId('cr-quota-cella');
        expect(cella).toHaveTextContent('1 1,90/1,92');
        const back = within(cella).getByTestId('cr-quota-back');
        const lay = within(cella).getByTestId('cr-quota-lay');
        expect(back).toHaveTextContent('1,90');
        expect(lay).toHaveTextContent('1,92');
        expect(back.className).toMatch(/text-sky-/);
        expect(lay.className).toMatch(/text-rose-/);
        for (const el of [back, lay]) {
            expect(el.className).toMatch(/font-mono/);
            expect(el.className).toMatch(/tabular-nums/);
            // corpo leggibile: non piu' i 10 px grigi di prima
            expect(el.className).not.toMatch(/text-\[10px\]/);
        }
    });

    it('prezzo assente, zero o non valido: «—», mai «0,00», mai una cella muta', () => {
        render(<QuoteMercato testId="q" celle={[
            { chiave: 'home', etichetta: '1', back: null, lay: 0 },
            { chiave: 'draw', etichetta: 'X', back: 1, lay: undefined },
        ]} />);
        const [c1, c2] = screen.getAllByTestId('cr-quota-cella');
        expect(c1).toHaveTextContent('1 —/—');
        expect(c2).toHaveTextContent('X —/—');
        expect(screen.getByTestId('q').textContent).not.toContain('0,00');
    });

    it('celleMatchOdds: calcio sempre 1 · X · 2 (anche con un lato assente), tennis P1 · P2', () => {
        const calcio = celleMatchOdds('calcio', { home: { back: 1.9, lay: 1.92 }, away: null });
        expect(calcio?.map((c) => c.etichetta)).toEqual(['1', 'X', '2']);
        expect(calcio?.[1]).toMatchObject({ back: null, lay: null });
        const tennis = celleMatchOdds('tennis', { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.65 } });
        expect(tennis?.map((c) => c.etichetta)).toEqual(['P1', 'P2']);
    });

    it('celleMatchOdds: nessun prezzo nel blocco = null (non si monta una fila di trattini)', () => {
        expect(celleMatchOdds('calcio', null)).toBeNull();
        expect(celleMatchOdds('calcio', { home: null, draw: null, away: null })).toBeNull();
        expect(celleMatchOdds('calcio', { home: { back: null, lay: null } })).toBeNull();
        expect(celleMatchOdds('tennis', { home: { back: 1.9, lay: 2 } })).toBeNull();
    });
});

describe('EtaQuote — l’età del prezzo con l’etichetta di cosa misura', () => {
    it('dice che è l’ULTIMO CAMBIO (odds_ts_ms), non l’ultima lettura', () => {
        render(<EtaQuote testId="e" latenzaS={4} stato="fresco" />);
        const e = screen.getByTestId('e');
        expect(e).toHaveTextContent('ultimo cambio: 4 s');
        expect(e.getAttribute('title')).toMatch(/ultimo CAMBIO/);
        expect(e.getAttribute('title')).toMatch(/non l.ultima lettura/i);
    });

    it('le quattro parole restano quelle: fresco / fermo / vecchio / età ignota, con i loro colori', () => {
        const casi = [
            ['fresco', 4, '4 s'], ['fermo', 40, 'fermo 40 s'], ['vecchio', 130, 'vecchio 2 min'], ['ignoto', null, 'età ignota'],
        ] as const;
        for (const [stato, lat, testo] of casi) {
            const { unmount } = render(<EtaQuote testId="e" latenzaS={lat} stato={stato} />);
            const v = screen.getByTestId('e-valore');
            expect(v).toHaveTextContent(testo);
            expect(v.className).toContain(QUOTE_CLS[stato]);
            unmount();
        }
        // «fermo» NON è un allarme
        expect(QUOTE_CLS.fermo).not.toMatch(/orange|red|amber/);
        expect(QUOTE_TESTO.ignoto('')).toBe('età ignota');
    });

    it('l’età cambia a schermo quando cambia il dato (il tic lo dà la pagina)', () => {
        const { rerender } = render(<EtaQuote testId="e" latenzaS={5} stato="fresco" />);
        expect(screen.getByTestId('e')).toHaveTextContent('5 s');
        rerender(<EtaQuote testId="e" latenzaS={6} stato="fresco" />);
        expect(screen.getByTestId('e')).toHaveTextContent('6 s');
    });
});

function linea(over: Partial<LineaOuScheda> = {}): LineaOuScheda {
    return {
        marketId: '1.35', linea: 3.5, stato: 'OPEN', decisa: false,
        under: { back: 1.5, lay: 1.52 }, over: { back: 2.6, lay: 2.7 }, etaBookS: 3, ...over,
    };
}

describe('LineeOu — le linee Under/Over con lo stesso componente', () => {
    it('linea, Under B/L, Over B/L e l’età dell’ultimo book, neutra', () => {
        render(<LineeOu testId="ou" linee={[linea(), linea({ marketId: '1.45', linea: 4.5, etaBookS: null })]} />);
        const righe = screen.getAllByTestId('cr-quote-ou-linea');
        expect(righe).toHaveLength(2);
        expect(righe[0]).toHaveTextContent('U/O 3,5');
        expect(righe[0]).toHaveTextContent('Under 1,50/1,52');
        expect(righe[0]).toHaveTextContent('Over 2,60/2,70');
        expect(righe[0]).toHaveTextContent('ultimo book: 3 s fa');
        expect(righe[1]).toHaveTextContent('ultimo book: età ignota');
        // seen_ms non distingue fermo da non osservato: nessun colore di allarme
        expect(screen.getByTestId('ou').querySelector('.text-orange-400')).toBeNull();
    });

    it('mercato SOSPESO e linea DECISA dai gol: si vedono', () => {
        render(<LineeOu testId="ou" linee={[linea({ stato: 'SUSPENDED', decisa: true })]} />);
        expect(screen.getByTestId('cr-quote-ou-mercato')).toHaveTextContent('SOSPESO');
        expect(screen.getByTestId('cr-quote-ou-decisa')).toHaveTextContent('decisa dai gol');
    });

    it('mercato OPEN: nessun badge di stato', () => {
        render(<LineeOu testId="ou" linee={[linea()]} />);
        expect(screen.queryByTestId('cr-quote-ou-mercato')).toBeNull();
        expect(screen.queryByTestId('cr-quote-ou-decisa')).toBeNull();
    });

    it(`nessuna linea, o più di ${MAX_LINEE_OU}: non si monta (nessuna scelta inventata di quali mostrare)`, () => {
        const { container, rerender } = render(<LineeOu testId="ou" linee={[]} />);
        expect(container.innerHTML).toBe('');
        const tante = Array.from({ length: MAX_LINEE_OU + 1 }, (_, i) => linea({ marketId: `1.${i}`, linea: i + 0.5 }));
        rerender(<LineeOu testId="ou" linee={tante} />);
        expect(container.innerHTML).toBe('');
        rerender(<LineeOu testId="ou" linee={tante.slice(0, MAX_LINEE_OU)} />);
        expect(screen.getAllByTestId('cr-quote-ou-linea')).toHaveLength(MAX_LINEE_OU);
    });
});
