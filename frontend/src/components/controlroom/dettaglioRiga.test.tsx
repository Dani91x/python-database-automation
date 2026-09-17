// ============================================================================
// dettaglioRiga.test.tsx — IL DETTAGLIO DELLA RIGA nella Control Room.
//
// I finti hanno le CHIAVI IDENTICHE alle righe vere che le RPC restituiscono
// (`get_omega_trades`, `get_safe_trades`, `get_mike_state`): snake_case,
// `meta.model`, `meta.greenup`, `size_matched`, `minute_at_entry`. Un finto
// scritto in camelCase certificherebbe un bug invece di un comportamento (il
// 15/09 è successo davvero, e sono usciti 32 ordini reali in loop).
//
// Ogni prova ha la sua FALSIFICAZIONE: tolto il campo dal finto, il test deve
// diventare rosso. Le falsificazioni sono scritte come prove a sé (`senza X →
// si dichiara assente`), così restano nella suite invece di vivere una volta
// sola nella sessione di chi ha scritto il codice.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { dettaglioDi, eGambaDiChiusura, quotaViva } from '@/components/controlroom/dettaglioRiga';
import {
    BadgeStato, Ingresso, QuotaOra, PnlVivo, Copertura, Greenup, ModelloP, Uscita,
} from '@/components/controlroom/DettaglioRigaView';
import { SchedaMike } from '@/components/controlroom/SchedaMike';
import { liabilityTennis } from '@/components/controlroom/useControlRoom';
import type { MikeEvent } from '@/lib/mike';

/** UNA RIGA di `omega_trades` come la RPC la restituisce davvero. */
function rigaOmega(over: Record<string, unknown> = {}) {
    return {
        id: 101,
        event_id: 'E1',
        event_name: 'Roma vs Lazio',
        market_id: '1.24',
        selection_id: 47972,
        runner_name: '2 - 1',
        side: 'lay',
        mode: 'live',
        phase: 'ft_cs',
        price: 26,
        size: 2,
        liability: 50,
        target: null,
        minute_at_entry: 63,
        score_at_entry: '1-0',
        kickoff: '2026-09-17T18:00:00Z',
        status: 'open',
        pnl: 0,
        bet_id: '3.1',
        placed_at: '2026-09-17T19:03:00Z',
        settled_at: null,
        closes_trade_id: null,
        meta: {
            model: { p_model_raw: 0.05, p_model: 0.04, calibrated: true },
            greenup: { state: 'hold', reason: 'ev_hold', attempts: 2, p_lose: 0.04, ev: 1.2 },
            exit_kind: 'greenup',
            hedge: { fraction: 0.4, remaining_liability: 50, hedged_size: 0.8, size: 2, complete: false },
        },
        ...over,
    };
}

