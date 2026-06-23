-- ============================================================================
-- PATTERN DISCOVERY — feature pre-match per scommessa + RPC di analisi (2026-06-23)
-- ============================================================================
-- Obiettivo: dato un mercato, scoprire QUALI caratteristiche della partita
-- (gol attesi, forma, lega, ritardo/frequenza, ecc.) discriminano le scommesse
-- VINCENTI, per riconoscere partite simili in futuro. Read-only, per analisi.
-- ============================================================================
set statement_timeout = 0;

create or replace view public.bet_features as
select
    b.fixture_id, b.kickoff, b.league_id, b.league_name, b.season_year,
    b.home_team, b.away_team, b.market, b.selection,
    b.poisson_prob, b.ml_prob, b.tacticai_prob, b.n_engines_agree,
    b.freq_deviation, b.delay_current, b.api_over_line,
    coalesce(b.odds_betfair, b.odds_book) as odds,
    b.odds_betfair, b.odds_book,
    b.settled, b.hit, b.total_goals, b.ht_home, b.ht_away, b.first_goal_minute,
    -- ---- Poisson inputs ----
    (fp.db_json_analisi->'inputs'->>'lambda_home')::numeric   as lambda_home,
    (fp.db_json_analisi->'inputs'->>'lambda_away')::numeric   as lambda_away,
    ((fp.db_json_analisi->'inputs'->>'lambda_home')::numeric
     + (fp.db_json_analisi->'inputs'->>'lambda_away')::numeric) as lambda_tot,
    (fp.db_json_analisi->'inputs'->>'lambda_1h_tot')::numeric as lambda_1h_tot,
    (fp.db_json_analisi->'inputs'->>'dc_rho')::numeric        as dc_rho,
    (fp.db_json_analisi->'inputs'->>'ht_ratio_home')::numeric as ht_ratio_home,
    (fp.db_json_analisi->'inputs'->>'ht_ratio_away')::numeric as ht_ratio_away,
    (fp.db_json_analisi->'inputs'->>'league_total_avg')::numeric as league_total_avg,
    -- ---- API flat_summary (forma/medie/confronti) ----
    (fp.flat_summary->>'percent_home')::numeric  as api_home,
    (fp.flat_summary->>'percent_draw')::numeric  as api_draw,
    (fp.flat_summary->>'percent_away')::numeric  as api_away,
    nullif(regexp_replace(fp.flat_summary->>'home_last5_form','[^0-9.]','','g'),'')::numeric as home_form,
    nullif(regexp_replace(fp.flat_summary->>'away_last5_form','[^0-9.]','','g'),'')::numeric as away_form,
    nullif(regexp_replace(fp.flat_summary->>'home_last5_goals_for_avg','[^0-9.]','','g'),'')::numeric     as home_gf,
    nullif(regexp_replace(fp.flat_summary->>'away_last5_goals_for_avg','[^0-9.]','','g'),'')::numeric     as away_gf,
    nullif(regexp_replace(fp.flat_summary->>'home_last5_goals_against_avg','[^0-9.]','','g'),'')::numeric as home_ga,
    nullif(regexp_replace(fp.flat_summary->>'away_last5_goals_against_avg','[^0-9.]','','g'),'')::numeric as away_ga,
    nullif(regexp_replace(fp.flat_summary->>'comparison_total_home','[^0-9.]','','g'),'')::numeric as comp_total_home
from public.analytics_bets b
left join public.fixture_predictions fp on fp.fixture_id = b.fixture_id;

revoke all on public.bet_features from anon, authenticated;

