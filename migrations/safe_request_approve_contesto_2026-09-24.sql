-- ============================================================================
-- SAFE STRATEGY - IL CONTESTO DEL PREZZO VISTO AL CLIC  (24/09/2026)
--
-- Ordine dell'utente (visto a video il 24/09): «una scheda che ricalcola al ms
-- tutto MA NON BLOCCA L'ENTRATA: me lo segnala e decido io». La scheda non
-- rifiuta piu' nessun clic: se a video non c'e' un prezzo vivo manda l'ULTIMO
-- prezzo noto. Il servizio deve sapere COSA ha visto l'utente: l'eta' del
-- prezzo, la fonte (canale al ms / DB / feed dello scanner / proposta) e se il
-- prezzo vivo era assente.
--
-- Aggiunge a `safe_request_approve` UN parametro OPZIONALE `p_contesto jsonb`
-- (DEFAULT NULL), scritto nel payload come `prezzo_visto_ctx`. Chi chiama coi
-- parametri di ieri (18/09) o col solo `p_id` ottiene ESATTAMENTE il
-- comportamento di prima. Il frontend ripiega da solo se questa migrazione non
-- e' applicata (PGRST202 -> chiamata senza `p_contesto`).
--
-- NESSUNA VALIDAZIONE DI MERITO qui dentro: la tolleranza fra prezzo visto e
-- mercato vive in Python (`bot_service._request_place`).
--
-- ORDINE DI APPLICAZIONE: DOPO `safe_request_approve_prezzo_visto_2026-09-18.sql`.
-- IDEMPOTENTE (DROP + CREATE: una sola versione della funzione).
-- ============================================================================

DROP FUNCTION IF EXISTS public.safe_request_approve(bigint);
DROP FUNCTION IF EXISTS public.safe_request_approve(bigint, numeric, jsonb, numeric);
DROP FUNCTION IF EXISTS public.safe_request_approve(bigint, numeric, jsonb, numeric, jsonb);

CREATE FUNCTION public.safe_request_approve(
    p_id bigint,
    p_price numeric DEFAULT NULL,
    p_legs_prices jsonb DEFAULT NULL,
    p_slippage_pct numeric DEFAULT NULL,
    p_contesto jsonb DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.safe_strategy_requests%ROWTYPE;
    v_extra jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT * INTO v_row FROM public.safe_strategy_requests
        WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non è più in attesa di approvazione');
    END IF;

    v_extra := jsonb_build_object(
        'approved_at', to_char(now() AT TIME ZONE 'utc',
                               'YYYY-MM-DD"T"HH24:MI:SS"Z"'));
    IF p_price IS NOT NULL OR p_legs_prices IS NOT NULL THEN
        v_extra := v_extra || jsonb_build_object(
            'price_visto_at', to_char(now() AT TIME ZONE 'utc',
                                      'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'));
    END IF;
    IF p_price IS NOT NULL THEN
        v_extra := v_extra || jsonb_build_object('price_visto', p_price);
    END IF;
    IF p_legs_prices IS NOT NULL THEN
        v_extra := v_extra || jsonb_build_object('legs_prices_visti', p_legs_prices);
    END IF;
    IF p_slippage_pct IS NOT NULL THEN
        v_extra := v_extra || jsonb_build_object('slippage_pct', p_slippage_pct);
    END IF;
    -- 24/09 - eta', fonte e `prezzo_vivo_assente` del prezzo visto (solo se mandati)
    IF p_contesto IS NOT NULL AND jsonb_typeof(p_contesto) = 'object' THEN
        v_extra := v_extra || jsonb_build_object('prezzo_visto_ctx', p_contesto);
    END IF;

    UPDATE public.safe_strategy_requests
       SET status = 'pending',
           payload = v_row.payload || v_extra,
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'pending');
END;
$$;

REVOKE ALL ON FUNCTION public.safe_request_approve(bigint, numeric, jsonb, numeric, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.safe_request_approve(bigint, numeric, jsonb, numeric, jsonb) FROM anon;
GRANT EXECUTE ON FUNCTION public.safe_request_approve(bigint, numeric, jsonb, numeric, jsonb) TO authenticated;
