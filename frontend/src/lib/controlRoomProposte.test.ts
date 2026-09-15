// ============================================================================
// controlRoomProposte.test.ts — la matematica delle proposte di chiusura.
//
// Qui si decide se un ordine VERO parte o no. Ogni blocco dice quale errore
// impedisce, e quasi tutti sono errori che costano soldi, non pixel.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    scostamento, abbinabileSufficiente, motivoNonApprovabile, ordinaProposte, prezzoVivo,
    stakeDiChiusura,
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
        expect(prezzoVivo(tennis, '1.24', 11, 'lay')).toMatchObject({ prezzo: 1.32, abbinabile: 116.38 });
    });

    it('chiusura BACK: prende il lato BACK', () => {
        expect(prezzoVivo(tennis, '1.24', 11, 'back')).toMatchObject({ prezzo: 1.28, abbinabile: 90 });
    });

    it('sceglie la SELEZIONE giusta, non la prima che trova', () => {
        expect(prezzoVivo(tennis, '1.24', 12, 'lay').prezzo).toBe(4.6);
    });

    it('selezione sconosciuta → null, MAI un ripiego inventato', () => {
        expect(prezzoVivo(tennis, '1.24', 99, 'lay')).toMatchObject({ prezzo: null, abbinabile: null });
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
        expect(prezzoVivo(senzaSize, null, 11, 'lay')).toMatchObject({ prezzo: 1.32, abbinabile: null });
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

// ===========================================================================
// REVIEW 15/09 — DUE CRITICI DEL CANCELLO DI APPROVAZIONE.
// ===========================================================================

describe('stakeDiChiusura — quanto si piazza DAVVERO per chiudere', () => {
    it('verificato sui trade veri del 14/09', () => {
        // #287: back 3,00 @ 1,11, chiuso lay @ 1,10 -> la gamba #288 piazzata
        // da Betfair era 3,03
        expect(stakeDiChiusura(3, 1.11, 1.10)).toBe(3.03);
        // #290: back 3,00 @ 1,04, chiuso lay @ 1,03 -> gamba #292 = 3,03
        expect(stakeDiChiusura(3, 1.04, 1.03)).toBe(3.03);
    });

    it('chiudere a quota PIU BASSA costa PIU della size di ingresso', () => {
        const s = stakeDiChiusura(10, 3.0, 2.0) as number;
        expect(s).toBe(15);
        expect(s).toBeGreaterThan(10);   // il controllo con 10 sarebbe ottimista
    });

    it('chiudere a quota PIU ALTA costa meno', () => {
        expect(stakeDiChiusura(10, 2.0, 4.0)).toBe(5);
    });

    it('ingrediente mancante o assurdo -> null, mai un numero inventato', () => {
        expect(stakeDiChiusura(null, 1.1, 1.1)).toBeNull();
        expect(stakeDiChiusura(3, null, 1.1)).toBeNull();
        expect(stakeDiChiusura(3, 1.1, null)).toBeNull();
        expect(stakeDiChiusura(3, 1.0, 1.1)).toBeNull();   // quota non valida
        expect(stakeDiChiusura(0, 1.1, 1.1)).toBeNull();
    });
});

describe('quote FERME non sono quote VECCHIE (critico)', () => {
    const base = {
        scost: { delta: 0, fuoriTolleranza: false } as never,
        etaMassimaS: 20,
        daChiudere: 3,
        abbinabileOra: 500,
    };

    it('prezzo fermo da 40 s ma SCANNER VIVO: si approva', () => {
        // e' il caso di un mercato poco scambiato: quel prezzo e' CORRENTE
        expect(motivoNonApprovabile({ ...base, etaQuoteS: 40, etaScannerS: 2 })).toBeNull();
    });

    it('prezzo vecchio 40 s e SCANNER FERMO: NON si approva', () => {
        const m = motivoNonApprovabile({ ...base, etaQuoteS: 40, etaScannerS: 60 });
        expect(m).toMatch(/quote vecchie/i);
    });

    it('eta dello scanner IGNOTA: si resta prudenti come prima', () => {
        expect(motivoNonApprovabile({ ...base, etaQuoteS: 40, etaScannerS: null }))
            .toMatch(/quote vecchie/i);
        expect(motivoNonApprovabile({ ...base, etaQuoteS: 40 })).toMatch(/quote vecchie/i);
    });

    it('lo scanner vivo NON scavalca gli altri blocchi: la liquidita resta un veto', () => {
        const m = motivoNonApprovabile({
            ...base, etaQuoteS: 40, etaScannerS: 2, daChiudere: 100, abbinabileOra: 1,
        });
        expect(m).toMatch(/non abbina abbastanza/i);
    });

    it('eta delle quote ignota resta un blocco anche con lo scanner vivo', () => {
        expect(motivoNonApprovabile({ ...base, etaQuoteS: null, etaScannerS: 1 }))
            .toMatch(/età delle quote sconosciuta/i);
    });
});

// ===========================================================================
// REVIEW 15/09 — MERCATO SOSPESO e l'ESITO DELLE RPC.
// ===========================================================================

describe('mercato sospeso: si dice PRIMA, non dopo il rifiuto del servizio', () => {
    const ok = {
        scost: scostamento({ prezzoDecisione: 1.30, prezzoCorrente: 1.30, lato: 'lay' as const }),
        etaQuoteS: 2, etaMassimaS: 20, daChiudere: 2, abbinabileOra: 100,
    };

    it('SUSPENDED blocca, ed e il PRIMO controllo', () => {
        expect(motivoNonApprovabile({ ...ok, statoMercato: 'SUSPENDED' }))
            .toMatch(/mercato sospeso/i);
        // vince anche su un prezzo assente, che altrimenti parlerebbe per primo
        const senzaPrezzo = scostamento({ prezzoDecisione: 1.3, prezzoCorrente: null, lato: 'lay' });
        expect(motivoNonApprovabile({ ...ok, scost: senzaPrezzo, statoMercato: 'SUSPENDED' }))
            .toMatch(/mercato sospeso/i);
    });

    it('CLOSED blocca con parole sue', () => {
        expect(motivoNonApprovabile({ ...ok, statoMercato: 'CLOSED' })).toMatch(/mercato chiuso/i);
    });

    it('mercato APERTO o stato IGNOTO non blocca niente', () => {
        expect(motivoNonApprovabile({ ...ok, statoMercato: 'OPEN' })).toBeNull();
        expect(motivoNonApprovabile({ ...ok, statoMercato: null })).toBeNull();
        expect(motivoNonApprovabile(ok)).toBeNull();
    });

    it('prezzoVivo riporta lo stato del mercato dal feed', () => {
        const sospeso = {
            mo_status: 'SUSPENDED',
            odds: { p1: { selection_id: 11, back: 1.28, lay: 1.32, back_size: 5, lay_size: 5 } },
        } as unknown as TennisScanPayload;
        expect(prezzoVivo(sospeso, null, 11, 'lay').statoMercato).toBe('SUSPENDED');
    });
});
