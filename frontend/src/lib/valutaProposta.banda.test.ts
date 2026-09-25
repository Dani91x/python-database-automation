// D7 (25/09) - la porta TS della BANDA DELLA STRATEGIA riproduce ESATTAMENTE il
// file d'oro scritto dal Python
// (`python -m Betfair.safe_strategy.tools.genera_oro_banda_strategia`). Se una
// delle due funzioni cambia da sola, questo test (o il gemello Python
// `test_esecuzione_a_mercato_d7_2026_09_25.py`) diventa rosso.
import { describe, expect, it } from 'vitest';
import oro from './bandaStrategia.golden.json';
import {
    bandaDellaStrategia, inBanda, testoBanda, type BandaStrategia, type CriteriProposta,
} from './valutaProposta';

interface Caso {
    nome: string;
    ingresso: { side: unknown; p_model: unknown; criteri: CriteriProposta | null };
    uscita: { banda: BandaStrategia | null; in_banda: Record<string, boolean> };
}

describe('bandaDellaStrategia = banda_della_strategia (file d’oro)', () => {
    const casi = oro as unknown as Caso[];

    it('il file d’oro ha bande piene, vuote e assenti', () => {
        expect(casi.length).toBeGreaterThanOrEqual(15);
        expect(casi.some((c) => c.uscita.banda && !c.uscita.banda.vuota)).toBe(true);
        expect(casi.some((c) => c.uscita.banda?.vuota === true)).toBe(true);
        expect(casi.some((c) => c.uscita.banda === null)).toBe(true);
    });

    for (const caso of casi) {
        it(caso.nome, () => {
            expect(bandaDellaStrategia(caso.ingresso)).toEqual(caso.uscita.banda);
            for (const [prezzo, atteso] of Object.entries(caso.uscita.in_banda)) {
                expect(inBanda({ ...caso.ingresso, prezzo: Number(prezzo) }), `prezzo ${prezzo}`)
                    .toBe(atteso);
            }
        });
    }
});

describe('testoBanda', () => {
    it('come il messaggio del servizio', () => {
        expect(testoBanda({ min: 1.05, max: 1000, vuota: false })).toBe('1.05-1000');
        expect(testoBanda({ min: null, max: null, vuota: true }))
            .toBe('vuota (nessun prezzo la soddisfa con la P del modello di adesso)');
        expect(testoBanda(null)).toBe('vuota (nessun prezzo la soddisfa con la P del modello di adesso)');
    });
});
