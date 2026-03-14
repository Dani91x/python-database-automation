-- signal_history.sql
-- Fix 16: Persistent signal history on Supabase.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS signal_history (
    signal_id    TEXT        PRIMARY KEY,
    fixture_id   BIGINT      NOT NULL,
    date         DATE        NOT NULL,
    track        TEXT        NOT NULL CHECK (track IN ('poisson', 'ml')),
    market       TEXT,
    market_label TEXT,
    prob         FLOAT,
    odds         FLOAT,
    edge         FLOAT,
    score        FLOAT,
    stake        FLOAT,
    result       TEXT        DEFAULT 'PENDING',
    pnl          FLOAT       DEFAULT 0,
    commission   FLOAT       DEFAULT 5.0,
    bss          FLOAT,
    closing_odds FLOAT,
    clv          FLOAT,
    goals_home   INT,
    goals_away   INT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_history_date  ON signal_history (date);
CREATE INDEX IF NOT EXISTS idx_signal_history_track ON signal_history (track, date);
CREATE INDEX IF NOT EXISTS idx_signal_history_fid   ON signal_history (fixture_id);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS set_updated_at ON signal_history;
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON signal_history
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE VIEW v_roi_by_track AS
SELECT
    track,
    COUNT(*)                                                      AS n_bets,
    SUM(CASE WHEN result LIKE 'VINTO%' THEN 1 ELSE 0 END)        AS n_won,
    ROUND(SUM(stake)::NUMERIC, 2)                                 AS total_staked,
    ROUND(SUM(pnl)::NUMERIC, 2)                                   AS total_pnl,
    ROUND((SUM(pnl) / NULLIF(SUM(stake), 0) * 100)::NUMERIC, 2)  AS roi_pct,
    ROUND((AVG(clv) * 100)::NUMERIC, 3)                           AS avg_clv_pct
FROM signal_history
WHERE result != 'PENDING'
GROUP BY track;

CREATE OR REPLACE VIEW v_roi_by_market AS
SELECT
    market_label,
    track,
    COUNT(*)                                                      AS n_bets,
    SUM(CASE WHEN result LIKE 'VINTO%' THEN 1 ELSE 0 END)        AS n_won,
    ROUND(SUM(pnl)::NUMERIC, 2)                                   AS total_pnl,
    ROUND((SUM(pnl) / NULLIF(SUM(stake), 0) * 100)::NUMERIC, 2)  AS roi_pct
FROM signal_history
WHERE result != 'PENDING'
GROUP BY market_label, track
ORDER BY roi_pct DESC;

CREATE OR REPLACE VIEW v_clv_summary AS
SELECT
    track,
    COUNT(*) FILTER (WHERE clv IS NOT NULL)                       AS n_with_clv,
    ROUND((AVG(clv) * 100)::NUMERIC, 3)                           AS avg_clv_pct,
    ROUND((STDDEV(clv) * 100)::NUMERIC, 3)                        AS stddev_clv_pct,
    CASE WHEN AVG(clv) > 0 THEN 'SKILL_SIGNAL' ELSE 'NO_EDGE' END AS verdict
FROM signal_history
WHERE result != 'PENDING'
GROUP BY track;
