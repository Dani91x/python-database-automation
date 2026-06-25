-- ============================================================================
-- direction_report_rpc.sql — RENDICONTO DIREZIONI (Reportistiche → "Direzioni")
-- ============================================================================
-- Monitora come performano nel tempo i MIGLIORI SEGNALI della tab "Direzione"
-- (cruscotto get_direction): per giorno, per lega, per segnale (mercato).
--
-- COS'È UNA "DIREZIONE" (unità di misura, money-critical):
--   per ogni (fixture, mercato) = la selezione argmax del motore LEADER (Poisson),
--   esattamente come la tab Direzione (get_direction). Tie-break DETERMINISTICO
--   (prob desc, selection asc) → riproducibile 1:1 dall'oracolo di certificazione.
--
-- VERITÀ SUI RISULTATI (auto-update): legge SOLO analytics_signals, la cui colonna
--   hit/settled è calcolata da analytics_settlement.hit() e riscritta ogni giorno
--   dalla pipeline (aggiorna_report.bat → betfair_report_manager Fase 13 →
--   merge_engine_signals.py --days 4). Quindi il report si aggiorna DA SOLO appena
--   i risultati entrano: nessun job nuovo, nessuna tabella nuova. Sola lettura.
--
-- CORRETTEZZA (soldi in gioco):
--   • hit_rate = hits / N  dove  N = direzioni con esito NOTO (hit IS NOT NULL).
--     Le direzioni con HT mancante (es. ht_1x2/first_half su leghe senza HT) hanno
--     hit NULL e NON entrano nel denominatore: MAI contate come errori.
--   • "buone" = concordanza ≥ 2 motori (n_engines_agree >= 2).
--   • avg_prob calcolato sullo STESSO insieme (hit not null) → calibrazione onesta.
--   • intervallo di WILSON 95% (z=1.96, sempre in [0,1]) sul totale.
--   • nessun arrotondamento nell'SQL: l'oracolo confronta a tol 1e-9.
--
-- SICUREZZA (repo pubblica): SECURITY DEFINER (analytics_signals non è esposta ad
--   anon/authenticated), STABLE, search_path fisso, input validati, solo aggregati.
--   REVOKE da public/anon; GRANT EXECUTE solo authenticated + service_role.
-- ============================================================================

-- Solo i 7 mercati canonici del cruscotto Direzione (intersezione Poisson∩ML∩TacticAI).
-- Whitelist usata per validare p_market.
--   1x2, ht_1x2, over_1_5, over_2_5, over_3_5, btts, first_half_over_0_5

-- INDICE COPRENTE per le 3 RPC: predicato esatto (engine='poisson' AND settled),
-- chiave kickoff (range) + fixture_id/market (DISTINCT ON), INCLUDE di ciò che si
-- legge → Index Scan mirato invece di seq-scan su tutta analytics_signals.
create index if not exists idx_as_poisson_report
    on public.analytics_signals (kickoff, fixture_id, market)
    include (selection, prob, hit, n_engines_agree, league_id, league_name,
             home_team, away_team, goals_home, goals_away)
    where engine = 'poisson' and settled;

-- p_betfair_only: se true, SOLO le partite presenti in engine_signals (= partite
-- realmente su Betfair, stesso criterio di get_betfair_fixtures). Filtro primario:
-- agisce su tutto (KPI, andamento, heatmap, leghe, lista).
drop function if exists public.get_direction_report(date,date,bigint,text,boolean);

