// ============================================================================
// PannelloBotUscite.test.tsx - l'interruttore delle uscite per singolo bot
// nella plancia della Control Room (25/09; 28/09 CANTIERE N: UN componente e
// le STESSE parole per tutti i bot, tennis compresi).
//
// "OGNI BOT, PER ORA, DEVE PASSARE DA ME, IO APPROVO LE USCITE; QUANDO MI
// FIDERO', LI LASCERO' LAVORARE IN AUTOMATICO" (utente, 28/09).
// Qui si prova CHE COSA si vede (testi esatti) e CHE COSA viene chiamato.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { PannelloBot, type RigaInterruttore } from './PannelloBot';
import { ATTESA_CONFERMA_USCITE_MS } from './InterruttoreUscite';
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

const testo = (s: ReturnType<typeof mostra>, id: string) =>
    (s.getByTestId(`cr-uscite-${id}`).textContent ?? '');

afterEach(() => { vi.useRealTimers(); });

describe('28/09 uscite - che cosa si vede (stesse parole per ogni bot)', () => {
    it('automatiche: "uscite: AUTOMATICHE" e pulsante "passa a manuali"', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: true } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('AUTOMATICHE');
        expect(testo(s, 'mike').startsWith('uscite:AUTOMATICHE')).toBe(true);
        expect(s.getByTestId('cr-uscite-cambia-mike').textContent).toBe('passa a manuali');
    });

    it('manuali: "uscite: MANUALI, approvi tu - 2 posizioni aperte da 7 min"', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 2, daMin: 7 } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent)
            .toBe('MANUALI, approvi tu - 2 posizioni aperte da 7 min');
        expect(s.getByTestId('cr-uscite-cambia-mike').textContent).toBe('passa ad automatiche');
    });

    it('manuali con una posizione, con zero e senza conteggio', () => {
        const s1 = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 1, daMin: 0 } });
        expect(s1.getByTestId('cr-uscite-stato-mike').textContent).toBe('MANUALI, approvi tu - 1 posizione aperta da 0 min');
        s1.unmount();
        const s0 = mostra([riga()], comandiFinti(), { mike: { automatiche: false, aperte: 0, daMin: null } });
        expect(s0.getByTestId('cr-uscite-stato-mike').textContent).toBe('MANUALI, approvi tu - 0 posizioni aperte');
        s0.unmount();
        const sn = mostra([riga()], comandiFinti(), { mike: { automatiche: false } });
        expect(sn.getByTestId('cr-uscite-stato-mike').textContent).toBe('MANUALI, approvi tu');
    });

    it('parametri non letti: «non lette» e NESSUN pulsante (fail-closed)', () => {
        const s = mostra([riga()], comandiFinti(), { mike: { automatiche: null } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('non lette');
        expect(s.queryByTestId('cr-uscite-cambia-mike')).toBeNull();
    });

    it('la nota del servizio si legge (scalper senza sessioni)', () => {
        const s = mostra([riga({ id: 'scalper', bot: 'scalper', etichetta: 'Scalper calcio' })], comandiFinti(),
            { scalper: { automatiche: false, nota: 'nessuna sessione attiva: le nuove nascono con le uscite manuali' } });
        expect(s.getByTestId('cr-uscite-stato-scalper').textContent)
            .toBe('MANUALI, approvi tu (nessuna sessione attiva: le nuove nascono con le uscite manuali)');
    });

    it('bot tennis: STESSO pulsante, STESSE parole, stesso posto', () => {
        const s = mostra([riga(), riga({ id: 'tennis_pro', bot: 'tennis_pro', etichetta: 'Tennis pro' })],
            comandiFinti(), { mike: { automatiche: false }, tennis_pro: { automatiche: false } });
        expect(s.getByTestId('cr-uscite-stato-tennis_pro').textContent)
            .toBe(s.getByTestId('cr-uscite-stato-mike').textContent);
        expect(s.getByTestId('cr-uscite-cambia-tennis_pro').textContent).toBe('passa ad automatiche');
    });

    it('riga senza interruttore delle uscite (Safe "a mano"): niente riga uscite', () => {
        const s = mostra([riga()], comandiFinti(), {});
        expect(s.queryByTestId('cr-uscite-mike')).toBeNull();
    });

    it('senza il comando lo stato si vede ma il pulsante no', () => {
        const s = mostra([riga()], comandiFinti(false), { mike: { automatiche: true } });
        expect(s.getByTestId('cr-uscite-stato-mike').textContent).toBe('AUTOMATICHE');
        expect(s.queryByTestId('cr-uscite-cambia-mike')).toBeNull();
    });
});

describe('28/09 uscite - che cosa viene chiamato', () => {
    it('"passa a manuali" chiama cambiaUscite(id, false) sulla SUA riga, senza conferma', async () => {
        const c = comandiFinti();
        const s = mostra([riga(), riga({ id: 'safe-tennis', bot: 'safe', etichetta: 'Safe tennis', primaDelBot: true })], c,
            { mike: { automatiche: true }, 'safe-tennis': { automatiche: false } });
        await act(async () => { fireEvent.click(s.getByTestId('cr-uscite-cambia-mike')); });
        expect(c.cambiaUscite).toHaveBeenCalledTimes(1);
        expect(c.cambiaUscite).toHaveBeenCalledWith('mike', false);
    });

    it('"passa ad automatiche" chiede conferma; la conferma e\' INERTE per un doppio clic', async () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-09-28T12:00:00Z'));
        const c = comandiFinti();
        const s = mostra([riga({ id: 'tennis_swing', bot: 'tennis_swing', etichetta: 'Tennis swing' })], c,
            { tennis_swing: { automatiche: false, aperte: 1, daMin: 3 } });
        fireEvent.click(s.getByTestId('cr-uscite-cambia-tennis_swing'));
        expect(c.cambiaUscite).not.toHaveBeenCalled();
        // doppio clic: il secondo cade sulla conferma appena comparsa -> niente
        const conferma = s.getByTestId('cr-uscite-conferma-tennis_swing') as HTMLButtonElement;
        expect(conferma.disabled).toBe(true);
        fireEvent.click(conferma);
        expect(c.cambiaUscite).not.toHaveBeenCalled();
        // passata l'attesa, il secondo clic vero conferma
        await act(async () => { vi.advanceTimersByTime(ATTESA_CONFERMA_USCITE_MS + 50); });
        await act(async () => { fireEvent.click(s.getByTestId('cr-uscite-conferma-tennis_swing')); });
        expect(c.cambiaUscite).toHaveBeenCalledWith('tennis_swing', true);
        expect(c.accendi).not.toHaveBeenCalled();
        expect(c.spegni).not.toHaveBeenCalled();
    });

    it('"annulla" toglie la conferma senza chiamare niente', () => {
        const c = comandiFinti();
        const s = mostra([riga()], c, { mike: { automatiche: false } });
        fireEvent.click(s.getByTestId('cr-uscite-cambia-mike'));
        fireEvent.click(s.getByTestId('cr-uscite-annulla-mike'));
        expect(s.queryByTestId('cr-uscite-conferma-mike')).toBeNull();
        expect(c.cambiaUscite).not.toHaveBeenCalled();
    });
});
