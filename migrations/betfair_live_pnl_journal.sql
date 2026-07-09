-- ============================================================================
-- betfair_live_pnl_journal.sql — Roadmap E34 + E37 + D33:
--
--   betfair_live_settled    P&L REALIZZATO per (mode, market_id): scritto dal
--                           runner alla chiusura/settlement del mercato.
--                           PAPER  → somma di order.simulated.profit (flumine).
--                           LIVE   → somma dei cleared orders Betfair (flumine
--                                    poll_market_closure → order.cleared_order).
--                           Fonte autoritativa del P&L di giornata (E34/D33).
--   betfair_live_risk_state singleton pubblicato dal daily_stop_worker:
--                           P&L di giornata (realized + MTM aperto), soglia e
--                           stato dello stop giornaliero. Realtime per la UI.
--   betfair_live_journal    trade journal AUTOMATICO (E37): una riga per ogni
--                           comando eseguito con contesto (minuto, score, book,
--                           segnali attivi al momento del click) + tag/nota.
--
-- IDEMPOTENTE. RPC SECURITY DEFINER owner-only (betfair_live_is_owner).
-- Applicare DOPO betfair_live_order_queue.sql e betfair_live_controls.sql.
-- ============================================================================


-- ============================================================================
-- 1. betfair_live_settled — P&L realizzato per mercato (upsert dal runner).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_settled (
    id          BIGSERIAL PRIMARY KEY,
    mode        TEXT NOT NULL CHECK (mode IN ('paper','live')),
    event_id    TEXT,
    market_id   TEXT NOT NULL,
    market_name TEXT,
    profit      NUMERIC NOT NULL,                 -- P&L realizzato del mercato (EUR)
    orders      INT NOT NULL DEFAULT 0,           -- n. ordini conteggiati
    source      TEXT NOT NULL CHECK (source IN ('simulated','cleared')),
    settled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Arbitro upsert: NON parziale (vincolo 42P10 — vedi betfair_live_order_queue).
CREATE UNIQUE INDEX IF NOT EXISTS idx_bls_settled_key
    ON public.betfair_live_settled (mode, market_id);
CREATE INDEX IF NOT EXISTS idx_bls_settled_at ON public.betfair_live_settled (settled_at DESC);
CREATE INDEX IF NOT EXISTS idx_bls_event ON public.betfair_live_settled (event_id);

ALTER TABLE public.betfair_live_settled ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_settled FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.betfair_live_settled_id_seq FROM anon, authenticated;


-- ============================================================================
-- 2. betfair_live_risk_state — singleton stato rischio giornaliero (realtime).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_risk_state (
    id           INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    mode         TEXT,                            -- mode del runner al momento
    day          DATE,                            -- giornata (locale runner)
    realized     NUMERIC,                         -- P&L settled della giornata
    open_mtm     NUMERIC,                         -- mark-to-market posizioni aperte
    total        NUMERIC,                         -- realized + open_mtm
    limit_value  NUMERIC,                         -- daily_loss_limit attivo (NULL = off)
    stop_fired   BOOLEAN NOT NULL DEFAULT false,  -- kill-switch scattato oggi
    detail       JSONB,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.betfair_live_risk_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.betfair_live_risk_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_risk_state FROM anon, authenticated;
-- lettura realtime dalla UI (top bar): SELECT per authenticated, mai anon.
DROP POLICY IF EXISTS betfair_live_risk_state_select ON public.betfair_live_risk_state;
CREATE POLICY betfair_live_risk_state_select ON public.betfair_live_risk_state
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON public.betfair_live_risk_state TO authenticated;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
          AND schemaname = 'public'
          AND tablename = 'betfair_live_risk_state'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.betfair_live_risk_state;
    END IF;
END $$;


-- ============================================================================
-- 3. betfair_live_journal — trade journal automatico (append-only + tag/nota).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.betfair_live_journal (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode         TEXT NOT NULL CHECK (mode IN ('paper','live')),
    request_id   BIGINT,
    action       TEXT NOT NULL,                   -- place | greenup | dutch | cashout_all | ...
    origin       TEXT NOT NULL DEFAULT 'manual'
                     CHECK (origin IN ('manual','risk_rule')),
    event_id     TEXT,
    market_id    TEXT,
    market_name  TEXT,
    selection_id BIGINT,
    side         TEXT CHECK (side IS NULL OR side IN ('back','lay')),
    price        NUMERIC,
    size         NUMERIC,
    persistence  TEXT,
    bet_id       TEXT,
    minute       SMALLINT,                        -- minuto di gioco al click
    score_home   SMALLINT,
    score_away   SMALLINT,
    inplay       BOOLEAN,
    ltp          NUMERIC,                         -- ultimo prezzo scambiato al click
    best_back    NUMERIC,
    best_lay     NUMERIC,
    book         JSONB,                           -- top-3 livelli back/lay al click
    signals      JSONB,                           -- segnale motore attivo (se presente)
    params       JSONB,                           -- parametri della richiesta
    tag          TEXT,                            -- etichetta assegnata in review
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_blj_ts ON public.betfair_live_journal (ts DESC);
CREATE INDEX IF NOT EXISTS idx_blj_market ON public.betfair_live_journal (market_id);
CREATE INDEX IF NOT EXISTS idx_blj_event ON public.betfair_live_journal (event_id);

ALTER TABLE public.betfair_live_journal ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.betfair_live_journal FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.betfair_live_journal_id_seq FROM anon, authenticated;


-- ============================================================================
-- 4.1 get_live_settled — righe settled in un intervallo. { rows: [...] }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_settled(
    p_from timestamptz DEFAULT NULL,
    p_to   timestamptz DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(s.*) ORDER BY s.settled_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
          SELECT * FROM public.betfair_live_settled
           WHERE (p_from IS NULL OR settled_at >= p_from)
             AND (p_to   IS NULL OR settled_at <  p_to)
           ORDER BY settled_at DESC
           LIMIT 2000
      ) s;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- 4.2 get_live_journal — ultime N righe journal (filtri opzionali). { rows }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_journal(
    p_limit     int  DEFAULT 200,
    p_market_id text DEFAULT NULL,
    p_from      timestamptz DEFAULT NULL,
    p_to        timestamptz DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
    v_lim  int := least(greatest(coalesce(p_limit, 200), 1), 2000);
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(j.*) ORDER BY j.ts DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
          SELECT * FROM public.betfair_live_journal
           WHERE (p_market_id IS NULL OR market_id = p_market_id)
             AND (p_from IS NULL OR ts >= p_from)
             AND (p_to   IS NULL OR ts <  p_to)
           ORDER BY ts DESC
           LIMIT v_lim
      ) j;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- 4.3 set_live_journal_note — assegna tag/nota a una riga journal (review).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_live_journal_note(
    p_id   bigint,
    p_tag  text DEFAULT NULL,
    p_note text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_id IS NULL THEN
        RAISE EXCEPTION 'p_id nullo';
    END IF;
    UPDATE public.betfair_live_journal
       SET tag  = CASE WHEN p_tag  IS NOT NULL THEN nullif(btrim(p_tag),  '') ELSE tag  END,
           note = CASE WHEN p_note IS NOT NULL THEN nullif(btrim(p_note), '') ELSE note END
     WHERE id = p_id;
    SELECT to_jsonb(j.*) INTO v_row FROM public.betfair_live_journal j WHERE j.id = p_id;
    IF v_row IS NULL THEN
        RAISE EXCEPTION 'riga journal % inesistente', p_id;
    END IF;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 4.4 get_live_positions_all / get_live_positions_event — posizioni aggregate
--      (dashboard P&L D33 e top bar esposizione evento E35). { rows: [...] }.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_live_positions_all()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(p.*) ORDER BY p.updated_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT * FROM public.betfair_live_positions ORDER BY updated_at DESC LIMIT 2000) p;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;

CREATE OR REPLACE FUNCTION public.get_live_positions_event(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR btrim(p_event_id) = '' THEN
        RAISE EXCEPTION 'p_event_id obbligatorio';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(p.*) ORDER BY p.updated_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM public.betfair_live_positions p
     WHERE p.event_id = p_event_id;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;


-- ============================================================================
-- GRANTS
-- ============================================================================
REVOKE ALL    ON FUNCTION public.get_live_settled(timestamptz, timestamptz)      FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_settled(timestamptz, timestamptz)      TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_live_journal(int, text, timestamptz, timestamptz) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_journal(int, text, timestamptz, timestamptz) TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.set_live_journal_note(bigint, text, text)       FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_live_journal_note(bigint, text, text)       TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_live_positions_all()                        FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_positions_all()                        TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_live_positions_event(text)                  FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_positions_event(text)                  TO authenticated, service_role;
