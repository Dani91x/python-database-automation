-- ============================================================================
-- replay_tennis_2026-10-07.sql - REPLAY TENNIS: tabelle e RPC SEPARATE dal calcio.
--
-- Ordine dell'utente (07/10/2026): "il replay del tennis va creato da 0 ... crea
-- una sezione separata per il replay tennis ... TENNIS E CALCIO SONO DISTINTI".
-- Questo file crea SOLO oggetti `tennis_replay_*` / `*_replay_tennis*` e non
-- tocca nessuna tabella o RPC del Match Replay del calcio (live_market_snapshots,
-- list_replays, get_replay*): nessuna partita di tennis puo' finire nel calcio.
--
-- Stessa architettura del calcio (live_stream.sql + live_stream_rpc_chunked.sql):
--   * tennis_replay_eventi     anagrafica e conteggi (1 riga per partita);
--   * tennis_replay_mercati    catalogo di TUTTI i mercati registrati, con le
--                              selezioni (nome, sortPriority, esito finale
--                              WINNER/LOSER dalla marketDefinition), betDelay e
--                              istante di regolamento (settled_ts);
--   * tennis_replay_snapshots  frame curati (ladder JSONB come il calcio: size
--                              in GBP storiche, il frontend converte in EUR);
--   * tennis_replay_punteggio  punteggio tennis nel tempo (TennisScoreState del
--                              runner: set, game, punti, servizio, tie-break),
--                              eventi della barra (BREAK, SET_END, ...) e punto.
-- RPC: list_replays_tennis, get_replay_tennis_meta, get_replay_tennis_frames.
--
-- Scrittura: SOLO il backend come service_role (importatore a mano e caricamento
-- a fine partita del runner tennis), idempotente per (evento, mercato).
--
-- SICUREZZA (come i blocchi del 24/09, SICUREZZA_DB_2026-09-24.md):
--   RLS ACCESA su ogni tabella, nessuna policy (lettura solo via RPC);
--   REVOKE ALL ad anon e authenticated su tabelle e sequenze; service_role
--   esplicito; RPC SECURITY DEFINER con search_path fissato, input whitelistato,
--   guardia owner `public.tennis_is_owner()` (tennis_bots.sql), EXECUTE tolto a
--   PUBLIC e anon, dato a authenticated e service_role.
-- Idempotente: si puo' rieseguire. NON applicata dal delegato: la applica l'utente
-- (SQL Editor, ruolo postgres). Verifica in coda (sola lettura).
-- ============================================================================

-- 0) guardia: i REVOKE/GRANT hanno senso solo come proprietario degli oggetti
DO $guardia$
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION 'Eseguire come postgres dal SQL Editor di Supabase (current_user = %)', current_user;
    END IF;
    IF to_regprocedure('public.tennis_is_owner()') IS NULL THEN
        RAISE EXCEPTION 'manca public.tennis_is_owner(): applicare prima migrations/tennis_bots.sql';
    END IF;
END
$guardia$;

