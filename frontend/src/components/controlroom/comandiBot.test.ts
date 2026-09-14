// ============================================================================
// comandiBot.test.ts — i comandi che possono accendere un bot su soldi veri.
//
// Qui non si collauda una formula: si impedisce che un salvataggio
// dell'importo porti via tutti gli altri parametri del bot, e che «avvia» in
// live parta con un obiettivo inventato.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/omega', () => ({
    activateOmega: vi.fn(async () => ({})),
    stopOmega: vi.fn(async () => ({})),
    updateOmegaParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/safeBot', () => ({
    activateSafe: vi.fn(async () => ({})),
    stopSafe: vi.fn(async () => ({})),
    updateSafeParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/mike', () => ({
    activateMike: vi.fn(async () => ({})),
    stopMike: vi.fn(async () => ({})),
    updateMikeParams: vi.fn(async () => ({})),
}));

import {
    leggiChiave, scriviChiave, importiDi, creaComandi, ObiettivoOmegaIgnoto, IMPORTI_DI,
} from './comandiBot';
import { activateOmega, stopOmega, updateOmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams } from '@/lib/mike';

const mActOmega = vi.mocked(activateOmega);
const mStopOmega = vi.mocked(stopOmega);
const mUpdOmega = vi.mocked(updateOmegaParams);
const mActSafe = vi.mocked(activateSafe);
const mStopSafe = vi.mocked(stopSafe);
const mUpdSafe = vi.mocked(updateSafeParams);
const mActMike = vi.mocked(activateMike);
const mStopMike = vi.mocked(stopMike);
const mUpdMike = vi.mocked(updateMikeParams);

beforeEach(() => { vi.clearAllMocks(); });

// ------------------------------------------------------------- chiavi annidate

describe('leggiChiave — legge anche dentro, e non esplode mai', () => {
    it('legge una chiave annidata', () => {
        expect(leggiChiave({ stake: { backSize: 3 } }, 'stake.backSize')).toBe(3);
    });

    it('chiave assente, parametri assenti, valore non numerico → null', () => {
        expect(leggiChiave({ stake: {} }, 'stake.backSize')).toBeNull();
        expect(leggiChiave(null, 'stake.backSize')).toBeNull();
        expect(leggiChiave({ stake: 'tre' }, 'stake.backSize')).toBeNull();
        expect(leggiChiave({ stake: { backSize: 'tre' } }, 'stake.backSize')).toBeNull();
    });

    it('zero è un valore, non un’assenza', () => {
        expect(leggiChiave({ min_stake: 0 }, 'min_stake')).toBe(0);
    });
});

describe('scriviChiave — CAMBIA UNA COSA E NON PORTA VIA IL RESTO', () => {
    it('conserva ogni altra chiave, anche quelle che nessun tipo conosce', () => {
        const prima = {
            stake: { backSize: 3, laySize: 2 },
            exits: { qualcosa: true },
            chiave_che_nessuno_conosce: 42,
        };
        const dopo = scriviChiave(prima, 'stake.backSize', 5);
        expect(dopo).toEqual({
            stake: { backSize: 5, laySize: 2 },
            exits: { qualcosa: true },
            chiave_che_nessuno_conosce: 42,
        });
    });

    it('NON muta l’oggetto di partenza: due salvataggi in fila devono partire puliti', () => {
        const prima = { stake: { backSize: 3 } };
        const dopo = scriviChiave(prima, 'stake.backSize', 9);
        expect(prima.stake.backSize).toBe(3);
        expect(dopo).not.toBe(prima);
        expect((dopo.stake as Record<string, number>)).not.toBe(prima.stake);
    });

    it('crea il ramo mancante invece di fallire', () => {
        expect(scriviChiave({}, 'stake.backSize', 3)).toEqual({ stake: { backSize: 3 } });
        expect(scriviChiave(null, 'min_stake', 1)).toEqual({ min_stake: 1 });
    });

    it('se il ramo esiste ma non è un oggetto lo sostituisce, non esplode', () => {
        expect(scriviChiave({ stake: 7 }, 'stake.backSize', 3)).toEqual({ stake: { backSize: 3 } });
    });
});

// ------------------------------------------------------------------- importi

describe('importiDi — le chiavi sono quelle che i servizi leggono davvero', () => {
    it('Safe ha DUE importi: chi punta e chi banca', () => {
        const c = importiDi('safe', { stake: { backSize: 3, laySize: 2 } });
        expect(c.map((x) => [x.chiave, x.valore])).toEqual([
            ['stake.backSize', 3], ['stake.laySize', 2],
        ]);
    });

    it('lo stake minimo di Omega porta scritto che è un MINIMO', () => {
        const c = importiDi('omega', { min_stake: 0.5 });
        expect(c[0].chiave).toBe('min_stake');
        expect(c[0].valore).toBe(0.5);
        expect(c[0].nota).toMatch(/minimo/i);
    });

    it('un importo che il servizio non dichiara vale null, non 0', () => {
        expect(importiDi('mike', {})[0].valore).toBeNull();
        expect(importiDi('mike', null)[0].valore).toBeNull();
    });

    it('nessun bot dichiara chiavi che non siano le sue', () => {
        expect(IMPORTI_DI.mike.map((x) => x.chiave)).toEqual(['stake']);
        expect(IMPORTI_DI.omega.map((x) => x.chiave)).toEqual(['min_stake']);
    });
});

