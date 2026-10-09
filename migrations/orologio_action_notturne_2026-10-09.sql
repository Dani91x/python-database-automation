-- =====================================================================
-- OROLOGIO DELLE ACTION NOTTURNE (09/10/2026) - DA APPLICARE A CURA DELL'UTENTE
-- =====================================================================
-- NOTA (09/10/2026, ordine DEFINITIVO della catena, vedi
-- AUDIT_2026-10-09/orologio_action/ORDINE_DEFINITIVO.md): in questo file cambia SOLO
-- l'ordine dell'elenco di public._orologio_catena() e del commento qui sotto.
-- Ri-applicare il file e' FACOLTATIVO: la verifica delle 07:30 cerca la run di
-- oggi di ognuno dei 9 anelli, uno per uno, e NON dipende dall'ordine (l'ordine
-- cambia solo l'ordine dei nomi nel testo dell'allarme). Il file e' idempotente
-- (CREATE OR REPLACE, IF NOT EXISTS, unschedule prima di schedule).
-- Perche': il cron di GitHub (schedule:) parte con 5-6 ore di ritardo mediano;
-- il Daily delle 01:12 UTC partiva alle 07:00-07:30 UTC e trascinava 4-5 action
-- insieme sul DB (Postgres in crash 5 volte il 09/10 fra le 07:28 e le 07:43 UTC).
-- Ordine dell'utente: le action girano di NOTTE (app spenta), IN FILA, MAI due
-- volte. Quindi:
--   - nel repo NON resta nessun cron GitHub;
--   - QUI pg_cron lancia SOLO il primo anello (Daily Yesterday Backfill) alle
--     00:12 UTC (02:12 ora italiana), con catena=true, UNA volta al giorno
--     (guardia: tabella public.lanci_action, una riga per giorno e workflow);
--   - ogni anello lancia il successivo da GitHub (job passa-testimone,
--     .github/scripts/passa_testimone.sh). Catena:
--       1 Daily Yesterday Backfill -> 2 Leagues Mapping -> 3 Today Predictions Backfill ->
--       4 Predictions Results Backfill -> 5 Hazard Atlas -> 6 Seasons Catchup ->
--       7 Retrain ML -> 8 ML Post-Calibration ->
--       9 Weekly Poisson Calibration (solo il lunedi').
--   - due verifiche scrivono in public.live_alerts se qualcosa non va:
--       00:15 UTC  ACTION_NON_PARTITA        (GitHub non ha accettato il lancio)
--       07:30 UTC  richiesta a GitHub delle run di oggi
--       07:33 UTC  CATENA_NOTTURNA_INCOMPLETA (un anello manca, e' fallito o
--                  e' ancora in corso)
--
-- ---------------------------------------------------------------------
-- ISTRUZIONI PER L'UTENTE (nell'ordine, una volta sola)
-- ---------------------------------------------------------------------
-- (a) Su GitHub: Settings -> Developer settings -> Personal access tokens ->
--     Fine-grained tokens -> Generate new token.
--       Resource owner: Dani91x
--       Repository access: Only select repositories -> python-database-automation
--       Permissions -> Repository permissions -> Actions: Read and write
--         (Metadata: Read-only viene aggiunto da GitHub da solo)
--       Expiration: la piu' lunga ammessa (segnarsi la data: alla scadenza il
--         lancio fallisce e la verifica delle 00:15 lo scrive in live_alerts).
--     Copiare il token (si vede una volta sola).
-- (b) Nel SQL editor di Supabase, A MANO (MAI nel repo, MAI in un file):
--       select vault.create_secret('<TOKEN>', 'github_actions_dispatch',
--                                  'lancio notturno delle action');
--     Per cambiarlo in futuro (token scaduto o rigenerato):
--       select vault.update_secret(
--         (select id from vault.secrets where name = 'github_actions_dispatch'),
--         '<TOKEN NUOVO>');
-- (c) Applicare QUESTO file nel SQL editor (e' idempotente: si puo' rilanciare).
--
-- Lettura la mattina:
--   select * from public.lanci_action order by giorno desc, chiesto_at desc limit 20;
--   select id, level, code, message, created_at from public.live_alerts
--    where code in ('ACTION_NON_PARTITA','CATENA_NOTTURNA_INCOMPLETA')
--    order by created_at desc limit 20;
--   select jobname, schedule, command, active from cron.job where jobname like 'orologio%';
--   select j.jobname, d.status, d.return_message, d.start_time
--     from cron.job_run_details d join cron.job j on j.jobid = d.jobid
--    where j.jobname like 'orologio%' order by d.start_time desc limit 20;
--
-- Per togliere l'orologio (torna tutto a mano):
--   select cron.unschedule(jobname) from cron.job where jobname like 'orologio%';
--
-- Firma di net.http_post / net.http_get (pg_net 0.19.5, sql/pg_net.sql al tag
-- v0.19.5 di github.com/supabase/pg_net; 0.19.1-0.19.5 senza cambi alle firme):
--   net.http_post(url text, body jsonb default '{}', params jsonb default '{}',
--                 headers jsonb default '{"Content-Type": "application/json"}',
--                 timeout_milliseconds int default 5000) returns bigint
--   net.http_get(url text, params jsonb default '{}', headers jsonb default '{}',
--                timeout_milliseconds int default 5000) returns bigint
--   Risposte in net._http_response(id, status_code, content_type, headers,
--   content, timed_out, error_msg, created), conservate 6 ore. La richiesta parte
--   DOPO il commit della transazione (coda net.http_request_queue).
-- Dispatch GitHub (docs REST "Create a workflow dispatch event", API 2022-11-28):
--   POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches
--   body {"ref": "...", "inputs": {...}}; senza return_run_details risponde
--   204 No Content (con return_run_details=true risponde 200: accettati entrambi).
-- Nessun segreto in questo file: il token sta SOLO nel Vault.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0) prerequisiti: pg_cron, pg_net e supabase_vault devono esserci
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RAISE EXCEPTION 'pg_cron non installato: Database -> Extensions -> pg_cron';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_net') THEN
        RAISE EXCEPTION 'pg_net non installato: Database -> Extensions -> pg_net';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'supabase_vault') THEN
        RAISE EXCEPTION 'supabase_vault non installato: Database -> Extensions -> supabase_vault';
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- 1) GUARDIA contro il doppio lancio: una riga per (giorno UTC, workflow).
--    Se la riga c'e' gia', nessuna chiamata a GitHub. La riga
--    'verifica_catena' fa da guardia (e da registro) della verifica delle 07:30.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.lanci_action (
    giorno         date        NOT NULL,
    workflow_file  text        NOT NULL,
    chiesto_at     timestamptz NOT NULL DEFAULT now(),
    request_id     bigint,                 -- id della richiesta pg_net
    esito_http     int,                    -- status HTTP letto dalla verifica
    errore         text,                   -- motivo leggibile se qualcosa non va
    PRIMARY KEY (giorno, workflow_file)
);

