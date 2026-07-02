-- ============================================================================
-- betfair_live_cashout_event_v2.sql — #7/#8: azione 'cashout_event' (cash-out
-- dell'INTERO evento, tutti i mercati) + dutching a TARGET-profit (mode=target,
-- che usa params.target_profit invece di total_stake) + modalità prezzo (in params).
--
-- IDEMPOTENTE. Drop/add CHECK per CONTENUTO. CREATE OR REPLACE della RPC.
-- Da applicare DOPO betfair_live_dutch_cashout.sql.
-- ============================================================================

-- 1) Allarga il CHECK 'action' per ammettere 'cashout_event'.
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    SELECT conname INTO c_name
      FROM pg_constraint
     WHERE conrelid = 'public.betfair_live_order_requests'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%action%IN%';
    IF c_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.betfair_live_order_requests DROP CONSTRAINT %I', c_name);
    END IF;
END; $$;

ALTER TABLE public.betfair_live_order_requests
    ADD CONSTRAINT betfair_live_order_requests_action_check
    CHECK (action IN ('place','cancel','replace','place_submin','greenup',
                      'dutch','cashout_all','cashout_event'));
COMMIT;

-- 2) request_betfair_live_order — + ramo cashout_event; dutch: total_stake NON richiesto se
--    mode='target' (allora serve params.target_profit).
CREATE OR REPLACE FUNCTION public.request_betfair_live_order(p jsonb)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id         bigint;
    v_client_ref text := nullif(p->>'client_ref', '');
    v_action     text := nullif(p->>'action', '');
    v_mode       text := nullif(p->>'mode', '');
    v_price      numeric := nullif(p->>'price', '')::numeric;
    v_new_price  numeric := nullif(p->>'new_price', '')::numeric;
    v_dmode      text := nullif(p->'params'->>'mode', '');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_action IS NULL OR v_action NOT IN
       ('place','cancel','replace','place_submin','greenup','dutch','cashout_all','cashout_event') THEN
        RAISE EXCEPTION 'action non valida';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;

    IF v_action IN ('place','place_submin') THEN
        IF nullif(p->>'market_id','') IS NULL
           OR nullif(p->>'selection_id','') IS NULL
           OR nullif(p->>'side','') IS NULL
           OR v_price IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: market_id, selection_id, side, price obbligatori';
        END IF;
        IF nullif(p->>'size','') IS NULL AND nullif(p->>'liability','') IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: size o liability obbligatorio';
        END IF;
    ELSIF v_action = 'greenup' THEN
        IF nullif(p->>'market_id','') IS NULL OR nullif(p->>'selection_id','') IS NULL THEN
            RAISE EXCEPTION 'greenup: market_id, selection_id obbligatori';
        END IF;
        IF nullif(p->>'side','') IS NOT NULL OR v_price IS NOT NULL OR nullif(p->>'size','') IS NOT NULL THEN
            RAISE EXCEPTION 'greenup: side/price/size non ammessi (derivati a runtime dal worker)';
        END IF;
        IF (p->'params'->>'fraction') IS NOT NULL
           AND (p->'params'->>'fraction')::numeric NOT BETWEEN 0.0 AND 1.0 THEN
            RAISE EXCEPTION 'greenup: params.fraction deve essere in [0.0, 1.0]';
        END IF;
    ELSIF v_action = 'dutch' THEN
        IF nullif(p->>'market_id','') IS NULL THEN
            RAISE EXCEPTION 'dutch: market_id obbligatorio';
        END IF;
        IF (p->'params'->'selections') IS NULL
           OR jsonb_typeof(p->'params'->'selections') <> 'array'
           OR jsonb_array_length(p->'params'->'selections') < 1 THEN
            RAISE EXCEPTION 'dutch: params.selections (array non vuoto) obbligatorio';
        END IF;
        -- Validazione PER GAMBA (fix review DB HIGH): una gamba senza selection_id o con
        -- prezzo invalido non deve MAI arrivare al worker — un dutch su N-1 selezioni
        -- perde l'intero stake se vince quella scartata. (Il worker rifiuta comunque le
        -- gambe senza prezzo risolvibile: questa è la barriera server-side.)
        DECLARE
            v_leg jsonb;
            v_leg_price numeric;
        BEGIN
            FOR v_leg IN SELECT jsonb_array_elements(p->'params'->'selections')
            LOOP
                IF nullif(v_leg->>'selection_id','') IS NULL THEN
                    RAISE EXCEPTION 'dutch: ogni gamba richiede selection_id';
                END IF;
                IF (v_leg->>'price') IS NOT NULL THEN
                    v_leg_price := (v_leg->>'price')::numeric;
                    IF v_leg_price NOT BETWEEN 1.01 AND 1000 THEN
                        RAISE EXCEPTION 'dutch: prezzo gamba % fuori range [1.01, 1000]',
                                        v_leg->>'selection_id';
                    END IF;
                ELSIF coalesce(nullif(p->'params'->>'pricing',''), 'as_given')
                      NOT IN ('best','in_front','nominated') THEN
                    -- pricing as_given SENZA prezzo: il worker non potrà risolverlo.
                    RAISE EXCEPTION 'dutch: gamba % senza price (pricing=as_given)',
                                    v_leg->>'selection_id';
                END IF;
            END LOOP;
        END;
        -- total_stake richiesto SALVO mode=target (che usa target_profit).
        IF v_dmode = 'target' THEN
            IF (p->'params'->>'target_profit') IS NULL
               OR (p->'params'->>'target_profit')::numeric <= 0 THEN
                RAISE EXCEPTION 'dutch mode=target: params.target_profit (>0) obbligatorio';
            END IF;
        ELSE
            IF (p->'params'->>'total_stake') IS NULL
               OR (p->'params'->>'total_stake')::numeric <= 0 THEN
                RAISE EXCEPTION 'dutch: params.total_stake (>0) obbligatorio';
            END IF;
        END IF;
        IF nullif(p->>'side','') IS NOT NULL OR v_price IS NOT NULL OR nullif(p->>'size','') IS NOT NULL THEN
            RAISE EXCEPTION 'dutch: side/price/size vanno dentro params, non al top-level';
        END IF;
    ELSIF v_action IN ('cashout_all','cashout_event') THEN
        IF nullif(p->>'market_id','') IS NULL THEN
            RAISE EXCEPTION '%: market_id obbligatorio', v_action;
        END IF;
        IF (p->'params'->>'fraction') IS NOT NULL
           AND (p->'params'->>'fraction')::numeric NOT BETWEEN 0.0 AND 1.0 THEN
            RAISE EXCEPTION '%: params.fraction deve essere in [0.0, 1.0]', v_action;
        END IF;
    ELSIF v_action = 'cancel' THEN
        IF nullif(p->>'bet_id','') IS NULL THEN
            RAISE EXCEPTION 'cancel: bet_id obbligatorio';
        END IF;
    ELSIF v_action = 'replace' THEN
        IF nullif(p->>'bet_id','') IS NULL OR v_new_price IS NULL THEN
            RAISE EXCEPTION 'replace: bet_id + new_price obbligatori';
        END IF;
    END IF;

    IF v_price IS NOT NULL AND v_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'price fuori range Betfair [1.01, 1000]';
    END IF;
    IF v_new_price IS NOT NULL AND v_new_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'new_price fuori range Betfair [1.01, 1000]';
    END IF;

    SELECT id INTO v_id
      FROM public.betfair_live_order_requests
     WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_live_order_requests
        (client_ref, action, mode, market_id, selection_id, handicap, side,
         order_type, price, size, liability, persistence, time_in_force,
         min_fill_size, bet_id, new_price, size_reduction, params)
    VALUES (
        v_client_ref, v_action, v_mode,
        nullif(p->>'market_id',''), nullif(p->>'selection_id','')::bigint,
        coalesce(nullif(p->>'handicap','')::numeric, 0), nullif(p->>'side',''),
        coalesce(nullif(p->>'order_type',''), 'LIMIT'), v_price,
        nullif(p->>'size','')::numeric, nullif(p->>'liability','')::numeric,
        coalesce(nullif(p->>'persistence',''), 'LAPSE'), nullif(p->>'time_in_force',''),
        nullif(p->>'min_fill_size','')::numeric, nullif(p->>'bet_id',''), v_new_price,
        nullif(p->>'size_reduction','')::numeric,
        CASE WHEN p ? 'params' THEN p->'params' ELSE NULL END
    )
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id
          FROM public.betfair_live_order_requests
         WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;

REVOKE ALL     ON FUNCTION public.request_betfair_live_order(jsonb) FROM public, anon;
GRANT EXECUTE  ON FUNCTION public.request_betfair_live_order(jsonb) TO authenticated, service_role;
