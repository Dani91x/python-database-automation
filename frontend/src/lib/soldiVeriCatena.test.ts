// ============================================================================
// soldiVeriCatena.test.ts — «SOLDI VERI» HA SOLO DUE ESITI (04/10).
//
// Incidente: Safe tennis acceso in «soldi veri» con il runner tennis in PAPER.
// Ogni ordine rifiutato (`mode_non_servibile`), la pagina diceva «acceso in
// soldi veri» e taceva. Ordine dell'utente: «se clicca soldi veri e attiva un
// bot, quello deve partire come da progettato» — o opera davvero, o il gesto e'
// RIFIUTATO subito, col motivo, SENZA scrivere niente.
//
// I finti parlano come il vero: la riga di «Ordini reali» ha le chiavi di
// `get_live_settings` (`order_mode`, `order_mode_tetto`, ...), il modo del
// runner tennis e' quello dell'hello/battito (`'PAPER'` | `'LIVE'`).
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
vi.mock('@/lib/tennis', () => ({
    activateTennisBotService: vi.fn(async () => ({})),
    stopTennisBotService: vi.fn(async () => ({})),
    updateTennisBotService: vi.fn(async () => ({})),
}));
vi.mock('@/lib/localChannel', () => ({ svegliaBot: vi.fn() }));

import {
    INTERRUTTORI, interruttoreDi, creaInterruttori, motivoSoldiVeriNonServiti,
    statoOrdiniReali, SoldiVeriNonServiti, leggiStradaOrdini, verificaSoldiVeri,
    verificaSoldiVeriSafe,
    type Bot, type CatenaLive, type SorgenteInterruttori, type StatoServizio,
} from '@/lib/interruttori';
import { creaComandiControlRoom } from '@/components/controlroom/comandiBot';
import type { LiveSettings } from '@/lib/liveOrders';
import { activateOmega, updateOmegaParams } from '@/lib/omega';
import { activateSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, updateMikeParams } from '@/lib/mike';
import { activateTennisBotService, updateTennisBotService } from '@/lib/tennis';

beforeEach(() => { vi.clearAllMocks(); });

/** la riga VERA di `get_live_settings` (chiavi della migrazione del 24/09) */
function riga(order_mode: string | null, order_mode_tetto: string | null): LiveSettings {
    return {
        id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
        order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null,
        max_exposure_per_event: null, max_exposure_per_league: null,
        updated_at: '2026-10-04T10:00:00+00:00',
        order_mode, order_mode_updated_at: '2026-10-04T10:00:00+00:00',
        order_mode_updated_by: 'daniele', order_mode_boot_id: 'b1',
        order_mode_tetto, order_mode_tetto_at: '2026-10-04T08:00:00+00:00',
    };
}

const ARMATA: CatenaLive = {
    modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('live', 'live')),
    stradaSafeTennis: 'runner_tennis',
};
// lo stato del 04/10: calcio armato, runner tennis in PAPER, Safe tennis sul canale
const INCIDENTE: CatenaLive = {
    modoRunnerTennis: 'PAPER', ordiniReali: statoOrdiniReali(riga('live', 'live')),
    stradaSafeTennis: 'runner_tennis',
};

const SAFE_PARAMS: Record<string, unknown> = {
    variants: ['base'], strategy_modes: { base: 'paper', tennis: 'paper' }, stake: { laySize: 2 },
};
const SAFE_SERVIZIO: StatoServizio = {
    inCorsa: true, modalita: 'paper', varianti: ['base'], modiStrategia: { base: 'paper' },
};

function sorgente(catena: CatenaLive | null): SorgenteInterruttori {
    return {
        params: (b: Bot) => (b === 'safe' ? SAFE_PARAMS : b === 'omega' ? { min_stake: 2 } : { stake: 10 }),
        servizio: (b: Bot) => (b === 'safe' ? SAFE_SERVIZIO : { inCorsa: true, modalita: 'paper' }),
        obiettivoOmega: () => 250,
        rileggiSafe: async () => ({ params: SAFE_PARAMS, servizio: SAFE_SERVIZIO }),
        ...(catena ? { catenaLive: async () => catena } : {}),
    };
}

