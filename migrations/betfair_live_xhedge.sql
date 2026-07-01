-- ============================================================================
-- betfair_live_xhedge.sql — #9: analisi hedging CROSS-MARKET per evento.
-- Il ``xhedge_worker`` (nel runner) calcola il P&L per-scoreline sulle posizioni
-- MATCHED di TUTTI i mercati correlati dell'evento (trading/xhedge) e scrive qui
-- la sintesi + il suggerimento di copertura. La UI la legge (sola lettura).
--
-- IDEMPOTENTE. RPC owner-only. Da applicare DOPO betfair_live_order_queue.sql.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.betfair_live_xhedge (
    id          BIGSERIAL PRIMARY KEY,
    event_id    TEXT NOT NULL,
    mode        TEXT NOT NULL CHECK (mode IN ('paper','live')),
    analysis    JSONB NOT NULL,           -- { n_positions, summary, grid, suggestion }
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_blx_event_mode
    ON public.betfair_live_xhedge (event_id, mode);

ALTER TABLE public.betfair_live_xhedge ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_xhedge FROM anon, authenticated;


CREATE OR REPLACE FUNCTION public.get_live_xhedge(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL THEN
        RAISE EXCEPTION 'p_event_id nullo';
    END IF;
    IF length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(z.*) ORDER BY z.mode), '[]'::jsonb)
      INTO v_rows
      FROM public.betfair_live_xhedge z
     WHERE z.event_id = p_event_id;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_live_xhedge(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_xhedge(text) TO authenticated, service_role;
