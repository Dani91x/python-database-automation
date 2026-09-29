// ============================================================================
// EsitoChiusuraMike.test.tsx - piano Mike 29/09, M7.2: l'esito della chiusura
// nella scheda di Mike. Le gambe finte hanno le chiavi VERE di `engine.Leg`
// (`dataclasses.asdict`, `service._row_from_ctx` -> `mike_events.positions`),
// il contesto quelle di `service._CTX_FIELDS` (`close_reason`, `attempts`,
// `flatten_pending`, `no_reentry`), `live` quelle di `ev["live"]` del servizio.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MikeEvent, MikeLeg } from '@/lib/mike';
import { esitoChiusuraMike, esposizioniAperte } from '@/lib/mikeEsitoChiusura';
import { EsitoChiusuraMike } from './EsitoChiusuraMike';
import { SchedaMike } from './SchedaMike';

const ORA_MS = Date.now();
const ORA_S = ORA_MS / 1000;

function gamba(over: Partial<MikeLeg>): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back',
        price: 1.5, size: 10, matched: 10, avg_price: 1.5, ref: `r-${Math.random()}`,
        status: 'open', placed_at: ORA_S - 600, persistence: 'LAPSE', cycle_no: 0,
        final: false, archived: false, closes_ref: null, ...over,
    };
}

function ev(state: string, legs: MikeLeg[], ctx: Record<string, unknown>, live: Record<string, unknown> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date(ORA_MS - 3600_000).toISOString(), mode: 'paper', markets: {}, state: state as MikeEvent['state'],
        cycle_no: 0, entry_price_initial: 1.5, dossier: null,
        live: { goals: 0, published_ts: ORA_S - 1, feed_age_s: 1, ...live } as MikeEvent['live'],
        positions: legs, ctx, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    };
}

const INGRESSO = gamba({ ref: 'ing' });
// green-up a 1,48 per l'importo che spalma: +0,13 / +0,14
const BANCA_PIENA = gamba({ ref: 'chi', role: 'under_close', side: 'lay', price: 1.48, size: 10.14, matched: 10.14, avg_price: 1.48, placed_at: ORA_S - 60 });

const opt = { nowMs: ORA_MS, tentativiMax: 20 };

describe('M7.2 - quando non c’e’ niente da raccontare', () => {
    it('partita che lavora normalmente: nessun esito', () => {
        expect(esitoChiusuraMike(ev('LIVE_COVERED', [INGRESSO], { close_reason: null, attempts: 0 }), opt)).toBeNull();
        const { container } = render(<EsitoChiusuraMike ev={ev('LIVE_UNCOVERED', [INGRESSO], {})} />);
        expect(container.textContent).toBe('');
    });

    it('re-ingresso dopo una chiusura in profitto: lo stato non e’ piu’ chiuso, nessun esito vecchio', () => {
        expect(esitoChiusuraMike(ev('REENTRY_OPEN', [INGRESSO], { close_reason: 'profit' }), opt)).toBeNull();
    });
});

