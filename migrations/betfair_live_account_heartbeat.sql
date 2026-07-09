-- ============================================================================
-- betfair_live_account_heartbeat.sql — Roadmap A2 + A5:
--
--   betfair_live_account    (singleton id=1) saldo/exposure del CONTO Betfair
--                           (fonte: REST getAccountFunds, scritto dal
--                           reconcile_worker). Realtime → top bar.
--   betfair_live_heartbeat  (singleton id=1) heartbeat del runner (ts, pid,
--                           mode) + del watchdog (watchdog_ts, watchdog_pid).
--                           Realtime → chip "runner vivo" in top bar.
--   betfair_live_orders.source — origine della riga specchio: 'runner'
--                           (default, ordini nostri) o 'account' (ordini
--                           trovati sul conto ma NON piazzati dal runner,
--                           es. dal sito Betfair — A2: sempre visibili).
--
-- IDEMPOTENTE. Applicare DOPO betfair_live_order_queue.sql.
-- ============================================================================


-- ============================================================================
-- 1. betfair_live_account — saldo disponibile / esposizione del conto.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_account (
    id          INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    available   NUMERIC,                          -- availableToBetBalance (EUR)
    exposure    NUMERIC,                          -- exposure corrente (EUR, <=0 da API)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.betfair_live_account (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.betfair_live_account ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_account FROM anon, authenticated;
DROP POLICY IF EXISTS betfair_live_account_select ON public.betfair_live_account;
CREATE POLICY betfair_live_account_select ON public.betfair_live_account
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON public.betfair_live_account TO authenticated;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'betfair_live_account'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.betfair_live_account;
    END IF;
END $$;


-- ============================================================================
-- 2. betfair_live_heartbeat — heartbeat runner + watchdog.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_heartbeat (
    id           INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    ts           TIMESTAMPTZ,                     -- ultimo battito del RUNNER
    pid          BIGINT,
    mode         TEXT,                            -- OFF | PAPER | LIVE
    watchdog_ts  TIMESTAMPTZ,                     -- ultimo battito del WATCHDOG
    watchdog_pid BIGINT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.betfair_live_heartbeat (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.betfair_live_heartbeat ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_heartbeat FROM anon, authenticated;
DROP POLICY IF EXISTS betfair_live_heartbeat_select ON public.betfair_live_heartbeat;
CREATE POLICY betfair_live_heartbeat_select ON public.betfair_live_heartbeat
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON public.betfair_live_heartbeat TO authenticated;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'betfair_live_heartbeat'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.betfair_live_heartbeat;
    END IF;
END $$;


-- ============================================================================
-- 3. betfair_live_orders.source — origine della riga specchio (A2).
-- ============================================================================
ALTER TABLE public.betfair_live_orders
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'runner';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'betfair_live_orders_source_check'
          AND conrelid = 'public.betfair_live_orders'::regclass
    ) THEN
        ALTER TABLE public.betfair_live_orders
            ADD CONSTRAINT betfair_live_orders_source_check
            CHECK (source IN ('runner', 'account'));
    END IF;
END $$;
