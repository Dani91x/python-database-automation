-- ============================================================================
-- mike_history_v2.sql — STORICO condiviso: una sola firma, Mike ammessa.
--
-- PERCHE' (audit 11/09, R2 / M-20): `mike_history.sql` aveva ricreato le
-- versioni a 7 e 3 argomenti di trading_daily_history / trading_day_trades che
-- `omega_daily_v2.sql` aveva sostituito con quelle a 8 e 4 argomenti
-- (p_day_by). Risultato: DUE overload coesistenti e ogni chiamata che non
-- specifica tutti gli argomenti fallisce con
--   "function public.trading_daily_history(...) is not unique"  (42725)
-- Omega e Safe funzionavano solo perche' passano TUTTI gli argomenti; lo
-- storico di Mike era completamente ROTTO (verificato sul DB reale l'11/09).
--
-- COSA FA
--   1. DROP delle firme VECCHIE (7 e 3 argomenti): una sola versione viva.
--   2. CREATE OR REPLACE delle firme a 8 e 4 argomenti (base:
--      omega_models_v4.sql:378 e omega_daily_v2.sql:413) con la whitelist
--      tabelle estesa a 'mike_trades'.
--   3. M-17: finestra oltre 400 giorni -> CLAMP a 400 giorni con nota
--      (`window_clamped`), non piu' un errore che svuota la pagina.
--   4. L-08: `hedged_closed` non conta piu' le chiusure PENDING;
--      `commission_paid` calcolata per (giorno, mercato) usando il valore
--      SCRITTO dal servizio quando c'e' e la stima dal netto positivo solo dove
--      manca (prima: se un solo mercato del giorno aveva il valore, tutti gli
--      altri contavano zero).
--   5. Predicato ``is_placed`` allineato ai KPI: una riga 'pending' in
--      RICONCILIAZIONE (meta.reason='place_exception_reconciling') conta come
--      PIAZZATA, come fanno gli aggregati di Omega/Safe/Mike — prima lo storico
--      mostrava meno trades_placed dei KPI della stessa giornata.
--   6. get_mike_daily / get_mike_day_trades passano TUTTI gli argomenti con
--      p_day_by = 'placed' (M6: giornata operativa = giorno di PIAZZAMENTO,
--      Europe/Rome) e dichiarano `goal_snapshot` (Mike non ha un obiettivo
--      giornaliero: la UI non deve giudicare un obiettivo di ripiego).
--
-- ORDINE DI APPLICAZIONE (importante):
--   daily_history.sql -> mike_bot.sql -> omega_daily_v2.sql ->
--   omega_models_v4.sql -> [mike_bot_v2.sql] -> QUESTA.
--   Se in futuro si riapplica omega_models_v4.sql, RIAPPLICARE anche questa
--   (altrimenti torna una whitelist senza 'mike_trades').
--
-- IDEMPOTENTE. Nessuna modifica ai dati.
-- ============================================================================

-- 1. via le firme vecchie (quelle reintrodotte da mike_history.sql) ------------
DROP FUNCTION IF EXISTS public.trading_daily_history(text,text,text,text,date,date,numeric);
DROP FUNCTION IF EXISTS public.trading_day_trades(text,text,date);

-- 2. motore comune dello storico giornaliero (8 argomenti) --------------------
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
    v_from      timestamptz;
    v_to        timestamptz;
    v_out       jsonb;
    v_by_placed boolean;
    v_from_d    date;
    v_clamped   boolean := false;
    v_row       jsonb;
    v_acc       jsonb := '[]'::jsonb;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed') THEN
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', p_from, p_to;
    END IF;
    -- M-17: finestra troppo ampia = si RESTRINGE (ultimi 400 giorni) e lo si
    -- dichiara. Prima era un'eccezione: la pagina Storico restava vuota.
    v_from_d := p_from;
    IF (p_to - p_from) > 400 THEN
        v_from_d := p_to - 400;
        v_clamped := true;
    END IF;
    v_by_placed := (p_day_by = 'placed');
    v_from := (v_from_d::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    EXECUTE format($q$
        WITH originals AS (
            SELECT t.id, t.status, t.pnl::numeric AS pnl, t.liability::numeric AS liability,
                   t.origin, t.placed_at, t.settled_at,
                   (%s)::text AS strategy, (%s)::text AS sport,
                   (t.placed_at  AT TIME ZONE 'Europe/Rome')::date AS placed_day,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day,
                   CASE WHEN $6 THEN (t.placed_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS op_settled_day,
                   -- PIAZZATA: bet_id reale, marker flumine, OPPURE riga
                   -- 'pending' in RICONCILIAZIONE (esito ignoto: l'ordine puo'
                   -- essere vivo su Betfair). Senza l'ultimo caso lo storico
                   -- contava meno trade piazzati dei KPI della stessa giornata,
                   -- che invece le contano aperte (review Safe 11/09).
                   (t.bet_id IS NOT NULL
                    OR (t.meta->>'flumine_client_ref') IS NOT NULL
                    OR t.meta->>'reason' = 'place_exception_reconciling') AS is_placed
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
        ), trade_raw AS (
            SELECT o.id, o.op_settled_day AS settled_day, o.status AS raw_status, o.strategy, o.sport, o.origin,
                   o.pnl + coalesce((SELECT sum(c.pnl) FROM closers c
                                      WHERE c.closes_trade_id = o.id
                                        AND c.status IN ('won','lost','void')), 0) AS total_pnl
              FROM originals o
             WHERE o.status IN ('won','lost','void')
               AND o.op_settled_day BETWEEN $3 AND $4
        ), trade_tot AS (
            -- esito della POSIZIONE (ciclo) per SEGNO del P&L totale: un ciclo
            -- greenato e' UNA vittoria, non 1 vinta + 1 persa (audit Mike H4)
            SELECT id, settled_day, strategy, sport, origin, total_pnl,
                   CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost' ELSE raw_status END AS status
              FROM trade_raw
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
            -- L-08: commissione REALE per (giorno, mercato) quando il servizio
            -- l'ha scritta (meta.commission_paid), stima dal netto positivo solo
            -- dove manca. Prima un solo mercato con il valore azzerava gli altri.
            SELECT op_day, market_id,
                   sum(nullif(meta->>'commission_paid','')::numeric) AS paid,
                   sum(pnl) AS net,
                   coalesce(avg(commission), 0.05) AS c
              FROM settled_rows
             WHERE op_day BETWEEN $3 AND $4
             GROUP BY op_day, market_id
        ), comm_day AS (
            SELECT op_day,
                   sum(CASE WHEN paid IS NOT NULL THEN paid
                            WHEN net > 0 AND c < 1 THEN net * c / (1 - c)
                            ELSE 0 END) AS commission_paid
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
                   -- L-08: le chiusure ancora PENDING non hanno chiuso nulla
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day
                       AND (p.status = 'hedged'
                            OR EXISTS (SELECT 1 FROM closers c WHERE c.closes_trade_id = p.id
                                         AND c.status NOT IN ('error','pending')))) AS hedged_closed,
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
    USING v_from, v_to, v_from_d, p_to, p_goal, v_by_placed;

    v_out := coalesce(v_out, '[]'::jsonb);
    IF v_clamped THEN
        -- la nota viaggia su ogni riga: nessun campo nuovo obbligatorio per chi legge
        FOR v_row IN SELECT * FROM jsonb_array_elements(v_out) LOOP
            v_acc := v_acc || jsonb_build_array(v_row || jsonb_build_object(
                'window_clamped', true,
                'window_from', to_char(v_from_d, 'YYYY-MM-DD'),
                'window_note', 'finestra ridotta agli ultimi 400 giorni'));
        END LOOP;
        RETURN v_acc;
    END IF;
    RETURN v_out;
END;
$$;
REVOKE ALL ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;

-- 3. trade di UN giorno (4 argomenti) ----------------------------------------
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
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
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

-- 4. RPC Mike: giornata operativa = giorno di PIAZZAMENTO (M6) ----------------
CREATE OR REPLACE FUNCTION public.get_mike_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_rows  jsonb;
    v_out   jsonb := '[]'::jsonb;
    v_row   jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    v_rows := public.trading_daily_history(
        'mike_trades',
        $e$coalesce(t.role, t.strategy)$e$,
        $e$'calcio'$e$,
        NULL,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        NULL,
        'placed');
    -- Mike non ha un obiettivo giornaliero: si dichiara esplicitamente, cosi'
    -- la UI non tratta un obiettivo di ripiego come uno storico (L-08).
    FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP
        v_out := v_out || jsonb_build_array(v_row || jsonb_build_object('goal_snapshot', false));
    END LOOP;
    RETURN v_out;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_daily(date,date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_daily(date,date) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_mike_day_trades(p_day date)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN public.trading_day_trades('mike_trades', NULL, p_day, 'placed');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_day_trades(date) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_day_trades(date) TO authenticated, service_role;

-- VERIFICA (facoltativa):
--   SELECT count(*) FROM pg_proc WHERE proname = 'trading_daily_history';  -- 1
--   SELECT count(*) FROM pg_proc WHERE proname = 'trading_day_trades';     -- 1
--   SELECT public.get_mike_daily();                                        -- nessun errore
--   SELECT public.get_omega_daily(), public.get_safe_daily();              -- invariati
