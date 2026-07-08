-- ============================================================================
-- tennis_orders.sql — ORDINI LIVE TENNIS: coda comandi + specchio ordini/posizioni.
--
-- BACKEND DEDICATO AL TENNIS. Regola d'oro (richiesta esplicita utente): Tennis e
-- Calcio NON condividono MAI dati. Questo file crea solo tabelle/RPC `tennis_*` e
-- non tocca alcuna tabella/RPC del calcio (nessuna contaminazione). Mirror di
-- betfair_live_order_queue.sql, ma su storage tennis separato.
--
-- Flusso (mirror di lib/liveOrders.ts, contratto frozen frontend/src/lib/tennis.ts):
--   frontend → request_tennis_live_order(p)  (accoda, idempotente su client_ref)
--   worker locale tennis → CLAIM atomico → place/cancel/replace/greenup/dutch/...
--   frontend → get_tennis_live_order(p_id)   (poll fino a done/error)
--   frontend → get_tennis_live_orders(p_market_id,p_mode)    -> {rows} LiveOrderRow[]
--   frontend → get_tennis_live_positions(p_market_id,p_mode) -> {rows} LivePositionRow[]
--
-- MONEY-CRITICAL (denaro REALE in mode='live'): tutte le RPC sono OWNER-ONLY. Le
-- tabelle specchio sono scritte dal backend come service_role (bypassa la RLS).
-- IDEMPOTENTE. RPC SECURITY DEFINER, search_path fisso.
-- ============================================================================

-- ============================================================================
-- 0)  tennis_is_owner — guard OWNER-ONLY dedicato al tennis (denaro REALE).
-- Stesso regime di sicurezza del lockdown calcio (betfair_live_is_owner), ma
-- DEFINITO QUI per mantenere i file tennis autoconsistenti (nessuna dipendenza dai
-- file calcio). Autorizzati: service_role (backend/runner) oppure owner loggato
-- (email del JWT == owner). CREATE OR REPLACE → idempotente in ogni file tennis.
-- (Se cambi email owner: aggiornala anche in tennis_bots.sql, security_lockdown.sql,
--  src/lib/auth-config.ts.)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.tennis_is_owner()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT
        coalesce(auth.jwt() ->> 'role', '') = 'service_role'
        OR session_user = 'service_role'
        OR lower(coalesce(auth.jwt() ->> 'email', '')) = 'daniele.ritrovato@gmail.com';
$$;
REVOKE ALL    ON FUNCTION public.tennis_is_owner() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_is_owner() TO service_role;

