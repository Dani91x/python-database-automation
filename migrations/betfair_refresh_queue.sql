-- ============================================================================
-- betfair_refresh_queue.sql — coda DB per "Aggiorna quote" (mediato dal database,
-- come lo stream). Permette di aggiornare le quote ANCHE dal sito online senza
-- chiamate dirette browser→PC:
--   frontend → request_betfair_refresh()  (mette una richiesta in coda)
--   worker locale (start_order_server.py) → esegue il refresh e scrive l'esito
--   frontend → get_betfair_refresh_request()  (poll fino a done/error)
-- NESSUN ordine reale: solo aggiornamento quote.
--
-- IDEMPOTENTE: CREATE TABLE/INDEX/FUNCTION IF NOT EXISTS / OR REPLACE.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_refresh_requests (
    id           BIGSERIAL PRIMARY KEY,
    fixture_id   BIGINT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','done','error')),
    result       JSONB,
    error        TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_brr_pending
    ON public.betfair_refresh_requests (id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_brr_fixture
    ON public.betfair_refresh_requests (fixture_id, requested_at DESC);

-- Solo il worker (service_role) e le RPC SECURITY DEFINER accedono alla tabella.
ALTER TABLE public.betfair_refresh_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_refresh_requests FROM anon, authenticated;

-- ============================================================================
-- request_betfair_refresh — accoda una richiesta di refresh per una fixture.
-- Anti-spam: se esiste già una richiesta 'pending' recente (<30s) per la stessa
-- fixture, ne riusa l'id invece di crearne una nuova.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_betfair_refresh(p_fixture_id bigint)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id bigint;
BEGIN
    IF p_fixture_id IS NULL THEN
        RAISE EXCEPTION 'p_fixture_id nullo';
    END IF;

    SELECT id INTO v_id
      FROM public.betfair_refresh_requests
     WHERE fixture_id = p_fixture_id
       AND status = 'pending'
       AND requested_at > now() - interval '30 seconds'
     ORDER BY id DESC
     LIMIT 1;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_refresh_requests (fixture_id)
    VALUES (p_fixture_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- ============================================================================
-- get_betfair_refresh_request — stato/esito di una richiesta (poll dal frontend).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_betfair_refresh_request(p_id bigint)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT to_jsonb(r.*) FROM public.betfair_refresh_requests r WHERE r.id = p_id;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role.
-- ============================================================================
REVOKE ALL     ON FUNCTION public.request_betfair_refresh(bigint)     FROM public;
GRANT EXECUTE  ON FUNCTION public.request_betfair_refresh(bigint)     TO authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.request_betfair_refresh(bigint)     FROM anon;

REVOKE ALL     ON FUNCTION public.get_betfair_refresh_request(bigint) FROM public;
GRANT EXECUTE  ON FUNCTION public.get_betfair_refresh_request(bigint) TO authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.get_betfair_refresh_request(bigint) FROM anon;
