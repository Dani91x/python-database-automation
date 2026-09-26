// FIX-A (26/09/2026) - banco delle tre migrazioni su PostgreSQL VERO (PGlite,
// in memoria: nessun servizio, nessuna rete, nessun contatto col DB vero).
//
// Per ogni reperto il banco carica PRIMA i corpi VIVI (gli stessi file il cui
// md5 coincide con pg_proc, vedi referto) e controlla che il difetto si veda
// (ROSSO), poi applica la migrazione nuova e controlla che sparisca (VERDE),
// piu' l'equivalenza per chi legge le funzioni oggi (servizio Omega).
// Righe di prova: colonne e tipi di information_schema; le righe di Mike 527,
// 528, 555, 4762, 4768 e le posizioni/regolazioni 14265, 14291, 18 sono copiate
// dal DB (sola lettura, 26/09).
//
// Uso (PGlite installato FUORI dal repo, es. nello scratchpad):
//   npm install --prefix <DIR> @electric-sql/pglite
//   node AUDIT_2026-09-25/fix_a_soldi/banco_sql_pglite.mjs <DIR>/node_modules/@electric-sql/pglite/dist/index.js
// Esce 0 se: ogni controllo del difetto e' ROSSO sui corpi vivi e VERDE dopo.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const MOD = process.argv[2];
if (!MOD) { console.error('manca il percorso di @electric-sql/pglite (dist/index.js)'); process.exit(2); }
const { PGlite } = await import(pathToFileURL(MOD).href);
const leggi = (p) => readFileSync(join(REPO, p), 'utf8').replace(/\r/g, '');
const tra = (src, da, a) => {
  const i = src.indexOf(da); const j = src.indexOf(a, i);
  if (i < 0 || j < 0) throw new Error(`segmento non trovato: ${da.slice(0, 60)}`);
  return src.slice(i, j + a.length);
};

// ---- corpi VIVI (prima) ----------------------------------------------------
const VIVO_STORICO = tra(leggi('migrations/mike_history_v2.sql'),
  'CREATE OR REPLACE FUNCTION public.trading_daily_history(',
  'GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;');
const OMEGA16 = leggi('migrations/omega_chiuso_dall_utente_2026-09-16.sql');
const VIVO_OMEGA_AGG = tra(OMEGA16, 'CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)',
  'GRANT EXECUTE ON FUNCTION public.get_omega_aggregates() TO authenticated, service_role;');
const VIVO_OMEGA_STATE = tra(leggi('migrations/omega_models_v5.sql'),
  'CREATE OR REPLACE FUNCTION public.get_omega_state(',
  'GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;');
const VIVO_POS = tra(leggi('migrations/betfair_live_pnl_journal.sql'),
  'CREATE OR REPLACE FUNCTION public.get_live_positions_all()', '$$;');

// ---- migrazioni NUOVE (dopo) -----------------------------------------------
const NUOVA_STORICO = leggi('migrations/storico_esito_a_zero_2026-09-26.sql');
const NUOVA_OMEGA = leggi('migrations/omega_state_per_modalita_2026-09-26.sql');
const NUOVA_POS = leggi('migrations/live_positions_senza_mercati_regolati_2026-09-26.sql');

