-- ============================================================================
-- RPC DECISIONI — analisi del layer decisionale analytics_decisions (2026-06-22)
-- ============================================================================
-- get_decisions: aggrega le DECISIONI con filtri (decision_logic, status, motore,
-- mercato, lega, motivo scarto, date) e raggruppamento. Per ogni gruppo:
--   n, piazzate/scartate/no_signal, settlate, hit, hit_rate (delle piazzate
--   settlate), stake/pnl/ROI, edge/odds/prob medi.
-- → "filtrare le piazzate per tipologia di idea (decision_logic) e capire ROI,
--    dove si vince/perde, e PERCHÉ i segnali vengono scartati (reject_filter)".
--
-- SICUREZZA: SECURITY DEFINER (analytics_decisions non esposta), STABLE,
-- search_path fisso, input whitelist, SQL dinamico injection-safe (%L/typed-%s),
-- solo aggregati. get_decisions_filters per i menu.
-- ============================================================================

create or replace function public.get_decisions(
    p_logic       text    default null,
    p_status      text    default null,   -- PLACED|REJECTED|NO_SIGNAL
    p_engine      text    default null,
    p_market      text    default null,
    p_selection   text    default null,
    p_league_id   integer default null,
    p_season_year integer default null,
    p_reject      text    default null,   -- reject_filter
    p_date_from   timestamptz default null,
    p_date_to     timestamptz default null,
    p_group_by    text    default 'logic' -- logic|engine|market|selection|status|reject|league|confidence
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_grp text; w text := ''; v_sql text; v_rows jsonb;
begin
    if p_status is not null and p_status not in ('PLACED','REJECTED','NO_SIGNAL') then
        raise exception 'p_status invalido: %', p_status; end if;
    if p_engine is not null and p_engine not in ('poisson','ml','api','tacticai') then
        raise exception 'p_engine invalido: %', p_engine; end if;
    if p_group_by not in ('logic','engine','market','selection','status','reject','league','confidence') then
        raise exception 'p_group_by invalido: %', p_group_by; end if;

    v_grp := case p_group_by
        when 'logic'      then 'd.decision_logic'
        when 'engine'     then 'd.engine'
        when 'market'     then 'd.market'
        when 'selection'  then 'd.market || '' / '' || d.selection'
        when 'status'     then 'd.status'
        when 'reject'     then 'coalesce(d.reject_filter, ''(nessuno)'')'
        when 'league'     then 'coalesce(d.league_name, d.league_id::text)'
        when 'confidence' then 'case when d.prob is null then ''(n/d)'' else (least(floor(d.prob*20),19)*5)::int::text || ''-'' || (least(floor(d.prob*20),19)*5+5)::int::text || ''%'' end'
    end;

    if p_logic     is not null then w := w || format(' and d.decision_logic = %L', p_logic); end if;
    if p_status    is not null then w := w || format(' and d.status = %L', p_status); end if;
    if p_engine    is not null then w := w || format(' and d.engine = %L', p_engine); end if;
    if p_market    is not null then w := w || format(' and d.market = %L', p_market); end if;
    if p_selection is not null then w := w || format(' and d.selection = %L', p_selection); end if;
    if p_reject    is not null then w := w || format(' and d.reject_filter = %L', p_reject); end if;
    if p_league_id is not null then w := w || format(' and d.league_id = %s', p_league_id); end if;
    if p_season_year is not null then w := w || format(' and d.season_year = %s', p_season_year); end if;
    if p_date_from is not null then w := w || format(' and d.kickoff >= %L', p_date_from); end if;
    if p_date_to   is not null then w := w || format(' and d.kickoff <= %L', p_date_to); end if;

    v_sql :=
        'with f as (select ' || v_grp || ' as grp, d.status, d.settled, d.hit, d.stake, d.pnl, d.edge, d.odds, d.prob'
     || '   from analytics_decisions d where true' || w || '),'
     || ' agg as (select grp,'
     || '   count(*)::int n,'
     || '   count(*) filter (where status=''PLACED'')::int placed,'
     || '   count(*) filter (where status=''REJECTED'')::int rejected,'
     || '   count(*) filter (where status=''NO_SIGNAL'')::int no_signal,'
     || '   count(*) filter (where status=''PLACED'' and settled and hit is not null)::int settled_placed,'
     || '   count(*) filter (where status=''PLACED'' and settled and hit)::int hits,'
     -- ROI/pnl SOLO su piazzate SETTLATE (stessa popolazione di hit_rate): è il
     -- rendimento REALIZZATO, non diluito dalle bet ancora aperte.
     || '   coalesce(sum(stake) filter (where status=''PLACED'' and settled),0) stake,'
     || '   coalesce(sum(pnl)   filter (where status=''PLACED'' and settled),0) pnl,'
     -- medie sull''intero gruppo (popolazione coerente; avg ignora i NULL → avg_odds
     -- è di fatto sulle piazzate, le scartate non hanno quota).
     || '   avg(edge) avg_edge,'
     || '   avg(odds) avg_odds,'
     || '   avg(prob) avg_prob'
     || '   from f group by grp having count(*)>0),'
     || ' out as (select grp, n, placed, rejected, no_signal, settled_placed, hits,'
     || '   round(stake,2) stake, round(pnl,2) pnl,'
     || '   case when settled_placed>0 then round(hits::numeric/settled_placed,4) end hit_rate,'
     || '   case when stake>0 then round(pnl/stake,4) end roi,'
     || '   round(avg_edge,4) avg_edge, round(avg_odds,3) avg_odds, round(avg_prob,4) avg_prob'
     || '   from agg)'
     || ' select coalesce(jsonb_agg(to_jsonb(o) order by o.n desc),''[]''::jsonb) from out o';
    execute v_sql into v_rows;
    return jsonb_build_object('group_by', p_group_by, 'groups', coalesce(v_rows,'[]'::jsonb));
end;
$$;


create or replace function public.get_decisions_filters()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select jsonb_build_object(
        'logics',  (select coalesce(jsonb_agg(jsonb_build_object('value',decision_logic,'n',n) order by n desc),'[]'::jsonb)
                    from (select decision_logic, count(*) n from analytics_decisions group by decision_logic) x),
        'statuses',(select coalesce(jsonb_agg(jsonb_build_object('value',status,'n',n) order by n desc),'[]'::jsonb)
                    from (select status, count(*) n from analytics_decisions group by status) x),
        'engines', (select coalesce(jsonb_agg(jsonb_build_object('value',engine,'n',n) order by n desc),'[]'::jsonb)
                    from (select engine, count(*) n from analytics_decisions group by engine) x),
        'markets', (select coalesce(jsonb_agg(jsonb_build_object('value',market,'n',n) order by n desc),'[]'::jsonb)
                    from (select market, count(*) n from analytics_decisions where market <> '(none)' group by market) x),
        'rejects', (select coalesce(jsonb_agg(jsonb_build_object('value',reject_filter,'n',n) order by n desc),'[]'::jsonb)
                    from (select reject_filter, count(*) n from analytics_decisions where reject_filter is not null group by reject_filter) x),
        'total',   (select count(*) from analytics_decisions)
    );
$$;

revoke all on function public.get_decisions(text,text,text,text,text,integer,integer,text,timestamptz,timestamptz,text) from public;
grant execute on function public.get_decisions(text,text,text,text,text,integer,integer,text,timestamptz,timestamptz,text) to anon, authenticated, service_role;
revoke all on function public.get_decisions_filters() from public;
grant execute on function public.get_decisions_filters() to anon, authenticated, service_role;
