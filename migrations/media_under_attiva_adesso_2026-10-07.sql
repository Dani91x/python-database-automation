-- ============================================================================
-- 07/10/2026 - MEDIA UNDER DELLO SCALPER: IL PULSANTE <<ATTIVA ADESSO>>
-- ============================================================================
-- Ordine dell'utente (07/10): <<voglio un pulsante che quando cliccato, sia in
-- paper che in live, attiva immediatamente il bot e lo fa lavorare come
-- progettato, sia in pre-match che in live>>.
--
-- Il clic e' un COMANDO con un id unico. Arriva alla sessione dello scalper per
-- la STESSA strada dei parametri: la chiave `media_attiva_adesso` dentro
-- scalper_control.params (JSONB gia' esistente), che la sessione rilegge a ogni
-- battito (scalper_session.consegna_comando_media). La sessione consuma l'id una
-- sola volta e lo registra nelle stats della riga PRIMA di eseguirlo: un
-- riavvio non riesegue mai lo stesso clic.
--
-- * Sessione FERMA: il pulsante usa la RPC di sempre `scalper_activate` coi
--   params della modalita' + `media_a_clic: true` + il comando (nessuna
--   migrazione serve per questo).
-- * Sessione ACCESA: questa RPC owner-only scrive il comando nella riga attiva
--   della partita (solo se la Media Under e' accesa), con l'istante del server.
--
-- ADDITIVA e IDEMPOTENTE. Nessuna colonna nuova, nessun dato toccato.
-- Ordine di applicazione: dopo scalper_bot.sql, scalper_auto_mode_2026-09-25.sql
-- e uscite_approva_bot_flusso_2026-09-28.sql (gia' applicate).
-- NON applicata dal delegato: la applica l'utente.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.scalper_media_attiva_adesso(
    p_event_id text, p_id text
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.scalper_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF coalesce(btrim(p_id), '') = '' OR length(p_id) > 64 THEN
        RAISE EXCEPTION 'p_id obbligatorio (l''id del clic, al piu'' 64 caratteri)';
    END IF;
    UPDATE public.scalper_control AS c
       SET params = coalesce(c.params, '{}'::jsonb)
                    || jsonb_build_object('media_attiva_adesso',
                                          jsonb_build_object('id', btrim(p_id),
                                                             'ts', to_jsonb(now()))),
           updated_at = now()
     WHERE c.event_id = p_event_id
       AND c.status IN ('requested', 'arming', 'armed', 'running')
       AND coalesce(c.params ->> 'media_mode', 'false') = 'true'
    RETURNING * INTO v_row;
    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'nessuna sessione Media Under attiva sulla partita %', p_event_id;
    END IF;
    RETURN to_json(v_row);
END;
$$;

REVOKE ALL    ON FUNCTION public.scalper_media_attiva_adesso(text, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_media_attiva_adesso(text, text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- Verifica (facoltativa, sola lettura):
--   SELECT proname FROM pg_proc WHERE proname = 'scalper_media_attiva_adesso';
--   SELECT event_id, status, params -> 'media_attiva_adesso', stats -> 'media_comando'
--     FROM public.scalper_control WHERE params ->> 'media_mode' = 'true';
-- ============================================================================
