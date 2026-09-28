-- =====================================================================
-- season_gaps_perf_2026-09-28.sql -- season_detail_gaps piu' veloce (57014)
-- =====================================================================
-- SOSTITUTIVA di una sola funzione (CREATE OR REPLACE, ripetibile). Nessuna
-- tabella toccata, nessun dato modificato. La applica l'utente (SQL Editor
-- di Supabase), quando vuole: non cambia il contratto (stessi parametri,
-- stesso RETURNS TABLE, stesso output riga per riga - verificato di persona,
-- vedi sotto), quindi season_gaps_summary/season_detail_gaps e tutto il
-- codice Python che li chiama restano identici.
--
-- CAUSA RADICE (cantiere 28/09/2026, AUDIT_2026-09-28/CANTIERE_E_CATCHUP_57014.md):
-- la CTE `senza` del vecchio season_detail_gaps calcola le 5 tabelle di
-- dettaglio con
--     cross join lateral (values
--         ('match_events',  exists (select 1 from match_events x where x.fixture_id = ft.fixture_id)),
--         ... altre 4 ...
--     ) as t(tabella, presente)
-- Le 5 EXISTS(...) sono DENTRO una VALUES: il planner di Postgres non le
-- vede come condizioni di join (non le trasforma in Anti Join) ma come 5
-- sotto-piani (SubPlan) da rieseguire per OGNI riga di `ft` (ogni partita
-- FT della lega-stagione): per una stagione da 380 partite sono 1.900 probe
-- sugli indici (380 x 5), uno scan per volta, invece di 5 join a insieme
-- (uno per tabella). Prova con EXPLAIN (non ANALYZE, nessuna esecuzione)
-- sulla lega 39 stagione 2024 (Premier League, 733 righe FT nel range
-- lega+stagione prima del filtro status_short): il costo totale stimato dal
-- planner sulla forma vecchia e' ~828 (la VALUES nasconde il costo reale dei
-- 5 SubPlan, tra cui il probe su match_odds da solo costerebbe 4.109 per un
-- singolo probe: il planner quindi NON vede il costo vero e non puo' mai
-- scegliere un piano diverso, nemmeno quando le tabelle o il carico
-- crescono). Riscritta con NOT EXISTS/EXISTS a livello di WHERE (non dentro
-- una VALUES), il planner trasforma correttamente in Anti Join/Semi Join per
-- ciascuna tabella e il costo totale stimato sale a ~4.536 (5 aggregate
-- separati, somma ~3.775): la stima ora e' vera, il planner puo' scegliere
-- hash/merge join se conviene, e soprattutto il tempo reale smette di
-- dipendere dal numero di probe sparsi quando la cache e' fredda o il DB e'
-- sotto carico (misura EXPLAIN ANALYZE sul primo blocco reale della corsa
-- rossa del 26/09, lega 1+2, 20 coppie: 2,47 s, 95.925 buffer hit + 2.537
-- letture fisiche anche a DB fermo; indici delle 5 tabelle 6,6 GB,
-- effective_cache_size sul progetto 768 MB, DB totale 50 GB: il set di
-- lavoro NON entra in cache e ogni sessione concorrente lo scaccia).
-- Equivalenza dell'output VERIFICATA sul DB vero (SELECT, sola lettura,
-- nessuna scrittura) confrontando season_detail_gaps() col vecchio corpo
-- contro la stessa logica riscritta, riga per riga:
--   lega 39 stagione 2024 (tutto pieno): entrambe -> match_odds
--     non_disponibile 380 (unica riga oltre alle 2 "_partite"), stesso numero.
--   lega 45 stagione 2026 (buchi veri, stati misti): entrambe ->
--     match_events da_chiamare 238; match_lineups da_richiamare 94,
--     vuoto_definitivo 144; match_odds da_richiamare 7, non_disponibile 202;
--     match_player_stats da_chiamare 238; match_team_stats da_chiamare 238.
--     Identiche, stesso ordine, stessi conteggi.
-- Il ramo esito='parziale' (dato presente ma da riscrivere) non ha righe sul
-- DB vero oggi (fixture_detail_checks: solo esito='vuoto', 2.669 righe): la
-- riscrittura lo copre con un secondo pezzo per tabella (semi-join EXISTS +
-- JOIN su fixture_detail_checks con esito='parziale'), stessa condizione del
-- vecchio `where not t.presente or c.esito = 'parziale'`, verificata a mano
-- confrontando le due espressioni booleane (non eseguibile: nessuna riga
-- 'parziale' nel DB oggi per una prova diretta).
--
-- QUESTA MIGRAZIONE NON RISOLVE DA SOLA IL 57014: riduce il costo e rende
-- il piano stabile, ma un DB sotto carico puo' comunque essere lento. La
-- protezione "non deve mai morire per un timeout di riepilogo" e' nel
-- CODICE (season_gaps.py:riepilogo_lacune, ritentativo con blocco dimezzato
-- e degrado della singola lega-stagione, seasons_catchup.py), non qui.
-- =====================================================================

