// ============================================================================
// Verifica delle migrazioni del 25/09 (AUDIT5) su un PostgreSQL VERO in memoria
// (PGlite = Postgres compilato in WebAssembly), SENZA toccare il DB di produzione.
//
//   1. migrations/market_delays_ht_2026-09-25.sql (R7)
//      - lega finta 547, 10 partite, 2 SENZA HT: over 0.5 1T calcolato su 8 eventi
//        (prima: su 10, con le 2 partite contate 0-0);
//      - mercati FT IDENTICI alla versione di prima (sql/market_delays_rpc.sql);
//      - la serie di ogni mercato del cruscotto coincide con quella di
//        get_market_frequency (stesse partite, stesso ordine, stesso esito).
//   2. migrations/get_direction_eta_2026-09-25.sql (R5)
//      - eta' della pagella, presenza della quota in analytics_bets, data della
//        calibrazione Poisson settimanale (lega -> globale).
//
// Uso (PGlite NON e' nel repo: si installa in una cartella a parte, mai nel
// checkout principale):
//   mkdir C:\tmp\pgl && cd C:\tmp\pgl && npm init -y && npm i @electric-sql/pglite@0.5.8
//   set PGLITE_DIR=C:\tmp\pgl
//   node AUDIT_2026-09-25/verifica_audit5_pglite.mjs            (atteso: tutto OK, exit 0)
//   set MUTANTE=coalesce  -> rimette "HT mancante = 0-0"       (atteso: ROSSO, exit 1)
//   set MUTANTE=noguard   -> toglie la sola guardia HT         (atteso: ROSSO, exit 1)
//   set MUTANTE=eta_quota -> la quota della partita non si filtra per fixture (ROSSO)
//   set MUTANTE=eta_engine -> l eta della pagella prende anche le righe non Poisson (ROSSO)
// ============================================================================
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const pgliteDir = process.env.PGLITE_DIR;
if (!pgliteDir) { console.error('PGLITE_DIR non impostata'); process.exit(2); }
const { PGlite } = await import(pathToFileURL(path.join(pgliteDir, 'node_modules/@electric-sql/pglite/dist/index.js')).href);

const MUT = process.env.MUTANTE || '';
let fallimenti = 0;
function ok(cond, msg) {
    console.log(`${cond ? 'OK  ' : 'FAIL'} ${msg}`);
    if (!cond) fallimenti++;
}
const leggi = rel => fs.readFileSync(path.join(root, rel), 'utf8');

async function nuovoDb() {
    const db = new PGlite();
    await db.exec(`
        create role anon; create role authenticated; create role service_role;
        create table public.matches (
            fixture_id bigint primary key, league_id int, season_year int,
            fixture_date timestamptz, status_short text,
            home_team_name text, away_team_name text,
            goals_home int, goals_away int, halftime_home int, halftime_away int,
            fulltime_home int, fulltime_away int);
    `);
    return db;
}

// lega 547: [fid, gol casa, gol trasf., HT casa, HT trasf.] in ordine cronologico
const PARTITE = [
    [1001, 1, 0, 1, 0],
    [1002, 0, 0, 0, 0],
    [1003, 2, 1, 0, 0],
    [1004, 1, 1, 1, 0],
    [1005, 2, 2, 1, 1],
    [1006, 0, 1, 0, 0],
    [1007, 3, 0, 2, 0],
    [1008, 1, 2, 0, 1],
    [1009, 2, 0, null, null],   // HT ignoto
    [1010, 1, 1, null, null],   // HT ignoto
];

async function carica(db) {
    for (const [i, [fid, h, a, hh, ha]] of PARTITE.entries()) {
        await db.query(
            `insert into matches values ($1::bigint,547,2026,$2::timestamptz,'FT',$7::text,$8::text,
                                        $3::int,$4::int,$5::int,$6::int,$3::int,$4::int)`,
            [fid, new Date(Date.UTC(2026, 7, 1 + i)).toISOString(), h, a, hh, ha, `H${fid}`, `A${fid}`]);
    }
}

const delays = async (db, market, target = null) =>
    (await db.query(`select public.get_market_delays(547,$1,$2,'all',null,null) as r`, [market, target])).rows[0].r;
const freq = async (db, market, sel, line = null) =>
    (await db.query(`select public.get_market_frequency(547,$1,$2,$3,'all',null,null) as r`, [market, sel, line])).rows[0].r;

// ---------------------------------------------------------------- R7
const vecchio = await nuovoDb();
await vecchio.exec(leggi('sql/market_delays_rpc.sql'));
await carica(vecchio);

