// ============================================================================
// scalperAuto.test.ts - 25/09: l'AUTO-MODE dello scalper lato pagina.
// Ordine dell'utente: «lo scalper deve lavorare da solo su tutte le partite
// del feed come gli altri bot».
//
// Le chiamate (RPC con i nomi e i parametri VERI della migrazione
// scalper_auto_mode_2026-09-25.sql), la lettura della riga dell'interruttore,
// lo stato della riga di plancia e la frase: testi ESATTI.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: (...a: unknown[]) => rpc(...a), from: vi.fn(), channel: vi.fn() },
}));

import {
    fetchScalperControlRoom, attivaScalperAuto, fermaScalperAuto, aggiornaScalperAuto,
    rpcAssente, leggiAutoScalper, notaAutoScalper, statoBotScalper, type ServizioScalper,
} from '@/lib/scalperControlRoom';
import { sessione } from '@/lib/__fixtures__/scalperFinti';

function servizio(over: Partial<ServizioScalper> = {}): ServizioScalper {
    return {
        id: 1, status: 'running', mode: 'paper', strategia: 'maker', stake: 25, params: {},
        stats: null, started_at: '2026-09-25T17:00:00+00:00', stopped_at: null,
        updated_at: '2026-09-25T17:00:00+00:00', ...over,
    };
}

/** `stats.auto` come lo scrive `scalper_service.giro_auto` */
const AUTO = {
    acceso: true, modalita: 'paper', tetto: 2, sessioni: 2, sessioni_auto: 1,
    armate_ora: ['35800001'], fermate_ora: [], motivo_blocco: null, conflitto: null,
    pnl_lordo_bot: 0.4, ordini_vivi: 3,
    feed: { letto: true, vivo: true, partite: 7, eta_scanner_s: 4.4, fonte: 'safe_strategy_scan' },
    giro_at: '2026-09-25T18:00:00+00:00',
};

beforeEach(() => { rpc.mockReset(); });

describe('le chiamate: nomi e parametri veri', () => {
    it('accendi: scalper_auto_activate con la modalita\' SCRITTA', async () => {
        rpc.mockResolvedValue({ data: servizio({ mode: 'live' }), error: null });
        const s = await attivaScalperAuto('live');
        expect(rpc).toHaveBeenCalledWith('scalper_auto_activate', { p_mode: 'live' });
        expect(s.mode).toBe('live');
    });

    it('ferma: scalper_auto_stop, ritorna quante sessioni ha fermato', async () => {
        rpc.mockResolvedValue({ data: { servizio: servizio({ status: 'stopped' }), sessioni_fermate: 3 }, error: null });
        expect(await fermaScalperAuto()).toBe(3);
        expect(rpc).toHaveBeenCalledWith('scalper_auto_stop', {});
    });

    it('stake: scalper_auto_update, status e mode non si toccano', async () => {
        rpc.mockResolvedValue({ data: servizio({ stake: 10 }), error: null });
        await aggiornaScalperAuto({ stake: 10 });
        expect(rpc).toHaveBeenCalledWith('scalper_auto_update', { p_stake: 10, p_params: null, p_strategia: null });
    });

    it('errore della RPC: si propaga col suo testo', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: "scalper gia' acceso in paper: spegnilo e riaccendilo in live (paper e live mai insieme)" } });
        await expect(attivaScalperAuto('live')).rejects.toThrow("scalper gia' acceso in paper");
    });

    it('rpcAssente riconosce la funzione mancante (migrazione non applicata)', () => {
        expect(rpcAssente(new Error('Could not find the function public.scalper_auto_stop without parameters in the schema cache'))).toBe(true);
        expect(rpcAssente(new Error('non autorizzato (owner-only)'))).toBe(false);
    });
});

describe('la lettura porta l\'interruttore', () => {
    it('chiave servizio presente: servizioLetto true', async () => {
        rpc.mockResolvedValue({ data: { sessions: [], orders: [], servizio: servizio(), letto_at: 'x' }, error: null });
        const r = await fetchScalperControlRoom();
        expect(r.servizioLetto).toBe(true);
        expect(r.servizio?.status).toBe('running');
    });

    it('RPC di prima (nessuna chiave servizio): servizioLetto false, servizio null', async () => {
        rpc.mockResolvedValue({ data: { sessions: [], orders: [], letto_at: 'x' }, error: null });
        const r = await fetchScalperControlRoom();
        expect(r.servizioLetto).toBe(false);
        expect(r.servizio).toBeNull();
    });
});

describe('statoBotScalper con l\'interruttore', () => {
    it('acceso senza sessioni: in corsa, running, con la modalita\' dell\'interruttore', () => {
        const st = statoBotScalper([], servizio({ mode: 'live' }));
        expect(st).toMatchObject({ inCorsa: true, stato: 'running', modalita: 'live', autoAcceso: true, misto: false });
    });

    it('spento: come prima (solo le sessioni)', () => {
        expect(statoBotScalper([], servizio({ status: 'stopped' }))).toMatchObject({
            inCorsa: false, stato: 'stopped', modalita: null, autoAcceso: false,
        });
        expect(statoBotScalper([sessione({ status: 'running', dry_run: true })], null)).toMatchObject({
            inCorsa: true, modalita: 'paper', autoAcceso: false,
        });
    });

    it('interruttore in prova con una sessione della card in soldi veri: soldi veri e misto', () => {
        const st = statoBotScalper([sessione({ dry_run: false })], servizio({ mode: 'paper' }));
        expect(st.modalita).toBe('live');
        expect(st.misto).toBe(true);
    });
});

describe('la frase dell\'auto-mode', () => {
    it('testo esatto in prova', () => {
        const a = leggiAutoScalper({ auto: AUTO });
        expect(notaAutoScalper(a, null)).toBe(
            'auto-mode: 2 sessioni (1 dal feed) - tetto 2 - feed calcio: 7 partite, scanner 4 s fa '
            + '(safe_strategy_scan) - 3 ordini vivi');
    });

    it('testo esatto con soldi veri e feed muto', () => {
        const a = leggiAutoScalper({ auto: { ...AUTO, modalita: 'live', sessioni: 1, sessioni_auto: 1, ordini_vivi: null, feed: { letto: true, vivo: false } } });
        expect(notaAutoScalper(a, null)).toBe(
            'auto-mode: 1 sessione (1 dal feed) - tetto 2 - feed calcio non disponibile - '
            + 'LIVE: le partite del feed nascono con soldi veri');
    });

    it('spento o non dichiarato: nessuna frase', () => {
        expect(notaAutoScalper(leggiAutoScalper({ auto: { ...AUTO, acceso: false } }), 2)).toBeNull();
        expect(leggiAutoScalper(null)).toBeNull();
        expect(leggiAutoScalper({ auto: [] })).toBeNull();
    });

    it('il motivo del blocco passa com\'e\'', () => {
        const a = leggiAutoScalper({ auto: { ...AUTO, sessioni: 0, motivo_blocco: 'feed calcio vuoto: nessuna partita in gioco o imminente ora' } });
        expect(a?.motivo).toBe('feed calcio vuoto: nessuna partita in gioco o imminente ora');
    });
});
