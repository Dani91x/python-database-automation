// ============================================================================
// ControlRoom.test.tsx — test di PAGINA del banco.
//
// Il modello di vista (`useControlRoom`) è mockato: qui si collauda quello che
// il TRADER LEGGE, e in particolare le frasi che, se sbagliate, gli fanno
// credere una cosa per un'altra:
//   · soldi veri o simulati, per bot, con le varianti quando servono;
//   · un freno assente scritto «assente», non «0,00 €»;
//   · un bot muto dichiarato muto, e le sue proposte non approvabili;
//   · un target CALCOLATO dalla pagina marcato come tale;
//   · una partita senza risultato con «—», mai «0,00 €».
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, cleanup, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/components/controlroom/useControlRoom', () => ({ useControlRoom: vi.fn() }));

import ControlRoom from './ControlRoom';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import type { GruppoCampionato, PartitaGiornata } from '@/lib/controlRoom';

const mVm = vi.mocked(useControlRoom);

function partita(over: Partial<PartitaGiornata> = {}): PartitaGiornata {
    return {
        event_id: 'E1', sport: 'calcio', nome: 'Milan – Inter', campionato: 'Serie A',
        koMs: Date.parse('2026-09-14T13:00:00Z'), stato: 'live',
        minuto: 58, punteggio: '1-0', controlloDisponibile: true,
        etaFeedS: 2, freschezza: 'fresca', latenzaQuoteS: 1, freschezzaQuote: 'fresca', statoQuote: 'fresco',
        media: { video: true, viz: true }, marketId: '1.24',
        soldi: {
            live: { netPnl: 12.5, liability: 40, investito: 10, aperta: true },
            paper: { netPnl: null, liability: 0, investito: 0, aperta: false },
            modi: ['live'], bots: ['omega'],
        },
        target: { valore: 31.2, fonte: 'servizio' },
        avanzamento: 40,
        extra: null,
        ...over,
    };
}

function gruppo(partite: PartitaGiornata[]): GruppoCampionato[] {
    return [{ campionato: partite[0]?.campionato ?? 'Serie A', primoKoMs: partite[0]?.koMs ?? null, partite }];
}

function vm(over: Partial<ReturnType<typeof useControlRoom>> = {}): ReturnType<typeof useControlRoom> {
    return {
        caricamento: false, errore: null, nowMs: Date.parse('2026-09-14T15:00:00Z'),
        giornata: gruppo([partita()]),
        totali: {
            letti: true,
            partite: 1, live: 1, pre: 0, conPosizione: 1, conPosizioneLive: 1,
            liability: 40, liabilityPaper: 0, netPnl: 12.5, netPnlPaper: null,
        },
        obiettivo: 250, obiettivoStoricizzato: true, realizzato: 96.4, targetServizio: 31.2,
        bots: [
            { bot: 'omega', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 2, freschezzaPush: 'fresca', varianti: null },
            { bot: 'safe', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 1, freschezzaPush: 'fresca', varianti: null },
            { bot: 'mike', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 3, freschezzaPush: 'fresca', varianti: null },
        ],
        posizioni: [],
        chiuse: [],
        registrazioni: new Set<string>(),
        copertura: { conDato: 1, senzaDato: 0, totale: 1, pct: 100 },
        freni: { daily_loss_stop: -50, loss_stop_active: false },
        runner: { ts: '2026-09-14T14:59:30Z', mode: 'PAPER', ageS: 30, up: true, streaming: 2 },
        mikeRestingLive: true,
        soldiGiornata: {
            realizzato: 96.4,
            realizzatoPaper: null,
            discordanza: null,
            perBot: { omega: 90, safe: 6.4, mike: 0 },
            liability: 40,
            perSport: {
                calcio: { n: 3, pnl: 1.5, won: 2, lost: 1 },
                tennis: { n: 2, pnl: 0.08, won: 1, lost: 1 },
            },
            perSportPaper: null,
            operazioni: 5, vinte: 3, perse: 2, operazioniPaper: null,
        },
        schermo: { feedMs: 800, pushMs: 1200, letturaMs: 4000, schermoMs: 4000 },
        ultimaCatena: { salti: [], trade: null, evento: null },
        operazioni: new Map(),
        proposte: [], slippagePct: 2, setSlippagePct: vi.fn(),
        approva: vi.fn(), ignora: vi.fn(), chiudi: vi.fn(),
        // 16/09 — il FINTO parla come il VERO: le chiavi nuove del modello di
        // vista ci sono tutte, con lo stesso tipo. Un finto piu' povero del
        // vero fa passare una pagina che dal vivo esplode (memoria 15/09).
        statoChiusura: () => ({ chiusa: false, fonte: null, marcatore: null }),
        cashOutEvento: vi.fn(), riprendiEvento: vi.fn(), eventiChiusiOmega: [],
        proposteOmega: [], erroreProposteOmega: null,
        approvaOmega: vi.fn(), ignoraOmega: vi.fn(),
        feedSorgente: 'stream', feedEtaS: 1, feedFreschezza: 'fresca',
        ricarica: vi.fn(),
        ...over,
    } as ReturnType<typeof useControlRoom>;
}

function mostra() {
    return render(
        <HelmetProvider><MemoryRouter><ControlRoom /></MemoryRouter></HelmetProvider>,
    );
}

/** Le partite e le posizioni ora vivono in SCHEDE: per guardarci dentro
 *  bisogna aprirle, come fa il trader.
 *
 *  `userEvent` e non `fireEvent`: Radix Tabs ascolta eventi di puntatore veri,
 *  e con fireEvent la linguetta non cambia (il test fallirebbe per il motivo
 *  sbagliato). Stesso pattern dei test di Safe Strategy e Mike. */
async function apri(s: ReturnType<typeof mostra>, tab: 'pre' | 'live' | 'aperte' | 'chiuse') {
    await userEvent.click(s.getByTestId(`cr-tab-${tab}`));
    return s;
}

beforeEach(() => { vi.clearAllMocks(); });

// ---------------------------------------------------------------- modalità

describe('modalità — soldi veri o simulati, senza possibilità di equivoco', () => {
    it('tutto in paper: il banner lo dice, e NON parla di soldi veri', () => {
        mVm.mockReturnValue(vm());
        const b = mostra().getByTestId('cr-banner-modalita');
        expect(b.textContent).toMatch(/simulate/i);
        expect(b.textContent).not.toMatch(/REALI/);
    });

    it('un solo bot in live: l\'avviso c\'è e NOMINA quel bot', () => {
        const v = vm();
        v.bots[1] = { ...v.bots[1], modalita: 'live' };
        mVm.mockReturnValue(v);
        mostra();
        const banner = screen.getByTestId('cr-banner-modalita');
        expect(banner.textContent).toMatch(/REALI/);
        expect(banner.textContent).toMatch(/Safe: LIVE/);
    });

    it('in live con varianti: dice QUALI apre, perché «LIVE» da solo sarebbe fuorviante', () => {
        const v = vm();
        v.bots[1] = { ...v.bots[1], modalita: 'live', varianti: ['tennis'] };
        mVm.mockReturnValue(v);
        mostra();
        expect(screen.getByTestId('cr-banner-modalita').textContent).toMatch(/apre solo tennis/);
    });

    it('modalità sconosciuta non si mostra come paper: si dichiara ignota', () => {
        const v = vm();
        v.bots[0] = { ...v.bots[0], modalita: null };
        mVm.mockReturnValue(v);
        mostra();
        expect(within(screen.getByTestId('cr-bot-omega')).getByText(/modalità ignota/)).toBeTruthy();
    });
});