describe('dettaglioDi — il dettaglio esce dalle stesse funzioni delle pagine dei bot', () => {
    it('minuto e punteggio ALL INGRESSO arrivano dalle colonne della riga', () => {
        const d = dettaglioDi(rigaOmega());
        expect(d.ingresso).toEqual({ minuto: 63, punteggio: '1-0' });
    });

    // FALSIFICAZIONE
    it('senza minute_at_entry/score_at_entry l ingresso e IGNOTO, non zero', () => {
        const d = dettaglioDi(rigaOmega({ minute_at_entry: null, score_at_entry: null }));
        expect(d.ingresso).toEqual({ minuto: null, punteggio: null });
    });

    it('lo stato e il badge RICCO di Omega/Safe, non lo stato grezzo del database', () => {
        const d = dettaglioDi(rigaOmega());
        expect(d.stato.label).toBe('APERTO');
        // una riga con un ordine ancora da riconciliare NON e' «a posto»
        const rec = dettaglioDi(rigaOmega({
            status: 'pending', meta: { ...rigaOmega().meta, reconcile_pending: true },
        }));
        expect(rec.stato.label).not.toBe('APERTO');
    });

    it('P del MODELLO contro quella del MERCATO, col margine', () => {
        // quota lay viva 20 -> P implicita 5%
        const d = dettaglioDi(rigaOmega(), [], { pMercato: 1 / 20 });
        expect(d.modello?.pModello).toBe(0.04);       // calibrata: `calibrated: true`
        expect(d.modello?.pMercato).toBeCloseTo(0.05, 6);
        expect(d.modello?.margine).toBeCloseTo(0.01, 6);
    });

    // FALSIFICAZIONE
    it('senza meta.model e senza quota viva NON si inventa nessuna probabilita', () => {
        const meta = { ...rigaOmega().meta };
        delete (meta as Record<string, unknown>).model;
        expect(dettaglioDi(rigaOmega({ meta })).modello).toBeNull();
    });

    it('P&L VIVO: una gamba coperta e BLOCCATA, non «aperta»', () => {
        const apertura = rigaOmega({
            status: 'hedged',
            meta: { ...rigaOmega().meta, locked_pnl_net: 3.21, residual_size: 0 },
        });
        const chiusura = rigaOmega({ id: 102, closes_trade_id: 101, status: 'open', side: 'back' });
        const d = dettaglioDi(apertura, [chiusura]);
        expect(d.pnlVivo).toEqual({ stato: 'locked', valore: 3.21 });
    });

    // FALSIFICAZIONE
    it('senza locked_pnl_net e senza chiusure la gamba resta APERTA e il P&L IGNOTO', () => {
        const d = dettaglioDi(rigaOmega());
        expect(d.pnlVivo).toEqual({ stato: 'open', valore: null });
    });

    it('la COPERTURA parziale dice la frazione e la responsabilita ancora a rischio', () => {
        const d = dettaglioDi(rigaOmega());
        expect(d.copertura).toEqual({ frazione: 0.4, residua: 50, completa: false });
    });

    // FALSIFICAZIONE
    it('senza meta.hedge la copertura e ASSENTE, non «0%»', () => {
        const meta = { ...rigaOmega().meta };
        delete (meta as Record<string, unknown>).hedge;
        expect(dettaglioDi(rigaOmega({ meta })).copertura).toBeNull();
    });

    it('il badge GREEN-UP arriva da meta.greenup del servizio', () => {
        expect(dettaglioDi(rigaOmega()).greenup?.state).toBe('hold');
    });

    // FALSIFICAZIONE
    it('senza meta.greenup nessun badge inventato', () => {
        const meta = { ...rigaOmega().meta };
        delete (meta as Record<string, unknown>).greenup;
        expect(dettaglioDi(rigaOmega({ meta })).greenup).toBeNull();
    });

    it('l uscita e la gamba sono quelle dichiarate dalla riga', () => {
        const d = dettaglioDi(rigaOmega());
        expect(d.uscita).toBe('greenup');
        expect(d.gamba).toBe('ft_cs');
        // Safe non ha `phase`: la gamba e' la strategia, passata da chi legge
        expect(dettaglioDi(rigaOmega({ phase: null }), [], { gamba: 'base' }).gamba).toBe('base');
    });
});

describe('quotaViva — quota d ingresso contro quota di ADESSO', () => {
    it('back e lay di adesso e i tick di movimento sul lato d ingresso', () => {
        const v = quotaViva(26, 'lay', { back: 24, lay: 22 });
        expect(v?.back).toBe(24);
        expect(v?.lay).toBe(22);
        expect(v?.ora).toBe(22);
        // su un LAY entrato a 26 la quota che SCENDE e' a nostro favore: tick > 0
        expect(v?.tick).toBeGreaterThan(0);
    });

    it('su un BACK il segno e rovesciato: la quota che scende ci danneggia', () => {
        expect(quotaViva(3, 'back', { back: 2.5, lay: 2.52 })?.tick).toBeLessThan(0);
    });

    // FALSIFICAZIONE
    it('senza nessun prezzo nel feed la quota viva NON esiste (mai un ripiego)', () => {
        expect(quotaViva(26, 'lay', { back: null, lay: null })).toBeNull();
        expect(quotaViva(null, 'lay', { back: 24, lay: 22 })?.tick).toBeNull();
    });
});

