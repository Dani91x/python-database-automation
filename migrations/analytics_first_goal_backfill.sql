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

-- ⚠️ FIX H1: 'Goal' include i RIGORI SBAGLIATI (detail='Missed Penalty') → vanno
-- ESCLUSI (non sono gol). I rigori SEGNATI ('Penalty'), gli autogol ('Own Goal')
-- e i gol normali nei 90' VALGONO come gol e restano. `is distinct from` mantiene
-- anche i Goal con detail NULL.
-- 1) RESET: azzera tutto (così le partite il cui UNICO 'Goal' era un Missed Penalty
--    — es. 0-0 decise ai rigori — tornano NULL invece di restare col minuto sbagliato).
update analytics_signals set first_goal_minute = null where first_goal_minute is not null;
-- 2) BACKFILL con il filtro corretto.
with fg as (
    select fixture_id, min(minute) as first_goal
    from match_events
    where event_type = 'Goal'
      and detail is distinct from 'Missed Penalty'
      and minute is not null
    group by fixture_id
)
update analytics_signals s
   set first_goal_minute = fg.first_goal
  from fg
 where s.fixture_id = fg.fixture_id;
