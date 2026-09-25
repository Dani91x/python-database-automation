-- ============================================================================
-- SAFE STRATEGY - TENNIS: QUOTA MINIMA D'INGRESSO DA 1,01 A 1,02
-- (decisione dell'utente 25/09/2026, Q5)
-- ============================================================================
-- COSA CAMBIA NEL CODICE (gia' fatto): `engine.DEFAULT_PARAMS["tennis"]["backMin"]`
-- = 1.02 (era 1.01), e il controllo T1 del banco tennis
-- (`certificazione_tennis.SPEC_TENNIS_BACK_MIN`) e' rosso con qualunque backMin
-- diverso da 1,02.
--
-- ATTENZIONE: QUESTA MIGRAZIONE SERVE DAVVERO SE SUL DB C'E' `tennis.backMin`: il valore
-- dell'utente vince sul default del codice (`engine.merge_params`), quindi un
-- 1,01 scritto dalla scheda parametri terrebbe viva la quota vecchia anche col
-- codice nuovo. Se la chiave NON c'e', il default 1,02 vale gia' e questo file
-- non cambia niente.
--
-- CHE COSA FA: se `params.tennis.backMin` esiste ed e' diverso da 1.02, lo
-- porta a 1.02 e lo dice (RAISE NOTICE col valore vecchio). Non tocca nessun
-- altro parametro (backMax, set, game, stake, uscite).
-- IDEMPOTENTE.
--
-- VERIFICA PRIMA (sola lettura), per sapere se serve:
--   SELECT params -> 'tennis' -> 'backMin' FROM public.safe_strategy_control WHERE id = 1;
-- ============================================================================

DO $$
DECLARE
    v_params jsonb;
    v_tennis jsonb;
    v_old    jsonb;
BEGIN
    SELECT params INTO v_params FROM public.safe_strategy_control WHERE id = 1;
    IF v_params IS NULL THEN
        RAISE NOTICE 'safe_strategy_control: nessuna riga id=1, niente da migrare';
        RETURN;
    END IF;

    v_tennis := v_params -> 'tennis';
    IF v_tennis IS NULL OR jsonb_typeof(v_tennis) <> 'object' OR NOT (v_tennis ? 'backMin') THEN
        RAISE NOTICE 'tennis.backMin assente sul DB: vale il default del codice (1.02), niente da fare';
        RETURN;
    END IF;

    v_old := v_tennis -> 'backMin';
    IF jsonb_typeof(v_old) = 'number' AND (v_old #>> '{}')::numeric = 1.02 THEN
        RAISE NOTICE 'tennis.backMin gia'' 1.02: niente da fare';
        RETURN;
    END IF;

    UPDATE public.safe_strategy_control
       SET params     = v_params || jsonb_build_object(
                            'tennis', v_tennis || jsonb_build_object('backMin', 1.02)),
           updated_at = now()
     WHERE id = 1;

    RAISE NOTICE 'tennis.backMin: % -> 1.02', v_old;
END $$;

-- VERIFICA DOPO:
--   SELECT params -> 'tennis' -> 'backMin' FROM public.safe_strategy_control WHERE id = 1;
--   atteso: 1.02
