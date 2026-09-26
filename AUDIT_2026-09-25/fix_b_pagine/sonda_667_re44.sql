select md5(public.get_market_delays(667,'re','4-4','all',null,null)::text) vecchia, md5((    with scope as (
 select fixture_id, fixture_date, home_team_name, away_team_name,
 case when fulltime_home is not null then fulltime_home
 when status_short = 'FT'       then goals_home end as h,
 case when fulltime_away is not null then fulltime_away
 when status_short = 'FT'       then goals_away end as a,
 halftime_home as hh,
 halftime_away as ha
 from matches
 where league_id = 667::integer
 and status_short in ('FT','AET','PEN')
 and ('all'::text <> 'season' or season_year = null::integer)
 order by fixture_date desc, fixture_id desc
 limit case when 'all'::text = 'last_n' then null::integer else null end
 ),
 outcomes as (
 select s.fixture_id, s.fixture_date, s.home_team_name, s.away_team_name,
 s.h, s.a, s.hh, s.ha,
 case
 when (s.h is null or s.a is null) then null
 when false and (s.hh is null or s.ha is null) then null
 else
 case 're'::text
 when 're'    then (s.h = 4::integer and s.a = 4::integer)::int
 when 'sge'   then ((s.h + s.a) = null::integer)::int
 when 'over'  then ((s.h + s.a)::numeric > null::numeric)::int
 when 'under' then ((s.h + s.a)::numeric < null::numeric)::int
 when 'ovpt'  then ((s.hh + s.ha)::numeric > null::numeric)::int
 when 'unpt'  then ((s.hh + s.ha)::numeric < null::numeric)::int
 when 'ggpt'  then (s.hh > 0 and s.ha > 0)::int
 when 'ggst'  then ((s.h - s.hh) > 0 and (s.a - s.ha) > 0)::int
 when 'pf1x'  then (s.hh > s.ha and s.h = s.a)::int
 when 'pf2x'  then (s.hh < s.ha and s.h = s.a)::int
 when 'pfx1'  then (s.hh = s.ha and s.h > s.a)::int
 when 'pfx2'  then (s.hh = s.ha and s.h < s.a)::int
 when 'pt1'   then (s.hh > s.ha)::int
 when 'ptx'   then (s.hh = s.ha)::int
 when 'pt2'   then (s.hh < s.ha)::int
 when 'x'     then (s.h = s.a)::int
 when '1'     then (s.h > s.a)::int
 when '2'     then (s.h < s.a)::int
 when 'gg'    then (s.h > 0 and s.a > 0)::int
 when 'ng'    then (s.h = 0 or s.a = 0)::int
 when 'ggov25' then (s.h > 0 and s.a > 0 and (s.h + s.a) > 2)::int
 end
 end as outcome
 from scope s
 ),
 scope_stats as (
 select count(*)::int                                              as n_scope,
 (count(*) filter (where false and h is not null and a is not null
 and (hh is null or ha is null)))::int as n_ht_missing,
 round(100*avg((hh is not null and ha is not null)::int),1) as ht_cov,
 min(fixture_date)                                          as d_from,
 max(fixture_date)                                          as d_to
 from scope
 ),
 ordered as (
 select o.fixture_id, o.fixture_date, o.home_team_name, o.away_team_name,
 o.h as gc, o.a as ga, o.hh as gcfh, o.ha as gafh, o.outcome,
 row_number() over (order by o.fixture_date asc, o.fixture_id asc) as idx
 from outcomes o
 where o.outcome is not null
 ),
 series_rows as (
 select r.*,
 coalesce(max(case when r.outcome = 1 then r.idx end)
 over (order by r.idx rows between unbounded preceding and current row), 0) as last_hit
 from ordered r
 ),
 rit as (
 select sr.*, (sr.idx - sr.last_hit) as rit_val
 from series_rows sr
 ),
 hits as (
 select h.idx as hit_idx,
 row_number() over (order by h.idx) as hit_seq,
 (h.idx - coalesce(lag(h.idx) over (order by h.idx), 0) - 1) as suc
 from ordered h
 where h.outcome = 1
 ),
 base as (
 select (select count(*)::int from ordered)                            as n_eff,
 (select count(*)::int from hits)                               as n_occ,
 (select rit_val from rit order by idx desc limit 1)            as ritardo_attuale,
 (select max(suc)::int from hits)                              as record,
 (select avg(rit_val)::numeric
 from rit where rit_val <> 0)                                as media_rit
 ),
 derived as (
 select b.*,
 case when b.n_occ > 0 then round(b.n_occ::numeric / b.n_eff, 6) end as frequency,
 case when b.n_occ > 0 then round(b.n_eff::numeric / b.n_occ, 6) end as media_storica
 from base b
 ),
 occ_by_len as (
 select suc as k, count(*)::int as c from hits group by suc
 ),
 rit_by_len as (
 select rit_val as k, count(*)::int as c from rit group by rit_val
 ),
 distrib as (
 select v.k as len,
 coalesce(o.c, 0)   as occ_suc,
 coalesce(r2.c, 0)  as cnt_rit
 from generate_series(0, greatest(
 coalesce((select max(suc) from hits), 0),
 coalesce((select max(rit_val) from rit), 0))) as v(k)
 left join occ_by_len o  on o.k  = v.k
 left join rit_by_len r2 on r2.k = v.k
 ),
 last10 as (
 select suc, hit_idx
 from hits order by hit_idx desc limit 10
 ),
 cond_last as (
 select suc as last_suc from hits order by hit_seq desc limit 1
 ),
 cond_pairs as (
 select h.suc as cur, lead(h.suc) over (order by h.hit_seq) as nxt
 from hits h
 ),
 storico as (
 select cp.nxt as len, count(*)::int as cnt
 from cond_pairs cp, cond_last cl
 where cp.cur = cl.last_suc and cp.nxt is not null
 group by cp.nxt
 ),
 over_under as (
 select
 count(*) filter (where suc <= floor((select media_rit from derived)))::int      as sotto,
 count(*) filter (where suc >= floor((select media_rit from derived)) + 1)::int   as sopra
 from hits
 ),
 runs_flag as (
 select h.hit_seq, h.suc,
 case when h.suc >= (select media_rit from derived) then 1 else 0 end as over_flag
 from hits h
 ),
 runs_island as (
 select rf.*,
 rf.hit_seq - row_number() over (order by rf.hit_seq) as island
 from runs_flag rf
 where rf.over_flag = 1
 ),
 runs_len as (
 select island, count(*)::int as run_len
 from runs_island group by island
 ),
 runs_hist as (
 select run_len, count(*)::int as cnt
 from runs_len group by run_len
 ),
 bl_tokens as (
 select h.hit_seq as ord, 0 as token
 from hits h
 where h.suc < (select media_rit from derived)
 union all
 select max(ri.hit_seq) as ord, count(*)::int as token
 from runs_island ri
 group by ri.island
 )
 select jsonb_build_object(
 'meta', jsonb_build_object(
 'league_id',       667::integer,
 'market',          're'::text,
 'target',          '4-4'::text,
 'mode',            'all'::text,
 'season_year',     null::integer,
 'n_requested',     case when 'all'::text='last_n' then null::integer end,
 'n_scope',         ss.n_scope,
 'n_effective',     d.n_eff,
 'uses_ht',         false,
 'ht_coverage_pct', ss.ht_cov,
 'ht_missing_rule', 'escluse',
 'n_ht_missing',    ss.n_ht_missing,
 'date_from',       ss.d_from,
 'date_to',         ss.d_to
 ),
 'stats', jsonb_build_object(
 'n_occ',            d.n_occ,
 'frequency',        d.frequency,
 'media_storica',    d.media_storica,
 'quota_oggettiva',  d.media_storica,
 'ritardo_attuale',  d.ritardo_attuale,
 'record',           d.record,
 'media_ritardi',    round(d.media_rit, 4),
 'sotto_media',      ou.sotto,
 'sopra_media',      ou.sopra,
 'sotto_media_pct',  case when d.n_occ>0 then round(ou.sotto::numeric/d.n_occ,4) end,
 'sopra_media_pct',  case when d.n_occ>0 then round(ou.sopra::numeric/d.n_occ,4) end,
 'rit_vs_media',     case when d.media_storica>0
 then round(d.ritardo_attuale::numeric/d.media_storica,3) end,
 'storico_cond_su',  (select last_suc from cond_last)
 ),
 'distribuzione_serie', coalesce((
 select jsonb_agg(jsonb_build_object('len',len,'occ_suc',occ_suc,'cnt_rit',cnt_rit) order by len)
 from distrib), '[]'::jsonb),
 'ultime_10_serie', coalesce((
 select jsonb_agg(suc order by hit_idx) from last10), '[]'::jsonb),
 'storico_serie', coalesce((
 select jsonb_agg(jsonb_build_object(
 'len', len, 'count', cnt,
 'pct', round(cnt::numeric / nullif((select sum(cnt) from storico),0), 4))
 order by cnt desc, len asc)
 from storico), '[]'::jsonb),
 'run_sopra_media', coalesce((
 select jsonb_agg(jsonb_build_object(
 'run_len', run_len, 'count', cnt,
 'pct', round(cnt::numeric / nullif((select sum(cnt) from runs_hist),0), 4))
 order by run_len asc)
 from runs_hist), '[]'::jsonb),
 'ultime_10_strisce_sopra_media', coalesce((
 select jsonb_agg(token order by ord)
 from (select token, ord from bl_tokens order by ord desc limit 10) t),
 '[]'::jsonb),
 'series', coalesce((
 select jsonb_agg(jsonb_build_object(
 'idx',  rt.idx,
 'fid',  rt.fixture_id,
 'date', rt.fixture_date,
 'home', rt.home_team_name,
 'away', rt.away_team_name,
 'gc',   rt.gc,
 'ga',   rt.ga,
 'gcfh', rt.gcfh,
 'gafh', rt.gafh,
 'gcsh', rt.gc - coalesce(rt.gcfh,0),
 'gash', rt.ga - coalesce(rt.gafh,0),
 'out',  rt.outcome,
 'rit',  rt.rit_val,
 'suc',  h.suc)
 order by rt.idx)
 from rit rt
 left join hits h on h.hit_idx = rt.idx), '[]'::jsonb)
 )
 from derived d, scope_stats ss, over_under ou)::text) nuova