const BASE = `
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role; END IF;
END $$;
CREATE FUNCTION public.betfair_live_is_owner() RETURNS boolean LANGUAGE sql AS $$ SELECT true $$;
CREATE TABLE public.mike_trades (id bigint PRIMARY KEY, event_id text, event_name text, sport text,
  strategy text, role text, cycle_no integer, persistence text, market_id text, market_type text,
  selection_id bigint, selection_name text, side text, mode text, price numeric, size numeric,
  liability numeric, commission numeric, minute_at_entry integer, score_at_entry text, status text,
  pnl numeric, bet_id text, placed_at timestamptz, settled_at timestamptz, origin text,
  closes_trade_id bigint, signal_key text, meta jsonb);
CREATE TABLE public.omega_trades (id bigint PRIMARY KEY, event_id text, event_name text, market_id text,
  selection_id bigint, runner_name text, side text, mode text, price numeric, size numeric,
  liability numeric, commission numeric, target numeric, minute_at_entry integer, score_at_entry text,
  kickoff timestamptz, status text, pnl numeric, bet_id text, placed_at timestamptz,
  settled_at timestamptz, meta jsonb, origin text, phase text, closes_trade_id bigint);
CREATE TABLE public.safe_strategy_trades (id bigint PRIMARY KEY);
CREATE TABLE public.omega_control (id integer PRIMARY KEY, status text, mode text, daily_goal numeric,
  params jsonb, stats jsonb, error text, started_at timestamptz, stopped_at timestamptz,
  heartbeat_at timestamptz, updated_at timestamptz, created_at timestamptz);
CREATE TABLE public.omega_activity (id bigint PRIMARY KEY, ts timestamptz, kind text, payload jsonb);
CREATE TABLE public.omega_daily_goal (day date PRIMARY KEY, goal numeric, updated_at timestamptz);
CREATE TABLE public.betfair_live_positions (id bigint PRIMARY KEY, mode text, event_id text,
  market_id text, selection_id bigint, handicap numeric, matched_if_win numeric,
  matched_if_lose numeric, worst_if_win numeric, worst_if_lose numeric, selection_exposure numeric,
  unmatched_back_exposure numeric, unmatched_lay_exposure numeric, net_position numeric,
  updated_at timestamptz);
CREATE TABLE public.betfair_live_settled (id bigint PRIMARY KEY, mode text, event_id text,
  market_id text, market_name text, profit numeric, orders integer, source text,
  settled_at timestamptz, updated_at timestamptz);
`;

// righe VERE (Mike 12-15/09) + una vinta e una persa per il contorno
const DATI = `
INSERT INTO public.mike_trades (id,event_id,strategy,role,market_id,side,mode,price,size,liability,commission,status,pnl,bet_id,placed_at,settled_at,origin,closes_trade_id,meta) VALUES
 (527,'36053366','under_entry','under_entry','1.262255589','back','paper',1.51,10.0,10.0,0.05,'won',5.1,NULL,'2026-09-12 18:31:26.084636+00','2026-09-12 21:01:06.737701+00','auto',NULL,'{"fill":"paper_fill:execution_mode_rest","phase":"open","pnl_gross":5.1,"commission_paid":0}'),
 (528,'36053366','under_green','under_green','1.262255589','lay','paper',1.49,10.13,4.96,0.05,'error',0.0,NULL,'2026-09-12 18:31:29.951752+00',NULL,'auto',527,'{"phase":"cancelled","reason":"cancelled_by_engine"}'),
 (555,'36053366','under_close','under_close','1.262255589','lay','paper',1.51,10.0,5.1,0.05,'lost',-5.1,NULL,'2026-09-12 20:28:46.915168+00','2026-09-12 21:01:06.737701+00','auto',527,'{"fill":"paper_fill:execution_mode_rest","phase":"open","pnl_gross":-5.1,"commission_paid":0}'),
 (4762,'36046449','under_entry','under_entry','1.262258585','back','paper',1.49,10.0,10.0,0.05,'won',4.77,NULL,'2026-09-14 22:47:22.079624+00','2026-09-15 06:58:55.013797+00','auto',NULL,'{"fill":"paper_fill:execution_mode_rest","phase":"open","pnl_gross":4.9,"commission_paid":0.13}'),
 (4768,'36046449','under_green','under_green','1.262258585','lay','paper',1.47,10.14,4.77,0.05,'lost',-4.77,NULL,'2026-09-14 22:47:26.571789+00','2026-09-15 06:58:55.013797+00','auto',4762,'{"fill":"paper_resting","phase":"open","pnl_gross":-4.77,"commission_paid":0}'),
 (9001,'e-v','under_entry','under_entry','1.9','back','paper',1.6,5.0,5.0,0.05,'won',2.85,NULL,'2026-09-14 12:00:00+00','2026-09-14 14:00:00+00','auto',NULL,'{}'),
 (9002,'e-p','under_entry','under_entry','1.8','back','paper',1.6,5.0,5.0,0.05,'lost',-5.0,NULL,'2026-09-14 12:00:00+00','2026-09-14 14:00:00+00','auto',NULL,'{}'),
 (9003,'e-d','under_entry','under_entry','1.7','back','paper',1.6,5.0,5.0,0.05,'void',0.0,NULL,'2026-09-14 12:00:00+00','2026-09-14 14:00:00+00','auto',NULL,'{}');

INSERT INTO public.omega_control (id,status,mode,daily_goal) VALUES (1,'running','paper',100);
-- Omega: evento A due gambe paper (1T+2T), evento B una gamba paper, evento C una gamba LIVE vinta
INSERT INTO public.omega_trades (id,event_id,market_id,selection_id,side,mode,price,size,liability,status,pnl,bet_id,placed_at,settled_at,meta,origin,phase,closes_trade_id) VALUES
 (1,'A','m-a-ht',3,'lay','paper',48,1,47,'won',0.95,NULL,now() - interval '3 days',now() - interval '3 days','{}','auto','ht_cs',NULL),
 (2,'A','m-a-ft',4,'lay','paper',80,1,79,'lost',-79,NULL,now() - interval '3 days',now() - interval '3 days','{}','auto','ft_cs',NULL),
 (3,'B','m-b-ft',4,'lay','paper',55,1,54,'open',0,'b3',now(),NULL,'{"flumine_client_ref":"x"}','auto','ft_cs',NULL),
 (4,'C','m-c-ft',4,'lay','live',30,2,58,'won',1.9,'b4',now() - interval '1 day',now() - interval '1 day','{}','auto','ft_cs',NULL),
 (5,'C','m-c-ft',4,'back','live',20,1,1,'won',-0.5,'b5',now() - interval '1 day',now() - interval '1 day','{}','manual',NULL,4);

INSERT INTO public.betfair_live_positions VALUES
 (14265,'live','35797769','1.259819675',5851482,0,-4.4,5.0,-4.4,5.0,4.4,0,0,-5.0,'2026-07-10 19:29:57.79521+00'),
 (14291,'paper','36091663','1.262661065',1,0,-47.0,1.0,-47.0,1.0,47.0,0,0,-1.0,'2026-09-26 15:28:03.542233+00');
INSERT INTO public.betfair_live_settled VALUES
 (18,'live','35797769','1.259819675',NULL,105,2,'cleared','2026-07-10 19:31:29.231768+00','2026-07-10 19:31:29.110718+00');
`;

