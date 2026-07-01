-- ============================================================================
-- betfair_live_risk_rules_v2.sql — Risk engine v2 (punti #2/#3/#4/#6).
-- Estende betfair_live_risk_rules con:
--   * colonna ``entry_bet_id`` → l'ordine d'INGRESSO da osservare (timing on-fill /
--     anti-gamba-nuda: l'offset si piazza SOLO quando l'ingresso si abbina; se l'ingresso
--     lapsa senza match, niente offset orfano);
--   * rule_type ``bracket`` → offset (take-profit) + stop insieme, con logica OCO
--     (one-cancels-other): chi scatta per primo chiude e cancella l'altro.
-- I nuovi parametri (timing, greening, place_at_ticks, on_inplay, stop/trigger) vivono in
-- ``params`` (jsonb) — nessuna colonna nuova oltre entry_bet_id.
--
-- IDEMPOTENTE. Da applicare DOPO betfair_live_risk_rules.sql.
-- ============================================================================

-- 1) nuova colonna (l'ordine d'ingresso osservato per on-fill / anti-gamba-nuda).
ALTER TABLE public.betfair_live_risk_rules
    ADD COLUMN IF NOT EXISTS entry_bet_id TEXT;

-- 2) allarga il CHECK rule_type per ammettere 'bracket' (trova il constraint per CONTENUTO).
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
    CHECK (rule_type IN ('offset','stop_loss','take_profit','trailing_stop','bracket'));
COMMIT;

-- 3) request_live_risk_rule — accetta 'bracket' + entry_bet_id. entry_price obbligatorio
--    per le regole tick-based (offset/stop_loss/trailing_stop/bracket).
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
       OR v_rule_type NOT IN ('offset','stop_loss','take_profit','trailing_stop','bracket') THEN
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
        nullif(p->>'entry_size','')::numeric,
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
