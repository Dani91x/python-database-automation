// ============================================================================
// CashOutGlobale.montaggio.test.tsx - 30/09 (P12b): il riquadro del cash out
// della PARTITA montato nella scheda VERA (`SchedaPartita`), accanto al
// pulsante «Cash out Safe» che resta com'e'.
//
// FALSIFICAZIONE (`falsifica_c_p12b.sh`): togliendo il montaggio, `dueEsiti`,
// `esitoDeciso` o il filtro «nessuna sottoscrizione senza gambe» -> rossi.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SchedaPartita } from './SchedaPartita';
import { ChiusuraRigaContext } from './BottoneChiudiRiga';
import type { OperazionePartita } from './useControlRoom';
import type { PartitaGiornata } from '@/lib/controlRoom';
import type { MikeEvent } from '@/lib/mike';

function partitaCalcio(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: '35001', sport: 'calcio', nome: 'Follo – Sarpsborg', campionato: 'Coppa',
        koMs: Date.now() - 3600_000, stato: 'live', minuto: 63, punteggio: '0-0',
        controlloDisponibile: false, etaFeedS: null, freschezza: 'ignota',
        latenzaQuoteS: null, freschezzaQuote: 'ignota', statoQuote: 'ignoto',
        media: null, extra: null, marketId: null,
        soldi: null, target: null, avanzamento: null,
        ...over,
    };
}

function op(p: Partial<OperazionePartita> & Pick<OperazionePartita, 'id' | 'bot'>): OperazionePartita {
    return {
        selezione: null, lato: 'back', prezzo: 2, size: 5, stato: 'open', pnl: null, modalita: 'live',
        at: '2026-09-30T14:00:00.000Z', quale: null,
        ordine: { status: 'open', side: 'back', price: 2, size: 5, size_requested: 5, size_matched: 5,
            size_remaining: 0, avg_price_matched: 2, betfair_updated_at: null, meta: null },
        dettaglio: null, marketId: null, selectionId: null, liability: null, vivo: null, etaQuoteS: null,
        chiusura: null, chiusureOrdini: [], eventId: '35001', chiudeId: null,
        ...p,
    };
}

/** una gamba di Mike abbinata per intero, col prezzo dello scanner come ripiego */
function gambaMike(id: number, selezione: string, lato: 'back' | 'lay', prezzo: number, importo: number,
    marketId: string, selectionId: number, scanner: { back: number | null; lay: number | null }): OperazionePartita {
    return op({
        id, bot: 'mike', selezione, lato, marketId, selectionId, prezzo, size: importo,
        ordine: { status: 'open', side: lato, price: prezzo, size: importo, size_requested: importo,
            size_matched: importo, size_remaining: 0, avg_price_matched: prezzo, betfair_updated_at: null, meta: null },
        chiusura: {
            lato: lato === 'back' ? 'lay' : 'back', prezzo: null, abbinabile: null, bloccabile: null,
            alMs: { win: 0, lose: 0, marketId, selectionId, sport: 'calcio', istanteScannerMs: Date.now() - 4300,
                scanner: { back: scanner.back, backSize: 50, lay: scanner.lay, laySize: 50 }, aliquota: 0.05 },
        },
    });
}

function mikeEvento(over: Partial<MikeEvent> = {}, live: Partial<NonNullable<MikeEvent['live']>> = {}): MikeEvent {
    return {
        event_id: '35001', fixture_id: null, event_name: 'Follo v Sarpsborg', competition: null, league_id: null,
        ko_at: null, mode: 'live', markets: { OU35: { market_id: '1.35' }, OU45: { market_id: '1.45' } },
        state: 'LIVE_COVERED', cycle_no: 0, entry_price_initial: null, dossier: null,
        live: {
            goals: 0, published_ts: Date.now() / 1000 - 1, feed_age_s: 0.2,
            cashout: { net: -0.84, gross: -0.84, base: 9.8, complete: true, pct: -8.6 },
            ...live,
        },
        positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
        ...over,
    } as MikeEvent;
}

const FOLLO = (): OperazionePartita[] => [
    gambaMike(5085, 'Under 3.5 Goals', 'back', 2.4, 5, '1.35', 11, { back: 2.46, lay: 2.56 }),
    gambaMike(5094, 'Under 4.5 Goals', 'lay', 1.76, 6.32, '1.45', 21, { back: 1.63, lay: 1.68 }),
];

const SAFE = {
    modalita: 'paper' as const, chiusa: { chiusa: false, fonte: null, marcatore: null },
    onCashOut: vi.fn(async () => undefined), onRiprendi: vi.fn(async () => undefined),
};

function monta(operazioni: OperazionePartita[], mike: MikeEvent | null, sorgente?: () => never) {
    const scheda = (
        <MemoryRouter>
            <SchedaPartita p={partitaCalcio()} operazioni={operazioni} mike={mike} safe={SAFE} />
        </MemoryRouter>
    );
    return render(sorgente
        ? <ChiusuraRigaContext.Provider value={{ chiudi: vi.fn(), stato: () => null, sorgenteLadder: sorgente }}>{scheda}</ChiusuraRigaContext.Provider>
        : scheda);
}

