-- ============================================================================
-- SAFE STRATEGY — CANCELLETTO DI APPROVAZIONE SULLE CHIUSURE  (14/09/2026)
--
-- Ordine dell'utente: «IL BOT TENNIS (SOLO LUI PER ORA) PUÒ INSERIRE GLI ORDINI
-- AUTOMATICI MA LE CHIUSURE MI DEVONO ESSERE SEGNALATE IN CONTROL ROOM E LE
-- APPROVO IO.»
--
-- UN SOLO stato nuovo: 'proposed'. Niente tabelle nuove, niente kind nuovi.
-- Il perno è che il servizio drena SOLO 'pending' (`bot_db.pending_requests`
-- filtra su status='pending'): quindi una riga 'proposed' resta ferma finché
-- un essere umano non la promuove. È questo, e solo questo, a fare il
-- cancelletto — se un domani qualcuno allargasse quel filtro, il cancelletto
-- sparirebbe in silenzio.
--
-- IDEMPOTENTE: si può rieseguire.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Lo stato 'proposed'
-- ----------------------------------------------------------------------------
ALTER TABLE public.safe_strategy_requests
    DROP CONSTRAINT IF EXISTS safe_strategy_requests_status_check;
ALTER TABLE public.safe_strategy_requests
    ADD CONSTRAINT safe_strategy_requests_status_check
    CHECK (status IN ('proposed','pending','processing','done','rejected','error'));

-- Una sola proposta VIVA per trade: al ciclo dopo il servizio AGGIORNA la riga
-- (prezzo, liquidità, motivo) invece di crearne una seconda. Senza questo
-- indice un servizio riavviato a metà ciclo potrebbe scriverne due, e la
-- Control Room mostrerebbe due pulsanti APPROVA per la stessa posizione.
CREATE UNIQUE INDEX IF NOT EXISTS uq_safe_requests_proposta_viva
    ON public.safe_strategy_requests (((payload->>'trade_id')))
    WHERE status = 'proposed';

CREATE INDEX IF NOT EXISTS idx_safe_requests_proposed
    ON public.safe_strategy_requests (created_at DESC)
    WHERE status = 'proposed';

-- ----------------------------------------------------------------------------
-- 2. APPROVA: proposed → pending
--    Da qui in poi il percorso è quello di sempre, invariato: il servizio la
--    drena come qualunque richiesta manuale della UI.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_request_approve(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.safe_strategy_requests%ROWTYPE;
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

    UPDATE public.safe_strategy_requests
       SET status = 'pending',
           payload = v_row.payload || jsonb_build_object(
               'approved_at', to_char(now() AT TIME ZONE 'utc',
                                      'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'pending');
END;
$$;

-- ----------------------------------------------------------------------------
-- 3. IGNORA: proposed → rejected, con il motivo
--    Non è «non chiudere mai»: se al ciclo successivo la condizione di uscita
--    regge ancora, il servizio propone di nuovo. «Torna alla prossima
--    occasione», come deciso dall'utente.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_request_ignore(p_id bigint,
                                                      p_reason text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.safe_strategy_requests%ROWTYPE;
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

    UPDATE public.safe_strategy_requests
       SET status = 'rejected',
           result = coalesce(v_row.result, '{}'::jsonb) || jsonb_build_object(
               'ignorata_dall_utente', true,
               'motivo', coalesce(nullif(btrim(p_reason), ''), 'nessun motivo indicato')),
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'rejected');
END;
$$;

REVOKE ALL ON FUNCTION public.safe_request_approve(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.safe_request_ignore(bigint, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.safe_request_approve(bigint) TO authenticated;
GRANT EXECUTE ON FUNCTION public.safe_request_ignore(bigint, text) TO authenticated;

-- ----------------------------------------------------------------------------
-- 4. PROMEMORIA DI COSA *NON* È CAMBIATO, perché è la parte che regge tutto
--
--  · `safe_request(p_kind, p_payload)` non è toccata: le richieste manuali
--    della UI continuano a nascere 'pending' ed essere eseguite subito.
--  · Il servizio non drena 'proposed': `pending_requests` filtra su 'pending'.
--  · Le APERTURE non passano di qui. L'ordine dell'utente riguarda SOLO le
--    chiusure, e solo quelle del tennis.
--  · Nessun freno (fermo macchina, cap, kill-switch) può rendere una proposta
--    di chiusura non approvabile: quelli valgono sulle aperture. Chi ha una
--    posizione aperta deve sempre poterla chiudere.
-- ----------------------------------------------------------------------------
