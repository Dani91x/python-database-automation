// ============================================================================
// PannelloBot.test.tsx — i comandi che accendono e spengono i bot.
//
// Nasce da un reperto della review 15/09: il doppio consenso «soldi veri» non
// era provato da NESSUNA asserzione. I test di pagina montavano il pannello
// coi comandi veri, quindi potevano solo guardare i pixel; qui `comandi` è una
// prop, e si può verificare CHE COSA viene davvero chiamato.
//
// ⚠️ 16/09 — UNA RIGA = UN INTERRUTTORE, non un processo: Safe ha quattro
// strategie e quattro righe (`safe-base`, `safe-esatto`, `safe-punta`,
// `safe-tennis`), Omega e Mike una ciascuno.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, within, fireEvent, act } from '@testing-library/react';
import { PannelloBot, type RigaInterruttore } from './PannelloBot';
import type { CampoImporto, ComandiInterruttori, InterruttoreId } from '@/lib/interruttori';
import type { Bot } from '@/lib/controlRoom';

function riga(over: Partial<RigaInterruttore> = {}): RigaInterruttore {
    return {
        id: 'safe-base', bot: 'safe', etichetta: 'Safe base',
        acceso: false, modalita: 'paper', statoNoto: true, stato: 'stopped',
        etaPushS: 1,
        // quello che il SERVIZIO dichiara: di serie non dichiara niente, ed è
        // giusto che la pagina in quel caso non scriva niente.
        motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: false, fermatoAllAvvioAt: null,
        primaDelBot: true,
        ...over,
    };
}

const SENZA_IMPORTI: Partial<Record<InterruttoreId, CampoImporto[]>> = {};

function comandiFinti(): ComandiInterruttori {
    return {
        accendi: vi.fn(async () => {}),
        spegni: vi.fn(async () => {}),
        cambiaModalita: vi.fn(async () => {}),
        cambiaImporto: vi.fn(async () => {}),
        fermaBot: vi.fn(async () => {}),
        scriviAccensioni: vi.fn(async () => {}),
        cambiaModalitaServizio: vi.fn(async () => {}),
    };
}

function mostra(
    righe: RigaInterruttore[], comandi: ComandiInterruttori,
    importi = SENZA_IMPORTI,
    serviziAccesi?: { bot: Bot; modalita: 'paper' | 'live' | null }[],
) {
    return render(
        <PannelloBot righe={righe} importi={importi} comandi={comandi}
            serviziAccesi={serviziAccesi} />,
    );
}

beforeEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });

// ---------------------------------------------------------------------------

