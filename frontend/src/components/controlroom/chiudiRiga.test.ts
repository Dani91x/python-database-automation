// ============================================================================
// chiudiRiga.test.ts — B16 (24/09): il «Chiudi» di una riga va AL SUO BOT.
//
// FALSIFICAZIONE (24/09, patch salvata): (1) `INVIO.omega`/`INVIO.mike` che
// chiamano `requestSafe` → rossi i test di instradamento; (2) `chiudibile` che
// lascia passare i bot tennis → rosso; (3) `faseDaRichiesta` che legge 'done'
// di Mike come 'eseguita' → rosso; (4) `mode` tolto dal payload → rosso.
// I finti hanno le chiavi VERE delle tre code (status/result con message,
// rejected, error, code, phase), non una grafia inventata (catalogo §7, 27).
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

import { requestManual, fetchManualRequests } from '@/lib/omega';
import { requestSafe, fetchSafeRequests } from '@/lib/safeBot';
import { requestMike, fetchMikeRequests } from '@/lib/mike';
import {
    chiudibile, inviaChiusura, faseDaRichiesta, faseMostrata, LETTURA,
    cambiataPerChiusura, firmaRiga, statoConScadenza, SCADENZA_ESITO_MS,
    motivoDelServizio, type RigaDaChiudere, type StatoChiusuraRiga,
} from './chiudiRiga';

const riga = (over: Partial<RigaDaChiudere> = {}): RigaDaChiudere => ({
    bot: 'omega', id: 900, eventId: 'E1', modalita: 'live', stato: 'open', ...over,
});

beforeEach(() => { vi.clearAllMocks(); });

describe('instradamento: ogni riga sulla coda del SUO bot', () => {
    it('Omega → omega_request, con bot/partita/modalita\' della riga', async () => {
        const r = await inviaChiusura(riga());
        expect(r).toEqual({ bot: 'omega', requestId: 11 });
        expect(requestManual).toHaveBeenCalledWith('cashout', {
            trade_id: 900, fraction: 1, bot: 'omega', event_id: 'E1', mode: 'live',
        });
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
    });

    it('Safe → safe_request (calcio e tennis: stessa coda)', async () => {
        await inviaChiusura(riga({ bot: 'safe', id: 5, eventId: 'T9', modalita: 'paper' }));
        expect(requestSafe).toHaveBeenCalledWith('cashout', {
            trade_id: 5, fraction: 1, bot: 'safe', event_id: 'T9', mode: 'paper',
        });
        expect(requestManual).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
    });

    it('Mike → mike_request per la PARTITA (event_id obbligatorio della RPC)', async () => {
        await inviaChiusura(riga({ bot: 'mike', id: 801, eventId: 'E2', modalita: 'paper' }));
        expect(requestMike).toHaveBeenCalledWith('cashout', {
            event_id: 'E2', trade_id: 801, bot: 'mike', mode: 'paper',
        });
        expect(requestSafe).not.toHaveBeenCalled();
    });

    it('bot tennis → nessuna richiesta, errore col motivo', async () => {
        await expect(inviaChiusura(riga({ bot: 'tennis_scalper', stato: 'EXECUTABLE' })))
            .rejects.toThrow(/bot tennis/);
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestManual).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
    });

    it('modalita\' non dichiarata → nessuna richiesta (mai alla cieca)', async () => {
        await expect(inviaChiusura(riga({ modalita: null }))).rejects.toThrow(/modalita/);
        expect(requestManual).not.toHaveBeenCalled();
    });
});

describe('chiudibile: il bottone dice sempre perche\'', () => {
    it('regolata / errore / annullata: nessun bottone', () => {
        expect(chiudibile(riga({ stato: 'won' }))).toBeNull();
        expect(chiudibile(riga({ stato: 'error' }))).toBeNull();
        expect(chiudibile(riga({ stato: 'cancelled' }))).toBeNull();
        expect(chiudibile(riga({ bot: 'tennis_pro', stato: 'EXECUTION_COMPLETE', regolata: true }))).toBeNull();
    });
    it.each([
        [riga({ bot: 'tennis_flb', stato: 'EXECUTABLE' }), /bot tennis/],
        [riga({ chiudeId: 7 }), /gamba di chiusura/],
        [riga({ stato: 'hedged' }), /coperta/],
        [riga({ stato: 'pending_reconcile' }), /riconciliazione/],
        [riga({ stato: 'pending' }), /in volo/],
        [riga({ bot: 'mike', eventId: null }), /partita/],
    ])('spento con motivo: %#', (r, motivo) => {
        const c = chiudibile(r);
        expect(c).not.toBeNull();
        expect(c!.ok).toBe(false);
        expect((c as { motivo: string }).motivo).toMatch(motivo);
    });
    it('Safe e Mike su una riga in attesa restano chiudibili (i servizi la gestiscono)', () => {
        expect(chiudibile(riga({ bot: 'safe', stato: 'pending' }))).toEqual({ ok: true });
        expect(chiudibile(riga({ bot: 'mike', stato: 'pending' }))).toEqual({ ok: true });
    });
});

