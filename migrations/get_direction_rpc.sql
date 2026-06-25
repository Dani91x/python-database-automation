-- get_direction_rpc.sql
-- RPC del cruscotto DIREZIONE. Per una partita, per ogni mercato:
--   direzione  = leader con FALLBACK Poisson -> ML -> TacticAI -> API
--                (il cruscotto resta visibile anche se manca Poisson).
--   affidabilita = hit-rate reale dalla pagella (direction_pagella) SOLO quando c'e'
--                  la previsione Poisson (per-lega con SHRINKAGE empirical-Bayes verso
--                  il globale, K=50). Quando manca Poisson -> affidabilita/wilson/lift
--                  NULL e il mercato e' marcato poisson_missing/calibrated=false.
--   banda Wilson 95%, lift = affid - base, concordanza motori, quota, dettaglio per-motore.
--
-- API (motore "book/consenso") preso da fixture_predictions:
--   * 1x2 dall'advice testuale: "Winner : <team>" -> H/A ; "Double chance : draw or
--     <away>" -> X2 ; "<home> or draw" -> 1X. (prefisso "Combo " e suffisso
--     " and +/-X.5 goals" rimossi).
--   * over_1_5/2_5/3_5 da under_over_line: "+X.5" -> Over, "-X.5" -> Under, applicato
--     SOLO al mercato la cui linea coincide.
--   * btts / ht_1x2 / first_half_over_0_5: NON presenti nell'API -> nessuna direzione API.
--
-- I VALORI LIVE DEI MOTORI poisson/ml/tacticai sono letti dai json di fixture_predictions
-- con la STESSA normalizzazione di build_analytics_signals.py (extract_*).
-- Idempotente: CREATE OR REPLACE. SECURITY DEFINER. Certificata da _certify_direction.py.

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
  v_home text; v_away text; v_advice text; v_uol text;
  v_adv_main text;     -- advice ripulito da "Combo " e " and +/-X.5 goals"
  v_uo_dir text;       -- 'Over' / 'Under' / NULL
  v_uo_line numeric;   -- 1.5 / 2.5 / 3.5 / NULL
  v_api1x2 text;       -- 'H'/'A'/'1X'/'X2'/NULL
  v_result  jsonb;
  K  constant numeric := 50;     -- forza shrinkage (partite-equivalenti del prior globale)
  z  constant numeric := 1.96;   -- 95%
