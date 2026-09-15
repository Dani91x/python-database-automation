// ============================================================================
// PannelloBot.test.tsx — i comandi che accendono e spengono i bot.
//
// Nasce da un reperto della review 15/09: il doppio consenso «soldi veri» non
// era provato da NESSUNA asserzione. I test di pagina montavano il pannello
// col vero `creaComandi`, quindi potevano solo guardare i pixel; qui `comandi`
// è una prop, e si può verificare CHE COSA viene davvero chiamato.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, within, fireEvent, act } from '@testing-library/react';
import { PannelloBot, type ComandiBot, type CampoImporto } from './PannelloBot';
import type { StatoBot } from './useControlRoom';
import type { Bot } from '@/lib/controlRoom';

function bot(over: Partial<StatoBot> = {}): StatoBot {
    return {
        bot: 'safe', modalita: 'paper', inCorsa: false, battitoAt: null,
        canale: 'connected', etaPushS: 1, freschezzaPush: 'fresca',
        varianti: null, modiStrategia: null,
        stato: 'stopped', params: { stake: { backSize: 3 } }, obiettivoGiorno: null,
        // quello che il SERVIZIO dichiara: di serie non dichiara niente, ed è
        // giusto che la pagina in quel caso non scriva niente.
        motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: false,
        ...over,
    } as StatoBot;
}

const IMPORTI_VUOTI: Record<Bot, CampoImporto[]> = { omega: [], safe: [], mike: [] };

function comandiFinti(): ComandiBot {
    return {
        avvia: vi.fn(async () => {}),
        ferma: vi.fn(async () => {}),
        cambiaModalita: vi.fn(async () => {}),
        cambiaImporto: vi.fn(async () => {}),
    };
}

function mostra(bots: StatoBot[], comandi: ComandiBot, importi = IMPORTI_VUOTI) {
    return render(<PannelloBot bots={bots} importi={importi} comandi={comandi} />);
}

beforeEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });

// ---------------------------------------------------------------------------

