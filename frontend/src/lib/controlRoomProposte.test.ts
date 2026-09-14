// ============================================================================
// controlRoomProposte.test.ts — la matematica delle proposte di chiusura.
//
// Qui si decide se un ordine VERO parte o no. Ogni blocco dice quale errore
// impedisce, e quasi tutti sono errori che costano soldi, non pixel.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    scostamento, abbinabileSufficiente, motivoNonApprovabile, ordinaProposte, prezzoVivo,
    SLIPPAGE_PCT_DEFAULT, type PropostaChiusura,
} from './controlRoomProposte';
import type { TennisScanPayload } from './safeStrategyScan';

function prop(id: number, over: Record<string, unknown> = {}, at = '2026-09-14T12:00:00Z'): PropostaChiusura {
    return {
        id, kind: 'cashout', status: 'proposed', created_at: at,
        payload: { trade_id: id, event_id: 'T1', ...over },
    } as PropostaChiusura;
}

// ------------------------------------------------------------- prezzo vivo

describe('prezzoVivo — il prezzo viene dal FEED, non dalla proposta', () => {
    const tennis = {
        event_name: 'Rossi v Bianchi', p1: 'Rossi', p2: 'Bianchi',
        mo_market_id: '1.24', inplay: true,
        odds: {
            p1: { selection_id: 11, back: 1.28, lay: 1.32, back_size: 90, lay_size: 116.38 },
            p2: { selection_id: 12, back: 4.2, lay: 4.6, back_size: 30, lay_size: 22 },
        },
    } as unknown as TennisScanPayload;

    it('chiusura LAY: prende il lato LAY, che è quello su cui si piazza', () => {
        expect(prezzoVivo(tennis, '1.24', 11, 'lay')).toEqual({ prezzo: 1.32, abbinabile: 116.38 });
    });

    it('chiusura BACK: prende il lato BACK', () => {
        expect(prezzoVivo(tennis, '1.24', 11, 'back')).toEqual({ prezzo: 1.28, abbinabile: 90 });
    });

    it('sceglie la SELEZIONE giusta, non la prima che trova', () => {
        expect(prezzoVivo(tennis, '1.24', 12, 'lay').prezzo).toBe(4.6);
    });

    it('selezione sconosciuta → null, MAI un ripiego inventato', () => {
        expect(prezzoVivo(tennis, '1.24', 99, 'lay')).toEqual({ prezzo: null, abbinabile: null });
    });

    it('senza feed, senza lato o senza selezione non si inventa niente', () => {
        expect(prezzoVivo(null, '1.24', 11, 'lay').prezzo).toBeNull();
        expect(prezzoVivo(tennis, '1.24', 11, null).prezzo).toBeNull();
        expect(prezzoVivo(tennis, '1.24', null, 'lay').prezzo).toBeNull();
    });

    it('un prezzo non valido (≤ 1) non è un prezzo', () => {
        const rotto = { odds: { p1: { selection_id: 11, back: 1, lay: 0 } } } as unknown as TennisScanPayload;
        expect(prezzoVivo(rotto, null, 11, 'lay').prezzo).toBeNull();
        expect(prezzoVivo(rotto, null, 11, 'back').prezzo).toBeNull();
    });

    it('prezzo presente ma size assente: il prezzo vale, l’abbinabile resta ignoto', () => {
        const senzaSize = { odds: { p1: { selection_id: 11, back: 1.28, lay: 1.32 } } } as unknown as TennisScanPayload;
        expect(prezzoVivo(senzaSize, null, 11, 'lay')).toEqual({ prezzo: 1.32, abbinabile: null });
    });
});

// ------------------------------------------------------------- scostamento

