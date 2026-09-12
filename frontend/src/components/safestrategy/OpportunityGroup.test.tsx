// Test COMPONENTE di OpportunityGroup: filtri (helper esportato per lo stato
// vuoto della pagina), eta' della riga e "Investi" spento oltre 60 s.
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OpportunityGroup, filterOpps, OPP_ROW_STALE_MS } from './OpportunityGroup';
import type { SafeOpportunityRow } from '@/lib/safeBot';

const NOW = Date.parse('2026-09-10T12:00:00Z');

function row(over: Partial<SafeOpportunityRow> = {}): SafeOpportunityRow {
    return {
        event_id: 'e1', sport: 'calcio',
        updated_at: new Date(NOW - 5_000).toISOString(),
        payload: {
            minute: 60, score_home: 1, score_away: 0, event_name: 'Roma vs Lazio',
            opps: [
                {
                    market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5', line: 2.5,
                    market_id: '1.9', selection_id: 1, selection_name: 'Over 2.5', side: 'back',
                    price: 2.1, size_available: 50, p_model: 0.55, p_implied: 0.48, edge: 0.07,
                    ev: 0.15, confidence: 0.8, rationale: null,
                },
                {
                    market_type: 'MATCH_ODDS', market_name: 'Match Odds', line: null,
                    market_id: '1.1', selection_id: 2, selection_name: 'Lazio', side: 'lay',
                    price: 9, size_available: 20, p_model: 0.05, p_implied: 0.11, edge: 0.06,
                    ev: 0.1, confidence: 0.4, rationale: null,
                },
            ],
        },
        ...over,
    };
}

function renderGroup(r: SafeOpportunityRow, over: Partial<Parameters<typeof OpportunityGroup>[0]> = {}) {
    const onPlace = vi.fn(async () => 1);
    render(
        <OpportunityGroup
            row={r} mode="paper" stake={5} requests={[]} minConfidence={0} sideFilter="all"
            nowMs={NOW} onPlace={onPlace} {...over}
        />,
    );
    return { onPlace };
}

describe('filterOpps', () => {
    it('applica confidenza minima e lato, ordina per EV × confidenza', () => {
        expect(filterOpps(row(), 0, 'all').map((o) => o.selection_id)).toEqual([1, 2]);
        expect(filterOpps(row(), 0.5, 'all').map((o) => o.selection_id)).toEqual([1]);
        expect(filterOpps(row(), 0, 'lay').map((o) => o.selection_id)).toEqual([2]);
        expect(filterOpps(row(), 0.9, 'all')).toEqual([]);
    });

    it('payload senza opps -> vuoto', () => {
        expect(filterOpps(row({ payload: { opps: [] } as never }), 0, 'all')).toEqual([]);
    });
});