describe('doppio consenso per i soldi veri — che cosa viene DAVVERO chiamato', () => {
    it('il primo clic NON avvia niente: arma soltanto', () => {
        const c = comandiFinti();
        const s = mostra([bot()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe'));
        expect(c.avvia).not.toHaveBeenCalled();
        expect(s.getByTestId('cr-conferma-avvio-live-safe')).toBeTruthy();
    });

    it('LA CONFERMA È INERTE per la finestra del doppio clic', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([bot()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe'));

        // secondo clic immediato: è il doppio clic che aggirava tutto
        const conferma = s.getByTestId('cr-conferma-avvio-live-safe');
        expect(conferma).toHaveProperty('disabled', true);
        fireEvent.click(conferma);
        expect(c.avvia).not.toHaveBeenCalled();
    });

    it('passata l’attesa, la conferma funziona e avvia in LIVE', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([bot()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe'));
        act(() => { vi.advanceTimersByTime(500); });

        fireEvent.click(s.getByTestId('cr-conferma-avvio-live-safe'));
        expect(c.avvia).toHaveBeenCalledWith('safe', 'live');
    });

    it('avviare IN PROVA non chiede niente e non tocca il live', () => {
        const c = comandiFinti();
        const s = mostra([bot()], c);
        fireEvent.click(s.getByTestId('cr-avvia-paper-safe'));
        expect(c.avvia).toHaveBeenCalledWith('safe', 'paper');
        expect(c.avvia).toHaveBeenCalledTimes(1);
    });

    it('passare a soldi veri A BOT ACCESO ha la stessa difesa', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([bot({ inCorsa: true, stato: 'running', modalita: 'paper' })], c);
        fireEvent.click(s.getByTestId('cr-a-live-safe'));
        fireEvent.click(s.getByTestId('cr-conferma-live-safe'));
        expect(c.cambiaModalita).not.toHaveBeenCalled();

        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-conferma-live-safe'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe', 'live');
    });

    it('TORNARE IN PROVA è immediato: toglie rischio, non lo aggiunge', () => {
        const c = comandiFinti();
        const s = mostra([bot({ inCorsa: true, stato: 'running', modalita: 'live' })], c);
        fireEvent.click(s.getByTestId('cr-a-paper-safe'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe', 'paper');
    });
});

describe('FERMA TUTTI — un freno d’emergenza li prova TUTTI', () => {
    const tre = () => [
        bot({ bot: 'omega', inCorsa: true, stato: 'running' }),
        bot({ bot: 'safe', inCorsa: true, stato: 'running' }),
        bot({ bot: 'mike', inCorsa: true, stato: 'running', modalita: 'live' }),
    ];

    it('ferma tutti i bot accesi, uno per uno', async () => {
        const c = comandiFinti();
        const s = mostra(tre(), c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });
        expect(c.ferma).toHaveBeenCalledTimes(3);
        expect((c.ferma as ReturnType<typeof vi.fn>).mock.calls.map((x) => x[0]))
            .toEqual(['omega', 'safe', 'mike']);
    });

    it('SE IL PRIMO FALLISCE, GLI ALTRI VENGONO FERMATI LO STESSO', async () => {
        const c = comandiFinti();
        (c.ferma as ReturnType<typeof vi.fn>).mockImplementation(async (b: Bot) => {
            if (b === 'omega') throw new Error('RPC in errore');
        });
        const s = mostra(tre(), c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });

        // Mike è l'ultimo della fila ed è quello in LIVE: prima si fermava il
        // ciclo e non veniva nemmeno chiamato.
        expect((c.ferma as ReturnType<typeof vi.fn>).mock.calls.map((x) => x[0]))
            .toEqual(['omega', 'safe', 'mike']);
    });

    it('e DICE quale non si è fermato, invece di lasciar credere che sia tutto spento', async () => {
        const c = comandiFinti();
        (c.ferma as ReturnType<typeof vi.fn>).mockImplementation(async (b: Bot) => {
            if (b === 'mike') throw new Error('rete giù');
        });
        const s = mostra(tre(), c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });

        const avviso = s.getByTestId('cr-non-fermati');
        expect(avviso.textContent).toMatch(/NON si è fermato/i);
        expect(avviso.textContent).toMatch(/Mike/);
        expect(avviso.textContent).toMatch(/stanno ancora operando/i);
    });

    it('se si fermano tutti non compare nessun allarme', async () => {
        const c = comandiFinti();
        const s = mostra(tre(), c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });
        expect(s.queryByTestId('cr-non-fermati')).toBeNull();
    });

    it('è spento se non c’è niente da fermare', () => {
        const s = mostra([bot()], comandiFinti());
        expect(s.getByTestId('cr-ferma-tutti')).toHaveProperty('disabled', true);
    });
});

describe('importi — si salva solo ciò che si è potuto leggere', () => {
    const conValore: Record<Bot, CampoImporto[]> = {
        ...IMPORTI_VUOTI,
        safe: [{ chiave: 'stake.backSize', etichetta: 'punta', valore: 3 }],
    };
    const senzaValore: Record<Bot, CampoImporto[]> = {
        ...IMPORTI_VUOTI,
        safe: [{ chiave: 'stake.backSize', etichetta: 'punta', valore: null }],
    };

    it('con il valore noto si può salvare, e arriva la chiave giusta', () => {
        const c = comandiFinti();
        const s = mostra([bot()], c, conValore);
        fireEvent.change(s.getByTestId('cr-importo-safe-stake-backSize'), { target: { value: '5' } });
        fireEvent.click(s.getByTestId('cr-importo-safe-stake-backSize-salva'));
        expect(c.cambiaImporto).toHaveBeenCalledWith('safe', 'stake.backSize', 5);
    });

    it('VALORE CORRENTE NON LETTO: nessun pulsante salva, e la ragione è scritta', () => {
        const c = comandiFinti();
        const s = mostra([bot()], c, senzaValore);
        fireEvent.change(s.getByTestId('cr-importo-safe-stake-backSize'), { target: { value: '5' } });
        expect(s.queryByTestId('cr-importo-safe-stake-backSize-salva')).toBeNull();
        expect(s.getByTestId('cr-importo-safe-stake-backSize-bloccato').textContent)
            .toMatch(/sostituirebbe/i);
        expect(c.cambiaImporto).not.toHaveBeenCalled();
    });

    it('un importo sotto il centesimo non si salva', () => {
        const s = mostra([bot()], comandiFinti(), conValore);
        fireEvent.change(s.getByTestId('cr-importo-safe-stake-backSize'), { target: { value: '0' } });
        expect(s.queryByTestId('cr-importo-safe-stake-backSize-salva')).toBeNull();
    });
});

