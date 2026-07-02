-- ============================================================================
-- scalper_bot.sql — controllo, telemetria e log dello SCALPER BOT pre-match.
--
-- Flusso: la UI (Segui Live → pannello Scalper) chiama le RPC owner-only per
-- ATTIVARE/FERMARE il bot su un evento seguito; il servizio locale
-- ``scalper_service.py`` (processo SEPARATO dal runner, decisione 30/06)
-- legge ``scalper_control`` via service_role, avvia una sessione flumine
-- per evento e scrive stato/heartbeat/statistiche + log append-only in
-- ``scalper_activity`` (debug e analisi veloci).
--
-- Modalita' (``mode``):
--   'maker' = tradizionale validata (maker neutro two-sided)
--   'bias'  = SOLO direzionale (quota solo il lato dei motori; se il
--             connettore non trova consenso l'evento resta in attesa)
--   'both'  = maker neutro + bias sulle selezioni con consenso
-- ``dry_run`` TRUE (default) = tutto cablato e verificato, NESSUN ordine
-- reale: il bot logga le quote che AVREBBE piazzato.
--
-- IDEMPOTENTE. RLS: tabelle NON esposte; accesso UI solo via RPC owner-only
-- (pattern identico a betfair_live_xhedge/risk_rules). Richiede
-- public.betfair_live_is_owner() (security_lockdown.sql).
-- ============================================================================

-- 1. scalper_control — una riga per evento (l'ultima attivazione vince).
CREATE TABLE IF NOT EXISTS public.scalper_control (
    event_id      TEXT PRIMARY KEY REFERENCES public.live_follow(event_id)
                  ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'requested'
                  CHECK (status IN ('requested','arming','armed','running',
                                    'stopping','stopped','done','error')),
    mode          TEXT NOT NULL DEFAULT 'maker'
                  CHECK (mode IN ('maker','bias','both')),
    dry_run       BOOLEAN NOT NULL DEFAULT TRUE,
    stake         NUMERIC NOT NULL DEFAULT 25 CHECK (stake >= 2 AND stake <= 500),
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- override parametri strategia
    -- esito del CONNETTORE (bias resolver): scritti dal servizio, letti dalla UI
    bias          JSONB,          -- {selection_id: 'BACK'|'LAY'} oppure null
    bias_meta     JSONB,          -- {consenso, direzione, prob, edge, motivi[]}
    stats         JSONB,          -- {cicli, ordini, fill, scratch, stop, pnl_locked,...}
    error         TEXT,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    stopped_at    TIMESTAMPTZ,
    heartbeat_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.scalper_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scalper_control FROM anon, authenticated;

-- 2. scalper_activity — log APPEND-ONLY per debug/analisi (dry_place, place,
--    cancel, fill, scratch, stop, cycle, flatten, state, error, info).
CREATE TABLE IF NOT EXISTS public.scalper_activity (
    id        BIGSERIAL PRIMARY KEY,
    event_id  TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind      TEXT NOT NULL,
    payload   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_scalper_activity_event_ts
    ON public.scalper_activity (event_id, ts DESC);

ALTER TABLE public.scalper_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scalper_activity FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- RPC: attivazione (upsert). Ri-attivare un evento fermo = nuova richiesta.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_activate(
    p_event_id text,
    p_mode     text DEFAULT 'maker',
    p_dry_run  boolean DEFAULT true,
    p_stake    numeric DEFAULT 25,
    p_params   jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.scalper_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_mode NOT IN ('maker','bias','both') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    IF p_stake IS NULL OR p_stake < 2 OR p_stake > 500 THEN
        RAISE EXCEPTION 'stake fuori range [2,500]: %', p_stake;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.live_follow f WHERE f.event_id = p_event_id) THEN
        RAISE EXCEPTION 'evento non seguito: % (segui prima la partita)', p_event_id;
    END IF;

    INSERT INTO public.scalper_control AS c
        (event_id, status, mode, dry_run, stake, params,
         bias, bias_meta, stats, error,
         requested_at, started_at, stopped_at, heartbeat_at, updated_at)
    VALUES
        (p_event_id, 'requested', p_mode, coalesce(p_dry_run, true),
         p_stake, coalesce(p_params, '{}'::jsonb),
         NULL, NULL, NULL, NULL, now(), NULL, NULL, NULL, now())
    ON CONFLICT (event_id) DO UPDATE SET
        status       = 'requested',
        mode         = EXCLUDED.mode,
        dry_run      = EXCLUDED.dry_run,
        stake        = EXCLUDED.stake,
        params       = EXCLUDED.params,
        bias         = NULL,
        bias_meta    = NULL,
        error        = NULL,
        requested_at = now(),
        started_at   = NULL,
        stopped_at   = NULL,
        updated_at   = now()
    WHERE c.status IN ('stopped','done','error','requested','armed')
    RETURNING * INTO v_row;

    IF v_row IS NULL THEN
        RAISE EXCEPTION 'scalper gia'' attivo su %: fermalo prima', p_event_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_activate(text,text,boolean,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_activate(text,text,boolean,numeric,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stop (il servizio vede 'stopping', chiude flat e mette 'stopped').
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_stop(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.scalper_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.scalper_control
       SET status = CASE WHEN status IN ('running','arming','armed')
                         THEN 'stopping' ELSE 'stopped' END,
           updated_at = now()
     WHERE event_id = p_event_id
    RETURNING * INTO v_row;
    IF v_row IS NULL THEN
        RAISE EXCEPTION 'nessuna attivazione scalper per %', p_event_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_stop(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_stop(text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stato + ultime attivita' (per il pannello UI, polling).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_scalper_state(
    p_event_id text,
    p_activity_limit integer DEFAULT 40
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl jsonb;
    v_act  jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl
      FROM public.scalper_control c WHERE c.event_id = p_event_id;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.scalper_activity
             WHERE event_id = p_event_id
             ORDER BY ts DESC
             LIMIT least(greatest(coalesce(p_activity_limit, 40), 1), 200)) a;
    RETURN jsonb_build_object('control', v_ctrl, 'activity', v_act);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_scalper_state(text,integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_scalper_state(text,integer) TO authenticated, service_role;
