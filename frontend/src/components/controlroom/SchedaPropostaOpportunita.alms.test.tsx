// ============================================================================
// SchedaPropostaOpportunita.alms.test.tsx - LA SCHEDA AL MS (24/09/2026).
//
// Ordine dell'utente (visto a video): «per QUALSIASI PROPOSTA DI QUALSIASI BOT,
// se il prezzo cambia ricevo "prezzo vivo assente: non si piazza al buio" E
// NON POSSO PIAZZARE NULLA. Voglio una scheda che ricalcola al ms tutto MA NON
// BLOCCA L'ENTRATA: me lo segnala e decido io.»
//
// Qui: il bottone NON si spegne mai per il prezzo; gli avvisi nei tre casi
// (prezzo vivo assente da X s, prezzo mosso di N tick, non piu' valida per il
// modello); al clic parte il prezzo a video con eta'/fonte/flag; i numeri si
// ricalcolano al tick dal ladder; il semaforo SI/QUASI/NO.
// La sorgente finta ha la FORMA di `LiveLadderRow` (lib/live.ts) e di
// `LadderSource` (components/live/LadderView.tsx), come `sorgenteLadderAlMs`.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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
        created_at: '2026-09-24T21:00:00Z', updated_at: '2026-09-24T21:00:00Z',
        payload: {
            opp_key: '36077210|tennis:MATCH_ODDS:11:back', strategy: 'model', kind: 'tennis',
            event_id: '36077210', event_name: 'Uno v Due', sport: 'tennis',
            market_id: '1.900', market_type: 'MATCH_ODDS', selection_id: 11,
            selection_name: 'Uno', side: 'back', price: 1.1, size: 5, liability: 5,
            mode: 'paper', minute: null, score: 'set 1-0', signal_key: 'tennis:MATCH_ODDS:11:back',
            price_at_decision: 1.1, size_available: 500, size_available_at_decision: 500,
            p_model: 0.99, p_implied: 0.909, edge: 0.0809, ev: 0.08, confidence: 0.9,
            rationale: 'leader', decided_at: '2026-09-24T21:00:00Z',
            proposed_at: '2026-09-24T21:00:00Z',
            criteri: CRITERI,
            valutazione: { valida: true, causa: null, motivi: [] },
            ...over,
        } as unknown as PropostaOpportunita['payload'],
    };
}

function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    let staccate = 0;
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { staccate += 1; cbs.delete(mid); };
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
                { selection_id: 22, name: 'Due', ltp: 9, tv: 0, back: [[9, 50]], lay: [[10, 50]],
                    trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ] },
        });
    });
    return { sorgente: () => src as never, spingi, iscritti: () => cbs.size, staccate: () => staccate };
}

