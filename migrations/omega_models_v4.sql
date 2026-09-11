-- ============================================================================
-- OMEGA — certificazione §16 (11/09/2026): revisione SQL/dati.
-- Da applicare DOPO omega_daily_v2.sql e omega_models_v3.sql. IDEMPOTENTE.
--
-- Contenuto:
--   1. grant espliciti a service_role sulle tabelle dei modelli (RLS on, il
--      servizio legge via RPC SECURITY DEFINER ma l'accesso diretto deve restare
--      possibile per audit/ricostruzioni);
--   2. indici mirati su omega_trades per i percorsi del servizio (posizioni
--      aperte, regolate per giorno, eventi manuali) — la tabella cresce ~200
--      righe/giorno: gli indici parziali restano minuscoli;
--   3. lookup dei modelli empirici come UNION ALL di due range sulla PK
--      (globale + lega) invece di un OR: piano deterministico, due index scan;
--   4. get_omega_daily set-based (niente loop plpgsql riga per riga);
--   5. costruzione incrementale della tabella per minuto: lock NOWAIT (un passo
--      manuale non resta appeso dietro al job pg_cron: risponde 'busy'), tabelle
--      temporanee qualificate pg_temp.*, max_id aggiornato a ogni passo (partite
--      arrivate durante la costruzione incluse), niente set_config inefficace.
--
-- NON cambia l'unique uq_omega_trades_auto_leg (event_id, phase) WHERE origin =
-- 'auto' AND closes_trade_id IS NULL: una gamba in 'error' (ordine reale a esito
-- ignoto) NON si ripiazza — è la rete di sicurezza del live, non un difetto.
-- ============================================================================

-- 1. grant espliciti
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.omega_ht_ft_transitions     TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.omega_minute_transitions    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.omega_minute_league_counts  TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.omega_build_jobs            TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.omega_daily_goal            TO service_role;

-- 2. indici mirati (parziali: piccoli e sempre caldi)
CREATE INDEX IF NOT EXISTS idx_omega_trades_open_pos
    ON public.omega_trades (status, id)
    WHERE status IN ('open', 'hedged', 'pending');
CREATE INDEX IF NOT EXISTS idx_omega_trades_settled
    ON public.omega_trades (settled_at DESC)
    WHERE settled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_omega_trades_pos_placed
    ON public.omega_trades (placed_at DESC)
    WHERE closes_trade_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_omega_trades_manual_event
    ON public.omega_trades (event_id)
    WHERE origin = 'manual' AND status <> 'error';
CREATE INDEX IF NOT EXISTS idx_omega_trades_legs
    ON public.omega_trades (id, event_id, phase)
    WHERE closes_trade_id IS NULL AND status <> 'error';

