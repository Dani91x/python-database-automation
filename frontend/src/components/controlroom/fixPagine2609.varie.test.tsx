// ============================================================================
// fixPagine2609.varie.test.tsx - F-6 / F-7 del test e2e FASE 3 (26/09).
//
//  F-6  una proposta di opportunita' di 41 ore fa (la #257, partita finita)
//       compariva con «Piazza»: `propostaScaduta` (12 ore, o mercato CHIUSO).
//  F-7  senza «al prezzo di adesso» la scheda mostrava P mercato = p_implied
//       de-vig (90,6 %) accanto a un Vantaggio = p_model − 1/quota (0,058):
//       97,6 − 90,6 ≠ 5,8. Ora P mercato = 1/quota della proposta.
//
// Proposta con le chiavi di `proposte_opportunita.corpo_proposta` (Python).
// FALSIFICAZIONE (26/09): rimettendo `p.p_implied` nella cella «P del
// mercato» il test F-7 e' rosso (90,6 %); togliendo il ramo `CLOSED` o l'eta'
// da `propostaScaduta` i test F-6 sono rossi.
// ============================================================================
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SchedaPropostaOpportunita, pMercatoProposta } from './SchedaPropostaOpportunita';
import { propostaScaduta, SCADENZA_PROPOSTA_ORE } from '@/lib/controlRoomProposte';
import type { PropostaOpportunita } from '@/lib/safeBot';

const P257: PropostaOpportunita = {
    id: 257, kind: 'place', status: 'proposed',
    created_at: '2026-09-24T16:03:30Z', updated_at: '2026-09-24T16:03:30Z',
    payload: {
        opp_key: '35999999|model:MATCH_ODDS:1:back', strategy: 'model', kind: 'model',
        event_id: '35999999', event_name: 'Andorra v Malta', sport: 'calcio',
        market_id: '1.9', market_type: 'MATCH_ODDS', selection_id: 1, selection_name: 'Malta',
        side: 'back', price: 1.09, size: 2, liability: 2, mode: 'paper',
        minute: 80, score: '0-1', signal_key: 'model:MATCH_ODDS:1:back',
        price_at_decision: 1.09, size_available: 100, size_available_at_decision: 100,
        p_model: 0.976, p_implied: 0.905953, edge: 0.058, ev: 0.064, confidence: 0.9,
        rationale: 'modello sopra il mercato',
        decided_at: '2026-09-24T16:03:30Z', proposed_at: '2026-09-24T16:03:30Z',
    } as PropostaOpportunita['payload'],
};

describe('F-7: P del mercato coerente col vantaggio mostrato', () => {
    it('senza prezzo vivo: P mercato = 1/1,09 = 91,7 %, e P modello − P mercato = vantaggio', () => {
        render(<SchedaPropostaOpportunita proposta={P257} abbinabileOra={null}
            etaQuoteS={null} prezzoVivo={null} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-pimplied').textContent).toBe('91,7 %');
        expect(screen.getByTestId('cr-opp-edge').textContent).toBe('0,058');
        // la differenza a video torna col vantaggio (al decimo di punto)
        const pm = pMercatoProposta(P257.payload.price, P257.payload.p_implied)!;
        expect(Math.abs((P257.payload.p_model as number) - pm - (P257.payload.edge as number))).toBeLessThan(0.001);
    });
    it('quota assente o non valida: la p_implied del motore (mai un numero inventato)', () => {
        expect(pMercatoProposta(null, 0.9)).toBe(0.9);
        expect(pMercatoProposta(1, 0.9)).toBe(0.9);
        expect(pMercatoProposta(null, null)).toBeNull();
    });
});

describe('F-6: una proposta scaduta non si offre piu\'', () => {
    const ORA = Date.parse('2026-09-26T09:19:38Z');
    it('la #257 (41 ore fa) e\' scaduta; una di 5 minuti fa no', () => {
        expect(SCADENZA_PROPOSTA_ORE).toBe(12);
        expect(propostaScaduta(P257.created_at, null, ORA)).toBe(true);
        expect(propostaScaduta('2026-09-26T09:14:00Z', { mo_status: 'OPEN' }, ORA)).toBe(false);
    });
    it('mercato CHIUSO nel feed = scaduta anche se giovane; data illeggibile non basta', () => {
        expect(propostaScaduta('2026-09-26T09:14:00Z', { mo_status: 'CLOSED' }, ORA)).toBe(true);
        expect(propostaScaduta(null, { mo_status: 'OPEN' }, ORA)).toBe(false);
    });
});
