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
        etaFeedS: 2, freschezza: 'fresca', latenzaQuoteS: 1, freschezzaQuote: 'fresca',
        soldi: { netPnl: 12.5, liability: 40, investito: 10, aperta: true, bots: ['omega'] },
        target: { valore: 31.2, fonte: 'servizio' },
        avanzamento: 40,
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
        totali: { partite: 1, live: 1, pre: 0, conPosizione: 1, liability: 40, netPnl: 12.5 },
        obiettivo: 250, obiettivoStoricizzato: true, realizzato: 96.4, targetServizio: 31.2,
        bots: [
            { bot: 'omega', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 2, freschezzaPush: 'fresca', varianti: null },
            { bot: 'safe', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 1, freschezzaPush: 'fresca', varianti: null },
            { bot: 'mike', modalita: 'paper', inCorsa: true, battitoAt: null, canale: 'connected', etaPushS: 3, freschezzaPush: 'fresca', varianti: null },
        ],
        posizioni: [],
        copertura: { conDato: 1, senzaDato: 0, totale: 1, pct: 100 },
        freni: { daily_loss_stop: -50, loss_stop_active: false },
        runner: { ts: '2026-09-14T14:59:30Z', mode: 'PAPER', ageS: 30, up: true, streaming: 2 },
        mikeRestingLive: true,
        proposte: [], slippagePct: 2, setSlippagePct: vi.fn(),
        approva: vi.fn(), ignora: vi.fn(),
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

beforeEach(() => { vi.clearAllMocks(); });

// ---------------------------------------------------------------- modalità

describe('modalità — soldi veri o simulati, senza possibilità di equivoco', () => {
    it('tutto in paper: nessun avviso di soldi veri', () => {
        mVm.mockReturnValue(vm());
        mostra();
        expect(screen.queryByTestId('cr-banner-live')).toBeNull();
    });

    it('un solo bot in live: l\'avviso c\'è e NOMINA quel bot', () => {
        const v = vm();
        v.bots[1] = { ...v.bots[1], modalita: 'live' };
        mVm.mockReturnValue(v);
        mostra();
        const banner = screen.getByTestId('cr-banner-live');
        expect(within(banner).getByText(/soldi veri/i)).toBeTruthy();
        expect(within(banner).getByText(/Safe: LIVE/)).toBeTruthy();
    });

    it('in live con varianti: dice QUALI apre, perché «LIVE» da solo sarebbe fuorviante', () => {
        const v = vm();
        v.bots[1] = { ...v.bots[1], modalita: 'live', varianti: ['tennis'] };
        mVm.mockReturnValue(v);
        mostra();
        expect(within(screen.getByTestId('cr-banner-live')).getByText(/apre solo tennis/)).toBeTruthy();
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
    it('in gioco: minuto e punteggio; pre-match: l\'orario', () => {
        mVm.mockReturnValue(vm({
            giornata: [
                ...gruppo([partita()]),
                { campionato: 'Liga', primoKoMs: Date.parse('2026-09-14T19:00:00Z'), partite: [partita({ event_id: 'E2', nome: 'Girona – Betis', campionato: 'Liga', stato: 'pre', minuto: null, punteggio: null, koMs: Date.parse('2026-09-14T19:00:00Z'), soldi: null, avanzamento: null })] },
            ],
        }));
        mostra();
        expect(screen.getByText(/58′/)).toBeTruthy();
        expect(screen.getByText(/1-0/)).toBeTruthy();
        expect(screen.getByText('Girona – Betis')).toBeTruthy();
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
        expect(within(riga).getByText(/Target \*/)).toBeTruthy();
    });

    it('un target del SERVIZIO non porta l\'asterisco', () => {
        mVm.mockReturnValue(vm());
        const riga = mostra().getByTestId('cr-partita');
        expect(within(riga).getByText('Target')).toBeTruthy();
    });

    it('i campionati si leggono nell\'ordine in cui il modello li consegna', () => {
        mVm.mockReturnValue(vm({
            giornata: [
                { campionato: 'Serie A', primoKoMs: 1, partite: [partita()] },
                { campionato: 'Liga', primoKoMs: 2, partite: [partita({ event_id: 'E2', campionato: 'Liga' })] },
            ],
        }));
        const { container } = mostra();
        const titoli = Array.from(container.querySelectorAll('h3')).map((h) => h.textContent?.trim());
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
    it('una posizione LIVE è marcata live e contata a parte', () => {
        mVm.mockReturnValue(vm({
            posizioni: [{
                bot: 'safe', id: 1, eventId: 'E1', partita: 'Rune – Musetti', selezione: 'Rune',
                lato: 'back', prezzo: 1.03, size: 2, liability: 2, modalita: 'live',
                piazzataAt: '2026-09-14T14:50:00Z',
            }],
        }));
        const col = mostra().getByTestId('cr-posizioni');
        expect(within(col).getByText(/1 posizione con soldi veri/)).toBeTruthy();
        expect(within(col).getByText('Punta')).toBeTruthy();
    });

    it('senza posizioni lo dice invece di mostrare una tabella vuota', () => {
        mVm.mockReturnValue(vm());
        expect(within(mostra().getByTestId('cr-posizioni')).getByText(/Nessuna posizione aperta/)).toBeTruthy();
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
        vivo: { prezzo: 1.32, abbinabile: 116.38, ...vivoOver },
        etaQuoteS: eta,
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
        expect(screen.getByText(/non ancora storicizzato/)).toBeTruthy();
    });
});
