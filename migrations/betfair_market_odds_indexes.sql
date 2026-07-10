-- ============================================================================
-- betfair_market_odds_indexes.sql — indici per purge/idempotenza quote complete
--
-- betfair_full_odds.py (step 4 di aggiorna_report.bat) fa:
--   • purge globale: DELETE ... WHERE run_date = :today
--   • idempotenza per-fixture: DELETE ... WHERE fixture_id = :fid AND run_date = :today
-- Senza indice su run_date questi DELETE fanno seqscan e lockano piu' righe del
-- necessario: sotto contesa (worker quote / stream) restano in attesa del lock e
-- scattano in statement timeout (57014). Gli indici sotto rendono i filtri diretti
-- e riducono lo scope dei lock.
--
-- Idempotente: CREATE INDEX IF NOT EXISTS. Additivo: nessun dato toccato.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_bmo_run_date
    ON public.betfair_market_odds (run_date);

CREATE INDEX IF NOT EXISTS idx_bmo_fixture_run
    ON public.betfair_market_odds (fixture_id, run_date);