describe('come si MOSTRA il dettaglio', () => {
    const d = dettaglioDi(rigaOmega(), [], { pMercato: 1 / 20 });

    it('ogni pezzo scrive il suo numero sotto il suo testid', () => {
        render(<>
            <BadgeStato d={d} />
            <Ingresso d={d} />
            <QuotaOra v={quotaViva(26, 'lay', { back: 24, lay: 22 })!} />
            <PnlVivo d={d} />
            <Copertura d={d} />
            <Greenup d={d} />
            <ModelloP d={d} />
            <Uscita d={d} />
        </>);
        expect(screen.getByTestId('cr-stato-riga')).toHaveTextContent('APERTO');
        expect(screen.getByTestId('cr-ingresso')).toHaveTextContent('63′ 1-0');
        expect(screen.getByTestId('cr-quota-viva')).toHaveTextContent('B 24,00');
        expect(screen.getByTestId('cr-quota-viva')).toHaveTextContent('L 22,00');
        expect(screen.getByTestId('cr-quota-viva-tick')).toHaveTextContent('tick');
        expect(screen.getByTestId('cr-copertura-riga')).toHaveTextContent('40 %');
        expect(screen.getByTestId('cr-greenup')).toHaveTextContent('TENGO');
        expect(screen.getByTestId('cr-modello-p')).toHaveTextContent('4,0 %');
        expect(screen.getByTestId('cr-uscita')).toHaveTextContent('green-up');
    });

    it('un P&L che non esiste ancora si scrive «—», mai «0,00 €»', () => {
        render(<PnlVivo d={d} />);
        const el = screen.getByTestId('cr-pnl-vivo');
        expect(el).toHaveAttribute('data-stato', 'open');
        expect(el.textContent).not.toMatch(/0,00/);
    });
});

// --------------------------------------------------------------------- MIKE

/** UN EVENTO di `get_mike_state().events` con le chiavi vere del servizio. */
function eventoMike(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E9', fixture_id: 77, event_name: 'Milan vs Inter',
        competition: 'Serie A', league_id: 135, ko_at: '2026-09-17T18:45:00Z',
        mode: 'paper', markets: {}, state: 'in_play', cycle_no: 2,
        entry_price_initial: 1.42,
        dossier: { lambda_home: 1.35, lambda_away: 1.1, p4_pre: 0.18, source: 'fixture' },
        live: {
            minute: 58, goals: 2, inplay: true, ht: false, hazard: null,
            p4_market: 0.21, p4_model: 0.16,
            lambda_source: 'fixture',
            ko_price_under: 1.38, ko_drift_ticks: -4,
            total_matched: 128000, liability: 12.4, locked: 1.55, cicli_chiusi: 1,
            cashout: { net: 2.1, gross: 2.21, base: 10, complete: true, pct: 21, target_pct: 30 },
            pnl_by_total: { '2': 3.4, '3': 3.4, '4': -6.2 },
            pnl_totale_by_total: { '2': 4.95, '3': 4.95, '4': -4.65 },
            books: {
                'OU35|UNDER': { best_back: 1.36, back_size: 200, best_lay: 1.37, lay_size: 180, status: 'OPEN', inplay: true, bet_delay: 5 },
                'OU45|OVER': { best_back: 7.2, back_size: 40, best_lay: 7.6, lay_size: 33, status: 'OPEN', inplay: true, bet_delay: 5 },
            },
            feed_fresh: true,
        },
        positions: [], ctx: null, skipped: false, settled_pnl: null,
        updated_at: '2026-09-17T19:40:00Z',
        ...over,
    } as MikeEvent;
}

