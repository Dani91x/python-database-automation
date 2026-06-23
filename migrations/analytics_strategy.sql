-- ============================================================================
-- MOTORE STRATEGIE — fondazione (2026-06-23, v2 TABELLE INCREMENTALI)
-- ============================================================================
-- Money-critical. Unità di analisi = LA SCOMMESSA: (fixture_id, market, selection).
-- I motori (poisson/ml/tacticai/api), snapshot freq/ritardi e quote sono COLONNE
-- di quella scommessa; il P&L si calcola UNA volta sola → nessun doppio conteggio.
--
-- PERFORMANCE / SCALA (fix definitivo): analytics_bets e book_odds_cache sono
-- TABELLE REALI INDICIZZATE, non viste. Il lavoro pesante (pivot + estrazione quote
-- bookmaker set-based + segnale API) si fa al POPOLAMENTO, per INTERVALLO DI DATE
-- (incrementale). Le query del backtest leggono la tabella indicizzata → veloci e
-- scalano quando i dati crescono (l'action notturna aggiorna solo i giorni nuovi).
--
-- SNAPSHOT freq/ritardi e prob dei motori sono PRE-MATCH (leak-free). hit/result/
-- goals/first_goal_minute sono ESITO (non filtri pre-bet).  Idempotente.
-- ============================================================================
set statement_timeout = 0;

-- ----------------------------------------------------------------------------
-- A) book_odds(raw_json_odds, market, selection): quota bookmaker per una coppia
--    canonica (uso ad-hoc / riferimento). Il popolamento usa la versione set-based.
-- ----------------------------------------------------------------------------
create or replace function public.book_odds(p_raw jsonb, p_market text, p_selection text)
returns numeric
language sql
immutable
as $$
  with m as (
    select
      case
        when p_market = '1x2'                  then 'Match Winner'
        when p_market = 'ht_1x2'               then 'First Half Winner'
        when p_market = 'btts'                 then 'Both Teams Score'
        when p_market like 'first_half_over_%' then 'Goals Over/Under First Half'
        when p_market like 'over_%'            then 'Goals Over/Under'
      end as bet_name,
      case
        when p_market in ('1x2','ht_1x2') then
          case p_selection when 'H' then 'Home' when 'D' then 'Draw' when 'A' then 'Away' end
        when p_market = 'btts' then p_selection
        when p_market like 'first_half_over_%' then
          p_selection || ' ' || replace(substring(p_market from 'first_half_over_(.*)'), '_', '.')
        when p_market like 'over_%' then
          p_selection || ' ' || replace(substring(p_market from 'over_(.*)'), '_', '.')
      end as val
  )
  select min((v->>'odd')::numeric)
  from m,
       lateral jsonb_array_elements(coalesce(p_raw->'bookmakers','[]'::jsonb)) bk,
       lateral jsonb_array_elements(coalesce(bk->'bets','[]'::jsonb)) bet,
       lateral jsonb_array_elements(coalesce(bet->'values','[]'::jsonb)) v
  where m.bet_name is not null and m.val is not null
    and bet->>'name' = m.bet_name and v->>'value' = m.val
    and (v->>'odd') ~ '^[0-9]+(\.[0-9]+)?$';
$$;
revoke all on function public.book_odds(jsonb, text, text) from public, anon, authenticated;
grant execute on function public.book_odds(jsonb, text, text) to service_role;

-- ----------------------------------------------------------------------------
-- B) TABELLE: book_odds_cache (quota bookmaker canonica) + analytics_bets (scommesse).
--    Drop dell'eventuale vista/matview precedente.
-- ----------------------------------------------------------------------------
-- drop type-safe: rimuove eventuali vista/matview preesistenti (NON tocca le tabelle)
do $$
declare k char;
begin
    select relkind into k from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname='analytics_bets';
    if k='v' then execute 'drop view public.analytics_bets cascade';
    elsif k='m' then execute 'drop materialized view public.analytics_bets cascade'; end if;
    select relkind into k from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname='book_odds_cache';
    if k='v' then execute 'drop view public.book_odds_cache cascade';
    elsif k='m' then execute 'drop materialized view public.book_odds_cache cascade'; end if;
end $$;

create table if not exists public.book_odds_cache (
    fixture_id  bigint  not null,
    market      text    not null,
    selection   text    not null,
    odd         numeric,
    primary key (fixture_id, market, selection)
);

