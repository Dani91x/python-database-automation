-- ============================================================================
-- MOTORE STRATEGIE — storage VIRTUALE delle strategie salvate (2026-06-23)
-- ============================================================================
-- Una strategia = nome + set di filtri (JSON). NESSUNA riga di risultato salvata:
-- la performance si ricalcola al volo con backtest_strategy → si aggiorna da sola
-- ogni giorno appena arrivano dati nuovi (architettura "virtuale" scelta utente).
-- Compare come voce selezionabile nel tab "Decisioni" accanto a 'google_sheets'.
--
-- SICUREZZA: RLS ON, nessuna policy → tabella non leggibile dal client. Accesso
-- SOLO via RPC SECURITY DEFINER (sotto), granted ad authenticated (owner early-access).
-- Idempotente.
-- ============================================================================

create table if not exists public.strategies (
    id          uuid         primary key default gen_random_uuid(),
    name        text         not null unique,
    filters     jsonb        not null default '{}'::jsonb,   -- i parametri p_* di backtest_strategy
    created_at  timestamptz  not null default now(),
    updated_at  timestamptz  not null default now()
);

alter table public.strategies enable row level security;
alter table public.strategies force row level security;
revoke all on table public.strategies from anon, authenticated;

-- ---- salva (o aggiorna per nome) una strategia ----
create or replace function public.save_strategy(p_name text, p_filters jsonb)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare v_id uuid;
begin
    if p_name is null or length(trim(p_name)) = 0 then
        raise exception 'nome strategia obbligatorio';
    end if;
    insert into public.strategies(name, filters)
    values (trim(p_name), coalesce(p_filters, '{}'::jsonb))
    on conflict (name) do update
        set filters = excluded.filters, updated_at = now()
    returning id into v_id;
    return v_id;
end;
$$;

-- ---- elenca le strategie salvate ----
create or replace function public.list_strategies()
returns table(id uuid, name text, filters jsonb, created_at timestamptz, updated_at timestamptz)
language sql
stable
security definer
set search_path = public
as $$
    select id, name, filters, created_at, updated_at
    from public.strategies order by created_at;
$$;

-- ---- elimina una strategia ----
create or replace function public.delete_strategy(p_id uuid)
returns void
language sql
security definer
set search_path = public
as $$
    delete from public.strategies where id = p_id;
$$;

-- ---- esegue il backtest di una strategia salvata (mapping filtri→RPC in un posto solo) ----
create or replace function public.run_strategy(p_id uuid, p_group_by text default null)
returns table(
    grp text, n bigint, n_settled bigint, n_hit bigint, hit_rate numeric,
    wilson_low numeric, wilson_high numeric, n_priced bigint, n_unpriced bigint,
    profit numeric, turnover numeric, roi numeric, roi_low numeric, roi_high numeric, avg_odds numeric
)
language plpgsql
stable
security definer
set search_path = public
set statement_timeout = '60s'
as $$
declare f jsonb;
begin
    select filters into f from public.strategies where id = p_id;
    if f is null then raise exception 'strategia % inesistente', p_id; end if;
    return query select * from public.backtest_strategy(
        p_date_from    => nullif(f->>'date_from','')::date,
        p_date_to      => nullif(f->>'date_to','')::date,
        p_market       => nullif(f->>'market',''),
        p_selection    => nullif(f->>'selection',''),
        p_leagues      => case when f ? 'leagues' and jsonb_typeof(f->'leagues')='array'
                               then (select array_agg((x)::bigint) from jsonb_array_elements_text(f->'leagues') x) end,
        p_direction    => coalesce(nullif(f->>'direction',''), 'back'),
        p_odds_source  => coalesce(nullif(f->>'odds_source',''), 'betfair_book'),
        p_commission   => coalesce(nullif(f->>'commission','')::numeric, 0.05),
        p_min_odds     => nullif(f->>'min_odds','')::numeric,
        p_max_odds     => nullif(f->>'max_odds','')::numeric,
        p_poisson_min  => nullif(f->>'poisson_min','')::numeric,
        p_ml_min       => nullif(f->>'ml_min','')::numeric,
        p_tacticai_min => nullif(f->>'tacticai_min','')::numeric,
        p_api_over     => coalesce((f->>'api_over')::boolean, false),
        p_n_engines_min => nullif(f->>'n_engines_min','')::int,
        p_min_edge     => nullif(f->>'min_edge','')::numeric,
        p_delay_eq     => nullif(f->>'delay_eq','')::int,
        p_delay_min    => nullif(f->>'delay_min','')::int,
        p_freq_dir     => nullif(f->>'freq_dir',''),
        p_ml_clean     => coalesce((f->>'ml_clean')::boolean, false),
        p_status       => nullif(f->>'status',''),
        p_group_by     => coalesce(nullif(p_group_by,''), nullif(f->>'group_by',''), 'market_league')
    );
