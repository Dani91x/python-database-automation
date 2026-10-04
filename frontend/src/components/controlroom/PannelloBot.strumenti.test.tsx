// ============================================================================
// PannelloBot.strumenti.test.tsx - «Safe modello» e «Safe a mano» NON SONO BOT.
//
// Ordine dell'utente (04/10): «fixa le etichette, il trader non puo' essere
// confuso». Le due righe sembravano due bot accesi con un FERMA che non puo'
// mai funzionare. Qui si prova la sola PRESENTAZIONE: niente stato di bot in
// corsa, niente FERMA, non contano fra i bot accesi, e l'unica cosa detta e'
// con che soldi partono gli ordini approvati / fatti a mano.
//
// I finti hanno le chiavi e i tipi di `StatoBotPlancia` / `ComandiInterruttori`.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { PannelloBot } from './PannelloBot';
import { righeInterruttori, type StatoBotPlancia } from './righeBot';
import type { ComandiInterruttori } from '@/lib/interruttori';

function safe(over: Partial<StatoBotPlancia> = {}): StatoBotPlancia {
    return {
        bot: 'safe', inCorsa: true, modalita: 'paper',
        varianti: ['tennis'], modiStrategia: { tennis: 'paper' },
        stato: 'running', etaPushS: 1, motivoBlocco: null, tettoPartite: null,
        partiteEsposte: null, stopFermaSoloAperture: true, fermatoAllAvvioAt: null,
        ...over,
    };
}

/** i quattro stati del servizio Safe che il brief chiede di coprire */
const STATI: Record<string, StatoBotPlancia> = {
    corsa_paper: safe(),
    corsa_live_strumenti_prova: safe({
        modalita: 'live', modiStrategia: { tennis: 'live', model: 'paper', manual: 'paper' },
    }),
    corsa_live_strumenti_live: safe({
        modalita: 'live', modiStrategia: { tennis: 'live', model: 'live', manual: 'live' },
    }),
    fermo: safe({
        inCorsa: false, stato: 'stopped', varianti: null, modiStrategia: null,
        stopFermaSoloAperture: false,
    }),
    // Safe fermo ma con il tetto del servizio ancora in live (`safe_set_mode`
    // persiste la modalita' anche a bot fermo) e le voci in live
    fermo_live_live: safe({
        inCorsa: false, stato: 'stopped', modalita: 'live', varianti: null,
        modiStrategia: { model: 'live', manual: 'live' }, stopFermaSoloAperture: false,
    }),
    fermo_modalita_null: safe({
        inCorsa: false, stato: 'stopped', modalita: null, varianti: null,
        modiStrategia: null, stopFermaSoloAperture: false,
    }),
};
const STRUMENTI = ['safe-model', 'safe-manual'] as const;

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

function mostra(st: StatoBotPlancia, c = comandiFinti(), opzioni: { soloSafe?: boolean } = {}) {
    // soloSafe = come la pagina Safe Strategy: tutti gli sport, solo il bot safe
    const righe = opzioni.soloSafe
        ? righeInterruttori([st], null).filter((r) => r.bot === 'safe')
        : righeInterruttori([st], 'calcio');
    return {
        righe,
        ...render(<PannelloBot righe={righe} importi={{}} comandi={c}
            serviziAccesi={st.inCorsa ? [{ bot: 'safe', modalita: st.modalita }] : []}
            ambito={opzioni.soloSafe ? 'safe' : 'tutti'}
            testId={opzioni.soloSafe ? 'safe-interruttori' : 'cr-pannello-bot'} />),
    };
}

beforeEach(() => { vi.clearAllMocks(); vi.useRealTimers(); window.localStorage.clear(); });

