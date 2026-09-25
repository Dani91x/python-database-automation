-- ============================================================================
-- SAFE STRATEGY - BASE: QUOTA DI BANCA 20-34 AL POSTO DELLA "LETTURA A"
-- (decisione dell'utente 25/09/2026, Q1)
-- ============================================================================
-- COSA CAMBIA NEL CODICE (gia' fatto, non serve questo file per attivarlo):
--   `engine.DEFAULT_PARAMS["base"]` ha `dogLayMin = 20`, `dogLayMax = 34`
--   (la quota di BANCA della squadra che perde, estremi inclusi; corso,
--   "4. STRATEGIA/2. Entrata a mercato" @93.0: "vanno dal 20 al 34, a dir
--   tanto"). Il filtro sul back live della favorita (1,20-1,34, chiavi
--   `favLiveMin`/`favLiveMax`) e' TOLTO e `engine.merge_params` non legge piu'
--   quelle chiavi: se restano sul DB sono INERTI.
--
-- NON E' OBBLIGATORIA. Senza questa migrazione il bot usa gia' 20-34 (default
-- nel codice). Serve a due cose:
--   1. togliere dal JSON dei parametri le due chiavi morte, cosi' chi legge
--      `safe_strategy_control.params` non crede che la Lettura A sia viva;
--   2. scrivere la banda nuova in chiaro SOLO se non c'e' gia' (mai
--      sovrascrivere un valore che l'utente abbia messo a mano).
--
-- NON TOCCA NIENT'ALTRO: nessuna soglia, minuto, stake, uscita.
-- IDEMPOTENTE: rilanciarla non cambia nulla la seconda volta.
-- ============================================================================

DO $$
DECLARE
    v_params jsonb;
    v_base   jsonb;
BEGIN
    SELECT params INTO v_params FROM public.safe_strategy_control WHERE id = 1;
    IF v_params IS NULL THEN
        RAISE NOTICE 'safe_strategy_control: nessuna riga id=1, niente da migrare';
        RETURN;
    END IF;

    v_base := coalesce(v_params -> 'base', '{}'::jsonb);

    -- 1. le chiavi della Lettura A, deprecate dal 25/09
    v_base := v_base - 'favLiveMin' - 'favLiveMax';

    -- 2. la banda del corso, solo se mancante
    IF NOT (v_base ? 'dogLayMin') THEN
        v_base := v_base || jsonb_build_object('dogLayMin', 20);
    END IF;
    IF NOT (v_base ? 'dogLayMax') THEN
        v_base := v_base || jsonb_build_object('dogLayMax', 34);
    END IF;

    UPDATE public.safe_strategy_control
       SET params     = v_params || jsonb_build_object('base', v_base),
           updated_at = now()
     WHERE id = 1;
END $$;

-- VERIFICA (sola lettura):
--   SELECT params -> 'base' FROM public.safe_strategy_control WHERE id = 1;
--   atteso: niente favLiveMin/favLiveMax; dogLayMin 20, dogLayMax 34.
