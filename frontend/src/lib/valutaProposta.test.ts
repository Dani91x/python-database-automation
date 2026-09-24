// La porta TS di `valuta_al_prezzo` riproduce ESATTAMENTE il file d'oro scritto
// dal Python (`python -m Betfair.safe_strategy.tools.genera_oro_valuta_proposta`).
// Se una delle due funzioni cambia da sola, questo test (o il gemello Python
// `test_scheda_al_ms_2026_09_24.py`) diventa rosso.
import { describe, expect, it } from 'vitest';
import oro from './valutaProposta.golden.json';
import { valutaAlPrezzo, testoMotivo, type CriteriProposta } from './valutaProposta';

interface Caso {
    nome: string;
    ingresso: { side: unknown; prezzo: unknown; abbinabile: unknown; p_model: unknown;
        criteri: CriteriProposta | null };
    uscita: ReturnType<typeof valutaAlPrezzo>;
}

describe('valutaAlPrezzo = valuta_al_prezzo (file d’oro)', () => {
    const casi = oro as unknown as Caso[];

    it('il file d’oro ha casi validi e non validi', () => {
        expect(casi.length).toBeGreaterThan(20);
        expect(casi.some((c) => c.uscita.valida)).toBe(true);
        expect(casi.some((c) => !c.uscita.valida)).toBe(true);
    });

    for (const caso of (oro as unknown as Caso[])) {
        it(caso.nome, () => {
            expect(valutaAlPrezzo(caso.ingresso)).toEqual(caso.uscita);
        });
    }
});

describe('testoMotivo', () => {
    it('dice valore e soglia', () => {
        expect(testoMotivo({ codice: 'edge_sotto_minimo', valore: 0.012, soglia: 0.03 }))
            .toBe('vantaggio sotto la soglia del modello: 0.012 contro soglia 0.03');
    });
    it('usa il testo del servizio quando c’è', () => {
        expect(testoMotivo({ codice: 'non_piu_proposta_dal_modello', valore: null, soglia: null,
            testo: 'il modello non la propone piu\'' })).toBe('il modello non la propone piu\'');
    });
});