describe('M7.2 - chiusura in corso', () => {
    it('mostra gli ordini con chiesto e abbinato e il tentativo', () => {
        const parziale = gamba({ ref: 'c1', role: 'under_close', side: 'lay', price: 1.48, size: 10.14, matched: 4, avg_price: 1.48, status: 'pending', placed_at: ORA_S - 5 });
        render(<EsitoChiusuraMike ev={ev('LIVE_CLOSING', [INGRESSO, parziale], { close_reason: 'profit', attempts: 2 })} tentativiMax={20} />);
        expect(screen.getByTestId('cr-mike-esito-chiusura').getAttribute('data-tipo')).toBe('in_corso');
        expect(screen.getByTestId('cr-mike-esito-chiusura-titolo').textContent).toBe('Chiusura in corso - tentativo 3 di 20');
        expect(screen.getByTestId('cr-mike-esito-chiusura-motivo').textContent).toBe('chiusa da Mike in profitto (parte da sola)');
        expect(screen.getByTestId('cr-mike-esito-chiusura-ordine').textContent).toBe(
            'Chiusura Under 3.5 · banca · chiesti 10,14 € · abbinati 4,00 € @ 1,48 · abbinato in parte, resto sul book');
    });

    it('massimo dei tentativi non noto (card della Control Room): «tentativo n» senza «di M»', () => {
        const parziale = gamba({ ref: 'c1', role: 'under_close', side: 'lay', price: 1.48, size: 10.14, matched: 0, avg_price: null, status: 'pending' });
        render(<EsitoChiusuraMike ev={ev('LIVE_CLOSING', [INGRESSO, parziale], { close_reason: 'manual', attempts: 4 })} />);
        expect(screen.getByTestId('cr-mike-esito-chiusura-titolo').textContent).toBe('Chiusura in corso - tentativo 5');
        // i tentativi esauriti si riconoscono comunque (valore di serie del bot)
        const e = esitoChiusuraMike(ev('LIVE_CLOSING', [INGRESSO, parziale], { close_reason: 'manual', attempts: 20 }),
            { nowMs: ORA_MS, tentativiMax: null })!;
        expect(e.titolo).toBe('NON COMPLETA - resta esposizione di 10,00 € su Under 3.5 - tentativo 20');
    });

    it('comando dell’utente in pre-partita (flatten in corso): chiusura in corso', () => {
        const e = esitoChiusuraMike(ev('PRE_GREEN_PENDING', [INGRESSO], { flatten_pending: true, attempts: 0 }), opt);
        expect(e?.tipo).toBe('in_corso');
        expect(e?.motivo).toBe('chiusa col tuo comando (Chiudi / Cash out)');
    });

    it('tentativi esauriti con esposizione: NON COMPLETA, tentativo 20 di 20', () => {
        const poco = gamba({ ref: 'c1', role: 'under_close', side: 'lay', price: 1.48, size: 10.14, matched: 5, avg_price: 1.48, status: 'pending' });
        const e = esitoChiusuraMike(ev('LIVE_CLOSING', [INGRESSO, poco], { close_reason: 'loss_2t', attempts: 20 }), opt)!;
        expect(e.tipo).toBe('non_completa');
        expect(e.titolo).toBe('NON COMPLETA - resta esposizione di 5,00 € su Under 3.5 - tentativo 20 di 20');
        expect(e.motivo).toBe('uscita in perdita nel secondo tempo, firmata da te');
    });
});

