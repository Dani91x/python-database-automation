-- ============================================================================
-- live_stream_rpc_chunked.sql — Match Replay: caricamento a FINESTRE TEMPORALI
--
-- PERCHÉ: get_replay (payload unico) muore sugli eventi grandi con
-- "canceling statement due to statement timeout" (codice 57014). Il limite di
-- statement_timeout del RUOLO API (~8s) si arma all'INIZIO dello statement:
-- il `SET statement_timeout` dentro la funzione NON ha effetto sullo statement
-- già in corso. Con 40k-91k snapshot la singola chiamata non può farcela.
--
-- SOLUZIONE: due RPC leggere che il frontend chiama in sequenza:
--   • get_replay_meta(event)                → event, markets, score_timeline,
--       ts_min/ts_max, inplay_from_ts (tutte query da indice, <1s)
--   • get_replay_frames(event, from, to, bucket, max) → SOLO i frame della
--       finestra [from, to), downsampled a 1 frame/mercato/bucket_sec.
--       Ogni finestra tocca poche migliaia di righe → sempre sotto il timeout.
--
-- get_replay (live_stream_rpc.sql) RESTA per compatibilità: il frontend la usa
-- come fallback finché questa migrazione non è applicata.
--
-- Convenzioni: SECURITY DEFINER, STABLE, search_path fissato, input whitelistato,
-- REVOKE da public/anon, GRANT a authenticated+service_role. Idempotente.
-- ============================================================================

-- Indice PARZIALE per trovare l'istante del calcio d'inizio (primo snapshot
-- in-play) con una probe: usato da get_replay_meta.
CREATE INDEX IF NOT EXISTS idx_lms_event_inplay_ts
    ON public.live_market_snapshots (event_id, ts)
    WHERE inplay;

-- ============================================================================
-- get_replay_meta — tutto ciò che serve PRIMA dei frame: anagrafica evento,
-- catalogo mercati, score timeline completa e l'estensione temporale reale
-- della registrazione (per pianificare le finestre di fetch dei frame).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_replay_meta(p_event_id text)
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
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
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

    -- estremi temporali della registrazione: probe sull'indice (event_id, ts)
    SELECT min(s.ts), max(s.ts)
      INTO v_ts_min, v_ts_max
      FROM public.live_market_snapshots s
     WHERE s.event_id = p_event_id;

    -- primo snapshot IN-PLAY (calcio d'inizio secondo Betfair): probe
    -- sull'indice parziale idx_lms_event_inplay_ts.
    SELECT min(s.ts)
      INTO v_inplay
      FROM public.live_market_snapshots s
     WHERE s.event_id = p_event_id
       AND s.inplay;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'ts',         t.ts,
               'minute',     t.minute,
               'score_home', t.score_home,
               'score_away', t.score_away,
               'event_type', t.event_type,
               'source',     t.source,
               'payload',    t.payload
             ) ORDER BY t.ts
           ), '[]'::jsonb)
      INTO v_timeline
      FROM public.live_score_timeline t
     WHERE t.event_id = p_event_id;

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
-- get_replay_frames — frame di UNA finestra temporale [p_from_ts, p_to_ts),
-- downsampled: max 1 frame per (mercato, bucket di p_bucket_sec secondi).
-- Il frontend somma le finestre e riordina per ts (come già fa).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_replay_frames(
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
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;
    IF p_from_ts IS NULL OR p_to_ts IS NULL OR p_to_ts <= p_from_ts THEN
        RAISE EXCEPTION 'finestra temporale non valida';
    END IF;
    -- guardia: finestre oltre le 12h rifiutate (il client usa finestre di minuti)
    IF p_to_ts - p_from_ts > interval '12 hours' THEN
        RAISE EXCEPTION 'finestra temporale troppo ampia';
    END IF;

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'market_id', x.market_id,
               'ts',        x.ts,
               'minute',    x.minute,
               'inplay',    x.inplay,
               'status',    x.status,
               'ladder',    x.ladder
             )
           ), '[]'::jsonb)
      INTO v_frames
      FROM (
        SELECT DISTINCT ON (s.market_id, floor(extract(epoch FROM s.ts) / v_bucket))
               s.market_id, s.ts, s.minute, s.inplay, s.status, s.ladder
          FROM public.live_market_snapshots s
         WHERE s.event_id = p_event_id
           AND s.ts >= p_from_ts
           AND s.ts <  p_to_ts
         ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts
         LIMIT v_max
      ) x;

    RETURN jsonb_build_object(
        'frames', v_frames,
        'n',      coalesce(jsonb_array_length(v_frames), 0)
    );
END;
$$;

-- ============================================================================
-- LOCKDOWN — come live_stream_rpc.sql: mai ad anon/public.
-- ============================================================================
REVOKE ALL ON FUNCTION public.get_replay_meta(text) FROM public, anon;
REVOKE ALL ON FUNCTION public.get_replay_frames(text, timestamptz, timestamptz, integer, integer) FROM public, anon;

GRANT EXECUTE ON FUNCTION public.get_replay_meta(text) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_replay_frames(text, timestamptz, timestamptz, integer, integer) TO authenticated, service_role;
