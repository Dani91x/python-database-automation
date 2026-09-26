-- ============================================================================
-- analytics_rpc_veloci_2026-09-26.sql  (IDEMPOTENTE; la applica l'UTENTE dal SQL Editor)
-- ============================================================================
-- PERCHE' (referto AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md par.10 KO2/KO3):
--   il ruolo `authenticated` ha statement_timeout = 8 s (pg_roles). Sul DB vero
--   (istanza piccola: shared_buffers 256 MB, tabelle > 5 GB) le RPC della pagina
--   Analytics leggevano OGNI VOLTA tutte le righe da disco:
--     get_analytics_filters  2 scansioni intere di analytics_signals (278 MB) +
--                            fixture_predictions: 73.322 pagine lette = 4,7 s a DB
--                            quieto, 37,8 s misurati dal banco di fase 3 (sotto carico)
--     get_analytics          35.635 pagine (tutta la tabella)       = 4,0 s / timeout
--     get_analytics_rows     31.534 pagine per 100 righe di drill   = 2,4 s
--     get_decisions_filters  5 scansioni di analytics_decisions     = 3,3 s / timeout
--     get_decisions          1,9 s / timeout
--   Studio Ritardi (get_market_delays mode 'all') e get_league_seasons su leghe grandi
--   (667: 44.534 partite) leggevano ~9.700 pagine sparse di `matches` (2,3 GB) e la
--   distribuzione serie rileggeva la serie per ogni lunghezza (K x N, 25.536 pagine
--   temporanee): 21,8 s (667) e 16,2 s (45) misurati in fase 3.
--   Il timeout NON si alza. Misure prima/dopo: AUDIT_2026-09-25/FIX_B_PAGINE_PRESTAZIONI_2026-09-26.md.
--
-- COSA FA (nessun dato esistente modificato; tabelle NUOVE di solo riepilogo):
--   A. RIEPILOGHI aggiornati dal JOB ESISTENTE (Action predictions_results_backfill,
--      passo "Riepilogo analytics" dopo build/merge/enrich): nessun processo nuovo.
--        analytics_riepilogo_segnali   conteggi esatti (n, somma hit, somma prob) per
--                                      fonte/motore/mercato/selezione/lega/stagione/
--                                      fascia 5 %/concordanza/piazzato
--        analytics_riepilogo_decisioni idem per analytics_decisions
--        analytics_riepilogo_meta      filtri pronti (stesso jsonb delle RPC di prima)
--                                      + orario dell'ultimo aggiornamento
--      refresh_analytics_riepilogo() li ricostruisce in UNA transazione (chi legge vede
--      sempre il riepilogo precedente o il nuovo, mai uno a meta').
--   B. get_analytics / get_decisions: se i filtri attivi sono tutti dimensioni del
--      riepilogo (motore, mercato, selezione, lega, stagione, concordanza, piazzato /
--      logica, stato, motivo scarto) leggono il riepilogo: STESSI numeri (somme esatte,
--      stessa formula di Wilson, stessa divisione numeric di avg()); altrimenti (date,
--      prob min/max, ritardo, frequenza, timing) restano sulla query diretta di prima,
--      invariata. La risposta dichiara 'fonte_dati' ('riepilogo' | 'diretta') e
--      'riepilogo_at' (quando il riepilogo e' stato calcolato).
--   C. get_analytics_filters / get_decisions_filters: leggono i filtri pronti; se il
--      riepilogo non esiste ancora calcolano come prima (funzioni _live, corpo identico).
--   D. get_analytics_rows (drill-down): ogni ramo ordina e limita PRIMA dell'unione,
--      con indici parziali sul kickoff nello stesso ordine (desc nulls last).
--   E. matches: indice di copertura per lo storico-lega (Studio Ritardi, Frequenze,
--      Stagioni) -> index-only scan invece di pagine sparse; get_market_delays: la
--      distribuzione serie diventa due GROUP BY (O(N)) invece di K sottoquery sulla
--      serie (O(K x N)); output identico (verificato col banco PGlite e sul DB vero).
--
-- DOPO L'APPLICAZIONE (fuori da questo file: VACUUM non puo' stare in una transazione):
--   VACUUM (ANALYZE) public.matches;      -- mai fatto dal reset delle statistiche:
--                                         -- il 25 % delle pagine non e' "all-visible"
--   VACUUM (ANALYZE) public.analytics_signals;
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. TABELLE DI RIEPILOGO (nessun accesso diretto: RLS senza policy + revoke;
--    le leggono solo le RPC SECURITY DEFINER)
-- ---------------------------------------------------------------------------
create table if not exists public.analytics_riepilogo_segnali (
    lvl             char(1)  not null,   -- 'G' senza lega (league_* NULL) | 'L' con lega
    fonte           char(1)  not null,   -- 's' analytics_signals | 'a' API (fixture_predictions)
    engine          text,
    market          text,
    selection       text,
    league_id       bigint,
    league_name     text,
    season_year     smallint,
    conf_bin        smallint,            -- least(floor(prob*20),19)*5 (stessa formula del gruppo 'confidence')
    n_engines_agree smallint,
    placed          boolean,
    n               integer  not null,
    hit_sum         numeric  not null,   -- sum(case when hit then 1.0 else 0.0 end)
    prob_sum        numeric  not null    -- sum(prob)
);
create index if not exists idx_ars_lvl_league on public.analytics_riepilogo_segnali (lvl, league_id);

create table if not exists public.analytics_riepilogo_decisioni (
    lvl            char(1)  not null,    -- 'G' | 'L'
    decision_logic text,
    status         text,
    engine         text,
    market         text,
    selection      text,
    reject_filter  text,
    league_id      bigint,
    league_name    text,
    season_year    smallint,
    conf_bin       smallint,             -- NULL se prob NULL (gruppo '(n/d)')
    settled        boolean,
    hit            boolean,
    n              integer  not null,
    stake_sum      numeric,              -- sum(stake)
    pnl_sum        numeric,              -- sum(pnl)
    edge_sum       numeric,  edge_n integer not null,   -- avg(edge) = sum/count dei non NULL
    odds_sum       numeric,  odds_n integer not null,
    prob_sum       numeric,  prob_n integer not null
);
create index if not exists idx_ard_lvl_league on public.analytics_riepilogo_decisioni (lvl, league_id);

create table if not exists public.analytics_riepilogo_meta (
    chiave        text primary key,      -- 'segnali' | 'decisioni' | 'filtri_analytics' | 'filtri_decisioni'
    payload       jsonb,
    righe         integer,
    durata_ms     integer,
    aggiornato_at timestamptz not null default now()
);

alter table public.analytics_riepilogo_segnali   enable row level security;
alter table public.analytics_riepilogo_decisioni enable row level security;
alter table public.analytics_riepilogo_meta      enable row level security;
revoke all on table public.analytics_riepilogo_segnali   from public, anon, authenticated;
revoke all on table public.analytics_riepilogo_decisioni from public, anon, authenticated;
revoke all on table public.analytics_riepilogo_meta      from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 1. INDICI
-- ---------------------------------------------------------------------------
-- 1a. storico-lega di `matches` (get_market_delays, get_market_frequency,
--     get_league_seasons): stessa condizione di stato delle RPC -> index-only scan.
create index if not exists idx_matches_storico_lega_cover
    on public.matches (league_id, fixture_date, fixture_id)
    include (season_year, status_short, fulltime_home, fulltime_away, goals_home, goals_away,
             halftime_home, halftime_away, home_team_name, away_team_name)
    where status_short in ('FT','AET','PEN');
-- 1b. drill-down Analytics: ultime righe per kickoff, nello stesso ordine della RPC
create index if not exists idx_as_drill_kickoff
    on public.analytics_signals (kickoff desc nulls last)
    where settled and hit is not null and prob is not null;
create index if not exists idx_fp_drill_fixture_date
    on public.fixture_predictions (fixture_date desc nulls last)
    where result_outcome is not null;
-- 1c. autovacuum di matches (mai passato: soglia 20 % di 1,5 M righe): visibility map fresca
alter table public.matches set (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.01);

-- ---------------------------------------------------------------------------
-- 2. FILTRI "LIVE" (corpo IDENTICO alle RPC di prima: servono al refresh e
--    come ripiego quando il riepilogo non esiste ancora)
-- ---------------------------------------------------------------------------
create or replace function public._analytics_filters_live()
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

create or replace function public._decisions_filters_live()
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

-- ---------------------------------------------------------------------------
-- 3. REFRESH (lo chiama il job esistente con la service role; 600 s come
--    refresh_analytics_bets). Una transazione: chi legge non vede mai meta' riepilogo.
-- ---------------------------------------------------------------------------
create or replace function public.refresh_analytics_riepilogo()
returns jsonb
language plpgsql
volatile
security definer
set search_path = public, pg_temp
set statement_timeout = '600s'
as $$
declare
    v_t0   timestamptz := clock_timestamp();
    v_t    timestamptz;
    v_ns   integer;
    v_nd   integer;
    v_fa   jsonb;
    v_fd   jsonb;
begin
    -- un solo refresh alla volta (due job sovrapposti non si mescolano)
    perform pg_advisory_xact_lock(hashtext('refresh_analytics_riepilogo'));

    -- SEGNALI: livello L (con lega) dalle righe, livello G sommando L (somme esatte)
    delete from analytics_riepilogo_segnali where true;   -- WHERE: pg-safeupdate (sessioni PostgREST)
    insert into analytics_riepilogo_segnali
        (lvl, fonte, engine, market, selection, league_id, league_name, season_year,
         conf_bin, n_engines_agree, placed, n, hit_sum, prob_sum)
    select 'L', b.fonte, b.engine, b.market, b.selection, b.league_id, b.league_name, b.season_year,
           b.conf_bin, b.n_engines_agree, b.placed, count(*)::int, sum(b.hv), sum(b.prob)
    from (
        select 's'::char(1) as fonte, s.engine, s.market, s.selection, s.league_id::bigint as league_id,
               s.league_name, s.season_year::smallint as season_year,
               (least(floor(s.prob*20),19)*5)::smallint as conf_bin,
               s.n_engines_agree, s.placed, s.prob,
               case when s.hit then 1.0 else 0.0 end as hv
        from analytics_signals s
        where s.settled and s.hit is not null and s.prob is not null
        union all
        select 'a'::char(1), 'api'::text, '1x2'::text, v.sel, fp.league_id::bigint, fp.league_name,
               fp.season_year::smallint,
               (least(floor(((v.pct/100.0)::numeric)*20),19)*5)::smallint,
               null::smallint, null::boolean, (v.pct/100.0)::numeric,
               case when (fp.result_outcome = v.sel) then 1.0 else 0.0 end
        from fixture_predictions fp cross join lateral (values
             ('H',fp.percent_home),('D',fp.percent_draw),('A',fp.percent_away)) v(sel,pct)
        where fp.result_outcome is not null and v.pct is not null
    ) b
    group by b.fonte, b.engine, b.market, b.selection, b.league_id, b.league_name, b.season_year,
             b.conf_bin, b.n_engines_agree, b.placed;

    insert into analytics_riepilogo_segnali
        (lvl, fonte, engine, market, selection, league_id, league_name, season_year,
         conf_bin, n_engines_agree, placed, n, hit_sum, prob_sum)
    select 'G', fonte, engine, market, selection, null, null, season_year,
           conf_bin, n_engines_agree, placed, sum(n)::int, sum(hit_sum), sum(prob_sum)
    from analytics_riepilogo_segnali where lvl = 'L'
    group by fonte, engine, market, selection, season_year, conf_bin, n_engines_agree, placed;
    select count(*) into v_ns from analytics_riepilogo_segnali;

    -- DECISIONI
    delete from analytics_riepilogo_decisioni where true;
    insert into analytics_riepilogo_decisioni
        (lvl, decision_logic, status, engine, market, selection, reject_filter, league_id, league_name,
         season_year, conf_bin, settled, hit, n, stake_sum, pnl_sum, edge_sum, edge_n, odds_sum, odds_n,
         prob_sum, prob_n)
    select 'L', d.decision_logic, d.status, d.engine, d.market, d.selection, d.reject_filter,
           d.league_id::bigint, d.league_name, d.season_year::smallint,
           case when d.prob is null then null else (least(floor(d.prob*20),19)*5)::smallint end,
           d.settled, d.hit, count(*)::int, sum(d.stake), sum(d.pnl),
           sum(d.edge), count(d.edge)::int, sum(d.odds), count(d.odds)::int, sum(d.prob), count(d.prob)::int
    from analytics_decisions d
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13;

    insert into analytics_riepilogo_decisioni
        (lvl, decision_logic, status, engine, market, selection, reject_filter, league_id, league_name,
         season_year, conf_bin, settled, hit, n, stake_sum, pnl_sum, edge_sum, edge_n, odds_sum, odds_n,
         prob_sum, prob_n)
    select 'G', decision_logic, status, engine, market, selection, reject_filter, null, null,
           season_year, conf_bin, settled, hit, sum(n)::int, sum(stake_sum), sum(pnl_sum),
           sum(edge_sum), sum(edge_n)::int, sum(odds_sum), sum(odds_n)::int, sum(prob_sum), sum(prob_n)::int
    from analytics_riepilogo_decisioni where lvl = 'L'
    group by decision_logic, status, engine, market, selection, reject_filter, season_year, conf_bin, settled, hit;
    select count(*) into v_nd from analytics_riepilogo_decisioni;

    -- FILTRI pronti (stesso jsonb delle RPC di prima)
    v_fa := public._analytics_filters_live();
    v_fd := public._decisions_filters_live();

    v_t := clock_timestamp();
    insert into analytics_riepilogo_meta (chiave, payload, righe, durata_ms, aggiornato_at) values
        ('segnali',          null, v_ns, (extract(epoch from (v_t - v_t0))*1000)::int, v_t),
        ('decisioni',        null, v_nd, (extract(epoch from (v_t - v_t0))*1000)::int, v_t),
        ('filtri_analytics', v_fa, null, (extract(epoch from (v_t - v_t0))*1000)::int, v_t),
        ('filtri_decisioni', v_fd, null, (extract(epoch from (v_t - v_t0))*1000)::int, v_t)
    on conflict (chiave) do update
        set payload = excluded.payload, righe = excluded.righe,
            durata_ms = excluded.durata_ms, aggiornato_at = excluded.aggiornato_at;

    return jsonb_build_object('righe_segnali', v_ns, 'righe_decisioni', v_nd,
                              'durata_ms', (extract(epoch from (v_t - v_t0))*1000)::int,
                              'aggiornato_at', v_t);
end;
$$;

-- ---------------------------------------------------------------------------
-- 4. FILTRI: dal riepilogo (istantaneo) o, se manca, calcolo diretto come prima
-- ---------------------------------------------------------------------------
create or replace function public.get_analytics_filters()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select coalesce(
        (select m.payload || jsonb_build_object('fonte_dati', 'riepilogo', 'riepilogo_at', m.aggiornato_at)
           from analytics_riepilogo_meta m
          where m.chiave = 'filtri_analytics' and m.payload is not null),
        public._analytics_filters_live() || jsonb_build_object('fonte_dati', 'diretta', 'riepilogo_at', null)
    );
$$;

create or replace function public.get_decisions_filters()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select coalesce(
        (select m.payload || jsonb_build_object('fonte_dati', 'riepilogo', 'riepilogo_at', m.aggiornato_at)
           from analytics_riepilogo_meta m
          where m.chiave = 'filtri_decisioni' and m.payload is not null),
        public._decisions_filters_live() || jsonb_build_object('fonte_dati', 'diretta', 'riepilogo_at', null)
    );
$$;

-- ---------------------------------------------------------------------------
-- 5. get_analytics: ramo RIEPILOGO + ramo DIRETTO (quest'ultimo invariato)
-- ---------------------------------------------------------------------------
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
    p_delay_min     integer default null,    -- ritardo attuale minimo del mercato (solo motori in tabella)
    p_freq_dev      text    default null,    -- 'pos'|'neg': freq attuale sopra/sotto baseline
    p_timing_max    integer default null,    -- primo gol entro il minuto X (solo motori in tabella)
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
    v_riep_at timestamptz;  -- orario del riepilogo (NULL = riepilogo assente)
    v_lvl    text;
    f_r      text := '';    -- filtri sul riepilogo (alias r)
    v_wilson text;
begin
    -- validazione (whitelist -> errore rumoroso, mai output silenzioso sbagliato)
    if p_engine is not null and p_engine not in ('poisson','ml','api','tacticai') then
        raise exception 'p_engine invalido: %', p_engine; end if;
    if p_group_by not in ('overall','engine','market','selection','league','confidence') then
        raise exception 'p_group_by invalido: %', p_group_by; end if;
    if p_prob_min is not null and (p_prob_min < 0 or p_prob_min > 1) then
        raise exception 'p_prob_min fuori [0,1]: %', p_prob_min; end if;
    if p_prob_max is not null and (p_prob_max < 0 or p_prob_max > 1) then
        raise exception 'p_prob_max fuori [0,1]: %', p_prob_max; end if;
    if p_freq_dev is not null and p_freq_dev not in ('pos','neg') then
        raise exception 'p_freq_dev invalido (pos|neg): %', p_freq_dev; end if;

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
               and (p_min_agree is null)                    -- l'API non ha concordanza
               and (p_delay_min is null)                    -- l'API non ha snapshot ritardo
               and (p_freq_dev is null)                     -- l'API non ha snapshot frequenza
               and (p_timing_max is null);                  -- l'API non ha timing gol

    -- stessa formula di Wilson per entrambi i rami (agg: grp, n, hits, hit_rate, avg_prob)
    v_wilson :=
        ' wilson as (select grp, n, hits, round(hit_rate,4) hit_rate, round(avg_prob,4) avg_prob,'
     || '   round(((hit_rate + ' || v_z || '*' || v_z || '/(2*n))/(1+' || v_z || '*' || v_z || '/n))'
     || '     - (' || v_z || '*sqrt((hit_rate*(1-hit_rate)+' || v_z || '*' || v_z || '/(4*n))/n)/(1+' || v_z || '*' || v_z || '/n)),4) wilson_low,'
     || '   round(((hit_rate + ' || v_z || '*' || v_z || '/(2*n))/(1+' || v_z || '*' || v_z || '/n))'
     || '     + (' || v_z || '*sqrt((hit_rate*(1-hit_rate)+' || v_z || '*' || v_z || '/(4*n))/n)/(1+' || v_z || '*' || v_z || '/n)),4) wilson_high,'
     || '   round(hit_rate-avg_prob,4) calib_gap from agg)'
     || ' select coalesce(jsonb_agg(to_jsonb(w) order by w.n desc, w.grp),''[]''::jsonb) from wilson w';

    -- ================= RAMO RIEPILOGO =================
    -- solo se TUTTI i filtri attivi sono dimensioni del riepilogo
    if p_prob_min is null and p_prob_max is null and p_date_from is null and p_date_to is null
       and p_delay_min is null and p_freq_dev is null and p_timing_max is null then
        select m.aggiornato_at into v_riep_at from analytics_riepilogo_meta m where m.chiave = 'segnali';
    end if;
    if v_riep_at is not null then
        if not inc_as and not inc_api then
            return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', '[]'::jsonb,
                                      'fonte_dati', 'riepilogo', 'riepilogo_at', v_riep_at);
        end if;
        v_lvl := case when p_league_id is not null or v_group = 'league' then 'L' else 'G' end;
        if not inc_as  then f_r := f_r || ' and r.fonte = ''a'''; end if;
        if not inc_api then f_r := f_r || ' and r.fonte = ''s'''; end if;
        if p_engine is not null and p_engine <> 'api' then
            f_r := f_r || format(' and r.engine = %L', p_engine); end if;
        if p_market is not null then
            f_r := f_r || format(' and r.market = %L', p_market); end if;
        if p_selection is not null then
            f_r := f_r || format(' and r.selection = %L', p_selection); end if;
        if p_league_id is not null then
            f_r := f_r || format(' and r.league_id = %s', p_league_id); end if;
        if p_season_year is not null then
            f_r := f_r || format(' and r.season_year = %s', p_season_year); end if;
        if p_min_agree is not null then
            f_r := f_r || format(' and r.n_engines_agree >= %s', p_min_agree); end if;
        if p_placed_only then
            f_r := f_r || ' and r.placed = true'; end if;

        v_sql :=
            'with g as (select '
         || case v_group
                when 'engine'     then 'r.engine'
                when 'market'     then 'r.market'
                when 'selection'  then 'r.market || '' / '' || r.selection'
                when 'league'     then 'coalesce(r.league_name, r.league_id::text)'
                when 'confidence' then 'r.conf_bin::int::text || ''-'' || (r.conf_bin+5)::int::text || ''%'''
                else '''overall'''
            end
         || ' as grp, r.n, r.hit_sum, r.prob_sum from analytics_riepilogo_segnali r'
         || ' where r.lvl = ' || quote_literal(v_lvl) || f_r || '),'
         || ' agg as (select grp, sum(n)::int n, sum(hit_sum)::int hits,'
         || '   sum(hit_sum) / sum(n)::numeric hit_rate, sum(prob_sum) / sum(n)::numeric avg_prob'
         || '   from g group by grp having sum(n)>0),'
         || v_wilson;
        execute v_sql into v_rows;
        return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', coalesce(v_rows,'[]'::jsonb),
                                  'fonte_dati', 'riepilogo', 'riepilogo_at', v_riep_at);
    end if;

    -- ================= RAMO DIRETTO (invariato) =================
    -- FILTRI PUSHED-DOWN: solo quelli attivi -> il planner usa gli indici.
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
    -- filtri SNAPSHOT (solo analytics_signals; l'API non li ha -> gia' esclusa via inc_api)
    if p_delay_min is not null then
        f_as := f_as || format(' and s.delay_current >= %s', p_delay_min); end if;
    if p_freq_dev = 'pos' then
        f_as := f_as || ' and s.freq_deviation > 0'; end if;
    if p_freq_dev = 'neg' then
        f_as := f_as || ' and s.freq_deviation < 0'; end if;
    if p_timing_max is not null then
        f_as := f_as || format(' and s.first_goal_minute <= %s', p_timing_max); end if;

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
        return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', '[]'::jsonb,
                                  'fonte_dati', 'diretta', 'riepilogo_at', null);
    end if;

    v_sql :=
        'with base(engine,league_id,league_name,season_year,kickoff,market,selection,prob,hit) as (' || v_base || '),'
     || ' g as (select ' || v_grp || ' as grp, hit, prob from base b where b.prob is not null and b.hit is not null),'
     || ' agg as (select grp, count(*)::int n, sum(case when hit then 1 else 0 end)::int hits,'
     || '   avg(case when hit then 1.0 else 0.0 end) hit_rate, avg(prob) avg_prob'
     || '   from g group by grp having count(*)>0),'
     || v_wilson;

    execute v_sql into v_rows;
    return jsonb_build_object('group_by', v_group, 'z', v_z, 'groups', coalesce(v_rows,'[]'::jsonb),
                              'fonte_dati', 'diretta', 'riepilogo_at', null);