end;
$$;

-- ---- drill-down: partite della strategia salvata (tutti i dati, per certificare a occhio) ----
create or replace function public.run_strategy_rows(p_id uuid, p_limit int default 300, p_offset int default 0)
returns table(
    kickoff timestamptz, league_name text, home_team text, away_team text,
    market text, selection text, poisson_prob numeric, ml_prob numeric, tacticai_prob numeric,
    api_over_line numeric, n_engines_agree smallint, delay_current integer, freq_deviation numeric,
    odds numeric, odds_src text, edge numeric, status text,
    settled boolean, hit boolean, total_goals smallint, goals_home smallint, goals_away smallint,
    first_goal_minute smallint, pnl numeric
)
language plpgsql stable security definer set search_path = public set statement_timeout = '60s'
as $$
declare f jsonb;
begin
    select filters into f from public.strategies where id = p_id;
    if f is null then raise exception 'strategia % inesistente', p_id; end if;
    return query select * from public.backtest_strategy_rows(
        p_date_from => nullif(f->>'date_from','')::date, p_date_to => nullif(f->>'date_to','')::date,
        p_market => nullif(f->>'market',''), p_selection => nullif(f->>'selection',''),
        p_leagues => case when f ? 'leagues' and jsonb_typeof(f->'leagues')='array'
                          then (select array_agg((x)::bigint) from jsonb_array_elements_text(f->'leagues') x) end,
        p_direction => coalesce(nullif(f->>'direction',''),'back'),
        p_odds_source => coalesce(nullif(f->>'odds_source',''),'betfair_book'),
        p_commission => coalesce(nullif(f->>'commission','')::numeric, 0.05),
        p_min_odds => nullif(f->>'min_odds','')::numeric, p_max_odds => nullif(f->>'max_odds','')::numeric,
        p_poisson_min => nullif(f->>'poisson_min','')::numeric, p_ml_min => nullif(f->>'ml_min','')::numeric,
        p_tacticai_min => nullif(f->>'tacticai_min','')::numeric, p_api_over => coalesce((f->>'api_over')::boolean,false),
        p_n_engines_min => nullif(f->>'n_engines_min','')::int, p_min_edge => nullif(f->>'min_edge','')::numeric,
        p_delay_eq => nullif(f->>'delay_eq','')::int, p_delay_min => nullif(f->>'delay_min','')::int,
        p_freq_dir => nullif(f->>'freq_dir',''), p_ml_clean => coalesce((f->>'ml_clean')::boolean,false),
        p_status => nullif(f->>'status',''), p_limit => p_limit, p_offset => p_offset
    );
end;
$$;

revoke all on function public.save_strategy(text, jsonb)   from public, anon;
revoke all on function public.run_strategy_rows(uuid, int, int) from public, anon;
grant execute on function public.run_strategy_rows(uuid, int, int) to authenticated, service_role;
revoke all on function public.list_strategies()             from public, anon;
revoke all on function public.delete_strategy(uuid)         from public, anon;
revoke all on function public.run_strategy(uuid, text)      from public, anon;
grant execute on function public.save_strategy(text, jsonb) to authenticated, service_role;
grant execute on function public.list_strategies()          to authenticated, service_role;
grant execute on function public.delete_strategy(uuid)      to authenticated, service_role;
grant execute on function public.run_strategy(uuid, text)   to authenticated, service_role;