const esiti = [];
function controlla(fase, nome, ok, dettaglio = '') {
  esiti.push({ fase, nome, ok });
  console.log(`${fase.padEnd(5)} ${ok ? 'OK  ' : 'KO  '} ${nome}${dettaglio ? '  ' + dettaglio : ''}`);
}
const q1 = async (db, sql) => (await db.query(sql)).rows[0];

async function difetti(db, fase) {
  // A. storico: le posizioni a zero (527, 4762) NON sono vittorie
  const r = await q1(db, `SELECT sum((x->>'won')::int) v, sum((x->>'lost')::int) p,
      sum((x->>'void')::int) d, sum((x->>'settled')::int) s
    FROM jsonb_array_elements(public.trading_daily_history('mike_trades',
      $e$coalesce(t.role, t.strategy)$e$, $e$'calcio'$e$, $e$t.mode = 'paper'$e$,
      '2026-09-01','2026-09-26', NULL, 'placed')) x`);
  controlla(fase, 'A storico: V = solo P&L totale positivo (1 vinta, 527/4762 a zero esclusi)',
    Number(r.v) === 1, `V=${r.v} P=${r.p} void=${r.d} regolate=${r.s}`);
  controlla(fase, 'A storico: P e void invariati, regolate contano tutto', Number(r.p) === 1
    && Number(r.d) === 1 && Number(r.s) === 5, `P=${r.p} void=${r.d} regolate=${r.s}`);

  // B. Omega: modalita' separate e partite distinte
  const st = (await q1(db, 'SELECT public.get_omega_state() s')).s;
  const byp = st.aggregates_by_mode?.paper;
  const byl = st.aggregates_by_mode?.live;
  controlla(fase, 'B omega: aggregates_by_mode presente', byp != null && byl != null);
  controlla(fase, 'B omega: paper senza il live (realized paper = 0.95-79 = -78.05)',
    byp != null && Number(byp.realized_profit) === -78.05, `paper=${byp?.realized_profit}`);
  controlla(fase, 'B omega: live separato (1.9-0.5 = 1.4)',
    byl != null && Math.abs(Number(byl.realized_profit) - 1.4) < 1e-9, `live=${byl?.realized_profit}`);
  controlla(fase, 'B omega: partite distinte paper = 2 (aperture 3)',
    byp != null && Number(byp.events_traded) === 2 && Number(byp.matches_traded) === 3,
    `events=${byp?.events_traded} aperture=${byp?.matches_traded}`);

  // C. live P&L: la posizione su mercato regolato non e' aperta
  const pos = (await q1(db, 'SELECT public.get_live_positions_all() r')).r.rows;
  controlla(fase, 'C posizioni: 14265 (mercato regolato) esclusa, 14291 resta',
    pos.length === 1 && Number(pos[0].id) === 14291, `ids=${pos.map((p) => p.id).join(',')}`);
}

