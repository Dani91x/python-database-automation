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
                   r.row || jsonb_build_object(
                       'goal', g.goal,
                       'goal_pct', CASE WHEN g.goal > 0
                                        THEN round((r.row->>'pnl_realized')::numeric / g.goal * 100, 1) END,
                       'goal_snapshot', true)
               ELSE r.row || jsonb_build_object('goal_snapshot', false)
               END ORDER BY r.ord), '[]'::jsonb)
      INTO v_out
      FROM jsonb_array_elements(v_rows) WITH ORDINALITY AS r(row, ord)
      LEFT JOIN public.omega_daily_goal g ON g.day = (r.row->>'day')::date;
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

-- VERIFICA (facoltativa):
--   SELECT * FROM public.omega_build_jobs;                       -- done = true
--   SELECT public.get_omega_minute_ft(NULL, 45, 'ft') ->> 0;      -- righe globali al 45′
