-- ============================================================================
-- mike_bot_v2.sql — audit 11/09/2026: colonne, stati richiesta, aggregati veri
-- e contratto COMPLETO di get_mike_state per la UI.
--
-- Da applicare DOPO migrations/mike_bot.sql. IDEMPOTENTE, nessuna perdita dati.
-- Il servizio Python funziona anche SENZA questa migrazione (fallback), ma:
--   * le richieste rifiutate restano 'error' invece di 'rejected' (M1);
--   * gli aggregati passano dalla lettura completa di mike_trades (H5);
--   * get_mike_state non espone requests / aggregati di giornata (la UI resta
--     con i KPI vecchi).
--
-- COSA FA
--  1. colonne difensive (closes_trade_id, result) — nate in mike_bot.sql, qui
--     ribadite per i DB partiti da versioni intermedie;
--  2. mike_requests.status ammette 'rejected' (M1: rifiuto ATTESO != errore);
--  3. get_mike_aggregates(): UNA query per i KPI, giornata operativa = giorno
--     di PIAZZAMENTO della POSIZIONE (M6), liability NETTA dalle partite (M4),
--     esito del CICLO per segno del P&L totale (H4);
--  4. get_mike_state(): contratto completo per la UI
--     { control, events, trades, activity, aggregates, requests }.
-- ============================================================================

-- 1. colonne ------------------------------------------------------------------
ALTER TABLE public.mike_trades   ADD COLUMN IF NOT EXISTS closes_trade_id BIGINT REFERENCES public.mike_trades(id);
ALTER TABLE public.mike_requests ADD COLUMN IF NOT EXISTS result JSONB;
CREATE INDEX IF NOT EXISTS idx_mike_trades_closes ON public.mike_trades (closes_trade_id);
CREATE INDEX IF NOT EXISTS idx_mike_trades_settled ON public.mike_trades (settled_at DESC);

-- 2. stato 'rejected' sulle richieste (M1) ------------------------------------
DO $$
BEGIN
    ALTER TABLE public.mike_requests DROP CONSTRAINT IF EXISTS mike_requests_status_check;
    ALTER TABLE public.mike_requests
        ADD CONSTRAINT mike_requests_status_check
        CHECK (status IN ('pending','processing','done','rejected','error'));
END $$;

-- 3. aggregati (una query, regole Mike) ---------------------------------------
--    * giornata operativa = mezzanotte Europe/Rome del giorno di PIAZZAMENTO
--      della POSIZIONE: una chiusura eredita il giorno della sua apertura e un
--      regolamento notturno resta nel giorno in cui il trade e' stato aperto (M6);
--    * pnl di riga NETTO commissione (lo scrive il servizio, H4): si somma;
--    * open_liability: NON la somma delle righe (un back coperto da lay non e'
--      back + lay) ma la liability NETTA che il servizio calcola per partita e
--      pubblica in mike_events.live->>'liability' (M4);
--    * una riga 'pending' con esito IGNOTO (place_exception_reconciling) conta
--      come APERTA: potrebbe essere un ordine reale vivo (C3).
CREATE OR REPLACE FUNCTION public.mike_aggregates_sql()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day
    ), t AS (
        SELECT o.id, o.status, o.pnl, o.event_id, o.closes_trade_id,
               (o.bet_id IS NOT NULL
                OR (o.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed,
               (o.status = 'pending' AND o.meta->>'reason' = 'place_exception_reconciling') AS reconciling,
               coalesce(p.placed_at, o.placed_at) AS pos_placed_at,
               CASE WHEN o.closes_trade_id IS NULL AND o.status IN ('won','lost','void') THEN
                    o.pnl + coalesce((SELECT sum(c.pnl) FROM public.mike_trades c
                                       WHERE c.closes_trade_id = o.id
                                         AND c.status IN ('won','lost','void')), 0)
               END AS total_pnl
          FROM public.mike_trades o
          LEFT JOIN public.mike_trades p ON p.id = o.closes_trade_id
    ), liab AS (
        -- M4 (review): la liability NETTA la pubblica il servizio in
        -- mike_events.live->>'liability'. Se NESSUN evento ha la chiave (bot
        -- appena aggiornato, servizio non ancora riavviato) il valore sarebbe 0
        -- e i KPI mostrerebbero "nessun rischio" con 32 posizioni aperte: in
        -- quel caso si ripiega sulla somma delle righe e lo si DICHIARA.
        SELECT coalesce(sum(nullif(e.live->>'liability','')::numeric), 0) AS open_liability,
               count(*) FILTER (WHERE (e.live ? 'liability')) AS with_liability,
               count(*) FILTER (WHERE (e.live->>'inplay')::boolean) AS live_now
          FROM public.mike_events e
         WHERE e.state NOT IN ('SETTLED','ERROR','SKIPPED')
    ), hb AS (
        SELECT heartbeat_at, (heartbeat_at IS NULL
                              OR heartbeat_at < now() - interval '60 seconds') AS stale
          FROM public.mike_control WHERE id = 1
    )
    SELECT jsonb_build_object(
        'realized_total',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')
                               AND t.pos_placed_at >= d.v_day), 0),
        'open_count',      count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR t.reconciling)),
        'open_liability',  CASE WHEN (SELECT with_liability FROM liab) > 0
                                THEN (SELECT open_liability FROM liab)
                                ELSE coalesce(sum(
                                       CASE WHEN t.closes_trade_id IS NULL
                                             AND (t.status IN ('open','hedged') OR t.reconciling)
                                            THEN (SELECT liability FROM public.mike_trades z WHERE z.id = t.id)
                                       END), 0) END,
        'liability_source', CASE WHEN (SELECT with_liability FROM liab) > 0
                                THEN 'net_positions' ELSE 'rows_sum' END,
        'liability_stale', (SELECT stale FROM hb),
        'heartbeat_at',    (SELECT heartbeat_at FROM hb),
        'open_liability_rows', coalesce(sum(
                               CASE WHEN t.closes_trade_id IS NULL
                                     AND (t.status IN ('open','hedged') OR t.reconciling)
                                    THEN (SELECT liability FROM public.mike_trades z WHERE z.id = t.id)
                               END), 0),
        'live_now',        (SELECT live_now FROM liab),
        'won',             count(*) FILTER (WHERE t.total_pnl > 0),
        'lost',            count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',       count(*) FILTER (WHERE t.total_pnl > 0 AND t.pos_placed_at >= d.v_day),
        'lost_today',      count(*) FILTER (WHERE t.total_pnl < 0 AND t.pos_placed_at >= d.v_day),
        'cycles_today',    count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed OR t.reconciling)
                               AND t.pos_placed_at >= d.v_day),
        'events_today',    count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL
                               AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed OR t.reconciling)
                               AND t.pos_placed_at >= d.v_day),
        'reconciling',     count(*) FILTER (WHERE t.reconciling),
        'day_by',          'placed'
    )
      FROM d LEFT JOIN t ON true
     GROUP BY d.v_day;