COMMENT ON TABLE public.lanci_action IS
    'Orologio notturno delle action (09/10/2026): una riga per giorno UTC e workflow lanciato da pg_cron = guardia contro il doppio lancio. Riga verifica_catena = verifica delle 07:30 UTC.';

-- solo il server (postgres / service_role); l'app non ne ha bisogno
ALTER TABLE public.lanci_action ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lanci_action FROM anon, authenticated;


-- ---------------------------------------------------------------------
-- 2) aiuti interni
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public._orologio_allarme(p_level text, p_code text, p_message text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    INSERT INTO public.live_alerts (level, code, message)
    VALUES (p_level, p_code, p_message);
END;
$$;

-- token dal Vault (NULL se assente); mai stampato, mai salvato in tabelle nostre
CREATE OR REPLACE FUNCTION public._orologio_token()
RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT nullif(btrim(ds.decrypted_secret), '')
      FROM vault.decrypted_secrets ds
     WHERE ds.name = 'github_actions_dispatch'
     LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public._orologio_intestazioni(p_token text)
RETURNS jsonb
LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'Authorization',        'Bearer ' || p_token,
        'Accept',               'application/vnd.github+json',
        'X-GitHub-Api-Version', '2022-11-28',
        'User-Agent',           'python-database-automation-orologio',
        'Content-Type',         'application/json');
$$;

-- elenco UNICO degli anelli, nell'ordine della catena (usato dalla verifica)
CREATE OR REPLACE FUNCTION public._orologio_catena()
RETURNS text[]
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp
AS $$
    SELECT ARRAY[
        'daily_yesterday_backfill.yml',
        'leagues_mapper.yml',
        'today_predictions_backfill.yml',
        'predictions_results_backfill.yml',
        'hazard_atlas.yml',
        'seasons_catchup.yml',
        'retrain_models.yml',
        'ml_calibration.yml',
        'weekly_poisson_calibration.yml'
    ]::text[];
