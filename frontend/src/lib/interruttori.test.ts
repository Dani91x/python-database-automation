// ============================================================================
// interruttori.test.ts — UN INTERRUTTORE PER BOT, E QUELLO CHE SCRIVE SUL DB.
//
// Qui non si collauda una formula: si impedisce che accendere una strategia
// ne accenda un'altra, che spegnere l'ultima le riaccenda tutte (il servizio
// legge `variants: []` come «usa il default»), e che un salvataggio
// dell'importo porti via tutti gli altri parametri del bot.
//
// I FINTI PARLANO COME IL VERO: le chiavi sono quelle della riga di control
// (`variants`, `strategy_modes`, `stake.per_strategia`, `mode`, `status`), e i
// payload si confrontano CAMPO PER CAMPO — il 15/09 un finto in camelCase ha
// certificato un bug e sono usciti 32 ordini reali in loop.
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
// i quattro bot tennis parlano con `tennis_bot_service_control`: il finto ha
// le STESSE firme del vero (bot_key, mode, stake, params), perche' un finto
// che parla un'altra lingua certifica un bug invece di trovarlo.
vi.mock('@/lib/tennis', () => ({
    activateTennisBotService: vi.fn(async () => ({})),
    stopTennisBotService: vi.fn(async () => ({})),
    updateTennisBotService: vi.fn(async () => ({})),
}));

import {
    INTERRUTTORI, interruttoriDiSport, interruttoreDi, statoInterruttore,
    accensioniCorrenti, paramsAccensioni, modalitaServizio, nessunaAccesa,
    leggiChiave, scriviChiave, importoDi, importiInterruttori, creaInterruttori,
    ObiettivoOmegaIgnoto, ParametriOmegaIgnoti, ParametriNonLetti,
    BotFermoNonCambiaModalita,
    STRATEGIE_SAFE_TUTTE,
    type Accensioni, type Bot, type SorgenteInterruttori, type StatoServizio,
} from '@/lib/interruttori';
import { activateOmega, stopOmega, updateOmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams } from '@/lib/mike';
import {
    activateTennisBotService, stopTennisBotService, updateTennisBotService,
} from '@/lib/tennis';

const mActOmega = vi.mocked(activateOmega);
const mStopOmega = vi.mocked(stopOmega);
const mUpdOmega = vi.mocked(updateOmegaParams);
const mActSafe = vi.mocked(activateSafe);
const mStopSafe = vi.mocked(stopSafe);
const mUpdSafe = vi.mocked(updateSafeParams);
const mActMike = vi.mocked(activateMike);
const mStopMike = vi.mocked(stopMike);
const mUpdMike = vi.mocked(updateMikeParams);
const mActTennis = vi.mocked(activateTennisBotService);
const mStopTennis = vi.mocked(stopTennisBotService);
const mUpdTennis = vi.mocked(updateTennisBotService);

beforeEach(() => { vi.clearAllMocks(); });

/** i parametri come stanno sul servizio: chiavi vere, comprese quelle che
 *  nessun tipo conosce (arrivano cosi' dalla riga di control) */
const CORRENTI_SAFE: Record<string, unknown> = {
    variants: ['base', 'esatto', 'punta', 'tennis'],
    strategy_modes: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'live' },
    stake: { laySize: 2, backSize: 3 },
    tennis_exit_approval: true,
    daily_loss_stop: -50,
    exits: { due_game: true },
    chiave_che_nessuno_conosce: 42,
};

/** Safe in corsa in live, con il solo tennis a soldi veri: e' lo stato reale
 *  del 14-16/09 (`strategy_modes.tennis = 'live'`). */
const SERVIZIO_SAFE: StatoServizio = {
    inCorsa: true, modalita: 'live',
    varianti: ['base', 'esatto', 'punta', 'tennis'],
    modiStrategia: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'live' },
};

