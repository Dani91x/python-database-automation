-- ============================================================================
-- betfair_live_risk_limits_v4.sql — Roadmap E34 + E35: limiti di rischio runtime.
--
--   E34: daily_loss_limit — stop giornaliero di CONTO (es. 50 = kill-switch
--        automatico quando il P&L di giornata scende sotto −€50; NULL = off).
--        Il runner (daily_stop_worker) lo legge via get_live_settings e, se
--        sfondato, chiama set_live_kill_switch(true) + alert CRITICAL.
--   E35: max_exposure_per_event / max_exposure_per_league — esposizione
--        worst-case massima aggregata per evento / per campionato (NULL = off).
--        Enforcement nel path di esecuzione flumine (trading control nativo).
--
-- IDEMPOTENTE. Ridefinisce set_live_settings come SUPERSET (tutte le colonne
-- note fin qui). Applicare DOPO betfair_live_controls.sql.
-- ============================================================================


-- ============================================================================
-- 1. Nuove colonne su betfair_live_settings (NULL = limite disattivato).
-- ============================================================================
ALTER TABLE public.betfair_live_settings
    ADD COLUMN IF NOT EXISTS daily_loss_limit         NUMERIC,
    ADD COLUMN IF NOT EXISTS max_exposure_per_event   NUMERIC,
    ADD COLUMN IF NOT EXISTS max_exposure_per_league  NUMERIC;

-- I limiti devono essere positivi quando presenti (0/negativo = configurazione
-- ambigua: MAI accettarla silenziosamente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'betfair_live_settings_limits_positive'
          AND conrelid = 'public.betfair_live_settings'::regclass
    ) THEN
        ALTER TABLE public.betfair_live_settings
            ADD CONSTRAINT betfair_live_settings_limits_positive CHECK (
                (daily_loss_limit        IS NULL OR daily_loss_limit        > 0) AND
                (max_exposure_per_event  IS NULL OR max_exposure_per_event  > 0) AND
                (max_exposure_per_league IS NULL OR max_exposure_per_league > 0)
            );
    END IF;
END $$;


-- ============================================================================
-- 2. set_live_settings — superset: campi esistenti + i nuovi limiti E34/E35.
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
        daily_loss_limit = CASE WHEN p ? 'daily_loss_limit'
            THEN nullif(p->>'daily_loss_limit','')::numeric ELSE daily_loss_limit END,
        max_exposure_per_event = CASE WHEN p ? 'max_exposure_per_event'
            THEN nullif(p->>'max_exposure_per_event','')::numeric ELSE max_exposure_per_event END,
        max_exposure_per_league = CASE WHEN p ? 'max_exposure_per_league'
            THEN nullif(p->>'max_exposure_per_league','')::numeric ELSE max_exposure_per_league END,
        updated_at = now()
     WHERE id = 1;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN v_row;
END;
$$;

REVOKE ALL    ON FUNCTION public.set_live_settings(jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_live_settings(jsonb) TO authenticated, service_role;
