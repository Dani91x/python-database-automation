-- ============================================================================
-- personal_tracking_import.sql — Import automatico operazioni Betfair nel Report
-- Personale (alimenta aggiorna_report_betfair.bat / import_betfair_operations.py).
--
-- Aggiunge a personal_trades i campi che l'utente vuole vedere in dashboard e che
-- NON venivano dal flusso watchlist:
--   • betfair_event_id  : ID evento Betfair (colonna "ID Evento")
--   • country           : nazione lega (colonna "Nazione")
--   • season_year       : stagione (colonna "Stagione")
--   • coverage          : "Copertura" (stake sul lato opposto / hedge del mercato)
--   • context (jsonb)   : snapshot CONGELATO dei pronostici API-Football + direzioni
--                         motori (get_direction) al momento dell'operazione, con
--                         l'esito reale e i "hit" (pronostico azzeccato o no).
--
-- Idempotenza import: 1 riga per (betfair_market_id, trade_date) con entry_source
-- ='import'. Ri-eseguire il .bat AGGIORNA la riga (es. risultato/net appena regolati)
-- invece di duplicare. UPSERT via upsert_imported_trade (UPDATE-then-INSERT, robusto
-- rispetto a ON CONFLICT su indice parziale).
--
-- Migrazione ADDITIVA e IDEMPOTENTE. Presuppone personal_tracking_manual_entry.sql
-- (pnl_source/entry_source/commission_amount/betfair_market_id già presenti).
-- ============================================================================

------------------------------------------------------------------------------
-- 1) Colonne nuove (additive)
------------------------------------------------------------------------------
ALTER TABLE public.personal_trades
    ADD COLUMN IF NOT EXISTS betfair_event_id TEXT,
    ADD COLUMN IF NOT EXISTS country          TEXT,
    ADD COLUMN IF NOT EXISTS season_year      SMALLINT,
    ADD COLUMN IF NOT EXISTS coverage         NUMERIC,
    ADD COLUMN IF NOT EXISTS context          JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Idempotenza dell'import per-mercato: una riga per mercato per giorno operativo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pt_import_market
    ON public.personal_trades (betfair_market_id, trade_date)
    WHERE entry_source = 'import' AND betfair_market_id IS NOT NULL;

-- ============================================================================
-- 2) upsert_imported_trade — INSERT o UPDATE della riga import (idempotente).
--    Sempre pnl_source='actual' (P&L reale Betfair) + entry_source='import'.
--    Il P&L (net/gross) è autoritativo; recompute calcola solo roi/hourly.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.upsert_imported_trade(p jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_side       text    := lower(coalesce(p->>'side',''));
    v_timing     text    := lower(coalesce(NULLIF(p->>'timing',''),'prematch'));
    v_status     text    := upper(coalesce(NULLIF(p->>'status',''),'WON'));
    v_odds       numeric := (p->>'entry_odds')::numeric;
    v_stake      numeric := (p->>'stake')::numeric;
    v_net        numeric := NULLIF(p->>'net_pnl','')::numeric;
    v_gross      numeric := NULLIF(p->>'gross_pnl','')::numeric;
    v_comm       numeric := NULLIF(p->>'commission_amount','')::numeric;
    v_cov        numeric := NULLIF(p->>'coverage','')::numeric;
    v_liab       numeric := NULLIF(p->>'liability','')::numeric;
    v_tmin       numeric := NULLIF(p->>'time_operative_min','')::numeric;
    v_market_id  text    := NULLIF(p->>'betfair_market_id','');
    v_trade_date date    := COALESCE(NULLIF(p->>'trade_date','')::date, current_date);
    v_ctx        jsonb   := COALESCE(p->'context', '{}'::jsonb);
    v_tags       text[]  := COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(
                       CASE WHEN jsonb_typeof(p->'tags')='array' THEN p->'tags' ELSE '[]'::jsonb END) x),
                       '{}'::text[]);
    v_id         bigint;
