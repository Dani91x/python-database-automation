// O2 (25/09/2026) -- costo RELATIVO della ricostruzione nuova rispetto al
// costruttore originale (omega_models_v3.sql), sugli STESSI dati sintetici, in
// PGlite (PostgreSQL in wasm). Il tempo assoluto del wasm non vale per Supabase;
// il RAPPORTO nuovo/vecchio si applica ai 27 minuti misurati l'11/09 sul DB vero.
// Uso: node AUDIT_2026-09-25/O2_misura_costo_pglite_2026-09-25.mjs <pglite dist/index.js> [N partite]
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..');
const { PGlite } = await import(pathToFileURL(process.argv[2]).href);
const N = Number(process.argv[3] || 40000);
const leggi = (p) => readFileSync(join(REPO, p), 'utf8');
const V2 = leggi('migrations/omega_daily_v2.sql');
const tra = (s, a, b) => s.slice(s.indexOf(a), s.indexOf(b, s.indexOf(a)) + b.length);
const V2_HTFT = tra(V2, 'CREATE TABLE IF NOT EXISTS public.omega_ht_ft_transitions',
  'GRANT EXECUTE ON FUNCTION public.get_omega_ht_ft(bigint) TO authenticated, service_role;');

const BASE = `
CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
CREATE TABLE public.matches (id bigserial PRIMARY KEY, fixture_id integer NOT NULL UNIQUE, league_id integer,
  season_year integer, fixture_date timestamptz, status_short text, home_team_id integer, away_team_id integer,
  halftime_home integer, halftime_away integer, fulltime_home integer, fulltime_away integer);
CREATE TABLE public.match_events (id bigserial PRIMARY KEY, fixture_id integer NOT NULL, team_id integer,
  minute integer, event_type text, detail text);
CREATE OR REPLACE FUNCTION public.betfair_live_is_owner() RETURNS boolean LANGUAGE sql AS $$ SELECT true $$;
CREATE TEMP TABLE gen AS SELECT g, (g % 4) AS fh, ((g / 7) % 3) AS fa FROM generate_series(1, ${N}) g;
INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail)
SELECT 1000000 + g, CASE WHEN k <= fh THEN g % 400 + 1 ELSE 400 + g % 400 + 1 END,
       1 + ((g * 31 + k * 17) % 90), 'Goal', 'Normal Goal'
  FROM gen, generate_series(1, fh + fa) k
 WHERE g % 13 <> 0;                                   -- 1 su 13 senza eventi: scartata
INSERT INTO public.match_events (fixture_id, team_id, minute, event_type, detail)
SELECT 1000000 + g, g % 400 + 1, 30, 'Card', 'Yellow Card' FROM gen;
INSERT INTO public.matches (fixture_id, league_id, season_year, fixture_date, status_short, home_team_id, away_team_id,
                            halftime_home, halftime_away, fulltime_home, fulltime_away)
SELECT 1000000 + g, (ARRAY[39,135,140,61,78,207,333,444])[1 + g % 8], 2025, now() - (g % 400) * interval '1 day',
       CASE WHEN g % 10 = 0 THEN 'NS' ELSE 'FT' END, g % 400 + 1, 400 + g % 400 + 1,
       coalesce(h.hh, 0), coalesce(h.ha, 0), fh, fa
  FROM gen
  LEFT JOIN (SELECT e.fixture_id,
                    count(*) FILTER (WHERE e.team_id <= 400 AND e.minute <= 45) AS hh,
                    count(*) FILTER (WHERE e.team_id > 400 AND e.minute <= 45) AS ha
               FROM public.match_events e WHERE e.event_type = 'Goal' GROUP BY e.fixture_id) h
    ON h.fixture_id = 1000000 + g;
CREATE INDEX idx_matches_fixture_date_settled ON public.matches (fixture_date) WHERE status_short IN ('FT','AET','PEN');
`;
async function nuovoDb() {
  const db = new PGlite();
  await db.exec(BASE);
  await db.exec(V2_HTFT);
  await db.exec(leggi('migrations/omega_models_v3.sql'));
  await db.exec('ANALYZE');
  return db;
}
const t = () => performance.now();

const vecchio = await nuovoDb();
let t0 = t();
for (let k = 0; k < 10000; k++) {
  const r = (await vecchio.query('SELECT public.omega_build_minute_transitions_step(5000, 1000) AS r')).rows[0].r;
  if (r.done) break;
}
const tMinOld = t() - t0;
t0 = t();
await vecchio.query('SELECT public.omega_build_ht_ft_transitions()');
const tHtOld = t() - t0;

const nuovo = await nuovoDb();
await nuovo.exec(leggi('migrations/omega_transitions_catchup_2026-09-25.sql'));
t0 = t();
const r = (await nuovo.query('SELECT public.omega_transitions_nightly(36000) AS r')).rows[0].r;
const tNew = t() - t0;
const ok = (await nuovo.query(`SELECT count(*) c FROM public.omega_minute_transitions_raw r
   FULL JOIN (SELECT * FROM public.omega_minute_transitions) o USING (league_id,bucket,target,score,result)
   WHERE r.n IS DISTINCT FROM o.n`)).rows[0].c;   // pubblicato vuoto qui: = righe del grezzo
const diff = (await vecchio.query('SELECT count(*) c FROM public.omega_minute_transitions')).rows[0].c;
console.log(JSON.stringify({ partite: N, vecchio_minuto_ms: Math.round(tMinOld), vecchio_htft_ms: Math.round(tHtOld),
  nuovo_bootstrap_ms: Math.round(tNew), rapporto_nuovo_su_vecchio: +(tNew / (tMinOld + tHtOld)).toFixed(2),
  nuovo: { passi: r.steps, esaminate: r.scanned, minuto: r.minute_counted, htft: r.ht_ft_counted, scartate: r.minute_rejected },
  righe_vecchio_minuto: Number(diff), righe_grezzo_nuovo: Number(ok) }));
