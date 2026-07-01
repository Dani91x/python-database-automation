-- ============================================================================
-- betfair_live_risk_rules.sql — Fase 3: RISK ENGINE (offset / stop-loss /
-- take-profit / trailing stop). Regole ARMATE per-selezione che il
-- ``risk_engine_worker`` (nel runner) monitora ad ogni giro: quando la condizione
-- scatta, ACCODA l'ordine di chiusura/copertura nella coda esistente
-- ``betfair_live_order_requests`` (stesso path audited/mirror) e marca la regola
-- 'triggered'. NESSUN ordine viene piazzato da questa tabella: è solo lo stato
-- delle regole. La matematica (tick/soglie) è in Betfair/stream/trading/risk_engine.py.
--
-- ⚠️ SOFTWARE-SIDE: come in tutti i tool pro (Bet Angel/Cymatic/Fairbot) questi
-- stop/offset sono innescati dal software, NON sono ordini "resting" sull'Exchange:
-- se il runner/processo cade, NON esistono. La UI lo dichiara esplicitamente.
--
-- MONEY-CRITICAL (soldi veri in mode='live'). Idempotenza anti-doppio-trigger:
--  * client_ref UNIQUE della regola → una richiesta del frontend non crea due regole;
--  * quando scatta, il worker accoda con un client_ref DETERMINISTICO ('risk<rule_id>')
--    → il vincolo UNIQUE della coda ordini garantisce UN SOLO ordine di chiusura anche
--    se il worker rivalutasse la regola prima di vederla 'triggered'.
--
-- IDEMPOTENTE: CREATE ... IF NOT EXISTS / OR REPLACE. Tutte le RPC SECURITY DEFINER,
-- owner-only (betfair_live_is_owner da betfair_live_order_queue.sql — applicare DOPO).
-- ============================================================================