function sorgente(over: Partial<{
    safe: Record<string, unknown> | null;
    omega: Record<string, unknown> | null;
    mike: Record<string, unknown> | null;
    servizioSafe: StatoServizio | null;
    servizioOmega: StatoServizio | null;
    servizioMike: StatoServizio | null;
    obiettivo: number | null;
}> = {}): SorgenteInterruttori {
    const safe = 'safe' in over ? over.safe ?? null : CORRENTI_SAFE;
    return {
        params: (b: Bot) => (b === 'safe' ? safe
            : b === 'omega' ? ('omega' in over ? over.omega ?? null : { min_stake: 2 })
                : ('mike' in over ? over.mike ?? null : { stake: 10 })),
        servizio: (b: Bot) => (b === 'safe' ? ('servizioSafe' in over ? over.servizioSafe ?? null : SERVIZIO_SAFE)
            : b === 'omega' ? (over.servizioOmega ?? { inCorsa: false, modalita: null })
                : (over.servizioMike ?? { inCorsa: false, modalita: null })),
        obiettivoOmega: () => ('obiettivo' in over ? over.obiettivo ?? null : 250),
    };
}

// ---------------------------------------------------------------- il catalogo

describe('i dieci interruttori, divisi per sport', () => {
    it('la scheda calcio non contiene il tennis', () => {
        expect(interruttoriDiSport('calcio').map((i) => i.id))
            .toEqual(['omega', 'mike', 'safe-base', 'safe-esatto', 'safe-punta']);
    });

    it('la scheda tennis non contiene il calcio', () => {
        expect(interruttoriDiSport('tennis').map((i) => i.id)).toEqual([
            'safe-tennis',
            // i QUATTRO BOT del tennis (17/09): servizi indipendenti, non
            // strategie di Safe
            'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing',
        ]);
    });

    it('senza scheda scelta ci sono tutti e dieci', () => {
        expect(interruttoriDiSport(null)).toHaveLength(10);
        expect(INTERRUTTORI).toHaveLength(10);
    });

    it('i quattro del tennis comandano il SERVIZIO, non una strategia', () => {
        for (const id of ['tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing'] as const) {
            const i = interruttoreDi(id);
            expect(i.strategia).toBeNull();      // non e' una variante di Safe
            expect(i.bot).toBe(id);              // un bot per riga: nessuno condiviso
            expect(i.sport).toBe('tennis');
            // lo stake e' la COLONNA della riga di control, non una voce annidata
            expect(i.chiaveImporto).toBe('stake');
            expect(i.chiaveImportoPerLato).toBeNull();
        }
    });

    it('ogni interruttore di Safe nomina la sua strategia e la sua chiave di stake', () => {
        expect(interruttoreDi('safe-punta').strategia).toBe('punta');
        expect(interruttoreDi('safe-punta').chiaveImporto).toBe('stake.per_strategia.punta');
        expect(interruttoreDi('safe-punta').chiaveImportoPerLato).toBe('stake.backSize');
        expect(interruttoreDi('safe-base').chiaveImportoPerLato).toBe('stake.laySize');
    });
});

// ------------------------------------------------------------------- lo stato

describe('statoInterruttore — si legge da variants + strategy_modes, non da un flag', () => {
    it('una strategia in `variants` a servizio in corsa e ACCESA', () => {
        expect(statoInterruttore(interruttoreDi('safe-base'), SERVIZIO_SAFE).acceso).toBe(true);
    });

    it('una strategia FUORI da `variants` e spenta anche a servizio in corsa', () => {
        const s = { ...SERVIZIO_SAFE, varianti: ['tennis'] };
        expect(statoInterruttore(interruttoreDi('safe-base'), s).acceso).toBe(false);
        expect(statoInterruttore(interruttoreDi('safe-tennis'), s).acceso).toBe(true);
    });

    it('servizio fermo = tutte le strategie spente', () => {
        const s = { ...SERVIZIO_SAFE, inCorsa: false };
        for (const i of INTERRUTTORI) expect(statoInterruttore(i, s).acceso).toBe(false);
    });

    it('SOLDI VERI solo se scritto DUE volte: mode del servizio E voce della strategia', () => {
        expect(statoInterruttore(interruttoreDi('safe-tennis'), SERVIZIO_SAFE).modalita).toBe('live');
        expect(statoInterruttore(interruttoreDi('safe-base'), SERVIZIO_SAFE).modalita).toBe('paper');
        // servizio in prova: il mode e' un TETTO, nessuna strategia e' in live
        const prova = { ...SERVIZIO_SAFE, modalita: 'paper' as const };
        expect(statoInterruttore(interruttoreDi('safe-tennis'), prova).modalita).toBe('paper');
    });

    it('servizio in corsa senza `variants` = NON LO SO, e non si comanda', () => {
        const s = { ...SERVIZIO_SAFE, varianti: null };
        expect(statoInterruttore(interruttoreDi('safe-base'), s).noto).toBe(false);
    });

    it('Omega e Mike: acceso = il servizio e in corsa', () => {
        expect(statoInterruttore(interruttoreDi('omega'), { inCorsa: true, modalita: 'live' }))
            .toEqual({ acceso: true, modalita: 'live', noto: true });
        expect(statoInterruttore(interruttoreDi('mike'), null))
            .toEqual({ acceso: false, modalita: null, noto: false });
    });
});

