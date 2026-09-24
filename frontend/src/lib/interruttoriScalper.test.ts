// ============================================================================
// interruttoriScalper.test.ts - la riga "Scalper calcio" della plancia: che
// cosa scrive sul database e che cosa si RIFIUTA di scrivere (24/09).
//
// Lo scalper si arma PER PARTITA: da qui si ferma (tutte le sessioni attive,
// con la guardia d'identita' della RPC), e NON si accende, non cambia
// modalita', non cambia stake. Questi test impediscono che un "avvia" o un
// "passa a soldi veri" sulla riga dello scalper tocchi un altro bot o scriva
// qualcosa: il 16/09 "avvia il tennis" accendeva anche il calcio.
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
}));

import {
    creaInterruttori, interruttoreDi, ScalperSiArmaPerPartita, ScalperNonTutteFermate,
    type Bot, type SorgenteInterruttori,
} from '@/lib/interruttori';
import { activateOmega, stopOmega, updateOmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams } from '@/lib/mike';
import {
    activateTennisBotService, stopTennisBotService, updateTennisBotService,
} from '@/lib/tennis';
import { fetchScalperControlRoom, stopScalperSessione } from '@/lib/scalperControlRoom';
import { sessione } from '@/lib/__fixtures__/scalperFinti';

const mFetch = vi.mocked(fetchScalperControlRoom);
const mStop = vi.mocked(stopScalperSessione);

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
});

describe('la riga Scalper calcio nel catalogo', () => {
    it('comanda il bot scalper, sport calcio, senza importo e con la frase del dove si arma', () => {
        const i = interruttoreDi('scalper');
        expect(i).toMatchObject({ bot: 'scalper', strategia: null, sport: 'calcio', chiaveImporto: null });
        expect(i.armoPerPartita).toMatch(/Segui Live/);
    });
});

describe('FERMA: tutte le sessioni ATTIVE, ciascuna con la sua firma e modalita', () => {
    it('ferma solo le attive, dalla lettura FRESCA, e non tocca nessun altro bot', async () => {
        mFetch.mockResolvedValue({
            sessioni: [
                sessione({ event_id: '1', status: 'running', dry_run: true, requested_at: '2026-09-24T12:00:00.123456+00:00' }),
                sessione({ event_id: '2', status: 'armed', dry_run: false, requested_at: '2026-09-24T12:05:00.5+00:00' }),
                sessione({ event_id: '3', status: 'requested', dry_run: true }),
                sessione({ event_id: '4', status: 'stopping' }),   // gia' in arresto
                sessione({ event_id: '5', status: 'stopped' }),
                sessione({ event_id: '6', status: 'done' }),
                sessione({ event_id: '7', status: 'error' }),
            ],
            ordini: [], lettoAt: null,
        });
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await c.spegni('scalper');
        expect(mFetch).toHaveBeenCalledTimes(1);
        expect(mStop.mock.calls).toEqual([
            ['1', '2026-09-24T12:00:00.123456+00:00', 'paper'],   // la firma passa INTATTA
            ['2', '2026-09-24T12:05:00.5+00:00', 'live'],
            ['3', sessione().requested_at, 'paper'],
        ]);
        expect(dopo).toHaveBeenCalledTimes(1);
        expect(altreScritture().every((n) => n === 0)).toBe(true);
    });

    it('una sessione rifiutata non ferma il freno: prova tutte, poi dice quale e perche', async () => {
        mFetch.mockResolvedValue({
            sessioni: [
                sessione({ event_id: '1' }),
                sessione({ event_id: '2' }),
                sessione({ event_id: '3', dry_run: null }),       // modalita' ignota
            ],
            ordini: [], lettoAt: null,
        });
        mStop.mockImplementation(async (ev: string) => {
            if (ev === '1') throw new Error('richiesta_ambigua: la sessione di 1 e\' stata riarmata');
            return {} as never;
        });
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        const err = await c.fermaBot('scalper').catch((e: unknown) => e);
        expect(err).toBeInstanceOf(ScalperNonTutteFermate);
        expect(String((err as Error).message)).toContain('1 (richiesta_ambigua');
        expect(String((err as Error).message)).toContain('3 (modalita');
        expect(mStop.mock.calls.map((x) => x[0])).toEqual(['1', '2']);
        expect(dopo).toHaveBeenCalledTimes(1);   // la pagina si rilegge comunque
    });
});

describe('da qui lo scalper NON si accende, non cambia modalita, non cambia stake', () => {
    it.each([
        ['accendi in prova', (c: ReturnType<typeof creaInterruttori>) => c.accendi('scalper', 'paper')],
        ['accendi con soldi veri', (c: ReturnType<typeof creaInterruttori>) => c.accendi('scalper', 'live')],
        ['passa a soldi veri', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalita('scalper', 'live')],
        ['passa a prova', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalita('scalper', 'paper')],
        ['tetto di modalita', (c: ReturnType<typeof creaInterruttori>) => c.cambiaModalitaServizio('scalper', 'live')],
        ['stake', (c: ReturnType<typeof creaInterruttori>) => c.cambiaImporto('scalper', 'stake', 5)],
    ])('%s: rifiutato con il motivo, e NESSUNA scrittura', async (_nome, gesto) => {
        const dopo = vi.fn();
        const c = creaInterruttori(sorgente(), dopo);
        await expect(gesto(c)).rejects.toBeInstanceOf(ScalperSiArmaPerPartita);
        expect(mStop).not.toHaveBeenCalled();
        expect(mFetch).not.toHaveBeenCalled();
        expect(altreScritture().every((n) => n === 0)).toBe(true);
        expect(dopo).not.toHaveBeenCalled();
    });
});
