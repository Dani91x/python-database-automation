-- ============================================================================
-- FIX "Segui Live": mostra OGNI partita selezionata dall'utente.
--
-- PROBLEMA (06/07): get_live_follows leggeva SOLO public.live_follow con
-- WHERE status IN ('PENDING','STREAMING','CLOSED'). Conseguenze:
--   * le partite in ERROR (registrazione fallita, es. WinError 10035) sparivano;
--   * le partite selezionate ma NON ancora promosse dal recorder a live_follow
--     (es. aggiunte a ridosso del KO) non comparivano affatto.
-- L'utente vedeva un sottoinsieme di cio' che aveva selezionato.
--
-- CURA: la lista e' guidata dalla SELEZIONE dell'utente
-- (personal_watchlist.follow_live = true), con LEFT JOIN a live_follow per lo
-- stato reale e a live_now per il glance realtime. Cosi' OGNI selezione appare:
--   * non ancora agganciata -> status 'IN_ATTESA' (event_id null);
--   * in registrazione       -> 'PENDING'/'STREAMING';
--   * fallita                -> 'ERROR' (con error_detail);
--   * finita e caricata      -> esclusa (e' nel Match Replay).
-- Finestra: kickoff nelle ultime 12h .. futuro (non trascina partite vecchie).
--
-- Idempotente: CREATE OR REPLACE. Nessuna modifica allo scalper.
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
    SELECT coalesce(jsonb_agg(r ORDER BY od), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT DISTINCT ON (w.fixture_id)
               jsonb_build_object(
                 'event_id',     f.event_id,
                 'fixture_id',   w.fixture_id,
                 'league_name',  coalesce(f.league_name, w.league_name),
                 'home_name',    coalesce(f.home_name, w.home_team),
                 'away_name',    coalesce(f.away_name, w.away_team),
                 'open_date',    coalesce(f.open_date, w.kickoff),
                 'status',       coalesce(f.status, 'IN_ATTESA'),
                 'error_detail', f.error_detail,
                 'inplay',       n.inplay,
                 'minute',       n.minute,
                 'score_home',   n.score_home,
                 'score_away',   n.score_away,
                 'live_status',  n.status,
                 'score_source', n.score_source,
                 'updated_at',   n.updated_at
               ) AS r,
               coalesce(f.open_date, w.kickoff) AS od
          FROM public.personal_watchlist w
          LEFT JOIN public.live_follow f ON f.fixture_id = w.fixture_id
          LEFT JOIN public.live_now   n ON n.event_id   = f.event_id
         WHERE w.follow_live = true
           AND w.kickoff >= now() - interval '12 hours'
           AND coalesce(f.status, '') <> 'UPLOADED'
         ORDER BY w.fixture_id, f.updated_at DESC NULLS LAST
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;

-- (i GRANT esistenti sulla funzione restano validi: CREATE OR REPLACE non li tocca)
