-- ============================================================================
-- tennis_bots.sql — controllo multi-bot DEDICATO al TENNIS (arm/disarm/state).
--
-- BACKEND DEDICATO AL TENNIS. Regola d'oro (richiesta esplicita utente): Tennis e
-- Calcio NON condividono MAI dati. Questo file crea solo tabelle/RPC `tennis_*` e
-- non tocca alcuna tabella/RPC del calcio (nessuna contaminazione). Mirror di
-- scalper_bot.sql (control table + arm/stop/state), esteso a PIÙ bot per-evento.
--
-- Flusso (contratto frozen frontend/src/lib/tennis.ts):
--   frontend → tennis_bot_arm(...)     -> json TennisBotControl (status 'requested')
--   frontend → tennis_bot_disarm(...)  -> json TennisBotControl (status 'stopping')
--   frontend → get_tennis_bots_state(...) -> json {controls[], activity[]}
-- Il servizio locale tennis (tennis_bot_service.py) legge tennis_bot_control via
-- service_role, avvia/ferma i bot e scrive stato/heartbeat/stats + log append-only
-- in tennis_bot_activity.
--
-- OWNER-ONLY (può muovere denaro reale con dry_run=false). IDEMPOTENTE. RPC
-- SECURITY DEFINER, search_path fisso.
-- ============================================================================

-- ============================================================================
-- 0)  tennis_is_owner — guard OWNER-ONLY dedicato al tennis (vedi tennis_orders.sql).
-- Ridefinito QUI (CREATE OR REPLACE, idempotente) per mantenere i file tennis
-- autoconsistenti a prescindere dall'ordine di applicazione.
-- (Se cambi email owner: aggiornala anche in tennis_orders.sql, security_lockdown.sql,
--  src/lib/auth-config.ts.)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.tennis_is_owner()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT
        coalesce(auth.jwt() ->> 'role', '') = 'service_role'
        OR session_user = 'service_role'
        OR lower(coalesce(auth.jwt() ->> 'email', '')) = 'daniele.ritrovato@gmail.com';
$$;
REVOKE ALL    ON FUNCTION public.tennis_is_owner() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_is_owner() TO service_role;

-- ============================================================================
-- 1)  tennis_bot_control — una riga per (event_id, bot_key). Più bot armabili in
-- contemporanea sullo stesso evento (l'ultima attivazione per bot vince).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tennis_bot_control (
    event_id     TEXT NOT NULL,
    bot_key      TEXT NOT NULL
                    CHECK (bot_key IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')),
    status       TEXT NOT NULL DEFAULT 'requested'
                    CHECK (status IN ('idle','requested','arming','armed','running',
                                      'stopping','stopped','done','error')),
    dry_run      BOOLEAN NOT NULL DEFAULT TRUE,
    stake        NUMERIC NOT NULL DEFAULT 5 CHECK (stake >= 0 AND stake <= 100000),
    params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats        JSONB,                                  -- TennisBotStats
    error        TEXT,
    market_id    TEXT,                                   -- valorizzato dal servizio/runner
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    stopped_at   TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, bot_key)
);

ALTER TABLE public.tennis_bot_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_bot_control FROM anon, authenticated;

-- ============================================================================
-- 2)  tennis_bot_activity — log APPEND-ONLY per debug/analisi (arm, place, cancel,
-- fill, scratch, stop, cycle, flatten, state, error, info, ...).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tennis_bot_activity (
    id        BIGSERIAL PRIMARY KEY,
    event_id  TEXT NOT NULL,
    bot_key   TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind      TEXT NOT NULL,
    payload   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_tennis_bot_activity_event_ts
    ON public.tennis_bot_activity (event_id, ts DESC);

ALTER TABLE public.tennis_bot_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_bot_activity FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_bot_activity_id_seq FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- Helper interno: serializza una riga di controllo come TennisBotControl.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public._tennis_bot_control_json(c public.tennis_bot_control)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'event_id',     c.event_id,
        'bot_key',      c.bot_key,
        'status',       c.status,
        'dry_run',      c.dry_run,
        'stake',        c.stake,
        'params',       c.params,
        'stats',        c.stats,
        'error',        c.error,
        'requested_at', c.requested_at,
        'started_at',   c.started_at,
        'stopped_at',   c.stopped_at,
        'heartbeat_at', c.heartbeat_at
    );
