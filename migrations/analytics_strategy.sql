-- ============================================================================
-- MOTORE STRATEGIE — fondazione (2026-06-23)
-- ============================================================================
-- Money-critical. Unità di analisi = LA SCOMMESSA: (fixture_id, market, selection).
-- I motori (poisson/ml/tacticai/api), snapshot freq/ritardi e quote sono COLONNE
-- di quella scommessa; il P&L si calcola UNA volta sola → nessun doppio conteggio.
--
-- Parte 1 (questo file, incrementale):
--   A) book_odds(raw_json_odds, market, selection) → quota bookmaker (fallback).
--   B) vista analytics_bets: pivot di analytics_signals (1 riga/motore) + collapse
--      di analytics_decisions (quota Betfair + edge/score/stato) → 1 riga/scommessa.
--
-- SNAPSHOT point-in-time (freq/ritardi) e prob dei motori sono PRE-MATCH (leak-free,
-- vedi analytics_market_stats.py / build_analytics_signals.py). hit/result/goals/
-- first_goal_minute sono ESITO (da misurare, NON filtri pre-bet).
--
-- Idempotente: CREATE OR REPLACE. Additivo, non distrugge nulla.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- A) book_odds: estrae la quota del bookmaker (raw_json_odds API-Football) per la
--    coppia canonica (market, selection). Fallback quando manca la quota Betfair.
--    Mappa canonico → (bet name, value) del payload bookmaker:
--      1x2            → "Match Winner"            Home/Draw/Away
--      ht_1x2         → "First Half Winner"       Home/Draw/Away
--      btts           → "Both Teams Score"        Yes/No
--      over_X_Y       → "Goals Over/Under"        "Over X.Y"/"Under X.Y"
--      first_half_over_X_Y → "Goals Over/Under First Half" "Over X.Y"/"Under X.Y"
--    Ritorna NULL se il payload non contiene quel mercato/selezione.
-- ----------------------------------------------------------------------------
create or replace function public.book_odds(p_raw jsonb, p_market text, p_selection text)
returns numeric
language sql
immutable
as $$
  with m as (
    select
      case
        when p_market = '1x2'                  then 'Match Winner'
        when p_market = 'ht_1x2'               then 'First Half Winner'
        when p_market = 'btts'                 then 'Both Teams Score'
        when p_market like 'first_half_over_%' then 'Goals Over/Under First Half'
        when p_market like 'over_%'            then 'Goals Over/Under'
      end as bet_name,
      case
        when p_market in ('1x2','ht_1x2') then
          case p_selection when 'H' then 'Home' when 'D' then 'Draw' when 'A' then 'Away' end
        when p_market = 'btts' then p_selection                       -- 'Yes'/'No'
        when p_market like 'first_half_over_%' then
          p_selection || ' ' || replace(substring(p_market from 'first_half_over_(.*)'), '_', '.')
        when p_market like 'over_%' then
          p_selection || ' ' || replace(substring(p_market from 'over_(.*)'), '_', '.')
      end as val
  )
  select min((v->>'odd')::numeric)
  from m,
       lateral jsonb_array_elements(coalesce(p_raw->'bookmakers','[]'::jsonb)) bk,
       lateral jsonb_array_elements(coalesce(bk->'bets','[]'::jsonb)) bet,
       lateral jsonb_array_elements(coalesce(bet->'values','[]'::jsonb)) v
  where m.bet_name is not null
    and m.val is not null
    and bet->>'name' = m.bet_name
    and v->>'value' = m.val
    and (v->>'odd') ~ '^[0-9]+(\.[0-9]+)?$';
$$;

-- Funzione interna (usata dalle RPC SECURITY DEFINER): non esposta al client.
revoke all on function public.book_odds(jsonb, text, text) from public, anon, authenticated;
grant execute on function public.book_odds(jsonb, text, text) to service_role;

