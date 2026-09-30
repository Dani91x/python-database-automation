// ============================================================================
// SchedaPreMatch.cashout.test.tsx - W_B1 (30/09, P10): la scheda PRE-PARTITA
// riceve le operazioni e mostra il cash out della partita e la scheda di Mike,
// come la scheda in gioco. Finti con le STESSE chiavi di
// `CashOutGlobale.montaggio.test.tsx` (riga `OperazionePartita` e `MikeEvent`).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SchedaPreMatch } from './SchedaPreMatch';
import type { OperazionePartita } from './useControlRoom';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { MikeEvent } from '@/lib/mike';

function partitaPre(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: '36132117', sport: 'calcio', nome: 'Roma – Lazio', campionato: 'Serie A',
        koMs: Date.now() + 1800_000, stato: 'pre', minuto: null, punteggio: null,
        controlloDisponibile: false, etaFeedS: null, freschezza: 'ignota',
        latenzaQuoteS: null, freschezzaQuote: 'ignota', statoQuote: 'ignoto',
        media: null, extra: null, marketId: null,
        soldi: null, target: null, avanzamento: null,
        ...over,
    };
}

/** una punta di Mike pre-fischio, abbinata per intero, prezzo dello scanner come ripiego */
function puntaMike(): OperazionePartita {
    return {
        id: 7001, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', prezzo: 1.5, size: 10,
        stato: 'open', pnl: null, modalita: 'live', at: '2026-09-30T18:00:00.000Z', quale: null,
        ordine: { status: 'open', side: 'back', price: 1.5, size: 10, size_requested: 10, size_matched: 10,
            size_remaining: 0, avg_price_matched: 1.5, betfair_updated_at: null, meta: null },
        dettaglio: null, marketId: '1.35', selectionId: 11, liability: null, vivo: null, etaQuoteS: null,
        chiusura: {
            lato: 'lay', prezzo: null, abbinabile: null, bloccabile: null,
            alMs: { win: 0, lose: 0, marketId: '1.35', selectionId: 11, sport: 'calcio', istanteScannerMs: Date.now() - 2000,
                scanner: { back: 1.52, backSize: 50, lay: 1.54, laySize: 50 }, aliquota: 0.05 },
        },
        chiusureOrdini: [], eventId: '36132117', chiudeId: null,
    };
}

function mikeEvento(): MikeEvent {
    return {
        event_id: '36132117', fixture_id: null, event_name: 'Roma v Lazio', competition: null, league_id: null,
        ko_at: new Date(Date.now() + 1800_000).toISOString(), mode: 'live',
        markets: { OU35: { market_id: '1.35' }, OU45: { market_id: '1.45' } },
        state: 'PRE_OPEN', cycle_no: 0, entry_price_initial: 1.5, dossier: null,
        live: { goals: 0, published_ts: Date.now() / 1000 - 1, feed_age_s: 0.2 },
        positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    } as MikeEvent;
}

function monta(operazioni: OperazionePartita[] | undefined, mike: MikeEvent | null = null) {
    return render(
        <MemoryRouter>
            <SchedaPreMatch p={partitaPre()} scheda="pre" mancaS={1800} operazioni={operazioni} mike={mike} />
        </MemoryRouter>,
    );
}

describe('W_B1 P10: la scheda pre-partita con le operazioni e il cash out', () => {
    it('una punta di Mike pre-fischio: la riga dell’operazione, il riquadro del cash out e la scheda di Mike', () => {
        monta([puntaMike()], mikeEvento());
        const ops = screen.getByTestId('cr-pre-operazioni');
        expect(within(ops).getByTestId('cr-op-riga')).toHaveTextContent('Under 3.5');
        const co = screen.getByTestId('cr-cashout-globale');
        expect(within(co).getAllByTestId('cr-cashout-globale-live-gamba')).toHaveLength(1);
        expect(screen.getByTestId('cr-pre-mike')).toBeTruthy();
    });

    it('senza operazioni: niente riquadro del cash out, niente scheda di Mike', () => {
        monta([], mikeEvento());
        expect(screen.queryByTestId('cr-pre-operazioni')).toBeNull();
        expect(screen.queryByTestId('cr-cashout-globale')).toBeNull();
        expect(screen.queryByTestId('cr-pre-mike')).toBeNull();
    });

    it('operazioni di un altro bot, Mike che non lavora la partita: cash out sì, scheda di Mike no', () => {
        monta([{ ...puntaMike(), bot: 'omega', id: 8001 }], null);
        expect(screen.getByTestId('cr-cashout-globale')).toBeTruthy();
        expect(screen.queryByTestId('cr-pre-mike')).toBeNull();
    });
});
