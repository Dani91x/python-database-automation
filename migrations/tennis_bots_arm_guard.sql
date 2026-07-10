-- ============================================================================
-- tennis_bots_arm_guard.sql — GUARD anti re-arm sulla RPC tennis_bot_arm.
--
-- BUG (audit 2026-07-10): ri-armare un bot GIÀ attivo azzerava stats/params via
-- upsert, ma il runner NON re-istanzia la strategia già ospitata → il bot
-- continuava a girare coi VECCHI parametri mentre il DB mostrava i nuovi
-- ("param fantasma") e le stats ripartivano da zero (contabilità falsata).
--
-- FIX: se esiste già una riga (event_id, bot_key) con status attivo
-- ('requested','arming','armed','running') la RPC RIFIUTA con un errore chiaro:
-- si disarma prima, POI si riarma coi nuovi parametri.
--
-- IDEMPOTENTE (CREATE OR REPLACE). Testo base: migrations/tennis_bots.sql
-- (RPC tennis_bot_arm) + il guard. OWNER-ONLY, SECURITY DEFINER, search_path
-- fisso, grants invariati.
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

    -- GUARD anti re-arm (fix param fantasma): un bot ancora attivo NON è
    -- ri-armabile — il runner non re-istanzia la strategia ospitata e il
    -- reset di stats/params qui sotto mentirebbe sullo stato reale.
    IF EXISTS (
        SELECT 1
          FROM public.tennis_bot_control
         WHERE event_id = p_event_id
           AND bot_key  = p_bot_key
           AND status IN ('requested','arming','armed','running')
    ) THEN
        RAISE EXCEPTION 'bot già attivo: disarma prima di riarmare';
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

-- GRANTS (ribaditi: CREATE OR REPLACE preserva i grant, ma il file deve essere
-- autoconsistente a prescindere dall'ordine di applicazione).
REVOKE ALL    ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) TO authenticated, service_role;