describe('SchedaMike — i dati di MODELLO di Mike, dalla lettura gia fatta', () => {
    it('P(4 gol) mercato e modello, gol attesi, le due linee, ingresso e fischio', () => {
        render(<SchedaMike ev={eventoMike()} />);
        expect(screen.getByTestId('cr-mike-p4-mercato')).toHaveTextContent('21,0 %');
        expect(screen.getByTestId('cr-mike-p4-modello')).toHaveTextContent('16,0 %');
        expect(screen.getByTestId('cr-mike-lambda')).toHaveTextContent('1,35');
        expect(screen.getByTestId('cr-mike-lambda')).toHaveTextContent('1,10');
        expect(screen.getByTestId('cr-mike-u35')).toHaveTextContent('1,36');
        expect(screen.getByTestId('cr-mike-o45')).toHaveTextContent('7,20');
        expect(screen.getByTestId('cr-mike-entry')).toHaveTextContent('1,42');
        expect(screen.getByTestId('cr-mike-ko')).toHaveTextContent('1,38');
        expect(screen.getByTestId('cr-mike-ko-drift')).toHaveTextContent('4 tick');
        expect(screen.getByTestId('cr-mike-cicli')).toHaveTextContent('2');
        expect(screen.getByTestId('cr-mike-cashout')).toHaveTextContent('soglia');
        // il segno «meno» del design system e' il MENO tipografico (U+2212)
        expect(screen.getByTestId('cr-mike-gol-4')).toHaveTextContent('4,65 €');
    });

    it('la fonte dei gol attesi si DICHIARA: «nessuna» vuol dire bot cieco', () => {
        render(<SchedaMike ev={eventoMike({
            live: { ...eventoMike().live, lambda_source: 'none' },
        })} />);
        expect(screen.getByTestId('cr-mike-lambda-fonte')).toHaveTextContent('cieco');
    });

    // FALSIFICAZIONE
    it('senza `live` la scheda non inventa numeri: tutto «—»', () => {
        render(<SchedaMike ev={eventoMike({ live: null, dossier: null })} />);
        expect(screen.getByTestId('cr-mike-p4-mercato')).toHaveTextContent('—');
        expect(screen.getByTestId('cr-mike-lambda')).toHaveTextContent('—');
        expect(screen.queryByTestId('cr-mike-cashout')).toBeNull();
        expect(screen.queryByTestId('cr-mike-per-gol')).toBeNull();
    });
});

// ------------------------------------------------------------------- TENNIS

describe('liabilityTennis — la responsabilita di un ordine tennis, dalla riga', () => {
    it('su un LAY e (quota − 1) × importo; su un BACK e l importo', () => {
        expect(liabilityTennis({ side: 'LAY', price: 2.5, size: 4 })).toBe(6);
        expect(liabilityTennis({ side: 'BACK', price: 2.5, size: 4 })).toBe(4);
    });

    // FALSIFICAZIONE
    it('senza importo o senza prezzo su un lay resta IGNOTA, mai zero', () => {
        expect(liabilityTennis({ side: 'LAY', price: 2.5, size: null })).toBeNull();
        expect(liabilityTennis({ side: 'LAY', price: null, size: 4 })).toBeNull();
        expect(liabilityTennis({ side: null, price: 2.5, size: 4 })).toBeNull();
    });
});

// ------------------------------------------------ GAMBE DI CHIUSURA (17/09 sera)

describe('eGambaDiChiusura — il back che chiude un lay non e una posizione aperta', () => {
    // il caso vero: Safe «esatto», Union Brescia-Treviso, lay 2 @70 (id 321) chiuso
    // in perdita da tre back con `closes_trade_id: 321`, tutti ancora `open`
    it('una riga con closes_trade_id e una chiusura, anche se lo stato e open', () => {
        expect(eGambaDiChiusura({ closes_trade_id: 321 })).toBe(true);
    });

    // FALSIFICAZIONE: l apertura, che NON chiude nessuno, resta una posizione
    it('l apertura (closes_trade_id nullo o assente) resta una posizione', () => {
        expect(eGambaDiChiusura({ closes_trade_id: null })).toBe(false);
        expect(eGambaDiChiusura({})).toBe(false);
    });
});
