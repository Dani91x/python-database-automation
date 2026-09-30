// ============================================================================
// QuoteMercato.test.tsx — B1 (30/09), «rendere le quote in tempo reale piu'
// visibili e da trader» (utente, sezioni 4-5-6). Un solo componente per le
// schede pre-partita, in gioco e aperte: BACK sky, LAY rose, cifre mono, `—`
// per un prezzo assente, e l'eta' con l'etichetta di COSA misura.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import {
    QuoteMercato, EtaQuote, LineeOu, celleMatchOdds, MAX_LINEE_OU, QUOTE_CLS, QUOTE_TESTO, SOGLIA_SPREAD_TICK,
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

    it('W_B1 tennis: con i nomi dello scanner le celle portano il NOME, e il title dichiara l’ordine (sortPriority)', () => {
        const odds = { p1: { back: 1.5, lay: 1.52 }, p2: { back: 2.6, lay: 2.66 } };
        const c = celleMatchOdds('tennis', odds, { p1: 'Sinner J.', p2: 'Alcaraz C.' });
        expect(c?.map((x) => x.etichetta)).toEqual(['Sinner J.', 'Alcaraz C.']);
        expect(c?.[0].titolo).toMatch(/sortPriority/);
        expect(c?.[0].titolo).toMatch(/scanner/);
        // un nome mancante o vuoto: si resta su P1/P2 (mai un nome solo, mai un nome indovinato)
        expect(celleMatchOdds('tennis', odds, { p1: 'Sinner J.', p2: '  ' })?.map((x) => x.etichetta)).toEqual(['P1', 'P2']);
        expect(celleMatchOdds('tennis', odds, null)?.map((x) => x.etichetta)).toEqual(['P1', 'P2']);
        // il calcio non usa i nomi dei giocatori
        expect(celleMatchOdds('calcio', { home: { back: 2, lay: 2.02 } }, { p1: 'A', p2: 'B' })?.map((x) => x.etichetta))
            .toEqual(['1', 'X', '2']);
    });

    it('celleMatchOdds: nessun prezzo nel blocco = null (non si monta una fila di trattini)', () => {
        expect(celleMatchOdds('calcio', null)).toBeNull();
        expect(celleMatchOdds('calcio', { home: null, draw: null, away: null })).toBeNull();
        expect(celleMatchOdds('calcio', { home: { back: null, lay: null } })).toBeNull();
        expect(celleMatchOdds('tennis', { home: { back: 1.9, lay: 2 } })).toBeNull();
    });
});

