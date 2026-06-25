-- ============================================================================
-- personal_tracking_rpc.sql — RPC Watchlist + Report Personale
-- Contratto: REPORT_PERSONALE_CONTRACT.md §2 + §3 — fonte UNICA e vincolante.
--
-- Tutte SECURITY DEFINER, SET search_path = public, pg_temp.
-- Lettura: STABLE. Scrittura: VOLATILE. Input whitelistato.
-- Grant: REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role.
-- Lockdown anon in coda (§2.9). Idempotente: CREATE OR REPLACE.
--
-- Stile mirror di analytics_decisions_rpc.sql (jsonb_build_object, CTE, round)
-- e get_direction_rpc.sql (lettura fixture_predictions + chiamata RPC interne).
-- ============================================================================


-- ============================================================================
-- 2.1 add_to_watchlist — congela lo snapshot pre-match (server-side, immutabile)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.add_to_watchlist(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_fp        record;
    v_dir       jsonb;
    v_bf        jsonb;
    v_full      jsonb;
    v_edges     jsonb;
    v_consigli  jsonb;
    v_snapshot  jsonb;
    v_row       jsonb;
    v_existing  public.personal_watchlist%ROWTYPE;
BEGIN
    IF p_fixture_id IS NULL THEN
        RAISE EXCEPTION 'p_fixture_id nullo';
    END IF;

    -- identità match da fixture_predictions (country/round non presenti → NULL)
    SELECT fixture_id, league_id, league_name, season_year, fixture_date,
           home_team_name, away_team_name
      INTO v_fp
      FROM public.fixture_predictions
     WHERE fixture_id = p_fixture_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'fixture_id % non trovato in fixture_predictions', p_fixture_id;
    END IF;

    -- se esiste già una decisione presa (GIOCATA/SCARTATA) → NON sovrascrivere
    SELECT * INTO v_existing FROM public.personal_watchlist WHERE fixture_id = p_fixture_id;
    IF FOUND AND v_existing.status <> 'DA_VALUTARE' THEN
        RETURN to_jsonb(v_existing);
    END IF;

    -- snapshot integrale dei motori e delle quote (output INTEGRALE delle RPC)
    v_dir  := public.get_direction(p_fixture_id);
    v_bf   := public.get_betfair_direction_odds(p_fixture_id);

    -- elenco mercati Betfair disponibili (nomi mercato della full-odds)
    SELECT coalesce(jsonb_agg(DISTINCT market_name ORDER BY market_name), '[]'::jsonb)
      INTO v_full
      FROM public.betfair_market_odds
     WHERE fixture_id = p_fixture_id;

    -- edges: 1 per (market, selection) dei mercati della direzione, incrociati con
    -- le quote Betfair canoniche. model_prob = prob Poisson della selezione (engine
    -- leader del cruscotto). best_back/best_lay = miglior livello (indice 0) del
    -- ladder. edge = model_prob - 1/odds (su best_back). EV Betfair (comm su vincita):
    --   ev_back = model_prob*(odds-1)*(1-comm) - (1-model_prob).   comm = 0.05 default.
    WITH dm AS (   -- ogni mercato della direzione → selezione + prob per-motore
        SELECT  m->>'market'                                   AS market,
                m->>'direction'                                AS direction,
                (m->>'affidabilita')::numeric                  AS affidabilita,
                (m->>'lift')::numeric                          AS lift,
                COALESCE(m->'concordi','[]'::jsonb)            AS concordi_list,
                COALESCE((m->>'motori_totali')::int,0)         AS motori_totali,
                m->'engines'->'poisson'                        AS poisson_obj
        -- guard anti-scalar: COALESCE non cattura il JSON null (solo SQL NULL);
        -- se 'markets' non e' un array (null/scalar) usa '[]' per non far esplodere
        -- jsonb_array_elements ("cannot extract elements from a scalar").
        FROM jsonb_array_elements(
                 CASE WHEN jsonb_typeof(v_dir->'markets')='array'
                      THEN v_dir->'markets' ELSE '[]'::jsonb END) m
    ),
    ed AS (
        SELECT
            dm.market,
            dm.direction                                        AS selection,
            (dm.poisson_obj ->> dm.direction)::numeric          AS model_prob,
            ((v_bf -> dm.market -> dm.direction -> 'back' -> 0) ->> 'price')::numeric AS best_back,
            ((v_bf -> dm.market -> dm.direction -> 'lay'  -> 0) ->> 'price')::numeric AS best_lay,
            dm.affidabilita,
            dm.lift,
            dm.concordi_list,
            dm.motori_totali
        FROM dm
    ),
    ed2 AS (
        SELECT *,
            CASE WHEN model_prob IS NOT NULL AND best_back IS NOT NULL AND best_back > 0
                 THEN round(1.0/best_back, 6) END AS implied_prob,
            CASE WHEN model_prob IS NOT NULL AND best_back IS NOT NULL AND best_back > 0
                 THEN round(model_prob - 1.0/best_back, 6) END AS edge,
            CASE WHEN model_prob IS NOT NULL AND best_back IS NOT NULL AND best_back > 1
                 THEN round(model_prob*(best_back-1)*(1-0.05) - (1-model_prob), 6) END AS ev_back
        FROM ed
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
                'market',        market,
                'selection',     selection,
                'model_prob',    round(model_prob, 6),
                'best_back',     best_back,
                'best_lay',      best_lay,
                'implied_prob',  implied_prob,
                'edge',          edge,
                'ev_back',       ev_back,
                'affidabilita',  affidabilita,
                'lift',          lift,
                'concordi',      concordi_list,
                'motori_totali', motori_totali
            ) ORDER BY edge DESC NULLS LAST), '[]'::jsonb)
      INTO v_edges
      FROM ed2;

    -- consigli = sottoinsieme di edges, edge>0, ordinato per edge desc, top 5
    SELECT coalesce(jsonb_agg(e ORDER BY (e->>'edge')::numeric DESC), '[]'::jsonb)
      INTO v_consigli
      FROM (
        SELECT e FROM jsonb_array_elements(v_edges) e
        WHERE (e->>'edge') IS NOT NULL AND (e->>'edge')::numeric > 0
        ORDER BY (e->>'edge')::numeric DESC
        LIMIT 5
      ) t;

    v_snapshot := jsonb_build_object(
        'generated_at',      now(),
        'direction',         v_dir,
        'betfair',           v_bf,
        'full_odds_markets', v_full,
        'edges',             v_edges
    );

    -- UPSERT su UNIQUE(fixture_id): se esiste DA_VALUTARE aggiorna snapshot;
    -- (le decisioni prese sono già state ritornate sopra senza arrivare qui).
    INSERT INTO public.personal_watchlist
        (fixture_id, league_id, league_name, season_year, country, round,
         home_team, away_team, kickoff, status, snapshot, consigli, snapshot_at)
    VALUES
        (v_fp.fixture_id, v_fp.league_id, v_fp.league_name, v_fp.season_year, NULL, NULL,
         v_fp.home_team_name, v_fp.away_team_name, v_fp.fixture_date, 'DA_VALUTARE',
         v_snapshot, v_consigli, now())
    ON CONFLICT (fixture_id) DO UPDATE SET
         league_id   = EXCLUDED.league_id,
         league_name = EXCLUDED.league_name,
         season_year = EXCLUDED.season_year,
         home_team   = EXCLUDED.home_team,
         away_team   = EXCLUDED.away_team,
         kickoff     = EXCLUDED.kickoff,
         snapshot    = EXCLUDED.snapshot,
         consigli    = EXCLUDED.consigli,
         snapshot_at = now(),
         updated_at  = now()
    RETURNING to_jsonb(personal_watchlist.*) INTO v_row;

    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.2 get_watchlist — righe watchlist (filtrabili per status) + n_trades
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_watchlist(p_status text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_result jsonb;
BEGIN
    IF p_status IS NOT NULL AND p_status NOT IN ('DA_VALUTARE','GIOCATA','SCARTATA') THEN
        RAISE EXCEPTION 'p_status invalido: %', p_status;
    END IF;

    SELECT coalesce(jsonb_agg(row ORDER BY (row->>'kickoff')), '[]'::jsonb)
      INTO v_result
      FROM (
        SELECT to_jsonb(w.*) || jsonb_build_object(
                 'n_trades',
                 (SELECT count(*) FROM public.personal_trades pt WHERE pt.watchlist_id = w.id)
               ) AS row
        FROM public.personal_watchlist w
        WHERE p_status IS NULL OR w.status = p_status
        ORDER BY w.kickoff NULLS LAST
      ) t;

    RETURN coalesce(v_result, '[]'::jsonb);
END;
$$;


-- ============================================================================
-- 2.3 set_watchlist_decision — registra la scelta dell'utente (GIOCATA/SCARTATA)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_watchlist_decision(
    p_id            bigint,
    p_status        text,
    p_reject_reason text    DEFAULT NULL,
    p_reject_note   text    DEFAULT NULL,
    p_note          text    DEFAULT NULL,
    p_strategia     text    DEFAULT NULL,
    p_tags          text[]  DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF p_status NOT IN ('GIOCATA','SCARTATA','DA_VALUTARE') THEN
        RAISE EXCEPTION 'p_status invalido: %', p_status;
    END IF;
    IF p_status = 'SCARTATA' THEN
        IF p_reject_reason IS NULL OR p_reject_reason NOT IN (
            'quota_bassa','edge_insufficiente','formazioni','infortuni','non_mi_fido',
            'troppe_operazioni','liquidita_scarsa','gestione_rischio','altro') THEN
            RAISE EXCEPTION 'p_reject_reason invalido: %', p_reject_reason;
        END IF;
        -- una partita con trade collegati (GIOCATA) NON puo' diventare SCARTATA:
        -- i suoi trade alimentano il P&L → falserebbe le analitiche giocate/scartate.
        IF EXISTS (SELECT 1 FROM public.personal_trades WHERE watchlist_id = p_id) THEN
            RAISE EXCEPTION 'Impossibile scartare: la partita ha gia'' % trade collegati',
                (SELECT count(*) FROM public.personal_trades WHERE watchlist_id = p_id);
        END IF;
    END IF;

    UPDATE public.personal_watchlist SET
        status               = p_status,
        -- fuori da SCARTATA azzero SIA reason SIA note (nessun residuo incoerente)
        reject_reason        = CASE WHEN p_status = 'SCARTATA' THEN p_reject_reason ELSE NULL END,
        reject_note          = CASE WHEN p_status = 'SCARTATA' THEN p_reject_note   ELSE NULL END,
        user_note            = COALESCE(p_note, user_note),
        strategia_ipotizzata = COALESCE(p_strategia, strategia_ipotizzata),
        tags                 = COALESCE(p_tags, tags),
        decided_at           = now(),
        updated_at           = now()
    WHERE id = p_id
    RETURNING to_jsonb(personal_watchlist.*) INTO v_row;

    IF v_row IS NULL THEN
        RAISE EXCEPTION 'watchlist id % non trovato', p_id;
    END IF;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.6 recompute_personal_trade — ricalcola net/gross/roi/hourly (interna)
-- Definita PRIMA delle RPC che la chiamano (add_personal_trade/add_trade_leg/
-- settle_personal_trade). §2.6 — back/lay, win/lose/void, commissione, legs.
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
        -- back chiuso = lay a exit_odds sulla stessa stake; lay chiuso = back a exit_odds.
        -- pnl_back_cashout = stake*(entry_odds - exit_odds)/exit_odds (green/red book).
        IF t.exit_odds IS NOT NULL AND t.exit_odds > 0 THEN
            IF t.side = 'back' THEN
                v_gross := t.stake * (t.entry_odds - t.exit_odds) / t.exit_odds;
            ELSE  -- lay
                v_gross := t.stake * (t.exit_odds - t.entry_odds) / t.exit_odds;
            END IF;
            -- commissione applicata solo sul profitto netto positivo
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

    -- net = entry + legs (se entry NULL ma esistono leg, conta solo i leg)
    v_net   := COALESCE(v_entry_net, 0) + v_legs_net;
    v_gross := COALESCE(v_entry_gro, 0) + v_legs_net;
    -- se l'ingresso è indefinito e non ci sono leg → net/gross restano NULL
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
-- 2.4 add_personal_trade — crea il trade (entry) e congela il contesto snapshot
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
    v_consiglio jsonb;
    v_edge      numeric; v_mprob numeric; v_iprob numeric;
    v_affid     numeric; v_conc smallint; v_mot smallint;
    v_followed  boolean;
    v_new_id    bigint;
    v_row       jsonb;
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

        -- congela edge/model_prob/implied/affidabilita/concordi/motori per (market,selection)
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
        -- followed_advice: la selezione è tra i consigli?
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
        followed_advice, comment, tags, trade_date)
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
        -- FIX "cannot extract elements from a scalar": il frontend invia tags:null
        -- (JSON null = scalare) quando non ci sono tag. jsonb_array_elements_text su
        -- uno scalare esplode; il guard lo tratta come array vuoto -> '{}'::text[].
        COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(p->'tags')='array' THEN p->'tags' ELSE '[]'::jsonb END) x), '{}'::text[]),
        v_trade_date)
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


