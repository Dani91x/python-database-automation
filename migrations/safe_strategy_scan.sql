-- ============================================================================
-- safe_strategy_scan.sql — scanner AUTONOMO della sezione Safe Strategy.
--
-- Il servizio Betfair/safe_strategy (service_role) scansiona TUTTI gli eventi
-- calcio+tennis in-play del momento (nessuna iscrizione manuale) e scrive qui
-- i FATTI per evento (quote, punteggio, minuto, mercati, riferimento pre-KO):
-- la VALUTAZIONE delle strategie resta nel motore certificato del frontend
-- (lib/safeStrategy.ts) che sottoscrive questa tabella via Supabase Realtime.
--
-- Convenzioni progetto (come live_signals.sql): schema public, RLS ON,
-- REVOKE da anon/authenticated con ECCEZIONE SELECT per 'authenticated'
-- (richiesta da Realtime; mai ad anon). service_role bypassa la RLS.
-- Tutto IDEMPOTENTE.
-- ============================================================================

------------------------------------------------------------------------------
-- safe_strategy_scan — 1 riga per evento monitorato (in-play o KO imminente).
--   payload calcio: { event_name, home, away, competition, open_date, inplay,
--     mo_market_id, mo_status, odds:{home,draw,away:{back,lay}}, minute,
--     score_home, score_away, red_home, red_away,
--     pre_ko:{home,draw,away,captured_at}|null,
--     cs:{status, market_id, any_other_home:{back,lay}, any_other_away:{...}}|null }
--   payload tennis: { event_name, p1, p2, competition, open_date, inplay,
--     mo_market_id, mo_status, odds:{p1,p2:{back,lay}}, sets:{p1,p2}|null,
--     games:{p1,p2}|null }
-- Le righe degli eventi finiti/spariti vengono CANCELLATE dallo scanner.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.safe_strategy_scan (
    event_id    TEXT PRIMARY KEY,
    sport       TEXT NOT NULL CHECK (sport IN ('calcio', 'tennis')),
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

------------------------------------------------------------------------------
-- safe_strategy_status — heartbeat/stato dello scanner (1 riga, id='scanner').
--   payload: { calcio_inplay, tennis_inplay, monitored, dry, last_error,
--              scan_ms, started_at }
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.safe_strategy_status (
    id          TEXT PRIMARY KEY,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- RLS + lockdown (pattern live_signals.sql)
-- ============================================================================
ALTER TABLE public.safe_strategy_scan ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.safe_strategy_status ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.safe_strategy_scan FROM anon, authenticated;
REVOKE ALL ON TABLE public.safe_strategy_status FROM anon, authenticated;

DROP POLICY IF EXISTS safe_strategy_scan_select_authenticated ON public.safe_strategy_scan;
CREATE POLICY safe_strategy_scan_select_authenticated ON public.safe_strategy_scan
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS safe_strategy_status_select_authenticated ON public.safe_strategy_status;
CREATE POLICY safe_strategy_status_select_authenticated ON public.safe_strategy_status
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.safe_strategy_scan TO authenticated;
GRANT SELECT ON TABLE public.safe_strategy_status TO authenticated;
REVOKE SELECT ON TABLE public.safe_strategy_scan FROM anon;
REVOKE SELECT ON TABLE public.safe_strategy_status FROM anon;

-- Replica Realtime (idempotente) su entrambe le tabelle.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'safe_strategy_scan'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.safe_strategy_scan;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'safe_strategy_status'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.safe_strategy_status;
    END IF;
END;
$$;