// ---- i 4 tipi (modello / anomalia / combinazione / tennis)
const ANOMALY = {
    kind: 'anomaly', market_type: 'OVER_UNDER_75', market_name: 'Over/Under 7.5', line: 7.5,
    market_id: '1.75', selection_id: 3, selection_name: 'Under 7.5', side: 'back',
    price: 1.1, size_available: 80, p_model: 0.99, p_implied: 0.909, edge: 0.08, ev: 0.09, confidence: 0.95,
    rationale: null, rule: 'ou_ladder', gap: 0.089,
    ref: { market_type: 'OVER_UNDER_65', selection_name: 'Under 6.5', price: 1.01 },
} as const;
const COMBO = {
    kind: 'combo', combo: 'under_stack', market_type: 'OVER_UNDER_25', market_name: 'Under stack', line: null,
    market_id: '1.25', selection_id: 10, selection_name: 'Under 2.5 + Under 3.5', side: 'back',
    price: 1.5, size_available: 40, p_model: 0.7, p_implied: 0.66, edge: 0.04, ev: 0.06, confidence: 0.9,
    rationale: null, total_stake: 10, locked_profit_per_eur: 0.03, best_case_per_eur: 0.25,
    legs: [
        { market_type: 'OVER_UNDER_25', market_id: '1.25', selection_id: 10, selection_name: 'Under 2.5', side: 'back', price: 1.9, size_available: 40, stake_ratio: 0.6, stake: 6 },
        { market_type: 'OVER_UNDER_35', market_id: '1.35', selection_id: 11, selection_name: 'Under 3.5', side: 'lay', price: 1.3, size_available: 25, stake_ratio: 0.4, stake: 4 },
    ],
} as const;
const TENNIS = {
    kind: 'tennis', market_type: 'MATCH_ODDS', market_name: 'Match Odds', line: null,
    market_id: '2.1', selection_id: 501, selection_name: 'Sinner', side: 'back',
    price: 1.4, size_available: 300, p_model: 0.8, p_implied: 0.71, edge: 0.09, ev: 0.12, confidence: 0.75,
    rationale: null,
    extra: { p_model_raw: 0.78, retire_risk: 0.12, best_of: 5, server: 'Sinner', momentum_against: true, sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 } },
} as const;
const MODEL_CAL = {
    market_type: 'MATCH_ODDS', market_name: 'Match Odds', line: null,
    market_id: '1.1', selection_id: 5, selection_name: 'Roma', side: 'back',
    price: 1.5, size_available: 100, p_model: 0.72, p_model_raw: 0.8, p_implied: 0.667, edge: 0.05, ev: 0.08, confidence: 0.7,
    rationale: 'λ casa alta', kind: 'model', calibration: { applied: true, family: 'MO', n: 420 },
} as const;