$$;


-- ---------------------------------------------------------------------
-- 3) lancia_action: chiede a GitHub di far partire UN workflow, UNA volta al
--    giorno. Ritorna un testo che dice cosa ha fatto (si legge anche in
--    cron.job_run_details.return_message).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.lancia_action(
    workflow_file text,
    inputs jsonb DEFAULT '{"catena": "true"}'::jsonb
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
-- il parametro si chiama come la colonna: nelle query vince la COLONNA, il
-- parametro si legge solo qualificato (lancia_action.workflow_file -> v_file)
#variable_conflict use_column
DECLARE
    v_giorno date := (now() AT TIME ZONE 'UTC')::date;
    v_file   text := lancia_action.workflow_file;
    v_input  jsonb := lancia_action.inputs;
    v_token  text;
    v_req    bigint;
BEGIN
    IF v_file IS NULL OR v_file !~ '^[a-z0-9_]+\.yml$' THEN
        RAISE EXCEPTION 'lancia_action: nome di workflow non valido: %', v_file;
    END IF;

    -- GUARDIA: la riga del giorno si inserisce UNA volta; se c'e' gia', stop.
    -- (vincolo per nome: niente ambiguita' fra parametro e colonna)
    INSERT INTO public.lanci_action (giorno, workflow_file)
    VALUES (v_giorno, v_file)
    ON CONFLICT ON CONSTRAINT lanci_action_pkey DO NOTHING;
    IF NOT FOUND THEN
        RETURN format('%s gia'' chiesto oggi (%s): nessuna chiamata', v_file, v_giorno);
    END IF;

    v_token := public._orologio_token();
    IF v_token IS NULL THEN
        UPDATE public.lanci_action
           SET errore = 'token assente nel Vault (github_actions_dispatch): nessuna chiamata'
         WHERE lanci_action.giorno = v_giorno AND lanci_action.workflow_file = v_file;
        PERFORM public._orologio_allarme('CRITICAL', 'ACTION_NON_PARTITA',
            format('Orologio notturno: %s NON lanciato il %s: token GitHub assente nel Vault '
                   '(segreto github_actions_dispatch). Crearlo come scritto in '
                   'migrations/orologio_action_notturne_2026-10-09.sql, poi lanciare a mano '
                   'il workflow da GitHub con catena=true.', v_file, v_giorno));
        RETURN 'token assente: allarme scritto';
    END IF;

    BEGIN
        v_req := net.http_post(
            url := format('https://api.github.com/repos/%s/actions/workflows/%s/dispatches',
                          'Dani91x/python-database-automation', v_file),
            body := jsonb_build_object('ref', 'master', 'inputs', coalesce(v_input, '{}'::jsonb)),
            params := '{}'::jsonb,
            headers := public._orologio_intestazioni(v_token),
            timeout_milliseconds := 20000
        );
    EXCEPTION WHEN OTHERS THEN
        UPDATE public.lanci_action
           SET errore = left('richiesta pg_net non accodata: ' || SQLERRM, 500)
         WHERE giorno = v_giorno AND lanci_action.workflow_file = v_file;
        PERFORM public._orologio_allarme('CRITICAL', 'ACTION_NON_PARTITA',
            left(format('Orologio notturno: %s NON lanciato il %s: richiesta pg_net non '
                        'accodata (%s). Lanciare a mano da GitHub con catena=true.',
                        v_file, v_giorno, SQLERRM), 1000));
        RETURN 'pg_net in errore: allarme scritto';
    END;

    UPDATE public.lanci_action
       SET request_id = v_req
     WHERE giorno = v_giorno AND lanci_action.workflow_file = v_file;
    RETURN format('%s chiesto a GitHub (pg_net request_id %s)', v_file, v_req);
END;
$$;


-- ---------------------------------------------------------------------
-- 4) verifica_lancio_action (00:15 UTC): legge la risposta di GitHub per i
--    lanci di oggi non ancora verificati. 204 (o 200) = accettato; altro, o
--    nessuna risposta, o nessun lancio chiesto = allarme ACTION_NON_PARTITA.
--    Rilanciabile: tocca solo le righe non ancora verificate.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.verifica_lancio_action()
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_giorno date := (now() AT TIME ZONE 'UTC')::date;
    r        record;
    v_trovata boolean;
    v_status int;
    v_timeout boolean;
    v_errmsg text;
    v_corpo  text;
    v_motivo text;
    v_ok     int := 0;
    v_ko     int := 0;
BEGIN
    -- l'orologio non ha nemmeno chiesto il primo anello (pg_cron fermo?)
    IF NOT EXISTS (SELECT 1 FROM public.lanci_action
                    WHERE giorno = v_giorno AND workflow_file = 'daily_yesterday_backfill.yml') THEN
        PERFORM public._orologio_allarme('CRITICAL', 'ACTION_NON_PARTITA',
            format('Orologio notturno: nessuna richiesta di lancio del Daily il %s '
                   '(job pg_cron orologio_daily non partito?). Lanciare a mano '
                   'daily_yesterday_backfill.yml da GitHub con catena=true.', v_giorno));
        v_ko := v_ko + 1;
    END IF;

    FOR r IN
        SELECT * FROM public.lanci_action
         WHERE giorno = v_giorno
           AND workflow_file LIKE '%.yml'
           AND esito_http IS NULL
           AND errore IS NULL          -- gli errori gia' scritti hanno gia' il loro allarme
         ORDER BY chiesto_at
    LOOP
        v_motivo := NULL;
        v_status := NULL; v_timeout := NULL; v_errmsg := NULL; v_corpo := NULL;
        IF r.request_id IS NULL THEN
            v_motivo := 'nessuna richiesta pg_net registrata';
        ELSE
            SELECT true, h.status_code, h.timed_out, h.error_msg, h.content
              INTO v_trovata, v_status, v_timeout, v_errmsg, v_corpo
              FROM net._http_response h
             WHERE h.id = r.request_id;
            IF NOT coalesce(v_trovata, false) THEN
                v_motivo := format('nessuna risposta di pg_net (request_id %s) dopo %s min',
                                   r.request_id,
                                   round(extract(epoch FROM now() - r.chiesto_at) / 60.0));
            ELSIF v_status IN (200, 204) THEN
                UPDATE public.lanci_action SET esito_http = v_status
                 WHERE giorno = r.giorno AND workflow_file = r.workflow_file;
                v_ok := v_ok + 1;
                v_trovata := NULL;
                CONTINUE;
            ELSE
                v_motivo := format('HTTP %s%s: %s',
                                   coalesce(v_status::text, 'nessuno'),
                                   CASE WHEN v_timeout THEN ' (timeout)' ELSE '' END,
                                   left(coalesce(v_errmsg, v_corpo, ''), 300));
            END IF;
            v_trovata := NULL;
        END IF;

        UPDATE public.lanci_action
           SET esito_http = v_status,
               errore = left(v_motivo, 500)
         WHERE giorno = r.giorno AND workflow_file = r.workflow_file;
        PERFORM public._orologio_allarme('CRITICAL', 'ACTION_NON_PARTITA',
            left(format('Orologio notturno: GitHub NON ha accettato il lancio di %s il %s: %s. '
                        '(401/403 = token scaduto o senza permesso Actions: Read and write; '
                        '404 = repo o file errato; 422 = input non valido.) Lanciare a mano '
                        'da GitHub con catena=true.', r.workflow_file, r.giorno, v_motivo), 1000));
        v_ko := v_ko + 1;
    END LOOP;

    RETURN format('verifica lanci del %s: %s accettati, %s problemi', v_giorno, v_ok, v_ko);
END;
$$;


-- ---------------------------------------------------------------------
-- 5) verifica della catena (07:30 richiesta, 07:33 lettura). pg_net e'
--    asincrona: la richiesta si fa in un job e la risposta si legge nel
--    successivo. Guardia per giorno: riga (giorno, 'verifica_catena').
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.verifica_catena_notturna()
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_giorno date := (now() AT TIME ZONE 'UTC')::date;
    v_token  text;
    v_req    bigint;
