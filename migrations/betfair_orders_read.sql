-- ============================================================================
-- betfair_orders_read.sql — RPC di LETTURA degli ordini reali piazzati (pre-match)
-- per una fixture. Alimenta il pannello "Ordini piazzati" della watchlist: mostra
-- cosa e' stato inviato a Betfair e lo stato di abbinamento, senza dover aprire la
-- UI di Betfair. SOLO lettura: non accoda e non piazza nulla.
--
-- Legge public.betfair_order_requests (la coda ordini pre-match, "Invia Giocate").
-- OWNER-ONLY: sono dati su denaro reale. SECURITY DEFINER + SET search_path.
-- IDEMPOTENTE: CREATE OR REPLACE.
-- (Se cambi l'email owner aggiornala anche in security_lockdown.sql,
--  betfair_live_order_queue.sql e src/lib/auth-config.ts.)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_betfair_orders(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    -- OWNER-ONLY: ordini reali → nessun altro authenticated li legge.
    -- (Via PostgREST il ruolo arriva nel claim 'role' del JWT; service_role bypassa.
    --  Niente check su session_user: in PostgREST è sempre 'authenticator' → sarebbe dead code.)
    IF NOT (
        coalesce(auth.jwt() ->> 'role', '') = 'service_role'
        OR lower(coalesce(auth.jwt() ->> 'email', '')) = 'daniele.ritrovato@gmail.com'
    ) THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF p_fixture_id IS NULL OR p_fixture_id <= 0 THEN
        RAISE EXCEPTION 'p_fixture_id non valido';
    END IF;

    -- LIMIT difensivo (200): in uso normale gli ordini per fixture sono pochi; il cap
    -- evita payload enormi in casi anomali. jsonb_agg su sotto-query già ordinata+limitata.
    SELECT coalesce(jsonb_agg(sub.j ORDER BY sub.ord DESC), '[]'::jsonb)
    INTO v_rows
    FROM (
        SELECT
            r.id AS ord,
            jsonb_build_object(
                'id',           r.id,
                'market',       r.market,
                'selection',    r.selection,
                'side',         r.side,
                'price',        r.price,
                'size',         r.size,
                'liability',    r.liability,
                'persistence',  r.persistence,
                'fill_or_kill', r.fill_or_kill,
                'status',       r.status,
                'result',       r.result,
                'error',        r.error,
                'requested_at', r.requested_at,
                'processed_at', r.processed_at
            ) AS j
        FROM public.betfair_order_requests r
        WHERE r.fixture_id = p_fixture_id
        ORDER BY r.id DESC
        LIMIT 200
    ) sub;

    RETURN v_rows;
END;
$$;

REVOKE ALL    ON FUNCTION public.get_betfair_orders(bigint) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_betfair_orders(bigint) TO authenticated, service_role;