// ------------------------------------------------------------------- freni

describe('freni — un freno che nessuno vede non è un freno', () => {
    it('mostra la soglia dello stop di perdita', () => {
        mVm.mockReturnValue(vm());
        expect(within(mostra().getByTestId('cr-freni')).getByText(/50,00/)).toBeTruthy();
    });

    it('SOGLIA ASSENTE si scrive «assente», MAI «0,00 €»', () => {
        mVm.mockReturnValue(vm({ freni: null }));
        const el = mostra().getByTestId('cr-freni');
        expect(within(el).getByText('assente')).toBeTruthy();
        expect(el.textContent).not.toMatch(/0,00/);
    });

    it('stop già scattato: lo dice, non mostra solo un numero', () => {
        mVm.mockReturnValue(vm({ freni: { daily_loss_stop: -50, loss_stop_active: true } }));
        expect(within(mostra().getByTestId('cr-freni')).getByText('SCATTATO')).toBeTruthy();
    });
});

// -------------------------------------------------------------- bot muti

describe('bot muto — fail-closed dichiarato', () => {
    it('canale caduto: lo dice, e avvisa che le sue proposte non saranno approvabili', () => {
        const v = vm();
        v.bots[2] = { ...v.bots[2], canale: 'off', etaPushS: null, freschezzaPush: 'ignota' };
        mVm.mockReturnValue(v);
        mostra();
        expect(within(screen.getByTestId('cr-bot-mike')).getByText(/senza spinta/)).toBeTruthy();
        expect(within(screen.getByTestId('cr-bot-muti')).getByText(/Mike/)).toBeTruthy();
        expect(screen.getByTestId('cr-bot-muti').textContent).toMatch(/non conosciamo l/);
    });

    it('dato vecchio oltre soglia: muto anche col canale connesso', () => {
        const v = vm();
        v.bots[0] = { ...v.bots[0], etaPushS: 120, freschezzaPush: 'vecchia' };
        mVm.mockReturnValue(v);
        mostra();
        expect(screen.getByTestId('cr-bot-muti').textContent).toMatch(/Omega/);
    });

    it('tutti freschi: nessun avviso', () => {
        mVm.mockReturnValue(vm());
        mostra();
        expect(screen.queryByTestId('cr-bot-muti')).toBeNull();
    });
});

// ------------------------------------------------------------------ partite

describe('partite — quello che la riga dice e quello che non deve dire', () => {
    it('in gioco: minuto e punteggio; pre-match: l\'orario', async () => {
        mVm.mockReturnValue(vm({
            giornata: [
                ...gruppo([partita()]),
                { campionato: 'Liga', primoKoMs: Date.parse('2026-09-14T19:00:00Z'), partite: [partita({ event_id: 'E2', nome: 'Girona – Betis', campionato: 'Liga', stato: 'pre', minuto: null, punteggio: null, koMs: Date.parse('2026-09-14T19:00:00Z'), soldi: null, avanzamento: null })] },
            ],
        }));
        const s = mostra();
        // in gioco sta nella scheda Live, col minuto e il punteggio...
        const live = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(live).getByText(/58′/)).toBeTruthy();
        expect(within(live).getByText(/1-0/)).toBeTruthy();
        expect(within(live).queryByText('Girona – Betis')).toBeNull();

        // ...e la pre-match nella sua, con l'orario. È il senso della divisione:
        // due stati diversi non stanno nella stessa lista.
        //
        // Nella scheda pre-match i due nomi stanno su righe separate (ognuna
        // col suo logo): si cercano separatamente, non come una stringa sola.
        const pre = (await apri(s, 'pre')).getByTestId('cr-elenco-pre');
        expect(within(pre).getByText('Girona')).toBeTruthy();
        expect(within(pre).getByText('Betis')).toBeTruthy();
        expect(within(pre).queryByText(/58′/)).toBeNull();
    });

    it('PARTITA SENZA RISULTATO: «—», mai «0,00 €»', () => {
        mVm.mockReturnValue(vm({ giornata: gruppo([partita({ soldi: null, avanzamento: null })]) }));
        const riga = mostra().getByTestId('cr-partita');
        expect(riga.textContent).toContain('—');
        expect(riga.textContent).not.toMatch(/0,00\s*€/);
    });

    it('un target CALCOLATO dalla pagina è marcato: non si spaccia per quello del servizio', () => {
        mVm.mockReturnValue(vm({ giornata: gruppo([partita({ target: { valore: 20, fonte: 'ripiego' } })]) }));
        const riga = mostra().getByTestId('cr-partita');
        expect(riga.textContent).toContain('target');
        expect(riga.textContent).toContain('*');
    });

    it('un target del SERVIZIO non porta l\'asterisco', () => {
        mVm.mockReturnValue(vm());
        const riga = mostra().getByTestId('cr-partita');
        expect(riga.textContent).toMatch(/target/);
        expect(riga.textContent).not.toMatch(/\*/);
    });

    it('i campionati si leggono nell\'ordine in cui il modello li consegna', async () => {
        mVm.mockReturnValue(vm({
            giornata: [
                { campionato: 'Serie A', primoKoMs: 1, partite: [partita()] },
                { campionato: 'Liga', primoKoMs: 2, partite: [partita({ event_id: 'E2', campionato: 'Liga' })] },
            ],
        }));
        const elenco = (await apri(mostra(), 'live')).getByTestId('cr-elenco-live');
        // il titolo del campionato e' il PRIMO span dell'h3: accanto ci sono
        // il conteggio e l'orario di apertura, che non fanno parte del nome.
        const titoli = Array.from(elenco.querySelectorAll('h3'))
            .map((h) => h.querySelector('span')?.textContent?.trim());
        expect(titoli).toEqual(['Serie A', 'Liga']);
    });
});

// ------------------------------------------------------- controllo del gioco

describe('spia del controllo del gioco', () => {
    it('quando il dato manca su qualche partita in gioco, lo dichiara con i numeri', () => {
        mVm.mockReturnValue(vm({ copertura: { conDato: 4, senzaDato: 6, totale: 10, pct: 40 } }));
        expect(mostra().getByTestId('cr-copertura').textContent).toMatch(/4 partite in gioco su 10/);
    });

    it('copertura piena: NON si allarma (niente rumore quando non serve)', () => {
        mVm.mockReturnValue(vm({ copertura: { conDato: 10, senzaDato: 0, totale: 10, pct: 100 } }));
        mostra();
        expect(screen.queryByTestId('cr-copertura')).toBeNull();
    });

    it('nessuna partita in gioco: nessuna percentuale inventata', () => {
        mVm.mockReturnValue(vm({ copertura: { conDato: 0, senzaDato: 0, totale: 0, pct: null } }));
        mostra();
        expect(screen.queryByTestId('cr-copertura')).toBeNull();
    });
});

// ---------------------------------------------------------------- posizioni