------------------------------------------------------------------------------
-- 1) tennis_replay_eventi - una riga per partita registrata e caricata
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_replay_eventi (
    event_id          TEXT PRIMARY KEY,                    -- Betfair event_id
    competition_name  TEXT,
    player1_name      TEXT NOT NULL DEFAULT '',            -- sortPriority 1 del Match Odds (= home IPS)
    player2_name      TEXT NOT NULL DEFAULT '',
    open_date         TIMESTAMPTZ,                         -- marketDefinition.openDate
    n_markets         INTEGER NOT NULL DEFAULT 0,
    n_snapshots       INTEGER NOT NULL DEFAULT 0,
    n_score           INTEGER NOT NULL DEFAULT 0,
    ts_min            TIMESTAMPTZ,
    ts_max            TIMESTAMPTZ,
    fonte             TEXT NOT NULL DEFAULT 'import'
                         CHECK (fonte IN ('import', 'runner')),
    valuta            TEXT NOT NULL DEFAULT 'GBP' CHECK (valuta IN ('GBP', 'EUR')),
    raw_files         JSONB NOT NULL DEFAULT '[]'::jsonb,  -- percorsi dei file raw usati
    raw_bytes         BIGINT,
    diagnostica       JSONB,                               -- righe lette/scartate, buchi
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tre_open ON public.tennis_replay_eventi (open_date DESC);

------------------------------------------------------------------------------
-- 2) tennis_replay_mercati - catalogo di TUTTI i mercati registrati
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_replay_mercati (
    id             BIGSERIAL PRIMARY KEY,
    event_id       TEXT NOT NULL REFERENCES public.tennis_replay_eventi(event_id) ON DELETE CASCADE,
    market_id      TEXT NOT NULL,
    market_type    TEXT,                                   -- MATCH_ODDS, SET_BETTING, ...
    market_name    TEXT,
    sort_priority  INTEGER,
    selections     JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{selection_id, name, sort_priority, status}]
    bet_delay      INTEGER,                                -- marketDefinition.betDelay (s)
    settled_ts     TIMESTAMPTZ,                            -- primo istante CLOSED (regolato)
    n_updates      INTEGER NOT NULL DEFAULT 0,             -- snapshot curati del mercato
    ts_min         TIMESTAMPTZ,
    ts_max         TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, market_id)
);
CREATE INDEX IF NOT EXISTS idx_trm_event ON public.tennis_replay_mercati (event_id);

------------------------------------------------------------------------------
-- 3) tennis_replay_snapshots - frame curati (write-on-change, come il calcio)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_replay_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    event_id    TEXT NOT NULL REFERENCES public.tennis_replay_eventi(event_id) ON DELETE CASCADE,
    market_id   TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,                      -- publish time Betfair (UTC)
    inplay      BOOLEAN NOT NULL DEFAULT false,
    status      TEXT NOT NULL,                             -- OPEN|SUSPENDED|CLOSED
    ladder      JSONB NOT NULL,                            -- {sel: {back, lay, ltp, tv, trd?}}
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trs_event_market_ts ON public.tennis_replay_snapshots (event_id, market_id, ts);
CREATE INDEX IF NOT EXISTS idx_trs_event_ts        ON public.tennis_replay_snapshots (event_id, ts);
CREATE INDEX IF NOT EXISTS idx_trs_event_inplay_ts ON public.tennis_replay_snapshots (event_id, ts) WHERE inplay;

------------------------------------------------------------------------------
-- 4) tennis_replay_punteggio - punteggio tennis nel tempo (overlay del replay)
------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tennis_replay_punteggio (
    id           BIGSERIAL PRIMARY KEY,
    event_id     TEXT NOT NULL REFERENCES public.tennis_replay_eventi(event_id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL,                     -- orologio del POLL IPS (non del mercato)
    source       TEXT NOT NULL DEFAULT 'ips',
    score        JSONB NOT NULL,                           -- TennisScoreState
    event_types  TEXT[] NOT NULL DEFAULT '{}',             -- BREAK, SET_END, SET_START, TIEBREAK_START, MATCH_END, SALTO
    point        JSONB,                                    -- TennisPointEvent (null sulla prima riga)
    payload      JSONB,                                    -- riga IPS grezza, per audit
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trp_event_ts ON public.tennis_replay_punteggio (event_id, ts);

-- ============================================================================
-- RLS + lockdown (BLOCCHI del 24/09): nessun accesso diretto da anon/authenticated
-- ============================================================================
ALTER TABLE public.tennis_replay_eventi    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tennis_replay_mercati   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tennis_replay_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tennis_replay_punteggio ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
    public.tennis_replay_eventi, public.tennis_replay_mercati,
    public.tennis_replay_snapshots, public.tennis_replay_punteggio
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE
    public.tennis_replay_mercati_id_seq, public.tennis_replay_snapshots_id_seq,
    public.tennis_replay_punteggio_id_seq
    FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.tennis_replay_eventi, public.tennis_replay_mercati,
    public.tennis_replay_snapshots, public.tennis_replay_punteggio
    TO service_role;
GRANT USAGE, SELECT ON SEQUENCE
    public.tennis_replay_mercati_id_seq, public.tennis_replay_snapshots_id_seq,
    public.tennis_replay_punteggio_id_seq
    TO service_role;

-- ============================================================================
-- RPC 1: list_replays_tennis(p_limit) -> {rows: [...]}
-- ============================================================================
CREATE OR REPLACE FUNCTION public.list_replays_tennis(p_limit integer DEFAULT 100)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
    v_lim  integer := least(greatest(coalesce(p_limit, 100), 1), 500);
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'accesso negato';
    END IF;

    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'open_date') DESC NULLS LAST), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',         e.event_id,
                 'competition_name', e.competition_name,
                 'player1_name',     e.player1_name,
                 'player2_name',     e.player2_name,
                 'open_date',        e.open_date,
                 'n_markets',        e.n_markets,
                 'n_snapshots',      e.n_snapshots,
                 'n_score',          e.n_score,
                 'ts_min',           e.ts_min,
                 'ts_max',           e.ts_max,
                 'fonte',            e.fonte
               ) AS r
          FROM public.tennis_replay_eventi e
         WHERE e.n_snapshots > 0
         ORDER BY e.open_date DESC NULLS LAST
         LIMIT v_lim
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;