BEGIN
    INSERT INTO public.lanci_action (giorno, workflow_file)
    VALUES (v_giorno, 'verifica_catena')
    ON CONFLICT (giorno, workflow_file) DO NOTHING;
    IF NOT FOUND THEN
        RETURN format('verifica della catena del %s gia'' chiesta: nessuna chiamata', v_giorno);
    END IF;

    v_token := public._orologio_token();
    IF v_token IS NULL THEN
        UPDATE public.lanci_action SET errore = 'token assente nel Vault: verifica non fatta'
         WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
        PERFORM public._orologio_allarme('WARN', 'CATENA_NOTTURNA_INCOMPLETA',
            format('Verifica della catena notturna del %s NON fatta: token GitHub assente '
                   'nel Vault (github_actions_dispatch).', v_giorno));
        RETURN 'token assente: allarme scritto';
    END IF;

    BEGIN
        v_req := net.http_get(
            url := 'https://api.github.com/repos/Dani91x/python-database-automation/actions/runs',
            params := jsonb_build_object('created', '>=' || to_char(v_giorno, 'YYYY-MM-DD'),
                                         'per_page', '100'),
            headers := public._orologio_intestazioni(v_token),
            timeout_milliseconds := 30000
        );
    EXCEPTION WHEN OTHERS THEN
        UPDATE public.lanci_action
           SET errore = left('richiesta pg_net non accodata: ' || SQLERRM, 500)
         WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
        PERFORM public._orologio_allarme('WARN', 'CATENA_NOTTURNA_INCOMPLETA',
            left(format('Verifica della catena notturna del %s NON fatta: pg_net in errore (%s).',
                        v_giorno, SQLERRM), 1000));
        RETURN 'pg_net in errore: allarme scritto';
    END;

    UPDATE public.lanci_action SET request_id = v_req
     WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
    RETURN format('verifica della catena chiesta a GitHub (pg_net request_id %s)', v_req);
