-- ============================================================================
-- SAFE STRATEGY — LO STAKE E' PER STRATEGIA, NON PER LATO (16/09/2026, B.5)
-- ============================================================================
-- IL PROBLEMA. Fino a oggi il motore sceglieva lo stake dal LATO dell'ordine
-- (`engine.py`: `stake["laySize" if side == "lay" else "backSize"]`):
--
--   * `stake.backSize` -> TENNIS **e** PUNTA (che puntano)
--   * `stake.laySize`  -> BASE **ed** ESATTO (che bancano)
--
-- Due strategie diverse condividevano quindi lo stesso importo. Portare il
-- tennis a 3,00 EUR dalla scheda tennis portava a 3,00 EUR anche la PUNTA,
-- senza che niente e nessuno lo dicesse. E' esattamente la situazione trovata
-- sul database il 16/09 (`stake.backSize = 3`).
--
-- LA CORREZIONE e' UNA SOLA: da quale chiave il motore legge. Adesso c'e'
-- `stake.per_strategia`, una mappa per NOME (base / esatto / punta / tennis),
-- e `engine.stake_di_strategia` legge prima quella e poi, se manca, quella per
-- lato — quindi una configurazione salvata prima di oggi si comporta
-- ESATTAMENTE come si comportava.
--
-- CHE COSA FA QUESTO FILE. Scrive la mappa per strategia CON I VALORI CHE CI
-- SONO GIA', in modo che ogni strategia abbia da subito una manopola sua senza
-- che NESSUN importo cambi di un centesimo:
--
--   per_strategia.tennis = stake.backSize      per_strategia.base   = stake.laySize
--   per_strategia.punta  = stake.backSize      per_strategia.esatto = stake.laySize
--
-- Da quel momento in poi le quattro manopole sono indipendenti.
--
-- NON E' OBBLIGATORIA. Senza questa migrazione il bot opera come sempre (il
-- ripiego per lato e' dichiarato nel codice e la Control Room lo scrive accanto
-- al campo: «non ha ancora un importo suo: usa quello per lato»). Serve solo a
-- far partire le quattro manopole gia' separate.
--
-- NON TOCCA NESSUNA STRATEGIA: nessuna soglia, nessun minuto, nessuna quota,
-- nessun tetto, nessuna gamba. Solo la forma con cui lo stake e' scritto.
--
-- IDEMPOTENTE: scrive solo le chiavi MANCANTI, quindi rilanciarla non
-- sovrascrive mai un importo gia' personalizzato dall'utente.
-- ============================================================================

DO $$
DECLARE
    v_params  jsonb;
    v_stake   jsonb;
    v_per     jsonb;
    v_back    jsonb;
    v_lay     jsonb;
BEGIN
    SELECT params INTO v_params FROM public.safe_strategy_control WHERE id = 1;
    IF v_params IS NULL THEN
        RAISE NOTICE 'safe_strategy_control: nessuna riga id=1, niente da migrare';
        RETURN;
    END IF;

    v_stake := coalesce(v_params -> 'stake', '{}'::jsonb);
    v_per   := coalesce(v_stake  -> 'per_strategia', '{}'::jsonb);

    -- i valori COME SONO ADESSO. Se una delle due chiavi non c'e', si lascia
    -- stare: il default lo mette il motore in lettura (2,00 EUR), e scriverlo
    -- qui vorrebbe dire congelare un default sul database — cioe' rendere
    -- invisibile un cambio futuro del motore.
    v_back := v_stake -> 'backSize';
    v_lay  := v_stake -> 'laySize';

    IF v_back IS NOT NULL AND jsonb_typeof(v_back) = 'number' THEN
        IF v_per -> 'tennis' IS NULL THEN v_per := v_per || jsonb_build_object('tennis', v_back); END IF;
        IF v_per -> 'punta'  IS NULL THEN v_per := v_per || jsonb_build_object('punta',  v_back); END IF;
    END IF;
    IF v_lay IS NOT NULL AND jsonb_typeof(v_lay) = 'number' THEN
        IF v_per -> 'base'   IS NULL THEN v_per := v_per || jsonb_build_object('base',   v_lay);  END IF;
        IF v_per -> 'esatto' IS NULL THEN v_per := v_per || jsonb_build_object('esatto', v_lay);  END IF;
    END IF;

    IF v_per = coalesce(v_stake -> 'per_strategia', '{}'::jsonb) THEN
        RAISE NOTICE 'stake.per_strategia gia'' completo: niente da scrivere';
        RETURN;
    END IF;

    -- `jsonb_set` con `create_missing = true` su un percorso di due livelli
    -- pretende che il primo esista: si ricostruisce `stake` intero e lo si
    -- rimette al suo posto, senza toccare nessun'altra chiave dei parametri.
    v_stake := v_stake || jsonb_build_object('per_strategia', v_per);

    UPDATE public.safe_strategy_control
       SET params     = v_params || jsonb_build_object('stake', v_stake),
           updated_at = now()
     WHERE id = 1;

    RAISE NOTICE 'stake.per_strategia scritto: %', v_per;
END $$;

-- ----------------------------------------------------------------------------
-- VERIFICA (da lanciare a mano dopo l'applicazione):
--
--   SELECT params -> 'stake' FROM public.safe_strategy_control WHERE id = 1;
--
-- Atteso, partendo da `{"laySize": 2, "backSize": 3}`:
--   {"laySize": 2, "backSize": 3,
--    "per_strategia": {"base": 2, "esatto": 2, "punta": 3, "tennis": 3}}
--
-- Cioe': gli stessi identici importi di prima, ma separati.
-- ----------------------------------------------------------------------------