-- ============================================================================
-- 2.5a add_trade_leg — inserisce una copertura/hedge/cashout e ricalcola
-- ============================================================================
CREATE OR REPLACE FUNCTION public.add_trade_leg(p jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_trade_id bigint := (p->>'trade_id')::bigint;
    v_leg_type text   := lower(coalesce(p->>'leg_type',''));
    v_side     text   := lower(NULLIF(p->>'side',''));
    v_timing   text   := lower(NULLIF(p->>'timing',''));
    v_new_id   bigint;
    v_row      jsonb;
BEGIN
    IF v_trade_id IS NULL THEN
        RAISE EXCEPTION 'trade_id obbligatorio'; END IF;
    IF v_leg_type NOT IN ('hedge','cashout','coverage','adjust') THEN
        RAISE EXCEPTION 'leg_type invalido: %', v_leg_type; END IF;
    IF v_side IS NOT NULL AND v_side NOT IN ('back','lay') THEN
        RAISE EXCEPTION 'side invalido: %', v_side; END IF;
    IF v_timing IS NOT NULL AND v_timing NOT IN ('prematch','live') THEN
        RAISE EXCEPTION 'timing invalido: %', v_timing; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.personal_trades WHERE id = v_trade_id) THEN
        RAISE EXCEPTION 'trade_id % non trovato', v_trade_id; END IF;

    INSERT INTO public.personal_trade_legs (
        trade_id, leg_type, side, market, selection, odds, stake, liability,
        timing, minute, net_pnl, note)
    VALUES (
        v_trade_id, v_leg_type, v_side, p->>'market', p->>'selection',
        NULLIF(p->>'odds','')::numeric, NULLIF(p->>'stake','')::numeric,
        NULLIF(p->>'liability','')::numeric, v_timing,
        NULLIF(p->>'minute','')::smallint, NULLIF(p->>'net_pnl','')::numeric, p->>'note')
    RETURNING id INTO v_new_id;

    PERFORM public.recompute_personal_trade(v_trade_id);

    SELECT to_jsonb(l.*) INTO v_row FROM public.personal_trade_legs l WHERE id = v_new_id;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.5b settle_personal_trade — esito finale (WON/LOST/VOID/PARTIAL) + ricalcolo
