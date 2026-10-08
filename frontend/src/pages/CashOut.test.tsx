// ============================================================================
// CashOut.test.tsx - 08/10 (cantiere W1): test di PAGINA del «Cash Out».
//
// Il modello di vista (`useControlRoom`) e' mockato come in `ControlRoom.test.
// tsx`: i finti portano le chiavi e i tipi VERI (`PartitaGiornata`,
// `PosizioneAperta`, `OperazionePartita`, `MikeEvent`, `OrdineContoFuoriBot`
// via `raggruppaOrdiniConto`). Qui si collauda quello che il trader LEGGE e i
// comandi che partono: una scatola per partita, le due sezioni, i filtri, il
// passaggio pre -> in gioco senza sparire, la fase delle fuori programma, il
// testo dei pulsanti dei bot e il comando di oggi, gli ordini fuori dai bot col
// comando del contratto W2, la doppia conferma live e il clic unico in prova,
// il ladder pop-out, il punto di ritorno.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

vi.mock('@/components/controlroom/useControlRoom', () => ({ useControlRoom: vi.fn() }));
// I PREZZI AL MS: la sorgente del ladder (`sorgenteLadderAlMs`) e' sostituita da
// una finta che risponde con le righe `LiveLadderRow` (chiavi vere, `lib/live.ts`)
// della tabella `PREZZI`: vuota = nessun prezzo (canale spento, come nei test).
const PREZZI = new Map<string, { sid: number; back: number; lay: number }[]>();
vi.mock('@/lib/localTransport', async (orig) => ({
    ...(await orig() as object),
    sorgenteLadderAlMs: () => ({
        fetch: async () => null,
        fonte: () => 'canale' as const,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            const sel = PREZZI.get(mid);
            if (sel) {
                const ms = Date.now() - 200;
                cb({
                    event_id: 'E', market_id: mid, market_type: null, market_name: null, status: 'OPEN',
                    updated_at: new Date(ms).toISOString(),
                    ladder: { updated_ms: ms, selections: sel.map((s) => ({
                        selection_id: s.sid, name: 'X', ltp: s.back, tv: 0, back: [[s.back, 100]], lay: [[s.lay, 100]],
                        trd: [], wom: { back_pct: 50, lay_pct: 50 },
                    })) },
                });
            }
            return () => {};
        },
    }),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    sendGreenupFuoriBot: vi.fn(async () => ({ ok: true, action: 'greenup', mode: 'live' })),
}));

import CashOut from './CashOut';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import { sendGreenupFuoriBot } from '@/lib/liveOrders';
import { raggruppaOrdiniConto, ORDINI_CONTO_NON_LETTI } from '@/components/controlroom/ordiniConto';
import type { PartitaGiornata, GruppoCampionato } from '@/lib/controlRoom';
import type { MikeEvent } from '@/lib/mike';
import type { OperazionePartita, PosizioneAperta } from '@/components/controlroom/useControlRoom';
import type { OrdineContoFuoriBot } from '@/lib/liveOrders';

const mVm = vi.mocked(useControlRoom);
const mGreen = vi.mocked(sendGreenupFuoriBot);
const ORA = Date.parse('2026-10-08T15:00:00Z');

function partita(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'E1', sport: 'calcio', nome: 'Inter v Milan', campionato: 'Serie A',
        koMs: ORA - 60 * 60_000, stato: 'live',
        minuto: 67, punteggio: '2-1', controlloDisponibile: true,
        etaFeedS: 2, freschezza: 'fresca', latenzaQuoteS: 1, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        media: { video: true, viz: true }, marketId: '1.MO',
        soldi: null, target: null, avanzamento: null, extra: null,
        ...over,
    };
}

function gruppo(partite: PartitaGiornata[]): GruppoCampionato[] {
    return [{ campionato: 'Serie A', primoKoMs: partite[0]?.koMs ?? null, partite }];
}

const ordine = (side: 'back' | 'lay', price: number, size: number) => ({
    status: 'open', side, price, size, size_requested: size, size_matched: size, size_remaining: 0,
    avg_price_matched: price, betfair_updated_at: null, meta: null,
});

