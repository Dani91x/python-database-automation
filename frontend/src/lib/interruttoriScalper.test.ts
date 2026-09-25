// ============================================================================
// interruttoriScalper.test.ts - la riga "Scalper calcio" della plancia: che
// cosa scrive sul database e che cosa si RIFIUTA di scrivere.
//
// 24/09: lo scalper si armava SOLO per partita e da qui si fermava soltanto.
// 25/09 (ordine dell'utente: «lo scalper deve lavorare da solo su tutte le
// partite del feed come gli altri bot»): AVVIA accende l'interruttore globale
// con la modalita' SCRITTA (`scalper_auto_activate`), FERMA spegne e ferma
// tutte le sessioni in UN gesto (`scalper_auto_stop`; migrazione assente = il
// FERMA di prima, sessione per sessione con la guardia d'identita'), lo stake
// e' la colonna dell'interruttore (`scalper_auto_update`), la modalita' NON si
// cambia a caldo. Nessun gesto sullo scalper tocca un altro bot (il 16/09
// "avvia il tennis" accendeva anche il calcio).
//
// I finti parlano come il vero: le sessioni hanno le chiavi di
// `get_scalper_control_room`, lo stop le tre della RPC `scalper_stop_sessione`.
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
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    fetchScalperControlRoom: vi.fn(),
    stopScalperSessione: vi.fn(async () => ({})),
    attivaScalperAuto: vi.fn(async () => ({})),
    fermaScalperAuto: vi.fn(async () => 2),
    aggiornaScalperAuto: vi.fn(async () => ({})),
}));

import {
    creaInterruttori, interruttoreDi, ScalperModalitaAllAvvio, ScalperNonTutteFermate,
    ScalperImportoSconosciuto, type Bot, type SorgenteInterruttori,
} from '@/lib/interruttori';
import { activateOmega, stopOmega, updateOmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams } from '@/lib/mike';
import {
    activateTennisBotService, stopTennisBotService, updateTennisBotService,
} from '@/lib/tennis';
import {
    fetchScalperControlRoom, stopScalperSessione, attivaScalperAuto, fermaScalperAuto,
    aggiornaScalperAuto,
} from '@/lib/scalperControlRoom';
import { svegliaBot } from '@/lib/localChannel';
import { sessione } from '@/lib/__fixtures__/scalperFinti';

const mFetch = vi.mocked(fetchScalperControlRoom);
const mStop = vi.mocked(stopScalperSessione);
const mAttiva = vi.mocked(attivaScalperAuto);
const mFerma = vi.mocked(fermaScalperAuto);
const mAggiorna = vi.mocked(aggiornaScalperAuto);

/** tutte le RPC di scrittura degli ALTRI bot: nessuna deve partire */
const altreScritture = () => [
    activateOmega, stopOmega, updateOmegaParams, activateSafe, stopSafe, updateSafeParams,
    activateMike, stopMike, updateMikeParams,
    activateTennisBotService, stopTennisBotService, updateTennisBotService,
].map((f) => vi.mocked(f).mock.calls.length);

function sorgente(): SorgenteInterruttori {
    return {
        params: (_b: Bot) => ({ stake: 10 }),
        servizio: (_b: Bot) => ({ inCorsa: false, modalita: null }),
        obiettivoOmega: () => 250,
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    mStop.mockResolvedValue({} as never);
    mFerma.mockResolvedValue(2);
});

describe('la riga Scalper calcio nel catalogo', () => {
    it('comanda il bot scalper, sport calcio, stake come colonna, modalita\' solo all\'avvio', () => {
        const i = interruttoreDi('scalper');
        expect(i).toMatchObject({ bot: 'scalper', strategia: null, sport: 'calcio', chiaveImporto: 'stake' });
        expect(i.armoPerPartita).toBeUndefined();
        expect(i.modalitaSoloAllAvvio).toBe('prova o soldi veri si scelgono all’avvio: per cambiare, ferma e riavvia');
    });
});

describe('AVVIA: l\'interruttore globale con la modalita\' scritta', () => {
    it.each([['paper'], ['live']] as const)('avvia in %s: scalper_auto_activate e nient\'altro', async (m) => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await c.accendi('scalper', m);
        expect(mAttiva.mock.calls).toEqual([[m]]);
        expect(mFerma).not.toHaveBeenCalled();
        expect(altreScritture().every((n) => n === 0)).toBe(true);
        expect(vi.mocked(svegliaBot)).not.toHaveBeenCalled();
        expect(dopo).toHaveBeenCalledTimes(1);
    });
});

