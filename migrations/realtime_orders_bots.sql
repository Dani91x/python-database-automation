-- ============================================================================
-- realtime_orders_bots.sql — REALTIME (canale WS) per ordini, posizioni e bot.
--
-- Richiesta 16/07: "NON polling, deve essere il canale WS realtime".
-- La UI ladder (calcio+tennis) e il Bot Panel tennis passano da poll a
-- postgres_changes: queste tabelle devono stare nella publication
-- supabase_realtime e avere una policy SELECT per il SOTTOSCRITTORE (Realtime
-- rispetta la RLS del sottoscrittore; senza policy non arriva NULLA).
--
-- SICUREZZA (fix audit 16/07): le policy NON sono USING(true) — userebbero il
-- lockdown owner-only del queue-migration. Si riusa public.betfair_live_is_owner()
-- (stessa email del lockdown): anche se domani si riaprissero i signup, nessun
-- altro 'authenticated' potrebbe leggere ordini/posizioni. MAI anon.
--
-- Idempotente: eseguibile più volte senza errori.
-- DA APPLICARE MANUALMENTE nel SQL editor di Supabase, DOPO
-- betfair_live_order_queue.sql / tennis_orders.sql / tennis_bots.sql / tennis_markets.sql.
-- ============================================================================

-- La policy RLS gira col ruolo del sottoscrittore (authenticated): serve EXECUTE
-- sulla guard. La funzione legge SOLO i claim JWT ("chi sei"), non tabelle:
-- esporla ad authenticated non fa trapelare nulla oltre a "sei l'owner? sì/no".
GRANT EXECUTE ON FUNCTION public.betfair_live_is_owner() TO authenticated;

-- ---------------------------------------------------------------- TENNIS ----
DROP POLICY IF EXISTS tennis_live_orders_select_authenticated ON public.tennis_live_orders;
DROP POLICY IF EXISTS tennis_live_orders_select_owner ON public.tennis_live_orders;
CREATE POLICY tennis_live_orders_select_owner ON public.tennis_live_orders
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.tennis_live_orders TO authenticated;
REVOKE SELECT ON TABLE public.tennis_live_orders FROM anon;

DROP POLICY IF EXISTS tennis_live_positions_select_authenticated ON public.tennis_live_positions;
DROP POLICY IF EXISTS tennis_live_positions_select_owner ON public.tennis_live_positions;
CREATE POLICY tennis_live_positions_select_owner ON public.tennis_live_positions
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.tennis_live_positions TO authenticated;
REVOKE SELECT ON TABLE public.tennis_live_positions FROM anon;

DROP POLICY IF EXISTS tennis_bot_control_select_authenticated ON public.tennis_bot_control;
DROP POLICY IF EXISTS tennis_bot_control_select_owner ON public.tennis_bot_control;
CREATE POLICY tennis_bot_control_select_owner ON public.tennis_bot_control
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.tennis_bot_control TO authenticated;
REVOKE SELECT ON TABLE public.tennis_bot_control FROM anon;

DROP POLICY IF EXISTS tennis_bot_activity_select_authenticated ON public.tennis_bot_activity;
DROP POLICY IF EXISTS tennis_bot_activity_select_owner ON public.tennis_bot_activity;
CREATE POLICY tennis_bot_activity_select_owner ON public.tennis_bot_activity
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.tennis_bot_activity TO authenticated;
REVOKE SELECT ON TABLE public.tennis_bot_activity FROM anon;

-- tennis_markets: lista partite/quote del giorno (Screen 2) — realtime per far
-- aggiornare la lista da sola quando il worker scrive nuove quote.
DROP POLICY IF EXISTS tennis_markets_select_authenticated ON public.tennis_markets;
DROP POLICY IF EXISTS tennis_markets_select_owner ON public.tennis_markets;
CREATE POLICY tennis_markets_select_owner ON public.tennis_markets
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.tennis_markets TO authenticated;
REVOKE SELECT ON TABLE public.tennis_markets FROM anon;

-- ---------------------------------------------------------------- CALCIO ----
DROP POLICY IF EXISTS betfair_live_orders_select_authenticated ON public.betfair_live_orders;
DROP POLICY IF EXISTS betfair_live_orders_select_owner ON public.betfair_live_orders;
CREATE POLICY betfair_live_orders_select_owner ON public.betfair_live_orders
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.betfair_live_orders TO authenticated;
REVOKE SELECT ON TABLE public.betfair_live_orders FROM anon;

DROP POLICY IF EXISTS betfair_live_positions_select_authenticated ON public.betfair_live_positions;
DROP POLICY IF EXISTS betfair_live_positions_select_owner ON public.betfair_live_positions;
CREATE POLICY betfair_live_positions_select_owner ON public.betfair_live_positions
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.betfair_live_positions TO authenticated;
REVOKE SELECT ON TABLE public.betfair_live_positions FROM anon;

-- ------------------------------------------------- publication (idempotente) ----
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'tennis_live_orders', 'tennis_live_positions',
        'tennis_bot_control', 'tennis_bot_activity', 'tennis_markets',
        'betfair_live_orders', 'betfair_live_positions'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
             WHERE pubname = 'supabase_realtime' AND schemaname = 'public'
               AND tablename = t
        ) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
        END IF;
    END LOOP;
END $$;
