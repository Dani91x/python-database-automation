-- ============================================================================
-- betfair_live_greenup.sql — Fase 2: azione 'greenup' (green-up / cash-out).
-- Estende la coda comandi betfair_live_order_queue.sql con una NUOVA azione:
--   action='greenup' → il worker (live_order_worker._do_greenup) legge le esposizioni
--   MATCHED fresche da flumine (blotter.get_exposures) + il best price opposto dal book,
--   calcola l'UNICO ordine di hedge (trading/greenup.compute_greenup) e lo piazza con
--   reduces_liability=True (sotto-minimo .it consentito; hedge self-bounded).
--
-- La richiesta porta SOLO market_id + selection_id (+ handicap, + params.fraction per il
-- cash-out parziale): side/price/size NON sono dati dal frontend ma DERIVATI a runtime
-- dalle esposizioni reali — così il green-up usa la matematica di flumine, non numeri
-- pollati potenzialmente stantii.
--
-- IDEMPOTENTE: DROP/ADD CONSTRAINT IF EXISTS, CREATE OR REPLACE FUNCTION.
-- Da applicare DOPO betfair_live_order_queue.sql.
-- ============================================================================

-- 1) Allarga il CHECK sull'azione per ammettere 'greenup'.
-- C1 (money-critical): NON ci affidiamo al nome auto-generato del constraint inline. Se il
-- nome reale in catalogo differisse (constraint rinominato, name-mangling di un tool), un
-- DROP IF EXISTS per nome assunto non rimuoverebbe nulla e l'ADD lascerebbe ATTIVO il vecchio
-- CHECK → ogni INSERT 'greenup' bloccato a livello DB (la RPC valida, ma l'insert fallisce):
-- green-up mai accodato, posizione esposta. Quindi troviamo il constraint PER CONTENUTO.
-- H1: tutto in UNA transazione → nessuna finestra in cui la colonna 'action' resta senza CHECK.
BEGIN;
DO $$
DECLARE
    c_name text;
BEGIN
    SELECT conname INTO c_name
      FROM pg_constraint
     WHERE conrelid = 'public.betfair_live_order_requests'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%action%IN%';
    IF c_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE public.betfair_live_order_requests DROP CONSTRAINT %I', c_name
        );
    END IF;
END;
$$;

ALTER TABLE public.betfair_live_order_requests
    ADD CONSTRAINT betfair_live_order_requests_action_check
    CHECK (action IN ('place','cancel','replace','place_submin','greenup'));
COMMIT;


-- 2) request_betfair_live_order — stessa firma/idempotenza, con il ramo di validazione
--    per 'greenup' (market_id + selection_id obbligatori; side/price/size non richiesti).
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
BEGIN
    -- OWNER-ONLY: denaro REALE in mode='live'. Nessun altro authenticated accoda.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- obbligatori comuni
    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_action IS NULL OR v_action NOT IN ('place','cancel','replace','place_submin','greenup') THEN
        RAISE EXCEPTION 'action non valida (place|cancel|replace|place_submin|greenup)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;

    -- obbligatori per azione
    IF v_action IN ('place','place_submin') THEN
        IF nullif(p->>'market_id','') IS NULL
           OR nullif(p->>'selection_id','') IS NULL
           OR nullif(p->>'side','') IS NULL
           OR v_price IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: market_id, selection_id, side, price obbligatori';
        END IF;
        -- size O liability: serve almeno uno per dimensionare l'ordine (back→size, lay→size|liability).
        IF nullif(p->>'size','') IS NULL AND nullif(p->>'liability','') IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: size o liability obbligatorio';
        END IF;
    ELSIF v_action = 'greenup' THEN
        -- green-up: side/price/size DERIVATI a runtime dalle esposizioni → bastano mercato+selezione.
        IF nullif(p->>'market_id','') IS NULL
           OR nullif(p->>'selection_id','') IS NULL THEN
            RAISE EXCEPTION 'greenup: market_id, selection_id obbligatori';
        END IF;
        -- M2: side/price/size NON ammessi per greenup (sono derivati dal worker dalle
        -- esposizioni reali). Rifiutarli evita righe ambigue e usi impropri della coda.
        IF nullif(p->>'side','') IS NOT NULL
           OR v_price IS NOT NULL
           OR nullif(p->>'size','') IS NOT NULL THEN
            RAISE EXCEPTION 'greenup: side/price/size non ammessi (derivati a runtime dal worker)';
        END IF;
        -- M1: frazione di cash-out parziale, se passata, deve stare in [0,1] (difesa in
        -- profondità: il worker la clampa comunque, ma una richiesta malformata va respinta).
        IF (p->'params'->>'fraction') IS NOT NULL
           AND (p->'params'->>'fraction')::numeric NOT BETWEEN 0.0 AND 1.0 THEN
            RAISE EXCEPTION 'greenup: params.fraction deve essere in [0.0, 1.0]';
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

    -- range Betfair (chiarezza all'accodamento, non solo al piazzamento)
    IF v_price IS NOT NULL AND v_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'price fuori range Betfair [1.01, 1000]';
    END IF;
    IF v_new_price IS NOT NULL AND v_new_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'new_price fuori range Betfair [1.01, 1000]';
    END IF;

    -- idempotenza: stesso client_ref → stessa richiesta
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
        v_client_ref,
        v_action,
        v_mode,
        nullif(p->>'market_id',''),
        nullif(p->>'selection_id','')::bigint,
        coalesce(nullif(p->>'handicap','')::numeric, 0),
        nullif(p->>'side',''),
        coalesce(nullif(p->>'order_type',''), 'LIMIT'),
        v_price,
        nullif(p->>'size','')::numeric,
        nullif(p->>'liability','')::numeric,
        coalesce(nullif(p->>'persistence',''), 'LAPSE'),
        nullif(p->>'time_in_force',''),
        nullif(p->>'min_fill_size','')::numeric,
        nullif(p->>'bet_id',''),
        v_new_price,
        nullif(p->>'size_reduction','')::numeric,
        CASE WHEN p ? 'params' THEN p->'params' ELSE NULL END
    )
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    -- se ON CONFLICT ha saltato (race tra due insert concorrenti), recupera l'id.
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