const db = new PGlite();
await db.exec(BASE);
await db.exec(DATI);
await db.exec(VIVO_STORICO);
await db.exec(VIVO_OMEGA_AGG);
await db.exec(VIVO_OMEGA_STATE);
await db.exec(VIVO_POS);

// fotografia dell'uscita di OGGI per il servizio Omega (equivalenza dopo)
const prima = {
  agg: (await q1(db, 'SELECT public.omega_aggregates_sql(false) a')).a,
  auto: (await q1(db, 'SELECT public.omega_aggregates_sql(true) a')).a,
  vuoto: (await q1(db, 'SELECT public.omega_aggregates_sql() a')).a,
  servizio: (await q1(db, 'SELECT public.get_omega_aggregates() a')).a,
  stato: (await q1(db, 'SELECT public.get_omega_state() s')).s,
};
try { await difetti(db, 'PRIMA'); } catch (e) { controlla('PRIMA', 'errore sui corpi vivi', false, String(e.message)); }

await db.exec(NUOVA_STORICO);
await db.exec(NUOVA_OMEGA);
await db.exec(NUOVA_POS);
// idempotenza: una seconda applicazione non cambia niente e non fallisce
await db.exec(NUOVA_STORICO);
await db.exec(NUOVA_OMEGA);
await db.exec(NUOVA_POS);
await difetti(db, 'DOPO');

// equivalenza: il servizio Omega legge gli stessi numeri (piu' 2 chiavi nuove)
const senzaNuove = (o) => { const c = { ...o }; delete c.events_traded; delete c.mode; return c; };
const eq = (a, b) => JSON.stringify(a, Object.keys(a).sort()) === JSON.stringify(b, Object.keys(b).sort());
const dopo = {
  agg: (await q1(db, 'SELECT public.omega_aggregates_sql(false) a')).a,
  auto: (await q1(db, 'SELECT public.omega_aggregates_sql(true) a')).a,
  vuoto: (await q1(db, 'SELECT public.omega_aggregates_sql() a')).a,
  servizio: (await q1(db, 'SELECT public.get_omega_aggregates() a')).a,
  stato: (await q1(db, 'SELECT public.get_omega_state() s')).s,
};
controlla('EQUIV', 'omega_aggregates_sql(false): stessi numeri di prima', eq(senzaNuove(dopo.agg), prima.agg));
controlla('EQUIV', 'omega_aggregates_sql(true): stessi numeri di prima', eq(senzaNuove(dopo.auto), prima.auto));
controlla('EQUIV', 'omega_aggregates_sql(): stessi numeri di prima', eq(senzaNuove(dopo.vuoto), prima.vuoto));
const servDopo = { ...senzaNuove(dopo.servizio), auto: senzaNuove(dopo.servizio.auto) };
controlla('EQUIV', 'get_omega_aggregates (servizio): stessi numeri + blocco auto', eq(servDopo, prima.servizio));
const aggStato = senzaNuove(dopo.stato.aggregates);
controlla('EQUIV', 'get_omega_state.aggregates: invariato', eq(aggStato, prima.stato.aggregates));
controlla('EQUIV', 'get_omega_state: nessuna chiave tolta',
  Object.keys(prima.stato).every((k) => k in dopo.stato));

const rossiPrima = esiti.filter((e) => e.fase === 'PRIMA' && !e.ok).length;
const koDopo = esiti.filter((e) => e.fase !== 'PRIMA' && !e.ok).length;
console.log(`\nPRIMA: ${rossiPrima} controlli rossi (attesi: il difetto si vede) · DOPO+EQUIV: ${koDopo} KO`);
process.exit(rossiPrima >= 5 && koDopo === 0 ? 0 : 1);
