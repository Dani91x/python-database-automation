-- Misura dell'UPSERT reale dei workflow (INSERT ... ON CONFLICT (fixture_id) DO UPDATE) con il trigger della
-- decisione 10 (revisione D-G del 10/10). PostgreSQL 16 usa-e-getta, MAI il DB vero; dati PICCOLI (3.000 righe,
-- JSON di ~2 KB) per non riempire il disco della macchina condivisa. Schema di test_g2_pg_sentinella.py.
TRUNCATE public.fixture_predictions;
INSERT INTO public.fixture_predictions (fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id)
SELECT g, g % 90, jsonb_build_object('lambda_home', 1.3, 'lambda_away', 1.1, 'pad', repeat('x', 1000)),
       json_build_object('inputs', json_build_object('lambda_home', 1.3, 'lambda_away', 1.1), 'pad', repeat('y', 1000)),
       g % 500, (g + 1) % 500
  FROM generate_series(1, 3000) g;
ANALYZE public.fixture_predictions;
CREATE TEMP TABLE prima AS SELECT fixture_id, nucleo_versione FROM public.fixture_predictions;
SELECT last_value AS sequenza_prima FROM public.nucleo_versione_dossier_seq;
\timing on
-- 1. 3.000 upsert IDENTICI con il trigger
INSERT INTO public.fixture_predictions AS f (fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id)
SELECT fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id FROM public.fixture_predictions
ON CONFLICT (fixture_id) DO UPDATE SET league_id = EXCLUDED.league_id, tactical_engine_json = EXCLUDED.tactical_engine_json,
    db_json_analisi = EXCLUDED.db_json_analisi, home_team_id = EXCLUDED.home_team_id, away_team_id = EXCLUDED.away_team_id;
-- 2. gli stessi 3.000 SENZA il trigger (riferimento)
ALTER TABLE public.fixture_predictions DISABLE TRIGGER trg_nucleo_versione_dossier;
INSERT INTO public.fixture_predictions AS f (fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id)
SELECT fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id FROM public.fixture_predictions
ON CONFLICT (fixture_id) DO UPDATE SET league_id = EXCLUDED.league_id, tactical_engine_json = EXCLUDED.tactical_engine_json,
    db_json_analisi = EXCLUDED.db_json_analisi, home_team_id = EXCLUDED.home_team_id, away_team_id = EXCLUDED.away_team_id;
ALTER TABLE public.fixture_predictions ENABLE TRIGGER trg_nucleo_versione_dossier;
-- 3. 3.000 upsert con il dossier CAMBIATO, con il trigger
INSERT INTO public.fixture_predictions AS f (fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id)
SELECT fixture_id, league_id, tactical_engine_json || '{"lambda_home": 1.4}', db_json_analisi, home_team_id, away_team_id
  FROM public.fixture_predictions
ON CONFLICT (fixture_id) DO UPDATE SET league_id = EXCLUDED.league_id, tactical_engine_json = EXCLUDED.tactical_engine_json,
    db_json_analisi = EXCLUDED.db_json_analisi, home_team_id = EXCLUDED.home_team_id, away_team_id = EXCLUDED.away_team_id;
\timing off
SELECT last_value AS sequenza_dopo FROM public.nucleo_versione_dossier_seq;
-- versioni sulle righe dopo il passo 1 (identico): uguali; dopo il passo 3: tutte nuove
SELECT count(*) FILTER (WHERE f.nucleo_versione IS DISTINCT FROM p.nucleo_versione) AS righe_con_versione_nuova,
       count(*) AS righe
  FROM public.fixture_predictions f JOIN prima p USING (fixture_id);
TRUNCATE public.fixture_predictions;
