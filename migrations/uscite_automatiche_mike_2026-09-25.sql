-- ============================================================================
-- 25/09/2026 - MIKE: INTERRUTTORE "USCITE AUTOMATICHE" + APPROVAZIONE DI UN'USCITA
-- ============================================================================
-- Ordine dell'utente: «Tutti i bot (in live e in paper) DEVONO AVERE
-- L'ABILITAZIONE per le uscite automatiche [...]; se disattivo il pulsante
-- (TUTTO IN UI PER SINGOLO BOT) le uscite le gestisco io manualmente tramite
-- l'apposita scheda».
--
-- L'interruttore e' la chiave `uscite_automatiche` dentro mike_control.params
-- (default nel codice: true = comportamento di OGGI; nessun dato da toccare:
-- finche' la chiave non c'e' Mike esce da solo come sempre).
-- Con l'interruttore spento l'uscita che il motore vorrebbe fare diventa una
-- PROPOSTA nel contesto della partita (mike_events.ctx.uscita_proposta, gia'
-- esistente come JSONB: nessuna colonna nuova). L'utente la APPROVA con una
-- richiesta nuova 'approva_uscita' nella coda di sempre (mike_requests), con
-- payload {event_id, chiave, contesto:{prezzo_visto, eta_ms, fonte}}.
--
-- ADDITIVA e IDEMPOTENTE: si allarga il CHECK di `kind` e la RPC accetta il
-- kind nuovo (richiede la `chiave`). Nessun kind esistente cambia.
-- Ordine di applicazione: dopo mike_bot.sql e mike_bot_v2.sql (gia' applicate).
-- ============================================================================

BEGIN;

-- il CHECK di `kind` nato con mike_bot.sql ha il nome di default
-- (mike_requests_kind_check); per prudenza si tolgono TUTTI i CHECK su `kind`,
-- qualunque nome abbiano, prima di rimettere quello allargato.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint
              WHERE conrelid = 'public.mike_requests'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) ILIKE '%kind%'
    LOOP
        EXECUTE format('ALTER TABLE public.mike_requests DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;
ALTER TABLE public.mike_requests
    ADD CONSTRAINT mike_requests_kind_check
    CHECK (kind IN ('cashout','flatten','skip_event','resume_event','cancel','approva_uscita'));

CREATE OR REPLACE FUNCTION public.mike_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id      bigint;
    v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('cashout','flatten','skip_event','resume_event','cancel','approva_uscita') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;
    IF coalesce(v_payload->>'event_id','') = '' THEN
        RAISE EXCEPTION 'payload senza event_id';
    END IF;
    -- 25/09: un'approvazione senza la chiave della proposta non si scrive
    -- (il servizio approverebbe "qualcosa" al buio).
    IF p_kind = 'approva_uscita' AND coalesce(v_payload->>'chiave','') = '' THEN
        RAISE EXCEPTION 'approva_uscita senza chiave della proposta';
    END IF;
    INSERT INTO public.mike_requests (kind, payload) VALUES (p_kind, v_payload) RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.mike_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.mike_request(text,jsonb) TO authenticated, service_role;

COMMIT;

-- Verifica (sola lettura):
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid = 'public.mike_requests'::regclass AND contype = 'c';