END;
$$;

CREATE OR REPLACE FUNCTION public.leggi_verifica_catena()
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_giorno   date := (now() AT TIME ZONE 'UTC')::date;
    r          record;
    v_trovata  boolean;
    v_status   int;
    v_timeout  boolean;
    v_errmsg   text;
    v_corpo    text;
    v_json     jsonb;
    v_file     text;
    v_run      jsonb;
    v_mancanti text[] := ARRAY[]::text[];
    v_in_corso text[] := ARRAY[]::text[];
    v_testo    text;
    v_level    text;
BEGIN
    SELECT * INTO r FROM public.lanci_action
     WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
    IF NOT FOUND THEN
        PERFORM public._orologio_allarme('WARN', 'CATENA_NOTTURNA_INCOMPLETA',
            format('Verifica della catena notturna del %s NON chiesta (job orologio_verifica_catena non partito?).', v_giorno));
        RETURN 'verifica non chiesta: allarme scritto';
    END IF;
    IF r.esito_http IS NOT NULL OR r.errore IS NOT NULL THEN
        RETURN 'verifica del giorno gia'' letta (o gia'' in errore): niente da fare';
    END IF;

    IF r.request_id IS NOT NULL THEN
        SELECT true, h.status_code, h.timed_out, h.error_msg, h.content
          INTO v_trovata, v_status, v_timeout, v_errmsg, v_corpo
          FROM net._http_response h WHERE h.id = r.request_id;
    END IF;
    IF v_status = 200 THEN
        BEGIN
            v_json := v_corpo::jsonb;
        EXCEPTION WHEN OTHERS THEN
            v_json := NULL;
        END;
    END IF;
    IF NOT coalesce(v_trovata, false) OR v_status IS DISTINCT FROM 200 OR v_json IS NULL THEN
        v_testo := CASE WHEN NOT coalesce(v_trovata, false) THEN 'nessuna risposta di pg_net'
                        WHEN v_status = 200 THEN 'risposta 200 ma non e'' JSON leggibile'
                        ELSE format('HTTP %s%s: %s', coalesce(v_status::text, 'nessuno'),
                                    CASE WHEN v_timeout THEN ' (timeout)' ELSE '' END,
                                    left(coalesce(v_errmsg, v_corpo, ''), 300)) END;
        UPDATE public.lanci_action SET esito_http = v_status, errore = left(v_testo, 500)
         WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
        PERFORM public._orologio_allarme('WARN', 'CATENA_NOTTURNA_INCOMPLETA',
            left(format('Verifica della catena notturna del %s NON riuscita: %s. Controllare a mano '
                        'la pagina Actions di GitHub.', v_giorno, v_testo), 1000));
        RETURN 'verifica non riuscita: allarme scritto';
    END IF;

    -- per ogni anello: la run PIU' RECENTE creata oggi (UTC)
    FOREACH v_file IN ARRAY public._orologio_catena() LOOP
        SELECT x INTO v_run
          FROM jsonb_array_elements(coalesce(v_json -> 'workflow_runs', '[]'::jsonb)) AS x
         WHERE split_part(x ->> 'path', '@', 1) = '.github/workflows/' || v_file
         ORDER BY x ->> 'created_at' DESC
         LIMIT 1;
        IF v_run IS NULL THEN
            v_mancanti := v_mancanti || format('%s: nessuna run oggi', v_file);
        ELSIF v_run ->> 'status' IS DISTINCT FROM 'completed' THEN
            v_in_corso := v_in_corso || format('%s: %s', v_file, v_run ->> 'status');
        ELSIF coalesce(v_run ->> 'conclusion', '') NOT IN ('success', 'skipped') THEN
            v_mancanti := v_mancanti || format('%s: %s (%s)', v_file,
                                              coalesce(v_run ->> 'conclusion', 'senza esito'),
                                              coalesce(v_run ->> 'html_url', ''));
        END IF;
        v_run := NULL;
    END LOOP;

    IF cardinality(v_mancanti) = 0 AND cardinality(v_in_corso) = 0 THEN
        UPDATE public.lanci_action SET esito_http = 200
         WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
        RETURN format('catena notturna del %s completa (9 anelli success/skipped)', v_giorno);
    END IF;

    v_level := CASE WHEN cardinality(v_mancanti) > 0 THEN 'CRITICAL' ELSE 'WARN' END;
    v_testo := format('Catena notturna del %s INCOMPLETA alle %s UTC.', v_giorno,
                      to_char(now() AT TIME ZONE 'UTC', 'HH24:MI'))
            || CASE WHEN cardinality(v_mancanti) > 0
                    THEN ' Mancanti o falliti: ' || array_to_string(v_mancanti, '; ') || '.' ELSE '' END
            || CASE WHEN cardinality(v_in_corso) > 0
                    THEN ' Ancora in corso: ' || array_to_string(v_in_corso, '; ') || '.' ELSE '' END
            || CASE WHEN (v_json ->> 'total_count')::int > 100
                    THEN format(' (GitHub ha %s run oggi, lette le prime 100.)', v_json ->> 'total_count') ELSE '' END;
    UPDATE public.lanci_action SET esito_http = 200, errore = left(v_testo, 2000)
     WHERE giorno = v_giorno AND workflow_file = 'verifica_catena';
    PERFORM public._orologio_allarme(v_level, 'CATENA_NOTTURNA_INCOMPLETA', left(v_testo, 2000));
    RETURN v_testo;
