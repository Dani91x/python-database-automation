-- ============================================================================
-- refresh_analytics_bets_range v2 (24/09/2026) -- STESSA firma, STESSO risultato
-- riga per riga su analytics_bets; il client (refresh_analytics_bets.py) non
-- cambia chiamata. DA APPLICARE A CURA DELL'UTENTE nello SQL editor (una sola
-- esecuzione dell'intero file; e' idempotente).
--
-- CAUSA DEL FALLIMENTO (run 35976004167 e precedenti; pg_stat_statements 24/09:
-- RPC scalare 70 chiamate, media 439 s, MAX 2.950 s; tutte le 6 finestre
-- 19->25/09 in "APIError dopo 600s"):
--   1) book_odds_cache ricostruita a OGNI chiamata per TUTTI i fixture del
--      giorno con il TRIPLO unnest di fixture_predictions.raw_json_odds (righe
--      ~14 KB, bookmaker x bet x value): il costo dominante, rifatto ogni notte
--      anche per le quote che non sono cambiate;
--   2) il sottoselect "distinct fixture_id from analytics_signals where kickoff
--      in [from,to)" ripetuto 3 volte (delete, dec, piv);
--   3) `SET statement_timeout = 0` sulla funzione: PostgREST applica le
--      impostazioni della funzione alla transazione della chiamata, quindi lo
--      statement NON aveva limite (il ruolo ha 8 s: e' proprio questo SET che
--      gli ha permesso di girare 49 minuti). Il client chiudeva a 600 s, il
--      server continuava, e la finestra del giorno dopo si accodava sulla
--      stessa istanza piccola (shared_buffers ~224 MB): tempi sempre crescenti.
--
-- v2:
--   (a) insieme dei fixture della finestra calcolato UNA volta in una tabella
--       temporanea `on commit drop` con PK (fixture_id), ANALYZE-ata, riusata
--       da book_odds_cache, delete, dec, piv;
--   (b) book_odds_cache ricostruita SOLO per i fixture della finestra la cui
--       sorgente e' cambiata dall'ultima costruzione. Impronta per fixture in
--       public.book_odds_cache_fonte: (updated_at di fixture_predictions,
--       pg_column_size(raw_json_odds)). pg_column_size NON decomprime il JSON
--       (legge la dimensione memorizzata): l'impronta costa zero letture del
--       JSON grosso, e cambia anche se uno scrittore aggiornasse raw_json_odds
--       SENZA toccare updated_at (quasi sempre la dimensione cambia). L'unnest
--       si fa solo per i fixture cambiati, leggendo raw_json_odds UNA volta,
--       via la tabella temporanea (mai piu' via fixture_date sul JSON);
--   (c) analytics_bets: `delete ... using` la temporanea + insert ... select con
--       dec/piv in JOIN sulla temporanea (stesse aggregazioni, stesse colonne,
--       stesso ordine: identico al v1);
--   (d) `SET statement_timeout = '600s'` e `SET lock_timeout = '30s'` sulla
--       FUNZIONE. NB: un `SET LOCAL statement_timeout` scritto DENTRO il corpo
--       NON limiterebbe lo statement gia' in corso (Postgres arma il timer
--       all'inizio dello statement di primo livello, cioe' la chiamata stessa);
--       e' l'impostazione della FUNZIONE che PostgREST applica PRIMA della
--       chiamata (come faceva col vecchio `= 0`), quindi e' quella che conta.
--       In piu' un controllo del tempo trascorso fra le fasi (600 s) solleva
--       57014 anche quando la funzione e' chiamata dallo SQL editor/da un'altra
--       funzione (dove il SET della funzione non riarma il timer);
--   (e) security definer, search_path = public, GRANT invariati.
--   + refresh_analytics_bets_range_diag(p_from, p_to): stesso lavoro, ritorna
--     righe e millisecondi per fase (per misurare dallo SQL editor). La scalare
--     e' un involucro della diag: un solo corpo, nessuna deriva fra le due.
--
-- DIFFERENZA DICHIARATA rispetto al v1 (non tocca analytics_bets): il v1
-- ricostruiva book_odds_cache anche per i fixture con fixture_date nella
-- finestra ma SENZA segnali in analytics_signals; quelle righe della cache non
-- le legge nessuno (book_odds_cache e' usata SOLO dall'insert di questa
-- funzione, verificato con grep su tutto il repo): il v2 le lascia come sono e
-- le ricostruisce quando il fixture entra nell'insieme di una finestra.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) Impronta della sorgente per fixture (tabella di controllo minima)
-- ----------------------------------------------------------------------------
create table if not exists public.book_odds_cache_fonte (
    fixture_id        bigint      primary key,
    fonte_updated_at  timestamptz,
    fonte_bytes       integer,
    costruita_at      timestamptz not null default now()
);
alter table public.book_odds_cache_fonte enable row level security;
revoke all on public.book_odds_cache_fonte from anon, authenticated;

