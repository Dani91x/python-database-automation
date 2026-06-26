-- ============================================================================
-- live_stream_rpc.sql — RPC per "Segui Live" e "Match Replay"
-- Tabelle: migrations/live_stream.sql.
--
-- Tutte SECURITY DEFINER, SET search_path = public, pg_temp.
-- Lettura: STABLE. Input whitelistato.
-- Grant: REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role.
-- MAI ad anon (lockdown in coda). Idempotente: CREATE OR REPLACE.
--
-- Stile mirror di personal_tracking_rpc.sql (jsonb_build_object, CTE, coalesce).
-- La scrittura delle tabelle live_* è fatta dal BACKEND come service_role
-- (bypassa RLS): NON servono RPC di scrittura qui.
-- ============================================================================


-- ============================================================================
-- get_live_follows — elenco partite agganciate allo stream + glance live_now.
-- Usata dalla tab "Segui Live" (lista). Per il dettaglio real-time il frontend
-- legge/sottoscrive direttamente public.live_now (Realtime).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_follows()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'open_date')), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',     f.event_id,
                 'fixture_id',   f.fixture_id,
                 'league_name',  f.league_name,
                 'home_name',    f.home_name,
                 'away_name',    f.away_name,
                 'open_date',    f.open_date,
                 'status',       f.status,
                 'error_detail', f.error_detail,
                 'inplay',       n.inplay,
                 'minute',       n.minute,
                 'score_home',   n.score_home,
                 'score_away',   n.score_away,
                 'live_status',  n.status,
                 'score_source', n.score_source,
                 'updated_at',   n.updated_at
               ) AS r
          FROM public.live_follow f
          LEFT JOIN public.live_now n ON n.event_id = f.event_id
         WHERE f.status IN ('PENDING','STREAMING','CLOSED')
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- list_replays — partite con replay disponibile (snapshot caricati).
-- Usata dalla tab "Match Replay" (selettore partita).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.list_replays(p_limit integer DEFAULT 100)
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
    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'open_date') DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',    f.event_id,
                 'fixture_id',  f.fixture_id,
                 'league_name', f.league_name,
                 'home_name',   f.home_name,
                 'away_name',   f.away_name,
                 'open_date',   f.open_date,
                 'status',      f.status,
                 'n_markets',   rl.n_markets,
                 'n_snapshots', rl.n_snapshots,
                 'started_at',  rl.started_at,
                 'ended_at',    rl.ended_at
               ) AS r
          FROM public.live_follow f
          JOIN public.live_run_log rl ON rl.event_id = f.event_id
         WHERE f.status = 'UPLOADED'
           AND coalesce(rl.n_snapshots, 0) > 0
         ORDER BY f.open_date DESC
         LIMIT v_lim
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- get_replay — payload COMPLETO per il simulatore di una partita.
--   { event, markets[], frames[], score_timeline[] }
-- markets   = catalogo (nomi mercato + selezioni) di TUTTI i mercati registrati.
-- frames    = snapshot curati in ordine cronologico (ladder per mercato/istante).
-- timeline  = punteggio/eventi nel tempo (overlay sul replay).
-- ============================================================================
-- p_bucket_sec: downsampling per coprire TUTTA la partita con payload limitato →
-- max 1 frame per mercato ogni p_bucket_sec secondi (default 6s). Così il replay
-- arriva fino a fine partita (niente troncamento alla prima parte).
CREATE OR REPLACE FUNCTION public.get_replay(
    p_event_id text,
    p_max_frames integer DEFAULT 40000,
    p_bucket_sec integer DEFAULT 6
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_event    jsonb;
    v_markets  jsonb;
    v_frames   jsonb;
    v_timeline jsonb;
    v_lim      integer := least(greatest(coalesce(p_max_frames, 40000), 1), 60000);
    v_bucket   integer := greatest(coalesce(p_bucket_sec, 6), 1);
BEGIN
    IF p_event_id IS NULL THEN
        RAISE EXCEPTION 'p_event_id nullo';
    END IF;
    -- guardia lunghezza: gli event_id Betfair sono brevi (~10 char); evita che
    -- input abnormi finiscano nei log / nel messaggio d'errore.
    IF length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;

    SELECT jsonb_build_object(
             'event_id',    f.event_id,
             'fixture_id',  f.fixture_id,
             'league_name', f.league_name,
             'home_name',   f.home_name,
             'away_name',   f.away_name,
             'open_date',   f.open_date,
             'status',      f.status
           )
      INTO v_event
      FROM public.live_follow f
     WHERE f.event_id = p_event_id;

    IF v_event IS NULL THEN
        RAISE EXCEPTION 'event_id % non trovato in live_follow', p_event_id;
    END IF;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'market_id',     m.market_id,
               'market_type',   m.market_type,
               'market_name',   m.market_name,
               'sort_priority', m.sort_priority,
               'selections',    m.selections
             ) ORDER BY coalesce(m.sort_priority, 999999), m.market_id
           ), '[]'::jsonb)
      INTO v_markets
      FROM public.live_markets m
     WHERE m.event_id = p_event_id;

    -- frames DOWNSAMPLED su bucket temporali: max 1 frame per mercato ogni
    -- v_bucket secondi → copre l'INTERA partita (no troncamento) con payload
    -- limitato. DISTINCT ON tiene il primo frame di ogni (mercato, bucket).
    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'market_id', x.market_id,
               'ts',        x.ts,
               'minute',    x.minute,
               'inplay',    x.inplay,
               'status',    x.status,
               'ladder',    x.ladder
             ) ORDER BY x.ts, x.market_id
           ), '[]'::jsonb)
      INTO v_frames
      FROM (
        SELECT DISTINCT ON (s.market_id, floor(extract(epoch FROM s.ts) / v_bucket))
               s.market_id, s.ts, s.minute, s.inplay, s.status, s.ladder
          FROM public.live_market_snapshots s
         WHERE s.event_id = p_event_id
         ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts
         LIMIT v_lim
      ) x;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'ts',         t.ts,
               'minute',     t.minute,
               'score_home', t.score_home,
               'score_away', t.score_away,
               'event_type', t.event_type,
               'source',     t.source
             ) ORDER BY t.ts
           ), '[]'::jsonb)
      INTO v_timeline
      FROM public.live_score_timeline t
     WHERE t.event_id = p_event_id;

    RETURN jsonb_build_object(
        'event',          v_event,
        'markets',        v_markets,
        'frames',         v_frames,
        'score_timeline', v_timeline
    );
END;
$$;


-- ============================================================================
-- LOCKDOWN — coerente con security_lockdown.sql.
-- Nega l'esecuzione ad anon; concede solo a authenticated + service_role.
-- ============================================================================
-- REVOKE ALL FROM public rimuove il grant EXECUTE di default che CREATE FUNCTION
-- assegna a PUBLIC; il REVOKE FROM anon è ridondante ma esplicito (belt-and-suspenders).
-- rimuovi le vecchie firme di get_replay (overload) prima di concedere la nuova
DROP FUNCTION IF EXISTS public.get_replay(text);
DROP FUNCTION IF EXISTS public.get_replay(text, integer);

REVOKE ALL ON FUNCTION public.get_live_follows()                  FROM public, anon;
REVOKE ALL ON FUNCTION public.list_replays(integer)               FROM public, anon;
REVOKE ALL ON FUNCTION public.get_replay(text, integer, integer)  FROM public, anon;

GRANT EXECUTE ON FUNCTION public.get_live_follows()                  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.list_replays(integer)              TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_replay(text, integer, integer)  TO authenticated, service_role;
