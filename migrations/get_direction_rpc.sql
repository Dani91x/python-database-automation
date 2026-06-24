-- get_direction_rpc.sql
-- RPC del cruscotto DIREZIONE. Per una partita, per ogni mercato calibrato:
--   direzione  = argmax Poisson (motore leader, certificato dai test come il migliore)
--   affidabilita = hit-rate reale dalla pagella (direction_pagella), per-lega con SHRINKAGE
--                  empirical-Bayes verso il globale (K=50)
--   banda Wilson 95%, lift = affid - base, concordanza motori, quota, dettaglio per-motore.
-- Tutto su DB. Letta dal frontend via supabase.rpc('get_direction', {p_fixture_id}).
-- Idempotente: CREATE OR REPLACE. SECURITY DEFINER (legge bet_features/pagella lockate).

-- helper: fascia di probabilita' [lo,hi) — STESSA convenzione del builder build_direzione.py
CREATE OR REPLACE FUNCTION public._prob_bucket(p numeric)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
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
  v_result  jsonb;
  K  constant numeric := 50;     -- forza shrinkage (partite-equivalenti del prior globale)
  z  constant numeric := 1.96;   -- 95%
BEGIN
  IF p_fixture_id IS NULL THEN
    RAISE EXCEPTION 'p_fixture_id nullo';
  END IF;
  SELECT league_id INTO v_league FROM public.fixture_predictions WHERE fixture_id = p_fixture_id;
  IF NOT FOUND THEN   -- fixture inesistente: errore esplicito, niente degrado silenzioso
    RETURN jsonb_build_object('fixture_id', p_fixture_id, 'league_id', NULL,
                              'error', 'fixture_id non trovato', 'markets', '[]'::jsonb);
  END IF;

  WITH bf AS (
    SELECT market, selection,
           poisson_prob::numeric  AS pp,
           ml_prob::numeric       AS mlp,
           tacticai_prob::numeric AS tap,
           api_home::numeric AS ah, api_draw::numeric AS ad, api_away::numeric AS aa,
           api_over_line::numeric AS aol,
           odds::numeric AS od
    FROM public.bet_features
    WHERE fixture_id = p_fixture_id
      AND market IN ('1x2','ht_1x2','over_1_5','over_2_5','over_3_5','btts','first_half_over_0_5')
  ),
  dir AS (   -- direzione = argmax Poisson per mercato (+ quota di quella selezione)
    --        tiebreaker 'selection' per determinismo su prob identiche (di fatto impossibili coi float)
    SELECT DISTINCT ON (market) market, selection AS direction, pp AS p, od AS odds
    FROM bf WHERE pp IS NOT NULL
    ORDER BY market, pp DESC, selection
  ),
  pag AS (   -- pagella Poisson per la direzione: riga della lega + riga globale
    SELECT d.market, d.direction, d.p, d.odds, public._prob_bucket(d.p) AS bkt,
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
    SELECT market, direction, p, odds, bkt, base_g,
      CASE WHEN n_l IS NOT NULL THEN (n_l*hr_l + K*hr_g)/(n_l+K) ELSE hr_g END AS affid,
      CASE WHEN n_l IS NOT NULL THEN n_l + K ELSE n_g END AS eff_n,
      CASE WHEN n_l IS NOT NULL THEN 'lega' ELSE 'globale' END AS scope
    FROM pag
  ),
  wil AS (   -- Wilson 95%
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
  amax AS (  -- direzione di ogni motore (per la concordanza)
    SELECT b.market,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.pp  IS NOT NULL ORDER BY x.pp  DESC LIMIT 1) AS poisson_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.mlp IS NOT NULL ORDER BY x.mlp DESC LIMIT 1) AS ml_dir,
      (SELECT selection FROM bf x WHERE x.market=b.market AND x.tap IS NOT NULL ORDER BY x.tap DESC LIMIT 1) AS tacticai_dir,
      bool_or(b.mlp IS NOT NULL) AS has_ml,
      bool_or(b.tap IS NOT NULL) AS has_tac
    FROM bf b GROUP BY b.market
  ),
  apidir AS ( -- direzione API: 1x2/ht_1x2 da home/draw/away; over da over_line.
    --          In caso di PAREGGIO tra esiti -> NULL (niente direzione arbitraria che gonfi la concordanza).
    SELECT market,
      CASE
        WHEN market IN ('1x2','ht_1x2') THEN
          CASE
            WHEN MAX(ah) IS NULL AND MAX(ad) IS NULL AND MAX(aa) IS NULL THEN NULL
            WHEN MAX(ah) > COALESCE(MAX(ad),-1) AND MAX(ah) > COALESCE(MAX(aa),-1) THEN 'H'
            WHEN MAX(ad) > COALESCE(MAX(ah),-1) AND MAX(ad) > COALESCE(MAX(aa),-1) THEN 'D'
            WHEN MAX(aa) > COALESCE(MAX(ah),-1) AND MAX(aa) > COALESCE(MAX(ad),-1) THEN 'A'
            ELSE NULL   -- pareggio: nessun vincitore netto
          END
        WHEN MAX(aol) IS NOT NULL THEN CASE WHEN MAX(aol) > 50 THEN 'Over' ELSE 'Under' END
        ELSE NULL
      END AS api_dir,
      bool_or(ah IS NOT NULL OR aol IS NOT NULL) AS has_api
    FROM bf GROUP BY market
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
        'odds', w.odds,
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
  LEFT JOIN apidir ap ON ap.market = w.market;

  RETURN COALESCE(v_result,
                  jsonb_build_object('fixture_id', p_fixture_id, 'league_id', v_league, 'markets', '[]'::jsonb));
END;
$$;

REVOKE ALL ON FUNCTION public.get_direction(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_direction(bigint) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public._prob_bucket(numeric) FROM public;
GRANT EXECUTE ON FUNCTION public._prob_bucket(numeric) TO authenticated, service_role;
