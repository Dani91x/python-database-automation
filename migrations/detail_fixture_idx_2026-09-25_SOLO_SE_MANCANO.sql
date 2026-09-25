-- =====================================================================
-- detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql   (OPZIONALE)
-- =====================================================================
-- Da applicare SOLO se season_gaps_2026-09-25.sql ha stampato
-- "ATTENZIONE: public.<tabella> senza indice utile". Additiva.
--
-- Perche': season_detail_gaps fa una sonda NOT EXISTS per (partita, tabella)
-- su fixture_id. Con l'indice e' una lettura di pochi blocchi; senza, su
-- match_odds (~82M righe) sarebbe una lettura dell'intera tabella (57014 e
-- budget IO, come il 13/09).
--
-- COME: SQL Editor, UNA RIGA ALLA VOLTA (CONCURRENTLY non puo' stare in una
-- transazione), di giorno fuori dagli orari delle action. Creare l'indice
-- consuma IO una volta: attendere che l'istanza sia reattiva.
-- IF NOT EXISTS: se l'indice c'e' gia' con questo nome non fa nulla (ma un
-- indice equivalente con altro nome renderebbe questo un doppione: per questo
-- si applica SOLO se l'avviso e' comparso).
-- =====================================================================

create index concurrently if not exists idx_match_events_fixture_id       on public.match_events (fixture_id);
create index concurrently if not exists idx_match_lineups_fixture_id      on public.match_lineups (fixture_id);
create index concurrently if not exists idx_match_player_stats_fixture_id on public.match_player_stats (fixture_id);
create index concurrently if not exists idx_match_team_stats_fixture_id   on public.match_team_stats (fixture_id);
create index concurrently if not exists idx_match_odds_fixture_id         on public.match_odds (fixture_id);