// --------------------------------------------------------- le due mappe intere

describe('paramsAccensioni — le due mappe si scrivono SEMPRE intere', () => {
    const acc: Accensioni = { base: 'paper', esatto: null, punta: null, tennis: 'live' };

    it('`variants` contiene SOLO le accese, nell ordine del manuale', () => {
        expect(paramsAccensioni(CORRENTI_SAFE, acc).variants).toEqual(['base', 'tennis']);
    });

    it('`strategy_modes` nomina TUTTE le strategie: una chiave assente erediterebbe il servizio', () => {
        const modi = paramsAccensioni(CORRENTI_SAFE, acc).strategy_modes as Record<string, string>;
        for (const s of STRATEGIE_SAFE_TUTTE) expect(modi[s]).toBeDefined();
        expect(modi).toEqual({
            base: 'paper', esatto: 'paper', punta: 'paper',
            tennis: 'live', model: 'paper', manual: 'paper',
        });
    });

    it('una strategia SPENTA non e mai in live: spenta vuol dire paper', () => {
        const modi = paramsAccensioni(CORRENTI_SAFE, acc).strategy_modes as Record<string, string>;
        expect(modi.punta).toBe('paper');
        expect(modi.esatto).toBe('paper');
    });

    it('una strategia che oggi non conosciamo viene comunque NOMINATA', () => {
        const modi = paramsAccensioni(
            { strategy_modes: { strategia_nuova: 'live' } }, acc,
        ).strategy_modes as Record<string, string>;
        expect(modi.strategia_nuova).toBe('live');   // conservata: non e' nostra da spegnere
        const inProva = paramsAccensioni(
            { strategy_modes: { strategia_nuova: 'live' } }, acc, 'prova',
        ).strategy_modes as Record<string, string>;
        expect(inProva.strategia_nuova).toBe('paper');
    });

    it('model e manual restano come sono: spegnerli in silenzio sarebbe alterare una scelta', () => {
        const modi = paramsAccensioni(
            { ...CORRENTI_SAFE, strategy_modes: { manual: 'live' } }, acc,
        ).strategy_modes as Record<string, string>;
        expect(modi.manual).toBe('live');
    });

    it('non porta via niente e non muta i parametri di partenza', () => {
        const copia = JSON.parse(JSON.stringify(CORRENTI_SAFE));
        const p = paramsAccensioni(CORRENTI_SAFE, acc);
        expect(p.tennis_exit_approval).toBe(true);
        expect(p.daily_loss_stop).toBe(-50);
        expect(p.exits).toEqual({ due_game: true });
        expect(p.chiave_che_nessuno_conosce).toBe(42);
        expect(p.stake).toEqual({ laySize: 2, backSize: 3 });
        expect(CORRENTI_SAFE).toEqual(copia);
    });

    it('la modalita del SERVIZIO e live se e solo se lo e almeno una strategia', () => {
        expect(modalitaServizio(acc)).toBe('live');
        expect(modalitaServizio({ base: 'paper', esatto: null, punta: null, tennis: 'paper' })).toBe('paper');
        expect(nessunaAccesa({ base: null, esatto: null, punta: null, tennis: null })).toBe(true);
    });
});

