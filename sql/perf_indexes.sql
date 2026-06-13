-- =====================================================================
-- perf_indexes.sql — Indici + manutenzione per ridurre il consumo di I/O.
-- =====================================================================
--
-- CONTESTO (2026-06-13)
-- L'istanza Supabase (Dani91x, ref dqbwaocvlzbxfrpacsac) ha esaurito il budget
-- di I/O del disco. Due cause:
--   1) Il training ML legge `matches` (milioni di righe) filtrando per
--      (league_id, season_year) e per fixture_id. Senza indici adatti ogni
--      lettura e' un SEQ SCAN dell'intera tabella; con 16 shard ogni 4h => I/O
--      del disco saturato 24/7.
--   2) `fixture_predictions` e' aggiornata pesantemente ogni giorno (resolve
--      risultati / evaluation) => BLOAT da tuple morte: persino "select id
--      limit 1" va in statement timeout. Serve VACUUM.
--
-- Gli indici NON cambiano i risultati delle query: stesse righe, ma lette con
-- index scan invece di full scan. L'I/O per run crolla di ordini di grandezza.
--
-- COME LANCIARLO
--   Supabase Dashboard -> SQL Editor.
--   ATTENDI che l'istanza sia di nuovo reattiva (budget I/O ricaricato) prima
--   di lanciare: creare un indice su una tabella enorme consuma I/O una volta.
--   Esegui PRIMA il blocco INDICI (puo' andare tutto insieme), POI il blocco
--   VACUUM (una riga alla volta: VACUUM non puo' stare in una transazione).
-- =====================================================================

-- ----------------------- BLOCCO 1: INDICI ----------------------------
-- (CREATE INDEX prende un lock in SCRITTURA sulla tabella durante la creazione;
--  i backfill girano di notte, quindi di giorno e' sicuro. Se vuoi zero lock,
--  aggiungi CONCURRENTLY ma allora esegui ogni CREATE da solo, fuori transazione.)

-- 1) TRAINING — il piu' importante. Filtri: eq(league_id) AND eq(season_year).
CREATE INDEX IF NOT EXISTS idx_matches_league_season
    ON public.matches (league_id, season_year);

-- 2) RESOLVE RISULTATI / HT — lookup per fixture_id. No-op se fixture_id e' gia' PK/UNIQUE.
CREATE INDEX IF NOT EXISTS idx_matches_fixture_id
    ON public.matches (fixture_id);

-- 3) REPORT GIORNALIERO — fixture_predictions per range di data (gte/lt fixture_date).
CREATE INDEX IF NOT EXISTS idx_fixture_predictions_fixture_date
    ON public.fixture_predictions (fixture_date);

-- 4) REPORT / training — fixture_predictions lookup per fixture_id.
CREATE INDEX IF NOT EXISTS idx_fixture_predictions_fixture_id
    ON public.fixture_predictions (fixture_id);

-- 5) TRAINING — standings per (league_id, season_year).
CREATE INDEX IF NOT EXISTS idx_standings_league_season
    ON public.standings (league_id, season_year);

-- Aggiorna le statistiche del planner cosi' usa subito i nuovi indici.
ANALYZE public.matches;
ANALYZE public.fixture_predictions;
ANALYZE public.standings;


-- ----------------------- BLOCCO 2: VACUUM ----------------------------
-- Esegui queste DOPO il blocco indici, UNA RIGA ALLA VOLTA (VACUUM non puo'
-- stare in un blocco transazionale). VACUUM (non FULL) e' online e sicuro:
-- rimuove le tuple morte cosi' le letture non le scansionano piu'.
-- Risolve il "limit 1" lentissimo su fixture_predictions.

VACUUM (ANALYZE) public.fixture_predictions;
VACUUM (ANALYZE) public.matches;

-- Se dopo il VACUUM normale fixture_predictions e' ancora gonfia e vuoi
-- recuperare spazio su disco (richiede lock esclusivo + spazio libero):
--   VACUUM FULL public.fixture_predictions;


-- ----------------------- VERIFICA ------------------------------------
-- Indici presenti:
--   select tablename, indexname from pg_indexes
--   where tablename in ('matches','fixture_predictions','standings')
--   order by tablename, indexname;
--
-- Bloat / tuple morte (dopo il VACUUM dead_tup deve crollare):
--   select relname, n_live_tup, n_dead_tup, last_autovacuum
--   from pg_stat_user_tables
--   where relname in ('fixture_predictions','matches') order by n_dead_tup desc;
--
-- Job pg_cron interni (verifica che non ci sia altro schedulato lato DB):
--   select * from cron.job;   -- errore "schema cron does not exist" = nessun pg_cron, ok
