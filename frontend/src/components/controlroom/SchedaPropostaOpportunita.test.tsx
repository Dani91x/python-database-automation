// ============================================================================
// SchedaPropostaOpportunita.test.tsx — LA SCHEDA CHE DECIDE UN'APERTURA.
//
// Ordine dell'utente (17/09): le opportunità di modello (calcio e tennis)
// devono arrivare come la card della chiusura, con TUTTE le informazioni e i
// due tasti PIAZZA / RIFIUTA. Qui si verifica che ogni numero su cui si decide
// sia davvero a schermo, che in LIVE serva la doppia conferma e che il
// bottone, quando è spento, DICA PERCHÉ.
//
// 18/09 — ORDINE DELL'UTENTE: «il prezzo può muoversi, io devo vedere la tab
// aggiornata e quando clicco prendiamo QUEL NUMERO CHE VEDO.» PIAZZA ora
// richiede un `prezzoVivo`/`prezziViviGambe` noto e manda ESATTAMENTE quel
// numero — mai quello della proposta.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
    SchedaPropostaOpportunita, motivoNonPiazzabile, motivoNonPiazzabileCombo,
} from './SchedaPropostaOpportunita';
import type { PropostaOpportunita, PrezziViviGambe } from '@/lib/safeBot';

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
    it('mostra TUTTE le informazioni su cui si decide, prezzo VIVO in grande', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} prezzoVivo={1.32} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-partita').textContent).toContain('Pieczonka v Trungelliti');
        expect(screen.getByTestId('cr-opp-partita').textContent).toContain('set 1-0');
        expect(screen.getByTestId('cr-opp-sport').textContent).toContain('tennis');
        expect(screen.getByTestId('cr-opp-lato').textContent).toContain('Punta');
        expect(screen.getByTestId('cr-opp-selezione').textContent).toContain('Pieczonka');
        expect(screen.getByTestId('cr-opp-mercato').textContent).toContain('MATCH_ODDS');
        // il numero GRANDE è il prezzo VIVO (quello che PIAZZA manderà), non
        // la fotografia della proposta (1,30) né quella su cui ha deciso (1,28)
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('1,32');
        expect(screen.getByTestId('cr-opp-prezzo').textContent).toContain('1,28');
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

    it('senza prezzo vivo, PIAZZA resta ACCESO e lo dice (24/09: avviso, non blocco) — CRITERIO ESPLICITO', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('prezzo vivo assente');
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('—');
    });

    it('PIAZZA manda ESATTAMENTE il prezzo vivo mostrato, non quello della proposta — CRITERIO ESPLICITO', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        // la proposta dice 1,30 / 1,28: la scheda mostra (e deve mandare) 1,35
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} prezzoVivo={1.35} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('1,35');
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        expect(onPiazza).toHaveBeenCalledWith(77, 1.35, undefined, undefined, expect.objectContaining({ prezzo_vivo_assente: false, fonte: 'scanner' }));
    });

    it('il prezzo vivo cambia fra due render: PIAZZA manda sempre quello CORRENTE', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        const { rerender } = render(<SchedaPropostaOpportunita proposta={proposta()}
            abbinabileOra={500} etaQuoteS={3} prezzoVivo={1.31} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        rerender(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} prezzoVivo={1.40} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('1,40');
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        expect(onPiazza).toHaveBeenCalledWith(77, 1.40, undefined, undefined, expect.objectContaining({ prezzo_vivo_assente: false, fonte: 'scanner' }));
    });

    it('lo slippage impostato a video viaggia con l’approvazione', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} prezzoVivo={1.32} slippagePct={5} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalledWith(77, 1.32, undefined, 5, expect.objectContaining({ prezzo_vivo_assente: false, fonte: 'scanner' })));
    });

    it('in LIVE il primo clic ARMA e solo il secondo manda: sono soldi veri', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta({ mode: 'live' })}
            abbinabileOra={500} etaQuoteS={3} prezzoVivo={1.3} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        expect(screen.getByTestId('cr-opp-modalita').textContent).toContain('soldi veri');
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        expect(onPiazza).not.toHaveBeenCalled();
        fireEvent.click(screen.getByTestId('cr-opp-conferma-live'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalledWith(77, 1.3, undefined, undefined, expect.objectContaining({ prezzo_vivo_assente: false, fonte: 'scanner' })));
    });

    it('RIFIUTA chiama il rifiuto con l’id della proposta', async () => {
        const onRifiuta = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={3} prezzoVivo={1.3} onPiazza={vi.fn()} onRifiuta={onRifiuta} />);
        fireEvent.click(screen.getByTestId('cr-opp-rifiuta'));
        await waitFor(() => expect(onRifiuta).toHaveBeenCalledWith(77));
    });

    it('quote vecchie: il bottone resta acceso E dice perché', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={95} prezzoVivo={1.3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('quote vecchie');
    });

    it('età delle quote ignota: avviso, il bottone resta acceso', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={500}
            etaQuoteS={null} prezzoVivo={1.3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('età delle quote ignota');
    });

    it('liquidità insufficiente: in LIVE il FOK annullerebbe tutto', () => {
        render(<SchedaPropostaOpportunita proposta={proposta()} abbinabileOra={1.2}
            etaQuoteS={3} prezzoVivo={1.3} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('FILL_OR_KILL');
    });
});

