-- =====================================================================
-- season_gaps_2026-09-25.sql  --  "cosa manca" per (lega, stagione)
-- =====================================================================
-- ADDITIVA: una tabella nuova piccola + 3 funzioni nuove. Nessuna tabella
-- esistente viene modificata, nessun dato cancellato. La applica l'utente
-- (SQL Editor di Supabase), una volta. Ripetibile (IF NOT EXISTS / OR REPLACE).
--
-- A cosa serve (ordine dell'utente 25/09: DB sempre aggiornato, senza buchi,
-- quota rispettata, backfill ripartibile):
--
-- 1) public.fixture_detail_checks
--    Memoria delle partite GIA' interrogate che l'API ha dato VUOTE, in
--    ERRORE, o scritte solo in PARTE (insert fallito a meta'), per una tabella
--    di dettaglio. Serve a non richiamare ogni notte l'API per partite che
--    l'API stessa non ha, a non PERDERE in silenzio una partita vuota (resta
--    visibile finche' non e' piena o "vuota definitiva": 2 risposte vuote,
--    oppure una vuota chiesta >= 7 giorni dopo la partita) e a non lasciare
--    invisibile una partita scritta a meta' (esito 'parziale': le righe ci
--    sono ma la partita resta da rifare). Una scrittura riuscita (esito 'ok')
--    cancella la riga. Tabella piccola: solo le eccezioni.
--
-- 2) public.record_fixture_detail_checks(p_rows jsonb)
--    'vuoto' | 'errore' | 'parziale' -> scrive/aggiorna (conta vuoti ed
--    errori); 'ok' -> cancella la riga; altri esiti ignorati (il codice usa
--    esito 'sonda' per verificare che la migrazione sia applicata).
--
-- 3) public.season_detail_gaps(p_league_id, p_season_year, p_fixture_ids)
--    Per le partite FT/AET/PEN di una lega-stagione (o solo delle fixture
--    indicate) restituisce, per tabella di dettaglio e per stato, il numero e
--    gli id delle partite SENZA righe (o scritte in parte):
--      da_chiamare | errore | da_richiamare  -> il codice chiama l'API
--      in_attesa        (1 vuoto da < 2 giorni)  -> buco aperto, si ritenta dopo
--      vuoto_definitivo (l'API non ha il dato)   -> non e' un buco, si dichiara
--      non_disponibile  (solo match_odds: partita di oltre 7 giorni fa; l'API
--                        tiene lo storico quote solo 7 giorni) -> non si chiama,
--                        non e' un buco recuperabile, si dichiara
--    Per match_odds conta SOLO la fonte snapshot_type = 'api_football' (le
--    righe 'football_data_csv', quote di chiusura importate da CSV, sono
--    un'altra fonte e non riempiono il buco API).
--    piu' due righe '_partite' (ft = partite FT, tutte = tutte le partite).
--    Una riga per (tabella, stato) con array di id: mai piu' di ~30 righe,
--    quindi niente limite di 1000 righe di PostgREST.
--
-- 4) public.season_gaps_summary(p_league_ids int[], p_season_years int[])
--    Solo i conteggi di (3) per piu' lega-stagioni (array paralleli), usata
--    dal recupero giornaliero a blocchi di 20 lega-stagioni.
--
-- COSTO IO: EXISTS per (partita, tabella) = una sonda su indice fixture_id
-- per tabella; le partite si leggono con idx_matches_league_season
-- (sql/perf_indexes.sql). Il blocco DO in fondo AVVISA se una tabella di
-- dettaglio non ha un indice su fixture_id (senza, match_odds da ~82M righe
-- verrebbe letta per intero): in quel caso applicare prima
-- migrations/detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql.
--
-- Senza questa migrazione: il recupero giornaliero e l'orchestratore si
-- FERMANO con "applica migrations/season_gaps_2026-09-25.sql" (fail-loud);
-- il Daily continua come prima e stampa un AVVISO (vuoti non registrati).
-- =====================================================================

begin;

create table if not exists public.fixture_detail_checks (
    fixture_id          integer     not null,
    tabella             text        not null,
    league_id           integer     not null,
    season_year         integer     not null,
    esito               text        not null,            -- ultimo esito: 'vuoto' | 'errore' | 'parziale'
    vuoti               integer     not null default 0,  -- risposte VUOTE ricevute
    errori              integer     not null default 0,  -- tentativi in ERRORE o scritti in PARTE
    primo_controllo_at  timestamptz not null default now(),
    ultimo_controllo_at timestamptz not null default now(),
    primary key (fixture_id, tabella),
    constraint fixture_detail_checks_tabella_chk check (tabella in
        ('match_events', 'match_lineups', 'match_player_stats', 'match_team_stats', 'match_odds'))
);

-- vincolo sugli esiti separato: ripetibile anche se una versione precedente del file fosse gia' stata applicata
alter table public.fixture_detail_checks drop constraint if exists fixture_detail_checks_esito_chk;
alter table public.fixture_detail_checks add constraint fixture_detail_checks_esito_chk
    check (esito in ('vuoto', 'errore', 'parziale'));

comment on table public.fixture_detail_checks is
    'Partite FT interrogate con risposta VUOTA, in ERRORE o scritte in PARTE per una tabella di dettaglio '
    '(season_gaps_2026-09-25). Scrive per_fixture_backfill via record_fixture_detail_checks; '
    'legge season_detail_gaps.';

create index if not exists idx_fixture_detail_checks_league_season
    on public.fixture_detail_checks (league_id, season_year);

-- Coerente con i blocchi di sicurezza del 24/09: RLS attiva, nessuna policy
-- (solo service_role, che bypassa RLS, legge e scrive).
alter table public.fixture_detail_checks enable row level security;
revoke all on public.fixture_detail_checks from anon, authenticated;


create or replace function public.record_fixture_detail_checks(p_rows jsonb)
returns integer
language sql
volatile
security invoker
set search_path = public
as $$
    with r as (
        select distinct on ((x->>'fixture_id')::int, x->>'tabella')
               (x->>'fixture_id')::int   as fixture_id,
               x->>'tabella'             as tabella,
               (x->>'league_id')::int    as league_id,
               (x->>'season_year')::int  as season_year,
               x->>'esito'               as esito
        from jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) as x
        where x->>'esito' in ('vuoto', 'errore', 'parziale', 'ok')
    ), cancellate as (
        delete from public.fixture_detail_checks c
        using r
        where r.esito = 'ok' and c.fixture_id = r.fixture_id and c.tabella = r.tabella
        returning 1
    ), scritte as (
        insert into public.fixture_detail_checks as c
               (fixture_id, tabella, league_id, season_year, esito, vuoti, errori)
        select fixture_id, tabella, league_id, season_year, esito,
               case when esito = 'vuoto' then 1 else 0 end,
               case when esito in ('errore', 'parziale') then 1 else 0 end
        from r
        where r.esito <> 'ok'
        on conflict (fixture_id, tabella) do update
           set esito = excluded.esito,
               vuoti = c.vuoti + excluded.vuoti,
               errori = c.errori + excluded.errori,
               ultimo_controllo_at = now()
        returning 1
    )
    select ((select count(*) from cancellate) + (select count(*) from scritte))::int;
