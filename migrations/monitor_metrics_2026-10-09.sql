-- monitor_metrics_2026-10-09.sql
--
-- Tappa T0A della migrazione (ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md par. 1):
-- il modulo "Salute" (`Betfair/monitor/`). Ogni servizio dell'app con
-- MONITOR_SALUTE=1 nel .env scrive UNA riga ogni 30 s (contatori in memoria della
-- finestra: CPU, RAM, richieste al DB per tabella, REST Betfair per metodo,
-- transazioni, tratti in ms su istogrammi a secchi fissi). Di serie il monitor e'
-- SPENTO: senza questa migrazione nessun servizio cambia comportamento (con il
-- monitor acceso e la tabella assente lo scrittore avvisa ogni 10 minuti e tiene la
-- copia locale in `_logs/monitor/`).
--
-- Contenuto:
--   1. tabella public.monitor_metrics (+ indici); RLS attiva, lettura SOLO owner
--      (betfair_live_is_owner(), come le tabelle del blocco 2 di sicurezza del
--      24/09), scrittura solo service_role (i servizi Python);
--   2. RPC public.monitor_salute_stato(p_ore) per la pagina "Salute" dell'app:
--      l'ultima riga di ogni servizio + una serie a secchi di 5 minuti (UNA
--      chiamata, poche decine di KB, invece di migliaia di righe);
--   3. RPC public.monitor_vitalita_raccoglitori(): max(data) delle tabelle
--      scritte dai raccoglitori del cloud (G par. 1.5, G-045), una per volta, mai un
--      errore che ferma le altre (da PostgREST vale il tetto di 8 s del ruolo
--      authenticator per l'intera chiamata: G par. 7, i giganti sono esclusi);
--   4. public.monitor_metrics_pulizia(p_giorni): conservazione (la lancia
--      l'utente o un job che l'utente decide; nessun pg_cron creato qui).
--
-- Volume atteso: ~10 servizi x 2.880 righe/giorno = ~29.000 righe/giorno,
-- 1-2 KB l'una (~30-55 MB/giorno). Conservazione suggerita 14 giorni.
--
-- IDEMPOTENTE. La applica l'utente (SQL Editor, ruolo postgres).

-- ============================================================================
-- 1. tabella
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.monitor_metrics (
    id             BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL,               -- fine della finestra (orologio del PC)
    servizio       TEXT NOT NULL,                      -- runner-calcio, mike-service, ...
    sport          TEXT,                               -- calcio | tennis (mai mischiati)
    pid            INTEGER NOT NULL,
    host           TEXT,
    avvio_ts       TIMESTAMPTZ,                        -- avvio del monitor nel processo
    uptime_s       NUMERIC,
    cpu_pct        NUMERIC,                            -- % di UN core, media della finestra
    rss_mb         NUMERIC,
    db_richieste   INTEGER NOT NULL DEFAULT 0,         -- richieste PostgREST nella finestra
    rest_richieste INTEGER NOT NULL DEFAULT 0,         -- REST Betfair (sessione dell'APIClient)
    metriche       JSONB NOT NULL DEFAULT '{}'::jsonb, -- contatori, tratti, valori (v=1)
    creato_at      TIMESTAMPTZ NOT NULL DEFAULT now()  -- orologio del DB (scarto col PC)
);

CREATE INDEX IF NOT EXISTS idx_monitor_metrics_servizio_ts
    ON public.monitor_metrics (servizio, ts DESC);
CREATE INDEX IF NOT EXISTS idx_monitor_metrics_ts
    ON public.monitor_metrics (ts);

ALTER TABLE public.monitor_metrics ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.monitor_metrics FROM public, anon, authenticated;
GRANT ALL ON TABLE public.monitor_metrics TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.monitor_metrics_id_seq TO service_role;
DROP POLICY IF EXISTS monitor_metrics_select_owner ON public.monitor_metrics;
CREATE POLICY monitor_metrics_select_owner ON public.monitor_metrics
    FOR SELECT TO authenticated USING (public.betfair_live_is_owner());
GRANT SELECT ON TABLE public.monitor_metrics TO authenticated;

-- ============================================================================
-- 2. stato per la pagina "Salute"
-- ============================================================================
-- {"adesso": ts del DB,
--  "ultimi": [ultima riga per servizio nelle ultime p_ore],
--  "serie":  [{servizio, t (secchio di 5 min), cpu_media, cpu_max, rss_max,
--              db_richieste, rest_richieste, righe}],
--  "sistema": [{servizio, ts, sistema}] (ultime versioni/Windows lette)}
CREATE OR REPLACE FUNCTION public.monitor_salute_stato(p_ore integer DEFAULT 6)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_ore integer := GREATEST(1, LEAST(COALESCE(p_ore, 6), 48));
    v_da timestamptz := now() - make_interval(hours => v_ore);
    v_ultimi jsonb;
    v_serie jsonb;
    v_sistema jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT COALESCE(jsonb_agg(to_jsonb(u) ORDER BY u.servizio), '[]'::jsonb) INTO v_ultimi
      FROM (SELECT DISTINCT ON (m.servizio)
                   m.servizio, m.sport, m.ts, m.pid, m.host, m.avvio_ts, m.uptime_s,
                   m.cpu_pct, m.rss_mb, m.db_richieste, m.rest_richieste, m.metriche,
                   m.creato_at
              FROM public.monitor_metrics m
             WHERE m.ts >= v_da
             ORDER BY m.servizio, m.ts DESC) u;
    SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY s.servizio, s.t), '[]'::jsonb) INTO v_serie
      FROM (SELECT m.servizio,
                   date_bin('5 minutes', m.ts, TIMESTAMPTZ '2000-01-01') AS t,
                   round(avg(m.cpu_pct), 2) AS cpu_media,
                   round(max(m.cpu_pct), 2) AS cpu_max,
                   round(max(m.rss_mb), 1) AS rss_max,
                   sum(m.db_richieste) AS db_richieste,
                   sum(m.rest_richieste) AS rest_richieste,
                   count(*) AS righe
              FROM public.monitor_metrics m
             WHERE m.ts >= v_da
             GROUP BY 1, 2) s;
    -- versioni/Windows: lo scrittore le allega ogni 10 minuti, non a ogni riga
    SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.servizio), '[]'::jsonb) INTO v_sistema
      FROM (SELECT DISTINCT ON (m.servizio) m.servizio, m.ts, m.metriche -> 'sistema' AS sistema
              FROM public.monitor_metrics m
             WHERE m.ts >= v_da AND m.metriche ? 'sistema'
             ORDER BY m.servizio, m.ts DESC) x;
    RETURN jsonb_build_object('adesso', now(), 'ore', v_ore, 'ultimi', v_ultimi,
                              'serie', v_serie, 'sistema', v_sistema);
