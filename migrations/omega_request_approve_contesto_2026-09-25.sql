-- ============================================================================
-- OMEGA - IL PREZZO VISTO AL CLIC SULL'USCITA PROPOSTA  (25/09/2026, B17)
--
-- Ordine dell'utente (25/09, punto 14): "una volta che clicco, devo sapere a
-- che prezzo e' stato abbinato il mio ordine rispetto al segnale". Per la Safe
-- il prezzo visto e il suo contesto arrivano gia' nel payload della richiesta
-- (`safe_request_approve_contesto_2026-09-24.sql`); per Omega no: la scheda
-- "Omega - uscita" mandava solo `p_id`.
--
-- Aggiunge a `omega_request_approve` DUE parametri OPZIONALI (DEFAULT NULL):
--   p_price     numeric - il prezzo di BACK a video al clic
--   p_contesto  jsonb   - eta', fonte, `prezzo_vivo_assente`, istante del clic
--                          e `prezzo_segnale` (il back della proposta)
-- scritti nel payload come `price_visto`, `price_visto_at`,
-- `prezzo_visto_ctx`. Chi chiama col solo `p_id` ottiene ESATTAMENTE il
-- comportamento di prima. Il frontend ripiega da solo se questa migrazione non
-- e' applicata (PGRST202 -> chiamata col solo `p_id`).
--
-- NESSUN EFFETTO SULL'ESECUZIONE: il servizio Omega (`_manual_cashout`)
-- continua a chiudere a mercato come oggi. Se l'uscita debba rispettare il
-- prezzo visto (tolleranza, come la Safe sulle aperture) e' la decisione B17
-- ancora aperta dell'utente: qui si SALVA soltanto, per l'audit e per il
-- confronto a video (differenza in tick fra medio abbinato, prezzo visto e segnale).
--
-- ORDINE DI APPLICAZIONE: DOPO `omega_proposte_coda_unica_2026-09-17.sql` e
-- `sicurezza_db_2026-09-24_BLOCCO_3_revoke_anon.sql`.
-- IDEMPOTENTE (DROP + CREATE: una sola versione della funzione).
-- ============================================================================

DROP FUNCTION IF EXISTS public.omega_request_approve(bigint);
DROP FUNCTION IF EXISTS public.omega_request_approve(bigint, numeric, jsonb);

CREATE FUNCTION public.omega_request_approve(
    p_id bigint,
    p_price numeric DEFAULT NULL,
    p_contesto jsonb DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.omega_manual_requests%ROWTYPE;
    v_extra jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- FOR UPDATE: approvare e' un atto sui soldi, si prende il lock
    SELECT * INTO v_row FROM public.omega_manual_requests WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non e'' piu'' in attesa di approvazione');
    END IF;

    -- il payload si CONSERVA e si AGGIUNGE la firma (difetto 27 del catalogo)
    v_extra := jsonb_build_object(
        'approved_at', to_char(now() AT TIME ZONE 'utc',
                               'YYYY-MM-DD"T"HH24:MI:SS"Z"'));
    IF p_price IS NOT NULL THEN
        v_extra := v_extra || jsonb_build_object(
            'price_visto', p_price,
            'price_visto_at', to_char(now() AT TIME ZONE 'utc',
                                      'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'));
    END IF;
    IF p_contesto IS NOT NULL AND jsonb_typeof(p_contesto) = 'object' THEN
        v_extra := v_extra || jsonb_build_object('prezzo_visto_ctx', p_contesto);
    END IF;

    UPDATE public.omega_manual_requests
       SET status = 'pending',
           payload = v_row.payload || v_extra,
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'pending');
END;
$$;

-- stessi permessi della versione di prima (BLOCCO 3: niente anon)
REVOKE ALL ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) FROM anon;
GRANT EXECUTE ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) TO authenticated;