describe('OpportunityGroup — tipi di opportunita', () => {
    it('anomalia: badge tipo, regola e riferimento "sorella → anomala"', () => {
        renderGroup(row({ payload: { ...row().payload, opps: [ANOMALY as never] } }));
        expect(screen.getByTestId('opp-kind')).toHaveAttribute('data-kind', 'anomaly');
        expect(screen.getByTestId('opp-kind')).toHaveTextContent('ANOMALIA');
        expect(screen.getByTestId('anomaly-rule')).toHaveTextContent('scala Under/Over incoerente');
        expect(screen.getByTestId('anomaly-ref')).toHaveTextContent('Under 6.5 @1,01 → Under 7.5 @1,10');
        expect(screen.getByTestId('anomaly-rule')).toHaveTextContent('scarto +8,9 %');
    });

    it('combinazione: gambe con stake scalato allo stake totale e lock in € (peggiore/migliore)', async () => {
        const user = userEvent.setup();
        const { onPlace } = renderGroup(row({ payload: { ...row().payload, opps: [COMBO as never] } }), { stake: 10 });
        expect(screen.getByTestId('opp-kind')).toHaveAttribute('data-kind', 'combo');
        const legs = screen.getAllByTestId('combo-leg');
        expect(legs).toHaveLength(2);
        expect(legs[0]).toHaveTextContent('Under 2.5');
        expect(legs[0]).toHaveTextContent('6,00 €');
        expect(legs[1]).toHaveTextContent('LAY');
        expect(legs[1]).toHaveTextContent('4,00 €');
        const lock = screen.getByTestId('combo-lock');
        expect(lock).toHaveTextContent('+0,03 €');   // per €
        expect(lock).toHaveTextContent('+0,30 €');   // bloccato su €10
        expect(lock).toHaveTextContent('+2,50 €');   // migliore su €10
        // cambio stake totale → gambe e lock si riscalano
        const stake = screen.getByLabelText('Stake');
        await user.clear(stake);
        await user.type(stake, '20');
        expect(screen.getAllByTestId('combo-leg')[0]).toHaveTextContent('12,00 €');
        expect(screen.getByTestId('combo-lock')).toHaveTextContent('+0,60 €');
        // "Piazza" consegna lo stake TOTALE: e' la pagina a spezzarlo per gamba
        await user.click(screen.getByTestId('invest-place'));
        expect(onPlace).toHaveBeenCalledWith(expect.objectContaining({ kind: 'combo' }), 20);
    });

    it('modello calibrato: probabilita calibrata e grezza affiancate', () => {
        renderGroup(row({ payload: { ...row().payload, opps: [MODEL_CAL as never] } }));
        expect(screen.getByTestId('opp-kind')).toHaveAttribute('data-kind', 'model');
        expect(screen.getByText('Modello (calibrato)')).toBeInTheDocument();
        expect(screen.getByText('72,0 %')).toBeInTheDocument();
        expect(screen.getByTestId('model-raw')).toHaveTextContent('grezza 80,0 %');
    });

    it('modello senza calibrazione (payload vecchio): nessuna grezza, tipo MODELLO', () => {
        renderGroup(row());
        expect(screen.getAllByTestId('opp-kind')[0]).toHaveTextContent('MODELLO');
        expect(screen.queryByTestId('model-raw')).toBeNull();
    });

    it('tennis: set/game, rischio ritiro (rosso ≥10%) e avviso momentum', () => {
        renderGroup(row({
            sport: 'tennis', event_id: 't1',
            payload: { minute: null, score_home: null, score_away: null, event_name: 'Sinner v Alcaraz', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 }, opps: [TENNIS as never] },
        }));
        expect(screen.getByTestId('opp-kind')).toHaveAttribute('data-kind', 'tennis');
        expect(screen.getByTestId('tennis-extra')).toHaveTextContent('set 1-0 · game 3-2');
        expect(screen.getByTestId('tennis-extra')).toHaveTextContent('al meglio di 5');
        expect(screen.getByTestId('tennis-retire')).toHaveTextContent('ritiro 12 %');
        expect(screen.getByTestId('tennis-retire').className).toMatch(/red/);
        expect(screen.getByTestId('tennis-momentum')).toHaveTextContent('momentum contro');
    });

    it('anomalia "decided": nessuno "scarto" (gap non e uno scarto relativo, review L4)', () => {
        const decided = { ...(ANOMALY as Record<string, unknown>), rule: 'decided', gap: 0.5 };
        renderGroup(row({ payload: { ...row().payload, opps: [decided as never] } }));
        expect(screen.getByTestId('anomaly-rule')).not.toHaveTextContent('scarto');
    });

    it('tennis: chi serve mostrato col NOME del giocatore (review L5)', () => {
        renderGroup(row({
            sport: 'tennis', event_id: 't1',
            payload: { minute: null, score_home: null, score_away: null, event_name: 'Sinner v Alcaraz', sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 },
                       opps: [{ ...(TENNIS as Record<string, unknown>), extra: { ...((TENNIS as { extra: Record<string, unknown> }).extra), server: 'p2' } } as never] },
        }), { players: { p1: 'Sinner', p2: 'Alcaraz' } } as never);
        expect(screen.getByTestId('tennis-extra')).toHaveTextContent('serve: Alcaraz');
    });

    it('filtro per tipo: mostra solo il tipo scelto', () => {
        const r = row({ payload: { ...row().payload, opps: [ANOMALY as never, COMBO as never, ...row().payload.opps] } });
        expect(filterOpps(r, 0, 'all', 'anomaly').map((o) => o.kind)).toEqual(['anomaly']);
        expect(filterOpps(r, 0, 'all', 'model')).toHaveLength(2);
        renderGroup(r, { kindFilter: 'combo' });
        expect(screen.getAllByTestId('opp-row')).toHaveLength(1);
        expect(screen.getByTestId('opp-row')).toHaveAttribute('data-kind', 'combo');
    });
});