describe('doppio consenso per i soldi veri — che cosa viene DAVVERO chiamato', () => {
    it('il primo clic NON avvia niente: arma soltanto', () => {
        const c = comandiFinti();
        const s = mostra([riga()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe-base'));
        expect(c.accendi).not.toHaveBeenCalled();
        expect(s.getByTestId('cr-conferma-avvio-live-safe-base')).toBeTruthy();
    });

    it('LA CONFERMA È INERTE per la finestra del doppio clic', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([riga()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe-base'));

        // secondo clic immediato: è il doppio clic che aggirava tutto
        const conferma = s.getByTestId('cr-conferma-avvio-live-safe-base');
        expect(conferma).toHaveProperty('disabled', true);
        fireEvent.click(conferma);
        expect(c.accendi).not.toHaveBeenCalled();
    });

    it('passata l’attesa, la conferma funziona e avvia in LIVE', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([riga()], c);
        fireEvent.click(s.getByTestId('cr-avvia-live-safe-base'));
        act(() => { vi.advanceTimersByTime(500); });

        fireEvent.click(s.getByTestId('cr-conferma-avvio-live-safe-base'));
        expect(c.accendi).toHaveBeenCalledWith('safe-base', 'live');
    });

    it('avviare IN PROVA non chiede niente e non tocca il live', () => {
        const c = comandiFinti();
        const s = mostra([riga()], c);
        fireEvent.click(s.getByTestId('cr-avvia-paper-safe-base'));
        expect(c.accendi).toHaveBeenCalledWith('safe-base', 'paper');
        expect(c.accendi).toHaveBeenCalledTimes(1);
    });

    it('passare a soldi veri A STRATEGIA ACCESA ha la stessa difesa', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([riga({ acceso: true, stato: 'running', modalita: 'paper' })], c);
        fireEvent.click(s.getByTestId('cr-a-live-safe-base'));
        fireEvent.click(s.getByTestId('cr-conferma-live-safe-base'));
        expect(c.cambiaModalita).not.toHaveBeenCalled();

        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-conferma-live-safe-base'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe-base', 'live');
    });

    it('TORNARE IN PROVA è immediato: toglie rischio, non lo aggiunge', () => {
        const c = comandiFinti();
        const s = mostra([riga({ acceso: true, stato: 'running', modalita: 'live' })], c);
        fireEvent.click(s.getByTestId('cr-a-paper-safe-base'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe-base', 'paper');
    });

    it('SPEGNERE una strategia chiama `spegni`, non il freno del servizio', () => {
        const c = comandiFinti();
        const s = mostra([riga({ acceso: true, stato: 'running' })], c);
        fireEvent.click(s.getByTestId('cr-ferma-safe-base'));
        expect(c.spegni).toHaveBeenCalledWith('safe-base');
        expect(c.fermaBot).not.toHaveBeenCalled();
    });

    it('ogni strategia ha la SUA riga e i SUOI pulsanti', () => {
        const c = comandiFinti();
        const s = mostra([
            riga({ id: 'safe-base', etichetta: 'Safe base' }),
            riga({ id: 'safe-punta', etichetta: 'Safe punta', primaDelBot: false }),
        ], c);
        fireEvent.click(s.getByTestId('cr-avvia-paper-safe-punta'));
        expect(c.accendi).toHaveBeenCalledWith('safe-punta', 'paper');
        expect(s.getByTestId('cr-bot-riga-safe-base')).toBeTruthy();
        expect(s.getByTestId('cr-bot-riga-safe-punta')).toBeTruthy();
    });
});

describe('FERMA TUTTI — un freno d’emergenza li prova TUTTI', () => {
    const tre: { bot: Bot; modalita: 'paper' | 'live' | null }[] = [
        { bot: 'omega', modalita: 'paper' },
        { bot: 'safe', modalita: 'paper' },
        { bot: 'mike', modalita: 'live' },
    ];

    it('ferma tutti i SERVIZI accesi, uno per uno', async () => {
        const c = comandiFinti();
        const s = mostra([riga()], c, SENZA_IMPORTI, tre);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });
        expect(c.fermaBot).toHaveBeenCalledTimes(3);
        expect((c.fermaBot as ReturnType<typeof vi.fn>).mock.calls.map((x) => x[0]))
            .toEqual(['omega', 'safe', 'mike']);
    });

    it('SE IL PRIMO FALLISCE, GLI ALTRI VENGONO FERMATI LO STESSO', async () => {
        const c = comandiFinti();
        (c.fermaBot as ReturnType<typeof vi.fn>).mockImplementation(async (b: Bot) => {
            if (b === 'omega') throw new Error('RPC in errore');
        });
        const s = mostra([riga()], c, SENZA_IMPORTI, tre);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });

        // Mike è l'ultimo della fila ed è quello in LIVE: prima si fermava il
        // ciclo e non veniva nemmeno chiamato.
        expect((c.fermaBot as ReturnType<typeof vi.fn>).mock.calls.map((x) => x[0]))
            .toEqual(['omega', 'safe', 'mike']);
    });

    it('e DICE quale non si è fermato, invece di lasciar credere che sia tutto spento', async () => {
        const c = comandiFinti();
        (c.fermaBot as ReturnType<typeof vi.fn>).mockImplementation(async (b: Bot) => {
            if (b === 'mike') throw new Error('rete giù');
        });
        const s = mostra([riga()], c, SENZA_IMPORTI, tre);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });

        const avviso = s.getByTestId('cr-non-fermati');
        expect(avviso.textContent).toMatch(/NON si è fermato/i);
        expect(avviso.textContent).toMatch(/Mike/);
        expect(avviso.textContent).toMatch(/stanno ancora operando/i);
    });

    it('se si fermano tutti non compare nessun allarme', async () => {
        const c = comandiFinti();
        const s = mostra([riga()], c, SENZA_IMPORTI, tre);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });
        expect(s.queryByTestId('cr-non-fermati')).toBeNull();
    });

    it('è spento se non c’è niente da fermare', () => {
        const s = mostra([riga()], comandiFinti(), SENZA_IMPORTI, []);
        expect(s.getByTestId('cr-ferma-tutti')).toHaveProperty('disabled', true);
    });
});