describe('accensioniCorrenti — quello che il servizio sta facendo adesso', () => {
    it('legge le quattro strategie con la loro modalita', () => {
        expect(accensioniCorrenti(SERVIZIO_SAFE))
            .toEqual({ base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'live' });
    });

    it('il DANNO del 16/09 (`variants = ["tennis"]`) si legge per quello che e', () => {
        expect(accensioniCorrenti({ ...SERVIZIO_SAFE, varianti: ['tennis'] }))
            .toEqual({ base: null, esatto: null, punta: null, tennis: 'live' });
    });
});

// ------------------------------------------------------------ i gesti su Safe

describe('accendi / spegni una strategia di Safe — payload campo per campo', () => {
    it('accendere BASE in prova NON tocca il tennis che opera con soldi veri', async () => {
        const c = creaInterruttori(sorgente({ servizioSafe: { ...SERVIZIO_SAFE, varianti: ['tennis'] } }), vi.fn());
        await c.accendi('safe-base', 'paper');
        expect(mUpdSafe).toHaveBeenCalledTimes(1);
        const p = mUpdSafe.mock.calls[0][0] as Record<string, unknown>;
        expect(p.variants).toEqual(['base', 'tennis']);
        expect(p.strategy_modes).toEqual({
            base: 'paper', esatto: 'paper', punta: 'paper',
            tennis: 'live', model: 'paper', manual: 'paper',
        });
        // il servizio e gia in live per il tennis: non si riattiva niente
        expect(mActSafe).not.toHaveBeenCalled();
        expect(mStopSafe).not.toHaveBeenCalled();
    });

    it('la PRIMA strategia in live arma il servizio: `safe_activate("live")` con params espliciti', async () => {
        const servizioSafe: StatoServizio = {
            inCorsa: true, modalita: 'paper',
            varianti: ['base'], modiStrategia: { base: 'paper' },
        };
        const c = creaInterruttori(sorgente({ servizioSafe }), vi.fn());
        await c.cambiaModalita('safe-base', 'live');
        expect(mActSafe).toHaveBeenCalledTimes(1);
        expect(mActSafe.mock.calls[0][0]).toBe('live');
        const p = mActSafe.mock.calls[0][1] as Record<string, unknown>;
        expect(p.variants).toEqual(['base']);
        expect((p.strategy_modes as Record<string, string>).base).toBe('live');
        expect(mUpdSafe).not.toHaveBeenCalled();
    });

    it('a servizio FERMO accendere una strategia lo avvia con i parametri espliciti', async () => {
        const c = creaInterruttori(sorgente({
            servizioSafe: { inCorsa: false, modalita: null, varianti: null, modiStrategia: null },
        }), vi.fn());
        await c.accendi('safe-punta', 'paper');
        expect(mActSafe).toHaveBeenCalledWith('paper', expect.objectContaining({
            variants: ['punta'],
        }));
    });

    it('spegnere l ULTIMA strategia = `safe_stop`: `variants: []` le riaccenderebbe tutte', async () => {
        const servizioSafe: StatoServizio = {
            inCorsa: true, modalita: 'live',
            varianti: ['tennis'], modiStrategia: { tennis: 'live' },
        };
        const c = creaInterruttori(sorgente({ servizioSafe }), vi.fn());
        await c.spegni('safe-tennis');
        expect(mStopSafe).toHaveBeenCalledTimes(1);
        expect(mUpdSafe).not.toHaveBeenCalled();
        expect(mActSafe).not.toHaveBeenCalled();
    });

    it('spegnere una strategia quando ne restano altre la toglie SOLO da `variants`', async () => {
        const c = creaInterruttori(sorgente(), vi.fn());
        await c.spegni('safe-esatto');
        const p = mUpdSafe.mock.calls[0][0] as Record<string, unknown>;
        expect(p.variants).toEqual(['base', 'punta', 'tennis']);
        expect((p.strategy_modes as Record<string, string>).esatto).toBe('paper');
        expect((p.strategy_modes as Record<string, string>).tennis).toBe('live');
    });

    it('spegnendo l ultima strategia LIVE il servizio torna in prova', async () => {
        const servizioSafe: StatoServizio = {
            inCorsa: true, modalita: 'live',
            varianti: ['base', 'tennis'], modiStrategia: { base: 'paper', tennis: 'live' },
        };
        const c = creaInterruttori(sorgente({ servizioSafe }), vi.fn());
        await c.spegni('safe-tennis');
        expect(mActSafe).toHaveBeenCalledTimes(1);
        expect(mActSafe.mock.calls[0][0]).toBe('paper');
        expect(mActSafe.mock.calls[0][1]).toEqual(expect.objectContaining({ variants: ['base'] }));
    });

    it('senza i parametri correnti NON si scrive niente', async () => {
        const c = creaInterruttori(sorgente({ safe: null }), vi.fn());
        await expect(c.accendi('safe-base', 'paper')).rejects.toBeInstanceOf(ParametriNonLetti);
        await expect(c.spegni('safe-base')).rejects.toBeInstanceOf(ParametriNonLetti);
        expect(mActSafe).not.toHaveBeenCalled();
        expect(mUpdSafe).not.toHaveBeenCalled();
        expect(mStopSafe).not.toHaveBeenCalled();
    });
});