describe('quello che il pannello DICE dello stato', () => {
    it('«sta fermandosi» non è «fermo»', () => {
        const s = mostra([bot({ inCorsa: true, stato: 'stopping' })], comandiFinti());
        expect(s.getByTestId('cr-bot-stato-safe').textContent).toMatch(/sta fermandosi/i);
    });

    it('conta i bot che usano soldi veri', () => {
        const s = mostra([
            bot({ bot: 'omega', inCorsa: true, stato: 'running', modalita: 'paper' }),
            bot({ bot: 'safe', inCorsa: true, stato: 'running', modalita: 'live' }),
        ], comandiFinti());
        expect(within(s.getByTestId('cr-pannello-bot')).getByTestId('cr-quanti-live').textContent)
            .toMatch(/1 con soldi veri/);
    });

    it('nessun bot in live: nessun contatore rosso (niente rumore inutile)', () => {
        const s = mostra([bot({ inCorsa: true, stato: 'running' })], comandiFinti());
        expect(s.queryByTestId('cr-quanti-live')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// ⚠️ 15/09 — PERCHÉ IL BOT NON APRE
//
// Il trader ha visto Mike «fermo» mentre era vivissimo: il tetto delle partite
// era pieno, e quel tetto sommava paper e live. Il motivo non era scritto da
// nessuna parte, e un bot acceso che non apre e non dice perché è
// indistinguibile da un bot rotto. Il motivo lo DICHIARA il servizio: la
// pagina lo riporta e basta, non lo deduce.
// ---------------------------------------------------------------------------

describe('un bot acceso che non apre deve dire perché', () => {
    it('riporta il motivo dichiarato dal servizio, parola per parola', () => {
        const s = mostra([bot({
            bot: 'mike', inCorsa: true, stato: 'running',
            motivoBlocco: 'tetto partite raggiunto: 2 su 2 in live',
            tettoPartite: 2, partiteEsposte: 2,
        })], comandiFinti());
        const riga = s.getByTestId('cr-motivo-blocco-mike');
        expect(riga.textContent).toMatch(/tetto partite raggiunto: 2 su 2 in live/);
        expect(riga.textContent).toMatch(/2\/2/);
    });

    it('nessun blocco dichiarato: la pagina non inventa niente', () => {
        const s = mostra([bot({ bot: 'mike', inCorsa: true, stato: 'running' })], comandiFinti());
        expect(s.queryByTestId('cr-motivo-blocco-mike')).toBeNull();
    });

    it('un bot FERMO non parla di blocchi: non sta aprendo perché è spento', () => {
        const s = mostra([bot({
            bot: 'mike', inCorsa: false, stato: 'stopped',
            motivoBlocco: 'tetto partite raggiunto: 2 su 2 in live',
        })], comandiFinti());
        expect(s.queryByTestId('cr-motivo-blocco-mike')).toBeNull();
    });

    it('il tetto non letto non diventa uno 0/0 inventato', () => {
        const s = mostra([bot({
            bot: 'mike', inCorsa: true, stato: 'running',
            motivoBlocco: 'tetto partite raggiunto',
            tettoPartite: null, partiteEsposte: null,
        })], comandiFinti());
        expect(s.getByTestId('cr-motivo-blocco-mike').textContent).not.toMatch(/0\/0/);
    });
});

describe('«ferma» deve dire che cosa ferma davvero', () => {
    it('quando il servizio dichiara che toglie solo le aperture, il pannello lo scrive', () => {
        const s = mostra([bot({
            bot: 'mike', inCorsa: true, stato: 'running', stopFermaSoloAperture: true,
        })], comandiFinti());
        expect(s.getByTestId('cr-cosa-ferma-mike').textContent)
            .toMatch(/ferma le aperture, non le uscite/i);
        expect(s.getByTestId('cr-ferma-mike').getAttribute('title'))
            .toMatch(/green.?up|cash out|regolamento/i);
    });

    it('se il servizio non lo dichiara, non si promette niente', () => {
        const s = mostra([bot({ bot: 'mike', inCorsa: true, stato: 'running' })], comandiFinti());
        expect(s.queryByTestId('cr-cosa-ferma-mike')).toBeNull();
    });
});
