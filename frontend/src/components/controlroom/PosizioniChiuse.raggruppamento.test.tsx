// ============================================================================
// PosizioniChiuse.raggruppamento.test.tsx - LA SCHEDA DEL 24/09.
//
// "Posizioni chiuse / storico: e' LENTISSIMO nel caricamento, i dati sono
// mischiati per giornata, sono confusionari e il trader non capisce
// assolutamente nulla. IL TRADER DEVE FIDARSI DI QUELLO CHE VEDE" (utente).
//
// Si prova a video: giornata di regolamento -> bot -> partita -> ciclo; paper
// e live mai insieme; la fonte accanto a ogni cifra; orfane e ripiego B13
// dichiarati; giornate passate lette a richiesta; controprova con la barra;
// apertura con 500 operazioni sotto il secondo.
// I finti hanno le chiavi delle tabelle vere; le posizioni le costruisce la
// funzione VERA.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PosizioniChiuse, type LeggiGiornata } from './PosizioniChiuse';
import { rigaDaOrdineTennis, type TradeChiudibile } from '@/lib/posizioniChiuse';
import type { ChiuseGiornata } from '@/lib/chiuseGiornata';
import type { ComposizioneObiettivo } from '@/lib/composizioneObiettivo';
import { isBotTennis, type Bot } from '@/lib/controlRoom';
import type { TennisBotOrderRow } from '@/lib/tennis';
import { MINUS } from '@/lib/format';

const OGGI = '2026-09-24';
const IERI = '2026-09-23';

function t(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'safe', event_id: 'E1', event_name: 'Inter - Milan', sport: 'calcio',
        mode: 'live', status: 'won', pnl: 1, side: 'back', price: 2, size: 5,
        selection_name: 'Inter', market_type: 'MATCH_ODDS', placed_at: `${OGGI}T08:00:00.000Z`,
        settled_at: `${OGGI}T10:00:00.000Z`, closes_trade_id: null, strategy: 'base',
        bet_id: `B${over.id}`, origin: 'auto',
        size_requested: 5, size_matched: 5, size_remaining: 0, avg_price_matched: 2, meta: null,
        ...over,
    };
}

function ordineTennis(over: Partial<TennisBotOrderRow> & { id: number }): TennisBotOrderRow {
    return {
        bet_id: `T${over.id}`, client_order_ref: `awtq${over.id}`, request_id: over.id,
        mode: 'live', source: 'tennis_scalper', event_id: 'T1', market_id: '1.234', selection_id: 111,
        handicap: 0, side: 'back', order_type: 'LIMIT', price: 1.8, size: 2,
        size_matched: 2, size_remaining: 0, size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        average_price_matched: 1.8, status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
        placed_at: `${OGGI}T09:00:00.000Z`, matched_at: `${OGGI}T09:00:01.000Z`, updated_at: `${OGGI}T11:00:00.000Z`,
        pnl: 1.6, commission: 0.08, settled_at: `${OGGI}T11:00:00.000Z`,
        pnl_betfair: null, pnl_betfair_settled_at: null,
        ...over,
    };
}

function giornata(giorno: string, modo: 'live' | 'paper', righe: TradeChiudibile[] = [], avvisi: string[] = []): ChiuseGiornata {
    return { giorno, modo, righe, fonte: avvisi.length ? 'ripiego' : 'rpc', avvisi, lettoAlle: 0 };
}

const vuota: LeggiGiornata = async (g, m) => giornata(g, m);

function monta(righe: TradeChiudibile[], opz: {
    leggi?: LeggiGiornata; barra?: ComposizioneObiettivo | null; sport?: 'calcio' | 'tennis' | null;
} = {}) {
    return render(
        <MemoryRouter>
            <PosizioniChiuse righe={righe} sport={opz.sport ?? null} giorno={OGGI}
                barra={opz.barra ?? null} leggiGiornata={opz.leggi ?? vuota} />
        </MemoryRouter>,
    );
}

