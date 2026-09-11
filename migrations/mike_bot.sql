-- ============================================================================
-- mike_bot.sql — controllo, stato partite, trade, log e richieste del BOT MIKE
-- (Under 3.5 / Over 4.5; sezione "Mike" dell'app).
--
-- Modellato 1:1 su safe_strategy_bot.sql (DB-as-bus): la UI chiama le RPC
-- owner-only per ATTIVARE/FERMARE/CONFIGURARE il bot e per accodare richieste
-- (cashout / flatten / skip_event / resume_event); il servizio locale
-- ``python -m Betfair.mike.service`` legge ``mike_control`` (singleton id=1) via
-- service_role, segue le partite sul feed unico (``safe_strategy_scan``, ramo
-- pre-KO O/U acceso con SAFE_PRE_KO_OU_HOURS) e scrive lo stato per partita in
-- ``mike_events`` + lo specchio gambe in ``mike_trades`` + log in ``mike_activity``.
--
-- MODALITÀ: default 'paper'. Il 'live' è SEMPRE una scelta esplicita dell'utente
-- (toggle + conferma in UI). Nessun default live.
--
-- IDEMPOTENTE. RLS: tabelle NON esposte in scrittura; SELECT owner-only per il
-- Realtime. Richiede public.betfair_live_is_owner() (betfair_live_order_queue.sql).
-- Da applicare DOPO betfair_live_order_queue.sql, safe_strategy_scan.sql e
-- safe_strategy_bot.sql (mike_trades ha le stesse colonne di safe_strategy_trades
-- così lo storico generico trading_daily_history potrà servirla — mike_history.sql).
-- ============================================================================

-- 1. mike_control — SINGLETON (id = 1): stato/modalità/parametri/stats del bot.
CREATE TABLE IF NOT EXISTS public.mike_control (
    id            INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    status        TEXT NOT NULL DEFAULT 'idle'
                  CHECK (status IN ('idle','running','stopping','stopped','error')),
    mode          TEXT NOT NULL DEFAULT 'paper'
                  CHECK (mode IN ('paper','live')),
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats         JSONB,
    error         TEXT,
    started_at    TIMESTAMPTZ,
    stopped_at    TIMESTAMPTZ,
    heartbeat_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.mike_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.mike_control FROM anon, authenticated;
INSERT INTO public.mike_control (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 2. mike_events — UNA riga per partita seguita: macchina a stati, gambe (positions),
--    dossier pre-match, quadro live (write-on-change lato servizio).
CREATE TABLE IF NOT EXISTS public.mike_events (
    event_id             TEXT PRIMARY KEY,
    fixture_id           BIGINT,
    event_name           TEXT,
    competition          TEXT,
    league_id            INTEGER,
    ko_at                TIMESTAMPTZ,
    mode                 TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper','live')),
    markets              JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {OU35:{market_id}, OU45:{market_id}}
    state                TEXT NOT NULL DEFAULT 'WATCH'
                         CHECK (state IN ('WATCH','PRE_ENTRY_PENDING','PRE_OPEN','PRE_GREEN_PENDING','HOLD',
                                          'PRE_LAST_ENTRY_PENDING','IDLE_LIVE','LIVE_UNCOVERED',
                                          'LIVE_COVER_PENDING','LIVE_COVERED','LIVE_CLOSING','FLAT',
                                          'REENTRY_PENDING','REENTRY_OPEN','REENTRY_GREEN_PENDING',
                                          'SETTLING','SETTLED','ERROR','SKIPPED')),
    cycle_no             INTEGER NOT NULL DEFAULT 0,
    entry_price_initial  NUMERIC,
    dossier              JSONB NOT NULL DEFAULT '{}'::jsonb,
    live                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    positions            JSONB NOT NULL DEFAULT '[]'::jsonb,   -- gambe (engine.Leg)
    ctx                  JSONB NOT NULL DEFAULT '{}'::jsonb,   -- contesto engine (attempts, reentry, deferred…)
    skipped              BOOLEAN NOT NULL DEFAULT false,
    settled_pnl          NUMERIC,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mike_events_state ON public.mike_events (state);
CREATE INDEX IF NOT EXISTS idx_mike_events_ko    ON public.mike_events (ko_at DESC);
ALTER TABLE public.mike_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.mike_events FROM anon, authenticated;

-- 3. mike_trades — specchio APPEND/UPDATE di ogni gamba (stesse colonne di
--    safe_strategy_trades + role/cycle_no/persistence). 'pending' = riga RISERVATA
--    prima del piazzamento (reserve-first). signal_key = ref della gamba (univoco).
CREATE TABLE IF NOT EXISTS public.mike_trades (
    id               BIGSERIAL PRIMARY KEY,
    event_id         TEXT NOT NULL,
    event_name       TEXT,
    sport            TEXT NOT NULL DEFAULT 'calcio' CHECK (sport IN ('calcio','tennis')),
    strategy         TEXT NOT NULL DEFAULT 'under_entry'
                     CHECK (strategy IN ('under_entry','under_green','under_last','over_cover','under_close',
                                         'over_close','reentry','reentry_green','manual_close')),
    role             TEXT,
    cycle_no         INTEGER NOT NULL DEFAULT 0,
    persistence      TEXT NOT NULL DEFAULT 'LAPSE' CHECK (persistence IN ('LAPSE','PERSIST')),
    market_id        TEXT,
    market_type      TEXT,
    selection_id     BIGINT,
    selection_name   TEXT,
    side             TEXT NOT NULL DEFAULT 'back' CHECK (side IN ('back','lay')),
    mode             TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper','live')),
    price            NUMERIC,
    size             NUMERIC,
    liability        NUMERIC,
    commission       NUMERIC NOT NULL DEFAULT 0.05,
    minute_at_entry  INTEGER,
    score_at_entry   TEXT,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','open','hedged','won','lost','void','error')),
    pnl              NUMERIC NOT NULL DEFAULT 0,
    bet_id           TEXT,
    placed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at       TIMESTAMPTZ,
    origin           TEXT NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','manual')),
    closes_trade_id  BIGINT REFERENCES public.mike_trades(id),
    signal_key       TEXT,
    meta             JSONB NOT NULL DEFAULT '{}'::jsonb
);
DROP INDEX IF EXISTS public.uq_mike_trades_signal;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mike_trades_signal
    ON public.mike_trades (event_id, coalesce(signal_key, ''))
    WHERE origin = 'auto' AND status <> 'error' AND closes_trade_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_mike_trades_status ON public.mike_trades (status);
CREATE INDEX IF NOT EXISTS idx_mike_trades_event  ON public.mike_trades (event_id);
CREATE INDEX IF NOT EXISTS idx_mike_trades_placed ON public.mike_trades (placed_at DESC);
ALTER TABLE public.mike_trades ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.mike_trades FROM anon, authenticated;

-- 4. mike_activity — log APPEND-ONLY (armed, state, place, cancel, settled, error…).
CREATE TABLE IF NOT EXISTS public.mike_activity (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_id  TEXT,
    kind      TEXT NOT NULL,
    payload   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_mike_activity_ts    ON public.mike_activity (ts DESC);
CREATE INDEX IF NOT EXISTS idx_mike_activity_event ON public.mike_activity (event_id);
ALTER TABLE public.mike_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.mike_activity FROM anon, authenticated;

-- 5. mike_requests — coda comandi dalla UI.
CREATE TABLE IF NOT EXISTS public.mike_requests (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('cashout','flatten','skip_event','resume_event','cancel')),
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','error')),
    result       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mike_requests_pending
    ON public.mike_requests (status, created_at) WHERE status = 'pending';
ALTER TABLE public.mike_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.mike_requests FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- Realtime + SELECT owner-only
-- ----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['mike_control','mike_events','mike_trades','mike_activity','mike_requests'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                       WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename=t) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
        END IF;
    END LOOP;
EXCEPTION WHEN undefined_object THEN
    NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['mike_control','mike_events','mike_trades','mike_activity','mike_requests'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_owner', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (public.betfair_live_is_owner())',
            t || '_select_owner', t);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
        EXECUTE format('REVOKE SELECT ON TABLE public.%I FROM anon', t);
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- RPC owner-only (specchio di safe_*)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.mike_activate(p_mode text DEFAULT 'paper', p_params jsonb DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.mike_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NULL OR p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    UPDATE public.mike_control SET
        status = 'running', mode = p_mode, params = coalesce(p_params, params),
        error = NULL, started_at = now(), stopped_at = NULL, updated_at = now()
    WHERE id = 1 RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.mike_activate(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.mike_activate(text,jsonb) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.mike_stop()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.mike_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.mike_control SET
        status = CASE WHEN status = 'running' THEN 'stopping' ELSE 'stopped' END,
        updated_at = now()
    WHERE id = 1 RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.mike_stop() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.mike_stop() TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.mike_update_params(p_params jsonb, p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.mike_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NOT NULL AND p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    UPDATE public.mike_control SET
        params = coalesce(p_params, params),
        mode = coalesce(p_mode, mode),
        updated_at = now()
    WHERE id = 1 RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.mike_update_params(jsonb,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.mike_update_params(jsonb,text) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_mike_state()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl   jsonb;
    v_events jsonb;
    v_trades jsonb;
    v_agg    jsonb;
    v_act    jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.mike_control c WHERE c.id = 1;
    SELECT coalesce(jsonb_agg(to_jsonb(e.*) ORDER BY e.ko_at ASC), '[]'::jsonb) INTO v_events
      FROM (SELECT * FROM public.mike_events
             WHERE state NOT IN ('SETTLED','SKIPPED','ERROR') OR updated_at >= now() - interval '24 hours'
             ORDER BY ko_at ASC LIMIT 200) e;
    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb) INTO v_trades
      FROM (SELECT * FROM public.mike_trades ORDER BY placed_at DESC LIMIT 200) t;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb) INTO v_act
      FROM (SELECT * FROM public.mike_activity ORDER BY ts DESC LIMIT 100) a;
    SELECT jsonb_build_object(
        'realized_total',  coalesce(sum(pnl) FILTER (WHERE status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(pnl) FILTER (WHERE status IN ('won','lost','void')
                               AND settled_at >= (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome')), 0),
        'open_liability',  coalesce(sum(liability) FILTER (WHERE status IN ('open','hedged')), 0),
        'open_count',      count(*) FILTER (WHERE status IN ('open','hedged')),
        'won',             count(*) FILTER (WHERE status = 'won'),
        'lost',            count(*) FILTER (WHERE status = 'lost')
    ) INTO v_agg FROM public.mike_trades;
    RETURN jsonb_build_object('control', v_ctrl, 'events', v_events, 'trades', v_trades,
                              'activity', v_act, 'aggregates', v_agg);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_state() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_state() TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_mike_trades(p_limit integer DEFAULT 200)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb) INTO v_rows
      FROM (SELECT * FROM public.mike_trades ORDER BY placed_at DESC
             LIMIT least(greatest(coalesce(p_limit, 200), 1), 2000)) t;
    RETURN v_rows;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_trades(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_trades(integer) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.mike_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id      bigint;
    v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('cashout','flatten','skip_event','resume_event','cancel') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;
    IF coalesce(v_payload->>'event_id','') = '' THEN
        RAISE EXCEPTION 'payload senza event_id';
    END IF;
    INSERT INTO public.mike_requests (kind, payload) VALUES (p_kind, v_payload) RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.mike_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.mike_request(text,jsonb) TO authenticated, service_role;
