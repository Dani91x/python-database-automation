// FIX-B (26/09/2026) KO7: un solo verdetto nel riquadro ML.
// Dato VERO della partita A del referto (fixture 1492980, target_btts, DB 26/09):
//   targets.target_btts = {True: 0.4826, False: 0.5174}  -> Previsione "No / Under" 52 %
//   ensemble_agreement.target_btts = {votes: {rf: True, lgb: True, xgb: True, logreg: False},
//                                     agreement_ratio: 0.75, predicted_class: "True"}
// Prima: "Previsione No 52 %" e, sotto, "classe prevista Si 75 % accordo" (verdetti opposti).
// La VERITA' e' `targets` (probabilita' finali calibrate dell'ensemble: le stesse che
// usano i segnali di valore, Ai Engine/ai_engine/predict_fixture.py "targets": results);
// i voti sono le classi dei 4 modelli base NON calibrati (ensemble_trainer.get_ensemble_agreement).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import type { MLData } from '@/lib/fixtureModels';

vi.mock('@/lib/fixtureModels', async (orig) => ({
    ...(await orig<typeof import('@/lib/fixtureModels')>()),
    fetchML: vi.fn(),
}));

import { fetchML } from '@/lib/fixtureModels';
import { MLPanel } from './MLPanel';

function dati(): MLData {
    return {
        schema_version: '2.0', model_name: 'ensemble_v2', generated_at: '2026-09-25T16:38:00+00:00', run_id: 'r1',
        targets: {
            target_btts: { True: 0.4826, False: 0.5174 },
            target_1x2: { A: 0.3337, D: 0.2072, H: 0.4591 },
        },
        ensemble_agreement: {
            target_btts: { votes: { rf: 'True', lgb: 'True', xgb: 'True', logreg: 'False' }, agreement_ratio: 0.75, predicted_class: 'True' },
            target_1x2: { votes: { rf: 'H', lgb: 'H', xgb: 'H', logreg: 'D' }, agreement_ratio: 0.75, predicted_class: 'H' },
        },
        calibration_metrics: { target_btts: { brier: 0.2489, ece: 0.03 }, target_1x2: { brier: 0.5895, ece: 0.0533 } },
        reliability: { alpha: 1, grade: 'high', score: 1 },
        coverage: { features_pct: 1, matches_home: 110, matches_away: 111 },
        bet_signals: [], no_bet_reasons: [], targets_not_reliable: [], targets_skipped: [],
    };
}

async function apriSu(target: string) {
    const s = render(<MLPanel fixtureId="1492980" leagueName="First Division" homeName="Cobh" awayName="Athlone" />);
    fireEvent.click(s.getByRole('button', { name: /Modelli ML/ }));
    await waitFor(() => expect(s.getByText(/Mercato \(2\)/)).toBeTruthy());
    fireEvent.click(s.getByRole('button', { name: target }));
    return s;
}

beforeEach(() => { vi.mocked(fetchML).mockReset(); });

describe('MLPanel - un solo verdetto', () => {
    it('BTTS del referto: il verdetto e\' la Previsione calibrata (No 52 %), nessuna "classe prevista" opposta', async () => {
        vi.mocked(fetchML).mockResolvedValue(dati());
        const s = await apriSu('BTTS');
        await waitFor(() => expect(s.getByTestId('ml-accordo')).toBeTruthy());
        expect(s.queryByText(/classe prevista/i)).toBeNull();
        // accordo MISURATO sulla previsione mostrata: 1 modello su 4 (logreg)
        expect(s.getByTestId('ml-accordo').textContent).toMatch(/1\/4/);
        // la divergenza dei voti grezzi e' dichiarata come tale, non come secondo verdetto
        expect(s.getByTestId('ml-voti-divergenti').textContent).toMatch(/non calibrat/i);
    });

    it('1X2 concorde: 3/4 modelli con la Previsione, nessun avviso di divergenza', async () => {
        vi.mocked(fetchML).mockResolvedValue(dati());
        const s = await apriSu('1X2 (FT)');
        await waitFor(() => expect(s.getByTestId('ml-accordo')).toBeTruthy());
        expect(s.getByTestId('ml-accordo').textContent).toMatch(/3\/4/);
        expect(s.queryByTestId('ml-voti-divergenti')).toBeNull();
    });
});
