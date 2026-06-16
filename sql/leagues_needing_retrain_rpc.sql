-- ============================================================================
-- leagues_needing_retrain — RPC per la MANUTENZIONE INCREMENTALE dei modelli.
-- ============================================================================
-- Ritorna le leghe da riaddestrare perche' hanno abbastanza partite settlate
-- NUOVE dall'ultimo trained_at del loro modello.
--
-- Soglia ADATTIVA per lega: greatest(p_min_new, squadre_stagione_corrente / 2)
--   ~ una "giornata" di campionato (una lega a 20 squadre => 10 partite/giornata;
--   leghe piccole => almeno p_min_new). Cosi' le leghe attive si aggiornano spesso,
--   quelle poco attive solo quando c'e' abbastanza segnale nuovo.
--
-- Usata da training_planner._incremental_todo() quando la campagna di massa e'
-- conversa (todo cutoff = 0): lo stesso workflow di retrain, da li' in poi,
-- mantiene i modelli freschi all'infinito senza intervento manuale.
--
-- SICUREZZA: SECURITY DEFINER, sola lettura (STABLE), search_path fissato,
-- eseguibile SOLO da service_role (i nostri script) — MAI da anon.
-- ============================================================================

create or replace function public.leagues_needing_retrain(p_min_new integer default 10)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  with last_train as (
    -- ultimo addestramento per lega
    select league_id, max(trained_at) as trained_at
    from ai_model_registry
    where trained_at is not null
    group by league_id
  ),
  latest_season as (
    select league_id, max(season_year) as sy
    from matches
    where status_short in ('FT','AET','PEN')
    group by league_id
  ),
  team_counts as (
    -- squadre della STAGIONE CORRENTE (per stimare la dimensione di una giornata)
    select m.league_id, count(distinct m.home_team_id) as n_teams
    from matches m
    join latest_season ls
      on ls.league_id = m.league_id and m.season_year = ls.sy
    where m.status_short in ('FT','AET','PEN')
    group by m.league_id
  ),
  new_counts as (
    -- partite settlate NUOVE dopo l'ultimo trained_at
    select m.league_id, count(*)::int as new_matches
    from matches m
    join last_train lt on lt.league_id = m.league_id
    where m.status_short in ('FT','AET','PEN')
      and m.fixture_date > lt.trained_at
    group by m.league_id
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'league_id',   nc.league_id,
           'new_matches', nc.new_matches,
           'threshold',   greatest(p_min_new, coalesce(tc.n_teams, 20) / 2)
         ) order by nc.new_matches desc), '[]'::jsonb)
  from new_counts nc
  left join team_counts tc on tc.league_id = nc.league_id
  where nc.new_matches >= greatest(p_min_new, coalesce(tc.n_teams, 20) / 2);
$$;

-- Solo i nostri script (service_role). NON anon/authenticated (repo pubblica).
revoke all on function public.leagues_needing_retrain(integer) from public;
grant execute on function public.leagues_needing_retrain(integer) to service_role;

comment on function public.leagues_needing_retrain is
'Leghe da riaddestrare in manutenzione incrementale: partite settlate nuove dall ultimo trained_at >= soglia adattiva (max(p_min_new, squadre_correnti/2)). Solo service_role.';