function scritture(): number {
    return [activateOmega, updateOmegaParams, activateSafe, updateSafeParams, activateMike,
        updateMikeParams, activateTennisBotService, updateTennisBotService]
        .reduce((n, f) => n + vi.mocked(f).mock.calls.length, 0);
}

// ----------------------------------------------------------- la regola, pura
describe('motivoSoldiVeriNonServiti: per ogni interruttore', () => {
    it('catena armata: nessun interruttore e’ rifiutato', () => {
        for (const i of INTERRUTTORI) expect(motivoSoldiVeriNonServiti(i, ARMATA)).toBeNull();
    });

    it('runner tennis in PAPER: rifiutati i 5 tennis, non i calcio', () => {
        const rifiutati = INTERRUTTORI.filter((i) => motivoSoldiVeriNonServiti(i, INCIDENTE) != null)
            .map((i) => i.id);
        const tennis = INTERRUTTORI.filter((i) => i.sport === 'tennis').map((i) => i.id);
        expect(tennis).toHaveLength(5);          // Safe tennis + i 4 bot tennis
        expect(rifiutati).toEqual(tennis);
        expect(motivoSoldiVeriNonServiti(interruttoreDi('safe-tennis'), INCIDENTE))
            .toContain('il runner tennis gira solo in PROVA (PAPER)');
    });

    it('runner tennis muto: rifiutato (non posso verificare)', () => {
        const m = motivoSoldiVeriNonServiti(interruttoreDi('safe-tennis'), { ...ARMATA, modoRunnerTennis: null });
        expect(m).toContain('il runner tennis non risponde');
    });

    it('«Ordini reali» su PAPER: rifiutati i calcio che passano da runner o REST (Mike compreso), non lo scalper', () => {
        const c: CatenaLive = { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('paper', 'live')) };
        const rifiutati = INTERRUTTORI.filter((i) => i.sport === 'calcio'
            && motivoSoldiVeriNonServiti(i, c) != null).map((i) => i.id);
        expect(rifiutati).toEqual(['omega', 'mike', 'safe-base', 'safe-esatto', 'safe-punta',
            'safe-model', 'safe-manual']);
        expect(motivoSoldiVeriNonServiti(interruttoreDi('mike'), c))
            .toContain('Porta prima «Ordini reali» a LIVE');
    });

    it('tetto del runner calcio PAPER: lo dice', () => {
        const c: CatenaLive = { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('live', 'paper')) };
        expect(motivoSoldiVeriNonServiti(interruttoreDi('omega'), c)).toContain('tetto PAPER');
    });

    // 04/10 (cantiere tetto tennis): il tennis segue lo STESSO «Ordini reali»
    it('tennis: runner LIVE ma «Ordini reali» in PROVA -> rifiutati i 5 tennis col motivo', () => {
        const c: CatenaLive = { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('paper', 'live')) };
        const rifiutati = INTERRUTTORI.filter((i) => i.sport === 'tennis'
            && motivoSoldiVeriNonServiti(i, c) != null).map((i) => i.id);
        expect(rifiutati).toEqual(INTERRUTTORI.filter((i) => i.sport === 'tennis').map((i) => i.id));
        expect(motivoSoldiVeriNonServiti(interruttoreDi('safe-tennis'), c))
            .toContain('Porta prima «Ordini reali» a LIVE');
    });

    it('tennis: «Ordini reali» LIVE ma tetto del CALCIO in prova -> il tennis passa (conta il suo tetto)', () => {
        // unione dei due cantieri del 04/10: per Safe tennis la strada la dichiara il
        // servizio; qui e' quella del runner tennis (a strada NON dichiarata servono
        // tutte e due le catene: caso coperto piu' sotto)
        const c: CatenaLive = {
            modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('live', 'paper')),
            stradaSafeTennis: 'runner_tennis',
        };
        expect(motivoSoldiVeriNonServiti(interruttoreDi('safe-tennis'), c)).toBeNull();
        expect(motivoSoldiVeriNonServiti(interruttoreDi('tennis_scalper'), c)).toBeNull();
    });

    it('tennis: «Ordini reali» non letto -> fail-closed', () => {
        const c: CatenaLive = { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(null) };
        expect(motivoSoldiVeriNonServiti(interruttoreDi('safe-tennis'), c)).toContain('non leggibile');
    });

    it('«Ordini reali» non letto: fail-closed', () => {
        expect(motivoSoldiVeriNonServiti(interruttoreDi('safe-base'),
            { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(null) })).toContain('non leggibile');
    });
});

