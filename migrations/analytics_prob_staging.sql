-- ============================================================================
-- STAGING per il FIX C1/C2 storico — ri-popolamento bulk di prob/concordanza
-- ============================================================================
-- Lo storico (da engine_signals) aveva prob PER-SCOMMESSA (overround, argmax
-- invertibile). Questo fix ri-scrive la prob PURA (Poisson da markets_calibrated;
-- ML da engine_signals normalizzato) + ricalcola n_engines_agree/consensus_prob.
-- Scrittura bulk: lo script Python calcola e carica qui, poi 1 UPDATE FROM.
-- RLS-locked. Idempotente.
-- ============================================================================

create table if not exists analytics_prob_staging (
    signal_uid       text primary key,
    prob             numeric,
    fair_odds        numeric,
    n_engines_agree  smallint,
    consensus_prob   numeric
);
alter table analytics_prob_staging enable row level security;
alter table analytics_prob_staging force row level security;
revoke all on table analytics_prob_staging from anon, authenticated;

create or replace function public.flush_analytics_prob_staging()
returns void
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
begin
    update analytics_signals s
       set prob = st.prob,
           fair_odds = st.fair_odds,
           n_engines_agree = st.n_engines_agree,
           consensus_prob = st.consensus_prob
      from analytics_prob_staging st
     where s.signal_uid = st.signal_uid;
    delete from analytics_prob_staging where true;   -- WHERE obbligatorio (safe-update)
end;
$$;
revoke all on function public.flush_analytics_prob_staging() from anon, authenticated;
grant execute on function public.flush_analytics_prob_staging() to service_role;