-- ----------------------------------------------------------------------------
-- 2) Corpo unico: diag (righe e ms per fase)
-- ----------------------------------------------------------------------------
create or replace function public.refresh_analytics_bets_range_diag(p_from date, p_to date)
returns table (fase text, righe bigint, ms numeric)
language plpgsql
security definer
set search_path = public
set statement_timeout = '600s'
set lock_timeout = '30s'
as $fn$
declare
    v_t0    timestamptz := clock_timestamp();
    v_t     timestamptz;
    v_n     bigint;
    v_max   constant interval := interval '600 seconds';
begin
    -- (a) fixture della finestra: UNA volta, con PK, statistiche fresche
    v_t := clock_timestamp();
    drop table if exists pg_temp._rab_fx;
    create temp table _rab_fx (fixture_id bigint primary key) on commit drop;
    insert into pg_temp._rab_fx (fixture_id)
    select distinct s.fixture_id
      from public.analytics_signals s
     where s.kickoff >= p_from and s.kickoff < p_to
       and s.fixture_id is not null;
    get diagnostics v_n = row_count;
    analyze pg_temp._rab_fx;
    fase := 'fixture_finestra'; righe := v_n;
    ms := round(extract(epoch from clock_timestamp() - v_t) * 1000, 1);
    return next;

    -- (b1) fixture la cui sorgente quote e' cambiata (impronta senza leggere il JSON)
    v_t := clock_timestamp();
    drop table if exists pg_temp._rab_odds;
    create temp table _rab_odds (
        fixture_id       bigint primary key,
        fonte_updated_at timestamptz,
        fonte_bytes      integer
    ) on commit drop;
    insert into pg_temp._rab_odds (fixture_id, fonte_updated_at, fonte_bytes)
    select fp.fixture_id, fp.updated_at, pg_column_size(fp.raw_json_odds)
      from pg_temp._rab_fx fx
      join public.fixture_predictions fp on fp.fixture_id = fx.fixture_id
      left join public.book_odds_cache_fonte f on f.fixture_id = fp.fixture_id
     where f.fixture_id is null
        or f.fonte_updated_at is distinct from fp.updated_at
        or f.fonte_bytes is distinct from pg_column_size(fp.raw_json_odds);
    get diagnostics v_n = row_count;
    analyze pg_temp._rab_odds;
    fase := 'quote_da_ricostruire'; righe := v_n;
    ms := round(extract(epoch from clock_timestamp() - v_t) * 1000, 1);
    return next;
    if clock_timestamp() - v_t0 > v_max then
        raise exception 'refresh_analytics_bets_range(%, %): oltre 600 s', p_from, p_to
              using errcode = '57014';
    end if;

    -- (b2) book_odds_cache: delete + insert SOLO per i fixture cambiati
    v_t := clock_timestamp();
    delete from public.book_odds_cache c
     using pg_temp._rab_odds o
     where c.fixture_id = o.fixture_id;

    insert into public.book_odds_cache (fixture_id, market, selection, odd)
    select fp.fixture_id, mm.market, mm.selection, min((v->>'odd')::numeric)
      from pg_temp._rab_odds o
      join public.fixture_predictions fp on fp.fixture_id = o.fixture_id
        cross join lateral jsonb_array_elements(coalesce(fp.raw_json_odds->'bookmakers','[]'::jsonb)) bk
        cross join lateral jsonb_array_elements(coalesce(bk->'bets','[]'::jsonb)) bet
        cross join lateral jsonb_array_elements(coalesce(bet->'values','[]'::jsonb)) v
        cross join lateral (
            select
                case bet->>'name'
                    when 'Match Winner'                then '1x2'
                    when 'First Half Winner'           then 'ht_1x2'
                    when 'Both Teams Score'            then 'btts'
                    when 'Goals Over/Under'            then 'over_' || replace(regexp_replace(v->>'value','^(Over|Under) ',''),'.','_')
                    when 'Goals Over/Under First Half' then 'first_half_over_' || replace(regexp_replace(v->>'value','^(Over|Under) ',''),'.','_')
                end as market,
                case bet->>'name'
                    when 'Match Winner'      then case v->>'value' when 'Home' then 'H' when 'Draw' then 'D' when 'Away' then 'A' end
                    when 'First Half Winner' then case v->>'value' when 'Home' then 'H' when 'Draw' then 'D' when 'Away' then 'A' end
                    when 'Both Teams Score'  then v->>'value'
                    else split_part(v->>'value',' ',1)
                end as selection
        ) mm
     where fp.raw_json_odds is not null
       and mm.market is not null and mm.selection is not null
       and (v->>'odd') ~ '^[0-9]+(\.[0-9]+)?$'
     group by fp.fixture_id, mm.market, mm.selection;
    get diagnostics v_n = row_count;

    -- impronta registrata NELLA STESSA transazione: o cache+impronta, o niente.
    -- Se la sorgente cambia fra la lettura dell'impronta e l'unnest (READ
    -- COMMITTED), la cache e' piu' nuova dell'impronta: al giro dopo si
    -- ricostruisce di nuovo (direzione sicura, mai una cache vecchia creduta nuova).
    insert into public.book_odds_cache_fonte (fixture_id, fonte_updated_at, fonte_bytes, costruita_at)
    select o.fixture_id, o.fonte_updated_at, o.fonte_bytes, now()
      from pg_temp._rab_odds o
    on conflict (fixture_id) do update
       set fonte_updated_at = excluded.fonte_updated_at,
           fonte_bytes      = excluded.fonte_bytes,
           costruita_at     = excluded.costruita_at;
    fase := 'book_odds_cache_insert'; righe := v_n;
    ms := round(extract(epoch from clock_timestamp() - v_t) * 1000, 1);
    return next;
    if clock_timestamp() - v_t0 > v_max then
        raise exception 'refresh_analytics_bets_range(%, %): oltre 600 s', p_from, p_to
              using errcode = '57014';
    end if;

    -- (c1) analytics_bets: delete dei fixture della finestra
    v_t := clock_timestamp();
    delete from public.analytics_bets b
     using pg_temp._rab_fx fx
     where b.fixture_id = fx.fixture_id;
    get diagnostics v_n = row_count;
    fase := 'analytics_bets_delete'; righe := v_n;
    ms := round(extract(epoch from clock_timestamp() - v_t) * 1000, 1);
    return next;

    -- (c2) analytics_bets: insert (stesse aggregazioni e stesse colonne del v1;
    --      l'unica differenza e' il filtro: JOIN sulla temporanea invece del
    --      sottoselect ripetuto, stesso insieme di fixture)
    v_t := clock_timestamp();
    insert into public.analytics_bets
    with dec as (
        select d.fixture_id, d.market, d.selection,
            coalesce(
                max(d.odds) filter (where d.status = 'PLACED' and d.odds is not null),
                avg(d.odds) filter (where d.odds is not null)
            ) as odds_betfair,
            bool_or(d.status = 'PLACED') as placed,
            case when bool_or(d.status='PLACED') then 'PLACED'
                 when bool_or(d.status='REJECTED') then 'REJECTED'
                 when bool_or(d.status='NO_SIGNAL') then 'NO_SIGNAL' else null end as dec_status,
            max(d.edge) as edge, max(d.score) as score, max(d.implied_prob) as implied_prob,
            bool_or(coalesce(d.is_best,false)) as is_best,
            (array_remove(array_agg(d.reject_filter) filter (where d.reject_filter is not null), null))[1] as reject_filter
        from public.analytics_decisions d
        join pg_temp._rab_fx fx on fx.fixture_id = d.fixture_id
        group by d.fixture_id, d.market, d.selection
    ),
    piv as (
        select
            s.fixture_id,
            max(s.league_id) as league_id, max(s.league_name) as league_name,
            max(s.season_year) as season_year, max(s.home_team) as home_team,
            max(s.away_team) as away_team, max(s.kickoff) as kickoff,
            s.market, s.selection,
            max(s.line) as line,
            max(s.prob) filter (where s.engine='poisson') as poisson_prob,
            max(s.prob) filter (where s.engine='ml') as ml_prob,
            max(s.prob) filter (where s.engine='tacticai') as tacticai_prob,
            bool_and(s.oos_valid) filter (where s.engine='ml') as ml_oos_valid,
            bool_or(s.reliable) filter (where s.engine='ml') as ml_reliable,
            count(distinct s.engine)::int as n_engines_present,
            max(s.n_engines_agree) as n_engines_agree,
            max(s.consensus_prob) as consensus_prob,
            max(s.freq_baseline) as freq_baseline, max(s.freq_current) as freq_current,
            max(s.freq_deviation) as freq_deviation, max(s.delay_current) as delay_current,
            max(s.delay_record) as delay_record, max(s.delay_avg) as delay_avg,
            bool_or(s.settled) as settled, bool_or(s.hit) as hit,
            max(s.total_goals) as total_goals, max(s.goals_home) as goals_home,
            max(s.goals_away) as goals_away, max(s.ht_home) as ht_home, max(s.ht_away) as ht_away,
            max(s.first_goal_minute) as first_goal_minute
        from public.analytics_signals s
        join pg_temp._rab_fx fx on fx.fixture_id = s.fixture_id
        group by s.fixture_id, s.market, s.selection
    )
    select
        piv.fixture_id, piv.league_id, piv.league_name, piv.season_year,
        piv.home_team, piv.away_team, piv.kickoff, piv.market, piv.selection, piv.line,
        piv.poisson_prob, piv.ml_prob, piv.tacticai_prob, piv.ml_oos_valid, piv.ml_reliable,
        piv.n_engines_present, piv.n_engines_agree, piv.consensus_prob,
        piv.freq_baseline, piv.freq_current, piv.freq_deviation,
        piv.delay_current, piv.delay_record, piv.delay_avg,
        piv.settled, piv.hit, piv.total_goals, piv.goals_home, piv.goals_away,
        piv.ht_home, piv.ht_away, piv.first_goal_minute,
        d.odds_betfair, coalesce(d.placed,false), d.dec_status, d.edge, d.score,
        d.implied_prob, d.is_best, d.reject_filter,
        boc.odd as odds_book,
        case when (fp.flat_summary->>'prediction_under_over') ~ '^\+'
             then nullif(regexp_replace(fp.flat_summary->>'prediction_under_over','[^0-9.]','','g'),'')::numeric end as api_over_line
    from piv
    left join dec d on d.fixture_id=piv.fixture_id and d.market=piv.market and d.selection=piv.selection
    left join public.book_odds_cache boc on boc.fixture_id=piv.fixture_id and boc.market=piv.market and boc.selection=piv.selection
    left join public.fixture_predictions fp on fp.fixture_id=piv.fixture_id;
    get diagnostics v_n = row_count;
    fase := 'analytics_bets_insert'; righe := v_n;
    ms := round(extract(epoch from clock_timestamp() - v_t) * 1000, 1);
    return next;

    fase := 'totale'; righe := null;
    ms := round(extract(epoch from clock_timestamp() - v_t0) * 1000, 1);
    return next;