describe('importi — si salva solo ciò che si è potuto leggere', () => {
    const conValore = {
        'safe-base': [{ chiave: 'stake.per_strategia.base', etichetta: 'stake base', valore: 3 }],
    } as Partial<Record<InterruttoreId, CampoImporto[]>>;
    const senzaValore = {
        'safe-base': [{ chiave: 'stake.per_strategia.base', etichetta: 'stake base', valore: null }],
    } as Partial<Record<InterruttoreId, CampoImporto[]>>;
    const id = 'cr-importo-safe-base-stake-per-strategia-base';

    it('con il valore noto si può salvare, e arriva la chiave giusta', () => {
        const c = comandiFinti();
        const s = mostra([riga()], c, conValore);
        fireEvent.change(s.getByTestId(id), { target: { value: '5' } });
        fireEvent.click(s.getByTestId(`${id}-salva`));
        expect(c.cambiaImporto).toHaveBeenCalledWith('safe-base', 'stake.per_strategia.base', 5);
    });

    it('VALORE CORRENTE NON LETTO: nessun pulsante salva, e la ragione è scritta', () => {
        const c = comandiFinti();
        const s = mostra([riga()], c, senzaValore);
        fireEvent.change(s.getByTestId(id), { target: { value: '5' } });
        expect(s.queryByTestId(`${id}-salva`)).toBeNull();
        expect(s.getByTestId(`${id}-bloccato`).textContent).toMatch(/sostituirebbe/i);
        expect(c.cambiaImporto).not.toHaveBeenCalled();
    });

    it('un importo sotto il centesimo non si salva', () => {
        const s = mostra([riga()], comandiFinti(), conValore);
        fireEvent.change(s.getByTestId(id), { target: { value: '0' } });
        expect(s.queryByTestId(`${id}-salva`)).toBeNull();
    });

    it('UN IMPORTO EREDITATO SI DICHIARA: finché non è suo, è condiviso', () => {
        const ereditato = {
            'safe-base': [{
                chiave: 'stake.per_strategia.base', etichetta: 'stake base', valore: 2,
                ereditato: 'non ha ancora un importo suo: usa quello per lato (banca).',
            }],
        } as Partial<Record<InterruttoreId, CampoImporto[]>>;
        const s = mostra([riga()], comandiFinti(), ereditato);
        expect(s.getByTestId(`${id}-ereditato`).textContent).toMatch(/per lato/i);
    });
});

