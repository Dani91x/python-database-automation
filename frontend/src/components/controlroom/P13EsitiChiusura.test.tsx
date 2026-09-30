// ============================================================================
// P13EsitiChiusura.test.tsx - 30/09 (blocco P13 del monitor veritiero,
// `AUDIT_2026-09-30/PROGETTO_UI_MONITOR_VERITIERO.md` §5.A e §5.C.6).
//
// Caso vero, Follo v Sarpsborg (utente, 16:05): sotto la punta Under 3,5
// (mike_trades 5085) due banche di green-up (5086, 5093) mai abbinate e
// RITIRATE da Mike comparivano come «ERRORE green-up» due volte. Non erano
// errori ne' rifiuti di Betfair:
//   5086  status 'error', meta.reason 'reconciled_not_placed'
//         (Betfair/mike/service.py:5422-5424, riconciliazione: nessun ordine
//         abbinato con quel riferimento su Betfair)
//   5093  status 'error', meta.reason 'cancelled_by_engine',
//         meta.esito_ordine 'ritirato_da_noi' (service.py:4307, :5532-5548)
// Le chiavi dei finti sono quelle che scrive il servizio (`_trade_row`
// service.py:563-590: phase, leg_ref, final, exit_kind, exit_reason,
// closes_ref; poi reason/esito_ordine/reconciled) e le colonne di
// consapevolezza (size_matched, size_remaining, ...).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { esitoOrdineMeta, statusMetaOf } from '@/lib/tradeStatus';
import { dettaglioDi } from './dettaglioRiga';
import { RigaOperazione } from './DettaglioRigaView';
import type { OperazionePartita } from './useControlRoom';
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';

type RigaMike = {
    id: number; event_id: string; event_name: string; side: string; status: string; pnl: number;
    price: number; size: number; liability: number; placed_at: string; closes_trade_id: number | null;
    mode: string; role: string; strategy: string; cycle_no: number; market_type: string;
    selection_name: string; size_requested: number | null; size_matched: number | null;
    size_remaining: number | null; avg_price_matched: number | null; betfair_updated_at: string | null;
    minute_at_entry: number | null; score_at_entry: string | null;
    meta: Record<string, unknown>;
};

const APERTURA_5085: RigaMike = {
    id: 5085, event_id: '35760084', event_name: 'Follo v Sarpsborg', side: 'back', status: 'open', pnl: 0,
    price: 2.4, size: 5, liability: 5, placed_at: '2026-09-30T13:04:00Z', closes_trade_id: null,
    mode: 'live', role: 'under_entry', strategy: 'under_entry', cycle_no: 0, market_type: 'OVER_UNDER_35',
    selection_name: 'Under 3.5 Goals', size_requested: 5, size_matched: 5, size_remaining: 0,
    avg_price_matched: 2.4, betfair_updated_at: '2026-09-30T13:04:01Z',
    minute_at_entry: null, score_at_entry: null,
    meta: { phase: 'open', leg_ref: 'E35760084-c0-under_entry-1', final: false, bet_id: '1' },
};

const GREEN_5086: RigaMike = {
    id: 5086, event_id: '35760084', event_name: 'Follo v Sarpsborg', side: 'lay', status: 'error', pnl: 0,
    price: 2.36, size: 5.08, liability: 6.91, placed_at: '2026-09-30T13:10:00Z', closes_trade_id: 5085,
    mode: 'live', role: 'under_green', strategy: 'under_green', cycle_no: 0, market_type: 'OVER_UNDER_35',
    selection_name: 'Under 3.5 Goals', size_requested: 5.08, size_matched: null, size_remaining: null,
    avg_price_matched: null, betfair_updated_at: null, minute_at_entry: null, score_at_entry: null,
    meta: {
        phase: 'cancelled', leg_ref: 'E35760084-c0-under_green-2', final: false,
        exit_kind: 'greenup', exit_reason: 'under_green', closes_ref: 'E35760084-c0-under_entry-1',
        reason: 'reconciled_not_placed', reconciled: true,
    },
};

const GREEN_5093: RigaMike = {
    ...GREEN_5086, id: 5093, placed_at: '2026-09-30T13:40:00Z',
    size_matched: 0, size_remaining: 0,
    meta: {
        phase: 'cancelled', leg_ref: 'E35760084-c0-under_green-3', final: false,
        exit_kind: 'greenup', exit_reason: 'under_green', closes_ref: 'E35760084-c0-under_entry-1',
        reason: 'cancelled_by_engine', esito_ordine: 'ritirato_da_noi',
    },
};

function ordineDi(r: RigaMike): RigaOrdine {
    return {
        status: r.status, side: r.side, price: r.price, size: r.size,
        size_requested: r.size_requested, size_matched: r.size_matched, size_remaining: r.size_remaining,
        avg_price_matched: r.avg_price_matched, betfair_updated_at: r.betfair_updated_at, meta: r.meta,
    };
}

