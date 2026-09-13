// ============================================================================
// CERTIFICAZIONE 12/09 — "cosa vede il trader quando apre una posizione".
//
// Regressioni delle quattro bugie tolte da InvestAction:
//   1. fill PARZIALE mostrato come "eseguito" (caso REALE: richiesta #7
//      dell'11/09, richiesti 5,00 €, result.size 0,43);
//   2. ordine a ESITO IGNOTO (pending_fill) mostrato come "eseguito";
//   3. richiesta DEDUPLICATA mostrata come "eseguito" (nessun ordine nuovo);
//   4. stake oltre l'importo abbinabile al miglior prezzo (in LIVE l'ordine è
//      FILL_OR_KILL: verrebbe annullato per intero) con il bottone acceso.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { InvestAction, placementOutcome, type InvestActionProps } from './InvestAction';
import type { SafeRequest } from '@/lib/safeBot';

function req(over: Partial<SafeRequest> = {}): SafeRequest {
    return {
        id: 7, kind: 'place', status: 'done',
        payload: { size: 5, price: 1.08 },
        result: { ok: true, size: 5, price: 1.08, status: 'open', pending_fill: false },
        created_at: '2026-09-12T15:00:00Z', updated_at: '2026-09-12T15:00:02Z',
        ...over,
    } as SafeRequest;
}

describe('placementOutcome — "done" del servizio NON significa "eseguito"', () => {
    it('fill PIENO: eseguito, con quanto è stato abbinato', () => {
        const o = placementOutcome(req())!;
        expect(o.tone).toBe('ok');
        expect(o.label).toBe('eseguito');
        expect(o.message).toContain('abbinati 5,00 €');
        expect(o.noNewOrder).toBe(false);
    });

    it('fill PARZIALE (caso reale #7: 0,43 su 5,00): NON è "eseguito"', () => {
        const o = placementOutcome(req({ result: { ok: true, size: 0.43, price: 1.08, status: 'open' } }))!;
        expect(o.tone).toBe('partial');
        expect(o.label).toBe('abbinato in parte');
        expect(o.message).toContain('abbinati 0,43 €');
        expect(o.message).toContain('5,00 €');
        expect(o.message).toContain('4,57 €');
    });

    it('esito IGNOTO (pending_fill): "in attesa di abbinamento", non "eseguito"', () => {
        const o = placementOutcome(req({ result: { ok: true, status: 'pending', pending_fill: true } }))!;
        expect(o.tone).toBe('awaiting');
        expect(o.label).toBe('in attesa di abbinamento');
        expect(o.message).toMatch(/non è ancora confermato/);
    });

    it('richiesta DEDUPLICATA: nessun ordine nuovo, e lo dice', () => {
        const o = placementOutcome(req({ result: { ok: true, deduplicated: true, trade_id: 40, status: 'open' } }))!;
        expect(o.tone).toBe('duplicate');
        expect(o.label).toBe('già piazzato');
        expect(o.noNewOrder).toBe(true);
    });

    it('rifiuto ed errore restano tali, col motivo del servizio', () => {
        const rej = placementOutcome(req({ status: 'rejected', result: { message: 'mercato sospeso' } }))!;
        expect(rej.tone).toBe('rejected');
        expect(rej.message).toBe('mercato sospeso');
        const err = placementOutcome(req({ status: 'error', result: { error: 'riserva_fallita' } }))!;
        expect(err.tone).toBe('error');
        expect(err.message).toBe('riserva_fallita');
    });

    it('in coda: ancora nessun esito', () => {
        expect(placementOutcome(req({ status: 'pending', result: null }))!.tone).toBe('pending');
        expect(placementOutcome(null)).toBeNull();
    });

    it('centesimi di arrotondamento NON sono un fill parziale', () => {
        const o = placementOutcome(req({ result: { ok: true, size: 4.999, status: 'open' } }))!;
        expect(o.tone).toBe('ok');
    });
});

function renderIt(over: Partial<InvestActionProps> = {}) {
    const onPlace = vi.fn(async () => 7);
    const props: InvestActionProps = {
        mode: 'paper', side: 'back', price: 2.5, sizeAvailable: 100, defaultStake: 5,
        requests: [], onPlace, ...over,
    };
    return { onPlace, ...render(<InvestAction {...props} />) };
}

