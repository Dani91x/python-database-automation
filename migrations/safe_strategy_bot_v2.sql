-- ============================================================================
-- safe_strategy_bot_v2.sql — SAFE STRATEGY, correzioni dell'indagine
-- 11/09/2026 (Betfair/AUDIT_2026-09-11_omega_safe_mike.md, sezione 2).
--
-- Cosa cambia (tutto IDEMPOTENTE, nessuna tabella nuova, nessun dato toccato):
--
--  C-01  GIORNATA OPERATIVA = giorno di PIAZZAMENTO (Europe/Rome) per TUTTO:
--        KPI, pannello rischio, tab Trade e storico. Un numero solo per la
--        stessa giornata. Prima: KPI e storico per giorno di REGOLAZIONE, tab
--        Trade per giorno di piazzamento → tre numeri diversi.
--  H-03  la liability aperta della RPC include i 'pending' in RICONCILIAZIONE
--        (esito dell'ordine ignoto: l'ordine reale può essere vivo) e li espone
--        a parte in ``reconciling_liability``.
--  M-26  ``open_liability`` di una posizione COPERTA è il RESIDUO dopo la
--        copertura (a copertura COMPLETA e CONFERMATA è 0: la perdita è
--        BLOCCATA, non è più un rischio). Una copertura ancora IN VOLO non
--        riduce nulla: liability PIENA. ``day_liability`` invece è sempre il
--        capitale IMPEGNATO (coprire non libera il cap del giorno).
--  M-16  ``won``/``lost`` per SEGNO del P&L della POSIZIONE (apertura +
--        chiusure), non per lo status grezzo della gamba: un green-up in utile
--        non è "perso" solo perché la gamba d'apertura è 'lost'.
--  M-29  ``get_safe_aggregates``: il servizio non legge più TUTTA la tabella a
--        ogni ciclo (2 s) — una funzione SQL, una scansione.
--  H-16  ``get_safe_state`` restituisce anche ``activity`` (le ultime righe di
--        ``safe_strategy_activity``): il log del servizio era invisibile.
--  H-15  ``get_safe_state`` restituisce ``params_effective`` (i valori davvero
--        in uso, clampati dal servizio).
--  M-21  ``safe_strategy_requests.status`` ammette 'rejected' (richiesta
--        RIFIUTATA dal servizio: non un guasto) e ``safe_request`` valida la
--        ``fraction`` del cash out anche come chiusura del RESIDUO.
--  M-17  la finestra massima dello storico vive nelle funzioni CONDIVISE
--        (corretta in mike_history_v2.sql): qui get_safe_daily le chiama solo
--        con p_day_by='placed'.
--
-- NON tocca ``trading_daily_history`` / ``trading_day_trades`` (condivise con
-- Omega e Mike): le richiama solo col parametro ``p_day_by`` = 'placed'.
-- La finestra massima di 400 giorni dello storico (M-17) è corretta dentro
-- quelle funzioni condivise da ``mike_history_v2.sql``: qui non si tocca.
--
-- ORDINE DI APPLICAZIONE (obbligatorio — gli overload a 8/4 argomenti di
-- trading_daily_history / trading_day_trades nascono solo in omega_daily_v2.sql,
-- e le funzioni richiamate qui NON esistono prima):
--    1. betfair_live_order_queue.sql      (betfair_live_is_owner)
--    2. safe_strategy_scan.sql
--    3. safe_strategy_bot.sql
--    4. daily_history.sql
--    5. omega_daily_v2.sql                (p_day_by: firme a 8 e 4 argomenti)
--    6. omega_models_v4.sql
--    7. mike_history_v2.sql               (finestra 400 gg, se presente)
--    8. safe_strategy_bot_v2.sql          ← QUESTO FILE, per ultimo
-- Il codice Python TOLLERA la migrazione non applicata: ``bot_db.aggregates``
-- ripiega sulla scansione a pagine e ``set_request_status`` su 'error'.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Richieste della UI: stato 'rejected' + esito sempre leggibile.
-- ----------------------------------------------------------------------------
ALTER TABLE public.safe_strategy_requests
    DROP CONSTRAINT IF EXISTS safe_strategy_requests_status_check;
