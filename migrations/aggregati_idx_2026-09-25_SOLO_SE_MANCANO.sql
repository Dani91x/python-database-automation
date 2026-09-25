-- =====================================================================
-- aggregati_idx_2026-09-25_SOLO_SE_MANCANO.sql   (OPZIONALE)
-- =====================================================================
-- Da applicare SOLO se season_aggregates_2026-09-25.sql ha stampato
-- "ATTENZIONE: public.<tabella> senza indice su (league_id, season_year)".
-- Additiva. UNA RIGA ALLA VOLTA (CONCURRENTLY non puo' stare in una
-- transazione), fuori dagli orari delle action. standings ha gia'
-- idx_standings_league_season (sql/perf_indexes.sql).
-- =====================================================================

create index concurrently if not exists idx_injuries_league_season    on public.injuries (league_id, season_year);
create index concurrently if not exists idx_top_scorers_league_season on public.top_scorers (league_id, season_year);
create index concurrently if not exists idx_top_assists_league_season on public.top_assists (league_id, season_year);
create index concurrently if not exists idx_top_cards_league_season   on public.top_cards (league_id, season_year);
