-- ============================================================================
-- 25/09/2026 - SCALPER CALCIO: INTERRUTTORE "USCITE AUTOMATICHE" DALLA CONTROL ROOM
-- ============================================================================
-- Ordine dell'utente: «Tutti i bot (in live e in paper) DEVONO AVERE
-- L'ABILITAZIONE per le uscite automatiche [...]; se disattivo il pulsante
-- (TUTTO IN UI PER SINGOLO BOT) le uscite le gestisco io manualmente».
--
-- Lo scalper si arma PER PARTITA (una riga scalper_control per evento): non
-- ha una riga di servizio. L'interruttore e' la chiave `uscite_automatiche`
-- dentro scalper_control.params (colonna JSONB gia' esistente; la sessione la
-- accetta dalla whitelist UI e la RILEGGE a caldo a ogni battito di 5 s,
-- scalper_session.applica_uscite_automatiche). Chiave assente = true =
-- comportamento di OGGI: nessun dato da toccare.
--
-- Questa migrazione aggiunge SOLO la RPC owner-only che la Control Room usa
-- per scrivere la scelta su TUTTE le sessioni attive in un colpo (le righe
-- ferme non si toccano). ADDITIVA e IDEMPOTENTE. Nessuna colonna nuova.
-- Ordine di applicazione: dopo scalper_bot.sql e
-- scalper_control_room_2026-09-24.sql (gia' applicate).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.scalper_uscite_automatiche(p_automatiche boolean)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_n integer;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_automatiche IS NULL THEN
        RAISE EXCEPTION 'p_automatiche non dichiarato (true|false)';
    END IF;
    UPDATE public.scalper_control
       SET params = coalesce(params, '{}'::jsonb)
                    || jsonb_build_object('uscite_automatiche', p_automatiche),
           updated_at = now()
     WHERE status IN ('requested', 'arming', 'armed', 'running');
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_uscite_automatiche(boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_uscite_automatiche(boolean) TO authenticated, service_role;

-- Verifica (sola lettura):
--   SELECT event_id, status, params->'uscite_automatiche' FROM public.scalper_control
--    WHERE status IN ('requested','arming','armed','running');