describe('FERMA: interruttore spento e sessioni ferme in UN gesto', () => {
    it('scalper_auto_stop, nessuna lettura, nessuno stop per sessione, nessun altro bot', async () => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await c.spegni('scalper');
        expect(mFerma).toHaveBeenCalledTimes(1);
        expect(mFetch).not.toHaveBeenCalled();
        expect(mStop).not.toHaveBeenCalled();
        expect(altreScritture().every((n) => n === 0)).toBe(true);
        expect(dopo).toHaveBeenCalledTimes(1);
    });

    it('migrazione non applicata: il FERMA di prima, sessione per sessione con la firma', async () => {
        mFerma.mockRejectedValue(new Error('Could not find the function public.scalper_auto_stop without parameters in the schema cache'));
        mFetch.mockResolvedValue({
            sessioni: [
                sessione({ event_id: '1', status: 'running', dry_run: true, requested_at: '2026-09-24T12:00:00.123456+00:00' }),
                sessione({ event_id: '2', status: 'armed', dry_run: false, requested_at: '2026-09-24T12:05:00.5+00:00' }),
                sessione({ event_id: '4', status: 'stopping' }),
                sessione({ event_id: '5', status: 'stopped' }),
            ],
            ordini: [], lettoAt: null,
        });
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await c.fermaBot('scalper');
        expect(mStop.mock.calls).toEqual([
            ['1', '2026-09-24T12:00:00.123456+00:00', 'paper'],   // la firma passa INTATTA
            ['2', '2026-09-24T12:05:00.5+00:00', 'live'],
        ]);
        expect(dopo).toHaveBeenCalledTimes(1);
    });

    it('migrazione assente e una sessione rifiutata: prova tutte, poi dice quale', async () => {
        mFerma.mockRejectedValue(new Error('Could not find the function public.scalper_auto_stop'));
        mFetch.mockResolvedValue({
            sessioni: [sessione({ event_id: '1' }), sessione({ event_id: '3', dry_run: null })],
            ordini: [], lettoAt: null,
        });
        mStop.mockImplementation(async (ev: string) => {
            if (ev === '1') throw new Error('richiesta_ambigua: la sessione di 1 e\' stata riarmata');
            return {} as never;
        });
        const dopo = vi.fn();
        const err = await creaInterruttori(sorgente(), dopo).fermaBot('scalper').catch((e: unknown) => e);
        expect(err).toBeInstanceOf(ScalperNonTutteFermate);
        expect(String((err as Error).message)).toContain('1 (richiesta_ambigua');
        expect(String((err as Error).message)).toContain('3 (modalita');
        expect(dopo).toHaveBeenCalledTimes(1);
    });

    it('un errore VERO della RPC (non "funzione assente") si propaga: niente ripiego silenzioso', async () => {
        mFerma.mockRejectedValue(new Error('non autorizzato (owner-only)'));
        const dopo = vi.fn();
        await expect(creaInterruttori(sorgente(), dopo).spegni('scalper')).rejects.toThrow('owner-only');
        expect(mFetch).not.toHaveBeenCalled();
        expect(dopo).toHaveBeenCalledTimes(1);   // la pagina si rilegge comunque
    });
});

describe('la modalita\' non si cambia a caldo; lo stake si', () => {
    it.each([
        ['passa a soldi veri', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalita('scalper', 'live')],
        ['passa a prova', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalita('scalper', 'paper')],
        ['tetto di modalita', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalitaServizio('scalper', 'live')],
    ])('%s: rifiutato con il motivo, e NESSUNA scrittura', async (_nome, gesto) => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await expect(gesto(c)).rejects.toBeInstanceOf(ScalperModalitaAllAvvio);
        expect(mAttiva).not.toHaveBeenCalled();
        expect(mFerma).not.toHaveBeenCalled();
        expect(altreScritture().every((n) => n === 0)).toBe(true);
        expect(dopo).not.toHaveBeenCalled();
    });

    it('stake: scalper_auto_update, e nient\'altro', async () => {
        const dopo = vi.fn();
        await creaInterruttori(sorgente(), dopo).cambiaImporto('scalper', 'stake', 5);
        expect(mAggiorna.mock.calls).toEqual([[{ stake: 5 }]]);
        expect(mAttiva).not.toHaveBeenCalled();
        expect(altreScritture().every((n) => n === 0)).toBe(true);
        expect(dopo).toHaveBeenCalledTimes(1);
    });

    it('un\'altra chiave: rifiutata', async () => {
        const dopo = vi.fn();
        await expect(creaInterruttori(sorgente(), dopo).cambiaImporto('scalper', 'min_size', 5))
            .rejects.toBeInstanceOf(ScalperImportoSconosciuto);
        expect(mAggiorna).not.toHaveBeenCalled();
    });
});