describe('motivoNonPiazzabile', () => {
    const base = { prezzo: 1.3, size: 5, abbinabileOra: 500, etaQuoteS: 3, prezzoVivo: 1.3 };
    it('con tutto a posto (prezzo vivo compreso) non blocca', () => {
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
    it('CRITERIO ESPLICITO — blocca senza prezzo vivo', () => {
        expect(motivoNonPiazzabile({ ...base, prezzoVivo: null })).toContain('prezzo vivo assente');
        expect(motivoNonPiazzabile({ ...base, prezzoVivo: undefined })).toContain('prezzo vivo assente');
    });
    it('blocca un prezzo vivo non finito', () => {
        expect(motivoNonPiazzabile({ ...base, prezzoVivo: Number.NaN })).toContain('prezzo vivo assente');
        expect(motivoNonPiazzabile({ ...base, prezzoVivo: 1 })).toContain('prezzo vivo assente');
    });
});

// ============================================================================
// COMBO (18/09) — la stessa card, con TUTTE le gambe dentro e un prezzo VIVO
// per ognuna.
// ============================================================================
function propostaCombo(over: Record<string, unknown> = {}): PropostaOpportunita {
    return {
        id: 88, kind: 'place', status: 'proposed',
        created_at: '2026-09-18T21:00:00Z', updated_at: '2026-09-18T21:00:00Z',
        payload: {
            opp_key: '36099001|combo:cA', strategy: 'model', kind: 'combo',
            event_id: '36099001', event_name: 'Roma v Lazio', sport: 'calcio',
            combo_id: 'cA', mode: 'paper', minute: 40, score: '1-0',
            signal_key: 'combo:cA',
            size: 10, liability: 10, ev: 0.18, confidence: 0.85, edge: 0.3,
            rationale: 'dutching', p_model: null, p_implied: null,
            decided_at: '2026-09-18T21:00:00Z', proposed_at: '2026-09-18T21:00:05Z',
            legs: [
                { market_id: 'ou25', market_type: 'OVER_UNDER_25', selection_id: 47972,
                    selection_name: 'Over 2.5 Goals', side: 'back', price: 2.2, size: 5, liability: 5 },
                { market_id: 'btts1', market_type: 'BOTH_TEAMS_TO_SCORE', selection_id: 30246,
                    selection_name: 'Yes', side: 'back', price: 1.9, size: 5, liability: 5 },
            ],
            ...over,
        } as PropostaOpportunita['payload'],
    };
}

const PREZZI_VIVI_COMBO_OK: PrezziViviGambe = { 0: 2.22, 1: 1.91 };

describe('SchedaPropostaOpportunita — COMBO', () => {
    it('mostra TUTTE le gambe con il prezzo VIVO di ognuna', () => {
        render(<SchedaPropostaOpportunita proposta={propostaCombo()}
            prezziViviGambe={PREZZI_VIVI_COMBO_OK} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        const gambe = screen.getAllByTestId('cr-opp-combo-gamba');
        expect(gambe).toHaveLength(2);
        expect(gambe[0].textContent).toContain('Over 2.5 Goals');
        expect(gambe[0].textContent).toContain('OVER_UNDER_25');
        expect(gambe[0].textContent).toContain('2,22');   // prezzo VIVO
        expect(gambe[0].textContent).toContain('2,20');   // fotografia, piu' piccola
        expect(gambe[1].textContent).toContain('Yes');
        expect(gambe[1].textContent).toContain('BOTH_TEAMS_TO_SCORE');
        expect(gambe[1].textContent).toContain('1,91');
        // il tipo si legge in testata come "combinazione" (KIND_IT)
        expect(screen.getAllByText(/combinazione/).length).toBeGreaterThanOrEqual(1);
        // gli importi AGGREGATI restano quelli di sempre (stake/liability totali)
        expect(screen.getByTestId('cr-opp-stake').textContent).toMatch(/10/);
        expect(screen.getByTestId('cr-opp-liability').textContent).toMatch(/10/);
        // NON deve comparire la riga a gamba singola
        expect(screen.queryByTestId('cr-opp-lato')).toBeNull();
    });

    it('senza prezzi vivi delle gambe, PIAZZA resta ACCESO e avvisa — CRITERIO ESPLICITO', () => {
        render(<SchedaPropostaOpportunita proposta={propostaCombo()}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('prezzo vivo assente');
    });

    it('con una sola gamba senza prezzo vivo, PIAZZA resta ACCESO (l’avviso dice quale gamba)', () => {
        render(<SchedaPropostaOpportunita proposta={propostaCombo()}
            prezziViviGambe={{ 0: 2.22, 1: null }} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('gamba 2');
    });

    it('PIAZZA manda ESATTAMENTE i prezzi vivi mostrati per OGNI gamba — CRITERIO ESPLICITO', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={propostaCombo()}
            prezziViviGambe={PREZZI_VIVI_COMBO_OK} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        expect(onPiazza).toHaveBeenCalledWith(88, undefined, { 0: 2.22, 1: 1.91 }, undefined, expect.objectContaining({ prezzo_vivo_assente: false }));
    });

    it('in LIVE il primo clic ARMA anche per una combo', () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={propostaCombo({ mode: 'live' })}
            prezziViviGambe={PREZZI_VIVI_COMBO_OK} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        expect(onPiazza).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-opp-conferma-live')).toBeTruthy();
    });

    it('una gamba con prezzo (della proposta) non valido: avviso, PIAZZA resta acceso', () => {
        const legs = [
            { market_id: 'ou25', market_type: 'OVER_UNDER_25', selection_id: 47972,
                selection_name: 'Over 2.5 Goals', side: 'back', price: 2.2, size: 5, liability: 5 },
            { market_id: 'btts1', market_type: 'BOTH_TEAMS_TO_SCORE', selection_id: 30246,
                selection_name: 'Yes', side: 'back', price: 0, size: 5, liability: 5 },
        ];
        render(<SchedaPropostaOpportunita proposta={propostaCombo({ legs })}
            prezziViviGambe={PREZZI_VIVI_COMBO_OK} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain('prezzo');
    });

    it('RIFIUTA funziona anche su una combo', async () => {
        const onRifiuta = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={propostaCombo()}
            prezziViviGambe={PREZZI_VIVI_COMBO_OK} onPiazza={vi.fn()} onRifiuta={onRifiuta} />);
        fireEvent.click(screen.getByTestId('cr-opp-rifiuta'));
        await waitFor(() => expect(onRifiuta).toHaveBeenCalledWith(88));
    });
});

describe('motivoNonPiazzabileCombo', () => {
    const gambeOk = [
        { price: 2.2, size: 5 }, { price: 1.9, size: 5 },
    ];
    const viviOk: PrezziViviGambe = { 0: 2.2, 1: 1.9 };
    it('con tutte le gambe a posto (prezzi vivi compresi) non blocca', () => {
        expect(motivoNonPiazzabileCombo({ legs: gambeOk, prezziViviGambe: viviOk })).toBeNull();
    });
    it('blocca senza gambe (o con una sola)', () => {
        expect(motivoNonPiazzabileCombo({ legs: [gambeOk[0]], prezziViviGambe: viviOk })).toContain('gambe');
        expect(motivoNonPiazzabileCombo({ legs: null, prezziViviGambe: viviOk })).toContain('gambe');
    });
    it('blocca una gamba con prezzo impossibile', () => {
        expect(motivoNonPiazzabileCombo({ legs: [{ price: 1, size: 5 }, gambeOk[1]], prezziViviGambe: viviOk }))
            .toContain('prezzo');
    });
    it('blocca una gamba con importo nullo', () => {
        expect(motivoNonPiazzabileCombo({ legs: [{ price: 2.2, size: 0 }, gambeOk[1]], prezziViviGambe: viviOk }))
            .toContain('importo');
    });
    it('CRITERIO ESPLICITO — blocca senza la mappa dei prezzi vivi', () => {
        expect(motivoNonPiazzabileCombo({ legs: gambeOk })).toContain('prezzo vivo assente');
        expect(motivoNonPiazzabileCombo({ legs: gambeOk, prezziViviGambe: null })).toContain('prezzo vivo assente');
    });
    it('CRITERIO ESPLICITO — blocca se manca il prezzo vivo di UNA gamba sola', () => {
        expect(motivoNonPiazzabileCombo({ legs: gambeOk, prezziViviGambe: { 0: 2.2, 1: null } }))
            .toContain('gamba 2');
        expect(motivoNonPiazzabileCombo({ legs: gambeOk, prezziViviGambe: { 0: 2.2 } }))
            .toContain('gamba 2');
    });
});
