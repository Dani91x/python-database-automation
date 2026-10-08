-- ============================================================================
-- replay_tennis_fonte_nomi_2026-10-08.sql
-- Replay Tennis: l'elenco e la testata dichiarano DA DOVE VIENE il nome dei giocatori.
--
-- Perche' (08/10, cantiere 14, caso vero 35790089): il flusso Betfair non porta i
-- nomi dei runner. Senza catalogo ne' _names.json il convertitore ripiega sul nome
-- del punteggio IPS, che e' TRONCATO («Marcelo Tomas Barrios V»). L'importatore ora
-- scrive in `tennis_replay_eventi.diagnostica` (jsonb, gia' esistente) la chiave
-- `nomi_fonte` = {"player1_name": "<fonte>", "player2_name": "<fonte>"} con fonte in
-- catalogo | marketdef | evento | ips. Questa migrazione la ESPONE alla pagina:
--   * list_replays_tennis       -> ogni riga ha 'nomi_fonte' (null se assente);
--   * get_replay_tennis_meta    -> l'oggetto 'event' ha 'nomi_fonte' (null se assente).
-- La pagina, per un nome con fonte 'ips', mostra il tooltip «nome dall'IPS, troncato».
--
-- ATTENZIONE: questa versione di list_replays_tennis CONTIENE anche 'market_types'
-- (replay_tennis_mercati_elenco_2026-10-08.sql): applicandola si ha l'elenco completo
-- a prescindere dall'ordine. NON riapplicare DOPO questo file la sola
-- replay_tennis_mercati_elenco_2026-10-08.sql: ripristinerebbe la versione senza
-- 'nomi_fonte' (la verifica in coda lo mostra).
--
-- Tutto il resto e' IDENTICO alle versioni precedenti (stessa firma, stessa guardia
-- owner, stessi permessi). Nessuna tabella toccata, nessun dato scritto.
-- Prerequisito: replay_tennis_2026-10-07.sql applicata. Idempotente (CREATE OR
-- REPLACE). La applica l'utente dal SQL Editor (ruolo postgres).
-- Senza questa migrazione la pagina funziona come prima (nessuna nota sui nomi).
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
                 'nomi_fonte',       e.diagnostica -> 'nomi_fonte',
                 'open_date',        e.open_date,
                 'n_markets',        e.n_markets,
                 'market_types',     coalesce((
                                         SELECT jsonb_agg(t.market_type ORDER BY t.market_type)
                                           FROM (SELECT DISTINCT m.market_type
                                                   FROM public.tennis_replay_mercati m
                                                  WHERE m.event_id = e.event_id
                                                    AND m.market_type IS NOT NULL) t
                                     ), '[]'::jsonb),
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
             'nomi_fonte',       e.diagnostica -> 'nomi_fonte',
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

REVOKE ALL ON FUNCTION public.list_replays_tennis(integer) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.get_replay_tennis_meta(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.list_replays_tennis(integer) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_replay_tennis_meta(text) TO authenticated, service_role;

-- Verifica (sola lettura, dal SQL Editor come owner). Atteso: ogni riga con
-- ha_nomi_fonte = true E ha_market_types = true (le chiavi ci sono anche con valore null):
--   SELECT bool_and(r ? 'nomi_fonte') AS ha_nomi_fonte, bool_and(r ? 'market_types') AS ha_market_types
--     FROM jsonb_array_elements(public.list_replays_tennis(500)->'rows') r;
--   SELECT (public.get_replay_tennis_meta('35790089')->'event') ? 'nomi_fonte' AS meta_ha_nomi_fonte;
-- Dopo un reimport con la nuova versione, per la 35790089 senza nomi veri:
--   SELECT diagnostica->'nomi_fonte' FROM public.tennis_replay_eventi WHERE event_id = '35790089';
--   Atteso: {"player1_name": "ips", "player2_name": "ips"} finche' manca il catalogo;
--           {"player1_name": "catalogo", ...} dopo il reimport con _names.json.
