-- direction_pagella.sql
-- LA PAGELLA: hit-rate direzionale REALE per motore × mercato × selezione × lega × fascia-prob.
-- E' la fonte dell'AFFIDABILITA' del cruscotto "Direzione". Sostituisce ENGINE_GRID_REPORT.json
-- (file locale) con una tabella nel DB, popolata da build_direzione.py dallo storico settled.
--
-- league_id = 0  => GLOBALE (tutti i campionati);  > 0 => per-lega.
-- L'affidabilita' usa la riga per-lega con SHRINKAGE empirical-Bayes verso la globale
-- (lega con pochi dati -> conta il globale). Test ha mostrato per-lega ~ rumore => shrinkage
-- garantisce che non peggiori, e accumula lo storico per analisi future.
--
-- Additivo, idempotente: CREATE ... IF NOT EXISTS. Rilanciabile senza danni.

CREATE TABLE IF NOT EXISTS direction_pagella (
    engine       TEXT        NOT NULL,            -- poisson | ml | tacticai
    market       TEXT        NOT NULL,            -- 1x2, over_2_5, btts, ...
    selection    TEXT        NOT NULL,            -- H/D/A, Over/Under, Yes/No, ...
    league_id    BIGINT      NOT NULL,            -- 0 = GLOBALE; >0 = per-lega
    prob_bucket  TEXT        NOT NULL,            -- '<.30','.30-.40','.40-.50','.50-.60','.60-.70','>.70'
    n            INT         NOT NULL,            -- partite nello scope (settled)
    hits         INT         NOT NULL,            -- quante volte la selezione si e' avverata
    hit_rate     NUMERIC     NOT NULL,            -- hits / n  (l'affidabilita' grezza dello scope)
    base_rate    NUMERIC,                         -- frequenza base della (market,selection) nello scope
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (engine, market, selection, league_id, prob_bucket)
);

COMMENT ON TABLE direction_pagella IS
    'Pagella direzionale: hit-rate reale per motore x mercato x selezione x lega(0=globale) x fascia-prob. Fonte affidabilita del cruscotto Direzione. Popolata da build_direzione.py.';

-- NB: nessun indice aggiuntivo. La PRIMARY KEY (engine,market,selection,league_id,prob_bucket)
-- crea gia' un b-tree unique che copre i lookup di equality della RPC get_direction.
DROP INDEX IF EXISTS idx_pagella_lookup;   -- rimuove l'indice ridondante se creato da versioni precedenti

-- Sicurezza: dato di calibrazione, non leggibile da client diretti; accesso via RPC SECURITY DEFINER.
REVOKE ALL ON direction_pagella FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON direction_pagella TO service_role;