describe('posizioni aperte', () => {
    it('una posizione LIVE è marcata live e contata a parte', async () => {
        mVm.mockReturnValue(vm({
            posizioni: [{
                bot: 'safe', id: 1, eventId: 'E1', partita: 'Rune – Musetti', selezione: 'Rune',
                lato: 'back', prezzo: 1.03, size: 2, liability: 2, modalita: 'live',
                piazzataAt: '2026-09-14T14:50:00Z',
                chiusura: { lato: 'lay', prezzo: 1.02, abbinabile: 88, bloccabile: 0.24 },
            }],
        }));
        const col = (await apri(mostra(), 'aperte')).getByTestId('cr-posizioni');
        expect(within(col).getByText(/1 posizione con soldi veri/)).toBeTruthy();
        expect(within(col).getByText('BACK')).toBeTruthy();
    });

    it('senza posizioni lo dice invece di mostrare una tabella vuota', async () => {
        mVm.mockReturnValue(vm());
        expect(within((await apri(mostra(), 'aperte')).getByTestId('cr-posizioni')).getByText(/Nessuna posizione aperta/)).toBeTruthy();
    });
});

// -------------------------------------------------------- uscite da decidere

function propostaVista(over: Record<string, unknown> = {}, vivoOver: Record<string, unknown> = {}, eta: number | null = 2) {
    return {
        proposta: {
            id: 1, kind: 'cashout', status: 'proposed', created_at: '2026-09-14T14:50:00Z',
            payload: {
                trade_id: 271, event_id: 'T1', event_name: 'Rossi v Bianchi', sport: 'tennis',
                strategy: 'tennis', selection_name: 'Rossi', market_id: '1.24', selection_id: 11,
                side: 'lay', entry_side: 'back', entry_price: 1.03, size: 3,
                price_at_decision: 1.32, size_available_at_decision: 116.38,
                locked_at_decision: -0.21, hold_profit: 0.06, loss_if_lose: 3,
                exit_kind: 'mandatory', exit_reason: 'due_game_persi_di_fila_e_parita',
                urgente: true, score: 'set 1-0 · game 4-4', mode: 'paper',
                ...over,
            },
        },
        vivo: { prezzo: 1.32, abbinabile: 116.38, statoMercato: null, ...vivoOver },
        etaQuoteS: eta,
        bloccabileOra: null,
    } as unknown as ReturnType<typeof useControlRoom>['proposte'][number];
}

describe('uscite — la scheda che decide un ordine vero', () => {
    it('senza proposte spiega cosa comparirà, invece di restare muta', () => {
        mVm.mockReturnValue(vm());
        expect(within(mostra().getByTestId('cr-nastro')).getByText(/Nessuna uscita da decidere/)).toBeTruthy();
    });

    it('mostra il PREZZO VIVO e il confronto con la proposta', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista({}, { prezzo: 1.28 })] }));
        mostra();
        expect(within(screen.getByTestId('cr-prezzo-vivo')).getByText(/1,28/)).toBeTruthy();
        expect(screen.getByTestId('cr-scostamento').textContent).toMatch(/1,32/);
    });

    it('URGENTE è marcata e lo dice: non approvarla costa', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista()] }));
        const card = mostra().getByTestId('cr-proposta');
        expect(card.getAttribute('data-urgente')).toBe('1');
        expect(card.textContent).toMatch(/non approvarla ha un costo/);
    });

    it('PREZZO CORRENTE ASSENTE: bottone spento e ragione scritta', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista({}, { prezzo: null, abbinabile: null })] }));
        const { getByTestId } = mostra();
        expect(getByTestId('cr-proposta-bloccata').textContent).toMatch(/non disponibile/);
        expect((getByTestId('cr-approva') as HTMLButtonElement).disabled).toBe(true);
    });

    it('ETÀ DELLE QUOTE IGNOTA: non si piazza', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista({}, {}, null)] }));
        expect(mostra().getByTestId('cr-proposta-bloccata').textContent).toMatch(/età/);
    });

    it('MERCATO CHE NON ABBINA ABBASTANZA: blocca e spiega la conseguenza', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista({ size: 50 }, { abbinabile: 4 })] }));
        expect(mostra().getByTestId('cr-proposta-bloccata').textContent).toMatch(/annullato per intero/);
    });

    it('tutto a posto: si può chiudere, e il bottone non è muto', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista()] }));
        const { getByTestId, queryByTestId } = mostra();
        expect(queryByTestId('cr-proposta-bloccata')).toBeNull();
        expect((getByTestId('cr-approva') as HTMLButtonElement).disabled).toBe(false);
    });

    it('in PAPER un clic basta; in LIVE serve la seconda conferma', async () => {
        const approva = vi.fn(async () => {});
        mVm.mockReturnValue(vm({ proposte: [propostaVista()], approva }));
        fireEvent.click(mostra().getByTestId('cr-approva'));
        expect(approva).toHaveBeenCalledWith(1);

        cleanup();
        vi.clearAllMocks();
        const approvaLive = vi.fn(async () => {});
        mVm.mockReturnValue(vm({ proposte: [propostaVista({ mode: 'live' })], approva: approvaLive }));
        const r = mostra();
        fireEvent.click(r.getByTestId('cr-approva'));
        expect(approvaLive).not.toHaveBeenCalled();          // il primo clic ARMA soltanto
        expect(r.getByTestId('cr-conferma-live')).toBeTruthy();
    });

    it('IGNORA è sempre possibile, anche quando non si può chiudere', () => {
        const ignora = vi.fn(async () => {});
        mVm.mockReturnValue(vm({ proposte: [propostaVista({}, { prezzo: null })], ignora }));
        const b = mostra().getByTestId('cr-ignora') as HTMLButtonElement;
        expect(b.disabled).toBe(false);
        fireEvent.click(b);
        expect(ignora).toHaveBeenCalledWith(1);
    });

    it('il motivo dell’uscita è in italiano, e l’ingresso è ricordato', () => {
        mVm.mockReturnValue(vm({ proposte: [propostaVista()] }));
        const card = mostra().getByTestId('cr-proposta');
        expect(card.textContent).toMatch(/Perché:/);
        expect(card.textContent).toMatch(/1,03/);
    });
});

// ------------------------------------------------------------------- catena

describe('catena dei tempi - da Betfair al pixel', () => {
    // `latenza: false` sul primo: e' l'ETA' DEL PREZZO, non un ritardo — si
    // mostra ma non entra in nessun totale (review 15/09).
    const salti = [
        { id: 'eta_prezzo', nome: 'prezzo gia fermo da', ms: 120, spiega: '', nostro: true, latenza: false },
        { id: 'lettura', nome: 'feed al bot', ms: 780, spiega: '', nostro: true, latenza: true },
        { id: 'decisione', nome: 'bot alla decisione', ms: 50, spiega: '', nostro: true, latenza: true },
        { id: 'invio', nome: 'decisione all invio', ms: 50, spiega: '', nostro: true, latenza: true },
        { id: 'betfair', nome: 'Betfair risponde', ms: 180, spiega: '', nostro: false, latenza: true },
        { id: 'fill', nome: 'risposta al fill', ms: 20, spiega: '', nostro: true, latenza: true },
    ];

    it('mostra quanto e vecchio quello che il trader vede', () => {
        mVm.mockReturnValue(vm());
        expect(mostra().getByTestId('cr-schermo').textContent).toMatch(/4[.,]0 s/);
    });

    it('senza istanti lo DICHIARA, invece di mostrare degli zero', () => {
        mVm.mockReturnValue(vm());
        const el = mostra().getByTestId('cr-catena-operazione');
        expect(el.textContent).toMatch(/nessun istante registrato/);
        expect(el.textContent).not.toMatch(/0 ms/);
    });

    it('con gli istanti mostra i salti e indica il PIU LENTO', () => {
        mVm.mockReturnValue(vm({ ultimaCatena: { salti, trade: 285, evento: 'X v Y' } }));
        const r = mostra();
        const el = r.getByTestId('cr-catena-operazione');
        expect(el.textContent).toMatch(/120 ms/);
        expect(el.textContent).toMatch(/780 ms/);
        expect(r.getByTestId('cr-collo').textContent).toMatch(/feed al bot/);
    });

    it('separa il tempo NOSTRO da quello totale: Betfair non e colpa nostra', () => {
        mVm.mockReturnValue(vm({ ultimaCatena: { salti, trade: 285, evento: 'X v Y' } }));
        const el = mostra().getByTestId('cr-catena-operazione');
        // 780+50+50+20 = 900 ms nostri; +180 di Betfair = 1,08 s totali.
        // I 120 ms di «prezzo gia fermo» non entrano in nessuno dei due.
        expect(el.textContent).toMatch(/900 ms/);
        expect(el.textContent).toMatch(/1[.,]1 s/);
    });

    it('un salto non misurato e un trattino, mai zero', () => {
        const parziali = salti.map((s) => (s.id === 'fill' ? { ...s, ms: null } : s));
        mVm.mockReturnValue(vm({ ultimaCatena: { salti: parziali, trade: 285, evento: null } }));
        expect(mostra().getByTestId('cr-catena-operazione').textContent).toContain('—');
    });
});

