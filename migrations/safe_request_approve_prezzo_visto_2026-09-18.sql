-- ============================================================================
-- SAFE STRATEGY — PIAZZA MANDA IL PREZZO CHE L'UTENTE VEDE  (18/09/2026)
--
-- Ordine dell'utente: «il prezzo può muoversi, io devo vedere la tab
-- aggiornata e quando clicco prendiamo QUEL NUMERO CHE VEDO.»
--
-- OGGI `safe_request_approve(p_id bigint)` accetta SOLO l'id: approva la
-- proposta al prezzo CONGELATO nel payload al momento della proposta (la
-- fotografia), non al prezzo che l'utente sta guardando nell'istante del
-- clic. Questa migrazione aggiunge TRE parametri OPZIONALI, con DEFAULT
-- NULL: chi chiama con il solo `p_id` (come fa OGGI ogni client) ottiene
-- ESATTAMENTE il comportamento di ieri. Il codice Python (bot_service.py,
-- _request_place/_request_place_combo) legge questi campi SOLO se presenti
-- nel payload — funziona IDENTICO prima e dopo che questa migrazione venga
-- applicata: prima dell'applicazione la RPC vecchia (un solo parametro)
-- risponde come sempre, il codice Python semplicemente non trova mai
-- `price_visto` nel payload e usa il prezzo congelato di sempre.
--
-- NESSUNA VALIDAZIONE DI MERITO qui dentro (prezzo finito, eta' del clic,
-- tolleranza): quella vive in Python, che e' la fonte di verita' per tutto
-- cio' che decide se un ordine parte. Questa funzione scrive soltanto cio'
-- che le viene detto, cosi' come faceva gia' per `approved_at`.
--
-- IDEMPOTENTE: si puo' rieseguire. Il DROP+CREATE e' l'unico modo per
-- aggiungere parametri a una funzione gia' esistente restando con UNA sola
-- versione della funzione (senza, PostgreSQL creerebbe un OVERLOAD in più,
-- e le due firme convivrebbero invece che la nuova sostituire la vecchia).
-- ============================================================================

DROP FUNCTION IF EXISTS public.safe_request_approve(bigint);

CREATE FUNCTION public.safe_request_approve(
    p_id bigint,
    p_price numeric DEFAULT NULL,
    p_legs_prices jsonb DEFAULT NULL,
    p_slippage_pct numeric DEFAULT NULL
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

    -- FOR UPDATE: fra la lettura e la scrittura il servizio potrebbe aver
    -- aggiornato la proposta col prezzo nuovo. Approvare è un atto sui soldi:
    -- si prende il lock, non si spera.
    SELECT * INTO v_row FROM public.safe_strategy_requests
        WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        -- non è un errore del chiamante: è una corsa fra due schede aperte, o
        -- l'utente che preme due volte. Si dichiara cosa è successo.
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non è più in attesa di approvazione');
    END IF;

    v_extra := jsonb_build_object(
        'approved_at', to_char(now() AT TIME ZONE 'utc',
                               'YYYY-MM-DD"T"HH24:MI:SS"Z"'));
    -- 18/09 — il prezzo (e l'istante) che l'utente VEDEVA quando ha cliccato.
    -- Scritti SOLO se il chiamante li manda: un client vecchio (solo p_id)
    -- non li tocca, e il payload resta quello di ieri.
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

    UPDATE public.safe_strategy_requests
       SET status = 'pending',
           payload = v_row.payload || v_extra,
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'pending');
END;
$$;

REVOKE ALL ON FUNCTION public.safe_request_approve(bigint, numeric, jsonb, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.safe_request_approve(bigint, numeric, jsonb, numeric) TO authenticated;