-- ============================================================================
-- 1. betfair_live_risk_rules — regole armate del risk engine.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_risk_rules (
    id                  BIGSERIAL PRIMARY KEY,
    client_ref          TEXT NOT NULL UNIQUE,          -- idempotency key (UUID dal frontend)
    mode                TEXT NOT NULL
                          CHECK (mode IN ('paper','live')),
    rule_type           TEXT NOT NULL
                          CHECK (rule_type IN ('offset','stop_loss','take_profit','trailing_stop')),
    market_id           TEXT NOT NULL,
    selection_id        BIGINT NOT NULL,
    handicap            NUMERIC NOT NULL DEFAULT 0,
    entry_side          TEXT NOT NULL
                          CHECK (entry_side IN ('back','lay')),  -- lato della POSIZIONE protetta
    entry_price         NUMERIC
                          CHECK (entry_price IS NULL OR entry_price BETWEEN 1.01 AND 1000),
    entry_size          NUMERIC,
    -- params jsonb: offset_ticks|offset_pct, trigger_ticks|trigger_pct, trail_ticks|trail_pct,
    -- greening(bool), stop_amount, target_amount, place_at_ticks. Interpretati da risk_engine.
    params              JSONB,
    trail_extreme       NUMERIC,                        -- estremo favorevole (worker, trailing)
    status              TEXT NOT NULL DEFAULT 'armed'
                          CHECK (status IN ('armed','triggered','cancelled','done','error')),
    enqueued_client_ref TEXT,                           -- client_ref usato per accodare la chiusura
    enqueued_request_id BIGINT,                         -- id riga betfair_live_order_requests creata
    result              JSONB,
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    triggered_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_blrr_armed
    ON public.betfair_live_risk_rules (id) WHERE status = 'armed';
CREATE INDEX IF NOT EXISTS idx_blrr_market
    ON public.betfair_live_risk_rules (market_id);

ALTER TABLE public.betfair_live_risk_rules ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_risk_rules FROM anon, authenticated;


-- ============================================================================
-- 2.1 request_live_risk_rule — arma UNA regola. Idempotente su client_ref.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_live_risk_rule(p jsonb)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id          bigint;
    v_client_ref  text := nullif(p->>'client_ref', '');
    v_mode        text := nullif(p->>'mode', '');
    v_rule_type   text := nullif(p->>'rule_type', '');
    v_side        text := nullif(p->>'entry_side', '');
    v_market      text := nullif(p->>'market_id', '');
    v_selection   text := nullif(p->>'selection_id', '');
    v_entry_price numeric := nullif(p->>'entry_price', '')::numeric;
BEGIN
    -- OWNER-ONLY: denaro REALE in mode='live'.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;
    IF v_rule_type IS NULL
       OR v_rule_type NOT IN ('offset','stop_loss','take_profit','trailing_stop') THEN
        RAISE EXCEPTION 'rule_type non valido (offset|stop_loss|take_profit|trailing_stop)';
    END IF;
    IF v_side IS NULL OR v_side NOT IN ('back','lay') THEN
        RAISE EXCEPTION 'entry_side non valido (back|lay)';
    END IF;
    IF v_market IS NULL OR v_selection IS NULL THEN
        RAISE EXCEPTION 'market_id, selection_id obbligatori';
    END IF;
    -- entry_price obbligatorio per le regole TICK-based (offset/stop_loss/trailing_stop);
    -- take_profit può basarsi solo su soglia P&L (params.target_amount/stop_amount).
    IF v_rule_type IN ('offset','stop_loss','trailing_stop') AND v_entry_price IS NULL THEN
        RAISE EXCEPTION 'entry_price obbligatorio per %', v_rule_type;
    END IF;
    IF v_entry_price IS NOT NULL AND v_entry_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'entry_price fuori range Betfair [1.01, 1000]';
    END IF;

    -- idempotenza: stesso client_ref → stessa regola
    SELECT id INTO v_id FROM public.betfair_live_risk_rules WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_live_risk_rules
        (client_ref, mode, rule_type, market_id, selection_id, handicap,
         entry_side, entry_price, entry_size, params)
    VALUES (
        v_client_ref,
        v_mode,
        v_rule_type,
        v_market,
        v_selection::bigint,
        coalesce(nullif(p->>'handicap','')::numeric, 0),
        v_side,
        v_entry_price,
        nullif(p->>'entry_size','')::numeric,
        CASE WHEN p ? 'params' THEN p->'params' ELSE NULL END
    )
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM public.betfair_live_risk_rules WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;


-- ============================================================================
-- 2.2 cancel_live_risk_rule — disarma una regola ancora 'armed'. Owner-only.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.cancel_live_risk_rule(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_id IS NULL OR p_id <= 0 THEN
        RAISE EXCEPTION 'p_id non valido';
    END IF;

    -- Solo se ancora 'armed': una regola già 'triggered' ha (forse) già accodato la
    -- chiusura → non la si tocca, per non lasciare l'ordine di chiusura orfano.
    UPDATE public.betfair_live_risk_rules
       SET status = 'cancelled', updated_at = now()
     WHERE id = p_id AND status = 'armed';

    SELECT to_jsonb(r.*) INTO v_row
      FROM public.betfair_live_risk_rules r WHERE r.id = p_id;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.3 get_live_risk_rules — regole di un mercato per la UI. { rows: [...] }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_risk_rules(p_market_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_market_id IS NULL THEN
        RAISE EXCEPTION 'p_market_id nullo';
    END IF;
    IF length(p_market_id) > 32 THEN
        RAISE EXCEPTION 'p_market_id non valido';
    END IF;

    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM public.betfair_live_risk_rules r
     WHERE r.market_id = p_market_id;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- GRANTS — owner-only DENTRO le RPC; tabelle invisibili a anon/authenticated.
-- ============================================================================
REVOKE ALL    ON FUNCTION public.request_live_risk_rule(jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.request_live_risk_rule(jsonb) TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.cancel_live_risk_rule(bigint) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.cancel_live_risk_rule(bigint) TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_live_risk_rules(text)     FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_risk_rules(text)     TO authenticated, service_role;
