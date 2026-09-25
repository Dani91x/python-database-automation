-- ============================================================================
-- tennis_uscite_manuali_2026-09-25.sql - AUTO-MODE dei 4 bot tennis e USCITE
-- AUTOMATICHE/MANUALI per bot. LA APPLICA L'UTENTE. ADDITIVA e IDEMPOTENTE.
--
-- ORDINE DELL'UTENTE (25/09): «I bot tennis (a esclusione di Safe) non partono
-- anche se li attivo [...] devono partire e lavorare tramite feed unico una
-- volta attivati [...] e gestire le uscite in automatico o in manuale sia in
-- paper che in live.»
--
-- 1) tennis_live_follow.origine ('manuale' | 'auto'). Il ponte
--    (`tennis_bot_service.riconcilia_interruttori`) crea da solo il follow
--    delle partite del FEED UNICO (`safe_strategy_scan`, sport tennis) con
--    origine 'auto', e lo CHIUDE quando nessun bot lo usa piu'. Un follow
--    dell'utente resta 'manuale' e il ponte non lo chiude mai.
--    Tutte le righe esistenti diventano 'manuale' (il default): nessuna scelta
--    dell'utente viene scambiata per automatica.
--    FINCHE' NON E' APPLICATA: l'auto-mode resta SPENTO (il ponte non puo'
--    marcare un follow come automatico e non lo scrive), i bot si armano sulle
--    sole partite seguite a mano come prima, e la Control Room lo DICE
--    («auto-mode spento: migrazione ... non applicata»).
--
-- 2) uscite_automatiche (boolean, DEFAULT false = MANUALI) su
--    tennis_bot_service_control (l'interruttore del bot) e su
--    tennis_bot_control (la riga per partita, che il runner rilegge a caldo).
--    25/09 SERA (ordine dell'utente, successivo a quello del §5.7 sopra: «di
--    default tutte le uscite le voglio spente, decido io se uscire o no, per
--    tutti i bot») - il DEFAULT e' cambiato da true a false: false = il bot
--    non prende profitto da solo (target, scaglione, green sullo swing);
--    stop, time-stop, uscita strutturale, fine mercato, «Chiudi» D3 restano
--    SEMPRE. Lo scalper resta sempre automatico (la sua uscita a target e' la
--    gamba opposta dell'ingresso: spegnerla altera la strategia - decisione
--    dell'utente, non presa qui). Il codice funziona anche senza questa
--    migrazione: il default manuale vive gia' in ``auto_mode.py``.
--
-- 3) RPC owner-only tennis_bot_service_set_uscite(p_bot_key, p_automatiche):
--    cambia SOLO l'interruttore delle uscite. Non tocca mai `status` (i bot li
--    accende solo l'utente, e non da qui), `mode`, `stake`, `params`.
--
-- 4) tennis_follow_event (il «segui» dell'utente dal Terminale): stesso corpo
--    di `migrations/tennis_live.sql`, in piu' un follow seguito a mano torna
--    SEMPRE 'manuale' (anche se il ponte l'aveva gia' aperto come 'auto').
-- ============================================================================

-- 1) origine del follow ------------------------------------------------------
ALTER TABLE public.tennis_live_follow
    ADD COLUMN IF NOT EXISTS origine TEXT NOT NULL DEFAULT 'manuale';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'tennis_live_follow_origine_check'
           AND conrelid = 'public.tennis_live_follow'::regclass
    ) THEN
        ALTER TABLE public.tennis_live_follow
            ADD CONSTRAINT tennis_live_follow_origine_check
            CHECK (origine IN ('manuale', 'auto'));
    END IF;
END;
$$;

COMMENT ON COLUMN public.tennis_live_follow.origine IS
    'manuale = seguito dall''utente; auto = aperto dal ponte dei bot tennis '
    'dal feed unico (auto-mode, 25/09/2026) e chiuso quando nessun bot lo usa.';

