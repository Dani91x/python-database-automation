-- ============================================================================
-- live_backtest.sql — backtest UFFICIALE (FlumineSimulation) richiesto da UI
-- Piano: cozy-beaming-pretzel.md (F1bis).
--
-- Flusso: la dashboard (tab "Backtest Automatico") inserisce una richiesta via
-- RPC request_backtest → un worker LOCALE polla live_backtest_requests
-- (PENDING→RUNNING→DONE/ERROR), esegue FlumineSimulation sui file grezzi nativi
-- e scrive le metriche in live_backtest_results. Una richiesta alla volta (DB-safe).
--
-- Convenzioni progetto (come live_stream.sql):
--   schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
--   REVOKE ALL FROM anon, authenticated. Accesso dati via RPC SECURITY DEFINER
--   (live_backtest_rpc.sql). ECCEZIONE Realtime: live_backtest_requests ha una
--   policy SELECT per 'authenticated' + GRANT SELECT + publication, così la UI
--   può seguire lo stato in tempo reale (pattern identico a live_now). MAI anon.
--   live_backtest_results è letta SOLO via RPC. NON usiamo FORCE RLS → il
--   backend (service_role) bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS.
-- ============================================================================

------------------------------------------------------------------------------
-- 1) live_backtest_requests — coda richieste di backtest dalla UI.
--    params = { events:[event_id...], mode: 'engine'|'sandbox', rules:{...} }
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_backtest_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    params        JSONB NOT NULL,
    status        TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','RUNNING','DONE','ERROR')),
    error_detail  TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lbr_status
    ON public.live_backtest_requests (status, created_at DESC);

------------------------------------------------------------------------------
-- 2) live_backtest_results — metriche aggregate per richiesta.
--    Derivate SOLO dagli ordini simulati da flumine (settlement/blotter).
--    scope/grp = granularità del raggruppamento (es. 'event' + event_id,
--    'market_type' + tipo, 'overall' + '*').
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_backtest_results (
    id            BIGSERIAL PRIMARY KEY,
    request_id    UUID NOT NULL REFERENCES public.live_backtest_requests(id) ON DELETE CASCADE,
    scope         TEXT,                                -- es. 'overall' | 'event' | 'market_type'
    grp           TEXT,                                -- chiave del gruppo (event_id, market_type, '*')
    n_bets        INTEGER,
    n_won         INTEGER,
    hit_rate      NUMERIC,
    roi           NUMERIC,
    total_pnl     NUMERIC,
    max_drawdown  NUMERIC,
    avg_odds      NUMERIC,
    metrics       JSONB,                               -- diagnostica extra (per-mercato, equity curve…)
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lbres_request
    ON public.live_backtest_results (request_id);

-- ============================================================================
-- RLS + lockdown — coerente con live_stream.sql.
-- ============================================================================
ALTER TABLE public.live_backtest_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_backtest_results  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.live_backtest_requests FROM anon, authenticated;
REVOKE ALL ON TABLE public.live_backtest_results  FROM anon, authenticated;

-- difesa in profondità: niente USAGE/SELECT sulla sequenza BIGSERIAL ad anon/auth
REVOKE ALL ON SEQUENCE public.live_backtest_results_id_seq FROM anon, authenticated;

------------------------------------------------------------------------------
-- ECCEZIONE live_backtest_requests: la UI segue lo stato (PENDING→…→DONE) in
-- tempo reale. Supabase Realtime richiede il privilegio SELECT sul ruolo che
-- sottoscrive: concediamo la SOLA SELECT a 'authenticated', MAI ad anon.
-- Pattern identico a live_now in live_stream.sql.
-- live_backtest_results NON entra nella publication: si legge SOLO via RPC.
------------------------------------------------------------------------------
DROP POLICY IF EXISTS live_backtest_requests_select_authenticated ON public.live_backtest_requests;
CREATE POLICY live_backtest_requests_select_authenticated ON public.live_backtest_requests
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_backtest_requests TO authenticated;
REVOKE SELECT ON TABLE public.live_backtest_requests FROM anon;

-- Abilita la replica Realtime sulla tabella live_backtest_requests (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_backtest_requests'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_backtest_requests;
    END IF;
END;
$$;

-- ============================================================================
-- Le RPC (request_backtest, list_backtest_runs, list_backtest_results) sono in
-- migrations/live_backtest_rpc.sql (SECURITY DEFINER, search_path fisso,
-- grant solo authenticated + service_role, mai anon).
-- ============================================================================