-- 3. lookup empirici: due range sulla PK
CREATE OR REPLACE FUNCTION public.get_omega_ht_ft(p_league_id bigint DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_out jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('league_id', x.league_id, 'ht', x.ht, 'ft', x.ft, 'n', x.n)), '[]'::jsonb)
      INTO v_out
      FROM (
          SELECT t.league_id, t.ht, t.ft, t.n FROM public.omega_ht_ft_transitions t WHERE t.league_id = 0
          UNION ALL
          SELECT t.league_id, t.ht, t.ft, t.n FROM public.omega_ht_ft_transitions t
           WHERE p_league_id IS NOT NULL AND p_league_id <> 0 AND t.league_id = p_league_id
      ) x;
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_ht_ft(bigint) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_ht_ft(bigint) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_omega_minute_ft(
    p_league_id bigint DEFAULT NULL,
    p_bucket    integer DEFAULT 0,
    p_target    text DEFAULT 'ft'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_out jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_target NOT IN ('ft', 'ht') THEN
        RAISE EXCEPTION 'target non valido: %', p_target;
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'league_id', x.league_id, 'bucket', x.bucket, 'score', x.score,
               'target', x.target, 'result', x.result, 'n', x.n)), '[]'::jsonb)
      INTO v_out
      FROM (
          SELECT t.league_id, t.bucket, t.score, t.target, t.result, t.n
            FROM public.omega_minute_transitions t
           WHERE t.league_id = 0 AND t.bucket = p_bucket AND t.target = p_target
          UNION ALL
          SELECT t.league_id, t.bucket, t.score, t.target, t.result, t.n
            FROM public.omega_minute_transitions t
           WHERE p_league_id IS NOT NULL AND p_league_id <> 0
             AND t.league_id = p_league_id AND t.bucket = p_bucket AND t.target = p_target
      ) x;
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_minute_ft(bigint,integer,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_minute_ft(bigint,integer,text) TO authenticated, service_role;

-- 4. get_omega_daily set-based
CREATE OR REPLACE FUNCTION public.get_omega_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_goal  numeric;
    v_rows  jsonb;
    v_out   jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;
    v_rows := public.trading_daily_history(
        'omega_trades',
        $e$coalesce(t.phase, 'none')$e$,
        $e$'calcio'$e$,
        NULL,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        v_goal,
        'placed');
    -- obiettivo STORICO del giorno (snapshot) quando c'è, altrimenti quello corrente
    SELECT coalesce(jsonb_agg(
               CASE WHEN g.goal IS NOT NULL THEN
                   r.elem || jsonb_build_object(
                       'goal', g.goal,
                       'goal_pct', CASE WHEN g.goal > 0
                                        THEN round((r.elem->>'pnl_realized')::numeric / g.goal * 100, 1) END,
                       'goal_snapshot', true)
               ELSE r.elem || jsonb_build_object('goal_snapshot', false)
               END ORDER BY r.ord), '[]'::jsonb)
      INTO v_out
      FROM jsonb_array_elements(v_rows) WITH ORDINALITY AS r(elem, ord)
      LEFT JOIN public.omega_daily_goal g ON g.day = (r.elem->>'day')::date;
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_daily(date,date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_daily(date,date) TO authenticated, service_role;

-- 5. costruzione incrementale: lock NOWAIT, pg_temp, max_id aggiornato
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_step(
    p_batch integer DEFAULT 5000,
    p_min_league_matches integer DEFAULT 1000
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_job   public.omega_build_jobs;
    v_hi    bigint;
    v_valid integer;
    v_scan  integer;
BEGIN
    INSERT INTO public.omega_build_jobs (job, max_id)
    VALUES ('minute_transitions', (SELECT max(id) FROM public.matches))
    ON CONFLICT (job) DO NOTHING;
    BEGIN
        SELECT * INTO v_job FROM public.omega_build_jobs
         WHERE job = 'minute_transitions' FOR UPDATE NOWAIT;
    EXCEPTION WHEN lock_not_available THEN
        RETURN jsonb_build_object('busy', true, 'done', false,
                                  'note', 'un altro passo (pg_cron) sta lavorando: riprova');
    END;
    IF v_job.done THEN
        RETURN jsonb_build_object('done', true, 'last_id', v_job.last_id, 'processed', v_job.processed);
    END IF;
    IF v_job.last_id = 0 THEN
        DELETE FROM public.omega_minute_transitions;
        DELETE FROM public.omega_minute_league_counts;
    END IF;
    -- partite arrivate DURANTE la costruzione: il traguardo si aggiorna
    UPDATE public.omega_build_jobs
       SET max_id = greatest(coalesce(max_id, 0), (SELECT coalesce(max(id), 0) FROM public.matches))
     WHERE job = 'minute_transitions'
    RETURNING * INTO v_job;
    v_hi := v_job.last_id + greatest(p_batch, 1000);

    DROP TABLE IF EXISTS pg_temp.tmp_fx;
    DROP TABLE IF EXISTS pg_temp.tmp_goals;
    DROP TABLE IF EXISTS pg_temp.tmp_state;

    -- partite del lotto con i punteggi
    CREATE TEMP TABLE tmp_fx AS
    SELECT m.id, m.fixture_id, m.league_id, m.home_team_id, m.away_team_id,
           m.halftime_home::text || '-' || m.halftime_away::text AS ht,
           m.fulltime_home::text || '-' || m.fulltime_away::text AS ft,
           m.fulltime_home, m.fulltime_away
      FROM public.matches m
     WHERE m.id > v_job.last_id AND m.id <= v_hi
       AND m.status_short = 'FT'
       AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
       AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL;
    GET DIAGNOSTICS v_scan = ROW_COUNT;
    CREATE INDEX ON pg_temp.tmp_fx (fixture_id);
    ANALYZE pg_temp.tmp_fx;

    -- gol con minuto (autogol alla squadra che ne beneficia; 90'+recupero = 90)
    CREATE TEMP TABLE tmp_goals AS
    SELECT e.fixture_id, e.minute,
           (e.team_id = f.home_team_id)::int AS h,
           (e.team_id = f.away_team_id)::int AS a
      FROM public.match_events e
      JOIN pg_temp.tmp_fx f ON f.fixture_id = e.fixture_id
     WHERE e.event_type = 'Goal'
       AND coalesce(e.detail, '') <> 'Missed Penalty'
       AND e.minute IS NOT NULL AND e.minute BETWEEN 0 AND 90;
    CREATE INDEX ON pg_temp.tmp_goals (fixture_id);
    ANALYZE pg_temp.tmp_goals;

    -- solo partite COERENTI (gol ricostruiti = finale): join aggregato, una passata
    DELETE FROM pg_temp.tmp_fx f
     USING (SELECT x.fixture_id, coalesce(g.gh, 0) AS gh, coalesce(g.ga, 0) AS ga
              FROM pg_temp.tmp_fx x
              LEFT JOIN (SELECT fixture_id, sum(h) AS gh, sum(a) AS ga FROM pg_temp.tmp_goals GROUP BY fixture_id) g
                ON g.fixture_id = x.fixture_id) t
     WHERE t.fixture_id = f.fixture_id
       AND (t.gh <> f.fulltime_home OR t.ga <> f.fulltime_away);
    SELECT count(*) INTO v_valid FROM pg_temp.tmp_fx;

    IF v_valid > 0 THEN
        -- stato (bucket x partita): gol con minuto <= bucket
        CREATE TEMP TABLE tmp_state AS
        SELECT f.fixture_id, f.league_id, b.bucket, f.ht, f.ft,
               coalesce(sum(g.h) FILTER (WHERE g.minute <= b.bucket), 0)::text || '-' ||
               coalesce(sum(g.a) FILTER (WHERE g.minute <= b.bucket), 0)::text AS score
          FROM pg_temp.tmp_fx f
         CROSS JOIN (SELECT generate_series(0, 85, 5) AS bucket) b
          LEFT JOIN pg_temp.tmp_goals g ON g.fixture_id = f.fixture_id
         GROUP BY f.fixture_id, f.league_id, b.bucket, f.ht, f.ft;

        INSERT INTO public.omega_minute_transitions (league_id, bucket, score, target, result, n)
        SELECT coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result, count(*)::integer
          FROM (
            SELECT NULL::bigint AS league_id, s.bucket, s.score, 'ft'::text AS target, s.ft AS result FROM pg_temp.tmp_state s
            UNION ALL
            SELECT NULL::bigint, s.bucket, s.score, 'ht', s.ht FROM pg_temp.tmp_state s WHERE s.bucket <= 40
            UNION ALL
            SELECT s.league_id, s.bucket, s.score, 'ft', s.ft FROM pg_temp.tmp_state s WHERE s.league_id IS NOT NULL
            UNION ALL
            SELECT s.league_id, s.bucket, s.score, 'ht', s.ht FROM pg_temp.tmp_state s WHERE s.league_id IS NOT NULL AND s.bucket <= 40
          ) x
         GROUP BY coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result
        ON CONFLICT (league_id, bucket, target, score, result)
        DO UPDATE SET n = public.omega_minute_transitions.n + EXCLUDED.n, built_at = now();

        INSERT INTO public.omega_minute_league_counts (league_id, n)
        SELECT f.league_id, count(*) FROM pg_temp.tmp_fx f WHERE f.league_id IS NOT NULL GROUP BY f.league_id
        ON CONFLICT (league_id) DO UPDATE SET n = public.omega_minute_league_counts.n + EXCLUDED.n;
    END IF;

    UPDATE public.omega_build_jobs
       SET last_id = v_hi, processed = processed + v_valid, scanned = scanned + v_scan,
           done = (v_hi >= coalesce(max_id, 0)), updated_at = now()
     WHERE job = 'minute_transitions'
    RETURNING * INTO v_job;

    IF v_job.done THEN
        -- leghe con poche partite valide: via (resta il globale, league_id 0)
        DELETE FROM public.omega_minute_transitions t
         WHERE t.league_id <> 0
           AND t.league_id NOT IN (SELECT c.league_id FROM public.omega_minute_league_counts c
                                    WHERE c.n >= p_min_league_matches);
        BEGIN
            PERFORM cron.unschedule('omega_minute_build');
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'cron.unschedule: % (pg_cron assente o job mai schedulato)', SQLERRM;
        END;
    END IF;

    DROP TABLE IF EXISTS pg_temp.tmp_state;
    DROP TABLE IF EXISTS pg_temp.tmp_goals;
    DROP TABLE IF EXISTS pg_temp.tmp_fx;
    RETURN jsonb_build_object('done', v_job.done, 'last_id', v_job.last_id, 'max_id', v_job.max_id,
                              'processed', v_job.processed, 'scanned', v_job.scanned,
                              'batch_valid', v_valid);
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_step(integer,integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_step(integer,integer) TO service_role;

CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_run(
    p_seconds integer DEFAULT 90,
    p_batch integer DEFAULT 5000
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_t0  timestamptz := clock_timestamp();
    v_out jsonb;
    v_steps integer := 0;
BEGIN
    -- (nessun set_config di statement_timeout: dentro una funzione non ha effetto
    --  sullo statement in corso — il budget di tempo è p_seconds, sotto il gateway)
    LOOP
        v_out := public.omega_build_minute_transitions_step(p_batch);
        v_steps := v_steps + 1;
        EXIT WHEN coalesce((v_out->>'done')::boolean, false)
              OR coalesce((v_out->>'busy')::boolean, false)
              OR extract(epoch FROM clock_timestamp() - v_t0) >= p_seconds;
    END LOOP;
    RETURN v_out || jsonb_build_object('steps', v_steps,
                                       'elapsed_s', round(extract(epoch FROM clock_timestamp() - v_t0)::numeric, 1));
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_run(integer,integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_run(integer,integer) TO service_role;

-- 6. aggregati e storico: liability aperta RESIDUA dopo la copertura (HIGH-1) e
--    vinte/perse per SEGNO del P&L totale della posizione (MEDIUM-1), come la UI live.
--    trading_daily_history è condivisa con la Safe Strategy: la modifica vale per entrambe
--    (una posizione coperta in perdita non è "vinta" in nessuna delle due).
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    -- UNA sola scansione di omega_trades (tabella piccola: ~100 righe/giorno);
    -- giorno della posizione = placed_at dell'apertura (join su PK).
    -- Usata da get_omega_state (UI) e da get_omega_aggregates (servizio, ogni
    -- ciclo): il servizio non legge piu' tutta la tabella a pagine.
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day
    ), t AS (
        SELECT o.status, o.pnl, o.placed_at, o.event_id, o.closes_trade_id,
               -- liability RESIDUA dopo la copertura (§16 seconda passata HIGH-1: come
               -- omega_engine.residual_liability — meta.if_win quando c'è hedged_size)
               CASE WHEN o.meta ? 'hedged_size' AND (o.meta->>'if_win') ~ '^-?[0-9.]+$'
                    THEN greatest(0, -(o.meta->>'if_win')::numeric)
                    ELSE o.liability END AS liability,
               (o.bet_id IS NOT NULL OR (o.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed,
               coalesce(p.placed_at, o.placed_at) AS pos_placed_at,
               -- esito della POSIZIONE (apertura + chiusure) per SEGNO del P&L totale
               CASE WHEN o.closes_trade_id IS NULL AND o.status IN ('won','lost','void') THEN
                    o.pnl + coalesce((SELECT sum(c.pnl) FROM public.omega_trades c
                                       WHERE c.closes_trade_id = o.id AND c.status IN ('won','lost','void')), 0)
               END AS total_pnl
          FROM public.omega_trades o
          LEFT JOIN public.omega_trades p ON p.id = o.closes_trade_id
    )
    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.pos_placed_at >= d.v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))), 0),
        'matches_traded',  count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        'matches_traded_today', count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))
                               AND t.placed_at >= d.v_day),
        'legs_today',      count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'events_today',    count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'matches_open',    count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))),
        'matches_won',     count(*) FILTER (WHERE t.total_pnl > 0),
        'matches_lost',    count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',       count(*) FILTER (WHERE t.total_pnl > 0 AND t.placed_at >= d.v_day),
        'lost_today',      count(*) FILTER (WHERE t.total_pnl < 0 AND t.placed_at >= d.v_day)
    )
      FROM d LEFT JOIN t ON true
     GROUP BY d.v_day;
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql() TO service_role;

