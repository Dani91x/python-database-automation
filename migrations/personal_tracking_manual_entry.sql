-- ============================================================================
-- personal_tracking_manual_entry.sql — Inserimento operazioni PASSATE + P&L reale
--
-- Estende Report Personale per due esigenze GEMELLE che scrivono nella STESSA
-- tabella public.personal_trades:
--   1) inserimento MANUALE di operazioni passate dalla UI (Report Personale),
--      agganciate a un match Betfair reale (fixture_id via get_betfair_fixtures);
--   2) import AUTOMATICO (un .bat autonomo, futuro) delle giocate regolate da
--      Betfair (listClearedOrders): profit + commissione REALI per mercato.
--
-- Problema risolto: recompute_personal_trade calcola il P&L da un MODELLO
-- (esito+quota+stake+commissione). Va bene per i trade "da watchlist", ma NON
-- replica il P&L reale di Betfair (scalping, back+lay multipli, fill parziali).
-- Introduciamo quindi un P&L "actual": net_pnl/gross_pnl memorizzati COSÌ COME
-- arrivano da Betfair, e recompute li PRESERVA (calcola solo roi/hourly_yield).
--
-- Migrazione ADDITIVA e IDEMPOTENTE: nessun dato esistente viene toccato; il
-- default pnl_source='model' mantiene identico il comportamento pre-esistente.
-- Convenzioni invariate: schema public, RLS ON, accesso SOLO via RPC SECURITY
-- DEFINER (grant già presenti sulle funzioni CREATE OR REPLACE qui sotto).
-- ============================================================================

------------------------------------------------------------------------------
-- 1) Colonne nuove su personal_trades (tutte NULL/default → additive)
------------------------------------------------------------------------------
ALTER TABLE public.personal_trades
    -- 'model'  : P&L derivato dal modello (recompute) — comportamento storico
    -- 'actual' : P&L reale memorizzato (manuale/import Betfair), recompute NON tocca
    ADD COLUMN IF NOT EXISTS pnl_source TEXT NOT NULL DEFAULT 'model'
        CHECK (pnl_source IN ('model','actual')),
    -- provenienza della riga (audit/telemetria)
    ADD COLUMN IF NOT EXISTS entry_source TEXT NOT NULL DEFAULT 'app'
        CHECK (entry_source IN ('app','manual','import')),
    -- commissione REALE in € (per pnl_source='actual'); il campo `commission`
    -- esistente resta l'ALIQUOTA (0.05) usata dal modello.
    ADD COLUMN IF NOT EXISTS commission_amount NUMERIC
        CHECK (commission_amount IS NULL OR commission_amount >= 0),
    -- riconciliazione con l'import Betfair (listClearedOrders)
    ADD COLUMN IF NOT EXISTS betfair_market_id TEXT,
    ADD COLUMN IF NOT EXISTS betfair_bet_id    TEXT;

-- Idempotenza dell'import automatico: un betId Betfair entra UNA sola volta.
-- Parziale: vincola solo le righe importate (betfair_bet_id valorizzato).
CREATE UNIQUE INDEX IF NOT EXISTS uq_pt_betfair_bet_id
    ON public.personal_trades (betfair_bet_id)
    WHERE betfair_bet_id IS NOT NULL;

-- Lookup per riconciliazione/riepilogo per mercato.
CREATE INDEX IF NOT EXISTS idx_pt_betfair_market
    ON public.personal_trades (betfair_market_id)
    WHERE betfair_market_id IS NOT NULL;

-- ============================================================================
-- 2) recompute_personal_trade — short-circuit per pnl_source='actual'
--    (identica a §2.6 tranne il ramo 'actual' in testa). CREATE OR REPLACE.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.recompute_personal_trade(p_id bigint)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    t           public.personal_trades%ROWTYPE;
    v_liab      numeric;   -- liability effettiva (per lay)
    v_entry_net numeric;   -- pnl netto dell'ingresso (entry)
    v_entry_gro numeric;   -- pnl lordo dell'ingresso (entry)
    v_legs_net  numeric;   -- Σ net_pnl dei leg
    v_net       numeric;
    v_gross     numeric;
