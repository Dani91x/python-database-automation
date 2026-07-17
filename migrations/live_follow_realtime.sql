-- ============================================================================
-- live_follow_realtime.sql — Realtime sullo stato dei follow (fix 17/07
-- "Trading = streaming immediato").
--
-- PROBLEMA: al click "Trading" la UI aspettava il poll di backup (15s) per
-- vedere il follow PENDING→STREAMING. Con questa migrazione la pagina Segui
-- Live sottoscrive postgres_changes su live_follow (filtrata per event_id) e
-- reagisce APPENA il runner aggancia lo stream.
--
-- Pattern IDENTICO a live_backtest_requests (live_backtest.sql) e live_now
-- (live_stream.sql): Supabase Realtime consegna gli eventi solo al ruolo che
-- ha il privilegio SELECT → concediamo la SOLA SELECT ad 'authenticated',
-- MAI ad anon. La scrittura resta esclusiva del backend (service_role, bypassa
-- la RLS). Idempotente: riapplicabile senza effetti collaterali.
-- ============================================================================

DROP POLICY IF EXISTS live_follow_select_authenticated ON public.live_follow;
CREATE POLICY live_follow_select_authenticated ON public.live_follow
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_follow TO authenticated;
REVOKE SELECT ON TABLE public.live_follow FROM anon;

-- Abilita la replica Realtime sulla tabella live_follow (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_follow'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_follow;
    END IF;
END;
$$;