-- 2) uscite automatiche --------------------------------------------------------
-- 25/09 sera: DEFAULT false (manuali), ordine dell'utente. Se questa colonna
-- fosse gia' stata creata con DEFAULT true da un apply precedente della
-- versione di questo file, la migrazione additiva
-- `uscite_manuali_default_2026-09-25.sql` corregge sia il default sia i
-- valori NULL/assenti gia' scritti.
ALTER TABLE public.tennis_bot_service_control
    ADD COLUMN IF NOT EXISTS uscite_automatiche BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.tennis_bot_control
    ADD COLUMN IF NOT EXISTS uscite_automatiche BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.tennis_bot_service_control.uscite_automatiche IS
    'true = il bot prende profitto da solo; false (DEFAULT dal 25/09 sera) = '
    'uscite MANUALI: restano stop e protezioni, la posizione la chiude '
    'l''utente con «Chiudi». Identico in paper e live. Lo scalper e'' sempre automatico.';

-- 3) RPC: cambia SOLO le uscite -----------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_bot_service_set_uscite(
    p_bot_key text, p_automatiche boolean
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.tennis_bot_service_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_automatiche IS NULL THEN
        RAISE EXCEPTION 'p_automatiche obbligatorio (true|false)';
    END IF;
    -- la riga DEVE esistere: crearla qui vorrebbe dire inventare `status` e
    -- `mode` che nessuno ha scelto (stessa regola di update_params).
    UPDATE public.tennis_bot_service_control AS c
       SET uscite_automatiche = p_automatiche,
           updated_at = now()
     WHERE c.bot_key = p_bot_key
    RETURNING * INTO v_row;
    IF v_row.bot_key IS NULL THEN
        RAISE EXCEPTION 'bot tennis sconosciuto o mai acceso: %', p_bot_key;
    END IF;
    RETURN to_json(v_row);
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_bot_service_set_uscite(text, boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_service_set_uscite(text, boolean) TO authenticated, service_role;

-- 4) il «segui» dell'utente resta manuale ------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_follow_event(p_event_id text, p_market_id text)
RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_live_follow;
    v_mk  record;
BEGIN
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;

    SELECT * INTO v_mk FROM public.tennis_markets WHERE event_id = p_event_id;

    INSERT INTO public.tennis_live_follow AS f
        (event_id, market_id, competition_name, player1_name, player2_name,
         open_date, status, error_detail, updated_at, origine)
    VALUES (
        p_event_id,
        coalesce(nullif(p_market_id, ''), v_mk.market_id),
        v_mk.competition_name,
        coalesce(v_mk.player1->>'name', ''),
        coalesce(v_mk.player2->>'name', ''),
        coalesce(v_mk.open_date, now()),
        'PENDING',
        NULL,
        now(),
        'manuale'
    )
    ON CONFLICT (event_id) DO UPDATE SET
        market_id        = coalesce(EXCLUDED.market_id, f.market_id),
        competition_name = coalesce(EXCLUDED.competition_name, f.competition_name),
        player1_name     = CASE WHEN EXCLUDED.player1_name <> '' THEN EXCLUDED.player1_name ELSE f.player1_name END,
        player2_name     = CASE WHEN EXCLUDED.player2_name <> '' THEN EXCLUDED.player2_name ELSE f.player2_name END,
        open_date        = coalesce(f.open_date, EXCLUDED.open_date),
        status           = 'PENDING',
        error_detail     = NULL,
        updated_at       = now(),
        origine          = 'manuale'
    RETURNING * INTO v_row;

    RETURN json_build_object(
        'event_id',         v_row.event_id,
        'competition_name', v_row.competition_name,
        'player1_name',     v_row.player1_name,
        'player2_name',     v_row.player2_name,
        'open_date',        v_row.open_date,
        'status',           v_row.status,
        'error_detail',     v_row.error_detail,
        'inplay',           v_row.inplay,
        'score',            v_row.score,
        'live_status',      v_row.live_status,
        'updated_at',       v_row.updated_at
    );
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_follow_event(text, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_follow_event(text, text) TO authenticated, service_role;