// ---------------------------------------------------------------- Omega e Mike

describe('Omega e Mike — un interruttore per il servizio intero', () => {
    it('Mike si accende nella modalita scelta e si ferma con la sua RPC', async () => {
        const c = creaInterruttori(sorgente(), vi.fn());
        await c.accendi('mike', 'live');
        expect(mActMike).toHaveBeenCalledWith('live');
        await c.spegni('mike');
        expect(mStopMike).toHaveBeenCalledTimes(1);
    });

    it('Omega si accende con l obiettivo e i parametri CORRENTI, mai con un oggetto vuoto', async () => {
        const c = creaInterruttori(sorgente({ omega: { min_stake: 0.5, daily_loss_cap: 30 } }), vi.fn());
        await c.accendi('omega', 'paper');
        expect(mActOmega).toHaveBeenCalledWith('paper', 250, { min_stake: 0.5, daily_loss_cap: 30 });
        await c.spegni('omega');
        expect(mStopOmega).toHaveBeenCalledTimes(1);
    });

    it('Omega senza obiettivo o senza parametri NON parte', async () => {
        await expect(creaInterruttori(sorgente({ obiettivo: null }), vi.fn()).accendi('omega', 'live'))
            .rejects.toBeInstanceOf(ObiettivoOmegaIgnoto);
        await expect(creaInterruttori(sorgente({ omega: null }), vi.fn()).accendi('omega', 'live'))
            .rejects.toBeInstanceOf(ParametriOmegaIgnoti);
        expect(mActOmega).not.toHaveBeenCalled();
    });

    it('la modalita di Mike passa da `mike_update_params` con i parametri INTERI', async () => {
        const c = creaInterruttori(sorgente({ mike: { stake: 10, altro: 1 } }), vi.fn());
        await c.cambiaModalita('mike', 'live');
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 10, altro: 1 }, 'live');
        const senza = creaInterruttori(sorgente({ mike: null }), vi.fn());
        await expect(senza.cambiaModalita('mike', 'live')).rejects.toBeInstanceOf(ParametriNonLetti);
    });

    it('la modalita di Omega passa da `omega_update_params`', async () => {
        await creaInterruttori(sorgente(), vi.fn()).cambiaModalita('omega', 'paper');
        expect(mUpdOmega).toHaveBeenCalledWith({ mode: 'paper' });
    });

    it('`fermaBot` ferma il SERVIZIO, non una strategia', async () => {
        const c = creaInterruttori(sorgente(), vi.fn());
        await c.fermaBot('safe');
        expect(mStopSafe).toHaveBeenCalledTimes(1);
    });
});

// -------------------------------------------------------------- gli importi