function operazione(apertura: RigaMike, chiusure: RigaMike[]): OperazionePartita {
    return {
        bot: 'mike', id: apertura.id, selezione: apertura.selection_name, lato: 'back', prezzo: apertura.price,
        size: apertura.size, stato: apertura.status, pnl: null, modalita: 'live',
        at: apertura.placed_at, quale: apertura.strategy,
        ordine: ordineDi(apertura),
        dettaglio: dettaglioDi(apertura, chiusure),
        marketId: '1.35', selectionId: 47972, liability: apertura.liability,
        vivo: null, etaQuoteS: null, chiusura: null,
        chiusureOrdini: chiusure.map(ordineDi),
    };
}

// ----------------------------------------------------------- mappa degli esiti
describe('esitoOrdineMeta - l’esito VERO di un ordine non abbinato', () => {
    it('ritirato da noi (esito_ordine) e ritiro del motore (reason di prima del 29/09)', () => {
        expect(esitoOrdineMeta({ status: 'error', meta: GREEN_5093.meta })?.label).toBe('RITIRATO dal bot');
        expect(esitoOrdineMeta({ status: 'error', meta: { phase: 'cancelled', reason: 'cancelled_by_engine' } })?.label)
            .toBe('RITIRATO dal bot');
    });

    it('riconciliazione senza ordine su Betfair', () => {
        expect(esitoOrdineMeta({ status: 'error', meta: GREEN_5086.meta })?.label)
            .toBe('NON ABBINATO (verificato su Betfair)');
    });

    it('rifiuto di Betfair col codice, dovunque il servizio l’abbia scritto (codice da statoOrdine)', () => {
        const rif = (meta: Record<string, unknown>) => esitoOrdineMeta({ status: 'error', meta }, statoOrdine({ status: 'error', meta }).errorCode)?.label;
        expect(rif({ esito_ordine: 'rifiutato', reason: 'live_rifiutato:INSUFFICIENT_FUNDS' })).toBe('RIFIUTATO da Betfair: INSUFFICIENT_FUNDS');
        expect(rif({ esito_ordine: 'rifiutato', reason: 'live_not_matched:EXECUTION_COMPLETE:BET_TAKEN_OR_LAPSED' })).toBe('RIFIUTATO da Betfair: BET_TAKEN_OR_LAPSED');
        expect(rif({ esito_ordine: 'rifiutato', reason: 'runner_rifiutato' })).toBe('RIFIUTATO da Betfair (codice non dichiarato)');
    });

    it('gli altri esiti del servizio di Mike (M8.13)', () => {
        expect(esitoOrdineMeta({ status: 'error', meta: { esito_ordine: 'non_abbinato_fok' } })?.label)
            .toBe('NON ABBINATO (tutto o niente)');
        expect(esitoOrdineMeta({ status: 'error', meta: { esito_ordine: 'cancellato_da_betfair' } })?.label)
            .toBe('CANCELLATO da Betfair');
        expect(esitoOrdineMeta({ status: 'error', meta: { esito_ordine: 'fermato_da_noi' } })?.label)
            .toBe('FERMATO dal bot (mai inviato)');
    });

    it('fail-closed: esito sconosciuto, nessun esito, o riga non in errore -> nessuna etichetta nuova', () => {
        expect(esitoOrdineMeta({ status: 'error', meta: { esito_ordine: 'boh' } })).toBeNull();
        expect(esitoOrdineMeta({ status: 'error', meta: { reason: 'qualcosa_di_nuovo' } })).toBeNull();
        expect(esitoOrdineMeta({ status: 'error', meta: null })).toBeNull();
        expect(esitoOrdineMeta({ status: 'open', meta: { esito_ordine: 'ritirato_da_noi' } })).toBeNull();
    });

    // W_B2 (30/09): cambiato di proposito - Omega e Safe ora hanno i LORO esiti
    // (W_B2EsitiOmegaSafe.test.tsx); qui resta la regola: statusMetaOf non cambia,
    // e cio' che non si classifica resta ERRORE col motivo scritto accanto
    it('Omega e Safe: statusMetaOf invariato; il non classificabile resta ERRORE col motivo', () => {
        const omega = { status: 'error', meta: { error_final: true, leg_failed: true, reason: 'live_not_matched', error_at: '2026-09-30T10:00:00Z' } };
        expect(esitoOrdineMeta(omega)).toBeNull();
        expect(statusMetaOf(omega).label).toBe('ERRORE (definitivo)');
        expect(dettaglioDi({ id: 1, event_id: 'E', side: 'lay', status: 'error', pnl: 0, placed_at: '2026-09-30T10:00:00Z', meta: omega.meta }).stato.label)
            .toBe('ERRORE (definitivo) · non abbinato o rifiutato da Betfair (codice non scritto sulla riga)');
        const safeSemplice = { status: 'error', meta: { reason: 'live_not_matched:EXPIRED' } };
        expect(statusMetaOf(safeSemplice).label).toBe('ERRORE');
        expect(esitoOrdineMeta(safeSemplice)?.label).toBe('NON ABBINATO (tutto o niente)');
    });
});