create table if not exists public.analytics_bets (
    fixture_id      bigint  not null,
    league_id       bigint,
    league_name     text,
    season_year     smallint,
    home_team       text,
    away_team       text,
    kickoff         timestamptz,
    market          text    not null,
    selection       text    not null,
    line            numeric,
    poisson_prob    numeric,
    ml_prob         numeric,
    tacticai_prob   numeric,
    ml_oos_valid    boolean,
    ml_reliable     boolean,
    n_engines_present integer,
    n_engines_agree smallint,
    consensus_prob  numeric,
    freq_baseline   numeric,
    freq_current    numeric,
    freq_deviation  numeric,
    delay_current   integer,
    delay_record    integer,
    delay_avg       numeric,
    settled         boolean,
    hit             boolean,
    total_goals     smallint,
    goals_home      smallint,
    goals_away      smallint,
    ht_home         smallint,
    ht_away         smallint,
    first_goal_minute smallint,
    odds_betfair    numeric,
    placed          boolean,
    dec_status      text,
    edge            numeric,
    score           numeric,
    implied_prob    numeric,
    is_best         boolean,
    reject_filter   text,
    odds_book       numeric,
    api_over_line   numeric,
    primary key (fixture_id, market, selection)
);

create index if not exists analytics_bets_mkt_sel on public.analytics_bets (market, selection);
create index if not exists analytics_bets_kickoff on public.analytics_bets (kickoff);
create index if not exists analytics_bets_league  on public.analytics_bets (league_id);
create index if not exists analytics_bets_settled on public.analytics_bets (settled) where settled;

revoke all on public.book_odds_cache from anon, authenticated;
revoke all on public.analytics_bets  from anon, authenticated;