// --------------------------------------------- il gesto: rifiutato, niente scritto
describe('il gesto «soldi veri» con la catena che non serve', () => {
    const casi: Array<[string, CatenaLive]> = [
        ['safe-tennis', INCIDENTE],
        ['safe-base', { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('paper', 'live')) }],
        ['omega', { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('paper', 'live')) }],
        ['mike', { modoRunnerTennis: 'LIVE', ordiniReali: statoOrdiniReali(riga('paper', 'live')) }],
    ];
    for (const [id, catena] of casi) {
        it(`${id}: accendi e cambiaModalita in live rifiutati, zero scritture`, async () => {
            const c = creaInterruttori(sorgente(catena), () => undefined);
            const i = INTERRUTTORI.find((x) => x.id === id)!;
            await expect(c.accendi(i.id, 'live')).rejects.toBeInstanceOf(SoldiVeriNonServiti);
            await expect(c.cambiaModalita(i.id, 'live')).rejects.toBeInstanceOf(SoldiVeriNonServiti);
            expect(scritture()).toBe(0);
        });
    }

    it('i 4 bot tennis: anche il cambio di modalita’ del servizio', async () => {
        const c = creaInterruttori(sorgente(INCIDENTE), () => undefined);
        for (const i of INTERRUTTORI.filter((x) => x.sport === 'tennis' && x.strategia == null)) {
            await expect(c.cambiaModalitaServizio(i.bot, 'live')).rejects.toBeInstanceOf(SoldiVeriNonServiti);
        }
        expect(scritture()).toBe(0);
    });

    it('la scheda tennis della Control Room (gesto «solo tennis»): rifiutato, zero scritture', async () => {
        const c = creaComandiControlRoom(sorgente(INCIDENTE), () => undefined, 'tennis');
        await expect(c.accendi('safe-tennis', 'live')).rejects.toBeInstanceOf(SoldiVeriNonServiti);
        await expect(c.cambiaModalita('safe-tennis', 'live')).rejects.toBeInstanceOf(SoldiVeriNonServiti);
        expect(scritture()).toBe(0);
    });

    it('in PROVA il gesto passa sempre (la catena non si legge nemmeno)', async () => {
        const letta = vi.fn(async () => INCIDENTE);
        const c = creaInterruttori({ ...sorgente(null), catenaLive: letta }, () => undefined);
        await c.accendi('omega', 'paper');
        expect(letta).not.toHaveBeenCalled();
        expect(vi.mocked(activateOmega)).toHaveBeenCalledTimes(1);
    });
});

// ------------------------- Safe tennis: la strada la DICHIARA il servizio (04/10)
describe('Safe tennis: strada dichiarata dal servizio Safe', () => {
    const tennis = () => interruttoreDi('safe-tennis');
    it('stats.strade_ordini letto con le chiavi vere', () => {
        expect(leggiStradaOrdini({ strade_ordini: { calcio: 'runner_calcio', tennis: 'diretta' } }, 'tennis'))
            .toBe('diretta');
        expect(leggiStradaOrdini({ strade_ordini: { tennis: 'runner_tennis' } }, 'tennis')).toBe('runner_tennis');
        expect(leggiStradaOrdini({ strade_ordini: { tennis: 'boh' } }, 'tennis')).toBeNull();
        expect(leggiStradaOrdini({}, 'tennis')).toBeNull();
        expect(leggiStradaOrdini(null, 'tennis')).toBeNull();
    });
    it('strada DIRETTA: il runner tennis in prova NON blocca, decide «Ordini reali»', () => {
        const diretta = { ...INCIDENTE, stradaSafeTennis: 'diretta' as const };
        expect(motivoSoldiVeriNonServiti(tennis(), diretta)).toBeNull();
        expect(motivoSoldiVeriNonServiti(tennis(), { ...diretta, modoRunnerTennis: null })).toBeNull();
        const ordiniPaper = { ...diretta, ordiniReali: statoOrdiniReali(riga('paper', 'live')) };
        expect(motivoSoldiVeriNonServiti(tennis(), ordiniPaper))
            .toContain('Porta prima «Ordini reali» a LIVE');
    });
    it('strada del RUNNER TENNIS: decide il tetto del runner tennis', () => {
        expect(motivoSoldiVeriNonServiti(tennis(), INCIDENTE)).toContain('gira solo in PROVA');
    });
    it('strada NON dichiarata: si accetta solo se tutte e due servirebbero', () => {
        const ignota = (c: CatenaLive): CatenaLive => ({ ...c, stradaSafeTennis: null });
        expect(motivoSoldiVeriNonServiti(tennis(), ignota(ARMATA))).toBeNull();
        expect(motivoSoldiVeriNonServiti(tennis(), ignota(INCIDENTE)))
            .toContain('non ha ancora dichiarato');
        expect(motivoSoldiVeriNonServiti(tennis(),
            ignota({ ...ARMATA, ordiniReali: statoOrdiniReali(riga('paper', 'live')) })))
            .toContain('non ha ancora dichiarato');
    });
    it('i 4 bot tennis restano sul runner tennis (la strada di Safe non li tocca)', () => {
        const diretta = { ...INCIDENTE, stradaSafeTennis: 'diretta' as const };
        for (const i of INTERRUTTORI.filter((x) => x.sport === 'tennis' && x.strategia == null)) {
            expect(motivoSoldiVeriNonServiti(i, diretta)).toContain('gira solo in PROVA');
        }
    });
});

