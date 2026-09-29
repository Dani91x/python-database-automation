-- ============================================================================
-- uscite_approva_bot_flusso_2026-09-28.sql - CANTIERE N. LA APPLICA L'UTENTE.
-- ADDITIVA E IDEMPOTENTE (solo CREATE OR REPLACE di due funzioni nuove; nessuna
-- tabella, nessuna colonna, nessun dato toccato).
--
-- Ordine dell'utente (28/09, testuale): "TUTTI I BOT DEVONO AVERE LA
-- POSSIBILITA' DI USCITE MANUALI, OVVERO APPROVATE DA ME [...] OGNI BOT, PER
-- ORA, DEVE PASSARE DA ME, IO APPROVO LE USCITE".
--
-- I bot di flusso (4 bot tennis, scalper calcio) a uscite MANUALI non chiudono:
-- tengono la PROPOSTA coi numeri in `stats.uscite_proposte` della loro riga di
-- controllo (il battito la scrive gia'). La Control Room mostra "approva"; il
-- clic chiama una di queste RPC, che scrive la FIRMA `{chiave: now()}` in
-- `params.uscite_approvate` della riga (unione con le firme gia' presenti). Il
-- runner tennis / la sessione scalper rileggono la riga al battito (3 s / 5 s)
-- e passano la firma al bot: l'uscita parte la PROSSIMA volta che la strategia
-- la decide ancora, sul mercato di adesso, entro 120 s
-- (`Betfair/stream/uscite_proposte.py`, stesso TTL di Mike).
--
-- Stesso schema delle RPC owner-only gia' in uso:
--   tennis  -> public.tennis_is_owner()   (tennis_bot_service_set_uscite)
--   scalper -> public.betfair_live_is_owner() (scalper_uscite_automatiche)
-- Senza questa migrazione: il pulsante "approva" risponde con l'errore della
-- funzione mancante e NIENTE parte (fail-closed); il "Chiudi" di sempre resta.
-- Richiede: tennis_bots.sql, scalper_bot.sql, security_lockdown.sql.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) TENNIS: firma su una proposta di UN bot su UNA partita
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_bot_approva_uscita(
    p_event_id text, p_bot_key text, p_chiave text
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.tennis_bot_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF coalesce(btrim(p_chiave), '') = '' THEN
        RAISE EXCEPTION 'p_chiave obbligatoria (la chiave della proposta)';
    END IF;
    -- la chiave porta il bot come primo pezzo (`tennis_swing|...`): una firma
    -- data a un bot non puo' sbloccare l'uscita di un altro
    IF split_part(p_chiave, '|', 1) <> p_bot_key THEN
        RAISE EXCEPTION 'la proposta % non e'' del bot %', p_chiave, p_bot_key;
    END IF;
    UPDATE public.tennis_bot_control AS c
       SET params = jsonb_set(
               coalesce(c.params, '{}'::jsonb), '{uscite_approvate}',
               coalesce(c.params -> 'uscite_approvate', '{}'::jsonb)
                   || jsonb_build_object(p_chiave, to_jsonb(now())),
               true),
           updated_at = now()
     WHERE c.event_id = p_event_id
       AND c.bot_key = p_bot_key
       AND c.status IN ('requested', 'arming', 'armed', 'running')
    RETURNING * INTO v_row;
    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'nessun bot % attivo sulla partita %', p_bot_key, p_event_id;
    END IF;
    RETURN to_json(v_row);
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_bot_approva_uscita(text, text, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_approva_uscita(text, text, text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 2) SCALPER CALCIO: firma su una proposta della sessione di UNA partita
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_approva_uscita(
    p_event_id text, p_chiave text
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.scalper_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF coalesce(btrim(p_chiave), '') = '' THEN
        RAISE EXCEPTION 'p_chiave obbligatoria (la chiave della proposta)';
    END IF;
    IF split_part(p_chiave, '|', 1) <> 'scalper' THEN
        RAISE EXCEPTION 'la proposta % non e'' dello scalper calcio', p_chiave;
    END IF;
    UPDATE public.scalper_control AS c
       SET params = jsonb_set(
               coalesce(c.params, '{}'::jsonb), '{uscite_approvate}',
               coalesce(c.params -> 'uscite_approvate', '{}'::jsonb)
                   || jsonb_build_object(p_chiave, to_jsonb(now())),
               true),
           updated_at = now()
     WHERE c.event_id = p_event_id
       AND c.status IN ('requested', 'arming', 'armed', 'running')
    RETURNING * INTO v_row;
    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'nessuna sessione scalper attiva sulla partita %', p_event_id;
    END IF;
    RETURN to_json(v_row);
END;
$$;

REVOKE ALL    ON FUNCTION public.scalper_approva_uscita(text, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_approva_uscita(text, text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- Verifica (facoltativa, sola lettura):
--   SELECT proname FROM pg_proc WHERE proname IN
--     ('tennis_bot_approva_uscita', 'scalper_approva_uscita');
-- ============================================================================
