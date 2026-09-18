// ============================================================================
// certezzaChiusura.test.ts — IL GIUDIZIO «EFFETTIVAMENTE CHIUSA», falsificato.
//
// Ogni riga (`RigaOrdine`) porta le IDENTICHE chiavi delle colonne della
// migrazione `trades_consapevolezza_ordine_2026-09-16.sql`
// (`size_matched`, `size_remaining`, `avg_price_matched`, `betfair_updated_at`)
// o le note equivalenti nel `meta`, esattamente come le legge
// `lib/statoOrdine.ts` — nessuna chiave inventata, nessun tipo diverso dal vero.
//
// Il caso del test "tre pezzi di cui uno non abbinato" ricalca la forma reale
// citata da `components/controlroom/dettaglioRiga.ts:92-97` (Safe, Union
// Brescia-Treviso: più back a chiudere un lay), con numeri scelti apposta
// perché UNO dei tre non abbini nulla.
//
// FALSIFICAZIONE (referto `frontend/CHECKPOINT_F4_CERTEZZA_CHIUSURA_2026-09-18.md`):
// ogni ramo qui sotto è stato spento a mano nel codice vero e il test relativo
// e' diventato rosso, poi ripristinato — md5 prima/dopo identico.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    certezzaChiusura, riepilogoCertezza, eCertezzaVerde, eCertezzaAllarme,
    type PosizioneDaGiudicare,
} from './certezzaChiusura';
import type { RigaOrdine } from './statoOrdine';

function apertura(over: Partial<RigaOrdine> = {}): RigaOrdine {
    return {
        status: 'open', side: 'back', price: 2.0, size: 10,
        size_requested: 10, size_matched: 10, size_remaining: 0,
        avg_price_matched: 2.0, betfair_updated_at: '2026-09-18T10:00:00.000Z',
        meta: null,
        ...over,
    };
}

function gamba(over: Partial<RigaOrdine> = {}): RigaOrdine {
    return {
        status: 'open', side: 'lay', price: 2.0, size: 0,
        size_requested: 0, size_matched: 0, size_remaining: 0,
        avg_price_matched: null, betfair_updated_at: '2026-09-18T10:05:00.000Z',
        meta: null,
        ...over,
    };
}

describe('REGOLATA_DAL_MERCATO vince su tutto', () => {
    it('mercato regolato -> REGOLATA, esposizione zero, anche senza chiusure', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura(), chiusure: [], regolataDalMercato: true, modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('REGOLATA_DAL_MERCATO');
        expect(r.esposizione).toEqual({ stake: 0, liability: 0 });
        expect(eCertezzaVerde(r.stato)).toBe(true);
    });
});

describe('CHIUSA_CONFERMATA: copertura al 100%, dati da Betfair', () => {
    it('back coperto da lay abbinato per intero, dalle COLONNE, in LIVE', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({ side: 'lay', size_matched: 10, size_remaining: 0, avg_price_matched: 2.0 }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSA_CONFERMATA');
        expect(r.esposizione).toEqual({ stake: 0, liability: 0 });
        expect(r.coperturaFrazione).toBe(1);
        expect(eCertezzaVerde(r.stato)).toBe(true);
    });

    it('la STESSA chiusura, ma i numeri vengono SOLO dalla nota (meta) -> NON confermata in LIVE', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({
                    side: 'lay',
                    // nessuna colonna: solo la nota del servizio (fallback di statoOrdine)
                    size_matched: null, size_remaining: null, avg_price_matched: null,
                    betfair_updated_at: null,
                    meta: { size_matched: 10, size_remaining: 0, avg_price_matched: 2.0 },
                }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('NON_VERIFICABILE');
        expect(eCertezzaVerde(r.stato)).toBe(false);
        expect(r.motivo).toMatch(/nota del servizio/);
    });

    it("la STESSA situazione ma in PAPER: la nota basta (la verita' e' il fill simulato)", () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({
                    side: 'lay',
                    size_matched: null, size_remaining: null, avg_price_matched: null,
                    betfair_updated_at: null,
                    meta: { size_matched: 10, size_remaining: 0, avg_price_matched: 2.0 },
                }),
            ],
            regolataDalMercato: false,
            modo: 'paper',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSA_CONFERMATA');
    });
});

describe('CHIUSA_PARZIALE: tre gambe di chiusura, una NON abbinata', () => {
    it('due lay abbinate a 4,00 ciascuna @2,00, la terza annullata senza abbinare nulla', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                // la terza: ANNULLATA, non ha abbinato nulla (nessun residuo vivo)
                gamba({
                    side: 'lay', status: 'cancelled',
                    size_matched: 0, size_remaining: 0, avg_price_matched: null,
                }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSA_PARZIALE');
        // richiesto = 10*2,00/2,00 = 10,00; abbinato = 8,00; residuo ESATTO = 2,00
        expect(r.esposizione.stake).toBeCloseTo(2.0, 2);
        expect(r.esposizione.liability).toBeCloseTo(2.0, 2); // lay: (2,00-1)*2,00
        expect(r.coperturaFrazione).toBeCloseTo(0.8, 5);
        expect(eCertezzaVerde(r.stato)).toBe(false);
    });

    it('il caso reale citato da dettaglioRiga.ts: tre back a chiudere un lay 2 @70, copertura quasi esatta', () => {
        // Union Brescia-Treviso: lay 2 @70 chiuso da back 4,78@9,6 + 7,20@9,6 + 2,08@12
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'lay', size_matched: 2, avg_price_matched: 70 }),
            chiusure: [
                gamba({ side: 'back', size_matched: 4.78, size_remaining: 0, avg_price_matched: 9.6 }),
                gamba({ side: 'back', size_matched: 7.20, size_remaining: 0, avg_price_matched: 9.6 }),
                gamba({ side: 'back', size_matched: 2.08, size_remaining: 0, avg_price_matched: 12 }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        // richiesto = 2*70/9,9552... ~= 14,06; abbinato totale 14,06: copertura ~100%
        expect(r.coperturaFrazione).toBeGreaterThan(0.99);
        expect(['CHIUSA_CONFERMATA', 'CHIUSA_PARZIALE']).toContain(r.stato);
    });
});