// ------------------------------------------------------------------- runner

describe('runner — tre stati, non due', () => {
    it('battito fresco + follow STREAMING = in streaming', () => {
        mVm.mockReturnValue(vm());
        expect(within(mostra().getByTestId('cr-runner')).getByText(/in streaming/)).toBeTruthy();
    });

    it('battito fresco SENZA follow = «vivo, in attesa»: il processo c’è, la coda no', () => {
        mVm.mockReturnValue(vm({ runner: { ts: '2026-09-14T14:59:30Z', mode: 'PAPER', ageS: 30, up: true, streaming: 0 } }));
        expect(within(mostra().getByTestId('cr-runner')).getByText(/vivo, in attesa/)).toBeTruthy();
    });

    it('streaming NON LETTO vale attesa, mai streaming: il dubbio non concede la coda', () => {
        mVm.mockReturnValue(vm({ runner: { ts: '2026-09-14T14:59:30Z', mode: 'PAPER', ageS: 30, up: true, streaming: null } }));
        expect(within(mostra().getByTestId('cr-runner')).getByText(/vivo, in attesa/)).toBeTruthy();
    });

    it('battito vecchio = spento', () => {
        mVm.mockReturnValue(vm({ runner: { ts: '2026-09-02T17:55:00Z', mode: 'PAPER', ageS: 1_000_000, up: false } }));
        expect(within(mostra().getByTestId('cr-runner')).getByText(/spento/)).toBeTruthy();
    });

    it('MAI battuto non si confonde con spento: si dice «mai avviato»', () => {
        mVm.mockReturnValue(vm({ runner: { ts: null, mode: null, ageS: null, up: false } }));
        expect(within(mostra().getByTestId('cr-runner')).getByText(/mai avviato/)).toBeTruthy();
    });

    it('stato non letto = «ignoto», e non si spaccia per spento', () => {
        mVm.mockReturnValue(vm({ runner: null }));
        expect(within(mostra().getByTestId('cr-runner')).getByText(/ignoto/)).toBeTruthy();
    });
});

// ----------------------------------------------- la valvola che fa divergere

describe('Mike: uscita appoggiata in live', () => {
    it('SPENTA: lo grida, perché demo e live diventano due strategie diverse', () => {
        mVm.mockReturnValue(vm({ mikeRestingLive: false }));
        const avviso = mostra().getByTestId('cr-mike-resting');
        expect(avviso.textContent).toMatch(/diversa/);
        expect(avviso.textContent).toMatch(/perdita/);
    });

    it('accesa: nessun allarme', () => {
        mVm.mockReturnValue(vm({ mikeRestingLive: true }));
        mostra();
        expect(screen.queryByTestId('cr-mike-resting')).toBeNull();
    });

    it('valore SCONOSCIUTO non vale «spento»: non si allarma su un dato assente', () => {
        mVm.mockReturnValue(vm({ mikeRestingLive: null }));
        mostra();
        expect(screen.queryByTestId('cr-mike-resting')).toBeNull();
    });
});

// ------------------------------------------------------------------- fonti

describe('onestà sulle fonti', () => {
    it('una fonte caduta si dichiara, e si dice che i numeri sono gli ultimi letti', () => {
        mVm.mockReturnValue(vm({ errore: 'fonti non raggiunte: Mike' }));
        const box = mostra().getByTestId('cr-errore');
        expect(box.textContent).toMatch(/Mike/);
        expect(box.textContent).toMatch(/ultimo dato letto/);
    });

    it('la sorgente del feed è scritta: fra stream e rest c\'è un ordine di grandezza', () => {
        mVm.mockReturnValue(vm({ feedSorgente: 'rest', feedEtaS: 40, feedFreschezza: 'vecchia' }));
        expect(within(mostra().getByTestId('cr-feed')).getByText('rest')).toBeTruthy();
    });

    it('obiettivo non storicizzato: la pagina lo dice invece di spacciarlo per quello del giorno', () => {
        mVm.mockReturnValue(vm({ obiettivoStoricizzato: false }));
        mostra();
        expect(screen.getAllByText(/non ancora storicizzato/).length).toBeGreaterThan(0);
    });
});

// ------------------------------------------------- filtro per sport (tessere)

/** Una giornata con una partita per sport e una posizione aperta ciascuna. */
function vmDueSport(over: Partial<ReturnType<typeof useControlRoom>> = {}) {
    const calcio = partita({ event_id: 'C1', sport: 'calcio', nome: 'Milan – Inter', campionato: 'Serie A' });
    const tennis = partita({ event_id: 'T1', sport: 'tennis', nome: 'Rune – Musetti', campionato: 'ATP' });
    const pos = (id: number, eventId: string, partitaNome: string) => ({
        bot: 'safe' as const, id, eventId, partita: partitaNome, selezione: 'X',
        lato: 'back' as const, prezzo: 1.03, size: 3, liability: 3, modalita: 'live' as const,
        piazzataAt: '2026-09-14T14:50:00Z',
        chiusura: { lato: 'lay', prezzo: 1.02, abbinabile: 88, bloccabile: 0.24 },
    });
    return vm({
        giornata: [
            { campionato: 'Serie A', primoKoMs: calcio.koMs, partite: [calcio] },
            { campionato: 'ATP', primoKoMs: tennis.koMs, partite: [tennis] },
        ],
        totali: {
            letti: true,
            partite: 2, live: 2, pre: 0, conPosizione: 2, conPosizioneLive: 2,
            liability: 80, liabilityPaper: 0, netPnl: 25, netPnlPaper: null,
        },
        posizioni: [pos(1, 'C1', 'Milan – Inter'), pos(2, 'T1', 'Rune – Musetti')] as never,
        ...over,
    });
}

