-- betfair_full_odds_rpc.sql
-- Espone le quote Betfair complete (betfair_market_odds) al frontend via RPC SECURITY DEFINER.

-- 1) TUTTI i mercati con back/lay (per il pannello "Quote Betfair").
--    Output: [ { "market": "Match Odds", "runners": [ {selection, sort_priority, back[], lay[]}, ... ] }, ... ]
CREATE OR REPLACE FUNCTION public.get_betfair_full_odds(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
  SELECT coalesce(jsonb_agg(mk ORDER BY (mk->>'market')), '[]'::jsonb)
  FROM (
    SELECT jsonb_build_object(
      'market', market_name,
      'runners', jsonb_agg(
        jsonb_build_object('selection', selection, 'sort_priority', sort_priority,
                           'back', back, 'lay', lay)
        ORDER BY sort_priority NULLS LAST, selection)
    ) AS mk
    FROM public.betfair_market_odds
    WHERE fixture_id = p_fixture_id
    GROUP BY market_name
  ) t;
$$;

-- 2) Quote back/lay per i 7 mercati CANONICI del cruscotto Direzione.
--    Mappa: 1x2/ht_1x2 via sort_priority (1=Home, 2=Away, 3=Draw); over/btts via nome runner.
--    Output: { "1x2": {"H":{back,lay},"D":..,"A":..}, "over_2_5": {"Over":..,"Under":..}, ... }
CREATE OR REPLACE FUNCTION public.get_betfair_direction_odds(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
  WITH m AS (
    SELECT market_name, selection, sort_priority, back, lay
    FROM public.betfair_market_odds WHERE fixture_id = p_fixture_id
  ),
  map(cmkt, csel, bf_market, bf_runner, bf_sort) AS (VALUES
    ('1x2','H','Match Odds', NULL, 1),
    ('1x2','A','Match Odds', NULL, 2),
    ('1x2','D','Match Odds', NULL, 3),
    ('ht_1x2','H','Half Time', NULL, 1),
    ('ht_1x2','A','Half Time', NULL, 2),
    ('ht_1x2','D','Half Time', NULL, 3),
    ('over_1_5','Over','Over/Under 1.5 Goals','Over 1.5 Goals', NULL),
    ('over_1_5','Under','Over/Under 1.5 Goals','Under 1.5 Goals', NULL),
    ('over_2_5','Over','Over/Under 2.5 Goals','Over 2.5 Goals', NULL),
    ('over_2_5','Under','Over/Under 2.5 Goals','Under 2.5 Goals', NULL),
    ('over_3_5','Over','Over/Under 3.5 Goals','Over 3.5 Goals', NULL),
    ('over_3_5','Under','Over/Under 3.5 Goals','Under 3.5 Goals', NULL),
    ('btts','Yes','Both teams to Score?','Yes', NULL),
    ('btts','No','Both teams to Score?','No', NULL),
    ('first_half_over_0_5','Over','First Half Goals 0.5','Over 0.5 Goals', NULL),
    ('first_half_over_0_5','Under','First Half Goals 0.5','Under 0.5 Goals', NULL)
  ),
  joined AS (
    SELECT mp.cmkt, mp.csel, m.back, m.lay
    FROM map mp JOIN m
      ON m.market_name = mp.bf_market
     AND ( (mp.bf_runner IS NOT NULL AND m.selection = mp.bf_runner)
        OR (mp.bf_sort   IS NOT NULL AND m.sort_priority = mp.bf_sort) )
  )
  SELECT coalesce(jsonb_object_agg(cmkt, sel_obj), '{}'::jsonb)
  FROM (
    SELECT cmkt, jsonb_object_agg(csel, jsonb_build_object('back', back, 'lay', lay)) AS sel_obj
    FROM joined GROUP BY cmkt
  ) t;
$$;

REVOKE ALL ON FUNCTION public.get_betfair_full_odds(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_betfair_full_odds(bigint) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.get_betfair_direction_odds(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_betfair_direction_odds(bigint) TO authenticated, service_role;
