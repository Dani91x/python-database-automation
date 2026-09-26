// FIX-B (26/09/2026) -- banco della migrazione migrations/analytics_rpc_veloci_2026-09-26.sql
// su un PostgreSQL VERO (PGlite = PostgreSQL 17 in wasm, in memoria; nessuna rete).
//
// ORACOLO: le RPC di PRIMA, prese byte per byte dai file che coincidono col DB vero
// (md5 del corpo verificato il 26/09 su pg_proc): migrations/analytics_rpc.sql,
// migrations/analytics_decisions_rpc.sql, migrations/market_delays_ht_2026-09-25.sql.
// Sono create nello schema `vecchio`; la migrazione nuova in `public`. Stessi dati.
// Ogni risposta nuova deve essere IDENTICA (testo jsonb) a quella di prima, salvo le
// chiavi aggiunte 'fonte_dati' / 'riepilogo_at' (controllate a parte).
//
// Uso:  node banco_pglite_analytics_veloci.mjs <.../@electric-sql/pglite/dist/index.js>
// Variabile MUTAZIONE=<nome>: applica una mutazione IN MEMORIA al testo della
// migrazione (il file non si tocca) -> il banco deve uscire ROSSO. Codice 0 = verde.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const QUI = dirname(fileURLToPath(import.meta.url));
const REPO = join(QUI, '..', '..');
const MOD = process.argv[2];
if (!MOD) { console.error('manca il percorso di @electric-sql/pglite (dist/index.js)'); process.exit(2); }
const { PGlite } = await import(pathToFileURL(MOD).href);
const leggi = (p) => readFileSync(join(REPO, p), 'utf8').replace(/\r\n/g, '\n');

// ------------------------------------------------------------------ mutazioni
const MUTAZIONI = {
  // riepilogo: una fascia di confidenza sbagliata (bin *4 invece di *5)
  bin: ["(least(floor(s.prob*20),19)*5)::smallint as conf_bin", "(least(floor(s.prob*20),19)*4)::smallint as conf_bin"],
  // riepilogo: hit contati come 1 anche quando sbagliati
  hit: ["case when s.hit then 1.0 else 0.0 end as hv", "1.0 as hv"],
  // livello G che perde la stagione
  livello: ["group by fonte, engine, market, selection, season_year, conf_bin, n_engines_agree, placed;",
            "group by fonte, engine, market, selection, conf_bin, n_engines_agree, placed, season_year;\n    delete from analytics_riepilogo_segnali where lvl = 'G' and placed;"],
  // ramo riepilogo che ignora il filtro stagione
  stagione: ["f_r := f_r || format(' and r.season_year = %s', p_season_year);", "null;"],
  // decisioni: media della quota sulla popolazione sbagliata
  quota: ["sum(odds_sum) / nullif(sum(odds_n),0)::numeric avg_odds", "sum(odds_sum) / nullif(sum(n),0)::numeric avg_odds"],
  // decisioni: stake anche delle non settlate
  stake: ["coalesce(sum(stake_sum) filter (where status=''PLACED'' and settled),0) stake",
          "coalesce(sum(stake_sum) filter (where status=''PLACED''),0) stake"],
  // drill: limite per ramo senza l'offset
  drill: ["v_top := v_lim + v_off;", "v_top := v_lim;"],
  // ritardi: distribuzione con join sbagliato (cnt_rit contato sulle serie)
  distrib: ["left join rit_by_len r2 on r2.k = v.k", "left join occ_by_len r2 on r2.k = v.k"],
  // filtri: payload del riepilogo al posto sbagliato
  filtri: ["where m.chiave = 'filtri_analytics' and m.payload is not null", "where m.chiave = 'filtri_decisioni' and m.payload is not null"],
};
let NUOVA = leggi('migrations/analytics_rpc_veloci_2026-09-26.sql');
const MUT = process.env.MUTAZIONE || '';
if (MUT) {
  const m = MUTAZIONI[MUT];
  if (!m) { console.error(`mutazione sconosciuta: ${MUT}`); process.exit(2); }
  if (!NUOVA.includes(m[0])) { console.error(`mutazione ${MUT}: testo non trovato (la migrazione e' cambiata)`); process.exit(2); }
  NUOVA = NUOVA.replace(m[0], m[1]);
  console.log(`MUTAZIONE ATTIVA: ${MUT}`);
}

