-- ============================================================================
-- RPC ANALYTICS — lettura aggregata della tabella analytics_signals (2026-06-22)
-- ============================================================================
-- get_analytics: pagella aggregata (hit-rate + intervallo di Wilson 95%) con
-- filtri iper-personalizzabili e raggruppamento. SOLO righe settlate per gli
-- hit-rate (settled=true, hit non-null).
--
-- CORRETTEZZA STATISTICA (soldi in gioco):
--   - hit_rate = hits / n  (n = righe settlate che matchano i filtri).
--   - Intervallo di WILSON al 95% (z=1.96): robusto su n piccoli, sempre in
--     [0,1] (a differenza del normale/Wald). center/half secondo la formula
--     standard del Wilson score interval.
--   - avg_prob = media della prob del motore (per confronto con la frequenza reale
--     = calibrazione: se hit_rate < avg_prob il motore è sovrastimato).
--   - Nessun gruppo con n=0 viene emesso (niente percentuali su zero).
--
-- SICUREZZA (repo pubblica): SECURITY DEFINER (analytics_signals NON è esposta
-- ad anon), STABLE (sola lettura), search_path fissato, input validati. Grant
-- execute ad anon/authenticated; la tabella resta inaccessibile direttamente.
-- ============================================================================

create or replace function public.get_analytics(
    p_engine        text    default null,    -- 'poisson'|'ml'|'api'|'tacticai'|null=tutti
    p_market        text    default null,    -- es 'over_2_5'|null=tutti
    p_selection     text    default null,    -- es 'Over'|null=tutte
    p_league_id     integer default null,
    p_season_year   integer default null,
    p_prob_min      numeric default null,    -- fascia di confidenza [min,max]
    p_prob_max      numeric default null,
    p_min_agree     integer default null,    -- concordanza minima fra motori
    p_placed_only   boolean default false,
    p_date_from     timestamptz default null,
    p_date_to       timestamptz default null,
    p_group_by      text    default 'overall' -- overall|engine|market|selection|league|confidence
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_z      constant numeric := 1.96;   -- 95%
    v_rows   jsonb;
    v_group  text;
begin
    -- validazione input (whitelist: input invalido => errore rumoroso)
    if p_engine is not null and p_engine not in ('poisson','ml','api','tacticai') then
        raise exception 'p_engine invalido: %', p_engine;
    end if;
    if p_group_by not in ('overall','engine','market','selection','league','confidence') then
        raise exception 'p_group_by invalido: %', p_group_by;
    end if;
    if p_prob_min is not null and (p_prob_min < 0 or p_prob_min > 1) then
        raise exception 'p_prob_min fuori [0,1]: %', p_prob_min; end if;
    if p_prob_max is not null and (p_prob_max < 0 or p_prob_max > 1) then
        raise exception 'p_prob_max fuori [0,1]: %', p_prob_max; end if;

    v_group := p_group_by;

    with filtered as (
        select s.*,
            case
                when v_group = 'engine'     then s.engine
                when v_group = 'market'     then s.market
                when v_group = 'selection'  then s.market || ' / ' || s.selection
                when v_group = 'league'     then coalesce(s.league_name, s.league_id::text)
                when v_group = 'confidence' then
                    -- fasce di confidenza 5% sulla prob del motore.
                    -- least(...,19) evita la fascia spuria '100-105%' quando prob=1.0.
                    (least(floor(s.prob * 20), 19) * 5)::int::text || '-'
                        || (least(floor(s.prob * 20), 19) * 5 + 5)::int::text || '%'
                else 'overall'
            end as grp
        from analytics_signals s
        -- prob NOT NULL obbligatoria: serve a confidence-bin e avg_prob; senza,
        -- avg(prob) userebbe un denominatore diverso da n/hits (calib_gap errato).
        where s.settled = true and s.hit is not null and s.prob is not null
          and (p_engine      is null or s.engine = p_engine)
          and (p_market      is null or s.market = p_market)
          and (p_selection   is null or s.selection = p_selection)
          and (p_league_id   is null or s.league_id = p_league_id)
          and (p_season_year is null or s.season_year = p_season_year)
          and (p_prob_min    is null or s.prob >= p_prob_min)
          and (p_prob_max    is null or s.prob <= p_prob_max)
          and (p_min_agree   is null or s.n_engines_agree >= p_min_agree)
          and (p_placed_only is false or s.placed = true)
          and (p_date_from   is null or s.kickoff >= p_date_from)
          and (p_date_to     is null or s.kickoff <= p_date_to)
    ),
    agg as (
        select grp,
            count(*)::int                          as n,
            sum(case when hit then 1 else 0 end)::int as hits,
            avg(case when hit then 1.0 else 0.0 end)  as hit_rate,
            avg(prob)                                 as avg_prob
        from filtered
        group by grp
        having count(*) > 0
    ),
    wilson as (
        select grp, n, hits,
            round(hit_rate, 4)  as hit_rate,
            round(avg_prob, 4)  as avg_prob,
            -- Wilson 95%: center ± half, sempre in [0,1]
            round( ((hit_rate + v_z*v_z/(2*n)) / (1 + v_z*v_z/n))
                   - (v_z * sqrt( (hit_rate*(1-hit_rate) + v_z*v_z/(4*n)) / n ) / (1 + v_z*v_z/n)), 4) as wilson_low,
            round( ((hit_rate + v_z*v_z/(2*n)) / (1 + v_z*v_z/n))
                   + (v_z * sqrt( (hit_rate*(1-hit_rate) + v_z*v_z/(4*n)) / n ) / (1 + v_z*v_z/n)), 4) as wilson_high,
            -- scostamento calibrazione: hit_rate - avg_prob (negativo = motore sovrastima)
            round(hit_rate - avg_prob, 4) as calib_gap
        from agg
    )
    select coalesce(jsonb_agg(to_jsonb(w) order by w.n desc), '[]'::jsonb)
    into v_rows from wilson w;

    return jsonb_build_object(
        'group_by', v_group,
        'z', v_z,
        'groups', v_rows
    );
end;
$$;


-- ----------------------------------------------------------------------------
-- get_analytics_filters: valori distinti per popolare i menu del frontend
-- (engine, market, lega, stagione) — solo righe settlate, con conteggi.
-- ----------------------------------------------------------------------------
create or replace function public.get_analytics_filters()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select jsonb_build_object(
        'engines',  (select coalesce(jsonb_agg(jsonb_build_object('value', engine, 'n', n) order by n desc), '[]'::jsonb)
                     from (select engine, count(*) n from analytics_signals where settled group by engine) e),
        'markets',  (select coalesce(jsonb_agg(jsonb_build_object('value', market, 'n', n) order by n desc), '[]'::jsonb)
                     from (select market, count(*) n from analytics_signals where settled group by market) m),
        'leagues',  (select coalesce(jsonb_agg(jsonb_build_object('id', league_id, 'name', league_name, 'n', n) order by n desc), '[]'::jsonb)
                     from (select league_id, max(league_name) league_name, count(*) n from analytics_signals where settled group by league_id) l),
        'seasons',  (select coalesce(jsonb_agg(distinct season_year order by season_year desc), '[]'::jsonb)
                     from analytics_signals where settled and season_year is not null),
        'total_settled', (select count(*) from analytics_signals where settled)
    );
$$;

-- ----------------------------------------------------------------------------
-- GRANT: eseguibili dal client anon (sola lettura aggregata). La tabella
-- analytics_signals resta NON accessibile direttamente (RLS, nessuna policy).
-- ----------------------------------------------------------------------------
revoke all on function public.get_analytics(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,text) from public;
grant execute on function public.get_analytics(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,text) to anon, authenticated, service_role;

revoke all on function public.get_analytics_filters() from public;
grant execute on function public.get_analytics_filters() to anon, authenticated, service_role;