-- ============================================================================
CREATE OR REPLACE FUNCTION public.settle_personal_trade(
    p_id        bigint,
    p_status    text,
    p_result_ft text    DEFAULT NULL,
    p_exit_odds numeric DEFAULT NULL,
    p_time_min  numeric DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF p_status NOT IN ('OPEN','WON','LOST','VOID','PARTIAL') THEN
        RAISE EXCEPTION 'p_status invalido: %', p_status; END IF;

    UPDATE public.personal_trades SET
        status             = p_status,
        result_ft          = COALESCE(p_result_ft, result_ft),
        exit_odds          = COALESCE(p_exit_odds, exit_odds),
        time_operative_min = COALESCE(p_time_min, time_operative_min),
        updated_at         = now()
    WHERE id = p_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'personal_trades id % non trovato', p_id; END IF;

    PERFORM public.recompute_personal_trade(p_id);

    SELECT to_jsonb(pt.*) INTO v_row FROM public.personal_trades pt WHERE id = p_id;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 2.7 get_personal_report — KPI + equity + breakdown + advice + discarded
-- Metriche §3 (oracle==RPC). Solo trade chiusi (WON/LOST/VOID/PARTIAL) nei P&L.
-- Serie input = pnl giornaliero (Σ net_pnl per trade_date). eq[i]=Σpnl[0..i] da 0.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_personal_report(
    p_from      date    DEFAULT NULL,
    p_to        date    DEFAULT NULL,
    p_strategia text    DEFAULT NULL,
    p_league_id integer DEFAULT NULL,
    p_status    text    DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_result jsonb;
BEGIN
    IF p_status IS NOT NULL AND p_status NOT IN ('WON','LOST','VOID','PARTIAL') THEN
        RAISE EXCEPTION 'p_status invalido: %', p_status; END IF;

    WITH
    -- popolazione: trade chiusi che entrano nelle metriche P&L, con i filtri
    base AS (
        SELECT pt.*
        FROM public.personal_trades pt
        WHERE pt.status IN ('WON','LOST','VOID','PARTIAL')
          AND pt.net_pnl IS NOT NULL
          AND (p_from      IS NULL OR pt.trade_date >= p_from)
          AND (p_to        IS NULL OR pt.trade_date <= p_to)
          AND (p_strategia IS NULL OR pt.strategia  = p_strategia)
          AND (p_league_id IS NULL OR pt.league_id  = p_league_id)
          AND (p_status    IS NULL OR pt.status      = p_status)
    ),
    -- serie giornaliera: 1 riga per trade_date (giorno operativo)
    daily0 AS (
        SELECT pt.trade_date AS day,
               sum(pt.net_pnl)                          AS pnl,
               count(*)::int                            AS n_trades,
               coalesce(sum(pt.stake),0)                AS stake,
               coalesce(sum(pt.time_operative_min),0)   AS tmin
        FROM base pt
        GROUP BY pt.trade_date
    ),
    -- equity cumulativa da 0 (eq[i]=Σpnl[0..i]); il running peak NON può essere
    -- annidato in un'altra window function → due passi (equity, poi peak/drawdown).
    daily_eq AS (
        SELECT day, pnl, n_trades, stake, tmin,
               sum(pnl) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS equity
        FROM daily0
    ),
    daily2 AS (
        SELECT day, pnl, n_trades, stake, tmin, equity,
               max(equity) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak,
               equity - max(equity) OVER (ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS drawdown
        FROM daily_eq
    ),
    -- aggregati base sulla serie pnl
    agg AS (
        SELECT
            count(*)::int                                        AS n,
            count(*) FILTER (WHERE pnl > 0)::int                 AS profit_days,
            count(*) FILTER (WHERE pnl < 0)::int                 AS loss_days,
            coalesce(sum(pnl),0)                                 AS tot,
            avg(pnl)                                             AS mean,
            max(pnl)                                             AS max_day,
            min(pnl)                                             AS min_day,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY pnl)::numeric AS median,
            avg(pnl) FILTER (WHERE pnl > 0)                      AS avg_win,
            avg(pnl) FILTER (WHERE pnl < 0)                      AS avg_loss,
            sum(pnl) FILTER (WHERE pnl > 0)                      AS sum_pos,
            sum(pnl) FILTER (WHERE pnl < 0)                      AS sum_neg,
            stddev_samp(pnl)                                     AS vol,           -- n-1
            coalesce(sum(stake),0)                               AS sum_stake,
            coalesce(sum(tmin),0)                                AS sum_tmin,
            (SELECT count(*) FROM base)::int                     AS n_trades_tot
        FROM daily2
    ),
    -- max drawdown (min del drawdown), recovery/ulcer/calmar
    risk AS (
        SELECT
            min(drawdown)                                        AS max_drawdown,
            -- ulcer §3: sqrt(mean dei DD_pct^2) su TUTTI gli n giorni; DD_pct=0
            -- quando peak<=0 (nessun massimo positivo → drawdown % non definito = 0).
            sqrt(avg((CASE WHEN peak > 0 THEN (equity-peak)/peak*100 ELSE 0 END)^2)) AS ulcer_index
        FROM daily2
    ),
    -- downside deviation + sortino (su min(0,pnl))
    dside AS (
        SELECT sqrt(avg(LEAST(0,pnl)^2)) AS downside_dev FROM daily2
    ),
    -- CVaR 5%: media dei peggiori ceil(5%) pnl
    cvar AS (
        SELECT avg(pnl) AS cvar_5 FROM (
            SELECT pnl FROM daily2 ORDER BY pnl ASC
            LIMIT GREATEST(1, (SELECT ceil(count(*)*0.05)::int FROM daily2))
        ) z
    ),
    -- top5 / worst per la concentrazione del P&L
    top5 AS (
        SELECT coalesce(sum(pnl),0) AS s FROM (
            SELECT pnl FROM daily2 ORDER BY pnl DESC LIMIT 5
        ) z
    ),
    -- kurtosis (excess, corretta per campione = formula Excel KURT)
    kurt AS (
        SELECT CASE WHEN a.n > 3 AND a.vol > 0 THEN
            (a.n*(a.n+1)::numeric)/((a.n-1)*(a.n-2)*(a.n-3))
              * (SELECT sum(((pnl-a.mean)/a.vol)^4) FROM daily2)
            - 3*((a.n-1)::numeric^2)/((a.n-2)*(a.n-3))
        END AS kurtosis
        FROM agg a
    ),
    -- max durata drawdown: max #giorni consecutivi sotto un peak precedente.
    -- "sotto un peak" = drawdown < 0 (equity sotto il running peak). Conta i run.
    dd_dur AS (
        SELECT coalesce(max(run_len),0) AS max_dd_duration_days FROM (
            SELECT count(*) AS run_len
            FROM (
                SELECT day, drawdown,
                       sum(CASE WHEN drawdown < 0 THEN 0 ELSE 1 END)
                         OVER (ORDER BY day) AS grp
                FROM daily2
            ) g
            WHERE drawdown < 0
            GROUP BY grp
        ) r
    ),
    -- numero giornate con perdita > stake del giorno (|pnl| > stake, pnl<0)
    glt AS (
        SELECT count(*)::int AS giornate_perdita_gt_stake
        FROM daily2 WHERE pnl < 0 AND (-pnl) > stake
    )
    SELECT jsonb_build_object(
        'daily', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                    'day', day, 'pnl', round(pnl,6), 'equity', round(equity,6),
                    'peak', round(peak,6), 'drawdown', round(drawdown,6),
                    'n_trades', n_trades) ORDER BY day) FROM daily2), '[]'::jsonb),

        'metrics', (SELECT jsonb_build_object(
            -- ESATTE vs Excel
            'giorni',                a.n,
            'profit_days',           a.profit_days,
            'loss_days',             a.loss_days,
            'pct_profit',            CASE WHEN a.n>0 THEN round(a.profit_days::numeric/a.n*100,6) END,
            'tot',                   round(a.tot,6),
            'mean',                  round(a.mean,6),
            'max_day',               round(a.max_day,6),
            'min_day',               round(a.min_day,6),
            'median',                round(a.median,6),
            'avg_win',               round(a.avg_win,6),
            'avg_loss',              round(a.avg_loss,6),
            'wl_ratio',              CASE WHEN a.loss_days>0 THEN round(a.profit_days::numeric/a.loss_days,6) END,
            'profit_factor',         CASE WHEN a.sum_neg<0 THEN round(a.sum_pos/abs(a.sum_neg),6) END,
            'vol',                   round(a.vol,6),
            'sharpe',                CASE WHEN a.vol>0 THEN round(a.mean/a.vol,6) END,
            'kurtosis',              round(k.kurtosis,6),
            'pct_top5',              CASE WHEN a.tot<>0 THEN round(t5.s/a.tot,6) END,
            'pct_worst',             CASE WHEN a.tot<>0 THEN round(a.min_day/a.tot,6) END,
            -- operative
            'tempo_medio_giorno',    CASE WHEN a.n>0 THEN round(a.sum_tmin/a.n,6) END,
            'guadagno_orario_medio', CASE WHEN a.sum_tmin>0 THEN round(a.tot/(a.sum_tmin/60.0),6) END,
            'profit_per_stake',      CASE WHEN a.sum_stake>0 THEN round(a.tot/a.sum_stake,6) END,
            'stake_medio_giorno',    CASE WHEN a.n>0 THEN round(a.sum_stake/a.n,6) END,
            'media_trade_giorno',    CASE WHEN a.n>0 THEN round(a.n_trades_tot::numeric/a.n,6) END,
            'giornate_perdita_gt_stake', g.giornate_perdita_gt_stake,
            -- STANDARD (rischio)
            'max_drawdown',          round(r.max_drawdown,6),
            'recovery_factor',       CASE WHEN r.max_drawdown<0 THEN round(a.tot/abs(r.max_drawdown),6) END,
            'calmar',                CASE WHEN r.max_drawdown<0 THEN round(a.tot/abs(r.max_drawdown),6) END,
            'ulcer_index',           round(r.ulcer_index,6),
            'upi',                   CASE WHEN r.ulcer_index>0 THEN round(a.mean/r.ulcer_index,6) END,
            'downside_dev',          round(ds.downside_dev,6),
            'sortino',               CASE WHEN ds.downside_dev>0 THEN round(a.mean/ds.downside_dev,6) END,
            'cvar_5',                round(cv.cvar_5,6),
            'max_dd_duration_days',  dd.max_dd_duration_days,
            'n_trades',              a.n_trades_tot
            )
            FROM agg a, risk r, dside ds, cvar cv, top5 t5, kurt k, dd_dur dd, glt g),

        'by_strategia', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'strategia', strategia, 'n', n, 'n_won', n_won,
                'win_rate', CASE WHEN n>0 THEN round(n_won::numeric/n,6) END,
                'stake', round(stake,6), 'net_pnl', round(net_pnl,6),
                'roi', CASE WHEN stake>0 THEN round(net_pnl/stake,6) END,
                'profit_factor', CASE WHEN sum_neg<0 THEN round(sum_pos/abs(sum_neg),6) END
            ) ORDER BY net_pnl DESC)
            FROM (
                SELECT strategia, count(*)::int n,
                       count(*) FILTER (WHERE status='WON')::int n_won,
                       coalesce(sum(stake),0) stake, coalesce(sum(net_pnl),0) net_pnl,
                       coalesce(sum(net_pnl) FILTER (WHERE net_pnl>0),0) sum_pos,
                       coalesce(sum(net_pnl) FILTER (WHERE net_pnl<0),0) sum_neg
                FROM base GROUP BY strategia
            ) s), '[]'::jsonb),

        'by_league', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'league_id', league_id, 'league_name', league_name,
                'n', n, 'n_won', n_won,
                'win_rate', CASE WHEN n>0 THEN round(n_won::numeric/n,6) END,
                'stake', round(stake,6), 'net_pnl', round(net_pnl,6),
                'roi', CASE WHEN stake>0 THEN round(net_pnl/stake,6) END,
                'profit_factor', CASE WHEN sum_neg<0 THEN round(sum_pos/abs(sum_neg),6) END
            ) ORDER BY net_pnl DESC)
            FROM (
                SELECT league_id, max(league_name) league_name, count(*)::int n,
                       count(*) FILTER (WHERE status='WON')::int n_won,
                       coalesce(sum(stake),0) stake, coalesce(sum(net_pnl),0) net_pnl,
                       coalesce(sum(net_pnl) FILTER (WHERE net_pnl>0),0) sum_pos,
                       coalesce(sum(net_pnl) FILTER (WHERE net_pnl<0),0) sum_neg
                FROM base GROUP BY league_id
            ) s), '[]'::jsonb),

        'advice', (
            SELECT jsonb_build_object(
                'n_followed',    count(*) FILTER (WHERE followed_advice)::int,
                'n_off_advice',  count(*) FILTER (WHERE followed_advice IS NOT TRUE)::int,
                'roi_followed',
                    CASE WHEN coalesce(sum(stake) FILTER (WHERE followed_advice),0) > 0
                         THEN round(sum(net_pnl) FILTER (WHERE followed_advice)
                                    / sum(stake) FILTER (WHERE followed_advice), 6) END,
                'roi_off_advice',
                    CASE WHEN coalesce(sum(stake) FILTER (WHERE followed_advice IS NOT TRUE),0) > 0
                         THEN round(sum(net_pnl) FILTER (WHERE followed_advice IS NOT TRUE)
                                    / sum(stake) FILTER (WHERE followed_advice IS NOT TRUE), 6) END
            ) FROM base),

        'discarded', (
            SELECT jsonb_build_object(
                'n', (SELECT count(*)::int FROM public.personal_watchlist WHERE status='SCARTATA'),
                'by_reason', COALESCE((
                    SELECT jsonb_agg(jsonb_build_object('reason', reason, 'n', n) ORDER BY n DESC)
                    FROM (
                        SELECT coalesce(reject_reason,'(non indicato)') reason, count(*)::int n
                        FROM public.personal_watchlist WHERE status='SCARTATA'
                        GROUP BY reject_reason
                    ) d), '[]'::jsonb)
            ))
    ) INTO v_result;

    RETURN v_result;
