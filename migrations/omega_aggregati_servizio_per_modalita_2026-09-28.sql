-- ============================================================================
-- OMEGA: aggregati del SERVIZIO per MODALITA' (cantiere C, 28/09/2026, D4)
-- ============================================================================
-- REPERTO (catalogo 7.21, ordine dell'utente 'paper e live non si sommano mai'):
--   `get_omega_aggregates()` (il servizio) chiama `omega_aggregates_sql(boolean)`
--   senza filtro di modalita': stop giornaliero (`daily_loss_cap`,
--   `stop_on_goal`), tetti (`max_open_liability`, `max_events`) e obiettivo
--   del bot sommavano euro veri e simulati. La migrazione del 26/09
--   (`omega_state_per_modalita_2026-09-26.sql`) aveva separato SOLO la pagina.
--
-- CORREZIONE (solo lettura, nessun dato toccato, nessuna funzione esistente
-- cambiata): una RPC NUOVA per il servizio, `get_omega_aggregates_modalita(text)`,
-- che RIUSA `omega_aggregates_sql(boolean, text)` del 26/09 (filtro sulla
-- modalita' della POSIZIONE: `coalesce(p.mode, o.mode)`). Stessa forma di
-- `get_omega_aggregates()`: totali + blocco `auto` (i numeri del solo bot).
--
-- PRIMA dell'applicazione il servizio funziona lo stesso: `omega_db` calcola
-- gli aggregati per modalita' IN CASA dalle righe (piu' IO, stesso risultato)
-- e lo dichiara nel log (WARNING, una volta per processo).
--
-- PREREQUISITO: `omega_state_per_modalita_2026-09-26.sql` applicata (crea
-- `omega_aggregates_sql(boolean, text)`; applicata dall'utente il 26/09).
-- IDEMPOTENTE: CREATE OR REPLACE.
--
-- VERIFICA dopo l'applicazione:
--   SELECT public.get_omega_aggregates_modalita('paper')->>'mode';          -- 'paper'
--   SELECT public.get_omega_aggregates_modalita('live')->'auto'->>'mode';   -- 'live'
--   SELECT public.get_omega_aggregates_modalita('boh');                     -- errore
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_omega_aggregates_modalita(p_mode text)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_mode text := lower(btrim(coalesce(p_mode, '')));
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    -- mai "tutte le modalita'" da qui: e' la RPC delle DECISIONI per modalita'
    IF v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalita'' non valida: %', p_mode;
    END IF;
    RETURN coalesce(public.omega_aggregates_sql(false, v_mode), '{}'::jsonb)
           || jsonb_build_object('auto',
                coalesce(public.omega_aggregates_sql(true, v_mode), '{}'::jsonb));
END;
$fn$;
REVOKE ALL    ON FUNCTION public.get_omega_aggregates_modalita(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_aggregates_modalita(text) TO authenticated, service_role;
