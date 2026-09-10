-- ============================================================================
-- omega_cashout.sql — CASH-OUT / GREEN-UP delle gambe Omega (additiva a
-- omega_bot.sql + omega_manual.sql + omega_missions.sql + omega_v2.sql).
-- Da applicare DOPO omega_v2.sql (ricrea l'unique uq_omega_trades_auto_leg,
-- che usa la colonna omega_trades.phase di omega_missions.sql).
--
-- Aggiunge il MINIMO indispensabile perché l'utente possa chiudere a mercato
-- una gamba già aperta (green-up totale o cash-out parziale):
--   • kind 'cashout' nella coda manuale (payload: {trade_id, amount?|fraction?})
--   • omega_trades.closes_trade_id → la gamba di chiusura punta all'apertura
--   • status 'hedged' → apertura CHIUSA a mercato, P&L bloccato in
--     meta.locked_pnl; il settlement nettizza le due gambe insieme
--     (Betfair/safe_strategy/execution.settle_pair).
--   • gli unique parziali (gamba / gamba automatica) ESCLUDONO le chiusure:
--     una gamba di chiusura ha stesso (event, market, selection) dell'apertura
--     e side opposto, ma una SECONDA chiusura parziale della stessa apertura
--     collide con la prima — e la chiusura eredita origin/phase dall'apertura.
--
-- IDEMPOTENTE. I CHECK vengono cercati in pg_constraint per COLONNA (mai per
-- nome hard-coded: il nome può differire se la tabella è nata da un CREATE
-- inline). Nessun'altra modifica: aggregati e RPC esistenti restano com'erano.
-- ============================================================================

-- 1. coda manuale: kind 'cashout' ammesso.
--    Drop di OGNI check mono-colonna su omega_manual_requests.kind, poi add.
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    FOR c_name IN
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conrelid = 'public.omega_manual_requests'::regclass
           AND c.contype = 'c'
           AND a.attname = 'kind'
           AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format('ALTER TABLE public.omega_manual_requests DROP CONSTRAINT %I', c_name);
    END LOOP;
END; $$;

ALTER TABLE public.omega_manual_requests
    ADD CONSTRAINT omega_manual_requests_kind_check
    CHECK (kind IN ('refresh_events','load_markets','load_book','place','cashout'));
COMMIT;

-- 2. omega_trades: gamba di chiusura + stato 'hedged'.
ALTER TABLE public.omega_trades
    ADD COLUMN IF NOT EXISTS closes_trade_id BIGINT REFERENCES public.omega_trades(id);
CREATE INDEX IF NOT EXISTS idx_omega_trades_closes
    ON public.omega_trades (closes_trade_id) WHERE closes_trade_id IS NOT NULL;

--    Drop di OGNI check mono-colonna su omega_trades.status, poi add.
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    FOR c_name IN
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conrelid = 'public.omega_trades'::regclass
           AND c.contype = 'c'
           AND a.attname = 'status'
           AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format('ALTER TABLE public.omega_trades DROP CONSTRAINT %I', c_name);
    END LOOP;
END; $$;

ALTER TABLE public.omega_trades
    ADD CONSTRAINT omega_trades_status_check
    CHECK (status IN ('pending','open','hedged','won','lost','void','error'));
COMMIT;

-- 2b. Unique parziali: le gambe di CHIUSURA (closes_trade_id NOT NULL) restano
--     fuori. uq_omega_trades_leg (omega_manual.sql) e uq_omega_trades_auto_leg
--     (omega_v2.sql) altrimenti bloccano la seconda chiusura parziale della
--     stessa apertura (stessa chiave, stesso side) o — per l'automatico — la
--     chiusura di una gamba auto (stesso event_id + phase dell'apertura).
DROP INDEX IF EXISTS public.uq_omega_trades_leg;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_leg
    ON public.omega_trades (event_id, market_id, selection_id, side)
    WHERE status <> 'error' AND closes_trade_id IS NULL;

DROP INDEX IF EXISTS public.uq_omega_trades_auto_leg;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_auto_leg
    ON public.omega_trades (event_id, coalesce(phase, ''))
    WHERE origin = 'auto' AND closes_trade_id IS NULL;

-- 3. RPC omega_request: la whitelist dei kind deve includere 'cashout',
--    altrimenti la UI non può accodare la richiesta (stessa firma, owner-only).
--    Validazione payload: trade_id obbligatorio; amount>0 / fraction in (0,1].
CREATE OR REPLACE FUNCTION public.omega_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id       bigint;
    v_payload  jsonb := coalesce(p_payload, '{}'::jsonb);
    v_amount   numeric;
    v_fraction numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('refresh_events','load_markets','load_book','place','cashout') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;
    IF p_kind = 'cashout' THEN
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cashout senza trade_id';
        END IF;
        v_amount   := nullif(v_payload->>'amount','')::numeric;
        v_fraction := nullif(v_payload->>'fraction','')::numeric;
        IF v_amount IS NOT NULL AND v_amount <= 0 THEN
            RAISE EXCEPTION 'amount deve essere > 0: %', v_amount;
        END IF;
        IF v_fraction IS NOT NULL AND (v_fraction <= 0 OR v_fraction > 1) THEN
            RAISE EXCEPTION 'fraction deve essere in (0,1]: %', v_fraction;
        END IF;
    END IF;
    INSERT INTO public.omega_manual_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_request(text,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. get_omega_state: gli aggregati contano anche le aperture 'hedged' (rischio
--    vivo fino al settlement, stima prudente = liability piena) ed ESCLUDONO le
--    gambe di chiusura (closes_trade_id) dai conteggi partita: il loro pnl entra
--    nel realizzato quando regolate. Un 'pending' conta come piazzato se ha
--    bet_id (ordine reale a mercato) OPPURE meta.flumine_client_ref (ordine
--    PAPER già sul book simulato). Allineato a omega_engine.aggregate_trades.
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
    v_day  timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.omega_control c WHERE c.id = 1;

    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.settled_at >= v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))), 0),
        'matches_traded',  count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        'matches_traded_today', count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))
                               AND t.placed_at >= v_day),
        'matches_open',    count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))),
        'matches_won',     count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'won'),
        'matches_lost',    count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status = 'lost')
    ) INTO v_agg
      FROM (SELECT o.*,
                   (o.bet_id IS NOT NULL OR (o.meta->>'flumine_client_ref') IS NOT NULL) AS is_placed
              FROM public.omega_trades o) t;

    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.omega_activity
             ORDER BY ts DESC
             LIMIT least(greatest(coalesce(p_activity_limit, 50), 1), 300)) a;

    RETURN jsonb_build_object('control', v_ctrl, 'aggregates', v_agg, 'activity', v_act);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_state(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;
