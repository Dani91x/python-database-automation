-- get_direction_rpc.sql
-- RPC del cruscotto DIREZIONE. Per una partita, per ogni mercato calibrato:
--   direzione  = argmax Poisson (motore leader, certificato dai test come il migliore)
--   affidabilita = hit-rate reale dalla pagella (direction_pagella), per-lega con SHRINKAGE
--                  empirical-Bayes verso il globale (K=50)
--   banda Wilson 95%, lift = affid - base, concordanza motori, quota, dettaglio per-motore.
--
-- I VALORI LIVE DEI MOTORI (poisson/ml/tacticai/api) sono letti DIRETTAMENTE dai json di
-- fixture_predictions (db_json_analisi / model_predictions_json / tactical_engine_json /
-- flat_summary), con la STESSA normalizzazione di build_analytics_signals.py (extract_*),
-- cosi' la concordanza e' IMMEDIATA (niente attesa della catena analytics_signals/_bets).
-- L'affidabilita' resta calibrata sullo storico (pagella). La quota e' best-effort da
-- analytics_bets (puo' mancare su partite freschissime).
-- Idempotente: CREATE OR REPLACE. SECURITY DEFINER (legge fixture_predictions/pagella).

-- helper: fascia di probabilita' [lo,hi) — STESSA convenzione del builder build_direzione.py
CREATE OR REPLACE FUNCTION public._prob_bucket(p numeric)
RETURNS text LANGUAGE sql IMMUTABLE
SET search_path = public, pg_temp AS $$
  SELECT CASE
    WHEN p IS NULL  THEN NULL
    WHEN p < 0.30   THEN '<.30'
    WHEN p < 0.40   THEN '.30-.40'
    WHEN p < 0.50   THEN '.40-.50'
    WHEN p < 0.60   THEN '.50-.60'
    WHEN p < 0.70   THEN '.60-.70'
    ELSE '>.70'
  END;
$$;

CREATE OR REPLACE FUNCTION public.get_direction(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
SET statement_timeout = '15s'
AS $$
DECLARE
  v_league  bigint;
  v_dj jsonb; v_mp jsonb; v_tj jsonb; v_fs jsonb;
  v_result  jsonb;
  K  constant numeric := 50;     -- forza shrinkage (partite-equivalenti del prior globale)
  z  constant numeric := 1.96;   -- 95%
BEGIN
  IF p_fixture_id IS NULL THEN
    RAISE EXCEPTION 'p_fixture_id nullo';
  END IF;
  SELECT league_id, db_json_analisi, model_predictions_json, tactical_engine_json, flat_summary
    INTO v_league, v_dj, v_mp, v_tj, v_fs
    FROM public.fixture_predictions WHERE fixture_id = p_fixture_id;
  IF NOT FOUND THEN   -- fixture inesistente: errore esplicito, niente degrado silenzioso
    RETURN jsonb_build_object('fixture_id', p_fixture_id, 'league_id', NULL,
                              'error', 'fixture_id non trovato', 'markets', '[]'::jsonb);
  END IF;

  WITH
  -- mappa canonica mercato/selezione -> chiave json di OGNI motore (specchio di extract_*)
  map(market, selection, pois_key, ml_target, ml_class, tac_scope, tac_key) AS (
    VALUES
      ('1x2','H','H','target_1x2','H','ft','home'),
      ('1x2','D','D','target_1x2','D','ft','draw'),
      ('1x2','A','A','target_1x2','A','ft','away'),
      ('ht_1x2','H','H','target_ht_1x2','H','ht','home'),
      ('ht_1x2','D','D','target_ht_1x2','D','ht','draw'),
      ('ht_1x2','A','A','target_ht_1x2','A','ht','away'),
      ('over_1_5','Over','True','target_over_1_5','True','ft','over_1_5'),
      ('over_1_5','Under','False','target_over_1_5','False','ft','under_1_5'),
      ('over_2_5','Over','True','target_over_2_5','True','ft','over_2_5'),
      ('over_2_5','Under','False','target_over_2_5','False','ft','under_2_5'),
      ('over_3_5','Over','True','target_over_3_5','True','ft','over_3_5'),
      ('over_3_5','Under','False','target_over_3_5','False','ft','under_3_5'),
      ('btts','Yes','True','target_btts','True','ft','btts_yes'),
      ('btts','No','False','target_btts','False','ft','btts_no'),
      ('first_half_over_0_5','Over','True','target_ht_over_0_5','True','ht','over_0_5'),
      ('first_half_over_0_5','Under','False','target_ht_over_0_5','False','ht','under_0_5')
  ),
  -- prob LIVE dei 3 motori per ogni (mercato, selezione), dai json di fixture_predictions
  bf AS (
    SELECT m.market, m.selection,
      -- Poisson: markets_calibrated.<market> se presente, altrimenti markets.<market>
      -- (fallback a livello di MERCATO, come extract_poisson), poi ->> chiave selezione
      (COALESCE(v_dj->'markets_calibrated'->m.market, v_dj->'markets'->m.market)->>m.pois_key)::numeric AS pp,
      -- ML: targets.<target>.<class>
      (v_mp->'targets'->m.ml_target->>m.ml_class)::numeric AS mlp,
      -- TacticAI: markets.<key> (FT) oppure markets_ht.<key> (HT)
      (CASE WHEN m.tac_scope='ft' THEN (v_tj->'markets'->>m.tac_key)
            ELSE (v_tj->'markets_ht'->>m.tac_key) END)::numeric AS tap
    FROM map m
  ),
  dir AS (   -- direzione = argmax Poisson per mercato (tiebreaker 'selection')
    SELECT DISTINCT ON (market) market, selection AS direction, pp AS p
    FROM bf WHERE pp IS NOT NULL
    ORDER BY market, pp DESC, selection
  ),
  -- quota best-effort dalla tabella analytics_bets (puo' mancare su partite freschissime).
  -- odds_betfair/odds_book sono colonne NUMERIC nel DDL -> il cast e' sicuro (no parse di stringhe).
  od AS (
    SELECT d.market, coalesce(ab.odds_betfair, ab.odds_book)::numeric AS odds
    FROM dir d
    LEFT JOIN public.analytics_bets ab
      ON ab.fixture_id = p_fixture_id AND ab.market = d.market AND ab.selection = d.direction
  ),
  pag AS (   -- pagella Poisson per la direzione: riga della lega + riga globale
    SELECT d.market, d.direction, d.p, public._prob_bucket(d.p) AS bkt,
           pl.n AS n_l, pl.hit_rate AS hr_l,
           pg.n AS n_g, pg.hit_rate AS hr_g, pg.base_rate AS base_g
    FROM dir d
    LEFT JOIN public.direction_pagella pg
      ON pg.engine='poisson' AND pg.market=d.market AND pg.selection=d.direction
     AND pg.league_id=0 AND pg.prob_bucket=public._prob_bucket(d.p)
    LEFT JOIN public.direction_pagella pl
      ON pl.engine='poisson' AND pl.market=d.market AND pl.selection=d.direction
     AND pl.league_id=COALESCE(v_league,-1) AND pl.prob_bucket=public._prob_bucket(d.p)
  ),
  calc AS (  -- shrinkage lega->globale
    SELECT market, direction, p, base_g,
      CASE WHEN n_l IS NOT NULL THEN (n_l*hr_l + K*hr_g)/(n_l+K) ELSE hr_g END AS affid,
      CASE WHEN n_l IS NOT NULL THEN n_l + K ELSE n_g END AS eff_n,
      CASE WHEN n_l IS NOT NULL THEN 'lega' ELSE 'globale' END AS scope
    FROM pag
  ),
  wil AS (   -- Wilson 95%. Il WHERE esclude (INTENZIONALMENTE) i mercati senza pagella:
    --        il cruscotto mostra solo i mercati con affidabilita' storica calibrata.
    SELECT *,
      (affid + z*z/(2*eff_n)) / (1 + z*z/eff_n) AS wc,
      z*sqrt(affid*(1-affid)/eff_n + z*z/(4*eff_n*eff_n)) / (1 + z*z/eff_n) AS wh
    FROM calc
    WHERE affid IS NOT NULL AND eff_n IS NOT NULL AND eff_n > 0
  ),
  eng AS (   -- "cosa dice ogni motore": prob per selezione
    SELECT market,
      jsonb_object_agg(selection, pp)  FILTER (WHERE pp  IS NOT NULL) AS poisson,
      jsonb_object_agg(selection, mlp) FILTER (WHERE mlp IS NOT NULL) AS ml,
      jsonb_object_agg(selection, tap) FILTER (WHERE tap IS NOT NULL) AS tacticai
    FROM bf GROUP BY market
  ),
  amax AS (  -- direzione di ogni motore (per la concordanza). NB: bf ha al piu' 16 righe
    --        (mappa fissa) -> le subquery correlate qui sotto sono trascurabili.
    SELECT b.market,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.pp  IS NOT NULL ORDER BY x.pp  DESC, selection LIMIT 1) AS poisson_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.mlp IS NOT NULL ORDER BY x.mlp DESC, selection LIMIT 1) AS ml_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.tap IS NOT NULL ORDER BY x.tap DESC, selection LIMIT 1) AS tacticai_dir,
      bool_or(b.mlp IS NOT NULL) AS has_ml,
      bool_or(b.tap IS NOT NULL) AS has_tac
    FROM bf b GROUP BY b.market
  ),
  api AS (   -- consensus book (flat_summary): direzione SOLO su 1x2/ht_1x2
    SELECT (v_fs->>'percent_home')::numeric AS ph,
           (v_fs->>'percent_draw')::numeric AS pd,
           (v_fs->>'percent_away')::numeric AS pa
  ),
  apidir AS (
    SELECT d.market,
      CASE WHEN d.market IN ('1x2','ht_1x2') THEN
        CASE
          WHEN a.ph IS NULL AND a.pd IS NULL AND a.pa IS NULL THEN NULL
          WHEN a.ph > COALESCE(a.pd,-1) AND a.ph > COALESCE(a.pa,-1) THEN 'H'
          WHEN a.pd > COALESCE(a.ph,-1) AND a.pd > COALESCE(a.pa,-1) THEN 'D'
          WHEN a.pa > COALESCE(a.ph,-1) AND a.pa > COALESCE(a.pd,-1) THEN 'A'
          ELSE NULL   -- pareggio fra esiti: niente direzione
        END
      ELSE NULL END AS api_dir,
      (d.market IN ('1x2','ht_1x2') AND (a.ph IS NOT NULL OR a.pd IS NOT NULL OR a.pa IS NOT NULL)) AS has_api
    FROM dir d CROSS JOIN api a
  )
  SELECT jsonb_build_object(
    'fixture_id', p_fixture_id,
    'league_id', v_league,
    'generated_at', now(),
    'markets', COALESCE(jsonb_agg(jsonb_build_object(
        'market', w.market,
        'direction', w.direction,
        'affidabilita', round(w.affid, 4),
        'wilson_low',  round(GREATEST(0, w.wc - w.wh), 4),
        'wilson_high', round(LEAST(1,  w.wc + w.wh), 4),
        'n', round(w.eff_n)::int,
        'base', round(w.base_g, 4),
        'lift', round(w.affid - w.base_g, 4),
        'odds', o.odds,
        'scope', w.scope,
        'concordi',
          (CASE WHEN am.poisson_dir  = w.direction THEN jsonb_build_array('poisson')  ELSE '[]'::jsonb END) ||
          (CASE WHEN am.ml_dir       = w.direction THEN jsonb_build_array('ml')       ELSE '[]'::jsonb END) ||
          (CASE WHEN am.tacticai_dir = w.direction THEN jsonb_build_array('tacticai') ELSE '[]'::jsonb END) ||
          (CASE WHEN ap.api_dir      = w.direction THEN jsonb_build_array('api')      ELSE '[]'::jsonb END),
        'motori_totali', 1
          + (CASE WHEN am.has_ml  THEN 1 ELSE 0 END)
          + (CASE WHEN am.has_tac THEN 1 ELSE 0 END)
          + (CASE WHEN ap.has_api THEN 1 ELSE 0 END),
        'engines', jsonb_build_object(
            'poisson', e.poisson, 'ml', e.ml, 'tacticai', e.tacticai,
            'api', CASE WHEN ap.api_dir IS NOT NULL THEN jsonb_build_object('dir', ap.api_dir) ELSE NULL END)
      ) ORDER BY (w.affid - w.base_g) DESC), '[]'::jsonb)
  ) INTO v_result
  FROM wil w
  LEFT JOIN eng    e  ON e.market  = w.market
  LEFT JOIN amax   am ON am.market = w.market
  LEFT JOIN apidir ap ON ap.market = w.market
  LEFT JOIN od     o  ON o.market  = w.market;

  RETURN COALESCE(v_result,
                  jsonb_build_object('fixture_id', p_fixture_id, 'league_id', v_league, 'markets', '[]'::jsonb));
END;
$$;

REVOKE ALL ON FUNCTION public.get_direction(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_direction(bigint) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public._prob_bucket(numeric) FROM public;
GRANT EXECUTE ON FUNCTION public._prob_bucket(numeric) TO authenticated, service_role;
