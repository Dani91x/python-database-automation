-- ============================================================================
-- omega_models_v3.sql — OMEGA §15 (11/09/2026): TABELLA PER MINUTO
-- "punteggio al minuto m → risultato finale / al 45′" dai gol con minuto.
--
-- Da applicare DOPO omega_daily_v2.sql. La COSTRUZIONE è un passo separato
-- (vedi in fondo): legge match_events (~9,8 M righe) e matches una volta.
--
-- Definizioni:
--   • partita valida = status FT, punteggi 45′/finale presenti, e gol ricostruiti
--     dagli eventi (event_type 'Goal', detail ≠ 'Missed Penalty', minuto ≤ 90;
--     autogol accreditato alla squadra che ne beneficia, come in API-Football)
--     UGUALI al finale: senza questa coerenza la riga è scartata (eventi mancanti);
--   • bucket = 0,5,…,85: stato = gol con minuto ≤ bucket (i gol al 90′+recupero
--     hanno minute = 90 → contano solo nel finale);
--   • target 'ft' (tutti i bucket) = risultato finale; target 'ht' (bucket ≤ 40)
--     = risultato al 45′;
--   • league_id 0 = tutte le leghe; per lega solo le leghe con ≥ 1000 partite valide.
--
-- IDEMPOTENTE. Owner-only via public.betfair_live_is_owner().
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.omega_minute_transitions (
    league_id   BIGINT   NOT NULL,
    bucket      SMALLINT NOT NULL,
    score       TEXT     NOT NULL,
    target      TEXT     NOT NULL CHECK (target IN ('ft','ht')),
    result      TEXT     NOT NULL,
    n           INTEGER  NOT NULL,
    built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (league_id, bucket, target, score, result)
);
ALTER TABLE public.omega_minute_transitions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_minute_transitions FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- COSTRUZIONE INCREMENTALE E RIPRISTINABILE (l'SQL editor di Supabase ha un
-- timeout del gateway di ~2 minuti: una passata unica su 1,6 M partite non ci
-- sta). Ogni PASSO lavora un lotto di partite (per id) e SOMMA i conteggi nella
-- tabella; ``_run(p_seconds)`` ripete i passi entro un budget di tempo; il
-- progresso sta in ``omega_build_jobs`` e riparte da dove era arrivato.
-- Al termine le leghe con meno di p_min_league_matches partite valide vengono
-- tolte (resta il globale). Da capo: SELECT public.omega_build_minute_transitions_reset();
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.omega_build_jobs (
    job          TEXT PRIMARY KEY,
    last_id      BIGINT  NOT NULL DEFAULT 0,
    max_id       BIGINT,
    processed    BIGINT  NOT NULL DEFAULT 0,   -- partite valide contate
    scanned      BIGINT  NOT NULL DEFAULT 0,   -- righe di matches esaminate
    done         BOOLEAN NOT NULL DEFAULT false,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_build_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_build_jobs FROM anon, authenticated;

CREATE TABLE IF NOT EXISTS public.omega_minute_league_counts (
    league_id  BIGINT PRIMARY KEY,
    n          INTEGER NOT NULL
);
ALTER TABLE public.omega_minute_league_counts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_minute_league_counts FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_reset()
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    DELETE FROM public.omega_minute_transitions;
    DELETE FROM public.omega_minute_league_counts;
    DELETE FROM public.omega_build_jobs WHERE job = 'minute_transitions';
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_reset() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_reset() TO service_role;

-- UN passo: lotto di p_batch id di matches (pochi secondi per 20.000)
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_step(
    p_batch integer DEFAULT 20000,
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
    SELECT * INTO v_job FROM public.omega_build_jobs WHERE job = 'minute_transitions' FOR UPDATE;
    IF v_job.done THEN
        RETURN jsonb_build_object('done', true, 'last_id', v_job.last_id, 'processed', v_job.processed);
    END IF;
    IF v_job.last_id = 0 THEN
        DELETE FROM public.omega_minute_transitions;
        DELETE FROM public.omega_minute_league_counts;
    END IF;
    v_hi := v_job.last_id + greatest(p_batch, 1000);

    DROP TABLE IF EXISTS tmp_fx;
    DROP TABLE IF EXISTS tmp_goals;
    DROP TABLE IF EXISTS tmp_state;

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

    -- gol con minuto (autogol alla squadra che ne beneficia; 90'+recupero = 90)
    CREATE TEMP TABLE tmp_goals AS
    SELECT e.fixture_id, e.minute,
           (e.team_id = f.home_team_id)::int AS h,
           (e.team_id = f.away_team_id)::int AS a
      FROM public.match_events e
      JOIN tmp_fx f ON f.fixture_id = e.fixture_id
     WHERE e.event_type = 'Goal'
       AND coalesce(e.detail, '') <> 'Missed Penalty'
       AND e.minute IS NOT NULL AND e.minute BETWEEN 0 AND 90;

    -- solo partite COERENTI (gol ricostruiti = finale)
    DELETE FROM tmp_fx f
     WHERE (SELECT coalesce(sum(g.h), 0) FROM tmp_goals g WHERE g.fixture_id = f.fixture_id) <> f.fulltime_home
        OR (SELECT coalesce(sum(g.a), 0) FROM tmp_goals g WHERE g.fixture_id = f.fixture_id) <> f.fulltime_away;
    SELECT count(*) INTO v_valid FROM tmp_fx;

    IF v_valid > 0 THEN
        -- stato (bucket x partita): gol con minuto <= bucket
        CREATE TEMP TABLE tmp_state AS
        SELECT f.fixture_id, f.league_id, b.bucket, f.ht, f.ft,
               coalesce(sum(g.h) FILTER (WHERE g.minute <= b.bucket), 0)::text || '-' ||
               coalesce(sum(g.a) FILTER (WHERE g.minute <= b.bucket), 0)::text AS score
          FROM tmp_fx f
         CROSS JOIN (SELECT generate_series(0, 85, 5) AS bucket) b
          LEFT JOIN tmp_goals g ON g.fixture_id = f.fixture_id
         GROUP BY f.fixture_id, f.league_id, b.bucket, f.ht, f.ft;

        INSERT INTO public.omega_minute_transitions (league_id, bucket, score, target, result, n)
        SELECT coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result, count(*)::integer
          FROM (
            SELECT NULL::bigint AS league_id, s.bucket, s.score, 'ft'::text AS target, s.ft AS result FROM tmp_state s
            UNION ALL
            SELECT NULL::bigint, s.bucket, s.score, 'ht', s.ht FROM tmp_state s WHERE s.bucket <= 40
            UNION ALL
            SELECT s.league_id, s.bucket, s.score, 'ft', s.ft FROM tmp_state s WHERE s.league_id IS NOT NULL
            UNION ALL
            SELECT s.league_id, s.bucket, s.score, 'ht', s.ht FROM tmp_state s WHERE s.league_id IS NOT NULL AND s.bucket <= 40
          ) x
         GROUP BY coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result
        ON CONFLICT (league_id, bucket, target, score, result)
        DO UPDATE SET n = public.omega_minute_transitions.n + EXCLUDED.n, built_at = now();

        INSERT INTO public.omega_minute_league_counts (league_id, n)
        SELECT f.league_id, count(*) FROM tmp_fx f WHERE f.league_id IS NOT NULL GROUP BY f.league_id
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
        EXCEPTION WHEN OTHERS THEN NULL;   -- pg_cron assente o job mai schedulato
        END;
    END IF;

    DROP TABLE IF EXISTS tmp_state;
    DROP TABLE IF EXISTS tmp_goals;
    DROP TABLE IF EXISTS tmp_fx;
    RETURN jsonb_build_object('done', v_job.done, 'last_id', v_job.last_id, 'max_id', v_job.max_id,
                              'processed', v_job.processed, 'scanned', v_job.scanned,
                              'batch_valid', v_valid);
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_step(integer,integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_step(integer,integer) TO service_role;

-- piu' passi entro un budget di tempo (default 90 s: sotto il timeout del gateway)
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_run(
    p_seconds integer DEFAULT 90,
    p_batch integer DEFAULT 20000
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_t0  timestamptz := clock_timestamp();
    v_out jsonb;
    v_steps integer := 0;
BEGIN
    PERFORM set_config('statement_timeout', ((greatest(p_seconds, 10) + 60) * 1000)::text, true);
    LOOP
        v_out := public.omega_build_minute_transitions_step(p_batch);
        v_steps := v_steps + 1;
        EXIT WHEN (v_out->>'done')::boolean
              OR extract(epoch FROM clock_timestamp() - v_t0) >= p_seconds;
    END LOOP;
    RETURN v_out || jsonb_build_object('steps', v_steps,
                                       'elapsed_s', round(extract(epoch FROM clock_timestamp() - v_t0)::numeric, 1));
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_run(integer,integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_run(integer,integer) TO service_role;

-- vecchia versione a passata unica: rimossa (andava in timeout sul gateway)
DROP FUNCTION IF EXISTS public.omega_build_minute_transitions(integer);

-- AUTOMATICO con pg_cron (se l'estensione e' attiva: Database -> Extensions -> pg_cron):
-- un job al minuto che lavora 50 s e si cancella da solo quando ha finito.
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_schedule()
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RETURN 'pg_cron non attivo: lancia a mano SELECT public.omega_build_minute_transitions_run(90); finche'' done = true';
    END IF;
    BEGIN
        PERFORM cron.unschedule('omega_minute_build');
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
    PERFORM cron.schedule('omega_minute_build', '* * * * *',
                          'SELECT public.omega_build_minute_transitions_run(50);');
    RETURN 'schedulato: un passo al minuto, si ferma da solo. Progresso: SELECT * FROM public.omega_build_jobs;';
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions_schedule() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions_schedule() TO service_role;

-- lettura a runtime: un bucket, un target, globale + lega (poche centinaia di righe, PK)
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
               'league_id', t.league_id, 'bucket', t.bucket, 'score', t.score,
               'target', t.target, 'result', t.result, 'n', t.n)), '[]'::jsonb)
      INTO v_out
      FROM public.omega_minute_transitions t
     WHERE t.bucket = p_bucket AND t.target = p_target
       AND (t.league_id = 0 OR (p_league_id IS NOT NULL AND t.league_id = p_league_id));
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_minute_ft(bigint,integer,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_minute_ft(bigint,integer,text) TO authenticated, service_role;

-- COSTRUZIONE (dopo aver applicato questo file):
--   automatica:  SELECT public.omega_build_minute_transitions_schedule();
--   oppure a mano, ripetendo finche' "done": true:
--                SELECT public.omega_build_minute_transitions_run(90);
--   progresso:   SELECT * FROM public.omega_build_jobs;
-- Finche' la tabella e' vuota il servizio usa il veto HT->FT (§14) e il modello.
