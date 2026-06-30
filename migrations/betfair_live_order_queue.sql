-- ============================================================================
-- betfair_live_order_queue.sql — FOUNDATION LIVE TRADING (Fase 1).
-- Coda comandi ordini (place/cancel/replace/place_submin) mediata dal DB, come
-- lo stream e betfair_order_queue.sql, ma per il RUNNER live (Betfair/stream/):
--   frontend → request_betfair_live_order(p)   (accoda, idempotente su client_ref)
--   worker nel runner (live_order_worker)       → CLAIM atomico → place/cancel/replace
--   frontend → get_betfair_live_order(id)        (poll fino a done/error)
-- + 2 tabelle SPECCHIO scritte dal backend (service_role, bypassa RLS):
--   betfair_live_orders     ← LiveTradingStrategy.process_orders (write-on-change)
--   betfair_live_positions  ← blotter.get_exposures (esposizioni per selezione)
--   lette dalla UI via get_live_orders / get_live_positions.
--
-- MONEY-CRITICAL (soldi veri in mode='live'). Garanzie anti-doppio-ordine REALI:
--  * client_ref UNIQUE → la stessa richiesta del frontend non crea due righe
--    (enqueue idempotente, retry sicuro su glitch di rete).
--  * il worker fa CLAIM atomico (pending→processing) → una sola esecuzione per riga.
--  Queste due sono l'INTERA garanzia. NB: NON esiste un customerRef Betfair "deterministico":
--  ciò che flumine invia all'Exchange è customer_order_ref = name_hash+sep+order.id (order.id
--  = uuid1, non deterministico). Il nostro awlq<id> (client_order_ref nello specchio sotto) è
--  solo un ref INTERNO di correlazione richiesta↔ordine per la UI/specchio: non viaggia verso
--  Betfair e non fa de-dup lato Exchange.
--
-- IDEMPOTENTE: CREATE TABLE/INDEX/FUNCTION IF NOT EXISTS / OR REPLACE.
-- Tutte le RPC: SECURITY DEFINER, SET search_path = public, pg_temp.
-- Grant: REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- ============================================================================


