-- ============================================================================
-- betfair_live_risk_rules_v4.sql — Risk engine v4 (roadmap F39).
-- Nuovo rule_type:
--   * ``auto_hedge`` → floor-keeper del worst-case SCORELINE dell'EVENTO:
--     quando il P&L peggiore cross-market (betfair_live_xhedge) scende sotto
--     −params.floor, il risk engine accoda la copertura Correct Score suggerita
--     (BACK sullo scoreline peggiore, ID esatti dal catalogo scritti dal worker).
--     La regola RESTA armata (ri-copre se il worst degrada di nuovo), con
--     params.max_hedges (default 3) e params.cooldown_sec (default 60) come
--     limiti espliciti. MAI su matrice incompleta (ignored_orders > 0).
--
--     Campi regola: market_id = mercato CORRECT_SCORE dell'evento (dove verranno
--     piazzate le coperture), selection_id = 0 (la selezione varia per copertura),
--     entry_side = 'back'. params: { event_id, floor > 0, max_hedges?, cooldown_sec?,
--     max_stake? }.
--
-- IDEMPOTENTE. Da applicare DOPO betfair_live_risk_rules_v3.sql.
-- ============================================================================

-- 1) allarga il CHECK rule_type (trova il constraint per CONTENUTO, mai per nome).
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    SELECT conname INTO c_name
      FROM pg_constraint
     WHERE conrelid = 'public.betfair_live_risk_rules'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%rule_type%IN%';
    IF c_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.betfair_live_risk_rules DROP CONSTRAINT %I', c_name);
    END IF;
END; $$;

ALTER TABLE public.betfair_live_risk_rules
    ADD CONSTRAINT betfair_live_risk_rules_rule_type_check
    CHECK (rule_type IN ('offset','stop_loss','take_profit','trailing_stop','bracket',
                         'stop_entry','chase','auto_hedge'));
COMMIT;

-- 2) request_live_risk_rule — validazione del nuovo tipo.
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
    v_entry_size  numeric := nullif(p->>'entry_size', '')::numeric;
    v_trigger     numeric := nullif(p->'params'->>'trigger_price', '')::numeric;
    v_direction   text := nullif(p->'params'->>'trigger_direction', '');
    v_offset      numeric := nullif(p->'params'->>'offset_ticks', '')::numeric;
    v_floor       numeric := nullif(p->'params'->>'floor', '')::numeric;
    v_event       text := nullif(p->'params'->>'event_id', '');
BEGIN
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
       OR v_rule_type NOT IN ('offset','stop_loss','take_profit','trailing_stop','bracket',
                              'stop_entry','chase','auto_hedge') THEN
        RAISE EXCEPTION 'rule_type non valido';
    END IF;
    IF v_side IS NULL OR v_side NOT IN ('back','lay') THEN
        RAISE EXCEPTION 'entry_side non valido (back|lay)';
    END IF;
    IF v_market IS NULL OR v_selection IS NULL THEN
        RAISE EXCEPTION 'market_id, selection_id obbligatori';
    END IF;
    IF v_rule_type IN ('offset','stop_loss','trailing_stop','bracket') AND v_entry_price IS NULL THEN
        RAISE EXCEPTION 'entry_price obbligatorio per %', v_rule_type;
    END IF;
    IF v_entry_price IS NOT NULL AND v_entry_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'entry_price fuori range Betfair [1.01, 1000]';
    END IF;

    -- stop_entry: serve lo stake dell'ingresso + soglia/direzione valide.
    IF v_rule_type = 'stop_entry' THEN
        IF v_entry_size IS NULL OR v_entry_size <= 0 THEN
            RAISE EXCEPTION 'stop_entry: entry_size > 0 obbligatorio';
        END IF;
        IF v_trigger IS NULL OR v_trigger NOT BETWEEN 1.01 AND 1000 THEN
            RAISE EXCEPTION 'stop_entry: params.trigger_price in [1.01, 1000] obbligatorio';
        END IF;
        IF v_direction IS NULL OR v_direction NOT IN ('at_or_above','at_or_below') THEN
            RAISE EXCEPTION 'stop_entry: params.trigger_direction non valida (at_or_above|at_or_below)';
        END IF;
    END IF;

    -- chase: serve l'ordine da inseguire + offset non negativo.
    IF v_rule_type = 'chase' THEN
        IF nullif(p->>'entry_bet_id','') IS NULL THEN
            RAISE EXCEPTION 'chase: entry_bet_id obbligatorio (ordine da inseguire)';
        END IF;
        IF v_offset IS NOT NULL AND (v_offset < 0 OR v_offset <> floor(v_offset)) THEN
            RAISE EXCEPTION 'chase: params.offset_ticks deve essere un intero >= 0';
        END IF;
    END IF;

    -- auto_hedge (F39): serve il floor (>0) e l'evento; il lato è sempre back
    -- (copertura = BACK sul Correct Score dello scoreline peggiore).
    IF v_rule_type = 'auto_hedge' THEN
        IF v_floor IS NULL OR v_floor <= 0 THEN
            RAISE EXCEPTION 'auto_hedge: params.floor > 0 obbligatorio (perdita worst-case massima tollerata)';
        END IF;
        IF v_event IS NULL THEN
            RAISE EXCEPTION 'auto_hedge: params.event_id obbligatorio';
        END IF;
        IF v_side <> 'back' THEN
            RAISE EXCEPTION 'auto_hedge: entry_side deve essere back';
        END IF;
    END IF;

    SELECT id INTO v_id FROM public.betfair_live_risk_rules WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_live_risk_rules
        (client_ref, mode, rule_type, market_id, selection_id, handicap,
         entry_side, entry_price, entry_size, entry_bet_id, params)
    VALUES (
        v_client_ref,
        v_mode,
        v_rule_type,
        v_market,
        v_selection::bigint,
        coalesce(nullif(p->>'handicap','')::numeric, 0),
        v_side,
        v_entry_price,
        v_entry_size,
        nullif(p->>'entry_bet_id',''),
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

REVOKE ALL    ON FUNCTION public.request_live_risk_rule(jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.request_live_risk_rule(jsonb) TO authenticated, service_role;
