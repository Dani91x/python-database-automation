-- ============================================================================
-- RPC ANALYTICS — lettura aggregata (2026-06-22, v2: + API pescato)
-- ============================================================================
-- get_analytics: pagella aggregata (hit-rate + Wilson 95%) con filtri e
-- raggruppamento, su DUE fonti unite a sola lettura:
--   • analytics_signals  → motori 'poisson'/'ml'/'tacticai' (settlement 90')
--   • fixture_predictions → motore 'api' PESCATO (1x2 da percent_*, esito
--     result_outcome a TEMPO PIENO — scelta utente, NON migrato, NON duplicato:
--     l'API non è mai scritto in analytics_signals → zero doppi conteggi).
--
-- CORRETTEZZA STATISTICA (soldi in gioco): hit_rate=hits/n ; intervallo di WILSON
-- 95% (z=1.96, sempre in [0,1]); avg_prob per la calibrazione; solo righe con
-- esito noto (hit non-null) e prob non-null.
--
-- SICUREZZA (repo pubblica): SECURITY DEFINER (nessuna delle due tabelle è
-- esposta ad anon), STABLE, search_path fisso, input whitelist, solo aggregati.
-- ============================================================================

-- COVERING INDEX per il pull API: chiave (league_id, season_year) + INCLUDE di
-- tutte le colonne lette dall'aggregazione → Index-Only Scan (zero heap-fetch),
-- veloce sia filtrato per lega sia in broad. Parziale (solo righe valutate).
-- NB: richiede VACUUM per una visibility-map fresca (vedi tuning autovacuum sotto).
create index if not exists idx_fp_api_full
    on fixture_predictions (league_id, season_year)
    include (league_name, percent_home, percent_draw, percent_away, result_outcome, fixture_date)
    where result_outcome is not null;

create or replace function public.get_analytics(
    p_engine        text    default null,
    p_market        text    default null,
    p_selection     text    default null,
    p_league_id     integer default null,
    p_season_year   integer default null,
    p_prob_min      numeric default null,
    p_prob_max      numeric default null,
    p_min_agree     integer default null,
    p_placed_only   boolean default false,
    p_date_from     timestamptz default null,
    p_date_to       timestamptz default null,
    p_group_by      text    default 'overall'
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_z      constant numeric := 1.96;
    v_rows   jsonb;
    v_group  text := p_group_by;
    v_grp    text;          -- espressione SQL del raggruppamento (su alias b)
    f_as     text := '';    -- filtri PUSHED-DOWN sullo scan analytics_signals (alias s)
    f_api    text := '';    -- filtri PUSHED-DOWN sullo scan API (alias fp / v)
    inc_as   boolean;       -- includere analytics_signals?
    inc_api  boolean;       -- includere l'API (fixture_predictions)?
    v_base   text;
    v_sql    text;
begin
    -- validazione (whitelist → errore rumoroso, mai output silenzioso sbagliato)
    if p_engine is not null and p_engine not in ('poisson','ml','api','tacticai') then
        raise exception 'p_engine invalido: %', p_engine; end if;
    if p_group_by not in ('overall','engine','market','selection','league','confidence') then
        raise exception 'p_group_by invalido: %', p_group_by; end if;
    if p_prob_min is not null and (p_prob_min < 0 or p_prob_min > 1) then
        raise exception 'p_prob_min fuori [0,1]: %', p_prob_min; end if;
    if p_prob_max is not null and (p_prob_max < 0 or p_prob_max > 1) then
        raise exception 'p_prob_max fuori [0,1]: %', p_prob_max; end if;

    -- espressione di raggruppamento (su alias b della UNION)
    v_grp := case v_group
        when 'engine'     then 'b.engine'
        when 'market'     then 'b.market'
        when 'selection'  then 'b.market || '' / '' || b.selection'
        when 'league'     then 'coalesce(b.league_name, b.league_id::text)'
        when 'confidence' then
            '(least(floor(b.prob*20),19)*5)::int::text || ''-'' || (least(floor(b.prob*20),19)*5+5)::int::text || ''%'''
        else '''overall'''
    end;

    -- quali fonti includere (rispetta i filtri che escludono interamente una fonte)
    inc_as  := (p_engine is null or p_engine <> 'api');
    inc_api := (p_engine is null or p_engine = 'api')
               and (p_market is null or p_market = '1x2')   -- l'API copre solo 1x2
               and (p_placed_only is false)                 -- l'API non ha "piazzato"
               and (p_min_agree is null);                   -- l'API non ha concordanza

    -- FILTRI PUSHED-DOWN: solo quelli attivi → il planner usa gli indici.
    -- text via %L (quoting injection-safe); interi/numerici via %s (var tipate).
    if p_engine is not null and p_engine <> 'api' then
        f_as := f_as || format(' and s.engine = %L', p_engine); end if;
    if p_market is not null then
        f_as := f_as || format(' and s.market = %L', p_market); end if;
    if p_selection is not null then
        f_as  := f_as  || format(' and s.selection = %L', p_selection);
        f_api := f_api || format(' and v.sel = %L', p_selection); end if;
    if p_league_id is not null then
        f_as  := f_as  || format(' and s.league_id = %s', p_league_id);
        f_api := f_api || format(' and fp.league_id = %s', p_league_id); end if;
    if p_season_year is not null then
        f_as  := f_as  || format(' and s.season_year = %s', p_season_year);
        f_api := f_api || format(' and fp.season_year = %s', p_season_year); end if;
    if p_prob_min is not null then
        f_as  := f_as  || format(' and s.prob >= %s', p_prob_min);
        f_api := f_api || format(' and (v.pct/100.0) >= %s', p_prob_min); end if;
    if p_prob_max is not null then
        f_as  := f_as  || format(' and s.prob <= %s', p_prob_max);
        f_api := f_api || format(' and (v.pct/100.0) <= %s', p_prob_max); end if;
    if p_min_agree is not null then
        f_as := f_as || format(' and s.n_engines_agree >= %s', p_min_agree); end if;
    if p_placed_only then
        f_as := f_as || ' and s.placed = true'; end if;
    if p_date_from is not null then
        f_as  := f_as  || format(' and s.kickoff >= %L', p_date_from);
        f_api := f_api || format(' and fp.fixture_date >= %L', p_date_from); end if;
    if p_date_to is not null then
        f_as  := f_as  || format(' and s.kickoff <= %L', p_date_to);
        f_api := f_api || format(' and fp.fixture_date <= %L', p_date_to); end if;

    -- costruzione della UNION (solo le fonti incluse)
    v_base := '';
    if inc_as then
        v_base := 'select s.engine, s.league_id, s.league_name, s.season_year, s.kickoff,'
               || ' s.market, s.selection, s.prob, s.hit from analytics_signals s'
               || ' where s.settled and s.hit is not null and s.prob is not null' || f_as;
    end if;
    if inc_api then
        if v_base <> '' then v_base := v_base || ' union all '; end if;
        v_base := v_base
               || 'select ''api''::text, fp.league_id, fp.league_name, fp.season_year::smallint,'
               || ' fp.fixture_date, ''1x2''::text, v.sel, (v.pct/100.0)::numeric, (fp.result_outcome = v.sel)'
               || ' from fixture_predictions fp cross join lateral (values'
               || ' (''H'',fp.percent_home),(''D'',fp.percent_draw),(''A'',fp.percent_away)) v(sel,pct)'
               || ' where fp.result_outcome is not null and v.pct is not null' || f_api;
    end if;
    if v_base = '' then
        return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', '[]'::jsonb);
    end if;

    v_sql :=
        'with base(engine,league_id,league_name,season_year,kickoff,market,selection,prob,hit) as (' || v_base || '),'
     || ' g as (select ' || v_grp || ' as grp, hit, prob from base b where b.prob is not null and b.hit is not null),'
     || ' agg as (select grp, count(*)::int n, sum(case when hit then 1 else 0 end)::int hits,'
     || '   avg(case when hit then 1.0 else 0.0 end) hit_rate, avg(prob) avg_prob'
     || '   from g group by grp having count(*)>0),'
     || ' wilson as (select grp, n, hits, round(hit_rate,4) hit_rate, round(avg_prob,4) avg_prob,'
     || '   round(((hit_rate + ' || v_z || '*' || v_z || '/(2*n))/(1+' || v_z || '*' || v_z || '/n))'
     || '     - (' || v_z || '*sqrt((hit_rate*(1-hit_rate)+' || v_z || '*' || v_z || '/(4*n))/n)/(1+' || v_z || '*' || v_z || '/n)),4) wilson_low,'
     || '   round(((hit_rate + ' || v_z || '*' || v_z || '/(2*n))/(1+' || v_z || '*' || v_z || '/n))'
     || '     + (' || v_z || '*sqrt((hit_rate*(1-hit_rate)+' || v_z || '*' || v_z || '/(4*n))/n)/(1+' || v_z || '*' || v_z || '/n)),4) wilson_high,'
     || '   round(hit_rate-avg_prob,4) calib_gap from agg)'
     || ' select coalesce(jsonb_agg(to_jsonb(w) order by w.n desc),''[]''::jsonb) from wilson w';

    execute v_sql into v_rows;
    return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', coalesce(v_rows,'[]'::jsonb));
end;
$$;


-- ----------------------------------------------------------------------------
-- get_analytics_filters: valori distinti per i menu (UNIONE analytics_signals +
-- API da fixture_predictions, così le leghe dell'API sono filtrabili anche se
-- non in analytics_signals).
-- ----------------------------------------------------------------------------
-- TUNING autovacuum: fixture_predictions e analytics_signals ricevono scritture
-- giornaliere (predizioni/risultati/upsert). Senza vacuum frequente la VISIBILITY
-- MAP si sporca e gli Index-Only Scan tornano a fare heap-fetch (lenti). Soglie
-- abbassate → autovacuum tiene la visibility map fresca → i filtri restano <0.5s.
alter table fixture_predictions set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);
alter table analytics_signals   set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);

-- get_analytics_filters: LIVE (niente cache). Veloce grazie al covering index
-- idx_fp_api_full (league_id, season_year) INCLUDE (...) → index-only scan.
-- 2 scansioni di fixture_predictions (leghe, stagioni). Le leghe API sono un
-- SUPERSET di analytics_signals → lista leghe da fixture_predictions sola.
create or replace function public.get_analytics_filters()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    with apilg as (
        select league_id, max(league_name) league_name, count(*) * 3 n
        from fixture_predictions where result_outcome is not null group by league_id
    ),
    apise as (
        select distinct season_year from fixture_predictions
        where result_outcome is not null and season_year is not null
    ),
    aseng as (select engine, count(*) n from analytics_signals where settled group by engine),
    asmkt as (select market, count(*) n from analytics_signals where settled group by market),
    apitot as (select coalesce(sum(n),0) n from apilg)
    select jsonb_build_object(
        'engines', (select coalesce(jsonb_agg(jsonb_build_object('value',value,'n',sn) order by sn desc),'[]'::jsonb)
            from (select value, sum(n) sn from (select engine value, n from aseng
                  union all select 'api', (select n from apitot)) e group by value) eg),
        'markets', (select coalesce(jsonb_agg(jsonb_build_object('value',value,'n',sn) order by sn desc),'[]'::jsonb)
            from (select value, sum(n) sn from (select market value, n from asmkt
                  union all select '1x2', (select n from apitot)) m group by value) mg),
        'leagues', (select coalesce(jsonb_agg(jsonb_build_object('id',league_id,'name',league_name,'n',n) order by n desc),'[]'::jsonb)
            from apilg),
        'seasons', (select coalesce(jsonb_agg(season_year order by season_year desc),'[]'::jsonb) from apise),
        'total_settled', (select n from apitot) + (select coalesce(sum(n),0) from aseng)
    );
$$;

-- GRANT: sola lettura aggregata da anon; le tabelle base restano inaccessibili.
revoke all on function public.get_analytics(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,text) from public;
grant execute on function public.get_analytics(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,text) to anon, authenticated, service_role;
revoke all on function public.get_analytics_filters() from public;
grant execute on function public.get_analytics_filters() to anon, authenticated, service_role;