describe('P12b: il cash out della PARTITA dentro la scheda', () => {
    it('Follo, due gambe di Mike: −0,82 netto, accanto «il bot Mike calcola −0,84 [BOT]»; il pulsante Safe resta', () => {
        monta(FOLLO(), mikeEvento());
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,82 €');
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba')).toHaveLength(2);
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-netto').textContent).toBe('−0,84 €');
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-marchio').getAttribute('data-fonte')).toBe('bot');
        // prezzi dello scanner (nessun ladder al ms): dichiarato riga per riga
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba')[0].textContent).toContain('prezzo dello scanner');
        // il pulsante di Safe c'e' ancora, con il suo nome vero
        expect(screen.getByTestId('cr-cashout-partita-avvia').textContent).toBe('Cash out Safe');
        expect(screen.getByTestId('cr-cashout-partita-bloccato').textContent)
            .toBe('nessuna posizione viva di Safe su questa partita');
    });

    it('Mike dichiara la SUA cifra incompleta: «il bot: non calcolabile», nessun numero', () => {
        monta(FOLLO(), mikeEvento({}, { cashout: { net: -0.1, gross: -0.1, base: 9.8, complete: false, pct: null } }));
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-netto').textContent).toBe('non calcolabile');
        expect(screen.queryByTestId('cr-cashout-globale-live-bot-mike-differenza')).toBeNull();
    });

    it('senza gambe: nessun riquadro e NESSUNA sorgente toccata (le card del giorno non aprono niente)', () => {
        const subscribe = vi.fn(() => () => undefined);
        const sorgente = vi.fn(() => ({ fetch: async () => null, subscribe, fonte: () => 'canale' as const }) as never);
        monta([], null, sorgente as unknown as () => never);
        expect(screen.queryByTestId('cr-cashout-globale')).toBeNull();
        expect(sorgente).not.toHaveBeenCalled();
        expect(subscribe).not.toHaveBeenCalled();
        // il pulsante Safe e' indipendente dal riquadro
        expect(screen.getByTestId('cr-cashout-partita-avvia')).toBeTruthy();
    });

    it('con gambe: UNA sottoscrizione per mercato dal contesto della Control Room', () => {
        const subscribe = vi.fn(() => () => undefined);
        const sorgente = vi.fn(() => ({ fetch: async () => null, subscribe, fonte: () => 'canale' as const }) as never);
        monta(FOLLO(), null, sorgente as unknown as () => never);
        expect(subscribe.mock.calls.map((c) => (c as unknown[])[0]).sort()).toEqual(['1.35', '1.45']);
    });

    it('Mike, 4 gol: l\'Under 3,5 e\' PERSA (engine.selection_decided): vale −stake senza prezzo, cifra completa −8,75', () => {
        // engine.py:666-677 - gol > linea: Over vinto, Under perso. Parita' con
        // test_mike_engine_cert_2026_09_12.py:303-316 (net -8,75)
        const ops = [
            gambaMike(1, 'Under 3.5 Goals', 'back', 1.5, 20, '1.35', 11, { back: null, lay: null }),
            gambaMike(2, 'Over 4.5 Goals', 'back', 8.0, 4, '1.45', 22, { back: 2.0, lay: 2.02 }),
        ];
        monta(ops, mikeEvento({}, { goals: 4, cashout: null }));
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−8,75 €');
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba')[0].getAttribute('data-stato')).toBe('decisa');
    });

    it('W_C: TENNIS, punta P1 e punta P2 sul Match Odds (due esiti): si nettano in UNA riga pareggiata', () => {
        // back 10 @ 2,0 su entrambi: qualunque vinca, +10 -10 = 0. Senza i due esiti
        // sarebbero due posizioni in perdita da chiudere separatamente.
        const tennis = (id: number, sel: number) => gambaMike(id, `Giocatore ${sel}`, 'back', 2.0, 10, '1.9', sel, { back: 1.98, lay: 2.02 });
        const ops = [tennis(11, 1), tennis(12, 2)].map((o) => ({ ...o, bot: 'tennis_scalper' as const }));
        const conMo = render(
            <MemoryRouter>
                <SchedaPartita p={partitaCalcio({ sport: 'tennis', marketId: '1.9' })} operazioni={ops} />
            </MemoryRouter>,
        );
        expect(conMo.getAllByTestId('cr-cashout-globale-live-gamba')).toHaveLength(1);
        expect(conMo.getAllByTestId('cr-cashout-globale-live-gamba')[0].getAttribute('data-stato')).toBe('piatta');
        expect(conMo.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('+0,00 €');
        conMo.unmount();
        // un altro mercato tennis (non il Match Odds): resta per selezione
        render(
            <MemoryRouter>
                <SchedaPartita p={partitaCalcio({ sport: 'tennis', marketId: '1.55' })} operazioni={ops} />
            </MemoryRouter>,
        );
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba')).toHaveLength(2);
    });

    it('Mike, Over 4,5 + Under 4,5 sullo stesso mercato O/U (due esiti): UNA riga, +1,81', () => {
        // parita' con test_mike_engine_cert_2026_09_12.py:164-174
        const ops = [
            gambaMike(3, 'Over 4.5 Goals', 'back', 8.0, 4, '1.45', 22, { back: 9.0, lay: 9.4 }),
            gambaMike(4, 'Under 4.5 Goals', 'back', 1.4, 10, '1.45', 21, { back: 1.3, lay: 1.32 }),
        ];
        monta(ops, mikeEvento({}, { cashout: null }));
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba')).toHaveLength(1);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('+1,81 €');
    });
});
