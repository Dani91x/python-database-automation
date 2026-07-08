-- ============================================================================
-- tennis_markets.sql — PARTITE TENNIS del giorno + quote COMPLETE + refresh queue.
--
-- BACKEND DEDICATO AL TENNIS. Regola d'oro (richiesta esplicita utente): Tennis e
-- Calcio sono sport diversi e NON devono MAI condividere dati. Questo file crea
-- ESCLUSIVAMENTE tabelle/RPC `tennis_*` / `get_tennis_*` / `request_tennis_*` e non
-- tocca, legge o modifica ALCUNA tabella o RPC del calcio (nessuna contaminazione).
--
-- Mirror strutturale di betfair_market_odds.sql + betfair_fixtures_rpc.sql +
-- betfair_full_odds_rpc.sql + betfair_refresh_queue.sql, ma su storage tennis
-- separato. Contratto frozen del frontend: frontend/src/lib/tennis.ts
--   get_tennis_fixtures(p_date)         -> SETOF json (TennisFixtureRow)
--   get_tennis_full_odds(p_event_id)    -> jsonb (TennisFullMarket[])
--   request_tennis_refresh(p_event_id)  -> bigint
--   get_tennis_refresh_request(p_id)    -> json {status, updated, error}
--
-- Convenzioni progetto: schema public, snake_case, *_at TIMESTAMPTZ default now(),
-- RLS ON, REVOKE ALL FROM anon, authenticated. Accesso dati SOLO via RPC SECURITY
-- DEFINER (search_path fisso). Backend = service_role → bypassa la RLS.
-- Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS, CREATE OR REPLACE FUNCTION.
-- ============================================================================

