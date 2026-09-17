-- ============================================================================
-- OMEGA V3 — LE USCITE DIVENTANO PROPOSTE CHE APPROVA L'UTENTE  (16/09/2026)
--
-- Ordine dell'utente (16/09 sera): «il green-up/cash-out passa dalla Control
-- Room come proposta con avviso e decide l'utente; nessuna chiusura automatica».
--
-- NON E' UNA TABELLA NUOVA. Il modello e' quello gia' vivo e certificato della
-- Safe Strategy (`migrations/safe_strategy_proposed_2026-09-14.sql`): UN SOLO
-- stato nuovo, 'proposed', su una coda di richieste che esiste gia'. Il perno e'
-- che il servizio drena SOLO 'pending': una riga 'proposed' resta ferma finche'
-- un essere umano non la promuove. E' questo, e solo questo, a fare il
-- cancelletto — se un domani qualcuno allargasse quel filtro, il cancelletto
-- sparirebbe in silenzio, e per questo il controllo G1 della certificazione lo
-- verifica a ogni giro.
--
-- MEMORIA CHE QUESTA MIGRAZIONE SERVE A ONORARE (12/09): tutte e cinque le
-- chiusure automatiche di Omega v2 erano sbagliate (-42,39 EUR contro +79,95 EUR
-- fatti dalle aperture). Su un lay la liability e' GIA' impegnata: chiudere non
-- riduce il rischio preso, lo trasforma in perdita certa. Da qui in poi quella
-- decisione la prende una persona, con i numeri davanti.
--
-- IDEMPOTENTE: si puo' rieseguire.
-- DA APPLICARE DALL'UTENTE. Non e' stata applicata.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. La coda delle richieste di Omega, se non esiste gia'.
--    Stessa forma di `safe_strategy_requests`: kind + payload + status.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.omega_requests (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT        NOT NULL,
    payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    result      JSONB,
    status      TEXT        NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- RLS come tutte le tabelle sorelle Safe (`safe_strategy_control`,
-- `safe_strategy_trades`, `safe_strategy_activity`, `safe_strategy_requests`,
-- `safe_strategy_opportunities` in `safe_strategy_bot.sql`): ENABLE + REVOKE,
-- nessuna policy — l'accesso passa dalle RPC SECURITY DEFINER qui sotto, non
-- da SELECT diretto della UI, quindi non serve una policy owner come per la
-- realtime di Safe.
ALTER TABLE public.omega_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.omega_requests
    DROP CONSTRAINT IF EXISTS omega_requests_status_check;
ALTER TABLE public.omega_requests
    ADD CONSTRAINT omega_requests_status_check
    CHECK (status IN ('proposed','pending','processing','done','rejected','error'));

-- UNA SOLA PROPOSTA VIVA PER GAMBA. Senza questo indice un servizio riavviato a
-- meta' ciclo potrebbe scriverne due, e la Control Room mostrerebbe due pulsanti
-- APPROVA per la stessa posizione.
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_requests_proposta_viva
    ON public.omega_requests (((payload->>'trade_id')))
    WHERE status = 'proposed';

CREATE INDEX IF NOT EXISTS idx_omega_requests_proposed
    ON public.omega_requests (created_at DESC)
    WHERE status = 'proposed';

REVOKE ALL ON public.omega_requests FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.omega_requests TO service_role;

-- ----------------------------------------------------------------------------
-- 1. CHE COSA CONTIENE IL PAYLOAD DI UNA PROPOSTA V3
--
-- I campi sono quelli di `omega_v3.PropostaUscita` piu' l'identita' della gamba.
-- Sono CODICI, non frasi: la traduzione in italiano vive in UN solo posto della
-- UI, come per la Safe. Due tabelle che traducono la stessa cosa prima o poi
-- dicono due cose diverse.
--
--   trade_id, event_id, event_name, market_id, market_type, selection_id,
--   selection_name      -- che cosa si sta chiudendo
--   side                -- lato dell'ordine di CHIUSURA ('back' su un lay aperto)
--   entry_side, entry_price, size            -- com'era l'apertura
--   price_at_decision, size_available_at_decision
--                       -- FOTOGRAFIA al momento della decisione: serve a sapere
--                          su cosa il bot ha deciso e a misurare lo scostamento.
--                          NON e' il prezzo su cui si piazza: quello lo guarda
--                          l'utente, vivo, un istante prima (come nella Safe).
--   motivo_codice       -- 'blocca_il_profitto' | ... (omega_v3.proposta_uscita)
--   profitto_bloccabile -- EUR netti, uguali in ogni esito, se si chiude ORA
--   back_price, back_size -- l'ordine che realizzerebbe quel profitto
--   ev_tenere           -- quanto vale portarla al settlement con la P di adesso
--   p_evento            -- P che il risultato bancato ESCA (modello V3)
--   meglio_aspettare, bloccabile_max_atteso, minuto_del_massimo
--                       -- la TRAIETTORIA: se il punteggio regge, quanto si
--                          bloccherebbe piu' avanti e a che minuto. E' la
--                          ragione per cui una proposta puo' NON partire.
--   minute, score, mode ('paper'|'live')
--   decided_at          -- istante della DECISIONE: NON si rinfresca mai
--   proposed_at         -- ultimo aggiornamento della proposta
--
-- `decided_at` fermo e `proposed_at` mobile sono i due istanti che rendono
-- misurabile la latenza vera di una chiusura approvata a mano (cert. Safe
-- 14/09). Il controllo G2 della certificazione di Omega verifica entrambi.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 2. APPROVA: proposed -> pending.
--    Da qui in poi il percorso e' quello di sempre, invariato.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_request_approve(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.omega_requests%ROWTYPE;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- FOR UPDATE: fra la lettura e la scrittura il servizio potrebbe aver
    -- aggiornato la proposta col prezzo nuovo. Approvare e' un atto sui soldi:
    -- si prende il lock, non si spera.
    SELECT * INTO v_row FROM public.omega_requests WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        -- non e' un errore del chiamante: e' una corsa fra due schede aperte, o
        -- l'utente che preme due volte. Si dichiara cosa e' successo.
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non e'' piu'' in attesa di approvazione');
    END IF;

    UPDATE public.omega_requests
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
-- 3. IGNORA: proposed -> rejected, col motivo.
--    Non e' «non chiudere mai»: se la situazione CAMBIA (prezzo, punteggio,
--    profitto bloccabile) il servizio ripropone. «Torna alla prossima
--    occasione», come deciso dall'utente per la Safe il 14/09.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_request_ignore(p_id bigint,
                                                       p_reason text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.omega_requests%ROWTYPE;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT * INTO v_row FROM public.omega_requests WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non e'' piu'' in attesa di approvazione');
    END IF;

    UPDATE public.omega_requests
       SET status = 'rejected',
           result = coalesce(v_row.result, '{}'::jsonb) || jsonb_build_object(
               'ignorata_dall_utente', true,
               'motivo', coalesce(nullif(btrim(p_reason), ''), 'nessun motivo indicato')),
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'rejected');
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. LE PROPOSTE VIVE, per la Control Room (una lettura sola).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_proposte()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
  SELECT coalesce(jsonb_agg(jsonb_build_object(
             'id', r.id, 'kind', r.kind, 'payload', r.payload,
             'created_at', r.created_at, 'updated_at', r.updated_at)
           ORDER BY r.created_at DESC), '[]'::jsonb)
    FROM public.omega_requests r
   WHERE r.status = 'proposed';
$$;

REVOKE ALL ON FUNCTION public.omega_request_approve(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.omega_request_ignore(bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_omega_proposte() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.omega_request_approve(bigint) TO authenticated;
GRANT EXECUTE ON FUNCTION public.omega_request_ignore(bigint, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_omega_proposte() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5. PROMEMORIA DI COSA *NON* CAMBIA, perche' e' la parte che regge tutto
--
--  * Le APERTURE non passano di qui: restano automatiche, coi loro cap.
--  * Il servizio non drena 'proposed'. Se un domani lo facesse, il cancelletto
--    sparirebbe senza che nessuno se ne accorga: e' per questo che G1 esiste.
--  * Nessun freno (fermo macchina, cap, stop giornaliero) puo' rendere una
--    proposta di chiusura non approvabile: quei freni valgono sulle APERTURE.
--    Chi ha una posizione aperta deve sempre poterla chiudere.
--  * Le protezioni che NON chiudono restano attive e automatiche: settlement
--    dal mercato Betfair e riconciliazione degli ordini a esito ignoto.
--  * «Quota rotta» o mercato chiuso NON producono un'uscita automatica: al
--    massimo una riga di attivita'. In V3 nessuna uscita parte da sola.
-- ----------------------------------------------------------------------------
