-- segui_live_apri_partita_2026-10-06.sql
--
-- Segui Live: "clicco una partita e non si carica nulla" (06/10).
-- Le partite che il runner segue DA SOLO per i bot (`live_follow.origine =
-- 'auto'`, status STREAMING) compaiono nella lista di Segui Live ma sono
-- "silenziose" per progetto (`Betfair/stream/auto_follow.py`): niente
-- `live_now`, quindi niente ladder. Il runner prevede che "un clic dell'utente
-- la porta a PENDING e torna un follow manuale" (`runner._nuovi_follow_manuali`),
-- ma il clic nella pagina non scriveva niente: l'attesa non finiva mai.
--
-- `segui_live_apri_partita(p_event_id)`: promuove la riga AUTOMATICA a follow
-- MANUALE (origine 'manuale', status PENDING): il runner la cataloga e la
-- aggancia (dal 06/10 a caldo, senza ricostruire lo stream) e scrive il ladder.
-- Una riga gia' manuale NON si tocca (nessun effetto: idempotente). Owner-only,
-- come `set_follow_record`. La applica l'utente.

CREATE OR REPLACE FUNCTION public.segui_live_apri_partita(
    p_event_id text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.live_follow;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) = 0 OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;

    UPDATE public.live_follow SET
        origine    = 'manuale',
        status     = 'PENDING',
        updated_at = now()
    WHERE event_id = p_event_id
      AND origine = 'auto'
      AND status IN ('STREAMING', 'PENDING', 'CLOSED')
    RETURNING * INTO v_row;

    IF v_row.event_id IS NULL THEN
        -- gia' manuale (o inesistente): niente da fare, si torna la riga com'e'
        SELECT * INTO v_row FROM public.live_follow WHERE event_id = p_event_id;
        RETURN jsonb_build_object('promossa', false, 'follow', to_jsonb(v_row));
    END IF;
    RETURN jsonb_build_object('promossa', true, 'follow', to_jsonb(v_row));
END;
$$;
REVOKE ALL    ON FUNCTION public.segui_live_apri_partita(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.segui_live_apri_partita(text) TO authenticated, service_role;
