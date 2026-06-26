-- ============================================================================
-- live_alerts.sql — avvisi operativi (limiti Betfair, backoff, anomalie)
-- Piano: cozy-beaming-pretzel.md (F5).
--
-- Il backend (limits.py / runner) inserisce alert come service_role. Il frontend
-- ("Segui Live" → LiveAlertBanner) li mostra come banner WARN/CRITICAL via
-- Supabase Realtime; il "dismiss" imposta acknowledged=true via RPC ack_alert.
--
-- Convenzioni progetto (come live_stream.sql):
--   schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
--   REVOKE ALL FROM anon, authenticated. ECCEZIONE Realtime: policy SELECT per
--   'authenticated' + GRANT SELECT authenticated + ADD TABLE alla publication
--   supabase_realtime (pattern identico a live_now). MAI ad anon.
--   La scrittura/ack è fatta dal backend (service_role) o via RPC SECURITY
--   DEFINER. NON usiamo FORCE RLS → service_role bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS.
-- ============================================================================

------------------------------------------------------------------------------
-- live_alerts — coda di avvisi in-app. event_id opzionale (alert globali).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_alerts (
    id            BIGSERIAL PRIMARY KEY,
    level         TEXT NOT NULL
                     CHECK (level IN ('INFO','WARN','CRITICAL')),
    code          TEXT,                                -- codice macchina (es. SUBSCRIPTION_LIMIT_EXCEEDED)
    message       TEXT NOT NULL,                       -- testo leggibile per il banner
    event_id      TEXT REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    acknowledged  BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- avvisi non letti, più recenti prima (come li legge il banner)
CREATE INDEX IF NOT EXISTS idx_la_unack
    ON public.live_alerts (acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_la_event
    ON public.live_alerts (event_id);

-- ============================================================================
-- RLS + lockdown — coerente con live_stream.sql.
-- ============================================================================
ALTER TABLE public.live_alerts ENABLE ROW LEVEL SECURITY;

-- difesa in profondità: niente USAGE/SELECT sulla sequenza BIGSERIAL ad anon/auth
REVOKE ALL ON SEQUENCE public.live_alerts_id_seq FROM anon, authenticated;

------------------------------------------------------------------------------
-- ECCEZIONE live_alerts: Supabase Realtime richiede il privilegio SELECT sul
-- ruolo che sottoscrive. Concediamo la SOLA SELECT a 'authenticated', MAI ad
-- anon. Pattern identico a live_now in live_stream.sql.
------------------------------------------------------------------------------
REVOKE ALL ON TABLE public.live_alerts FROM anon, authenticated;

DROP POLICY IF EXISTS live_alerts_select_authenticated ON public.live_alerts;
CREATE POLICY live_alerts_select_authenticated ON public.live_alerts
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_alerts TO authenticated;
REVOKE SELECT ON TABLE public.live_alerts FROM anon;

-- Abilita la replica Realtime sulla tabella live_alerts (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_alerts'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_alerts;
    END IF;
END;
$$;

-- ============================================================================
-- Le RPC (get_live_alerts, ack_alert) sono in migrations/live_backtest_rpc.sql
-- (SECURITY DEFINER, grant solo authenticated + service_role, mai anon).
-- ============================================================================