describe('tessere calcio/tennis — sono il filtro del banco', () => {
    it('senza filtro si vedono ENTRAMBI gli sport', async () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        const partite = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(partite).getByText('Milan – Inter')).toBeTruthy();
        expect(within(partite).getByText('Rune – Musetti')).toBeTruthy();
    });

    it('cliccando TENNIS resta solo il tennis, fra le partite e fra le posizioni', async () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));

        const partite = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(partite).queryByText('Milan \u2013 Inter')).toBeNull();
        expect(within(partite).getByText('Rune \u2013 Musetti')).toBeTruthy();

        const posizioni = (await apri(s, 'aperte')).getByTestId('cr-posizioni');
        expect(within(posizioni).queryByText('Milan \u2013 Inter')).toBeNull();
        expect(within(posizioni).getByText('Rune \u2013 Musetti')).toBeTruthy();
    });

    it('cliccando CALCIO resta solo il calcio', async () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-calcio'));
        const partite = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(partite).getByText('Milan – Inter')).toBeTruthy();
        expect(within(partite).queryByText('Rune – Musetti')).toBeNull();
    });

    it('il secondo clic sulla stessa tessera RIMETTE tutti gli sport', async () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        const partite = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(partite).getByText('Milan – Inter')).toBeTruthy();
        expect(within(partite).getByText('Rune – Musetti')).toBeTruthy();
    });

    it('la tessera scelta lo dichiara con aria-pressed', () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        const t = s.getByTestId('cr-filtro-tennis');
        expect(t.getAttribute('aria-pressed')).toBe('false');
        fireEvent.click(t);
        expect(s.getByTestId('cr-filtro-tennis').getAttribute('aria-pressed')).toBe('true');
        expect(s.getByTestId('cr-filtro-calcio').getAttribute('aria-pressed')).toBe('false');
    });

    it('LE USCITE NON SI FILTRANO MAI: la proposta di tennis resta visibile col filtro sul calcio', () => {
        mVm.mockReturnValue(vmDueSport({ proposte: [propostaVista()] }));
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-calcio'));
        const nastro = s.getByTestId('cr-nastro');
        // la proposta e' di tennis (`sport: 'tennis'` nel payload) e c'e' ancora
        expect(within(nastro).getByText(/Rossi v Bianchi/)).toBeTruthy();
        // e la pagina lo DICHIARA, invece di lasciarlo intuire
        expect(s.getByTestId('cr-nastro-non-filtrato').textContent).toMatch(/entrambi gli sport/i);
    });

    it('IL CONTATORE DELLA LINGUETTA segue il filtro: 2 sport -> 1', async () => {
        mVm.mockReturnValue(vmDueSport());
        const s = mostra();
        expect(s.getByTestId('cr-tab-live').textContent).toMatch(/2/);
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.getByTestId('cr-tab-live').textContent).toMatch(/1/);
        // e l'elenco mostra davvero una sola partita
        const elenco = (await apri(s, 'live')).getByTestId('cr-elenco-live');
        expect(within(elenco).queryByText('Milan \u2013 Inter')).toBeNull();
        expect(within(elenco).getByText('Rune \u2013 Musetti')).toBeTruthy();
    });

    it('una posizione su un evento SCONOSCIUTO non sparisce mai dietro un filtro', async () => {
        const base = vmDueSport();
        mVm.mockReturnValue(vm({
            ...base,
            posizioni: [{
                bot: 'safe', id: 9, eventId: 'IGNOTO', partita: 'Tizio – Caio', selezione: 'Tizio',
                lato: 'back', prezzo: 1.05, size: 3, liability: 3, modalita: 'live',
                piazzataAt: '2026-09-14T14:50:00Z',
                chiusura: { lato: 'lay', prezzo: 1.04, abbinabile: 50, bloccabile: 0.1 },
            }] as never,
        }));
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-calcio'));
        expect(within((await apri(s, 'aperte')).getByTestId('cr-posizioni')).getByText('Tizio – Caio')).toBeTruthy();
    });
});

// ========================================================================
// «NON VOGLIO DATI MISCHIATI» (utente, 14/09).
//
// Questi test guardano i PIXEL, non le funzioni: la matematica puo' essere
// giusta e la pagina mostrare lo stesso un numero misto.
// ========================================================================

describe('la pagina non mostra MAI un numero che somma paper e live', () => {
    it('la BARRA dell’obiettivo porta i soldi veri, e il paper ha una riga sua', () => {
        mVm.mockReturnValue(vm({
            soldiGiornata: {
                realizzato: 0.44,          // soldi veri
                realizzatoPaper: -4.83,    // prova: NON deve entrare nella barra
                discordanza: null,
                perBot: { omega: null, safe: 0.44, mike: null },
                liability: 3,
                perSport: { tennis: { n: 5, pnl: 0.44, won: 5, lost: 0 } },
                perSportPaper: { calcio: { n: 2, pnl: -4.83, won: 0, lost: 2 } },
                operazioni: 5, vinte: 5, perse: 0, operazioniPaper: 2,
            },
        }));
        const s = mostra();
        const barra = s.getByTestId('cr-giornata');
        expect(barra.textContent).toContain('0,44');
        // il numero misto (-4,39) non deve comparire da nessuna parte
        expect(barra.textContent).not.toContain('4,39');
        // il paper si vede, ma fuori dalla barra e dichiarato tale
        const riga = s.getByTestId('cr-riga-paper');
        expect(riga.textContent).toMatch(/4,83/);
        expect(riga.textContent).toMatch(/non entra nell/i);
    });

    it('L’ESPOSIZIONE in testata e’ quella VERA; la prova e’ una nota separata', () => {
        mVm.mockReturnValue(vm({
            totali: {
                letti: true,
                partite: 59, live: 14, pre: 45,
                conPosizione: 14, conPosizioneLive: 2,
                liability: 77.71, liabilityPaper: 315.97,
                netPnl: 0.44, netPnlPaper: -4.83,
            },
        }));
        const s = mostra();
        const testo = s.container.textContent ?? '';
        expect(testo).toContain('77,71');
        // 393,68 = 77,71 + 315,97: il totale mischiato non deve esistere
        expect(testo).not.toContain('393,68');
        // e le partite con soldi veri sono 2, non 14
        expect(testo).toContain('2 / 59');
    });

    it('quando server e pagina non concordano la pagina LO DICE', () => {
        mVm.mockReturnValue(vm({
            soldiGiornata: {
                ...vm().soldiGiornata,
                discordanza: 'il servizio dice 0.44 € e la pagina 0.41 €',
            },
        }));
        const avviso = mostra().getByTestId('cr-discordanza');
        expect(avviso.textContent).toMatch(/due conti diversi/i);
        expect(avviso.textContent).toMatch(/0\.44/);
    });

    it('senza niente in prova non compare nessuna riga della prova (niente rumore)', () => {
        mVm.mockReturnValue(vm({
            soldiGiornata: {
                ...vm().soldiGiornata, realizzatoPaper: null, operazioniPaper: null,
            },
        }));
        expect(mostra().queryByTestId('cr-riga-paper')).toBeNull();
    });

    it('LA SCHEDA PARTITA: numero grande = soldi veri, prova sotto e mai sommata', () => {
        mVm.mockReturnValue(vm({
            giornata: gruppo([partita({
                soldi: {
                    live: { netPnl: 0.12, liability: 3, investito: 3, aperta: false },
                    paper: { netPnl: -40, liability: 0, investito: 20, aperta: false },
                    modi: ['live', 'paper'], bots: ['safe'],
                } as never,
            })]),
        }));
        const s = mostra();
        expect(s.getByTestId('cr-pnl-partita').textContent).toContain('0,12');
        const prova = s.getByTestId('cr-pnl-partita-paper');
        expect(prova.textContent).toMatch(/40,00/);
        expect(prova.textContent).toMatch(/non entra nel target/i);
        // -39,88 (la somma) non deve esistere
        expect(s.container.textContent ?? '').not.toContain('39,88');
    });

    it('LE TESSERE: «2 aperte» dice sempre con che soldi', () => {
        mVm.mockReturnValue(vm({
            giornata: gruppo([
                partita({
                    event_id: 'T9', sport: 'tennis',
                    soldi: {
                        live: { netPnl: null, liability: 3, investito: 3, aperta: true },
                        paper: { netPnl: null, liability: 0, investito: 0, aperta: false },
                        modi: ['live'], bots: ['safe'],
                    } as never,
                }),
                partita({
                    event_id: 'C9', sport: 'calcio',
                    soldi: {
                        live: { netPnl: null, liability: 0, investito: 0, aperta: false },
                        paper: { netPnl: null, liability: 50, investito: 50, aperta: true },
                        modi: ['paper'], bots: ['omega'],
                    } as never,
                }),
            ]),
        }));
        const s = mostra();
        expect(within(s.getByTestId('cr-sport-tennis')).getByText(/1 aperta/)).toBeTruthy();
        expect(within(s.getByTestId('cr-sport-calcio')).getByText(/1 in prova/)).toBeTruthy();
    });
});

