-- ============================================================================
-- omega_missions.sql — CENTRO DI CONTROLLO PER PARTITA (tab MISSIONE di /omega).
--
-- Una "missione" = una partita attivata dall'utente con un target in €.
-- Il servizio locale (omega_service) per ogni missione attiva:
--   * aggiorna minuto/punteggio/fase (endpoint pubblico in-play Betfair, batch);
--   * genera i SUGGERIMENTI per gamba: HT_CS (lay Correct Score PRIMO TEMPO),
--     FT_CS (lay Correct Score generale, proposto all'INTERVALLO), SCALP
--     (back Under X.5 per chiudere il gap del target);
--   * NON piazza mai da solo: ogni ordine parte da un click dell'utente che
--     accoda una richiesta 'place' (omega_manual_requests) con la sua `phase`.
--
-- Il P&L per gamba NON è duplicato qui: si calcola da omega_trades (phase) e
-- da scalper_control.stats->>'pnl_locked' (gamba pre-match) nella RPC di lettura.
--
-- IDEMPOTENTE. Richiede omega_bot.sql + omega_manual.sql + betfair_live_is_owner().
-- ============================================================================

-- gamba della missione sul trade (NULL = trade non-missione: auto legacy o manuale puro)
ALTER TABLE public.omega_trades
    ADD COLUMN IF NOT EXISTS phase TEXT
    CHECK (phase IS NULL OR phase IN ('ht_cs','ft_cs','scalp'));
CREATE INDEX IF NOT EXISTS idx_omega_trades_event_phase
    ON public.omega_trades (event_id, phase) WHERE phase IS NOT NULL;

-- 1. omega_missions — una riga per partita attivata.
CREATE TABLE IF NOT EXISTS public.omega_missions (
    event_id     TEXT PRIMARY KEY,
    event_name   TEXT NOT NULL,
    kickoff      TIMESTAMPTZ,
    mission_date DATE NOT NULL DEFAULT ((now() AT TIME ZONE 'Europe/Rome')::date),
    target       NUMERIC NOT NULL CHECK (target > 0 AND target <= 10000),
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','paused','closed')),
    -- fase rilevata dal servizio: pre | 1t | ht (intervallo) | 2t | finita
    phase_now    TEXT NOT NULL DEFAULT 'pre'
                 CHECK (phase_now IN ('pre','1t','ht','2t','finita')),
    minute       INTEGER,
    score_home   INTEGER,
    score_away   INTEGER,
    score_status TEXT,        -- raw provider: FirstHalf|HalfTime|SecondHalf|Finished
    -- suggerimenti scritti dal servizio (la UI mostra, l'utente clicca):
    -- ht/ft: {market_id,market_name,selection_id,runner_name,lay_price,lay_size,advisor,updated_at}
    --   advisor (CONSULENTE DATI, informativo, puo' essere null): {poisson_prob,
    --   freq_league:{p,n}, h2h:{n_meetings,n_score}, matched_fixture_id, sources}
    -- scalp: {market_id,market_name,selection_id,runner_name,back_price,back_size,line,updated_at}
    suggestion_ht    JSONB,
    suggestion_ft    JSONB,
    suggestion_scalp JSONB,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_omega_missions_date   ON public.omega_missions (mission_date);
CREATE INDEX IF NOT EXISTS idx_omega_missions_status ON public.omega_missions (status);
ALTER TABLE public.omega_missions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_missions FROM anon, authenticated;

-- Realtime + SELECT owner-only (stesso pattern di omega_control/omega_trades).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname='supabase_realtime' AND schemaname='public'
                     AND tablename='omega_missions') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.omega_missions;
    END IF;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;
DROP POLICY IF EXISTS omega_missions_select_owner ON public.omega_missions;
CREATE POLICY omega_missions_select_owner ON public.omega_missions
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.omega_missions TO authenticated;
REVOKE SELECT ON TABLE public.omega_missions FROM anon;

-- ----------------------------------------------------------------------------
-- RPC: attiva (o riattiva) la missione su una partita.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_mission_activate(
    p_event_id   text,
    p_event_name text,
    p_kickoff    timestamptz DEFAULT NULL,
    p_target     numeric DEFAULT 5
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_missions;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) = 0 OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_event_name IS NULL OR length(trim(p_event_name)) = 0 THEN
        RAISE EXCEPTION 'event_name mancante';
    END IF;
    IF p_target IS NULL OR p_target <= 0 OR p_target > 10000 THEN
        RAISE EXCEPTION 'target fuori range (0,10000]: %', p_target;
    END IF;
    -- guardie 16/07 (audit): SOLO per le NUOVE attivazioni — kickoff obbligatorio
    -- (senza, un evento non coperto dall'inplay service resterebbe 'pre' per
    -- sempre = missione eterna) e non più vecchio di 3h (cache eventi stantia →
    -- missione auto-chiusa subito). La RIATTIVAZIONE di una missione in pausa
    -- NON passa di qui (review 16/07: una partita coi supplementari supera le 3h
    -- dal kickoff — bloccare il resume la renderebbe irrecuperabile mentre M7
    -- tiene l'evento riservato).
    IF NOT EXISTS (SELECT 1 FROM public.omega_missions g
                    WHERE g.event_id = p_event_id AND g.status IN ('active','paused')) THEN
        IF p_kickoff IS NULL THEN
            RAISE EXCEPTION 'kickoff mancante: aggiorna gli eventi e riprova';
        END IF;
        IF p_kickoff < now() - interval '3 hours' THEN
            RAISE EXCEPTION 'partita già terminata (calcio d''inizio %): aggiorna gli eventi', p_kickoff;
        END IF;
    END IF;
    INSERT INTO public.omega_missions AS m
        (event_id, event_name, kickoff, mission_date, target, status, updated_at)
    VALUES (p_event_id, p_event_name, p_kickoff,
            (now() AT TIME ZONE 'Europe/Rome')::date, p_target, 'active', now())
    ON CONFLICT (event_id) DO UPDATE SET
        event_name   = EXCLUDED.event_name,
        kickoff      = coalesce(EXCLUDED.kickoff, m.kickoff),
        mission_date = EXCLUDED.mission_date,
        target       = EXCLUDED.target,
        status       = 'active',
        error        = NULL,
        -- suggestion CONGELATE durante la pausa = prezzi stantii piazzabili al
        -- rientro (audit M9): si azzerano, il servizio le ricalcola al 1° ciclo.
        suggestion_ht    = NULL,
        suggestion_ft    = NULL,
        suggestion_scalp = NULL,
        updated_at   = now()
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_mission_activate(text,text,timestamptz,numeric) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_mission_activate(text,text,timestamptz,numeric) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: pausa/chiudi la missione (i trade aperti si regolano comunque — I3).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_mission_stop(
    p_event_id text,
    p_close    boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_missions;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.omega_missions SET
        status     = CASE WHEN p_close THEN 'closed' ELSE 'paused' END,
        -- audit M9 16/07: mai lasciare suggestion congelate su missione ferma
        suggestion_ht    = NULL,
        suggestion_ft    = NULL,
        suggestion_scalp = NULL,
        updated_at = now()
    WHERE event_id = p_event_id
    RETURNING * INTO v_row;
    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'missione inesistente: %', p_event_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_mission_stop(text,boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_mission_stop(text,boolean) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: segui la partita (live_follow) — prerequisito dello SCALPER pre-match.
-- Inserisce SOLO se assente: non tocca lo stato di un follow già esistente.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_mission_follow(
    p_event_id  text,
    p_home      text,
    p_away      text,
    p_open_date timestamptz
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_exists boolean;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF coalesce(trim(p_home), '') = '' OR coalesce(trim(p_away), '') = '' THEN
        RAISE EXCEPTION 'home/away mancanti';
    END IF;
    IF p_open_date IS NULL THEN
        RAISE EXCEPTION 'open_date mancante';
    END IF;
    SELECT EXISTS (SELECT 1 FROM public.live_follow f WHERE f.event_id = p_event_id)
      INTO v_exists;
    IF NOT v_exists THEN
        INSERT INTO public.live_follow (event_id, home_name, away_name, open_date, status)
        VALUES (p_event_id, trim(p_home), trim(p_away), p_open_date, 'PENDING')
        ON CONFLICT (event_id) DO NOTHING;
    END IF;
    RETURN jsonb_build_object('event_id', p_event_id, 'followed', true,
                              'already', v_exists);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_mission_follow(text,text,text,timestamptz) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_mission_follow(text,text,text,timestamptz) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: missioni di oggi + P&L per gamba (calcolato, MAI duplicato).
--   pre   = scalper_control.stats->>'pnl_locked' (se la partita è armata)
--   ht/ft/scalp = omega_trades per (event_id, phase): realizzato + liability aperta
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_missions()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows    jsonb;
    v_summary jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'kickoff') NULLS LAST), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT to_jsonb(m.*)
               || jsonb_build_object(
                    'legs', (
                        SELECT coalesce(jsonb_object_agg(t.phase, t.agg), '{}'::jsonb)
                          FROM (
                            SELECT tr.phase,
                                   jsonb_build_object(
                                     'realized', coalesce(sum(tr.pnl) FILTER (WHERE tr.status IN ('won','lost','void')), 0),
                                     'open_liability', coalesce(sum(tr.liability) FILTER (WHERE tr.status = 'open' OR (tr.status='pending' AND tr.bet_id IS NOT NULL)), 0),
                                     'n_open', count(*) FILTER (WHERE tr.status = 'open' OR (tr.status='pending' AND tr.bet_id IS NOT NULL)),
                                     'n_settled', count(*) FILTER (WHERE tr.status IN ('won','lost','void')),
                                     'trades', coalesce(jsonb_agg(jsonb_build_object(
                                         'id', tr.id, 'runner_name', tr.runner_name, 'side', tr.side,
                                         'price', tr.price, 'size', tr.size, 'liability', tr.liability,
                                         'status', tr.status, 'pnl', tr.pnl, 'mode', tr.mode)
                                       ORDER BY tr.placed_at), '[]'::jsonb)
                                   ) AS agg
                              FROM public.omega_trades tr
                             WHERE tr.event_id = m.event_id AND tr.phase IS NOT NULL
                             GROUP BY tr.phase
                          ) t
                    ),
                    'scalper', (
                        SELECT jsonb_build_object(
                                 'status', s.status, 'dry_run', s.dry_run,
                                 'pnl_locked', coalesce((s.stats->>'pnl_locked')::numeric, 0))
                          FROM public.scalper_control s
                         WHERE s.event_id = m.event_id
                    ),
                    'followed', EXISTS (SELECT 1 FROM public.live_follow f
                                         WHERE f.event_id = m.event_id)
                  ) AS r
          FROM public.omega_missions m
         -- oggi + ATTIVE e IN PAUSA di giorni passati (audit H3c + review 16/07:
         -- una missione attiva o pausata di ieri era processata/riservata dal
         -- servizio ma INVISIBILE in UI → l'utente non poteva né riprenderla
         -- né chiuderla, e M7 teneva l'evento bloccato per sempre)
         WHERE m.mission_date = (now() AT TIME ZONE 'Europe/Rome')::date
            OR m.status IN ('active','paused')
      ) sub(r);

    SELECT jsonb_build_object(
             'missions_total',  count(*),
             'missions_active', count(*) FILTER (WHERE status = 'active'))
      INTO v_summary
      FROM public.omega_missions
     WHERE mission_date = (now() AT TIME ZONE 'Europe/Rome')::date
        OR status IN ('active','paused');

    RETURN jsonb_build_object('missions', v_rows, 'summary', v_summary);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_missions() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_missions() TO authenticated, service_role;
