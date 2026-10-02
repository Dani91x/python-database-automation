// ============================================================================
// ResiduoScopertoMike.test.tsx - 01/10 (FC Ashdod v Maccabi Herzliya, live):
// la chiusura NON completata di Mike. Le chiavi dei finti sono quelle che
// scrivono `engine._controllo_di_piatto` / `engine._proposta_residuo`
// (`mike_events.ctx.uscita_proposta` con `residuo_scoperto`) e
// `service._registra_avvisi_esecuzione` (`mike_activity`).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MikeEvent, MikeLeg } from '@/lib/mike';
import { MIKE_ACTIVITY_EXTRA, mikeActivityLine } from '@/lib/mike';
import { esitoChiusuraMike } from '@/lib/mikeEsitoChiusura';

const requestMike = vi.fn(async () => 1);
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    requestMike: (...a: unknown[]) => requestMike(...a as []),
}));

import { PropostaUscitaMike } from './PropostaUscitaMike';

const ORA_MS = Date.now();
const ORA_S = ORA_MS / 1000;

function gamba(over: Partial<MikeLeg>): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back',
        price: 1.54, size: 5, matched: 5, avg_price: 1.54, ref: `r-${Math.random()}`,
        status: 'open', placed_at: ORA_S - 600, persistence: 'LAPSE', cycle_no: 0,
        final: false, archived: false, closes_ref: null, ...over,
    };
}

// i numeri veri di Ashdod: punta Under 3,5 5 @ 1,54, banca Under 4,5 6,32 @ 1,23,
// banca Under 3,5 6,21 @ 1,24 abbinata; la banca Under 4,5 resta a mercato
const GAMBE: MikeLeg[] = [
    gamba({ ref: 'under_entry-0-1' }),
    gamba({ ref: 'over_cover-0-4', role: 'over_cover', market: 'OU45', side: 'lay', price: 1.23, size: 6.32, matched: 6.32, avg_price: 1.23 }),
    gamba({ ref: 'under_close-0-5', role: 'under_close', side: 'lay', price: 1.24, size: 6.21, matched: 6.21, avg_price: 1.24, placed_at: ORA_S - 30 }),
];

function proposta(over: Record<string, unknown> = {}) {
    const motivo = 'chiusura parziale: residuo scoperto su OU45/UNDER punta 7.55 @ 1.03 (tentativi esauriti (20))';
    return {
        chiave: 'residuo_scoperto|c0', categoria: 'residuo_scoperto', ciclo: 0, stato: 'LIVE_CLOSING',
        stato_voluto: 'FLAT', motivo, close_reason: 'profit',
        ordini: [{ ruolo: 'over_close', mercato: 'OU45', selezione: 'UNDER', lato: 'back', prezzo: 1.03, size: 7.55, piazzabile: true }],
        bloccabile: 0.33, urgente: true, minuto: 67, gol: 2,
        decided_at: ORA_S - 12, proposed_at: ORA_S - 12, residuo_scoperto: true,
        esposizioni: [{ mercato: 'OU45', selezione: 'OVER', se_vince: 6.32, se_perde: -1.45, sbilancio: 7.77 }],
        sostanza: ['residuo_scoperto|c0', [['OU45', 'UNDER', 'back', true]]],
        ...over,
    };
}

function ev(ctx: Record<string, unknown>, state = 'LIVE_CLOSING'): MikeEvent {
    return {
        event_id: '36134689', fixture_id: null, event_name: 'FC Ashdod v Maccabi Herzliya',
        competition: 'Israeli Premier League', league_id: null,
        ko_at: new Date(ORA_MS - 4000_000).toISOString(), mode: 'live', markets: {},
        state: state as MikeEvent['state'], cycle_no: 0, entry_price_initial: 1.54, dossier: null,
        live: {
            goals: 2, published_ts: ORA_S - 1, feed_age_s: 1,
            cashout: { net: 0.33, gross: 0.41, base: 5, complete: true, pct: 6.6 },
            books: { 'OU45|UNDER': { best_back: 1.03, best_lay: 1.04 } },
        } as unknown as MikeEvent['live'],
        positions: GAMBE, ctx, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    };
}