function op(o: Partial<OperazionePartita> & Pick<OperazionePartita, 'bot' | 'id'>): OperazionePartita {
    return {
        selezione: 'Under 3.5 Goals', lato: 'back', prezzo: 2, size: 5, stato: 'open', pnl: null,
        modalita: 'live', at: '2026-10-08T14:04:00Z', quale: null, ordine: ordine('back', 2, 5),
        dettaglio: null, marketId: '1.OU35', selectionId: 35, liability: null, vivo: null, etaQuoteS: null,
        chiusura: null, chiusureOrdini: [], eventId: 'E1', chiudeId: null,
        ...o,
    };
}

function pos(o: Partial<PosizioneAperta> & Pick<PosizioneAperta, 'bot' | 'id' | 'eventId'>): PosizioneAperta {
    return {
        partita: 'Inter v Milan', selezione: 'Under 3.5 Goals', lato: 'back', prezzo: 2, size: 5, liability: 5,
        modalita: 'live', piazzataAt: '2026-10-08T14:04:00Z', chiusura: null, ordine: ordine('back', 2, 5),
        dettaglio: null, vivo: null,
        ...o,
    };
}

function mike(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Inter v Milan', competition: 'Serie A', league_id: null,
        ko_at: null, mode: 'live', markets: {}, state: 'LIVE_COVERED', cycle_no: 0, entry_price_initial: null,
        dossier: null, live: null, positions: [], ctx: null, skipped: false, settled_pnl: null,
        updated_at: '2026-10-08T14:59:00Z',
        ...over,
    };
}

const SITO: OrdineContoFuoriBot = {
    bet_id: '351001', market_id: '1.OU25', selection_id: 47973, event_id: 'E1',
    event_name: 'Inter v Milan', market_name: 'Over/Under 2.5 Goals', selection_name: 'Under 2.5 Goals',
    side: 'LAY', price_matched: 1.6, size_matched: 8, size_remaining: 0,
    status: 'EXECUTION_COMPLETE', source: 'account', placed_at: '2026-10-08T14:31:02Z',
};

/** Mike con TRE gambe live sulla stessa partita (E1, in gioco). */
const MIKE3 = {
    posizioni: [
        pos({ bot: 'mike', id: 1, eventId: 'E1' }),
        pos({ bot: 'mike', id: 2, eventId: 'E1', selezione: 'Under 4.5 Goals', lato: 'lay' }),
        pos({ bot: 'mike', id: 3, eventId: 'E1', selezione: 'Inter' }),
    ],
    operazioni: [
        op({ bot: 'mike', id: 1, marketId: '1.OU35', selectionId: 35 }),
        op({ bot: 'mike', id: 2, selezione: 'Under 4.5 Goals', lato: 'lay', marketId: '1.OU45', selectionId: 45, ordine: ordine('lay', 1.3, 15) }),
        op({ bot: 'mike', id: 3, selezione: 'Inter', marketId: '1.MO', selectionId: 1, ordine: ordine('back', 2.1, 10) }),
    ],
};

function vm(over: Partial<ReturnType<typeof useControlRoom>> = {}): ReturnType<typeof useControlRoom> {
    return {
        caricamento: false, errore: null, nowMs: ORA,
        giornata: gruppo([partita()]),
        posizioni: MIKE3.posizioni,
        operazioni: new Map([['E1', MIKE3.operazioni]]),
        mikeEventi: new Map(),
        ordiniConto: ORDINI_CONTO_NON_LETTI,
        registrazioni: new Set<string>(),
        runner: null, runnerTennis: null,
        bots: [{ bot: 'safe', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 1, freschezzaPush: 'fresca', varianti: null }],
        chiudi: vi.fn(async () => {}),
        statoChiusuraRiga: () => null,
        statoChiusura: () => ({ chiusa: false, fonte: null, marcatore: null }),
        cashOutEvento: vi.fn(async () => {}), riprendiEvento: vi.fn(async () => {}),
        ...over,
    } as ReturnType<typeof useControlRoom>;
}

function Dove() {
    const l = useLocation();
    return <div data-testid="dove">{l.pathname + l.search}</div>;
}

