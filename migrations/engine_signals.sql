-- engine_signals.sql
-- Firehose: UNA riga per ogni segnale emesso dai motori (PLACED / REJECTED / NO_SIGNAL),
-- con massima profondita' di informazioni + concordanza tra motori + esito reale.
-- Additivo: NON tocca signal_history ne' le sue viste. Esegui una volta in Supabase SQL Editor.
-- Idempotente: usa IF NOT EXISTS / CREATE OR REPLACE; rilanciabile senza danni.

CREATE TABLE IF NOT EXISTS engine_signals (
    signal_uid     TEXT        PRIMARY KEY,        -- "{engine}|{fixture_id}|{market}|{run_date}"  (target di on_conflict)
    run_date       DATE        NOT NULL,
    emitted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    engine         TEXT        NOT NULL,           -- 'poisson' | 'ml' | 'tacticai' ...  (NO CHECK: N motori)
    -- contesto partita
    fixture_id     BIGINT      NOT NULL,
    league_id      BIGINT,
    league_name    TEXT,
    season_year    SMALLINT,
    home_team      TEXT,
    away_team      TEXT,
    kickoff        TIMESTAMPTZ,
    -- mercato
    market         TEXT        NOT NULL,
    market_label   TEXT,
    direction      TEXT        DEFAULT 'back' CHECK (direction IN ('back', 'lay')),
    -- output modello (FLOAT: output del modello, precisione non finanziaria)
    prob_raw       FLOAT,                          -- prob prima della calibrazione (Poisson)
    prob_calibrated FLOAT,                         -- prob usata per la decisione
    edge           FLOAT,
    score          FLOAT,
    fair_odds      FLOAT,                          -- 1 / prob_calibrated
    implied_prob   FLOAT,                          -- 1 / odds
    cal_source     TEXT,
    trust_score    FLOAT,
    z_score        FLOAT,
    safety_vault   BOOLEAN,
    bss            FLOAT,
    reliability_multiplier FLOAT,
    -- dati di mercato / valori finanziari (NUMERIC: niente drift negli aggregati SUM)
    odds           NUMERIC,
    available_size NUMERIC,                         -- liquidita' alla miglior quota (NULL per lo storico)
    -- decisione
    status         TEXT        NOT NULL CHECK (status IN ('PLACED', 'REJECTED', 'NO_SIGNAL')),
    is_best        BOOLEAN,
    reject_filter  TEXT,                           -- categoria del filtro che ha scartato
    reject_detail  TEXT,                           -- testo originale del motivo
    stake          NUMERIC,
    -- concordanza vs l'altro motore (stessa fixture+mercato)
    concordant     BOOLEAN,
    other_engine   TEXT,
    other_engine_prob FLOAT,
    other_engine_status TEXT,
    agreement_strength FLOAT,                       -- 1 - |p_self - p_other|
    -- esito reale (popolato dal resolver). NOT NULL per le viste NULL-safe.
    -- NB: nessun CHECK su result: i valori reali del resolver includono emoji ('VINTO ✅','PERSO ❌').
    result         TEXT        NOT NULL DEFAULT 'PENDING',
    pnl            NUMERIC,
    closing_odds   NUMERIC,
    clv            FLOAT,
    goals_home     INT,
    goals_away     INT,
    ht_home        INT,
    ht_away        INT,
    -- provenienza
    backfilled     BOOLEAN     DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Indici. (Il PK su signal_uid e' gia' il target di on_conflict; nessun unique-index ridondante.)
CREATE INDEX IF NOT EXISTS idx_es_main    ON engine_signals (run_date, engine, status);  -- pattern analitico principale
CREATE INDEX IF NOT EXISTS idx_es_engine  ON engine_signals (engine, run_date);          -- filtro per solo motore
CREATE INDEX IF NOT EXISTS idx_es_status  ON engine_signals (status, run_date);          -- filtro per solo stato
CREATE INDEX IF NOT EXISTS idx_es_fixture ON engine_signals (fixture_id);
CREATE INDEX IF NOT EXISTS idx_es_market  ON engine_signals (market, status);
CREATE INDEX IF NOT EXISTS idx_es_league  ON engine_signals (league_id, market);
-- supporta le viste ROI (solo piazzati risolti)
CREATE INDEX IF NOT EXISTS idx_es_placed_resolved ON engine_signals (status, result)
    WHERE status = 'PLACED' AND result <> 'PENDING';

-- trigger updated_at (riusa la funzione gia' definita da signal_history.sql; ridefinita qui per
-- rendere la migration eseguibile in autonomia)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS set_updated_at_es ON engine_signals;
CREATE TRIGGER set_updated_at_es
    BEFORE UPDATE ON engine_signals
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ==========================================================================
-- VISTE ANALITICHE (additive: nuovi nomi v_es_*, non toccano le viste esistenti)
-- ==========================================================================

-- 1) Conteggio emissioni per motore x mercato x stato
CREATE OR REPLACE VIEW v_es_emission_by_engine_market AS
SELECT
    engine,
    market,
    MAX(market_label)                            AS market_label,
    COUNT(*) FILTER (WHERE status = 'PLACED')    AS n_placed,
    COUNT(*) FILTER (WHERE status = 'REJECTED')  AS n_rejected,
    COUNT(*) FILTER (WHERE status = 'NO_SIGNAL') AS n_no_signal,
    COUNT(*)                                     AS n_total
FROM engine_signals
GROUP BY engine, market
ORDER BY engine, n_total DESC;

-- 2) Imbuto degli scarti: dove i filtri tagliano di piu'
CREATE OR REPLACE VIEW v_es_reject_funnel AS
SELECT
    engine,
    reject_filter,
    COUNT(*)                                                     AS n,
    ROUND(AVG(prob_calibrated)::NUMERIC, 3)                      AS avg_prob,
    ROUND(AVG(edge)::NUMERIC, 4)                                 AS avg_edge,
    ROUND(AVG(odds)::NUMERIC, 2)                                 AS avg_odds
FROM engine_signals
WHERE status = 'REJECTED'
GROUP BY engine, reject_filter
ORDER BY engine, n DESC;

-- 3) ROI concordi vs non-concordi (solo segnali risolti e piazzati)
CREATE OR REPLACE VIEW v_es_concordance_roi AS
SELECT
    engine,
    concordant,
    COUNT(*)                                                     AS n_bets,
    SUM(CASE WHEN result LIKE 'VINTO%' THEN 1 ELSE 0 END)        AS n_won,
    ROUND((AVG(CASE WHEN result LIKE 'VINTO%' THEN 1.0 ELSE 0 END) * 100)::NUMERIC, 1) AS win_pct,
    ROUND(SUM(pnl)::NUMERIC, 1)                                  AS total_pnl,
    ROUND((SUM(pnl) / NULLIF(SUM(stake), 0) * 100)::NUMERIC, 2)  AS roi_pct
FROM engine_signals
WHERE status = 'PLACED' AND result IS DISTINCT FROM 'PENDING'
GROUP BY engine, concordant
ORDER BY engine, concordant;
