-- ============================================================================
-- safe_strategy_bot.sql — controllo, trade, log, richieste e opportunità del
-- BOT della sezione SAFE STRATEGY (calcio + tennis).
--
-- Modellato 1:1 su omega_bot.sql + omega_manual.sql (stesso DB-as-bus):
-- la UI chiama le RPC owner-only per ATTIVARE/FERMARE/CONFIGURARE il bot e per
-- accodare richieste manuali (place / cashout / cancel); il servizio locale
-- ``python -m Betfair.safe_strategy.bot_service`` legge ``safe_strategy_control``
-- (singleton, id=1) via service_role, valuta i segnali sul feed unico
-- (``safe_strategy_scan``) e scrive lo specchio in ``safe_strategy_trades`` +
-- log in ``safe_strategy_activity``.
--
-- MODALITÀ: default 'paper' (simulato). Il 'live' è SEMPRE una scelta esplicita
-- dell'utente (toggle + conferma in UI, come Omega): qui nessun default live.
--
-- IDEMPOTENTE. RLS: tabelle NON esposte in scrittura; SELECT owner-only per il
-- Realtime. Richiede public.betfair_live_is_owner() (betfair_live_order_queue.sql).
-- Da applicare DOPO betfair_live_order_queue.sql e safe_strategy_scan.sql.
-- ============================================================================