-- ============================================================================
-- RPC 2: get_replay_tennis_meta(p_event_id) - tutto cio' che serve PRIMA dei frame
-- (anagrafica, catalogo, punteggio, estremi temporali, inizio in gioco).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_replay_tennis_meta(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_event    jsonb;
    v_markets  jsonb;
    v_timeline jsonb;
    v_ts_min   timestamptz;
    v_ts_max   timestamptz;
    v_inplay   timestamptz;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'accesso negato';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;

    SELECT jsonb_build_object(
             'event_id',         e.event_id,
             'competition_name', e.competition_name,
             'player1_name',     e.player1_name,
             'player2_name',     e.player2_name,
             'open_date',        e.open_date,
             'valuta',           e.valuta
           )
      INTO v_event
      FROM public.tennis_replay_eventi e
     WHERE e.event_id = p_event_id;

    IF v_event IS NULL THEN
        RAISE EXCEPTION 'event_id % non trovato in tennis_replay_eventi', p_event_id;
    END IF;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'market_id',     m.market_id,
               'market_type',   m.market_type,
               'market_name',   m.market_name,
               'sort_priority', m.sort_priority,
               'selections',    m.selections,
               'bet_delay',     m.bet_delay,
               'settled_ts',    m.settled_ts
             ) ORDER BY coalesce(m.sort_priority, 999999), m.market_id
           ), '[]'::jsonb)
      INTO v_markets
      FROM public.tennis_replay_mercati m
     WHERE m.event_id = p_event_id;

    SELECT min(s.ts), max(s.ts)
      INTO v_ts_min, v_ts_max
      FROM public.tennis_replay_snapshots s
     WHERE s.event_id = p_event_id;

    SELECT min(s.ts)
      INTO v_inplay
      FROM public.tennis_replay_snapshots s
     WHERE s.event_id = p_event_id
       AND s.inplay;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'ts',          p.ts,
               'source',      p.source,
               'score',       p.score,
               'event_types', to_jsonb(p.event_types),
               'point',       p.point
             ) ORDER BY p.ts
           ), '[]'::jsonb)
      INTO v_timeline
      FROM public.tennis_replay_punteggio p
     WHERE p.event_id = p_event_id;

    RETURN jsonb_build_object(
        'event',          v_event,
        'markets',        v_markets,
        'score_timeline', v_timeline,
        'ts_min',         v_ts_min,
        'ts_max',         v_ts_max,
        'inplay_from_ts', v_inplay
    );
END;
$$;

