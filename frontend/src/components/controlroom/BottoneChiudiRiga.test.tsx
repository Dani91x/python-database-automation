// ============================================================================
// BottoneChiudiRiga.test.tsx — B16 (24/09): il «Chiudi» di ogni riga della
// Control Room porta al SUO bot, e dice sempre in che stato e'.
//
// Montato dentro `RigaOperazione` (la riga vera di Live/Aperte/Pre-match) con
// il contesto che la pagina fornisce. Il finto dell'API ha la stessa forma di
// quella vera (`vm.chiudi` / `vm.statoChiusuraRiga`).
//
// FALSIFICAZIONE (24/09, patch salvata): (1) il bottone che passa
// `bot: 'safe'` fisso invece di `o.bot` → rosso il test Omega/Mike; (2) il
// bottone nascosto (return null) per i bot tennis invece che spento col
// motivo → rosso; (3) l'esito non mostrato → rosso.
// D3 (24/09): i bot tennis ora hanno il Chiudi ACCESO (coda tennis
// `chiudi_bot`). Falsificazione D3: (4) `marketId` non passato dalla riga ->
// rosso; (5) il rifiuto per i bot tennis rimesso in `chiudibile` -> rosso.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RigaOperazione } from './DettaglioRigaView';
import { ChiusuraRigaContext, type ChiusuraRigaApi } from './BottoneChiudiRiga';
import type { RigaOrdine } from '@/lib/statoOrdine';
import type { OperazionePartita } from './useControlRoom';
import type { StatoChiusuraRiga } from './chiudiRiga';

function ordine(status = 'open'): RigaOrdine {
    return {
        status, side: 'lay', price: 55, size: 5,
        size_requested: 8, size_matched: 5, size_remaining: 0,
        avg_price_matched: 55, betfair_updated_at: '2026-09-24T10:00:00.000Z', meta: null,
    };
}

function op(over: Partial<OperazionePartita> = {}): OperazionePartita {
    return {
        bot: 'omega', id: 900, selezione: '1 - 3', lato: 'lay', prezzo: 55, size: 5,
        stato: 'open', pnl: null, modalita: 'live', at: '2026-09-24T10:00:00.000Z',
        quale: 'ft_cs', ordine: ordine(), dettaglio: null, marketId: '1.9', selectionId: 14,
        liability: 270, vivo: null, etaQuoteS: null, chiusura: null, chiusureOrdini: [],
        eventId: 'E1', chiudeId: null,
        ...over,
    };
}

function monta(o: OperazionePartita, stato: StatoChiusuraRiga | null = null) {
    const api: ChiusuraRigaApi = {
        chiudi: vi.fn(async () => undefined),
        stato: vi.fn(() => stato),
    };
    render(
        <ChiusuraRigaContext.Provider value={api}>
            <RigaOperazione o={o} />
        </ChiusuraRigaContext.Provider>,
    );
    return api;
}

