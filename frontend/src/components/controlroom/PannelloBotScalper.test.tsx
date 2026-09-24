// ============================================================================
// PannelloBotScalper.test.tsx - la riga "Scalper calcio" nella card dei bot
// (24/09): stesso stile delle altre, una riga in piu', niente riquadri nuovi.
//
// Lo scalper si arma PER PARTITA: la riga mostra stato, modalita' e la nota
// delle sessioni (quante, in che modalita', fonte ed eta'), offre FERMA quando
// una sessione e' attiva e, al posto di "avvia", dice dove si arma. Mai un
// pulsante "passa a soldi veri" che non puo' riuscire.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { PannelloBot, type RigaInterruttore } from './PannelloBot';
import { righeInterruttori, type StatoBotPlancia } from './righeBot';
import type { ComandiInterruttori } from '@/lib/interruttori';

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

/** lo stato del bot scalper come `useControlRoom` lo costruisce (chiavi di StatoBotPlancia) */
function statoScalper(over: Partial<StatoBotPlancia> = {}): StatoBotPlancia {
    return {
        bot: 'scalper', inCorsa: true, modalita: 'paper', varianti: null, modiStrategia: null,
        stato: 'running', etaPushS: null, motivoBlocco: null, tettoPartite: null,
        partiteEsposte: null, stopFermaSoloAperture: false, fermatoAllAvvioAt: null,
        pnlOggi: null, pnlOggiPaper: null,
        nota: '1 sessione viva (1 prova) - dal database, letto 4 s fa',
        ...over,
    };
}

function righeDi(s: StatoBotPlancia): RigaInterruttore[] {
    return righeInterruttori([s], 'calcio');
}

beforeEach(() => { vi.clearAllMocks(); });

describe('la riga Scalper calcio', () => {
    it('righeInterruttori la costruisce dal catalogo, con la frase del dove si arma e la nota', () => {
        const [r] = righeDi(statoScalper());
        expect(r).toMatchObject({
            id: 'scalper', bot: 'scalper', etichetta: 'Scalper calcio',
            acceso: true, modalita: 'paper', stato: 'running',
            nota: '1 sessione viva (1 prova) - dal database, letto 4 s fa',
        });
        expect(r.armoPerPartita).toMatch(/Segui Live/);
    });

    it('accesa: si vede la nota, c e FERMA, e NON c e il cambio di modalita', async () => {
        const c = comandiFinti();
        const s = render(<PannelloBot righe={righeDi(statoScalper())} importi={{}} comandi={c} />);
        expect(s.getByTestId('cr-bot-nota-scalper').textContent).toContain('dal database');
        expect(s.queryByTestId('cr-a-live-scalper')).toBeNull();
        expect(s.queryByTestId('cr-a-paper-scalper')).toBeNull();
        fireEvent.click(s.getByTestId('cr-ferma-scalper'));
        await waitFor(() => expect(c.spegni).toHaveBeenCalledWith('scalper'));
        expect(c.accendi).not.toHaveBeenCalled();
        expect(c.cambiaModalita).not.toHaveBeenCalled();
    });

    it('accesa con soldi veri: badge soldi veri, e ancora nessun "passa a prova" (la sessione non lo legge)', () => {
        const s = render(<PannelloBot righe={righeDi(statoScalper({ modalita: 'live' }))}
            importi={{}} comandi={comandiFinti()} />);
        expect(s.getByTestId('cr-bot-modalita-scalper').textContent).toBe('soldi veri');
        expect(s.queryByTestId('cr-a-paper-scalper')).toBeNull();
    });

    it('spenta: niente "avvia", al suo posto la frase del dove si arma', () => {
        const c = comandiFinti();
        const s = render(<PannelloBot
            righe={righeDi(statoScalper({ inCorsa: false, modalita: null, stato: 'stopped' }))}
            importi={{}} comandi={c} />);
        expect(s.queryByTestId('cr-avvia-paper-scalper')).toBeNull();
        expect(s.queryByTestId('cr-avvia-live-scalper')).toBeNull();
        expect(s.getByTestId('cr-armo-per-partita-scalper').textContent).toMatch(/Segui Live/);
    });

    it('fermata all avvio dell app: lo dice, come per gli altri bot', () => {
        const s = render(<PannelloBot
            righe={righeDi(statoScalper({
                inCorsa: false, modalita: null, stato: 'stopped',
                fermatoAllAvvioAt: '2026-09-24T07:00:00+00:00',
            }))}
            importi={{}} comandi={comandiFinti()} />);
        expect(s.getByTestId('cr-fermato-avvio-scalper')).toBeTruthy();
    });

    it('le altre righe non cambiano: Mike acceso ha ancora "passa a soldi veri"', () => {
        const mike: StatoBotPlancia = { ...statoScalper(), bot: 'mike', nota: null };
        const s = render(<PannelloBot righe={righeInterruttori([mike], 'calcio')}
            importi={{}} comandi={comandiFinti()} />);
        expect(s.getByTestId('cr-a-live-mike')).toBeTruthy();
        expect(s.queryByTestId('cr-armo-per-partita-mike')).toBeNull();
        expect(s.queryByTestId('cr-bot-nota-mike')).toBeNull();
    });
});
