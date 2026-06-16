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

-- PERFORMANCE: il conteggio squadre viene da `standings` (tabella PICCOLA: ~poche
-- righe per lega/stagione), NON da `matches` (milioni di righe) — cosi' si evita
-- una scansione pesante. L'unico accesso a `matches` resta `new_counts`, accelerato
-- dall'indice idx_matches_fixture_date_settled (vedi in fondo). Filtro fixture_date
-- > now()-400gg per limitare lo scan: trained_at e' sempre recente (la campagna e
-- la manutenzione incrementale riaddestrano spesso), quindi 400gg coprono con
-- ampio margine ogni "nuova" partita.
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
  team_counts as (
    -- squadre della STAGIONE CORRENTE, da STANDINGS (leggero)
    select s.league_id, count(*)::int as n_teams
    from standings s
    join (select league_id, max(season_year) as sy from standings group by league_id) ls
      on ls.league_id = s.league_id and s.season_year = ls.sy
    group by s.league_id
  ),
  new_counts as (
    -- partite settlate NUOVE dopo l'ultimo trained_at (scan limitato a ~400gg)
    select m.league_id, count(*)::int as new_matches
    from matches m
    join last_train lt on lt.league_id = m.league_id
    where m.status_short in ('FT','AET','PEN')
      and m.fixture_date > lt.trained_at
      and m.fixture_date > (now() - interval '400 days')
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

-- ----------------------------------------------------------------------------
-- INDICE che rende veloce l'unico accesso a `matches` (filtro per fixture_date).
-- Senza, la RPC fa scan pesanti e va in timeout su Nano sotto carico.
-- ⚠️ CREATE INDEX CONCURRENTLY NON puo' stare in una transazione: nell'SQL Editor
--    eseguilo DA SOLO (una sola istruzione selezionata), non insieme al resto.
--    CONCURRENTLY = nessun lock sulla tabella => sicuro anche con la campagna in
--    corso (solo piu' lento a costruirsi).
-- ----------------------------------------------------------------------------
-- create index concurrently if not exists idx_matches_fixture_date_settled
--   on public.matches (fixture_date)
--   where status_short in ('FT','AET','PEN');
