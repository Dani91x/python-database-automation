-- ============================================================================
-- omega_manual.sql — MODALITÀ MANUALE del bot OMEGA (additiva a omega_bot.sql).
--
-- Permette all'utente di scegliere a mano evento → mercato → selezione → target/
-- importo/quota/mode e piazzare UN lay, con lo stesso motore reserve-first (I1).
--
-- Flusso DB-as-bus (il frontend NON parla con Betfair): la UI accoda "richieste"
-- (refresh eventi, carica mercati, carica quote, piazza) in omega_manual_requests;
-- il servizio locale omega_service.py le esegue via service_role e scrive i
-- risultati in omega_events / omega_market_snapshot / omega_trades.
--
-- IDEMPOTENTE. Richiede omega_bot.sql + betfair_live_is_owner().
-- ============================================================================

-- origine del trade: 'auto' (loop) | 'manual' (scelto dall'utente).
ALTER TABLE public.omega_trades
    ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'auto'
    CHECK (origin IN ('auto','manual'));

-- Unique index rivisto: l'invariante I1 "un solo lay per match" vale per
-- l'AUTOMATICO; il MANUALE deve poter piazzare su PIU' mercati/selezioni dello
-- stesso evento (e anche su un evento gia' toccato dall'auto). Quindi:
--  • unique PARZIALE su event_id solo per origin='auto' (I1 automatico)
--  • unique per-gamba (event_id,market_id,selection_id,side) contro i doppioni
--    ESATTI, sia auto sia manuale (reserve-first).
DROP INDEX IF EXISTS public.uq_omega_trades_event;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_auto_event
    ON public.omega_trades (event_id) WHERE origin = 'auto';
-- PARZIALE (audit H1 16/07): una gamba finita in 'error' (FOK non matchato,
-- place_exception, rigetto) NON deve bloccare per sempre il ripiazzamento
-- della stessa gamba — il design della missione prevede il retry (il servizio
-- esclude i trade 'error' dal conteggio "gamba già fatta").
DROP INDEX IF EXISTS public.uq_omega_trades_leg;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_leg
    ON public.omega_trades (event_id, market_id, selection_id, side)
    WHERE status <> 'error';

-- 1. omega_events — cache degli eventi calcio di oggi (per il menu a tendina UI).
CREATE TABLE IF NOT EXISTS public.omega_events (
    event_id    TEXT PRIMARY KEY,
    name        TEXT,
    open_date   TIMESTAMPTZ,
    markets     JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{market_id,market_name,market_type,total_matched}]
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_events FROM anon, authenticated;

-- Enrichment 16/07 (tab MISSIONE): competizione da Betfair (COMPETITION
-- projection) + abbinamento fixture DB (betfair_match) per i loghi API-Football
-- (media.api-sports.io/football/{leagues|teams}/{id}.png). Tutto best-effort:
-- NULL = metadato non risolto, la UI degrada senza logo.
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS country_code     TEXT;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS competition_id   TEXT;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS competition_name TEXT;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS fixture_id       BIGINT;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS league_id        INTEGER;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS home_team_id     INTEGER;
ALTER TABLE public.omega_events ADD COLUMN IF NOT EXISTS away_team_id     INTEGER;

-- 2. omega_market_snapshot — quote di UN mercato caricato a richiesta.
CREATE TABLE IF NOT EXISTS public.omega_market_snapshot (
    market_id    TEXT PRIMARY KEY,
    event_id     TEXT,
    event_name   TEXT,
    market_name  TEXT,
    inplay       BOOLEAN NOT NULL DEFAULT false,
    minute       INTEGER,
    runners      JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{selection_id,name,lay_price,lay_size,back_price,back_size}]
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.omega_market_snapshot ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_market_snapshot FROM anon, authenticated;

-- 3. omega_manual_requests — coda comandi manuali dalla UI.
CREATE TABLE IF NOT EXISTS public.omega_manual_requests (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('refresh_events','load_markets','load_book','place')),
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','error')),
    result       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_omega_manual_pending
    ON public.omega_manual_requests (status, created_at) WHERE status = 'pending';
ALTER TABLE public.omega_manual_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_manual_requests FROM anon, authenticated;

-- Realtime per la UI (idempotente).
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['omega_events','omega_market_snapshot','omega_manual_requests'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                       WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename=t) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
        END IF;
    END LOOP;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;

-- Realtime OWNER-ONLY sulle tabelle manuali (policy SELECT + GRANT authenticated).
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['omega_events','omega_market_snapshot','omega_manual_requests'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_owner', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (public.betfair_live_is_owner())',
            t || '_select_owner', t);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
        EXECUTE format('REVOKE SELECT ON TABLE public.%I FROM anon', t);
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- RPC: accoda una richiesta manuale. Ritorna l'id.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_id bigint;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('refresh_events','load_markets','load_book','place') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;
    INSERT INTO public.omega_manual_requests (kind, payload)
    VALUES (p_kind, coalesce(p_payload, '{}'::jsonb))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_request(text,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: eventi cache (menu a tendina).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_events()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(e.*) ORDER BY e.open_date NULLS LAST), '[]'::jsonb)
      INTO v FROM public.omega_events e;
    RETURN v;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_events() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_events() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: snapshot quote di un mercato.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_market(p_market_id text)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(s.*) INTO v FROM public.omega_market_snapshot s WHERE s.market_id = p_market_id;
    RETURN coalesce(v, 'null'::jsonb);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_market(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_market(text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stato ultime richieste manuali (feedback UI).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_manual_requests(p_limit integer DEFAULT 20)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb)
      INTO v FROM (SELECT * FROM public.omega_manual_requests
                    ORDER BY created_at DESC
                    LIMIT least(greatest(coalesce(p_limit,20),1),100)) r;
    RETURN v;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_manual_requests(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_manual_requests(integer) TO authenticated, service_role;
