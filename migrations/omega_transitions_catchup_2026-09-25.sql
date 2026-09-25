-- ============================================================================
-- omega_transitions_catchup_2026-09-25.sql -- O2 dell'audit 24/09
-- TABELLE DI TRANSIZIONE DI OMEGA SEMPRE AGGIORNATE, SENZA DOPPI CONTEGGI,
-- SENZA PARTITE PERSE.
--
-- Da applicare DOPO omega_daily_v2.sql, omega_models_v3.sql, omega_models_v4.sql.
-- ADDITIVA e IDEMPOTENTE (si puo' rilanciare): non modifica le RPC lette dai bot
-- (get_omega_minute_ft, get_omega_ht_ft: firma e semantica INVARIATE).
--
-- IL PROBLEMA (stato verificato sul DB il 25/09):
--   * omega_minute_transitions e omega_ht_ft_transitions sono ferme all'11/09;
--   * il vecchio passo incrementale procede per matches.id e SOMMA
--     (n = n + EXCLUDED.n): le partite entrano in matches PRIMA di finire
--     (backfill stagionale) e diventano FT dopo, quindi un recupero "per id >
--     last_id" le perde per sempre (1.556 partite FT dal 11/09 con id <= 1.620.000),
--     e un recupero "rifai il lotto" le conta due volte;
--   * pg_cron attivo ma nessun job omega_* schedulato.
--
-- LA SOLUZIONE:
--   1. REGISTRO PER PARTITA (omega_transitions_ledger): una riga per fixture_id,
--      con l'istante in cui e' stata contata in ciascuna delle due tabelle
--      (ht_ft_at, minute_at). Una partita si somma SOLO se non e' nel registro,
--      e il registro si scrive nella STESSA transazione dei conteggi: rilanciare
--      non cambia n (idempotenza), nessuna partita contata due volte.
--   2. CONTEGGI GREZZI (*_raw): tutte le leghe, mai potate. Le tabelle lette dai
--      bot (omega_minute_transitions, omega_ht_ft_transitions) sono la loro
--      PUBBLICAZIONE: minute = globale + leghe ammesse (>= soglia partite),
--      ht_ft = tutto (come prima).
--   3. RICOSTRUZIONE UNA TANTUM nelle tabelle grezze (i bot continuano a leggere
--      i numeri dell'11/09 finche' non si PUBBLICA), a lotti, entro un budget di
--      tempo per notte. Si pubblica A MANO (omega_transitions_publish), dopo la
--      verifica: una sola transazione, nessuna finestra con tabelle a meta'.
--   4. DOPO la pubblicazione ogni passo scrive grezzo E pubblicato nella stessa
--      transazione (n pubblicato = n grezzo, cella per cella).
--   5. omega_transitions_nightly(p_budget_s): finestra calda (partite con
--      fixture_date recente), cursore per id (ricostruzione e righe nuove), giro
--      di controllo a rotazione su tutto lo spazio id (partite tardive e scartate
--      da ricontrollare). Referto per giro in omega_transitions_runs.
--   6. pg_cron alle 04:00 UTC (idempotente, con guardia se pg_cron manca).
--
-- Definizioni INVARIATE rispetto a omega_models_v3/v4 e omega_daily_v2:
--   * ht_ft: status FT, punteggi 45' e finale presenti; lega + globale (0);
--   * minute: in piu' gol ricostruiti da match_events (Goal, detail <> 'Missed
--     Penalty', 0 <= minute <= 90, autogol alla squadra che ne beneficia) UGUALI
--     al finale; bucket 0..85 passo 5; target 'ft' (tutti) e 'ht' (bucket <= 40).
--
-- Procedura completa: Betfair/omega/TRANSIZIONI_NOTTURNE_2026-09-25.md
-- Verifica:           python -m Betfair.omega.tools.verifica_transizioni_2026_09_25
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. INDICI PREREQUISITI (no-op se gia' presenti)
-- ----------------------------------------------------------------------------
-- gol per partita (gia' creato da omega_models_v3.sql)
CREATE INDEX IF NOT EXISTS idx_match_events_goal_fixture
    ON public.match_events (fixture_id) WHERE event_type = 'Goal';
-- NB: la FINESTRA CALDA usa un indice su matches(fixture_date). Quello
-- documentato in sql/leagues_needing_retrain_rpc.sql e':
--     create index concurrently if not exists idx_matches_fixture_date_settled
--       on public.matches (fixture_date) where status_short in ('FT','AET','PEN');
-- NON lo creo qui (CREATE INDEX senza CONCURRENTLY blocca le scritture su
-- matches). Se manca, il giro notturno SALTA la finestra calda e lo scrive nel
-- referto (hot_skipped_no_index = true): lanciare il comando sopra DA SOLO.

-- ----------------------------------------------------------------------------
-- 1. TABELLE
-- ----------------------------------------------------------------------------
-- registro per partita: "gia' contata?" per ciascuna delle due tabelle
CREATE TABLE IF NOT EXISTS public.omega_transitions_ledger (
    fixture_id         BIGINT      PRIMARY KEY,
    match_id           BIGINT      NOT NULL,          -- matches.id al momento del conteggio
    league_id          BIGINT,                        -- lega con cui e' stata contata
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ht_ft_at           TIMESTAMPTZ,                   -- contata in omega_ht_ft_transitions(_raw)
    minute_at          TIMESTAMPTZ,                   -- contata in omega_minute_transitions(_raw)
    minute_rejects     INTEGER     NOT NULL DEFAULT 0 CHECK (minute_rejects >= 0),
    minute_checked_at  TIMESTAMPTZ                    -- ultimo controllo di coerenza gol/finale
);
ALTER TABLE public.omega_transitions_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_transitions_ledger FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_transitions_ledger TO service_role;

-- conteggi grezzi per minuto: TUTTE le leghe (mai potate) + globale (0)
CREATE TABLE IF NOT EXISTS public.omega_minute_transitions_raw (
    league_id   BIGINT   NOT NULL,
    bucket      SMALLINT NOT NULL,
    score       TEXT     NOT NULL,
    target      TEXT     NOT NULL CHECK (target IN ('ft','ht')),
    result      TEXT     NOT NULL,
    n           INTEGER  NOT NULL CHECK (n > 0),
    built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (league_id, bucket, target, score, result)
);
ALTER TABLE public.omega_minute_transitions_raw ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_minute_transitions_raw FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_minute_transitions_raw TO service_role;

-- conteggi grezzi HT->FT: tutte le leghe + globale (0)
CREATE TABLE IF NOT EXISTS public.omega_ht_ft_transitions_raw (
    league_id   BIGINT  NOT NULL,
    ht          TEXT    NOT NULL,
    ft          TEXT    NOT NULL,
    n           INTEGER NOT NULL CHECK (n > 0),
    built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (league_id, ht, ft)
);
ALTER TABLE public.omega_ht_ft_transitions_raw ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_ht_ft_transitions_raw FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_ht_ft_transitions_raw TO service_role;

-- partite contate per lega (0 = tutte, comprese quelle senza lega)
CREATE TABLE IF NOT EXISTS public.omega_transitions_league_counts (
    league_id   BIGINT  PRIMARY KEY,
    n_minute    INTEGER NOT NULL DEFAULT 0 CHECK (n_minute >= 0),
    n_ht_ft     INTEGER NOT NULL DEFAULT 0 CHECK (n_ht_ft >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_transitions_league_counts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_transitions_league_counts FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_transitions_league_counts TO service_role;

-- stato (una riga): cursori, ricostruzione, pubblicazione, soglia delle leghe
CREATE TABLE IF NOT EXISTS public.omega_transitions_state (
    id                    SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    id_cursor             BIGINT  NOT NULL DEFAULT 0,   -- matches.id gia' passati dal cursore
    sweep_cursor          BIGINT  NOT NULL DEFAULT 0,   -- giro di controllo a rotazione
    sweep_cycles          INTEGER NOT NULL DEFAULT 0,
    bootstrap_started_at  TIMESTAMPTZ,
    bootstrap_done_at     TIMESTAMPTZ,                  -- il cursore ha raggiunto max(id)
    published_at          TIMESTAMPTZ,                  -- NULL = i bot leggono ancora l'11/09
    min_league_matches    INTEGER NOT NULL DEFAULT 1000 CHECK (min_league_matches >= 1),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_transitions_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_transitions_state FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_transitions_state TO service_role;
INSERT INTO public.omega_transitions_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- referto per giro (come omega_build_jobs, ma una riga per esecuzione)
CREATE TABLE IF NOT EXISTS public.omega_transitions_runs (
    id                     BIGSERIAL PRIMARY KEY,
    started_at             TIMESTAMPTZ NOT NULL,
    finished_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    elapsed_s              NUMERIC(10,1),
    dry_run                BOOLEAN NOT NULL DEFAULT false,
    status                 TEXT    NOT NULL,   -- ok | budget | dry_run | busy | errore
    published              BOOLEAN,
    steps                  INTEGER NOT NULL DEFAULT 0,
    scanned                BIGINT  NOT NULL DEFAULT 0,   -- partite FT da lavorare esaminate
    ht_ft_counted          BIGINT  NOT NULL DEFAULT 0,
    minute_counted         BIGINT  NOT NULL DEFAULT 0,
    minute_rejected        BIGINT  NOT NULL DEFAULT 0,   -- gol ricostruiti <> finale (si ritenta)
    hot_candidates         INTEGER NOT NULL DEFAULT 0,
    hot_skipped_no_index   BOOLEAN NOT NULL DEFAULT false,
    id_cursor_from         BIGINT,
    id_cursor_to           BIGINT,
    max_id                 BIGINT,
    sweep_from             BIGINT,
    sweep_to               BIGINT,
    live_minute_upserts    BIGINT  NOT NULL DEFAULT 0,
    live_ht_ft_upserts     BIGINT  NOT NULL DEFAULT 0,
    new_leagues            INTEGER NOT NULL DEFAULT 0,
    error                  TEXT,
    params                 JSONB
);
ALTER TABLE public.omega_transitions_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_transitions_runs FROM anon, authenticated;
GRANT SELECT ON TABLE public.omega_transitions_runs TO service_role;
REVOKE ALL ON SEQUENCE public.omega_transitions_runs_id_seq FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- 2. UN PASSO: conta un lotto di partite NON ancora nel registro.
--    Lotto = range di matches.id (p_lo, p_hi] oppure un elenco di id (p_ids).
--    Tutto nella transazione del chiamante: conteggi grezzi, pubblicati (se la
--    pubblicazione e' avvenuta), conteggi per lega e registro insieme.
--    Interno: lo chiamano solo omega_transitions_nightly (stesso proprietario).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_transitions_step(
    p_lo          bigint,
    p_hi          bigint,
    p_ids         bigint[] DEFAULT NULL,
    p_retry_hours integer  DEFAULT 20
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_retry      timestamptz := now() - make_interval(hours => greatest(p_retry_hours, 1));
    v_published  boolean;
    v_min        integer;
    v_scan       integer := 0;
    v_htft       integer := 0;
    v_minute     integer := 0;
    v_rej        integer := 0;
    v_live_min   integer := 0;
    v_live_htft  integer := 0;
    v_new_lg     integer := 0;
    v_rows       integer := 0;
BEGIN
    -- stesso lucchetto del giro notturno e della pubblicazione (rientrante nella
    -- stessa sessione): due scrittori non contano mai la stessa partita
    PERFORM pg_advisory_xact_lock(hashtext('omega_transitions'));

    INSERT INTO public.omega_transitions_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
    SELECT s.published_at IS NOT NULL, s.min_league_matches
      INTO v_published, v_min
      FROM public.omega_transitions_state s WHERE s.id = 1;

    DROP TABLE IF EXISTS pg_temp.omg_fx;
    DROP TABLE IF EXISTS pg_temp.omg_goals;
    DROP TABLE IF EXISTS pg_temp.omg_ok;
    DROP TABLE IF EXISTS pg_temp.omg_state;
    DROP TABLE IF EXISTS pg_temp.omg_inc;

    -- partite FT valide del lotto che hanno ancora qualcosa da contare
    -- (due rami separati: ciascuno con il suo piano, range sulla PK o elenco)
    IF p_ids IS NULL THEN
        CREATE TEMP TABLE omg_fx AS
        SELECT m.id, m.fixture_id, m.league_id, m.home_team_id, m.away_team_id,
               m.halftime_home::text || '-' || m.halftime_away::text AS ht,
               m.fulltime_home::text || '-' || m.fulltime_away::text AS ft,
               m.fulltime_home, m.fulltime_away,
               (l.ht_ft_at IS NULL) AS need_htft,
               (l.minute_at IS NULL AND (l.minute_checked_at IS NULL OR l.minute_checked_at < v_retry)) AS need_min
          FROM public.matches m
          LEFT JOIN public.omega_transitions_ledger l ON l.fixture_id = m.fixture_id
         WHERE m.id > p_lo AND m.id <= p_hi
           AND m.status_short = 'FT'
           AND m.fixture_id IS NOT NULL
           AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
           AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
           AND (l.fixture_id IS NULL OR l.ht_ft_at IS NULL
                OR (l.minute_at IS NULL AND (l.minute_checked_at IS NULL OR l.minute_checked_at < v_retry)));
    ELSE
        CREATE TEMP TABLE omg_fx AS
        SELECT m.id, m.fixture_id, m.league_id, m.home_team_id, m.away_team_id,
               m.halftime_home::text || '-' || m.halftime_away::text AS ht,
               m.fulltime_home::text || '-' || m.fulltime_away::text AS ft,
               m.fulltime_home, m.fulltime_away,
               (l.ht_ft_at IS NULL) AS need_htft,
               (l.minute_at IS NULL AND (l.minute_checked_at IS NULL OR l.minute_checked_at < v_retry)) AS need_min
          FROM public.matches m
          LEFT JOIN public.omega_transitions_ledger l ON l.fixture_id = m.fixture_id
         WHERE m.id = ANY (p_ids)
           AND m.status_short = 'FT'
           AND m.fixture_id IS NOT NULL
           AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
           AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
           AND (l.fixture_id IS NULL OR l.ht_ft_at IS NULL
                OR (l.minute_at IS NULL AND (l.minute_checked_at IS NULL OR l.minute_checked_at < v_retry)));
    END IF;
    GET DIAGNOSTICS v_scan = ROW_COUNT;
    IF v_scan = 0 THEN
        DROP TABLE IF EXISTS pg_temp.omg_fx;
        RETURN jsonb_build_object('scanned', 0, 'ht_ft_counted', 0, 'minute_counted', 0,
                                  'minute_rejected', 0, 'live_minute_upserts', 0,
                                  'live_ht_ft_upserts', 0, 'new_leagues', 0);
    END IF;
    CREATE INDEX ON pg_temp.omg_fx (fixture_id);
    ANALYZE pg_temp.omg_fx;

    -- gol con minuto delle sole partite da contare per minuto
    CREATE TEMP TABLE omg_goals AS
    SELECT e.fixture_id, e.minute,
           (e.team_id = f.home_team_id)::int AS h,
           (e.team_id = f.away_team_id)::int AS a
      FROM public.match_events e
      JOIN pg_temp.omg_fx f ON f.fixture_id = e.fixture_id
     WHERE f.need_min
       AND e.event_type = 'Goal'
       AND coalesce(e.detail, '') <> 'Missed Penalty'
       AND e.minute IS NOT NULL AND e.minute BETWEEN 0 AND 90;
    CREATE INDEX ON pg_temp.omg_goals (fixture_id);
    ANALYZE pg_temp.omg_goals;

    -- partite COERENTI (gol ricostruiti = finale): le sole contate per minuto
    CREATE TEMP TABLE omg_ok AS
    SELECT x.fixture_id
      FROM pg_temp.omg_fx x
      LEFT JOIN (SELECT fixture_id, sum(h) AS gh, sum(a) AS ga
                   FROM pg_temp.omg_goals GROUP BY fixture_id) g
        ON g.fixture_id = x.fixture_id
     WHERE x.need_min
       AND coalesce(g.gh, 0) = x.fulltime_home
       AND coalesce(g.ga, 0) = x.fulltime_away;
    CREATE UNIQUE INDEX ON pg_temp.omg_ok (fixture_id);
    SELECT count(*) INTO v_minute FROM pg_temp.omg_ok;
    SELECT count(*) INTO v_rej FROM pg_temp.omg_fx WHERE need_min;
    v_rej := v_rej - v_minute;
    SELECT count(*) INTO v_htft FROM pg_temp.omg_fx WHERE need_htft;

    -- incrementi per lega (0 = tutte) di questo passo
    CREATE TEMP TABLE omg_inc AS
    SELECT coalesce(s.league_id, 0)::bigint AS league_id,
           count(o.fixture_id)::integer AS d_minute,
           (count(*) FILTER (WHERE s.need_htft))::integer AS d_ht_ft
      FROM pg_temp.omg_fx s
      LEFT JOIN pg_temp.omg_ok o ON o.fixture_id = s.fixture_id
     GROUP BY GROUPING SETS ((s.league_id), ())
    HAVING (s.league_id IS NOT NULL OR GROUPING(s.league_id) = 1)
       AND (count(o.fixture_id) > 0 OR count(*) FILTER (WHERE s.need_htft) > 0);

    INSERT INTO public.omega_transitions_league_counts AS c (league_id, n_minute, n_ht_ft, updated_at)
    SELECT i.league_id, i.d_minute, i.d_ht_ft, now() FROM pg_temp.omg_inc i
    ON CONFLICT (league_id) DO UPDATE
       SET n_minute = c.n_minute + EXCLUDED.n_minute,
           n_ht_ft  = c.n_ht_ft  + EXCLUDED.n_ht_ft,
           updated_at = EXCLUDED.updated_at;

    IF v_published THEN
        -- partite valide per lega pubblicate (le legge anche tools/estrai_transizioni.py)
        INSERT INTO public.omega_minute_league_counts AS c (league_id, n)
        SELECT t.league_id, t.n_minute
          FROM public.omega_transitions_league_counts t
          JOIN pg_temp.omg_inc i ON i.league_id = t.league_id
         WHERE t.league_id <> 0 AND i.d_minute > 0
        ON CONFLICT (league_id) DO UPDATE SET n = EXCLUDED.n;
    END IF;

    -- (1) HT -> FT: grezzo, e pubblicato (tutte le leghe) se pubblicato
    WITH agg AS (
        SELECT coalesce(s.league_id, 0)::bigint AS league_id, s.ht, s.ft, count(*)::integer AS n
          FROM pg_temp.omg_fx s
         WHERE s.need_htft
         GROUP BY GROUPING SETS ((s.league_id, s.ht, s.ft), (s.ht, s.ft))
        HAVING s.league_id IS NOT NULL OR GROUPING(s.league_id) = 1
    ), ins AS (
        INSERT INTO public.omega_ht_ft_transitions_raw AS t (league_id, ht, ft, n, built_at)
        SELECT a.league_id, a.ht, a.ft, a.n, now() FROM agg a
        ON CONFLICT (league_id, ht, ft)
        DO UPDATE SET n = t.n + EXCLUDED.n, built_at = EXCLUDED.built_at
        RETURNING t.league_id, t.ht, t.ft, t.n
    )
    INSERT INTO public.omega_ht_ft_transitions AS p (league_id, ht, ft, n, built_at)
    SELECT i.league_id, i.ht, i.ft, i.n, now() FROM ins i
     WHERE v_published
    ON CONFLICT (league_id, ht, ft)
    DO UPDATE SET n = EXCLUDED.n, built_at = EXCLUDED.built_at;
    GET DIAGNOSTICS v_live_htft = ROW_COUNT;

    -- (2) PER MINUTO: stato (bucket x partita) delle sole partite coerenti
    IF v_minute > 0 THEN
        CREATE TEMP TABLE omg_state AS
        SELECT f.fixture_id, f.league_id, b.bucket, f.ht, f.ft,
               coalesce(sum(g.h) FILTER (WHERE g.minute <= b.bucket), 0)::text || '-' ||
               coalesce(sum(g.a) FILTER (WHERE g.minute <= b.bucket), 0)::text AS score
          FROM pg_temp.omg_fx f
          JOIN pg_temp.omg_ok o ON o.fixture_id = f.fixture_id
         CROSS JOIN (SELECT generate_series(0, 85, 5) AS bucket) b
          LEFT JOIN pg_temp.omg_goals g ON g.fixture_id = f.fixture_id
         GROUP BY f.fixture_id, f.league_id, b.bucket, f.ht, f.ft;

        WITH agg AS (
            SELECT coalesce(x.league_id, 0)::bigint AS league_id, x.bucket::smallint AS bucket,
                   x.score, x.target, x.result, count(*)::integer AS n
              FROM (
                SELECT NULL::bigint AS league_id, s.bucket, s.score, 'ft'::text AS target, s.ft AS result FROM pg_temp.omg_state s
                UNION ALL
                SELECT NULL::bigint, s.bucket, s.score, 'ht', s.ht FROM pg_temp.omg_state s WHERE s.bucket <= 40
                UNION ALL
                SELECT s.league_id, s.bucket, s.score, 'ft', s.ft FROM pg_temp.omg_state s WHERE s.league_id IS NOT NULL
                UNION ALL
                SELECT s.league_id, s.bucket, s.score, 'ht', s.ht FROM pg_temp.omg_state s WHERE s.league_id IS NOT NULL AND s.bucket <= 40
              ) x
             GROUP BY coalesce(x.league_id, 0), x.bucket, x.score, x.target, x.result
        ), ins AS (
            INSERT INTO public.omega_minute_transitions_raw AS t (league_id, bucket, score, target, result, n, built_at)
            SELECT a.league_id, a.bucket, a.score, a.target, a.result, a.n, now() FROM agg a
            ON CONFLICT (league_id, bucket, target, score, result)
            DO UPDATE SET n = t.n + EXCLUDED.n, built_at = EXCLUDED.built_at
            RETURNING t.league_id, t.bucket, t.score, t.target, t.result, t.n
        )
        INSERT INTO public.omega_minute_transitions AS p (league_id, bucket, score, target, result, n, built_at)
        SELECT i.league_id, i.bucket, i.score, i.target, i.result, i.n, now() FROM ins i
         WHERE v_published
           AND (i.league_id = 0
                OR EXISTS (SELECT 1 FROM public.omega_transitions_league_counts c
                            WHERE c.league_id = i.league_id AND c.n_minute >= v_min))
        ON CONFLICT (league_id, bucket, target, score, result)
        DO UPDATE SET n = EXCLUDED.n, built_at = EXCLUDED.built_at;
        GET DIAGNOSTICS v_live_min = ROW_COUNT;

        -- leghe che con QUESTO passo superano la soglia: si pubblicano per intero
        -- dal grezzo (i conteggi grezzi non si sono mai persi)
        IF v_published THEN
            INSERT INTO public.omega_minute_transitions AS p (league_id, bucket, score, target, result, n, built_at)
            SELECT r.league_id, r.bucket, r.score, r.target, r.result, r.n, now()
              FROM public.omega_minute_transitions_raw r
              JOIN pg_temp.omg_inc i ON i.league_id = r.league_id
              JOIN public.omega_transitions_league_counts c ON c.league_id = i.league_id
             WHERE i.league_id <> 0 AND i.d_minute > 0
               AND c.n_minute >= v_min AND c.n_minute - i.d_minute < v_min
            ON CONFLICT (league_id, bucket, target, score, result)
            DO UPDATE SET n = EXCLUDED.n, built_at = EXCLUDED.built_at;
            GET DIAGNOSTICS v_rows = ROW_COUNT;
            v_live_min := v_live_min + v_rows;
            SELECT count(*) INTO v_new_lg
              FROM pg_temp.omg_inc i
              JOIN public.omega_transitions_league_counts c ON c.league_id = i.league_id
             WHERE i.league_id <> 0 AND i.d_minute > 0
               AND c.n_minute >= v_min AND c.n_minute - i.d_minute < v_min;
        END IF;
    END IF;

    -- (3) REGISTRO: nella stessa transazione dei conteggi (idempotenza)
    INSERT INTO public.omega_transitions_ledger AS l
           (fixture_id, match_id, league_id, ht_ft_at, minute_at, minute_rejects, minute_checked_at)
    SELECT f.fixture_id, f.id, f.league_id,
           CASE WHEN f.need_htft THEN now() END,
           CASE WHEN o.fixture_id IS NOT NULL THEN now() END,
           CASE WHEN f.need_min AND o.fixture_id IS NULL THEN 1 ELSE 0 END,
           CASE WHEN f.need_min THEN now() END
      FROM pg_temp.omg_fx f
      LEFT JOIN pg_temp.omg_ok o ON o.fixture_id = f.fixture_id
    ON CONFLICT (fixture_id) DO UPDATE
       SET ht_ft_at          = coalesce(l.ht_ft_at, EXCLUDED.ht_ft_at),
           minute_at         = coalesce(l.minute_at, EXCLUDED.minute_at),
           minute_rejects    = l.minute_rejects + EXCLUDED.minute_rejects,
           minute_checked_at = coalesce(EXCLUDED.minute_checked_at, l.minute_checked_at);

    DROP TABLE IF EXISTS pg_temp.omg_state;
    DROP TABLE IF EXISTS pg_temp.omg_inc;
    DROP TABLE IF EXISTS pg_temp.omg_ok;
    DROP TABLE IF EXISTS pg_temp.omg_goals;
    DROP TABLE IF EXISTS pg_temp.omg_fx;
    RETURN jsonb_build_object('scanned', v_scan, 'ht_ft_counted', v_htft,
                              'minute_counted', v_minute, 'minute_rejected', v_rej,
                              'live_minute_upserts', v_live_min, 'live_ht_ft_upserts', v_live_htft,
                              'new_leagues', v_new_lg);
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_step(bigint,bigint,bigint[],integer) FROM public, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. IL GIRO NOTTURNO: passi finche' c'e' lavoro o finche' dura il budget.
--    Fasi, in quest'ordine:
--      A. finestra calda: partite FT con fixture_date negli ultimi p_hot_days
--         giorni non ancora contate (quelle entrate in matches prima di finire);
--      B. cursore per id: ricostruzione (dal 0 alla prima notte) e poi righe nuove;
--      C. giro di controllo (solo a ricostruzione finita): p_sweep_ids id a notte,
--         a rotazione su tutto lo spazio id (partite finite tardi fuori finestra,
--         scartate per eventi mancanti da ricontrollare).
--    p_dry_run = true: stesso lavoro, poi ANNULLATO (sottotransazione); resta
--    solo la riga di referto con i numeri.
--    Una sola transazione (una sola sottotransazione, niente subxact per passo).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_transitions_nightly(
    p_budget_s    integer DEFAULT 600,
    p_dry_run     boolean DEFAULT false,
    p_batch       integer DEFAULT 5000,
    p_hot_days    integer DEFAULT 10,
    p_sweep_ids   integer DEFAULT 100000,
    p_retry_hours integer DEFAULT 20
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_t0        timestamptz := clock_timestamp();
    v_batch     integer := least(greatest(coalesce(p_batch, 5000), 100), 50000);
    v_retry     timestamptz := now() - make_interval(hours => greatest(coalesce(p_retry_hours, 20), 1));
    v_st        public.omega_transitions_state;
    v_max       bigint;
    v_has_idx   boolean;
    v_hot       bigint[];
    v_i         integer;
    v_res       jsonb;
    v_cursor    bigint;
    v_hi        bigint;
    v_sweep     bigint;
    v_sweep_end bigint;
    v_cycles    integer;
    v_boot_done timestamptz;
    v_boot_start timestamptz;
    v_status    text := 'ok';
    v_err       text;
    v_steps     integer := 0;
    v_scan      bigint := 0;
    v_htft      bigint := 0;
    v_minute    bigint := 0;
    v_rej       bigint := 0;
    v_live_min  bigint := 0;
    v_live_htft bigint := 0;
    v_new_lg    integer := 0;
    v_hot_n     integer := 0;
    v_cur_from  bigint;
    v_sw_from   bigint;
    v_published boolean;
    v_out       jsonb;
BEGIN
    IF NOT pg_try_advisory_xact_lock(hashtext('omega_transitions')) THEN
        INSERT INTO public.omega_transitions_runs (started_at, dry_run, status, params)
        VALUES (v_t0, coalesce(p_dry_run, false), 'busy',
                jsonb_build_object('budget_s', p_budget_s));
        RETURN jsonb_build_object('status', 'busy',
                                  'note', 'un altro giro (pg_cron o manuale) sta lavorando: riprova');
    END IF;

    INSERT INTO public.omega_transitions_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
    SELECT * INTO v_st FROM public.omega_transitions_state WHERE id = 1 FOR UPDATE;
    v_published := v_st.published_at IS NOT NULL;
    v_cur_from := v_st.id_cursor;
    v_sw_from  := v_st.sweep_cursor;

    -- la finestra calda si fa SOLO con l'indice su fixture_date (niente seq scan di matches)
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE schemaname = 'public' AND tablename = 'matches'
           AND indexdef ILIKE '%(fixture_date)%'
    ) INTO v_has_idx;

    BEGIN   -- sottotransazione: annullata per il dry-run o per un errore
        SELECT max(id) INTO v_max FROM public.matches;
        v_max := coalesce(v_max, 0);
        v_cursor := v_st.id_cursor;
        v_sweep := v_st.sweep_cursor;
        v_cycles := v_st.sweep_cycles;
        v_boot_done := v_st.bootstrap_done_at;
        v_boot_start := coalesce(v_st.bootstrap_started_at, now());

        -- A. finestra calda
        IF v_has_idx THEN
            SELECT coalesce(array_agg(m.id ORDER BY m.id), '{}'::bigint[])
              INTO v_hot
              FROM public.matches m
             WHERE m.status_short IN ('FT', 'AET', 'PEN')      -- predicato dell'indice parziale
               AND m.status_short = 'FT'
               AND m.fixture_date >= now() - make_interval(days => greatest(coalesce(p_hot_days, 10), 1))
               AND m.fixture_id IS NOT NULL
               AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
               AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM public.omega_transitions_ledger l
                    WHERE l.fixture_id = m.fixture_id
                      AND l.ht_ft_at IS NOT NULL
                      AND (l.minute_at IS NOT NULL OR l.minute_checked_at >= v_retry));
            v_hot_n := coalesce(cardinality(v_hot), 0);
            v_i := 1;
            WHILE v_i <= v_hot_n LOOP
                EXIT WHEN extract(epoch FROM clock_timestamp() - v_t0) >= p_budget_s;
                v_res := public.omega_transitions_step(NULL, NULL, v_hot[v_i : v_i + v_batch - 1], p_retry_hours);
                v_steps := v_steps + 1;
                v_scan := v_scan + (v_res->>'scanned')::bigint;
                v_htft := v_htft + (v_res->>'ht_ft_counted')::bigint;
                v_minute := v_minute + (v_res->>'minute_counted')::bigint;
                v_rej := v_rej + (v_res->>'minute_rejected')::bigint;
                v_live_min := v_live_min + (v_res->>'live_minute_upserts')::bigint;
                v_live_htft := v_live_htft + (v_res->>'live_ht_ft_upserts')::bigint;
                v_new_lg := v_new_lg + (v_res->>'new_leagues')::integer;
                v_i := v_i + v_batch;
            END LOOP;
            IF v_i <= v_hot_n THEN
                v_status := 'budget';
            END IF;
        END IF;

        -- B. cursore per id (ricostruzione, poi righe nuove)
        WHILE v_cursor < v_max LOOP
            IF extract(epoch FROM clock_timestamp() - v_t0) >= p_budget_s THEN
                v_status := 'budget';
                EXIT;
            END IF;
            v_hi := least(v_cursor + v_batch, v_max);
            v_res := public.omega_transitions_step(v_cursor, v_hi, NULL, p_retry_hours);
            v_steps := v_steps + 1;
            v_scan := v_scan + (v_res->>'scanned')::bigint;
            v_htft := v_htft + (v_res->>'ht_ft_counted')::bigint;
            v_minute := v_minute + (v_res->>'minute_counted')::bigint;
            v_rej := v_rej + (v_res->>'minute_rejected')::bigint;
            v_live_min := v_live_min + (v_res->>'live_minute_upserts')::bigint;
            v_live_htft := v_live_htft + (v_res->>'live_ht_ft_upserts')::bigint;
            v_new_lg := v_new_lg + (v_res->>'new_leagues')::integer;
            v_cursor := v_hi;
        END LOOP;
        IF v_cursor >= v_max AND v_boot_done IS NULL THEN
            v_boot_done := now();
        END IF;

        -- C. giro di controllo a rotazione (solo a ricostruzione finita)
        IF v_boot_done IS NOT NULL AND v_status = 'ok' AND coalesce(p_sweep_ids, 0) > 0 THEN
            v_sweep_end := least(v_sweep + p_sweep_ids, v_max);
            WHILE v_sweep < v_sweep_end LOOP
                IF extract(epoch FROM clock_timestamp() - v_t0) >= p_budget_s THEN
                    v_status := 'budget';
                    EXIT;
                END IF;
                v_hi := least(v_sweep + v_batch, v_sweep_end);
                v_res := public.omega_transitions_step(v_sweep, v_hi, NULL, p_retry_hours);
                v_steps := v_steps + 1;
                v_scan := v_scan + (v_res->>'scanned')::bigint;
                v_htft := v_htft + (v_res->>'ht_ft_counted')::bigint;
                v_minute := v_minute + (v_res->>'minute_counted')::bigint;
                v_rej := v_rej + (v_res->>'minute_rejected')::bigint;
                v_live_min := v_live_min + (v_res->>'live_minute_upserts')::bigint;
                v_live_htft := v_live_htft + (v_res->>'live_ht_ft_upserts')::bigint;
                v_new_lg := v_new_lg + (v_res->>'new_leagues')::integer;
                v_sweep := v_hi;
            END LOOP;
            IF v_sweep >= v_max THEN
                v_sweep := 0;
                v_cycles := v_cycles + 1;
            END IF;
        END IF;

        UPDATE public.omega_transitions_state
           SET id_cursor = v_cursor,
               sweep_cursor = v_sweep,
               sweep_cycles = v_cycles,
               bootstrap_started_at = v_boot_start,
               bootstrap_done_at = v_boot_done,
               updated_at = now()
         WHERE id = 1;

        IF coalesce(p_dry_run, false) THEN
            RAISE EXCEPTION USING ERRCODE = 'OT001', MESSAGE = 'omega_transitions dry-run: annullo';
        END IF;
    EXCEPTION
        WHEN SQLSTATE 'OT001' THEN
            v_status := 'dry_run';
        WHEN OTHERS THEN
            -- tutto il lavoro del giro e' annullato: i cursori restano dov'erano,
            -- i contatori del referto dicono cosa si era TENTATO
            v_status := 'errore';
            v_err := SQLSTATE || ' ' || SQLERRM;
            v_cursor := v_cur_from;
            v_sweep := v_sw_from;
    END;

    INSERT INTO public.omega_transitions_runs
           (started_at, finished_at, elapsed_s, dry_run, status, published, steps, scanned,
            ht_ft_counted, minute_counted, minute_rejected, hot_candidates, hot_skipped_no_index,
            id_cursor_from, id_cursor_to, max_id, sweep_from, sweep_to,
            live_minute_upserts, live_ht_ft_upserts, new_leagues, error, params)
    VALUES (v_t0, clock_timestamp(),
            round(extract(epoch FROM clock_timestamp() - v_t0)::numeric, 1),
            coalesce(p_dry_run, false), v_status, v_published, v_steps, v_scan,
            v_htft, v_minute, v_rej, v_hot_n, NOT v_has_idx,
            v_cur_from, v_cursor, v_max, v_sw_from, v_sweep,
            v_live_min, v_live_htft, v_new_lg, v_err,
            jsonb_build_object('budget_s', p_budget_s, 'batch', v_batch, 'hot_days', p_hot_days,
                               'sweep_ids', p_sweep_ids, 'retry_hours', p_retry_hours));

    v_out := jsonb_build_object(
        'status', v_status, 'dry_run', coalesce(p_dry_run, false), 'published', v_published,
        'steps', v_steps, 'scanned', v_scan, 'ht_ft_counted', v_htft,
        'minute_counted', v_minute, 'minute_rejected', v_rej,
        'hot_candidates', v_hot_n, 'hot_skipped_no_index', NOT v_has_idx,
        'id_cursor_from', v_cur_from, 'id_cursor_to', v_cursor, 'max_id', v_max,
        'sweep_from', v_sw_from, 'sweep_to', v_sweep,
        'bootstrap_done', v_boot_done IS NOT NULL,
        'live_minute_upserts', v_live_min, 'live_ht_ft_upserts', v_live_htft,
        'new_leagues', v_new_lg, 'error', v_err,
        'elapsed_s', round(extract(epoch FROM clock_timestamp() - v_t0)::numeric, 1));
    RETURN v_out;
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_nightly(integer,boolean,integer,integer,integer,integer) FROM public, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. PUBBLICAZIONE (una tantum, A MANO, dopo la verifica): le tabelle lette dai
--    bot prendono i conteggi ricostruiti, in UNA transazione (chi legge vede i
--    numeri vecchi fino al commit, poi i nuovi: mai tabelle a meta').
--    E' l'UNICO punto in cui si cancellano righe da omega_minute_transitions e
--    omega_ht_ft_transitions (piu' il ritorno indietro, sotto).
--    p_keep_backup: copia delle tabelle dell'11/09 per il confronto e il ritorno.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_transitions_publish(
    p_confirm             text,
    p_min_league_matches  integer DEFAULT 1000,
    p_keep_backup         boolean DEFAULT true,
    p_force               boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_st      public.omega_transitions_state;
    v_min     integer := greatest(coalesce(p_min_league_matches, 1000), 1);
    v_minute  bigint;
    v_htft    bigint;
    v_leagues bigint;
    v_backup  boolean := false;
BEGIN
    IF p_confirm IS DISTINCT FROM 'PUBBLICA' THEN
        RAISE EXCEPTION 'conferma mancante: SELECT public.omega_transitions_publish(''PUBBLICA'');';
    END IF;
    IF NOT pg_try_advisory_xact_lock(hashtext('omega_transitions')) THEN
        RAISE EXCEPTION 'un giro notturno sta lavorando: riprova fra qualche minuto';
    END IF;
    INSERT INTO public.omega_transitions_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
    SELECT * INTO v_st FROM public.omega_transitions_state WHERE id = 1 FOR UPDATE;
    IF v_st.bootstrap_done_at IS NULL AND NOT coalesce(p_force, false) THEN
        RAISE EXCEPTION 'ricostruzione non finita (id_cursor %): pubblicare ora darebbe conteggi parziali', v_st.id_cursor;
    END IF;

    IF coalesce(p_keep_backup, true)
       AND to_regclass('public.omega_minute_transitions_pre_ledger') IS NULL THEN
        CREATE TABLE public.omega_minute_transitions_pre_ledger AS
            SELECT * FROM public.omega_minute_transitions;
        CREATE TABLE public.omega_ht_ft_transitions_pre_ledger AS
            SELECT * FROM public.omega_ht_ft_transitions;
        CREATE TABLE public.omega_minute_league_counts_pre_ledger AS
            SELECT * FROM public.omega_minute_league_counts;
        ALTER TABLE public.omega_minute_transitions_pre_ledger ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.omega_ht_ft_transitions_pre_ledger ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.omega_minute_league_counts_pre_ledger ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE public.omega_minute_transitions_pre_ledger FROM anon, authenticated;
        REVOKE ALL ON TABLE public.omega_ht_ft_transitions_pre_ledger FROM anon, authenticated;
        REVOKE ALL ON TABLE public.omega_minute_league_counts_pre_ledger FROM anon, authenticated;
        GRANT SELECT ON TABLE public.omega_minute_transitions_pre_ledger TO service_role;
        GRANT SELECT ON TABLE public.omega_ht_ft_transitions_pre_ledger TO service_role;
        GRANT SELECT ON TABLE public.omega_minute_league_counts_pre_ledger TO service_role;
        v_backup := true;
    END IF;

    DELETE FROM public.omega_minute_league_counts;
    INSERT INTO public.omega_minute_league_counts (league_id, n)
    SELECT c.league_id, c.n_minute FROM public.omega_transitions_league_counts c
     WHERE c.league_id <> 0 AND c.n_minute > 0;
    SELECT count(*) INTO v_leagues FROM public.omega_minute_league_counts WHERE n >= v_min;

    DELETE FROM public.omega_minute_transitions;
    INSERT INTO public.omega_minute_transitions (league_id, bucket, score, target, result, n, built_at)
    SELECT r.league_id, r.bucket, r.score, r.target, r.result, r.n, now()
      FROM public.omega_minute_transitions_raw r
     WHERE r.league_id = 0
        OR EXISTS (SELECT 1 FROM public.omega_transitions_league_counts c
                    WHERE c.league_id = r.league_id AND c.n_minute >= v_min);
    GET DIAGNOSTICS v_minute = ROW_COUNT;

    DELETE FROM public.omega_ht_ft_transitions;
    INSERT INTO public.omega_ht_ft_transitions (league_id, ht, ft, n, built_at)
    SELECT r.league_id, r.ht, r.ft, r.n, now() FROM public.omega_ht_ft_transitions_raw r;
    GET DIAGNOSTICS v_htft = ROW_COUNT;

    UPDATE public.omega_transitions_state
       SET published_at = now(), min_league_matches = v_min, updated_at = now()
     WHERE id = 1;

    RETURN jsonb_build_object('published', true, 'minute_rows', v_minute, 'ht_ft_rows', v_htft,
                              'leagues_admitted', v_leagues, 'min_league_matches', v_min,
                              'backup_created', v_backup,
                              'note', 'dopo: VACUUM (ANALYZE) public.omega_minute_transitions; VACUUM (ANALYZE) public.omega_ht_ft_transitions;');
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_publish(text,integer,boolean,boolean) FROM public, anon, authenticated, service_role;

-- ritorno ai numeri dell'11/09 (dalla copia fatta alla pubblicazione); la
-- ricostruzione grezza e il registro restano: si ripubblica quando si vuole
CREATE OR REPLACE FUNCTION public.omega_transitions_unpublish(p_confirm text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_minute bigint;
    v_htft   bigint;
BEGIN
    IF p_confirm IS DISTINCT FROM 'RITORNA' THEN
        RAISE EXCEPTION 'conferma mancante: SELECT public.omega_transitions_unpublish(''RITORNA'');';
    END IF;
    IF to_regclass('public.omega_minute_transitions_pre_ledger') IS NULL THEN
        RAISE EXCEPTION 'copia dell''11/09 assente (pubblicazione fatta con p_keep_backup = false)';
    END IF;
    IF NOT pg_try_advisory_xact_lock(hashtext('omega_transitions')) THEN
        RAISE EXCEPTION 'un giro notturno sta lavorando: riprova fra qualche minuto';
    END IF;
    DELETE FROM public.omega_minute_transitions;
    EXECUTE 'INSERT INTO public.omega_minute_transitions SELECT * FROM public.omega_minute_transitions_pre_ledger';
    GET DIAGNOSTICS v_minute = ROW_COUNT;
    DELETE FROM public.omega_ht_ft_transitions;
    EXECUTE 'INSERT INTO public.omega_ht_ft_transitions SELECT * FROM public.omega_ht_ft_transitions_pre_ledger';
    GET DIAGNOSTICS v_htft = ROW_COUNT;
    DELETE FROM public.omega_minute_league_counts;
    EXECUTE 'INSERT INTO public.omega_minute_league_counts SELECT * FROM public.omega_minute_league_counts_pre_ledger';
    UPDATE public.omega_transitions_state SET published_at = NULL, updated_at = now() WHERE id = 1;
    RETURN jsonb_build_object('published', false, 'minute_rows', v_minute, 'ht_ft_rows', v_htft);
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_unpublish(text) FROM public, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5. LETTURE PER LA VERIFICA (sola lettura, service_role): lo script
--    Betfair/omega/tools/verifica_transizioni_2026_09_25.py
-- ----------------------------------------------------------------------------
-- partite nel registro per lega, contate ORA dal registro (non dai contatori)
CREATE OR REPLACE FUNCTION public.omega_transitions_ledger_counts()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'league_id', x.league_id, 'n_minute', x.n_minute, 'n_ht_ft', x.n_ht_ft,
               'n_rejected_open', x.n_rej) ORDER BY x.league_id), '[]'::jsonb)
      FROM (
        SELECT coalesce(l.league_id, 0) AS league_id,
               count(*) FILTER (WHERE l.minute_at IS NOT NULL) AS n_minute,
               count(*) FILTER (WHERE l.ht_ft_at IS NOT NULL) AS n_ht_ft,
               count(*) FILTER (WHERE l.minute_at IS NULL AND l.minute_rejects > 0) AS n_rej
          FROM public.omega_transitions_ledger l
         GROUP BY GROUPING SETS ((l.league_id), ())
        HAVING l.league_id IS NOT NULL OR GROUPING(l.league_id) = 1
      ) x;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_ledger_counts() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_transitions_ledger_counts() TO service_role;

-- confronto cella per cella: 'pre' = pubblicato (11/09) contro grezzo ammesso;
-- 'post' = copia dell'11/09 contro pubblicato
CREATE OR REPLACE FUNCTION public.omega_transitions_compare(
    p_mode text DEFAULT 'pre',
    p_min_league_matches integer DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_min      integer;
    v_old_min  text;
    v_new_min  text;
    v_old_htft text;
    v_new_htft text;
    v_m        jsonb;
    v_h        jsonb;
BEGIN
    SELECT coalesce(p_min_league_matches, s.min_league_matches) INTO v_min
      FROM public.omega_transitions_state s WHERE s.id = 1;
    v_min := coalesce(v_min, 1000);
    IF p_mode = 'pre' THEN
        v_old_min  := 'SELECT league_id, bucket, score, target, result, n FROM public.omega_minute_transitions';
        v_new_min  := format('SELECT r.league_id, r.bucket, r.score, r.target, r.result, r.n
                                FROM public.omega_minute_transitions_raw r
                               WHERE r.league_id = 0 OR EXISTS (SELECT 1 FROM public.omega_transitions_league_counts c
                                                                 WHERE c.league_id = r.league_id AND c.n_minute >= %s)', v_min);
        v_old_htft := 'SELECT league_id, ht, ft, n FROM public.omega_ht_ft_transitions';
        v_new_htft := 'SELECT league_id, ht, ft, n FROM public.omega_ht_ft_transitions_raw';
    ELSIF p_mode = 'post' THEN
        IF to_regclass('public.omega_minute_transitions_pre_ledger') IS NULL THEN
            RAISE EXCEPTION 'copia dell''11/09 assente: il confronto post non si puo'' fare';
        END IF;
        v_old_min  := 'SELECT league_id, bucket, score, target, result, n FROM public.omega_minute_transitions_pre_ledger';
        v_new_min  := 'SELECT league_id, bucket, score, target, result, n FROM public.omega_minute_transitions';
        v_old_htft := 'SELECT league_id, ht, ft, n FROM public.omega_ht_ft_transitions_pre_ledger';
        v_new_htft := 'SELECT league_id, ht, ft, n FROM public.omega_ht_ft_transitions';
    ELSE
        RAISE EXCEPTION 'p_mode non valido: % (pre | post)', p_mode;
    END IF;

    EXECUTE format($q$
        SELECT jsonb_build_object(
            'cells_old', count(o_n), 'cells_new', count(w_n),
            'cells_equal', count(*) FILTER (WHERE w_n = o_n),
            'cells_grown', count(*) FILTER (WHERE w_n > o_n),
            'cells_lower', count(*) FILTER (WHERE w_n < o_n),
            'deficit_sum', coalesce(sum(o_n - w_n) FILTER (WHERE w_n < o_n), 0),
            'cells_missing', count(*) FILTER (WHERE w_n IS NULL),
            'cells_added', count(*) FILTER (WHERE o_n IS NULL),
            'matches_global_old', coalesce(sum(o_n) FILTER (WHERE lg = 0 AND bk = 0 AND tg = 'ft'), 0),
            'matches_global_new', coalesce(sum(w_n) FILTER (WHERE lg = 0 AND bk = 0 AND tg = 'ft'), 0),
            'leagues_old', count(DISTINCT lg) FILTER (WHERE o_n IS NOT NULL AND lg <> 0),
            'leagues_new', count(DISTINCT lg) FILTER (WHERE w_n IS NOT NULL AND lg <> 0))
          FROM (SELECT coalesce(o.league_id, w.league_id) AS lg, coalesce(o.bucket, w.bucket) AS bk,
                       coalesce(o.target, w.target) AS tg, o.n AS o_n, w.n AS w_n
                  FROM (%s) o FULL JOIN (%s) w
                    ON w.league_id = o.league_id AND w.bucket = o.bucket AND w.target = o.target
                   AND w.score = o.score AND w.result = o.result) j
    $q$, v_old_min, v_new_min) INTO v_m;

    EXECUTE format($q$
        SELECT jsonb_build_object(
            'cells_old', count(o_n), 'cells_new', count(w_n),
            'cells_equal', count(*) FILTER (WHERE w_n = o_n),
            'cells_grown', count(*) FILTER (WHERE w_n > o_n),
            'cells_lower', count(*) FILTER (WHERE w_n < o_n),
            'deficit_sum', coalesce(sum(o_n - w_n) FILTER (WHERE w_n < o_n), 0),
            'cells_missing', count(*) FILTER (WHERE w_n IS NULL),
            'cells_added', count(*) FILTER (WHERE o_n IS NULL),
            'matches_global_old', coalesce(sum(o_n) FILTER (WHERE lg = 0), 0),
            'matches_global_new', coalesce(sum(w_n) FILTER (WHERE lg = 0), 0),
            'leagues_old', count(DISTINCT lg) FILTER (WHERE o_n IS NOT NULL AND lg <> 0),
            'leagues_new', count(DISTINCT lg) FILTER (WHERE w_n IS NOT NULL AND lg <> 0))
          FROM (SELECT coalesce(o.league_id, w.league_id) AS lg, o.n AS o_n, w.n AS w_n
                  FROM (%s) o FULL JOIN (%s) w
                    ON w.league_id = o.league_id AND w.ht = o.ht AND w.ft = o.ft) j
    $q$, v_old_htft, v_new_htft) INTO v_h;

    RETURN jsonb_build_object('mode', p_mode, 'min_league_matches', v_min,
                              'minute', v_m, 'ht_ft', v_h);
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_compare(text,integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_transitions_compare(text,integer) TO service_role;

-- stato complessivo: registro, cursori, ultimi giri, pg_cron, indici
CREATE OR REPLACE FUNCTION public.omega_transitions_status()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_state jsonb;
    v_runs  jsonb;
    v_cron  jsonb := NULL;
    v_det   jsonb := NULL;
    v_has_cron boolean;
BEGIN
    SELECT to_jsonb(s) INTO v_state FROM public.omega_transitions_state s WHERE s.id = 1;
    SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.id DESC), '[]'::jsonb) INTO v_runs
      FROM (SELECT * FROM public.omega_transitions_runs ORDER BY id DESC LIMIT 10) r;
    v_has_cron := EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron');
    IF v_has_cron THEN
        EXECUTE $q$SELECT coalesce(jsonb_agg(jsonb_build_object('jobname', j.jobname, 'schedule', j.schedule,
                                                     'command', j.command, 'active', j.active)
                                   ORDER BY j.jobname), '[]'::jsonb)
                     FROM cron.job j WHERE j.jobname LIKE 'omega%'$q$ INTO v_cron;
        EXECUTE $q$SELECT coalesce(jsonb_agg(jsonb_build_object('status', d.status, 'start_time', d.start_time,
                                                     'end_time', d.end_time, 'return_message', d.return_message)
                                   ORDER BY d.start_time DESC), '[]'::jsonb)
                     FROM (SELECT d.* FROM cron.job_run_details d
                             JOIN cron.job j ON j.jobid = d.jobid
                            WHERE j.jobname = 'omega_transitions_nightly'
                            ORDER BY d.start_time DESC LIMIT 5) d$q$ INTO v_det;
    END IF;
    RETURN jsonb_build_object(
        'state', v_state,
        'runs', v_runs,
        'pg_cron', v_has_cron,
        'cron_jobs', v_cron,
        'cron_last_runs', v_det,
        'index_matches_fixture_date', EXISTS (SELECT 1 FROM pg_indexes
                                               WHERE schemaname = 'public' AND tablename = 'matches'
                                                 AND indexdef ILIKE '%(fixture_date)%'),
        'index_match_events_goal', EXISTS (SELECT 1 FROM pg_indexes
                                            WHERE schemaname = 'public' AND tablename = 'match_events'
                                              AND indexname = 'idx_match_events_goal_fixture'),
        'backup_pre_ledger', to_regclass('public.omega_minute_transitions_pre_ledger') IS NOT NULL,
        'league_counts_global', (SELECT to_jsonb(c) FROM public.omega_transitions_league_counts c WHERE c.league_id = 0),
        'now', now());
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_status() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_transitions_status() TO service_role;

-- ----------------------------------------------------------------------------
-- 6. I VECCHI COSTRUTTORI SI SPENGONO: sommavano senza registro (un rilancio o un
--    "riapri il job" contava due volte, un reset svuotava le tabelle lette dai
--    bot). Stesse firme, corpo che rifiuta e indica la strada nuova.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_reset()
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'dismessa il 25/09 (conteggi senza registro): usare public.omega_transitions_nightly';
END;
$$;
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_step(
    p_batch integer DEFAULT 5000,
    p_min_league_matches integer DEFAULT 1000
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'dismessa il 25/09 (conteggi senza registro): usare public.omega_transitions_nightly';
END;
$$;
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_run(
    p_seconds integer DEFAULT 90,
    p_batch integer DEFAULT 5000
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'dismessa il 25/09 (conteggi senza registro): usare public.omega_transitions_nightly';
END;
$$;
CREATE OR REPLACE FUNCTION public.omega_build_minute_transitions_schedule()
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'dismessa il 25/09: usare public.omega_transitions_schedule(true)';
END;
$$;
CREATE OR REPLACE FUNCTION public.omega_build_ht_ft_transitions()
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'dismessa il 25/09 (ricostruzione senza registro): usare public.omega_transitions_nightly';
END;
$$;

-- ----------------------------------------------------------------------------
-- 7. PG_CRON: ogni notte alle 04:00 UTC. Idempotente (toglie il job se c'e',
--    poi lo rimette); se pg_cron manca lo dice e non fa nulla.
--    Il comando alza statement_timeout per il SOLO giro (budget 600 s + ultimo
--    passo): un timeout di ruolo piu' basso cancellerebbe il giro a meta'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_transitions_schedule(p_enable boolean DEFAULT true)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RETURN 'pg_cron non attivo: lanciare a mano ogni giorno SELECT public.omega_transitions_nightly(90); (anche piu'' volte: e'' idempotente)';
    END IF;
    -- il vecchio costruttore a minuto, se mai schedulato, non deve piu' girare
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'omega_minute_build') THEN
        PERFORM cron.unschedule('omega_minute_build');
    END IF;
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'omega_transitions_nightly') THEN
        PERFORM cron.unschedule('omega_transitions_nightly');
    END IF;
    IF NOT coalesce(p_enable, true) THEN
        RETURN 'omega_transitions_nightly tolto da pg_cron';
    END IF;
    PERFORM cron.schedule('omega_transitions_nightly', '0 4 * * *',
        $cmd$SET statement_timeout = '20min'; SELECT public.omega_transitions_nightly(600);$cmd$);
    RETURN 'schedulato: omega_transitions_nightly ogni giorno alle 04:00 UTC (budget 600 s)';
END;
$$;
REVOKE ALL ON FUNCTION public.omega_transitions_schedule(boolean) FROM public, anon, authenticated, service_role;

SELECT public.omega_transitions_schedule(true);

-- ----------------------------------------------------------------------------
-- USO (dettagli e numeri in Betfair/omega/TRANSIZIONI_NOTTURNE_2026-09-25.md):
--   stato:        SELECT public.omega_transitions_status();
--   prova:        SELECT public.omega_transitions_nightly(60, true);   -- conta e annulla
--   a mano:       SELECT public.omega_transitions_nightly(90);          -- ripetibile
--   confronto:    SELECT public.omega_transitions_compare('pre');
--   pubblica:     SELECT public.omega_transitions_publish('PUBBLICA');
--   ritorno:      SELECT public.omega_transitions_unpublish('RITORNA');
--   pg_cron:      SELECT public.omega_transitions_schedule(true | false);
-- ----------------------------------------------------------------------------