BEGIN
  IF p_fixture_id IS NULL THEN
    RAISE EXCEPTION 'p_fixture_id nullo';
  END IF;
  SELECT league_id, db_json_analisi, model_predictions_json, tactical_engine_json, flat_summary,
         home_team_name, away_team_name, advice, under_over_line
    INTO v_league, v_dj, v_mp, v_tj, v_fs, v_home, v_away, v_advice, v_uol
    FROM public.fixture_predictions WHERE fixture_id = p_fixture_id;
  IF NOT FOUND THEN   -- fixture inesistente: errore esplicito, niente degrado silenzioso
    RETURN jsonb_build_object('fixture_id', p_fixture_id, 'league_id', NULL,
                              'error', 'fixture_id non trovato', 'markets', '[]'::jsonb);
  END IF;

  -- ---- API 1x2 dall'advice -------------------------------------------------
  -- togli prefisso "Combo " e suffisso " and +/-X.5 goals" (robusto a team con " and ")
  v_adv_main := btrim(regexp_replace(
                  regexp_replace(coalesce(v_advice,''), '^Combo[[:space:]]+', ''),
                  '[[:space:]]+and[[:space:]]+[+-][0-9.]+[[:space:]]+goals[[:space:]]*$', ''));
  v_api1x2 := CASE
    WHEN v_adv_main ILIKE 'Winner : %' THEN
      CASE
        WHEN btrim(substring(v_adv_main from 'Winner : (.*)$')) = v_home THEN 'H'
        WHEN btrim(substring(v_adv_main from 'Winner : (.*)$')) = v_away THEN 'A'
        ELSE NULL END
    WHEN v_adv_main ILIKE 'Double chance : %' THEN
      CASE
        WHEN btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',1)) = 'draw'
             AND btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',2)) = v_home THEN '1X'
        WHEN btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',1)) = 'draw'
             AND btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',2)) = v_away THEN 'X2'
        WHEN btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',2)) = 'draw'
             AND btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',1)) = v_home THEN '1X'
        WHEN btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',2)) = 'draw'
             AND btrim(split_part(substring(v_adv_main from 'Double chance : (.*)$'),' or ',1)) = v_away THEN 'X2'
        ELSE NULL END
    ELSE NULL END;

  -- ---- API over da under_over_line ("+2.5" -> Over 2.5 ; "-3.5" -> Under 3.5) ----
  v_uo_dir  := CASE WHEN left(btrim(coalesce(v_uol,'')),1)='+' THEN 'Over'
                    WHEN left(btrim(coalesce(v_uol,'')),1)='-' THEN 'Under' ELSE NULL END;
  v_uo_line := NULLIF(regexp_replace(coalesce(v_uol,''), '[^0-9.]', '', 'g'), '')::numeric;

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
      (COALESCE(v_dj->'markets_calibrated'->m.market, v_dj->'markets'->m.market)->>m.pois_key)::numeric AS pp,
      (v_mp->'targets'->m.ml_target->>m.ml_class)::numeric AS mlp,
      (CASE WHEN m.tac_scope='ft' THEN (v_tj->'markets'->>m.tac_key)
            ELSE (v_tj->'markets_ht'->>m.tac_key) END)::numeric AS tap
    FROM map m
  ),
  -- direzione API per mercato (1x2 dall'advice; over da under_over_line)
  apimkt AS (
    SELECT DISTINCT m.market,
      CASE m.market
        WHEN '1x2'      THEN v_api1x2
        WHEN 'over_1_5' THEN CASE WHEN v_uo_line = 1.5 THEN v_uo_dir END
        WHEN 'over_2_5' THEN CASE WHEN v_uo_line = 2.5 THEN v_uo_dir END
        WHEN 'over_3_5' THEN CASE WHEN v_uo_line = 3.5 THEN v_uo_dir END
        ELSE NULL END AS api_dir
    FROM map m
  ),
  -- direzione di ogni motore (argmax) + presenza motori
  amax AS (
    SELECT b.market,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.pp  IS NOT NULL ORDER BY x.pp  DESC, selection LIMIT 1) AS poisson_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.mlp IS NOT NULL ORDER BY x.mlp DESC, selection LIMIT 1) AS ml_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.tap IS NOT NULL ORDER BY x.tap DESC, selection LIMIT 1) AS tacticai_dir,
      bool_or(b.pp  IS NOT NULL) AS has_pois,
      bool_or(b.mlp IS NOT NULL) AS has_ml,
      bool_or(b.tap IS NOT NULL) AS has_tac
    FROM bf b GROUP BY b.market
  ),
  -- LEADER con fallback Poisson -> ML -> TacticAI -> API. Tiene la prob Poisson della
  -- direzione (per la pagella): NULL se il leader non e' Poisson o Poisson assente.
  dir AS (
    SELECT a.market,
      COALESCE(a.poisson_dir, a.ml_dir, a.tacticai_dir, ap.api_dir) AS direction,
      a.has_pois AS has_poisson,
      (SELECT x.pp FROM bf x WHERE x.market=a.market
         AND x.selection = COALESCE(a.poisson_dir, a.ml_dir, a.tacticai_dir, ap.api_dir)) AS p
    FROM amax a
    LEFT JOIN apimkt ap ON ap.market = a.market
    WHERE COALESCE(a.poisson_dir, a.ml_dir, a.tacticai_dir, ap.api_dir) IS NOT NULL
  ),
  -- quota best-effort dalla tabella analytics_bets (puo' mancare su partite freschissime)
  od AS (
    SELECT d.market, coalesce(ab.odds_betfair, ab.odds_book)::numeric AS odds
    FROM dir d
    LEFT JOIN public.analytics_bets ab
      ON ab.fixture_id = p_fixture_id AND ab.market = d.market AND ab.selection = d.direction
  ),
  pag AS (   -- pagella Poisson per la direzione (solo se c'e' prob Poisson): lega + globale
    SELECT d.market, d.direction, d.p,
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
  wil AS (   -- Wilson 95% — SOLO i mercati con affidabilita' (pagella) calibrata.
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
  )
  SELECT jsonb_build_object(
    'fixture_id', p_fixture_id,
    'league_id', v_league,
    'generated_at', now(),
    'poisson_present', COALESCE((SELECT bool_or(has_poisson) FROM dir), false),
    'markets', COALESCE(jsonb_agg(jsonb_build_object(
        'market', d.market,
        'direction', d.direction,
        'calibrated', (w.affid IS NOT NULL),
        'poisson_missing', NOT d.has_poisson,
        'affidabilita', round(w.affid, 4),
        'wilson_low',  CASE WHEN w.affid IS NOT NULL THEN round(GREATEST(0, w.wc - w.wh), 4) END,
        'wilson_high', CASE WHEN w.affid IS NOT NULL THEN round(LEAST(1,  w.wc + w.wh), 4) END,
        'n', CASE WHEN w.affid IS NOT NULL THEN round(w.eff_n)::int END,
        'base', round(w.base_g, 4),
        'lift', CASE WHEN w.affid IS NOT NULL THEN round(w.affid - w.base_g, 4) END,
        'odds', o.odds,
        'scope', w.scope,
        'concordi',
          (CASE WHEN am.poisson_dir  = d.direction THEN jsonb_build_array('poisson')  ELSE '[]'::jsonb END) ||
          (CASE WHEN am.ml_dir       = d.direction THEN jsonb_build_array('ml')       ELSE '[]'::jsonb END) ||
          (CASE WHEN am.tacticai_dir = d.direction THEN jsonb_build_array('tacticai') ELSE '[]'::jsonb END) ||
          (CASE WHEN ap.api_dir      = d.direction THEN jsonb_build_array('api')      ELSE '[]'::jsonb END),
        'motori_totali',
            (CASE WHEN am.has_pois THEN 1 ELSE 0 END)
          + (CASE WHEN am.has_ml   THEN 1 ELSE 0 END)
          + (CASE WHEN am.has_tac  THEN 1 ELSE 0 END)
          + (CASE WHEN ap.api_dir IS NOT NULL THEN 1 ELSE 0 END),
        'engines', jsonb_build_object(
            'poisson', e.poisson, 'ml', e.ml, 'tacticai', e.tacticai,
            'api', CASE WHEN ap.api_dir IS NOT NULL THEN jsonb_build_object('dir', ap.api_dir) ELSE NULL END)
      ) ORDER BY (w.affid IS NULL), (w.affid - w.base_g) DESC NULLS LAST, d.market), '[]'::jsonb)
  ) INTO v_result
  FROM dir d
  LEFT JOIN wil    w  ON w.market  = d.market
  LEFT JOIN eng    e  ON e.market  = d.market
  LEFT JOIN amax   am ON am.market = d.market
  LEFT JOIN apimkt ap ON ap.market = d.market
  LEFT JOIN od     o  ON o.market  = d.market;

  RETURN COALESCE(v_result,
                  jsonb_build_object('fixture_id', p_fixture_id, 'league_id', v_league,
                                     'poisson_present', false, 'markets', '[]'::jsonb));
END;
$$;

REVOKE ALL ON FUNCTION public.get_direction(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_direction(bigint) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public._prob_bucket(numeric) FROM public;
GRANT EXECUTE ON FUNCTION public._prob_bucket(numeric) TO authenticated, service_role;