describe('leggiChiave / scriviChiave — cambia una cosa e non porta via il resto', () => {
    it('legge anche dentro e non esplode mai', () => {
        expect(leggiChiave({ stake: { per_strategia: { punta: 7 } } }, 'stake.per_strategia.punta')).toBe(7);
        expect(leggiChiave(null, 'stake.backSize')).toBeNull();
        expect(leggiChiave({ stake: 'tre' }, 'stake.backSize')).toBeNull();
        expect(leggiChiave({ min_stake: 0 }, 'min_stake')).toBe(0);
    });

    it('conserva ogni altra chiave e non muta l oggetto di partenza', () => {
        const prima = { stake: { backSize: 3, laySize: 2 }, exits: { x: true } };
        const dopo = scriviChiave(prima, 'stake.per_strategia.punta', 5);
        expect(dopo).toEqual({
            stake: { backSize: 3, laySize: 2, per_strategia: { punta: 5 } },
            exits: { x: true },
        });
        expect(prima.stake).toEqual({ backSize: 3, laySize: 2 });
    });
});

describe('importoDi — la chiave per strategia, col ripiego DICHIARATO', () => {
    it('quando la chiave per strategia c e, si usa quella', () => {
        const c = importoDi(interruttoreDi('safe-punta'),
                            { stake: { backSize: 3, per_strategia: { punta: 11 } } });
        expect(c.chiave).toBe('stake.per_strategia.punta');
        expect(c.valore).toBe(11);
        expect(c.ereditato).toBeUndefined();
    });

    it('quando manca si mostra quella per LATO e la pagina lo DICE', () => {
        const c = importoDi(interruttoreDi('safe-punta'), { stake: { backSize: 3 } });
        expect(c.valore).toBe(3);
        expect(c.ereditato).toMatch(/per lato/);
        // e salvando si scrive sulla chiave SUA, non su quella condivisa
        expect(c.chiave).toBe('stake.per_strategia.punta');
    });

    it('base ed esatto ripiegano su `laySize`, punta e tennis su `backSize`', () => {
        const p = { stake: { laySize: 2, backSize: 3 } };
        expect(importoDi(interruttoreDi('safe-base'), p).valore).toBe(2);
        expect(importoDi(interruttoreDi('safe-esatto'), p).valore).toBe(2);
        expect(importoDi(interruttoreDi('safe-punta'), p).valore).toBe(3);
        expect(importoDi(interruttoreDi('safe-tennis'), p).valore).toBe(3);
    });

    it('Omega dichiara che il suo e un MINIMO, Mike il suo stake', () => {
        expect(importoDi(interruttoreDi('omega'), { min_stake: 0.5 }).nota).toMatch(/minimo/);
        expect(importoDi(interruttoreDi('mike'), { stake: 10 }).valore).toBe(10);
        expect(importoDi(interruttoreDi('mike'), {}).valore).toBeNull();
    });

    it('ogni interruttore visibile ha il suo importo', () => {
        const m = importiInterruttori(interruttoriDiSport('calcio'), () => CORRENTI_SAFE);
        expect(Object.keys(m).sort())
            .toEqual(['mike', 'omega', 'safe-base', 'safe-esatto', 'safe-punta']);
    });
});

describe('cambiaImporto — riparte SEMPRE dai parametri correnti', () => {
    it('lo stake della PUNTA si scrive sulla chiave sua e non tocca il tennis', async () => {
        const c = creaInterruttori(sorgente(), vi.fn());
        await c.cambiaImporto('safe-punta', 'stake.per_strategia.punta', 7);
        const p = mUpdSafe.mock.calls[0][0] as Record<string, unknown>;
        expect(p.stake).toEqual({ laySize: 2, backSize: 3, per_strategia: { punta: 7 } });
        // tutto il resto passa intatto: `strategy_modes` compreso
        expect(p.strategy_modes).toEqual(CORRENTI_SAFE.strategy_modes);
        expect(p.variants).toEqual(CORRENTI_SAFE.variants);
        expect(p.tennis_exit_approval).toBe(true);
    });

    it('senza i parametri correnti non si salva: sostituirebbe tutti gli altri', async () => {
        const c = creaInterruttori(sorgente({ safe: null }), vi.fn());
        await expect(c.cambiaImporto('safe-base', 'stake.per_strategia.base', 5))
            .rejects.toBeInstanceOf(ParametriNonLetti);
        expect(mUpdSafe).not.toHaveBeenCalled();
    });

    it('Mike e Omega scrivono con le loro RPC, sempre con i parametri interi', async () => {
        const c = creaInterruttori(sorgente({ mike: { stake: 10, altro: 1 }, omega: { min_stake: 0.5, x: 2 } }), vi.fn());
        await c.cambiaImporto('mike', 'stake', 12);
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 12, altro: 1 });
        await c.cambiaImporto('omega', 'min_stake', 1);
        expect(mUpdOmega).toHaveBeenCalledWith({ params: { min_stake: 1, x: 2 } });
    });
});

