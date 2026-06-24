-- ============================================================================
-- personal_tracking.sql — Watchlist + Report Personale (schema DB)
-- Contratto: REPORT_PERSONALE_CONTRACT.md §1 — fonte UNICA e vincolante.
--
-- Traccia l'operatività reale dell'utente (pre-match + live) con piena
-- tracciabilità: snapshot server-side IMMUTABILE del pre-match (motori + quote
-- Betfair + edge + consigli), decisione GIOCATA/SCARTATA, trade + coperture.
--
-- Convenzioni progetto (come security_lockdown.sql / analytics_decisions.sql):
--   schema public, snake_case, created_at/updated_at TIMESTAMPTZ default now(),
--   RLS ON, REVOKE ALL FROM anon, authenticated (accesso SOLO via RPC SECURITY
--   DEFINER, vedi personal_tracking_rpc.sql). NON usiamo FORCE RLS così
--   service_role (backend) bypassa la RLS.
--   Tutto IDEMPOTENTE: CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
-- ============================================================================

------------------------------------------------------------------------------
-- 1.1 personal_watchlist (1 riga = 1 partita spuntata)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.personal_watchlist (
    id                   BIGSERIAL PRIMARY KEY,
    fixture_id           BIGINT NOT NULL,
    league_id            BIGINT,
    league_name          TEXT,
    season_year          SMALLINT,
    country              TEXT,
    round                TEXT,
    home_team            TEXT,
    away_team            TEXT,
    kickoff              TIMESTAMPTZ,
    status               TEXT NOT NULL DEFAULT 'DA_VALUTARE'
                            CHECK (status IN ('DA_VALUTARE','GIOCATA','SCARTATA')),
    snapshot             JSONB NOT NULL DEFAULT '{}'::jsonb,   -- vedi §1.4
    consigli             JSONB NOT NULL DEFAULT '[]'::jsonb,   -- top selezioni consigliate (§1.4)
    snapshot_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_note            TEXT,
    strategia_ipotizzata TEXT,
    tags                 TEXT[] NOT NULL DEFAULT '{}',
    reject_reason        TEXT,   -- valorizzato se SCARTATA (enum §1.5)
    reject_note          TEXT,
    decided_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fixture_id)   -- una partita una sola volta in watchlist (riusabile)
);

CREATE INDEX IF NOT EXISTS idx_pw_status  ON public.personal_watchlist (status);
CREATE INDEX IF NOT EXISTS idx_pw_kickoff ON public.personal_watchlist (kickoff);
CREATE INDEX IF NOT EXISTS idx_pw_fixture ON public.personal_watchlist (fixture_id);

------------------------------------------------------------------------------
-- 1.2 personal_trades (1 riga = 1 operazione piazzata)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.personal_trades (
    id              BIGSERIAL PRIMARY KEY,
    watchlist_id    BIGINT REFERENCES public.personal_watchlist(id) ON DELETE SET NULL,
    -- identità match denormalizzata (per query report senza join)
    fixture_id      BIGINT,
    league_id       BIGINT,
    league_name     TEXT,
    home_team       TEXT,
    away_team       TEXT,
    kickoff         TIMESTAMPTZ,
    -- ingresso a mercato
    strategia       TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('back','lay')),
    market          TEXT,
    selection       TEXT,
    line            NUMERIC,
    entry_odds      NUMERIC NOT NULL CHECK (entry_odds > 1),
    stake           NUMERIC NOT NULL CHECK (stake >= 0),   -- backer stake
    liability       NUMERIC,                               -- per lay = stake*(odds-1)
    exit_odds       NUMERIC,                               -- cash-out (opz.)
    timing          TEXT NOT NULL DEFAULT 'prematch' CHECK (timing IN ('prematch','live')),
    entry_minute    SMALLINT,
    entry_score     TEXT,
    exchange        TEXT NOT NULL DEFAULT 'Betfair',
    commission      NUMERIC NOT NULL DEFAULT 0.05,
    time_operative_min NUMERIC,
    -- esito
    status          TEXT NOT NULL DEFAULT 'OPEN'
                       CHECK (status IN ('OPEN','WON','LOST','VOID','PARTIAL')),
    result_ft       TEXT,
    gross_pnl       NUMERIC,
    net_pnl         NUMERIC,                               -- "Gain Netto" (entry + legs)
    roi             NUMERIC,                               -- net_pnl/stake (stored)
    hourly_yield    NUMERIC,                               -- net_pnl/(time_min/60)
    -- contesto congelato dallo snapshot per la selezione scelta (analytics)
    edge_at_entry   NUMERIC,
    model_prob      NUMERIC,
    implied_prob    NUMERIC,
    affidabilita    NUMERIC,                               -- da get_direction
    concordi        SMALLINT,
    motori_totali   SMALLINT,
    followed_advice BOOLEAN,                               -- la selezione era tra i consigli?
    -- meta
    comment         TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    trade_date      DATE NOT NULL,                         -- giorno operativo (default kickoff::date)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pt_date      ON public.personal_trades (trade_date);
CREATE INDEX IF NOT EXISTS idx_pt_status    ON public.personal_trades (status);
CREATE INDEX IF NOT EXISTS idx_pt_strategia ON public.personal_trades (strategia);
CREATE INDEX IF NOT EXISTS idx_pt_league    ON public.personal_trades (league_id);
CREATE INDEX IF NOT EXISTS idx_pt_fixture   ON public.personal_trades (fixture_id);
CREATE INDEX IF NOT EXISTS idx_pt_watchlist ON public.personal_trades (watchlist_id);

------------------------------------------------------------------------------
-- 1.3 personal_trade_legs (coperture/hedge/cashout aggiuntivi)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.personal_trade_legs (
    id          BIGSERIAL PRIMARY KEY,
    trade_id    BIGINT NOT NULL REFERENCES public.personal_trades(id) ON DELETE CASCADE,
    leg_type    TEXT NOT NULL CHECK (leg_type IN ('hedge','cashout','coverage','adjust')),
    side        TEXT CHECK (side IN ('back','lay')),
    market      TEXT,
    selection   TEXT,
    odds        NUMERIC,
    stake       NUMERIC,
    liability   NUMERIC,
    timing      TEXT CHECK (timing IN ('prematch','live')),
    minute      SMALLINT,
    net_pnl     NUMERIC,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ptl_trade ON public.personal_trade_legs (trade_id);

------------------------------------------------------------------------------
-- RLS + lockdown tabelle: nessun accesso diretto da anon/authenticated.
-- L'accesso passa ESCLUSIVAMENTE dalle RPC SECURITY DEFINER (owner del DB).
-- NON usiamo FORCE RLS → service_role (backend) bypassa la RLS senza ostacoli.
------------------------------------------------------------------------------
ALTER TABLE public.personal_watchlist  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.personal_trades     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.personal_trade_legs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.personal_watchlist  FROM anon, authenticated;
REVOKE ALL ON TABLE public.personal_trades     FROM anon, authenticated;
REVOKE ALL ON TABLE public.personal_trade_legs FROM anon, authenticated;

-- difesa in profondità: le sequenze BIGSERIAL sono oggetti separati; togliamo
-- USAGE/SELECT a anon/authenticated così non possono enumerare i contatori ID.
REVOKE ALL ON SEQUENCE
    public.personal_watchlist_id_seq,
    public.personal_trades_id_seq,
    public.personal_trade_legs_id_seq
    FROM anon, authenticated;

-- ============================================================================
-- Le RPC sono in migrations/personal_tracking_rpc.sql (SECURITY DEFINER,
-- search_path fisso, grant solo authenticated + service_role, mai anon).
-- ============================================================================
