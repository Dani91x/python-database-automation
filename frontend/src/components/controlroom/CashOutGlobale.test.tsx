// ============================================================================
// CashOutGlobale.test.tsx - 30/09 (P12a): il riquadro del cash out della
// partita, e il suo montaggio isolato con `useCashOutPartita` (righe VERE della
// scheda, `OperazionePartita`, e ladder al ms finto con le chiavi del vero).
// Il montaggio dentro `SchedaPartita` e' P12b (non qui).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, renderHook, act } from '@testing-library/react';
import { CashOutGlobale } from './CashOutGlobale';
import { useCashOutPartita } from './useCashOutPartita';
import { cashOutPartita, type GambaViva } from '@/lib/cashOutPartita';
import { PREZZO_VUOTO, type PrezzoScheda } from '@/lib/schedaAlMs';
import type { OperazionePartita } from './useControlRoom';

const NOW = 1_800_000_000_000;

const FOLLO: GambaViva[] = [
    { id: 5085, bot: 'mike', modalita: 'live', marketId: '1.35', selectionId: 11, selezione: 'Under 3.5 Goals',
        lato: 'back', abbinato: 5, prezzoMedio: 2.4, aliquota: 0.05 },
    { id: 5094, bot: 'mike', modalita: 'live', marketId: '1.45', selectionId: 21, selezione: 'Under 4.5 Goals',
        lato: 'lay', abbinato: 6.32, prezzoMedio: 1.76, aliquota: 0.05 },
];
const LIBRO: Record<string, Partial<PrezzoScheda>> = {
    '1.35|11': { back: 2.46, backSize: 80, lay: 2.56, laySize: 60 },
    '1.45|21': { back: 1.63, backSize: 90, lay: 1.68, laySize: 70 },
};
const prezzo = (libro: Record<string, Partial<PrezzoScheda>>) => (m: string, s: number): PrezzoScheda | null => {
    const p = libro[`${m}|${s}`];
    return p ? { ...PREZZO_VUOTO, fonte: 'canale', istanteMs: NOW - 300, statoMercato: 'OPEN', ...p } : null;
};