------------------------------------------------------------------------------
-- 1) tennis_markets — una riga per EVENTO Betfair tennis (eventTypeId=2).
--    Chiave = event_id Betfair (il tennis NON ha fixture calcio: tutto keyato
--    sull'evento Betfair). Popolata dal fetcher tennis dedicato (additivo).
--    player1/player2 JSONB = TennisMoneylineRunner (moneyline Match Odds P1/P2).
--    markets  JSONB = TennisEventMarket[] (tutti i mercati dell'evento, incl. MO).
--    full_odds JSONB = TennisFullMarket[] (tutti i mercati back/lay N livelli) per
--                      get_tennis_full_odds.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_markets (
    event_id           TEXT PRIMARY KEY,                 -- Betfair event_id (autoritativo)
    market_id          TEXT,                             -- market_id del Match Odds (moneyline)
    competition_id     TEXT,
    competition_name   TEXT,
    competition_region TEXT,
    open_date          TIMESTAMPTZ,                      -- orario d'inizio (Betfair openDate)
    inplay             BOOLEAN NOT NULL DEFAULT false,
    status             TEXT,                             -- OPEN|SUSPENDED|CLOSED
    player1            JSONB NOT NULL DEFAULT '{}'::jsonb, -- TennisMoneylineRunner
    player2            JSONB NOT NULL DEFAULT '{}'::jsonb, -- TennisMoneylineRunner
    total_matched      NUMERIC,
    markets            JSONB NOT NULL DEFAULT '[]'::jsonb, -- TennisEventMarket[]
    full_odds          JSONB NOT NULL DEFAULT '[]'::jsonb, -- TennisFullMarket[] (get_tennis_full_odds)
    captured_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_date           DATE NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date
);

COMMENT ON TABLE public.tennis_markets IS
    'Tennis-dedicato: eventi Betfair tennis del giorno + quote complete. Nessuna contaminazione col calcio.';

CREATE INDEX IF NOT EXISTS idx_tennis_markets_run_date  ON public.tennis_markets (run_date);
CREATE INDEX IF NOT EXISTS idx_tennis_markets_open_date ON public.tennis_markets (open_date);

-- Non leggibile dai client diretti; accesso via RPC SECURITY DEFINER.
ALTER TABLE public.tennis_markets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_markets FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.tennis_markets TO service_role;

------------------------------------------------------------------------------
-- 2) tennis_refresh_requests — coda "Aggiorna quote tennis" (mediata dal DB,
--    come lo stream). Il worker locale tennis esegue il refresh Betfair e scrive
--    l'esito; il frontend fa poll. NESSUN ordine reale: solo quote.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_refresh_requests (
    id           BIGSERIAL PRIMARY KEY,
    event_id     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','error')),
    updated      INTEGER,                                -- n. mercati/righe aggiornati
    result       JSONB,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_trr_pending
    ON public.tennis_refresh_requests (id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_trr_event
    ON public.tennis_refresh_requests (event_id, created_at DESC);

ALTER TABLE public.tennis_refresh_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_refresh_requests FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_refresh_requests_id_seq FROM anon, authenticated;

-- ============================================================================
-- RPC 1: get_tennis_fixtures(p_date) -> SETOF json (una TennisFixtureRow per riga)
-- Match tennis del giorno con moneyline P1/P2 (back/lay), volume, stato, mercati.
-- Mirror di get_betfair_fixtures ma su tennis_markets (dedicato).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_fixtures(p_date date)
RETURNS SETOF json
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT json_build_object(
             'event_id',           m.event_id,
             'market_id',          m.market_id,
             'competition_id',     m.competition_id,
             'competition_name',   m.competition_name,
             'competition_region', m.competition_region,
             'open_date',          m.open_date,
             'inplay',             m.inplay,
             'status',             m.status,
             'player1',            m.player1,
             'player2',            m.player2,
             'total_matched',      m.total_matched,
             'markets',            m.markets,
             'captured_at',        m.captured_at
           )
      FROM public.tennis_markets m
     WHERE m.run_date = p_date
     ORDER BY m.open_date NULLS LAST, m.event_id;
$$;

-- ============================================================================
-- RPC 2: get_tennis_full_odds(p_event_id) -> jsonb (TennisFullMarket[])
-- Quote COMPLETE dell'evento (tutti i mercati, back+lay N livelli).
-- Mirror di get_betfair_full_odds ma su tennis_markets.full_odds (dedicato).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_full_odds(p_event_id text)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT coalesce(
             (SELECT m.full_odds
                FROM public.tennis_markets m
               WHERE m.event_id = p_event_id),
             '[]'::jsonb
           );
$$;

-- ============================================================================
-- RPC 3: request_tennis_refresh(p_event_id) -> bigint
-- Accoda una richiesta di refresh quote per un evento tennis. Anti-spam: se esiste
-- già una richiesta 'pending' recente (<30s) per lo stesso evento, ne riusa l'id.
-- Mirror di request_betfair_refresh (dedicato al tennis).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_tennis_refresh(p_event_id text)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id bigint;
BEGIN
    IF p_event_id IS NULL THEN
        RAISE EXCEPTION 'p_event_id nullo';
    END IF;
    IF length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;

    SELECT id INTO v_id
      FROM public.tennis_refresh_requests
     WHERE event_id = p_event_id
       AND status = 'pending'
       AND created_at > now() - interval '30 seconds'
     ORDER BY id DESC
     LIMIT 1;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.tennis_refresh_requests (event_id)
    VALUES (p_event_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- ============================================================================
-- RPC 4: get_tennis_refresh_request(p_id) -> json {status, updated, error}
-- Stato/esito di una richiesta refresh (poll dal frontend). Lo stato interno
-- 'processing' viene riportato come 'pending' affinché la UI continui il poll
-- (TennisRefreshResult.status ∈ {done,error,pending}).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_refresh_request(p_id bigint)
RETURNS json
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT json_build_object(
             'status',  CASE WHEN r.status IN ('pending','processing')
                             THEN 'pending' ELSE r.status END,
             'updated', r.updated,
             'error',   r.error
           )
      FROM public.tennis_refresh_requests r
     WHERE r.id = p_id;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- Coerente con betfair_fixtures_rpc.sql / betfair_refresh_queue.sql (mai anon).
-- ============================================================================
REVOKE ALL    ON FUNCTION public.get_tennis_fixtures(date)          FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_fixtures(date)          TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_full_odds(text)         FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_full_odds(text)         TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.request_tennis_refresh(text)       FROM public, anon;
GRANT EXECUTE ON FUNCTION public.request_tennis_refresh(text)       TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_refresh_request(bigint) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_refresh_request(bigint) TO authenticated, service_role;