describe('W_B1: spread largo = «poco liquido», nota grigia accanto alla cella', () => {
    // l'esempio dell'utente: «1 40,00/50,00 · X 15,00/18,00». 40 -> 50 sono 5 tick
    // (passo 2 fra 30 e 50: alla soglia, nessuna nota); 15 -> 18 sono 6 tick (passo 0,50)
    it('X 15,00/18,00 (6 tick; soglia 5): «spread 6 tick · poco liquido», grigia, fuori dalla cella', () => {
        render(<QuoteMercato testId="q" celle={[{ chiave: 'draw', etichetta: 'X', back: 15, lay: 18 }]} />);
        const nota = screen.getByTestId('cr-quota-spread');
        expect(nota).toHaveTextContent('spread 6 tick · poco liquido');
        expect(nota.className).not.toMatch(/orange|red|amber|rose/);
        expect(nota.getAttribute('title')).toMatch(/soglia 5 tick/);
        expect(screen.getByTestId('cr-quota-cella').textContent).toBe('X 15,00/18,00');
        expect(SOGLIA_SPREAD_TICK).toBe(5);
    });

    it('spread entro la soglia (2 1,08/1,10 = 2 tick; 6 tick esatti = 5 no, 6 sì): nessuna nota o nota al posto giusto', () => {
        const { rerender } = render(<QuoteMercato testId="q" celle={[{ chiave: 'away', etichetta: '2', back: 1.08, lay: 1.1 }]} />);
        expect(screen.queryByTestId('cr-quota-spread')).toBeNull();
        // 2,00 -> 2,10 = 5 tick (passo 0,02): alla soglia, nessuna nota
        rerender(<QuoteMercato testId="q" celle={[{ chiave: 'x', etichetta: 'X', back: 2, lay: 2.1 }]} />);
        expect(screen.queryByTestId('cr-quota-spread')).toBeNull();
        // 2,00 -> 2,12 = 6 tick: sopra la soglia
        rerender(<QuoteMercato testId="q" celle={[{ chiave: 'x', etichetta: 'X', back: 2, lay: 2.12 }]} />);
        expect(screen.getByTestId('cr-quota-spread')).toHaveTextContent('spread 6 tick · poco liquido');
        // 40,00 -> 50,00 = 5 tick: alla soglia, nessuna nota
        rerender(<QuoteMercato testId="q" celle={[{ chiave: 'home', etichetta: '1', back: 40, lay: 50 }]} />);
        expect(screen.queryByTestId('cr-quota-spread')).toBeNull();
    });

    it('anche nelle linee Under/Over (stesso componente): Under 3,00/4,00 = 20 tick', () => {
        render(<LineeOu testId="ou" linee={[{
            marketId: '1.35', linea: 3.5, stato: 'OPEN', decisa: false, perMike: false,
            under: { back: 3, lay: 4 }, over: { back: 1.33, lay: 1.34 }, etaCambioS: 2,
        }]} />);
        const note = screen.getAllByTestId('cr-quota-spread');
        expect(note).toHaveLength(1);
        expect(note[0]).toHaveTextContent('spread 20 tick · poco liquido');
    });

    it('un lato assente: nessuno spread inventato', () => {
        render(<QuoteMercato testId="q" celle={[{ chiave: 'draw', etichetta: 'X', back: 15, lay: null }]} />);
        expect(screen.queryByTestId('cr-quota-spread')).toBeNull();
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
        marketId: '1.35', linea: 3.5, stato: 'OPEN', decisa: false, perMike: false,
        under: { back: 1.5, lay: 1.52 }, over: { back: 2.6, lay: 2.7 }, etaCambioS: 3, ...over,
    };
}

describe('LineeOu — le linee Under/Over con lo stesso componente', () => {
    it('linea, Under B/L, Over B/L e l’età dell’ultimo book, neutra', () => {
        render(<LineeOu testId="ou" linee={[linea(), linea({ marketId: '1.45', linea: 4.5, etaCambioS: null })]} />);
        const righe = screen.getAllByTestId('cr-quote-ou-linea');
        expect(righe).toHaveLength(2);
        expect(righe[0]).toHaveTextContent('U/O 3,5');
        expect(righe[0]).toHaveTextContent('Under 1,50/1,52');
        expect(righe[0]).toHaveTextContent('Over 2,60/2,70');
        expect(righe[0]).toHaveTextContent('ultimo cambio: 3 s');
        expect(righe[1]).toHaveTextContent('ultimo cambio: età ignota');
        // R_B1: e' l'ultimo CAMBIO della linea (ts_ms), non l'ultimo book ne' l'ultima lettura
        expect(righe[0].textContent).not.toMatch(/ultimo book/);
        expect(screen.getAllByTestId('cr-quote-ou-eta')[0].getAttribute('title'))
            .toMatch(/ultimo cambio di prezzo o di importo di questa linea: non è l.ultima lettura/);
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

    // B1bis (decisione del coordinatore, 30/09): oltre 4 linee NON si nasconde
    // piu' niente. Sostituisce il test B1 «più di 4: non si monta».
    it('nessuna linea: non si monta; fino a 4: tutte in vista, nessun riquadro «altre»', () => {
        const { container, rerender } = render(<LineeOu testId="ou" linee={[]} />);
        expect(container.innerHTML).toBe('');
        const quattro = [0.5, 1.5, 2.5, 5.5].map((l, i) => linea({ marketId: `1.${i}`, linea: l }));
        rerender(<LineeOu testId="ou" linee={quattro} />);
        expect(screen.getAllByTestId('cr-quote-ou-linea')).toHaveLength(MAX_LINEE_OU);
        expect(screen.queryByTestId('cr-quote-ou-altre')).toBeNull();
    });

    it('più di 4: in vista 3,5 · 4,5 e le linee marcate (Mike / decise), TUTTE le altre nel riquadro chiuso', () => {
        const otto = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5].map((l, i) => linea({
            marketId: `1.${i}`, linea: l, perMike: l === 1.5, decisa: l === 0.5,
        }));
        render(<LineeOu testId="ou" linee={otto} />);
        const tutte = screen.getAllByTestId('cr-quote-ou-linea');
        expect(tutte).toHaveLength(8);                                   // nessuna linea fuori dalla scheda
        const altre = screen.getByTestId('cr-quote-ou-altre') as HTMLDetailsElement;
        expect(altre.tagName).toBe('DETAILS');
        expect(altre.open).toBe(false);                                  // chiuso di default
        expect(within(altre).getByText('altre 4 linee')).toBeTruthy();
        const inAltre = within(altre).getAllByTestId('cr-quote-ou-linea').map((r) => r.textContent ?? '');
        expect(inAltre.map((t) => t.slice(0, 7))).toEqual(['U/O 2,5', 'U/O 5,5', 'U/O 6,5', 'U/O 7,5']);
        const inVista = tutte.filter((r) => !altre.contains(r)).map((r) => (r.textContent ?? '').slice(0, 7));
        expect(inVista).toEqual(['U/O 0,5', 'U/O 1,5', 'U/O 3,5', 'U/O 4,5']);
        // la regola e' scritta, non intuita
        expect(screen.getByTestId('ou').getAttribute('title')).toMatch(/3,5 e 4,5/);
    });
});
