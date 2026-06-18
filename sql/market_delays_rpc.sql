-- ============================================================================
-- MODULO "STUDIO RITARDI" — RPC di sola lettura
-- Riproduzione 1:1 del file Excel "STUDIO RITARDI_BASE_v5.0".
-- ============================================================================
-- Il file Excel calcola, partendo dal foglio DATI MATCH (lo storico di UNA
-- competizione, evento per evento dal piu' vecchio al piu' recente), per ogni
-- MERCATO scelto i RITARDI rispetto alla media storica del mercato.
--
-- Qui DATI MATCH e' ricostruito al volo dallo storico-lega della tabella
-- `matches` (stessa identica sorgente e stessa logica di settlement del modulo
-- Frequenze Mercati). Le colonne del nuovo DATI MATCH (quote ESCLUSE) sono:
--   B=EVENTO(progressivo)  C=HOME  D=AWAY  E=GC  F=GA  G=GCFH  H=GAFH
-- I gol di secondo tempo (GCSH/GASH) restano DERIVATI: GC-GCFH, GA-GAFH
-- (esattamente come le colonne L/M del foglio originale).
--
-- FORMULE RIPRODOTTE (per mercato):
--   W/L  = IF(condizione mercato, 1, 0)               -> esito binario
--   RIT  = IF(W/L=0, RIT_prec+1, 0)                   -> ritardo corrente
--   SUC  = IF(W/L=1, RIT_prec, "")                    -> lunghezza serie chiusa
--   n_occ           = SUM(W/L)
--   % mercato       = n_occ / n_eventi
--   QUOTA OGGETTIVA = MEDIA STORICA = 1 / %mercato = n_eventi / n_occ
--                     ("si verifica in media ogni Y partite")
--   RECORD          = MAX(SUC)                         -> serie storica massima
--   RITARDO ATTUALE = ultimo valore di RIT             -> da quante gare manca
--   MEDIA RIT.      = AVERAGEIF(RIT, "<>0")
--   distribuzione serie / ultime 10 serie / storico serie % /
--   conteggio < e > media / run sopra-media
--
-- EQUIVALENZA SQL DELLA MACCHINA A STATI (verificata, vedi test offline):
--   Sulla serie cronologica di esiti validi (idx = 1..M):
--     last_hit(i) = max idx j<=i con W/L=1  (0 se nessuno)
--     RIT(i)      = i - last_hit(i)
--     SUC(hit q)  = (q - prev_hit) - 1   con prev_hit = ultimo hit < q (0 se nessuno)
--   Identico, riga per riga, alle formule ricorsive del foglio.
--
-- SETTLEMENT 90': identico a get_market_frequency (fulltime_* primario, fallback
-- goals_* solo su status 'FT'; AET/PEN senza fulltime_* esclusi; whitelist status
-- IN ('FT','AET','PEN')).
-- COPERTURA HT: a differenza di get_market_frequency (che ESCLUDE le righe senza
-- primo tempo), qui si riproduce il foglio: HT vuoto = 0 (coalesce). Le righe
-- restano nella serie; la copertura HT e' comunque esposta in meta.ht_coverage_pct.
--
-- SICUREZZA: SECURITY DEFINER (matches non esposta ad anon), STABLE,
-- search_path fissato, input validati con whitelist.
-- ============================================================================

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
    v_uses_ht := p_market in ('ovpt','ggpt','ggst','pf1x','pf2x','pfx1','pfx2');

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
    elsif p_market in ('over','under','ovpt') then
        if p_target !~ '^[0-9]+(\.[0-9]+)?$' then
            raise exception 'linea % invalida: %', p_market, p_target; end if;
        v_line := p_target::numeric;
    elsif p_market in ('ggpt','ggst','pf1x','pf2x','pfx1','pfx2','x','ggov25') then
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
        -- FEDELTA' 1:1 COL FILE EXCEL: un evento = una riga di DATI MATCH, cioe'
        -- un risultato settlato con punteggio 90' noto (GC/GA = h/a non null).
        -- Sul PRIMO TEMPO l'Excel tratta la cella vuota come 0 nelle formule
        -- (blank>0 -> FALSE, blank=blank -> TRUE): si replica con coalesce(.,0).
        -- GCSH/GASH (2 tempo) DERIVATI: GC-GCFH, GA-GAFH (come colonne L/M).
        -- NB: divergenza VOLUTA da get_market_frequency, che invece ESCLUDE le
        -- righe senza HT. Qui si riproduce il comportamento letterale del foglio
        -- (rilevante solo su competizioni a bassa copertura HT, esposta in meta).
        select s.fixture_id, s.fixture_date, s.home_team_name, s.away_team_name,
               s.h, s.a, s.hh, s.ha,
            case
            when (s.h is null or s.a is null) then null   -- non e' un evento DATI MATCH
            else
              case p_market
                when 're'    then (s.h = v_re_h and s.a = v_re_a)::int
                when 'sge'   then ((s.h + s.a) = v_sge)::int
                when 'over'  then ((s.h + s.a)::numeric > v_line)::int
                when 'under' then ((s.h + s.a)::numeric < v_line)::int
                when 'ovpt'  then ((coalesce(s.hh,0) + coalesce(s.ha,0))::numeric > v_line)::int
                when 'ggpt'  then (coalesce(s.hh,0) > 0 and coalesce(s.ha,0) > 0)::int
                when 'ggst'  then ((s.h - coalesce(s.hh,0)) > 0 and (s.a - coalesce(s.ha,0)) > 0)::int
                when 'pf1x'  then (coalesce(s.hh,0) > coalesce(s.ha,0) and s.h = s.a)::int
                when 'pf2x'  then (coalesce(s.hh,0) < coalesce(s.ha,0) and s.h = s.a)::int
                when 'pfx1'  then (coalesce(s.hh,0) = coalesce(s.ha,0) and s.h > s.a)::int
                when 'pfx2'  then (coalesce(s.hh,0) = coalesce(s.ha,0) and s.h < s.a)::int
                when 'x'     then (s.h = s.a)::int
                when 'ggov25' then (s.h > 0 and s.a > 0 and (s.h + s.a) > 2)::int
              end
            end as outcome
        from scope s
    ),
    scope_stats as (
        select count(*)::int                                              as n_scope,
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
    distrib as (
        select v.k as len,
               (select count(*)::int from hits where hits.suc = v.k)      as occ_suc,
               (select count(*)::int from rit  where rit.rit_val = v.k)   as cnt_rit
        from generate_series(0, greatest(
                 coalesce((select max(suc) from hits), 0),
                 coalesce((select max(rit_val) from rit), 0))) as v(k)
    ),
    -- ultime 10 serie chiuse (piu' recenti), in ordine cronologico
    last10 as (
        select suc, hit_idx
        from hits order by hit_idx desc limit 10
    ),
    -- storico serie: lunghezze ordinate per frequenza (la piu' comune in testa)
    storico as (
        select suc as len, count(*)::int as cnt
        from hits group by suc
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
                                     then round(d.ritardo_attuale::numeric/d.media_storica,3) end
        ),
        'distribuzione_serie', coalesce((
            select jsonb_agg(jsonb_build_object('len',len,'occ_suc',occ_suc,'cnt_rit',cnt_rit) order by len)
            from distrib), '[]'::jsonb),
        'ultime_10_serie', coalesce((
            select jsonb_agg(suc order by hit_idx) from last10), '[]'::jsonb),
        'storico_serie', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'len', len, 'count', cnt,
                       'pct', case when d.n_occ>0 then round(cnt::numeric/d.n_occ,4) end)
                   order by cnt desc, len asc)
            from storico), '[]'::jsonb),
        'run_sopra_media', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'run_len', run_len, 'count', cnt,
                       'pct', round(cnt::numeric / nullif((select sum(cnt) from runs_hist),0), 4))
                   order by run_len asc)
            from runs_hist), '[]'::jsonb),
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

comment on function public.get_market_delays is
'Studio Ritardi (riproduzione 1:1 del file Excel): per (lega, mercato, target, intervallo) calcola la macchina W/L->RIT->SUC e tutte le statistiche dei ritardi (frequenza, media storica/quota oggettiva, ritardo attuale, record, media ritardi, distribuzione serie, ultime 10 serie, storico serie %, sotto/sopra media, run sopra-media). Sola lettura su matches, settlement 90 identico a get_market_frequency.';

-- ----------------------------------------------------------------------------
-- GRANT: eseguibile dal client anon del frontend (sola lettura aggregata)
-- ----------------------------------------------------------------------------
revoke all on function public.get_market_delays(integer,text,text,text,integer,integer) from public;
grant execute on function public.get_market_delays(integer,text,text,text,integer,integer) to anon, authenticated, service_role;