describe('B16 - il bottone chiama il SUO bot', () => {
    it.each([
        ['omega', 900, 'E1', 'live'],
        ['mike', 801, 'E2', 'paper'],
        ['safe', 321, '36061420', 'paper'],
    ] as const)('riga %s: chiudi con bot/id/partita/modalita\' DELLA RIGA', (bot, id, ev, modo) => {
        const api = monta(op({ bot, id, eventId: ev, modalita: modo }));
        const b = screen.getByTestId('cr-op-chiudi');
        expect(b).not.toBeDisabled();
        expect(b.getAttribute('data-bot')).toBe(bot);
        fireEvent.click(b);
        expect(api.chiudi).toHaveBeenCalledWith({
            bot, id, eventId: ev, marketId: '1.9', modalita: modo, stato: 'open', chiudeId: null, regolata: false,
        });
    });

    it.each(['tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing'] as const)(
        'D3 (24/09) - bot TENNIS %s: il bottone e\' ACCESO e chiude la partita del bot, col mercato della riga',
        (bot) => {
            const api = monta(op({
                bot, id: 5, stato: 'EXECUTABLE', modalita: 'paper', eventId: '35800001', marketId: '1.200',
            }));
            const b = screen.getByTestId('cr-op-chiudi');
            expect(b).not.toBeDisabled();
            expect(b.getAttribute('data-bot')).toBe(bot);
            expect(b.getAttribute('title')).toMatch(/non rientra/);
            fireEvent.click(b);
            expect(api.chiudi).toHaveBeenCalledWith({
                bot, id: 5, eventId: '35800001', marketId: '1.200', modalita: 'paper',
                stato: 'EXECUTABLE', chiudeId: null, regolata: false,
            });
        },
    );

    it('bot TENNIS senza mercato della riga: il bottone c\'e\', SPENTO, e dice perche\'', () => {
        const api = monta(op({ bot: 'tennis_scalper', id: 5, stato: 'EXECUTABLE', modalita: 'paper', marketId: null }));
        const b = screen.getByTestId('cr-op-chiudi');
        expect(b).toBeDisabled();
        expect(b.getAttribute('data-motivo')).toMatch(/mercato/);
        expect(b.getAttribute('title')).toMatch(/non chiudibile/);
        fireEvent.click(b);
        expect(api.chiudi).not.toHaveBeenCalled();
    });

    it('bot TENNIS regolato (P&L presente): nessun bottone', () => {
        monta(op({ bot: 'tennis_pro', id: 6, stato: 'EXECUTION_COMPLETE', modalita: 'paper', pnl: 0.4 }));
        expect(screen.queryByTestId('cr-op-chiudi')).toBeNull();
    });

    it('gamba di chiusura / coperta / modalita\' ignota: spento col motivo', () => {
        monta(op({ stato: 'hedged' }));
        expect(screen.getByTestId('cr-op-chiudi').getAttribute('data-motivo')).toMatch(/coperta/);
    });

    it('riga regolata: nessun bottone (non e\' una posizione)', () => {
        monta(op({ stato: 'won', pnl: 3 }));
        expect(screen.queryByTestId('cr-op-chiudi')).toBeNull();
    });

    it('senza il contesto della pagina: nessun bottone (le altre pagine restano identiche)', () => {
        render(<RigaOperazione o={op()} />);
        expect(screen.queryByTestId('cr-op-chiudi')).toBeNull();
    });
});

describe('B16 - l\'esito si vede accanto al bottone', () => {
    const base: StatoChiusuraRiga = {
        bot: 'omega', id: 900, requestId: 11, faseRichiesta: 'inviata', richiestaChiusa: false,
        motivo: null, rigaCambiata: false, inviataMs: 0,
    };
    it('inviata: bottone spento, «richiesta inviata»', () => {
        monta(op(), base);
        expect(screen.getByTestId('cr-op-chiudi')).toBeDisabled();
        expect(screen.getByTestId('cr-op-chiudi-esito')).toHaveTextContent('richiesta inviata');
    });
    it('presa in carico', () => {
        monta(op(), { ...base, faseRichiesta: 'presa_in_carico' });
        expect(screen.getByTestId('cr-op-chiudi-esito').getAttribute('data-fase')).toBe('presa_in_carico');
    });
    it('eseguita (la riga e\' cambiata sul canale)', () => {
        monta(op(), { ...base, rigaCambiata: true });
        expect(screen.getByTestId('cr-op-chiudi-esito')).toHaveTextContent('eseguita');
    });
    it('rifiutata: col motivo del servizio, e il bottone torna acceso', () => {
        monta(op(), { ...base, faseRichiesta: 'rifiutata', richiestaChiusa: true, motivo: 'rifiutato: altro bot' });
        expect(screen.getByTestId('cr-op-chiudi-esito')).toHaveTextContent('rifiutata: rifiutato: altro bot');
        expect(screen.getByTestId('cr-op-chiudi')).not.toBeDisabled();
    });
});
