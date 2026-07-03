-- ============================================================================
-- BULK UPDATE RISULTATI PREDICTIONS — RPC per predictions_results_backfill.py (2026-07-03)
-- ============================================================================
-- OBIETTIVO: ridurre i round-trip verso Supabase nel backfill risultati.
-- Prima: Prediction/predictions_results_backfill.py faceva 1 UPDATE HTTP per
-- fixture (N round-trip). Ora: il Python invia i payload gia' calcolati
-- (matematica di evaluate(), INVARIATA) a QUESTA RPC in chunk (~500), che fa
-- UN SOLO UPDATE ... FROM jsonb_to_recordset per chunk.
--
-- IDENTITA' DEI NUMERI: la RPC non cambia la matematica. Scrive le STESSE
-- colonne, con gli STESSI valori e lo STESSO WHERE (fixture_id = X) degli
-- UPDATE puntuali del metodo precedente. E' solo un canale di trasporto +
-- un JOIN set-based (pattern: flush_analytics_snap_staging).
--
-- SAFE (vincolo dello script): UPDATE-only. UPDATE ... FROM tocca SOLO le
-- righe gia' esistenti in fixture_predictions che matchano fixture_id: MAI
-- insert, quindi non puo' violare NOT NULL (es. status). Un payload il cui
-- fixture_id non esiste (piu') in tabella semplicemente non scrive nulla.
--
-- SICUREZZA: SECURITY DEFINER con search_path fisso (scrive su
-- fixture_predictions); REVOKE da anon/authenticated -> solo la service_role
-- del backend la chiama (come flush_analytics_snap_staging).
--
-- RITORNO: numero di righe di fixture_predictions effettivamente aggiornate
-- (ROW_COUNT), che lo script logga per chunk.
--
-- Idempotente: CREATE OR REPLACE FUNCTION. Rilanciabile.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.bulk_update_prediction_results(p_rows JSONB)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    -- Stessa lista di colonne e stessi valori del percorso riga-per-riga
    -- (update_prediction_row: payload meno fixture_id, WHERE fixture_id = X).
    -- JSON null -> SQL NULL, identico a quanto scriveva PostgREST.
    -- NB: il Python deduplica i payload per fixture_id (vince l'ultimo, come
    -- nel loop sequenziale), quindi qui ogni fixture_id compare al piu' una volta.
    UPDATE fixture_predictions fp
       SET result_status_short = u.result_status_short,
           result_home_goals   = u.result_home_goals,
           result_away_goals   = u.result_away_goals,
           result_total_goals  = u.result_total_goals,
           result_outcome      = u.result_outcome,
           hit_winner          = u.hit_winner,
           hit_win_or_draw     = u.hit_win_or_draw,
           hit_under_over      = u.hit_under_over,
           evaluated_at        = u.evaluated_at
      FROM jsonb_to_recordset(p_rows) AS u(
           fixture_id          BIGINT,
           result_status_short TEXT,
           result_home_goals   INTEGER,
           result_away_goals   INTEGER,
           result_total_goals  INTEGER,
           result_outcome      TEXT,
           hit_winner          BOOLEAN,
           hit_win_or_draw     BOOLEAN,
           hit_under_over      BOOLEAN,
           evaluated_at        TIMESTAMPTZ
      )
     WHERE fp.fixture_id = u.fixture_id;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    RETURN v_updated;
END;
$$;

-- la RPC e' SECURITY DEFINER: NON deve essere chiamabile da anon/authenticated
-- (scrive su fixture_predictions). Solo service_role.
REVOKE ALL ON FUNCTION public.bulk_update_prediction_results(JSONB) FROM anon, authenticated;