ALTER TABLE public.safe_strategy_requests
    ADD CONSTRAINT safe_strategy_requests_status_check
    CHECK (status IN ('pending','processing','done','rejected','error'));

CREATE INDEX IF NOT EXISTS idx_safe_requests_recent
    ON public.safe_strategy_requests (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_safe_activity_kind
    ON public.safe_strategy_activity (kind, ts DESC);
-- M5: la LATERAL degli aggregati risolve le chiusure per apertura su questo
-- indice (in safe_strategy_bot.sql esiste solo parziale: qui si aggiunge la
-- coppia (closes_trade_id, status) che serve al FILTER sui regolati)
CREATE INDEX IF NOT EXISTS idx_safe_trades_closes_status
    ON public.safe_strategy_trades (closes_trade_id, status)
    WHERE closes_trade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_safe_trades_placed_open
    ON public.safe_strategy_trades (placed_at DESC)
    WHERE closes_trade_id IS NULL;

-- ----------------------------------------------------------------------------
-- 2. Aggregati della GIORNATA DI PIAZZAMENTO (una scansione, riusata da
--    get_safe_state per la UI e da get_safe_aggregates per il servizio).
--
--    Specchio ESATTO di ``bot_db.aggregate_rows`` (stessa matematica in due
--    posti: qui per la UI, in Python per il motore di rischio).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_aggregates_sql()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome')
                AT TIME ZONE 'Europe/Rome') AS v_day
    ), t AS (
        SELECT o.id, o.status, o.pnl::numeric AS pnl, o.event_id, o.closes_trade_id,
               o.strategy,
               -- M-26 + review C1/M10: liability RESIDUA dopo la copertura.
               -- 0 SOLO se la copertura e' COMPLETA e CONFERMATA (residuo <= 1c
               -- e nessuna gamba in volo). IGNOTO = PIENO: senza worst_case
               -- (nessuna chiusura fillata: ordine ancora in coda) o senza
               -- residual_size il rischio e' tutto ancora a mercato.
               CASE
                 WHEN (o.meta->'hedge'->>'remaining_liability') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      THEN greatest(0, (o.meta->'hedge'->>'remaining_liability')::numeric)
                 WHEN (o.meta->>'hedged_size') IS NOT NULL
                      AND (o.meta->>'residual_size') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      AND (o.meta->>'residual_size')::numeric <= 0.01
                      AND coalesce(jsonb_array_length(
                            CASE WHEN jsonb_typeof(o.meta->'hedge_pending_ids') = 'array'
                                 THEN o.meta->'hedge_pending_ids' END), 0) = 0 THEN 0
                 WHEN (o.meta->>'hedged_size') IS NOT NULL
                      AND (o.meta->>'residual_size') IS NOT NULL
                      AND (o.meta->>'worst_case') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      THEN greatest(0, -(o.meta->>'worst_case')::numeric)
                 ELSE greatest(0, coalesce(o.liability, 0)::numeric)
               END AS liability,
               -- review H1: capitale IMPEGNATO nella giornata = liability
               -- d'apertura SEMPRE (coprire una posizione NON libera il cap)
               greatest(0, coalesce(o.liability, 0)::numeric) AS committed,
               -- ordine (potenzialmente) a mercato: conta nell'esposizione
               (o.bet_id IS NOT NULL
                OR (o.meta->>'flumine_client_ref') IS NOT NULL
                OR (o.meta->>'reason') = 'place_exception_reconciling') AS is_placed,
               -- H-03: 'pending' a esito IGNOTO (riconciliazione in corso)
               (o.status = 'pending'
                AND (o.meta->>'reason') = 'place_exception_reconciling') AS is_reconciling,
               -- C-01: giorno della POSIZIONE = piazzamento dell'APERTURA
               coalesce(p.placed_at, o.placed_at) AS pos_placed_at,
               o.placed_at,
               -- M-16: esito della POSIZIONE per SEGNO del P&L totale.
               -- M5: LATERAL aggregato (una passata sull'indice) invece di una
               -- sotto-query correlata per riga.
               CASE WHEN o.closes_trade_id IS NULL AND o.status IN ('won','lost','void') THEN
                    o.pnl + coalesce(cl.pnl_sum, 0)
               END AS total_pnl
          FROM public.safe_strategy_trades o
          LEFT JOIN public.safe_strategy_trades p ON p.id = o.closes_trade_id
          LEFT JOIN LATERAL (
              SELECT sum(c.pnl)::numeric AS pnl_sum
                FROM public.safe_strategy_trades c
               WHERE c.closes_trade_id = o.id
                 AND c.status IN ('won','lost','void')
          ) cl ON o.closes_trade_id IS NULL
    )
    SELECT jsonb_build_object(
        'realized_total', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')
                              AND t.pos_placed_at >= d.v_day), 0),
        'open_liability', coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                              AND (t.status IN ('open','hedged')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'open_count',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND (t.status IN ('open','hedged')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'reconciling_liability', coalesce(sum(t.liability) FILTER (
                              WHERE t.closes_trade_id IS NULL AND t.is_reconciling), 0),
        'reconciling_count',  count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.is_reconciling),
        -- CAPITALE IMPEGNATO nella giornata: base dei cap di risk.py (review
        -- H1: NON il residuo, altrimenti ogni green-up libera il cap)
        'day_liability',  coalesce(sum(t.committed) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'day_liability_model', coalesce(sum(t.committed) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND t.strategy = 'model'
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'day_trades',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'legs_today',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'events_today',   count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'won',            count(*) FILTER (WHERE t.total_pnl > 0),
        'lost',           count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',      count(*) FILTER (WHERE t.total_pnl > 0 AND t.pos_placed_at >= d.v_day),
        'lost_today',     count(*) FILTER (WHERE t.total_pnl < 0 AND t.pos_placed_at >= d.v_day),
        'operating_day',  to_char(d.v_day AT TIME ZONE 'Europe/Rome', 'YYYY-MM-DD')
    )
      FROM d LEFT JOIN t ON true
     GROUP BY d.v_day;
$$;
REVOKE ALL ON FUNCTION public.safe_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.safe_aggregates_sql() TO service_role;

-- RPC per il SERVIZIO (M-29): un solo giro invece della tabella intera.
-- SECURITY DEFINER + controllo owner (M4): senza, qualunque utente autenticato
-- leggerebbe l'esposizione del conto.
CREATE OR REPLACE FUNCTION public.get_safe_aggregates()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN public.safe_aggregates_sql();
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_aggregates() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_aggregates() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. get_safe_state — stato completo per la dashboard.
--    Aggiunge: aggregati della giornata di PIAZZAMENTO, reconciling_liability,
--    won/lost per posizione, activity del servizio (H-16) e params_effective
--    (H-15). Le chiavi vecchie restano tutte (nessuna rottura della UI).
-- ----------------------------------------------------------------------------
-- ATTENZIONE: UNA SOLA firma (nessun argomento). Aggiungere un overload con
-- DEFAULT renderebbe ambigua la chiamata ``get_safe_state()`` della UI — è
-- l'errore che ha rotto lo storico di Mike (mike_history.sql, punto R2).
CREATE OR REPLACE FUNCTION public.get_safe_state()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    c_activity integer := 80;
    v_ctrl     jsonb;
    v_trades   jsonb;
    v_agg      jsonb;
    v_activity jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.safe_strategy_control c WHERE c.id = 1;

    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_trades
      FROM (SELECT * FROM public.safe_strategy_trades
             ORDER BY placed_at DESC LIMIT 200) t;

    v_agg := public.safe_aggregates_sql();

    -- H-16: il log del servizio (skip, risk_block, exit, exit_failed, settle,
    -- feed_blind, params_invalid...) era scritto e mai letto da nessuno.
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.id DESC), '[]'::jsonb)
      INTO v_activity
      FROM (SELECT id, ts, kind, payload FROM public.safe_strategy_activity
             ORDER BY id DESC
             LIMIT c_activity) a;

    RETURN jsonb_build_object(
        'control',           v_ctrl,
        'trades',            v_trades,
        'aggregates',        v_agg,
        'activity',          v_activity,
        -- H-15: i parametri realmente in uso (il servizio li scrive in stats)
        'params_effective',  coalesce(v_ctrl->'stats'->'params_effective', 'null'::jsonb),
        'operating_day',     v_agg->'operating_day'
    );
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_state() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_state() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. Attività del servizio: RPC dedicata (filtrabile per kind) — la UI non
--    deve leggere 200 trade per vedere 50 righe di log.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_activity(
    p_limit integer DEFAULT 100,
    p_kinds text[] DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.id DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT id, ts, kind, payload FROM public.safe_strategy_activity
             WHERE p_kinds IS NULL OR kind = ANY(p_kinds)
             ORDER BY id DESC
             LIMIT least(greatest(coalesce(p_limit, 100), 1), 500)) a;
    RETURN v_rows;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_activity(integer,text[]) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_activity(integer,text[]) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5. STORICO per giorno di PIAZZAMENTO (C-01): get_safe_daily /