describe('scostamento — il verso conta quanto il numero', () => {
    it('chiusura LAY: il prezzo che SALE è contro di noi', () => {
        const s = scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.33, lato: 'lay' });
        expect(s.controDiNoi).toBe(true);
        expect(s.delta).toBeCloseTo(0.03, 6);
    });

    it('chiusura LAY: il prezzo che SCENDE è a nostro favore', () => {
        expect(scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.28, lato: 'lay' }).controDiNoi).toBe(false);
    });

    it('chiusura BACK: il verso è ESATTAMENTE opposto', () => {
        expect(scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.27, lato: 'back' }).controDiNoi).toBe(true);
        expect(scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.33, lato: 'back' }).controDiNoi).toBe(false);
    });

    it('oltre la tolleranza scatta il blocco, dentro no', () => {
        expect(scostamento({ prezzoDecisione: 1.00, prezzoCorrente: 1.019, lato: 'lay' }).fuoriTolleranza).toBe(false);
        expect(scostamento({ prezzoDecisione: 1.00, prezzoCorrente: 1.021, lato: 'lay' }).fuoriTolleranza).toBe(true);
    });

    it('la tolleranza è modificabile', () => {
        expect(scostamento({ prezzoDecisione: 1, prezzoCorrente: 1.05, lato: 'lay', slippagePct: 10 }).fuoriTolleranza).toBe(false);
        expect(SLIPPAGE_PCT_DEFAULT).toBe(2);
    });

    it('PREZZO CORRENTE ASSENTE = fuori tolleranza: non si piazza al buio', () => {
        expect(scostamento({ prezzoDecisione: 1.30, prezzoCorrente: null, lato: 'lay' }).fuoriTolleranza).toBe(true);
        expect(scostamento({ prezzoDecisione: null, prezzoCorrente: 1.30, lato: 'lay' }).fuoriTolleranza).toBe(true);
        expect(scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 0, lato: 'lay' }).fuoriTolleranza).toBe(true);
    });
});

// ------------------------------------------------------------- abbinabile

describe('abbinabileSufficiente — in live è tutto-o-niente', () => {
    it('basta quando il mercato copre quanto serve', () => {
        expect(abbinabileSufficiente(2.0, 2.0)).toBe(true);
        expect(abbinabileSufficiente(2.0, 116.38)).toBe(true);
    });

    it('NON basta quando il mercato copre meno: l’ordine verrebbe annullato per intero', () => {
        expect(abbinabileSufficiente(10.14, 7.70)).toBe(false);
    });

    it('assente non vale «abbastanza»', () => {
        expect(abbinabileSufficiente(2, null)).toBe(false);
        expect(abbinabileSufficiente(null, 100)).toBe(false);
        expect(abbinabileSufficiente(0, 100)).toBe(false);
    });
});

// --------------------------------------------------------- approvabilità

describe('motivoNonApprovabile — l’ordine dei controlli è l’ordine in cui contano', () => {
    const ok = {
        scost: scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.30, lato: 'lay' as const }),
        etaQuoteS: 2, etaMassimaS: 20, daChiudere: 2, abbinabileOra: 100,
    };

    it('tutto a posto: si può approvare', () => {
        expect(motivoNonApprovabile(ok)).toBeNull();
    });

    it('prezzo corrente assente: si dice PRIMA di tutto il resto', () => {
        const s = scostamento({ prezzoDecisione: 1.3, prezzoCorrente: null, lato: 'lay' });
        expect(motivoNonApprovabile({ ...ok, scost: s })).toMatch(/non disponibile/);
    });

    it('ETÀ SCONOSCIUTA blocca: non si piazza su un prezzo di cui non sappiamo l’età', () => {
        expect(motivoNonApprovabile({ ...ok, etaQuoteS: null })).toMatch(/età/);
    });

    it('quote vecchie: blocca e dice di quanto', () => {
        expect(motivoNonApprovabile({ ...ok, etaQuoteS: 45 })).toMatch(/45 s/);
    });

    it('prezzo mosso oltre la tolleranza: blocca', () => {
        const s = scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.40, lato: 'lay' });
        expect(motivoNonApprovabile({ ...ok, scost: s })).toMatch(/tolleranza/);
    });

    it('liquidità insufficiente: blocca e SPIEGA la conseguenza', () => {
        const m = motivoNonApprovabile({ ...ok, daChiudere: 10, abbinabileOra: 4 });
        expect(m).toMatch(/annullato per intero/);
    });
});

// ------------------------------------------------------------------ ordine

describe('ordinaProposte — le urgenti in cima, perché non approvarle costa', () => {
    it('urgente prima di non urgente, a prescindere dall’ora', () => {
        const out = ordinaProposte([
            prop(1, {}, '2026-09-14T11:00:00Z'),
            prop(2, { urgente: true }, '2026-09-14T12:00:00Z'),
        ]);
        expect(out.map((p) => p.id)).toEqual([2, 1]);
    });

    it('a parità di urgenza: la più vecchia prima, perché aspetta da più tempo', () => {
        const out = ordinaProposte([
            prop(1, { urgente: true }, '2026-09-14T12:00:00Z'),
            prop(2, { urgente: true }, '2026-09-14T11:00:00Z'),
        ]);
        expect(out.map((p) => p.id)).toEqual([2, 1]);
    });

    it('non modifica l’array di partenza', () => {
        const src = [prop(1), prop(2, { urgente: true })];
        ordinaProposte(src);
        expect(src.map((p) => p.id)).toEqual([1, 2]);
    });
});