$$;
REVOKE ALL ON FUNCTION public.mike_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mike_aggregates_sql() TO service_role;

-- versione chiamabile dal servizio (service_role) e dalla UI (owner)
CREATE OR REPLACE FUNCTION public.get_mike_aggregates()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN coalesce(public.mike_aggregates_sql(), '{}'::jsonb);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_aggregates() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_aggregates() TO authenticated, service_role;

-- 4. stato completo per la UI -------------------------------------------------
--    events   : partite vive + terminali delle ultime 24 h (live.* completo,
--               positions[] con closes_ref/status della gamba)
--    trades   : righe della GIORNATA OPERATIVA (giorno di piazzamento della
--               posizione, Europe/Rome) + TUTTE le righe ancora vive dei giorni
--               precedenti (mai una posizione aperta invisibile) — M6
--    activity : log della giornata operativa (tetto 400 righe)
--    requests : ultime 50 richieste con status ed esito (M1)
CREATE OR REPLACE FUNCTION public.get_mike_state()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl   jsonb;
    v_events jsonb;
    v_trades jsonb;
    v_agg    jsonb;
    v_act    jsonb;
    v_reqs   jsonb;
    v_day    timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.mike_control c WHERE c.id = 1;
    SELECT coalesce(jsonb_agg(to_jsonb(e.*) ORDER BY e.ko_at ASC), '[]'::jsonb) INTO v_events
      FROM (SELECT * FROM public.mike_events
             WHERE state NOT IN ('SETTLED','SKIPPED','ERROR') OR updated_at >= now() - interval '24 hours'
             ORDER BY ko_at ASC LIMIT 200) e;
    -- M5 (review): tetto DURO e ordinamento esplicito (una giornata piena di
    -- cicli pre-match puo' fare centinaia di righe: la RPC non deve crescere
    -- senza limite).
    SELECT coalesce(jsonb_agg(x.row ORDER BY x.placed_at DESC), '[]'::jsonb) INTO v_trades
      FROM (
        SELECT to_jsonb(t.*)
               || jsonb_build_object('day_placed_at', coalesce(p.placed_at, t.placed_at)) AS row,
               t.placed_at
          FROM public.mike_trades t
          LEFT JOIN public.mike_trades p ON p.id = t.closes_trade_id
         WHERE coalesce(p.placed_at, t.placed_at) >= v_day
            OR t.status IN ('pending','open','hedged')
         ORDER BY t.placed_at DESC
         LIMIT 500
      ) x;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb) INTO v_act
      FROM (SELECT * FROM public.mike_activity WHERE ts >= v_day ORDER BY ts DESC LIMIT 400) a;
    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb) INTO v_reqs
      FROM (SELECT * FROM public.mike_requests ORDER BY created_at DESC LIMIT 50) r;
    v_agg := public.mike_aggregates_sql();
    RETURN jsonb_build_object('control', v_ctrl, 'events', v_events, 'trades', v_trades,
                              'activity', v_act, 'aggregates', v_agg, 'requests', v_reqs,
                              'day_start', v_day, 'day_by', 'placed');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_state() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_state() TO authenticated, service_role;

-- VERIFICA (facoltativa):
--   SELECT public.get_mike_aggregates();
--   SELECT jsonb_object_keys(public.get_mike_state());
--   SELECT status, count(*) FROM public.mike_requests GROUP BY status;