CREATE OR REPLACE FUNCTION public.trading_daily_history(
    p_table         text,
    p_strategy_expr text,
    p_sport_expr    text,
    p_filter_expr   text,
    p_from          date,
    p_to            date,
    p_goal          numeric,
    p_day_by        text DEFAULT 'settled'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_from timestamptz;
    v_to   timestamptz;
    v_out  jsonb;
    v_by_placed boolean;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed') THEN
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', p_from, p_to;
    END IF;
    IF (p_to - p_from) > 400 THEN
        RAISE EXCEPTION 'intervallo troppo ampio (max 400 giorni): % → %', p_from, p_to;
    END IF;
    v_by_placed := (p_day_by = 'placed');
    v_from := (p_from::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    EXECUTE format($q$
        WITH originals AS (
            SELECT t.id, t.status, t.pnl::numeric AS pnl, t.liability::numeric AS liability,
                   t.origin, t.placed_at, t.settled_at,
                   (%s)::text AS strategy, (%s)::text AS sport,
                   (t.placed_at  AT TIME ZONE 'Europe/Rome')::date AS placed_day,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day,
                   -- giorno "di regolazione" usato dalle statistiche: con
                   -- l'attribuzione 'placed' è il giorno di piazzamento
                   CASE WHEN $6 THEN (t.placed_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS op_settled_day,
                   (t.bet_id IS NOT NULL OR (t.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed
              FROM public.%I t
             WHERE t.closes_trade_id IS NULL
               AND (%s)
               AND ((t.placed_at >= $1 AND t.placed_at < $2)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), closers AS (
            SELECT t.id, t.closes_trade_id, t.status, t.pnl::numeric AS pnl, t.market_id,
                   t.commission::numeric AS commission, t.meta, t.settled_at,
                   CASE WHEN $6 THEN (o.placed_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS settled_day
              FROM public.%I t
              JOIN public.%I o ON o.id = t.closes_trade_id
             WHERE t.closes_trade_id IS NOT NULL
               AND (%s)
               AND (t.closes_trade_id IN (SELECT id FROM originals)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), placed AS (
            SELECT * FROM originals
             WHERE status <> 'error'
               AND (status <> 'pending' OR is_placed)
               AND placed_day BETWEEN $3 AND $4
        ), trade_raw AS (
            SELECT o.id, o.op_settled_day AS settled_day, o.status AS raw_status, o.strategy, o.sport, o.origin,
                   o.pnl + coalesce((SELECT sum(c.pnl) FROM closers c
                                      WHERE c.closes_trade_id = o.id
                                        AND c.status IN ('won','lost','void')), 0) AS total_pnl
              FROM originals o
             WHERE o.status IN ('won','lost','void')
               AND o.op_settled_day BETWEEN $3 AND $4
        ), trade_tot AS (
            -- esito della POSIZIONE per SEGNO del P&L totale (§16 seconda passata MEDIUM-1:
            -- apertura 'won' +2 con chiusura −24 era contata "vinta")
            SELECT id, settled_day, strategy, sport, origin, total_pnl,
                   CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost' ELSE raw_status END AS status
              FROM trade_raw
        ), settled_rows AS (
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM (SELECT o.op_settled_day AS settled_day, o.pnl, t.market_id, t.commission::numeric AS commission, t.meta
                      FROM originals o JOIN public.%I t ON t.id = o.id
                     WHERE o.status IN ('won','lost','void')) x
            UNION ALL
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM closers WHERE status IN ('won','lost','void')
        ), days AS (
            SELECT placed_day AS op_day FROM placed
            UNION
            SELECT op_day FROM settled_rows WHERE op_day BETWEEN $3 AND $4
        ), comm_market AS (
            SELECT op_day, market_id,
                   sum(nullif(meta->>'commission_paid','')::numeric) AS paid,
                   sum(pnl) AS net,
                   coalesce(avg(commission), 0.05) AS c
              FROM settled_rows
             WHERE op_day BETWEEN $3 AND $4
             GROUP BY op_day, market_id
        ), comm_day AS (
            SELECT op_day,
                   CASE WHEN bool_or(paid IS NOT NULL) THEN sum(coalesce(paid, 0))
                        ELSE sum(CASE WHEN net > 0 AND c < 1 THEN net * c / (1 - c) ELSE 0 END)
                   END AS commission_paid
              FROM comm_market GROUP BY op_day
        ), brk AS (
            SELECT op_day, dim, dim_key,
                   count(*) FILTER (WHERE kind = 'placed')            AS n,
                   coalesce(sum(total_pnl) FILTER (WHERE kind = 'settled'), 0) AS pnl,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'won')  AS won,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'lost') AS lost
              FROM (
                  SELECT placed_day AS op_day, 'strategy' AS dim, strategy AS dim_key, 'placed' AS kind, 0::numeric AS total_pnl, status FROM placed
                  UNION ALL SELECT placed_day, 'sport',  sport,  'placed', 0, status FROM placed
                  UNION ALL SELECT placed_day, 'origin', origin, 'placed', 0, status FROM placed
                  UNION ALL SELECT settled_day, 'strategy', strategy, 'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'sport',  sport,  'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'origin', origin, 'settled', total_pnl, status FROM trade_tot
              ) u
             GROUP BY op_day, dim, dim_key
        ), brk_json AS (
            SELECT op_day, dim,
                   jsonb_object_agg(coalesce(dim_key, 'none'),
                       jsonb_build_object('n', n, 'pnl', round(pnl, 2), 'won', won, 'lost', lost)) AS j
              FROM brk GROUP BY op_day, dim
        ), per_day AS (
            SELECT d.op_day,
                   (SELECT coalesce(round(sum(pnl), 2), 0) FROM settled_rows s WHERE s.op_day = d.op_day) AS pnl_realized,
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day) AS trades_placed,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day) AS settled,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'won')  AS won,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'lost') AS lost,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'void') AS n_void,
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day
                       AND (p.status = 'hedged'
                            OR EXISTS (SELECT 1 FROM closers c WHERE c.closes_trade_id = p.id AND c.status <> 'error'))) AS hedged_closed,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS avg_win,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS avg_loss,
                   (SELECT round(max(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS best_trade,
                   (SELECT round(min(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS worst_trade,
                   (SELECT round(max(liability), 2) FROM placed p WHERE p.placed_day = d.op_day) AS max_liability,
                   (SELECT coalesce(round(sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS gross_profit,
                   (SELECT coalesce(round(-sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS gross_loss,
                   (SELECT round(commission_paid, 2) FROM comm_day cd WHERE cd.op_day = d.op_day) AS commission_paid,
                   (SELECT min(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS first_trade_at,
                   (SELECT max(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS last_trade_at,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'strategy') AS by_strategy,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'sport')    AS by_sport,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'origin')   AS by_origin
              FROM days d
        )
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'day',             to_char(op_day, 'YYYY-MM-DD'),
                   'pnl_realized',    pnl_realized,
                   'trades_placed',   trades_placed,
                   'settled',         settled,
                   'won',             won,
                   'lost',            lost,
                   'void',            n_void,
                   'hedged_closed',   hedged_closed,
                   'win_rate',        CASE WHEN won + lost > 0 THEN round(won::numeric / (won + lost), 4) END,
                   'avg_win',         avg_win,
                   'avg_loss',        avg_loss,
                   'best_trade',      best_trade,
                   'worst_trade',     worst_trade,
                   'max_liability',   max_liability,
                   'gross_profit',    gross_profit,
                   'gross_loss',      gross_loss,
                   'profit_factor',   CASE WHEN gross_loss > 0 THEN round(gross_profit / gross_loss, 3) END,
                   'commission_paid', commission_paid,
                   'goal',            $5::numeric,
                   'goal_pct',        CASE WHEN $5::numeric > 0 THEN round(pnl_realized / $5::numeric * 100, 1) END,
                   'by_strategy',     coalesce(by_strategy, '{}'::jsonb),
                   'by_sport',        coalesce(by_sport, '{}'::jsonb),
                   'by_origin',       coalesce(by_origin, '{}'::jsonb),
                   'first_trade_at',  first_trade_at,
                   'last_trade_at',   last_trade_at
               ) ORDER BY op_day), '[]'::jsonb)
          FROM per_day
    $q$, p_strategy_expr, p_sport_expr, p_table, coalesce(p_filter_expr, 'true'),
         p_table, p_table, coalesce(p_filter_expr, 'true'), p_table)
    INTO v_out
    USING v_from, v_to, p_from, p_to, p_goal, v_by_placed;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;

-- VERIFICA (facoltativa):
--   SELECT * FROM public.omega_build_jobs;                       -- done = true
--   SELECT public.get_omega_minute_ft(NULL, 45, 'ft') ->> 0;      -- righe globali al 45′