-- ----------------------------------------------------------------------------
-- B) analytics_bets: 1 riga = (fixture_id, market, selection).
--    - motori in colonna (prob calibrata per engine, pivot da analytics_signals);
--    - contesto e snapshot freq/ritardi (costanti per scommessa → max());
--    - esito a 90' (hit/settled/goals/...);
--    - quota Betfair collapsata da analytics_decisions con la REGOLA UTENTE:
--        odds_betfair = quota della PIAZZATA se esiste, altrimenti MEDIA delle
--        quote registrate (placed E scartate hanno quota).
--    - edge/score/is_best/status/reject_filter dal layer decisioni (universo Betfair).
--    NB: API (flat_summary) e quota bookmaker (raw_json_odds) NON sono qui: vengono
--        agganciate dall'RPC via join a fixture_predictions sul set già filtrato.
-- ----------------------------------------------------------------------------
create or replace view public.analytics_bets as
with dec as (
    -- collapse analytics_decisions per scommessa (tutte le decision_logic/engine)
    select
        d.fixture_id, d.market, d.selection,
        -- regola quota: PLACED se c'è, altrimenti media delle quote registrate.
        -- Se più righe PLACED sulla STESSA scommessa (es. due motori) con quote diverse,
        -- prendo la PIÙ FAVOREVOLE (max) — scelta documentata; di norma c'è 1 sola PLACED.
        coalesce(
            max(d.odds) filter (where d.status = 'PLACED' and d.odds is not null),
            avg(d.odds) filter (where d.odds is not null)
        )                                                   as odds_betfair,
        bool_or(d.status = 'PLACED')                        as placed,
        -- stato sintetico della scommessa nel layer decisioni
        case
            when bool_or(d.status = 'PLACED')   then 'PLACED'
            when bool_or(d.status = 'REJECTED') then 'REJECTED'
            when bool_or(d.status = 'NO_SIGNAL') then 'NO_SIGNAL'
            else null
        end                                                 as dec_status,
        -- valore: edge/score migliori disponibili sulla scommessa (universo Betfair)
        max(d.edge)                                         as edge,
        max(d.score)                                        as score,
        max(d.implied_prob)                                 as implied_prob,
        bool_or(coalesce(d.is_best, false))                 as is_best,
        -- motivo scarto: il primo non-nullo (per analisi "cosa se non scartassi")
        (array_remove(array_agg(d.reject_filter) filter (where d.reject_filter is not null), null))[1]
                                                            as reject_filter
    from public.analytics_decisions d
    group by d.fixture_id, d.market, d.selection
)
select
    s.fixture_id, s.league_id, s.league_name, s.season_year,
    s.home_team, s.away_team, s.kickoff, s.market, s.selection,
    max(s.line)                                             as line,
    -- ---- MOTORI (prob calibrata per engine) ----
    max(s.prob) filter (where s.engine = 'poisson')         as poisson_prob,
    max(s.prob) filter (where s.engine = 'ml')              as ml_prob,
    max(s.prob) filter (where s.engine = 'tacticai')        as tacticai_prob,
    bool_and(s.oos_valid) filter (where s.engine = 'ml')    as ml_oos_valid,
    bool_or(s.reliable)   filter (where s.engine = 'ml')    as ml_reliable,
    count(distinct s.engine)                                as n_engines_present,
    max(s.n_engines_agree)                                  as n_engines_agree,
    max(s.consensus_prob)                                   as consensus_prob,
    -- ---- SNAPSHOT point-in-time (costante per scommessa) ----
    max(s.freq_baseline)                                    as freq_baseline,
    max(s.freq_current)                                     as freq_current,
    max(s.freq_deviation)                                   as freq_deviation,
    max(s.delay_current)                                    as delay_current,
    max(s.delay_record)                                     as delay_record,
    max(s.delay_avg)                                        as delay_avg,
    -- ---- ESITO a 90' (costante per scommessa) ----
    bool_or(s.settled)                                      as settled,
    bool_or(s.hit)                                          as hit,
    max(s.total_goals)                                      as total_goals,
    max(s.goals_home)                                       as goals_home,
    max(s.goals_away)                                       as goals_away,
    max(s.ht_home)                                          as ht_home,
    max(s.ht_away)                                          as ht_away,
    max(s.first_goal_minute)                                as first_goal_minute,
    -- ---- DECISIONE / QUOTA BETFAIR (collapse) ----
    d.odds_betfair,
    coalesce(d.placed, false)                               as placed,
    d.dec_status,
    d.edge, d.score, d.implied_prob, d.is_best, d.reject_filter
from public.analytics_signals s
left join dec d
    on d.fixture_id = s.fixture_id and d.market = s.market and d.selection = s.selection
group by
    s.fixture_id, s.league_id, s.league_name, s.season_year,
    s.home_team, s.away_team, s.kickoff, s.market, s.selection,
    d.odds_betfair, d.placed, d.dec_status, d.edge, d.score, d.implied_prob,
    d.is_best, d.reject_filter;

-- La vista eredita la RLS delle tabelle sottostanti; l'accesso client passa SOLO
-- dalle RPC SECURITY DEFINER (sotto). Nessun grant diretto ad anon/authenticated.
revoke all on public.analytics_bets from anon, authenticated;