end;
$$;

-- ---------------------------------------------------------------------------
-- 6. get_decisions: ramo RIEPILOGO (senza filtri di data) + ramo DIRETTO invariato
-- ---------------------------------------------------------------------------
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
    v_riep_at timestamptz; v_lvl text; v_out text;
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

    -- parte finale comune ai due rami (agg -> out -> jsonb)
    v_out :=
        ' out as (select grp, n, placed, rejected, no_signal, settled_placed, hits,'
     || '   round(stake,2) stake, round(pnl,2) pnl,'
     || '   case when settled_placed>0 then round(hits::numeric/settled_placed,4) end hit_rate,'
     || '   case when stake>0 then round(pnl/stake,4) end roi,'
     || '   round(avg_edge,4) avg_edge, round(avg_odds,3) avg_odds, round(avg_prob,4) avg_prob'
     || '   from agg)'
     || ' select coalesce(jsonb_agg(to_jsonb(o) order by o.n desc, o.grp),''[]''::jsonb) from out o';

    -- ================= RAMO RIEPILOGO (nessun filtro di data) =================
    if p_date_from is null and p_date_to is null then
        select m.aggiornato_at into v_riep_at from analytics_riepilogo_meta m where m.chiave = 'decisioni';
    end if;
    if v_riep_at is not null then
        v_lvl := case when p_league_id is not null or p_group_by = 'league' then 'L' else 'G' end;
        -- stesse espressioni di gruppo sul riepilogo: la fascia e' gia' in conf_bin
        v_sql :=
            'with f as (select '
         || case p_group_by
                when 'confidence' then 'case when d.conf_bin is null then ''(n/d)'' else d.conf_bin::int::text || ''-'' || (d.conf_bin+5)::int::text || ''%'' end'
                else v_grp
            end
         || ' as grp, d.status, d.settled, d.hit, d.n, d.stake_sum, d.pnl_sum,'
         || ' d.edge_sum, d.edge_n, d.odds_sum, d.odds_n, d.prob_sum, d.prob_n'
         || '   from analytics_riepilogo_decisioni d where d.lvl = ' || quote_literal(v_lvl) || w || '),'
         || ' agg as (select grp,'
         || '   sum(n)::int n,'
         || '   coalesce(sum(n) filter (where status=''PLACED''),0)::int placed,'
         || '   coalesce(sum(n) filter (where status=''REJECTED''),0)::int rejected,'
         || '   coalesce(sum(n) filter (where status=''NO_SIGNAL''),0)::int no_signal,'
         || '   coalesce(sum(n) filter (where status=''PLACED'' and settled and hit is not null),0)::int settled_placed,'
         || '   coalesce(sum(n) filter (where status=''PLACED'' and settled and hit),0)::int hits,'
         || '   coalesce(sum(stake_sum) filter (where status=''PLACED'' and settled),0) stake,'
         || '   coalesce(sum(pnl_sum)   filter (where status=''PLACED'' and settled),0) pnl,'
         || '   sum(edge_sum) / nullif(sum(edge_n),0)::numeric avg_edge,'
         || '   sum(odds_sum) / nullif(sum(odds_n),0)::numeric avg_odds,'
         || '   sum(prob_sum) / nullif(sum(prob_n),0)::numeric avg_prob'
         || '   from f group by grp having sum(n)>0),'
         || v_out;
        execute v_sql into v_rows;
        return jsonb_build_object('group_by', p_group_by, 'groups', coalesce(v_rows,'[]'::jsonb),
                                  'fonte_dati', 'riepilogo', 'riepilogo_at', v_riep_at);
    end if;

    -- ================= RAMO DIRETTO (invariato) =================
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
     -- ROI/pnl SOLO su piazzate SETTLATE (stessa popolazione di hit_rate): e' il
     -- rendimento REALIZZATO, non diluito dalle bet ancora aperte.
     || '   coalesce(sum(stake) filter (where status=''PLACED'' and settled),0) stake,'
     || '   coalesce(sum(pnl)   filter (where status=''PLACED'' and settled),0) pnl,'
     -- medie sull'intero gruppo (popolazione coerente; avg ignora i NULL -> avg_odds
     -- e' di fatto sulle piazzate, le scartate non hanno quota).
     || '   avg(edge) avg_edge,'
     || '   avg(odds) avg_odds,'
     || '   avg(prob) avg_prob'
     || '   from f group by grp having count(*)>0),'
     || v_out;
    execute v_sql into v_rows;
    return jsonb_build_object('group_by', p_group_by, 'groups', coalesce(v_rows,'[]'::jsonb),
                              'fonte_dati', 'diretta', 'riepilogo_at', null);