create or replace function public.get_direction_report(
    p_from        date    default (now() at time zone 'Europe/Rome')::date - 7,
    p_to          date    default (now() at time zone 'Europe/Rome')::date,
    p_league_id   bigint  default null,
    p_market      text    default null,
    p_only_good   boolean default false,
    p_betfair_only boolean default false
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
set statement_timeout = '30s'
as $$
declare
    v_z       constant numeric := 1.96;
    v_from_ts timestamptz;
    v_to_ts   timestamptz;   -- esclusivo (giorno successivo a p_to)
    v_out     jsonb;
begin
    -- validazione input (errore rumoroso, mai output silenzioso sbagliato)
    if p_from is null or p_to is null then
        raise exception 'p_from/p_to obbligatori'; end if;
    if p_to < p_from then
        raise exception 'intervallo invalido: p_to (%) < p_from (%)', p_to, p_from; end if;
    if p_market is not null and p_market not in
        ('1x2','ht_1x2','over_1_5','over_2_5','over_3_5','btts','first_half_over_0_5') then
        raise exception 'p_market non canonico: %', p_market; end if;

    -- finestra su kickoff (mezzanotte di Roma → timestamptz): usa l'indice su kickoff
    v_from_ts := (p_from::timestamp) at time zone 'Europe/Rome';
    v_to_ts   := ((p_to + 1)::timestamp) at time zone 'Europe/Rome';

    with
    -- 1 riga = la DIREZIONE (argmax Poisson) per (fixture, mercato).
    -- Filtro lega/mercato applicato sullo scan; only_good lo si applica dopo
    -- (così meta.leagues resta stabile a prescindere dal toggle "solo buone").
    base_all as (
        select distinct on (s.fixture_id, s.market)
               s.fixture_id,
               s.market,
               s.selection,
               s.prob,
               s.hit,
               s.n_engines_agree,
               s.league_id,
               s.league_name,
               (s.kickoff at time zone 'Europe/Rome')::date as giorno
        from public.analytics_signals s
        where s.engine = 'poisson'
          and s.settled
          and s.kickoff >= v_from_ts
          and s.kickoff <  v_to_ts
          and (p_market is null or s.market = p_market)
          and (not p_betfair_only or s.fixture_id in (select fixture_id from public.engine_signals))
        order by s.fixture_id, s.market, s.prob desc nulls last, s.selection
    ),
    -- insieme valutato: + filtro lega + filtro "solo buone"
    b as (
        select *
        from base_all
        where (p_league_id is null or league_id = p_league_id)
          and (not p_only_good or n_engines_agree >= 2)
    ),
    -- elenco leghe disponibili (per il menu a tendina): su date+mercato, NON
    -- filtrato per lega né per only_good → stabile.
    leagues as (
        select league_id,
               max(league_name) as league_name,
               count(*) filter (where hit is not null) as n
        from base_all
        group by league_id
        having count(*) filter (where hit is not null) > 0
    ),
    -- KPI totali
    kpi as (
        select
            count(*) filter (where hit is not null)                          as n,
            count(*) filter (where hit)                                      as hits,
            avg(prob) filter (where hit is not null)                         as avg_prob,
            count(*) filter (where hit is not null and n_engines_agree >= 2) as good_n,
            count(*) filter (where hit and n_engines_agree >= 2)             as good_hits
        from b
    ),
    -- per giorno (andamento nel tempo)
    daily as (
        select giorno,
               count(*) filter (where hit is not null)                          as n,
               count(*) filter (where hit)                                      as hits,
               avg(prob) filter (where hit is not null)                         as avg_prob,
               count(*) filter (where hit is not null and n_engines_agree >= 2) as good_n,
               count(*) filter (where hit and n_engines_agree >= 2)             as good_hits
        from b
        group by giorno
        order by giorno
    ),
    -- per mercato (segnale)
    by_market as (
        select market,
               count(*) filter (where hit is not null)                          as n,
               count(*) filter (where hit)                                      as hits,
               avg(prob) filter (where hit is not null)                         as avg_prob,
               count(*) filter (where hit is not null and n_engines_agree >= 2) as good_n,
               count(*) filter (where hit and n_engines_agree >= 2)             as good_hits
        from b
        group by market
        order by market
    ),
    -- per mercato × giorno (mappa di calore)
    by_market_day as (
        select market, giorno,
               count(*) filter (where hit is not null) as n,
               count(*) filter (where hit)             as hits
        from b
        group by market, giorno
        order by market, giorno
    ),
    -- per lega (classifica)
    by_league as (
        select league_id,
               max(league_name)                                                as league_name,
               count(*) filter (where hit is not null)                          as n,
               count(*) filter (where hit)                                      as hits,
               avg(prob) filter (where hit is not null)                         as avg_prob,
               count(*) filter (where hit is not null and n_engines_agree >= 2) as good_n,
               count(*) filter (where hit and n_engines_agree >= 2)             as good_hits
        from b
        group by league_id
        order by league_id
    )
    select jsonb_build_object(
        'meta', jsonb_build_object(
            'from', p_from,
            'to', p_to,
            'league_id', p_league_id,
            'market', p_market,
            'only_good', p_only_good,
            'generated_at', now(),
            'leagues', coalesce((
                select jsonb_agg(jsonb_build_object('id', league_id, 'name', league_name, 'n', n)
                                 order by league_id)
                from leagues), '[]'::jsonb)
        ),
        'kpi', (
            select jsonb_build_object(
                'n', k.n,
                'hits', k.hits,
                'hit_rate',  case when k.n > 0 then k.hits::numeric / k.n end,
                'avg_prob',  k.avg_prob,
                'calib_gap', case when k.n > 0 then k.hits::numeric / k.n - k.avg_prob end,
                'wilson_low',  case when k.n > 0 then greatest(0,
                    ((k.hits::numeric/k.n) + v_z*v_z/(2*k.n)
                     - v_z*sqrt(((k.hits::numeric/k.n)*(1-k.hits::numeric/k.n) + v_z*v_z/(4*k.n))/k.n))
                    / (1 + v_z*v_z/k.n)) end,
                'wilson_high', case when k.n > 0 then least(1,
                    ((k.hits::numeric/k.n) + v_z*v_z/(2*k.n)
                     + v_z*sqrt(((k.hits::numeric/k.n)*(1-k.hits::numeric/k.n) + v_z*v_z/(4*k.n))/k.n))
                    / (1 + v_z*v_z/k.n)) end,
                'good_n', k.good_n,
                'good_hits', k.good_hits,
                'good_hit_rate', case when k.good_n > 0 then k.good_hits::numeric / k.good_n end
            ) from kpi k
        ),
        'daily', coalesce((
            select jsonb_agg(jsonb_build_object(
                'giorno', giorno, 'n', n, 'hits', hits,
                'hit_rate', case when n > 0 then hits::numeric/n end,
                'avg_prob', avg_prob,
                'good_n', good_n,
                'good_hit_rate', case when good_n > 0 then good_hits::numeric/good_n end
            ) order by giorno) from daily), '[]'::jsonb),
        'by_market', coalesce((
            select jsonb_agg(jsonb_build_object(
                'market', market, 'n', n, 'hits', hits,
                'hit_rate', case when n > 0 then hits::numeric/n end,
                'avg_prob', avg_prob,
                'good_n', good_n,
                'good_hit_rate', case when good_n > 0 then good_hits::numeric/good_n end
            ) order by market) from by_market), '[]'::jsonb),
        'by_market_day', coalesce((
            select jsonb_agg(jsonb_build_object(
                'market', market, 'giorno', giorno, 'n', n,
                'hit_rate', case when n > 0 then hits::numeric/n end
            ) order by market, giorno) from by_market_day), '[]'::jsonb),
        'by_league', coalesce((
            select jsonb_agg(jsonb_build_object(
                'league_id', league_id, 'league_name', league_name,
                'n', n, 'hits', hits,
                'hit_rate', case when n > 0 then hits::numeric/n end,
                'avg_prob', avg_prob,
                'good_n', good_n,
                'good_hit_rate', case when good_n > 0 then good_hits::numeric/good_n end
            ) order by league_id) from by_league), '[]'::jsonb)
    ) into v_out;

    return v_out;
end;
$$;

-- ============================================================================
-- get_direction_report_matches — DRILL: lo scorecard per singola partita.
-- Per ogni fixture (nel filtro): direzioni prese/totali e buone prese/totali.
-- PAGINATO: ritorna { total, offset, limit, rows } così il client può scorrere
-- TUTTE le partite del periodo (anche migliaia) caricandole a blocchi ("carica
-- altre"). total = partite totali nel filtro (ignora limit/offset). Ordinamento
-- DETERMINISTICO (giorno desc, lega, casa, fixture_id) per paginazione stabile.
-- Click su una riga → il client chiama get_direction(fixture_id) per le 7 direzioni.
-- ============================================================================
-- drop di TUTTE le firme storiche (no overload orfani): originale (solo p_limit) e
-- versione paginata (p_limit,p_offset), prima di creare quella attuale (+p_betfair_only).
drop function if exists public.get_direction_report_matches(date,date,bigint,text,boolean,integer);
drop function if exists public.get_direction_report_matches(date,date,bigint,text,boolean,integer,integer);

create or replace function public.get_direction_report_matches(
    p_from        date    default (now() at time zone 'Europe/Rome')::date - 7,
    p_to          date    default (now() at time zone 'Europe/Rome')::date,
    p_league_id   bigint  default null,
    p_market      text    default null,
    p_only_good   boolean default false,
    p_betfair_only boolean default false,
    p_limit       integer default 500,
    p_offset      integer default 0
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
set statement_timeout = '30s'
as $$
declare
    v_from_ts timestamptz;
    v_to_ts   timestamptz;
    v_lim     integer := least(greatest(coalesce(p_limit, 500), 1), 2000);
    v_off     integer := greatest(coalesce(p_offset, 0), 0);
    v_out     jsonb;
begin
    if p_from is null or p_to is null then
        raise exception 'p_from/p_to obbligatori'; end if;
    if p_to < p_from then
        raise exception 'intervallo invalido: p_to (%) < p_from (%)', p_to, p_from; end if;
    if p_market is not null and p_market not in
        ('1x2','ht_1x2','over_1_5','over_2_5','over_3_5','btts','first_half_over_0_5') then
        raise exception 'p_market non canonico: %', p_market; end if;

    v_from_ts := (p_from::timestamp) at time zone 'Europe/Rome';
    v_to_ts   := ((p_to + 1)::timestamp) at time zone 'Europe/Rome';

    with base_all as (
        select distinct on (s.fixture_id, s.market)
               s.fixture_id, s.market, s.selection, s.prob, s.hit, s.n_engines_agree,
               s.league_id, s.league_name, s.home_team, s.away_team,
               s.goals_home, s.goals_away,
               (s.kickoff at time zone 'Europe/Rome')::date as giorno
        from public.analytics_signals s
        where s.engine = 'poisson'
          and s.settled
          and s.kickoff >= v_from_ts
          and s.kickoff <  v_to_ts
          and (p_market is null or s.market = p_market)
          and (not p_betfair_only or s.fixture_id in (select fixture_id from public.engine_signals))
        order by s.fixture_id, s.market, s.prob desc nulls last, s.selection
    ),
    b as (
        select *
        from base_all
        where (p_league_id is null or league_id = p_league_id)
          and (not p_only_good or n_engines_agree >= 2)
    ),
    per_match as (
        select fixture_id,
               max(giorno)        as giorno,
               max(league_id)     as league_id,
               max(league_name)   as league_name,
               max(home_team)     as home_team,
               max(away_team)     as away_team,
               max(goals_home)    as goals_home,
               max(goals_away)    as goals_away,
               count(*) filter (where hit is not null)                          as dir_tot,
               count(*) filter (where hit)                                      as dir_ok,
               count(*) filter (where hit is not null and n_engines_agree >= 2) as good_tot,
               count(*) filter (where hit and n_engines_agree >= 2)             as good_ok
        from b
        group by fixture_id
        having count(*) filter (where hit is not null) > 0
    ),
    page as (
        select * from per_match
        order by giorno desc, league_name nulls last, home_team, fixture_id
        offset v_off limit v_lim
    )
    select jsonb_build_object(
        'total',  (select count(*) from per_match),
        'offset', v_off,
        'limit',  v_lim,
        'rows', coalesce((
            select jsonb_agg(jsonb_build_object(
                'fixture_id', fixture_id,
                'giorno', giorno,
                'league_id', league_id,
                'league_name', league_name,
                'home_team', home_team,
                'away_team', away_team,
                'goals_home', goals_home,
                'goals_away', goals_away,
                'dir_tot', dir_tot,
                'dir_ok', dir_ok,
                'good_tot', good_tot,
                'good_ok', good_ok
            ) order by giorno desc, league_name nulls last, home_team, fixture_id) from page), '[]'::jsonb)
    ) into v_out;

    return v_out;
end;
$$;

-- ============================================================================
-- get_direction_report_fixture — DRILL FINE: le 7 direzioni di UNA partita con
-- esito ✓/✗ (stessa unità del report: argmax Poisson per mercato). Per il
-- pannello "apri partita" del rendiconto. Esito = colonna hit di produzione.
-- ============================================================================
create or replace function public.get_direction_report_fixture(
    p_fixture_id bigint
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
set statement_timeout = '15s'
as $$
declare
    v_out jsonb;
begin
    if p_fixture_id is null then
        raise exception 'p_fixture_id obbligatorio'; end if;

    with dir as (
        select distinct on (s.market)
               s.market, s.selection, s.prob, s.n_engines_agree, s.hit,
               s.goals_home, s.goals_away,
               s.home_team, s.away_team, s.league_name, s.league_id,
               (s.kickoff at time zone 'Europe/Rome')::date as giorno
        from public.analytics_signals s
        where s.engine = 'poisson'
          and s.settled
          and s.fixture_id = p_fixture_id
        order by s.market, s.prob desc nulls last, s.selection
    )
    select jsonb_build_object(
        'fixture_id', p_fixture_id,
        'home_team',  (select max(home_team)  from dir),
        'away_team',  (select max(away_team)  from dir),
        'league_name',(select max(league_name) from dir),
        'giorno',     (select max(giorno)     from dir),
        'goals_home', (select max(goals_home) from dir),
        'goals_away', (select max(goals_away) from dir),
        'rows', coalesce((
            select jsonb_agg(jsonb_build_object(
                'market', market,
                'selection', selection,
                'prob', prob,
                'n_engines_agree', n_engines_agree,
                'hit', hit
            ) order by market) from dir), '[]'::jsonb)
    ) into v_out;

    return v_out;
end;
$$;

-- ============================================================================
-- GRANTS — REVOKE ALL FROM public/anon; EXECUTE solo authenticated + service_role
-- ============================================================================
revoke all on function public.get_direction_report(date,date,bigint,text,boolean,boolean)                 from public;
revoke all on function public.get_direction_report_matches(date,date,bigint,text,boolean,boolean,integer,integer) from public;
revoke all on function public.get_direction_report_fixture(bigint)                                 from public;

grant execute on function public.get_direction_report(date,date,bigint,text,boolean,boolean)                 to authenticated, service_role;
grant execute on function public.get_direction_report_matches(date,date,bigint,text,boolean,boolean,integer,integer) to authenticated, service_role;
grant execute on function public.get_direction_report_fixture(bigint)                                to authenticated, service_role;

revoke execute on function public.get_direction_report(date,date,bigint,text,boolean,boolean)                 from anon;
revoke execute on function public.get_direction_report_matches(date,date,bigint,text,boolean,boolean,integer,integer) from anon;
revoke execute on function public.get_direction_report_fixture(bigint)                                from anon;
