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
import { righeInterruttori, type StatoBotPlancia } from './righeBot';
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

// ===========================================================================
// TASK 2 (18/09) — «non è immediata l'attivazione dal pulsante»: la riga deve
// dire SUBITO «comando inviato — in attesa del servizio», MAI «in esecuzione»
// prima che il servizio confermi, e un avviso arancione se il tempo
// ragionevole passa senza conferma.
// ===========================================================================
describe('TASK 2 — stato onesto dopo un clic, mai finto immediato', () => {
    it('subito dopo il clic compare «comando inviato», non uno stato finto', async () => {
        const c = comandiFinti();
        const s = mostra([riga()], c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-avvia-paper-safe-base')); });
        expect(s.getByTestId('cr-comando-inviato-safe-base').textContent)
            .toMatch(/comando inviato — in attesa del servizio/i);
        // mai una parola che promette un esito non ancora confermato
        expect(s.getByTestId('cr-comando-inviato-safe-base').textContent).not.toMatch(/in esecuzione/i);
        // l'attesa TIPICA di Safe (2 s, letta da bot_service.py) e' dichiarata
        expect(s.getByTestId('cr-comando-inviato-safe-base').textContent).toMatch(/tipica/i);
    });

    it('appena la riga conferma (nuovo giro di ricarica) il «comando inviato» sparisce da solo', async () => {
        const c = comandiFinti();
        const s = mostra([riga()], c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-avvia-paper-safe-base')); });
        expect(s.getByTestId('cr-comando-inviato-safe-base')).toBeTruthy();

        // il prossimo giro di `vm.bots` porta la riga confermata: acceso=true,
        // modalita='paper', esattamente quello che il clic aveva chiesto
        s.rerender(
            <PannelloBot
                righe={[riga({ acceso: true, stato: 'running', modalita: 'paper' })]}
                importi={SENZA_IMPORTI} comandi={c}
            />,
        );
        expect(s.queryByTestId('cr-comando-inviato-safe-base')).toBeNull();
        expect(s.queryByTestId('cr-comando-non-confermato-safe-base')).toBeNull();
    });

    it('senza conferma entro l\'attesa ragionevole: avviso arancione, non silenzio', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra([riga()], c);
        fireEvent.click(s.getByTestId('cr-avvia-paper-safe-base'));
        // Safe: tipica 2 s, ragionevole = max(10, 2*3) = 10 s. La riga NON
        // conferma mai (stessa `riga()` di sempre, nessun rerender): dopo 10 s
        // e' disonesto restare zitti.
        act(() => { vi.advanceTimersByTime(10_500); });
        const avviso = s.getByTestId('cr-comando-non-confermato-safe-base');
        expect(avviso.textContent).toMatch(/non ha ancora confermato/i);
        expect(s.queryByTestId('cr-comando-inviato-safe-base')).toBeNull();
        vi.useRealTimers();
    });

    it('un errore del comando toglie subito il «comando inviato»: l\'errore e\' gia\' chiaro altrove', async () => {
        // `esegui` ripropaga l'errore (lo gestisce chi chiama i comandi veri,
        // `ControlRoom.tsx::avvolgi`): il clic del test lo lascia come
        // rifiuto NON gestito a livello di runtime, esattamente come in
        // produzione (il bottone non e' mai `await`-ato dal DOM). Qui si
        // sopprime SOLO il rumore del test runner (Node, non il `window` di
        // jsdom: e' li' che vitest ascolta), non l'errore stesso: la riga di
        // sotto verifica comunque che il comando sia stato chiamato e che il
        // «comando inviato» sia sparito.
        const acchiappa = () => { /* atteso: vedi commento sopra */ };
        process.on('unhandledRejection', acchiappa);
        try {
            const c = comandiFinti();
            (c.accendi as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('RPC fallita'));
            const s = mostra([riga()], c);
            await act(async () => {
                fireEvent.click(s.getByTestId('cr-avvia-paper-safe-base'));
                await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
            });
            expect(c.accendi).toHaveBeenCalledWith('safe-base', 'paper');
            expect(s.queryByTestId('cr-comando-inviato-safe-base')).toBeNull();
        } finally {
            process.removeListener('unhandledRejection', acchiappa);
        }
    });
});

// ===========================================================================
// TASK 3 (18/09) — due tendine indipendenti, Calcio e Tennis: mai una lista
// mista. Stato aperto/chiuso in localStorage, comandato SOLO dall'utente.
// ===========================================================================
describe('TASK 3 — due tendine, Calcio e Tennis, mai una lista mista', () => {
    beforeEach(() => { window.localStorage.clear(); });

    function rigaTennis(over: Partial<RigaInterruttore> = {}): RigaInterruttore {
        return riga({
            id: 'tennis_scalper', bot: 'tennis_scalper', etichetta: 'Scalper tennis', ...over,
        });
    }

    it('calcio e tennis stanno in DUE tendine separate, mai nella stessa lista', () => {
        const s = mostra([riga(), rigaTennis()], comandiFinti());
        expect(s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger').textContent).toMatch(/BOT CALCIO \(1\)/);
        expect(s.getByTestId('cr-pannello-bot-gruppo-tennis-trigger').textContent).toMatch(/BOT TENNIS \(1\)/);
        // la riga di calcio e' nel contenuto del SUO gruppo, non nell'altro
        const contenutoCalcio = s.getByTestId('cr-pannello-bot-gruppo-calcio-contenuto');
        const contenutoTennis = s.getByTestId('cr-pannello-bot-gruppo-tennis-contenuto');
        expect(within(contenutoCalcio).getByTestId('cr-bot-riga-safe-base')).toBeTruthy();
        expect(within(contenutoCalcio).queryByTestId('cr-bot-riga-tennis_scalper')).toBeNull();
        expect(within(contenutoTennis).getByTestId('cr-bot-riga-tennis_scalper')).toBeTruthy();
        expect(within(contenutoTennis).queryByTestId('cr-bot-riga-safe-base')).toBeNull();
    });

    it('di default (nessuna preferenza salvata) sono APERTE: nessuna regressione al primo avvio', () => {
        const s = mostra([riga(), rigaTennis()], comandiFinti());
        expect(s.getByTestId('cr-bot-riga-safe-base')).toBeTruthy();
        expect(s.getByTestId('cr-bot-riga-tennis_scalper')).toBeTruthy();
    });

    it('chiudere una tendina la ricorda in localStorage, e SOLO quella cambia', () => {
        const s = mostra([riga(), rigaTennis()], comandiFinti());
        fireEvent.click(s.getByTestId('cr-pannello-bot-gruppo-tennis-trigger'));
        expect(s.queryByTestId('cr-bot-riga-tennis_scalper')).toBeNull();
        // calcio resta aperta: le due tendine sono INDIPENDENTI
        expect(s.getByTestId('cr-bot-riga-safe-base')).toBeTruthy();
        const salvato = JSON.parse(window.localStorage.getItem('cr-pannello-bot-aperto-v1') ?? '{}');
        expect(salvato.tennis).toBe(false);
        expect(salvato.calcio).not.toBe(false);
    });

    it('la preferenza salvata sopravvive a un nuovo montaggio (persistenza per-viewer)', () => {
        window.localStorage.setItem('cr-pannello-bot-aperto-v1', JSON.stringify({ tennis: false }));
        const s = mostra([riga(), rigaTennis()], comandiFinti());
        expect(s.queryByTestId('cr-bot-riga-tennis_scalper')).toBeNull();
        expect(s.getByTestId('cr-bot-riga-safe-base')).toBeTruthy();
    });

    it('REGOLA 11 (eccezione del coordinatore): un\'anomalia nel gruppo chiuso non lo riapre da sola', () => {
        window.localStorage.setItem('cr-pannello-bot-aperto-v1', JSON.stringify({ tennis: false }));
        const s = mostra([riga(), rigaTennis({
            acceso: true, stato: 'running', motivoBlocco: 'tetto raggiunto',
        })], comandiFinti());
        // il pallino nell'intestazione segnala l'anomalia, ma la tendina resta
        // chiusa finche' non e' l'utente a cliccarla
        expect(s.queryByTestId('cr-bot-riga-tennis_scalper')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// 24/09 — «OGNI strumento che propone ingressi a mercato deve avere sia la
// versione PAPER che LIVE» (utente). Le righe `safe-model` e `safe-manual`
// nascono dal modello condiviso (`righeInterruttori`, lo stesso della Control
// Room) e hanno lo STESSO doppio consenso delle altre.
// ---------------------------------------------------------------------------
describe('24/09 — Safe modello e Safe a mano nella plancia', () => {
    const SAFE_IN_CORSA: StatoBotPlancia = {
        bot: 'safe', inCorsa: true, modalita: 'live',
        varianti: ['tennis'], modiStrategia: { tennis: 'live', model: 'paper' },
        stato: 'running', etaPushS: 1, motivoBlocco: null, tettoPartite: null,
        partiteEsposte: null, stopFermaSoloAperture: true, fermatoAllAvvioAt: null,
    };

    it('le due righe ci sono, in prova, con le parole chiare', () => {
        const righe = righeInterruttori([SAFE_IN_CORSA], 'calcio');
        const s = mostra(righe, comandiFinti());
        expect(s.getByTestId('cr-bot-riga-safe-model')).toBeTruthy();
        expect(s.getByTestId('cr-bot-riga-safe-manual')).toBeTruthy();
        expect(s.getByTestId('cr-bot-modalita-safe-model').textContent).toBe('prova');
        // `manual` non scritto: prova, mai ereditato dal servizio in live
        expect(s.getByTestId('cr-bot-modalita-safe-manual').textContent).toBe('prova');
        expect(within(s.getByTestId('cr-bot-riga-safe-model')).getByTitle('opportunità del modello che approvo'))
            .toBeTruthy();
        expect(within(s.getByTestId('cr-bot-riga-safe-manual')).getByTitle('ordini a mano dalla scheda'))
            .toBeTruthy();
    });

    it('«Safe modello» a soldi veri: doppio consenso, poi cambiaModalita(safe-model, live)', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra(righeInterruttori([SAFE_IN_CORSA], 'calcio'), c);
        fireEvent.click(s.getByTestId('cr-a-live-safe-model'));
        expect(c.cambiaModalita).not.toHaveBeenCalled();
        expect(s.getByTestId('cr-avviso-live-safe-model').textContent)
            .toContain('opportunità del modello che approvo');
        // doppio clic immediato: inerte
        fireEvent.click(s.getByTestId('cr-conferma-live-safe-model'));
        expect(c.cambiaModalita).not.toHaveBeenCalled();
        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-conferma-live-safe-model'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe-model', 'live');
        expect(c.cambiaModalita).toHaveBeenCalledTimes(1);
    });

    it('«Safe a mano» a soldi veri: stessa difesa, chiave giusta', () => {
        vi.useFakeTimers();
        const c = comandiFinti();
        const s = mostra(righeInterruttori([SAFE_IN_CORSA], 'calcio'), c);
        fireEvent.click(s.getByTestId('cr-a-live-safe-manual'));
        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-conferma-live-safe-manual'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe-manual', 'live');
        expect(c.cambiaModalita).not.toHaveBeenCalledWith('safe-model', expect.anything());
    });

    it('tornare in prova da «Safe modello» e immediato', () => {
        const c = comandiFinti();
        const live: StatoBotPlancia = {
            ...SAFE_IN_CORSA, modiStrategia: { tennis: 'live', model: 'live' },
        };
        const s = mostra(righeInterruttori([live], 'calcio'), c);
        expect(s.getByTestId('cr-bot-modalita-safe-model').textContent).toBe('soldi veri');
        fireEvent.click(s.getByTestId('cr-a-paper-safe-model'));
        expect(c.cambiaModalita).toHaveBeenCalledWith('safe-model', 'paper');
    });
});
