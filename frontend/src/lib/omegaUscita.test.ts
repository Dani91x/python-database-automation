// La porta TS dell'uscita di Omega al prezzo di adesso riproduce ESATTAMENTE il
// file d'oro scritto dal Python (`python -m Betfair.omega.tools.genera_oro_uscita`),
// che a sua volta e' a parita' con `omega_v3.proposta_uscita` (test Python
// `test_omega_scheda_al_ms_2026_09_24.py`).
import { describe, expect, it } from 'vitest';
import oro from './omegaUscita.golden.json';
import { esitoUscitaAlPrezzo, type EsitoUscitaAlPrezzo } from './omegaProposte';

interface Caso {
    nome: string;
    ingresso: Parameters<typeof esitoUscitaAlPrezzo>[0];
    uscita: EsitoUscitaAlPrezzo;
}

describe('esitoUscitaAlPrezzo = esito_uscita_al_prezzo (file d’oro)', () => {
    const casi = oro as unknown as Caso[];
    it('copre i rami che propongono e quelli che tengono', () => {
        const motivi = new Set(casi.map((c) => c.uscita.motivo_codice));
        for (const m of ['blocca_il_profitto', 'protezione', 'cap', 'rischio',
            'tenere_vale_di_piu', 'aspettare_vale_di_piu', 'controparte_insufficiente',
            'nessun_prezzo_di_back', 'bloccabile_non_positivo', 'posizione_senza_numeri']) {
            expect(motivi.has(m)).toBe(true);
        }
    });
    for (const caso of (oro as unknown as Caso[])) {
        it(caso.nome, () => {
            expect(esitoUscitaAlPrezzo(caso.ingresso)).toEqual(caso.uscita);
        });
    }
});
