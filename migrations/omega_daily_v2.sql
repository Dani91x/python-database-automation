-- ============================================================================
-- omega_daily_v2.sql — OMEGA §14 (11/09/2026): GIORNATA = PARTITE DEL GIORNO,
-- obiettivo storicizzato per giorno, due gambe sempre, dati storici HT→FT.
--
-- Da applicare DOPO daily_history.sql (ricrea le RPC dello storico con la
-- nuova attribuzione) e omega_cashout.sql (ricrea get_omega_state).
--
-- Cosa cambia:
--   1. omega_daily_goal — snapshot dell'obiettivo che valeva in OGNI giornata
--      (scritto da omega_activate / omega_update_params e dal servizio): lo
--      storico mostra l'obiettivo di quel giorno, non quello corrente.
--   2. get_omega_state — realized_today = P&L delle POSIZIONI PIAZZATE OGGI
--      (le gambe di chiusura ereditano il giorno dell'apertura che chiudono).
--      Una gamba di ieri regolata dopo mezzanotte non sposta la barra di oggi.
--      + legs_today / events_today per la dashboard.
--   3. trading_daily_history / trading_day_trades — parametro p_day_by:
--      'placed' (Omega: giornata = giorno di piazzamento della posizione) |
--      'settled' (Safe: invariato). get_omega_daily usa 'placed' e l'obiettivo
--      per giorno; get_safe_daily resta identico nel comportamento.
--   4. omega_events.model — λ pre-match risolti e persistiti per evento
--      (sopravvivono ai riavvii di scanner/servizio: la gamba 2T non resta mai
--      senza modello).
--   5. omega_ht_ft_transitions — conteggi storici (punteggio al 45′ → finale)
--      per lega e globali dalla tabella matches; RPC get_omega_ht_ft.
--
-- IDEMPOTENTE. Owner-only via public.betfair_live_is_owner(); stessa politica
-- di grant delle migrazioni precedenti (REVOKE public/anon, GRANT
-- authenticated + service_role sui wrapper; motori comuni solo service_role).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Obiettivo per giornata
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.omega_daily_goal (
    day         DATE PRIMARY KEY,
    goal        NUMERIC NOT NULL CHECK (goal >= 0 AND goal <= 100000),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_daily_goal ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_daily_goal FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.omega_snapshot_daily_goal(p_goal numeric)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    INSERT INTO public.omega_daily_goal (day, goal, updated_at)
    VALUES ((now() AT TIME ZONE 'Europe/Rome')::date, p_goal, now())
    ON CONFLICT (day) DO UPDATE SET goal = EXCLUDED.goal, updated_at = now();
$$;
REVOKE ALL ON FUNCTION public.omega_snapshot_daily_goal(numeric) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_snapshot_daily_goal(numeric) TO service_role;

CREATE OR REPLACE FUNCTION public.omega_activate(
    p_mode        text DEFAULT 'paper',
    p_daily_goal  numeric DEFAULT 250,
    p_params      jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    IF p_daily_goal IS NULL OR p_daily_goal < 0 OR p_daily_goal > 100000 THEN
        RAISE EXCEPTION 'daily_goal fuori range [0,100000]: %', p_daily_goal;
    END IF;
    UPDATE public.omega_control SET
        status      = 'running',
        mode        = p_mode,
        daily_goal  = p_daily_goal,
        params      = coalesce(p_params, '{}'::jsonb),
        error       = NULL,
        started_at  = now(),
        stopped_at  = NULL,
        updated_at  = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    PERFORM public.omega_snapshot_daily_goal(p_daily_goal);
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_activate(text,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_activate(text,numeric,jsonb) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.omega_update_params(
    p_daily_goal  numeric DEFAULT NULL,
    p_params      jsonb DEFAULT NULL,
    p_mode        text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NOT NULL AND p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    IF p_daily_goal IS NOT NULL AND (p_daily_goal < 0 OR p_daily_goal > 100000) THEN
        RAISE EXCEPTION 'daily_goal fuori range [0,100000]: %', p_daily_goal;
    END IF;
    UPDATE public.omega_control SET
        daily_goal = coalesce(p_daily_goal, daily_goal),
        params     = coalesce(p_params, params),
        mode       = coalesce(p_mode, mode),
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    IF p_daily_goal IS NOT NULL THEN
        PERFORM public.omega_snapshot_daily_goal(p_daily_goal);
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_update_params(numeric,jsonb,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_update_params(numeric,jsonb,text) TO authenticated, service_role;

-- snapshot di oggi con l'obiettivo corrente (così lo storico ha almeno oggi)
INSERT INTO public.omega_daily_goal (day, goal)
SELECT (now() AT TIME ZONE 'Europe/Rome')::date, c.daily_goal FROM public.omega_control c WHERE c.id = 1
ON CONFLICT (day) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. get_omega_state — realizzato di OGGI = posizioni PIAZZATE oggi
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_state(
    p_activity_limit integer DEFAULT 50
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl jsonb;
    v_act  jsonb;
    v_agg  jsonb;
    v_goal jsonb;
    v_day  timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.omega_control c WHERE c.id = 1;

    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        -- §14: giornata di una posizione = giorno di piazzamento dell'APERTURA
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.pos_placed_at >= v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))), 0),
        'matches_traded',  count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        'matches_traded_today', count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))
                               AND t.placed_at >= v_day),
        'legs_today',      count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= v_day),
        'events_today',    count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= v_day),
        'matches_open',    count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))),
        'matches_won',     count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'won'),
        'matches_lost',    count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'lost'),
        'won_today',       count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'won' AND t.placed_at >= v_day),
        'lost_today',      count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'lost' AND t.placed_at >= v_day)
    ) INTO v_agg
      FROM (SELECT o.*,
                   (o.bet_id IS NOT NULL OR (o.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed,
                   coalesce(p.placed_at, o.placed_at) AS pos_placed_at
              FROM public.omega_trades o
              LEFT JOIN public.omega_trades p ON p.id = o.closes_trade_id) t;

    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.omega_activity
             ORDER BY ts DESC
             LIMIT least(greatest(coalesce(p_activity_limit, 50), 1), 300)) a;

    SELECT to_jsonb(g.goal) INTO v_goal FROM public.omega_daily_goal g
     WHERE g.day = (now() AT TIME ZONE 'Europe/Rome')::date;

    RETURN jsonb_build_object('control', v_ctrl, 'aggregates', v_agg, 'activity', v_act,
                              'goal_today', v_goal);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_state(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. Storico per giornata: attribuzione 'placed' | 'settled'
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.trading_daily_history(text,text,text,text,date,date,numeric);
CREATE OR REPLACE FUNCTION public.trading_daily_history(
    p_table         text,
    p_strategy_expr text,
    p_sport_expr    text,
    p_filter_expr   text,
    p_from          date,
    p_to            date,
    p_goal          numeric,
    p_day_by        text DEFAULT 'settled'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_from timestamptz;
    v_to   timestamptz;
    v_out  jsonb;
    v_by_placed boolean;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed') THEN
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', p_from, p_to;
    END IF;
    IF (p_to - p_from) > 400 THEN
        RAISE EXCEPTION 'intervallo troppo ampio (max 400 giorni): % → %', p_from, p_to;
    END IF;
    v_by_placed := (p_day_by = 'placed');
    v_from := (p_from::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    EXECUTE format($q$
        WITH originals AS (
            SELECT t.id, t.status, t.pnl::numeric AS pnl, t.liability::numeric AS liability,
                   t.origin, t.placed_at, t.settled_at,
                   (%s)::text AS strategy, (%s)::text AS sport,
                   (t.placed_at  AT TIME ZONE 'Europe/Rome')::date AS placed_day,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day,
                   -- giorno "di regolazione" usato dalle statistiche: con
                   -- l'attribuzione 'placed' è il giorno di piazzamento
                   CASE WHEN $6 THEN (t.placed_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS op_settled_day,
                   (t.bet_id IS NOT NULL OR (t.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed
              FROM public.%I t
             WHERE t.closes_trade_id IS NULL
               AND (%s)
               AND ((t.placed_at >= $1 AND t.placed_at < $2)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), closers AS (
            SELECT t.id, t.closes_trade_id, t.status, t.pnl::numeric AS pnl, t.market_id,
                   t.commission::numeric AS commission, t.meta, t.settled_at,
                   CASE WHEN $6 THEN (o.placed_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS settled_day
              FROM public.%I t
              JOIN public.%I o ON o.id = t.closes_trade_id
             WHERE t.closes_trade_id IS NOT NULL
               AND (%s)
               AND (t.closes_trade_id IN (SELECT id FROM originals)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), placed AS (
            SELECT * FROM originals
             WHERE status <> 'error'
               AND (status <> 'pending' OR is_placed)
               AND placed_day BETWEEN $3 AND $4
        ), trade_tot AS (
            SELECT o.id, o.op_settled_day AS settled_day, o.status, o.strategy, o.sport, o.origin,
                   o.pnl + coalesce((SELECT sum(c.pnl) FROM closers c
                                      WHERE c.closes_trade_id = o.id
                                        AND c.status IN ('won','lost','void')), 0) AS total_pnl
              FROM originals o
             WHERE o.status IN ('won','lost','void')
               AND o.op_settled_day BETWEEN $3 AND $4
        ), settled_rows AS (
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM (SELECT o.op_settled_day AS settled_day, o.pnl, t.market_id, t.commission::numeric AS commission, t.meta
                      FROM originals o JOIN public.%I t ON t.id = o.id
                     WHERE o.status IN ('won','lost','void')) x
            UNION ALL
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM closers WHERE status IN ('won','lost','void')
        ), days AS (
            SELECT placed_day AS op_day FROM placed
            UNION
            SELECT op_day FROM settled_rows WHERE op_day BETWEEN $3 AND $4
        ), comm_market AS (
            SELECT op_day, market_id,
                   sum(nullif(meta->>'commission_paid','')::numeric) AS paid,
                   sum(pnl) AS net,
                   coalesce(avg(commission), 0.05) AS c
              FROM settled_rows
             WHERE op_day BETWEEN $3 AND $4
             GROUP BY op_day, market_id
        ), comm_day AS (
            SELECT op_day,
                   CASE WHEN bool_or(paid IS NOT NULL) THEN sum(coalesce(paid, 0))
                        ELSE sum(CASE WHEN net > 0 AND c < 1 THEN net * c / (1 - c) ELSE 0 END)
                   END AS commission_paid
              FROM comm_market GROUP BY op_day
        ), brk AS (
            SELECT op_day, dim, dim_key,
                   count(*) FILTER (WHERE kind = 'placed')            AS n,
                   coalesce(sum(total_pnl) FILTER (WHERE kind = 'settled'), 0) AS pnl,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'won')  AS won,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'lost') AS lost
              FROM (
                  SELECT placed_day AS op_day, 'strategy' AS dim, strategy AS dim_key, 'placed' AS kind, 0::numeric AS total_pnl, status FROM placed
                  UNION ALL SELECT placed_day, 'sport',  sport,  'placed', 0, status FROM placed
                  UNION ALL SELECT placed_day, 'origin', origin, 'placed', 0, status FROM placed
                  UNION ALL SELECT settled_day, 'strategy', strategy, 'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'sport',  sport,  'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'origin', origin, 'settled', total_pnl, status FROM trade_tot
              ) u
             GROUP BY op_day, dim, dim_key
        ), brk_json AS (
            SELECT op_day, dim,
                   jsonb_object_agg(coalesce(dim_key, 'none'),
                       jsonb_build_object('n', n, 'pnl', round(pnl, 2), 'won', won, 'lost', lost)) AS j
              FROM brk GROUP BY op_day, dim
        ), per_day AS (
            SELECT d.op_day,
                   (SELECT coalesce(round(sum(pnl), 2), 0) FROM settled_rows s WHERE s.op_day = d.op_day) AS pnl_realized,
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day) AS trades_placed,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day) AS settled,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'won')  AS won,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'lost') AS lost,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'void') AS n_void,
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day
                       AND (p.status = 'hedged'
                            OR EXISTS (SELECT 1 FROM closers c WHERE c.closes_trade_id = p.id AND c.status <> 'error'))) AS hedged_closed,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS avg_win,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS avg_loss,
                   (SELECT round(max(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS best_trade,
                   (SELECT round(min(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS worst_trade,
                   (SELECT round(max(liability), 2) FROM placed p WHERE p.placed_day = d.op_day) AS max_liability,
                   (SELECT coalesce(round(sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS gross_profit,
                   (SELECT coalesce(round(-sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS gross_loss,
                   (SELECT round(commission_paid, 2) FROM comm_day cd WHERE cd.op_day = d.op_day) AS commission_paid,
                   (SELECT min(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS first_trade_at,
                   (SELECT max(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS last_trade_at,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'strategy') AS by_strategy,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'sport')    AS by_sport,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'origin')   AS by_origin
              FROM days d
        )
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'day',             to_char(op_day, 'YYYY-MM-DD'),
                   'pnl_realized',    pnl_realized,
                   'trades_placed',   trades_placed,
                   'settled',         settled,
                   'won',             won,
                   'lost',            lost,
                   'void',            n_void,
                   'hedged_closed',   hedged_closed,
                   'win_rate',        CASE WHEN won + lost > 0 THEN round(won::numeric / (won + lost), 4) END,
                   'avg_win',         avg_win,
                   'avg_loss',        avg_loss,
                   'best_trade',      best_trade,
                   'worst_trade',     worst_trade,
                   'max_liability',   max_liability,
                   'gross_profit',    gross_profit,
                   'gross_loss',      gross_loss,
                   'profit_factor',   CASE WHEN gross_loss > 0 THEN round(gross_profit / gross_loss, 3) END,
                   'commission_paid', commission_paid,
                   'goal',            $5::numeric,
                   'goal_pct',        CASE WHEN $5::numeric > 0 THEN round(pnl_realized / $5::numeric * 100, 1) END,
                   'by_strategy',     coalesce(by_strategy, '{}'::jsonb),
                   'by_sport',        coalesce(by_sport, '{}'::jsonb),
                   'by_origin',       coalesce(by_origin, '{}'::jsonb),
                   'first_trade_at',  first_trade_at,
                   'last_trade_at',   last_trade_at
               ) ORDER BY op_day), '[]'::jsonb)
          FROM per_day
    $q$, p_strategy_expr, p_sport_expr, p_table, coalesce(p_filter_expr, 'true'),
         p_table, p_table, coalesce(p_filter_expr, 'true'), p_table)
    INTO v_out
    USING v_from, v_to, p_from, p_to, p_goal, v_by_placed;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;

DROP FUNCTION IF EXISTS public.trading_day_trades(text,text,date);
CREATE OR REPLACE FUNCTION public.trading_day_trades(
    p_table       text,
    p_filter_expr text,
    p_day         date,
    p_day_by      text DEFAULT 'settled'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_from timestamptz;
    v_to   timestamptz;
    v_out  jsonb;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed') THEN
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_day IS NULL THEN
        RAISE EXCEPTION 'giorno mancante';
    END IF;
    v_from := (p_day::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_day + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    EXECUTE format($q$
        SELECT coalesce(jsonb_agg(
                   to_jsonb(o.*)
                   || jsonb_build_object(
                          'placed_in_day',  (o.placed_at >= $1 AND o.placed_at < $2),
                          'settled_in_day', (o.settled_at >= $1 AND o.settled_at < $2),
                          'closes', coalesce((SELECT jsonb_agg(to_jsonb(c.*) ORDER BY c.placed_at)
                                                FROM public.%I c
                                               WHERE c.closes_trade_id = o.id), '[]'::jsonb),
                          'total_pnl', round(o.pnl::numeric + coalesce((SELECT sum(c.pnl::numeric)
                                                FROM public.%I c
                                               WHERE c.closes_trade_id = o.id
                                                 AND c.status IN ('won','lost','void')), 0), 2)
                      )
                   ORDER BY o.placed_at), '[]'::jsonb)
          FROM public.%I o
         WHERE o.closes_trade_id IS NULL
           AND (%s)
           AND ((o.placed_at >= $1 AND o.placed_at < $2)
                OR ($3 = 'settled' AND o.settled_at >= $1 AND o.settled_at < $2))
    $q$, p_table, p_table, p_table, coalesce(p_filter_expr, 'true'))
    INTO v_out
    USING v_from, v_to, p_day_by;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_day_trades(text,text,date,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_day_trades(text,text,date,text) TO service_role;

-- Omega: giornata = piazzamento; obiettivo = snapshot del giorno (fallback corrente)
CREATE OR REPLACE FUNCTION public.get_omega_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_goal  numeric;
    v_rows  jsonb;
    v_out   jsonb := '[]'::jsonb;
    v_row   jsonb;
    v_g     numeric;
    v_pnl   numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;
    v_rows := public.trading_daily_history(
        'omega_trades',
        $e$coalesce(t.phase, 'none')$e$,
        $e$'calcio'$e$,
        NULL,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        v_goal,
        'placed');
    FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP
        SELECT g.goal INTO v_g FROM public.omega_daily_goal g WHERE g.day = (v_row->>'day')::date;
        IF v_g IS NOT NULL THEN
            v_pnl := (v_row->>'pnl_realized')::numeric;
            v_row := v_row || jsonb_build_object(
                'goal', v_g,
                'goal_pct', CASE WHEN v_g > 0 THEN round(v_pnl / v_g * 100, 1) END,
                'goal_snapshot', true);
        ELSE
            v_row := v_row || jsonb_build_object('goal_snapshot', false);
        END IF;
        v_out := v_out || jsonb_build_array(v_row);
    END LOOP;
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_daily(date,date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_daily(date,date) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_omega_day_trades(p_day date)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN public.trading_day_trades('omega_trades', NULL, p_day, 'placed');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_day_trades(date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_day_trades(date) TO authenticated, service_role;

-- Safe Strategy: comportamento INVARIATO ('settled'), ricreate per la nuova firma
CREATE OR REPLACE FUNCTION public.get_safe_daily(
    p_from  date DEFAULT NULL,
    p_to    date DEFAULT NULL,
    p_sport text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today  date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_filter text := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_filter := format('t.sport = %L', p_sport);
    END IF;
    RETURN public.trading_daily_history(
        'safe_strategy_trades',
        $e$t.strategy$e$,
        $e$t.sport$e$,
        v_filter,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        NULL,
        'settled');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_daily(date,date,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_daily(date,date,text) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_safe_day_trades(
    p_day   date,
    p_sport text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_filter text := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_filter := format('o.sport = %L', p_sport);
    END IF;
    RETURN public.trading_day_trades('safe_strategy_trades', v_filter, p_day, 'settled');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_day_trades(date,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_day_trades(date,text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. λ persistiti per evento
-- ----------------------------------------------------------------------------
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS model JSONB;

-- ----------------------------------------------------------------------------
-- 5. Dati storici: punteggio al 45′ → risultato finale (per lega + globale)
--    Fonte: public.matches (API-Football, status FT = 90′ regolari).
--    league_id = 0 → tutte le leghe. Ricostruibile con
--    SELECT public.omega_build_ht_ft_transitions();
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.omega_ht_ft_transitions (
    league_id   BIGINT  NOT NULL,
    ht          TEXT    NOT NULL,
    ft          TEXT    NOT NULL,
    n           INTEGER NOT NULL,
    built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (league_id, ht, ft)
);
ALTER TABLE public.omega_ht_ft_transitions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_ht_ft_transitions FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.omega_build_ht_ft_transitions()
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_n integer;
BEGIN
    DELETE FROM public.omega_ht_ft_transitions;
    INSERT INTO public.omega_ht_ft_transitions (league_id, ht, ft, n)
    SELECT s.league_id, s.ht, s.ft, count(*)::integer
      FROM (
        SELECT m.league_id::bigint AS league_id,
               m.halftime_home::text || '-' || m.halftime_away::text AS ht,
               m.fulltime_home::text || '-' || m.fulltime_away::text AS ft
          FROM public.matches m
         WHERE m.status_short = 'FT'
           AND m.league_id IS NOT NULL
           AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
           AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
        UNION ALL
        SELECT 0::bigint,
               m.halftime_home::text || '-' || m.halftime_away::text,
               m.fulltime_home::text || '-' || m.fulltime_away::text
          FROM public.matches m
         WHERE m.status_short = 'FT'
           AND m.halftime_home IS NOT NULL AND m.halftime_away IS NOT NULL
           AND m.fulltime_home IS NOT NULL AND m.fulltime_away IS NOT NULL
      ) s
     GROUP BY s.league_id, s.ht, s.ft;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;
REVOKE ALL ON FUNCTION public.omega_build_ht_ft_transitions() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_build_ht_ft_transitions() TO service_role;

-- COSTRUZIONE INIZIALE — PASSO SEPARATO (legge ~1,4 M partite: fuori dalla
-- migrazione per non incappare nello statement timeout dell'SQL editor).
-- Eseguire una volta, da solo:
--     SELECT public.omega_build_ht_ft_transitions();
-- Finché la tabella è vuota il servizio lavora col solo modello (veto empirico off).

CREATE OR REPLACE FUNCTION public.get_omega_ht_ft(p_league_id bigint DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_out jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('league_id', t.league_id, 'ht', t.ht, 'ft', t.ft, 'n', t.n)), '[]'::jsonb)
      INTO v_out
      FROM public.omega_ht_ft_transitions t
     WHERE t.league_id = 0 OR (p_league_id IS NOT NULL AND t.league_id = p_league_id);
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_ht_ft(bigint) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_ht_ft(bigint) TO authenticated, service_role;
