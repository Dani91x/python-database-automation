-- =====================================================================
-- perf_indexes.sql — Indici per ridurre drasticamente il consumo di I/O.
-- =====================================================================
--
-- CONTESTO (2026-06-13)
-- L'istanza Supabase (Dani91x, ref dqbwaocvlzbxfrpacsac) ha esaurito il
-- budget di I/O del disco. Causa radice: il training ML legge la tabella
-- `matches` (milioni di righe) filtrando per (league_id, season_year) e per
-- fixture_id; senza indici adatti ogni lettura è un SEQ SCAN dell'intera
-- tabella. Moltiplicato per i 16 shard del cron ogni 4h => I/O saturato 24/7.
--
-- Questi indici NON cambiano in alcun modo i risultati delle query: le stesse
-- righe vengono restituite, ma lette con un index scan invece di un full scan.
-- L'I/O per run di training crolla di ordini di grandezza.
--
-- COME LANCIARLO
--   Supabase Dashboard -> SQL Editor -> incolla ed esegui.
--   Le righe CONCURRENTLY vanno eseguite UNA ALLA VOLTA (non in un blocco
--   transazionale): CREATE INDEX CONCURRENTLY non blocca le scritture (i
--   backfill notturni continuano a funzionare durante la creazione).
--   Se preferisci la via semplice e accetti un breve lock in scrittura sulla
--   tabella, togli "CONCURRENTLY" ed esegui tutto insieme.
--
-- VERIFICA PRIMA/DOPO (quali indici esistono già):
--   select tablename, indexname, indexdef
--   from pg_indexes
--   where tablename in ('matches','fixture_predictions','standings')
--   order by tablename, indexname;
-- =====================================================================

-- 1) TRAINING — il più importante. Filtri: eq(league_id) AND eq(season_year).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_matches_league_season
    ON public.matches (league_id, season_year);

-- 2) RESOLVE RISULTATI / HT — lookup per fixture_id (money_management +
--    db_adapter fetch_related_by_fixture_ids). Se fixture_id è già PK/UNIQUE
--    questo è un no-op grazie a IF NOT EXISTS.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_matches_fixture_id
    ON public.matches (fixture_id);

-- 3) REPORT GIORNALIERO — fixture_predictions filtrata per range di data
--    (gte fixture_date / lt fixture_date). Elimina il full scan nel report.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fixture_predictions_fixture_date
    ON public.fixture_predictions (fixture_date);

-- 4) REPORT — fetch_fixture_prediction_by_id e altri lookup per fixture_id.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fixture_predictions_fixture_id
    ON public.fixture_predictions (fixture_id);

-- 5) TRAINING — standings filtrate per (league_id, season_year).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_standings_league_season
    ON public.standings (league_id, season_year);

-- =====================================================================
-- Aggiorna le statistiche del planner così USA subito i nuovi indici.
-- (ANALYZE è leggero; VACUUM ANALYZE recupera anche spazio da tuple morte.)
-- =====================================================================
ANALYZE public.matches;
ANALYZE public.fixture_predictions;
ANALYZE public.standings;
