-- ============================================================================
-- daily_history.sql — STORICO PER GIORNATA OPERATIVA di OMEGA e SAFE STRATEGY.
--
-- La missione Omega è giornaliera (ogni giorno riparte da 0 verso l'obiettivo)
-- e anche Safe ragiona per giornata: qui le RPC owner-only che restituiscono
-- una riga di statistiche per ogni GIORNATA OPERATIVA con attività, più il
-- dettaglio dei trade di un singolo giorno (aperture con le loro chiusure).
--
-- DEFINIZIONI (identiche a get_omega_state / get_safe_state):
--   • giornata operativa = data in Europe/Rome (placed_at / settled_at AT TIME ZONE);
--   • P&L realizzato del giorno = somma di pnl delle righe con status won/lost/void
--     e settled_at nel giorno — INCLUSE le gambe di chiusura (closes_trade_id);
--   • trade piazzati nel giorno = APERTURE (closes_trade_id IS NULL) con
--     placed_at nel giorno, status <> 'error' e — se 'pending' — davvero a
--     mercato (bet_id oppure meta.flumine_client_ref, come is_placed);
--   • le statistiche "per trade" (media vincita/perdita, miglior/peggior trade,
--     gross profit/loss, profit factor) usano il P&L TOTALE dell'apertura =
--     pnl apertura + pnl delle sue chiusure regolate (il cash out nettizza);
--   • won/lost/void = aperture regolate nel giorno per status; win_rate =
--     won/(won+lost); hedged_closed = aperture piazzate nel giorno che sono
--     state chiuse a mercato (status 'hedged' o con una gamba di chiusura);
--   • commission_paid = somma di meta.commission_paid se il servizio la scrive,
--     altrimenti STIMA dal netto positivo per mercato: netto × c/(1−c) con c =
--     aliquota della riga (colonna commission, default 5%). NULL se nel giorno
--     non c'è nulla di regolato;
--   • goal (solo Omega) = omega_control.daily_goal CORRENTE (non esiste uno
--     storico dell'obiettivo): goal_pct = pnl_realized/goal×100.
--
-- Il pnl in tabella è già NETTO di commissione (execution.settle_group).
--
-- IDEMPOTENTE. Owner-only via public.betfair_live_is_owner(); stesso pattern
-- di grant di safe_strategy_bot.sql (REVOKE public/anon, GRANT authenticated,
-- service_role). Il motore comune trading_daily_history / trading_day_trades
-- NON è eseguibile dai client: solo i wrapper pubblici (SECURITY DEFINER) lo
-- chiamano, dopo il controllo owner.
-- Da applicare DOPO omega_cashout.sql e safe_strategy_bot.sql.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Motore comune: statistiche per giornata su una tabella trade.
--    p_table         'omega_trades' | 'safe_strategy_trades' (scelta dal wrapper)
--    p_strategy_expr espressione SQL sull'alias t → chiave del breakdown
--                    "strategia" (Safe: t.strategy · Omega: fase della gamba)
--    p_sport_expr    espressione SQL sull'alias t → chiave del breakdown sport
--    p_filter_expr   filtro aggiuntivo (es. sport) già quotato dal wrapper
--    p_goal          obiettivo giornaliero da riportare in ogni riga (o NULL)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trading_daily_history(
    p_table         text,
    p_strategy_expr text,
    p_sport_expr    text,
    p_filter_expr   text,
    p_from          date,
    p_to            date,
    p_goal          numeric
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
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', p_from, p_to;
    END IF;
    IF (p_to - p_from) > 400 THEN
        RAISE EXCEPTION 'intervallo troppo ampio (max 400 giorni): % → %', p_from, p_to;
    END IF;
    -- confini della finestra in Europe/Rome: [mezzanotte di p_from, mezzanotte di p_to+1)
    v_from := (p_from::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    EXECUTE format($q$
        WITH originals AS (
            -- aperture con attività nella finestra (piazzate O regolate dentro)
            SELECT t.id, t.status, t.pnl::numeric AS pnl, t.liability::numeric AS liability,
                   t.origin, t.placed_at, t.settled_at,
                   (%s)::text AS strategy, (%s)::text AS sport,
                   (t.placed_at  AT TIME ZONE 'Europe/Rome')::date AS placed_day,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day,
                   (t.bet_id IS NOT NULL OR (t.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed
              FROM public.%I t
             WHERE t.closes_trade_id IS NULL
               AND (%s)
               AND ((t.placed_at >= $1 AND t.placed_at < $2)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), closers AS (
            -- gambe di chiusura: quelle delle aperture sopra + quelle regolate nella finestra
            SELECT t.id, t.closes_trade_id, t.status, t.pnl::numeric AS pnl, t.market_id,
                   t.commission::numeric AS commission, t.meta, t.settled_at,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day
              FROM public.%I t
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
            -- P&L TOTALE per apertura regolata = apertura + chiusure regolate
            SELECT o.id, o.settled_day, o.status, o.strategy, o.sport, o.origin,
                   o.pnl + coalesce((SELECT sum(c.pnl) FROM closers c
                                      WHERE c.closes_trade_id = o.id
                                        AND c.status IN ('won','lost','void')), 0) AS total_pnl
              FROM originals o
             WHERE o.status IN ('won','lost','void')
               AND o.settled_day BETWEEN $3 AND $4
        ), settled_rows AS (
            -- TUTTE le righe regolate nel giorno (aperture + chiusure): P&L del giorno
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM (SELECT o.settled_day, o.pnl, t.market_id, t.commission::numeric AS commission, t.meta
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
            -- commissione per (giorno, mercato): scritta dal servizio o stimata dal netto positivo
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
            -- breakdown per (giorno, chiave): n = piazzati, pnl/won/lost = regolati
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
         p_table, coalesce(p_filter_expr, 'true'), p_table)
    INTO v_out
    USING v_from, v_to, p_from, p_to, p_goal;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric) TO service_role;

-- ----------------------------------------------------------------------------
-- 2. Motore comune: trade di UN giorno = aperture piazzate O regolate in quel
--    giorno operativo, con le gambe di chiusura annidate in `closes` e il P&L
--    totale della posizione (`total_pnl` = apertura + chiusure regolate).
--    `placed_in_day` / `settled_in_day` dicono perché la riga è nel giorno.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trading_day_trades(
    p_table       text,
    p_filter_expr text,
    p_day         date
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
                OR (o.settled_at >= $1 AND o.settled_at < $2))
    $q$, p_table, p_table, p_table, coalesce(p_filter_expr, 'true'))
    INTO v_out
    USING v_from, v_to;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_day_trades(text,text,date) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_day_trades(text,text,date) TO service_role;

-- ----------------------------------------------------------------------------
-- 3. RPC Omega: storico per giornata (breakdown "strategy" = fase della gamba
--    1T/2T/scalp; goal = obiettivo giornaliero corrente).
--    Default: ultimi 90 giorni fino a oggi (Europe/Rome).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_goal  numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;
    RETURN public.trading_daily_history(
        'omega_trades',
        $e$coalesce(t.phase, 'none')$e$,
        $e$'calcio'$e$,
        NULL,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        v_goal);
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
    RETURN public.trading_day_trades('omega_trades', NULL, p_day);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_day_trades(date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_day_trades(date) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. RPC Safe Strategy: storico per giornata (breakdown per strategia, sport,
--    origine; goal = NULL). p_sport opzionale ('calcio'|'tennis') filtra tutto.
-- ----------------------------------------------------------------------------
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
        NULL);
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
    RETURN public.trading_day_trades('safe_strategy_trades', v_filter, p_day);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_day_trades(date,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_day_trades(date,text) TO authenticated, service_role;
