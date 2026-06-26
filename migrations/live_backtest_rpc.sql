-- ============================================================================
-- live_backtest_rpc.sql — RPC per "Backtest Automatico" e per gli alert in-app
-- Tabelle: migrations/live_backtest.sql, migrations/live_alerts.sql.
--
-- Tutte SECURITY DEFINER, SET search_path = public, pg_temp.
-- Lettura: STABLE. Scrittura: VOLATILE. Input whitelistato.
-- Grant: REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- MAI ad anon (lockdown in coda). Idempotente: CREATE OR REPLACE.
--
-- Stile mirror di live_stream_rpc.sql (jsonb_build_object, CTE, coalesce).
-- La scrittura diretta delle tabelle live_backtest_* / live_alerts è fatta dal
-- BACKEND come service_role (bypassa RLS); qui esponiamo solo le operazioni che
-- servono al frontend loggato (richiedere backtest, leggere run/risultati,
-- leggere/ack degli alert).
-- ============================================================================


-- ============================================================================
-- request_backtest — inserisce una richiesta di backtest e ne ritorna l'id.
-- Usata dal pulsante "Lancia backtest" nella tab "Backtest Automatico".
-- p_params deve essere un oggetto JSON non nullo (es. {events, mode, rules}).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_backtest(p_params jsonb)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_params IS NULL THEN
        RAISE EXCEPTION 'p_params nullo';
    END IF;
    IF jsonb_typeof(p_params) <> 'object' THEN
        RAISE EXCEPTION 'p_params deve essere un oggetto JSON';
    END IF;

    INSERT INTO public.live_backtest_requests (params)
    VALUES (p_params)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;


-- ============================================================================
-- list_backtest_runs — elenco richieste di backtest, più recenti prima.
-- Usata dalla tab per mostrare lo storico/stato delle esecuzioni.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.list_backtest_runs()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'created_at') DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'id',           q.id,
                 'status',       q.status,
                 'params',       q.params,
                 'created_at',   q.created_at,
                 'updated_at',   q.updated_at,
                 'error_detail', q.error_detail
               ) AS r
          FROM public.live_backtest_requests q
         ORDER BY q.created_at DESC
         LIMIT 200
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- list_backtest_results — risultati aggregati di una richiesta di backtest.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.list_backtest_results(p_request_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF p_request_id IS NULL THEN
        RAISE EXCEPTION 'p_request_id nullo';
    END IF;

    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'id')::bigint), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'id',           res.id,
                 'request_id',   res.request_id,
                 'scope',        res.scope,
                 'grp',          res.grp,
                 'n_bets',       res.n_bets,
                 'n_won',        res.n_won,
                 'hit_rate',     res.hit_rate,
                 'roi',          res.roi,
                 'total_pnl',    res.total_pnl,
                 'max_drawdown', res.max_drawdown,
                 'avg_odds',     res.avg_odds,
                 'metrics',      res.metrics,
                 'created_at',   res.created_at
               ) AS r
          FROM public.live_backtest_results res
         WHERE res.request_id = p_request_id
         ORDER BY res.id
         LIMIT 5000
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- get_live_alerts — avvisi NON letti, più recenti prima (per il banner in-app).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_alerts()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'created_at') DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'id',           a.id,
                 'level',        a.level,
                 'code',         a.code,
                 'message',      a.message,
                 'event_id',     a.event_id,
                 'acknowledged', a.acknowledged,
                 'created_at',   a.created_at
               ) AS r
          FROM public.live_alerts a
         WHERE a.acknowledged = false
         ORDER BY a.created_at DESC
         LIMIT 100
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- ack_alert — marca un avviso come letto (dismiss dal banner).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.ack_alert(p_id bigint)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_id IS NULL THEN
        RAISE EXCEPTION 'p_id nullo';
    END IF;

    UPDATE public.live_alerts
       SET acknowledged = true
     WHERE id = p_id;
END;
$$;


-- ============================================================================
-- LOCKDOWN — coerente con live_stream_rpc.sql / security_lockdown.sql.
-- Nega l'esecuzione a public/anon; concede solo a authenticated + service_role.
-- ============================================================================
REVOKE ALL ON FUNCTION public.request_backtest(jsonb)      FROM public, anon;
REVOKE ALL ON FUNCTION public.list_backtest_runs()         FROM public, anon;
REVOKE ALL ON FUNCTION public.list_backtest_results(uuid)  FROM public, anon;
REVOKE ALL ON FUNCTION public.get_live_alerts()            FROM public, anon;
REVOKE ALL ON FUNCTION public.ack_alert(bigint)            FROM public, anon;

GRANT EXECUTE ON FUNCTION public.request_backtest(jsonb)      TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.list_backtest_runs()         TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.list_backtest_results(uuid)  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_live_alerts()            TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.ack_alert(bigint)            TO authenticated, service_role;