-- 1. safe_strategy_control — SINGLETON (id sempre = 1): stato/parametri del bot.
CREATE TABLE IF NOT EXISTS public.safe_strategy_control (
    id            INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    status        TEXT NOT NULL DEFAULT 'idle'
                  CHECK (status IN ('idle','running','stopping','stopped','error')),
    mode          TEXT NOT NULL DEFAULT 'paper'
                  CHECK (mode IN ('paper','live')),
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats         JSONB,      -- {events_total, signals_active, trades_open, open_liability, ...}
    error         TEXT,
    started_at    TIMESTAMPTZ,
    stopped_at    TIMESTAMPTZ,
    heartbeat_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.safe_strategy_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safe_strategy_control FROM anon, authenticated;
INSERT INTO public.safe_strategy_control (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 2. safe_strategy_trades — mirror APPEND/UPDATE di ogni gamba piazzata.
--    'pending'  = riga RISERVATA prima del piazzamento reale (reserve-first).
--    'hedged'   = gamba CHIUSA a mercato da un trade opposto (cash-out/green-up):
--                 il P&L bloccato è in meta.locked_pnl, il settlement finale
--                 nettizza le due gambe insieme (execution.settle_pair).
--    closes_trade_id = id della gamba che questo trade CHIUDE (NULL = apertura).
CREATE TABLE IF NOT EXISTS public.safe_strategy_trades (
    id               BIGSERIAL PRIMARY KEY,
    event_id         TEXT NOT NULL,
    event_name       TEXT,
    sport            TEXT NOT NULL DEFAULT 'calcio' CHECK (sport IN ('calcio','tennis')),
    strategy         TEXT NOT NULL DEFAULT 'base'
                     CHECK (strategy IN ('base','esatto','punta','tennis','model','manual')),
    market_id        TEXT,
    market_type      TEXT,
    selection_id     BIGINT,
    selection_name   TEXT,
    side             TEXT NOT NULL DEFAULT 'back' CHECK (side IN ('back','lay')),
    mode             TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper','live')),
    price            NUMERIC,
    size             NUMERIC,
    liability        NUMERIC,       -- LAY: size*(price-1); BACK: size
    commission       NUMERIC NOT NULL DEFAULT 0.05,  -- aliquota FISSATA al piazzamento
    minute_at_entry  INTEGER,
    score_at_entry   TEXT,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','open','hedged','won','lost','void','error')),
    pnl              NUMERIC NOT NULL DEFAULT 0,
    bet_id           TEXT,
    placed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at       TIMESTAMPTZ,
    origin           TEXT NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','manual')),
    closes_trade_id  BIGINT REFERENCES public.safe_strategy_trades(id),
    signal_key       TEXT,
    meta             JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- IDEMPOTENZA del percorso AUTOMATICO: un solo trade per (evento, segnale).
-- PARZIALE su status <> 'error' → una gamba fallita resta ripiazzabile (come Omega).
-- coalesce(signal_key,''): un signal_key NULL non è "distinto da tutto" (NULL <> NULL
-- nell'unique), altrimenti due auto senza chiave sullo stesso evento passerebbero.
-- Le gambe di CHIUSURA (closes_trade_id) restano fuori: ereditano origin/signal_key.
DROP INDEX IF EXISTS public.uq_safe_trades_signal;
CREATE UNIQUE INDEX IF NOT EXISTS uq_safe_trades_signal
    ON public.safe_strategy_trades (event_id, coalesce(signal_key, ''))
    WHERE origin = 'auto' AND status <> 'error' AND closes_trade_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_safe_trades_status ON public.safe_strategy_trades (status);
CREATE INDEX IF NOT EXISTS idx_safe_trades_event  ON public.safe_strategy_trades (event_id);
CREATE INDEX IF NOT EXISTS idx_safe_trades_placed ON public.safe_strategy_trades (placed_at DESC);
CREATE INDEX IF NOT EXISTS idx_safe_trades_closes ON public.safe_strategy_trades (closes_trade_id)
    WHERE closes_trade_id IS NOT NULL;
ALTER TABLE public.safe_strategy_trades ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safe_strategy_trades FROM anon, authenticated;

-- 3. safe_strategy_activity — log APPEND-ONLY (start, stop, place, skip, settle, error).
CREATE TABLE IF NOT EXISTS public.safe_strategy_activity (
    id       BIGSERIAL PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind     TEXT NOT NULL,
    payload  JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_safe_activity_ts ON public.safe_strategy_activity (ts DESC);
ALTER TABLE public.safe_strategy_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safe_strategy_activity FROM anon, authenticated;

-- 4. safe_strategy_requests — coda comandi dalla UI (place / cashout / cancel).
CREATE TABLE IF NOT EXISTS public.safe_strategy_requests (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('place','cashout','cancel')),
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','error')),
    result       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_safe_requests_pending
    ON public.safe_strategy_requests (status, created_at) WHERE status = 'pending';
ALTER TABLE public.safe_strategy_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safe_strategy_requests FROM anon, authenticated;

-- 5. safe_strategy_opportunities — opportunità di modello per evento (scritte
--    dal bot, lette dalla UI). 1 riga per evento, write-on-change lato servizio.
CREATE TABLE IF NOT EXISTS public.safe_strategy_opportunities (
    event_id    TEXT PRIMARY KEY,
    sport       TEXT NOT NULL DEFAULT 'calcio' CHECK (sport IN ('calcio','tennis')),
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_safe_opps_updated
    ON public.safe_strategy_opportunities (updated_at DESC);
ALTER TABLE public.safe_strategy_opportunities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safe_strategy_opportunities FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- Realtime + SELECT owner-only (senza policy SELECT il canale non consegna nulla).
-- ----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['safe_strategy_control','safe_strategy_trades',
                             'safe_strategy_activity','safe_strategy_requests',
                             'safe_strategy_opportunities'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                       WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename=t) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
        END IF;
    END LOOP;
EXCEPTION WHEN undefined_object THEN
    -- publication assente (ambiente non-Supabase): si ignora.
    NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['safe_strategy_control','safe_strategy_trades',
                             'safe_strategy_activity','safe_strategy_requests',
                             'safe_strategy_opportunities'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_owner', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (public.betfair_live_is_owner())',
            t || '_select_owner', t);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
        EXECUTE format('REVOKE SELECT ON TABLE public.%I FROM anon', t);
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- RPC: attivazione (il servizio locale vede status='running').
-- Il MODE è sempre esplicito: 'live' solo dal toggle+conferma della UI.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_activate(
    p_mode   text DEFAULT 'paper',
    p_params jsonb DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.safe_strategy_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NULL OR p_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    UPDATE public.safe_strategy_control SET
        status     = 'running',
        mode       = p_mode,
        params     = coalesce(p_params, params),
        error      = NULL,
        started_at = now(),
        stopped_at = NULL,
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_activate(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_activate(text,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stop (il servizio vede 'stopping' e passa a 'stopped').
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_stop()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.safe_strategy_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.safe_strategy_control SET
        status     = CASE WHEN status = 'running' THEN 'stopping' ELSE 'stopped' END,
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_stop() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_stop() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: aggiorna parametri a caldo (senza cambiare lo stato run).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_update_params(p_params jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.safe_strategy_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.safe_strategy_control SET
        params     = coalesce(p_params, params),
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_update_params(jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_update_params(jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: stato completo per la dashboard (control + ultimi trade + aggregati).
-- I trade 'hedged' hanno il P&L BLOCCATO ma NON ancora realizzato: contano
-- come aperti finché il mercato non si regola (nettizzazione a due gambe).
-- Le gambe di CHIUSURA (closes_trade_id) NON entrano in open_*: il rischio della
-- coppia è già contato dall'apertura 'hedged' — altrimenti la coppia varrebbe 2.
-- Un 'pending' conta come piazzato se ha bet_id (ordine reale) OPPURE
-- meta.flumine_client_ref (ordine PAPER sul book simulato), come bot_db.aggregate_rows.
-- realized_* restano NON filtrati: il pnl della chiusura regolata è realizzato.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_state()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl   jsonb;
    v_trades jsonb;
    v_agg    jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.safe_strategy_control c WHERE c.id = 1;

    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_trades
      FROM (SELECT * FROM public.safe_strategy_trades
             ORDER BY placed_at DESC LIMIT 200) t;

    SELECT jsonb_build_object(
        'realized_total',  coalesce(sum(pnl) FILTER (WHERE status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(pnl) FILTER (WHERE status IN ('won','lost','void')
                               AND settled_at >= (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome')), 0),
        'open_liability',  coalesce(sum(liability) FILTER (WHERE closes_trade_id IS NULL
                               AND (status IN ('open','hedged')
                                    OR (status = 'pending'
                                        AND (bet_id IS NOT NULL OR (meta->>'flumine_client_ref') IS NOT NULL)))), 0),
        'open_count',      count(*) FILTER (WHERE closes_trade_id IS NULL
                               AND (status IN ('open','hedged')
                                    OR (status = 'pending'
                                        AND (bet_id IS NOT NULL OR (meta->>'flumine_client_ref') IS NOT NULL)))),
        'won',             count(*) FILTER (WHERE status = 'won'),
        'lost',            count(*) FILTER (WHERE status = 'lost')
    ) INTO v_agg FROM public.safe_strategy_trades;

    RETURN jsonb_build_object('control', v_ctrl, 'trades', v_trades, 'aggregates', v_agg);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_state() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_state() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: elenco trade (lista live + curva equity).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_trades(p_limit integer DEFAULT 200)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT * FROM public.safe_strategy_trades
             ORDER BY placed_at DESC
             LIMIT least(greatest(coalesce(p_limit, 200), 1), 2000)) t;
    RETURN v_rows;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_trades(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_trades(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: accoda una richiesta (place / cashout / cancel). Ritorna l'id.
-- VALIDAZIONE nel DB (prima barriera): il servizio ri-valida comunque.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id       bigint;
    v_payload  jsonb := coalesce(p_payload, '{}'::jsonb);
    v_amount   numeric;
    v_fraction numeric;
    v_price    numeric;
    v_size     numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('place','cashout','cancel') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;

    IF p_kind = 'place' THEN
        IF coalesce(v_payload->>'event_id','') = ''
           OR coalesce(v_payload->>'market_id','') = ''
           OR coalesce(v_payload->>'market_type','') = ''
           OR v_payload->>'selection_id' IS NULL
           OR coalesce(v_payload->>'side','') NOT IN ('back','lay')
           OR v_payload->>'price' IS NULL
           OR v_payload->>'size' IS NULL THEN
            RAISE EXCEPTION 'payload place incompleto (servono event_id, market_id, market_type, selection_id, side, price, size)';
        END IF;
        -- Cast GUARDATI: '' → NULL; testo non numerico → messaggio parlante
        -- invece del 22P02 grezzo (invalid_text_representation).
        BEGIN
            v_price := nullif(v_payload->>'price','')::numeric;
            v_size  := nullif(v_payload->>'size','')::numeric;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'price/size non numerici: price=%, size=%',
                            v_payload->>'price', v_payload->>'size';
        END;
        IF v_price IS NULL OR v_price <= 1.0 THEN
            RAISE EXCEPTION 'price non valido: %', v_payload->>'price';
        END IF;
        IF v_size IS NULL OR v_size <= 0 THEN
            RAISE EXCEPTION 'size non valida: %', v_payload->>'size';
        END IF;
        IF coalesce(v_payload->>'mode','paper') NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    ELSIF p_kind = 'cashout' THEN
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cashout senza trade_id';
        END IF;
        v_amount   := nullif(v_payload->>'amount','')::numeric;
        v_fraction := nullif(v_payload->>'fraction','')::numeric;
        IF v_amount IS NOT NULL AND v_amount <= 0 THEN
            RAISE EXCEPTION 'amount deve essere > 0: %', v_amount;
        END IF;
        IF v_fraction IS NOT NULL AND (v_fraction <= 0 OR v_fraction > 1) THEN
            RAISE EXCEPTION 'fraction deve essere in (0,1]: %', v_fraction;
        END IF;
    ELSE  -- cancel
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cancel senza trade_id';
        END IF;
    END IF;

    INSERT INTO public.safe_strategy_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_request(text,jsonb) TO authenticated, service_role;
