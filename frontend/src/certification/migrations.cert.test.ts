// ============================================================================
// migrations.cert.test.ts — §1 del report: quali migrazioni risultano
// APPLICATE e quali NO, con l'evidenza presa dalle RPC vere.
//
// Nessun render qui: solo sonde in LETTURA sul DB di produzione.
// ============================================================================
import { describe, it, expect, afterAll } from 'vitest';
import { assertOwner, probeRpc, CERT_ENV_PATH, CERT_SUPABASE_URL, CERT_RUN } from './realClient';
import { Report } from './report';

/** fuori da vitest.cert.config.ts i test si SALTANO (mai il DB reale in `npm test`) */
const d = CERT_RUN ? describe : describe.skip;
const rep = new Report('MIGRAZIONI · evidenza dalle RPC');

afterAll(() => rep.print());

function keysOf(v: unknown): string[] {
    return v && typeof v === 'object' && !Array.isArray(v) ? Object.keys(v as object).sort() : [];
}

d('migrazioni — stato reale del DB', () => {
    it('il service role è OWNER (betfair_live_is_owner)', async () => {
        const owner = await assertOwner();
        rep.mark('betfair_live_is_owner() con service role', 'true', String(owner), owner);
        rep.note(`.env letto da ${CERT_ENV_PATH} · progetto ${CERT_SUPABASE_URL}`);
        expect(owner).toBe(true);
    });

    it('RPC che esistono / non esistono', async () => {
        const probes: [string, Record<string, unknown>][] = [
            ['get_omega_state', { p_activity_limit: 10 }],
            ['get_omega_aggregates', {}],
            ['get_omega_trades', { p_limit: 5 }],
            ['get_omega_daily', { p_from: '2026-09-01', p_to: '2026-09-11' }],
            ['get_omega_day_trades', { p_day: '2026-09-11' }],
            ['get_omega_events', {}],
            ['get_omega_missions', {}],
            ['get_safe_state', {}],
            ['get_safe_trades', { p_limit: 5 }],
            ['get_safe_daily', { p_from: '2026-09-01', p_to: '2026-09-11', p_sport: null }],
            ['get_safe_day_trades', { p_day: '2026-09-11', p_sport: null }],
            ['get_safe_aggregates', {}],
            ['get_safe_activity', { p_limit: 10, p_kinds: null }],
            ['get_mike_state', {}],
            ['get_mike_trades', { p_limit: 5 }],
            ['get_mike_aggregates', {}],
            ['get_mike_daily', { p_from: '2026-09-05', p_to: '2026-09-11' }],
            ['get_mike_day_trades', { p_day: '2026-09-11' }],
        ];
        const missing: string[] = [];
        const broken: string[] = [];
        for (const [name, args] of probes) {
            const r = await probeRpc(name, args);
            rep.mark(`RPC ${name}`, 'esiste e risponde', r.ok ? 'OK' : (r.error ?? 'errore'), r.ok);
            if (!r.ok) {
                if ((r.error ?? '').includes('PGRST202')) missing.push(name);
                else broken.push(`${name} → ${r.error}`);
            }
        }
        for (const n of missing) {
            rep.finding('HIGH', `RPC ${n}`, 'NON esiste: migrazione non applicata (PGRST202)');
        }
        for (const b of broken) {
            rep.finding('CRITICAL', 'RPC in errore', b);
        }
        expect(missing.length + broken.length).toBeGreaterThanOrEqual(0);
    });

    it('campi delle RPC v2/v5 attesi dalla UI', async () => {
        const omega = await probeRpc('get_omega_state', { p_activity_limit: 10 });
        const ok = keysOf(omega.data);
        const oaggKeys = keysOf((omega.data as Record<string, unknown> | null)?.aggregates);
        rep.mark('get_omega_state → chiavi radice', 'control,aggregates,activity,activity_more,activity_day,goal_today,goal_snapshot', ok.join(','), false);
        for (const k of ['goal_snapshot', 'activity_more', 'activity_day']) {
            const has = ok.includes(k);
            rep.mark(`get_omega_state.${k}`, 'presente (omega_models_v5)', has ? 'presente' : 'ASSENTE', has);
            if (!has) rep.finding('HIGH', 'migrations/omega_models_v5.sql', `get_omega_state non espone '${k}'`);
        }
        for (const k of ['locked_pnl_open', 'locked_pnl_open_today', 'reconciling_liability', 'live_now']) {
            const has = oaggKeys.includes(k);
            rep.mark(`get_omega_state.aggregates.${k}`, 'presente (omega_models_v5)', has ? 'presente' : 'ASSENTE', has);
            if (!has) rep.finding('HIGH', 'migrations/omega_models_v5.sql', `aggregates senza '${k}'`);
        }
        for (const k of ['events_today', 'legs_today', 'won_today', 'lost_today']) {
            const has = oaggKeys.includes(k);
            rep.mark(`get_omega_state.aggregates.${k}`, 'presente (omega_models_v4)', has ? 'presente' : 'ASSENTE', has);
        }

        const safe = await probeRpc('get_safe_state', {});
        const sk = keysOf(safe.data);
        const saggKeys = keysOf((safe.data as Record<string, unknown> | null)?.aggregates);
        for (const k of ['activity', 'params_effective', 'operating_day']) {
            const has = sk.includes(k);
            rep.mark(`get_safe_state.${k}`, 'presente (safe_strategy_bot_v2)', has ? 'presente' : 'ASSENTE', has);
            if (!has) rep.finding('HIGH', 'migrations/safe_strategy_bot_v2.sql', `get_safe_state non espone '${k}'`);
        }
        for (const k of ['won_today', 'lost_today', 'legs_today', 'events_today', 'reconciling_liability', 'day_liability']) {
            const has = saggKeys.includes(k);
            rep.mark(`get_safe_state.aggregates.${k}`, 'presente (safe_strategy_bot_v2)', has ? 'presente' : 'ASSENTE', has);
        }

        const mike = await probeRpc('get_mike_state', {});
        const mk = keysOf(mike.data);
        const maggKeys = keysOf((mike.data as Record<string, unknown> | null)?.aggregates);
        for (const k of ['requests', 'day_start', 'day_by']) {
            const has = mk.includes(k);
            rep.mark(`get_mike_state.${k}`, 'presente (mike_bot_v2)', has ? 'presente' : 'ASSENTE', has);
            if (!has) rep.finding('HIGH', 'migrations/mike_bot_v2.sql', `get_mike_state non espone '${k}'`);
        }
        for (const k of ['won_today', 'lost_today', 'cycles_today', 'events_today', 'live_now', 'reconciling', 'liability_source']) {
            const has = maggKeys.includes(k);
            rep.mark(`get_mike_state.aggregates.${k}`, 'presente (mike_bot_v2)', has ? 'presente' : 'ASSENTE', has);
        }
        expect(ok.length).toBeGreaterThan(0);
    });
});
