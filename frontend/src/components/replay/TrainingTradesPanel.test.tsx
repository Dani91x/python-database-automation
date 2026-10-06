// 06/10 — i trade del ladder training: listati e ELIMINABILI con la X.
// API di training VERA (createTrainingApi + matching engine) su un book finto
// con la forma di BookSnapshot.
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import type { BookSnapshot } from '@/lib/matching';
import { createTrainingApi } from '@/lib/trainingLadder';
import { TrainingTradesPanel } from './TrainingTradesPanel';

const T0 = 1_000_000;
const libro: BookSnapshot = {
    ts: T0, back: [[2.0, 100]], lay: [[2.02, 100]], ltp: 2.0, tv: 500, trd: [[2.0, 500]], status: 'OPEN',
};

function nuovaApi() {
    const ora = { t: T0 };
    const api = createTrainingApi({
        eventId: 'ev1', getSnaps: () => [libro], getNow: () => ora.t, isInplayAt: () => false,
    });
    return { api, ora };
}

async function piazza(api: ReturnType<typeof nuovaApi>['api'], side: 'back' | 'lay', price: number) {
    return api.send({
        action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11, handicap: 0,
        side, order_type: 'LIMIT', price, size: 5, persistence: 'LAPSE',
    });
}

describe('TrainingApi.remove / onChange', () => {
    it('remove elimina il trade, avvisa, e gli altri restano', async () => {
        const { api } = nuovaApi();
        let avvisi = 0;
        const via = api.onChange(() => { avvisi += 1; });
        await piazza(api, 'back', 2.0);
        await piazza(api, 'lay', 1.5);
        expect(api.resolved()).toHaveLength(2);
        const primo = api.resolved()[0].order.id;
        expect(api.remove(primo)).toBe(true);
        expect(api.resolved().map(r => r.order.id)).not.toContain(primo);
        expect(api.resolved()).toHaveLength(1);
        expect(api.remove(primo)).toBe(false);            // gia' tolto
        expect(avvisi).toBe(3);                            // 2 piazzati + 1 eliminato
        via();
        api.reset();
        expect(avvisi).toBe(3);                            // disiscritto
    });
});

describe('TrainingTradesPanel', () => {
    it('elenca i trade con lo stato del matching e la X li elimina', async () => {
        const { api } = nuovaApi();
        await piazza(api, 'back', 2.0);    // abbinato subito al best back 2.0
        await piazza(api, 'back', 3.0);    // in coda
        render(<TrainingTradesPanel api={api} nowMs={T0}
            nomeMercato={() => 'Match Odds'} nomeSelezione={() => 'Casa'} />);
        expect(screen.getByText(/Trade del training \(2\)/)).toBeTruthy();
        expect(screen.getByText('abbinato')).toBeTruthy();
        expect(screen.getByText('in coda')).toBeTruthy();
        const x = screen.getAllByRole('button', { name: /Elimina il trade/ });
        act(() => { fireEvent.click(x[0]); });
        expect(screen.getByText(/Trade del training \(1\)/)).toBeTruthy();
        expect(api.resolved()).toHaveLength(1);
    });

    it('un ordine piazzato dal ladder compare subito (senza muovere la timeline)', async () => {
        const { api } = nuovaApi();
        render(<TrainingTradesPanel api={api} nowMs={T0}
            nomeMercato={() => 'Match Odds'} nomeSelezione={() => 'Casa'} />);
        expect(screen.getByText(/Nessun ordine/)).toBeTruthy();
        await act(async () => { await piazza(api, 'lay', 1.5); });
        expect(screen.getByText(/Trade del training \(1\)/)).toBeTruthy();
        expect(screen.getByText('BANCA')).toBeTruthy();
    });
});