CREATE OR REPLACE FUNCTION public.season_detail_gaps(
    p_league_id integer,
    p_season_year integer,
    p_fixture_ids integer[] DEFAULT NULL::integer[]
)
RETURNS TABLE(tabella text, stato text, n integer, fixture_ids integer[])
LANGUAGE sql
STABLE
SET search_path TO 'public'
AS $function$
    with ft as (
        select m.fixture_id, m.fixture_date
        from public.matches m
        where m.league_id = p_league_id
          and m.season_year = p_season_year
          and m.status_short in ('FT', 'AET', 'PEN')
          and (p_fixture_ids is null or m.fixture_id = any (p_fixture_ids))
    ),
    -- Una tabella alla volta: NOT EXISTS/EXISTS a livello di WHERE (non dentro
    -- una VALUES) cosi' il planner li trasforma in Anti Join / Semi Join veri
    -- (vedi commento in testa al file). Stessa condizione del vecchio
    -- "where not t.presente or c.esito = 'parziale'", divisa in due pezzi che
    -- non si sovrappongono mai (una partita e' o senza dato, o con dato E
    -- parziale, mai entrambe le righe per la stessa tabella).
    senza as (
        -- match_events: senza dato
        select ft.fixture_id, ft.fixture_date, 'match_events'::text as tabella,
               c.fixture_id is not null as ha_check, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_events'
        where not exists (select 1 from public.match_events x where x.fixture_id = ft.fixture_id)
        union all
        -- match_events: dato presente ma segnato 'parziale'
        select ft.fixture_id, ft.fixture_date, 'match_events'::text,
               true, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_events' and c.esito = 'parziale'
        where exists (select 1 from public.match_events x where x.fixture_id = ft.fixture_id)

        union all
        select ft.fixture_id, ft.fixture_date, 'match_lineups'::text,
               c.fixture_id is not null, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_lineups'
        where not exists (select 1 from public.match_lineups x where x.fixture_id = ft.fixture_id)
        union all
        select ft.fixture_id, ft.fixture_date, 'match_lineups'::text,
               true, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_lineups' and c.esito = 'parziale'
        where exists (select 1 from public.match_lineups x where x.fixture_id = ft.fixture_id)

        union all
        select ft.fixture_id, ft.fixture_date, 'match_player_stats'::text,
               c.fixture_id is not null, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_player_stats'
        where not exists (select 1 from public.match_player_stats x where x.fixture_id = ft.fixture_id)
        union all
        select ft.fixture_id, ft.fixture_date, 'match_player_stats'::text,
               true, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_player_stats' and c.esito = 'parziale'
        where exists (select 1 from public.match_player_stats x where x.fixture_id = ft.fixture_id)

        union all
        select ft.fixture_id, ft.fixture_date, 'match_team_stats'::text,
               c.fixture_id is not null, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_team_stats'
        where not exists (select 1 from public.match_team_stats x where x.fixture_id = ft.fixture_id)
        union all
        select ft.fixture_id, ft.fixture_date, 'match_team_stats'::text,
               true, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_team_stats' and c.esito = 'parziale'
        where exists (select 1 from public.match_team_stats x where x.fixture_id = ft.fixture_id)

        union all
        -- match_odds: SOLO snapshot_type = 'api_football' (le 'football_data_csv'
        -- sono un'altra fonte, stessa regola del vecchio corpo)
        select ft.fixture_id, ft.fixture_date, 'match_odds'::text,
               c.fixture_id is not null, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        left join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_odds'
        where not exists (select 1 from public.match_odds x
                           where x.fixture_id = ft.fixture_id and x.snapshot_type = 'api_football')
        union all
        select ft.fixture_id, ft.fixture_date, 'match_odds'::text,
               true, c.esito, c.vuoti, c.ultimo_controllo_at
        from ft
        join public.fixture_detail_checks c
               on c.fixture_id = ft.fixture_id and c.tabella = 'match_odds' and c.esito = 'parziale'
        where exists (select 1 from public.match_odds x
                       where x.fixture_id = ft.fixture_id and x.snapshot_type = 'api_football')
    ),
    -- Da qui in poi IDENTICO al vecchio corpo (nessuna modifica alla logica
    -- di classificazione ne' alle due righe "_partite").
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
$function$;

-- season_gaps_summary NON cambia (chiama season_detail_gaps via lateral,
-- nessuna modifica al suo corpo necessaria).
