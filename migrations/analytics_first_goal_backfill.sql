-- ============================================================================
-- BACKFILL TIMING — first_goal_minute sullo storico (2026-06-22)
-- ============================================================================
-- first_goal_minute era NULL su tutte le righe storiche (il merge non lo popola;
-- il populator lo scrive solo sul forward). Qui: minuto del PRIMO gol per ogni
-- fixture, da match_events, applicato a tutte le righe della fixture in tabella.
--
-- 1 UPDATE server-side (GROUP BY su match_events + join). Solo righe NULL.
-- Idempotente. Pre-match-safe: il minuto del primo gol è un dato di ESITO della
-- partita → va usato SOLO per analisi retrospettiva (es. "se segna entro il 20'"),
-- mai come feature pre-match.
-- ============================================================================

with fg as (
    select fixture_id, min(minute) as first_goal
    from match_events
    where event_type = 'Goal' and minute is not null
    group by fixture_id
)
update analytics_signals s
   set first_goal_minute = fg.first_goal
  from fg
 where s.fixture_id = fg.fixture_id
   and s.first_goal_minute is null;
