-- poisson_calibration.sql
-- Calibrazione Poisson CENTRALIZZATA nel DB — gemella di public.ml_post_calibration.
-- Porta i fattori di correzione per-lega (oggi in dynamic_cal.json, file git letto SOLO
-- da money_management/Sheets) dentro il database, cosi' anche il percorso DB → dashboard →
-- ventaglio puo' servire Poisson CALIBRATO, coerente con l'ML.
--
-- Additivo: NON tocca dynamic_cal.json ne' money_management (i Google Sheet continuano a
-- funzionare invariati). Esegui una volta in Supabase SQL Editor.
-- Idempotente: CREATE ... IF NOT EXISTS; rilanciabile senza danni.
--
-- STRUTTURA corrections (uguale concettualmente a dynamic_cal.json, ma una riga per lega):
--   { cal_key : { bin("0".."9") : correction_factor } }
--   cal_key  = mercato+lato gia' codificato (H/D/A, O15/U15, O25/U25, O35/U35,
--              BTTS/BTTS_NO, HT05/HT_U05, HT_H/HT_D/HT_A)
--   bin      = fascia di probabilita' grezza Poisson (0=[0-10%] ... 9=[90-100%])
--   cf       = hit_rate_reale / prob_media_modello  (clamp [0.2, 3.0])
--
-- CONSUMO (poisson_calibrator.py): legge 2 righe — quella della lega + la globale
--   (league_id IN (<lega>, 0)) e cerca lega → bin; se assente → globale → bin; se assente → cf=1.0.

CREATE TABLE IF NOT EXISTS poisson_calibration (
    league_id    BIGINT      PRIMARY KEY,            -- 0 = FALLBACK GLOBALE; >0 = per-lega
    corrections  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    min_n        INT,                                -- soglia campioni per bin usata in generazione
    total_fixtures INT,                              -- fixture storiche usate (audit; solo riga globale)
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE poisson_calibration IS
    'Fattori di calibrazione Poisson per-lega (+ globale league_id=0). Gemella di ml_post_calibration. Popolata da generate_dynamic_cal.py / load_poisson_calibration_to_db.py.';

-- trigger updated_at (riusa la funzione gia' definita dalle altre migration; ridefinita qui
-- per rendere la migration eseguibile in autonomia)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS set_updated_at_poisson_cal ON poisson_calibration;
CREATE TRIGGER set_updated_at_poisson_cal
    BEFORE UPDATE ON poisson_calibration
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
