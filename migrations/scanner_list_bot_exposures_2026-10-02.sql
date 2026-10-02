-- ============================================================================
-- scanner_list_bot_exposures_2026-10-02.sql
--
-- R6 (02/10/2026, punto 27 "scanner mai cieco"): le ESPOSIZIONI DI TUTTI I BOT
-- (ordini vivi + posizioni aperte, paper E live) in UNA chiamata, invece delle
-- 6-7 SELECT che lo scanner faceva ogni 10 s (~60.000 letture/giorno).
--
-- Chi la usa: Betfair/safe_strategy/db.py::list_bot_exposures (service_role).
-- Finche' questa migrazione NON e' applicata lo scanner ripiega da solo sulle
-- letture per fonte (WARNING una volta sola): nulla si rompe.
--
-- Le STESSE regole del ripiego Python (db.py::_list_bot_exposures_a_fonti):
--   * omega_trades / safe_strategy_trades: status pending/open/hedged;
--   * betfair_live_orders / tennis_live_orders: status VIVO, nelle due grafie
--     di flumine (nome dell'Enum e valore);
--   * betfair_live_positions: esposizione aperta (|vinci - perdi| >= 0,01 o
--     esposizione non abbinata > 0) su un mercato NON regolato nella stessa
--     modalita' (betfair_live_settled), toccata negli ultimi 7 giorni;
--   * tennis_live_positions: esposizione aperta, ultimi 7 giorni (il tennis
--     non ha una tabella di regolazione).
-- `source` dello specchio letto via to_jsonb: la funzione non dipende dalla
-- migrazione che ha aggiunto la colonna.
--
-- Sola lettura, STABLE, SECURITY DEFINER con search_path fisso e guardia
-- owner-only (betfair_live_is_owner(): service_role o l'owner; un altro
-- chiamante riceve zero righe), come le altre RPC del conto
-- (get_live_positions_all). EXECUTE solo a service_role. IDEMPOTENTE.
--
-- VERIFICA (sola lettura, dopo l'applicazione, dall'SQL editor):
--   SELECT jsonb_array_length(public.list_bot_exposures()->'rows');
-- ============================================================================

-- LANGUAGE sql (non plpgsql) DI PROPOSITO: il corpo si valida alla CREATE, cosi'
-- una tabella o una colonna mancante fa fallire l'applicazione davanti
-- all'utente invece di far fallire ogni chiamata dello scanner a runtime.
CREATE OR REPLACE FUNCTION public.list_bot_exposures()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    WITH esposte AS (
        SELECT o.event_id::text AS event_id, o.market_id::text AS market_id,
               'omega'::text AS bot, o.mode::text AS modalita, 'calcio'::text AS sport
          FROM public.omega_trades o
         WHERE o.status IN ('pending', 'open', 'hedged')
        UNION ALL
        SELECT s.event_id::text, s.market_id::text, 'safe', s.mode::text,
               coalesce(s.sport::text, 'calcio')
          FROM public.safe_strategy_trades s
         WHERE s.status IN ('pending', 'open', 'hedged')
        UNION ALL
        SELECT b.event_id::text, b.market_id::text,
               coalesce(to_jsonb(b) ->> 'source', 'specchio'), b.mode::text, 'calcio'
          FROM public.betfair_live_orders b
         WHERE b.status IN ('PENDING', 'EXECUTABLE', 'CANCELLING', 'UPDATING', 'REPLACING',
                            'Pending', 'Executable', 'Cancelling', 'Updating', 'Replacing')
        UNION ALL
        SELECT p.event_id::text, p.market_id::text, 'specchio', p.mode::text, 'calcio'
          FROM public.betfair_live_positions p
         WHERE p.updated_at >= now() - interval '7 days'
           AND (abs(coalesce(p.matched_if_win, 0) - coalesce(p.matched_if_lose, 0)) >= 0.01
                OR coalesce(p.unmatched_back_exposure, 0) > 0
                OR coalesce(p.unmatched_lay_exposure, 0) > 0)
           AND NOT EXISTS (SELECT 1 FROM public.betfair_live_settled r
                            WHERE r.market_id = p.market_id AND r.mode = p.mode)
        UNION ALL
        SELECT t.event_id::text, t.market_id::text,
               coalesce(to_jsonb(t) ->> 'source', 'specchio'), t.mode::text, 'tennis'
          FROM public.tennis_live_orders t
         WHERE t.status IN ('PENDING', 'EXECUTABLE', 'CANCELLING', 'UPDATING', 'REPLACING',
                            'Pending', 'Executable', 'Cancelling', 'Updating', 'Replacing')
        UNION ALL
        SELECT q.event_id::text, q.market_id::text, 'specchio', q.mode::text, 'tennis'
          FROM public.tennis_live_positions q
         WHERE q.updated_at >= now() - interval '7 days'
           AND (abs(coalesce(q.matched_if_win, 0) - coalesce(q.matched_if_lose, 0)) >= 0.01
                OR coalesce(q.unmatched_back_exposure, 0) > 0
                OR coalesce(q.unmatched_lay_exposure, 0) > 0)
    )
    SELECT jsonb_build_object('rows', coalesce(jsonb_agg(jsonb_build_object(
               'event_id', e.event_id, 'market_id', e.market_id, 'bot', e.bot,
               'modalita', e.modalita, 'sport', e.sport)), '[]'::jsonb))
      FROM esposte e
     WHERE e.event_id IS NOT NULL
       -- guardia owner-only (service_role o l'owner), come le RPC del conto
       AND public.betfair_live_is_owner();
$$;

REVOKE ALL    ON FUNCTION public.list_bot_exposures() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_bot_exposures() TO service_role;
