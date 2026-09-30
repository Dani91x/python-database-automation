-- ============================================================================
-- live_orders_account_open_2026-09-30.sql
--
-- 30/09 (backend per la UI, monitor veritiero): RPC di SOLA LETTURA
-- ``get_live_orders_account_open()`` = gli ordini APERTI del CONTO Betfair che
-- NON sono dei bot (piazzati dall'utente dal sito o dal terminale manuale
-- dell'app), con i nomi di evento/mercato/selezione risolti dal catalogo.
--
-- FONTE: lo specchio ``betfair_live_orders`` (betfair_live_order_queue.sql
-- sez. 1.2), scritto dal runner (terminale manuale, source='runner') e dalla
-- riconciliazione col conto (reconcile_worker._account_order_row,
-- source='account' = ordine visto sul conto e mai piazzato da noi).
--
-- QUALI RIGHE:
--   * mode = 'live' (il paper non e' sul conto: mai sommato);
--   * source IN ('runner','account'): le source dei bot ('scalper','omega',
--     'safe','mike','safe_tennis','tennis_*', vincolo
--     betfair_live_orders_source_check) sono ESCLUSE; gli ordini REST diretti
--     dei bot (customerStrategyRef mike/omega/safe) non entrano nello specchio
--     (CHECK + reconcile_worker 30/09), e comunque una riga il cui bet_id sta in
--     omega_trades / safe_strategy_trades / mike_trades (mode live) e' del bot
--     ed e' esclusa (stessa regola «chi e' di chi» di reconcile_worker);
--   * status IN ('EXECUTABLE','EXECUTION_COMPLETE') con qualcosa in gioco
--     (abbinato > 0, oppure EXECUTABLE con residuo > 0);
--   * mercato NON regolato e NON chiuso: nessun pnl_betfair_settled_at sulla
--     riga, nessuna riga live di betfair_live_settled per il mercato, bet_id
--     non fra i regolati di oggi (betfair_live_account.pnl_reale_oggi.bet_ids), blocco del
--     feed dello scanner non 'CLOSED', partita del catalogo non finita
--     (live_follow.status non in CLOSED/UPLOADED, runner._finalize_event).
--
-- NOMI (null se non risolvibili, MAI inventati):
--   event_id       : riga dello specchio -> catalogo live_markets -> feed scanner;
--   event_name     : feed scanner (payload.event_name, nome Betfair) -> catalogo
--                    live_follow (home_name || ' v ' || away_name, il formato
--                    Betfair che scanner.split_event_name divide);
--   market_name    : catalogo live_markets.market_name del mercato -> nome VERO
--                    dello stesso market_type in live_markets (verificato 1:1 il
--                    30/09: MATCH_ODDS 'Match Odds', OVER_UNDER_25 'Over/Under 2.5
--                    Goals', ...);
--   selection_name : selections del mercato in live_markets -> selections del
--                    blocco del feed (cs/ht/ou/btts/ht_result; per il Match Odds
--                    odds.home/away/p1/p2 -> payload.home/away/p1/p2) -> stesso
--                    selection_id nello stesso market_type del catalogo.
--
-- FORMA: { "rows": [ { bet_id, market_id, selection_id, event_id, event_name,
--          market_name, selection_name, side ('BACK'|'LAY'), price_matched,
--          size_matched, size_remaining, status, source, placed_at } ],
--          "letto_at": now() }
-- price_matched = average_price_matched; NULL se nulla e' abbinato (lo specchio
-- scrive 0: non e' un prezzo).
--
-- SICUREZZA: SECURITY DEFINER, search_path fisso, owner-only
-- (betfair_live_is_owner, come get_live_orders). Nessuna scrittura.
-- IDEMPOTENTE (CREATE OR REPLACE). Da applicare DOPO betfair_live_order_queue.sql,
-- betfair_live_account_heartbeat.sql (colonna source), pnl_betfair_reale_2026-09-24.sql
-- (colonna pnl_betfair_settled_at), betfair_live_pnl_journal.sql (betfair_live_settled).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_orders_account_open()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    -- OWNER-ONLY: ordini su denaro reale.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    WITH ordini AS (
        SELECT o.*
          FROM public.betfair_live_orders o
         WHERE o.mode = 'live'
           AND o.source IN ('runner', 'account')
           AND o.bet_id IS NOT NULL
           AND o.status IN ('EXECUTABLE', 'EXECUTION_COMPLETE')
           AND (coalesce(o.size_matched, 0) > 0
                OR (o.status = 'EXECUTABLE' AND coalesce(o.size_remaining, 0) > 0))
           AND o.pnl_betfair_settled_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM public.betfair_live_settled s
                            WHERE s.mode = 'live' AND s.market_id = o.market_id)
           -- regolato OGGI secondo Betfair (listClearedOrders, giro del P&L
           -- reale del conto: betfair_live_account.pnl_reale_oggi.bet_ids)
           AND NOT EXISTS (SELECT 1 FROM public.betfair_live_account a
                            CROSS JOIN LATERAL jsonb_array_elements_text(
                                CASE WHEN jsonb_typeof(a.pnl_reale_oggi -> 'bet_ids') = 'array'
                                     THEN a.pnl_reale_oggi -> 'bet_ids' ELSE '[]'::jsonb END) AS r(bet)
                            WHERE a.id = 1 AND r.bet = o.bet_id)
           AND NOT EXISTS (SELECT 1 FROM public.omega_trades t
                            WHERE t.mode = 'live' AND t.bet_id = o.bet_id)
           AND NOT EXISTS (SELECT 1 FROM public.safe_strategy_trades t
                            WHERE t.mode = 'live' AND t.bet_id = o.bet_id)
           AND NOT EXISTS (SELECT 1 FROM public.mike_trades t
                            WHERE t.mode = 'live' AND t.bet_id = o.bet_id)
    ),
    -- catalogo del runner: un mercato -> evento, nome, selezioni
    catalogo AS (
        SELECT DISTINCT ON (lm.market_id)
               lm.market_id, lm.event_id, lm.market_name, lm.selections
          FROM public.live_markets lm
         WHERE lm.market_id IN (SELECT market_id FROM ordini)
         ORDER BY lm.market_id, lm.id DESC
    ),
    -- feed dello scanner: ogni blocco di mercato del payload
    feed AS (
        SELECT DISTINCT ON (m.market_id)
               sc.event_id, sc.payload ->> 'event_name' AS event_name,
               m.market_id, m.status, m.market_type, m.selections
          FROM public.safe_strategy_scan sc
         CROSS JOIN LATERAL (
            SELECT sc.payload ->> 'mo_market_id', sc.payload ->> 'mo_status',
                   'MATCH_ODDS',
                   (SELECT jsonb_agg(jsonb_build_object(
                               'selection_id', sc.payload -> 'odds' -> k -> 'selection_id',
                               'name', sc.payload ->> k))
                      FROM unnest(ARRAY['home', 'away', 'p1', 'p2']) AS k
                     WHERE jsonb_typeof(sc.payload -> 'odds' -> k) = 'object'
                       AND sc.payload -> 'odds' -> k ->> 'selection_id' IS NOT NULL
                       AND sc.payload ->> k IS NOT NULL)
            UNION ALL
            SELECT sc.payload -> 'cs' ->> 'market_id', sc.payload -> 'cs' ->> 'status',
                   'CORRECT_SCORE', sc.payload -> 'cs' -> 'selections'
             WHERE jsonb_typeof(sc.payload -> 'cs') = 'object'
            UNION ALL
            SELECT sc.payload -> 'ht' ->> 'market_id', sc.payload -> 'ht' ->> 'status',
                   'HALF_TIME_SCORE', sc.payload -> 'ht' -> 'selections'
             WHERE jsonb_typeof(sc.payload -> 'ht') = 'object'
            UNION ALL
            SELECT sc.payload -> 'btts' ->> 'market_id', sc.payload -> 'btts' ->> 'status',
                   coalesce(sc.payload -> 'btts' ->> 'market_type', 'BOTH_TEAMS_TO_SCORE'),
                   sc.payload -> 'btts' -> 'selections'
             WHERE jsonb_typeof(sc.payload -> 'btts') = 'object'
            UNION ALL
            SELECT sc.payload -> 'ht_result' ->> 'market_id', sc.payload -> 'ht_result' ->> 'status',
                   coalesce(sc.payload -> 'ht_result' ->> 'market_type', 'HALF_TIME'),
                   sc.payload -> 'ht_result' -> 'selections'
             WHERE jsonb_typeof(sc.payload -> 'ht_result') = 'object'
            UNION ALL
            SELECT b ->> 'market_id', b ->> 'status', b ->> 'market_type', b -> 'selections'
              FROM jsonb_array_elements(CASE WHEN jsonb_typeof(sc.payload -> 'ou') = 'array'
                                             THEN sc.payload -> 'ou' ELSE '[]'::jsonb END) AS b
             WHERE jsonb_typeof(b) = 'object'
         ) AS m(market_id, status, market_type, selections)
         WHERE m.market_id IN (SELECT market_id FROM ordini)
         ORDER BY m.market_id, sc.updated_at DESC
    ),
    base AS (
        SELECT o.*, c.event_id AS cat_event_id, c.market_name AS cat_market_name,
               c.selections AS cat_selections,
               f.event_id AS feed_event_id, f.event_name AS feed_event_name,
               f.status AS feed_status, f.market_type AS feed_market_type,
               f.selections AS feed_selections,
               lf.status AS follow_status,
               CASE WHEN lf.home_name IS NOT NULL AND lf.away_name IS NOT NULL
                    THEN lf.home_name || ' v ' || lf.away_name END AS follow_event_name
          FROM ordini o
          LEFT JOIN catalogo c ON c.market_id = o.market_id
          LEFT JOIN feed f     ON f.market_id = o.market_id
          LEFT JOIN public.live_follow lf
                 ON lf.event_id = coalesce(o.event_id, c.event_id, f.event_id)
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'bet_id',         b.bet_id,
               'market_id',      b.market_id,
               'selection_id',   b.selection_id,
               'event_id',       coalesce(b.event_id, b.cat_event_id, b.feed_event_id),
               'event_name',     coalesce(b.feed_event_name, b.follow_event_name),
               'market_name',    coalesce(
                                     b.cat_market_name,
                                     (SELECT n.market_name FROM public.live_markets n
                                       WHERE n.market_type = b.feed_market_type
                                         AND n.market_name IS NOT NULL
                                       ORDER BY n.id DESC LIMIT 1)),
               'selection_name', coalesce(
                                     (SELECT s ->> 'name'
                                        FROM jsonb_array_elements(
                                                 CASE WHEN jsonb_typeof(b.cat_selections) = 'array'
                                                      THEN b.cat_selections ELSE '[]'::jsonb END) AS s
                                       WHERE s ->> 'selection_id' = b.selection_id::text
                                       LIMIT 1),
                                     (SELECT s ->> 'name'
                                        FROM jsonb_array_elements(
                                                 CASE WHEN jsonb_typeof(b.feed_selections) = 'array'
                                                      THEN b.feed_selections ELSE '[]'::jsonb END) AS s
                                       WHERE s ->> 'selection_id' = b.selection_id::text
                                         AND coalesce(s ->> 'name', '') <> ''
                                       LIMIT 1),
                                     (SELECT s ->> 'name'
                                        FROM public.live_markets n
                                        CROSS JOIN LATERAL jsonb_array_elements(
                                                 CASE WHEN jsonb_typeof(n.selections) = 'array'
                                                      THEN n.selections ELSE '[]'::jsonb END) AS s
                                       WHERE n.market_type = b.feed_market_type
                                         AND s ->> 'selection_id' = b.selection_id::text
                                       LIMIT 1)),
               'side',           upper(b.side),
               'price_matched',  CASE WHEN coalesce(b.size_matched, 0) > 0
                                      THEN b.average_price_matched END,
               'size_matched',   b.size_matched,
               'size_remaining', b.size_remaining,
               'status',         b.status,
               'source',         b.source,
               'placed_at',      b.placed_at
           ) ORDER BY b.placed_at DESC NULLS LAST, b.id DESC), '[]'::jsonb)
      INTO v_rows
      FROM base b
     WHERE coalesce(b.feed_status, '') <> 'CLOSED'
       AND coalesce(b.follow_status, '') NOT IN ('CLOSED', 'UPLOADED');

    RETURN jsonb_build_object('rows', v_rows, 'letto_at', now());
END;
$$;

REVOKE ALL    ON FUNCTION public.get_live_orders_account_open() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_orders_account_open() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- VERIFICA (sola lettura, dopo l'applicazione, dal SQL editor come owner):
--   SELECT public.get_live_orders_account_open();
-- ----------------------------------------------------------------------------