-- ============================================================================
-- 1.1  betfair_live_order_requests — coda comandi (place/cancel/replace/place_submin)
-- Stesso pattern di betfair_order_requests (client_ref UNIQUE + claim atomico).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_order_requests (
    id             BIGSERIAL PRIMARY KEY,
    client_ref     TEXT NOT NULL UNIQUE,            -- idempotency key (UUID dal frontend)
    action         TEXT NOT NULL
                      CHECK (action IN ('place','cancel','replace','place_submin')),
    mode           TEXT NOT NULL
                      CHECK (mode IN ('paper','live')),
    market_id      TEXT,                            -- obblig. per place/place_submin (validato in RPC)
    selection_id   BIGINT,                          -- obblig. per place/place_submin
    handicap       NUMERIC NOT NULL DEFAULT 0,
    side           TEXT
                      CHECK (side IS NULL OR side IN ('back','lay')),
    order_type     TEXT NOT NULL DEFAULT 'LIMIT'
                      CHECK (order_type IN ('LIMIT','LIMIT_ON_CLOSE','MARKET_ON_CLOSE')),
    price          NUMERIC
                      CHECK (price IS NULL OR price BETWEEN 1.01 AND 1000),
    size           NUMERIC,
    liability      NUMERIC,
    persistence    TEXT NOT NULL DEFAULT 'LAPSE'
                      CHECK (persistence IN ('LAPSE','PERSIST','MARKET_ON_CLOSE')),
    time_in_force  TEXT
                      CHECK (time_in_force IS NULL OR time_in_force IN ('FILL_OR_KILL')),
    min_fill_size  NUMERIC,
    bet_id         TEXT,                            -- obblig. per cancel/replace
    new_price      NUMERIC
                      CHECK (new_price IS NULL OR new_price BETWEEN 1.01 AND 1000),
    size_reduction NUMERIC,
    params         JSONB,
    status         TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','processing','done','error')),
    result         JSONB,
    error          TEXT,
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_blor_pending
    ON public.betfair_live_order_requests (id) WHERE status = 'pending';

ALTER TABLE public.betfair_live_order_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_order_requests FROM anon, authenticated;


-- ============================================================================
-- 1.2  betfair_live_orders — specchio ordini (write-on-change da process_orders).
-- Scritta dal backend come service_role. Sola lettura per la UI via RPC.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_orders (
    id                    BIGSERIAL PRIMARY KEY,
    bet_id                TEXT,                       -- NULL finché PENDING (non ancora assegnato)
    client_order_ref      TEXT NOT NULL,              -- ref INTERNO awlq<req_id> (sempre valorizzato; NON il customerRef Betfair). NOT NULL: l'indice unique parziale idx_blo_mode_cref si appoggia su questo finché bet_id è NULL (NULL!=NULL romperebbe l'unicità)
    request_id            BIGINT,                     -- FK logica → betfair_live_order_requests.id
    mode                  TEXT NOT NULL
                             CHECK (mode IN ('paper','live')),
    event_id              TEXT,
    market_id             TEXT NOT NULL,
    selection_id          BIGINT NOT NULL,
    handicap              NUMERIC NOT NULL DEFAULT 0,
    side                  TEXT NOT NULL
                             CHECK (side IN ('back','lay')),
    order_type            TEXT NOT NULL DEFAULT 'LIMIT',
    price                 NUMERIC,
    size                  NUMERIC,
    size_matched          NUMERIC NOT NULL DEFAULT 0,
    size_remaining        NUMERIC NOT NULL DEFAULT 0,
    size_cancelled        NUMERIC NOT NULL DEFAULT 0,
    size_lapsed           NUMERIC NOT NULL DEFAULT 0,
    size_voided           NUMERIC NOT NULL DEFAULT 0,
    average_price_matched NUMERIC NOT NULL DEFAULT 0,
    status                TEXT NOT NULL,              -- flumine OrderStatus
    persistence           TEXT,
    placed_at             TIMESTAMPTZ,
    matched_at            TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- upsert per (mode, bet_id) quando bet_id è assegnato; fallback (mode, client_order_ref)
-- finché bet_id è NULL. Due indici UNIQUE PARZIALI coprono i due casi senza collidere.
CREATE UNIQUE INDEX IF NOT EXISTS idx_blo_mode_bet
    ON public.betfair_live_orders (mode, bet_id) WHERE bet_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_blo_mode_cref
    ON public.betfair_live_orders (mode, client_order_ref) WHERE bet_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_blo_market
    ON public.betfair_live_orders (market_id);

ALTER TABLE public.betfair_live_orders ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_orders FROM anon, authenticated;


-- ============================================================================
-- 1.3  betfair_live_positions — esposizioni per selezione (da blotter.get_exposures).
-- Una riga per (mode, market_id, selection_id, handicap). Numeri MAI ricalcolati a
-- mano: presi da flumine.markets.blotter.Blotter.get_exposures / selection_exposure.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_positions (
    id                      BIGSERIAL PRIMARY KEY,
    mode                    TEXT NOT NULL
                               CHECK (mode IN ('paper','live')),
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_blp_unique
    ON public.betfair_live_positions (mode, market_id, selection_id, handicap);
CREATE INDEX IF NOT EXISTS idx_blp_market
    ON public.betfair_live_positions (market_id);

ALTER TABLE public.betfair_live_positions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_positions FROM anon, authenticated;


-- ============================================================================
-- 2.0  betfair_live_is_owner — guard OWNER-ONLY (money-critical, denaro REALE).
-- Stesso regime di sicurezza del lockdown (security_lockdown.sql): l'UNICO utente
-- autorizzato è l'owner, identificato dalla stessa email del trigger
-- block_non_owner_signup. Qui NON ci affidiamo solo al fatto che "solo l'owner può
-- esistere in auth.users": mettiamo un controllo ESPLICITO dentro ogni RPC, così
-- anche se domani si riaprissero i signup, nessun altro 'authenticated' può
-- accodare ordini reali o leggere righe altrui.
--
-- Autorizzati:
--   * backend/runner come service_role  (role claim = service_role, oppure
--     connessione diretta col ruolo service_role) → bypassa, come la RLS;
--   * owner loggato                      (email del JWT == owner del lockdown).
-- NB: STABLE/SECURITY DEFINER ma legge solo i claim di sessione (auth.jwt()),
-- nessun accesso a tabelle: non aggira nulla, decide solo "chi sei".
-- (Se cambi email owner: aggiornala QUI, in security_lockdown.sql e in
--  src/lib/auth-config.ts.)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.betfair_live_is_owner()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT
        -- backend/runner: service_role (via PostgREST col role claim, o diretto)
        coalesce(auth.jwt() ->> 'role', '') = 'service_role'
        OR session_user = 'service_role'
        -- owner loggato: stessa email del lockdown (block_non_owner_signup)
        OR lower(coalesce(auth.jwt() ->> 'email', '')) = 'daniele.ritrovato@gmail.com';
$$;

-- non esporla come probe pubblica: la usano solo le RPC SECURITY DEFINER qui sotto
-- (che la chiamano come owner della funzione → hanno comunque EXECUTE).
REVOKE ALL ON FUNCTION public.betfair_live_is_owner() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.betfair_live_is_owner() TO service_role;


-- ============================================================================
-- 2.1  request_betfair_live_order — accoda UN comando. Idempotente su client_ref:
-- se la stessa richiesta è già in coda, ne ritorna l'id senza crearne un'altra.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.request_betfair_live_order(p jsonb)
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
    v_price      numeric := nullif(p->>'price', '')::numeric;
    v_new_price  numeric := nullif(p->>'new_price', '')::numeric;
BEGIN
    -- OWNER-ONLY: denaro REALE in mode='live'. Nessun altro authenticated accoda.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- obbligatori comuni
    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_action IS NULL OR v_action NOT IN ('place','cancel','replace','place_submin') THEN
        RAISE EXCEPTION 'action non valida (place|cancel|replace|place_submin)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;

    -- obbligatori per azione
    IF v_action IN ('place','place_submin') THEN
        IF nullif(p->>'market_id','') IS NULL
           OR nullif(p->>'selection_id','') IS NULL
           OR nullif(p->>'side','') IS NULL
           OR v_price IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: market_id, selection_id, side, price obbligatori';
        END IF;
        -- size O liability: serve almeno uno per dimensionare l'ordine (back→size, lay→size|liability).
        IF nullif(p->>'size','') IS NULL AND nullif(p->>'liability','') IS NULL THEN
            RAISE EXCEPTION 'place/place_submin: size o liability obbligatorio';
        END IF;
    ELSIF v_action = 'cancel' THEN
        IF nullif(p->>'bet_id','') IS NULL THEN
            RAISE EXCEPTION 'cancel: bet_id obbligatorio';
        END IF;
    ELSIF v_action = 'replace' THEN
        IF nullif(p->>'bet_id','') IS NULL OR v_new_price IS NULL THEN
            RAISE EXCEPTION 'replace: bet_id + new_price obbligatori';
        END IF;
    END IF;

    -- range Betfair (chiarezza all'accodamento, non solo al piazzamento)
    IF v_price IS NOT NULL AND v_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'price fuori range Betfair [1.01, 1000]';
    END IF;
    IF v_new_price IS NOT NULL AND v_new_price NOT BETWEEN 1.01 AND 1000 THEN
        RAISE EXCEPTION 'new_price fuori range Betfair [1.01, 1000]';
    END IF;

    -- idempotenza: stesso client_ref → stessa richiesta
    SELECT id INTO v_id
      FROM public.betfair_live_order_requests
     WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.betfair_live_order_requests
        (client_ref, action, mode, market_id, selection_id, handicap, side,
         order_type, price, size, liability, persistence, time_in_force,
         min_fill_size, bet_id, new_price, size_reduction, params)
    VALUES (
        v_client_ref,
        v_action,
        v_mode,
        nullif(p->>'market_id',''),
        nullif(p->>'selection_id','')::bigint,
        coalesce(nullif(p->>'handicap','')::numeric, 0),
        nullif(p->>'side',''),
        coalesce(nullif(p->>'order_type',''), 'LIMIT'),
        v_price,
        nullif(p->>'size','')::numeric,
        nullif(p->>'liability','')::numeric,
        coalesce(nullif(p->>'persistence',''), 'LAPSE'),
        nullif(p->>'time_in_force',''),
        nullif(p->>'min_fill_size','')::numeric,
        nullif(p->>'bet_id',''),
        v_new_price,
        nullif(p->>'size_reduction','')::numeric,
        CASE WHEN p ? 'params' THEN p->'params' ELSE NULL END
    )
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    -- se ON CONFLICT ha saltato (race tra due insert concorrenti), recupera l'id.
    IF v_id IS NULL THEN
        SELECT id INTO v_id
          FROM public.betfair_live_order_requests
         WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;


-- ============================================================================
-- 2.2  get_betfair_live_order — stato/esito di un comando in coda (poll dal frontend).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_betfair_live_order(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    -- OWNER-ONLY: non far leggere a nessun altro lo stato di ordini reali.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- guard di sanità input (coerente con get_live_orders/get_live_positions): l'id è una
    -- BIGSERIAL PRIMARY KEY → sempre > 0. NULL/<=0 è una richiesta malformata, non una riga.
    IF p_id IS NULL THEN
        RAISE EXCEPTION 'p_id nullo';
    END IF;
    IF p_id <= 0 THEN
        RAISE EXCEPTION 'p_id non valido';
    END IF;

    SELECT to_jsonb(r.*)
      INTO v_row
      FROM public.betfair_live_order_requests r
     WHERE r.id = p_id;

    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.3  get_live_orders — specchio ordini di un mercato. { rows: [ ... ] }.
-- Ritorna entrambe le mode (la UI filtra sul badge attivo).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_orders(p_market_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    -- OWNER-ONLY: lo specchio ordini espone righe su denaro reale.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF p_market_id IS NULL THEN
        RAISE EXCEPTION 'p_market_id nullo';
    END IF;
    -- guardia lunghezza: i market_id Betfair sono brevi (es. 1.234567890).
    IF length(p_market_id) > 32 THEN
        RAISE EXCEPTION 'p_market_id non valido';
    END IF;

    SELECT coalesce(jsonb_agg(to_jsonb(o.*) ORDER BY o.updated_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM public.betfair_live_orders o
     WHERE o.market_id = p_market_id;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- 2.4  get_live_positions — esposizioni/posizioni di un mercato. { rows: [ ... ] }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_positions(p_market_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    -- OWNER-ONLY: esposizioni/posizioni su denaro reale.
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF p_market_id IS NULL THEN
        RAISE EXCEPTION 'p_market_id nullo';
    END IF;
    IF length(p_market_id) > 32 THEN
        RAISE EXCEPTION 'p_market_id non valido';
    END IF;

    SELECT coalesce(jsonb_agg(to_jsonb(pz.*) ORDER BY pz.selection_id), '[]'::jsonb)
      INTO v_rows
      FROM public.betfair_live_positions pz
     WHERE pz.market_id = p_market_id;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- GRANTS — REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role.
-- Le tabelle restano invisibili a anon/authenticated (RLS + REVOKE): l'accesso
-- passa solo dalle RPC SECURITY DEFINER (che runnano come owner/service_role).
-- NB: 'authenticated' resta nel GRANT perché l'owner si logga come authenticated;
-- il filtro OWNER-ONLY è DENTRO le RPC (betfair_live_is_owner), quindi un eventuale
-- altro authenticated riceve subito RAISE 'non autorizzato (owner-only)' e NON può
-- accodare ordini reali né leggere righe altrui.
-- ============================================================================
REVOKE ALL     ON FUNCTION public.request_betfair_live_order(jsonb) FROM public, anon;
GRANT EXECUTE  ON FUNCTION public.request_betfair_live_order(jsonb) TO authenticated, service_role;

REVOKE ALL     ON FUNCTION public.get_betfair_live_order(bigint)    FROM public, anon;
GRANT EXECUTE  ON FUNCTION public.get_betfair_live_order(bigint)    TO authenticated, service_role;

REVOKE ALL     ON FUNCTION public.get_live_orders(text)             FROM public, anon;
GRANT EXECUTE  ON FUNCTION public.get_live_orders(text)             TO authenticated, service_role;

REVOKE ALL     ON FUNCTION public.get_live_positions(text)          FROM public, anon;
GRANT EXECUTE  ON FUNCTION public.get_live_positions(text)          TO authenticated, service_role;
