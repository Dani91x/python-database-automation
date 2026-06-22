-- ============================================================================
-- TABELLA DECISIONI — layer decisionale del centro di controllo (2026-06-22)
-- ============================================================================
-- 1 riga = (decision_logic × engine × fixture × market × selection × run_date).
-- Separa la DECISIONE (piazza/scarta + valore + motivo) dalla PREVISIONE
-- (analytics_signals = bravura del motore). Una stessa previsione può essere
-- decisa da PIÙ logiche decisionali → si filtra per "tipologia di idea".
--
-- decision_logic: 'google_sheets' (logica attuale money_management/Sheets) e, in
-- futuro, altri MODELLI DECISIONALI (es. 'model_v2'). Così l'utente filtra le
-- piazzate per logica.
--
-- ESITO: `hit` è ri-settlato a 90' (coerente con analytics_signals, via la
-- previsione corrispondente); `result_ft` conserva l'esito a tempo pieno
-- originale di engine_signals per riferimento.
--
-- SICUREZZA (repo pubblica): RLS ON, nessuna policy, REVOKE da anon/authenticated
-- → accesso solo via RPC SECURITY DEFINER. Idempotente.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_decisions (
    id              BIGSERIAL    PRIMARY KEY,
    decision_uid    TEXT         NOT NULL UNIQUE,  -- "{logic}|{engine}|{fixture}|{market}|{selection}|{run_date}"
    decision_logic  TEXT         NOT NULL,         -- 'google_sheets' | strategie future

    -- link alla previsione (denormalizzato per filtri senza join)
    engine          TEXT         NOT NULL,
    fixture_id      BIGINT       NOT NULL,
    league_id       BIGINT,
    league_name     TEXT,
    season_year     SMALLINT,
    home_team       TEXT,
    away_team       TEXT,
    kickoff         TIMESTAMPTZ,
    market          TEXT         NOT NULL,         -- canonico (over_2_5, 1x2, ...)
    selection       TEXT         NOT NULL,         -- canonico (Over, H, Yes, ...)
    market_label    TEXT,
    run_date        DATE,

    -- decisione
    status          TEXT         NOT NULL CHECK (status IN ('PLACED','REJECTED','NO_SIGNAL')),
    is_best         BOOLEAN,
    reject_filter   TEXT,                          -- categoria scarto (es 'edge_below_threshold')
    reject_detail   TEXT,                          -- testo motivo (es 'edge +1.1% < min 5%')

    -- valore / probabilità al momento della decisione
    prob            NUMERIC,                       -- prob calibrata della selezione
    prob_raw        NUMERIC,
    edge            NUMERIC,                       -- prob - prob_implicita
    score           NUMERIC,
    implied_prob    NUMERIC,
    fair_odds       NUMERIC,
    odds            NUMERIC,                       -- quota reale (Betfair)
    stake           NUMERIC,
    pnl             NUMERIC,                       -- profitto/perdita
    closing_odds    NUMERIC,
    clv             NUMERIC,                       -- closing line value
    available_size  NUMERIC,                       -- liquidità
    cal_source      TEXT,

    -- metriche qualità motore (sparse storicamente, piene sui live)
    trust_score     NUMERIC,
    z_score         NUMERIC,
    bss             NUMERIC,
    reliability_multiplier NUMERIC,
    safety_vault    BOOLEAN,

    -- concordanza in dettaglio
    other_engine    TEXT,
    other_engine_prob NUMERIC,
    agreement_strength NUMERIC,

    -- esito
    result_ft       TEXT,                          -- esito tempo pieno originale (engine_signals)
    hit             BOOLEAN,                        -- ri-settlato a 90' (NULL se non settlabile)
    settled         BOOLEAN      NOT NULL DEFAULT FALSE,

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- indici: i pattern tipici filtrano per logica+status, motore+mercato, lega.
CREATE INDEX IF NOT EXISTS idx_ad_logic_status   ON analytics_decisions (decision_logic, status);
CREATE INDEX IF NOT EXISTS idx_ad_engine_market  ON analytics_decisions (engine, market, selection);
CREATE INDEX IF NOT EXISTS idx_ad_league         ON analytics_decisions (league_id);
CREATE INDEX IF NOT EXISTS idx_ad_fixture        ON analytics_decisions (fixture_id);
CREATE INDEX IF NOT EXISTS idx_ad_placed_settled ON analytics_decisions (decision_logic) WHERE status = 'PLACED' AND settled = TRUE;

-- SICUREZZA
ALTER TABLE analytics_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_decisions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE analytics_decisions FROM anon, authenticated;