describe('una regola: giornata -> bot -> partita -> ciclo', () => {
    const righe = [
        t({ __bot: 'omega', id: 1, pnl: 3, runner_name: '1 - 0', selection_name: null, phase: 'ft_cs', market_type: null }),
        t({ __bot: 'omega', id: 2, pnl: -2, status: 'lost', closes_trade_id: 1, side: 'lay' }),
        t({ id: 1, pnl: 0.5 }),
        t({ id: 3, pnl: -0.2, status: 'lost', event_id: 'E2', event_name: 'Roma - Lazio' }),
        t({ id: 4, pnl: 0.3, sport: 'tennis', event_id: 'T9', event_name: 'Sinner - Alcaraz' }),
    ];

    it('un blocco per bot (Safe diviso per sport), con il totale del bot', () => {
        monta(righe);
        expect(screen.getByTestId('cr-chiuse-bot-omega')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-bot-safe_calcio')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-bot-safe_tennis')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-bot-totale-omega')).toHaveTextContent('+1,00');
        expect(screen.getByTestId('cr-chiuse-bot-totale-safe_calcio')).toHaveTextContent('+0,30');
    });

    it('dentro il bot, una riga per partita; dentro la partita, i cicli', () => {
        monta(righe);
        const safe = screen.getByTestId('cr-chiuse-bot-safe_calcio');
        const partite = within(safe).getAllByTestId('cr-chiuse-partita');
        expect(partite.map((p) => p.dataset.eventId).sort()).toEqual(['E1', 'E2']);
        // il green-up di Omega e' UNA operazione, non due righe
        const omega = screen.getByTestId('cr-chiuse-bot-omega');
        expect(within(omega).getAllByTestId('cr-chiusa')).toHaveLength(1);
    });

    it('ogni ciclo dice bot, mercato, selezione, lato, esito, netto e fonte', () => {
        monta(righe);
        const omega = within(screen.getByTestId('cr-chiuse-bot-omega')).getByTestId('cr-chiusa');
        expect(omega).toHaveTextContent('Omega');
        expect(omega).toHaveTextContent('Risultato esatto');
        expect(omega).toHaveTextContent('1 - 0');
        expect(omega).toHaveTextContent('punta');
        expect(omega).toHaveTextContent('vinta');
        expect(within(omega).getByTestId('cr-chiusa-pnl-1')).toHaveTextContent('+1,00');
        expect(within(omega).getByTestId('cr-chiusa-fonte-1').dataset.fonte).toBe('stimato');
    });

    it('il totale in testa e\' la somma dei bot', () => {
        monta(righe);
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,60');
    });
});

describe('paper e live: mai insieme', () => {
    const righe = [t({ id: 1, pnl: 1 }), t({ id: 2, mode: 'paper', pnl: 50, event_id: 'P1', event_name: 'Finta' })];

    it('non esiste piu\' il filtro "entrambi"', () => {
        monta(righe);
        expect(screen.queryByTestId('cr-f-modo-tutte')).toBeNull();
    });

    it('di serie soldi veri; "prova" mostra solo la simulazione', () => {
        monta(righe);
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00');
        expect(screen.queryByText('Finta')).toBeNull();
        fireEvent.click(screen.getByTestId('cr-f-modo-paper'));
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+50,00');
        expect(screen.getByTestId('cr-chiuse-totale-fonte').dataset.fonte).toBe('paper');
        expect(screen.queryByText('Inter - Milan')).toBeNull();
    });

    it('la lettura della giornata chiede UNA modalita\' alla volta', async () => {
        const leggi = vi.fn(vuota);
        monta(righe, { leggi });
        await waitFor(() => expect(leggi).toHaveBeenCalledWith(OGGI, 'live', false));
        fireEvent.click(screen.getByTestId('cr-f-modo-paper'));
        await waitFor(() => expect(leggi).toHaveBeenCalledWith(OGGI, 'paper', false));
    });
});