$$;
REVOKE ALL ON FUNCTION public._tennis_bot_control_json(public.tennis_bot_control) FROM public, anon;
GRANT EXECUTE ON FUNCTION public._tennis_bot_control_json(public.tennis_bot_control) TO service_role;

-- ============================================================================
-- RPC 1: tennis_bot_arm(p_event_id,p_bot_key,p_dry_run,p_stake,p_params)
--        -> json TennisBotControl. Upsert → status 'requested'. Ri-armare un bot
--        fermo = nuova richiesta (reset error/stopped_at/stats).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.tennis_bot_arm(
    p_event_id text,
    p_bot_key  text,
    p_dry_run  boolean,
    p_stake    numeric,
    p_params   jsonb
) RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_bot_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_bot_key NOT IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing') THEN
        RAISE EXCEPTION 'bot_key non valido: %', p_bot_key;
    END IF;
    IF p_stake IS NULL OR p_stake < 0 OR p_stake > 100000 THEN
        RAISE EXCEPTION 'stake fuori range [0,100000]: %', p_stake;
    END IF;

    INSERT INTO public.tennis_bot_control AS c
        (event_id, bot_key, status, dry_run, stake, params, stats, error,
         requested_at, started_at, stopped_at, heartbeat_at, updated_at)
    VALUES
        (p_event_id, p_bot_key, 'requested', coalesce(p_dry_run, true),
         p_stake, coalesce(p_params, '{}'::jsonb), NULL, NULL,
         now(), NULL, NULL, NULL, now())
    ON CONFLICT (event_id, bot_key) DO UPDATE SET
        status       = 'requested',
        dry_run      = EXCLUDED.dry_run,
        stake        = EXCLUDED.stake,
        params       = EXCLUDED.params,
        stats        = NULL,
        error        = NULL,
        requested_at = now(),
        started_at   = NULL,
        stopped_at   = NULL,
        updated_at   = now()
    RETURNING * INTO v_row;

    RETURN public._tennis_bot_control_json(v_row)::json;
END;
$$;

-- ============================================================================
-- RPC 2: tennis_bot_disarm(p_event_id,p_bot_key) -> json TennisBotControl.
-- Il servizio vede 'stopping' (chiude flat) e poi mette 'stopped'. Se il bot non è
-- attivo va direttamente a 'stopped'.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.tennis_bot_disarm(p_event_id text, p_bot_key text)
RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_bot_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    UPDATE public.tennis_bot_control
       SET status = CASE WHEN status IN ('running','arming','armed','requested')
                         THEN 'stopping' ELSE 'stopped' END,
           updated_at = now()
     WHERE event_id = p_event_id AND bot_key = p_bot_key
    RETURNING * INTO v_row;

    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'nessuna attivazione bot % per %', p_bot_key, p_event_id;
    END IF;
    RETURN public._tennis_bot_control_json(v_row)::json;
END;
$$;

-- ============================================================================
-- RPC 3: get_tennis_bots_state(p_event_id,p_activity_limit)
--        -> json {controls: TennisBotControl[], activity: TennisBotActivityRow[]}.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_bots_state(
    p_event_id       text,
    p_activity_limit integer DEFAULT 60
) RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_controls jsonb;
    v_activity jsonb;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;

    SELECT coalesce(jsonb_agg(public._tennis_bot_control_json(c) ORDER BY c.bot_key), '[]'::jsonb)
      INTO v_controls
      FROM public.tennis_bot_control c
     WHERE c.event_id = p_event_id;

    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_activity
      FROM (
        SELECT * FROM public.tennis_bot_activity
         WHERE event_id = p_event_id
         ORDER BY ts DESC
         LIMIT least(greatest(coalesce(p_activity_limit, 60), 1), 500)
      ) a;

    RETURN json_build_object('controls', v_controls, 'activity', v_activity);
END;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- ============================================================================
REVOKE ALL    ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.tennis_bot_disarm(text,text)         FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_disarm(text,text)         TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_bots_state(text,integer)  FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bots_state(text,integer)  TO authenticated, service_role;
