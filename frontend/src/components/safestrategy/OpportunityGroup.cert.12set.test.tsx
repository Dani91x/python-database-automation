// ============================================================================
// CERTIFICAZIONE 12/09 — dati in tempo reale sulle card OPPORTUNITÀ.
//
// Regressioni:
//   · l'età mostrata è quella del CALCOLO, non della quota: va detto, e
//     l'età VERA (riga del feed) deve poter spegnere «Piazza»;
//   · `source='default'` (λ di ripiego, visto nel feed reale) non deve
//     arrivare a schermo come codice nudo;
//   · la linea Over/Under non va stampata due volte ("Over/Under 5.5 5,5");
//   · per una COMBINAZIONE l'abbinabile è lo stake TOTALE massimo che entra
//     su tutte le gambe, non la size della gamba più stretta.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
    OpportunityGroup, comboMatchableTotal, lambdaSourceLabel, lambdaSourceIsWeak, marketLabelOf,
} from './OpportunityGroup';
import { feedFreshness, type SafeOpportunityRow } from '@/lib/safeBot';

const NOW = Date.UTC(2026, 8, 12, 15, 0, 0);

const OPP = {
    kind: 'model', market_type: 'OVER_UNDER', market_name: null, line: 5.5,
    market_id: '1.262261950', selection_id: 1485567, selection_name: 'Under 5.5 Goals',
    side: 'back', price: 1.05, size_available: 120, p_model: 0.97, p_implied: 0.95,
    edge: 0.02, ev: 0.01, confidence: 0.8, rationale: null,
};

function row(over: Partial<SafeOpportunityRow> = {}, payload: Record<string, unknown> = {}): SafeOpportunityRow {
    return {
        event_id: '36000001', sport: 'calcio',
        updated_at: new Date(NOW - 5_000).toISOString(),
        payload: {
            minute: 46, score_home: 0, score_away: 1, event_name: 'Wofoo Tai Po v Hong Kong FC',
            source: 'fixture', lambdas: { home: 1.35, away: 1.15 }, opps: [OPP], ...payload,
        },
        ...over,
    } as unknown as SafeOpportunityRow;
}

function renderGroup(r: SafeOpportunityRow, over: Record<string, unknown> = {}) {
    return render(
        <OpportunityGroup
            row={r} mode="paper" stake={5} requests={[]} minConfidence={0} sideFilter="all"
            nowMs={NOW} onPlace={vi.fn(async () => 1)} {...over}
        />,
    );
}

describe('sorgente dei λ: mai un codice tecnico a schermo', () => {
    it('"default" (ripiego reale del servizio) diventa una frase in italiano', () => {
        expect(lambdaSourceLabel('default')).toMatch(/ripiego/);
        expect(lambdaSourceLabel('default')).not.toBe('default');
        expect(lambdaSourceIsWeak('default')).toBe(true);
        expect(lambdaSourceIsWeak('fixture')).toBe(false);
    });

    it('codice sconosciuto: leggibile, senza underscore', () => {
        expect(lambdaSourceLabel('qualche_fonte_nuova')).toBe('λ da qualche fonte nuova');
    });

    it('λ di ripiego: il badge AVVERTE (ambra), non finge un modello', () => {
        renderGroup(row({}, { source: 'default' }));
        const b = screen.getByTestId('opp-lambda-source');
        expect(b).toHaveAttribute('data-weak', 'true');
        expect(b).toHaveTextContent('ripiego');
    });
});

describe('etichetta del mercato: la linea una volta sola', () => {
    it('OVER_UNDER con linea: niente doppione', () => {
        expect(marketLabelOf({ market_name: null, market_type: 'OVER_UNDER', line: 5.5 })).toBe('Over/Under 5,5');
    });
    it('market_name che porta già la linea: non la ripete', () => {
        expect(marketLabelOf({ market_name: 'Over/Under 5.5', market_type: 'OVER_UNDER', line: 5.5 }))
            .toBe('Over/Under 5.5');
    });
    it('mercato senza linea nel nome: la linea si aggiunge', () => {
        expect(marketLabelOf({ market_name: 'Gol Asiatici', market_type: 'ASIAN_HANDICAP', line: 1.5 }))
            .toBe('Gol Asiatici 1,5');
    });
});

describe('età: calcolo del modello vs età VERA delle quote', () => {
    it('il badge dice "calcolo", non si spaccia per età della quota', () => {
        renderGroup(row());
        expect(screen.getByTestId('opp-age')).toHaveTextContent('calcolo 5s fa');
    });

    it('senza freschezza del feed lo dichiara: "età quote n/d"', () => {
        renderGroup(row());
        expect(screen.getByTestId('opp-feed-unknown')).toBeTruthy();
    });

    it('CALCOLO fresco ma FEED morto: «Piazza» SPENTO col motivo vero', () => {
        // il servizio riscrive la riga a ogni ciclo (la confidenza decade col
        // tempo): senza questo controllo una quota di 5 minuti prima appariva
        // come "calcolo 3s fa" col bottone acceso.
        const f = feedFreshness(
            new Date(NOW - 300_000).toISOString(),   // riga del feed: 5 minuti
            new Date(NOW - 2_000).toISOString(),     // scanner vivo
            NOW,
        );
        renderGroup(row(), { freshness: f });
        expect(screen.getByTestId('opp-age')).toHaveTextContent('calcolo 5s fa');
        expect(screen.getByTestId('opp-feed-age')).toHaveTextContent('feed 300s');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('opp-stale-note')).toHaveTextContent('troppo vecchie');
    });

    it('feed fresco e calcolo fresco: «Piazza» acceso', () => {
        const f = feedFreshness(new Date(NOW - 3_000).toISOString(), new Date(NOW - 1_000).toISOString(), NOW);
        renderGroup(row(), { freshness: f });
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        expect(screen.queryByTestId('opp-stale-note')).toBeNull();
    });
});

describe('punteggio: il ritardo del feed è dichiarato', () => {
    it('minuto e punteggio portano il ritardo di 2-3 s', () => {
        renderGroup(row());
        expect(screen.getByTestId('opp-score')).toHaveTextContent('(−2/3 s)');
        expect(screen.getByTestId('opp-score').title).toMatch(/2-3 s di ritardo/);
    });
});

describe('combinazione: abbinabile = stake TOTALE che entra su tutte le gambe', () => {
    it('la gamba più stretta detta il totale massimo', () => {
        // totale 10 €: gamba A 6 € con 12 € abbinabili (→ max 20 €),
        //              gamba B 4 € con 2 € abbinabili  (→ max  5 €)
        const legs = [
            { stake: 6, size_available: 12 },
            { stake: 4, size_available: 2 },
        ];
        expect(comboMatchableTotal(legs, 10)).toBe(5);
    });

    it('una gamba senza size: totale NON verificabile (mai un numero inventato)', () => {
        expect(comboMatchableTotal([{ stake: 5, size_available: 10 }, { stake: 5, size_available: null }], 10))
            .toBeNull();
    });

    it('nessuna gamba o totale nullo: null', () => {
        expect(comboMatchableTotal([], 10)).toBeNull();
        expect(comboMatchableTotal([{ stake: 5, size_available: 10 }], 0)).toBeNull();
    });
});