describe('la fonte di ogni cifra: Betfair / stimato', () => {
    const righe = [
        t({ id: 1, pnl: 3, pnl_betfair: 2.85, pnl_betfair_settled_at: `${OGGI}T10:05:00.000Z` }),
        t({ id: 2, pnl: -0.4, status: 'lost', event_id: 'E2', event_name: 'Roma - Lazio' }),
    ];

    it('la testata separa il regolato da Betfair dallo stimato', () => {
        monta(righe);
        expect(screen.getByTestId('cr-chiuse-reale')).toHaveTextContent('+2,85');
        expect(screen.getByTestId('cr-chiuse-stimato')).toHaveTextContent(`${MINUS}0,40`);
        expect(screen.getByTestId('cr-chiuse-totale-fonte').dataset.fonte).toBe('misto');
        expect(screen.getByTestId('cr-chiusa-fonte-1').dataset.fonte).toBe('betfair');
        expect(screen.getByTestId('cr-chiusa-fonte-2').dataset.fonte).toBe('stimato');
    });

    it('"solo Betfair" lascia solo cio\' che Betfair ha regolato', () => {
        monta(righe);
        fireEvent.click(screen.getByTestId('cr-f-fonte-betfair'));
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+2,85');
        expect(screen.queryByText('Roma - Lazio')).toBeNull();
    });
});