describe('scheda al ms: si aggancia al ladder del mercato', () => {
    it('si iscrive con la scheda, aggiorna prezzo, book e numeri a ogni tick, si stacca alla chiusura', () => {
        const f = sorgenteFinta();
        const { unmount } = render(<SchedaPropostaOpportunita proposta={proposta()}
            sorgenteLadder={f.sorgente} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(f.iscritti()).toBe(1);
        f.spingi(1.1);
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('1,10');
        expect(screen.getByTestId('cr-opp-book').textContent).toMatch(/punta 1,10.*banca 1,11/);
        expect(screen.getByTestId('cr-opp-fonte').textContent).toMatch(/canale al ms/);
        // edge al prezzo: 0.99 - 1/1.10 = 0.080909
        expect(screen.getByTestId('cr-opp-edge').textContent).toBe('0,081');
        f.spingi(1.05);
        expect(screen.getByTestId('cr-opp-prezzo-vivo').textContent).toContain('1,05');
        // 0.99 - 1/1.05 = 0.037619 ; P implicita 1/1.05 = 95,2 %
        expect(screen.getByTestId('cr-opp-edge').textContent).toBe('0,038');
        expect(screen.getByTestId('cr-opp-pimplied').textContent).toBe('95,2 %');
        expect(screen.getByTestId('cr-opp-scarto').textContent).toMatch(/5 tick/);
        unmount();
        expect(f.staccate()).toBe(1);
    });

    it('semaforo SI / QUASI / NO coi criteri del modello, al tick', () => {
        const f = sorgenteFinta();
        render(<SchedaPropostaOpportunita proposta={proposta()} sorgenteLadder={f.sorgente}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        const sem = () => screen.getByTestId('cr-opp-semaforo').getAttribute('data-semaforo');
        f.spingi(1.1);
        expect(sem()).toBe('SI');
        // a 1.04 l'edge e' 0.0285 < 0.03 del servizio: NO
        f.spingi(1.04);
        expect(sem()).toBe('NO');
        expect(screen.getByTestId('cr-opp-avviso').textContent).toMatch(/fuori criterio: .*soglia del servizio/);
        // a 1.045 l'edge e' 0.03306: regge; a 1.04 (un tick contro) no -> QUASI
        f.spingi(1.045);
        expect(sem()).toBe('QUASI');
    });
});

describe('PIAZZA non si spegne mai per il prezzo: gli AVVISI', () => {
    it('prezzo vivo assente da X s: avviso con l’ultimo noto, bottone acceso', () => {
        vi.useFakeTimers();
        try {
            vi.setSystemTime(new Date('2026-09-24T21:10:00Z'));
            const f = sorgenteFinta();
            const { rerender } = render(<SchedaPropostaOpportunita proposta={proposta()}
                sorgenteLadder={f.sorgente} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
            f.spingi(1.1, 500, Date.now());
            // il lato BACK sparisce dal ladder (mercato che si svuota)
            act(() => { vi.advanceTimersByTime(12_000); });
            f.spingi(Number.NaN, 0, Date.now());
            rerender(<SchedaPropostaOpportunita proposta={proposta()}
                sorgenteLadder={f.sorgente} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
            const avviso = screen.getByTestId('cr-opp-avviso').textContent ?? '';
            expect(avviso).toMatch(/prezzo vivo assente da 12 s: ultimo noto 1,10/);
            expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        } finally { vi.useRealTimers(); }
    });

    it('prezzo mosso di N tick dalla proposta: avviso, bottone acceso', () => {
        const f = sorgenteFinta();
        render(<SchedaPropostaOpportunita proposta={proposta()} sorgenteLadder={f.sorgente}
            onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        f.spingi(1.13);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toMatch(/prezzo mosso di 3 tick/);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
    });

    it('non più valida per il modello (lo dice il servizio): avviso, semaforo NO, bottone acceso', () => {
        const f = sorgenteFinta();
        render(<SchedaPropostaOpportunita proposta={proposta({
            valutazione: { valida: false, causa: 'modello', motivi: [{ codice: 'non_piu_proposta_dal_modello',
                valore: null, soglia: null, testo: 'il modello tennis non la propone piu\'' }] } })}
            sorgenteLadder={f.sorgente} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        f.spingi(1.1);
        expect(screen.getByTestId('cr-opp-avviso').textContent).toMatch(/non più valida per il modello/);
        expect(screen.getByTestId('cr-opp-semaforo').getAttribute('data-semaforo')).toBe('NO');
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
    });
});

describe('al clic parte il prezzo VISTO, con età, fonte e flag', () => {
    it('prezzo vivo dal canale: prezzo a video, fonte canale, flag false', async () => {
        const f = sorgenteFinta();
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} sorgenteLadder={f.sorgente}
            onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        f.spingi(1.09, 500, Date.now() - 300);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        const [id, prezzo, gambe, , ctx] = onPiazza.mock.calls[0];
        expect(id).toBe(77);
        expect(prezzo).toBe(1.09);
        expect(gambe).toBeUndefined();
        expect(ctx.fonte).toBe('canale');
        expect(ctx.prezzo_vivo_assente).toBe(false);
        expect(ctx.eta_ms).toBeGreaterThanOrEqual(300);
    });

    it('nessun prezzo mai visto: parte il prezzo della proposta con prezzo_vivo_assente=true', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        expect((screen.getByTestId('cr-opp-piazza') as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        const [, prezzo, , , ctx] = onPiazza.mock.calls[0];
        expect(prezzo).toBe(1.1);
        expect(ctx).toMatchObject({ prezzo_vivo_assente: true, fonte: 'proposta', eta_ms: null });
    });

    it('prezzo vivo sparito dopo averlo visto: parte l’ULTIMO NOTO con la sua età e il flag', async () => {
        const f = sorgenteFinta();
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta()} sorgenteLadder={f.sorgente}
            onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        f.spingi(1.08, 500, Date.now() - 5000);
        f.spingi(Number.NaN, 0, Date.now());
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        const [, prezzo, , , ctx] = onPiazza.mock.calls[0];
        expect(prezzo).toBe(1.08);
        expect(ctx.prezzo_vivo_assente).toBe(true);
        expect(ctx.fonte).toBe('canale');
        expect(ctx.eta_ms).toBeGreaterThanOrEqual(5000);
    });
});

// B17 (25/09) — col prezzo visto parte il prezzo del SEGNALE: quello alla
// NASCITA della proposta (`price_at_decision`), anche quando il servizio ha
// riscritto `price` col prezzo di adesso.
describe('B17: al clic parte anche il prezzo del segnale', () => {
    it('segnale = price_at_decision, non il price riscritto', async () => {
        const f = sorgenteFinta();
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta({ price: 1.15, price_at_decision: 1.1 })}
            sorgenteLadder={f.sorgente} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        f.spingi(1.12);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        const [, prezzo, , , ctx] = onPiazza.mock.calls[0];
        expect(prezzo).toBe(1.12);
        expect(ctx.prezzo_segnale).toBe(1.1);
    });
    it('senza price_at_decision: il price della proposta', async () => {
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={proposta({ price: 1.15, price_at_decision: null })}
            onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        expect(onPiazza.mock.calls[0][4].prezzo_segnale).toBe(1.15);
    });
});
