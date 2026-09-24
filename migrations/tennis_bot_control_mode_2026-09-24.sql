-- ============================================================================
-- tennis_bot_control_mode_2026-09-24.sql - la MODALITA' DEL BOT sulla riga per
-- partita (reperto T1 del 24/09/2026). LA APPLICA L'UTENTE.
--
-- IL DIFETTO: `tennis_bot_control` (una riga per evento x bot) non portava la
-- modalita' del bot. Il ponte (`tennis_bot_service.riconcilia_interruttori`)
-- scriveva solo `dry_run = (mode == 'live')`, quindi un bot acceso in PAPER
-- nasceva con `dry_run=false`, e il runner tennis, se il processo girava in
-- LIVE (`TENNIS_LIVE_ORDER_MODE`), lo eseguiva sul client REALE.
--
-- LA CORREZIONE (lato Python gia' nel codice):
--   * la riga porta `mode` ('paper' | 'live'), scritta ESPLICITAMENTE dal ponte;
--   * il runner simula SEMPRE quando la riga e' 'paper' (o senza modalita'), e
--     va a reale SOLO con riga 'live' + runner LIVE + dry_run=false esplicito.
--
-- FAIL-CLOSED:
--   * la colonna nasce con DEFAULT 'paper' e NOT NULL: tutte le righe esistenti
--     diventano 'paper' (ai soldi veri si arriva scrivendolo, mai ereditandolo);
--   * la RPC `tennis_bot_arm` (armamento dalla scheda partita) NON riceve una
--     modalita': da oggi scrive SEMPRE 'paper', anche sul riarmo di una riga che
--     era 'live' (prima un riarmo avrebbe ereditato la modalita' vecchia). Il
--     live per partita dalla scheda richiedera' una RPC con `p_mode` esplicito:
--     DECISIONE dell'utente, non presa qui.
--   * finche' questa migrazione NON e' applicata il codice scrive la riga senza
--     `mode` e il runner la legge PAPER (`tennis_db.upsert_tennis_bot_control`).
--
-- IDEMPOTENTE. Testo base della RPC: `migrations/tennis_bots_arm_guard.sql`
-- (guard anti re-arm compreso), cambia SOLO la colonna `mode`.
-- ============================================================================

ALTER TABLE public.tennis_bot_control
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'paper';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'tennis_bot_control_mode_check'
           AND conrelid = 'public.tennis_bot_control'::regclass
    ) THEN
        ALTER TABLE public.tennis_bot_control
            ADD CONSTRAINT tennis_bot_control_mode_check
            CHECK (mode IN ('paper', 'live'));
    END IF;
END;
$$;

COMMENT ON COLUMN public.tennis_bot_control.mode IS
    'Modalita'' DEL BOT (paper|live), scritta dal ponte. Il runner tennis esegue '
    'reale SOLO con mode=''live'' + runner LIVE + dry_run=false esplicito. '
    'Default paper: mai ereditata (T1, 24/09/2026).';

-- ----------------------------------------------------------------------------
-- RPC tennis_bot_arm: stesso corpo di tennis_bots_arm_guard.sql + mode='paper'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_bot_arm(
    p_event_id text,
    p_bot_key  text,
    p_dry_run  boolean,
    p_stake    numeric,
    p_params   jsonb
) RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_bot_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_bot_key NOT IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing') THEN
        RAISE EXCEPTION 'bot_key non valido: %', p_bot_key;
    END IF;
    IF p_stake IS NULL OR p_stake < 0 OR p_stake > 100000 THEN
        RAISE EXCEPTION 'stake fuori range [0,100000]: %', p_stake;
    END IF;

    -- GUARD anti re-arm (invariato da tennis_bots_arm_guard.sql)
    IF EXISTS (
        SELECT 1
          FROM public.tennis_bot_control
         WHERE event_id = p_event_id
           AND bot_key  = p_bot_key
           AND status IN ('requested','arming','armed','running','stopping')
    ) THEN
        RAISE EXCEPTION 'bot già attivo o in chiusura: attendi lo stop prima di riarmare';
    END IF;

    INSERT INTO public.tennis_bot_control AS c
        (event_id, bot_key, status, mode, dry_run, stake, params, stats, error,
         requested_at, started_at, stopped_at, heartbeat_at, updated_at)
    VALUES
        (p_event_id, p_bot_key, 'requested', 'paper', coalesce(p_dry_run, true),
         p_stake, coalesce(p_params, '{}'::jsonb), NULL, NULL,
         now(), NULL, NULL, NULL, now())
    ON CONFLICT (event_id, bot_key) DO UPDATE SET
        status       = 'requested',
        -- T1: la modalita' NON si eredita dal riarmo precedente
        mode         = 'paper',
        dry_run      = EXCLUDED.dry_run,
        stake        = EXCLUDED.stake,
        params       = EXCLUDED.params,
        stats        = NULL,
        error        = NULL,
        requested_at = now(),
        started_at   = NULL,
        stopped_at   = NULL,
        updated_at   = now()
    RETURNING * INTO v_row;

    RETURN public._tennis_bot_control_json(v_row)::json;
END;
$$;

-- ----------------------------------------------------------------------------
-- GRANT (ribaditi: il file deve essere autoconsistente). La tabella resta
-- chiusa ad anon; authenticated legge (policy owner di realtime_orders_bots.sql);
-- scrive solo service_role (il servizio) e la RPC SECURITY DEFINER.
-- ----------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON TABLE public.tennis_bot_control TO service_role;
GRANT SELECT ON TABLE public.tennis_bot_control TO authenticated;
REVOKE ALL ON TABLE public.tennis_bot_control FROM anon;

REVOKE ALL    ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_arm(text,text,boolean,numeric,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- VERIFICA (sola lettura, da lanciare dopo):
--   SELECT mode, count(*) FROM public.tennis_bot_control GROUP BY mode;
--   -> solo 'paper' subito dopo l'applicazione.
-- ============================================================================
