-- ============================================================================
-- betfair_order_queue.sql — coda DB per PIAZZARE ORDINI REALI (mediato dal DB,
-- come lo stream). Permette "Invia Giocate" ANCHE dal sito online senza chiamate
-- dirette browser→PC:
--   frontend → request_betfair_order(p)   (mette l'ordine in coda, idempotente)
--   worker locale (start_order_server.py) → CLAIM atomico → place_order REALE
--   frontend → get_betfair_order_request() (poll fino a done/error)
--
-- MONEY-CRITICAL (soldi veri). Garanzie anti-doppio-ordine:
--  * client_ref UNIQUE → la stessa richiesta del frontend non crea due righe
--    (enqueue idempotente, retry sicuro su glitch di rete).
--  * il worker fa CLAIM atomico (pending→processing) → una sola esecuzione per riga.
--  * il worker usa un customerRef Betfair deterministico (awlq<id>) → de-dup 60s.
--
-- IDEMPOTENTE: CREATE TABLE/INDEX/FUNCTION IF NOT EXISTS / OR REPLACE.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_order_requests (
    id            BIGSERIAL PRIMARY KEY,
    client_ref    TEXT NOT NULL UNIQUE,           -- idempotency key dal frontend
    fixture_id    BIGINT NOT NULL,
    market        TEXT NOT NULL,
    selection     TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('back','lay')),
    price         NUMERIC NOT NULL,
    size          NUMERIC,
    liability     NUMERIC,
    persistence   TEXT NOT NULL DEFAULT 'LAPSE'
                     CHECK (persistence IN ('LAPSE','PERSIST','MARKET_ON_CLOSE')),
    fill_or_kill  BOOLEAN NOT NULL DEFAULT false,
    min_fill_size NUMERIC,
    max_stake     NUMERIC NOT NULL,               -- cap obbligatorio (tripwire)
    status        TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','processing','done','error')),
    result        JSONB,
    error         TEXT,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bor_pending
    ON public.betfair_order_requests (id) WHERE status = 'pending';

ALTER TABLE public.betfair_order_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_order_requests FROM anon, authenticated;

-- ============================================================================
-- request_betfair_order — accoda UN ordine. Idempotente su client_ref: se la
-- stessa richiesta è già in coda, ne ritorna l'id senza crearne un'altra.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_betfair_order(p jsonb)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id         bigint;
    v_client_ref text := nullif(p->>'client_ref', '');
BEGIN
    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF (p->>'fixture_id') IS NULL THEN
        RAISE EXCEPTION 'fixture_id obbligatorio';
    END IF;
    IF nullif(p->>'market','') IS NULL OR nullif(p->>'selection','') IS NULL
       OR nullif(p->>'side','') IS NULL THEN
        RAISE EXCEPTION 'market/selection/side obbligatori';
    END IF;
    IF (p->>'price') IS NULL THEN
        RAISE EXCEPTION 'price obbligatorio';
    END IF;
    IF (p->>'max_stake') IS NULL THEN
        RAISE EXCEPTION 'max_stake obbligatorio';
    END IF;
    -- range check (chiarezza all'accodamento, non solo al piazzamento):
    IF (p->>'max_stake')::numeric <= 0 THEN
        RAISE EXCEPTION 'max_stake deve essere positivo';
    END IF;
    IF (p->>'price')::numeric NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'price fuori range Betfair [1.01, 1000]';
    END IF;

    -- idempotenza: stesso client_ref → stessa richiesta
    SELECT id INTO v_id FROM public.betfair_order_requests WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_order_requests
        (client_ref, fixture_id, market, selection, side, price, size, liability,
         persistence, fill_or_kill, min_fill_size, max_stake)
    VALUES (
        v_client_ref,
        (p->>'fixture_id')::bigint,
        p->>'market', p->>'selection', p->>'side',
        (p->>'price')::numeric,
        nullif(p->>'size','')::numeric,
        nullif(p->>'liability','')::numeric,
        coalesce(nullif(p->>'persistence',''), 'LAPSE'),
        coalesce((p->>'fill_or_kill')::boolean, false),
        nullif(p->>'min_fill_size','')::numeric,
        (p->>'max_stake')::numeric
    )
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    -- se ON CONFLICT ha saltato (race tra due insert concorrenti), recupera l'id.
    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM public.betfair_order_requests WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;

-- ============================================================================
-- get_betfair_order_request — stato/esito di un ordine in coda (poll dal frontend).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_betfair_order_request(p_id bigint)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT to_jsonb(r.*) FROM public.betfair_order_requests r WHERE r.id = p_id;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role.
-- ============================================================================
REVOKE ALL     ON FUNCTION public.request_betfair_order(jsonb)     FROM public;
GRANT EXECUTE  ON FUNCTION public.request_betfair_order(jsonb)     TO authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.request_betfair_order(jsonb)     FROM anon;

REVOKE ALL     ON FUNCTION public.get_betfair_order_request(bigint) FROM public;
GRANT EXECUTE  ON FUNCTION public.get_betfair_order_request(bigint) TO authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.get_betfair_order_request(bigint) FROM anon;
