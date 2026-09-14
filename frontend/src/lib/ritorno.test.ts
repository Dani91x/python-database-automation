// ============================================================================
// ritorno.test.ts — il ritorno al punto esatto.
//
// Qui si difende una cosa sola: **un ritorno impreciso deve degradare in un
// ritorno onesto**, mai in un ritorno sbagliato. Riportare il trader sulla
// riga di un'altra partita è peggio che riportarlo in cima alla pagina.
// ============================================================================
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { salvaRitorno, leggiRitorno, dimenticaRitorno, portaInVista, VALIDO_PER_MS } from './ritorno';

const PUNTO = {
    rotta: '/control-room', nome: 'Control Room',
    scheda: 'live', eventId: 'E1', scorrimento: 640,
};

beforeEach(() => { sessionStorage.clear(); });

describe('salva e rilegge', () => {
    it('riporta indietro tutte e quattro le cose che servono', () => {
        salvaRitorno(PUNTO);
        const p = leggiRitorno();
        expect(p).toMatchObject(PUNTO);
        expect(typeof p?.quando).toBe('number');
    });

    it('senza niente salvato ritorna null, non un punto finto', () => {
        expect(leggiRitorno()).toBeNull();
    });

    it('dimenticare lo cancella: un secondo ritorno non riporta dove non si è più stati', () => {
        salvaRitorno(PUNTO);
        dimenticaRitorno();
        expect(leggiRitorno()).toBeNull();
    });
});

describe('un punto scaduto NON si usa', () => {
    it('oltre il tempo di validità vale null: la partita di allora adesso è un’altra', () => {
        salvaRitorno(PUNTO);
        expect(leggiRitorno(Date.now() + VALIDO_PER_MS + 1)).toBeNull();
    });

    it('appena dentro il tempo vale ancora', () => {
        salvaRitorno(PUNTO);
        expect(leggiRitorno(Date.now() + VALIDO_PER_MS - 1000)).not.toBeNull();
    });

    it('un istante FUTURO (orologio spostato) non si accetta', () => {
        salvaRitorno(PUNTO);
        expect(leggiRitorno(Date.now() - 60_000)).toBeNull();
    });
});

describe('roba illeggibile non rompe niente', () => {
    it('JSON rotto → null', () => {
        sessionStorage.setItem('ritorno.punto', '{{{');
        expect(leggiRitorno()).toBeNull();
    });

    it('senza rotta non è un punto di ritorno', () => {
        sessionStorage.setItem('ritorno.punto', JSON.stringify({ nome: 'x', quando: Date.now() }));
        expect(leggiRitorno()).toBeNull();
    });

    it('una rotta che non è una rotta (link esterno) si rifiuta', () => {
        sessionStorage.setItem('ritorno.punto', JSON.stringify({
            rotta: 'https://altro-sito.example', quando: Date.now(),
        }));
        expect(leggiRitorno()).toBeNull();
    });

    it('i campi accessori storti si normalizzano invece di far fallire tutto', () => {
        sessionStorage.setItem('ritorno.punto', JSON.stringify({
            rotta: '/control-room', quando: Date.now(),
            nome: 42, scheda: 7, eventId: false, scorrimento: -9,
        }));
        const p = leggiRitorno();
        expect(p?.rotta).toBe('/control-room');
        expect(p?.nome).toBe('pagina precedente');
        expect(p?.scheda).toBeNull();
        expect(p?.eventId).toBeNull();
        expect(p?.scorrimento).toBe(0);
    });

    it('senza sessionStorage non lancia: si perde il ritorno, non la navigazione', () => {
        const vero = Object.getOwnPropertyDescriptor(window, 'sessionStorage');
        Object.defineProperty(window, 'sessionStorage', {
            configurable: true,
            get() { throw new Error('dati del sito bloccati'); },
        });
        expect(() => salvaRitorno(PUNTO)).not.toThrow();
        expect(leggiRitorno()).toBeNull();
        expect(() => dimenticaRitorno()).not.toThrow();
        if (vero) Object.defineProperty(window, 'sessionStorage', vero);
    });
});

describe('portaInVista — la riga si nota, o si dice che non c’è', () => {
    afterEach(() => { document.body.innerHTML = ''; vi.useRealTimers(); });

    it('trova la riga, la porta in vista e la accende', () => {
        vi.useFakeTimers();
        document.body.innerHTML = '<div data-event-id="E1">Milan – Inter</div>';
        const el = document.querySelector('[data-event-id="E1"]') as HTMLElement;
        el.scrollIntoView = vi.fn();

        expect(portaInVista('E1')).toBe(true);
        expect(el.scrollIntoView).toHaveBeenCalled();
        expect(el.className).toContain('ring-primary');

        // l'evidenziazione è un lampo, non una decorazione permanente
        vi.advanceTimersByTime(2100);
        expect(el.className).not.toContain('ring-primary');
    });

    it('riga assente → false, così chi chiama può dirlo invece di far cercare', () => {
        document.body.innerHTML = '<div data-event-id="ALTRO"></div>';
        expect(portaInVista('E1')).toBe(false);
    });

    it('un id con caratteri strani non diventa un selettore rotto', () => {
        document.body.innerHTML = '<div data-event-id="1.234:x"></div>';
        const el = document.querySelector('[data-event-id]') as HTMLElement;
        el.scrollIntoView = vi.fn();
        expect(portaInVista('1.234:x')).toBe(true);
    });
});