describe('CashOutGlobale: la cifra della partita, netta, con fonte ed eta\'', () => {
    it('Follo: -0,82 netto commissione, due righe, STIMA della pagina, e accanto il bot -0,84 spiegato', () => {
        const r = cashOutPartita(FOLLO, { prezzo: prezzo(LIBRO), nowMs: NOW });
        render(<CashOutGlobale risultato={r} valoriBot={[{ bot: 'mike', netto: -0.84, completo: true, etaS: 1.2 }]} />);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,82 €');
        expect(screen.getByTestId('cr-cashout-globale-live').textContent).toContain('netto commissione');
        expect(screen.getByTestId('cr-cashout-globale-live').textContent)
            .toContain('Cash out della partita: gambe dei bot (se le chiudo tutte adesso)');
        // R_C: sempre scritto, sotto la cifra: gli ordini del sito/app NON sono inclusi
        expect(screen.getByTestId('cr-cashout-globale-live-solo-bot').textContent)
            .toBe('solo ordini dei bot: gli ordini fatti dal sito o dall\'app Betfair non sono inclusi');
        const marchio = screen.getByTestId('cr-cashout-globale-live-marchio');
        expect(marchio.getAttribute('data-fonte')).toBe('pagina');
        // MarchioSoldi: «STIMA» + «· <eta'> fa» in due span (eta' del prezzo piu' vecchio, 0,3 s)
        expect(marchio.textContent).toBe('STIMA· 0 s fa');
        const righe = screen.getAllByTestId('cr-cashout-globale-live-gamba');
        expect(righe).toHaveLength(2);
        expect(righe[0].textContent).toContain('punta Under 3.5 Goals 5,00 € @ 2,40');
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba-chiudo').map((e) => e.textContent))
            .toEqual(['chiudo banca 4,69 € @ 2,56', 'chiudo punta 6,82 € @ 1,63']);
        expect(screen.getAllByTestId('cr-cashout-globale-live-gamba-pnl').map((e) => e.textContent))
            .toEqual(['−0,32 €', '−0,50 €']);
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-netto').textContent).toBe('−0,84 €');
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-marchio').getAttribute('data-fonte')).toBe('bot');
        expect(screen.getByTestId('cr-cashout-globale-live-bot-mike-differenza').textContent)
            .toMatch(/^differenza 0,02 € · cause possibili: prezzi letti in istanti diversi .*; il bot chiude la copertura su un altro libro; il bot conta solo le sue gambe$/);
        expect(screen.queryByTestId('cr-cashout-globale-prova')).toBeNull();
    });

    it('manca un prezzo: «NON CALCOLABILE: manca il prezzo di ...» e NESSUNA cifra', () => {
        const r = cashOutPartita(FOLLO, { prezzo: prezzo({ '1.35|11': LIBRO['1.35|11'] }), nowMs: NOW });
        render(<CashOutGlobale risultato={r} />);
        expect(screen.getByTestId('cr-cashout-globale-live-non-calcolabile').textContent)
            .toBe('NON CALCOLABILE: manca il prezzo di Under 4.5 Goals (punta)');
        expect(screen.queryByTestId('cr-cashout-globale-live-netto')).toBeNull();
        // R_C: anche senza cifra si dice che gli ordini fuori dai bot non ci sono
        expect(screen.getByTestId('cr-cashout-globale-live-solo-bot')).toBeTruthy();
    });

    it('gambe PROVA: riga PROVA separata, mai sommata al live', () => {
        const prova: GambaViva = { id: 900, bot: 'safe', modalita: 'paper', marketId: '1.35', selectionId: 11,
            selezione: 'Under 3.5 Goals', lato: 'back', abbinato: 10, prezzoMedio: 2.2, aliquota: 0.05 };
        const r = cashOutPartita([...FOLLO, prova], { prezzo: prezzo(LIBRO), nowMs: NOW });
        render(<CashOutGlobale risultato={r} />);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,82 €');
        expect(screen.getByTestId('cr-cashout-globale-prova-netto').textContent).toBe('−1,41 €');
        expect(screen.getByTestId('cr-cashout-globale-prova-marchio').getAttribute('data-fonte')).toBe('prova');
        expect(screen.getByTestId('cr-cashout-globale-prova').textContent).toContain('Prova (simulato, mai sommato ai soldi veri)');
        // R_C: nel blocco PROVA la riga «solo ordini dei bot» non serve
        expect(screen.queryByTestId('cr-cashout-globale-prova-solo-bot')).toBeNull();
    });

    it('liquidita\' insufficiente: la cifra resta, «e\' il caso migliore»', () => {
        const r = cashOutPartita(FOLLO, { prezzo: prezzo({ ...LIBRO, '1.35|11': { lay: 2.56, laySize: 3 } }), nowMs: NOW });
        render(<CashOutGlobale risultato={r} />);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,82 €');
        expect(screen.getByTestId('cr-cashout-globale-live-caso-migliore').textContent)
            .toBe('liquidita\' insufficiente al miglior prezzo: e\' il caso migliore');
        expect(screen.getByTestId('cr-cashout-globale-live-gamba-liquidita').textContent)
            .toBe('solo 3,00 € al miglior prezzo: caso migliore');
    });

    it('nessuna gamba abbinata di nessun bot: lo dice, senza cifre', () => {
        render(<CashOutGlobale risultato={null} />);
        expect(screen.getByTestId('cr-cashout-globale').textContent)
            .toBe('Cash out della partita: nessuna gamba abbinata di nessun bot su questa partita');
    });
});

