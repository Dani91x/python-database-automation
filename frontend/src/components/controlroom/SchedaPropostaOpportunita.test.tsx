// ============================================================================
// SchedaPropostaOpportunita.test.tsx — LA SCHEDA CHE DECIDE UN'APERTURA.
//
// Ordine dell'utente (17/09): le opportunità di modello (calcio e tennis)
// devono arrivare come la card della chiusura, con TUTTE le informazioni e i
// due tasti PIAZZA / RIFIUTA. Qui si verifica che ogni numero su cui si decide
// sia davvero a schermo, che in LIVE serva la doppia conferma e che il
// bottone, quando è spento, DICA PERCHÉ.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SchedaPropostaOpportunita, motivoNonPiazzabile } from './SchedaPropostaOpportunita';
import type { PropostaOpportunita } from '@/lib/safeBot';

// chiavi IDENTICHE a quelle che scrive
// `Betfair/safe_strategy/proposte_opportunita.corpo_proposta`
function proposta(over: Record<string, unknown> = {}): PropostaOpportunita {
    return {
        id: 77, kind: 'place', status: 'proposed',
        created_at: '2026-09-17T21:00:00Z', updated_at: '2026-09-17T21:00:00Z',
        payload: {
            opp_key: '36077210|tennis:MATCH_ODDS:11:back',
            strategy: 'model', kind: 'tennis',
            event_id: '36077210', event_name: 'Pieczonka v Trungelliti',
            sport: 'tennis', market_id: '1.900', market_type: 'MATCH_ODDS',
            selection_id: 11, selection_name: 'Pieczonka', side: 'back',
            price: 1.3, size: 5, liability: 5, mode: 'paper',
            minute: null, score: 'set 1-0 · game 4-2',
            signal_key: 'tennis:MATCH_ODDS:11:back',
            price_at_decision: 1.28, size_available: 500,
            size_available_at_decision: 500,
            p_model: 0.77, p_implied: 0.55, edge: 0.2, ev: 0.15, confidence: 0.9,
            rationale: 'modello sopra il mercato',
            decided_at: '2026-09-17T21:00:00Z', proposed_at: '2026-09-17T21:00:05Z',
            ...over,
        } as PropostaOpportunita['payload'],
    };
}

describe('SchedaPropostaOpportunita', () => {
    it('mostra TUTTE le informazioni su cui si decide', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-partita').textContent).toContain('Pieczonka v Trungelliti');
        expect(screen.getByTestId('cr-opp-partita').textContent).toContain('set 1-0');
        expect(screen.getByTestId('cr-opp-sport').textContent).toContain('tennis');
        expect(screen.getByTestId('cr-opp-lato').textContent).toContain('Punta');
        expect(screen.getByTestId('cr-opp-selezione').textContent).toContain('Pieczonka');
        expect(screen.getByTestId('cr-opp-mercato').textContent).toContain('MATCH_ODDS');
        expect(screen.getByTestId('cr-opp-prezzo').textContent).toContain('1,30');
        expect(screen.getByTestId('cr-opp-stake').textContent).toMatch(/5/);
        expect(screen.getByTestId('cr-opp-liability').textContent).toMatch(/5/);
        expect(screen.getByTestId('cr-opp-abbinabile').textContent).toMatch(/500/);
        expect(screen.getByTestId('cr-opp-pmodel').textContent).toBe('77,0 %');
        expect(screen.getByTestId('cr-opp-pimplied').textContent).toBe('55,0 %');
        expect(screen.getByTestId('cr-opp-edge').textContent).toBe('0,200');
        expect(screen.getByTestId('cr-opp-ev').textContent).toBe('0,150');
        expect(screen.getByTestId('cr-opp-confidence').textContent).toBe('90,0 %');
        expect(screen.getByTestId('cr-opp-rationale').textContent).toContain('modello sopra il mercato');
        // la MODALITA' con cui l'ordine partirebbe, scritta due volte perché è
        // l'informazione che nessuno deve poter fraintendere
        expect(screen.getByTestId('cr-opp-modalita').textContent).toContain('paper');
        expect(screen.getByTestId('cr-opp-eta').textContent).toContain('PAPER');
        // e i DUE tasti
        expect(screen.getByTestId('cr-opp-piazza')).toBeTruthy();
        expect(screen.getByTestId('cr-opp-rifiuta')).toBeTruthy();
    });

    it('in PAPER un clic solo manda l’ordine', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalledWith(77));
    });

    it('in LIVE il primo clic ARMA e solo il secondo manda: sono soldi veri', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta({ mode: 'live' })}
            abbinabileOra={500} etaQuoteS={3} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-modalita').textContent).toContain('soldi veri');
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        expect(onPiazza).not.toHaveBeenCalled();
        fireEvent.click(screen.getByTestId('cr-opp-conferma-live'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalledWith(77));
    });

    it('RIFIUTA chiama il rifiuto con l’id della proposta', async () => {
        const onRifiuta = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} onPiazza={vi.fn()} onRifiuta={onRifiuta} />);
        fireEvent.click(screen.getByTestId('cr-opp-rifiuta'));
        await waitFor(() => expect(onRifiuta).toHaveBeenCalledWith(77));
    });

    it('quote vecchie: il bottone è spento E dice perché', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={95} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId('cr-opp-bloccata').textContent).toContain('quote vecchie');
    });

    it('età delle quote ignota: fail-closed, non si piazza al buio', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={null} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId('cr-opp-bloccata').textContent).toContain('età delle quote ignota');
    });

    it('liquidità insufficiente: in LIVE il FOK annullerebbe tutto', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={1.2}
            etaQuoteS={3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId('cr-opp-bloccata').textContent).toContain('FILL_OR_KILL');
    });
});

describe('motivoNonPiazzabile', () => {
    const base = { prezzo: 1.3, size: 5, abbinabileOra: 500, etaQuoteS: 3 };
    it('con tutto a posto non blocca', () => {
        expect(motivoNonPiazzabile(base)).toBeNull();
    });
    it('blocca un prezzo impossibile', () => {
        expect(motivoNonPiazzabile({ ...base, prezzo: 1 })).toContain('prezzo');
    });
    it('blocca un importo nullo', () => {
        expect(motivoNonPiazzabile({ ...base, size: 0 })).toContain('importo');
    });
    it('blocca un book vuoto', () => {
        expect(motivoNonPiazzabile({ ...base, abbinabileOra: 0 })).toContain('abbinabile');
    });
});
