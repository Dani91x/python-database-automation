-- ============================================================================
-- replay_tennis_mercati_elenco_2026-10-08.sql
-- Replay Tennis: l'ELENCO delle partite dichiara i MERCATI registrati.
--
-- Perche' (08/10, caso vero 35797566): nell'elenco una partita col solo
-- SET_BETTING si presentava come le altre e <<Applica bot>> rispondeva
-- <<registrazione assente>>. I bot tennis lavorano sul MATCH_ODDS: l'elenco
-- deve dire quali mercati ha ogni partita (la pagina, quando la partita e'
-- aperta, li legge gia' da get_replay_tennis_meta e spegne <<Applica>> col
-- motivo; questa migrazione serve SOLO all'elenco).
--
-- Cosa cambia: list_replays_tennis aggiunge a ogni riga la chiave
-- 'market_types' (tipi DISTINTI da tennis_replay_mercati, in ordine
-- alfabetico; [] se nessuno). Tutto il resto e' IDENTICO alla versione di
-- replay_tennis_2026-10-07.sql (stessa firma, stessa guardia owner, stessi
-- permessi). Nessuna tabella toccata, nessun dato scritto.
--
-- Prerequisito: replay_tennis_2026-10-07.sql applicata.
-- Idempotente (CREATE OR REPLACE). La applica l'utente dal SQL Editor.
-- Senza questa migrazione la pagina funziona come prima (mostra <N> mercati).
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

REVOKE ALL ON FUNCTION public.list_replays_tennis(integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.list_replays_tennis(integer) TO authenticated, service_role;

-- Verifica (sola lettura, dal SQL Editor come owner):
--   SELECT r->>'event_id', r->'market_types'
--     FROM jsonb_array_elements(public.list_replays_tennis(500)->'rows') r
--    WHERE r->>'event_id' IN ('35797566', '35790089', '35793960');
-- Atteso: 35797566 -> ["SET_BETTING"], 35790089 -> ["MATCH_ODDS"],
--         35793960 -> ["MATCH_ODDS", "SET_BETTING"].
