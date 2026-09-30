// ============================================================================
// OrdiniContoPartita.test.tsx - P14 (30/09): ordini del conto fuori dai bot.
// Finti nella forma ESATTA del contratto di `get_live_orders_account_open()`:
// { rows: [{ bet_id, market_id, selection_id, event_id, event_name,
// market_name, selection_name, side: 'BACK'|'LAY', price_matched,
// size_matched, size_remaining, status, source, placed_at }], letto_at }.
// Il caso di oggi: FC Vsetin, due punte dal sito (~13:31 UTC).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OrdiniContoPartita, OrdiniContoContext } from './OrdiniContoPartita';
import {
    raggruppaOrdiniConto, motivoNonLetti, partiteConOrdiniFuori, ORDINI_CONTO_NON_LETTI, type OrdiniContoStato,
} from './ordiniConto';
import type { OrdineContoFuoriBot } from '@/lib/liveOrders';

const NOW = Date.parse('2026-09-30T14:20:00Z');
export const VSETIN: OrdineContoFuoriBot[] = [
    {
        bet_id: '351001', market_id: '1.OU35V', selection_id: 1222347, event_id: 'VSETIN',
        event_name: 'FC Vsetin v Bohemians', market_name: 'Over/Under 3.5 Goals', selection_name: 'Over 3.5 Goals',
        side: 'BACK', price_matched: 1.92, size_matched: 4.43, size_remaining: 0,
        status: 'EXECUTION_COMPLETE', source: 'account', placed_at: '2026-09-30T13:31:02Z',
    },
    {
        bet_id: '351002', market_id: '1.OU45V', selection_id: 1222346, event_id: 'VSETIN',
        event_name: 'FC Vsetin v Bohemians', market_name: 'Over/Under 4.5 Goals', selection_name: 'Under 4.5 Goals',
        side: 'BACK', price_matched: 1.44, size_matched: 5.18, size_remaining: 0,
        status: 'EXECUTION_COMPLETE', source: 'account', placed_at: '2026-09-30T13:31:40Z',
    },
];

function mostra(stato: OrdiniContoStato, eventId: string) {
    return render(
        <OrdiniContoContext.Provider value={{ stato, nowMs: NOW }}>
            <OrdiniContoPartita eventId={eventId} />
        </OrdiniContoContext.Provider>,
    );
}

describe('ordiniConto - puro', () => {
    it('raggruppa per partita; senza event_id a parte', () => {
        const s = raggruppaOrdiniConto([...VSETIN, { ...VSETIN[0], bet_id: '9', event_id: null }], '2026-09-30T14:19:48Z');
        expect(s.stato).toBe('letti');
        expect(s.perEvento.get('VSETIN')).toHaveLength(2);
        expect(s.senzaEvento).toHaveLength(1);
        expect(partiteConOrdiniFuori(s)).toEqual({ n: 1, nomi: ['FC Vsetin v Bohemians'] });
    });
    it('RPC assente: \u00abRPC non disponibile\u00bb', () => {
        expect(motivoNonLetti(new Error('Could not find the function public.get_live_orders_account_open'))).toBe('RPC non disponibile');
        expect(motivoNonLetti(new Error('timeout'))).toMatch(/lettura fallita: timeout/);
    });
});

describe('OrdiniContoPartita', () => {
    it('Vsetin: i due ordini del sito con lato, selezione, importo e quota; marchio CONTO; avviso ambra', () => {
        mostra(raggruppaOrdiniConto(VSETIN, '2026-09-30T14:19:48Z'), 'VSETIN');
        const el = screen.getByTestId('cr-ordini-conto');
        expect(el.textContent).toMatch(/BACK Over 3\.5 Goals 4,43 \u20ac @ 1,92/);
        expect(el.textContent).toMatch(/BACK Under 4\.5 Goals 5,18 \u20ac @ 1,44/);
        expect(screen.getByTestId('cr-ordini-conto-marchio').textContent).toMatch(/CONTO BETFAIR\s*\u00b7 12 s fa/);
        const avviso = screen.getByTestId('cr-ordini-conto-avviso');
        expect(avviso.textContent).toMatch(/il bot non li vede/);
        expect(avviso.className).toMatch(/amber/);
    });
    it('contratto 2a5cbba: price_matched null = \u00abnon abbinato\u00bb, MAI \u00ab0,00\u00bb ne\' una quota', () => {
        const nulla: OrdineContoFuoriBot = { ...VSETIN[0], bet_id: '351009', price_matched: null, size_matched: 0, size_remaining: 3, status: 'EXECUTABLE' };
        mostra(raggruppaOrdiniConto([nulla], '2026-09-30T14:19:48Z'), 'VSETIN');
        const el = screen.getByTestId('cr-ordine-conto');
        expect(el.textContent).toMatch(/non abbinato/);
        expect(el.textContent).not.toMatch(/0,00/);
        expect(el.textContent).not.toMatch(/@/);
        expect(el.textContent).toMatch(/\+3,00 \u20ac sul book/);
    });
    it('limite del backend: \u00abaperto per il conto letto alle HH:MM:SS\u00bb (ora di Roma)', () => {
        mostra(raggruppaOrdiniConto(VSETIN, '2026-09-30T14:19:48Z'), 'VSETIN');
        expect(screen.getByTestId('cr-ordini-conto-letto').textContent).toMatch(/^aperto secondo lo specchio degli ordini interrogato alle 16:19:48/) // R2-A2: letto_at = interrogazione;
    });
    it('scheda TENNIS: niente (gli ordini manuali tennis non sono in questa fonte)', () => {
        const { container } = render(
            <OrdiniContoContext.Provider value={{ stato: raggruppaOrdiniConto(VSETIN, '2026-09-30T14:19:48Z'), nowMs: NOW }}>
                <OrdiniContoPartita eventId="VSETIN" sport="tennis" />
            </OrdiniContoContext.Provider>,
        );
        expect(container.textContent).toBe('');
    });

    it('partita senza ordini fuori dai bot (letti): niente', () => {
        const { container } = mostra(raggruppaOrdiniConto(VSETIN, '2026-09-30T14:19:48Z'), 'FOLLO');
        expect(container.textContent).toBe('');
    });
    it('non letti: lo dice (mai \u00abnessun ordine\u00bb)', () => {
        mostra({ ...ORDINI_CONTO_NON_LETTI, motivo: 'RPC non disponibile' }, 'VSETIN');
        expect(screen.getByTestId('cr-ordini-conto-non-letti').textContent).toBe('ordini del conto: non letti (RPC non disponibile)');
    });
    it('fuori dalla Control Room (nessun contesto): niente', () => {
        const { container } = render(<OrdiniContoPartita eventId="VSETIN" />);
        expect(container.textContent).toBe('');
    });
});
