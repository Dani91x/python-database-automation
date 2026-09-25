// O2 (25/09/2026) -- banco di collaudo della migrazione
// migrations/omega_transitions_catchup_2026-09-25.sql su un PostgreSQL VERO
// (PGlite = PostgreSQL compilato in wasm, in memoria; nessun servizio, nessuna rete).
//
// ORACOLO: il costruttore ORIGINALE (migrations/omega_models_v3.sql + la
// ricostruzione HT->FT di migrations/omega_daily_v2.sql), eseguito DA ZERO su un
// secondo database con gli stessi dati finali. Le tabelle pubblicate dalla
// migrazione nuova devono essere identiche, riga per riga, a quelle dell'oracolo.
//
// Uso (PGlite installato fuori dal repo, es. nello scratchpad):
//   npm install --prefix <DIR> @electric-sql/pglite
//   node AUDIT_2026-09-25/O2_banco_pglite_2026-09-25.mjs <DIR>/node_modules/@electric-sql/pglite/dist/index.js
// Esce con codice 0 se tutti i controlli passano, 1 altrimenti. Stampa numeri.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const QUI = dirname(fileURLToPath(import.meta.url));
const REPO = join(QUI, '..');
const MOD = process.argv[2];
if (!MOD) { console.error('manca il percorso di @electric-sql/pglite (dist/index.js)'); process.exit(2); }
const { PGlite } = await import(pathToFileURL(MOD).href);

const leggi = (p) => readFileSync(join(REPO, p), 'utf8');
const V3 = leggi('migrations/omega_models_v3.sql');
const V2 = leggi('migrations/omega_daily_v2.sql');
const V4 = leggi('migrations/omega_models_v4.sql');
const NUOVA = leggi('migrations/omega_transitions_catchup_2026-09-25.sql');
const tra = (src, da, a) => {
  const i = src.indexOf(da); const j = src.indexOf(a, i);
  if (i < 0 || j < 0) throw new Error(`segmento non trovato: ${da}`);
  return src.slice(i, j + a.length);
};
const V2_HTFT = tra(V2, 'CREATE TABLE IF NOT EXISTS public.omega_ht_ft_transitions',
  'GRANT EXECUTE ON FUNCTION public.get_omega_ht_ft(bigint) TO authenticated, service_role;');
const V4_RPC = tra(V4, 'CREATE OR REPLACE FUNCTION public.get_omega_ht_ft',
  'GRANT EXECUTE ON FUNCTION public.get_omega_minute_ft(bigint,integer,text) TO authenticated, service_role;');

let esiti = 0, falliti = 0;
function controlla(nome, ok, dettaglio = '') {
  esiti++; if (!ok) falliti++;
  console.log(`${ok ? 'OK  ' : 'KO  '} ${nome}${dettaglio ? '  ' + dettaglio : ''}`);
}

// --------------------------------------------------------------------------
// schema minimo con i tipi del vero (matches, match_events) + ruoli Supabase
// --------------------------------------------------------------------------
const BASE = `
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role; END IF;
END $$;
CREATE TABLE public.matches (
  id bigserial PRIMARY KEY,
  fixture_id integer NOT NULL UNIQUE,
  league_id integer,
  season_year integer,
  fixture_date timestamptz,
  status_short text,
  home_team_id integer, away_team_id integer,
  halftime_home integer, halftime_away integer,
  fulltime_home integer, fulltime_away integer,
  raw_json jsonb
);
CREATE TABLE public.match_events (
  id bigserial PRIMARY KEY,
  fixture_id integer NOT NULL,
  team_id integer,
  minute integer,
  event_type text,
  detail text
);
CREATE OR REPLACE FUNCTION public.betfair_live_is_owner() RETURNS boolean LANGUAGE sql AS $$ SELECT true $$;
`;

