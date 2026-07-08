-- ============================================================================
-- betfair_live_risk_rules_v3.sql — Risk engine v3 (roadmap C23/C25).
-- Nuovi rule_type:
--   * ``stop_entry`` → ordine CONDIZIONALE: entra (place) solo quando l'LTP tocca
--     params.trigger_price nella direzione params.trigger_direction
--     (at_or_above|at_or_below). Richiede entry_size (lo stake dell'ingresso);
--     entry_price NON serve (il riferimento è la soglia, non un fill).
--   * ``chase`` → tick-offset sul re-quote: insegue il best re-quotando l'ordine
--     NON abbinato (cancel→place, mai replace singolo) a params.offset_ticks dal
--     best del proprio lato. Richiede entry_bet_id (l'ordine da inseguire).
--
-- IDEMPOTENTE. Da applicare DOPO betfair_live_risk_rules_v2.sql.
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
                         'stop_entry','chase'));
COMMIT;

-- 2) request_live_risk_rule — validazione dei nuovi tipi.
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
                              'stop_entry','chase') THEN
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