--    get_safe_day_trades passano 'placed' al motore condiviso, come Omega.
--    Le funzioni condivise NON vengono ridefinite (lezione di mike_history.sql:
--    ricrearle con firme diverse le rende ambigue e rompe tutti i bot).
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
        NULL,
        'placed');   -- C-01: giornata = giorno di PIAZZAMENTO
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
    RETURN public.trading_day_trades('safe_strategy_trades', v_filter, p_day, 'placed');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_day_trades(date,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_day_trades(date,text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 6. safe_request: validazione della ``fraction`` come chiusura del RESIDUO
--    (M-06) e messaggio parlante. Resto invariato rispetto a safe_strategy_bot.sql.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id       bigint;
    v_payload  jsonb := coalesce(p_payload, '{}'::jsonb);
    v_amount   numeric;
    v_fraction numeric;
    v_price    numeric;
    v_size     numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('place','cashout','cancel') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;

    IF p_kind = 'place' THEN
        IF coalesce(v_payload->>'event_id','') = ''
           OR coalesce(v_payload->>'market_id','') = ''
           OR coalesce(v_payload->>'market_type','') = ''
           OR v_payload->>'selection_id' IS NULL
           OR coalesce(v_payload->>'side','') NOT IN ('back','lay')
           OR v_payload->>'price' IS NULL
           OR v_payload->>'size' IS NULL THEN
            RAISE EXCEPTION 'payload place incompleto (servono event_id, market_id, market_type, selection_id, side, price, size)';
        END IF;
        BEGIN
            v_price := nullif(v_payload->>'price','')::numeric;
            v_size  := nullif(v_payload->>'size','')::numeric;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'price/size non numerici: price=%, size=%',
                            v_payload->>'price', v_payload->>'size';
        END;
        IF v_price IS NULL OR v_price <= 1.0 THEN
            RAISE EXCEPTION 'price non valido: %', v_payload->>'price';
        END IF;
        IF v_size IS NULL OR v_size <= 0 THEN
            RAISE EXCEPTION 'size non valida: %', v_payload->>'size';
        END IF;
        IF coalesce(v_payload->>'mode','paper') NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    ELSIF p_kind = 'cashout' THEN
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cashout senza trade_id';
        END IF;
        BEGIN
            v_amount   := nullif(v_payload->>'amount','')::numeric;
            v_fraction := nullif(v_payload->>'fraction','')::numeric;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'amount/fraction non numerici: amount=%, fraction=%',
                            v_payload->>'amount', v_payload->>'fraction';
        END;
        IF v_amount IS NOT NULL AND v_amount <= 0 THEN
            RAISE EXCEPTION 'amount deve essere > 0: %', v_amount;
        END IF;
        -- M-06: la frazione si applica all'esposizione RESIDUA (cash out
        -- ripetuti sullo stesso trade): resta valida in (0,1].
        IF v_fraction IS NOT NULL AND (v_fraction <= 0 OR v_fraction > 1) THEN
            RAISE EXCEPTION 'fraction deve essere in (0,1]: %', v_fraction;
        END IF;
    ELSE  -- cancel
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cancel senza trade_id';
        END IF;
    END IF;

    INSERT INTO public.safe_strategy_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_request(text,jsonb) TO authenticated, service_role;
