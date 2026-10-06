// ============================================================================
// replayBot — "APPLICA BOT" del Match Replay (06/10).
// Il bot gira col CODICE DI PRODUZIONE sulla registrazione della partita (banco
// comune, Betfair/stream/backtest/applica_bot.py) nel worker del Backtest
// Automatico; la richiesta passa dalla coda esistente (request_backtest con
// params.tipo = 'applica_bot'), l'esito da get_replay_bot_esito (migrazione
// replay_applica_bot_2026-10-06.sql).
// L'esito e' la CRONOLOGIA degli ordini del bot: righe betfair_live_orders (le
// stesse che il ladder legge dal vivo) con l'istante `_ms` del banco (= publish
// time Betfair, lo stesso orologio dei frame del replay). Qui si ricostruisce lo
// stato degli ordini a un istante della timeline e lo si mostra nel ladder.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { LadderOrderApi } from '@/components/live/LadderView';
import type { LiveOrderRow } from '@/lib/liveOrders';

// stesso elenco di applica_bot.SCENARI_VISIVI (il worker rifiuta il resto)
export const SCENARI_BOT: ReadonlyArray<{ bot: string; scenario: string; etichetta: string }> = [
    { bot: 'scalper_calcio', scenario: 'media-under-paper', etichetta: 'Scalper - Media Under 2,5 (prova)' },
    { bot: 'scalper_calcio', scenario: 'media-under-35', etichetta: 'Scalper - Media Under 3,5' },
    { bot: 'scalper_calcio', scenario: 'media-under', etichetta: 'Scalper - Media Under 2,5 (soldi veri simulati)' },
    { bot: 'scalper_calcio', scenario: 'media-under-liquidita-100', etichetta: "Scalper - Media Under 2,5, liquidita' minima 100 EUR" },
    { bot: 'scalper_calcio', scenario: 'media-under-35-liquidita-50', etichetta: "Scalper - Media Under 3,5, liquidita' minima 50 EUR" },
    { bot: 'scalper_calcio', scenario: 'paper', etichetta: 'Scalper - maker (prova)' },
    { bot: 'scalper_calcio', scenario: 'base', etichetta: 'Scalper - maker (soldi veri simulati)' },
    { bot: 'scalper_calcio', scenario: 'sniper-paper', etichetta: 'Scalper - sniper (prova)' },
];

// una riga della cronologia: la riga dello specchio + l'istante del banco
export type RigaBot = Omit<LiveOrderRow, 'id' | 'updated_at'> & { _ms: number };

export interface EsitoBot {
    bot: string;
    scenario: string;
    event_id: string;
    etichetta: string;
    righe: RigaBot[];
    ordini: number;
    violazioni: string[];
    note: string[];
}

export interface StatoRichiestaBot {
    status: 'PENDING' | 'RUNNING' | 'DONE' | 'ERROR';
    error_detail: string | null;
    esito: EsitoBot | null;
}

export async function richiediApplicaBot(eventId: string, bot: string, scenario: string): Promise<string> {
    const { data, error } = await supabase.rpc('request_backtest', {
        p_params: { tipo: 'applica_bot', bot, scenario, event_id: eventId },
    });
    if (error) throw new Error(error.message);
    return String(data);
}

export async function leggiEsitoBot(requestId: string): Promise<StatoRichiestaBot> {
    const { data, error } = await supabase.rpc('get_replay_bot_esito', { p_request_id: requestId });
    if (error) throw new Error(error.message);
    return data as StatoRichiestaBot;
}

function chiave(r: RigaBot): string {
    return String(r.client_order_ref ?? r.bet_id ?? '');
}

/** Le righe del referto che spiegano COSA ha fatto il bot e PERCHE' non
 *  entrava (cicli, P&L, motivi di non ingresso). PURA. */
export function noteUtili(note: ReadonlyArray<string>): string[] {
    return note.filter(n => /ciclo \d+:|P&L del replay|motivi di non ingresso|non entra/i.test(n))
        .map(n => n.replace(/^nota:\s*/, '').replace(/^MEDIA UNDER:?\s*/, ''));
}

/** Gli ordini del bot come erano all'istante `ms` (ultima riga di ogni ordine
 *  con _ms <= ms), come righe LiveOrderRow (quelle che il ladder legge).
 *  `marketId` filtra un mercato. PURA. */
export function ordiniBotAlMs(righe: ReadonlyArray<RigaBot>, ms: number, marketId?: string): LiveOrderRow[] {
    const ultima = new Map<string, RigaBot>();
    for (const r of righe) {
        if (r._ms > ms) break;                     // righe ordinate per _ms
        if (marketId && r.market_id !== marketId) continue;
        ultima.set(chiave(r), r);
    }
    const out: LiveOrderRow[] = [];
    let i = 0;
    for (const r of ultima.values()) {
        i += 1;
        const { _ms, ...riga } = r;
        // id negativo: mai in collisione con gli ordini del training (id >= 1)
        out.push({ ...riga, id: -i, updated_at: new Date(_ms).toISOString() });
    }
    return out;
}

/** L'orderApi del ladder training con IN PIU' gli ordini del bot (sola
 *  lettura): fetchOrders aggiunge quelli del bot del mercato all'istante
 *  corrente; un annullo di un ordine del bot e' rifiutato. */
export function conOrdiniDelBot(base: LadderOrderApi, ordiniBot: (marketId: string) => LiveOrderRow[]): LadderOrderApi {
    return {
        ...base,
        fetchOrders: async (marketId, mode) => [
            ...(await base.fetchOrders(marketId, mode)),
            ...ordiniBot(marketId),
        ],
        send: async (cmd) => {
            if (cmd.action === 'cancel' && cmd.bet_id && cmd.market_id
                && ordiniBot(cmd.market_id).some(o => o.bet_id === cmd.bet_id)) {
                return { ok: false, action: 'cancel', mode: 'paper',
                         error: 'ordine del bot applicato: sola lettura' };
            }
            return base.send(cmd);
        },
    };
}
