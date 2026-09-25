-- =====================================================================
-- season_aggregates_2026-09-25.sql  --  stato degli AGGREGATI per (lega, stagione)
-- =====================================================================
-- ADDITIVA: una funzione nuova, nessuna tabella toccata. La applica l'utente
-- (SQL Editor), DOPO season_gaps_2026-09-25.sql. Ripetibile (OR REPLACE).
--
-- public.season_aggregates_summary(p_league_ids int[], p_season_years int[])
--   Per ogni (lega, stagione) degli array paralleli restituisce:
--     tabella in ('standings','injuries','top_scorers','top_assists','top_cards'):
--         n = righe presenti, ultimo = max(coalesce(updated_at, created_at))
--         (gli script scrivono con delete+insert per (lega, stagione): 'ultimo'
--          e' l'ora dell'ultimo aggiornamento riuscito)
--     tabella = '_ft': ultimo = data della partita FT/AET/PEN piu' recente
--         (serve a capire se classifica/marcatori sono piu' vecchi dell'ultima giornata)
--   Solo le coppie con righe compaiono (una riga per tabella presente).
--   Il codice chiama a blocchi di 150 coppie: <= 900 righe (limite PostgREST 1000).
--
-- COSTO IO: un'aggregazione per tabella filtrata su (league_id, season_year):
-- con un indice su (league_id, season_year) sono letture di poche pagine. Il
-- blocco DO in fondo AVVISA se l'indice manca; in quel caso applicare
-- migrations/aggregati_idx_2026-09-25_SOLO_SE_MANCANO.sql (tabelle da 25k-190k righe).
--
-- Senza questa migrazione: recupero giornaliero e orchestratore si FERMANO con
-- "applica migrations/season_aggregates_2026-09-25.sql" (exit 2).
-- =====================================================================

begin;

create or replace function public.season_aggregates_summary(
    p_league_ids   integer[],
    p_season_years integer[]
)
returns table (league_id integer, season_year integer, tabella text, n integer, ultimo timestamptz)
language sql
stable
security invoker
set search_path = public
as $$
    with p as (
        select distinct x.league_id, x.season_year
        from unnest(p_league_ids, p_season_years) as x(league_id, season_year)
    )
    select s.league_id, s.season_year, 'standings'::text, count(*)::int, max(coalesce(s.updated_at, s.created_at))
    from public.standings s join p on p.league_id = s.league_id and p.season_year = s.season_year
    group by s.league_id, s.season_year
    union all
    select s.league_id, s.season_year, 'injuries'::text, count(*)::int, max(coalesce(s.updated_at, s.created_at))
    from public.injuries s join p on p.league_id = s.league_id and p.season_year = s.season_year
    group by s.league_id, s.season_year
    union all
    select s.league_id, s.season_year, 'top_scorers'::text, count(*)::int, max(coalesce(s.updated_at, s.created_at))
    from public.top_scorers s join p on p.league_id = s.league_id and p.season_year = s.season_year
    group by s.league_id, s.season_year
    union all
    select s.league_id, s.season_year, 'top_assists'::text, count(*)::int, max(coalesce(s.updated_at, s.created_at))
    from public.top_assists s join p on p.league_id = s.league_id and p.season_year = s.season_year
    group by s.league_id, s.season_year
    union all
    select s.league_id, s.season_year, 'top_cards'::text, count(*)::int, max(coalesce(s.updated_at, s.created_at))
    from public.top_cards s join p on p.league_id = s.league_id and p.season_year = s.season_year
    group by s.league_id, s.season_year
    union all
    select m.league_id, m.season_year, '_ft'::text, count(*)::int, max(m.fixture_date)
    from public.matches m join p on p.league_id = m.league_id and p.season_year = m.season_year
    where m.status_short in ('FT', 'AET', 'PEN')
    group by m.league_id, m.season_year;
$$;

revoke all on function public.season_aggregates_summary(integer[], integer[]) from public, anon, authenticated;
grant execute on function public.season_aggregates_summary(integer[], integer[]) to service_role;

commit;

notify pgrst, 'reload schema';

-- CONTROLLO INDICI (solo avvisi): indice non parziale che inizia con league_id
do $$
declare
    t  text;
    ok boolean;
begin
    foreach t in array array['standings', 'injuries', 'top_scorers', 'top_assists', 'top_cards'] loop
        select exists (
            select 1
            from pg_index i
            join pg_class c      on c.oid = i.indrelid
            join pg_namespace n  on n.oid = c.relnamespace
            join pg_attribute a  on a.attrelid = c.oid and a.attnum = i.indkey[0]
            where n.nspname = 'public' and c.relname = t and a.attname = 'league_id' and i.indpred is null
        ) into ok;
        if not ok then
            raise warning 'ATTENZIONE: public.% senza indice su (league_id, season_year): applica migrations/aggregati_idx_2026-09-25_SOLO_SE_MANCANO.sql', t;
        else
            raise notice 'ok: public.% ha un indice su league_id', t;
        end if;
    end loop;
end $$;

-- Verifica rapida (sola lettura): select * from public.season_aggregates_summary(array[135], array[2026]);