describe('01/10 - la proposta del residuo scoperto', () => {
    it('dice che Mike NON riesce a chiudere da solo, mostra l’ordine esatto e non si approva', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta(), close_reason: 'profit', attempts: 20 })} />);
        expect(screen.getByTestId('cr-mike-proposta-titolo').textContent)
            .toBe('Mike NON riesce a chiudere da solo: chiusura NON completata: residuo scoperto');
        expect(screen.getByTestId('cr-mike-proposta-ordini').textContent).toContain('back 7,55 € @ 1,03');
        expect(screen.queryByTestId('cr-mike-proposta-approva')).toBeNull();
        expect(screen.getByTestId('cr-mike-proposta-residuo').textContent)
            .toBe('chiudi a mano: «Chiudi» di Mike o direttamente su Betfair con l’ordine qui sopra');
        expect(screen.getByTestId('cr-mike-proposta-esecuzione').textContent).not.toContain('al clic');
    });

    it('mostra le scelte dell’utente scritte dal bot', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta({ alternative: [
            'lasciare il residuo fino al regolamento',
            'aumentare la posizione di un importo minimo e poi chiudere tutto'] }) })} />);
        expect(screen.getByTestId('cr-mike-proposta-alternative').textContent).toBe(
            'scelte: lasciare il residuo fino al regolamento · oppure aumentare la posizione di un importo minimo e poi chiudere tutto');
    });

    it('una proposta normale non cambia: titolo e bottone di sempre', () => {
        render(<PropostaUscitaMike ev={ev({ uscita_proposta: proposta({ residuo_scoperto: undefined, categoria: 'chiusura', urgente: false }) }, 'LIVE_COVERED')} />);
        expect(screen.getByTestId('cr-mike-proposta-titolo').textContent)
            .toBe('Mike vorrebbe uscire: cash out della posizione (può chiudere IN PERDITA)');
        expect(screen.getByTestId('cr-mike-proposta-approva')).toBeTruthy();
    });
});

describe('01/10 - l’esito della chiusura con il residuo scoperto', () => {
    it('NON COMPLETA con l’esposizione vera, e il motivo non dice «chiusa in profitto»', () => {
        const e = esitoChiusuraMike(ev({ uscita_proposta: proposta(), close_reason: 'profit', attempts: 20 }),
            { nowMs: ORA_MS, tentativiMax: 20 })!;
        expect(e.tipo).toBe('non_completa');
        expect(e.titolo).toMatch(/^NON COMPLETA - resta esposizione di 1,45 € su Over 4.5/);
        expect(e.motivo).toBe('chiusura avviata da Mike, NON completata: resta esposizione');
        expect(e.motivo).not.toContain('profitto');
        expect(e.dettagli.join(' | ')).toContain('Mike non riesce a chiudere il residuo da solo');
    });

    it('senza la proposta del residuo resta l’esito di prima («Chiusura in corso»)', () => {
        const e = esitoChiusuraMike(ev({ uscita_proposta: null, close_reason: 'profit', attempts: 2 }),
            { nowMs: ORA_MS, tentativiMax: 20 })!;
        expect(e.tipo).toBe('in_corso');
    });
});

describe('01/10 - le righe di attività nuove', () => {
    it('chiusura parziale e ordine sotto minimo: etichetta italiana critica e testo del servizio', () => {
        expect(MIKE_ACTIVITY_EXTRA.chiusura_parziale.critical).toBe(true);
        expect(MIKE_ACTIVITY_EXTRA.ordine_sotto_minimo.critical).toBe(true);
        expect(mikeActivityLine('chiusura_parziale', {
            testo: 'chiusura parziale: residuo scoperto su OU45/UNDER punta 7.55 @ 1.03',
            perche: 'tentativi esauriti (20)', state: 'LIVE_CLOSING', critical: true,
        })).toMatch(/^chiusura parziale: residuo scoperto su OU45\/UNDER punta 7\.55 @ 1\.03 \(tentativi esauriti \(20\)\) · la partita NON è chiusa/);
        expect(mikeActivityLine('ordine_sotto_minimo', {
            testo: 'ordine over_close banca 0.43 sotto il minimo Betfair .it di 0.50: non inviato',
            state: 'LIVE_CLOSING',
        })).toMatch(/^ordine over_close banca 0\.43 sotto il minimo Betfair \.it di 0\.50: non inviato · fase /);
    });
});