let esiti = 0, falliti = 0;
function controlla(nome, ok, dettaglio = '') {
  esiti++; if (!ok) falliti++;
  if (!ok || process.env.VERBOSO) console.log(`${ok ? 'OK  ' : 'KO  '} ${nome}${dettaglio ? '  ' + dettaglio : ''}`);
}

// ------------------------------------------------------------------ schema (tipi del vero)
const BASE = `
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role; END IF;
END $$;
CREATE SCHEMA vecchio;
CREATE TABLE public.analytics_signals (
  id bigserial PRIMARY KEY, signal_uid text UNIQUE, engine text, generated_at timestamptz,
  fixture_id bigint, league_id bigint, league_name text, season_year smallint,
  home_team text, away_team text, kickoff timestamptz, market text, selection text,
  line numeric, direction text, prob numeric, prob_raw numeric, fair_odds numeric,
  freq_baseline numeric, freq_current numeric, freq_deviation numeric,
  delay_current integer, delay_record integer, delay_avg numeric,
  n_engines_agree smallint, consensus_prob numeric, placed boolean, status text,
  settled boolean, result text, hit boolean, goals_home smallint, goals_away smallint,
  total_goals smallint, ht_home smallint, ht_away smallint, oos_valid boolean, reliable boolean,
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(), first_goal_minute smallint
);
CREATE TABLE public.fixture_predictions (
  fixture_id integer PRIMARY KEY, league_id integer, league_name text, season_year integer,
  fixture_date timestamptz, home_team_name text, away_team_name text,
  percent_home numeric, percent_draw numeric, percent_away numeric, result_outcome text, status text
);
CREATE TABLE public.analytics_decisions (
  id bigserial PRIMARY KEY, decision_uid text UNIQUE, decision_logic text, engine text,
  fixture_id bigint, league_id bigint, league_name text, season_year smallint,
  home_team text, away_team text, kickoff timestamptz, market text, selection text,
  run_date date, status text, reject_filter text, prob numeric, edge numeric,
  odds numeric, stake numeric, pnl numeric, hit boolean, settled boolean
);
CREATE TABLE public.matches (
  id bigserial PRIMARY KEY, fixture_id integer UNIQUE, league_id integer, season_year integer,
  fixture_date timestamptz, status_short text, home_team_name text, away_team_name text,
  goals_home integer, goals_away integer, halftime_home integer, halftime_away integer,
  fulltime_home integer, fulltime_away integer
);
`;

// solo le definizioni di funzione di un file (niente grant/indici), dirottate su `vecchio`
function funzioniVecchie(testo, nomi) {
  const out = [];
  for (const nome of nomi) {
    const i = testo.indexOf(`create or replace function public.${nome}(`);
    if (i < 0) throw new Error(`funzione ${nome} non trovata`);
    const j = testo.indexOf('$$;', testo.indexOf('$$', i) + 2) + 3;
    out.push(testo.slice(i, j).replace(`function public.${nome}(`, `function vecchio.${nome}(`));
  }
  return out.join('\n\n');
}
const VECCHIE = [
  funzioniVecchie(leggi('migrations/analytics_rpc.sql'), ['get_analytics', 'get_analytics_rows', 'get_analytics_filters']),
  funzioniVecchie(leggi('migrations/analytics_decisions_rpc.sql'), ['get_decisions', 'get_decisions_filters']),
  funzioniVecchie(leggi('migrations/market_delays_ht_2026-09-25.sql'), ['get_market_delays']),
].join('\n\n');