describe('quello che il pannello DICE dello stato', () => {
    it('«sta fermandosi» non è «fermo»', () => {
        const s = mostra([riga({ acceso: true, stato: 'stopping' })], comandiFinti());
        expect(s.getByTestId('cr-bot-stato-safe-base').textContent).toMatch(/sta fermandosi/i);
    });

    it('conta i SERVIZI che usano soldi veri', () => {
        const s = mostra([riga()], comandiFinti(), SENZA_IMPORTI, [
            { bot: 'omega', modalita: 'paper' },
            { bot: 'safe', modalita: 'live' },
        ]);
        expect(within(s.getByTestId('cr-pannello-bot')).getByTestId('cr-quanti-live').textContent)
            .toMatch(/1 con soldi veri/);
    });

    it('nessun bot in live: nessun contatore rosso (niente rumore inutile)', () => {
        const s = mostra([riga({ acceso: true, stato: 'running' })], comandiFinti(),
                         SENZA_IMPORTI, [{ bot: 'safe', modalita: 'paper' }]);
        expect(s.queryByTestId('cr-quanti-live')).toBeNull();
    });

    it('STATO NON LETTO: non si comanda un bot di cui non sappiamo niente', () => {
        const s = mostra([riga({ statoNoto: false, stato: 'ignoto' })], comandiFinti());
        expect(s.getByTestId('cr-stato-ignoto-safe-base')).toBeTruthy();
        expect(s.queryByTestId('cr-avvia-paper-safe-base')).toBeNull();
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
    const mike = (over: Partial<RigaInterruttore> = {}) =>
        riga({ id: 'mike', bot: 'mike', etichetta: 'Mike', ...over });

    it('riporta il motivo dichiarato dal servizio, parola per parola', () => {
        const s = mostra([mike({
            acceso: true, stato: 'running',
            motivoBlocco: 'tetto partite raggiunto: 2 su 2 in live',
            tettoPartite: 2, partiteEsposte: 2,
        })], comandiFinti());
        const r = s.getByTestId('cr-motivo-blocco-mike');
        expect(r.textContent).toMatch(/tetto partite raggiunto: 2 su 2 in live/);
        expect(r.textContent).toMatch(/2\/2/);
    });

    it('nessun blocco dichiarato: la pagina non inventa niente', () => {
        const s = mostra([mike({ acceso: true, stato: 'running' })], comandiFinti());
        expect(s.queryByTestId('cr-motivo-blocco-mike')).toBeNull();
    });

    it('un bot FERMO non parla di blocchi: non sta aprendo perché è spento', () => {
        const s = mostra([mike({
            acceso: false, stato: 'stopped',
            motivoBlocco: 'tetto partite raggiunto: 2 su 2 in live',
        })], comandiFinti());
        expect(s.queryByTestId('cr-motivo-blocco-mike')).toBeNull();
    });

    it('il tetto non letto non diventa uno 0/0 inventato', () => {
        const s = mostra([mike({
            acceso: true, stato: 'running', motivoBlocco: 'tetto partite raggiunto',
            tettoPartite: null, partiteEsposte: null,
        })], comandiFinti());
        expect(s.getByTestId('cr-motivo-blocco-mike').textContent).not.toMatch(/0\/0/);
    });
});

describe('«ferma» deve dire che cosa ferma davvero', () => {
    it('quando il servizio dichiara che toglie solo le aperture, il pannello lo scrive', () => {
        const s = mostra([riga({
            id: 'mike', bot: 'mike', etichetta: 'Mike',
            acceso: true, stato: 'running', stopFermaSoloAperture: true,
        })], comandiFinti());
        expect(s.getByTestId('cr-cosa-ferma-mike').textContent)
            .toMatch(/ferma le aperture, non le uscite/i);
        expect(s.getByTestId('cr-ferma-mike').getAttribute('title'))
            .toMatch(/green.?up|cash out|regolamento/i);
    });

    it('se il servizio non lo dichiara, non si promette niente', () => {
        const s = mostra([riga({
            id: 'mike', bot: 'mike', etichetta: 'Mike', acceso: true, stato: 'running',
        })], comandiFinti());
        expect(s.queryByTestId('cr-cosa-ferma-mike')).toBeNull();
    });
});

describe('fermato all\'avvio dell\'app (FASE A, 16/09)', () => {
    const mike = (over: Partial<RigaInterruttore> = {}) =>
        riga({ id: 'mike', bot: 'mike', etichetta: 'Mike', ...over });

    it('lo scrive quando il servizio lo dichiara, e chiede l\'accensione a mano', () => {
        const s = mostra([mike({
            acceso: false, stato: 'stopped', modalita: 'paper',
            fermatoAllAvvioAt: '2026-09-16T07:30:00+00:00',
        })], comandiFinti());
        expect(s.getByTestId('cr-fermato-avvio-mike').textContent)
            .toMatch(/fermato all'avvio dell'app/i);
        expect(s.getByTestId('cr-fermato-avvio-mike').textContent)
            .toMatch(/attivazione manuale richiesta/i);
    });

    it('se il servizio non lo dichiara, la pagina non lo inventa', () => {
        const s = mostra([mike({ acceso: false, stato: 'stopped' })], comandiFinti());
        expect(s.queryByTestId('cr-fermato-avvio-mike')).toBeNull();
    });

    it('sparisce appena il bot viene riacceso dall\'utente', () => {
        const s = mostra([mike({
            acceso: true, stato: 'running',
            fermatoAllAvvioAt: '2026-09-16T07:30:00+00:00',
        })], comandiFinti());
        expect(s.queryByTestId('cr-fermato-avvio-mike')).toBeNull();
    });
});