// -------------------------------------------------------------------- comandi

const sorgente = (params: Record<string, unknown> | null, obiettivo: number | null = 100) => ({
    params: () => params,
    obiettivoOmega: () => obiettivo,
});

describe('ferma — ogni bot col suo comando, e la pagina rilegge', () => {
    it('chiama lo stop giusto per ciascuno e avvisa che qualcosa è cambiato', async () => {
        const dopo = vi.fn();
        const c = creaComandi(sorgente({}), dopo);
        await c.ferma('safe'); await c.ferma('mike'); await c.ferma('omega');
        expect(mStopSafe).toHaveBeenCalledTimes(1);
        expect(mStopMike).toHaveBeenCalledTimes(1);
        expect(mStopOmega).toHaveBeenCalledTimes(1);
        expect(dopo).toHaveBeenCalledTimes(3);
    });

    it('se lo stop fallisce NON si dichiara che è cambiato qualcosa', async () => {
        mStopSafe.mockRejectedValueOnce(new Error('rete giù'));
        const dopo = vi.fn();
        const c = creaComandi(sorgente({}), dopo);
        await expect(c.ferma('safe')).rejects.toThrow('rete giù');
        expect(dopo).not.toHaveBeenCalled();
    });
});

describe('avvia — la modalità è esplicita, mai indovinata', () => {
    it('avvia Safe e Mike nella modalità chiesta', async () => {
        const c = creaComandi(sorgente({}), vi.fn());
        await c.avvia('safe', 'live');
        await c.avvia('mike', 'paper');
        expect(mActSafe).toHaveBeenCalledWith('live');
        expect(mActMike).toHaveBeenCalledWith('paper');
    });

    it('OMEGA SENZA OBIETTIVO NOTO NON PARTE: meglio rifiutare che inventare', async () => {
        const c = creaComandi(sorgente({}, null), vi.fn());
        await expect(c.avvia('omega', 'live')).rejects.toBeInstanceOf(ObiettivoOmegaIgnoto);
        expect(mActOmega).not.toHaveBeenCalled();
    });

    it('con l’obiettivo noto Omega parte con QUELLO, non con un default', async () => {
        const c = creaComandi(sorgente({}, 250), vi.fn());
        await c.avvia('omega', 'paper');
        expect(mActOmega).toHaveBeenCalledWith('paper', 250, {});
    });
});

describe('cambiaImporto — MANDA I PARAMETRI INTERI, non solo quello cambiato', () => {
    it('Safe: cambia backSize e conserva laySize, exits e le chiavi ignote', async () => {
        const correnti = {
            stake: { backSize: 3, laySize: 2 },
            exits: { due_game: true },
            roba_mia: 'x',
        };
        const c = creaComandi(sorgente(correnti), vi.fn());
        await c.cambiaImporto('safe', 'stake.backSize', 7);
        expect(mUpdSafe).toHaveBeenCalledWith({
            stake: { backSize: 7, laySize: 2 },
            exits: { due_game: true },
            roba_mia: 'x',
        });
    });

    it('Mike: stessa regola, l’oggetto intero', async () => {
        const c = creaComandi(sorgente({ stake: 10, altro: 1 }), vi.fn());
        await c.cambiaImporto('mike', 'stake', 4);
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 4, altro: 1 });
    });

    it('Omega: i parametri viaggiano sotto `params`, come vuole la sua RPC', async () => {
        const c = creaComandi(sorgente({ min_stake: 0.5, altro: 2 }), vi.fn());
        await c.cambiaImporto('omega', 'min_stake', 1.5);
        expect(mUpdOmega).toHaveBeenCalledWith({ params: { min_stake: 1.5, altro: 2 } });
    });

    it('con parametri correnti SCONOSCIUTI non si azzera niente: si manda solo la chiave', async () => {
        const c = creaComandi(sorgente(null), vi.fn());
        await c.cambiaImporto('mike', 'stake', 4);
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 4 });
    });
});

describe('cambiaModalita — ogni servizio col suo meccanismo', () => {
    it('Omega e Mike la cambiano con update_params', async () => {
        const c = creaComandi(sorgente({ stake: 10 }), vi.fn());
        await c.cambiaModalita('omega', 'live');
        expect(mUpdOmega).toHaveBeenCalledWith({ mode: 'live' });
        await c.cambiaModalita('mike', 'paper');
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 10 }, 'paper');
    });

    it('SAFE si riattiva: la sua RPC di update non accetta il mode', async () => {
        const c = creaComandi(sorgente({}), vi.fn());
        await c.cambiaModalita('safe', 'live');
        expect(mActSafe).toHaveBeenCalledWith('live');
        expect(mUpdSafe).not.toHaveBeenCalled();
    });
});
