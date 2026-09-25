// R7 (25/09/2026): il ritardo del cruscotto Direzione viene dalla STESSA RPC della
// tab Studio Ritardi (get_market_delays), con la regola HT unica.
// Il finto della RPC ha le stesse chiavi e gli stessi tipi dell'output jsonb di
// migrations/market_delays_ht_2026-09-25.sql (meta/stats/serie).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import type { DelayResult } from './marketDelays';

// Finto del client Supabase: si finge SOLO `rpc(nome, parametri)` -> { data, error },
// cioe' la forma vera di supabase-js. fetchMarketDelays/fetchMarketFrequency sono
// quelle VERE: il test copre anche i parametri che arrivano alla RPC.
type RpcRisposta = { data: unknown; error: { message: string } | null };
const rpcFinta = vi.hoisted(() => ({
    risposte: {} as Record<string, RpcRisposta>,
    chiamate: [] as { nome: string; parametri: Record<string, unknown> }[],
}));
vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: async (nome: string, parametri: Record<string, unknown>) => {
            rpcFinta.chiamate.push({ nome, parametri });
            return rpcFinta.risposte[nome] ?? { data: null, error: { message: `rpc ${nome} non prevista` } };
        },
    },
}));

import { delayMap, delayFromResult, fetchSignalContext, NOTA_REGOLA_HT_MANCANTE } from './signalContext';

function risultato(meta: Partial<DelayResult['meta']>, stats: Partial<DelayResult['stats']> = {}): DelayResult {
    return {
        meta: {
            league_id: 547, market: 'ovpt', target: '0.5', mode: 'all', season_year: null, n_requested: null,
            n_scope: 10, n_effective: 8, uses_ht: true, ht_coverage_pct: 80, ht_missing_rule: 'escluse',
            n_ht_missing: 2, date_from: '2026-08-01T00:00:00+00:00', date_to: '2026-08-10T00:00:00+00:00',
            ...meta,
        },
        stats: {
            n_occ: 5, frequency: 0.625, media_storica: 1.6, quota_oggettiva: 1.6, ritardo_attuale: 0,
            record: 2, media_ritardi: 1.3333, sotto_media: 3, sopra_media: 2, sotto_media_pct: 0.6,
            sopra_media_pct: 0.4, rit_vs_media: 0, storico_cond_su: 0, ...stats,
        },
        distribuzione_serie: [], ultime_10_serie: [], storico_serie: [], run_sopra_media: [],
        ultime_10_strisce_sopra_media: [], series: [],
    };
}

beforeEach(() => {
    rpcFinta.risposte = {};
    rpcFinta.chiamate = [];
});

describe('delayMap: i 7 mercati del cruscotto -> get_market_delays', () => {
    const casi: [string, string, string, string | null][] = [
        ['1x2', 'H', '1', null], ['1x2', 'D', 'x', null], ['1x2', 'A', '2', null],
        ['ht_1x2', 'H', 'pt1', null], ['ht_1x2', 'D', 'ptx', null], ['ht_1x2', 'A', 'pt2', null],
        ['btts', 'Yes', 'gg', null], ['btts', 'No', 'ng', null],
        ['over_1_5', 'Over', 'over', '1.5'], ['over_1_5', 'Under', 'under', '1.5'],
        ['over_2_5', 'Over', 'over', '2.5'], ['over_2_5', 'Under', 'under', '2.5'],
        ['over_3_5', 'Over', 'over', '3.5'], ['over_3_5', 'Under', 'under', '3.5'],
        ['first_half_over_0_5', 'Over', 'ovpt', '0.5'], ['first_half_over_0_5', 'Under', 'unpt', '0.5'],
    ];
    it.each(casi)('%s %s -> %s %s', (m, d, dm, dt) => {
        expect(delayMap(m, d)).toEqual({ market: dm, target: dt });
    });
    it('selezione sconosciuta -> null (nessun ritardo inventato)', () => {
        expect(delayMap('1x2', '1X')).toBeNull();
        expect(delayMap('btts', 'yes')).toBeNull();
        expect(delayMap('mercato_ignoto', 'Over')).toBeNull();
    });
    it('contratto con la migrazione: ogni codice usato e accettato dalla whitelist della RPC', () => {
        const sql = fs.readFileSync(path.resolve(process.cwd(), '../migrations/market_delays_ht_2026-09-25.sql'), 'utf8');
        for (const [m, d] of casi) {
            const code = delayMap(m, d)!.market;
            expect(sql).toMatch(new RegExp(`when '${code}'\\s+then`));
        }
    });
});

describe('delayFromResult', () => {
    it('restituisce ESATTAMENTE i valori della RPC (quelli della tab Ritardi)', () => {
        const { delay, note } = delayFromResult(risultato({}, { ritardo_attuale: 4, record: 9, media_storica: 2.5, rit_vs_media: 1.6 }));
        expect(note).toBeNull();
        expect(delay).toEqual({ current: 4, media: 2.5, record: 9, ratio: 1.6, n: 8, n_ht_missing: 2 });
    });
    it('mercato HT con la RPC VECCHIA (senza regola): nessun ritardo, nota esplicita', () => {
        const r = risultato({ ht_missing_rule: undefined, n_ht_missing: undefined, n_effective: 10 });
        expect(delayFromResult(r)).toEqual({ delay: null, note: NOTA_REGOLA_HT_MANCANTE });
    });
    it('mercato FT con la RPC vecchia: il numero FT e invariato, quindi si mostra', () => {
        const r = risultato({ market: 'over', uses_ht: false, ht_missing_rule: undefined, n_ht_missing: undefined });
        expect(delayFromResult(r).delay?.n).toBe(8);
    });
});

describe('fetchSignalContext', () => {
    it('chiede il ritardo alla RPC get_market_delays con tutto lo storico e lo passa invariato', async () => {
        rpcFinta.risposte.get_market_delays = { data: risultato({}, { ritardo_attuale: 3, record: 7 }), error: null };
        const ctx = await fetchSignalContext(547, 'first_half_over_0_5', 'Over');
        const rit = rpcFinta.chiamate.filter(c => c.nome === 'get_market_delays');
        expect(rit).toHaveLength(1);
        expect(rit[0].parametri).toEqual({
            p_league_id: 547, p_market: 'ovpt', p_target: '0.5', p_mode: 'all', p_last_n: null, p_season_year: null,
        });
        expect(ctx.delay?.current).toBe(3);
        expect(ctx.delay?.record).toBe(7);
        expect(ctx.delay?.n).toBe(8);
        expect(ctx.delayNote).toBeNull();
        expect(ctx.freq).toBeNull();  // la frequenza fallisce da sola (rpc non prevista), il ritardo resta
    });
    it('errore della RPC (es. codice non ancora deployato): ritardo non disponibile, nessun calcolo alternativo', async () => {
        rpcFinta.risposte.get_market_delays = { data: null, error: { message: 'mercato non supportato: unpt' } };
        const ctx = await fetchSignalContext(547, 'first_half_over_0_5', 'Under');
        expect(rpcFinta.chiamate.filter(c => c.nome === 'get_market_delays')).toHaveLength(1);
        expect(ctx.delay).toBeNull();
        expect(ctx.delayNote).toBeNull();
    });
});