describe('punto 1 - mai lo stato di un bot in esecuzione, mai FERMA', () => {
    for (const [nome, st] of Object.entries(STATI)) {
        for (const id of STRUMENTI) {
            it(`${nome} / ${id}: niente «running», niente «in corso», niente FERMA`, () => {
                const s = mostra(st);
                const riga = s.righe.find((r) => r.id === id)!;
                expect(riga.strumento).toBe(true);
                expect(riga.stato).not.toBe('running');
                const chip = s.getByTestId(`cr-bot-stato-${id}`).textContent ?? '';
                expect(chip).toBe('strumento, non un bot');
                expect(chip).not.toMatch(/in corsa|running|acceso|in esecuzione/i);
                expect(s.queryByTestId(`cr-ferma-${id}`)).toBeNull();
                expect(s.queryByTestId(`cr-cosa-ferma-${id}`)).toBeNull();
                expect(s.queryByTestId(`cr-motivo-blocco-${id}`)).toBeNull();
            });
        }
    }

    it('il FERMA dei bot veri resta: Safe base acceso lo ha ancora (non e’ sparito ovunque)', () => {
        const st = safe({ varianti: ['base', 'tennis'], modiStrategia: { base: 'paper', tennis: 'paper' } });
        const s = mostra(st);
        expect(s.getByTestId('cr-ferma-safe-base')).toBeTruthy();
    });

    it('anche con un motivo di blocco e «fermato all’avvio» di Safe le righe strumento restano pulite', () => {
        const s = mostra(safe({ motivoBlocco: 'tetto raggiunto' }));
        expect(s.queryByTestId('cr-motivo-blocco-safe-model')).toBeNull();
        const f = mostra(safe({
            inCorsa: false, stato: 'stopped', varianti: null, modiStrategia: null,
            fermatoAllAvvioAt: '2026-10-04T08:00:00Z',
        }));
        expect(f.queryAllByTestId('cr-fermato-avvio-safe-model')).toHaveLength(0);
        expect(f.queryAllByTestId('cr-fermato-avvio-safe-manual')).toHaveLength(0);
    });
});

