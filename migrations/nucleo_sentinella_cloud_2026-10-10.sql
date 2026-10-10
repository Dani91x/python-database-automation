-- nucleo_sentinella_cloud_2026-10-10.sql
--
-- Decisione 10 dell'utente (10/10/2026): "Tutta l'app in tempo reale per Betfair; il cloud
-- solo come backup; il resto sul DB locale". I dati che il cloud CALCOLA e l'app legge (il
-- dossier pre-partita di Mike in fixture_predictions e il ponte evento->fixture; le tabelle
-- delle transizioni di Omega ricostruite dal pg_cron delle 04:00 UTC) devono arrivare APPENA
-- il cloud ricalcola, non fino a 5 minuti dopo (oggi: ritento del dossier ogni 300 s,
-- sentinella di Omega riletta ogni 300 s).
--
-- Meccanismo (Betfair/nucleo/dati/cache_cloud.py, SentinellaCloud + Sorveglianza): UNA
-- chiamata leggera ogni 5 s a public.nucleo_sentinella_cloud, che risponde in una volta:
--   * "omega": le tre letture della sentinella di oggi (omega_transitions_state id=1,
--     built_at massimo di omega_ht_ft_transitions, ultimo omega_build_jobs), con le STESSE
--     colonne delle letture REST di cache_cloud.SorgenteOmega.sentinella;
--   * "eventi": per ogni evento seguito [event_id, fixture_id del ponte (live_follow, poi
--     omega_events: l'ordine di mike/db.fixture_id_for_event), riga presente in
--     fixture_predictions, nucleo_versione della riga].
-- Al cambio di una sola impronta l'app rilegge SOLO quel pezzo.
--
-- Contenuto (tutto ADDITIVO, nessun dato toccato, nessuna RPC di oggi cambiata):
--   1. sequenza public.nucleo_versione_dossier_seq;
--   2. colonna fixture_predictions.nucleo_versione BIGINT (NULL sulle righe esistenti: si
--      valorizza alla prima scrittura che cambia il dossier; nessun riempimento di massa);
--   3. trigger BEFORE INSERT OR UPDATE OF <le 5 colonne del dossier> su fixture_predictions:
--      nuova versione SOLO se cambia una colonna letta dal dossier (tactical_engine_json,
--      db_json_analisi, league_id, home_team_id, away_team_id); le scritture che non le
--      toccano (esiti, quote, ...) non accendono il trigger. Nessun DML: assegna NEW;
--   4. indice su omega_ht_ft_transitions(built_at): la lettura "built_at piu' recente" da
--      scansione della tabella diventa una discesa d'indice (serve anche alle letture REST
--      della sentinella di oggi);
--   5. RPC public.nucleo_sentinella_cloud(p_event_ids text[], p_omega boolean): STABLE,
--      solo SELECT, al massimo 500 eventi per chiamata, solo service_role.
--
-- Costo per il cloud: 12 chiamate al minuto per processo che la usa, ciascuna con 3 letture
-- di una riga per indice + 3 letture per chiave primaria per evento seguito (tipico 10-60
-- eventi); risposta ~60 byte per evento. Una nextval per riga di fixture_predictions il cui
-- dossier cambia davvero (le riscritture identiche non la consumano).
--
-- Senza questa migrazione l'app NON cambia comportamento: SentinellaCloud vede PGRST202
-- (funzione assente) e ripiega sulle letture REST di oggi (piu' richieste, cadenza 15 s),
-- riprovando la RPC ogni 10 minuti.
--
-- IDEMPOTENTE (si puo' rilanciare). La applica l'utente (SQL Editor, ruolo postgres).
-- Provata su PostgreSQL 16 usa-e-getta: Betfair/nucleo/dati/tests/test_g2_pg_sentinella.py
-- (variabile G1_PG_PSQL). Ritorno indietro in fondo al file.

-- ============================================================================
-- 1. sequenza delle versioni del dossier
-- ============================================================================
CREATE SEQUENCE IF NOT EXISTS public.nucleo_versione_dossier_seq AS BIGINT;
REVOKE ALL ON SEQUENCE public.nucleo_versione_dossier_seq FROM public, anon, authenticated;

-- ============================================================================
-- 2. colonna di versione (metadati soltanto: nessuna riscrittura della tabella)
-- ============================================================================
ALTER TABLE public.fixture_predictions ADD COLUMN IF NOT EXISTS nucleo_versione BIGINT;

-- ============================================================================
-- 3. trigger: nuova versione solo quando cambia cio' che il dossier legge
-- ============================================================================
CREATE OR REPLACE FUNCTION public.nucleo_versione_dossier()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    -- confronto in jsonb: identita' per jsonb, analisi per json, stringa per text
    -- (json non ha l'operatore di uguaglianza; jsonb si confronta senza riscriverlo)
    IF TG_OP = 'INSERT' THEN
        NEW.nucleo_versione := nextval('public.nucleo_versione_dossier_seq');
    ELSIF (to_jsonb(NEW.tactical_engine_json), to_jsonb(NEW.db_json_analisi),
           NEW.league_id, NEW.home_team_id, NEW.away_team_id)
          IS DISTINCT FROM
          (to_jsonb(OLD.tactical_engine_json), to_jsonb(OLD.db_json_analisi),
           OLD.league_id, OLD.home_team_id, OLD.away_team_id) THEN
        NEW.nucleo_versione := nextval('public.nucleo_versione_dossier_seq');
    ELSE
        -- stesso dossier: la versione resta (anche se chi scrive ne manda un'altra)
        NEW.nucleo_versione := OLD.nucleo_versione;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.nucleo_versione_dossier() FROM public, anon, authenticated;

DROP TRIGGER IF EXISTS trg_nucleo_versione_dossier ON public.fixture_predictions;
CREATE TRIGGER trg_nucleo_versione_dossier
    BEFORE INSERT OR UPDATE OF tactical_engine_json, db_json_analisi, league_id, home_team_id,
                               away_team_id, nucleo_versione
    ON public.fixture_predictions
    FOR EACH ROW EXECUTE FUNCTION public.nucleo_versione_dossier();

-- ============================================================================
-- 4. indice per "built_at piu' recente" della sentinella di Omega
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_omega_ht_ft_transitions_built_at
    ON public.omega_ht_ft_transitions (built_at);

-- ============================================================================
-- 5. la sentinella: UNA chiamata per giro
-- ============================================================================
CREATE OR REPLACE FUNCTION public.nucleo_sentinella_cloud(
    p_event_ids text[] DEFAULT '{}'::text[],
    p_omega     boolean DEFAULT true)
RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = public, pg_temp
AS $$
DECLARE
    v_eventi text[] := coalesce(p_event_ids, '{}'::text[]);
    v_omega  jsonb;
    v_ev     jsonb;
BEGIN
    IF cardinality(v_eventi) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = '22023',
            MESSAGE = 'nucleo_sentinella_cloud: al massimo 500 eventi per chiamata';
    END IF;
    IF coalesce(p_omega, true) THEN
        -- le stesse tre letture (e le stesse colonne) di cache_cloud.SorgenteOmega.sentinella
        v_omega := jsonb_build_array(
            coalesce((SELECT jsonb_agg(jsonb_build_object('updated_at', s.updated_at,
                                                          'published_at', s.published_at))
                        FROM public.omega_transitions_state s WHERE s.id = 1), '[]'::jsonb),
            coalesce((SELECT jsonb_agg(jsonb_build_object('built_at', t.built_at))
                        FROM (SELECT h.built_at FROM public.omega_ht_ft_transitions h
                               ORDER BY h.built_at DESC LIMIT 1) t), '[]'::jsonb),
            coalesce((SELECT jsonb_agg(jsonb_build_object('job', j.job, 'updated_at', j.updated_at))
                        FROM (SELECT b.job, b.updated_at FROM public.omega_build_jobs b
                               ORDER BY b.updated_at DESC LIMIT 1) j), '[]'::jsonb));
    END IF;
    -- ponte nell'ordine di mike/db.fixture_id_for_event: live_follow, poi omega_events
    SELECT coalesce(jsonb_agg(jsonb_build_array(x.e, x.fid, p.fixture_id IS NOT NULL, p.nucleo_versione)
                              ORDER BY x.e), '[]'::jsonb)
      INTO v_ev
      FROM (SELECT DISTINCT u.e,
                   coalesce((SELECT l.fixture_id FROM public.live_follow l WHERE l.event_id = u.e),
                            (SELECT o.fixture_id FROM public.omega_events o WHERE o.event_id = u.e)) AS fid
              FROM unnest(v_eventi) AS u(e)) x
      LEFT JOIN LATERAL (SELECT f.fixture_id, f.nucleo_versione
                           FROM public.fixture_predictions f
                          WHERE f.fixture_id = x.fid
                          ORDER BY f.nucleo_versione DESC NULLS LAST
                          LIMIT 1) p ON true;
    RETURN jsonb_build_object('formato', 1, 'omega', v_omega, 'eventi', v_ev);
END;
$$;
REVOKE ALL ON FUNCTION public.nucleo_sentinella_cloud(text[], boolean) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.nucleo_sentinella_cloud(text[], boolean) TO service_role;

-- ----------------------------------------------------------------------------
-- VERIFICA (dopo l'applicazione):
--   SELECT public.nucleo_sentinella_cloud(ARRAY['<event_id>'], true);
--   SELECT count(*) FILTER (WHERE nucleo_versione IS NOT NULL) FROM public.fixture_predictions;
-- RITORNO INDIETRO (nessun dato di oggi dipende da questi oggetti):
--   DROP FUNCTION IF EXISTS public.nucleo_sentinella_cloud(text[], boolean);
--   DROP TRIGGER IF EXISTS trg_nucleo_versione_dossier ON public.fixture_predictions;
--   DROP FUNCTION IF EXISTS public.nucleo_versione_dossier();
--   DROP INDEX IF EXISTS public.idx_omega_ht_ft_transitions_built_at;
--   ALTER TABLE public.fixture_predictions DROP COLUMN IF EXISTS nucleo_versione;
--   DROP SEQUENCE IF EXISTS public.nucleo_versione_dossier_seq;
-- ----------------------------------------------------------------------------