// ------------------------------------------------------ il caso vero, a schermo
describe('Follo v Sarpsborg: 5085 con le green-up 5086 e 5093', () => {
    it('nessun «ERRORE» a schermo, i due tentativi raggruppati, la striscia ANCORA APERTA resta', () => {
        const { container } = render(<RigaOperazione o={operazione(APERTURA_5085, [GREEN_5086, GREEN_5093])} />);
        const testo = container.textContent ?? '';
        expect(testo).not.toMatch(/ERRORE/);
        const gruppo = screen.getByTestId('cr-op-chiusure-gruppo');
        expect(gruppo.textContent).toContain('green-up: 2 tentativi, 0,00 € abbinati');
        expect(gruppo.textContent).toContain('1 ritirato dal bot');
        expect(gruppo.textContent).toContain('1 non abbinato (verificato su Betfair)');
        // le due righe restano, con l'esito vero di ciascuna
        const righe = screen.getAllByTestId('cr-op-chiusure-riga').map((r) => r.textContent ?? '');
        expect(righe).toHaveLength(2);
        expect(righe[0]).toContain('NON ABBINATO (verificato su Betfair)');
        expect(righe[1]).toContain('RITIRATO dal bot');
        // la striscia: vera, e il suo 0 % e' della CHIUSURA
        const striscia = screen.getByTestId('cr-op-esito');
        expect(striscia.getAttribute('data-stato')).toBe('CHIUSURA_FALLITA');
        expect(striscia.textContent).toContain('ANCORA APERTA');
        expect(striscia.textContent).toContain('chiusura abbinata 0%');
        expect(striscia.textContent).toContain('ancora esposti 5,00 €');
        expect(striscia.textContent).not.toMatch(/annullatae|rifiutatae/);
        expect(screen.getByTestId('cr-op-esito-motivo').textContent)
            .toContain('le 2 gambe di chiusura sono finite senza abbinare nulla (2 annullate)');
    });

    it('anche il badge della riga PRINCIPALE usa l’esito vero (una gamba non abbinata mostrata da sola)', () => {
        expect(dettaglioDi(GREEN_5093).stato.label).toBe('RITIRATO dal bot');
        expect(dettaglioDi(GREEN_5086).stato.label).toBe('NON ABBINATO (verificato su Betfair)');
    });

    it('un tentativo solo: nessun gruppo, la riga dice l’esito vero', () => {
        render(<RigaOperazione o={operazione(APERTURA_5085, [GREEN_5093])} />);
        expect(screen.queryByTestId('cr-op-chiusure-gruppo')).toBeNull();
        expect(screen.getByTestId('cr-op-chiusure-riga').textContent).toContain('RITIRATO dal bot');
        expect(screen.getByTestId('cr-op-esito-motivo').textContent)
            .toContain('la gamba di chiusura è finita senza abbinare nulla (annullata)');
    });

    it('esito che non si sa classificare: resta ERRORE anche dentro il gruppo (fail-closed)', () => {
        const ignoto: RigaMike = { ...GREEN_5093, id: 5099, meta: { ...GREEN_5093.meta, esito_ordine: 'nuovo_esito' , reason: 'nuovo' } };
        render(<RigaOperazione o={operazione(APERTURA_5085, [GREEN_5086, ignoto])} />);
        const righe = screen.getAllByTestId('cr-op-chiusure-riga').map((r) => r.textContent ?? '');
        expect(righe[1]).toContain('ERRORE');
        expect(screen.getByTestId('cr-op-chiusure-gruppo').textContent).toContain('1 ERRORE');
    });

    it('chip «banca» rose (design system), mai pink', () => {
        const { container } = render(<RigaOperazione o={operazione(APERTURA_5085, [GREEN_5086, GREEN_5093])} />);
        expect(container.innerHTML).not.toMatch(/pink/);
        const banca = screen.getAllByText('banca');
        expect(banca.length).toBeGreaterThanOrEqual(2);
        for (const b of banca) expect(b.className).toMatch(/rose/);
    });

    it('chip «banca» rose anche sulla riga di una posizione LAY', () => {
        const lay = { ...operazione(GREEN_5093, []), lato: 'lay' as const };
        const { container } = render(<RigaOperazione o={lay} />);
        expect(container.innerHTML).not.toMatch(/pink/);
        expect(screen.getByText('banca').className).toMatch(/rose/);
    });
});

describe('«chiudi ora» della riga: la cifra e’ NETTA di commissione e lo dice', () => {
    it('title del contenitore e della cifra', () => {
        const o = { ...operazione(APERTURA_5085, []), chiusura: { lato: 'lay' as const, prezzo: 2.56, abbinabile: 50, bloccabile: -0.32 } };
        render(<RigaOperazione o={o} />);
        expect(screen.getByTestId('cr-op-chiudo-ora').getAttribute('title')).toContain('netto di commissione');
        expect(screen.getByTestId('cr-op-chiudo-ora-pnl').getAttribute('title')).toContain('netto di commissione');
    });
});