-- ============================================================================
-- 1.1  tennis_live_order_queue — coda comandi (payload jsonb + dedup client_ref).
-- client_ref UNIQUE → enqueue idempotente (retry sicuro, niente doppio ordine).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tennis_live_order_queue (
    id           BIGSERIAL PRIMARY KEY,
    client_ref   TEXT NOT NULL UNIQUE,                   -- idempotency key (UUID dal frontend)
    payload      JSONB NOT NULL,                         -- LiveOrderCommand + client_ref
    status       TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','error')),
    result       JSONB,                                  -- LiveOrderResult
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tloq_pending
    ON public.tennis_live_order_queue (id) WHERE status = 'pending';

ALTER TABLE public.tennis_live_order_queue ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_live_order_queue FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_live_order_queue_id_seq FROM anon, authenticated;

-- ============================================================================
-- 1.2  tennis_live_orders — specchio ordini (mirror betfair_live_orders / LiveOrderRow).
-- Scritta dal backend come service_role (write-on-change). Sola lettura UI via RPC.
--   source = 'manual' | bot_key (tag dell'origine: mano o bot).
--   mode   = OFF | PAPER | LIVE (modalità ordini del runner tennis).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tennis_live_orders (
    id                    BIGSERIAL PRIMARY KEY,
    bet_id                TEXT,
    client_order_ref      TEXT NOT NULL,                 -- ref INTERNO (awtq<req_id>); NOT NULL per l'unique key
    request_id            BIGINT,                        -- → tennis_live_order_queue.id
    mode                  TEXT NOT NULL DEFAULT 'paper'
                              CHECK (mode IN ('paper','live')), -- lowercase (speculare al writer Python)
    source                TEXT NOT NULL DEFAULT 'manual',-- 'manual' | bot_key
    event_id              TEXT,
    market_id             TEXT NOT NULL,
    selection_id          BIGINT NOT NULL,
    handicap              NUMERIC NOT NULL DEFAULT 0,
    side                  TEXT NOT NULL CHECK (side IN ('back','lay')),
    order_type            TEXT NOT NULL DEFAULT 'LIMIT',
    price                 NUMERIC,
    size                  NUMERIC,
    size_matched          NUMERIC NOT NULL DEFAULT 0,
    size_remaining        NUMERIC NOT NULL DEFAULT 0,
    size_cancelled        NUMERIC NOT NULL DEFAULT 0,
    size_lapsed           NUMERIC NOT NULL DEFAULT 0,
    size_voided           NUMERIC NOT NULL DEFAULT 0,
    average_price_matched NUMERIC NOT NULL DEFAULT 0,
    status                TEXT NOT NULL,                 -- flumine OrderStatus
    persistence           TEXT,
    placed_at             TIMESTAMPTZ,
    matched_at            TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chiave UNICA (mode, client_order_ref) NON parziale → arbitro per ON CONFLICT upsert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tlo_order_key
    ON public.tennis_live_orders (mode, client_order_ref);
CREATE INDEX IF NOT EXISTS idx_tlo_market
    ON public.tennis_live_orders (market_id);

ALTER TABLE public.tennis_live_orders ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_live_orders FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_live_orders_id_seq FROM anon, authenticated;

-- ============================================================================
-- 1.3  tennis_live_positions — esposizioni per selezione (mirror betfair_live_positions
-- / LivePositionRow). Numeri presi dal blotter flumine, MAI ricalcolati a mano.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tennis_live_positions (
    id                      BIGSERIAL PRIMARY KEY,
    mode                    TEXT NOT NULL DEFAULT 'paper'
                                CHECK (mode IN ('paper','live')),  -- lowercase (speculare al writer Python)
    event_id                TEXT,
    market_id               TEXT NOT NULL,
    selection_id            BIGINT NOT NULL,
    handicap                NUMERIC NOT NULL DEFAULT 0,
    matched_if_win          NUMERIC NOT NULL DEFAULT 0,
    matched_if_lose         NUMERIC NOT NULL DEFAULT 0,
    worst_if_win            NUMERIC NOT NULL DEFAULT 0,
    worst_if_lose           NUMERIC NOT NULL DEFAULT 0,
    selection_exposure      NUMERIC NOT NULL DEFAULT 0,
    unmatched_back_exposure NUMERIC NOT NULL DEFAULT 0,
    unmatched_lay_exposure  NUMERIC NOT NULL DEFAULT 0,
    net_position            NUMERIC NOT NULL DEFAULT 0,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tlp_unique
    ON public.tennis_live_positions (mode, market_id, selection_id, handicap);
CREATE INDEX IF NOT EXISTS idx_tlp_market
    ON public.tennis_live_positions (market_id);

ALTER TABLE public.tennis_live_positions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_live_positions FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.tennis_live_positions_id_seq FROM anon, authenticated;

-- ============================================================================
-- 2.1  request_tennis_live_order(p) -> bigint. Accoda UN comando. Idempotente su
-- client_ref: se la stessa richiesta è già in coda, ne ritorna l'id senza duplicare.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_tennis_live_order(p jsonb)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id         bigint;
    v_client_ref text := nullif(p->>'client_ref', '');
    v_action     text := nullif(p->>'action', '');
    v_mode       text := nullif(p->>'mode', '');
BEGIN
    -- OWNER-ONLY: denaro REALE in mode='live'.
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_action IS NULL THEN
        RAISE EXCEPTION 'action obbligatoria';
    END IF;
    IF v_mode IS NULL OR lower(v_mode) NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;

    -- Whitelist azioni (difesa in profondità, come il calcio).
    IF lower(v_action) NOT IN ('place','cancel','replace','greenup','cashout_all','cashout_event') THEN
        RAISE EXCEPTION 'action non valida: %', v_action;
    END IF;

    -- Bound numerici money-critical su place/replace: prezzo ladder Betfair [1.01, 1000],
    -- size/liability > 0. Blocca prezzi/size assurdi PRIMA di raggiungere flumine.
    IF lower(v_action) = 'place' THEN
        IF (p->>'price') IS NULL OR (p->>'price')::numeric < 1.01 OR (p->>'price')::numeric > 1000 THEN
            RAISE EXCEPTION 'price fuori range [1.01,1000]: %', (p->>'price');
        END IF;
        IF coalesce((p->>'size')::numeric, 0) <= 0 THEN
            RAISE EXCEPTION 'size deve essere > 0';
        END IF;
    ELSIF lower(v_action) = 'replace' THEN
        IF (p->>'new_price') IS NOT NULL
           AND ((p->>'new_price')::numeric < 1.01 OR (p->>'new_price')::numeric > 1000) THEN
            RAISE EXCEPTION 'new_price fuori range [1.01,1000]: %', (p->>'new_price');
        END IF;
    END IF;

    -- idempotenza: stesso client_ref → stessa richiesta.
    SELECT id INTO v_id
      FROM public.tennis_live_order_queue
     WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.tennis_live_order_queue (client_ref, payload)
    VALUES (v_client_ref, p)
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id
          FROM public.tennis_live_order_queue
         WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;

-- ============================================================================
-- 2.2  get_tennis_live_order(p_id) -> json {status, result}. Poll dal frontend.
-- Su 'error', se result è NULL viene sintetizzato {error} così la UI mostra il motivo.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_live_order(p_id bigint)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_live_order_queue;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_id IS NULL OR p_id <= 0 THEN
        RAISE EXCEPTION 'p_id non valido';
    END IF;

    SELECT * INTO v_row FROM public.tennis_live_order_queue WHERE id = p_id;
    IF v_row.id IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN json_build_object(
        'status', v_row.status,
        'result', coalesce(
                    v_row.result,
                    CASE WHEN v_row.status = 'error'
                         THEN jsonb_build_object('error', coalesce(v_row.error, 'comando non eseguito'))
                         ELSE NULL END
                  )
    );
END;
$$;

-- ============================================================================
-- 2.3  get_tennis_live_orders(p_market_id, p_mode) -> json {rows: LiveOrderRow[]}.
-- Filtra per mercato e (case-insensitive) per mode. p_mode NULL/'' = tutte le mode.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_live_orders(p_market_id text, p_mode text)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
    v_mode text := nullif(p_mode, '');
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_market_id IS NULL OR length(p_market_id) > 32 THEN
        RAISE EXCEPTION 'p_market_id non valido';
    END IF;

    SELECT coalesce(json_agg(to_jsonb(o.*) ORDER BY o.updated_at DESC), '[]'::json)
      INTO v_rows
      FROM public.tennis_live_orders o
     WHERE o.market_id = p_market_id
       AND (v_mode IS NULL OR lower(o.mode) = lower(v_mode));

    RETURN json_build_object('rows', v_rows);
END;
$$;

-- ============================================================================
-- 2.4  get_tennis_live_positions(p_market_id, p_mode) -> json {rows: LivePositionRow[]}.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_tennis_live_positions(p_market_id text, p_mode text)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
    v_mode text := nullif(p_mode, '');
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_market_id IS NULL OR length(p_market_id) > 32 THEN
        RAISE EXCEPTION 'p_market_id non valido';
    END IF;

    SELECT coalesce(json_agg(to_jsonb(pz.*) ORDER BY pz.selection_id), '[]'::json)
      INTO v_rows
      FROM public.tennis_live_positions pz
     WHERE pz.market_id = p_market_id
       AND (v_mode IS NULL OR lower(pz.mode) = lower(v_mode));

    RETURN json_build_object('rows', v_rows);
END;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- Il filtro OWNER-ONLY è DENTRO le RPC (tennis_is_owner): un altro authenticated
-- riceve subito RAISE 'non autorizzato (owner-only)'.
-- ============================================================================
REVOKE ALL    ON FUNCTION public.request_tennis_live_order(jsonb)       FROM public, anon;
GRANT EXECUTE ON FUNCTION public.request_tennis_live_order(jsonb)       TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_live_order(bigint)          FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_live_order(bigint)          TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_live_orders(text, text)     FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_live_orders(text, text)     TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_live_positions(text, text)  FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_live_positions(text, text)  TO authenticated, service_role;