describe('OpportunityGroup — eta della riga (MEDIUM-3)', () => {
    it('riga fresca: mostra l eta e Investi e attivo', () => {
        renderGroup(row());
        expect(screen.getByTestId('opp-age')).toHaveTextContent('calcolo 5s fa');
        for (const b of screen.getAllByTestId('invest-place')) expect(b).toBeEnabled();
    });

    it('riga piu vecchia di 60 s: Investi spento con motivo', () => {
        renderGroup(row({ updated_at: new Date(NOW - OPP_ROW_STALE_MS - 15_000).toISOString() }));
        expect(screen.getByTestId('opp-age')).toHaveTextContent('calcolo 75s fa');
        for (const b of screen.getAllByTestId('invest-place')) expect(b).toBeDisabled();
        expect(screen.getAllByTestId('invest-disabled-reason')[0]).toHaveTextContent('modello non ricalcolato da 75s');
    });

    it('filtri che escludono tutto: il gruppo non rende nulla', () => {
        renderGroup(row(), { minConfidence: 0.9 });
        expect(screen.queryByTestId('opp-group')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// ANOMALIA: `p_model` NON e' il modello Poisson, e' 1/quota di RIFERIMENTO
// (anomaly.py `_rule_ou_ladder`). Chiamarlo "Modello" faceva leggere
// "Modello 90,1 %" su un Over 4.5 @16,50 solo perche' l'Over 7.5 era offerto a
// 1,11 (riferimento illiquido). La UI mostra il valore del payload SENZA
// ricalcolarlo e DICHIARA da quale quota viene.
// ---------------------------------------------------------------------------
describe('OpportunityGroup — anomalia: la probabilita dichiara la sua fonte', () => {
    const CASO_REALE = {
        kind: 'anomaly', market_type: 'OVER_UNDER', market_name: 'Over/Under 4.5', line: 4.5,
        market_id: '1.45', selection_id: 9, selection_name: 'Over 4.5', side: 'back',
        price: 16.5, size_available: 12, p_model: 0.901, p_implied: 0.0606,
        edge: 0.84, ev: 0.9, confidence: 0.9, rationale: null, rule: 'ou_ladder', gap: 13.8,
        ref: 'Over 7.5 back 1.11',
    } as const;

    it('etichetta "Limite dal riferimento", valore del payload, quota sorella dichiarata', () => {
        renderGroup(row({ payload: { ...row().payload, opps: [CASO_REALE as never] } }));
        expect(screen.queryByText('Modello')).toBeNull();
        expect(screen.getByText('Limite dal riferimento')).toBeInTheDocument();
        // il numero e' ESATTAMENTE quello del payload (nessun ricalcolo in UI)
        expect(screen.getByTestId('anomaly-ref-prob')).toHaveTextContent('90,1 %');
        const src = screen.getByTestId('anomaly-ref-source');
        expect(src).toHaveTextContent('Over 7.5 back 1,11');
        expect(screen.getByText('Limite dal riferimento').parentElement?.title)
            .toMatch(/quota SORELLA di riferimento/);
    });

    it('il riferimento e dichiarato anche quando arriva come oggetto', () => {
        const o = { ...(CASO_REALE as Record<string, unknown>), ref: { selection_name: 'Under 6.5', price: 1.01 } };
        renderGroup(row({ payload: { ...row().payload, opps: [o as never] } }));
        expect(screen.getByTestId('anomaly-ref-source')).toHaveTextContent('Under 6.5 1,01');
    });

    it('le opportunita di MODELLO restano etichettate "Modello"', () => {
        renderGroup(row());
        expect(screen.getAllByText('Modello').length).toBeGreaterThan(0);
        expect(screen.queryByTestId('anomaly-ref-prob')).toBeNull();
    });
});

// ===========================================================================
// CERTIFICAZIONE 12/09 — COMBINAZIONI: il minimo Betfair vale per OGNI GAMBA.
// Un dutching sbilanciato (9,66 € + 0,34 €) veniva accettato dalla UI: in live
// la gamba da 0,34 € e' rifiutata dall'exchange e resta una posizione NUDA,
// cioe' l'opposto del "rischio zero" promesso all'utente.
// ===========================================================================
describe('OpportunityGroup — combinazioni eseguibili per intero', () => {
    const comboRow = (over: Record<string, unknown> = {}) => row({
        payload: {
            minute: 60, score_home: 1, score_away: 0, event_name: 'Roma vs Lazio',
            opps: [{
                kind: 'combo', combo: 'dutch', side: 'back', price: 2.0,
                market_type: 'OVER_UNDER_55', market_name: 'Over/Under 5.5', line: 5.5,
                market_id: 'm1', selection_id: 1, selection_name: 'Dutching',
                p_model: 0.5, p_implied: 0.5, edge: 0.01, ev: 0.01, confidence: 0.85,
                size_available: 500, rationale: null, locked_profit_per_eur: 0.004,
                total_stake: 10, min_leg_stake: 2, min_total_stake: 58.8,
                executable_whole: true, book_supports_min: true,
                legs: [
                    { market_id: 'm1', selection_id: 1, side: 'back', price: 1.03, stake: 9.66,
                      stake_ratio: 0.966, size_available: 500, selection_name: 'Under 5.5 Goals',
                      market_type: 'OVER_UNDER_55' },
                    { market_id: 'm1', selection_id: 2, side: 'back', price: 29.0, stake: 0.34,
                      stake_ratio: 0.034, size_available: 500, selection_name: 'Over 5.5 Goals',
                      market_type: 'OVER_UNDER_55' },
                ],
                ...over,
            }],
        },
    } as Partial<SafeOpportunityRow>);

    it('lo stake minimo e quello che rende ESEGUIBILI tutte le gambe', () => {
        // stake totale 10 EUR: la gamba piccola varrebbe 0,35 EUR, sotto il
        // minimo Betfair -> la UI deve avvisare col minimo della COMBINAZIONE
        renderGroup(comboRow(), { stake: 10, minStake: 2 });
        const avviso = screen.getByTestId('invest-min-stake').textContent || '';
        expect(avviso).toMatch(/58,80|58\.80/);
    });

    it('combinazione non eseguibile per intero: piazzamento SPENTO con il motivo', () => {
        renderGroup(comboRow({ book_supports_min: false }), { stake: 10, minStake: 2 });
        expect((screen.getByTestId('invest-place') as HTMLButtonElement).disabled).toBe(true);
        expect(document.body.textContent || '').toMatch(/non regge tutte le gambe al minimo/i);
    });
});

// CERT. 12/09 — quando il BACKEND dichiara che la probabilita' dell'anomalia
// viene dalla stima del modello (piu' prudente del limite di mercato), la card
// deve dirlo: e' la differenza fra un numero affidabile e un numero di mercato.
describe('OpportunityGroup — anomalia: fonte dichiarata dal backend', () => {
    const anomRow = (over: Record<string, unknown> = {}) => row({
        payload: {
            minute: 48, score_home: 1, score_away: 0, event_name: 'Daegu Fc v Yongin FC',
            opps: [{
                kind: 'anomaly', rule: 'ou_ladder', side: 'back', price: 16.5,
                market_type: 'OVER_UNDER_45', market_name: 'Over/Under 4.5', line: 4.5,
                market_id: 'm45', selection_id: 9, selection_name: 'Over 4.5 Goals',
                p_model: 0.061, p_implied: 0.0606, edge: 0.0004, ev: 0.01,
                confidence: 0.75, size_available: 23.29, rationale: null,
                ref: 'Over 7.5 back 1.11', gap: 13.865, ...over,
            }],
        },
    } as Partial<SafeOpportunityRow>);

    it('p_source "modello": etichetta prudente, non "limite dal riferimento"', () => {
        renderGroup(anomRow({ p_source: 'modello' }));
        expect(document.body.textContent || '').toMatch(/Modello \(prudente\)/);
    });

    it('p_source "riferimento": resta dichiarata la quota sorella', () => {
        renderGroup(anomRow({ p_source: 'riferimento' }));
        expect(document.body.textContent || '').toMatch(/Limite dal riferimento/);
    });
});