// ========================================================================
// LA PLANCIA DI COMANDO.
// «Devo poter fermare uno o tutti i bot come e quando voglio» (14/09).
// Accendere in live e' l'unico gesto della pagina che mette a rischio
// denaro vero da fermo: si conferma due volte.
// ========================================================================

function botFermo(over: Record<string, unknown> = {}) {
    return {
        bot: 'safe', modalita: 'paper', inCorsa: false, battitoAt: null,
        canale: 'connected', etaPushS: 1, freschezzaPush: 'fresca',
        varianti: null, modiStrategia: null,
        stato: 'stopped', params: { stake: { backSize: 3 } }, obiettivoGiorno: null,
        ...over,
    };
}

describe('comando dei bot', () => {
    it('mostra lo stato ESATTO del servizio: «sta fermandosi» non e’ «fermo»', () => {
        mVm.mockReturnValue(vm({
            bots: [botFermo({
                bot: 'safe', inCorsa: true, stato: 'stopping',
                varianti: ['base', 'esatto', 'punta', 'tennis'],
            })] as never,
        }));
        expect(mostra().getByTestId('cr-bot-stato-safe-base').textContent).toMatch(/sta fermandosi/i);
    });

    it('FERMA TUTTI e’ spento se non c’e’ niente da fermare', () => {
        mVm.mockReturnValue(vm({ bots: [botFermo()] as never }));
        expect(mostra().getByTestId('cr-ferma-tutti')).toHaveProperty('disabled', true);
    });

    it('FERMA TUTTI e’ acceso e non chiede conferme: e’ un freno d’emergenza', () => {
        mVm.mockReturnValue(vm({ bots: [botFermo({ inCorsa: true, stato: 'running' })] as never }));
        const b = mostra().getByTestId('cr-ferma-tutti');
        expect(b).toHaveProperty('disabled', false);
        expect(b.textContent).toMatch(/ferma tutti/i);
    });

    it('AVVIARE CON SOLDI VERI chiede una seconda conferma', () => {
        mVm.mockReturnValue(vm({ bots: [botFermo()] as never }));
        const s = mostra();
        // al primo clic non parte niente: compare la conferma
        fireEvent.click(s.getByTestId('cr-avvia-live-safe-base'));
        expect(s.getByTestId('cr-conferma-avvio-live-safe-base').textContent).toMatch(/ordini reali/i);
        expect(s.getByTestId('cr-avviso-live-safe-base').textContent).toMatch(/ordini reali su Betfair/i);
    });

    it('avviare IN PROVA non chiede nessuna conferma: non ci sono soldi in gioco', () => {
        mVm.mockReturnValue(vm({ bots: [botFermo()] as never }));
        const s = mostra();
        expect(s.getByTestId('cr-avvia-paper-safe-base')).toBeTruthy();
        expect(s.queryByTestId('cr-avviso-live-safe-base')).toBeNull();
    });

    it('anche PASSARE a soldi veri a bot acceso vuole la seconda conferma', () => {
        mVm.mockReturnValue(vm({
            bots: [botFermo({
                inCorsa: true, stato: 'running', modalita: 'paper',
                varianti: ['base', 'esatto', 'punta', 'tennis'],
            })] as never,
        }));
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-a-live-safe-base'));
        expect(s.getByTestId('cr-conferma-live-safe-base').textContent).toMatch(/sono soldi veri/i);
    });

    it('tornare in prova NON chiede conferma: si toglie rischio, non si aggiunge', () => {
        mVm.mockReturnValue(vm({
            bots: [botFermo({
                inCorsa: true, stato: 'running', modalita: 'live',
                varianti: ['base', 'esatto', 'punta', 'tennis'],
                modiStrategia: { base: 'live' },
            })] as never,
        }));
        const s = mostra();
        expect(s.getByTestId('cr-a-paper-safe-base')).toBeTruthy();
        expect(s.queryByTestId('cr-conferma-live-safe-base')).toBeNull();
    });

    it('QUANTI BOT usano soldi veri si vede in cima al pannello', () => {
        mVm.mockReturnValue(vm({
            bots: [
                botFermo({ bot: 'omega', inCorsa: true, stato: 'running', modalita: 'paper' }),
                botFermo({ bot: 'safe', inCorsa: true, stato: 'running', modalita: 'live' }),
            ] as never,
        }));
        expect(mostra().getByTestId('cr-quanti-live').textContent).toMatch(/1 con soldi veri/);
    });

    it('l’importo mostra il valore VERO del servizio e non si salva a ogni tasto', () => {
        mVm.mockReturnValue(vm({
            bots: [botFermo({ params: { stake: { backSize: 3, laySize: 2 } } })] as never,
        }));
        const s = mostra();
        // B.5 — la PUNTA ha una chiave sua; finche' non e' scritta si mostra
        // quella per lato (`backSize`), e la riga lo dichiara.
        const campo = s.getByTestId('cr-importo-safe-punta-stake-per-strategia-punta') as HTMLInputElement;
        expect(campo.placeholder).toBe('3');
        expect(s.getByTestId('cr-importo-safe-punta-stake-per-strategia-punta-ereditato').textContent)
            .toMatch(/per lato/i);
        // finche' non cambia niente, nessun pulsante «salva»
        expect(s.queryByTestId('cr-importo-safe-punta-stake-per-strategia-punta-salva')).toBeNull();
        fireEvent.change(campo, { target: { value: '5' } });
        expect(s.getByTestId('cr-importo-safe-punta-stake-per-strategia-punta-salva')).toBeTruthy();
    });

    it('l’importo di Omega dichiara che e’ un MINIMO, non l’importo di lavoro', () => {
        mVm.mockReturnValue(vm({
            bots: [botFermo({ bot: 'omega', params: { min_stake: 0.5 } })] as never,
        }));
        const s = mostra();
        const eti = s.getByTestId('cr-bot-riga-omega');
        expect(eti.textContent).toMatch(/stake minimo/i);
    });

    it('un bot senza scheda parametri lo dice, invece di mostrare un pulsante morto', () => {
        mVm.mockReturnValue(vm({ bots: [botFermo({ bot: 'omega' })] as never }));
        expect(mostra().getByTestId('cr-parametri-omega').textContent).toMatch(/dalla sua pagina/i);
    });
});

