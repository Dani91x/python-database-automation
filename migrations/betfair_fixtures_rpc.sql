-- betfair_fixtures_rpc.sql
-- Espone al cruscotto le PARTITE BETFAIR del giorno e le loro QUOTE, leggendo la
-- tabella engine_signals (riempita dal report Betfair via aggiorna_report.bat).
-- engine_signals non e' leggibile dal frontend (no grant) -> due RPC SECURITY DEFINER.
-- Il match Betfair<->fixture e' GIA' fatto a monte (_find_match nel report): fixture_id
-- in engine_signals e' gia' la nostra fixture. Niente backfill, niente nuovo matching.

-- 1) LISTA: le fixture Betfair di una data, nella STESSA forma della query della dashboard
--    (così MatchesList le renderizza identiche, solo filtrate).
CREATE OR REPLACE FUNCTION public.get_betfair_fixtures(p_date date)
RETURNS TABLE (
    fixture_id     bigint,
    fixture_date   timestamptz,
    home_team_name text,
    away_team_name text,
    home_team_id   integer,
    away_team_id   integer,
    league_name    text,
    league_id      integer,
    status         text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT fp.fixture_id, fp.fixture_date, fp.home_team_name, fp.away_team_name,
           fp.home_team_id, fp.away_team_id, fp.league_name, fp.league_id, fp.status
    FROM public.fixture_predictions fp
    WHERE fp.status = 'ok'                          -- stessa condizione della lista normale
      AND fp.fixture_id IN (
        SELECT DISTINCT es.fixture_id
        FROM public.engine_signals es
        WHERE es.run_date = p_date
    )
    ORDER BY fp.fixture_date;
$$;

-- 2) QUOTE: tutte le quote Betfair disponibili per una fixture, mappate dai codici
--    engine_signals (H/D/A/O25/...) sui 7 mercati canonici del cruscotto.
--    Output: { "1x2": {"H":1.2,"D":..,"A":..}, "over_2_5": {"Over":..,"Under":..}, ... }
CREATE OR REPLACE FUNCTION public.get_betfair_odds(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    WITH o AS (   -- una quota per codice mercato (la stessa su tutte le righe del fixture)
        SELECT market, max(odds) AS odd
        FROM public.engine_signals
        WHERE fixture_id = p_fixture_id AND odds IS NOT NULL
        GROUP BY market
    ),
    map(code, market, selection) AS (VALUES
        ('H','1x2','H'),('D','1x2','D'),('A','1x2','A'),
        ('HT_H','ht_1x2','H'),('HT_D','ht_1x2','D'),('HT_A','ht_1x2','A'),
        ('O15','over_1_5','Over'),('U15','over_1_5','Under'),
        ('O25','over_2_5','Over'),('U25','over_2_5','Under'),
        ('O35','over_3_5','Over'),('U35','over_3_5','Under'),
        ('BTTS','btts','Yes'),('BTTS_NO','btts','No'),
        ('HT05','first_half_over_0_5','Over'),('HT_U05','first_half_over_0_5','Under')
    ),
    joined AS (
        SELECT m.market, m.selection, o.odd
        FROM map m JOIN o ON o.market = m.code
    )
    SELECT coalesce(jsonb_object_agg(market, sel_obj), '{}'::jsonb)
    FROM (
        SELECT market, jsonb_object_agg(selection, odd) AS sel_obj
        FROM joined GROUP BY market
    ) t;
$$;

REVOKE ALL ON FUNCTION public.get_betfair_fixtures(date) FROM public;
GRANT EXECUTE ON FUNCTION public.get_betfair_fixtures(date) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.get_betfair_odds(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_betfair_odds(bigint) TO authenticated, service_role;