describe('punto 2 - le parole: strumento, e con che soldi partono gli ordini', () => {
    it('Safe in corsa in prova: «in prova» + frase per ciascun strumento', () => {
        const s = mostra(STATI.corsa_paper);
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-bot-modalita-${id}`).textContent).toBe('in prova');
        }
        expect(s.getByTestId('cr-strumento-spiega-safe-model').textContent).toBe(
            'Strumento, non un bot: non apre niente da solo. Le opportunità del modello che approvi '
            + 'partono IN PROVA (nessun ordine reale).');
        expect(s.getByTestId('cr-strumento-spiega-safe-manual').textContent).toBe(
            'Strumento, non un bot: non apre niente da solo. Gli ordini che fai a mano dalla scheda di Safe '
            + 'partono IN PROVA (nessun ordine reale).');
    });

    it('Safe in live con gli strumenti in prova: restano «in prova» (il tetto del servizio non basta)', () => {
        const s = mostra(STATI.corsa_live_strumenti_prova);
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-bot-modalita-${id}`).textContent).toBe('in prova');
            expect(s.getByTestId(`cr-strumento-spiega-${id}`).textContent).toContain('IN PROVA');
            expect(s.getByTestId(`cr-strumento-spiega-${id}`).textContent).not.toContain('SOLDI VERI');
        }
    });

    it('Safe in live con la voce live: «SOLDI VERI», evidenziato in rosso come LIVE', () => {
        const s = mostra(STATI.corsa_live_strumenti_live);
        for (const id of STRUMENTI) {
            const chip = s.getByTestId(`cr-bot-modalita-${id}`);
            expect(chip.textContent).toBe('SOLDI VERI');
            expect(chip.className).toContain('ds-v2-chip--live');
            expect(chip.className).toContain('text-red-300');
            expect(s.getByTestId(`cr-strumento-spiega-${id}`).textContent).toContain('partono con SOLDI VERI su Betfair');
        }
    });

    it('Safe fermo in prova: chip «in prova» e frase vera (gli ordini partono lo stesso, in prova)', () => {
        const s = mostra(STATI.fermo);
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-bot-modalita-${id}`).textContent).toBe('in prova');
            const t = s.getByTestId(`cr-strumento-spiega-${id}`).textContent ?? '';
            expect(t).toContain('Safe è fermo (le sue strategie non aprono niente)');
            expect(t).toContain('partono lo stesso: IN PROVA (nessun ordine reale).');
            expect(t).not.toContain('non parte niente');
            expect(t).not.toContain('SOLDI VERI');
        }
        expect(s.getByTestId('cr-strumento-spiega-safe-model').textContent).toContain('le opportunità del modello che approvi');
        expect(s.getByTestId('cr-strumento-spiega-safe-manual').textContent).toContain('gli ordini che fai a mano dalla scheda di Safe');
    });

    it('Safe fermo con modalita’ live e voce live: SOLDI VERI in rosso, gruppo «soldi veri», nessun pulsante finto', () => {
        const s = mostra(STATI.fermo_live_live);
        for (const id of STRUMENTI) {
            const chip = s.getByTestId(`cr-bot-modalita-${id}`);
            expect(chip.textContent).toBe('SOLDI VERI');
            expect(chip.className).toContain('ds-v2-chip--live');
            const frase = s.getByTestId(`cr-strumento-spiega-${id}`);
            expect(frase.textContent).toContain('partono lo stesso: con SOLDI VERI su Betfair.');
            expect(frase.textContent).toContain('Per cambiarlo serve prima avviare Safe.');
            expect(frase.className).toContain('text-red-300');
            for (const t of ['cr-avvia-paper', 'cr-avvia-live', 'cr-a-live', 'cr-a-paper', 'cr-ferma']) {
                expect(s.queryByTestId(`${t}-${id}`)).toBeNull();
            }
        }
        expect(s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger').textContent).toContain('soldi veri');
    });

    it('Safe fermo in prova: il gruppo NON dice «soldi veri»', () => {
        const s = mostra(STATI.fermo);
        expect(s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger').textContent).not.toContain('soldi veri');
    });

    it('Safe fermo con modalita’ non letta: lo dice, mai il silenzio', () => {
        const s = mostra(STATI.fermo_modalita_null);
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-bot-stato-${id}`).textContent).toBe('strumento, non un bot');
            const t = s.getByTestId(`cr-strumento-spiega-${id}`).textContent ?? '';
            expect(t).toContain('la modalità (prova o soldi veri) non è stata letta');
            expect(s.queryByTestId(`cr-avvia-paper-${id}`)).toBeNull();
        }
        expect(s.getAllByText('modalità non letta').length).toBe(2);
    });

    it('Safe in corsa con modalita’ non letta: non finge «in prova»', () => {
        const s = mostra(safe({ modalita: null }));
        for (const id of STRUMENTI) {
            const t = s.getByTestId(`cr-strumento-spiega-${id}`).textContent ?? '';
            expect(t).toContain('la modalità (prova o soldi veri) non è stata letta');
            expect(t).not.toContain('IN PROVA');
        }
    });

    it('stato non letto (live senza mappa): lo dice, non finge un bot ne’ una modalita’', () => {
        const s = mostra(safe({ modalita: 'live', modiStrategia: null }));
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-bot-stato-${id}`).textContent).toBe('stato non letto');
            expect(s.getByTestId(`cr-strumento-spiega-${id}`).textContent).toContain('non è stato letto');
        }
    });
});

describe('punto 3 - i gesti che esistono restano, con la stessa conferma', () => {
    for (const id of STRUMENTI) {
        it(`${id}: passa a soldi veri: arma, conferma inerte, poi cambiaModalita(id, live) - una sola volta`, () => {
            vi.useFakeTimers();
            const c = comandiFinti();
            const s = mostra(STATI.corsa_paper, c);
            fireEvent.click(s.getByTestId(`cr-a-live-${id}`));
            expect(c.cambiaModalita).not.toHaveBeenCalled();
            fireEvent.click(s.getByTestId(`cr-conferma-live-${id}`));
            expect(c.cambiaModalita).not.toHaveBeenCalled();
            act(() => { vi.advanceTimersByTime(500); });
            fireEvent.click(s.getByTestId(`cr-conferma-live-${id}`));
            expect(c.cambiaModalita).toHaveBeenCalledTimes(1);
            expect(c.cambiaModalita).toHaveBeenCalledWith(id, 'live');
            expect(c.spegni).not.toHaveBeenCalled();
        });

        it(`${id}: passa a prova: immediato`, () => {
            const c = comandiFinti();
            const s = mostra(STATI.corsa_live_strumenti_live, c);
            fireEvent.click(s.getByTestId(`cr-a-paper-${id}`));
            expect(c.cambiaModalita).toHaveBeenCalledTimes(1);
            expect(c.cambiaModalita).toHaveBeenCalledWith(id, 'paper');
            expect(c.spegni).not.toHaveBeenCalled();
        });
    }
});

describe('punto 4 - non contano come bot accesi', () => {
    it('l’intestazione conta i BOT: gli strumenti non sono nel numero ne’ fra i pallini', () => {
        const s = mostra(STATI.corsa_paper);
        const trigger = s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger');
        // calcio: omega/mike non ci sono (solo Safe), restano base, esatto, punta
        expect(trigger.textContent).toContain('BOT CALCIO (3)');
        expect(trigger.querySelectorAll('[title]').length).toBe(3);
        expect(trigger.textContent).not.toContain('Safe modello');
    });

    it('riassunto di gruppo: con nessun bot di calcio acceso, gli strumenti non fanno comparire «prova»', () => {
        // Safe in corsa solo per il tennis: base/esatto/punta spente, i due strumenti «seguono»
        const s = mostra(STATI.corsa_paper);
        const trigger = s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger');
        expect(trigger.textContent).not.toMatch(/prova/);
        expect(trigger.textContent).not.toMatch(/soldi veri/);
    });

    it('riassunto di gruppo: strumento in LIVE si dice (e’ denaro vero), senza contarlo come bot', () => {
        const s = mostra(STATI.corsa_live_strumenti_live);
        const trigger = s.getByTestId('cr-pannello-bot-gruppo-calcio-trigger');
        expect(trigger.textContent).toContain('soldi veri');
        expect(trigger.textContent).toContain('BOT CALCIO (3)');
    });

    it('«ferma tutti» ferma il SERVIZIO Safe una volta: mai spegni() sulle righe strumento', async () => {
        const c = comandiFinti();
        const s = mostra(STATI.corsa_paper, c);
        await act(async () => { fireEvent.click(s.getByTestId('cr-ferma-tutti')); });
        expect(c.fermaBot).toHaveBeenCalledTimes(1);
        expect(c.fermaBot).toHaveBeenCalledWith('safe');
        expect(c.spegni).not.toHaveBeenCalled();
        expect(s.queryByTestId('cr-non-fermati')).toBeNull();
    });

    it('Safe fermo: «ferma tutti» disabilitato, nessun bot in esecuzione', () => {
        const s = mostra(STATI.fermo);
        expect((s.getByTestId('cr-ferma-tutti') as HTMLButtonElement).disabled).toBe(true);
    });
});

describe('punto 5 - stessa resa nella pagina Safe Strategy (stesse righe, stesso pannello)', () => {
    for (const [nome, st] of Object.entries(STATI)) {
        it(`${nome}: righe filtrate come SafeStrategy, niente FERMA e niente «running» sugli strumenti`, () => {
            const s = mostra(st, comandiFinti(), { soloSafe: true });
            for (const id of STRUMENTI) {
                const riga = s.getByTestId(`cr-bot-riga-${id}`);
                expect(riga).toBeTruthy();
                expect(s.queryByTestId(`cr-ferma-${id}`)).toBeNull();
                expect(s.getByTestId(`cr-bot-stato-${id}`).textContent).toBe('strumento, non un bot');
                expect(s.getByTestId(`cr-strumento-spiega-${id}`).textContent).toContain('Strumento, non un bot');
            }
        });
    }
});

describe('righeInterruttori - il dato che governa la resa', () => {
    for (const [nome, st] of Object.entries(STATI)) {
        it(`${nome}: strumento=true e stato «strumento» sulle due righe, mai sui bot`, () => {
            const righe = righeInterruttori([st], null);
            for (const r of righe) {
                if (r.id === 'safe-model' || r.id === 'safe-manual') {
                    expect(r.strumento).toBe(true);
                    expect(r.stato).toBe('strumento');
                    expect(r.stato).not.toBe('running');
                } else {
                    expect(r.strumento).toBeUndefined();
                }
            }
        });
    }

    it('Safe si sta fermando: gli strumenti dicono «stopping» e non offrono comandi', () => {
        const st = safe({ stato: 'stopping' });
        const s = mostra(st);
        for (const id of STRUMENTI) {
            expect(s.getByTestId(`cr-in-arresto-${id}`)).toBeTruthy();
            expect(s.queryByTestId(`cr-a-live-${id}`)).toBeNull();
            expect(s.queryByTestId(`cr-ferma-${id}`)).toBeNull();
        }
    });
});