BEGIN
    SELECT * INTO t FROM public.personal_trades WHERE id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'personal_trades id % non trovato', p_id;
    END IF;

    -- ---- P&L REALE (actual): net_pnl/gross_pnl sono autoritativi, NON ricalcolare.
    -- Aggiorna solo le metriche derivate (roi, resa oraria). I leg NON si sommano:
    -- l'operazione reale è già netta di tutto (per mercato/per bet come da Betfair).
    IF t.pnl_source = 'actual' THEN
        UPDATE public.personal_trades SET
            liability    = COALESCE(t.liability,
                             CASE WHEN t.side = 'lay' THEN t.stake * (t.entry_odds - 1) END),
            roi          = CASE WHEN t.net_pnl IS NOT NULL THEN t.net_pnl / NULLIF(t.stake, 0) END,
            hourly_yield = CASE WHEN t.net_pnl IS NOT NULL
                                THEN t.net_pnl / NULLIF(t.time_operative_min / 60.0, 0) END,
            updated_at   = now()
        WHERE id = p_id;
        RETURN;
    END IF;

    -- liability per lay: usa quella salvata, altrimenti stake*(entry_odds-1)
    v_liab := COALESCE(t.liability, t.stake * (t.entry_odds - 1));

    -- ---- P&L dell'ingresso (entry) per status ----
    IF t.status = 'WON' THEN
        IF t.side = 'back' THEN
            v_gross     := t.stake * (t.entry_odds - 1);
            v_entry_net := t.stake * (t.entry_odds - 1) * (1 - t.commission);
        ELSE  -- lay: vinco la stake del backer (commissione su vincita)
            v_gross     := t.stake;
            v_entry_net := t.stake * (1 - t.commission);
        END IF;
        v_entry_gro := v_gross;

    ELSIF t.status = 'LOST' THEN
        IF t.side = 'back' THEN
            v_entry_net := -t.stake;
        ELSE  -- lay: perdo la liability
            v_entry_net := -v_liab;
        END IF;
        v_entry_gro := v_entry_net;   -- nessuna commissione sulle perdite

    ELSIF t.status = 'VOID' THEN
        v_entry_net := 0;
        v_entry_gro := 0;

    ELSE
        -- PARTIAL / OPEN: se c'è exit_odds (cash-out) chiudo la posizione a exit.
        IF t.exit_odds IS NOT NULL AND t.exit_odds > 0 THEN
            IF t.side = 'back' THEN
                v_gross := t.stake * (t.entry_odds - t.exit_odds) / t.exit_odds;
            ELSE  -- lay
                v_gross := t.stake * (t.exit_odds - t.entry_odds) / t.exit_odds;
            END IF;
            v_entry_net := CASE WHEN v_gross > 0 THEN v_gross * (1 - t.commission) ELSE v_gross END;
            v_entry_gro := v_gross;
        ELSE
            v_entry_net := NULL;   -- aperto senza cash-out: P&L non ancora definito
            v_entry_gro := NULL;
        END IF;
    END IF;

    -- ---- Σ net_pnl dei leg (coperture/hedge/cashout aggiuntivi) ----
    SELECT COALESCE(sum(net_pnl), 0) INTO v_legs_net
      FROM public.personal_trade_legs WHERE trade_id = p_id;

    v_net   := COALESCE(v_entry_net, 0) + v_legs_net;
    v_gross := COALESCE(v_entry_gro, 0) + v_legs_net;
    IF v_entry_net IS NULL AND v_legs_net = 0 THEN
        v_net   := NULL;
        v_gross := NULL;
    END IF;

    UPDATE public.personal_trades SET
        liability    = v_liab,
        net_pnl      = v_net,
        gross_pnl    = v_gross,
        roi          = CASE WHEN v_net IS NOT NULL THEN v_net / NULLIF(t.stake, 0) END,
        hourly_yield = CASE WHEN v_net IS NOT NULL
                            THEN v_net / NULLIF(t.time_operative_min / 60.0, 0) END,
        updated_at   = now()
    WHERE id = p_id;
END;
$$;