describe('orfane e ripiego B13: dichiarati, mai nascosti', () => {
    it('una chiusura senza apertura lo dice sulla riga e in testata', () => {
        monta([t({ id: 9, pnl: -2, status: 'lost', closes_trade_id: 8 })]);
        expect(screen.getByTestId('cr-chiusa-orfana-9')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-nota-orfane')).toHaveTextContent('1 chiusura');
    });

    it('la giornata letta dal database ricuce l\'orfana: UN ciclo intero', async () => {
        const chiusura = t({ id: 9, pnl: -2, status: 'lost', closes_trade_id: 8, side: 'lay' });
        const leggi: LeggiGiornata = async (g, m) => giornata(g, m, [t({ id: 8, pnl: 3 }), chiusura]);
        monta([chiusura], { leggi });
        await waitFor(() => expect(screen.queryByTestId('cr-chiusa-orfana-9')).toBeNull());
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00');
        expect(screen.queryByTestId('cr-chiuse-nota-orfane')).toBeNull();
    });

    it('bot tennis: ingresso e uscita in UN gruppo a ripiego, dichiarato', () => {
        const eBot = (b: string) => isBotTennis(b as Bot);
        const righe = [
            ordineTennis({ id: 10, side: 'back', pnl: 1.6, commission: 0.08 }),
            ordineTennis({ id: 11, side: 'lay', pnl: -1.2, commission: 0 }),
        ].map((o) => rigaDaOrdineTennis(o, 'Sinner - Alcaraz', eBot) as TradeChiudibile);
        monta(righe);
        const blocco = screen.getByTestId('cr-chiuse-bot-tennis_scalper');
        expect(within(blocco).getAllByTestId('cr-chiusa')).toHaveLength(1);
        expect(screen.getByTestId('cr-chiusa-ripiego-10')).toHaveTextContent('B13');
        expect(screen.getByTestId('cr-chiuse-nota-ripiego')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-bot-totale-tennis_scalper')).toHaveTextContent('+0,32');
    });
});

describe('giornata di REGOLAMENTO, scelta dal trader, letta a richiesta', () => {
    it('aperta ieri sera e regolata oggi: e\' di OGGI', () => {
        monta([t({ id: 1, pnl: 2, placed_at: `${IERI}T21:30:00.000Z`, settled_at: `${OGGI}T06:00:00.000Z` })]);
        expect(screen.getByTestId('cr-chiuse-giornata')).toHaveTextContent('Oggi');
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+2,00');
    });

    it('il giorno prima si legge dal database e si mostra', async () => {
        const leggi = vi.fn<LeggiGiornata>(async (g, m) => (g === IERI
            ? giornata(g, m, [t({ id: 70, pnl: 4, event_name: 'Partita di ieri', settled_at: `${IERI}T15:00:00.000Z` })])
            : giornata(g, m)));
        monta([t({ id: 1, pnl: 1 })], { leggi });
        fireEvent.click(screen.getByTestId('cr-f-giorno-prima'));
        await waitFor(() => expect(screen.getByText('Partita di ieri')).toBeInTheDocument());
        expect(leggi).toHaveBeenCalledWith(IERI, 'live', false);
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+4,00');
        expect(screen.getByTestId('cr-chiuse-giornata')).not.toHaveTextContent('Oggi');
        // e si torna a oggi
        fireEvent.click(screen.getByTestId('cr-f-giorno-oggi'));
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00');
    });

    it('non si va oltre oggi', () => {
        monta([t({ id: 1 })]);
        expect(screen.getByTestId('cr-f-giorno-dopo')).toBeDisabled();
    });

    it('una lettura di ripiego o caduta si DICE', async () => {
        const leggi: LeggiGiornata = async (g, m) => giornata(g, m, [], ['Lettura di ripiego: bot tennis assenti']);
        monta([t({ id: 1 })], { leggi });
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-lettura')).toHaveTextContent('ripiego'));
        const caduta: LeggiGiornata = async () => { throw new Error('rete giu'); };
        monta([t({ id: 1 })], { leggi: caduta });
        await waitFor(() => expect(screen.getAllByTestId('cr-chiuse-lettura').some((n) => n.dataset.stato === 'errore')).toBe(true));
    });
});

describe('controprova con la barra di giornata', () => {
    const barra = (omega: number | null, safe: number | null): ComposizioneObiettivo => ({
        righe: [
            { chiave: 'omega', etichetta: 'Omega', valore: omega },
            { chiave: 'safe_calcio', etichetta: 'Safe calcio', valore: safe },
            { chiave: 'manuale_sito', etichetta: 'Manuale sito', valore: 99 },
        ],
        totale: null, provaPaper: null,
    });
    const righe = [t({ __bot: 'omega', id: 1, pnl: 1 }), t({ id: 2, pnl: 0.5, event_id: 'E2' })];

    it('coincide: lo dice', () => {
        monta(righe, { barra: barra(1, 0.5) });
        expect(screen.getByTestId('cr-chiuse-controprova').dataset.coincide).toBe('1');
    });

    it('non coincide: mostra la differenza (il manuale del sito non entra)', () => {
        monta(righe, { barra: barra(1, 0.2) });
        expect(screen.getByTestId('cr-chiuse-controprova').dataset.coincide).toBe('0');
        expect(screen.getByTestId('cr-chiuse-controprova-diff')).toHaveTextContent('+0,30');
    });

    it('con un filtro attivo non si confronta (non sarebbe lo stesso insieme)', () => {
        monta(righe, { barra: barra(1, 0.5) });
        fireEvent.click(screen.getByTestId('cr-f-bot-omega'));
        expect(screen.queryByTestId('cr-chiuse-controprova')).toBeNull();
    });
});

describe('VELOCITA\': 500 operazioni, apertura sotto il secondo', () => {
    function molte(n: number): TradeChiudibile[] {
        const out: TradeChiudibile[] = [];
        let id = 1;
        const bots: Bot[] = ['omega', 'safe', 'mike'];
        for (let i = 0; i < n; i++) {
            const bot = bots[i % 3];
            const h = String(6 + (i % 14)).padStart(2, '0');
            const a = id++;
            out.push(t({ __bot: bot, id: a, event_id: `E${i % 60}`, event_name: `Partita ${i % 60}`,
                pnl: 1.1, side: 'lay', placed_at: `${OGGI}T${h}:00:00.000Z`, settled_at: `${OGGI}T${h}:50:00.000Z`,
                pnl_betfair: i % 2 ? 1.05 : null }));
            const c = id++;
            out.push(t({ __bot: bot, id: c, event_id: `E${i % 60}`, event_name: `Partita ${i % 60}`,
                status: 'lost', pnl: -0.9, side: 'back', closes_trade_id: a,
                placed_at: `${OGGI}T${h}:30:00.000Z`, settled_at: `${OGGI}T${h}:50:00.000Z` }));
        }
        return out;
    }

    it('500 cicli (1000 righe): montata in meno di 1 s, cambio filtro in meno di 1 s', () => {
        const righe = molte(500);
        const t0 = performance.now();
        monta(righe);
        const apertura = performance.now() - t0;
        expect(screen.getByTestId('cr-chiuse-giornata')).toHaveTextContent('500');
        const t1 = performance.now();
        fireEvent.click(screen.getByTestId('cr-f-esito-vinta'));
        const filtro = performance.now() - t1;
        expect(apertura, `apertura ${apertura.toFixed(0)} ms`).toBeLessThan(1000);
        expect(filtro, `filtro ${filtro.toFixed(0)} ms`).toBeLessThan(1000);
    });
});
