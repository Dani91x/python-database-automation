-- ============================================================================
-- SECURITY LOCKDOWN — early access: SOLO l'owner accede a dati e dashboard.
-- Eseguire una volta nel Supabase SQL Editor (ruolo postgres).
--
-- Contesto: il frontend è pubblico (repo + bundle su Vercel) quindi la anon key
-- è nota a chiunque. La sicurezza NON può stare nel frontend: deve stare qui.
--
-- Cosa fa:
--  1) Toglie ad 'anon' (non autenticato) il permesso di chiamare le RPC dati.
--     Da loggato l'owner le chiama come 'authenticated' → continua a funzionare.
--  2) Blocca a livello DB qualsiasi registrazione che non sia l'owner
--     (trigger su auth.users): garanzia "solo io" indipendente dalle impostazioni.
--  3) Blinda la tabella leads: anon può solo INSERT (cattura lead), mai SELECT.
-- ============================================================================

-- Email dell'unico utente autorizzato.
-- (Se un giorno cambi email owner, aggiornala QUI e in src/lib/auth-config.ts.)

------------------------------------------------------------------------------
-- 1) RPC DATI: revoca esecuzione ad anon (resta authenticated + service_role)
------------------------------------------------------------------------------
revoke execute on function public.get_analytics(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,integer,text,integer,text) from anon;
revoke execute on function public.get_analytics_rows(text,text,text,integer,integer,numeric,numeric,integer,boolean,timestamptz,timestamptz,integer,text,integer,integer,integer,integer) from anon;
revoke execute on function public.get_analytics_filters() from anon;
revoke execute on function public.get_market_delays(integer,text,text,text,integer,integer) from anon;
revoke execute on function public.get_market_frequency(integer,text,text,numeric,text,integer,integer) from anon;
revoke execute on function public.get_league_seasons(integer) from anon;

-- Se in futuro aggiungi altre RPC che leggono dati, ricordati di NON concederle
-- ad anon: usa sempre solo "to authenticated, service_role".

------------------------------------------------------------------------------
-- 2) BLOCCO REGISTRAZIONI A LIVELLO DB — solo l'owner può esistere in auth.users
------------------------------------------------------------------------------
create or replace function public.block_non_owner_signup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if lower(coalesce(new.email, '')) <> 'daniele.ritrovato@gmail.com' then
        raise exception 'Registrazioni non ancora aperte.';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_block_non_owner_signup on auth.users;
create trigger trg_block_non_owner_signup
    before insert on auth.users
    for each row execute function public.block_non_owner_signup();

-- NB: oltre a questo trigger, i signup pubblici sono stati disabilitati anche a
-- livello di configurazione Auth (disable_signup = true) via Management API
-- (Dashboard → Authentication → Sign In/Up → "Allow new users to sign up" = OFF).
-- Doppia protezione: config + trigger DB.

------------------------------------------------------------------------------
-- 3) TABELLA leads: anon solo INSERT, lettura solo autenticati
------------------------------------------------------------------------------
alter table public.leads enable row level security;

drop policy if exists leads_anon_insert on public.leads;
drop policy if exists leads_select_authenticated on public.leads;

-- chiunque (anche non loggato) può lasciare un lead...
create policy leads_anon_insert on public.leads
    for insert to anon, authenticated
    with check (true);

-- ...ma solo gli autenticati (=> l'owner) possono leggerli
create policy leads_select_authenticated on public.leads
    for select to authenticated
    using (true);

-- con RLS attiva serve il GRANT esplicito di INSERT ad anon (la policy da sola
-- non basta: PostgREST richiede ANCHE il privilegio di tabella).
grant insert on table public.leads to anon;

-- nega invece la SELECT ad anon (a livello di grant): non deve leggere i lead
revoke select on table public.leads from anon;

------------------------------------------------------------------------------
-- 4) TABELLA fixture_predictions: letta DIRETTAMENTE dal frontend (.from()).
--    Oggi è leggibile da anon → va chiusa, ma l'owner autenticato deve leggerla.
--    NB: NON usiamo FORCE RLS, così il backend (service_role) continua a
--    scrivere/leggere senza ostacoli (service_role bypassa la RLS).
------------------------------------------------------------------------------
alter table public.fixture_predictions enable row level security;

drop policy if exists fixture_predictions_select_authenticated on public.fixture_predictions;
create policy fixture_predictions_select_authenticated on public.fixture_predictions
    for select to authenticated
    using (true);

-- l'owner loggato (authenticated) deve avere il grant di lettura...
grant select on table public.fixture_predictions to authenticated;
-- ...e anon NON deve poter leggere nulla
revoke select on table public.fixture_predictions from anon;

-- ============================================================================
-- VERIFICA POST-ESECUZIONE (esegui e controlla che 'anon' NON compaia):
--   select p.proname, r.rolname
--   from pg_proc p
--   join information_schema.routine_privileges rp
--     on rp.routine_name = p.proname
--   join pg_roles r on r.rolname = rp.grantee
--   where p.proname in ('get_analytics','get_analytics_rows','get_analytics_filters',
--                       'get_market_delays','get_market_frequency','get_league_seasons')
--   order by 1,2;
-- ============================================================================