describe('M7.2 - chiusura finita: la prova sui conti degli ordini abbinati', () => {
    it('tutto pari, nessun ordine vivo, risultato pubblicato: CHIUSA senza esposizione', () => {
        render(<EsitoChiusuraMike ev={ev('FLAT', [INGRESSO, BANCA_PIENA], { close_reason: 'profit', attempts: 0 }, { locked: 0.13 })} />);
        expect(screen.getByTestId('cr-mike-esito-chiusura').getAttribute('data-tipo')).toBe('chiusa');
        expect(screen.getByTestId('cr-mike-esito-chiusura-titolo').textContent).toBe(
            'CHIUSA - risultato bloccato +0,13 € - nessuna esposizione residua su questa partita');
    });

    it('il bot dice FLAT ma la banca e’ abbinata solo in parte: NON COMPLETA (i conti vincono sullo stato)', () => {
        const meta = gamba({ ref: 'chi', role: 'under_close', side: 'lay', price: 1.48, size: 10.14, matched: 5, avg_price: 1.48 });
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, meta], { close_reason: 'manual' }, { locked: 0.13 }), opt)!;
        expect(e.tipo).toBe('non_completa');
        expect(e.titolo).toBe('NON COMPLETA - resta esposizione di 5,00 € su Under 3.5');
        expect(e.dettagli[0]).toBe('linea 3.5: se vince l’Under +2,60 € / se vince l’Over −5,00 €');
    });

    it('un ordine a esito ignoto: DA VERIFICARE col motivo, mai «nessuna esposizione»', () => {
        const ignoto = gamba({ ref: 'x', role: 'over_close', market: 'OU45', selection: 'OVER', side: 'lay', price: 12, size: 2, matched: 0, avg_price: null, status: 'pending_reconcile' });
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, BANCA_PIENA, ignoto], { close_reason: 'profit' }, { locked: 0.13 }), opt)!;
        expect(e.tipo).toBe('da_verificare');
        expect(e.titolo).not.toContain('nessuna esposizione residua');
        expect(e.dettagli.join(' | ')).toContain('esito ignoto su Betfair (Chiusura Over 4.5)');
    });

    it('un ordine ancora sul book: DA VERIFICARE', () => {
        const vivo = gamba({ ref: 'v', role: 'reentry', market: 'OU45', selection: 'UNDER', matched: 0, avg_price: null, status: 'pending', price: 1.6, size: 10 });
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, BANCA_PIENA, vivo], { close_reason: 'profit' }, { locked: 0.13 }), opt)!;
        expect(e.tipo).toBe('da_verificare');
        expect(e.dettagli[0]).toContain('ancora sul book');
    });

    it('risultato bloccato non pubblicato: DA VERIFICARE', () => {
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, BANCA_PIENA], { close_reason: 'profit' }, { locked: null }), opt)!;
        expect(e.tipo).toBe('da_verificare');
        expect(e.dettagli).toContain('il bot non ha ancora pubblicato il risultato bloccato');
    });

    it('dati della partita vecchi: DA VERIFICARE (col servizio fermo non si firma niente)', () => {
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, BANCA_PIENA], { close_reason: 'profit' }, { locked: 0.13, published_ts: ORA_S - 200 }), opt)!;
        expect(e.tipo).toBe('da_verificare');
        expect(e.dettagli).toContain('i dati della partita sono vecchi di 200 s');
    });

    it('linea gia’ decisa dai gol: esito certo, non e’ esposizione; risultato dalla tabella per gol', () => {
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO], { close_reason: 'manual' }, {
            goals: 4, locked: null,
            pnl_totale_by_total: { 0: 4.75, 1: 4.75, 2: 4.75, 3: 4.75, 4: -10, 5: -10, 6: -10, 7: -10, 8: -10 },
        }), opt)!;
        expect(e.tipo).toBe('chiusa');
        expect(e.titolo).toBe('CHIUSA - risultato bloccato −10,00 € - nessuna esposizione residua su questa partita');
    });

    it('copertura sull’Under 4,5 chiusa bancando l’Over 4,5 (P5): pari PER MERCATO, non per selezione', () => {
        const cop = gamba({ ref: 'cov', role: 'over_cover', market: 'OU45', selection: 'UNDER', side: 'lay', price: 1.18, size: 12.63, matched: 12.63, avg_price: 1.18 });
        const chi = gamba({ ref: 'oc', role: 'over_close', market: 'OU45', selection: 'OVER', side: 'lay', price: 21, size: 0.71, matched: 0.71, avg_price: 21 });
        expect(esposizioniAperte([cop, chi], 0)).toEqual([]);
        // senza la chiusura la linea 4.5 e' esposta
        expect(esposizioniAperte([cop], 0)[0].selezione).toBe('Over 4.5');
        const e = esitoChiusuraMike(ev('FLAT', [INGRESSO, BANCA_PIENA, cop, chi], { close_reason: 'profit' }, { locked: -1.44 }), opt)!;
        expect(e.tipo).toBe('chiusa');
    });

    it('chiusura manuale in pre-partita (WATCH, niente rientro): CHIUSA', () => {
        const a = { ...INGRESSO, archived: true };
        const b = { ...BANCA_PIENA, archived: true, role: 'manual_close' };
        const e = esitoChiusuraMike(ev('WATCH', [a, b], { close_reason: 'manual', no_reentry: true }, { locked: 0.13 }), opt)!;
        expect(e.tipo).toBe('chiusa');
        // WATCH senza il comando dell'utente: nessun esito
        expect(esitoChiusuraMike(ev('WATCH', [a, b], { close_reason: null, no_reentry: false }), opt)).toBeNull();
    });
});

describe('M7.2 - stesso componente nella Control Room', () => {
    it('SchedaMike mostra l’esito della chiusura', () => {
        render(<SchedaMike ev={ev('FLAT', [INGRESSO, BANCA_PIENA], { close_reason: 'profit' }, { locked: 0.13 })} />);
        expect(screen.getByTestId('cr-mike-esito-chiusura-titolo').textContent).toMatch(/^CHIUSA - risultato bloccato \+0,13 €/);
    });
});
