-- ============================================================================
-- OMEGA — `omega_activate` non deve piu' AZZERARE i parametri (16/09/2026)
-- ============================================================================
-- IL PROBLEMA, in una riga: e' lo stesso pattern del bug di Mike del 15/09,
-- solo scritto in SQL invece che in Python.
--
--   safe_activate  -> params = coalesce(p_params, params)       CONSERVA
--   mike_activate  -> params = coalesce(p_params, params)       CONSERVA
--   omega_activate -> params = coalesce(p_params, '{}'::jsonb)  AZZERA
--
-- `{}` non e' NULL: chiamare `omega_activate('live', 250)` senza parametri
-- SOSTITUISCE l'intera colonna con un oggetto vuoto. E i tetti di rischio di
-- Omega, a ZERO, nel suo codice significano TETTO SPENTO:
--
--   * `max_liability_per_match` -> `apply_liability_cap`:
--     `if not cap or cap <= 0: return size`  (nessun tetto per partita)
--   * `max_open_liability`      -> `omega_service.py:1201`: controllo saltato
--   * `daily_loss_cap`          -> `omega_service.py:963`: lo stop perdite
--     non scatta MAI
--
-- Cioe': una riattivazione senza parametri toglie tutti e tre i freni, in
-- live, in silenzio. Oggi regge SOLO perche' il frontend passa sempre i
-- parametri correnti e si rifiuta di avviare quando non li ha letti
-- (`ParametriOmegaIgnoti`, `frontend/src/lib/interruttori.ts`). Ma una
-- protezione che vive solo nel browser non e' una protezione: basta un'altra
-- sessione, uno script, o una futura riscrittura della pagina.
--
-- LA CORREZIONE e' una parola: `'{}'::jsonb` -> `params`. Nient'altro cambia:
-- stessa firma, stessi controlli, stesso snapshot dell'obiettivo, stessi
-- privilegi. Chi passa i parametri continua a sovrascriverli come prima; chi
-- non li passa adesso li CONSERVA invece di cancellarli.
--
-- NON tocca nessuna strategia: i parametri sono quelli che c'erano.
--
-- IDEMPOTENTE: `CREATE OR REPLACE FUNCTION` con la firma identica a quella in
-- vigore (`omega_daily_v2.sql:52`), quindi si puo' rilanciare quante volte si
-- vuole senza effetti collaterali e senza `DROP`.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.omega_activate(
    p_mode        text DEFAULT 'paper',
    p_daily_goal  numeric DEFAULT 250,
    p_params      jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    IF p_daily_goal IS NULL OR p_daily_goal < 0 OR p_daily_goal > 100000 THEN
        RAISE EXCEPTION 'daily_goal fuori range [0,100000]: %', p_daily_goal;
    END IF;
    UPDATE public.omega_control SET
        status      = 'running',
        mode        = p_mode,
        daily_goal  = p_daily_goal,
        -- ⚠️ QUI stava il difetto: `coalesce(p_params, '{}'::jsonb)` azzerava
        -- i tetti di rischio a ogni attivazione senza parametri.
        params      = coalesce(p_params, params),
        error       = NULL,
        started_at  = now(),
        stopped_at  = NULL,
        updated_at  = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    PERFORM public.omega_snapshot_daily_goal(p_daily_goal);
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_activate(text,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_activate(text,numeric,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- NOTA sul default della firma. `p_params jsonb DEFAULT '{}'::jsonb` resta com'e'
-- per non cambiare la firma (e quindi non rompere PostgREST ne' i chiamanti
-- esistenti). Con il `coalesce` corretto, `'{}'` passato ESPLICITAMENTE
-- continua a voler dire "scrivi un oggetto vuoto" — che e' una scelta di chi
-- chiama, non piu' un effetto collaterale di chi tace.
-- Il frontend non chiama mai `omega_activate` senza parametri: si rifiuta di
-- avviare Omega quando non li ha letti. Questa migrazione toglie la dipendenza
-- da quella cortesia.
-- ----------------------------------------------------------------------------