-- whitelist feature → espressione (per injection-safety nelle RPC)
create or replace function public._feat_expr(p_feature text)
returns text language sql immutable as $$
  select case p_feature
    when 'lambda_home' then 'lambda_home' when 'lambda_away' then 'lambda_away'
    when 'lambda_tot' then 'lambda_tot' when 'lambda_1h_tot' then 'lambda_1h_tot'
    when 'dc_rho' then 'dc_rho' when 'ht_ratio_home' then 'ht_ratio_home' when 'ht_ratio_away' then 'ht_ratio_away'
    when 'league_total_avg' then 'league_total_avg'
    when 'api_home' then 'api_home' when 'api_draw' then 'api_draw' when 'api_away' then 'api_away'
    when 'home_form' then 'home_form' when 'away_form' then 'away_form'
    when 'home_gf' then 'home_gf' when 'away_gf' then 'away_gf'
    when 'home_ga' then 'home_ga' when 'away_ga' then 'away_ga'
    when 'comp_total_home' then 'comp_total_home'
    when 'poisson_prob' then 'poisson_prob' when 'ml_prob' then 'ml_prob'
    when 'n_engines_agree' then 'n_engines_agree' when 'freq_deviation' then 'freq_deviation'
    when 'delay_current' then 'delay_current' when 'odds' then 'odds'
  end;
$$;

-- ---- analyze_feature: hit-rate / quota / EV per FASCIA (ntile) di una feature ----
--   EV_back = hit*(avg_odds-1)*(1-comm) - (1-hit) ; EV_lay (a quota back, stima ottimistica).
create or replace function public.analyze_feature(
    p_market text, p_selection text, p_feature text,
    p_bins int default 10, p_comm numeric default 0.05
)
returns table(bin int, lo numeric, hi numeric, n bigint, n_priced bigint,
              hit_rate numeric, avg_odds numeric, ev_back numeric, ev_lay numeric)
language plpgsql stable security definer set search_path = public set statement_timeout = '60s'
as $fn$
declare v_col text := public._feat_expr(p_feature); v_sql text;
begin
    if v_col is null then raise exception 'feature non valida: %', p_feature; end if;
    v_sql := format($q$
        with f as (
            select %s::numeric as x, hit, settled, odds
            from public.bet_features
            where market = %L and selection = %L and settled = true and %s is not null
        ),
        b as (select x, hit, odds, ntile(%s) over (order by x) as bin from f)
        select bin::int, min(x), max(x), count(*)::bigint,
               count(*) filter (where odds is not null)::bigint,
               avg(hit::int)::numeric,
               avg(odds) filter (where odds is not null),
               avg(hit::int)*(avg(odds) filter (where odds is not null)-1)*(1-%s) - (1-avg(hit::int)),
               (1-avg(hit::int))*(1-%s) - avg(hit::int)*(avg(odds) filter (where odds is not null)-1)
        from b group by bin order by bin
    $q$, v_col, p_market, p_selection, v_col, p_bins, p_comm, p_comm);
    return query execute v_sql;
end;
$fn$;

-- ---- analyze_by_league: hit-rate / quota / EV per LEGA (per un mercato/selezione) ----
create or replace function public.analyze_by_league(
    p_market text, p_selection text, p_min_n int default 30, p_comm numeric default 0.05
)
returns table(league_id bigint, league_name text, n bigint, n_priced bigint,
              hit_rate numeric, avg_odds numeric, ev_back numeric)
language sql stable security definer set search_path = public set statement_timeout = '60s'
as $$
    select league_id, max(league_name), count(*)::bigint,
           count(*) filter (where odds is not null)::bigint,
           avg(hit::int)::numeric,
           avg(odds) filter (where odds is not null),
           avg(hit::int)*(avg(odds) filter (where odds is not null)-1)*(1-p_comm) - (1-avg(hit::int))
    from public.bet_features
    where market = p_market and selection = p_selection and settled = true
    group by league_id
    having count(*) >= p_min_n
    order by 7 desc nulls last;
$$;

revoke all on function public.analyze_feature(text,text,text,int,numeric) from public, anon;
revoke all on function public.analyze_by_league(text,text,int,numeric) from public, anon;
grant execute on function public.analyze_feature(text,text,text,int,numeric) to authenticated, service_role;
grant execute on function public.analyze_by_league(text,text,int,numeric) to authenticated, service_role;