-- ============================================================================
-- 3) add_personal_trade — supporta P&L reale + provenienza + chiavi Betfair.
--    Estende §2.4: nuovi campi opzionali nel payload jsonb, tutto retro-compat.
--    pnl_source='actual' → net_pnl obbligatorio, gross default = net + commissione.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.add_personal_trade(p jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_wl_id     bigint  := NULLIF(p->>'watchlist_id','')::bigint;
    v_side      text    := lower(coalesce(p->>'side',''));
    v_timing    text    := lower(coalesce(NULLIF(p->>'timing',''),'prematch'));
    v_status    text    := upper(coalesce(NULLIF(p->>'status',''),'OPEN'));
    v_entry_odds numeric := (p->>'entry_odds')::numeric;
    v_stake     numeric := (p->>'stake')::numeric;
    v_liab      numeric := NULLIF(p->>'liability','')::numeric;
    v_comm      numeric := coalesce(NULLIF(p->>'commission','')::numeric, 0.05);
    v_market    text    := p->>'market';
    v_selection text    := p->>'selection';
    v_kickoff   timestamptz := NULLIF(p->>'kickoff','')::timestamptz;
    v_trade_date date;
    v_wl        public.personal_watchlist%ROWTYPE;
    v_ctx       jsonb;
    v_edge      numeric; v_mprob numeric; v_iprob numeric;
    v_affid     numeric; v_conc smallint; v_mot smallint;
    v_followed  boolean;
    v_new_id    bigint;
    v_row       jsonb;
    -- ---- NUOVI (manual entry / import reale) ----
    v_pnl_src   text    := lower(coalesce(NULLIF(p->>'pnl_source',''),'model'));
    v_entry_src text    := lower(coalesce(NULLIF(p->>'entry_source',''),'app'));
    v_net_pnl   numeric := NULLIF(p->>'net_pnl','')::numeric;
    v_gross_pnl numeric := NULLIF(p->>'gross_pnl','')::numeric;
    v_comm_amt  numeric := NULLIF(p->>'commission_amount','')::numeric;
    v_bf_market text    := NULLIF(p->>'betfair_market_id','');
    v_bf_bet    text    := NULLIF(p->>'betfair_bet_id','');
BEGIN
    -- whitelist input
    IF v_side NOT IN ('back','lay') THEN
        RAISE EXCEPTION 'side invalido: %', v_side; END IF;
    IF v_timing NOT IN ('prematch','live') THEN
        RAISE EXCEPTION 'timing invalido: %', v_timing; END IF;
    IF v_status NOT IN ('OPEN','WON','LOST','VOID','PARTIAL') THEN
        RAISE EXCEPTION 'status invalido: %', v_status; END IF;
    IF v_entry_odds IS NULL OR v_entry_odds <= 1 THEN
        RAISE EXCEPTION 'entry_odds invalido: %', v_entry_odds; END IF;
    IF v_stake IS NULL OR v_stake < 0 THEN
        RAISE EXCEPTION 'stake invalido: %', v_stake; END IF;
    IF coalesce(p->>'strategia','') = '' THEN
        RAISE EXCEPTION 'strategia obbligatoria'; END IF;
    IF v_pnl_src NOT IN ('model','actual') THEN
        RAISE EXCEPTION 'pnl_source invalido: %', v_pnl_src; END IF;
    IF v_entry_src NOT IN ('app','manual','import') THEN
        RAISE EXCEPTION 'entry_source invalido: %', v_entry_src; END IF;

    -- P&L reale: net obbligatorio; gross default = net + commissione reale.
    IF v_pnl_src = 'actual' THEN
        IF v_net_pnl IS NULL THEN
            RAISE EXCEPTION 'net_pnl obbligatorio quando pnl_source=actual'; END IF;
        v_gross_pnl := COALESCE(v_gross_pnl, v_net_pnl + COALESCE(v_comm_amt, 0));
    ELSE
        -- in modalità modello il P&L lo calcola recompute: ignora eventuali override
        v_net_pnl   := NULL;
        v_gross_pnl := NULL;
    END IF;

    -- liability per lay: se non fornita, stake*(odds-1)
    IF v_side = 'lay' AND v_liab IS NULL THEN
        v_liab := v_stake * (v_entry_odds - 1);
    END IF;

    -- contesto match: dalla watchlist se collegata, altrimenti dai campi p
    IF v_wl_id IS NOT NULL THEN
        SELECT * INTO v_wl FROM public.personal_watchlist WHERE id = v_wl_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'watchlist_id % non trovato', v_wl_id; END IF;
        v_kickoff := COALESCE(v_kickoff, v_wl.kickoff);

        SELECT e INTO v_ctx
          FROM jsonb_array_elements(
                   CASE WHEN jsonb_typeof(v_wl.snapshot->'edges')='array'
                        THEN v_wl.snapshot->'edges' ELSE '[]'::jsonb END) e
         WHERE e->>'market' = v_market AND e->>'selection' = v_selection
         LIMIT 1;
        IF v_ctx IS NOT NULL THEN
            v_edge  := NULLIF(v_ctx->>'edge','')::numeric;
            v_mprob := NULLIF(v_ctx->>'model_prob','')::numeric;
            v_iprob := NULLIF(v_ctx->>'implied_prob','')::numeric;
            v_affid := NULLIF(v_ctx->>'affidabilita','')::numeric;
            v_conc  := COALESCE(jsonb_array_length(
                          CASE WHEN jsonb_typeof(v_ctx->'concordi')='array'
                               THEN v_ctx->'concordi' ELSE '[]'::jsonb END),0);
            v_mot   := NULLIF(v_ctx->>'motori_totali','')::smallint;
        END IF;
        SELECT EXISTS (
            SELECT 1 FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(v_wl.consigli)='array'
                            THEN v_wl.consigli ELSE '[]'::jsonb END) c
            WHERE c->>'market' = v_market AND c->>'selection' = v_selection
        ) INTO v_followed;
    END IF;

    -- trade_date: default kickoff::date, altrimenti oggi
    v_trade_date := COALESCE(
        NULLIF(p->>'trade_date','')::date,
        v_kickoff::date,
        current_date);

    INSERT INTO public.personal_trades (
        watchlist_id, fixture_id, league_id, league_name, home_team, away_team, kickoff,
        strategia, side, market, selection, line, entry_odds, stake, liability, exit_odds,
        timing, entry_minute, entry_score, exchange, commission, time_operative_min,
        status, result_ft,
        edge_at_entry, model_prob, implied_prob, affidabilita, concordi, motori_totali,
        followed_advice, comment, tags, trade_date,
        pnl_source, entry_source, commission_amount, betfair_market_id, betfair_bet_id,
        net_pnl, gross_pnl)
    VALUES (
        v_wl_id,
        COALESCE(NULLIF(p->>'fixture_id','')::bigint, v_wl.fixture_id),
        COALESCE(NULLIF(p->>'league_id','')::bigint, v_wl.league_id),
        COALESCE(p->>'league_name', v_wl.league_name),
        COALESCE(p->>'home_team', v_wl.home_team),
        COALESCE(p->>'away_team', v_wl.away_team),
        v_kickoff,
        p->>'strategia', v_side, v_market, v_selection,
        NULLIF(p->>'line','')::numeric, v_entry_odds, v_stake, v_liab,
        NULLIF(p->>'exit_odds','')::numeric,
        v_timing, NULLIF(p->>'entry_minute','')::smallint, p->>'entry_score',
        coalesce(NULLIF(p->>'exchange',''),'Betfair'), v_comm,
        NULLIF(p->>'time_operative_min','')::numeric,
        v_status, p->>'result_ft',
        v_edge, v_mprob, v_iprob, v_affid, v_conc, v_mot,
        v_followed, p->>'comment',
        COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(p->'tags')='array' THEN p->'tags' ELSE '[]'::jsonb END) x), '{}'::text[]),
        v_trade_date,
        v_pnl_src, v_entry_src, v_comm_amt, v_bf_market, v_bf_bet,
        v_net_pnl, v_gross_pnl)
    RETURNING id INTO v_new_id;

    -- watchlist collegata → status GIOCATA
    IF v_wl_id IS NOT NULL THEN
        UPDATE public.personal_watchlist
           SET status = 'GIOCATA', decided_at = COALESCE(decided_at, now()), updated_at = now()
         WHERE id = v_wl_id AND status <> 'GIOCATA';
    END IF;

    PERFORM public.recompute_personal_trade(v_new_id);

    SELECT to_jsonb(pt.*) INTO v_row FROM public.personal_trades pt WHERE id = v_new_id;
    RETURN v_row;
END;
$$;
