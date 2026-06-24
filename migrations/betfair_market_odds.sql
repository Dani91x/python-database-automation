-- betfair_market_odds.sql
-- Quote Betfair COMPLETE (tutti i mercati, back + lay) per fixture. Popolata da
-- betfair_full_odds.py (fetch ADDITIVO, separato dal report/Sheets/.bat).
-- Una riga per (fixture, mercato, selezione); back/lay = primi livelli [{price,size}].

CREATE TABLE IF NOT EXISTS betfair_market_odds (
    fixture_id    BIGINT      NOT NULL,
    market_name   TEXT        NOT NULL,            -- es. "Match Odds", "Over/Under 2.5 Goals", "Correct Score"
    selection     TEXT        NOT NULL,            -- nome runner Betfair (es. "Switzerland", "Over 2.5 Goals", "1 - 1")
    sort_priority INT,                             -- ordine runner Betfair (per mappare H/A/D)
    back          JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- [{ "price":2.58, "size":75.5 }, ...] migliori livelli
    lay           JSONB       NOT NULL DEFAULT '[]'::jsonb,
    market_id     TEXT,
    run_date      DATE        NOT NULL,
    captured_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (fixture_id, market_name, selection)
);

COMMENT ON TABLE betfair_market_odds IS
    'Quote Betfair complete (tutti i mercati, back+lay) per fixture. Popolata da betfair_full_odds.py (additivo, non tocca Sheets/MM).';

CREATE INDEX IF NOT EXISTS idx_bmo_fixture ON betfair_market_odds (fixture_id);

-- Non leggibile dai client diretti; accesso via RPC SECURITY DEFINER.
REVOKE ALL ON betfair_market_odds FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON betfair_market_odds TO service_role;
