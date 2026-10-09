import { describe, it, expect, vi, afterEach } from 'vitest';
import { leggiVisibile, scriviVisibile } from './preferenzaVista';

describe('preferenzaVista', () => {
    afterEach(() => { vi.restoreAllMocks(); window.localStorage.removeItem('vista.prova'); });

    it('assente = predefinito; scritta = letta', () => {
        expect(leggiVisibile('prova')).toBe(true);
        expect(leggiVisibile('prova', false)).toBe(false);
        expect(scriviVisibile('prova', false)).toBe(true);
        expect(leggiVisibile('prova')).toBe(false);
        scriviVisibile('prova', true);
        expect(leggiVisibile('prova', false)).toBe(true);
    });

    it('archiviazione che lancia: mai un errore, vale il predefinito', () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloccato'); });
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloccato'); });
        expect(leggiVisibile('prova')).toBe(true);
        expect(scriviVisibile('prova', false)).toBe(false);
    });
});
