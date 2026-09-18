import { describe, it, expect } from 'vitest';
import { prezzoVivoGamba, prezzoVivoPerGamba, type GambaCombo } from './comboPrezzoVivo';
import type { CalcioScanPayload } from './safeStrategyScan';

function payload(over: Partial<CalcioScanPayload> = {}): CalcioScanPayload {
    return {
        media: null, odds_ts_ms: null, event_name: 'A v B', home: 'A', away: 'B',
        competition: 'X', open_date: null, inplay: true,
        mo_market_id: '1.111', mo_status: 'OPEN',
        odds: {
            home: { selection_id: 11, back: 2.04, lay: 2.08, back_size: 50, lay_size: 40 },
            draw: { selection_id: 22, back: 3.5, lay: 3.6 },
            away: { selection_id: 33, back: 4.1, lay: 4.2 },
        },
        minute: 10, score_home: 0, score_away: 0, red_home: 0, red_away: 0,
        ...over,
    } as CalcioScanPayload;
}

describe('prezzoVivoGamba', () => {
    it('trova il prezzo su Match Odds per selection_id', () => {
        const gamba: GambaCombo = { market_id: '1.111', selection_id: 11, side: 'back' };
        const r = prezzoVivoGamba(gamba, [payload()]);
        expect(r.prezzo).toBe(2.04);
        expect(r.abbinabile).toBe(50);
    });

    it('LAY legge il lato lay, non il back', () => {
        const gamba: GambaCombo = { market_id: '1.111', selection_id: 33, side: 'lay' };
        const r = prezzoVivoGamba(gamba, [payload()]);
        expect(r.prezzo).toBe(4.2);
    });

    it('gamba senza market_id: nessun prezzo inventato', () => {
        const r = prezzoVivoGamba({ selection_id: 11, side: 'back' }, [payload()]);
        expect(r.prezzo).toBeNull();
    });

    it('gamba assente: vuoto, non esplode', () => {
        expect(prezzoVivoGamba(null, [payload()]).prezzo).toBeNull();
    });

    it('side non riconosciuto: vuoto', () => {
        const r = prezzoVivoGamba({ market_id: '1.111', selection_id: 11, side: 'strano' }, [payload()]);
        expect(r.prezzo).toBeNull();
    });

    it('cerca la gamba SU UN ALTRO evento se il primo payload non ha quel mercato', () => {
        const altro = payload({ mo_market_id: '1.222', odds: { home: { selection_id: 99, back: 1.5, lay: 1.55 }, draw: null, away: null } });
        const gamba: GambaCombo = { market_id: '1.222', selection_id: 99, side: 'back' };
        const r = prezzoVivoGamba(gamba, [payload(), altro]);
        expect(r.prezzo).toBe(1.5);
    });
});

describe('prezzoVivoPerGamba', () => {
    it('calcola il prezzo PER OGNI gamba, stesso ordine di ingresso', () => {
        const legs: GambaCombo[] = [
            { market_id: '1.111', selection_id: 11, side: 'back' },
            { market_id: '1.111', selection_id: 22, side: 'lay' },
        ];
        const out = prezzoVivoPerGamba(legs, [payload()]);
        expect(out).toHaveLength(2);
        expect(out[0].prezzo).toBe(2.04);
        expect(out[1].prezzo).toBe(3.6);
    });

    it('legs assenti: array vuoto, mai un errore', () => {
        expect(prezzoVivoPerGamba(null, [payload()])).toEqual([]);
        expect(prezzoVivoPerGamba(undefined, [payload()])).toEqual([]);
    });

    // ── FALSIFICAZIONE (documentata nel referto): mutazione manuale che
    // toglie il filtro `v.prezzo != null` in prezzoVivoGamba (prende sempre
    // il primo payload) → il test "cerca la gamba SU UN ALTRO evento" sopra
    // diventa rosso (prezzo null invece di 1.5). Verificato e ripristinato. ──
    it('falsificazione: non deve fermarsi al primo payload se non risolve un prezzo', () => {
        const vuoto = payload({ mo_market_id: '1.999', odds: { home: null, draw: null, away: null } });
        const conPrezzo = payload({ mo_market_id: '1.222', odds: { home: { selection_id: 5, back: 9.9, lay: 10 }, draw: null, away: null } });
        const r = prezzoVivoGamba({ market_id: '1.222', selection_id: 5, side: 'back' }, [vuoto, conPrezzo]);
        expect(r.prezzo).toBe(9.9);
    });
});
