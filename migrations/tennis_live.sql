-- ============================================================================
-- tennis_live.sql — proiezioni LIVE single-stream per il TENNIS (realtime).
--
-- BACKEND DEDICATO AL TENNIS. Regola d'oro (richiesta esplicita utente): Tennis e
-- Calcio NON condividono MAI dati. Questo file crea solo tabelle/RPC `tennis_*` e
-- non tocca alcuna tabella/RPC del calcio (nessuna contaminazione). È il mirror di
-- live_stream.sql + live_ladder.sql + live_stream_rpc.sql, ma su storage tennis.
--
-- Contratto frozen del frontend (frontend/src/lib/tennis.ts):
--   get_tennis_follows()                       -> json {rows: TennisFollow[]}
--   tennis_follow_event(p_event_id,p_market_id)-> json  TennisFollow
--   tennis_live_now      (SELECT diretto + Supabase Realtime, filtro event_id)
--   tennis_live_ladder   (SELECT diretto + Supabase Realtime, filtro market_id)
--
-- Convenzioni: schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
-- REVOKE ALL FROM anon, authenticated. Accesso via RPC SECURITY DEFINER — ECCEZIONE:
-- tennis_live_now / tennis_live_ladder hanno una policy SELECT per 'authenticated'
-- perché Supabase Realtime richiede il privilegio di lettura sul ruolo che
-- sottoscrive (pattern identico a live_now / live_ladder). MAI ad anon. Backend =
-- service_role → bypassa la RLS. Tutto IDEMPOTENTE.
-- ============================================================================

------------------------------------------------------------------------------
-- 1) tennis_live_follow — registro degli eventi tennis agganciati allo stream.
--    Chiave = event_id Betfair. Il runner tennis lo prende in carico (PENDING →
--    STREAMING → CLOSED/UPLOADED). score/inplay/live_status = ultimo glance.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_live_follow (
    event_id        TEXT PRIMARY KEY,                    -- Betfair event_id
    market_id       TEXT,                                -- market_id del Match Odds
    competition_name TEXT,
    player1_name    TEXT NOT NULL DEFAULT '',
    player2_name    TEXT NOT NULL DEFAULT '',
    open_date       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'PENDING'
                       CHECK (status IN ('PENDING','STREAMING','CLOSED','UPLOADED','ERROR')),
    error_detail    TEXT,
    inplay          BOOLEAN,
    score           JSONB,                               -- TennisScoreState (ultimo glance)
    live_status     TEXT,                                -- OPEN|SUSPENDED|CLOSED live
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tlf_status ON public.tennis_live_follow (status);
CREATE INDEX IF NOT EXISTS idx_tlf_open   ON public.tennis_live_follow (open_date);

------------------------------------------------------------------------------
-- 2) tennis_live_now — fotografia LIVE corrente (1 riga per evento attivo).
--    Aggiornata dal runner tennis (write-on-change). Sottoscritta dal frontend
--    via Supabase Realtime (filtro event_id). Tenuta MINUSCOLA di proposito.
--    state  = TennisLiveNowState { markets[], order_mode, updated_ms }
--    score  = TennisScoreState (Match Stats live)
--    points = TennisPointEvent[] (punto-per-punto)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_live_now (
    event_id   TEXT PRIMARY KEY
                  REFERENCES public.tennis_live_follow(event_id) ON DELETE CASCADE,
    inplay     BOOLEAN NOT NULL DEFAULT false,
    status     TEXT NOT NULL DEFAULT 'OPEN',             -- OPEN|SUSPENDED|CLOSED
    state      JSONB NOT NULL DEFAULT '{}'::jsonb,       -- TennisLiveNowState (markets + order_mode)
    score      JSONB,                                    -- TennisScoreState
    points     JSONB,                                    -- TennisPointEvent[]
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

------------------------------------------------------------------------------
-- 3) tennis_live_ladder — ladder corrente di UN mercato tennis (1 riga per
--    event_id+market_id). Il ladder_worker tennis pubblica QUI la ladder piena
--    (LiveLadderState) in modalità write-on-change. La pagina ladder sottoscrive
--    questa tabella via Realtime filtrando per market_id.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_live_ladder (
    id          BIGSERIAL PRIMARY KEY,
    event_id    TEXT NOT NULL
                   REFERENCES public.tennis_live_follow(event_id) ON DELETE CASCADE,
    market_id   TEXT NOT NULL,
    market_type TEXT,                                    -- MATCH_ODDS, SET_BETTING, ...
    market_name TEXT,
    status      TEXT,                                    -- OPEN|SUSPENDED|CLOSED
    ladder      JSONB NOT NULL,                          -- LiveLadderState
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chiave UNICA su market_id: il market_id Betfair è GLOBALMENTE unico (un mercato
-- appartiene a un solo evento) → arbitro per ON CONFLICT (market_id) del writer Python
-- e supporto al read del frontend `.eq('market_id').maybeSingle()`. Indice dedicato
-- per la sottoscrizione realtime filtrata per market_id.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tennis_ladder_market
    ON public.tennis_live_ladder (market_id);
CREATE INDEX IF NOT EXISTS idx_tennis_ladder_event
    ON public.tennis_live_ladder (event_id);

-- ============================================================================
-- RLS + lockdown — coerente con live_stream.sql / live_ladder.sql.
-- ============================================================================
ALTER TABLE public.tennis_live_follow ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tennis_live_now    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tennis_live_ladder ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.tennis_live_follow FROM anon, authenticated;
REVOKE ALL ON TABLE public.tennis_live_now    FROM anon, authenticated;
REVOKE ALL ON TABLE public.tennis_live_ladder FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_live_ladder_id_seq FROM anon, authenticated;

------------------------------------------------------------------------------
-- ECCEZIONE Realtime: SELECT per 'authenticated' (owner loggato) su tennis_live_now
-- e tennis_live_ladder, richiesta da Supabase Realtime. MAI ad anon.
------------------------------------------------------------------------------
DROP POLICY IF EXISTS tennis_live_now_select_authenticated ON public.tennis_live_now;
CREATE POLICY tennis_live_now_select_authenticated ON public.tennis_live_now
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON TABLE public.tennis_live_now TO authenticated;
REVOKE SELECT ON TABLE public.tennis_live_now FROM anon;

DROP POLICY IF EXISTS tennis_live_ladder_select_authenticated ON public.tennis_live_ladder;
CREATE POLICY tennis_live_ladder_select_authenticated ON public.tennis_live_ladder
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON TABLE public.tennis_live_ladder TO authenticated;
REVOKE SELECT ON TABLE public.tennis_live_ladder FROM anon;

-- Abilita la replica Realtime su tennis_live_now e tennis_live_ladder (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
         WHERE pubname = 'supabase_realtime' AND schemaname = 'public'
           AND tablename = 'tennis_live_now'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.tennis_live_now;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
         WHERE pubname = 'supabase_realtime' AND schemaname = 'public'
           AND tablename = 'tennis_live_ladder'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.tennis_live_ladder;
    END IF;
END;
$$;

-- ============================================================================
-- RPC 1: get_tennis_follows() -> json {rows: TennisFollow[]}
-- Elenco eventi tennis agganciati allo stream + glance live (tennis_live_now).
-- Mirror di get_live_follows (dedicato al tennis).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_follows()
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
BEGIN
    SELECT coalesce(json_agg(r ORDER BY (r->>'open_date')), '[]'::json)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',         f.event_id,
                 'competition_name', f.competition_name,
                 'player1_name',     f.player1_name,
                 'player2_name',     f.player2_name,
                 'open_date',        f.open_date,
                 'status',           f.status,
                 'error_detail',     f.error_detail,
                 'inplay',           coalesce(n.inplay, f.inplay),
                 'score',            coalesce(n.score, f.score),
                 'live_status',      coalesce(n.status, f.live_status),
                 'updated_at',       coalesce(n.updated_at, f.updated_at)
               ) AS r
          FROM public.tennis_live_follow f
          LEFT JOIN public.tennis_live_now n ON n.event_id = f.event_id
         WHERE f.status IN ('PENDING','STREAMING','CLOSED')
      ) s;

    RETURN json_build_object('rows', v_rows);