describe('CHIUSURA_IN_ATTESA: una gamba ancora sul book può ancora completarsi', () => {
    it('parte abbinata, il resto è ancora appoggiato (non fallito)', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                // appoggiata: nulla abbinato, ma 6 ancora vivi sul book
                gamba({ side: 'lay', size_matched: 0, size_remaining: 6, avg_price_matched: null }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSURA_IN_ATTESA');
        expect(r.coperturaFrazione).toBeCloseTo(0.4, 5);
        expect(eCertezzaVerde(r.stato)).toBe(false);
    });

    it('nessun abbinamento ancora, un solo ordine appoggiato: ATTESA con esposizione intera', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({ side: 'lay', size_matched: 0, size_remaining: 10, avg_price_matched: null }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSURA_IN_ATTESA');
        expect(r.coperturaFrazione).toBe(0);
        expect(r.esposizione.stake).toBe(10);
    });
});

describe('CHIUSURA_FALLITA: rifiutata, nessuna contropartita — posizione ANCORA APERTA', () => {
    it('unica gamba di chiusura rifiutata da Betfair', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({
                    side: 'lay', size_matched: 0, size_remaining: 0,
                    meta: { error_code: 'INSUFFICIENT_FUNDS' },
                }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSURA_FALLITA');
        // TUTTO lo stake d'apertura resta esposto: nessuna copertura è mai avvenuta
        expect(r.esposizione.stake).toBe(10);
        expect(eCertezzaAllarme(r.stato)).toBe(true);
        expect(eCertezzaVerde(r.stato)).toBe(false);
    });
});

describe('NON_VERIFICABILE: dati insufficienti, mai spacciata per chiusa', () => {
    it('apertura senza prezzo medio abbinato -> non calcolabile', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ avg_price_matched: null, price: null }),
            chiusure: [gamba({ side: 'lay', size_matched: 10, avg_price_matched: 2.0 })],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('NON_VERIFICABILE');
        expect(eCertezzaVerde(r.stato)).toBe(false);
    });

    it("nessuna gamba di chiusura: non e' un giudizio di chiusura, mai confermata", () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura(), chiusure: [], regolataDalMercato: false, modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('NON_VERIFICABILE');
    });
});

describe('tennis: la STESSA funzione, senza adattamenti, sulle stringhe di flumine', () => {
    it('EXECUTION_COMPLETE con size_remaining 0 -> abbinata, CONFERMATA', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({
                    status: 'EXECUTION_COMPLETE', side: 'lay',
                    size_matched: 10, size_remaining: 0, avg_price_matched: 2.0,
                }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        expect(certezzaChiusura(pos).stato).toBe('CHIUSA_CONFERMATA');
    });

    it('EXECUTABLE (a riposo, nulla abbinato) -> ATTESA, non fallita e non confermata', () => {
        const pos: PosizioneDaGiudicare = {
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({
                    status: 'EXECUTABLE', side: 'lay',
                    size_matched: 0, size_remaining: 10, avg_price_matched: null,
                }),
            ],
            regolataDalMercato: false,
            modo: 'live',
        };
        const r = certezzaChiusura(pos);
        expect(r.stato).toBe('CHIUSURA_IN_ATTESA');
        expect(r.coperturaFrazione).toBe(0);
    });
});

describe('riepilogoCertezza: paper e live non si sommano MAI', () => {
    const righe = [
        { modo: 'live' as const, risultato: certezzaChiusura({
            apertura: apertura(), chiusure: [], regolataDalMercato: true, modo: 'live',
        }) },
        { modo: 'live' as const, risultato: certezzaChiusura({
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [gamba({
                side: 'lay', status: 'cancelled', size_matched: 0, size_remaining: 0,
            })],
            regolataDalMercato: false, modo: 'live',
        }) }, // CHIUSURA_FALLITA, stake 10 esposto
        { modo: 'paper' as const, risultato: certezzaChiusura({
            apertura: apertura(), chiusure: [], regolataDalMercato: true, modo: 'paper',
        }) },
        { modo: 'paper' as const, risultato: certezzaChiusura({
            apertura: apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 }),
            chiusure: [
                gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                gamba({ side: 'lay', status: 'cancelled', size_matched: 0, size_remaining: 0 }),
            ],
            regolataDalMercato: false, modo: 'paper',
        }) }, // CHIUSA_PARZIALE paper, stake residuo 6,00
    ];

    it("il riepilogo LIVE non include le righe paper (ne' nel conteggio ne' nell'esposizione)", () => {
        const live = riepilogoCertezza(righe, 'live');
        expect(live.n).toBe(2);
        expect(live.regolate).toBe(1);
        expect(live.fallite).toBe(1);
        expect(live.parziali).toBe(0);
        expect(live.esposizioneStakeTotale).toBe(10); // SOLO la fallita live, non i 6 del paper
    });

    it('il riepilogo PAPER non include le righe live', () => {
        const paper = riepilogoCertezza(righe, 'paper');
        expect(paper.n).toBe(2);
        expect(paper.regolate).toBe(1);
        expect(paper.parziali).toBe(1);
        expect(paper.fallite).toBe(0);
        expect(paper.esposizioneStakeTotale).toBe(6); // SOLO il residuo paper, non i 10 del live
    });
});