describe('InvestAction — liquidità e cap di rischio spengono il bottone', () => {
    it('stake oltre l abbinabile al miglior prezzo: spento e MOTIVATO', () => {
        renderIt({ sizeAvailable: 3, defaultStake: 5 });
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('invest-liquidity')).toHaveTextContent('abbinabili solo 3,00 €');
        expect(screen.getByTestId('invest-liquidity')).toHaveTextContent('FILL_OR_KILL');
    });

    it('nessuna liquidità al miglior prezzo: spento', () => {
        renderIt({ sizeAvailable: 0 });
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('invest-liquidity')).toHaveTextContent('nessun importo abbinabile');
    });

    it('abbinabile sufficiente: acceso', () => {
        renderIt({ sizeAvailable: 5, defaultStake: 5 });
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        expect(screen.queryByTestId('invest-liquidity')).toBeNull();
    });

    it('size non pubblicata: acceso ma DICHIARATO non verificabile', () => {
        renderIt({ sizeAvailable: null });
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        expect(screen.getByTestId('invest-matchable')).toHaveTextContent('n/d');
        expect(screen.getByText(/non verificabile/)).toBeTruthy();
    });

    it('responsabilità oltre il cap per operazione: spento col numero', () => {
        // LAY 5 € @4,00 → responsabilità 15,00 € > cap 10,00 €
        renderIt({ side: 'lay', price: 4, defaultStake: 5, sizeAvailable: 100, maxLiability: 10 });
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('invest-cap')).toHaveTextContent('15,00 €');
        expect(screen.getByTestId('invest-cap')).toHaveTextContent('10,00 €');
    });

    it('LAY: la responsabilità NON è chiamata "liability aperta" (non esiste ancora)', () => {
        renderIt({ side: 'lay', price: 4, defaultStake: 5, sizeAvailable: 100 });
        expect(screen.getByText(/responsabilità se abbinato/)).toBeTruthy();
        expect(screen.queryByText(/Liability aperta/)).toBeNull();
    });

    /**
     * CERT. 13/09 — SOSTITUISCE «sotto il minimo Betfair: spento col motivo».
     * Quel test certificava un blocco FALSO: il servizio piazza qualsiasi
     * importo fino a 0,01 € col place-and-trim (parcheggio a 1000 → taglio →
     * riprezzo). La soglia di giurisdizione resta a schermo come NOTA, ma non
     * spegne più il bottone: spegnerlo impediva operazioni legittime.
     */
    it('sotto il minimo di giurisdizione: nota informativa, bottone ACCESO', () => {
        renderIt({ defaultStake: 1, minStake: 2 });
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        const note = screen.getByTestId('invest-min-stake');
        expect(note).toHaveTextContent('2,00 €');
        expect(note).toHaveTextContent('1000→cancella→sposta');
    });
});

describe('InvestAction — lo stato dopo il click è onesto a schermo', () => {
    function placed(result: Record<string, unknown>) {
        const r = req({ result });
        const { rerender } = render(
            <InvestAction mode="paper" side="back" price={1.08} sizeAvailable={100}
                defaultStake={5} requests={[]} onPlace={vi.fn(async () => 7)} />,
        );
        fireEvent.click(screen.getByTestId('invest-place'));
        rerender(
            <InvestAction mode="paper" side="back" price={1.08} sizeAvailable={100}
                defaultStake={5} requests={[r]} onPlace={vi.fn(async () => 7)} />,
        );
    }

    it('fill parziale: badge ambra "abbinato in parte", mai "eseguito"', async () => {
        placed({ ok: true, size: 0.43, price: 1.08, status: 'open' });
        const badge = await screen.findByTestId('invest-status');
        expect(badge).toHaveAttribute('data-tone', 'partial');
        expect(badge).toHaveTextContent('abbinato in parte');
        expect(screen.getByTestId('invest-status-message')).toHaveTextContent('0,43 €');
    });

    it('esito ignoto: badge "in attesa di abbinamento" e bottone spento (niente doppia posizione)', async () => {
        placed({ ok: true, status: 'pending', pending_fill: true });
        const badge = await screen.findByTestId('invest-status');
        expect(badge).toHaveAttribute('data-tone', 'awaiting');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
    });
});
