-- ============================================================================
-- MOTORE STRATEGIE — RPC backtest_strategy (2026-06-23)  [money-critical]
-- ============================================================================
-- Domanda: "combinando questi filtri, sullo storico, la strategia è profittevole?"
-- Unità = scommessa (fixture×market×selection). P&L UNA volta sola.
--
-- ROI (netto commissione, default 5% Betfair.it):
--   BACK stake 1:  hit → (odds-1)*(1-comm) ;  no → -1               capitale rischiato = 1
--   LAY  (liab.):  no  → 1*(1-comm)         ;  hit → -(odds-1)       capitale rischiato = (odds-1)
--   ROI = Σpnl / Σcapitale_rischiato (return on capital).  Banda CI 95% normale sui
--   ritorni-per-unità r_i = pnl_i/rischio_i  (per BACK r_i=pnl_i, rischio=1).
-- Hit-rate: solo scommesse SETTLATE (90'); intervallo WILSON 95%.
-- Quota: catena Betfair (ufficiale) → bookmaker (raw_json_odds) come fallback.
-- Le scommesse settlate SENZA quota entrano nel hit-rate ma NON nel ROI (n_unpriced).
--
-- Filtri tutti opzionali. SQL dinamico injection-safe (%L per i letterali, whitelist
-- per direzione/fonte/group_by). SECURITY DEFINER + search_path fisso. Solo aggregati.
-- ============================================================================
create or replace function public.backtest_strategy(
    p_date_from    date    default null,
    p_date_to      date    default null,
    p_market       text    default null,
    p_selection    text    default null,
    p_leagues      bigint[] default null,
    p_direction    text    default 'back',          -- 'back' | 'lay'
    p_odds_source  text    default 'betfair_book',   -- 'betfair_book' | 'betfair' | 'book'
    p_commission   numeric default 0.05,
    p_min_odds     numeric default null,
    p_max_odds     numeric default null,
    p_poisson_min  numeric default null,
    p_ml_min       numeric default null,
    p_tacticai_min numeric default null,
    p_api_over     boolean default false,            -- API prediction_under_over '+' e linea >= b.line
    p_n_engines_min int    default null,
    p_min_edge     numeric default null,
    p_delay_eq     int     default null,
    p_delay_min    int     default null,
    p_freq_dir     text    default null,             -- 'below' | 'above' | null
    p_ml_clean     boolean default false,            -- richiede ml_oos_valid AND ml_reliable
    p_status       text    default null,             -- 'PLACED' | 'REJECTED' | 'NO_SIGNAL'
    p_group_by     text    default 'market_league'   -- market_league|market|league|overall|month
)
returns table(
    grp         text,
    n           bigint,
    n_settled   bigint,
    n_hit       bigint,
    hit_rate    numeric,
    wilson_low  numeric,
    wilson_high numeric,
    n_priced    bigint,
    n_unpriced  bigint,
    profit      numeric,
    turnover    numeric,
    roi         numeric,
    roi_low     numeric,
    roi_high    numeric,
    avg_odds    numeric
)
language plpgsql
stable
security definer
set search_path = public
set statement_timeout = '60s'
as $fn$
declare
    v_dir  text := lower(coalesce(p_direction, 'back'));
    v_src  text := lower(coalesce(p_odds_source, 'betfair_book'));
    v_gb   text := lower(coalesce(p_group_by, 'market_league'));
    v_comm numeric := coalesce(p_commission, 0.05);
    v_odds text;
    v_grp  text;
    v_w    text := ' where true ';
    v_sql  text;
begin
    if v_dir not in ('back','lay')                                   then raise exception 'direction non valida: %', v_dir; end if;
    if v_src not in ('betfair_book','betfair','book')                then raise exception 'odds_source non valida: %', v_src; end if;
    if v_gb  not in ('market_league','market','league','overall','month') then raise exception 'group_by non valido: %', v_gb; end if;
    if v_comm < 0 or v_comm >= 1                                     then raise exception 'commission non valida: %', v_comm; end if;

    -- espressione quota secondo la fonte scelta (catena di fallback)
    v_odds := case v_src
        when 'betfair' then 'b.odds_betfair'
        when 'book'    then 'b.odds_book'
        else                'coalesce(b.odds_betfair, b.odds_book)'   -- catena Betfair → bookmaker
    end;

    -- chiave di raggruppamento
    v_grp := case v_gb
        when 'overall' then '''ALL''::text'
        when 'market'  then 'b.market'
        when 'league'  then 'coalesce(b.league_name, b.league_id::text)'
        when 'month'   then 'to_char(b.kickoff, ''YYYY-MM'')'
        else                'b.market || '' · '' || coalesce(b.league_name, b.league_id::text)'
    end;

    -- ---- filtri opzionali (injection-safe) ----
    if p_date_from    is not null then v_w := v_w || format(' and b.kickoff >= %L', p_date_from); end if;
    if p_date_to      is not null then v_w := v_w || format(' and b.kickoff < (%L::date + 1)', p_date_to); end if;
    if p_market       is not null then v_w := v_w || format(' and b.market = %L', p_market); end if;
    if p_selection    is not null then v_w := v_w || format(' and b.selection = %L', p_selection); end if;
    if p_leagues      is not null then v_w := v_w || format(' and b.league_id = any(%L::bigint[])', p_leagues); end if;
    if p_poisson_min  is not null then v_w := v_w || format(' and b.poisson_prob >= %L', p_poisson_min); end if;
    if p_ml_min       is not null then v_w := v_w || format(' and b.ml_prob >= %L', p_ml_min); end if;
    if p_tacticai_min is not null then v_w := v_w || format(' and b.tacticai_prob >= %L', p_tacticai_min); end if;
    if p_n_engines_min is not null then v_w := v_w || format(' and b.n_engines_agree >= %L', p_n_engines_min); end if;
    if p_min_edge     is not null then v_w := v_w || format(' and b.edge >= %L', p_min_edge); end if;
    -- NB filtri su campi nullable (snapshot freq/ritardi): NULL = dato non disponibile
    -- al momento → la scommessa NON soddisfa la condizione (esclusione esplicita).
    if p_delay_eq     is not null then v_w := v_w || format(' and b.delay_current is not null and b.delay_current = %L', p_delay_eq); end if;
    if p_delay_min    is not null then v_w := v_w || format(' and b.delay_current is not null and b.delay_current >= %L', p_delay_min); end if;
    if p_freq_dir = 'below'       then v_w := v_w || ' and b.freq_deviation is not null and b.freq_deviation < 0'; end if;
    if p_freq_dir = 'above'       then v_w := v_w || ' and b.freq_deviation is not null and b.freq_deviation > 0'; end if;
    if p_ml_clean                 then v_w := v_w || ' and b.ml_oos_valid is true and b.ml_reliable is true'; end if;
    if p_status       is not null then v_w := v_w || format(' and b.dec_status = %L', p_status); end if;
    if p_min_odds     is not null then v_w := v_w || format(' and (%s) >= %L', v_odds, p_min_odds); end if;
    if p_max_odds     is not null then v_w := v_w || format(' and (%s) <= %L', v_odds, p_max_odds); end if;
    -- API dice over la linea della scommessa (segnale pre-calcolato nella matview)
    if p_api_over then v_w := v_w || ' and b.api_over_line is not null and b.api_over_line >= b.line'; end if;

    v_sql :=
      'with base as ('
      || ' select b.*, (' || v_odds || ') as odds'
      || ' from analytics_bets b'
      || v_w || '),'
      || ' pnl as (select ' || v_grp || ' as grp, settled, hit, odds,'
      || '   case when settled and odds is not null then'
      || '     case when ' || quote_literal(v_dir) || ' = ''back'''
      || '       then (case when hit then (odds-1)*(1-' || quote_literal(v_comm) || '::numeric) else -1 end)'
      || '       else (case when hit then -(odds-1) else (1-' || quote_literal(v_comm) || '::numeric) end) end'
      || '   end as pnl,'
      || '   case when settled and odds is not null then'
      || '     case when ' || quote_literal(v_dir) || ' = ''back'' then 1 else (odds-1) end'
      || '   end as staked'
      || ' from base b),'
      || ' agg as (select grp,'
      || '   count(*) n,'
      || '   count(*) filter (where settled) n_settled,'
      || '   count(*) filter (where settled and hit) n_hit,'
      || '   (count(*) filter (where settled and hit))::numeric / nullif(count(*) filter (where settled),0) hit_rate,'
      || '   count(*) filter (where settled and odds is not null) n_priced,'
      || '   count(*) filter (where settled and odds is null) n_unpriced,'
      || '   sum(pnl) profit, sum(staked) turnover,'
      || '   sum(pnl)/nullif(sum(staked),0) roi,'
      -- momenti per la CI del ROI col METODO DELTA sullo stimatore-rapporto R=Sum(pnl)/Sum(rischio)
      -- (per BACK rischio=1 -> var_staked=cov=0, avg_staked=1 -> SE=stddev(pnl)/sqrt(n), identico al BACK precedente)
      || '   var_samp(pnl)::numeric vpnl, var_samp(staked)::numeric vstk, covar_samp(pnl,staked)::numeric cps, avg(staked) astk,'
      || '   avg(odds) filter (where settled and odds is not null) avg_odds'
      || ' from pnl group by grp)'
      || ' select grp, n, n_settled, n_hit, round(hit_rate,6) hit_rate,'
      || '   case when n_settled>0 then (hit_rate + 1.9208/n_settled - 1.96*sqrt((hit_rate*(1-hit_rate) + 0.9604/n_settled)/n_settled)) / (1 + 3.8416/n_settled) end,'
      || '   case when n_settled>0 then (hit_rate + 1.9208/n_settled + 1.96*sqrt((hit_rate*(1-hit_rate) + 0.9604/n_settled)/n_settled)) / (1 + 3.8416/n_settled) end,'
      || '   n_priced, n_unpriced, round(profit,4), round(turnover,4), round(roi,6),'
      || '   case when n_priced>1 and astk>0 and vpnl is not null then roi - 1.96*sqrt(greatest((vpnl - 2*roi*cps + roi*roi*vstk)/((n_priced::numeric)*astk*astk),0)) end,'
      || '   case when n_priced>1 and astk>0 and vpnl is not null then roi + 1.96*sqrt(greatest((vpnl - 2*roi*cps + roi*roi*vstk)/((n_priced::numeric)*astk*astk),0)) end,'
      || '   round(avg_odds,4)'
      || ' from agg order by n desc';

    return query execute v_sql;
end;
$fn$;

revoke all on function public.backtest_strategy from public, anon;
grant execute on function public.backtest_strategy to authenticated, service_role;

-- ============================================================================
-- backtest_strategy_rows: stesse selezioni di backtest_strategy, ma ritorna le
-- SINGOLE PARTITE con TUTTI i dati (per certificare a occhio i filtri). Stessa
-- logica di filtro/quota/P&L. Ordinate per kickoff desc. Paginazione limit/offset.
-- ============================================================================
create or replace function public.backtest_strategy_rows(
    p_date_from date default null, p_date_to date default null,
    p_market text default null, p_selection text default null, p_leagues bigint[] default null,
    p_direction text default 'back', p_odds_source text default 'betfair_book', p_commission numeric default 0.05,
    p_min_odds numeric default null, p_max_odds numeric default null,
    p_poisson_min numeric default null, p_ml_min numeric default null, p_tacticai_min numeric default null,
    p_api_over boolean default false, p_n_engines_min int default null, p_min_edge numeric default null,
    p_delay_eq int default null, p_delay_min int default null, p_freq_dir text default null,
    p_ml_clean boolean default false, p_status text default null,
    p_limit int default 200, p_offset int default 0
)
returns table(
    kickoff timestamptz, league_name text, home_team text, away_team text,
    market text, selection text, poisson_prob numeric, ml_prob numeric, tacticai_prob numeric,
    api_over_line numeric, n_engines_agree smallint, delay_current integer, freq_deviation numeric,
    odds numeric, odds_src text, edge numeric, status text,
    settled boolean, hit boolean, total_goals smallint, goals_home smallint, goals_away smallint,
    first_goal_minute smallint, pnl numeric
)
language plpgsql stable security definer set search_path = public set statement_timeout = '60s'
as $fn$
declare
    v_dir text := lower(coalesce(p_direction,'back'));
    v_src text := lower(coalesce(p_odds_source,'betfair_book'));
    v_comm numeric := coalesce(p_commission,0.05);
    v_odds text; v_w text := ' where true '; v_sql text;
begin
    if v_dir not in ('back','lay') then raise exception 'direction non valida'; end if;
    if v_src not in ('betfair_book','betfair','book') then raise exception 'odds_source non valida'; end if;
    if v_comm < 0 or v_comm >= 1 then raise exception 'commission non valida'; end if;
    v_odds := case v_src when 'betfair' then 'b.odds_betfair' when 'book' then 'b.odds_book'
                         else 'coalesce(b.odds_betfair, b.odds_book)' end;
    if p_date_from is not null then v_w := v_w || format(' and b.kickoff >= %L', p_date_from); end if;
    if p_date_to   is not null then v_w := v_w || format(' and b.kickoff < (%L::date + 1)', p_date_to); end if;
    if p_market    is not null then v_w := v_w || format(' and b.market = %L', p_market); end if;
    if p_selection is not null then v_w := v_w || format(' and b.selection = %L', p_selection); end if;
    if p_leagues   is not null then v_w := v_w || format(' and b.league_id = any(%L::bigint[])', p_leagues); end if;
    if p_poisson_min  is not null then v_w := v_w || format(' and b.poisson_prob >= %L', p_poisson_min); end if;
    if p_ml_min       is not null then v_w := v_w || format(' and b.ml_prob >= %L', p_ml_min); end if;
    if p_tacticai_min is not null then v_w := v_w || format(' and b.tacticai_prob >= %L', p_tacticai_min); end if;
    if p_n_engines_min is not null then v_w := v_w || format(' and b.n_engines_agree >= %L', p_n_engines_min); end if;
    if p_min_edge  is not null then v_w := v_w || format(' and b.edge >= %L', p_min_edge); end if;
    if p_delay_eq  is not null then v_w := v_w || format(' and b.delay_current is not null and b.delay_current = %L', p_delay_eq); end if;
    if p_delay_min is not null then v_w := v_w || format(' and b.delay_current is not null and b.delay_current >= %L', p_delay_min); end if;
    if p_freq_dir = 'below'    then v_w := v_w || ' and b.freq_deviation is not null and b.freq_deviation < 0'; end if;
    if p_freq_dir = 'above'    then v_w := v_w || ' and b.freq_deviation is not null and b.freq_deviation > 0'; end if;
    if p_ml_clean              then v_w := v_w || ' and b.ml_oos_valid is true and b.ml_reliable is true'; end if;
    if p_status    is not null then v_w := v_w || format(' and b.dec_status = %L', p_status); end if;
    if p_min_odds  is not null then v_w := v_w || format(' and (%s) >= %L', v_odds, p_min_odds); end if;
    if p_max_odds  is not null then v_w := v_w || format(' and (%s) <= %L', v_odds, p_max_odds); end if;
    if p_api_over then v_w := v_w || ' and b.api_over_line is not null and b.api_over_line >= b.line'; end if;

    v_sql :=
      'select b.kickoff, b.league_name, b.home_team, b.away_team, b.market, b.selection,'
      || ' b.poisson_prob, b.ml_prob, b.tacticai_prob, b.api_over_line, b.n_engines_agree,'
      || ' b.delay_current, b.freq_deviation,'
      || ' (' || v_odds || ') as odds,'
      || ' case when b.odds_betfair is not null then ''betfair'' when b.odds_book is not null then ''book'' end as odds_src,'
      || ' b.edge, b.dec_status,'
      || ' b.settled, b.hit, b.total_goals, b.goals_home, b.goals_away, b.first_goal_minute,'
      || ' case when b.settled and (' || v_odds || ') is not null then'
      || '   case when ' || quote_literal(v_dir) || ' = ''back'''
      || '     then (case when b.hit then ((' || v_odds || ')-1)*(1-' || quote_literal(v_comm) || '::numeric) else -1 end)'
      || '     else (case when b.hit then -((' || v_odds || ')-1) else (1-' || quote_literal(v_comm) || '::numeric) end) end'
      || ' end as pnl'
      || ' from analytics_bets b'
      || v_w
      || ' order by b.kickoff desc nulls last'
      || format(' limit %s offset %s', greatest(coalesce(p_limit,200),1), greatest(coalesce(p_offset,0),0));
    return query execute v_sql;
end;
$fn$;

revoke all on function public.backtest_strategy_rows from public, anon;
grant execute on function public.backtest_strategy_rows to authenticated, service_role;