describe('esito dalla coda del bot (chiavi vere delle tabelle)', () => {
    it('Omega: error con `error`+`message` → rifiutata col messaggio', () => {
        const f = faseDaRichiesta('omega', {
            id: 1, status: 'error',
            result: { error: 'richiesta_ambigua', message: 'rifiutato: altro bot' },
        });
        expect(f).toEqual({ fase: 'rifiutata', motivo: 'rifiutato: altro bot', chiusa: true });
    });
    it('Omega: error senza message → il codice, leggibile', () => {
        expect(motivoDelServizio({ error: 'trade_non_aperto:hedged' })).toBe('trade non aperto:hedged');
    });
    it('Safe: pending con messaggio di attesa → inviata, col messaggio', () => {
        const f = faseDaRichiesta('safe', {
            id: 2, status: 'pending', result: { attendi: 'riserva non ancora risolta', message: 'in attesa: ...' },
        });
        expect(f.fase).toBe('inviata');
        expect(f.motivo).toBe('in attesa: ...');
        expect(f.chiusa).toBe(false);
    });
    it('Safe: rejected → rifiutata; done → eseguita', () => {
        expect(faseDaRichiesta('safe', { id: 3, status: 'rejected', result: { rejected: 'stato hedged', message: 'rifiutato: gia\' coperta' } }).fase)
            .toBe('rifiutata');
        expect(faseDaRichiesta('safe', { id: 3, status: 'done', result: { ok: true } }).fase).toBe('eseguita');
    });
    it('Mike: done con phase=armed → PRESA IN CARICO (la chiusura la guida il bot)', () => {
        const f = faseDaRichiesta('mike', {
            id: 4, status: 'done',
            result: { code: 'ok', message: 'Cash out: chiusura in corso (netto stimato 0.40 EUR).', ok: true, phase: 'armed' },
        });
        expect(f.fase).toBe('presa_in_carico');
        expect(f.chiusa).toBe(true);
    });
    it('Mike: rejected con code → rifiutata col messaggio', () => {
        const f = faseDaRichiesta('mike', {
            id: 5, status: 'rejected', result: { code: 'feed_stantio', message: 'Feed non aggiornato' },
        });
        expect(f).toEqual({ fase: 'rifiutata', motivo: 'Feed non aggiornato', chiusa: true });
    });
    it('processing → presa in carico', () => {
        expect(faseDaRichiesta('omega', { id: 6, status: 'processing', result: null }).fase).toBe('presa_in_carico');
    });
});

describe('LETTURA: ognuno legge la SUA coda', () => {
    it('Omega legge get_omega_manual_requests, Safe safe_strategy_requests, Mike mike_requests', async () => {
        vi.mocked(fetchManualRequests).mockResolvedValue([
            { id: 11, kind: 'cashout', payload: {}, status: 'done', result: {}, created_at: 'x', processed_at: null },
        ]);
        vi.mocked(fetchSafeRequests).mockResolvedValue([
            { id: 22, kind: 'cashout', payload: {}, status: 'rejected', result: { message: 'no' }, created_at: 'x', updated_at: null },
        ]);
        vi.mocked(fetchMikeRequests).mockResolvedValue([
            { id: 33, kind: 'cashout', payload: { event_id: 'E2' }, status: 'processing', result: null, created_at: 'x', updated_at: null } as never,
        ]);
        expect((await LETTURA.omega(11))?.status).toBe('done');
        expect((await LETTURA.safe(22))?.status).toBe('rejected');
        expect((await LETTURA.mike(33))?.status).toBe('processing');
        expect(await LETTURA.omega(999)).toBeNull();
    });
});

describe('la riga che cambia e la scadenza', () => {
    const base: StatoChiusuraRiga = {
        bot: 'omega', id: 1, requestId: 11, faseRichiesta: 'inviata', richiestaChiusa: false,
        motivo: null, rigaCambiata: false, inviataMs: 0,
    };
    it('gamba di chiusura nuova o coperta = cambiata; il solo abbinamento dell\'apertura no', () => {
        const f = firmaRiga('open', 0);
        expect(cambiataPerChiusura(f, 'open', 1)).toBe(true);
        expect(cambiataPerChiusura(f, 'hedged', 0)).toBe(true);
        expect(cambiataPerChiusura(firmaRiga('pending', 0), 'open', 0)).toBe(false);
    });
    it('il rifiuto del servizio vince sulla riga cambiata', () => {
        expect(faseMostrata({ ...base, rigaCambiata: true })).toBe('eseguita');
        expect(faseMostrata({ ...base, rigaCambiata: true, faseRichiesta: 'rifiutata' })).toBe('rifiutata');
    });
    it('oltre 3 minuti senza esito: IGNOTA, detto', () => {
        const s = statoConScadenza(base, SCADENZA_ESITO_MS + 1);
        expect(s.faseRichiesta).toBe('ignota');
        expect(s.motivo).toMatch(/nessun esito/);
        expect(statoConScadenza(base, 1000)).toBe(base);
    });
});