end;
$$;

-- ---------------------------------------------------------------------------
-- 7. get_analytics_rows (drill-down): ordina e limita DENTRO ogni ramo
--    (indici parziali 1b), poi l'ordine/limite/offset finale come prima.
-- ---------------------------------------------------------------------------
create or replace function public.get_analytics_rows(
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
    p_delay_min     integer default null,
    p_freq_dev      text    default null,
    p_timing_max    integer default null,
    p_conf_bin      integer default null,    -- drill di una fascia confidenza: bin start % (0,5,..,95)
    p_limit         integer default 100,
    p_offset        integer default 0
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    f_as text := ''; f_api text := ''; inc_as boolean; inc_api boolean;
    v_base text; v_sql text; v_rows jsonb; v_lim int; v_off int; v_top int;
begin
    if p_engine is not null and p_engine not in ('poisson','ml','api','tacticai') then
        raise exception 'p_engine invalido: %', p_engine; end if;
    -- coerenza con get_analytics: prob in [0,1] (evita drill silenziosamente vuoto)
    if p_prob_min is not null and (p_prob_min < 0 or p_prob_min > 1) then
        raise exception 'p_prob_min fuori [0,1]: %', p_prob_min; end if;
    if p_prob_max is not null and (p_prob_max < 0 or p_prob_max > 1) then
        raise exception 'p_prob_max fuori [0,1]: %', p_prob_max; end if;
    if p_freq_dev is not null and p_freq_dev not in ('pos','neg') then
        raise exception 'p_freq_dev invalido: %', p_freq_dev; end if;
    v_lim := least(greatest(coalesce(p_limit,100), 1), 500);   -- cap a 500
    v_off := greatest(coalesce(p_offset,0),0);
    v_top := v_lim + v_off;   -- ogni ramo basta che dia le sue prime v_top righe

    inc_as  := (p_engine is null or p_engine <> 'api');
    inc_api := (p_engine is null or p_engine = 'api')
               and (p_market is null or p_market = '1x2')
               and (p_placed_only is false) and (p_min_agree is null)
               and (p_delay_min is null) and (p_freq_dev is null) and (p_timing_max is null);

    if p_engine is not null and p_engine <> 'api' then f_as := f_as || format(' and s.engine = %L', p_engine); end if;
    if p_market is not null then f_as := f_as || format(' and s.market = %L', p_market); end if;
    if p_selection is not null then
        f_as := f_as || format(' and s.selection = %L', p_selection);
        f_api := f_api || format(' and v.sel = %L', p_selection); end if;
    if p_league_id is not null then
        f_as := f_as || format(' and s.league_id = %s', p_league_id);
        f_api := f_api || format(' and fp.league_id = %s', p_league_id); end if;
    if p_season_year is not null then
        f_as := f_as || format(' and s.season_year = %s', p_season_year);
        f_api := f_api || format(' and fp.season_year = %s', p_season_year); end if;
    if p_prob_min is not null then
        f_as := f_as || format(' and s.prob >= %s', p_prob_min);
        f_api := f_api || format(' and (v.pct/100.0) >= %s', p_prob_min); end if;
    if p_prob_max is not null then
        f_as := f_as || format(' and s.prob <= %s', p_prob_max);
        f_api := f_api || format(' and (v.pct/100.0) <= %s', p_prob_max); end if;
    if p_min_agree is not null then f_as := f_as || format(' and s.n_engines_agree >= %s', p_min_agree); end if;
    if p_placed_only then f_as := f_as || ' and s.placed = true'; end if;
    if p_date_from is not null then
        f_as := f_as || format(' and s.kickoff >= %L', p_date_from);
        f_api := f_api || format(' and fp.fixture_date >= %L', p_date_from); end if;
    if p_date_to is not null then
        f_as := f_as || format(' and s.kickoff <= %L', p_date_to);
        f_api := f_api || format(' and fp.fixture_date <= %L', p_date_to); end if;
    if p_delay_min is not null then f_as := f_as || format(' and s.delay_current >= %s', p_delay_min); end if;
    if p_freq_dev = 'pos' then f_as := f_as || ' and s.freq_deviation > 0'; end if;
    if p_freq_dev = 'neg' then f_as := f_as || ' and s.freq_deviation < 0'; end if;
    if p_timing_max is not null then f_as := f_as || format(' and s.first_goal_minute <= %s', p_timing_max); end if;
    -- drill di una fascia di confidenza: STESSA formula del bin aggregato di
    -- get_analytics (semi-aperto [X,X+5)), per non mostrare righe del bin sbagliato.
    if p_conf_bin is not null then
        f_as  := f_as  || format(' and least(floor(s.prob*20),19)*5 = %s', p_conf_bin);
        f_api := f_api || format(' and least(floor((v.pct/100.0)*20),19)*5 = %s', p_conf_bin);
    end if;

    v_base := '';
    if inc_as then
        v_base := '(select s.engine, s.league_name, s.home_team, s.away_team, s.kickoff, s.market,'
               || ' s.selection, s.prob, s.hit, s.result, s.freq_baseline, s.freq_current, s.freq_deviation,'
               || ' s.delay_current, s.first_goal_minute from analytics_signals s'
               || ' where s.settled and s.hit is not null and s.prob is not null' || f_as
               || ' order by s.kickoff desc nulls last limit ' || v_top || ')';
    end if;
    if inc_api then
        if v_base <> '' then v_base := v_base || ' union all '; end if;
        v_base := v_base
               || '(select ''api''::text, fp.league_name, fp.home_team_name, fp.away_team_name, fp.fixture_date,'
               || ' ''1x2''::text, v.sel, (v.pct/100.0)::numeric, (fp.result_outcome = v.sel),'
               || ' case when fp.result_outcome = v.sel then ''WON'' else ''LOST'' end,'
               || ' null::numeric, null::numeric, null::numeric, null::int, null::smallint'
               || ' from fixture_predictions fp cross join lateral (values'
               || ' (''H'',fp.percent_home),(''D'',fp.percent_draw),(''A'',fp.percent_away)) v(sel,pct)'
               || ' where fp.result_outcome is not null and v.pct is not null' || f_api
               || ' order by fp.fixture_date desc nulls last limit ' || v_top || ')';
    end if;
    if v_base = '' then
        return jsonb_build_object('rows','[]'::jsonb,'limit',v_lim,'offset',v_off);
    end if;

    v_sql := 'with base(engine,league_name,home_team,away_team,kickoff,market,selection,prob,hit,result,'
          || 'freq_baseline,freq_current,freq_deviation,delay_current,first_goal_minute) as (' || v_base || ')'
          || ' select coalesce(jsonb_agg(to_jsonb(b) order by b.kickoff desc nulls last),''[]''::jsonb)'
          || ' from (select * from base order by kickoff desc nulls last limit ' || v_lim
          || ' offset ' || v_off || ') b';
    execute v_sql into v_rows;
    return jsonb_build_object('rows', coalesce(v_rows,'[]'::jsonb), 'limit', v_lim, 'offset', v_off);
end;
$$;

-- ---------------------------------------------------------------------------
-- 8. GRANT delle funzioni NUOVE (le create or replace di sopra conservano i
--    permessi gia' dati: get_* restano authenticated + service_role)
-- ---------------------------------------------------------------------------
revoke all on function public.refresh_analytics_riepilogo() from public, anon, authenticated;
grant execute on function public.refresh_analytics_riepilogo() to service_role;
revoke all on function public._analytics_filters_live() from public, anon, authenticated;
revoke all on function public._decisions_filters_live() from public, anon, authenticated;
grant execute on function public._analytics_filters_live() to service_role;
grant execute on function public._decisions_filters_live() to service_role;

-- ---------------------------------------------------------------------------
-- 10. get_market_delays (Studio Ritardi + ritardo della Direzione): STESSA firma,
--     STESSO output; solo la distribuzione serie riscritta (vedi commento nel corpo).
--     Corpo copiato da migrations/market_delays_ht_2026-09-25.sql (= DB vero, md5
--     del corpo verificato il 26/09) con la sola sostituzione del blocco distrib.
--     get_league_seasons / get_market_frequency: invariate, usano l'indice 1a.
-- ---------------------------------------------------------------------------
create or replace function public.get_market_delays(
    p_league_id   integer,
    p_market      text,
    p_target      text    default null,    -- sge: 'N'; over/under/ovpt: linea '2.5'; re: 'h-a'
    p_mode        text    default 'all',   -- 'all' | 'last_n' | 'season'
    p_last_n      integer default null,
    p_season_year integer default null
) returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_result   jsonb;
    v_line     numeric;
    v_sge      integer;
    v_re_h     integer;
    v_re_a     integer;
    v_uses_ht  boolean;
begin
    -- ------------------------------------------------------------------
    -- VALIDAZIONE INPUT (whitelist: input invalido = errore rumoroso)
    -- ------------------------------------------------------------------
    if p_league_id is null or p_league_id <= 0 then
        raise exception 'p_league_id non valido: %', p_league_id;
    end if;
    if p_mode not in ('all','last_n','season') then
        raise exception 'p_mode invalido: %', p_mode;
    end if;
    if p_mode = 'last_n' and (p_last_n is null or p_last_n < 10 or p_last_n > 20000) then
        raise exception 'p_last_n fuori range [10,20000]: %', p_last_n;
    end if;
    if p_mode = 'season' and p_season_year is null then
        raise exception 'p_season_year obbligatorio con p_mode=season';
    end if;

    -- Mercati che usano il primo tempo (flag esposto a meta per l'avviso copertura HT)
    -- (e, dal 25/09, per la regola: su questi mercati le righe senza HT sono escluse)
    v_uses_ht := p_market in ('ovpt','unpt','ggpt','ggst','pf1x','pf2x','pfx1','pfx2',
                              'pt1','ptx','pt2');

    -- Validazione mercato + parsing target
    if p_market = 're' then
        if p_target !~ '^[0-9]+-[0-9]+$' then
            raise exception 'target re invalido (atteso "h-a"): %', p_target; end if;
        v_re_h := split_part(p_target,'-',1)::int;
        v_re_a := split_part(p_target,'-',2)::int;
        if v_re_h > 30 or v_re_a > 30 then
            raise exception 'target re fuori range (max 30-30): %', p_target; end if;
    elsif p_market = 'sge' then
        if p_target !~ '^[0-9]+$' then
            raise exception 'target sge invalido (atteso intero): %', p_target; end if;
        v_sge := p_target::int;
    elsif p_market in ('over','under','ovpt','unpt') then
        if p_target !~ '^[0-9]+(\.[0-9]+)?$' then
            raise exception 'linea % invalida: %', p_market, p_target; end if;
        v_line := p_target::numeric;
    elsif p_market in ('ggpt','ggst','pf1x','pf2x','pfx1','pfx2','x','ggov25',
                       '1','2','gg','ng','pt1','ptx','pt2') then
        null;  -- nessun parametro
    else
        raise exception 'mercato non supportato: %', p_market;
    end if;

    -- ------------------------------------------------------------------
    -- PIPELINE
    -- ------------------------------------------------------------------
    with scope as (
        -- DATI MATCH: storico-lega. 'all' = tutto; 'season' = una stagione;
        -- 'last_n' = ultime N settlate. Riportato in ordine cronologico asc.
        select fixture_id, fixture_date, home_team_name, away_team_name,
               case when fulltime_home is not null then fulltime_home
                    when status_short = 'FT'       then goals_home end as h,   -- GC
               case when fulltime_away is not null then fulltime_away
                    when status_short = 'FT'       then goals_away end as a,   -- GA
               halftime_home as hh,   -- GCFH
               halftime_away as ha    -- GAFH
        from matches
        where league_id = p_league_id
          and status_short in ('FT','AET','PEN')
          and (p_mode <> 'season' or season_year = p_season_year)
        order by fixture_date desc, fixture_id desc
        limit case when p_mode = 'last_n' then p_last_n else null end
    ),
    outcomes as (
        -- Un evento = una riga di DATI MATCH, cioe' un risultato settlato con
        -- punteggio 90' noto (GC/GA = h/a non null).
        -- REGOLA HT (25/09): sui mercati che usano il primo tempo una riga senza
        -- halftime_* NON e' un evento (outcome NULL -> esclusa dalla serie), come in
        -- get_market_frequency. Prima il foglio la trattava come 0-0 (coalesce).
        -- GCSH/GASH (2 tempo) DERIVATI: GC-GCFH, GA-GAFH (come colonne L/M).
        select s.fixture_id, s.fixture_date, s.home_team_name, s.away_team_name,
               s.h, s.a, s.hh, s.ha,
            case
            when (s.h is null or s.a is null) then null   -- non e' un evento DATI MATCH
            when v_uses_ht and (s.hh is null or s.ha is null) then null  -- HT ignoto: escluso
            else
              case p_market
                when 're'    then (s.h = v_re_h and s.a = v_re_a)::int
                when 'sge'   then ((s.h + s.a) = v_sge)::int
                when 'over'  then ((s.h + s.a)::numeric > v_line)::int
                when 'under' then ((s.h + s.a)::numeric < v_line)::int
                when 'ovpt'  then ((s.hh + s.ha)::numeric > v_line)::int
                when 'unpt'  then ((s.hh + s.ha)::numeric < v_line)::int
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
               -- righe con punteggio 90' noto ma senza HT: sui mercati HT sono
               -- quelle ESCLUSE dalla regola (0 sui mercati FT, che non le escludono)
               (count(*) filter (where v_uses_ht and h is not null and a is not null
                                   and (hh is null or ha is null)))::int as n_ht_missing,
               round(100*avg((hh is not null and ha is not null)::int),1) as ht_cov,
               min(fixture_date)                                          as d_from,
               max(fixture_date)                                          as d_to
        from scope
    ),
    ordered as (
        -- DATI MATCH in ordine cronologico (dal piu' vecchio al piu' recente):
        -- una riga per evento settlato. idx = colonna EVENTO (progressivo).
        select o.fixture_id, o.fixture_date, o.home_team_name, o.away_team_name,
               o.h as gc, o.a as ga, o.hh as gcfh, o.ha as gafh, o.outcome,
               row_number() over (order by o.fixture_date asc, o.fixture_id asc) as idx
        from outcomes o
        where o.outcome is not null
    ),
    series_rows as (
        -- RIT(i) = i - last_hit(i)  ;  last_hit running-max degli idx dove out=1
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
        -- Ogni occorrenza con la lunghezza della serie chiusa (SUC = gap-1)
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
               -- media_rit a PIENA precisione: INT()/run la usano cosi' come C6
               -- nel foglio; l'arrotondamento avviene solo in output.
               (select avg(rit_val)::numeric
                  from rit where rit_val <> 0)                                as media_rit
    ),
    derived as (
        select b.*,
               case when b.n_occ > 0 then round(b.n_occ::numeric / b.n_eff, 6) end as frequency,
               case when b.n_occ > 0 then round(b.n_eff::numeric / b.n_occ, 6) end as media_storica
        from base b
    ),
    -- distribuzione F/G/H del foglio, su tutto l'asse valori 0..max:
    --   occ_suc = COUNTIF(SUC, k)  (serie durate k)
    --   cnt_rit = COUNTIF(RIT, k)  (righe con ritardo corrente k)
    -- 26/09 (prestazioni): due GROUP BY (una passata ciascuno) invece di due
    -- sottoquery correlate per OGNI lunghezza k (K x N). Stesso risultato: 0 dove
    -- nessuna serie/riga ha quella lunghezza (count(*)::int = 0 prima, coalesce 0 ora).
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
    -- ultime 10 serie chiuse (piu' recenti), in ordine cronologico
    last10 as (
        select suc, hit_idx
        from hits order by hit_idx desc limit 10
    ),
    -- STORICO SERIE (colonne BB/BC/BD/BE/BF/BG del foglio) = distribuzione
    -- CONDIZIONATA: BB/BC formano le coppie (serie_i, serie_i+1); BD filtra i
    -- "successori" delle serie la cui lunghezza = $AZ$13 (l'ULTIMO SUC, cioe' il
    -- ritardo dell'ultima uscita); BE/BF/BG = frequenza di quei successori.
    -- Significato: "dato il ritardo attuale, storicamente quale ritardo e'
    -- uscito SUBITO DOPO". % = conteggio / totale successori (|BD3|).
    cond_last as (
        select suc as last_suc from hits order by hit_seq desc limit 1
    ),
    cond_pairs as (
        select h.suc as cur, lead(h.suc) over (order by h.hit_seq) as nxt
        from hits h
    ),
    storico as (
        -- cond_last ha 0 o 1 riga: il join-virgola e' un INNER JOIN (1 riga) o
        -- restituisce 0 righe se non ci sono hit (n_occ=0) -> storico vuoto.
        select cp.nxt as len, count(*)::int as cnt
        from cond_pairs cp, cond_last cl
        where cp.cur = cl.last_suc and cp.nxt is not null
        group by cp.nxt
    ),
    -- conteggio occorrenze sotto / sopra la media ritardi (su INT(media)).
    -- media_rit (scalar, 1 sola riga in derived) valutata una volta sola.
    over_under as (
        select
            count(*) filter (where suc <= floor((select media_rit from derived)))::int      as sotto,
            count(*) filter (where suc >= floor((select media_rit from derived)) + 1)::int   as sopra
        from hits
    ),
    -- RUN SOPRA MEDIA: sulle serie chiuse in ordine cronologico, marca quelle
    -- con lunghezza >= media_rit, individua i run consecutivi e ne fa istogramma
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
    -- COLONNA BL del foglio ("ULTIME 10 SERIE" sopra media, indipendente da AZ):
    -- stream cronologico delle serie chiuse, dove
    --   serie chiusa SOTTO media (suc < media_rit) -> token 0  (pos = hit_seq)
    --   striscia di serie consecutive SOPRA media   -> token = lunghezza striscia
    --                                                  (pos = hit_seq di fine striscia)
    -- = trascrizione 1:1 della colonna BR/BL (BP/BQ -> FILTER): soglia a PIENA
    -- precisione (media_rit, come BP usa $C$7), non INT come sotto/sopra (BI/BJ).
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
            'league_id',       p_league_id,
            'market',          p_market,
            'target',          p_target,
            'mode',            p_mode,
            'season_year',     p_season_year,
            'n_requested',     case when p_mode='last_n' then p_last_n end,
            'n_scope',         ss.n_scope,        -- partite settlate nell'intervallo
            'n_effective',     d.n_eff,           -- eventi validi per questo mercato (= n DATI MATCH)
            'uses_ht',         v_uses_ht,
            'ht_coverage_pct', ss.ht_cov,
            'ht_missing_rule', 'escluse',         -- regola dal 25/09 (prima: 0-0)
            'n_ht_missing',    ss.n_ht_missing,   -- partite escluse per HT ignoto
            'date_from',       ss.d_from,
            'date_to',         ss.d_to
        ),
        'stats', jsonb_build_object(
            'n_occ',            d.n_occ,
            'frequency',        d.frequency,         -- % mercato
            'media_storica',    d.media_storica,     -- = quota oggettiva = "ogni Y partite"
            'quota_oggettiva',  d.media_storica,
            'ritardo_attuale',  d.ritardo_attuale,
            'record',           d.record,
            'media_ritardi',    round(d.media_rit, 4),
            'sotto_media',      ou.sotto,
            'sopra_media',      ou.sopra,
            'sotto_media_pct',  case when d.n_occ>0 then round(ou.sotto::numeric/d.n_occ,4) end,
            'sopra_media_pct',  case when d.n_occ>0 then round(ou.sopra::numeric/d.n_occ,4) end,
            -- ritardo attuale vs media storica: il segnale "intercetta ritardo"
            'rit_vs_media',     case when d.media_storica>0
                                     then round(d.ritardo_attuale::numeric/d.media_storica,3) end,
            -- valore di condizionamento dello storico (AZ13 = ultimo SUC):
            -- lo storico_serie mostra cosa e' uscito DOPO una serie di questa lunghezza
            'storico_cond_su',  (select last_suc from cond_last)
        ),
        'distribuzione_serie', coalesce((
            select jsonb_agg(jsonb_build_object('len',len,'occ_suc',occ_suc,'cnt_rit',cnt_rit) order by len)
            from distrib), '[]'::jsonb),
        'ultime_10_serie', coalesce((
            select jsonb_agg(suc order by hit_idx) from last10), '[]'::jsonb),
        -- storico CONDIZIONATO (BE/BF/BG): % sul totale dei successori (|BD3|)
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
        -- COLONNA BL: ultime 10 voci del token-stream (cronologico, vecchia->recente)
        'ultime_10_strisce_sopra_media', coalesce((
            select jsonb_agg(token order by ord)
            from (select token, ord from bl_tokens order by ord desc limit 10) t),
            '[]'::jsonb),
        -- DATI MATCH grezzo (per il confronto 1:1 con il foglio): tutte le
        -- colonne del foglio, incluse W/L, RIT, SUC del mercato selezionato.
        'series', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'idx',  rt.idx,                       -- EVENTO
                       'fid',  rt.fixture_id,
                       'date', rt.fixture_date,
                       'home', rt.home_team_name,            -- HOME
                       'away', rt.away_team_name,            -- AWAY
                       'gc',   rt.gc,                         -- GC
                       'ga',   rt.ga,                         -- GA
                       'gcfh', rt.gcfh,                       -- GCFH
                       'gafh', rt.gafh,                       -- GAFH
                       'gcsh', rt.gc - coalesce(rt.gcfh,0),   -- GCSH (derivato)
                       'gash', rt.ga - coalesce(rt.gafh,0),   -- GASH (derivato)
                       'out',  rt.outcome,                    -- W/L
                       'rit',  rt.rit_val,                    -- RIT
                       'suc',  h.suc)                         -- SUC (left join, O(n))
                   order by rt.idx)
            from rit rt
            left join hits h on h.hit_idx = rt.idx), '[]'::jsonb)
    )
    into v_result
    from derived d, scope_stats ss, over_under ou;

    return v_result;
end;
$$;

-- ---------------------------------------------------------------------------
-- 9. PRIMO RIEMPIMENTO (l'utente dal SQL Editor non ha il limite di 8 s)
-- ---------------------------------------------------------------------------
select public.refresh_analytics_riepilogo();

notify pgrst, 'reload schema';