let sqlNuovo = leggi('migrations/market_delays_ht_2026-09-25.sql');
if (MUT === 'coalesce') {
    sqlNuovo = sqlNuovo
        .replace("when v_uses_ht and (s.hh is null or s.ha is null) then null  -- HT ignoto: escluso", '')
        .replace("when 'ovpt'  then ((s.hh + s.ha)::numeric > v_line)::int",
                 "when 'ovpt'  then ((coalesce(s.hh,0) + coalesce(s.ha,0))::numeric > v_line)::int");
}
if (MUT === 'noguard') {
    sqlNuovo = sqlNuovo.replace("when v_uses_ht and (s.hh is null or s.ha is null) then null  -- HT ignoto: escluso", '');
}
if ((MUT === 'coalesce' || MUT === 'noguard') && sqlNuovo === leggi('migrations/market_delays_ht_2026-09-25.sql')) {
    console.error(`mutante ${MUT} NON applicato`); process.exit(3);
}
const nuovo = await nuovoDb();
await nuovo.exec(leggi('sql/market_frequency_rpc.sql'));
await nuovo.exec(sqlNuovo);
await carica(nuovo);

const o05v = await delays(vecchio, 'ovpt', '0.5');
const o05n = await delays(nuovo, 'ovpt', '0.5');
console.log(`over 0.5 1T  PRIMA: n_eventi=${o05v.meta.n_effective} ritardo=${o05v.stats.ritardo_attuale} record=${o05v.stats.record} media_rit=${o05v.stats.media_ritardi}`);
console.log(`over 0.5 1T  DOPO : n_eventi=${o05n.meta.n_effective} ritardo=${o05n.stats.ritardo_attuale} record=${o05n.stats.record} media_rit=${o05n.stats.media_ritardi} n_ht_missing=${o05n.meta.n_ht_missing}`);
ok(o05v.meta.n_effective === 10, 'prima: le 2 partite senza HT erano contate (10 eventi, 0-0)');
ok(o05n.meta.n_effective === 8, 'dopo: over 0.5 1T calcolato su 8 eventi (2 senza HT escluse)');
ok(o05n.meta.n_scope === 10 && o05n.meta.n_ht_missing === 2 && o05n.meta.ht_missing_rule === 'escluse',
   'meta: n_scope 10, n_ht_missing 2, regola dichiarata');
ok(!o05n.series.some(p => p.fid === 1009 || p.fid === 1010), 'le 2 partite senza HT non sono nella serie');
ok(o05n.stats.ritardo_attuale === 0 && o05v.stats.ritardo_attuale === 2,
   'ritardo attuale: 0 (ultima con HT e gol nel 1T) invece di 2 gonfiato dagli 0-0 finti');
const pf1x = await delays(nuovo, 'pf1x');
ok(pf1x.meta.n_effective === 8, `pf1x (HT+FT) su 8 eventi (visto ${pf1x.meta.n_effective})`);
const ggst = await delays(nuovo, 'ggst');
ok(ggst.meta.n_effective === 8, `ggst (2 tempo derivato) su 8 eventi (visto ${ggst.meta.n_effective})`);

// mercati FT: identici a prima (a meno delle 2 chiavi meta nuove)
const senzaNuove = r => { const c = structuredClone(r); delete c.meta.ht_missing_rule; delete c.meta.n_ht_missing; return c; };
for (const [m, t] of [['over', '2.5'], ['under', '1.5'], ['x', null], ['re', '1-1'], ['sge', '2'], ['ggov25', null]]) {
    const a = await delays(vecchio, m, t), b = await delays(nuovo, m, t);
    ok(JSON.stringify(a) === JSON.stringify(senzaNuove(b)), `FT invariato: ${m} ${t ?? ''}`);
    ok(b.meta.n_ht_missing === 0, `FT: nessuna esclusione HT su ${m}`);
}

// serie del cruscotto: stessa serie di get_market_frequency (stesse partite/ordine/esito)
const coppie = [
    [['ovpt', '0.5'], ['ou_ht', 'over', 0.5]], [['unpt', '0.5'], ['ou_ht', 'under', 0.5]],
    [['pt1', null], ['1x2_ht', '1']], [['ptx', null], ['1x2_ht', 'X']], [['pt2', null], ['1x2_ht', '2']],
    [['1', null], ['1x2', '1']], [['x', null], ['1x2', 'X']], [['2', null], ['1x2', '2']],
    [['gg', null], ['btts', 'yes']], [['ng', null], ['btts', 'no']],
    [['over', '1.5'], ['ou_ft', 'over', 1.5]], [['under', '2.5'], ['ou_ft', 'under', 2.5]],
    [['over', '3.5'], ['ou_ft', 'over', 3.5]],
];
for (const [[dm, dt], [fm, fs, fl]] of coppie) {
    const d = await delays(nuovo, dm, dt), f = await freq(nuovo, fm, fs, fl ?? null);
    const sd = JSON.stringify(d.series.map(p => [p.fid, p.out]));
    const sf = JSON.stringify(f.points.map(p => [p.fid, p.out]));
    ok(sd === sf, `serie ${dm} ${dt ?? ''} == frequenza ${fm} ${fs} ${fl ?? ''}`);
}