// ========================================================================
// REVIEW 14/09 — i due critici confermati da 3 scettici su 3.
// ========================================================================

describe('la TESTATA non somma paper e live (critico della review)', () => {
    it('la barra dell’obiettivo legge il realizzato LIVE, non quello misto di Omega', () => {
        mVm.mockReturnValue(vm({
            // `realizzato` e' `realized_today` di Omega: somma paper e live
            realizzato: -5,
            obiettivo: 20,
            soldiGiornata: { ...vm().soldiGiornata, realizzato: 0.44, realizzatoPaper: -5.44 },
        }));
        const testata = mostra().getByTestId('cr-obiettivo');
        expect(testata.textContent).toContain('0,44');
        // il numero misto non deve comparire in testata
        expect(testata.textContent).not.toContain('-5,00');
        expect(testata.textContent).not.toContain('−5,00');
    });

    it('testata e barra di giornata dicono LO STESSO numero', () => {
        mVm.mockReturnValue(vm({
            realizzato: 999,   // la fonte vecchia, che non deve piu' contare
            soldiGiornata: { ...vm().soldiGiornata, realizzato: 0.44 },
        }));
        const s = mostra();
        expect(s.getByTestId('cr-obiettivo').textContent).toContain('0,44');
        expect(s.getByTestId('cr-giornata').textContent).toContain('0,44');
        expect(s.getByTestId('cr-obiettivo').textContent).not.toContain('999');
    });
});

// ========================================================================
// REVIEW 15/09 — la scheda di chiusura dice il VERO sul numero che decide.
// ========================================================================

describe('«Chiudere adesso»: il numero vivo, o l’etichetta lo dichiara', () => {
    it('col valore VIVO l’etichetta dice «adesso»', () => {
        const pv = propostaVista();
        (pv as unknown as { bloccabileOra: number }).bloccabileOra = 0.42;
        mVm.mockReturnValue(vm({ proposte: [pv] }));
        const scheda = mostra().getByTestId('cr-proposta');
        expect(scheda.textContent).toMatch(/Chiudere adesso/);
        expect(scheda.textContent).toMatch(/0,42/);
    });

    it('SENZA valore vivo l’etichetta dice che e’ quello della proposta', () => {
        // prima si stampava il valore di ALLORA sotto la parola «adesso»
        mVm.mockReturnValue(vm({ proposte: [propostaVista({ locked_at_decision: -0.21 })] }));
        const scheda = mostra().getByTestId('cr-proposta');
        expect(scheda.textContent).toMatch(/Chiudere \(alla proposta\)/);
        expect(scheda.textContent).not.toMatch(/Chiudere adesso/);
    });
});

// ===========================================================================
// LA SCHEDA TENNIS — «voglio vedere SOLO il bot di tennis» (utente, 15/09)
// ===========================================================================

describe('scheda tennis: una plancia sola, e quella giusta', () => {
    /** Safe con i parametri letti: il tennis in prova, il calcio in live,
     *  stake 5 — cioè esattamente quello che l'avvio dalla scheda tennis deve
     *  raddrizzare. */
    function vmConSafe() {
        const v = vm();
        v.bots[1] = {
            ...v.bots[1], stato: 'stopped', inCorsa: false,
            params: {
                stake: { backSize: 5, laySize: 2 },
                strategy_modes: { tennis: 'paper', base: 'live' },
                variants: ['base', 'tennis'],
                auto_trade_tennis: false,
            },
        } as typeof v.bots[1];
        return v;
    }

    it('senza filtro si comandano tutti e tre', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        expect(s.queryByTestId('cr-bot-riga-omega')).not.toBeNull();
        expect(s.queryByTestId('cr-bot-riga-mike')).not.toBeNull();
        expect(s.getByTestId('cr-pannello-bot-titolo').textContent).toMatch(/Comando dei bot/i);
    });

    it('scelto il tennis, restano SOLO le sue righe: Mike e Omega sono calcio e spariscono', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.queryByTestId('cr-bot-riga-safe-tennis')).not.toBeNull();
        expect(s.queryByTestId('cr-bot-riga-safe-base')).toBeNull();
        expect(s.queryByTestId('cr-bot-riga-omega')).toBeNull();
        expect(s.queryByTestId('cr-bot-riga-mike')).toBeNull();
        expect(s.getByTestId('cr-pannello-bot-titolo').textContent).toMatch(/Bot del tennis/i);
    });

    it('il bot si chiama TENNIS, che è il nome con cui lo si comanda', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.getByTestId('cr-bot-riga-safe-tennis').textContent).toMatch(/TENNIS/i);
    });

    it('dice PRIMA del clic che parte solo il tennis, a 3,00 €', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        const nota = s.getByTestId('cr-pannello-bot-nota').textContent ?? '';
        expect(nota).toMatch(/solo la strategia tennis/i);
        expect(nota).toMatch(/3,00/);
        expect(nota).toMatch(/Mike e Omega/);
    });

    it('e dichiara che cosa cambierebbe rispetto a com’è adesso', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        const nota = s.getByTestId('cr-pannello-bot-nota').textContent ?? '';
        expect(nota).toMatch(/base/);
        expect(nota).toMatch(/entrate automatiche/);
    });

    it('resta il solo importo che muove il tennis: «banca» è del calcio', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.queryByTestId('cr-importo-safe-tennis-stake-per-strategia-tennis')).not.toBeNull();
        expect(s.queryByTestId('cr-importo-safe-base-stake-per-strategia-base')).toBeNull();
    });

    it('tolto il filtro tornano tutti: la plancia non resta ristretta per sbaglio', () => {
        mVm.mockReturnValue(vmConSafe());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.queryByTestId('cr-bot-riga-mike')).not.toBeNull();
        expect(s.queryByTestId('cr-pannello-bot-nota')).toBeNull();
    });
});

// ===========================================================================
// REVIEW 15/09, CRITICO — la conferma rossa NON sopravvive al cambio scheda.
// Armata sotto la promessa «solo tennis», fuori da quella scheda lo stesso
// pulsante avvia il servizio com'è: il calcio partirebbe a soldi veri.
// ===========================================================================

