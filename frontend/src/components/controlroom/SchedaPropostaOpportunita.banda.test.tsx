// ============================================================================
// SchedaPropostaOpportunita.banda.test.tsx - D7 (25/09/2026).
//
// Ordine dell'utente: «I prezzi delle schede devono aggiornarsi anche se il
// mercato si sposta; quando clicco devo essere avvisato del prezzo reale di
// abbinamento e se l'ordine e' stato abbinato». Regola di esecuzione: al clic
// l'ordine parte A MERCATO dentro la BANDA della strategia; fuori banda non
// parte e la scheda lo dice PRIMA del clic, con le parole del servizio.
// Sorgente finta con la FORMA di `LiveLadderRow` (come nel test al ms).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { SchedaPropostaOpportunita } from './SchedaPropostaOpportunita';
import type { PropostaOpportunita } from '@/lib/safeBot';

// criteri come li scrive `proposte_opportunita.criteri_proposta` (tennis di serie)
const CRITERI = {
    min_edge: 0.015, min_size: 20, max_lay_price: 8, min_back_price: 1.02, commission: 0.05,
    min_prob_back: 0.9, max_prob_lay: 0.1, opps_min_edge: 0.03, max_liability_per_trade: 0,
    stake: 5,
};

function proposta(over: Record<string, unknown> = {}): PropostaOpportunita {
    return {
        id: 77, kind: 'place', status: 'proposed',
        created_at: '2026-09-25T21:00:00Z', updated_at: '2026-09-25T21:00:00Z',
        payload: {
            opp_key: '36077210|tennis:MATCH_ODDS:11:back', strategy: 'model', kind: 'tennis',
            event_id: '36077210', event_name: 'Uno v Due', sport: 'tennis',
            market_id: '1.900', market_type: 'MATCH_ODDS', selection_id: 11,
            selection_name: 'Uno', side: 'back', price: 1.1, size: 5, liability: 5,
            mode: 'paper', minute: null, score: 'set 1-0', signal_key: 'tennis:MATCH_ODDS:11:back',
            price_at_decision: 1.1, size_available: 500, size_available_at_decision: 500,
            p_model: 0.99, p_implied: 0.909, edge: 0.0809, ev: 0.08, confidence: 0.9,
            rationale: 'leader', decided_at: '2026-09-25T21:00:00Z',
            proposed_at: '2026-09-25T21:00:00Z',
            criteri: CRITERI,
            valutazione: { valida: true, causa: null, motivi: [] },
            ...over,
        } as unknown as PropostaOpportunita['payload'],
    };
}

function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { cbs.delete(mid); };
        },
        fonte: () => 'canale' as const,
    };
    const spingi = (back: number, size = 500, ms = Date.now()) => act(() => {
        cbs.get('1.900')?.({
            event_id: '36077210', market_id: '1.900', market_type: 'MATCH_ODDS', market_name: 'MO',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [
                { selection_id: 11, name: 'Uno', ltp: back, tv: 0, back: [[back, size]],
                    lay: [[back + 0.01, size]], trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ] },
        });
    });
    return { sorgente: () => src as never, spingi };
}

describe('D7: la banda della strategia sulla scheda, al ms', () => {
    it('dentro la banda: al clic parte a mercato al prezzo di adesso; fuori: lo dice prima del clic', () => {
        const f = sorgenteFinta();
        render(<SchedaPropostaOpportunita proposta={proposta()} sorgenteLadder={f.sorgente}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        f.spingi(1.1);
        const riga = () => screen.getByTestId('cr-opp-esecuzione');
        expect(riga().textContent).toBe('al clic: a mercato, al miglior prezzo di quel momento (ora 1,10), '
            + 'solo dentro la banda 1,05-1000,00 della strategia · FILL_OR_KILL in live');
        expect(riga().getAttribute('data-in-banda')).toBe('true');
        expect(screen.queryByTestId('cr-opp-avviso')?.textContent ?? '').not.toMatch(/fuori dalla banda/);
        // il mercato scende sotto il minimo della banda (1,05): la scheda lo dice al tick
        f.spingi(1.04);
        expect(riga().getAttribute('data-in-banda')).toBe('false');
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain(
            'prezzo attuale 1,04 fuori dalla banda 1,05-1000,00 della strategia: al clic l’ordine non parte');
        // PIAZZA resta acceso: decide il servizio al prezzo dell'istante (puo' rientrare)
        expect(screen.getByTestId('cr-opp-piazza')).toHaveProperty('disabled', false);
        // rientra
        f.spingi(1.06);
        expect(riga().getAttribute('data-in-banda')).toBe('true');
        expect(riga().textContent).toContain('(ora 1,06)');
    });

    it('la banda segue la P del modello scritta dal servizio (mai una soglia ricopiata)', () => {
        const f = sorgenteFinta();
        render(<SchedaPropostaOpportunita proposta={proposta({ p_model: 0.77 })} sorgenteLadder={f.sorgente}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        f.spingi(1.4);
        // p=0,77 tennis: banda 1,36-1000 (file d'oro, caso «tennis back p 0.77»)
        expect(screen.getByTestId('cr-opp-esecuzione').textContent).toContain('banda 1,36-1000,00');
    });

    it('proposta senza criteri: nessuna banda, lo dice (regola del prezzo visto)', () => {
        render(<SchedaPropostaOpportunita proposta={proposta({ criteri: undefined })}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-esecuzione').textContent).toBe(
            'al clic: parte il prezzo a video (proposta senza criteri della strategia: nessuna banda, '
            + 'il servizio ricontrolla la tolleranza)');
        expect(screen.getByTestId('cr-opp-esecuzione').getAttribute('data-in-banda')).toBe('');
    });

    it('combinazione: nessuna banda per gamba, lo dice', () => {
        const legs = [
            { market_id: 'ou25', market_type: 'OVER_UNDER_25', selection_id: 1, selection_name: 'Over',
                side: 'back', price: 2.2, size: 2.5 },
            { market_id: 'btts', market_type: 'BOTH_TEAMS_TO_SCORE', selection_id: 2, selection_name: 'Yes',
                side: 'back', price: 1.9, size: 2.5 },
        ];
        render(<SchedaPropostaOpportunita proposta={proposta({ kind: 'combo', legs })}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-esecuzione').textContent).toMatch(
            /^al clic: partono i prezzi a video delle gambe \(per le combinazioni non c’è una banda/);
    });
});
