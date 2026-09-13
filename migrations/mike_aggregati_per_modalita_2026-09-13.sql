-- ============================================================================
-- MIKE — gli aggregati NON devono mai mescolare paper e soldi veri  (13/09/2026)
-- ============================================================================
-- IL PROBLEMA (audit UI del 13/09, bloccante per il passaggio in produzione).
-- `mike_aggregates_sql()` non aveva NESSUN filtro su `mike_trades.mode`, e la
-- CTE della liability nessun filtro su `mike_events.mode`. Finché Mike è girato
-- solo in paper è stato innocuo. Al primo giorno in LIVE, però:
--
--   * «P&L oggi» e «P&L totale» in cima alla pagina avrebbero sommato gli euro
--     veri con quelli simulati, e nulla lo avrebbe dichiarato;
--   * «Liability aperta» avrebbe dichiarato come rischio anche quello di partite
--     in paper, cioè un rischio che non esiste;
--   * lo storico «P&L totale» sarebbe stato inquinato per sempre dai mesi di
--     paper che lo precedono.
--
-- Un trader che legge +42,10 € deve sapere se sono 42 euro o 42 finti. Questa è
-- la differenza fra uno strumento e un giocattolo.
--
-- LA SOLUZIONE. Gli aggregati prendono una modalità:
--   * `NULL` (default)  → la modalità CORRENTE del bot (`mike_control.mode`):
--                         la pagina mostra i numeri di quello che stai facendo;
--   * 'paper' / 'live'  → esplicita, per chi vuole confrontare.
-- In uscita si aggiungono `mode` (quale modalità è stata usata) e i realizzati
-- di ENTRAMBE le modalità, così la UI può mostrare l'altra senza una seconda
-- chiamata e senza che nessuno dei due resti nascosto.
--
-- Idempotente: CREATE OR REPLACE. Nessuna modifica ai dati, nessuna migrazione
-- di righe: cambiano solo le funzioni di lettura.
--
-- VERIFICA dopo l'applicazione:
--   SELECT public.get_mike_aggregates();                    -- modalità corrente
--   SELECT public.mike_aggregates_sql('live');              -- solo soldi veri
--   SELECT public.mike_aggregates_sql('paper');             -- solo simulato
-- ============================================================================

-- 0. via le versioni SENZA argomento ----------------------------------------
-- Obbligatorio: se restassero, `mike_aggregates_sql()` diventerebbe ambigua fra
-- la vecchia a zero argomenti e la nuova con DEFAULT NULL, e Postgres
-- risponderebbe «function ... is not unique» — esattamente il codice nudo che
-- la pagina ha già mostrato una volta con lo storico.
DROP FUNCTION IF EXISTS public.mike_aggregates_sql();
DROP FUNCTION IF EXISTS public.get_mike_aggregates();

-- 1. aggregati, per modalità -------------------------------------------------
CREATE OR REPLACE FUNCTION public.mike_aggregates_sql(p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day,
               -- modalità richiesta, altrimenti quella con cui il bot sta girando.
               -- Il coalesce finale a 'paper' è la scelta prudente: se il control
               -- non fosse leggibile si mostrano i numeri simulati, mai quelli veri.
               coalesce(nullif(p_mode, ''),
                        (SELECT c.mode FROM public.mike_control c WHERE c.id = 1),
                        'paper') AS v_mode
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
         -- il filtro che mancava: mai paper e soldi veri nello stesso numero
         WHERE o.mode = (SELECT v_mode FROM d)
    ), liab AS (
        -- M4: la liability NETTA la pubblica il servizio in
        -- mike_events.live->>'liability'. Anche qui il filtro di modalità:
        -- il rischio delle partite in paper non è rischio.
        SELECT coalesce(sum(nullif(e.live->>'liability','')::numeric), 0) AS open_liability,
               count(*) FILTER (WHERE (e.live ? 'liability')) AS with_liability,
               count(*) FILTER (WHERE (e.live->>'inplay')::boolean) AS live_now
          FROM public.mike_events e
         WHERE e.state NOT IN ('SETTLED','ERROR','SKIPPED')
           AND coalesce(e.mode, 'paper') = (SELECT v_mode FROM d)
    ), altro AS (
        -- i realizzati dell'ALTRA modalità: la UI li mostra come nota, così
        -- nessuno dei due mondi resta invisibile
        SELECT coalesce(sum(x.pnl) FILTER (WHERE x.mode = 'paper'), 0) AS realized_paper,
               coalesce(sum(x.pnl) FILTER (WHERE x.mode = 'live'), 0)  AS realized_live
          FROM public.mike_trades x
         WHERE x.status IN ('won','lost','void')
    ), hb AS (
        SELECT heartbeat_at, (heartbeat_at IS NULL
                              OR heartbeat_at < now() - interval '60 seconds') AS stale
          FROM public.mike_control WHERE id = 1
    )
    SELECT jsonb_build_object(
        'mode',            (SELECT v_mode FROM d),
        'realized_total',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')
                               AND t.pos_placed_at >= d.v_day), 0),
        'realized_paper_total', (SELECT realized_paper FROM altro),
        'realized_live_total',  (SELECT realized_live  FROM altro),
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
     GROUP BY d.v_day, d.v_mode;
$$;
REVOKE ALL ON FUNCTION public.mike_aggregates_sql(text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mike_aggregates_sql(text) TO service_role;

-- Chi chiama `mike_aggregates_sql()` senza argomenti continua a funzionare: il
-- DEFAULT NULL risolve da solo, e NON esiste una seconda funzione con cui
-- l'overload possa diventare ambiguo.

-- 2. la versione owner-only chiamata dalla UI --------------------------------
CREATE OR REPLACE FUNCTION public.get_mike_aggregates(p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN public.mike_aggregates_sql(p_mode);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_aggregates(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_aggregates(text) TO authenticated, service_role;