describe('scheda tennis: la conferma «soldi veri» non cambia significato sotto il dito', () => {
    function vmSafeFermo() {
        const v = vm();
        v.bots[1] = {
            ...v.bots[1], stato: 'stopped', inCorsa: false,
            params: {
                stake: { backSize: 5, laySize: 2 },
                strategy_modes: { tennis: 'paper', base: 'live' },
                variants: ['base', 'tennis'],
                auto_trade_tennis: false,
            },
        } as typeof v.bots[1];
        return v;
    }

    it('armata nella scheda tennis, uscendo dalla scheda si DISARMA', () => {
        mVm.mockReturnValue(vmSafeFermo());
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        fireEvent.click(s.getByTestId('cr-avvia-live-safe-tennis'));
        expect(s.queryByTestId('cr-conferma-avvio-live-safe-tennis')).not.toBeNull();

        // via il filtro: i pulsanti tornano a voler dire «questa strategia»
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.queryByTestId('cr-conferma-avvio-live-safe-tennis')).toBeNull();
        expect(s.queryByTestId('cr-avvia-live-safe-tennis')).not.toBeNull();
    });

    it('il freno d’emergenza resta su TUTTI i bot, anche quelli nascosti dal filtro', () => {
        const v = vmSafeFermo();
        v.bots[0] = { ...v.bots[0], modalita: 'live', inCorsa: true, stato: 'running' } as typeof v.bots[0];
        mVm.mockReturnValue(v);
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        // Omega non ha una riga, ma è acceso: il freno lo deve vedere
        expect(s.queryByTestId('cr-bot-riga-omega')).toBeNull();
        expect((s.getByTestId('cr-ferma-tutti') as HTMLButtonElement).disabled).toBe(false);
        expect(s.getByTestId('cr-quanti-live').textContent).toMatch(/1 con soldi veri/);
    });

    it('se il calcio sta gia’ operando con soldi veri, la scheda tennis LO DICE', () => {
        const v = vmSafeFermo();
        v.bots[1] = {
            ...v.bots[1], modalita: 'live', inCorsa: true, stato: 'running',
            modiStrategia: { tennis: 'live', base: 'live' },
        } as typeof v.bots[1];
        mVm.mockReturnValue(v);
        const s = mostra();
        fireEvent.click(s.getByTestId('cr-filtro-tennis'));
        expect(s.getByTestId('cr-tennis-altre-live').textContent).toMatch(/base/);
    });
});

// ===========================================================================
// 16/09 — «SE CHIUDO IO, IL BOT DEVE SAPERLO» e le PROPOSTE DI OMEGA.
//
// Due ordini dell'utente della stessa sera, montati sulla stessa pagina:
//   · il cash out globale della partita, con il badge che lo dichiara;
//   · le uscite di Omega che diventano proposte da approvare.
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · togliere il montaggio di `CashOutPartita` dalla scheda partita;
//   · non passare `statoChiusura` alla scheda (badge sempre spento);
//   · mostrare l'elenco Omega vuoto senza dichiarare l'errore della RPC.
// ===========================================================================
/** una riga di SAFE ancora a mercato su E1: e' quello che il cash out globale
 *  chiuderebbe. Le chiavi sono quelle vere di `OperazionePartita`. */
function opsSafeVive() {
    return new Map([['E1', [{
        bot: 'safe' as const, id: 4821, selezione: 'Under 3.5', lato: 'back' as const,
        prezzo: 1.38, size: 3, stato: 'open', pnl: null, modalita: 'paper' as const,
        at: '2026-09-14T14:40:00Z', quale: 'tennis',
        ordine: {
            status: 'open', side: 'back', price: 1.38, size: 3,
            size_requested: 3, size_matched: 3, size_remaining: 0,
            avg_price_matched: 1.38, betfair_updated_at: null, meta: null,
        },
    }]]]) as ReturnType<typeof useControlRoom>['operazioni'];
}

describe('la partita si chiude TUTTA, e il bot lo sa', () => {
    it('la scheda della partita live porta il gesto, con l’event_id giusto', async () => {
        mVm.mockReturnValue(vm({ operazioni: opsSafeVive() }));
        const s = mostra();
        await apri(s, 'live');
        const g = s.getByTestId('cr-cashout-partita');
        expect(g.getAttribute('data-event-id')).toBe('E1');
        expect(g.getAttribute('data-chiusa')).toBe('0');
        expect(s.getByTestId('cr-cashout-partita-avvia')).toBeTruthy();
    });

    it('quando il servizio la dichiara chiusa: badge acceso e «Riprendi» al posto del cash out', async () => {
        mVm.mockReturnValue(vm({
            statoChiusura: () => ({
                chiusa: true, fonte: 'righe',
                marcatore: { quando: '2026-09-14T14:30:00Z', come: 'cashout_event', dettaglio: {} },
            }),
        }));
        const s = mostra();
        await apri(s, 'live');
        expect(s.getByTestId('cr-badge-chiusa-da-te')).toBeTruthy();
        expect(s.queryByTestId('cr-cashout-partita-avvia')).toBeNull();
        expect(s.getByTestId('cr-riprendi-partita')).toBeTruthy();
    });

    it('senza posizioni vive del bot il gesto e SPENTO, e dice perche', async () => {
        mVm.mockReturnValue(vm());        // `operazioni` vuota: nessuna riga di Safe
        const s = mostra();
        await apri(s, 'live');
        expect((s.getByTestId('cr-cashout-partita-avvia') as HTMLButtonElement).disabled).toBe(true);
        expect(s.getByTestId('cr-cashout-partita-bloccato').textContent)
            .toMatch(/nessuna posizione viva/);
    });

    it('il gesto chiama il servizio con l’event_id della partita', async () => {
        const cashOutEvento = vi.fn().mockResolvedValue(undefined);
        mVm.mockReturnValue(vm({ cashOutEvento, operazioni: opsSafeVive() }));
        const s = mostra();
        await apri(s, 'live');
        fireEvent.click(s.getByTestId('cr-cashout-partita-avvia'));
        // Safe e in paper nel modello finto: un clic solo basta
        await vi.waitFor(() => expect(cashOutEvento).toHaveBeenCalledWith('E1'));
    });
});

describe('le uscite di OMEGA arrivano nel nastro come proposte', () => {
    const propostaOmega = {
        id: 77, kind: 'cashout', created_at: '2026-09-14T14:50:00Z', updated_at: null,
        payload: {
            trade_id: 4821, event_id: 'E1', event_name: 'Milan – Inter',
            selection_name: '0 - 2', side: 'back' as const, entry_side: 'lay' as const,
            entry_price: 65, size: 1, price_at_decision: 31,
            motivo_codice: 'blocca_il_profitto', profitto_bloccabile: 0.94,
            back_price: 31, back_size: 2.1, ev_tenere: 0.42, p_evento: 0.0123,
            meglio_aspettare: false, minute: 58, score: '1-0', mode: 'paper' as const,
            decided_at: '2026-09-14T14:50:00Z', proposed_at: '2026-09-14T14:50:30Z',
        },
    };

    it('la scheda di Omega compare nel nastro e dice di chi e', () => {
        mVm.mockReturnValue(vm({ proposteOmega: [propostaOmega] }));
        const s = mostra();
        const card = s.getByTestId('cr-proposta-omega');
        expect(card.textContent).toMatch(/Omega/);
        expect(card.getAttribute('data-approvabile')).toBe('1');
    });

    it('il conteggio in testata somma le proposte dei due bot', () => {
        mVm.mockReturnValue(vm({ proposteOmega: [propostaOmega] }));
        const s = mostra();
        expect(within(s.getByTestId('cr-nastro')).getByText(/1 in attesa/)).toBeTruthy();
    });

    it('con una proposta di Omega il nastro NON dice «nessuna uscita da decidere»', () => {
        mVm.mockReturnValue(vm({ proposteOmega: [propostaOmega] }));
        const s = mostra();
        expect(s.getByTestId('cr-nastro').textContent).not.toMatch(/Nessuna uscita da decidere/);
    });

    it('migrazione non applicata: si DICHIARA perche l’elenco e vuoto', () => {
        mVm.mockReturnValue(vm({
            proposteOmega: [],
            erroreProposteOmega: 'function public.get_omega_proposte() does not exist',
        }));
        const s = mostra();
        const box = s.getByTestId('cr-proposte-omega-errore');
        expect(box.textContent).toMatch(/does not exist/);
        expect(box.textContent).toMatch(/non vuol dire che non ce ne siano/);
    });
});