// ======================================== montaggio isolato con l'hook
function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { cbs.delete(mid); };
        },
        fonte: () => 'canale' as const,
    };
    const spingi = (mid: string, sid: number, back: number, lay: number) => act(() => {
        const ms = Date.now() - 200;
        cbs.get(mid)?.({
            event_id: '35001', market_id: mid, market_type: 'OVER_UNDER', market_name: 'OU',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [
                { selection_id: sid, name: 'X', ltp: back, tv: 0, back: [[back, 80]], lay: [[lay, 60]],
                    trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ] },
        });
    });
    return { sorgente: () => src as never, spingi, iscritti: () => [...cbs.keys()].sort() };
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

function opsFollo(): OperazionePartita[] {
    const alMs = (marketId: string, selectionId: number, scanner: { back: number; lay: number }): OperazionePartita['chiusura'] => ({
        lato: 'lay', prezzo: null, abbinabile: null, bloccabile: null,
        alMs: { win: 0, lose: 0, marketId, selectionId, sport: 'calcio', istanteScannerMs: Date.now() - 4300,
            scanner: { back: scanner.back, backSize: 50, lay: scanner.lay, laySize: 50 }, aliquota: 0.05 },
    });
    return [
        op({ id: 5085, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.35', selectionId: 11,
            ordine: { status: 'open', side: 'back', price: 2.4, size: 5, size_requested: 5, size_matched: 5,
                size_remaining: 0, avg_price_matched: 2.4, betfair_updated_at: null, meta: null },
            chiusura: alMs('1.35', 11, { back: 2.46, lay: 2.56 }) }),
        op({ id: 5094, bot: 'mike', selezione: 'Under 4.5 Goals', lato: 'lay', marketId: '1.45', selectionId: 21,
            ordine: { status: 'open', side: 'lay', price: 1.76, size: 6.32, size_requested: 6.32, size_matched: 6.32,
                size_remaining: 0, avg_price_matched: 1.76, betfair_updated_at: null, meta: null },
            chiusura: alMs('1.45', 21, { back: 1.63, lay: 1.68 }) }),
    ];
}

describe('useCashOutPartita: prezzi al ms, ripiego dichiarato, nessuna sottoscrizione a vuoto', () => {
    it('una sottoscrizione per mercato; senza ladder il prezzo dello scanner, poi il ladder al tick', () => {
        const f = sorgenteFinta();
        const ops = opsFollo();
        const { result } = renderHook(() => useCashOutPartita({ operazioni: ops, sorgente: f.sorgente, sport: 'calcio' }));
        expect(f.iscritti()).toEqual(['1.35', '1.45']);
        // ripiego dello scanner (stessi prezzi): -0,82, fonte scanner dichiarata
        expect(result.current?.live.netto).toBe(-0.82);
        expect(result.current?.live.gambe.map((p) => p.fontePrezzo)).toEqual(['scanner', 'scanner']);
        // il ladder al ms: banca Under 3,5 a 2,50 -> 12/2,50 = 4,80; 4,80 x 1,50 = 7,20 -> -0,20
        f.spingi('1.35', 11, 2.44, 2.5);
        expect(result.current?.live.gambe[0]).toMatchObject({ fontePrezzo: 'canale', importoChiusura: 4.8, pnl: -0.2 });
        expect(result.current?.live.netto).toBe(-0.7);
    });
    it('partita senza gambe: null e NESSUNA sottoscrizione', () => {
        const f = sorgenteFinta();
        const { result } = renderHook(() => useCashOutPartita({ operazioni: [], sorgente: f.sorgente, sport: 'calcio' }));
        expect(result.current).toBeNull();
        expect(f.iscritti()).toEqual([]);
    });
    it('montaggio: hook + riquadro, la cifra segue il tick', () => {
        const f = sorgenteFinta();
        const ops = opsFollo();
        function Riquadro() {
            const r = useCashOutPartita({ operazioni: ops, sorgente: f.sorgente, sport: 'calcio' });
            return <CashOutGlobale risultato={r} />;
        }
        render(<Riquadro />);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,82 €');
        f.spingi('1.35', 11, 2.44, 2.5);
        expect(screen.getByTestId('cr-cashout-globale-live-netto').textContent).toBe('−0,70 €');
    });
});
