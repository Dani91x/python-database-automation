-- ============================================================================
-- live_stream.sql — Betfair Stream API live + storico per Match Replay (schema DB)
-- Piano: Betfair/PIANO_STREAM_LIVE.md (v1.1).
--
-- Due usi distinti, due livelli di scrittura:
--   • LIVE GLANCE  → tabella live_now (1 riga/partita, ~10s, write-on-change):
--       alimenta la tab "Segui Live" via Supabase Realtime. Carico I/O trascurabile.
--   • REPLAY        → live_markets (catalogo) + live_market_snapshots (firehose
--       curato) + live_score_timeline: scritte UNA VOLTA a fine partita (batch),
--       fonte del "Match Replay" (TUTTI i mercati realmente registrati).
--
-- Il firehose grezzo a piena fedeltà vive in LOCALE (formato nativo Betfair);
-- su Supabase arriva solo l'estratto curato. Vincolo I/O: incidente 2026-06-13.
--
-- Convenzioni progetto (come personal_tracking.sql / security_lockdown.sql):
--   schema public, snake_case, *_at TIMESTAMPTZ default now(), RLS ON,
--   REVOKE ALL FROM anon, authenticated. Accesso dati SOLO via RPC SECURITY
--   DEFINER (vedi live_stream_rpc.sql) — ECCEZIONI: live_now ha una policy
--   SELECT per 'authenticated' perché Supabase Realtime richiede il privilegio
--   di lettura sul ruolo che sottoscrive (come fixture_predictions); dal 17/07
--   anche live_follow (migrations/live_follow_realtime.sql, stesso motivo:
--   realtime dell'aggancio "Trading immediato" — colonne non sensibili).
--   NON usiamo FORCE RLS → il backend (service_role) bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS.
-- ============================================================================

------------------------------------------------------------------------------
-- 1) live_follow — registro delle partite agganciate allo Stream API
--    Chiave = event_id Betfair (autoritativo, stessi ID dello stream e
--    dell'in-play service → nessun matching con la nostra API nel flusso normale).
--    fixture_id (nostra) è OPZIONALE: serve solo al fallback punteggio API-Football.
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_follow (
    event_id        TEXT PRIMARY KEY,                 -- Betfair event_id
    fixture_id      BIGINT,                           -- nostra fixture (se nota; NULL = solo Betfair)
    watchlist_id    BIGINT REFERENCES public.personal_watchlist(id) ON DELETE SET NULL,
    league_name     TEXT,
    home_name       TEXT NOT NULL,
    away_name       TEXT NOT NULL,
    open_date       TIMESTAMPTZ NOT NULL,             -- kickoff (Betfair openDate)
    status          TEXT NOT NULL DEFAULT 'PENDING'
                       CHECK (status IN ('PENDING','STREAMING','CLOSED','UPLOADED','ERROR')),
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lf_status  ON public.live_follow (status);
CREATE INDEX IF NOT EXISTS idx_lf_open    ON public.live_follow (open_date);
CREATE INDEX IF NOT EXISTS idx_lf_fixture ON public.live_follow (fixture_id);

------------------------------------------------------------------------------
-- 2) live_now — fotografia LIVE corrente (1 riga per evento attivo)
--    Aggiornata dal runner ~10s (write-on-change). Sottoscritta dal frontend
--    "Segui Live" via Supabase Realtime. Tenuta MINUSCOLA di proposito.
--    state = { markets: [{market_id, market_type, market_name, selections:[
--                {selection_id, name, back, lay, ltp}]}], updated_ms }
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_now (
    event_id     TEXT PRIMARY KEY REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    inplay       BOOLEAN NOT NULL DEFAULT false,
    minute       SMALLINT,
    score_home   SMALLINT,
    score_away   SMALLINT,
    status       TEXT NOT NULL DEFAULT 'OPEN',        -- OPEN|SUSPENDED|CLOSED
    score_source TEXT,                                -- 'betfair' | 'api_football'
    state        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- prezzi mercati chiave (vedi sopra)
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

------------------------------------------------------------------------------
-- 3) live_markets — catalogo mercati per evento (per il replay: nomi mercati +
--    nomi selezioni di TUTTI i mercati realmente registrati per la partita).
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_markets (
    id            BIGSERIAL PRIMARY KEY,
    event_id      TEXT NOT NULL REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    market_id     TEXT NOT NULL,
    market_type   TEXT,                               -- MATCH_ODDS, OVER_UNDER_25, CORRECT_SCORE, ...
    market_name   TEXT,                               -- etichetta leggibile
    sort_priority INTEGER,                            -- ordine di visualizzazione (da Betfair)
    selections    JSONB NOT NULL DEFAULT '[]'::jsonb, -- [{selection_id, name, sort_priority}]
    n_updates     INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_lm_event ON public.live_markets (event_id);

------------------------------------------------------------------------------
-- 4) live_market_snapshots — firehose CURATO (write-on-change ~10s) per replay.
--    Una riga = stato di UN mercato a un istante. ladder JSONB:
--      { selection_id: { back:[[price,size]...], lay:[[price,size]...],
--                        ltp: number, tv: number } }
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_market_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    event_id      TEXT NOT NULL REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    market_id     TEXT NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,               -- publish time del delta (UTC)
    minute        SMALLINT,                           -- minuto di gioco stimato (se in-play)
    inplay        BOOLEAN NOT NULL DEFAULT false,
    status        TEXT NOT NULL,                      -- OPEN|SUSPENDED|CLOSED
    ladder        JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ordine cronologico per (evento, mercato) = come il replay rilegge i frame
CREATE INDEX IF NOT EXISTS idx_lms_event_market_ts
    ON public.live_market_snapshots (event_id, market_id, ts);
CREATE INDEX IF NOT EXISTS idx_lms_event_ts
    ON public.live_market_snapshots (event_id, ts);

------------------------------------------------------------------------------
-- 5) live_score_timeline — punteggio/eventi nel tempo (per overlay sul replay)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_score_timeline (
    id            BIGSERIAL PRIMARY KEY,
    event_id      TEXT NOT NULL REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    ts            TIMESTAMPTZ NOT NULL,
    source        TEXT NOT NULL,                      -- 'betfair' | 'api_football'
    minute        SMALLINT,
    score_home    SMALLINT,
    score_away    SMALLINT,
    event_type    TEXT,                               -- GOAL|RED_CARD|... (se disponibile)
    payload       JSONB,                              -- raw del provider, per audit
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lst_event_ts ON public.live_score_timeline (event_id, ts);

------------------------------------------------------------------------------
-- 6) live_run_log — osservabilità per partita
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.live_run_log (
    event_id        TEXT PRIMARY KEY REFERENCES public.live_follow(event_id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    raw_file_path   TEXT,
    raw_bytes       BIGINT,
    n_markets       INTEGER,
    n_snapshots     INTEGER,
    score_source    TEXT,                             -- sorgente punteggio effettiva
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    conflate_ms     INTEGER,                          -- sentinella Live vs Delayed key
    notes           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- RLS + lockdown — coerente con personal_tracking.sql / security_lockdown.sql.
-- Default: nessun accesso diretto da anon/authenticated; tutto via RPC SECURITY
-- DEFINER (live_stream_rpc.sql). Backend = service_role → bypassa la RLS.
-- ============================================================================
ALTER TABLE public.live_follow            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_now               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_markets           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_market_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_score_timeline    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_run_log           ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.live_follow           FROM anon, authenticated;
REVOKE ALL ON TABLE public.live_markets          FROM anon, authenticated;
REVOKE ALL ON TABLE public.live_market_snapshots FROM anon, authenticated;
REVOKE ALL ON TABLE public.live_score_timeline   FROM anon, authenticated;
REVOKE ALL ON TABLE public.live_run_log          FROM anon, authenticated;

-- difesa in profondità: niente USAGE/SELECT sulle sequenze BIGSERIAL ad anon/auth
REVOKE ALL ON SEQUENCE
    public.live_markets_id_seq,
    public.live_market_snapshots_id_seq,
    public.live_score_timeline_id_seq
    FROM anon, authenticated;

------------------------------------------------------------------------------
-- ECCEZIONE live_now: Supabase Realtime richiede il privilegio SELECT sul ruolo
-- che sottoscrive. Concediamo la SOLA SELECT a 'authenticated' (l'owner loggato),
-- MAI ad anon. Pattern identico a fixture_predictions in security_lockdown.sql.
------------------------------------------------------------------------------
REVOKE ALL ON TABLE public.live_now FROM anon, authenticated;

DROP POLICY IF EXISTS live_now_select_authenticated ON public.live_now;
CREATE POLICY live_now_select_authenticated ON public.live_now
    FOR SELECT TO authenticated
    USING (true);

GRANT SELECT ON TABLE public.live_now TO authenticated;
REVOKE SELECT ON TABLE public.live_now FROM anon;

-- Abilita la replica Realtime sulla tabella live_now (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'live_now'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.live_now;
    END IF;
END;
$$;

-- ============================================================================
-- Le RPC (lettura replay + scrittura watchlist live) sono in
-- migrations/live_stream_rpc.sql (SECURITY DEFINER, search_path fisso,
-- grant solo authenticated + service_role, mai anon).
-- ============================================================================