END;
$$;


-- ---------------------------------------------------------------------
-- 6) nessuno da fuori puo' chiamarle (le esegue pg_cron come postgres)
-- ---------------------------------------------------------------------
REVOKE ALL ON FUNCTION public._orologio_allarme(text, text, text)          FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public._orologio_token()                            FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public._orologio_intestazioni(text)                 FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public._orologio_catena()                           FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.lancia_action(text, jsonb)                   FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.verifica_lancio_action()                     FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.verifica_catena_notturna()                   FROM public, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.leggi_verifica_catena()                      FROM public, anon, authenticated, service_role;


-- ---------------------------------------------------------------------
-- 7) i job pg_cron (orari UTC). Idempotente: se un job con lo stesso nome
--    esiste lo si toglie e lo si rimette. SOLO il primo anello si lancia
--    da qui: tutto il resto e' catena (passa-testimone su GitHub).
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v_nome text;
BEGIN
    FOREACH v_nome IN ARRAY ARRAY['orologio_daily', 'orologio_verifica_lancio',
                                  'orologio_verifica_catena', 'orologio_leggi_catena'] LOOP
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = v_nome) THEN
            PERFORM cron.unschedule(v_nome);
        END IF;
    END LOOP;

    -- 00:12 UTC = 02:12 ora italiana (01:12 in inverno), app spenta
    PERFORM cron.schedule('orologio_daily', '12 0 * * *',
        $cmd$SELECT public.lancia_action('daily_yesterday_backfill.yml');$cmd$);
    -- 3 minuti dopo: GitHub ha accettato?
    PERFORM cron.schedule('orologio_verifica_lancio', '15 0 * * *',
        $cmd$SELECT public.verifica_lancio_action();$cmd$);
    -- 07:30 UTC: richiesta delle run di oggi; 07:33 lettura e verdetto
    PERFORM cron.schedule('orologio_verifica_catena', '30 7 * * *',
        $cmd$SELECT public.verifica_catena_notturna();$cmd$);
    PERFORM cron.schedule('orologio_leggi_catena', '33 7 * * *',
        $cmd$SELECT public.leggi_verifica_catena();$cmd$);
END;
$$;

-- controllo finale (si legge nel risultato del SQL editor)
SELECT jobname, schedule, command, active FROM cron.job WHERE jobname LIKE 'orologio%' ORDER BY jobname;