// ------------------- le pagine dei singoli bot: la STESSA verifica (04/10, B)
describe('verificaSoldiVeri / verificaSoldiVeriSafe (avvio diretto delle pagine)', () => {
    const paperOR: CatenaLive = { ...ARMATA, ordiniReali: statoOrdiniReali(riga('paper', 'live')) };
    it('Omega/Mike: live con «Ordini reali» PAPER rifiutato, prova mai letta', async () => {
        await expect(verificaSoldiVeri(interruttoreDi('mike'), 'live', async () => paperOR))
            .rejects.toBeInstanceOf(SoldiVeriNonServiti);
        await expect(verificaSoldiVeri(interruttoreDi('omega'), 'live', async () => paperOR))
            .rejects.toBeInstanceOf(SoldiVeriNonServiti);
        const letta = vi.fn(async () => paperOR);
        await verificaSoldiVeri(interruttoreDi('mike'), 'paper', letta);
        expect(letta).not.toHaveBeenCalled();
        await expect(verificaSoldiVeri(interruttoreDi('mike'), 'live', async () => ARMATA))
            .resolves.toBeUndefined();
    });
    it('Safe: si verificano SOLO le strategie scritte live', async () => {
        const soloTennisLive = { strategy_modes: { base: 'paper', tennis: 'live' } };
        // runner tennis in prova + Safe tennis sul runner: rifiutato
        await expect(verificaSoldiVeriSafe(soloTennisLive, 'live', async () => INCIDENTE))
            .rejects.toThrow('Safe tennis');
        // stessa cosa sulla strada diretta: passa («Ordini reali» LIVE)
        await expect(verificaSoldiVeriSafe(soloTennisLive, 'live',
            async () => ({ ...INCIDENTE, stradaSafeTennis: 'diretta' }))).resolves.toBeUndefined();
        // nessuna strategia in live: niente da verificare, niente letto
        const letta = vi.fn(async () => paperOR);
        await verificaSoldiVeriSafe({ strategy_modes: { base: 'paper' } }, 'live', letta);
        expect(letta).not.toHaveBeenCalled();
        // base in live con «Ordini reali» PAPER: rifiutato
        await expect(verificaSoldiVeriSafe({ strategy_modes: { base: 'live' } }, 'live',
            async () => paperOR)).rejects.toThrow('Safe base');
    });
});

describe('catena armata: il gesto scrive come prima', () => {
    it('safe-tennis e mike in live passano e scrivono', async () => {
        const c = creaComandiControlRoom(sorgente(ARMATA), () => undefined, 'tennis');
        await c.accendi('safe-tennis', 'live');
        expect(vi.mocked(activateSafe).mock.calls.length + vi.mocked(updateSafeParams).mock.calls.length)
            .toBe(1);
        const c2 = creaInterruttori(sorgente(ARMATA), () => undefined);
        await c2.accendi('mike', 'live');
        expect(vi.mocked(activateMike)).toHaveBeenCalledWith('live');
    });
});
