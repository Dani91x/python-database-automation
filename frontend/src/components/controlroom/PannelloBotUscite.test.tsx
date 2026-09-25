// ============================================================================
// PannelloBotUscite.test.tsx — 25/09: l'interruttore «Uscite automatiche» per
// singolo bot nella plancia della Control Room.
//
// «se disattivo il pulsante (TUTTO DEVE ESSERE IN UI PER SINGOLO BOT), le
// uscite le gestisco io manualmente tramite l'apposita scheda» (utente).
// Qui si prova CHE COSA si vede (testi esatti) e CHE COSA viene chiamato.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { PannelloBot, type RigaInterruttore } from './PannelloBot';
import type {
    CampoImporto, ComandiInterruttori, InterruttoreId, StatoUscite,
} from '@/lib/interruttori';

function riga(over: Partial<RigaInterruttore> = {}): RigaInterruttore {
    return {
        id: 'mike', bot: 'mike', etichetta: 'Mike',
        acceso: true, modalita: 'paper', statoNoto: true, stato: 'running',
        etaPushS: 1, motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: true, fermatoAllAvvioAt: null, primaDelBot: true,
        ...over,
    };
}

const SENZA_IMPORTI: Partial<Record<InterruttoreId, CampoImporto[]>> = {};

function comandiFinti(conUscite = true): ComandiInterruttori {
    return {
        accendi: vi.fn(async () => {}),
        spegni: vi.fn(async () => {}),
        cambiaModalita: vi.fn(async () => {}),
        cambiaImporto: vi.fn(async () => {}),
        fermaBot: vi.fn(async () => {}),
        scriviAccensioni: vi.fn(async () => {}),
        cambiaModalitaServizio: vi.fn(async () => {}),
        ...(conUscite ? { cambiaUscite: vi.fn(async () => {}) } : {}),
    };
}

function mostra(righe: RigaInterruttore[], comandi: ComandiInterruttori,
    uscite: Partial<Record<InterruttoreId, StatoUscite>> | undefined) {
    return render(<PannelloBot righe={righe} importi={SENZA_IMPORTI} comandi={comandi} uscite={uscite} />);
}

describe('25/09 uscite automatiche — che cosa si vede', () => {
    it('automatiche: testo esatto e pulsante «passa a manuali»', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: true } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('automatiche');
        expect(s.getByTestId('cr-uscite-cambia-mike').textContent).toBe('passa a manuali');
    });

    it('manuali con posizioni: «manuali — 2 posizioni aperte da 7 min»', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 2, daMin: 7 } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('manuali — 2 posizioni aperte da 7 min');
        expect(s.getByTestId('cr-uscite-cambia-mike').textContent).toBe('passa ad automatiche');
    });

    it('manuali con una posizione e con zero posizioni', () => {
        const s1 = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 1, daMin: 0 } });
        expect(s1.getByTestId('cr-uscite-stato-mike').textContent).toBe('manuali — 1 posizione aperta da 0 min');
        s1.unmount();
        const s0 = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 0, daMin: null } });
        expect(s0.getByTestId('cr-uscite-stato-mike').textContent).toBe('manuali — 0 posizioni aperte');
    });

    it('parametri non letti: «non lette» e NESSUN pulsante (fail-closed)', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: null } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('non lette');
        expect(s.queryByTestId('cr-uscite-cambia-mike')).toBeNull();
    });

    it('la nota del servizio si legge (scalper senza sessioni)', () => {
        const s = mostra([riga({ id: 'scalper', bot: 'scalper', etichetta: 'Scalper calcio' })], comandiFinti(),
            { scalper: { automatiche: true, nota: 'nessuna sessione attiva: le nuove nascono con le uscite automatiche' } });
        expect(s.getByTestId('cr-uscite-stato-scalper').textContent)
            .toBe('automatiche (nessuna sessione attiva: le nuove nascono con le uscite automatiche)');
    });

    it('riga senza interruttore delle uscite (es. bot tennis): niente riga uscite', () => {
        const s = mostra([riga()], comandiFinti(), {});
        expect(s.queryByTestId('cr-uscite-mike')).toBeNull();
    });

    it('senza il comando (pagine dei singoli bot) lo stato si vede ma il pulsante no', () => {
        const s = mostra([riga()], comandiFinti(false), { mike: { automatiche: true } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('automatiche');
        expect(s.queryByTestId('cr-uscite-cambia-mike')).toBeNull();
    });
});

describe('25/09 uscite automatiche — che cosa viene chiamato', () => {
    it('«passa a manuali» chiama cambiaUscite(id, false) sulla SUA riga', async () => {
        const c = comandiFinti();
        const s = mostra([riga(), riga({ id: 'safe-tennis', bot: 'safe', etichetta: 'Safe tennis', primaDelBot: true })], c,
            { mike: { automatiche: true }, 'safe-tennis': { automatiche: false } });
        await act(async () => { fireEvent.click(s.getByTestId('cr-uscite-cambia-mike')); });
        expect(c.cambiaUscite).toHaveBeenCalledTimes(1);
        expect(c.cambiaUscite).toHaveBeenCalledWith('mike', false);
    });

    it('«passa ad automatiche» chiede conferma, poi chiama cambiaUscite(id, true)', async () => {
        // 25/09 sera: passare ad automatiche e' la direzione che ora si
        // conferma (il default e' manuale); il primo clic arma, il secondo
        // manda il comando.
        const c = comandiFinti();
        const s = mostra([riga({ id: 'safe-tennis', bot: 'safe', etichetta: 'Safe tennis' })], c,
            { 'safe-tennis': { automatiche: false, aperte: 1, daMin: 3 } });
        fireEvent.click(s.getByTestId('cr-uscite-cambia-safe-tennis'));
        expect(c.cambiaUscite).not.toHaveBeenCalled();
        await act(async () => { fireEvent.click(s.getByTestId('cr-uscite-conferma-safe-tennis')); });
        expect(c.cambiaUscite).toHaveBeenCalledWith('safe-tennis', true);
        expect(c.accendi).not.toHaveBeenCalled();
        expect(c.spegni).not.toHaveBeenCalled();
    });
});
