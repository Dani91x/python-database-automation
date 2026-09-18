import { describe, it, expect } from 'vitest';
import { applicaEventoScan, applicaLottoScan, type ScanRowEvent } from './scanEventBuffer';

interface Riga { event_id: string; v: number }

describe('applicaEventoScan', () => {
    it('upsert su una riga nuova: append', () => {
        const out = applicaEventoScan<Riga>([], { type: 'upsert', row: { event_id: 'A', v: 1 } });
        expect(out).toEqual([{ event_id: 'A', v: 1 }]);
    });

    it('upsert su una riga esistente: sostituisce in posizione', () => {
        const base: Riga[] = [{ event_id: 'A', v: 1 }, { event_id: 'B', v: 2 }];
        const out = applicaEventoScan(base, { type: 'upsert', row: { event_id: 'A', v: 9 } });
        expect(out).toEqual([{ event_id: 'A', v: 9 }, { event_id: 'B', v: 2 }]);
    });

    it('delete rimuove la riga', () => {
        const base: Riga[] = [{ event_id: 'A', v: 1 }, { event_id: 'B', v: 2 }];
        const out = applicaEventoScan(base, { type: 'delete', eventId: 'A' });
        expect(out).toEqual([{ event_id: 'B', v: 2 }]);
    });
});

describe('applicaLottoScan', () => {
    it('applicare un lotto produce lo STESSO risultato di applicarli uno a uno, in ordine', () => {
        const base: Riga[] = [{ event_id: 'A', v: 1 }];
        const lotto: ScanRowEvent<Riga>[] = [
            { type: 'upsert', row: { event_id: 'A', v: 2 } },
            { type: 'upsert', row: { event_id: 'B', v: 3 } },
            { type: 'delete', eventId: 'A' },
            { type: 'upsert', row: { event_id: 'B', v: 4 } },
        ];
        const unoAUno = lotto.reduce((acc, ev) => applicaEventoScan(acc, ev), base);
        const inUnColpo = applicaLottoScan(base, lotto);
        expect(inUnColpo).toEqual(unoAUno);
        expect(inUnColpo).toEqual([{ event_id: 'B', v: 4 }]);
    });

    it('lotto vuoto: nessun cambiamento', () => {
        const base: Riga[] = [{ event_id: 'A', v: 1 }];
        expect(applicaLottoScan(base, [])).toEqual(base);
    });

    it('non muta l’array originale (immutabilità)', () => {
        const base: Riga[] = [{ event_id: 'A', v: 1 }];
        const copia = [...base];
        applicaLottoScan(base, [{ type: 'upsert', row: { event_id: 'A', v: 2 } }]);
        expect(base).toEqual(copia);
    });

    // ── FALSIFICAZIONE (documentata nel referto): mutazione manuale che
    // applica il lotto in ordine INVERSO (`[...lotto].reverse().reduce(...)`)
    // → il test sopra ("STESSO risultato... in ordine") diventa rosso perché
    // l'ultimo upsert su 'B' non vince più. Verificato e ripristinato. ──
    it('falsificazione: l’ordine del lotto conta, l’ultimo evento su una riga vince', () => {
        const out = applicaLottoScan<Riga>([], [
            { type: 'upsert', row: { event_id: 'A', v: 1 } },
            { type: 'upsert', row: { event_id: 'A', v: 2 } },
        ]);
        expect(out).toEqual([{ event_id: 'A', v: 2 }]);
    });
});
