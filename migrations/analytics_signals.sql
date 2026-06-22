-- ============================================================================
-- TABELLA UNICA SEGNALI MOTORI — "centro di controllo / pagella" (2026-06-22)
-- ============================================================================
-- 1 riga = (engine × fixture × market × selection). Raccoglie in UN posto la
-- previsione di ogni motore + l'esito reale + lo snapshot di frequenza/ritardo
-- al momento della partita, per analisi multi-motore (direzione/timing/dinamica).
--
-- ENGINE (motori predittivi, scoring per hit-rate):
--   'api'      = API-Football (advice + percentuali; non sempre presente)
--   'poisson'  = Poisson calibrato (markets_calibrated)
--   'ml'       = ensemble ML calibrato (forward-only: leak-free solo da 2026-06-22)
--   'tacticai' = Dixon-Coles (in costruzione)
-- Frequenze e Ritardi NON sono righe-engine: sono CONTESTO di mercato, salvato
-- come snapshot per-riga (freq_*/delay_*) così da poter filtrare "quando il
-- mercato era in ritardo / sotto baseline". I valori provengono dagli RPC
-- certificati get_market_frequency / get_market_delays (stessa matematica).
--
-- ⚠️ CORRETTEZZA SETTLEMENT (soldi in gioco — coerente con market_frequency_rpc):
--   - insieme settlato = status_short IN ('FT','AET','PEN').
--   - punteggio 90': fulltime_* fonte PRIMARIA; fallback su goals_* SOLO per 'FT'.
--     AET/PEN senza fulltime_* -> 90' SCONOSCIUTO -> settled=false, hit=NULL
--     (riga conservata per contesto ma ESCLUSA dagli hit-rate).
--   - `hit` = direzione del motore azzeccata sul punteggio 90' (vedi populator).
--
-- SICUREZZA (repo pubblica): RLS abilitata, NESSUNA policy -> la tabella NON e'
-- leggibile dal client anon. L'accesso del frontend avviene SOLO via l'RPC
-- read-only aggregato public.get_analytics (SECURITY DEFINER). I grant diretti
-- ad anon/authenticated sono REVOCATI.
--
-- Idempotente: IF NOT EXISTS / CREATE OR REPLACE. Rilanciabile senza danni.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_signals (
    id              BIGSERIAL    PRIMARY KEY,
    signal_uid      TEXT         NOT NULL UNIQUE,   -- "{engine}|{fixture_id}|{market}|{selection}"
    engine          TEXT         NOT NULL CHECK (engine IN ('api','poisson','ml','tacticai')),
    generated_at    TIMESTAMPTZ,                    -- quando il motore ha previsto

    -- contesto partita
    fixture_id      BIGINT       NOT NULL,
    league_id       BIGINT,
    league_name     TEXT,
    season_year     SMALLINT,
    home_team       TEXT,
    away_team       TEXT,
    kickoff         TIMESTAMPTZ,

    -- mercato + previsione
    market          TEXT         NOT NULL,          -- 'over_2_5','1x2','btts','ht_1x2',...
    selection       TEXT         NOT NULL,          -- 'Over','Under','H','D','A','Yes','No',...
    line            NUMERIC,                         -- 2.5, 1.5, ... (NULL se non applicabile)
    direction       TEXT         NOT NULL DEFAULT 'back' CHECK (direction IN ('back','lay')),
    prob            NUMERIC,                         -- prob CALIBRATA del motore (0..1)
    prob_raw        NUMERIC,                         -- prob grezza pre-calibrazione (Poisson)
    fair_odds       NUMERIC,                         -- 1/prob

    -- snapshot CONTESTO al momento della partita (da RPC freq/delay certificati)
    freq_baseline   NUMERIC,                         -- frequenza storica del mercato (lega)
    freq_current    NUMERIC,                         -- media mobile al momento (mm10)
    freq_deviation  NUMERIC,                         -- freq_current - freq_baseline (+/-)
    delay_current   INTEGER,                         -- ritardo del mercato al momento
    delay_record    INTEGER,                         -- record storico di ritardo
    delay_avg       NUMERIC,                         -- ritardo medio storico

    -- concordanza fra motori (stessa fixture+market+selection)
    n_engines_agree SMALLINT,                        -- quanti motori concordano sulla direzione
    consensus_prob  NUMERIC,                         -- media prob dei motori concordi

    -- decisione / piazzamento (da engine_signals, se presente)
    placed          BOOLEAN      NOT NULL DEFAULT FALSE,
    status          TEXT,                            -- 'PLACED'|'REJECTED'|'NO_SIGNAL'

    -- esito reale (settlement 90' certificato — vedi header)
    settled         BOOLEAN      NOT NULL DEFAULT FALSE,
    result          TEXT,                            -- 'WON'|'LOST'|'VOID'|NULL(non settlato)
    hit             BOOLEAN,                         -- direzione azzeccata? (NULL se non settlato)
    goals_home      SMALLINT,
    goals_away      SMALLINT,
    total_goals     SMALLINT,
    ht_home         SMALLINT,
    ht_away         SMALLINT,
    first_goal_minute SMALLINT,                          -- timing: minuto del 1° gol (da match_events; NULL se non coperto)

    -- qualita' / validita'
    oos_valid       BOOLEAN      NOT NULL DEFAULT TRUE,  -- predizione out-of-sample pulita? (ML può essere false)
    reliable        BOOLEAN,                            -- ML: target affidabile (gate BSS/ECE)? NULL per altri motori

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- INDICI — l'aggregazione tipica filtra per engine+market+lega e raggruppa per
-- fascia di probabilita'; gli hit-rate contano solo righe settled.
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_as_engine_market_league
    ON analytics_signals (engine, market, league_id);
CREATE INDEX IF NOT EXISTS idx_as_settled
    ON analytics_signals (settled) WHERE settled = TRUE;
CREATE INDEX IF NOT EXISTS idx_as_league_season
    ON analytics_signals (league_id, season_year);
CREATE INDEX IF NOT EXISTS idx_as_kickoff
    ON analytics_signals (kickoff);
CREATE INDEX IF NOT EXISTS idx_as_fixture
    ON analytics_signals (fixture_id);
CREATE INDEX IF NOT EXISTS idx_as_market_selection
    ON analytics_signals (market, selection);

-- ----------------------------------------------------------------------------
-- SICUREZZA: RLS ON, nessuna policy -> tabella NON leggibile da anon/authenticated.
-- L'accesso passa solo dall'RPC SECURITY DEFINER get_analytics. La service_role
-- (usata dal populator backend) bypassa comunque la RLS.
-- ----------------------------------------------------------------------------
ALTER TABLE analytics_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_signals FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE analytics_signals FROM anon, authenticated;