BEGIN
    -- whitelist minima (l'import è controllato, ma difesa in profondità)
    IF v_side NOT IN ('back','lay') THEN RAISE EXCEPTION 'side invalido: %', v_side; END IF;
    IF v_timing NOT IN ('prematch','live') THEN RAISE EXCEPTION 'timing invalido: %', v_timing; END IF;
    IF v_status NOT IN ('OPEN','WON','LOST','VOID','PARTIAL') THEN RAISE EXCEPTION 'status invalido: %', v_status; END IF;
    IF v_odds IS NULL OR v_odds <= 1 THEN RAISE EXCEPTION 'entry_odds invalido: %', v_odds; END IF;
    IF v_stake IS NULL OR v_stake < 0 THEN RAISE EXCEPTION 'stake invalido: %', v_stake; END IF;
    IF coalesce(p->>'strategia','') = '' THEN RAISE EXCEPTION 'strategia obbligatoria'; END IF;
    IF v_market_id IS NULL THEN RAISE EXCEPTION 'betfair_market_id obbligatorio per import'; END IF;
    IF v_net IS NULL THEN RAISE EXCEPTION 'net_pnl obbligatorio (P&L reale)'; END IF;
    v_gross := COALESCE(v_gross, v_net + COALESCE(v_comm, 0));
    IF v_side = 'lay' AND v_liab IS NULL THEN v_liab := v_stake * (v_odds - 1); END IF;

    -- UPSERT sulla chiave import (market, giorno). UPDATE prima; se assente, INSERT.
    UPDATE public.personal_trades SET
        fixture_id = NULLIF(p->>'fixture_id','')::bigint,
        league_id  = NULLIF(p->>'league_id','')::bigint,
        league_name = p->>'league_name',
        home_team  = p->>'home_team',
        away_team  = p->>'away_team',
        kickoff    = NULLIF(p->>'kickoff','')::timestamptz,
        country    = p->>'country',
        season_year = NULLIF(p->>'season_year','')::smallint,
        strategia  = p->>'strategia',
        side       = v_side,
        market     = p->>'market',
        selection  = p->>'selection',
        line       = NULLIF(p->>'line','')::numeric,
        entry_odds = v_odds,
        stake      = v_stake,
        coverage   = v_cov,
        liability  = v_liab,
        timing     = v_timing,
        commission_amount = v_comm,
        -- PRESERVA il tempo operativo inserito a mano dall'utente: il re-import
        -- (v_tmin normalmente NULL) NON deve azzerarlo.
        time_operative_min = COALESCE(v_tmin, public.personal_trades.time_operative_min),
        status     = v_status,
        result_ft  = p->>'result_ft',
        net_pnl    = v_net,
        gross_pnl  = v_gross,
        betfair_event_id = NULLIF(p->>'betfair_event_id',''),
        context    = v_ctx,
        comment    = p->>'comment',
        tags       = v_tags,
        pnl_source = 'actual',
        entry_source = 'import',
        exchange   = 'Betfair',
        updated_at = now()
    WHERE betfair_market_id = v_market_id AND trade_date = v_trade_date
      AND entry_source = 'import'
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        INSERT INTO public.personal_trades (
            fixture_id, league_id, league_name, home_team, away_team, kickoff,
            country, season_year, strategia, side, market, selection, line,
            entry_odds, stake, coverage, liability, timing, exchange,
            commission_amount, time_operative_min, status, result_ft,
            net_pnl, gross_pnl, pnl_source, entry_source,
            betfair_market_id, betfair_event_id, context, comment, tags, trade_date)
        VALUES (
            NULLIF(p->>'fixture_id','')::bigint, NULLIF(p->>'league_id','')::bigint,
            p->>'league_name', p->>'home_team', p->>'away_team',
            NULLIF(p->>'kickoff','')::timestamptz, p->>'country',
            NULLIF(p->>'season_year','')::smallint, p->>'strategia', v_side,
            p->>'market', p->>'selection', NULLIF(p->>'line','')::numeric,
            v_odds, v_stake, v_cov, v_liab, v_timing, 'Betfair',
            v_comm, v_tmin, v_status, p->>'result_ft',
            v_net, v_gross, 'actual', 'import',
            v_market_id, NULLIF(p->>'betfair_event_id',''), v_ctx, p->>'comment',
            v_tags, v_trade_date)
        RETURNING id INTO v_id;
    END IF;

    PERFORM public.recompute_personal_trade(v_id);
    RETURN (SELECT to_jsonb(pt.*) FROM public.personal_trades pt WHERE id = v_id);
END;
$$;

REVOKE ALL ON FUNCTION public.upsert_imported_trade(jsonb) FROM public;
GRANT EXECUTE ON FUNCTION public.upsert_imported_trade(jsonb) TO authenticated, service_role;

-- ============================================================================
-- 3) set_trade_time_operative — imposta il "Tempo Operativo (Min.)" a mano dalla
--    dashboard e ricalcola la resa oraria (hourly_yield = net/(min/60)).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_trade_time_operative(p_id bigint, p_minutes numeric)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_exists boolean;
BEGIN
    IF p_minutes IS NOT NULL AND p_minutes < 0 THEN
        RAISE EXCEPTION 'time_operative_min negativo: %', p_minutes; END IF;
    SELECT true INTO v_exists FROM public.personal_trades WHERE id = p_id;
    IF NOT v_exists THEN RAISE EXCEPTION 'trade % non trovato', p_id; END IF;

    UPDATE public.personal_trades
       SET time_operative_min = p_minutes, updated_at = now()
     WHERE id = p_id;
    PERFORM public.recompute_personal_trade(p_id);   -- ricalcola hourly_yield
    RETURN (SELECT to_jsonb(pt.*) FROM public.personal_trades pt WHERE id = p_id);
END;
$$;

REVOKE ALL ON FUNCTION public.set_trade_time_operative(bigint, numeric) FROM public;
GRANT EXECUTE ON FUNCTION public.set_trade_time_operative(bigint, numeric) TO authenticated, service_role;