// --------------------------------------------------------------------------
// generatore deterministico di partite ed eventi
// --------------------------------------------------------------------------
function rng(seme) { let s = seme >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
const R = rng(20260925);
const pick = (arr) => arr[Math.floor(R() * arr.length)];
const LEGHE = [39, 39, 39, 135, 135, 140, 140, 61, 78, 207, 333, null];   // 333 piccola, null = senza lega
let prossimoFixture = 1000000;

function goalsFor(nh, na, home, away) {
  const ev = [];
  for (let k = 0; k < nh; k++) ev.push({ team: home, minute: 1 + Math.floor(R() * 90) });
  for (let k = 0; k < na; k++) ev.push({ team: away, minute: 1 + Math.floor(R() * 90) });
  return ev;
}
// una partita: {row, events}. tipo: 'ft' | 'ns' | 'ft_no_events' | 'aet' | 'ht_null' | 'ft_bad_minute'
function partita(tipo, giorniFa, lega) {
  const fx = prossimoFixture++;
  const home = 1 + Math.floor(R() * 400), away = 401 + Math.floor(R() * 400);
  const league = lega === undefined ? pick(LEGHE) : lega;
  const nh = Math.floor(R() * 4), na = Math.floor(R() * 3);
  const ev = goalsFor(nh, na, home, away);
  const hth = ev.filter(e => e.team === home && e.minute <= 45).length;
  const hta = ev.filter(e => e.team === away && e.minute <= 45).length;
  const date = `now() - interval '${giorniFa} days'`;
  const row = { fixture_id: fx, league_id: league, fixture_date: date, home, away, status: 'FT',
                hth, hta, fth: nh, fta: na };
  let events = ev.map(e => ({ team: e.team, minute: e.minute, type: 'Goal', detail: R() < 0.1 ? 'Own Goal' : 'Normal Goal' }));
  if (R() < 0.3) events.push({ team: home, minute: 1 + Math.floor(R() * 90), type: 'Goal', detail: 'Missed Penalty' });
  if (R() < 0.5) events.push({ team: away, minute: 1 + Math.floor(R() * 90), type: 'Card', detail: 'Yellow Card' });
  if (tipo === 'ns') { row.status = 'NS'; row.hth = row.hta = row.fth = row.fta = null; events = []; }
  if (tipo === 'ft_no_events') { if (nh + na === 0) { row.fth = 1; } events = []; }
  if (tipo === 'aet') row.status = 'AET';
  if (tipo === 'ht_null') { row.hth = null; }
  if (tipo === 'ft_bad_minute' && events.length) { events[0].minute = 95; }
  return { row, events, goals: ev, home, away };
}
const lit = (v) => v === null || v === undefined ? 'NULL' : String(v);
async function inserisci(db, ps) {
  for (const p of ps) {
    const r = p.row;
    const res = await db.query(`INSERT INTO public.matches (fixture_id, league_id, season_year, fixture_date, status_short,
        home_team_id, away_team_id, halftime_home, halftime_away, fulltime_home, fulltime_away)
      VALUES (${r.fixture_id}, ${lit(r.league_id)}, 2026, ${r.fixture_date}, '${r.status}', ${r.home}, ${r.away},
              ${lit(r.hth)}, ${lit(r.hta)}, ${lit(r.fth)}, ${lit(r.fta)}) RETURNING id`);
    p.id = res.rows[0].id;
    for (const e of p.events) {
      await db.query(`INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail)
                      VALUES (${r.fixture_id}, ${e.team}, ${e.minute}, '${e.type}', '${e.detail}')`);
    }
  }
}
// porta a FT una partita NS (id vecchio), con i suoi eventi
async function finisci(db, p, giorniFa, conEventi = true) {
  const nh = p.goals.filter(g => g.team === p.home).length, na = p.goals.filter(g => g.team === p.away).length;
  const hth = p.goals.filter(g => g.team === p.home && g.minute <= 45).length;
  const hta = p.goals.filter(g => g.team === p.away && g.minute <= 45).length;
  await db.query(`UPDATE public.matches SET status_short = 'FT', halftime_home = ${hth}, halftime_away = ${hta},
                  fulltime_home = ${nh}, fulltime_away = ${na}, fixture_date = now() - interval '${giorniFa} days'
                  WHERE fixture_id = ${p.row.fixture_id}`);
  if (conEventi) await aggiungiEventi(db, p);
}
async function aggiungiEventi(db, p) {
  for (const g of p.goals) {
    await db.query(`INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail)
                    VALUES (${p.row.fixture_id}, ${g.team}, ${g.minute}, 'Goal', 'Normal Goal')`);
  }
}
async function aggiungiEventiMancanti(db, p) {
  // la partita FT senza eventi riceve i suoi gol coerenti con il finale registrato
  const r = (await db.query(`SELECT home_team_id h, away_team_id a, fulltime_home fh, fulltime_away fa FROM public.matches WHERE fixture_id = ${p.row.fixture_id}`)).rows[0];
  for (let k = 0; k < r.fh; k++) await db.query(`INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail) VALUES (${p.row.fixture_id}, ${r.h}, ${10 + k}, 'Goal', 'Normal Goal')`);
  for (let k = 0; k < r.fa; k++) await db.query(`INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail) VALUES (${p.row.fixture_id}, ${r.a}, ${50 + k}, 'Goal', 'Normal Goal')`);
}

// copia i dati (matches + events) da un db a un altro, id compresi
async function copiaDati(da, a) {
  const m = (await da.query('SELECT * FROM public.matches ORDER BY id')).rows;
  for (const r of m) {
    await a.query(`INSERT INTO public.matches (id, fixture_id, league_id, season_year, fixture_date, status_short, home_team_id, away_team_id, halftime_home, halftime_away, fulltime_home, fulltime_away)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
      [r.id, r.fixture_id, r.league_id, r.season_year, r.fixture_date, r.status_short, r.home_team_id, r.away_team_id, r.halftime_home, r.halftime_away, r.fulltime_home, r.fulltime_away]);
  }
  const e = (await da.query('SELECT * FROM public.match_events ORDER BY id')).rows;
  for (const r of e) {
    await a.query('INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail) VALUES ($1,$2,$3,$4,$5)',
      [r.fixture_id, r.team_id, r.minute, r.event_type, r.detail]);
  }
}

async function dbConVecchioCostruttore() {
  const db = new PGlite();
  await db.exec(BASE);
  await db.exec(V2_HTFT);
  await db.exec(V3);
  await db.exec(V4_RPC);
  return db;
}
async function costruisciVecchio(db, minLeague) {
  // costruttore originale: passi di 5.000 id finche' done, poi HT->FT totale
  for (let k = 0; k < 1000; k++) {
    const r = (await db.query(`SELECT public.omega_build_minute_transitions_step(5000, ${minLeague}) AS r`)).rows[0].r;
    if (r.done) break;
  }
  await db.query('SELECT public.omega_build_ht_ft_transitions()');
}
async function oracolo(dati, minLeague) {
  const o = await dbConVecchioCostruttore();
  await copiaDati(dati, o);
  await costruisciVecchio(o, minLeague);
  return o;
}
const MIN_Q = 'SELECT league_id, bucket, score, target, result, n FROM public.%T ORDER BY league_id, bucket, target, score, result';
const HT_Q = 'SELECT league_id, ht, ft, n FROM public.%T ORDER BY league_id, ht, ft';
async function righe(db, q, t) { return (await db.query(q.replace('%T', t))).rows.map(r => JSON.stringify(r)); }
async function uguali(nome, dbA, tA, dbB, tB, q) {
  const a = await righe(dbA, q, tA), b = await righe(dbB, q, tB);
  const sa = new Set(a), sb = new Set(b);
  const soloA = a.filter(x => !sb.has(x)).length, soloB = b.filter(x => !sa.has(x)).length;
  controlla(nome, soloA === 0 && soloB === 0 && a.length === b.length,
    `righe ${a.length} vs ${b.length}, solo_prima ${soloA}, solo_seconda ${soloB}`);
}
const uno = async (db, sql) => (await db.query(sql)).rows[0];
const nightly = async (db, args) => (await uno(db, `SELECT public.omega_transitions_nightly(${args}) AS r`)).r;

async function invarianti(db, fase, pubblicata, minLeague) {
  // somma n a bucket 0 target ft per lega = partite nel registro di quella lega
  const q = (t) => `SELECT coalesce(x.league_id, l.league_id) lg, x.s, l.c FROM
      (SELECT league_id, sum(n) s FROM public.${t} WHERE bucket = 0 AND target = 'ft' GROUP BY league_id) x
      FULL JOIN (SELECT coalesce(league_id, 0) league_id, count(*) c FROM public.omega_transitions_ledger WHERE minute_at IS NOT NULL GROUP BY GROUPING SETS ((league_id), ())
                 HAVING league_id IS NOT NULL OR GROUPING(league_id) = 1) l ON l.league_id = x.league_id`;
  const raw = (await db.query(q('omega_minute_transitions_raw'))).rows;
  const diffRaw = raw.filter(r => Number(r.s ?? 0) !== Number(r.c ?? 0));
  controlla(`${fase}: grezzo minuto, somma bucket 0 ft = registro, per lega e globale`, diffRaw.length === 0,
    `leghe ${raw.length}, diverse ${diffRaw.length}`);
  const qh = (t) => `SELECT coalesce(x.league_id, l.league_id) lg, x.s, l.c FROM
      (SELECT league_id, sum(n) s FROM public.${t} GROUP BY league_id) x
      FULL JOIN (SELECT coalesce(league_id, 0) league_id, count(*) c FROM public.omega_transitions_ledger WHERE ht_ft_at IS NOT NULL GROUP BY GROUPING SETS ((league_id), ())
                 HAVING league_id IS NOT NULL OR GROUPING(league_id) = 1) l ON l.league_id = x.league_id`;
  const rawh = (await db.query(qh('omega_ht_ft_transitions_raw'))).rows;
  const diffH = rawh.filter(r => Number(r.s ?? 0) !== Number(r.c ?? 0));
  controlla(`${fase}: grezzo HT-FT, somma n = registro, per lega e globale`, diffH.length === 0,
    `leghe ${rawh.length}, diverse ${diffH.length}`);
  const tlc = (await db.query(`SELECT count(*) c FROM public.omega_transitions_league_counts t
      FULL JOIN (SELECT coalesce(league_id,0) league_id, count(*) FILTER (WHERE minute_at IS NOT NULL) m, count(*) FILTER (WHERE ht_ft_at IS NOT NULL) h
                   FROM public.omega_transitions_ledger GROUP BY GROUPING SETS ((league_id), ()) HAVING league_id IS NOT NULL OR GROUPING(league_id) = 1) l
        ON l.league_id = t.league_id
      WHERE coalesce(t.n_minute,0) <> coalesce(l.m,0) OR coalesce(t.n_ht_ft,0) <> coalesce(l.h,0)`)).rows[0].c;
  controlla(`${fase}: contatori per lega = registro`, Number(tlc) === 0, `diverse ${tlc}`);
  const neg = (await uno(db, `SELECT (SELECT count(*) FROM public.omega_minute_transitions WHERE n <= 0)
      + (SELECT count(*) FROM public.omega_ht_ft_transitions WHERE n <= 0)
      + (SELECT count(*) FROM public.omega_minute_transitions_raw WHERE n <= 0)
      + (SELECT count(*) FROM public.omega_ht_ft_transitions_raw WHERE n <= 0) AS c`)).c;
  controlla(`${fase}: nessuna cella con n <= 0`, Number(neg) === 0, `celle ${neg}`);
  if (pubblicata) {
    const mis = (await uno(db, `SELECT count(*) c FROM public.omega_minute_transitions p
        LEFT JOIN public.omega_minute_transitions_raw r USING (league_id, bucket, target, score, result)
        WHERE r.n IS DISTINCT FROM p.n`)).c;
    controlla(`${fase}: pubblicato minuto = grezzo, cella per cella`, Number(mis) === 0, `celle diverse ${mis}`);
    const mancanti = (await uno(db, `SELECT count(*) c FROM public.omega_minute_transitions_raw r
        WHERE (r.league_id = 0 OR r.league_id IN (SELECT league_id FROM public.omega_transitions_league_counts WHERE n_minute >= ${minLeague}))
          AND NOT EXISTS (SELECT 1 FROM public.omega_minute_transitions p WHERE (p.league_id, p.bucket, p.target, p.score, p.result) = (r.league_id, r.bucket, r.target, r.score, r.result))`)).c;
    controlla(`${fase}: nessuna cella ammessa mancante nel pubblicato`, Number(mancanti) === 0, `mancanti ${mancanti}`);
    const nonAmm = (await uno(db, `SELECT count(DISTINCT league_id) c FROM public.omega_minute_transitions p
        WHERE p.league_id <> 0 AND NOT EXISTS (SELECT 1 FROM public.omega_transitions_league_counts c WHERE c.league_id = p.league_id AND c.n_minute >= ${minLeague})`)).c;
    controlla(`${fase}: nessuna lega sotto soglia nel pubblicato`, Number(nonAmm) === 0, `leghe ${nonAmm}`);
    const misH = (await uno(db, `SELECT count(*) c FROM public.omega_ht_ft_transitions_raw r
        FULL JOIN public.omega_ht_ft_transitions p USING (league_id, ht, ft) WHERE r.n IS DISTINCT FROM p.n`)).c;
    controlla(`${fase}: pubblicato HT-FT = grezzo`, Number(misH) === 0, `celle diverse ${misH}`);
  }
}

// ==========================================================================
// SCENARIO
// ==========================================================================
const MINL = 60;   // soglia leghe ridotta per i dati del banco (in produzione 1000)
const A = await dbConVecchioCostruttore();

// 1. dati "all'11/09": FT vecchie, NS future (entrate prima di finire), casi limite
const iniziali = [];
for (let k = 0; k < 900; k++) iniziali.push(partita('ft', 30 + Math.floor(R() * 300)));
for (let k = 0; k < 40; k++) iniziali.push(partita('ft', 60, 444));           // lega piccola: sotto soglia (40 < 60)
const nsRecenti = []; for (let k = 0; k < 60; k++) nsRecenti.push(partita('ns', 0));
const nsVecchie = []; for (let k = 0; k < 10; k++) nsVecchie.push(partita('ns', 0));
const senzaEventi = []; for (let k = 0; k < 25; k++) senzaEventi.push(partita('ft_no_events', 40));
for (let k = 0; k < 15; k++) iniziali.push(partita('aet', 50));
for (let k = 0; k < 15; k++) iniziali.push(partita('ht_null', 50));
for (let k = 0; k < 10; k++) iniziali.push(partita('ft_bad_minute', 50));
// ordine di inserimento mescolato: id vecchi per le NS
const tutte = [...iniziali, ...nsRecenti, ...nsVecchie, ...senzaEventi].sort(() => R() - 0.5);
await inserisci(A, tutte);
await costruisciVecchio(A, MINL);
const vecchioMin = await righe(A, MIN_Q, 'omega_minute_transitions');
const vecchioHt = await righe(A, HT_Q, 'omega_ht_ft_transitions');
console.log(`dati 11/09: matches ${tutte.length}, righe minuto ${vecchioMin.length}, righe HT-FT ${vecchioHt.length}`);

// 2. dopo l'11/09: NS che finiscono (id vecchi), partite nuove, eventi tardivi
for (const p of nsRecenti.slice(0, 40)) await finisci(A, p, 2);              // finestra calda
for (const p of nsVecchie) await finisci(A, p, 45);                           // fuori finestra: le prende il giro di controllo
for (const p of senzaEventi.slice(0, 10)) await aggiungiEventiMancanti(A, p); // eventi arrivati dopo
const nuove = []; for (let k = 0; k < 120; k++) nuove.push(partita('ft', 1 + Math.floor(R() * 5)));
await inserisci(A, nuove);
await A.exec(`CREATE INDEX idx_matches_fixture_date_settled ON public.matches (fixture_date) WHERE status_short IN ('FT','AET','PEN')`);

// 3. la migrazione (due volte: idempotente)
await A.exec(NUOVA);
await A.exec(NUOVA);
await uguali('dopo la migrazione i bot leggono ancora i numeri dell\'11/09 (minuto)', A, 'omega_minute_transitions', A, 'omega_minute_transitions', MIN_Q);
controlla('tabella minuto pubblicata invariata dopo la migrazione',
  JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions')) === JSON.stringify(vecchioMin));
controlla('tabella HT-FT pubblicata invariata dopo la migrazione',
  JSON.stringify(await righe(A, HT_Q, 'omega_ht_ft_transitions')) === JSON.stringify(vecchioHt));
const sch = (await uno(A, 'SELECT public.omega_transitions_schedule(true) AS r')).r;
controlla('senza pg_cron la schedulazione lo dice e non fallisce', sch.startsWith('pg_cron non attivo'), sch);

// 4. i vecchi costruttori rifiutano
for (const f of ['omega_build_minute_transitions_reset()', 'omega_build_minute_transitions_step(5000,1000)',
                 'omega_build_minute_transitions_run(90,5000)', 'omega_build_minute_transitions_schedule()',
                 'omega_build_ht_ft_transitions()']) {
  let err = '';
  try { await A.query(`SELECT public.${f}`); } catch (e) { err = String(e.message || e); }
  controlla(`vecchio costruttore ${f} rifiuta`, err.includes('dismessa'), err.slice(0, 60));
}

// 5. dry-run: stessi numeri, niente scritto
const dr = await nightly(A, '600, true');
const dopoDr = await uno(A, `SELECT (SELECT count(*) FROM public.omega_transitions_ledger) l,
   (SELECT count(*) FROM public.omega_minute_transitions_raw) r, (SELECT id_cursor FROM public.omega_transitions_state) c`);
controlla('dry-run: conta ma non scrive (registro, grezzo, cursore)', dr.status === 'dry_run' && dr.minute_counted > 0
  && Number(dopoDr.l) === 0 && Number(dopoDr.r) === 0 && Number(dopoDr.c) === 0,
  `contate ${dr.minute_counted}/${dr.ht_ft_counted}, registro ${dopoDr.l}, grezzo ${dopoDr.r}, cursore ${dopoDr.c}`);
const runDr = await uno(A, 'SELECT status, dry_run, minute_counted FROM public.omega_transitions_runs ORDER BY id DESC LIMIT 1');
controlla('dry-run: resta la riga di referto', runDr.status === 'dry_run' && runDr.dry_run === true
  && Number(runDr.minute_counted) === dr.minute_counted);

// 6. budget esaurito: nessun passo, stato 'budget', nulla perso
const b0 = await nightly(A, '0');
controlla('budget 0: nessun passo, stato budget', b0.status === 'budget' && b0.steps === 0, JSON.stringify({ s: b0.status, p: b0.steps }));

// 7. ricostruzione vera
const r1 = await nightly(A, '600');
controlla('ricostruzione: finita in un giro sui dati del banco', r1.status === 'ok' && r1.bootstrap_done === true,
  `passi ${r1.steps}, esaminate ${r1.scanned}, minuto ${r1.minute_counted}, HT-FT ${r1.ht_ft_counted}, scartate ${r1.minute_rejected}, calde ${r1.hot_candidates}`);
controlla('ricostruzione: i bot leggono ancora l\'11/09 (non pubblicato)',
  JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions')) === JSON.stringify(vecchioMin)
  && JSON.stringify(await righe(A, HT_Q, 'omega_ht_ft_transitions')) === JSON.stringify(vecchioHt));
await invarianti(A, 'dopo la ricostruzione', false, MINL);
const r2 = await nightly(A, '600');
controlla('secondo giro subito dopo: zero partite contate', r2.minute_counted === 0 && r2.ht_ft_counted === 0,
  `minuto ${r2.minute_counted}, HT-FT ${r2.ht_ft_counted}, riesaminate ${r2.scanned}`);
// cursori riportati a zero: si ripassa TUTTO, il registro impedisce il doppio conteggio
const grezzoPrima = await righe(A, MIN_Q, 'omega_minute_transitions_raw');
await A.exec('UPDATE public.omega_transitions_state SET id_cursor = 0, sweep_cursor = 0');
const r3 = await nightly(A, '600');
controlla('ripassata completa da capo: n invariato (registro)', r3.minute_counted === 0 && r3.ht_ft_counted === 0
  && JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions_raw')) === JSON.stringify(grezzoPrima),
  `minuto ${r3.minute_counted}, HT-FT ${r3.ht_ft_counted}`);

// 8. oracolo: grezzo = costruttore originale da zero senza potatura (soglia 1)
const O1 = await oracolo(A, 1);
await uguali('grezzo minuto = costruttore originale da zero (tutte le leghe)', A, 'omega_minute_transitions_raw', O1, 'omega_minute_transitions', MIN_Q);
await uguali('grezzo HT-FT = ricostruzione originale da zero', A, 'omega_ht_ft_transitions_raw', O1, 'omega_ht_ft_transitions', HT_Q);

// 9. confronto prima di pubblicare
const cmp = (await uno(A, `SELECT public.omega_transitions_compare('pre', ${MINL}) AS r`)).r;
controlla('confronto pre: nessuna cella scesa o sparita, partite globali cresciute',
  cmp.minute.cells_lower === 0 && cmp.minute.cells_missing === 0 && cmp.ht_ft.cells_lower === 0 && cmp.ht_ft.cells_missing === 0
  && cmp.minute.matches_global_new > cmp.minute.matches_global_old,
  JSON.stringify(cmp.minute));

// 10. pubblicazione
let errPub = '';
try { await A.query(`SELECT public.omega_transitions_publish('si')`); } catch (e) { errPub = String(e.message); }
controlla('pubblicazione senza conferma rifiutata', errPub.includes('conferma mancante'));
const pub = (await uno(A, `SELECT public.omega_transitions_publish('PUBBLICA', ${MINL}) AS r`)).r;
controlla('pubblicazione fatta con copia dell\'11/09', pub.published === true && pub.backup_created === true, JSON.stringify(pub));
const O2 = await oracolo(A, MINL);
await uguali('pubblicato minuto = costruttore originale da zero (soglia uguale)', A, 'omega_minute_transitions', O2, 'omega_minute_transitions', MIN_Q);
await uguali('pubblicato HT-FT = ricostruzione originale da zero', A, 'omega_ht_ft_transitions', O2, 'omega_ht_ft_transitions', HT_Q);
await uguali('conteggi per lega pubblicati = originale', A, 'omega_minute_league_counts', O2, 'omega_minute_league_counts',
  'SELECT league_id, n FROM public.%T ORDER BY league_id');
// le RPC lette dai bot rispondono uguale all'oracolo
for (const [lg, bk, tg] of [[39, 0, 'ft'], [135, 45, 'ft'], [140, 30, 'ht'], [333, 60, 'ft'], [null, 70, 'ft']]) {
  const a = (await uno(A, `SELECT public.get_omega_minute_ft(${lit(lg)}, ${bk}, '${tg}') r`)).r;
  const o = (await uno(O2, `SELECT public.get_omega_minute_ft(${lit(lg)}, ${bk}, '${tg}') r`)).r;
  const norm = (x) => JSON.stringify(x.map(r => JSON.stringify(r)).sort());
  controlla(`RPC get_omega_minute_ft(${lg},${bk},${tg}) = originale`, norm(a) === norm(o), `righe ${a.length}`);
}
for (const lg of [39, 207, null]) {
  const a = (await uno(A, `SELECT public.get_omega_ht_ft(${lit(lg)}) r`)).r;
  const o = (await uno(O2, `SELECT public.get_omega_ht_ft(${lit(lg)}) r`)).r;
  const norm = (x) => JSON.stringify(x.map(r => JSON.stringify(r)).sort());
  controlla(`RPC get_omega_ht_ft(${lg}) = originale`, norm(a) === norm(o), `righe ${a.length}`);
}
await invarianti(A, 'dopo la pubblicazione', true, MINL);
const cmpPost = (await uno(A, `SELECT public.omega_transitions_compare('post') AS r`)).r;
controlla('confronto post (copia 11/09 contro pubblicato): nessuna cella scesa', cmpPost.minute.cells_lower === 0 && cmpPost.ht_ft.cells_lower === 0,
  JSON.stringify(cmpPost.minute));

// 11. notti successive: nuove FT, lega piccola che supera la soglia, eventi tardivi, FT fuori finestra
const nuove2 = []; for (let k = 0; k < 60; k++) nuove2.push(partita('ft', 1));
for (let k = 0; k < 30; k++) nuove2.push(partita('ft', 1, 444));              // 444: da 40 a 70 >= 60
await inserisci(A, nuove2);
for (const p of nsRecenti.slice(40)) await finisci(A, p, 1);
for (const p of senzaEventi.slice(10, 20)) await aggiungiEventiMancanti(A, p);
const r4 = await nightly(A, '600');
controlla('notte dopo la pubblicazione: contate le nuove', r4.minute_counted > 0 && r4.published === true,
  `minuto ${r4.minute_counted}, HT-FT ${r4.ht_ft_counted}, leghe nuove ${r4.new_leagues}, righe pubblicate ${r4.live_minute_upserts}`);
controlla('lega che supera la soglia: pubblicata per intero', r4.new_leagues === 1, `leghe nuove ${r4.new_leagues}`);
await invarianti(A, 'notte 2', true, MINL);
const r5 = await nightly(A, '600');
controlla('rilancio immediato: zero variazioni', r5.minute_counted === 0 && r5.ht_ft_counted === 0 && r5.live_minute_upserts === 0,
  `minuto ${r5.minute_counted}, HT-FT ${r5.ht_ft_counted}, pubblicate ${r5.live_minute_upserts}`);
// il giorno dopo: le scartate si ritentano (finestra calda) -> retry simulato spostando l'orologio del registro
await A.exec(`UPDATE public.omega_transitions_ledger SET minute_checked_at = minute_checked_at - interval '1 day' WHERE minute_at IS NULL`);
for (const p of senzaEventi.slice(20)) await aggiungiEventiMancanti(A, p);
const r6 = await nightly(A, '600');
controlla('scartate ritentate il giorno dopo (eventi arrivati)', r6.minute_counted >= 5, `minuto ${r6.minute_counted}, scartate ancora ${r6.minute_rejected}`);
await invarianti(A, 'notte 3', true, MINL);
const O3 = await oracolo(A, MINL);
await uguali('notte 3: pubblicato minuto = originale da zero', A, 'omega_minute_transitions', O3, 'omega_minute_transitions', MIN_Q);
await uguali('notte 3: pubblicato HT-FT = originale da zero', A, 'omega_ht_ft_transitions', O3, 'omega_ht_ft_transitions', HT_Q);
await uguali('notte 3: conteggi per lega = originale', A, 'omega_minute_league_counts', O3, 'omega_minute_league_counts',
  'SELECT league_id, n FROM public.%T ORDER BY league_id');
const O3r = await oracolo(A, 1);
await uguali('notte 3: grezzo minuto = originale senza potatura', A, 'omega_minute_transitions_raw', O3r, 'omega_minute_transitions', MIN_Q);

// 12. dry-run a pubblicazione fatta: niente cambia
const primaDr = await righe(A, MIN_Q, 'omega_minute_transitions');
const nuove3 = []; for (let k = 0; k < 20; k++) nuove3.push(partita('ft', 1));
await inserisci(A, nuove3);
const dr2 = await nightly(A, '600, true');
controlla('dry-run dopo la pubblicazione: pubblicato invariato', dr2.status === 'dry_run' && dr2.minute_counted > 0
  && JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions')) === JSON.stringify(primaDr), `avrebbe contato ${dr2.minute_counted}`);
await nightly(A, '600');

// 13. senza indice su fixture_date: finestra calda saltata e dichiarata; il giro di controllo recupera
await A.exec('DROP INDEX public.idx_matches_fixture_date_settled');
const vecchiaNs = partita('ns', 0); await inserisci(A, [vecchiaNs]);
await nightly(A, '600');                                  // la NS passa dal cursore: non FT, non contata
await finisci(A, vecchiaNs, 1);
const r7 = await nightly(A, '600, false, 5000, 10, 1000000000');
controlla('senza indice: finestra calda saltata e scritta nel referto', r7.hot_skipped_no_index === true);
controlla('senza indice: la partita finita dopo la presa dal giro di controllo', r7.minute_counted + r7.minute_rejected >= 1,
  `minuto ${r7.minute_counted}, scartate ${r7.minute_rejected}, giro ${r7.sweep_from}->${r7.sweep_to}`);
await invarianti(A, 'senza indice', true, MINL);

// 14. ritorno ai numeri dell'11/09 e ripubblicazione
const un = (await uno(A, `SELECT public.omega_transitions_unpublish('RITORNA') AS r`)).r;
controlla('ritorno: tabelle pubblicate = copia dell\'11/09',
  un.published === false && JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions')) === JSON.stringify(vecchioMin)
  && JSON.stringify(await righe(A, HT_Q, 'omega_ht_ft_transitions')) === JSON.stringify(vecchioHt));
const rU = await nightly(A, '600');
controlla('a pubblicazione ritirata il giro non tocca le tabelle dei bot',
  JSON.stringify(await righe(A, MIN_Q, 'omega_minute_transitions')) === JSON.stringify(vecchioMin), `pubblicate ${rU.live_minute_upserts}`);
await uno(A, `SELECT public.omega_transitions_publish('PUBBLICA', ${MINL}) AS r`);
const O4 = await oracolo(A, MINL);
await uguali('ripubblicazione = originale da zero', A, 'omega_minute_transitions', O4, 'omega_minute_transitions', MIN_Q);

// 15. pg_cron finto (schema cron come quello vero) e pg_extension: schedulazione idempotente
await A.exec(`CREATE SCHEMA cron;
  CREATE TABLE cron.job (jobid bigserial PRIMARY KEY, schedule text, command text, jobname text UNIQUE, active boolean DEFAULT true);
  CREATE TABLE cron.job_run_details (jobid bigint, runid bigserial, status text, start_time timestamptz, end_time timestamptz, return_message text);
  CREATE FUNCTION cron.schedule(job_name text, schedule text, command text) RETURNS bigint LANGUAGE sql AS
    $$ INSERT INTO cron.job (schedule, command, jobname) VALUES (schedule, command, job_name) RETURNING jobid $$;
  CREATE FUNCTION cron.unschedule(job_name text) RETURNS boolean LANGUAGE plpgsql AS
    $$ BEGIN DELETE FROM cron.job WHERE jobname = job_name; IF NOT FOUND THEN RAISE EXCEPTION 'could not find valid entry for job ''%''', job_name; END IF; RETURN true; END $$;
  INSERT INTO cron.job (schedule, command, jobname) VALUES ('* * * * *', 'SELECT public.omega_build_minute_transitions_run(50);', 'omega_minute_build');`);
let finta = true;
try { await A.exec(`INSERT INTO pg_extension (oid, extname, extowner, extnamespace, extrelocatable, extversion) VALUES (999999, 'pg_cron', 10, 11, false, '1.6')`); }
catch (e) { finta = false; console.log('     (pg_extension non scrivibile in PGlite: schedulazione provata solo sul ramo senza pg_cron)', String(e.message).slice(0, 80)); }
if (finta) {
  await A.exec(NUOVA);                                     // la migrazione rilanciata schedula
  await uno(A, 'SELECT public.omega_transitions_schedule(true) AS r');
  const jobs = (await A.query(`SELECT jobname, schedule, command FROM cron.job ORDER BY jobname`)).rows;
  controlla('pg_cron: un solo job, alle 04:00 UTC, vecchio job tolto',
    jobs.length === 1 && jobs[0].jobname === 'omega_transitions_nightly' && jobs[0].schedule === '0 4 * * *'
    && jobs[0].command.includes('omega_transitions_nightly(600)') && jobs[0].command.includes('statement_timeout'),
    JSON.stringify(jobs));
  const st = (await uno(A, 'SELECT public.omega_transitions_status() AS r')).r;
  controlla('stato: pg_cron e job visibili', st.pg_cron === true && st.cron_jobs.length === 1, JSON.stringify(st.cron_jobs));
  const off = (await uno(A, 'SELECT public.omega_transitions_schedule(false) AS r')).r;
  const nj = (await uno(A, 'SELECT count(*) c FROM cron.job')).c;
  controlla('pg_cron: spegnimento', Number(nj) === 0, off);
}

// 16. stato e conteggi per la verifica (chiavi reali, stampate per lo script Python)
const st = (await uno(A, 'SELECT public.omega_transitions_status() AS r')).r;
console.log('chiavi status:', Object.keys(st).sort().join(','));
console.log('chiavi state:', Object.keys(st.state).sort().join(','));
console.log('chiavi run:', Object.keys(st.runs[0]).sort().join(','));
const lc = (await uno(A, 'SELECT public.omega_transitions_ledger_counts() AS r')).r;
console.log('chiavi ledger_counts:', Object.keys(lc[0]).sort().join(','), 'righe', lc.length);
console.log('chiavi compare:', Object.keys(cmp).sort().join(','), '|', Object.keys(cmp.minute).sort().join(','));

console.log(`\nCONTROLLI: ${esiti}, falliti: ${falliti}`);
process.exit(falliti === 0 ? 0 : 1);
