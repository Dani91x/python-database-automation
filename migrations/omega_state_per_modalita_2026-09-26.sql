-- ============================================================================
-- OMEGA: aggregati PER MODALITA' e partite DISTINTE (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTI (E2E fase 3 sessione B):
--   * U0419 latente: `omega_aggregates_sql` non filtra per `mode`: il giorno in
--     cui esistera' una riga live, P&L, liability e contatori della pagina Omega
--     sommeranno euro veri e simulati sotto l'etichetta della modalita' del bot.
--   * U0426: «storico 109 partite» = `matches_traded`, che conta le APERTURE
--     (gambe 1T/2T), non le partite (100 distinte).
--
-- CORREZIONE (solo lettura, nessun dato toccato):
--   1. omega_aggregates_sql(boolean, text) - lo STESSO corpo vivo con il filtro
--      della modalita' della POSIZIONE e due chiavi nuove: events_traded (partite
--      distinte) e mode (filtro applicato).
--   2. omega_aggregates_sql(boolean) - quella del SERVIZIO - delega alla nuova
--      con NULL: stessi numeri di prima + le due chiavi nuove (additive).
--   3. get_omega_state(integer) - aggiunge `aggregates_by_mode` {paper, live}.
--      `aggregates` resta com'era (tutte le modalita') per chi lo legge oggi.
--
-- BASE: corpi VIVI (md5 senza \r): omega_aggregates_sql(boolean)
-- 6c00a7346cec3efe9e638919b8d6fc2a = migrations/omega_chiuso_dall_utente_2026-09-16.sql;
-- get_omega_state(integer) 5027acf45a32f3814edbd941a61d3cf2 = migrations/omega_models_v5.sql.
-- Generato da AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs.
-- IDEMPOTENTE: CREATE OR REPLACE; la firma (boolean, text) e' un overload NUOVO
-- senza default (nessuna ambiguita' con (boolean) ne' con ()).
--
-- VERIFICA dopo l'applicazione:
--   SELECT public.get_omega_state()->'aggregates_by_mode'->'paper'->>'events_traded';
--   SELECT (public.get_omega_aggregates() ? 'auto');   -- il servizio: invariato
-- ============================================================================

CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean, p_mode text)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    -- UNA sola scansione di omega_trades (tabella piccola: ~200 righe/giorno);
    -- giorno della posizione = placed_at dell'APERTURA (join su PK).
    -- Usata da get_omega_state (UI) e da get_omega_aggregates (servizio).
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day,
               -- FIX-A 26/09: NULL/'' = tutte le modalita' (comportamento storico)
               nullif(lower(btrim(coalesce(p_mode, ''))), '') AS v_mode
    ), raw AS (
        -- estrazioni dal meta, SEMPRE difensive (un valore non numerico scritto a
        -- mano non deve far fallire l'RPC di stato: la UI resterebbe cieca)
        SELECT o.id, o.status, o.pnl, o.placed_at, o.event_id, o.closes_trade_id,
               o.liability AS liability_gross,
               CASE WHEN (o.meta->>'locked_pnl')    ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'locked_pnl')::numeric    END AS m_locked,
               CASE WHEN (o.meta->>'residual_size') ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'residual_size')::numeric END AS m_residual,
               CASE WHEN (o.meta->>'if_win')        ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'if_win')::numeric        END AS m_if_win,
               -- S-01(a): come omega_engine.residual_liability — hedged_size
               -- PRESENTE E NON NULL (un `null` JSON non è una copertura)
               ((o.meta->>'hedged_size') IS NOT NULL)                                       AS m_has_hedged,
               (o.meta->>'reconciling' IN ('true','t')
                OR o.meta->>'reason' = 'place_exception_reconciling')                      AS reconciling,
               (o.bet_id IS NOT NULL OR (o.meta->>'flumine_client_ref') IS NOT NULL)       AS has_order,
               coalesce(p.placed_at, o.placed_at)                                          AS pos_placed_at
          FROM public.omega_trades o
          LEFT JOIN public.omega_trades p ON p.id = o.closes_trade_id
         -- R6 (16/09, ordine dell'utente h18): con p_solo_auto restano SOLO le
         -- posizioni DEL BOT. Il proprietario di una riga e' l'origin della sua
         -- POSIZIONE: per un'apertura il proprio, per una gamba di chiusura
         -- quello dell'apertura che chiude (un cash-out fatto a mano su una
         -- gamba del bot porta origin='manual' ma il suo P&L e' del bot, e
         -- toglierlo renderebbe cieco il cap di perdita).
         -- Identico a omega_engine.posizione_manuale.
         WHERE (NOT p_solo_auto
            OR coalesce(p.origin, o.origin, 'auto') <> 'manual')
           -- FIX-A 26/09: la modalita' e' quella della POSIZIONE (apertura)
           AND ((SELECT v_mode FROM d) IS NULL
                OR coalesce(p.mode, o.mode) = (SELECT v_mode FROM d))
    ), t AS (
        SELECT r.status, r.pnl, r.placed_at, r.event_id, r.closes_trade_id,
               r.liability_gross, r.reconciling, r.pos_placed_at,
               -- copertura COMPLETA: meta.locked_pnl è scritto SOLO a residuo nullo
               -- (safe_strategy.execution.hedge_state) → P&L bloccato, rischio 0
               (r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01) AS hedge_complete,
               CASE WHEN r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01
                    THEN r.m_locked END AS locked_pnl,
               -- H-06: liability VIVA. 0 a copertura completa; altrimenti il residuo
               -- max(0,−if_win) scritto dallo strato di esecuzione; altrimenti la
               -- liability piena (posizione nuda).
               CASE WHEN r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01 THEN 0
                    WHEN r.m_has_hedged AND r.m_if_win IS NOT NULL
                    THEN greatest(0, -r.m_if_win)
                    ELSE r.liability_gross END AS liability,
               -- H-02: 'pending' in RICONCILIAZIONE = ordine reale forse vivo
               (r.has_order OR r.reconciling) AS is_placed,
               -- esito della POSIZIONE (apertura + chiusure) per SEGNO del P&L totale
               CASE WHEN r.closes_trade_id IS NULL AND r.status IN ('won','lost','void') THEN
                    r.pnl + coalesce((SELECT sum(c.pnl) FROM public.omega_trades c
                                       WHERE c.closes_trade_id = r.id AND c.status IN ('won','lost','void')), 0)
               END AS total_pnl
          FROM raw r
    ), live AS (
        -- posizione VIVA adesso (stesso predicato di omega_engine: open/hedged, o
        -- pending PIAZZATO). Definito una volta sola: tutti i filtri sotto lo usano.
        SELECT t.*,
               (t.closes_trade_id IS NULL
                AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))) AS is_live
          FROM t
    )
    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.pos_placed_at >= d.v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.is_live), 0),
        -- H-06: P&L già BLOCCATO sulle posizioni vive (non realizzato, rischio 0).
        -- S-01(b): ANCHE un pending piazzato a copertura completa (come il Python)
        'locked_pnl_open', coalesce(sum(t.locked_pnl) FILTER (WHERE t.is_live AND t.hedge_complete), 0),
        -- review H1: la quota del bloccato attribuita alla GIORNATA (posizioni
        -- PIAZZATE oggi): pesa su stop-loss giornaliero e target dinamico
        'locked_pnl_open_today', coalesce(sum(t.locked_pnl) FILTER (WHERE t.is_live AND t.hedge_complete
                               AND t.placed_at >= d.v_day), 0),
        -- H-02: quanto di open_liability è un ordine a esito IGNOTO in riconciliazione
        'reconciling_liability', coalesce(sum(t.liability_gross) FILTER (WHERE t.closes_trade_id IS NULL
                               AND t.status = 'pending' AND t.reconciling), 0),
        'matches_traded',  count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        -- FIX-A 26/09 (U0426): PARTITE distinte con almeno una posizione piazzata
        -- (matches_traded conta le APERTURE, cioe' le gambe: resta per il servizio)
        'events_traded',   count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        'mode',            d.v_mode,
        'matches_traded_today', count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))
                               AND t.placed_at >= d.v_day),
        'legs_today',      count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'events_today',    count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'matches_open',    count(*) FILTER (WHERE t.is_live),
        -- H-08: partite DISTINTE con una posizione VIVA adesso (nessun giorno)
        'live_now',        count(DISTINCT t.event_id) FILTER (WHERE t.is_live),
        'matches_won',     count(*) FILTER (WHERE t.total_pnl > 0),
        'matches_lost',    count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',       count(*) FILTER (WHERE t.total_pnl > 0 AND t.placed_at >= d.v_day),
        'lost_today',      count(*) FILTER (WHERE t.total_pnl < 0 AND t.placed_at >= d.v_day)
    )
      FROM d LEFT JOIN live t ON true
     GROUP BY d.v_day, d.v_mode;
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean, text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean, text) TO service_role;