END;
$$;

-- ============================================================================
-- RPC 2: tennis_follow_event(p_event_id, p_market_id) -> json TennisFollow
-- Registra un evento tennis da seguire live: upsert in tennis_live_follow con
-- status 'PENDING' (il runner tennis lo prende in carico). Metadati (competizione,
-- nomi giocatori, open_date) letti da tennis_markets se presenti. Ri-seguire un
-- evento chiuso lo riporta a 'PENDING'.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.tennis_follow_event(p_event_id text, p_market_id text)
RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_live_follow;
    -- `record` (non rowtype public.tennis_markets): evita la dipendenza a CREATE-time da
    -- tennis_markets, così l'ordine di applicazione delle migrazioni non è vincolante.
    v_mk  record;
BEGIN
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;

    -- metadati dell'evento (se già catturati dal fetcher tennis). Opzionali.
    SELECT * INTO v_mk FROM public.tennis_markets WHERE event_id = p_event_id;

    INSERT INTO public.tennis_live_follow AS f
        (event_id, market_id, competition_name, player1_name, player2_name,
         open_date, status, error_detail, updated_at)
    VALUES (
        p_event_id,
        coalesce(nullif(p_market_id, ''), v_mk.market_id),
        v_mk.competition_name,
        coalesce(v_mk.player1->>'name', ''),
        coalesce(v_mk.player2->>'name', ''),
        coalesce(v_mk.open_date, now()),
        'PENDING',
        NULL,
        now()
    )
    ON CONFLICT (event_id) DO UPDATE SET
        market_id        = coalesce(EXCLUDED.market_id, f.market_id),
        competition_name = coalesce(EXCLUDED.competition_name, f.competition_name),
        player1_name     = CASE WHEN EXCLUDED.player1_name <> '' THEN EXCLUDED.player1_name ELSE f.player1_name END,
        player2_name     = CASE WHEN EXCLUDED.player2_name <> '' THEN EXCLUDED.player2_name ELSE f.player2_name END,
        open_date        = coalesce(f.open_date, EXCLUDED.open_date),
        status           = 'PENDING',
        error_detail     = NULL,
        updated_at       = now()
    RETURNING * INTO v_row;

    RETURN json_build_object(
        'event_id',         v_row.event_id,
        'competition_name', v_row.competition_name,
        'player1_name',     v_row.player1_name,
        'player2_name',     v_row.player2_name,
        'open_date',        v_row.open_date,
        'status',           v_row.status,
        'error_detail',     v_row.error_detail,
        'inplay',           v_row.inplay,
        'score',            v_row.score,
        'live_status',      v_row.live_status,
        'updated_at',       v_row.updated_at
    );
END;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- ============================================================================
REVOKE ALL    ON FUNCTION public.get_tennis_follows()             FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_follows()             TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.tennis_follow_event(text, text)  FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_follow_event(text, text)  TO authenticated, service_role;
