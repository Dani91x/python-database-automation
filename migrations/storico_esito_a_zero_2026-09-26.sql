-- ============================================================================
-- STORICO: una posizione chiusa a ZERO non e' una vittoria (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTO (E2E fase 3 sessione B, U0541): lo Storico di Mike diceva «150V · 91P
-- · 1 void, win rate 62,2 %» mentre il tooltip dichiara «V = posizioni con P&L
-- totale POSITIVO, P = negativo». Le posizioni 527 e 4762 (Mike, paper) hanno
-- P&L totale 0,00 ma riga d'apertura 'won': `trading_daily_history` le
-- classificava col segno del P&L e, a ZERO, ricadeva sullo stato GREZZO
-- dell'apertura ('won'). Con la definizione dichiarata: 148V / 91P = 61,9 %.
--
-- CORREZIONE: a P&L totale zero l'esito e' 'scratch' (conta fra le regolate,
-- non fra V/P ne' fra i void). Void e P&L ignoto restano come prima.
-- Tocca TUTTI gli storici che usano il motore comune (Omega, Safe, Mike):
-- stessa definizione, stesso tooltip, in ogni pagina.
--
-- BASE: il corpo e' quello VIVO (md5 senza \r = e58a42c89c799e25286a65421a63fdff,
-- identico a migrations/mike_history_v2.sql), generato da
-- AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs con UNA sola sostituzione.
-- IDEMPOTENTE (CREATE OR REPLACE a firma invariata). Nessuna modifica ai dati.
--
-- VERIFICA dopo l'applicazione (Mike paper 01-26/09): won=148, lost=91
--   SELECT sum((r->>'won')::int) v, sum((r->>'lost')::int) p
--     FROM jsonb_array_elements(public.get_mike_daily('2026-09-01','2026-09-26','paper')) r;
-- ============================================================================

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
                   CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost'
                        -- FIX-A 26/09: a ZERO (scratch) non e' ne' V ne' P; void e ignoto restano com'erano
                        WHEN raw_status = 'void' OR total_pnl IS NULL THEN raw_status
                        ELSE 'scratch' END AS status
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