-- ----------------------------------------------------------------------------
-- C) refresh_analytics_bets_range(from,to): ripopola cache+bets per l'intervallo
--    [from, to) sui kickoff/fixture_date. Idempotente (delete+insert). Usato sia
--    per il popolamento iniziale (un mese per chiamata) sia dall'incrementale
--    notturno (ultimi N giorni). Ritorna il numero di scommesse scritte.
-- ----------------------------------------------------------------------------
create or replace function public.refresh_analytics_bets_range(p_from date, p_to date)
returns integer
language plpgsql
security definer
set search_path = public
set statement_timeout = 0
as $fn$
declare v_n integer;
begin
    -- 1) book_odds_cache (set-based) per i fixtures dell'intervallo — FILTRO PER DATA
    --    (indice su fixture_predictions.fixture_date): niente array → scala.
    delete from public.book_odds_cache c
    using public.fixture_predictions fp
    where c.fixture_id = fp.fixture_id and fp.fixture_date >= p_from and fp.fixture_date < p_to;

    insert into public.book_odds_cache (fixture_id, market, selection, odd)
    select fp.fixture_id, mm.market, mm.selection, min((v->>'odd')::numeric)
    -- PRE-FILTRO per data PRIMA dell'unnest JSON (usa l'indice su fixture_date) → scala col range
    from (select fixture_id, raw_json_odds from public.fixture_predictions
          where fixture_date >= p_from and fixture_date < p_to and raw_json_odds is not null) fp
        cross join lateral jsonb_array_elements(coalesce(fp.raw_json_odds->'bookmakers','[]'::jsonb)) bk
        cross join lateral jsonb_array_elements(coalesce(bk->'bets','[]'::jsonb)) bet
        cross join lateral jsonb_array_elements(coalesce(bet->'values','[]'::jsonb)) v
        cross join lateral (
            select
                case bet->>'name'
                    when 'Match Winner'                then '1x2'
                    when 'First Half Winner'           then 'ht_1x2'
                    when 'Both Teams Score'            then 'btts'
                    when 'Goals Over/Under'            then 'over_' || replace(regexp_replace(v->>'value','^(Over|Under) ',''),'.','_')
                    when 'Goals Over/Under First Half' then 'first_half_over_' || replace(regexp_replace(v->>'value','^(Over|Under) ',''),'.','_')
                end as market,
                case bet->>'name'
                    when 'Match Winner'      then case v->>'value' when 'Home' then 'H' when 'Draw' then 'D' when 'Away' then 'A' end
                    when 'First Half Winner' then case v->>'value' when 'Home' then 'H' when 'Draw' then 'D' when 'Away' then 'A' end
                    when 'Both Teams Score'  then v->>'value'
                    else split_part(v->>'value',' ',1)
                end as selection
        ) mm
    where mm.market is not null and mm.selection is not null
      and (v->>'odd') ~ '^[0-9]+(\.[0-9]+)?$'
    group by fp.fixture_id, mm.market, mm.selection;

    -- 2) analytics_bets — insieme = i FIXTURE con almeno un segnale nel range (per kickoff,
    --    indicizzato). delete/dec/pivot usano lo STESSO insieme e aggregano TUTTI i segnali
    --    del fixture → idempotente e robusto a kickoff incoerenti tra righe-motore (no PK dup).
    delete from public.analytics_bets
    where fixture_id in (select distinct fixture_id from public.analytics_signals
                         where kickoff >= p_from and kickoff < p_to);
    insert into public.analytics_bets
    with dec as (
        select d.fixture_id, d.market, d.selection,
            coalesce(
                max(d.odds) filter (where d.status = 'PLACED' and d.odds is not null),
                avg(d.odds) filter (where d.odds is not null)
            ) as odds_betfair,
            bool_or(d.status = 'PLACED') as placed,
            case when bool_or(d.status='PLACED') then 'PLACED'
                 when bool_or(d.status='REJECTED') then 'REJECTED'
                 when bool_or(d.status='NO_SIGNAL') then 'NO_SIGNAL' else null end as dec_status,
            max(d.edge) as edge, max(d.score) as score, max(d.implied_prob) as implied_prob,
            bool_or(coalesce(d.is_best,false)) as is_best,
            (array_remove(array_agg(d.reject_filter) filter (where d.reject_filter is not null), null))[1] as reject_filter
        from public.analytics_decisions d
        where d.fixture_id in (select distinct fixture_id from public.analytics_signals
                               where kickoff >= p_from and kickoff < p_to)
        group by d.fixture_id, d.market, d.selection
    ),
    piv as (
        -- 1 riga per scommessa: GROUP BY solo (fixture, market, selection); le colonne
        -- descrittive via max() (evita split se differiscono tra righe-motore → no duplicati PK)
        select
            s.fixture_id,
            max(s.league_id) as league_id, max(s.league_name) as league_name,
            max(s.season_year) as season_year, max(s.home_team) as home_team,
            max(s.away_team) as away_team, max(s.kickoff) as kickoff,
            s.market, s.selection,
            max(s.line) as line,
            max(s.prob) filter (where s.engine='poisson') as poisson_prob,
            max(s.prob) filter (where s.engine='ml') as ml_prob,
            max(s.prob) filter (where s.engine='tacticai') as tacticai_prob,
            bool_and(s.oos_valid) filter (where s.engine='ml') as ml_oos_valid,
            bool_or(s.reliable) filter (where s.engine='ml') as ml_reliable,
            count(distinct s.engine)::int as n_engines_present,
            max(s.n_engines_agree) as n_engines_agree,
            max(s.consensus_prob) as consensus_prob,
            max(s.freq_baseline) as freq_baseline, max(s.freq_current) as freq_current,
            max(s.freq_deviation) as freq_deviation, max(s.delay_current) as delay_current,
            max(s.delay_record) as delay_record, max(s.delay_avg) as delay_avg,
            bool_or(s.settled) as settled, bool_or(s.hit) as hit,
            max(s.total_goals) as total_goals, max(s.goals_home) as goals_home,
            max(s.goals_away) as goals_away, max(s.ht_home) as ht_home, max(s.ht_away) as ht_away,
            max(s.first_goal_minute) as first_goal_minute
        from public.analytics_signals s
        where s.fixture_id in (select distinct fixture_id from public.analytics_signals
                               where kickoff >= p_from and kickoff < p_to)
        group by s.fixture_id, s.market, s.selection
    )
    select
        piv.fixture_id, piv.league_id, piv.league_name, piv.season_year,
        piv.home_team, piv.away_team, piv.kickoff, piv.market, piv.selection, piv.line,
        piv.poisson_prob, piv.ml_prob, piv.tacticai_prob, piv.ml_oos_valid, piv.ml_reliable,
        piv.n_engines_present, piv.n_engines_agree, piv.consensus_prob,
        piv.freq_baseline, piv.freq_current, piv.freq_deviation,
        piv.delay_current, piv.delay_record, piv.delay_avg,
        piv.settled, piv.hit, piv.total_goals, piv.goals_home, piv.goals_away,
        piv.ht_home, piv.ht_away, piv.first_goal_minute,
        d.odds_betfair, coalesce(d.placed,false), d.dec_status, d.edge, d.score,
        d.implied_prob, d.is_best, d.reject_filter,
        boc.odd as odds_book,
        case when (fp.flat_summary->>'prediction_under_over') ~ '^\+'
             then nullif(regexp_replace(fp.flat_summary->>'prediction_under_over','[^0-9.]','','g'),'')::numeric end as api_over_line
    from piv
    left join dec d on d.fixture_id=piv.fixture_id and d.market=piv.market and d.selection=piv.selection
    left join public.book_odds_cache boc on boc.fixture_id=piv.fixture_id and boc.market=piv.market and boc.selection=piv.selection
    left join public.fixture_predictions fp on fp.fixture_id=piv.fixture_id;

    get diagnostics v_n = row_count;
    return v_n;
end;
$fn$;

-- wrapper incrementale per l'action notturna (ultimi N giorni, default 4)
create or replace function public.refresh_analytics_bets(p_days integer default 4)
returns integer
language sql
security definer
set search_path = public
set statement_timeout = 0
as $$
    select public.refresh_analytics_bets_range(
        (now() at time zone 'utc')::date - p_days,
        (now() at time zone 'utc')::date + 2
    );
$$;

revoke all on function public.refresh_analytics_bets_range(date, date) from public, anon;
revoke all on function public.refresh_analytics_bets(integer)         from public, anon;
grant execute on function public.refresh_analytics_bets_range(date, date) to authenticated, service_role;
grant execute on function public.refresh_analytics_bets(integer)         to authenticated, service_role;
