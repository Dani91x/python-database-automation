-- misura del costo della RPC e del trigger su volumi realistici (PostgreSQL 16 usa-e-getta, MAI il DB vero)
TRUNCATE public.fixture_predictions, public.live_follow, public.omega_events, public.omega_transitions_state,
    public.omega_ht_ft_transitions, public.omega_build_jobs;
ALTER TABLE public.fixture_predictions DISABLE TRIGGER trg_nucleo_versione_dossier;
INSERT INTO public.fixture_predictions (fixture_id, league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id)
SELECT g, g % 900, jsonb_build_object('lambda_home', 1.3, 'lambda_away', 1.1, 'pad', repeat('x', 2000)),
       json_build_object('inputs', json_build_object('lambda_home', 1.3, 'lambda_away', 1.1), 'pad', repeat('y', 20000)),
       g % 5000, (g + 1) % 5000
  FROM generate_series(1, 200000) g;
ALTER TABLE public.fixture_predictions ENABLE TRIGGER trg_nucleo_versione_dossier;
INSERT INTO public.live_follow (event_id, fixture_id) SELECT 'e' || g, CASE WHEN g % 3 = 0 THEN NULL ELSE g END FROM generate_series(1, 60000) g;
INSERT INTO public.omega_events (event_id, fixture_id) SELECT 'e' || g, g FROM generate_series(1, 60000) g;
INSERT INTO public.omega_transitions_state (id, published_at) VALUES (1, now());
INSERT INTO public.omega_ht_ft_transitions (league_id, ht, ft, n)
SELECT l, h || '-' || a, f || '-' || b, 1 FROM generate_series(0, 1200) l, generate_series(0, 3) h, generate_series(0, 2) a,
       generate_series(0, 4) f, generate_series(0, 3) b;
INSERT INTO public.omega_build_jobs (job) VALUES ('minute'), ('v4');
ANALYZE;
SELECT count(*) AS righe_ht_ft FROM public.omega_ht_ft_transitions;
\timing on
-- 60 eventi seguiti, sentinella di Omega compresa: 20 ripetizioni
SET ROLE service_role;
SELECT sum(length(public.nucleo_sentinella_cloud(ARRAY(SELECT 'e' || (g * 997 % 60000 + 1) FROM generate_series(1, 60) g), true)::text))
  FROM generate_series(1, 20);
RESET ROLE;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT h.built_at FROM public.omega_ht_ft_transitions h ORDER BY h.built_at DESC LIMIT 1;
-- trigger: 5.000 riscritture identiche (nessuna versione nuova) e 5.000 con il dossier cambiato
UPDATE public.fixture_predictions SET tactical_engine_json = tactical_engine_json, db_json_analisi = db_json_analisi
 WHERE fixture_id <= 5000;
ALTER TABLE public.fixture_predictions DISABLE TRIGGER trg_nucleo_versione_dossier;
UPDATE public.fixture_predictions SET tactical_engine_json = tactical_engine_json, db_json_analisi = db_json_analisi
 WHERE fixture_id <= 5000;
ALTER TABLE public.fixture_predictions ENABLE TRIGGER trg_nucleo_versione_dossier;
UPDATE public.fixture_predictions SET tactical_engine_json = tactical_engine_json || '{"lambda_home": 1.4}'
 WHERE fixture_id <= 5000;
\timing off
SELECT count(*) FILTER (WHERE nucleo_versione IS NOT NULL) AS con_versione FROM public.fixture_predictions;