// ------------------------------------------------------------------ dati deterministici
function rng(seme) { let s = seme >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
const R = rng(20260926);
const pick = (a) => a[Math.floor(R() * a.length)];
const q = (v) => v === null || v === undefined ? 'NULL' : (typeof v === 'string' ? `'${v.replace(/'/g, "''")}'` : String(v));
const LEGHE = [[39, 'Premier League'], [135, 'Serie A'], [667, 'Friendlies Clubs'], [45, 'FA Cup'], [5, null]];
const MERCATI = { '1x2': ['H', 'D', 'A'], over_2_5: ['Over', 'Under'], btts: ['Yes', 'No'], ht_1x2: ['H', 'D', 'A'] };
const ENGINES = ['poisson', 'ml', 'tacticai'];
const KO0 = Date.UTC(2025, 0, 1);

async function riempi(db, nFix, fid0) {
  const sig = [], fp = [], dec = [];
  for (let k = 0; k < nFix; k++) {
    const fid = fid0 + k;
    const [lid, lname] = pick(LEGHE);
    const season = pick([2024, 2025, 2026]);
    // kickoff UNICI (niente pari merito nel drill) + alcuni NULL
    const ko = R() < 0.03 ? null : new Date(KO0 + k * 3_600_000 + Math.floor(R() * 1000) * 1000).toISOString();
    const esito = R() < 0.15 ? null : pick(['H', 'D', 'A']);
    // percentuali API: interi o con decimali, qualcuna NULL
    const ph = R() < 0.05 ? null : (R() < 0.7 ? Math.floor(R() * 70) + 10 : Number((R() * 70 + 10).toFixed(1)));
    fp.push(`(${fid}, ${q(lid)}, ${q(lname)}, ${season}, ${q(ko)}, 'Casa ${k}', 'Ospite ${k}', ${q(ph)}, ${q(Math.floor(R() * 40))}, ${q(Math.floor(R() * 50))}, ${q(esito)}, 'ok')`);
    for (const eng of ENGINES) {
      if (R() < 0.25) continue;
      for (const [mk, sels] of Object.entries(MERCATI)) {
        if (R() < 0.3) continue;
        for (const sel of sels) {
          const settled = R() < 0.85;
          const hit = settled ? (R() < 0.05 ? null : R() < 0.45) : null;
          const prob = R() < 0.03 ? null : (R() < 0.02 ? 1 : Number(R().toFixed(4)));
          const agree = R() < 0.2 ? null : Math.floor(R() * 4);
          const placed = R() < 0.1 ? null : R() < 0.3;
          const lname2 = lname && R() < 0.05 ? lname + ' (vecchio nome)' : lname;
          sig.push(`(${q(`${eng}|${fid}|${mk}|${sel}`)}, ${q(eng)}, ${fid}, ${q(lid)}, ${q(lname2)}, ${season}, 'Casa', 'Ospite', ${q(ko)}, ${q(mk)}, ${q(sel)}, ${q(prob)}, ${q(agree)}, ${q(placed)}, ${settled}, ${q(hit)}, ${q(R() < 0.5 ? Math.floor(R() * 12) : null)}, ${q(R() < 0.5 ? Number((R() - 0.5).toFixed(3)) : null)}, ${q(R() < 0.5 ? Math.floor(R() * 90) : null)})`);
        }
      }
    }
    for (const logic of ['google_sheets', 'strategia_x']) {
      if (R() < 0.4) continue;
      const st = pick(['PLACED', 'PLACED', 'REJECTED', 'NO_SIGNAL']);
      const mk = st === 'NO_SIGNAL' ? '(none)' : pick(Object.keys(MERCATI));
      const settled = R() < 0.7;
      const hit = settled && st === 'PLACED' ? (R() < 0.1 ? null : R() < 0.5) : null;
      const odds = st === 'PLACED' ? Number((1.2 + R() * 4).toFixed(2)) : null;
      const stake = st === 'PLACED' ? (R() < 0.1 ? null : Number((R() * 20).toFixed(2))) : null;
      const pnl = stake != null ? Number(((R() - 0.5) * stake).toFixed(2)) : null;
      dec.push(`(${q(`${logic}|${fid}`)}, ${q(logic)}, ${q(pick(['poisson', 'ml']))}, ${fid}, ${q(lid)}, ${q(lname)}, ${season}, ${q(ko)}, ${q(mk)}, ${q(pick(['H', 'Over', 'Yes']))}, ${q(st)}, ${q(st === 'REJECTED' ? pick(['edge', 'liquidita', 'quota']) : null)}, ${q(R() < 0.1 ? null : Number(R().toFixed(4)))}, ${q(R() < 0.3 ? null : Number((R() * 0.2 - 0.05).toFixed(4)))}, ${q(odds)}, ${q(stake)}, ${q(pnl)}, ${q(hit)}, ${settled})`);
    }
  }
  const lotti = (arr, n) => { const o = []; for (let i = 0; i < arr.length; i += n) o.push(arr.slice(i, i + n)); return o; };
  for (const l of lotti(fp, 300)) await db.query(`INSERT INTO fixture_predictions VALUES ${l.join(',')}`);
  for (const l of lotti(sig, 300)) await db.query(`INSERT INTO analytics_signals (signal_uid, engine, fixture_id, league_id, league_name, season_year, home_team, away_team, kickoff, market, selection, prob, n_engines_agree, placed, settled, hit, delay_current, freq_deviation, first_goal_minute) VALUES ${l.join(',')}`);
  for (const l of lotti(dec, 300)) await db.query(`INSERT INTO analytics_decisions (decision_uid, decision_logic, engine, fixture_id, league_id, league_name, season_year, kickoff, market, selection, status, reject_filter, prob, edge, odds, stake, pnl, hit, settled) VALUES ${l.join(',')}`);
  return { nSig: sig.length, nFp: fp.length, nDec: dec.length };
}

async function riempiMatches(db) {
  const righe = [];
  let fid = 5_000_000;
  for (const [lid, n] of [[667, 900], [358, 350], [77, 25]]) {
    for (let k = 0; k < n; k++) {
      const st = R() < 0.06 ? 'NS' : pick(['FT', 'FT', 'FT', 'FT', 'AET', 'PEN']);
      const gh = Math.floor(R() * 5), ga = Math.floor(R() * 4);
      const ftNull = st !== 'FT' && R() < 0.4;             // AET/PEN senza fulltime_*: escluse
      const htNull = R() < 0.12;                           // HT ignoto: escluse dai mercati HT
      const hh = htNull ? null : Math.min(gh, Math.floor(R() * 3)), ha = htNull ? null : Math.min(ga, Math.floor(R() * 2));
      // date con PARI MERITO (stesso orario) per provare l'ordine (fixture_date, fixture_id)
      const d = new Date(Date.UTC(2019, 0, 1) + Math.floor(k / 3) * 86_400_000 * 2).toISOString();
      righe.push(`(${fid++}, ${lid}, ${2019 + Math.floor(k / 150)}, '${d}', '${st}', 'Casa ${k % 17}', 'Ospite ${k % 13}', ${st === 'NS' ? 'NULL' : gh}, ${st === 'NS' ? 'NULL' : ga}, ${st === 'NS' ? 'NULL' : q(hh)}, ${st === 'NS' ? 'NULL' : q(ha)}, ${st === 'NS' || ftNull ? 'NULL' : gh}, ${st === 'NS' || ftNull ? 'NULL' : ga})`);
    }
  }
  for (let i = 0; i < righe.length; i += 300) {
    await db.query(`INSERT INTO matches (fixture_id, league_id, season_year, fixture_date, status_short, home_team_name, away_team_name, goals_home, goals_away, halftime_home, halftime_away, fulltime_home, fulltime_away) VALUES ${righe.slice(i, i + 300).join(',')}`);
  }
}

// ------------------------------------------------------------------ confronto
const senzaChiaviNuove = (o) => { const c = { ...o }; delete c.fonte_dati; delete c.riepilogo_at; return c; };
const perGrp = (gs) => [...gs].sort((a, b) => (String(a.grp) < String(b.grp) ? -1 : String(a.grp) > String(b.grp) ? 1 : 0));

async function uno(db, sql) { return (await db.query(sql)).rows[0].r; }

async function confrontaAnalytics(db, nome, args, attesaFonte) {
  const a = args.join(', ');
  const vec = await uno(db, `select vecchio.get_analytics(${a})::text as r`);
  const nuo = await uno(db, `select public.get_analytics(${a})::text as r`);
  const V = JSON.parse(vec), N = JSON.parse(nuo);
  // stesso testo numerico: confronto sul testo jsonb dei gruppi ordinati per grp
  const tv = JSON.stringify(perGrp(V.groups)), tn = JSON.stringify(perGrp(N.groups));
  controlla(`get_analytics ${nome}: gruppi identici`, tv === tn, tv === tn ? `(${V.groups.length} gruppi)` : `\n   vecchia=${tv.slice(0, 400)}\n   nuova  =${tn.slice(0, 400)}`);
  controlla(`get_analytics ${nome}: fonte_dati=${attesaFonte}`, N.fonte_dati === attesaFonte, `vista ${N.fonte_dati}`);
  controlla(`get_analytics ${nome}: stesse chiavi di prima + 2`, JSON.stringify(Object.keys(senzaChiaviNuove(N)).sort()) === JSON.stringify(Object.keys(V).sort()));
  return V.groups.length;
}

async function confrontaDecisioni(db, nome, args, attesaFonte) {
  const a = args.join(', ');
  const V = JSON.parse(await uno(db, `select vecchio.get_decisions(${a})::text as r`));
  const N = JSON.parse(await uno(db, `select public.get_decisions(${a})::text as r`));
  const tv = JSON.stringify(perGrp(V.groups)), tn = JSON.stringify(perGrp(N.groups));
  controlla(`get_decisions ${nome}: gruppi identici`, tv === tn, tv === tn ? `(${V.groups.length} gruppi)` : `\n   vecchia=${tv.slice(0, 400)}\n   nuova  =${tn.slice(0, 400)}`);
  controlla(`get_decisions ${nome}: fonte_dati=${attesaFonte}`, N.fonte_dati === attesaFonte, `vista ${N.fonte_dati}`);
}

// ------------------------------------------------------------------ esecuzione
const db = new PGlite();
await db.exec(BASE);
await db.exec(VECCHIE);
const nDati = await riempi(db, 1500, 1_000_000);
await riempiMatches(db);
console.log(`dati: ${JSON.stringify(nDati)}`);

// (a) PRIMA della migrazione: la funzione vecchia risponde (sanita' del banco)
controlla('oracolo: vecchio.get_analytics risponde', (await uno(db, `select vecchio.get_analytics()::text as r`)).includes('groups'));

// (b) migrazione (con il primo riempimento del riepilogo) + idempotenza (seconda applicazione)
await db.exec(NUOVA);
await db.exec(NUOVA);
const meta = (await db.query(`select chiave, righe from analytics_riepilogo_meta order by chiave`)).rows;
controlla('riepilogo: 4 chiavi di meta', meta.length === 4, JSON.stringify(meta));

// (c) get_analytics: ramo riepilogo su ogni raggruppamento x filtri-dimensione
const GRUPPI = ['overall', 'engine', 'market', 'selection', 'league', 'confidence'];
const FILTRI_RIEP = [
  ['nessun filtro', {}],
  ['motore ml', { p_engine: "'ml'" }],
  ['motore api', { p_engine: "'api'" }],
  ['mercato 1x2', { p_market: "'1x2'" }],
  ['mercato btts', { p_market: "'btts'" }],
  ['selezione H', { p_selection: "'H'" }],
  ['lega 39', { p_league_id: '39' }],
  ['lega 5 (nome NULL)', { p_league_id: '5' }],
  ['stagione 2025', { p_season_year: '2025' }],
  ['concordanza >=2', { p_min_agree: '2' }],
  ['solo piazzati', { p_placed_only: 'true' }],
  ['combinati', { p_engine: "'poisson'", p_market: "'over_2_5'", p_league_id: '135', p_season_year: '2026' }],
];
const FILTRI_DIRETTI = [
  ['prob >= 0.6', { p_prob_min: '0.6' }],
  ['date', { p_date_from: "'2025-01-10'::timestamptz", p_date_to: "'2025-02-20'::timestamptz" }],
  ['ritardo >= 5', { p_delay_min: '5' }],
  ['frequenza neg', { p_freq_dev: "'neg'" }],
  ['timing <= 30', { p_timing_max: '30' }],
];
const argomenti = (f, g) => [...Object.entries(f).map(([k, v]) => `${k} => ${v}`), `p_group_by => '${g}'`];
let nonVuoti = 0;
for (const g of GRUPPI) {
  for (const [nome, f] of FILTRI_RIEP) nonVuoti += (await confrontaAnalytics(db, `${nome} / ${g}`, argomenti(f, g), 'riepilogo')) > 0 ? 1 : 0;
  for (const [nome, f] of FILTRI_DIRETTI) await confrontaAnalytics(db, `${nome} / ${g}`, argomenti(f, g), 'diretta');
}
controlla('get_analytics: la maggior parte dei confronti su dati NON vuoti', nonVuoti >= 60, `non vuoti ${nonVuoti}`);

// (d) get_decisions
const GRUPPI_D = ['logic', 'engine', 'market', 'selection', 'status', 'reject', 'league', 'confidence'];
const FILTRI_D = [
  ['nessun filtro', {}, 'riepilogo'], ['stato PLACED', { p_status: "'PLACED'" }, 'riepilogo'],
  ['logica', { p_logic: "'google_sheets'" }, 'riepilogo'], ['motivo', { p_reject: "'edge'" }, 'riepilogo'],
  ['lega 667', { p_league_id: '667' }, 'riepilogo'], ['mercato+stagione', { p_market: "'btts'", p_season_year: '2024' }, 'riepilogo'],
  ['date', { p_date_from: "'2025-01-05'::timestamptz" }, 'diretta'],
];
for (const g of GRUPPI_D) for (const [nome, f, fonte] of FILTRI_D) await confrontaDecisioni(db, `${nome} / ${g}`, argomenti(f, g), fonte);

// (e) filtri: stesso jsonb di prima (+ chiavi nuove)
for (const fn of ['get_analytics_filters', 'get_decisions_filters']) {
  const V = JSON.parse(await uno(db, `select vecchio.${fn}()::text as r`));
  const N = JSON.parse(await uno(db, `select public.${fn}()::text as r`));
  controlla(`${fn}: identico a prima`, JSON.stringify(senzaChiaviNuove(N)) === JSON.stringify(V));
  controlla(`${fn}: fonte riepilogo con orario`, N.fonte_dati === 'riepilogo' && typeof N.riepilogo_at === 'string');
}

// (f) drill-down: stesse righe, stesso ordine, anche con offset
for (const [nome, f] of [['bin 60', { p_conf_bin: '60' }], ['nessun filtro', {}], ['api', { p_engine: "'api'" }],
                         ['lega 39 offset 30', { p_league_id: '39', p_offset: '30', p_limit: '25' }],
                         ['bin 45 offset 120', { p_conf_bin: '45', p_offset: '120', p_limit: '50' }]]) {
  const a = Object.entries(f).map(([k, v]) => `${k} => ${v}`).join(', ');
  const V = JSON.parse(await uno(db, `select vecchio.get_analytics_rows(${a})::text as r`));
  const N = JSON.parse(await uno(db, `select public.get_analytics_rows(${a})::text as r`));
  // piu' righe per partita hanno lo STESSO kickoff: fra pari merito l'ordine non e'
  // definito (ne' prima ne' ora). Si esige: stessa sequenza di kickoff, stesso limite/
  // offset, e stesse righe (multinsieme) per ogni kickoff che non sta sul bordo di pagina.
  const ks = (x) => x.rows.map(r => r.kickoff);
  const bordo = new Set([ks(V)[0], ks(V)[ks(V).length - 1]]);
  const interno = (x) => x.rows.filter(r => !bordo.has(r.kickoff)).map(r => JSON.stringify(r)).sort();
  const ok = JSON.stringify(ks(V)) === JSON.stringify(ks(N)) && V.limit === N.limit && V.offset === N.offset
    && JSON.stringify(interno(V)) === JSON.stringify(interno(N));
  controlla(`get_analytics_rows ${nome}: stesse righe`, ok, `(${V.rows.length} righe, ${interno(V).length} interne)`);
}

// (g) Studio Ritardi: ogni mercato x modo, output testuale identico
const MERC = [['re', "'1-1'"], ['re', "'4-3'"], ['sge', "'2'"], ['over', "'2.5'"], ['under', "'1.5'"], ['ovpt', "'0.5'"],
              ['unpt', "'1.5'"], ['ggpt', 'null'], ['ggst', 'null'], ['pf1x', 'null'], ['pf2x', 'null'], ['pfx1', 'null'],
              ['pfx2', 'null'], ['pt1', 'null'], ['ptx', 'null'], ['pt2', 'null'], ['x', 'null'], ['1', 'null'], ['2', 'null'],
              ['gg', 'null'], ['ng', 'null'], ['ggov25', 'null']];
let nRit = 0;
for (const lega of [667, 358, 77, 999]) {
  for (const [m, t] of MERC) {
    for (const modo of [`'all', null, null`, `'last_n', 50, null`, `'season', null, 2020`]) {
      const a = `${lega}, '${m}', ${t}, ${modo}`;
      const V = await uno(db, `select vecchio.get_market_delays(${a})::text as r`);
      const N = await uno(db, `select public.get_market_delays(${a})::text as r`);
      controlla(`get_market_delays(${a}): identico`, V === N);
      nRit++;
    }
  }
}
console.log(`ritardi confrontati: ${nRit}`);

// (h) indice di copertura dello storico-lega presente
controlla('esiste idx_matches_storico_lega_cover', (await db.query(`select 1 from pg_indexes where indexname='idx_matches_storico_lega_cover'`)).rows.length === 1);

// (i) riepilogo VECCHIO dopo dati nuovi: fonte dichiarata, refresh lo riallinea
await riempi(db, 200, 2_000_000);
const V1 = JSON.parse(await uno(db, `select vecchio.get_analytics(p_group_by => 'engine')::text as r`));
const N1 = JSON.parse(await uno(db, `select public.get_analytics(p_group_by => 'engine')::text as r`));
controlla('dati nuovi senza refresh: il riepilogo e\' quello di prima (dichiarato)', JSON.stringify(perGrp(V1.groups)) !== JSON.stringify(perGrp(N1.groups)) && N1.fonte_dati === 'riepilogo');
const prima = N1.riepilogo_at;
await db.query('select public.refresh_analytics_riepilogo()');
const N2 = JSON.parse(await uno(db, `select public.get_analytics(p_group_by => 'engine')::text as r`));
controlla('dopo refresh: di nuovo identico al calcolo diretto', JSON.stringify(perGrp(V1.groups)) === JSON.stringify(perGrp(N2.groups)));
controlla('dopo refresh: orario del riepilogo avanzato', N2.riepilogo_at > prima, `${prima} -> ${N2.riepilogo_at}`);

// (j) senza riepilogo (meta vuota): si torna al calcolo diretto, stesso risultato
await db.query(`delete from analytics_riepilogo_meta where true`);
const N3 = JSON.parse(await uno(db, `select public.get_analytics(p_group_by => 'market')::text as r`));
const V3 = JSON.parse(await uno(db, `select vecchio.get_analytics(p_group_by => 'market')::text as r`));
controlla('meta assente: ramo diretto, identico', N3.fonte_dati === 'diretta' && JSON.stringify(perGrp(V3.groups)) === JSON.stringify(perGrp(N3.groups)));
const F3 = JSON.parse(await uno(db, `select public.get_analytics_filters()::text as r`));
controlla('meta assente: filtri calcolati diretti', F3.fonte_dati === 'diretta' && F3.riepilogo_at === null);

// (k) sicurezza: tabelle di riepilogo non leggibili da authenticated, refresh solo service_role
const priv = (await db.query(`select has_table_privilege('authenticated','public.analytics_riepilogo_segnali','select') s,
                                       has_table_privilege('anon','public.analytics_riepilogo_meta','select') m,
                                       has_function_privilege('authenticated','public.refresh_analytics_riepilogo()','execute') ra,
                                       has_function_privilege('anon','public.refresh_analytics_riepilogo()','execute') rn,
                                       has_function_privilege('service_role','public.refresh_analytics_riepilogo()','execute') rs`)).rows[0];
controlla('sicurezza: riepilogo chiuso a anon/authenticated, refresh solo service_role',
  !priv.s && !priv.m && !priv.ra && !priv.rn && priv.rs, JSON.stringify(priv));

console.log(`\n${esiti - falliti}/${esiti} controlli verdi${MUT ? ` (mutazione ${MUT})` : ''}`);
process.exit(falliti ? 1 : 0);
