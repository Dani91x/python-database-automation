-- ============================================================================
-- omega_bot.sql — controllo, trade e log del bot OMEGA (Correct Score LAY).
--
-- Fonte di verità: Betfair/omega/COSTITUZIONE_OMEGA.md
--
-- Flusso (DB-as-bus, come scalper/tennis): la UI (/omega) chiama le RPC
-- owner-only per ATTIVARE/FERMARE/CONFIGURARE il bot; il servizio locale
-- ``python -m Betfair.omega.omega_service`` legge ``omega_control`` (singleton,
-- id=1) via service_role, per ogni match in finestra piazza UN lay sul Correct
-- Score e scrive lo specchio in ``omega_trades`` + log in ``omega_activity``.
--
-- IDEMPOTENTE. RLS: tabelle NON esposte; accesso UI solo via RPC owner-only.
-- Richiede public.betfair_live_is_owner() (betfair_live_order_queue.sql).
-- ============================================================================

-- 1. omega_control — SINGLETON (id sempre = 1): stato/parametri del bot.
CREATE TABLE IF NOT EXISTS public.omega_control (
    id            INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    status        TEXT NOT NULL DEFAULT 'idle'
                  CHECK (status IN ('idle','running','stopping','stopped','error')),
    mode          TEXT NOT NULL DEFAULT 'paper'
                  CHECK (mode IN ('paper','live')),
    daily_goal    NUMERIC NOT NULL DEFAULT 250 CHECK (daily_goal >= 0 AND daily_goal <= 100000),
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats         JSONB,      -- {events_total, matches_traded, realized_profit, open_liability, target_match,...}
    error         TEXT,
    started_at    TIMESTAMPTZ,
    stopped_at    TIMESTAMPTZ,
    heartbeat_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_control FROM anon, authenticated;
INSERT INTO public.omega_control (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 2. omega_trades — mirror APPEND/UPDATE: un lay per match (I1).
CREATE TABLE IF NOT EXISTS public.omega_trades (
    id               BIGSERIAL PRIMARY KEY,
    event_id         TEXT NOT NULL,
    event_name       TEXT,
    market_id        TEXT,
    selection_id     BIGINT,
    runner_name      TEXT,          -- il punteggio esatto laid, es. "3 - 2"
    side             TEXT NOT NULL DEFAULT 'lay',
    mode             TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper','live')),
    price            NUMERIC,       -- quota lay
    size             NUMERIC,       -- backer stake
    liability        NUMERIC,       -- size*(price-1)
    commission       NUMERIC NOT NULL DEFAULT 0.05,  -- aliquota FISSATA al piazzamento (per settlement coerente)
    target           NUMERIC,       -- profit-target del match al momento del piazzamento
    minute_at_entry  INTEGER,
    score_at_entry   TEXT,
    kickoff          TIMESTAMPTZ,
    -- 'pending' = riga RISERVATA prima del piazzamento reale: l'unique index su
    -- event_id fa da lock (I1) anche cross-processo e oltre i 60s di de-dup Betfair.
    status           TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('pending','open','won','lost','void','error')),
    pnl              NUMERIC NOT NULL DEFAULT 0,
    bet_id           TEXT,
    placed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at       TIMESTAMPTZ,
    meta             JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- un solo trade per (event_id): garanzia hard dell'invariante I1.
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_event ON public.omega_trades (event_id);
CREATE INDEX IF NOT EXISTS idx_omega_trades_status ON public.omega_trades (status);
CREATE INDEX IF NOT EXISTS idx_omega_trades_placed ON public.omega_trades (placed_at DESC);
ALTER TABLE public.omega_trades ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_trades FROM anon, authenticated;

-- 3. omega_activity — log APPEND-ONLY (start, stop, scan, place, skip, settle, error).
CREATE TABLE IF NOT EXISTS public.omega_activity (
    id       BIGSERIAL PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind     TEXT NOT NULL,
    payload  JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_omega_activity_ts ON public.omega_activity (ts DESC);
ALTER TABLE public.omega_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_activity FROM anon, authenticated;

-- Realtime: control + trades pubblicati per la dashboard live (idempotente).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename='omega_control') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.omega_control;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename='omega_trades') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.omega_trades;
    END IF;
EXCEPTION WHEN undefined_object THEN
    -- publication assente (ambiente non-Supabase): si ignora.
    NULL;
END $$;

-- ----------------------------------------------------------------------------
-- RPC: attivazione (avvia il bot; il servizio locale vede status='running').
-- ----------------------------------------------------------------------------
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
        params      = coalesce(p_params, '{}'::jsonb),
        error       = NULL,
        started_at  = now(),
        stopped_at  = NULL,
        updated_at  = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_activate(text,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_activate(text,numeric,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stop (il servizio vede 'stopping' e passa a 'stopped').
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_stop()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.omega_control SET
        status     = CASE WHEN status = 'running' THEN 'stopping' ELSE 'stopped' END,
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_stop() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_stop() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: aggiorna parametri/obiettivo/mode a caldo (senza cambiare lo stato run).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_update_params(
    p_daily_goal  numeric DEFAULT NULL,
    p_params      jsonb DEFAULT NULL,
    p_mode        text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.omega_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NOT NULL AND p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    UPDATE public.omega_control SET
        daily_goal = coalesce(p_daily_goal, daily_goal),
        params     = coalesce(p_params, params),
        mode       = coalesce(p_mode, mode),
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_update_params(numeric,jsonb,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_update_params(numeric,jsonb,text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stato completo per la dashboard (control + aggregati + attività).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_state(
    p_activity_limit integer DEFAULT 50
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl jsonb;
    v_act  jsonb;
    v_agg  jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.omega_control c WHERE c.id = 1;

    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(pnl) FILTER (WHERE status IN ('won','lost','void')), 0),
        'open_liability',  coalesce(sum(liability) FILTER (WHERE status = 'open'), 0),
        'matches_traded',  count(*) FILTER (WHERE status IN ('open','won','lost','void')),
        'matches_open',    count(*) FILTER (WHERE status = 'open'),
        'matches_won',     count(*) FILTER (WHERE status = 'won'),
        'matches_lost',    count(*) FILTER (WHERE status = 'lost')
    ) INTO v_agg FROM public.omega_trades;

    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.omega_activity
             ORDER BY ts DESC
             LIMIT least(greatest(coalesce(p_activity_limit, 50), 1), 300)) a;

    RETURN jsonb_build_object('control', v_ctrl, 'aggregates', v_agg, 'activity', v_act);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_state(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: elenco trade (per lista live + equity curve; ordinabile).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_trades(
    p_limit integer DEFAULT 500
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT * FROM public.omega_trades
             ORDER BY placed_at DESC
             LIMIT least(greatest(coalesce(p_limit, 500), 1), 2000)) t;
    RETURN v_rows;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_trades(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_trades(integer) TO authenticated, service_role;
