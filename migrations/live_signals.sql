-- ============================================================================
-- live_signals.sql — segnali del Motore Poisson Live "definitivo" (1 riga/evento)
-- Piano: cozy-beaming-pretzel.md (F2).
--
-- Decoupling dalla cadenza prezzi di live_now: il runner scrive QUI i segnali
-- calcolati (DC + calibrazione + microstruttura) in modalità write-on-change,
-- 1 riga per evento. Il frontend ("Segui Live" → LiveSignalPanel) sottoscrive
-- questa tabella via Supabase Realtime.
--
-- Convenzioni progetto (come live_stream.sql / personal_tracking.sql):
--   schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
--   REVOKE ALL FROM anon, authenticated. Accesso dati SOLO via RPC SECURITY
--   DEFINER — ECCEZIONE: live_signals ha una policy SELECT per 'authenticated'
--   perché Supabase Realtime richiede il privilegio di lettura sul ruolo che
--   sottoscrive (pattern identico a live_now). MAI ad anon.
--   NON usiamo FORCE RLS → il backend (service_role) bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS, CREATE OR REPLACE.
-- ============================================================================

------------------------------------------------------------------------------
-- live_signals — output corrente del motore live per evento.
--   signals   = { markets: [{market_id, market_type, fair_back, fair_lay,
--                  edge, direction (BACK|LAY|HOLD), confidence, kelly_stake}],
--                  updated_ms }
--   model_meta = parametri/diagnostica del motore (lambdas, rho, calibrazione…)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_signals (
    event_id    TEXT PRIMARY KEY REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    signals     JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_meta  JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- RLS + lockdown — coerente con live_stream.sql.
-- Default: nessun accesso diretto da anon/authenticated; tutto via RPC SECURITY
-- DEFINER. Backend = service_role → bypassa la RLS.
-- ============================================================================
ALTER TABLE public.live_signals ENABLE ROW LEVEL SECURITY;

------------------------------------------------------------------------------
-- ECCEZIONE live_signals: Supabase Realtime richiede il privilegio SELECT sul
-- ruolo che sottoscrive. Concediamo la SOLA SELECT a 'authenticated' (l'owner
-- loggato), MAI ad anon. Pattern identico a live_now in live_stream.sql.
------------------------------------------------------------------------------
REVOKE ALL ON TABLE public.live_signals FROM anon, authenticated;

DROP POLICY IF EXISTS live_signals_select_authenticated ON public.live_signals;
CREATE POLICY live_signals_select_authenticated ON public.live_signals
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_signals TO authenticated;
REVOKE SELECT ON TABLE public.live_signals FROM anon;

-- Abilita la replica Realtime sulla tabella live_signals (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_signals'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_signals;
    END IF;
END;
$$;