end;
$fn$;

-- ----------------------------------------------------------------------------
-- 3) La funzione chiamata dal client: STESSA firma (date, date) -> integer,
--    ritorna le righe scritte in analytics_bets (come il v1).
-- ----------------------------------------------------------------------------
create or replace function public.refresh_analytics_bets_range(p_from date, p_to date)
returns integer
language plpgsql
security definer
set search_path = public
set statement_timeout = '600s'
set lock_timeout = '30s'
as $fn$
declare v_n integer;
begin
    select d.righe::integer into v_n
      from public.refresh_analytics_bets_range_diag(p_from, p_to) d
     where d.fase = 'analytics_bets_insert';
    return coalesce(v_n, 0);
end;
$fn$;

-- NB: il wrapper refresh_analytics_bets(p_days) NON e' toccato (resta
-- `statement_timeout = 0`, copre fino a 7 giorni in UNA chiamata; l'action non
-- lo usa piu' dal 21/09). Chi lo chiamasse via PostgREST resta senza limite:
-- decisione dell'utente se allinearlo (alter function ... set statement_timeout).

-- GRANT: invariati per la scalare; la diag solo a service_role (scrive dati).
revoke all on function public.refresh_analytics_bets_range(date, date) from public, anon;
grant execute on function public.refresh_analytics_bets_range(date, date) to authenticated, service_role;
revoke all on function public.refresh_analytics_bets_range_diag(date, date) from public, anon, authenticated;
grant execute on function public.refresh_analytics_bets_range_diag(date, date) to service_role;