END;
$$;


-- ============================================================================
-- 2.8 get_personal_trades — drill-down righe trade (+ snapshot-context)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_personal_trades(
    p_from      date    DEFAULT NULL,
    p_to        date    DEFAULT NULL,
    p_strategia text    DEFAULT NULL,
    p_league_id integer DEFAULT NULL,
    p_status    text    DEFAULT NULL,
    p_limit     integer DEFAULT 500
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_result jsonb;
    v_limit  int := LEAST(GREATEST(coalesce(p_limit,500),1), 5000);
BEGIN
    IF p_status IS NOT NULL AND p_status NOT IN ('OPEN','WON','LOST','VOID','PARTIAL') THEN
        RAISE EXCEPTION 'p_status invalido: %', p_status; END IF;

    SELECT coalesce(jsonb_agg(row ORDER BY (row->>'trade_date') DESC, (row->>'id')::bigint DESC), '[]'::jsonb)
      INTO v_result
      FROM (
        SELECT to_jsonb(pt.*) || jsonb_build_object(
                 'legs',
                 COALESCE((SELECT jsonb_agg(to_jsonb(l.*) ORDER BY l.id)
                           FROM public.personal_trade_legs l WHERE l.trade_id = pt.id), '[]'::jsonb)
               ) AS row
        FROM public.personal_trades pt
        WHERE (p_from      IS NULL OR pt.trade_date >= p_from)
          AND (p_to        IS NULL OR pt.trade_date <= p_to)
          AND (p_strategia IS NULL OR pt.strategia  = p_strategia)
          AND (p_league_id IS NULL OR pt.league_id  = p_league_id)
          AND (p_status    IS NULL OR pt.status      = p_status)
        ORDER BY pt.trade_date DESC, pt.id DESC
        LIMIT v_limit
      ) t;

    RETURN coalesce(v_result, '[]'::jsonb);
END;
$$;


-- ============================================================================
-- 2.10 delete_from_watchlist — elimina una riga watchlist SOLO se DA_VALUTARE e
-- senza trade collegati. Serve a ripulire la sezione "Da valutare" senza toccare
-- giocate/scartate (le decisioni prese restano tracciate) ne' i P&L (i trade
-- collegati alimentano le analitiche: vietato cancellarli da qui).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.delete_from_watchlist(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_status text;
    v_ntr    int;
BEGIN
    IF p_id IS NULL THEN
        RAISE EXCEPTION 'p_id nullo';
    END IF;

    SELECT status INTO v_status FROM public.personal_watchlist WHERE id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'watchlist id % non trovato', p_id;
    END IF;

    -- protezione P&L: mai eliminare partite con trade collegati
    SELECT count(*) INTO v_ntr FROM public.personal_trades WHERE watchlist_id = p_id;
    IF v_ntr > 0 THEN
        RAISE EXCEPTION 'Impossibile eliminare: % trade collegati (i P&L ne dipendono)', v_ntr;
    END IF;

    -- eliminabili solo le partite ancora DA_VALUTARE
    IF v_status <> 'DA_VALUTARE' THEN
        RAISE EXCEPTION 'Eliminabili solo le partite DA_VALUTARE (stato attuale: %)', v_status;
    END IF;

    DELETE FROM public.personal_watchlist WHERE id = p_id;
    RETURN jsonb_build_object('deleted', p_id);
END;
$$;


-- ============================================================================
-- 2.11 reset_personal_report — SVUOTA tutta la reportistica personale: trade,
-- leg (coperture/hedge) e watchlist (ogni stato). Operazione manuale dell'utente
-- (con conferma in UI) per ripartire da zero dopo i test. Tocca SOLO le tabelle
-- personal_* (NIENTE matches/fixture_predictions/analytics/ecc.).
-- Ritorna i conteggi delle righe eliminate.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.reset_personal_report()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    n_legs   int;
    n_trades int;
    n_wl     int;
BEGIN
    -- ordine FK-safe: prima le leg (FK -> trades), poi i trade (FK -> watchlist),
    -- infine la watchlist.
    -- NB: il WHERE e' OBBLIGATORIO -> Supabase carica pg_safeupdate sul ruolo
    -- authenticated, che blocca DELETE/UPDATE senza filtro ("DELETE requires a
    -- WHERE clause") anche dentro le funzioni. Uso "id > 0" (non "id IS NOT NULL")
    -- perche' il planner NON puo' semplificarlo a costante: gli id PK sono sempre
    -- >= 1, quindi elimina comunque TUTTE le righe.
    WITH d AS (DELETE FROM public.personal_trade_legs WHERE id > 0 RETURNING 1) SELECT count(*) INTO n_legs   FROM d;
    WITH d AS (DELETE FROM public.personal_trades     WHERE id > 0 RETURNING 1) SELECT count(*) INTO n_trades FROM d;
    WITH d AS (DELETE FROM public.personal_watchlist  WHERE id > 0 RETURNING 1) SELECT count(*) INTO n_wl     FROM d;

    RETURN jsonb_build_object('legs', n_legs, 'trades', n_trades, 'watchlist', n_wl);
END;
$$;


-- ============================================================================
-- GRANTS — REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role
-- ============================================================================
REVOKE ALL ON FUNCTION public.add_to_watchlist(bigint)                                          FROM public;
REVOKE ALL ON FUNCTION public.get_watchlist(text)                                               FROM public;
REVOKE ALL ON FUNCTION public.set_watchlist_decision(bigint,text,text,text,text,text,text[])    FROM public;
REVOKE ALL ON FUNCTION public.add_personal_trade(jsonb)                                         FROM public;
REVOKE ALL ON FUNCTION public.add_trade_leg(jsonb)                                              FROM public;
REVOKE ALL ON FUNCTION public.settle_personal_trade(bigint,text,text,numeric,numeric)           FROM public;
REVOKE ALL ON FUNCTION public.recompute_personal_trade(bigint)                                  FROM public;
REVOKE ALL ON FUNCTION public.get_personal_report(date,date,text,integer,text)                  FROM public;
REVOKE ALL ON FUNCTION public.get_personal_trades(date,date,text,integer,text,integer)          FROM public;
REVOKE ALL ON FUNCTION public.delete_from_watchlist(bigint)                                     FROM public;
REVOKE ALL ON FUNCTION public.reset_personal_report()                                           FROM public;

GRANT EXECUTE ON FUNCTION public.add_to_watchlist(bigint)                                        TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_watchlist(text)                                             TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.set_watchlist_decision(bigint,text,text,text,text,text,text[])  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.add_personal_trade(jsonb)                                       TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.add_trade_leg(jsonb)                                            TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.settle_personal_trade(bigint,text,text,numeric,numeric)         TO authenticated, service_role;
-- recompute_personal_trade è INTERNA (§2.6): chiamata solo via PERFORM dalle altre
-- funzioni SECURITY DEFINER (girano come definer/postgres). NON va esposta al client.
GRANT EXECUTE ON FUNCTION public.recompute_personal_trade(bigint)                                TO service_role;
-- Supabase concede EXECUTE ad authenticated di default su ogni funzione: lo revochiamo
-- esplicitamente (recompute è interna, deve restare solo service_role/definer).
REVOKE EXECUTE ON FUNCTION public.recompute_personal_trade(bigint)                              FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_personal_report(date,date,text,integer,text)                TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_personal_trades(date,date,text,integer,text,integer)        TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.delete_from_watchlist(bigint)                                   TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.reset_personal_report()                                         TO authenticated, service_role;

-- ============================================================================
-- 2.9 LOCKDOWN — revoca esecuzione ad anon per TUTTE le RPC sopra (MAI anon).
-- (Pattern di security_lockdown.sql.)
-- ============================================================================
REVOKE EXECUTE ON FUNCTION public.add_to_watchlist(bigint)                                       FROM anon;
REVOKE EXECUTE ON FUNCTION public.get_watchlist(text)                                            FROM anon;
REVOKE EXECUTE ON FUNCTION public.set_watchlist_decision(bigint,text,text,text,text,text,text[]) FROM anon;
REVOKE EXECUTE ON FUNCTION public.add_personal_trade(jsonb)                                      FROM anon;
REVOKE EXECUTE ON FUNCTION public.add_trade_leg(jsonb)                                           FROM anon;
REVOKE EXECUTE ON FUNCTION public.settle_personal_trade(bigint,text,text,numeric,numeric)        FROM anon;
REVOKE EXECUTE ON FUNCTION public.recompute_personal_trade(bigint)                               FROM anon;
REVOKE EXECUTE ON FUNCTION public.get_personal_report(date,date,text,integer,text)               FROM anon;
REVOKE EXECUTE ON FUNCTION public.get_personal_trades(date,date,text,integer,text,integer)       FROM anon;
REVOKE EXECUTE ON FUNCTION public.delete_from_watchlist(bigint)                                  FROM anon;
REVOKE EXECUTE ON FUNCTION public.reset_personal_report()                                        FROM anon;