function mostra() {
    return render(<HelmetProvider><MemoryRouter><CashOut /></MemoryRouter></HelmetProvider>);
}

beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    PREZZI.clear();
});

describe('dati: una sola chiamata, nessuna lettura nuova', () => {
    it('la pagina chiama useControlRoom UNA volta; scatole e regole non leggono niente', () => {
        // il codice, senza i commenti (che citano il hook per spiegarlo)
        const leggi = (f: string) => readFileSync(join(__dirname, f), 'utf-8')
            .replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
        expect(leggi('CashOut.tsx').match(/useControlRoom\(/g)).toHaveLength(1);
        for (const f of [
            'CashOut.tsx',
            '../components/controlroom/aperte/ScatolaCashOut.tsx',
            '../components/controlroom/aperte/cashOutPagina.ts',
            '../components/controlroom/aperte/PosizioniAperte.tsx',
        ]) {
            const t = leggi(f);
            if (f !== 'CashOut.tsx') expect(t.match(/useControlRoom\(/g), f).toBeNull();
            expect(t, f).not.toMatch(/integrations\/supabase|supabase\.(rpc|from)|\bfetch[A-Z]\w*\(|subscribe[A-Z]\w*\(/);
        }
    });
});

describe('una scatola per partita', () => {
    it('Mike con 3 gambe = UNA scatola, 3 righe, ogni pulsante dice «tutte le 3 gambe di Mike»', () => {
        mVm.mockReturnValue(vm());
        mostra();
        const box = screen.getByTestId('co-scatola-E1');
        expect(within(box).getAllByTestId('co-gamba')).toHaveLength(3);
        const bottoni = within(box).getAllByTestId('cr-op-chiudi');
        expect(bottoni).toHaveLength(3);
        for (const b of bottoni) expect(b.textContent).toBe('Cash out Mike');
        for (const a of within(box).getAllByTestId('cr-op-chiudi-ambito')) expect(a.textContent).toBe('tutte le 3 gambe di Mike');
        expect(screen.getAllByTestId(/^co-scatola-/)).toHaveLength(1);
    });

    it('il pulsante di Mike manda il comando di OGGI (vm.chiudi con la riga di Mike) dopo la conferma live', async () => {
        const v = vm();
        mVm.mockReturnValue(v);
        mostra();
        const box = screen.getByTestId('co-scatola-E1');
        fireEvent.click(within(box).getAllByTestId('cr-op-chiudi')[0]);
        expect(v.chiudi).not.toHaveBeenCalled();
        const conferma = within(box).getByTestId('cr-op-chiudi-conferma');
        expect(conferma).toBeDisabled();
        await waitFor(() => expect(within(box).getByTestId('cr-op-chiudi-conferma')).not.toBeDisabled(), { timeout: 1500 });
        fireEvent.click(within(box).getByTestId('cr-op-chiudi-conferma'));
        expect(v.chiudi).toHaveBeenCalledTimes(1);
        expect(v.chiudi).toHaveBeenCalledWith(expect.objectContaining({ bot: 'mike', id: 1, eventId: 'E1', modalita: 'live' }));
    });

    it('Omega e Safe chiudono la sola riga; in PROVA basta un clic', () => {
        const v = vm({
            posizioni: [pos({ bot: 'omega', id: 7, eventId: 'E1', modalita: 'paper' })],
            operazioni: new Map([['E1', [op({ bot: 'omega', id: 7, modalita: 'paper' })]]]),
        });
        mVm.mockReturnValue(v);
        mostra();
        const b = screen.getByTestId('cr-op-chiudi');
        expect(b.textContent).toBe('Cash out');
        expect(screen.getByTestId('cr-op-chiudi-ambito').textContent).toBe('solo questa gamba');
        fireEvent.click(b);
        expect(v.chiudi).toHaveBeenCalledWith(expect.objectContaining({ bot: 'omega', id: 7, modalita: 'paper' }));
    });
});

describe('sezioni, filtri e fasi', () => {
    function dueEventi(statoE2: PartitaGiornata['stato'] = 'pre', mercatoE2: string | null = 'OPEN') {
        return vm({
            giornata: gruppo([
                partita(),
                partita({ event_id: 'E2', sport: 'tennis', nome: 'Sinner v Alcaraz', stato: statoE2, koMs: ORA + 30 * 60_000, statoMercato: mercatoE2 }),
            ]),
            posizioni: [...MIKE3.posizioni, pos({ bot: 'tennis_pro', id: 9, eventId: 'E2', partita: 'Sinner v Alcaraz', selezione: null })],
            operazioni: new Map([
                ['E1', MIKE3.operazioni],
                ['E2', [op({ bot: 'tennis_pro', id: 9, eventId: 'E2', selezione: null, marketId: '1.TMO', selectionId: 11 })]],
            ]),
        });
    }

    it('In gioco e Pre-match; i filtri sport e fase scelgono e tolgono come le tessere della Control Room', () => {
        mVm.mockReturnValue(dueEventi());
        mostra();
        expect(within(screen.getByTestId('co-sezione-gioco')).getByTestId('co-scatola-E1')).toBeTruthy();
        expect(within(screen.getByTestId('co-sezione-pre')).getByTestId('co-scatola-E2')).toBeTruthy();
        // fase «Live»: solo la sezione in gioco
        fireEvent.click(screen.getByTestId('co-filtro-fase-live'));
        expect(screen.getByTestId('co-filtro-fase-live').getAttribute('aria-pressed')).toBe('true');
        expect(screen.queryByTestId('co-sezione-pre')).toBeNull();
        expect(screen.getByTestId('co-scatola-E1')).toBeTruthy();
        // secondo clic sullo stesso: tolto, si vede tutto
        fireEvent.click(screen.getByTestId('co-filtro-fase-live'));
        expect(screen.getByTestId('co-filtro-fase-live').getAttribute('aria-pressed')).toBe('false');
        expect(screen.getByTestId('co-scatola-E2')).toBeTruthy();
        // sport «Tennis»: sparisce il calcio
        fireEvent.click(screen.getByTestId('co-filtro-sport-tennis'));
        expect(screen.queryByTestId('co-scatola-E1')).toBeNull();
        expect(screen.getByTestId('co-scatola-E2')).toBeTruthy();
        // un altro sport sostituisce, non somma
        fireEvent.click(screen.getByTestId('co-filtro-sport-calcio'));
        expect(screen.getByTestId('co-scatola-E1')).toBeTruthy();
        expect(screen.queryByTestId('co-scatola-E2')).toBeNull();
    });

    it('passaggio pre -> in gioco: la STESSA scatola cambia sezione da sola, non sparisce', () => {
        mVm.mockReturnValue(dueEventi('pre'));
        const r = mostra();
        expect(within(screen.getByTestId('co-sezione-pre')).getByTestId('co-scatola-E2')).toBeTruthy();
        mVm.mockReturnValue(dueEventi('live'));
        r.rerender(<HelmetProvider><MemoryRouter><CashOut /></MemoryRouter></HelmetProvider>);
        expect(within(screen.getByTestId('co-sezione-gioco')).getByTestId('co-scatola-E2')).toBeTruthy();
        expect(within(screen.getByTestId('co-sezione-pre')).queryByTestId('co-scatola-E2')).toBeNull();
    });

    it('fischio passato ma non in gioco (mercato non CLOSED): resta in Pre-match e lo dice', () => {
        mVm.mockReturnValue(dueEventi('chiusa', 'OPEN'));
        mostra();
        const box = within(screen.getByTestId('co-sezione-pre')).getByTestId('co-scatola-E2');
        expect(box.textContent).toContain('non in gioco · orario passato');
        expect(box.getAttribute('data-fase')).toBe('pre');
    });

    it('fuori programma: fase dall\'orario di Mike; senza orario resta in Pre-match «orario non dichiarato»', () => {
        mVm.mockReturnValue(vm({
            giornata: [],
            posizioni: [
                pos({ bot: 'mike', id: 1, eventId: 'F1', partita: 'Juventus v Torino' }),
                pos({ bot: 'safe', id: 4, eventId: 'F2', partita: 'Atalanta v Lazio' }),
            ],
            operazioni: new Map([
                ['F1', [op({ bot: 'mike', id: 1, eventId: 'F1' })]],
                ['F2', [op({ bot: 'safe', id: 4, eventId: 'F2' })]],
            ]),
            mikeEventi: new Map([['F1', mike({ event_id: 'F1', ko_at: new Date(ORA + 40 * 60_000).toISOString() })]]),
        }));
        mostra();
        const pre = screen.getByTestId('co-sezione-pre');
        const f1 = within(pre).getByTestId('co-scatola-F1');
        expect(within(f1).getByTestId('co-fase-fuori-programma').getAttribute('data-nota')).toBe('fischio-fra');
        expect(within(f1).getByTestId('co-fase-fuori-programma').textContent).toMatch(/fra 40 min/);
        const f2 = within(pre).getByTestId('co-scatola-F2');
        expect(within(f2).getByTestId('co-fase-fuori-programma').textContent).toBe('orario non dichiarato');
    });

    it('fuori programma con Mike IN GIOCO: sezione In gioco', () => {
        mVm.mockReturnValue(vm({
            giornata: [],
            posizioni: [pos({ bot: 'mike', id: 1, eventId: 'F1', partita: 'Juventus v Torino' })],
            operazioni: new Map([['F1', [op({ bot: 'mike', id: 1, eventId: 'F1' })]]]),
            mikeEventi: new Map([['F1', mike({ event_id: 'F1', ko_at: new Date(ORA - 600_000).toISOString(), live: { inplay: true } })]]),
        }));
        mostra();
        expect(within(screen.getByTestId('co-sezione-gioco')).getByTestId('co-scatola-F1')).toBeTruthy();
    });
});

describe('ordini fuori dai bot (sito, app)', () => {
    it('una partita con SOLI ordini del sito compare; riga «Sito»; il Cash out chiede la doppia conferma e manda il comando del contratto', async () => {
        mVm.mockReturnValue(vm({
            giornata: gruppo([partita({ event_id: 'S1', nome: 'Arsenal v Chelsea' })]),
            posizioni: [], operazioni: new Map(),
            ordiniConto: raggruppaOrdiniConto([{ ...SITO, event_id: 'S1' }, { ...SITO, bet_id: '351002', source: 'runner', side: 'BACK', price_matched: 1.7, size_matched: 4 }], '2026-10-08T14:59:50Z'),
        }));
        mostra();
        const box = screen.getByTestId('co-scatola-S1');
        const riga = within(box).getByTestId('co-fuori-bot');
        expect(within(riga).getByTestId('co-fuori-bot-origine').textContent).toBe('Sito');
        expect(within(riga).getByTestId('co-fuori-bot-ordine').textContent).toMatch(/LAY 8,00 € @ 1,60/);
        // il prezzo non c'e' (nessun ladder nel test): niente cifra, pulsante spento col motivo
        expect(within(riga).getByTestId('co-fuori-bot-cashout')).toBeDisabled();
        expect(mGreen).not.toHaveBeenCalled();
    });

    it('con il prezzo: «se chiudo ora» con la stessa matematica; un clic arma, la conferma (inerte) manda sendGreenupFuoriBot per QUELLA selezione', async () => {
        PREZZI.set('1.OU25', [{ sid: 47973, back: 1.5, lay: 1.52 }]);
        mVm.mockReturnValue(vm({
            giornata: gruppo([partita({ event_id: 'S1', nome: 'Arsenal v Chelsea' })]),
            posizioni: [], operazioni: new Map(),
            ordiniConto: raggruppaOrdiniConto([{ ...SITO, event_id: 'S1' }], '2026-10-08T14:59:50Z'),
        }));
        mostra();
        const riga = screen.getByTestId('co-fuori-bot');
        // LAY 8 @ 1,60 chiuso puntando 8,53 @ 1,50: -0,53 su entrambi gli esiti
        await waitFor(() => expect(within(riga).getByTestId('co-fuori-bot-pnl').textContent).toBe('−0,53 €'));
        const b = within(riga).getByTestId('co-fuori-bot-cashout');
        expect(b).not.toBeDisabled();
        fireEvent.click(b);
        expect(mGreen).not.toHaveBeenCalled();
        expect(within(riga).getByTestId('co-fuori-bot-cashout-conferma')).toBeDisabled();
        await waitFor(() => expect(within(riga).getByTestId('co-fuori-bot-cashout-conferma')).not.toBeDisabled(), { timeout: 1500 });
        fireEvent.click(within(riga).getByTestId('co-fuori-bot-cashout-conferma'));
        expect(mGreen).toHaveBeenCalledTimes(1);
        expect(mGreen).toHaveBeenCalledWith({ marketId: '1.OU25', selectionId: 47973 });
        await waitFor(() => expect(within(riga).getByTestId('co-fuori-bot-esito').getAttribute('data-fase')).toBe('eseguita'));
    });

    it('ordine dall\'app (source runner) = «App»', () => {
        mVm.mockReturnValue(vm({
            ordiniConto: raggruppaOrdiniConto([{ ...SITO, source: 'runner' }], '2026-10-08T14:59:50Z'),
        }));
        mostra();
        const box = screen.getByTestId('co-scatola-E1');
        expect(within(box).getByTestId('co-fuori-bot-origine').textContent).toBe('App');
        // le 3 gambe di Mike restano: la riga fuori dai bot si AGGIUNGE
        expect(within(box).getAllByTestId('co-gamba')).toHaveLength(3);
    });

    it('ordini del conto non letti: la pagina lo dice, mai «nessun ordine»', () => {
        mVm.mockReturnValue(vm({ ordiniConto: { ...ORDINI_CONTO_NON_LETTI, motivo: 'RPC non disponibile' } }));
        mostra();
        expect(screen.getByTestId('co-ordini-conto-non-letti').textContent).toMatch(/RPC non disponibile/);
    });
});

describe('LIVE e PROVA mai sommati', () => {
    it('il totale della posizione col conto conta SOLO il live (bot live + sito); la prova resta nel suo riquadro', async () => {
        PREZZI.set('1.OU25', [{ sid: 47973, back: 1.5, lay: 1.52 }]);
        PREZZI.set('1.MO', [{ sid: 1, back: 2.0, lay: 2.02 }]);
        mVm.mockReturnValue(vm({
            posizioni: [pos({ bot: 'omega', id: 7, eventId: 'E1', modalita: 'paper', selezione: 'Inter' })],
            operazioni: new Map([['E1', [op({ bot: 'omega', id: 7, modalita: 'paper', selezione: 'Inter', marketId: '1.MO', selectionId: 1, ordine: ordine('back', 2.1, 10) })]]]),
            ordiniConto: raggruppaOrdiniConto([SITO], '2026-10-08T14:59:50Z'),
        }));
        mostra();
        const box = screen.getByTestId('co-scatola-E1');
        // solo il sito nel LIVE: -0,53 (la gamba PROVA di Omega non entra)
        await waitFor(() => expect(within(box).getByTestId('co-posizione-conto-netto').textContent).toBe('−0,53 €'));
        // la prova ha il suo riquadro, separato
        expect(within(box).getByTestId('cr-cashout-globale-prova')).toBeTruthy();
        expect(within(box).getByTestId('co-soldi-live')).toBeTruthy();
        expect(within(box).getByTestId('co-soldi-prova')).toBeTruthy();
    });
});

describe('ladder pop-out e ritorno', () => {
    it('«Ladder» di una gamba apre /ladder-popout del SUO mercato, finestra ladder_<id> 560x860', () => {
        const apri = vi.spyOn(window, 'open').mockImplementation(() => ({}) as Window);
        mVm.mockReturnValue(vm());
        mostra();
        fireEvent.click(within(screen.getByTestId('co-scatola-E1')).getAllByTestId('co-ladder')[1]);
        expect(apri).toHaveBeenCalledWith(
            '/ladder-popout?sport=calcio&market=1.OU45&event=E1&eventName=Inter+v+Milan',
            'ladder_1.OU45',
            'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes',
        );
        apri.mockRestore();
    });

    it('«Statistiche» segna il ritorno al Cash Out (non alla Control Room) e porta from=cash-out', () => {
        mVm.mockReturnValue(vm({ giornata: gruppo([partita({ extra: { campionato: null, leagueId: null, homeTeamId: null, awayTeamId: null, fixtureId: 1208845 } })]) }));
        render(
            <HelmetProvider>
                <MemoryRouter initialEntries={['/cash-out']}>
                    <Routes>
                        <Route path="/cash-out" element={<CashOut />} />
                        <Route path="/dashboard" element={<Dove />} />
                    </Routes>
                </MemoryRouter>
            </HelmetProvider>,
        );
        fireEvent.click(within(screen.getByTestId('co-scatola-E1')).getByTestId('cr-statistiche'));
        expect(screen.getByTestId('dove').textContent).toBe('/dashboard?fixture=1208845&from=cash-out');
        const punto = JSON.parse(sessionStorage.getItem('ritorno.punto') ?? '{}');
        expect(punto).toMatchObject({ rotta: '/cash-out', nome: 'Cash Out', eventId: 'E1' });
    });
});

// ========================================================================
// SECONDO GIRO (08/10): testata della scatola come il prototipo, filtro dei
// soldi, riepilogo «Se chiudo tutto adesso» LIVE e PROVA dalle cifre delle scatole.
// ========================================================================
const euro = (t: string | null | undefined) => Number(String(t ?? '').replace(/[^\d,−-]/g, '').replace('−', '-').replace(',', '.'));

describe('secondo giro: testata della scatola', () => {
    it('solo Video | Stats Betfair e «Statistiche»: niente Trading ne\' Segui live', () => {
        mVm.mockReturnValue(vm());
        mostra();
        const box = screen.getByTestId('co-scatola-E1');
        expect(within(box).getByTestId('cr-statistiche')).toBeTruthy();
        expect(within(box).queryByTestId('cr-trading')).toBeNull();
        expect(within(box).queryByTestId('cr-segui-live')).toBeNull();
    });
});

describe('secondo giro: filtro dei soldi', () => {
    it('«Solo live» / «Solo prova» scelgono, ri-clic = live e prova; una partita con una gamba non paper e\' LIVE', () => {
        mVm.mockReturnValue(vm({
            giornata: gruppo([partita(), partita({ event_id: 'E3', nome: 'Napoli v Roma' })]),
            posizioni: [...MIKE3.posizioni, pos({ bot: 'omega', id: 7, eventId: 'E3', partita: 'Napoli v Roma', modalita: 'paper' })],
            operazioni: new Map([['E1', MIKE3.operazioni], ['E3', [op({ bot: 'omega', id: 7, eventId: 'E3', modalita: 'paper' })]]]),
        }));
        mostra();
        expect(screen.getByTestId('co-filtro-soldi-tutti').getAttribute('aria-pressed')).toBe('true');
        fireEvent.click(screen.getByTestId('co-filtro-soldi-live'));
        expect(screen.getByTestId('co-scatola-E1')).toBeTruthy();
        expect(screen.queryByTestId('co-scatola-E3')).toBeNull();
        fireEvent.click(screen.getByTestId('co-filtro-soldi-prova'));
        expect(screen.queryByTestId('co-scatola-E1')).toBeNull();
        expect(screen.getByTestId('co-scatola-E3')).toBeTruthy();
        // ri-clic sullo stesso: tutto
        fireEvent.click(screen.getByTestId('co-filtro-soldi-prova'));
        expect(screen.getByTestId('co-filtro-soldi-tutti').getAttribute('aria-pressed')).toBe('true');
        expect(screen.getByTestId('co-scatola-E1')).toBeTruthy();
        expect(screen.getByTestId('co-scatola-E3')).toBeTruthy();
    });
});

describe('secondo giro: riepilogo «Se chiudo tutto adesso»', () => {
    function treEventi() {
        return vm({
            giornata: gruppo([
                partita(),
                partita({ event_id: 'E2', nome: 'Lazio v Torino' }),
                partita({ event_id: 'E3', nome: 'Napoli v Roma' }),
            ]),
            posizioni: [
                pos({ bot: 'omega', id: 2, eventId: 'E2', partita: 'Lazio v Torino', selezione: 'Lazio' }),
                pos({ bot: 'omega', id: 7, eventId: 'E3', partita: 'Napoli v Roma', modalita: 'paper', selezione: 'Napoli' }),
            ],
            operazioni: new Map([
                ['E2', [op({ bot: 'omega', id: 2, eventId: 'E2', selezione: 'Lazio', marketId: '1.MO2', selectionId: 1, ordine: ordine('back', 2.1, 10) })]],
                ['E3', [op({ bot: 'omega', id: 7, eventId: 'E3', modalita: 'paper', selezione: 'Napoli', marketId: '1.MO3', selectionId: 1, ordine: ordine('back', 2.1, 10) })]],
            ]),
            // E1: solo l'ordine del sito (LAY 8 @ 1,60)
            ordiniConto: raggruppaOrdiniConto([SITO], '2026-10-08T14:59:50Z'),
        });
    }

    it('LIVE = somma ESATTA delle cifre delle scatole (bot + sito); PROVA a parte; gambe e partite per modalita\'', async () => {
        PREZZI.set('1.OU25', [{ sid: 47973, back: 1.5, lay: 1.52 }]);
        PREZZI.set('1.MO2', [{ sid: 1, back: 2.0, lay: 2.02 }]);
        PREZZI.set('1.MO3', [{ sid: 1, back: 2.0, lay: 2.02 }]);
        mVm.mockReturnValue(treEventi());
        mostra();
        await waitFor(() => expect(screen.getByTestId('co-totale-live').getAttribute('data-stato')).toBe('ok'));
        const e1 = euro(within(screen.getByTestId('co-scatola-E1')).getByTestId('co-posizione-conto-netto').textContent);
        const e2 = euro(within(screen.getByTestId('co-scatola-E2')).getByTestId('cr-cashout-globale-live-netto').textContent);
        const e3 = euro(within(screen.getByTestId('co-scatola-E3')).getByTestId('cr-cashout-globale-prova-netto').textContent);
        expect(e1).toBe(-0.53);
        expect(e2).toBe(0.37);
        expect(screen.getByTestId('co-totale-live-netto').textContent).toBe('−0,16 €');
        expect(euro(screen.getByTestId('co-totale-live-netto').textContent)).toBeCloseTo(e1 + e2, 10);
        // la PROVA: solo E3, mai nel live
        expect(euro(screen.getByTestId('co-totale-prova-netto').textContent)).toBe(e3);
        expect(screen.getByTestId('co-totale-live-conta').textContent).toMatch(/^2 gambe aperte su 2 partite/);
        expect(screen.getByTestId('co-totale-prova-conta').textContent).toMatch(/^1 gamba aperta su 1 partita/);
    });

    it('una scatola non calcolabile: la cifra LIVE dice «non calcolabile» col motivo, nessuna somma monca', async () => {
        PREZZI.set('1.OU25', [{ sid: 47973, back: 1.5, lay: 1.52 }]);
        // E2 senza prezzo
        mVm.mockReturnValue(treEventi());
        mostra();
        await waitFor(() => expect(screen.getByTestId('co-totale-live').getAttribute('data-stato')).toBe('non-calcolabile'));
        expect(screen.queryByTestId('co-totale-live-netto')).toBeNull();
        expect(screen.getByTestId('co-totale-live-non-calcolabile').textContent).toMatch(/Lazio v Torino: manca il prezzo di Lazio/);
    });

    it('filtro «Solo prova»: il riepilogo segue le scatole mostrate (live senza gambe = «—»)', async () => {
        PREZZI.set('1.MO3', [{ sid: 1, back: 2.0, lay: 2.02 }]);
        mVm.mockReturnValue(treEventi());
        mostra();
        fireEvent.click(screen.getByTestId('co-filtro-soldi-prova'));
        await waitFor(() => expect(screen.getByTestId('co-totale-prova').getAttribute('data-stato')).toBe('ok'));
        expect(screen.getByTestId('co-totale-live').getAttribute('data-stato')).toBe('nessuna');
        expect(screen.getByTestId('co-totale-live-vuoto').textContent).toBe('—');
    });
});
