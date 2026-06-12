-- ============================================================================
-- MODULO "FREQUENZE MERCATI" — RPC di sola lettura (deploy: 2026-06-12)
-- ============================================================================
-- Calcola, per (league_id, mercato, selezione, intervallo):
--   baseline (frequenza storica), deviazione standard, MM5/MM10/MM15
--   (medie mobili cronologiche), z-score della MM10 vs baseline.
--
-- FATTI ACCERTATI (Fase 0 + certificazione copertura 2026-06-12):
--   - fulltime_* quasi mai NULL su settlate; goals_* diverge da fulltime_*
--     SOLO su AET/PEN (include i supplementari).
--   - SETTLEMENT 90': fulltime_* fonte primaria. Fallback su goals_* AMMESSO
--     SOLO per status 'FT' (dove goals=90', 0 divergenze verificate).
--     Per AET/PEN senza fulltime_* (213+19 righe nel DB) il punteggio al 90'
--     e' SCONOSCIUTO -> la riga viene ESCLUSA dalla serie (meglio escludere
--     che settlare a 120'). Resta contata in n_scope.
--   - Insieme settlato = whitelist status_short IN ('FT','AET','PEN')
--     (esistono anche 'CANC','Canc','Abd' -> esclusi).
--   - Copertura HT: ~100% campionati domestici, 35.3% FA Cup -> gate informativo.
--
-- CORRETTEZZA STATISTICA:
--   - Ordinamento DETERMINISTICO: ORDER BY fixture_date, fixture_id
--     (tiebreaker obbligatorio: kickoff simultanei sono comuni).
--   - MM solo a finestra piena: i primi N-1 punti sono NULL.
--   - Draw No Bet: i pareggi sono VOID -> esclusi dalla serie (non zeri).
--   - Mercati HT: righe senza halftime_* escluse dalla serie; la copertura HT
--     dell'intervallo viene restituita nei metadati (gate lato frontend).
--   - std = stddev_pop della serie binaria (= sqrt(p*(1-p)) per definizione).
--   - z-score = (MM10 - baseline) / (std / sqrt(10)).
--     NOTA: si normalizza per l'errore standard della media a finestra 10
--     (std/sqrt(10)), non per la std grezza dei singoli esiti: una banda
--     costruita sulla std grezza (~0.5) uscirebbe da [0,1] e lo z sarebbe
--     compresso di un fattore sqrt(10), rendendo il segnale inutilizzabile.
--     La std grezza resta esposta in meta.std; meta.se_mm5/10/15 sono gli
--     errori standard per ogni finestra (bande del grafico = baseline +/- k*se).
--
-- SICUREZZA: SECURITY DEFINER (la tabella matches non e' esposta ad anon),
-- sola lettura (STABLE), search_path fissato, input validati con whitelist.
-- ============================================================================

create or replace function public.get_market_frequency(
    p_league_id   integer,
    p_market      text,
    p_selection   text,
    p_line        numeric default null,   -- solo per ou_ft / ou_ht
    p_mode        text    default 'last_n', -- 'last_n' | 'season' | 'all'
    p_last_n      integer default 300,
    p_season_year integer default null      -- solo per mode='season'
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_result jsonb;
begin
    -- ------------------------------------------------------------------
    -- VALIDAZIONE INPUT (whitelist esplicite: un input invalido deve
    -- fallire rumorosamente, mai produrre una serie vuota silenziosa)
    -- ------------------------------------------------------------------
    if p_league_id is null or p_league_id <= 0 then
        raise exception 'p_league_id non valido: %', p_league_id;
    end if;
    if p_mode not in ('last_n','season','all') then
        raise exception 'p_mode invalido: %', p_mode;
    end if;
    if p_mode = 'last_n' and (p_last_n is null or p_last_n < 10 or p_last_n > 10000) then
        raise exception 'p_last_n fuori range [10,10000]: %', p_last_n;
    end if;
    if p_mode = 'season' and p_season_year is null then
        raise exception 'p_season_year obbligatorio con p_mode=season';
    end if;

    if p_market = '1x2' then
        if p_selection not in ('1','X','2') then raise exception 'selezione 1x2 invalida: %', p_selection; end if;
    elsif p_market = 'dc' then
        if p_selection not in ('1X','X2','12') then raise exception 'selezione dc invalida: %', p_selection; end if;
    elsif p_market = 'dnb' then
        if p_selection not in ('1','2') then raise exception 'selezione dnb invalida: %', p_selection; end if;
    elsif p_market = 'ou_ft' then
        if p_selection not in ('over','under') then raise exception 'selezione ou_ft invalida: %', p_selection; end if;
        if p_line is null or p_line not in (0.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5,8.5) then
            raise exception 'linea ou_ft invalida: %', p_line; end if;
    elsif p_market = 'btts' then
        if p_selection not in ('yes','no') then raise exception 'selezione btts invalida: %', p_selection; end if;
    elsif p_market in ('home_scores','away_scores') then
        if p_selection not in ('yes','no') then raise exception 'selezione % invalida: %', p_market, p_selection; end if;
    elsif p_market = 'exact_ft' then
        if p_selection !~ '^[0-3]-[0-3]$' and p_selection not in ('other_home','other_away','other_draw') then
            raise exception 'selezione exact_ft invalida: %', p_selection; end if;
    elsif p_market = '1x2_ht' then
        if p_selection not in ('1','X','2') then raise exception 'selezione 1x2_ht invalida: %', p_selection; end if;
    elsif p_market = 'ou_ht' then
        if p_selection not in ('over','under') then raise exception 'selezione ou_ht invalida: %', p_selection; end if;
        if p_line is null or p_line not in (0.5,1.5,2.5) then
            raise exception 'linea ou_ht invalida: %', p_line; end if;
    elsif p_market = 'exact_ht' then
        if p_selection !~ '^[0-2]-[0-2]$' and p_selection <> 'other' then
            raise exception 'selezione exact_ht invalida: %', p_selection; end if;
    elsif p_market = 'ht_ft' then
        if p_selection not in ('1-1','1-X','1-2','X-1','X-X','X-2','2-1','2-X','2-2') then
            raise exception 'selezione ht_ft invalida: %', p_selection; end if;
    else
        raise exception 'mercato non supportato: %', p_market;
    end if;

    -- ------------------------------------------------------------------
    -- PIPELINE: scope (intervallo) -> outcome binario -> serie valida
    --           -> baseline/std -> MM a finestra piena -> z-score
    -- ------------------------------------------------------------------
    with scope as (
        -- L'INTERVALLO: per 'last_n' = le ultime N partite SETTLATE della
        -- lega (poi rimesse in ordine cronologico ascendente); per 'season'
        -- la stagione; per 'all' tutto lo storico. SEMPRE filtrato per
        -- league_id (vincolo performance: mai full-scan).
        select fixture_id, fixture_date, home_team_name, away_team_name,
               -- Settlement 90': fallback su goals_* SOLO per status FT
               -- (su AET/PEN goals include i supplementari -> h/a NULL -> riga esclusa)
               case when fulltime_home is not null then fulltime_home
                    when status_short = 'FT'       then goals_home
               end as h,
               case when fulltime_away is not null then fulltime_away
                    when status_short = 'FT'       then goals_away
               end as a,
               halftime_home as hh, halftime_away as ha
        from matches
        where league_id = p_league_id
          and status_short in ('FT','AET','PEN')
          and (p_mode <> 'season' or season_year = p_season_year)
        order by fixture_date desc, fixture_id desc
        limit case when p_mode = 'last_n' then p_last_n else null end
    ),
    outcomes as (
        select s.*,
            case
            -- GUARD NULLITA' (prima di tutto): senza punteggio 90' i mercati FT
            -- non sono settlabili; senza HT i mercati HT non lo sono. Evita le
            -- trappole booleane SQL (NULL AND FALSE = FALSE) e il ramo ELSE
            -- di ht_ft che classificherebbe una riga ignota.
            when p_market in ('1x2','dc','dnb','ou_ft','btts','home_scores','away_scores','exact_ft','ht_ft')
                 and (s.h is null or s.a is null) then null
            when p_market in ('1x2_ht','ou_ht','exact_ht','ht_ft')
                 and (s.hh is null or s.ha is null) then null
            else
            case p_market
                when '1x2' then case p_selection
                    when '1' then (s.h > s.a)::int
                    when 'X' then (s.h = s.a)::int
                    when '2' then (s.h < s.a)::int end
                when 'dc' then case p_selection
                    when '1X' then (s.h >= s.a)::int
                    when 'X2' then (s.h <= s.a)::int
                    when '12' then (s.h <> s.a)::int end
                when 'dnb' then case
                    when s.h = s.a then null  -- VOID: pareggio escluso dalla serie
                    else case p_selection
                        when '1' then (s.h > s.a)::int
                        when '2' then (s.h < s.a)::int end end
                when 'ou_ft' then case p_selection
                    when 'over'  then ((s.h + s.a)::numeric > p_line)::int
                    when 'under' then ((s.h + s.a)::numeric < p_line)::int end
                when 'btts' then case p_selection
                    when 'yes' then (s.h > 0 and s.a > 0)::int
                    when 'no'  then (s.h = 0 or  s.a = 0)::int end
                when 'home_scores' then case p_selection
                    when 'yes' then (s.h > 0)::int
                    when 'no'  then (s.h = 0)::int end
                when 'away_scores' then case p_selection
                    when 'yes' then (s.a > 0)::int
                    when 'no'  then (s.a = 0)::int end
                when 'exact_ft' then case
                    when p_selection = 'other_home' then (s.h > s.a and (s.h > 3 or s.a > 3))::int
                    when p_selection = 'other_away' then (s.a > s.h and (s.h > 3 or s.a > 3))::int
                    when p_selection = 'other_draw' then (s.h = s.a and s.h >= 4)::int
                    else (s.h = split_part(p_selection,'-',1)::int
                      and s.a = split_part(p_selection,'-',2)::int)::int end
                -- Mercati HT: righe senza dato HT -> NULL -> escluse dalla serie
                when '1x2_ht' then case
                    when s.hh is null or s.ha is null then null
                    else case p_selection
                        when '1' then (s.hh > s.ha)::int
                        when 'X' then (s.hh = s.ha)::int
                        when '2' then (s.hh < s.ha)::int end end
                when 'ou_ht' then case
                    when s.hh is null or s.ha is null then null
                    else case p_selection
                        when 'over'  then ((s.hh + s.ha)::numeric > p_line)::int
                        when 'under' then ((s.hh + s.ha)::numeric < p_line)::int end end
                when 'exact_ht' then case
                    when s.hh is null or s.ha is null then null
                    when p_selection = 'other' then (s.hh > 2 or s.ha > 2)::int
                    else (s.hh = split_part(p_selection,'-',1)::int
                      and s.ha = split_part(p_selection,'-',2)::int)::int end
                when 'ht_ft' then case
                    when s.hh is null or s.ha is null then null
                    else ((case when s.hh > s.ha then '1' when s.hh = s.ha then 'X' else '2' end)
                          || '-' ||
                          (case when s.h > s.a then '1' when s.h = s.a then 'X' else '2' end)
                          = p_selection)::int end
            end
            end as outcome
        from scope s
    ),
    scope_stats as (
        select count(*)::int                                                as n_scope,
               round(100*avg((hh is not null and ha is not null)::int),1)   as ht_cov,
               min(fixture_date)                                            as d_from,
               max(fixture_date)                                            as d_to
        from scope
    ),
    ordered as (
        -- SPINA DORSALE: ordinamento cronologico deterministico
        select o.*, row_number() over (order by o.fixture_date asc, o.fixture_id asc) as idx
        from outcomes o
        where o.outcome is not null
    ),
    agg as (
        select count(*)::int                          as n_eff,
               avg(outcome)::numeric                  as baseline,
               coalesce(stddev_pop(outcome), 0)::numeric as std
        from ordered
    ),
    series as (
        select o.idx, o.fixture_id, o.fixture_date,
               o.home_team_name, o.away_team_name, o.outcome,
               -- MM SOLO a finestra piena: NULL per i primi N-1 punti
               case when o.idx >= 5  then round(avg(o.outcome) over w5, 6)  end as mm5,
               case when o.idx >= 10 then round(avg(o.outcome) over w10, 6) end as mm10,
               case when o.idx >= 15 then round(avg(o.outcome) over w15, 6) end as mm15
        from ordered o
        window
            w5  as (order by o.idx rows between 4  preceding and current row),
            w10 as (order by o.idx rows between 9  preceding and current row),
            w15 as (order by o.idx rows between 14 preceding and current row)
    )
    select jsonb_build_object(
        'meta', jsonb_build_object(
            'league_id',      p_league_id,
            'market',         p_market,
            'selection',      p_selection,
            'line',           case when p_market in ('ou_ft','ou_ht') then p_line end,
            'mode',           p_mode,
            'season_year',    p_season_year,
            'n_requested',    case when p_mode = 'last_n' then p_last_n end,
            'n_scope',        ss.n_scope,                  -- partite settlate nell'intervallo
            'n_effective',    a.n_eff,                     -- punti reali della serie (denominatore)
            'baseline',       round(a.baseline, 6),
            'std',            round(a.std, 6),
            'se_mm5',         round(a.std / sqrt(5.0), 6),
            'se_mm10',        round(a.std / sqrt(10.0), 6),
            'se_mm15',        round(a.std / sqrt(15.0), 6),
            'ht_coverage_pct', ss.ht_cov,
            'date_from',      ss.d_from,
            'date_to',        ss.d_to
        ),
        'points', coalesce((
            select jsonb_agg(jsonb_build_object(
                'idx',  se.idx,
                'fid',  se.fixture_id,
                'date', se.fixture_date,
                'home', se.home_team_name,
                'away', se.away_team_name,
                'out',  se.outcome,
                'mm5',  se.mm5,
                'mm10', se.mm10,
                'mm15', se.mm15,
                'z',    case when se.mm10 is not null and a.std > 0
                             then round((se.mm10 - a.baseline) / (a.std / sqrt(10.0)), 3) end
            ) order by se.idx)
            from series se
        ), '[]'::jsonb)
    )
    into v_result
    from agg a, scope_stats ss;

    return v_result;
end;
$$;

comment on function public.get_market_frequency is
'Frequenze Mercati: baseline + MM5/10/15 + z-score per (lega, mercato, selezione, intervallo). Sola lettura su matches. Ordinamento deterministico (fixture_date, fixture_id). MM a finestra piena. DNB: pareggi void. HT: righe senza dato escluse, copertura esposta in meta.';

-- ----------------------------------------------------------------------------
-- Stagioni disponibili per lega (per i picker dell''UI): n settlate + copertura HT
-- ----------------------------------------------------------------------------
create or replace function public.get_league_seasons(p_league_id integer)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_result jsonb;
begin
    if p_league_id is null or p_league_id <= 0 then
        raise exception 'p_league_id non valido: %', p_league_id;
    end if;
    select coalesce(jsonb_agg(jsonb_build_object(
               'season_year', t.season_year,
               'n_settled',   t.n,
               'ht_coverage_pct', t.ht
           ) order by t.season_year desc), '[]'::jsonb)
    into v_result
    from (
        select season_year,
               count(*)::int as n,
               round(100*avg((halftime_home is not null and halftime_away is not null)::int),1) as ht
        from matches
        where league_id = p_league_id
          and status_short in ('FT','AET','PEN')
        group by season_year
    ) t;
    return v_result;
end;
$$;

comment on function public.get_league_seasons is
'Stagioni disponibili per una lega: numero partite settlate e copertura HT per stagione.';

-- ----------------------------------------------------------------------------
-- GRANT: eseguibili dal client anon del frontend (sola lettura aggregata)
-- ----------------------------------------------------------------------------
revoke all on function public.get_market_frequency(integer,text,text,numeric,text,integer,integer) from public;
grant execute on function public.get_market_frequency(integer,text,text,numeric,text,integer,integer) to anon, authenticated, service_role;

revoke all on function public.get_league_seasons(integer) from public;
grant execute on function public.get_league_seasons(integer) to anon, authenticated, service_role;
