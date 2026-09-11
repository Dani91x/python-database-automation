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

CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions(p_min_league_matches integer DEFAULT 1000)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_n integer;
BEGIN
    PERFORM set_config('statement_timeout', '1800000', true);   -- 30 min: lavoro una tantum
    DELETE FROM public.omega_minute_transitions;

    -- gol con minuto per partita valida (tabella temporanea: una sola lettura di match_events)
    CREATE TEMP TABLE tmp_goals ON COMMIT DROP AS
    SELECT e.fixture_id, e.minute,
           (e.team_id = m.home_team_id)::int AS h,
           (e.team_id = m.away_team_id)::int AS a
      FROM public.match_events e
      JOIN public.matches m ON m.fixture_id = e.fixture_id
     WHERE e.event_type = 'Goal'
       AND coalesce(e.detail, '') <> 'Missed Penalty'
       AND e.minute IS NOT NULL AND e.minute BETWEEN 0 AND 90
       AND m.status_short = 'FT';

    -- partite coerenti: gol ricostruiti = finale
    CREATE TEMP TABLE tmp_fx ON COMMIT DROP AS
    SELECT m.fixture_id, m.league_id,
           m.halftime_home::text || '-' || m.halftime_away::text AS ht,
           m.fulltime_home::text || '-' || m.fulltime_away::text AS ft
      FROM public.matches m
      LEFT JOIN (SELECT fixture_id, sum(h) AS gh, sum(a) AS ga FROM tmp_goals GROUP BY fixture_id) g
        ON g.fixture_id = m.fixture_id
     WHERE m.status_short = 'FT'
       AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
       AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
       AND coalesce(g.gh, 0) = m.fulltime_home AND coalesce(g.ga, 0) = m.fulltime_away;
    CREATE INDEX ON tmp_fx (fixture_id);

    -- leghe con abbastanza partite valide
    CREATE TEMP TABLE tmp_leagues ON COMMIT DROP AS
    SELECT league_id FROM tmp_fx WHERE league_id IS NOT NULL
     GROUP BY league_id HAVING count(*) >= p_min_league_matches;

    -- stato (bucket × partita): gol con minuto ≤ bucket
    CREATE TEMP TABLE tmp_state ON COMMIT DROP AS
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
        -- globale
        SELECT NULL::bigint AS league_id, s.bucket, s.score, 'ft'::text AS target, s.ft AS result FROM tmp_state s
        UNION ALL
        SELECT NULL::bigint, s.bucket, s.score, 'ht', s.ht FROM tmp_state s WHERE s.bucket <= 40
        UNION ALL
        -- per lega (solo leghe con abbastanza partite)
        SELECT s.league_id, s.bucket, s.score, 'ft', s.ft FROM tmp_state s
          JOIN tmp_leagues l ON l.league_id = s.league_id
        UNION ALL
        SELECT s.league_id, s.bucket, s.score, 'ht', s.ht FROM tmp_state s
          JOIN tmp_leagues l ON l.league_id = s.league_id WHERE s.bucket <= 40
      ) x
     GROUP BY coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_minute_transitions(integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_minute_transitions(integer) TO service_role;

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

-- COSTRUZIONE — PASSO SEPARATO, una volta, da solo (legge ~9,8 M eventi + 1,4 M partite;
-- alcuni minuti; timeout locale 30 min dentro la funzione):
--     SELECT public.omega_build_minute_transitions();
-- Finché la tabella è vuota il servizio usa il veto HT→FT (§14) e il modello.