$$;


create or replace function public.season_detail_gaps(
    p_league_id   integer,
    p_season_year integer,
    p_fixture_ids integer[] default null
)
returns table (tabella text, stato text, n integer, fixture_ids integer[])
language sql
stable
security invoker
set search_path = public
as $$
    with ft as (
        select m.fixture_id, m.fixture_date
        from public.matches m
        where m.league_id = p_league_id
          and m.season_year = p_season_year
          and m.status_short in ('FT', 'AET', 'PEN')
          and (p_fixture_ids is null or m.fixture_id = any (p_fixture_ids))
    ),
    senza as (
        select ft.fixture_id, ft.fixture_date, t.tabella,
               c.fixture_id is not null as ha_check, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        cross join lateral (values
            ('match_events',       exists (select 1 from public.match_events       x where x.fixture_id = ft.fixture_id)),
            ('match_lineups',      exists (select 1 from public.match_lineups      x where x.fixture_id = ft.fixture_id)),
            ('match_player_stats', exists (select 1 from public.match_player_stats x where x.fixture_id = ft.fixture_id)),
            ('match_team_stats',   exists (select 1 from public.match_team_stats   x where x.fixture_id = ft.fixture_id)),
            ('match_odds',         exists (select 1 from public.match_odds         x where x.fixture_id = ft.fixture_id
                                                                                     and x.snapshot_type = 'api_football'))
        ) as t(tabella, presente)
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = t.tabella
        where not t.presente or c.esito = 'parziale'
    ),
    classificate as (
        select s.fixture_id, s.tabella,
               case
                   when s.tabella = 'match_odds'
                        and s.fixture_date < now() - interval '7 days' then 'non_disponibile'
                   when not s.ha_check then 'da_chiamare'
                   when s.esito in ('errore', 'parziale') then 'errore'
                   when s.vuoti >= 2
                        or s.ultimo_controllo_at >= s.fixture_date + interval '7 days' then 'vuoto_definitivo'
                   when s.ultimo_controllo_at > now() - interval '2 days' then 'in_attesa'
                   else 'da_richiamare'
               end as stato
        from senza s
    )
    select '_partite'::text, 'ft'::text, count(*)::int, null::integer[] from ft
    union all
    select '_partite'::text, 'tutte'::text, count(*)::int, null::integer[]
    from public.matches m
    where m.league_id = p_league_id and m.season_year = p_season_year
      and (p_fixture_ids is null or m.fixture_id = any (p_fixture_ids))
    union all
    select k.tabella, k.stato, count(*)::int, array_agg(k.fixture_id order by k.fixture_id)
    from classificate k
    group by k.tabella, k.stato;
