-- ============================================================================
-- betfair_live_controls.sql — Fase 6: SETTINGS runtime (kill-switch dalla UI,
-- limiti custom, velocità) + AUDIT LOG append-only di ogni comando/ordine.
--
--   betfair_live_settings  (singleton id=1): kill_switch globale controllabile dalla UI
--     (oltre all'env LIVE_KILL_SWITCH), max esposizione per selezione, rate-limit ordini/min,
--     parametri velocità. Il runner li rilegge ad ogni ciclo.
--   betfair_live_audit     (append-only): traccia chi/cosa/mode/esito di ogni comando
--     (events log stile Betting Toolkit). Scritto dal worker come service_role.
--
-- IDEMPOTENTE. RPC SECURITY DEFINER owner-only (betfair_live_is_owner). Applicare DOPO
-- betfair_live_order_queue.sql.
-- ============================================================================


-- ============================================================================
-- 1. betfair_live_settings — riga singola di configurazione runtime.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_settings (
    id                         INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    kill_switch                BOOLEAN NOT NULL DEFAULT false,   -- freno d'emergenza da UI
    max_exposure_per_selection NUMERIC,                          -- NULL = nessun limite
    max_orders_per_min         INT,                              -- NULL = nessun rate-limit
    order_poll_sec             NUMERIC,                          -- velocità worker coda (override)
    risk_poll_sec              NUMERIC,                          -- velocità risk engine (override)
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- garantisce l'esistenza della riga singleton.
INSERT INTO public.betfair_live_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.betfair_live_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_settings FROM anon, authenticated;


-- ============================================================================
-- 2. betfair_live_audit — log append-only dei comandi/ordini.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_audit (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode         TEXT,
    action       TEXT,
    market_id    TEXT,
    selection_id BIGINT,
    side         TEXT,
    price        NUMERIC,
    size         NUMERIC,
    status       TEXT,             -- 'done' | 'error'
    error        TEXT,
    request_id   BIGINT,
    detail       JSONB
);
CREATE INDEX IF NOT EXISTS idx_bla_ts ON public.betfair_live_audit (ts DESC);
CREATE INDEX IF NOT EXISTS idx_bla_market ON public.betfair_live_audit (market_id);

ALTER TABLE public.betfair_live_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_audit FROM anon, authenticated;


-- ============================================================================
-- 3.1 get_live_settings — legge la riga singleton. { ...settings }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_settings()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN coalesce(v_row, '{}'::jsonb);
END;
$$;


-- ============================================================================
-- 3.2 set_live_kill_switch — accende/spegne il kill-switch dalla UI.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_live_kill_switch(p_on boolean)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_on IS NULL THEN
        RAISE EXCEPTION 'p_on nullo';
    END IF;
    UPDATE public.betfair_live_settings
       SET kill_switch = p_on, updated_at = now()
     WHERE id = 1;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 3.3 set_live_settings — aggiorna i limiti/velocità (solo i campi passati).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_live_settings(p jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.betfair_live_settings SET
        kill_switch = coalesce((p->>'kill_switch')::boolean, kill_switch),
        max_exposure_per_selection = CASE WHEN p ? 'max_exposure_per_selection'
            THEN nullif(p->>'max_exposure_per_selection','')::numeric ELSE max_exposure_per_selection END,
        max_orders_per_min = CASE WHEN p ? 'max_orders_per_min'
            THEN nullif(p->>'max_orders_per_min','')::int ELSE max_orders_per_min END,
        order_poll_sec = CASE WHEN p ? 'order_poll_sec'
            THEN nullif(p->>'order_poll_sec','')::numeric ELSE order_poll_sec END,
        risk_poll_sec = CASE WHEN p ? 'risk_poll_sec'
            THEN nullif(p->>'risk_poll_sec','')::numeric ELSE risk_poll_sec END,
        updated_at = now()
     WHERE id = 1;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 3.4 get_live_audit — ultimi N eventi (default 100). { rows: [...] }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_audit(p_limit int DEFAULT 100)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
    v_lim  int := least(greatest(coalesce(p_limit, 100), 1), 1000);
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT * FROM public.betfair_live_audit ORDER BY ts DESC LIMIT v_lim) a;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- GRANTS
-- ============================================================================
REVOKE ALL    ON FUNCTION public.get_live_settings()            FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_settings()            TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.set_live_kill_switch(boolean)  FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_live_kill_switch(boolean)  TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.set_live_settings(jsonb)       FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_live_settings(jsonb)       TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_live_audit(int)            FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_audit(int)            TO authenticated, service_role;
