// ============================================================================
// live.valutaReplay.test.ts — CANTIERE G, voce 4 (28/09).
//
// Dal 26/09 (`AUDIT_2026-09-26/FIX_K1_VALUTA_GBP_EUR.md`) le size dello stream
// sono convertite in EUR alla fonte: il recorder marca ogni riga con
// `valuta:'EUR'` SOLO se il book era stato convertito. Match Replay leggeva
// ancora ogni file come sterline (referto §9.1, rischio residuo dichiarato
// "fuori dal perimetro" di quel cantiere).
//
// Verificato sul DB (SOLA LETTURA, 28/09): `live_market_snapshots` ha
// `max(created_at) = 2026-09-22`, PRIMA del fix K1 — OGGI ogni riga
// registrata e' in GBP, nessuna porta il marcatore. `convertiFrameEur` deve
// quindi convertire OGNI riga di oggi (nessun marcatore = storico) e non
// toccare mai una riga futura marcata `valuta:'EUR'` (nessuna doppia
// conversione, il giorno in cui l'importatore la scrivesse).
//
// Il finto: stessa forma del vero (`recorder.py::serialize_book` + il tipo
// `Frame`/`Ladder` di `live.ts`); il marcatore vive dentro `ladder`, come lo
// scrive il recorder (chiave in piu', non un campo del tipo TS).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { convertiFrameEur, convertiFramesEur, CAMBIO_RIPIEGO_GBP_EUR, type Frame } from './live';

function frameGbp(overrides: Partial<Frame> = {}): Frame {
    return {
        market_id: '1.234',
        ts: '2026-09-20T15:00:00Z',
        minute: 10,
        inplay: true,
        status: 'OPEN',
        ladder: {
            '111': {
                back: [[2.0, 10], [2.02, 5]],
                lay: [[2.04, 8]],
                ltp: 2.0,
                tv: 100,
                trd: [[2.0, 40], [1.98, 20]],
            },
        },
        ...overrides,
    };
}

describe('convertiFrameEur — file STORICO (nessun marcatore) = GBP, si converte', () => {
    it('converte le SIZE (back/lay/tv/trd), mai i PREZZI (quote, non denaro)', () => {
        const out = convertiFrameEur(frameGbp(), 1.1647);
        const e = out.ladder['111'];
        expect(e.back).toEqual([[2.0, 10 * 1.1647], [2.02, 5 * 1.1647]]);
        expect(e.lay).toEqual([[2.04, 8 * 1.1647]]);
        expect(e.ltp).toBe(2.0); // prezzo, INVARIATO
        expect(e.tv).toBeCloseTo(100 * 1.1647, 6);
        expect(e.trd).toEqual([[2.0, 40 * 1.1647], [1.98, 20 * 1.1647]]);
    });

    it('usa il cambio di ripiego del backend per default (stessa costante, referti riproducibili)', () => {
        expect(CAMBIO_RIPIEGO_GBP_EUR).toBeCloseTo(1.164687, 5);
        const out = convertiFrameEur(frameGbp());
        expect(out.ladder['111'].back[0][1]).toBeCloseTo(10 * CAMBIO_RIPIEGO_GBP_EUR, 6);
    });

    it('null/undefined in tv non esplode e resta null', () => {
        const f = frameGbp({ ladder: { '111': { back: [], lay: [], ltp: null, tv: null } } });
        const out = convertiFrameEur(f, 1.2);
        expect(out.ladder['111'].tv).toBeNull();
    });
});

describe('convertiFrameEur — riga marcata `valuta:\'EUR\'` = gia\' convertita, NESSUNA doppia conversione', () => {
    it('torna il frame INVARIATO', () => {
        const marcato = frameGbp({
            ladder: {
                valuta: 'EUR' as unknown as Frame['ladder'][string],
                '111': { back: [[2.0, 11.647]], lay: [[2.04, 9]], ltp: 2.0, tv: 116.47 },
            } as Frame['ladder'],
        });
        const out = convertiFrameEur(marcato, 1.1647);
        expect(out.ladder['111'].back).toEqual([[2.0, 11.647]]);
        expect(out.ladder['111'].tv).toBe(116.47);
    });

    it('il marcatore non diventa una selezione fantasma nell\'output', () => {
        const marcato = frameGbp({
            ladder: {
                valuta: 'EUR' as unknown as Frame['ladder'][string],
                '111': { back: [], lay: [], ltp: null, tv: null },
            } as Frame['ladder'],
        });
        const out = convertiFrameEur(marcato, 1.1647);
        expect(Object.keys(out.ladder)).toEqual(['111']);
    });
});

describe('convertiFramesEur — un elenco, stessa regola riga per riga', () => {
    it('converte ogni frame indipendentemente (mai un cambio "medio")', () => {
        const out = convertiFramesEur([frameGbp(), frameGbp({ market_id: '5.678' })], 2);
        expect(out[0].ladder['111'].back[0][1]).toBe(20);
        expect(out[1].market_id).toBe('5.678');
        expect(out[1].ladder['111'].back[0][1]).toBe(20);
    });
});