-- l'overload del SERVIZIO (boolean) resta la stessa cosa: UN corpo solo, tutte
-- le modalita'. In uscita due chiavi IN PIU' (events_traded, mode=null), nessuna
-- tolta ne' cambiata.
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT public.omega_aggregates_sql(p_solo_auto, NULL::text);
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean) TO service_role;

CREATE OR REPLACE FUNCTION public.get_omega_state(
    p_activity_limit integer DEFAULT 50
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl jsonb;
    v_act  jsonb;
    v_agg  jsonb;
    v_by   jsonb;
    v_goal numeric;
    v_snap boolean := false;
    v_day  date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_day0 timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
    v_lim  integer := least(greatest(coalesce(p_activity_limit, 50), 1), 300);
    v_more integer := 0;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.omega_control c WHERE c.id = 1;
    v_agg := coalesce(public.omega_aggregates_sql(), '{}'::jsonb);
    -- FIX-A 26/09: paper e live SEPARATI (la pagina mostra la modalita' del bot
    -- e, a parte, l'altra se ha qualcosa: mai una somma sotto un'etichetta)
    v_by := jsonb_build_object(
        'paper', coalesce(public.omega_aggregates_sql(false, 'paper'), '{}'::jsonb),
        'live',  coalesce(public.omega_aggregates_sql(false, 'live'),  '{}'::jsonb));

    -- M-22: SOLO la giornata operativa (Europe/Rome). Le righe di ieri non
    -- compaiono mai come "attività di oggi"; se la giornata ha più righe del
    -- limite si dice quante ne restano (activity_more) invece di mentire.
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.omega_activity
             WHERE ts >= v_day0
             ORDER BY ts DESC
             LIMIT v_lim) a;
    SELECT greatest(0, count(*) - v_lim) INTO v_more
      FROM public.omega_activity WHERE ts >= v_day0;

    SELECT g.goal INTO v_goal FROM public.omega_daily_goal g WHERE g.day = v_day;
    IF v_goal IS NOT NULL THEN
        v_snap := true;
    ELSE
        SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;
    END IF;

    RETURN jsonb_build_object('control', v_ctrl, 'aggregates', v_agg, 'aggregates_by_mode', v_by, 'activity', v_act,
                              'activity_more', v_more,
                              'activity_day', v_day,
                              'goal_today', to_jsonb(v_goal),
                              'goal_snapshot', v_snap);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_state(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;
