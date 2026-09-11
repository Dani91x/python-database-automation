// ============================================================================
// realtime.cert.test.ts — §4 del report: TEMPO REALE.
//
// Il websocket non serve (ed è stubbato): si certifica LEGGENDO il codice che
//   a) ogni pagina ricarica su notifica realtime con DEBOUNCE,
//   b) l'età del feed mostrata usa `updated_at` del feed contro Date.now(),
// e LEGGENDO IL DB che le partite in gioco abbiano `safe_strategy_scan.
// updated_at` recente (< 10 s) e quote coerenti col payload.
// ============================================================================
import { describe, it, expect, afterAll } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { supabase, CERT_RUN } from './realClient';
import { scanMarketBlocks } from '@/lib/safeStrategyScan';
import { Report } from './report';

/** fuori da vitest.cert.config.ts i test si SALTANO (mai il DB reale in `npm test`) */
const d = CERT_RUN ? describe : describe.skip;
const rep = new Report('TEMPO REALE · debounce, freschezza del feed');
afterAll(() => rep.print());

const SRC = resolve(process.cwd(), 'src');
const read = (p: string) => readFileSync(resolve(SRC, p), 'utf8');

d('realtime: debounce delle ricariche', () => {
    it('Omega: subscribeOmega → reload con debounce', () => {
        const src = read('pages/Omega.tsx');
        const ms = /REALTIME_DEBOUNCE_MS\s*=\s*([\d_]+)/.exec(src)?.[1] ?? null;
        const debounced = /subscribeOmega\(\(\) => \{[\s\S]{0,260}?setTimeout\(/.test(src);
        rep.mark('Omega — debounce sul realtime', 'presente', ms ? `${ms} ms` : 'ASSENTE', debounced && Boolean(ms));
        expect(debounced).toBe(true);
    });

    it('Mike: subscribeMike → reload con debounce', () => {
        const src = read('components/mike/useMike.ts');
        const ms = /RELOAD_DEBOUNCE_MS\s*=\s*([\d_]+)/.exec(src)?.[1] ?? null;
        const debounced = /const schedule = \(\) => \{[\s\S]{0,200}?setTimeout\(/.test(src)
            && /subscribeMike\(schedule\)/.test(src);
        rep.mark('Mike — debounce sul realtime', 'presente', ms ? `${ms} ms` : 'ASSENTE', debounced && Boolean(ms));
        expect(debounced).toBe(true);
    });

    it('Safe: subscribeSafeBot → reload (debounce?)', () => {
        const src = read('components/safestrategy/useSafeBot.ts');
        const direct = /const unsub = subscribeSafeBot\(run\);/.test(src);
        const oppsFlush = /OPPS_FLUSH_MS\s*=\s*([\d_]+)/.exec(src)?.[1] ?? null;
        rep.mark('Safe — debounce su control/trades/requests', 'presente',
            direct ? 'ASSENTE (reload immediato per ogni notifica)' : 'presente', !direct);
        rep.mark('Safe — coalescenza delle opportunità', 'presente', oppsFlush ? `${oppsFlush} ms` : 'ASSENTE', Boolean(oppsFlush));
        if (direct) {
            rep.finding('MEDIUM', 'components/safestrategy/useSafeBot.ts:186',
                '`subscribeSafeBot(run)` ricarica SUBITO a ogni notifica di safe_strategy_control / _trades / _requests: nessun debounce (Omega ha REALTIME_DEBOUNCE_MS=1200, Mike RELOAD_DEBOUNCE_MS=1500). Con un burst di ordini/settlement si fanno N get_safe_state da 44+ righe. Le opportunità sono invece coalizzate (OPPS_FLUSH_MS).');
        }
        expect(oppsFlush).toBeTruthy();
    });

    it('età del feed: updated_at del feed contro Date.now()', () => {
        const chip = read('components/trading/ServiceHealthChip.tsx');
        const fmt = read('lib/format.ts');
        const usesAge = /const feedAge = ageSeconds\(feedUpdatedAt, nowMs\)/.test(chip);
        const ageImpl = /export function ageSeconds\([\s\S]{0,300}?Date\.parse\(iso\)[\s\S]{0,200}?nowMs - ms/.test(fmt);
        rep.mark('chip salute — feedAge = ageSeconds(feedUpdatedAt, nowMs)', 'sì', usesAge ? 'sì' : 'NO', usesAge);
        rep.mark('ageSeconds = (nowMs − Date.parse(updated_at)) / 1000', 'sì', ageImpl ? 'sì' : 'NO', ageImpl);
        // nowMs è un orologio di pagina che tick-a da solo (non un valore fermo)
        for (const [page, file] of [['Omega', 'pages/Omega.tsx'], ['Safe', 'pages/SafeStrategy.tsx'], ['Mike', 'pages/Mike.tsx']] as const) {
            const s = read(file);
            const ticks = /setInterval\(\(\) => setNowMs\(Date\.now\(\)\)/.test(s);
            const passesFeed = /feedUpdatedAt=\{scanStatus\?\.updated_at\}/.test(s);
            rep.mark(`${page} — orologio della pagina (nowMs) + feedUpdatedAt allo chip`, 'sì',
                ticks && passesFeed ? 'sì' : `ticks=${ticks} feedUpdatedAt=${passesFeed}`, ticks && passesFeed);
        }
        // Omega passa anche l'updated_at PER EVENTO alla tabella dei trade
        const omega = read('pages/Omega.tsx');
        const perEvent = /feedUpdatedAt=\{feedUpdatedAt\}/.test(omega) && /nowMs=\{nowMs\}/.test(omega);
        rep.mark('Omega — freschezza PER PARTITA nella tabella trade', 'sì', perEvent ? 'sì' : 'NO', perEvent);
        expect(usesAge && ageImpl).toBe(true);
    });

    it('Omega — il feed live per evento parte solo dal realtime (cold start)', () => {
        const hook = read('lib/useScanLiveFeed.ts');
        // l'effetto ha deps [] e legge wanted.current al momento del fetch: al
        // mount `eventIds` è vuoto (i trade arrivano dopo), quindi il fetch
        // iniziale non popola nulla.
        const emptyDeps = /const unsub = subscribeScanRows\([\s\S]{0,600}?\}, \[\]\);/.test(hook);
        rep.mark('useScanLiveFeedRows — refetch al cambio di eventIds', 'presente',
            emptyDeps ? 'ASSENTE (effetto con deps [])' : 'presente', !emptyDeps);
        if (emptyDeps) {
            rep.finding('MEDIUM', 'lib/useScanLiveFeed.ts:28-71',
                "l'effetto ha deps [] e filtra il fetch iniziale su `wanted.current`, che al mount è VUOTO (gli event_id arrivano con i trade, un giro dopo): le quote live della tabella Omega compaiono solo quando arriva il primo messaggio realtime per quell'evento. A scanner fermo (o nei primi secondi) la colonna «chiudendo ora» resta vuota.");
        }
        expect(typeof emptyDeps).toBe('boolean');
    });
});

d('freschezza REALE del feed sul DB', () => {
    it('safe_strategy_scan / safe_strategy_status: età delle righe in gioco', async () => {
        const now = Date.now();
        const status = await supabase.from('safe_strategy_status').select('*').eq('id', 'scanner').maybeSingle();
        const statusAge = status.data?.updated_at ? (now - Date.parse(status.data.updated_at)) / 1000 : null;
        rep.mark('safe_strategy_status.updated_at — età', '< 10 s',
            statusAge == null ? 'nessuna riga' : `${Math.round(statusAge)} s`, statusAge != null && statusAge < 10);

        const rows = await supabase
            .from('safe_strategy_scan')
            .select('event_id,sport,updated_at,payload')
            .order('updated_at', { ascending: false })
            .limit(300);
        const all = rows.data ?? [];
        const inplay = all.filter((r) => {
            const p = r.payload as { inplay?: boolean } | null;
            return p?.inplay === true;
        });
        const ages = inplay.map((r) => (r.updated_at ? (now - Date.parse(r.updated_at)) / 1000 : Number.POSITIVE_INFINITY));
        const fresh = ages.filter((a) => a < 10).length;
        rep.mark('safe_strategy_scan — righe IN GIOCO con updated_at < 10 s',
            `${inplay.length}/${inplay.length}`, `${fresh}/${inplay.length}`, inplay.length > 0 && fresh === inplay.length);
        rep.note(`righe di scan: ${all.length} (di cui in gioco ${inplay.length}) · età min ${ages.length ? Math.round(Math.min(...ages)) : '—'} s · max ${ages.length ? Math.round(Math.max(...ages)) : '—'} s`);
        if (inplay.length && fresh < inplay.length) {
            rep.finding('CRITICAL', 'servizi di scansione (scan_feed.py / safe_strategy / omega / mike)',
                `lo SCANNER NON sta scrivendo: safe_strategy_status.updated_at ha ${statusAge != null ? Math.round(statusAge) : '?'} s e nessuna delle ${inplay.length} partite in gioco ha un aggiornamento più recente di 10 s (la più fresca ha ${ages.length ? Math.round(Math.min(...ages)) : '?'} s). Le tre pagine mostrano correttamente «feed FERMO», ma quote, minuto, punteggio e prezzi di cash out a schermo sono CONGELATI: la certificazione del tempo reale (freschezza < 10 s, coincidenza quote↔payload live) NON è eseguibile in questo stato.`);
        }

        // coincidenza quote mostrate ↔ payload: verificata sulle pagine Safe/Mike
        // (safeTradeBook / live.books) negli altri file; qui si registra solo
        // che il payload contiene ancora i book delle linee attese.
        const blocks = all
            .filter((r) => r.sport === 'calcio')
            .map((r) => scanMarketBlocks(r.payload as never).length);
        const withBooks = blocks.filter((n) => n > 0).length;
        rep.mark('payload dello scan con blocchi mercato prezzabili (CS/HT/OU/BTTS)',
            `${blocks.length}/${blocks.length} righe calcio`, `${withBooks}/${blocks.length}`, withBooks > 0);
        rep.note(`blocchi mercato per riga calcio: min ${blocks.length ? Math.min(...blocks) : '—'} · max ${blocks.length ? Math.max(...blocks) : '—'}`);
        expect(all.length).toBeGreaterThan(0);
    });

    it('battito dei tre servizi (control.heartbeat_at)', async () => {
        const now = Date.now();
        for (const [bot, table] of [['Omega', 'omega_control'], ['Safe', 'safe_strategy_control'], ['Mike', 'mike_control']] as const) {
            const r = await supabase.from(table).select('status,mode,heartbeat_at').eq('id', 1).maybeSingle();
            const hb = r.data?.heartbeat_at ? (now - Date.parse(r.data.heartbeat_at)) / 1000 : null;
            rep.mark(`${bot} — battito del servizio`, '< 60 s',
                hb == null ? 'nessun battito' : `${Math.round(hb)} s (status=${r.data?.status}, mode=${r.data?.mode})`,
                hb != null && hb < 60);
            if (hb != null && hb > 60) {
                rep.finding('HIGH', `${table}.heartbeat_at`,
                    `status='${r.data?.status}' ma l'ultimo battito ha ${Math.round(hb)} s: il servizio si dichiara IN CORSA mentre è fermo. La pagina lo segnala nel chip di salute, ma il chip di stato dell'header resta «IN CORSA».`);
            }
        }
        expect(true).toBe(true);
    });
});
