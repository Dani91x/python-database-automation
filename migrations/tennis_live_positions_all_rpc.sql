-- ============================================================================
-- tennis_live_positions_all_rpc.sql — Roadmap D30/D33 (lato tennis):
--   get_tennis_live_positions_all(p_mode) → TUTTE le posizioni tennis aperte
--   (watchlist multi-evento e dashboard P&L: MTM aggregato per evento).
--
-- IDEMPOTENTE. Owner-only (tennis_is_owner). Applicare DOPO tennis_orders.sql.
-- Tennis e calcio NON condividono dati: questa RPC legge SOLO tennis_live_positions.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_tennis_live_positions_all(p_mode text DEFAULT NULL)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
    v_mode text := nullif(p_mode, '');
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT coalesce(json_agg(to_jsonb(pz.*) ORDER BY pz.updated_at DESC), '[]'::json)
      INTO v_rows
      FROM (
          SELECT * FROM public.tennis_live_positions
           WHERE (v_mode IS NULL OR lower(mode) = lower(v_mode))
           ORDER BY updated_at DESC
           LIMIT 2000
      ) pz;

    RETURN json_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_tennis_live_positions_all(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_live_positions_all(text) TO authenticated, service_role;
