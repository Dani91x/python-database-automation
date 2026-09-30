// ============================================================================
// MikeP6Blocco6Copertura.test.tsx - piano Mike 29/09, P6 blocco 6 (da integrare
// INSIEME al pacchetto P5 della copertura): le etichette della copertura in
// tutte e due le forme. Il ruolo resta `over_cover`: la forma si legge da LATO
// e SELEZIONE della gamba. Gambe con le chiavi di `engine.Leg`, righe
// `mike_trades` con quelle di MikeEventPnlTable.test.tsx.
// Numeri del piano (MIKE_P5_PROGETTO.md par. 2): punta Under 3,5 10,00 a 1,50;
// vecchia: punta Over 4,5 2,26 a 6,60; nuova: banca Under 4,5 12,63 a 1,18
// (rischio 2,27); chiusura della copertura: banca Over 4,5 0,71 a 21.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MikeEventPnlTable } from './MikeEventPnlTable';
import {
    groupMikeTrades, investedOf, mikeActivityLine, positionRows, roleLabelGamba,
    MIKE_PARAM_DEFAULTS, MIKE_PARAM_FIELDS, MIKE_PHASE_META,
    type MikeEvent, type MikeLeg, type MikeTrade,
} from '@/lib/mike';
import { esitoChiusuraMike } from '@/lib/mikeEsitoChiusura';

function gamba(over: Partial<MikeLeg>): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10,
        matched: 10, avg_price: 1.5, ref: `r${Math.random()}`, status: 'open', placed_at: 1, persistence: 'LAPSE',
        cycle_no: 0, final: false, archived: false, closes_ref: null, ...over,
    };
}
const INGRESSO = gamba({});
const VECCHIA = gamba({ role: 'over_cover', market: 'OU45', selection: 'OVER', side: 'back', price: 6.6, size: 2.26, matched: 2.26, avg_price: 6.6 });
const NUOVA = gamba({ role: 'over_cover', market: 'OU45', selection: 'UNDER', side: 'lay', price: 1.18, size: 12.63, matched: 12.63, avg_price: 1.18 });
const CHIUSURA = gamba({ role: 'over_close', market: 'OU45', selection: 'OVER', side: 'lay', price: 21, size: 0.71, matched: 0.71, avg_price: 21 });

function ev(legs: MikeLeg[], over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: null, league_id: null,
        ko_at: null, mode: 'paper', markets: {}, state: 'LIVE_COVERED', cycle_no: 0, entry_price_initial: 1.5,
        dossier: null, live: { goals: 0, published_ts: Date.now() / 1000 } as MikeEvent['live'],
        positions: legs, ctx: {}, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(), ...over,
    };
}