-- ============================================================================
-- RPC 3: get_replay_tennis_frames - frame di UNA finestra [p_from_ts, p_to_ts),
-- al piu' 1 frame per (mercato, bucket di p_bucket_sec). Stessa forma dei frame
-- del calcio (`minute` sempre NULL: il tennis non ha minuto di gioco).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_replay_tennis_frames(
    p_event_id   text,
    p_from_ts    timestamptz,
    p_to_ts      timestamptz,
    p_bucket_sec integer DEFAULT 10,
    p_max_rows   integer DEFAULT 6000
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_frames jsonb;
    v_bucket integer := least(greatest(coalesce(p_bucket_sec, 10), 1), 600);
    v_max    integer := least(greatest(coalesce(p_max_rows, 6000), 100), 10000);
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'accesso negato';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;
    IF p_from_ts IS NULL OR p_to_ts IS NULL OR p_to_ts <= p_from_ts THEN
        RAISE EXCEPTION 'finestra temporale non valida';
    END IF;
    IF p_to_ts - p_from_ts > interval '12 hours' THEN
        RAISE EXCEPTION 'finestra temporale troppo ampia';
    END IF;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'market_id', x.market_id,
               'ts',        x.ts,
               'minute',    NULL,
               'inplay',    x.inplay,
               'status',    x.status,
               'ladder',    x.ladder
             )
           ), '[]'::jsonb)
      INTO v_frames
      FROM (
        SELECT DISTINCT ON (s.market_id, floor(extract(epoch FROM s.ts) / v_bucket))
               s.market_id, s.ts, s.inplay, s.status, s.ladder
          FROM public.tennis_replay_snapshots s
         WHERE s.event_id = p_event_id
           AND s.ts >= p_from_ts
           AND s.ts <  p_to_ts
         -- nel bucket vince l'ULTIMO frame (stato piu' recente: una chiusura o
         -- una sospensione a fine bucket non sparisce dietro un frame precedente)
         ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts DESC
         LIMIT v_max
      ) x;

    RETURN jsonb_build_object(
        'frames', v_frames,
        'n',      coalesce(jsonb_array_length(v_frames), 0)
    );
END;
$$;

-- ============================================================================
-- LOCKDOWN delle RPC: mai ad anon/PUBLIC
-- ============================================================================
REVOKE ALL ON FUNCTION public.list_replays_tennis(integer) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.get_replay_tennis_meta(text) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.get_replay_tennis_frames(text, timestamptz, timestamptz, integer, integer) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.list_replays_tennis(integer) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_replay_tennis_meta(text) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_replay_tennis_frames(text, timestamptz, timestamptz, integer, integer) TO authenticated, service_role;

-- ============================================================================
-- VERIFICA (SOLA LETTURA) - atteso: ogni riga 'OK'
-- ============================================================================
-- SELECT c.relname AS tabella, c.relrowsecurity AS rls_accesa,
--        has_table_privilege('anon', c.oid, 'SELECT')          AS anon_legge,
--        has_table_privilege('authenticated', c.oid, 'SELECT') AS auth_legge,
--        CASE WHEN c.relrowsecurity
--              AND NOT has_table_privilege('anon', c.oid, 'SELECT')
--              AND NOT has_table_privilege('authenticated', c.oid, 'SELECT')
--             THEN 'OK' ELSE 'KO' END AS esito
--   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--  WHERE n.nspname = 'public' AND c.relname LIKE 'tennis_replay_%' AND c.relkind = 'r';
--
-- SELECT p.oid::regprocedure AS rpc,
--        has_function_privilege('anon', p.oid, 'EXECUTE')          AS anon_esegue,
--        has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth_esegue,
--        CASE WHEN NOT has_function_privilege('anon', p.oid, 'EXECUTE')
--              AND has_function_privilege('authenticated', p.oid, 'EXECUTE')
--             THEN 'OK' ELSE 'KO' END AS esito
--   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--  WHERE n.nspname = 'public' AND p.proname IN ('list_replays_tennis', 'get_replay_tennis_meta', 'get_replay_tennis_frames');
