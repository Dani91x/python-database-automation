// ============================================================================
// chiudiRigaScalper.test.ts - il "Chiudi" della riga dello SCALPER CALCIO
// (24/09): la riga e' la SESSIONE di una partita, chiudere = fermarla
// (`scalper_stop_sessione`: force-flat + attesa flat), con la guardia
// d'identita' (firma = requested_at, modalita') e l'esito letto dalla stessa
// `faseDaRichiesta` degli altri bot (inviata / presa in carico / eseguita /
// rifiutata).
//
// I finti parlano come il vero: `get_scalper_state` restituisce {control,
// activity} con le chiavi di `scalper_control`/`scalper_activity`; lo stop
// riceve le tre chiavi della RPC.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig() as object),
    requestManual: vi.fn(async () => 11),
    fetchManualRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    requestSafe: vi.fn(async () => 22),
    fetchSafeRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    requestMike: vi.fn(async () => 33),
    fetchMikeRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/scalper', async (orig) => ({
    ...(await orig() as object),
    fetchScalperState: vi.fn(),
}));
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    stopScalperSessione: vi.fn(async () => ({})),
}));

import { requestManual } from '@/lib/omega';
import { requestSafe } from '@/lib/safeBot';
import { requestMike } from '@/lib/mike';
import { fetchScalperState } from '@/lib/scalper';
import { stopScalperSessione } from '@/lib/scalperControlRoom';
import {
    chiudibile, inviaChiusura, faseDaRichiesta, LETTURA, cosaFaIlClic,
    richiestaDaSessioneScalper, type RigaDaChiudere,
} from './chiudiRiga';

const FIRMA = '2026-09-24T12:00:00.123456+00:00';

const riga = (over: Partial<RigaDaChiudere> = {}): RigaDaChiudere => ({
    bot: 'scalper', id: 35760084, eventId: '35760084', modalita: 'paper',
    stato: 'running', firma: FIRMA, ...over,
});

/** la riga `scalper_control` come la restituisce `get_scalper_state` */
const control = (status: string, over: Record<string, unknown> = {}) => ({
    event_id: '35760084', status, mode: 'maker', dry_run: true, stake: 25, params: {},
    bias: null, bias_meta: null, stats: null, error: null, requested_at: FIRMA,
    started_at: null, stopped_at: null, heartbeat_at: null, ...over,
});

beforeEach(() => { vi.clearAllMocks(); });

describe('chiudibile: la sessione si ferma solo se attiva, firmata e con modalita', () => {
    it.each(['requested', 'arming', 'armed', 'running'])('%s: si chiude', (stato) => {
        expect(chiudibile(riga({ stato }))).toEqual({ ok: true });
    });

    it('stopping: bottone spento, dice che si sta gia fermando', () => {
        const c = chiudibile(riga({ stato: 'stopping' }));
        expect(c).toMatchObject({ ok: false });
        expect((c as { motivo: string }).motivo).toMatch(/gia' fermando/);
    });

    it.each(['stopped', 'done', 'error'])('%s senza residuo: non e una posizione (nessun bottone)', (stato) => {
        expect(chiudibile(riga({ stato }))).toBeNull();
    });

    it('ferma ma con esposizione scoperta: lo DICE (si chiude dal ladder)', () => {
        const c = chiudibile(riga({ stato: 'stopped', residuo: true }));
        expect(c).toMatchObject({ ok: false });
        expect((c as { motivo: string }).motivo).toMatch(/ladder/);
    });

    it('senza firma o senza modalita: mai alla cieca', () => {
        expect(chiudibile(riga({ firma: null }))).toMatchObject({ ok: false });
        expect(chiudibile(riga({ firma: undefined }))).toMatchObject({ ok: false });
        expect(chiudibile(riga({ modalita: null }))).toMatchObject({ ok: false });
        expect(chiudibile(riga({ eventId: null }))).toMatchObject({ ok: false });
    });

    it('il titolo dice che cosa fa il clic', () => {
        expect(cosaFaIlClic('scalper')).toMatch(/force-flat/);
    });
});

describe('instradamento: lo stop va allo SCALPER, con firma e modalita intatte', () => {
    it('scalper_stop_sessione(event, requested_at, mode) e nessuna coda di altri bot', async () => {
        const r = await inviaChiusura(riga({ modalita: 'live' }));
        expect(r).toEqual({ bot: 'scalper', requestId: 35760084 });
        expect(stopScalperSessione).toHaveBeenCalledWith('35760084', FIRMA, 'live');
        expect(requestManual).not.toHaveBeenCalled();
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
    });

    it('rifiuto della RPC (richiesta_ambigua): l errore arriva al chiamante', async () => {
        vi.mocked(stopScalperSessione).mockRejectedValueOnce(
            new Error('richiesta_ambigua: la sessione di 35760084 e\' stata riarmata'));
        await expect(inviaChiusura(riga())).rejects.toThrow(/richiesta_ambigua/);
    });

    it('una riga non chiudibile non manda niente', async () => {
        await expect(inviaChiusura(riga({ firma: null }))).rejects.toThrow(/firma/);
        expect(stopScalperSessione).not.toHaveBeenCalled();
    });
});

describe('esito: la sessione letta come una richiesta', () => {
    it.each([
        ['running', 'inviata', false],
        ['armed', 'inviata', false],
        ['stopping', 'presa_in_carico', false],
        ['stopped', 'eseguita', true],
        ['done', 'eseguita', true],
        ['error', 'rifiutata', true],
    ])('%s -> %s', (status, fase, chiusa) => {
        const r = richiestaDaSessioneScalper(1, control(status, { error: status === 'error' ? 'login KO' : null }));
        const f = faseDaRichiesta('scalper', r!);
        expect(f.fase).toBe(fase);
        expect(f.chiusa).toBe(chiusa);
        if (status === 'error') expect(f.motivo).toBe('login KO');
    });

    it('ferma ma NON flat dopo 30 s: eseguita, col motivo scritto dalla sessione', () => {
        const r = richiestaDaSessioneScalper(1, control('stopped'), [
            { kind: 'info', payload: { msg: 'sessione stopped' } },
            { kind: 'error', payload: { msg: 'stop: posizione NON flat dopo 30s' } },
        ]);
        const f = faseDaRichiesta('scalper', r!);
        expect(f.fase).toBe('eseguita');
        expect(f.motivo).toMatch(/NON era flat/);
    });

    it('riga assente: nessuna lettura', () => {
        expect(richiestaDaSessioneScalper(1, null)).toBeNull();
    });

    it('LETTURA.scalper rilegge get_scalper_state della partita della riga', async () => {
        vi.mocked(fetchScalperState).mockResolvedValue({
            control: control('stopping') as never, activity: [],
        });
        const r = await LETTURA.scalper(35760084);
        expect(fetchScalperState).toHaveBeenCalledWith('35760084', 5);
        expect(r).toEqual({ id: 35760084, status: 'processing', result: null });
    });
});