describe('dopo() — la pagina rilegge dal SERVIZIO, non si fida di se stessa', () => {
    it('ogni gesto riuscito chiama `dopo`', async () => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await c.accendi('safe-base', 'paper');
        await c.spegni('mike');
        await c.cambiaImporto('mike', 'stake', 3);
        expect(dopo).toHaveBeenCalledTimes(3);
    });

    it('un gesto FALLITO non chiama `dopo`', async () => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente({ safe: null }), dopo);
        await expect(c.accendi('safe-base', 'paper')).rejects.toBeTruthy();
        expect(dopo).not.toHaveBeenCalled();
    });
});

// ===========================================================================
// UN CAMBIO DI MODALITA' NON ACCENDE MAI NIENTE (ordine del 16/09)
//
// `X_activate` porta `status` a 'running'. Usarlo per cambiare solo la
// modalita' vuol dire che il gesto «passa a soldi veri» puo' ACCENDERE un bot
// fermo — e i bot li accende l'utente, con il gesto di accensione, scegliendo
// li' la modalita'.
// ===========================================================================

describe('cambiaModalita su un bot FERMO non contiene nessuna accensione', () => {
    it('Mike fermo: `mike_update_params(p_mode)`, MAI `mike_activate`', async () => {
        const c = creaInterruttori(sorgente({
            servizioMike: { inCorsa: false, modalita: null },
            mike: { stake: 10, altro: 1 },
        }), vi.fn());
        await c.cambiaModalita('mike', 'live');
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 10, altro: 1 }, 'live');
        expect(mActMike).not.toHaveBeenCalled();
    });

    it('Omega fermo: `omega_update_params(p_mode)`, MAI `omega_activate`', async () => {
        const c = creaInterruttori(sorgente({ servizioOmega: { inCorsa: false, modalita: null } }), vi.fn());
        await c.cambiaModalita('omega', 'live');
        expect(mUpdOmega).toHaveBeenCalledWith({ mode: 'live' });
        expect(mActOmega).not.toHaveBeenCalled();
    });

    it('Safe FERMO: ci si RIFIUTA, perche `safe_activate` lo accenderebbe', async () => {
        const c = creaInterruttori(sorgente({
            servizioSafe: { inCorsa: false, modalita: null, varianti: null, modiStrategia: null },
        }), vi.fn());
        await expect(c.cambiaModalita('safe-base', 'live'))
            .rejects.toBeInstanceOf(BotFermoNonCambiaModalita);
        await expect(c.cambiaModalitaServizio('safe', 'live'))
            .rejects.toBeInstanceOf(BotFermoNonCambiaModalita);
        expect(mActSafe).not.toHaveBeenCalled();
        expect(mUpdSafe).not.toHaveBeenCalled();
        expect(mStopSafe).not.toHaveBeenCalled();
    });

    it('Safe GIA in corsa: riarmare il `mode` non accende niente, ed e permesso', async () => {
        const servizioSafe: StatoServizio = {
            inCorsa: true, modalita: 'paper',
            varianti: ['base'], modiStrategia: { base: 'paper' },
        };
        const c = creaInterruttori(sorgente({ servizioSafe }), vi.fn());
        await c.cambiaModalita('safe-base', 'live');
        expect(mActSafe).toHaveBeenCalledTimes(1);
        expect(mActSafe.mock.calls[0][0]).toBe('live');
    });

    it('ACCENDERE invece puo far partire il servizio: e il suo mestiere', async () => {
        const c = creaInterruttori(sorgente({
            servizioSafe: { inCorsa: false, modalita: null, varianti: null, modiStrategia: null },
        }), vi.fn());
        await c.accendi('safe-base', 'paper');
        expect(mActSafe).toHaveBeenCalledTimes(1);
    });

    it('`cambiaModalitaServizio` su Omega e Mike non passa mai da `activate`', async () => {
        const c = creaInterruttori(sorgente(), vi.fn());
        await c.cambiaModalitaServizio('omega', 'paper');
        await c.cambiaModalitaServizio('mike', 'paper');
        expect(mUpdOmega).toHaveBeenCalledWith({ mode: 'paper' });
        expect(mUpdMike).toHaveBeenCalledWith({ stake: 10 }, 'paper');
        expect(mActOmega).not.toHaveBeenCalled();
        expect(mActMike).not.toHaveBeenCalled();
    });
});