END;
$$;
REVOKE ALL ON FUNCTION public.monitor_salute_stato(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.monitor_salute_stato(integer) TO authenticated, service_role;

-- ============================================================================
-- 3. vitalita' dei raccoglitori (G par. 1.5; esclusi i giganti match_* e match_odds,
--    che vanno in timeout: G par. 7 "usare indice o pg_stat")
-- ============================================================================
CREATE OR REPLACE FUNCTION public.monitor_vitalita_raccoglitori()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    r record;
    v_max timestamptz;
    v_out jsonb := '[]'::jsonb;
BEGIN
    -- owner loggato o service_role (betfair_live_is_owner li comprende entrambi);
    -- dal SQL Editor la sessione e' di postgres
    IF NOT (public.betfair_live_is_owner() OR session_user = 'postgres') THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    FOR r IN SELECT * FROM (VALUES
        ('matches', 'updated_at'),
        ('fixture_predictions', 'updated_at'),
        ('analytics_signals', 'updated_at'),
        ('season_backfill_state', 'last_run_at'),
        ('standings', 'updated_at'),
        ('injuries', 'updated_at'),
        ('top_scorers', 'updated_at'),
        ('api_coverage_by_season', 'updated_at'),
        ('poisson_calibration', 'generated_at'),
        ('ml_post_calibration', 'generated_at'),
        ('ai_model_registry', 'trained_at'),
        ('hazard_atlas', 'generated_at'),
        ('omega_minute_transitions', 'built_at'),
        ('omega_ht_ft_transitions', 'built_at'),
        ('api_call_log', 'created_at')
    ) AS t(tabella, colonna)
    LOOP
        BEGIN
            EXECUTE format('SELECT max(%I)::timestamptz FROM public.%I', r.colonna, r.tabella)
               INTO v_max;
            v_out := v_out || jsonb_build_array(jsonb_build_object(
                'tabella', r.tabella, 'colonna', r.colonna, 'max', v_max,
                'eta_ore', CASE WHEN v_max IS NULL THEN NULL
                                ELSE round(extract(epoch FROM now() - v_max) / 3600.0, 1) END));
        EXCEPTION WHEN OTHERS THEN
            v_out := v_out || jsonb_build_array(jsonb_build_object(
                'tabella', r.tabella, 'colonna', r.colonna, 'max', NULL,
                'errore', left(SQLERRM, 200)));
        END;
    END LOOP;
    RETURN jsonb_build_object('adesso', now(), 'tabelle', v_out);
END;
$$;
REVOKE ALL ON FUNCTION public.monitor_vitalita_raccoglitori() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.monitor_vitalita_raccoglitori() TO authenticated, service_role;

-- ============================================================================
-- 4. conservazione (la lancia l'utente: SELECT public.monitor_metrics_pulizia(14);)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.monitor_metrics_pulizia(p_giorni integer DEFAULT 14)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_n bigint;
BEGIN
    IF COALESCE(p_giorni, 0) < 2 THEN
        RAISE EXCEPTION 'conservazione minima 2 giorni (il referto legge le ultime 24 h)';
    END IF;
    DELETE FROM public.monitor_metrics WHERE ts < now() - make_interval(days => p_giorni);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;
REVOKE ALL ON FUNCTION public.monitor_metrics_pulizia(integer) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.monitor_metrics_pulizia(integer) TO service_role;

-- ============================================================================
-- Verifica (dopo l'applicazione, SQL Editor):
--   SELECT count(*), max(ts) FROM public.monitor_metrics;              -- 0 finche' il monitor e' spento
--   SELECT public.monitor_vitalita_raccoglitori();                      -- dal SQL Editor (postgres)
--   SELECT relrowsecurity FROM pg_class WHERE oid = 'public.monitor_metrics'::regclass;  -- true
-- Ritorno: DROP FUNCTION public.monitor_metrics_pulizia(integer);
--          DROP FUNCTION public.monitor_vitalita_raccoglitori();
--          DROP FUNCTION public.monitor_salute_stato(integer);
--          DROP TABLE public.monitor_metrics;   (con MONITOR_SALUTE=0 nessuno la usa)
-- ============================================================================