describe('P6 blocco 6 - il nome della copertura guarda lato e selezione', () => {
    it('forma nuova e forma vecchia, stessa chiave di ruolo', () => {
        expect(roleLabelGamba(NUOVA)).toBe('Copertura: banca Under 4.5');
        expect(roleLabelGamba(VECCHIA)).toBe('Copertura: punta Over 4.5');
        // la chiusura della copertura e' una banca Over in tutte e due le forme
        expect(roleLabelGamba(CHIUSURA)).toBe('Chiusura Over 4.5');
        // ripiego sotto 0,50 EUR (M3.3): punta Under 4,5
        expect(roleLabelGamba({ role: 'over_close', side: 'back', selection: 'UNDER' })).toBe('Chiusura copertura: punta Under 4.5');
        // nomi Betfair delle righe (`selection_name`)
        expect(roleLabelGamba({ role: 'over_cover', side: 'lay', selection: 'Under 4.5 Goals' })).toBe('Copertura: banca Under 4.5');
        // lato o selezione ignoti: il nome del ruolo, mai una forma indovinata
        expect(roleLabelGamba({ role: 'over_cover', side: null, selection: null })).toBe('Copertura linea 4.5');
        expect(roleLabelGamba({ role: 'under_entry', side: 'back', selection: 'UNDER' })).toBe('Ingresso Under 3.5');
    });

    it('capitale impegnato: la banca conta il RISCHIO (12,63 x 0,18 = 2,27), la punta l’importo', () => {
        expect(investedOf(ev([INGRESSO, VECCHIA]))).toBeCloseTo(12.26, 2);
        expect(investedOf(ev([INGRESSO, NUOVA]))).toBeCloseTo(12.27, 2);
    });

    it('posizioni: copertura banca Under + chiusura banca Over pari PER MERCATO = nessuna riga 4.5', () => {
        const righe = positionRows(ev([INGRESSO, NUOVA, CHIUSURA]));
        expect(righe.map((r) => r.key)).toEqual(['OU35|UNDER']);
        // senza chiusura: UNA riga sulla linea 4.5, banca Under
        const aperte = positionRows(ev([INGRESSO, NUOVA]));
        const r45 = aperte.find((r) => r.market === 'OU45')!;
        expect(r45.label).toBe('Under 4.5');
        expect(r45.netSide).toBe('LAY');
        expect(r45.entryPrice).toBe(1.18);
        // forma vecchia: invariata (una selezione sola)
        const v = positionRows(ev([INGRESSO, VECCHIA])).find((r) => r.market === 'OU45')!;
        expect([v.label, v.netSide, v.matched]).toEqual(['Over 4.5', 'BACK', 2.26]);
    });

    it('esito della chiusura: la copertura nuova chiusa e’ CHIUSA, con i nomi giusti degli ordini', () => {
        const e = esitoChiusuraMike(ev([INGRESSO, NUOVA, CHIUSURA,
            gamba({ role: 'under_close', side: 'lay', price: 1.2, size: 12.5, matched: 12.5, avg_price: 1.2 })],
        { state: 'FLAT', ctx: { close_reason: 'profit' }, live: { goals: 0, locked: 0.81, published_ts: Date.now() / 1000 } as MikeEvent['live'] }),
        { nowMs: Date.now(), tentativiMax: 20 })!;
        expect(e.ordini.map((o) => o.ruolo)).toEqual(['Chiusura Over 4.5', 'Chiusura Under 3.5']);
    });

    it('tabella delle operazioni: la riga della copertura dice la forma', () => {
        const apre: MikeTrade = {
            id: 7001, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'over_cover', role: 'over_cover',
            cycle_no: 0, market_type: 'OVER_UNDER_45', market_id: '1.45', selection_id: 1222346,
            selection_name: 'Under 4.5 Goals', side: 'lay', mode: 'paper', price: 1.18, size: 12.63, liability: 2.27,
            status: 'open', pnl: null, placed_at: '2026-09-29T19:00:00Z', settled_at: null, signal_key: 'k7001',
            meta: {}, closes_trade_id: null, day_placed_at: '2026-09-29T19:00:00Z', origin: 'auto',
        };
        render(<MikeEventPnlTable gruppi={groupMikeTrades([apre])} titolo="Operazioni" vuoto="-" />);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId('gamba-7001')).toHaveTextContent('Copertura: banca Under 4.5');
    });

    it('attivita’ «cover»: forma dal payload (lato/selezione, poi cover_form)', () => {
        expect(mikeActivityLine('cover', { side: 'lay', selection: 'UNDER', size: 12.63, price: 1.18, x: 1.2, minute: 12 }))
            .toMatch(/^copertura: banca under 4\.5 12,63 € @ 1,18/);
        expect(mikeActivityLine('cover', { cover_form: 'lay_under45', size: 12.63, price: 1.18, x: 1.2, minute: 12 }))
            .toMatch(/^copertura: banca under 4\.5 /);
        expect(mikeActivityLine('cover', { size: 2.26, price: 6.6, x: 1.2, minute: 12 })).toMatch(/^copertura linea 4\.5 2,26 €/);
    });

    it('parametro cover_form: due forme, di serie la banca Under 4,5', () => {
        const f = MIKE_PARAM_FIELDS.find((x) => x.key === 'cover_form')!;
        expect(f.kind === 'choice' ? f.choices : null).toEqual(['lay_under45', 'back_over45']);
        expect(f.group).toBe('cover');
        expect(MIKE_PARAM_DEFAULTS.cover_form).toBe('lay_under45');
    });

    it('le fasi non dicono piu’ «comprare l’Over 4.5»', () => {
        for (const s of ['LIVE_UNCOVERED', 'LIVE_COVER_PENDING', 'LIVE_COVERED'] as const) {
            expect(MIKE_PHASE_META[s].what).not.toContain('Over 4.5');
            expect(MIKE_PHASE_META[s].what).toContain('linea 4.5');
        }
    });
});