// ============================================================================
// I QUATTRO BOT DEL TENNIS — «indipendenti come gli altri» (utente, 17/09).
//
// Il pericolo di questo innesto ha un nome: prima del 17/09 `fermaBot` finiva
// con `else await stopOmega()`, cioe' «tutto quello che non e' Safe ne' Mike e'
// Omega». Con quattro bot nuovi nel modello, fermare lo Scalper avrebbe fermato
// OMEGA — e Omega opera sul calcio con soldi veri. I test qui sotto ci stanno
// per quello, e sono stati FALSIFICATI: rimettendo l'`else` che c'era prima,
// «spegnere un bot tennis non ferma Omega» diventa rosso; facendo passare il
// cambio di modalita' da `activateTennisBotService`, «non accende niente»
// diventa rosso.
// ============================================================================
describe('i quattro bot tennis: ognuno parla solo con la SUA riga di control', () => {
    it('accendere in prova scrive la modalita, e non tocca gli altri bot', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.accendi('tennis_scalper', 'paper');
        expect(mActTennis).toHaveBeenCalledWith('tennis_scalper', 'paper');
        expect(mActSafe).not.toHaveBeenCalled();
        expect(mActOmega).not.toHaveBeenCalled();
        expect(mActMike).not.toHaveBeenCalled();
    });

    it('accendere in LIVE scrive «live»: ai soldi veri si arriva solo scrivendolo', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.accendi('tennis_pro', 'live');
        expect(mActTennis).toHaveBeenCalledWith('tennis_pro', 'live');
    });

    it('spegnere un bot tennis NON ferma Omega (l’`else` che c’era prima)', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.spegni('tennis_flb');
        expect(mStopTennis).toHaveBeenCalledWith('tennis_flb');
        expect(mStopOmega).not.toHaveBeenCalled();
        expect(mStopSafe).not.toHaveBeenCalled();
        expect(mStopMike).not.toHaveBeenCalled();
    });

    it('anche il freno d’emergenza ferma il bot GIUSTO', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.fermaBot('tennis_swing');
        expect(mStopTennis).toHaveBeenCalledWith('tennis_swing');
        expect(mStopOmega).not.toHaveBeenCalled();
    });

    it('cambiare modalita NON accende niente: passa da update, mai da activate', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.cambiaModalita('tennis_scalper', 'live');
        expect(mUpdTennis).toHaveBeenCalledWith('tennis_scalper', { mode: 'live' });
        expect(mActTennis).not.toHaveBeenCalled();
    });

    it('lo stake e una COLONNA: si scrive da solo e non tocca `status`', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.cambiaImporto('tennis_pro', 'stake', 3.5);
        expect(mUpdTennis).toHaveBeenCalledWith('tennis_pro', { stake: 3.5 });
        expect(mActTennis).not.toHaveBeenCalled();
        // e non passa dai parametri degli altri bot
        expect(mUpdSafe).not.toHaveBeenCalled();
        expect(mUpdMike).not.toHaveBeenCalled();
        expect(mUpdOmega).not.toHaveBeenCalled();
    });

    it('un bot tennis non e una strategia di Safe: accenderlo non riscrive `variants`', async () => {
        const c = creaInterruttori(sorgente(), () => {});
        await c.accendi('tennis_swing', 'paper');
        expect(mUpdSafe).not.toHaveBeenCalled();
        expect(mActSafe).not.toHaveBeenCalled();
    });
});