$$;


create or replace function public.season_gaps_summary(
    p_league_ids   integer[],
    p_season_years integer[]
)
returns table (league_id integer, season_year integer, tabella text, stato text, n integer)
language sql
stable
security invoker
set search_path = public
as $$
    select p.league_id, p.season_year, g.tabella, g.stato, g.n
    from unnest(p_league_ids, p_season_years) as p(league_id, season_year)
    cross join lateral public.season_detail_gaps(p.league_id, p.season_year, null) as g;
$$;

revoke all on function public.record_fixture_detail_checks(jsonb) from public, anon, authenticated;
revoke all on function public.season_detail_gaps(integer, integer, integer[]) from public, anon, authenticated;
revoke all on function public.season_gaps_summary(integer[], integer[]) from public, anon, authenticated;
grant execute on function public.record_fixture_detail_checks(jsonb) to service_role;
grant execute on function public.season_detail_gaps(integer, integer, integer[]) to service_role;
grant execute on function public.season_gaps_summary(integer[], integer[]) to service_role;

commit;

-- Ricarica lo schema di PostgREST (le RPC nuove diventano visibili subito).
notify pgrst, 'reload schema';

-- ---------------------------------------------------------------------
-- CONTROLLO INDICI (solo avvisi, non modifica nulla): ogni tabella di
-- dettaglio deve avere un indice NON parziale che inizia con fixture_id.
-- ---------------------------------------------------------------------
do $$
declare
    t  text;
    ok boolean;
begin
    foreach t in array array['match_events', 'match_lineups', 'match_player_stats',
                             'match_team_stats', 'match_odds', 'matches'] loop
        select exists (
            select 1
            from pg_index i
            join pg_class c      on c.oid = i.indrelid
            join pg_namespace n  on n.oid = c.relnamespace
            join pg_attribute a  on a.attrelid = c.oid and a.attnum = i.indkey[0]
            where n.nspname = 'public' and c.relname = t
              and a.attname = case when t = 'matches' then 'league_id' else 'fixture_id' end
              and i.indpred is null
        ) into ok;
        if not ok then
            raise warning 'ATTENZIONE: public.% senza indice utile (fixture_id / league_id): applica migrations/detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql PRIMA di usare il recupero', t;
        else
            raise notice 'ok: public.% ha un indice utile', t;
        end if;
    end loop;
end $$;

-- Verifica rapida dopo l'applicazione (sola lettura, lega inesistente = 0 righe utili):
--   select * from public.season_detail_gaps(0, 0, null);
--   select public.record_fixture_detail_checks('[{"esito":"sonda"}]'::jsonb);   -- 0
