-- ============================================================================
-- get_replay — OTTIMIZZAZIONE PERFORMANCE (eventi grandi non aprivano il replay).
--
-- Problema: con registrazioni lunghe/dense (decine/centinaia di migliaia di
-- snapshot) la versione precedente produceva troppi frame — ciascuno porta il
-- JSONB `ladder` — e l'aggregazione ORDINATA di quell'array enorme superava lo
-- statement_timeout (8s, SQLSTATE 57014): la RPC falliva e il replay non si apriva.
--
-- Fix (nessuna perdita visibile — il frontend raggruppa la timeline a 10s e
-- riordina i frame per ts sia in MatchReplay.tsx sia in buildSnapshots):
--   1) BUCKET ADATTIVO: allarga il bucket per le registrazioni lunghe così il
--      totale frame resta ~ p_max_frames → veloce a prescindere dalla durata,
--      SENZA troncare la partita (niente LIMIT che tagliava la coda).
--   2) NIENTE ORDER BY nell'aggregazione dei frame: i consumer riordinano già per
--      ts → evitiamo di ordinare un grande array JSONB (costo dominante).
--   3) default bucket 6s → 10s (stessa granularità della timeline del frontend).
--   4) SET statement_timeout = 25s sulla funzione: rete di sicurezza per gli
--      eventi più grandi (meglio un load di qualche secondo che un fallimento).
--
-- Firma invariata get_replay(text,integer,integer) → i GRANT esistenti restano
-- validi; li ri-asseriamo in fondo per sicurezza (idempotente).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_replay(
    p_event_id text,
    p_max_frames integer DEFAULT 6000,   -- TARGET di frame (bucket adattivo per rispettarlo)
    p_bucket_sec integer DEFAULT 10      -- bucket MINIMO (allargato se serve)
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
SET statement_timeout = '25s'
AS $$
DECLARE
    v_event    jsonb;
    v_markets  jsonb;
    v_frames   jsonb;
    v_timeline jsonb;
    v_target   integer := least(greatest(coalesce(p_max_frames, 6000), 500), 40000);
    v_bucket   integer := greatest(coalesce(p_bucket_sec, 10), 1);
    v_span     integer;
    v_nmarkets integer;
BEGIN
    IF p_event_id IS NULL THEN
        RAISE EXCEPTION 'p_event_id nullo';
    END IF;
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

    -- BUCKET ADATTIVO: stima lo span temporale e allarga il bucket in modo che il
    -- totale frame (~ span/bucket * n_mercati) resti intorno a v_target. Il minimo
    -- resta p_bucket_sec. Una scan leggera min/max(ts) (indice idx_lms_event_ts).
    v_nmarkets := greatest(coalesce(jsonb_array_length(v_markets), 1), 1);
    SELECT extract(epoch FROM (max(s.ts) - min(s.ts)))::int
      INTO v_span
      FROM public.live_market_snapshots s
     WHERE s.event_id = p_event_id;
    IF v_span IS NOT NULL AND v_span > 0 THEN
        v_bucket := greatest(v_bucket, ceil(v_span::numeric * v_nmarkets / v_target)::int);
    END IF;

    -- frames DOWNSAMPLED: 1 frame per (mercato, bucket). NIENTE ORDER BY nell'agg
    -- (il frontend riordina per ts) → si evita di ordinare un grande array JSONB.
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
         ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts
      ) x;

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
        'frames',         v_frames,
        'score_timeline', v_timeline
    );
END;
$$;

-- lockdown invariato (firma identica): nega anon, concede authenticated/service_role.
REVOKE ALL ON FUNCTION public.get_replay(text, integer, integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_replay(text, integer, integer) TO authenticated, service_role;