// ---------------------------------------------------------------- R5
const eta = await nuovoDb();
await eta.exec(`
    create table public.direction_pagella (engine text, market text, selection text, league_id bigint,
        prob_bucket text, n int, hits int, hit_rate numeric, base_rate numeric, generated_at timestamptz,
        primary key (engine, market, selection, league_id, prob_bucket));
    create table public.analytics_bets (fixture_id bigint not null, market text not null, selection text not null,
        kickoff timestamptz, odds_betfair numeric, odds_book numeric, primary key (fixture_id, market, selection));
    create table public.poisson_calibration (league_id bigint primary key, corrections jsonb not null default '{}',
        min_n int, total_fixtures int, generated_at timestamptz not null default now(),
        created_at timestamptz default now(), updated_at timestamptz default now());
    insert into direction_pagella values
        ('poisson','1x2','H',0,'<.30',10,3,0.3,0.4,'2026-09-24T17:59:00Z'),
        ('poisson','1x2','H',39,'<.30',10,3,0.3,0.4,'2026-09-23T10:00:00Z'),
        ('ml','1x2','H',0,'<.30',10,3,0.3,0.4,'2026-09-25T09:00:00Z');
    insert into analytics_bets values
        (77,'1x2','H','2026-09-25T18:00:00Z',2.1,null),
        (77,'btts','Yes','2026-09-25T18:00:00Z',null,null),
        (88,'1x2','A','2026-09-26T18:00:00Z',3.0,2.9);
    insert into poisson_calibration (league_id, generated_at) values
        (0,'2026-09-21T03:27:00Z'), (39,'2026-09-21T03:27:00Z'), (135,'2026-09-07T03:27:00Z');
`);
let sqlEta = leggi('migrations/get_direction_eta_2026-09-25.sql');
if (MUT === 'eta_quota') sqlEta = sqlEta.replace('WHERE ab.fixture_id = p_fixture_id', 'WHERE true');
if (MUT === 'eta_engine') sqlEta = sqlEta.replace("WHERE pg.engine = 'poisson'", 'WHERE true');
// un mutante che non cambia il testo non falsifica niente: si ferma rumorosamente
const originali = { eta_quota: 'migrations/get_direction_eta_2026-09-25.sql', eta_engine: 'migrations/get_direction_eta_2026-09-25.sql' };
if (MUT in originali && sqlEta === leggi(originali[MUT])) { console.error(`mutante ${MUT} NON applicato`); process.exit(3); }
await eta.exec(sqlEta);
const e77 = (await eta.query(`select public.get_direction_eta(77) as r`)).rows[0].r;
const e99 = (await eta.query(`select public.get_direction_eta(99) as r`)).rows[0].r;
console.log('get_direction_eta(77) =', JSON.stringify(e77));
ok(new Date(e77.pagella_generated_at).toISOString() === '2026-09-24T17:59:00.000Z',
   'pagella: max(generated_at) delle righe Poisson (quelle che la RPC usa), non ML');
ok(e77.quota_righe === 2 && e77.quota_con_prezzo === 1, 'partita 77: 2 righe in analytics_bets, 1 con quota');
ok(e99.quota_righe === 0 && e99.quota_con_prezzo === 0, 'partita 99: nessuna riga -> quota assente');
const c39 = (await eta.query(`select public.get_poisson_calibration_eta(39) as r`)).rows[0].r;
const c7 = (await eta.query(`select public.get_poisson_calibration_eta(7) as r`)).rows[0].r;
ok(c39.scope === 'lega' && new Date(c39.generated_at).toISOString() === '2026-09-21T03:27:00.000Z', 'calibrazione lega 39: riga di lega');
ok(c7.scope === 'globale' && new Date(c7.generated_at).toISOString() === '2026-09-21T03:27:00.000Z', 'calibrazione lega 7: ripiego sulla globale (league_id 0)');

console.log(fallimenti ? `\nROSSO: ${fallimenti} controlli falliti` : '\nVERDE: tutti i controlli passati');
process.exit(fallimenti ? 1 : 0);
