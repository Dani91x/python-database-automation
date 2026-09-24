-- ============================================================================
-- SICUREZZA DB - BLOCCO 3 di 3 - CHIUSURA FINALE DI anon      (24/09/2026)
-- ============================================================================
-- Prerequisiti: BLOCCHI 1 e 2 applicati e verificati; checklist di prova
-- manuale del documento guida superata (app, bot, action, Telegram).
-- Documento guida: SICUREZZA_DB_2026-09-24.md. SQL Editor, ruolo postgres,
-- per intero; idempotente.
--
-- COSA FA
--   3.1 EXECUTE tolto ad anon e a PUBLIC su OGNI funzione di public (escluse
--       quelle delle estensioni e quelle che servono a un INSERT anonimo su
--       leads: default di colonna e trigger). authenticated conserva ESATTAMENTE
--       le funzioni che puo' eseguire oggi (grant esplicito); service_role le
--       riceve tutte in modo esplicito.
--   3.2 sequenze: via tutto ad anon/PUBLIC, tranne la sequenza di leads (serve
--       all'INSERT della landing se l'id e' un serial).
--   3.3 relazioni: ribadisce il blocco 1 (oggetti nati nel frattempo).
--   3.4 authenticated SOLO LETTURA: via INSERT/UPDATE/DELETE/TRUNCATE/
--       REFERENCES/TRIGGER su tutte le relazioni di public, tranne INSERT su
--       leads. Il frontend non scrive MAI con .from() (solo SELECT; unica
--       eccezione leads.insert, AuthSection.tsx:73): tutte le scritture passano
--       dalle RPC SECURITY DEFINER. Una sessione rubata non puo' piu' scrivere
--       sulle tabelle senza passare dai controlli owner delle RPC.
--   3.5 default privileges di postgres su public: niente piu' ad anon sulle
--       tabelle, sequenze e funzioni FUTURE.
--   3.6 (OPZIONALE, commentato) chiudere anche l'INSERT anonimo su leads.
--   3.7 (OPZIONALE, commentato) togliere a PUBLIC l'EXECUTE di default sulle
--       funzioni future.
--
-- PERCHE' NON ROMPE NULLA
--   * Il login (signInWithPassword, getSession, onAuthStateChange, reset
--     password) parla con GoTrue (/auth/v1), non con PostgREST: non usa grant.
--   * Nessun client chiama RPC con anon: il frontend le chiama solo nelle
--     pagine protette da ProtectedRoute (sessione owner), il resto e' service_role.
--   * Le funzioni di trigger non richiedono EXECUTE a chi fa l'INSERT; le
--     policy della UI usano betfair_live_is_owner(), che authenticated conserva.
--   * Il bot Telegram (telegram-bot) usa anon ma oggi e' GIA' cieco
--     (fixture_predictions senza SELECT per anon dal 22/06): non peggiora.
--     Per farlo funzionare serve un cambio di codice (documento guida, 5.3).
-- ============================================================================

-- ============================================================================
-- PARTE COMUNE (identica nei tre blocchi, idempotente).
-- Crea lo schema privato `sicurezza_bk` con:
--   * sicurezza_bk.fotografia      : lo stato dei permessi PRIMA di ogni blocco
--   * sicurezza_bk.fotografa(b)    : scatta la fotografia (una sola volta per blocco)
--   * sicurezza_bk.ripristina(b)   : riporta grant, RLS, policy, viste, publication
--                                    e default privileges allo stato fotografato
-- Lo schema NON e' esposto dalle API (PostgREST espone solo `public` e
-- `graphql_public`) e nessun ruolo applicativo ha USAGE: lo usa solo `postgres`.
-- ============================================================================

DO $guardia$
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION 'Eseguire come postgres dal SQL Editor di Supabase (current_user = %)', current_user;
    END IF;
END
$guardia$;

CREATE SCHEMA IF NOT EXISTS sicurezza_bk;
REVOKE ALL ON SCHEMA sicurezza_bk FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS sicurezza_bk.fotografia (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    blocco      text        NOT NULL,
    presa_at    timestamptz NOT NULL DEFAULT now(),
    tipo        text        NOT NULL,   -- rel | grant_rel | func | grant_func | policy | pub | defacl
    oggetto     text        NOT NULL,
    relkind     text,
    grantee     text,                   -- 'PUBLIC' oppure nome del ruolo
    privilegio  text,
    valore      text,
    extra       jsonb
);
CREATE INDEX IF NOT EXISTS fotografia_blocco_tipo ON sicurezza_bk.fotografia (blocco, tipo);
REVOKE ALL ON TABLE sicurezza_bk.fotografia FROM PUBLIC, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- fotografa(blocco): scatta la fotografia UNA SOLA VOLTA per blocco. Se il file
-- viene rieseguito, la fotografia resta quella di prima della PRIMA esecuzione
-- (e' lo stato a cui deve tornare il rollback).
-- search_path = pg_catalog: cosi' regprocedure::text esce SEMPRE qualificato
-- con lo schema ("public.nome(tipi)").
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sicurezza_bk.fotografa(p_blocco text)
RETURNS integer
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $f$
DECLARE
    v_n integer;
BEGIN
    IF EXISTS (SELECT 1 FROM sicurezza_bk.fotografia WHERE blocco = p_blocco) THEN
        RAISE NOTICE 'fotografia % gia'' presente: resta quella della prima esecuzione', p_blocco;
        RETURN 0;
    END IF;

    -- relazioni di public: RLS, FORCE RLS, opzioni (security_invoker), proprietario
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, relkind, valore, extra)
    SELECT p_blocco, 'rel', c.oid::regclass::text, c.relkind::text, c.relrowsecurity::text,
           jsonb_build_object('force', c.relforcerowsecurity,
                              'reloptions', coalesce(to_jsonb(c.reloptions), '[]'::jsonb),
                              'owner', pg_get_userbyid(c.relowner))
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S');

    -- grant sulle relazioni ai ruoli dell'API (+ PUBLIC)
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, relkind, grantee, privilegio)
    SELECT p_blocco, 'grant_rel', c.oid::regclass::text, c.relkind::text,
           CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
           a.privilege_type
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,
               acldefault(CASE WHEN c.relkind = 'S' THEN 's'::"char" ELSE 'r'::"char" END, c.relowner))) a
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
       AND (a.grantee = 0 OR pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role'));

    -- funzioni di public (escluse quelle delle estensioni)
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, valore, extra)
    SELECT p_blocco, 'func', p.oid::regprocedure::text, p.prosecdef::text,
           jsonb_build_object('owner', pg_get_userbyid(p.proowner))
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e');

    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, grantee, privilegio)
    SELECT p_blocco, 'grant_func', p.oid::regprocedure::text,
           CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
           a.privilege_type
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
     WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
       AND (a.grantee = 0 OR pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role'));

    -- policy RLS (definizione completa, per poterle ricreare)
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, valore, extra)
    SELECT p_blocco, 'policy', format('%I.%I', pol.schemaname, pol.tablename), pol.policyname,
           jsonb_build_object('cmd', pol.cmd, 'permissive', pol.permissive, 'roles', to_jsonb(pol.roles),
                              'qual', pol.qual, 'with_check', pol.with_check)
      FROM pg_policies pol
     WHERE pol.schemaname = 'public';

    -- publication del realtime
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto)
    SELECT p_blocco, 'pub', format('%I.%I', pt.schemaname, pt.tablename)
      FROM pg_publication_tables pt
     WHERE pt.pubname = 'supabase_realtime' AND pt.schemaname = 'public';

    -- default privileges di postgres (globali e su public)
    INSERT INTO sicurezza_bk.fotografia (blocco, tipo, oggetto, relkind, grantee, privilegio, valore)
    SELECT p_blocco, 'defacl', coalesce(n.nspname, '*'), d.defaclobjtype::text,
           CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
           a.privilege_type, pg_get_userbyid(d.defaclrole)
      FROM pg_default_acl d
      LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
     CROSS JOIN LATERAL aclexplode(d.defaclacl) a
     WHERE pg_get_userbyid(d.defaclrole) = 'postgres'
       AND (d.defaclnamespace = 0 OR n.nspname = 'public')
       AND (a.grantee = 0 OR pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role'));

    SELECT count(*) INTO v_n FROM sicurezza_bk.fotografia WHERE blocco = p_blocco;
    RAISE NOTICE 'fotografia % scattata: % righe', p_blocco, v_n;
    RETURN v_n;
END
$f$;

-- ---------------------------------------------------------------------------
-- ripristina(blocco): riporta lo stato a quello fotografato PRIMA del blocco.
-- Tocca SOLO gli oggetti presenti nella fotografia (quelli creati dopo restano
-- come sono). Non revoca MAI nulla a service_role.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sicurezza_bk.ripristina(p_blocco text)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $f$
DECLARE
    r          record;
    v_ruolo    text;
    v_ruoli    text;
    v_rls_ora  boolean;
    v_opt      text;
    v_sql      text;
    v_n        integer := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sicurezza_bk.fotografia WHERE blocco = p_blocco) THEN
        RAISE EXCEPTION 'nessuna fotografia per il blocco %', p_blocco;
    END IF;

    -- 1) grant sulle relazioni: via tutto ad anon/authenticated/PUBLIC, poi si
    --    ridanno esattamente quelli fotografati
    FOR r IN SELECT oggetto, relkind FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'rel' LOOP
        CONTINUE WHEN to_regclass(r.oggetto) IS NULL;
        EXECUTE format('REVOKE ALL ON %s %s FROM PUBLIC, anon, authenticated',
                       CASE WHEN r.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END, r.oggetto);
    END LOOP;
    FOR r IN SELECT oggetto, relkind, grantee, privilegio FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'grant_rel' LOOP
        CONTINUE WHEN to_regclass(r.oggetto) IS NULL;
        v_ruolo := CASE WHEN r.grantee = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END;
        EXECUTE format('GRANT %s ON %s %s TO %s', r.privilegio,
                       CASE WHEN r.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END, r.oggetto, v_ruolo);
        v_n := v_n + 1;
    END LOOP;

    -- 2) RLS e opzioni delle viste
    FOR r IN SELECT oggetto, relkind, valore, extra FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'rel' LOOP
        CONTINUE WHEN to_regclass(r.oggetto) IS NULL;
        IF r.relkind IN ('r', 'p') THEN
            SELECT c.relrowsecurity INTO v_rls_ora FROM pg_class c WHERE c.oid = to_regclass(r.oggetto);
            IF v_rls_ora AND r.valore = 'false' THEN
                EXECUTE format('ALTER TABLE %s DISABLE ROW LEVEL SECURITY', r.oggetto);
            ELSIF NOT v_rls_ora AND r.valore = 'true' THEN
                EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', r.oggetto);
            END IF;
        ELSIF r.relkind = 'v' THEN
            SELECT o INTO v_opt FROM jsonb_array_elements_text(r.extra->'reloptions') o
             WHERE o LIKE 'security_invoker=%';
            IF v_opt IS NULL THEN
                EXECUTE format('ALTER VIEW %s RESET (security_invoker)', r.oggetto);
            ELSE
                EXECUTE format('ALTER VIEW %s SET (%s)', r.oggetto, v_opt);
            END IF;
        END IF;
    END LOOP;

    -- 3) policy: via quelle nate dopo la fotografia, ricreate quelle cambiate o sparite
    FOR r IN SELECT format('%I.%I', pol.schemaname, pol.tablename) AS tab, pol.policyname
               FROM pg_policies pol
              WHERE pol.schemaname = 'public'
                AND EXISTS (SELECT 1 FROM sicurezza_bk.fotografia f
                             WHERE f.blocco = p_blocco AND f.tipo = 'rel'
                               AND f.oggetto = format('%I.%I', pol.schemaname, pol.tablename)::regclass::text)
                AND NOT EXISTS (SELECT 1 FROM sicurezza_bk.fotografia f
                                 WHERE f.blocco = p_blocco AND f.tipo = 'policy'
                                   AND f.oggetto = format('%I.%I', pol.schemaname, pol.tablename)
                                   AND f.valore = pol.policyname) LOOP
        EXECUTE format('DROP POLICY %I ON %s', r.policyname, r.tab);
    END LOOP;
    FOR r IN SELECT oggetto, valore, extra FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'policy' LOOP
        CONTINUE WHEN to_regclass(r.oggetto) IS NULL;
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM pg_policies pol
             WHERE format('%I.%I', pol.schemaname, pol.tablename) = r.oggetto
               AND pol.policyname = r.valore
               AND pol.cmd = r.extra->>'cmd'
               AND pol.permissive = r.extra->>'permissive'
               AND to_jsonb(pol.roles) = r.extra->'roles'
               AND pol.qual IS NOT DISTINCT FROM r.extra->>'qual'
               AND pol.with_check IS NOT DISTINCT FROM r.extra->>'with_check');
        EXECUTE format('DROP POLICY IF EXISTS %I ON %s', r.valore, r.oggetto);
        SELECT string_agg(CASE WHEN x = 'public' THEN 'PUBLIC' ELSE quote_ident(x) END, ', ')
          INTO v_ruoli FROM jsonb_array_elements_text(r.extra->'roles') x;
        v_sql := format('CREATE POLICY %I ON %s AS %s FOR %s TO %s',
                        r.valore, r.oggetto, r.extra->>'permissive', r.extra->>'cmd', v_ruoli);
        IF r.extra->>'qual' IS NOT NULL THEN
            v_sql := v_sql || format(' USING (%s)', r.extra->>'qual');
        END IF;
        IF r.extra->>'with_check' IS NOT NULL THEN
            v_sql := v_sql || format(' WITH CHECK (%s)', r.extra->>'with_check');
        END IF;
        EXECUTE v_sql;
    END LOOP;

    -- 4) EXECUTE sulle funzioni
    FOR r IN SELECT oggetto FROM sicurezza_bk.fotografia WHERE blocco = p_blocco AND tipo = 'func' LOOP
        CONTINUE WHEN to_regprocedure(r.oggetto) IS NULL;
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', r.oggetto);
    END LOOP;
    FOR r IN SELECT oggetto, grantee, privilegio FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'grant_func' LOOP
        CONTINUE WHEN to_regprocedure(r.oggetto) IS NULL;
        v_ruolo := CASE WHEN r.grantee = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END;
        EXECUTE format('GRANT %s ON FUNCTION %s TO %s', r.privilegio, r.oggetto, v_ruolo);
    END LOOP;

    -- 5) publication supabase_realtime
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        FOR r IN SELECT format('%I.%I', pt.schemaname, pt.tablename) AS tab
                   FROM pg_publication_tables pt
                  WHERE pt.pubname = 'supabase_realtime' AND pt.schemaname = 'public'
                    AND EXISTS (SELECT 1 FROM sicurezza_bk.fotografia f
                                 WHERE f.blocco = p_blocco AND f.tipo = 'rel'
                                   AND f.oggetto = format('%I.%I', pt.schemaname, pt.tablename)::regclass::text)
                    AND NOT EXISTS (SELECT 1 FROM sicurezza_bk.fotografia f
                                     WHERE f.blocco = p_blocco AND f.tipo = 'pub'
                                       AND f.oggetto = format('%I.%I', pt.schemaname, pt.tablename)) LOOP
            EXECUTE format('ALTER PUBLICATION supabase_realtime DROP TABLE %s', r.tab);
        END LOOP;
        FOR r IN SELECT oggetto FROM sicurezza_bk.fotografia f
                  WHERE f.blocco = p_blocco AND f.tipo = 'pub'
                    AND to_regclass(f.oggetto) IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM pg_publication_tables pt
                                     WHERE pt.pubname = 'supabase_realtime'
                                       AND format('%I.%I', pt.schemaname, pt.tablename) = f.oggetto) LOOP
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE %s', r.oggetto);
        END LOOP;
    END IF;

    -- 6) default privileges di postgres: si ridanno quelli fotografati
    FOR r IN SELECT oggetto, relkind, grantee, privilegio FROM sicurezza_bk.fotografia
              WHERE blocco = p_blocco AND tipo = 'defacl' AND relkind IN ('r', 'S', 'f') LOOP
        v_ruolo := CASE WHEN r.grantee = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r.grantee) END;
        EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres %s GRANT %s ON %s TO %s',
                       CASE WHEN r.oggetto = '*' THEN '' ELSE 'IN SCHEMA ' || quote_ident(r.oggetto) END,
                       r.privilegio,
                       CASE r.relkind WHEN 'r' THEN 'TABLES' WHEN 'S' THEN 'SEQUENCES' ELSE 'FUNCTIONS' END,
                       v_ruolo);
    END LOOP;

    RETURN format('ripristino %s completato (%s grant su relazioni ridati)', p_blocco, v_n);
END
$f$;

-- ---------------------------------------------------------------------------
-- chiudi_funzione(oid): toglie EXECUTE ad anon e a PUBLIC su UNA funzione,
-- senza togliere nulla a nessun altro: ogni ruolo applicativo o di sistema
-- di Supabase che OGGI la puo' eseguire (anche solo tramite PUBLIC) riceve
-- prima un grant esplicito. service_role la riceve sempre.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sicurezza_bk.chiudi_funzione(p_oid oid)
RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $f$
DECLARE
    v_fn    text := p_oid::regprocedure::text;
    v_ruolo text;
BEGIN
    FOR v_ruolo IN SELECT ro.rolname FROM pg_roles ro
                    WHERE NOT ro.rolsuper
                      AND ro.rolname IN ('authenticated', 'service_role', 'authenticator',
                                         'supabase_auth_admin', 'supabase_storage_admin',
                                         'supabase_realtime_admin', 'supabase_functions_admin',
                                         'dashboard_user', 'pgbouncer')
                      AND has_function_privilege(ro.oid, p_oid, 'EXECUTE') LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO %I', v_fn, v_ruolo);
    END LOOP;
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', v_fn);
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon', v_fn);
END
$f$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sicurezza_bk FROM PUBLIC, anon, authenticated, service_role;

-- ============================================================================
-- APPLICAZIONE DEL BLOCCO 3 (una sola transazione)
-- ============================================================================
BEGIN;
SET LOCAL search_path = pg_catalog;

SELECT sicurezza_bk.fotografa('B3');

-- ---------------------------------------------------------------------------
-- 3.1  FUNZIONI
-- ---------------------------------------------------------------------------
DO $b3_fun$
DECLARE
    r          record;
    v_leads    oid := to_regclass('public.leads');
    v_esenti   oid[] := '{}';
BEGIN
    -- esenti: funzioni usate dai default delle colonne di leads e trigger di leads
    IF v_leads IS NOT NULL THEN
        SELECT coalesce(array_agg(DISTINCT d.refobjid), '{}') INTO v_esenti
          FROM pg_attrdef ad
          JOIN pg_depend d ON d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid
                          AND d.refclassid = 'pg_proc'::regclass
         WHERE ad.adrelid = v_leads;
        SELECT v_esenti || coalesce(array_agg(DISTINCT tg.tgfoid), '{}') INTO v_esenti
          FROM pg_trigger tg
         WHERE tg.tgrelid = v_leads AND NOT tg.tgisinternal;
    END IF;

    FOR r IN SELECT p.oid, p.oid::regprocedure::text AS fn, pg_get_userbyid(p.proowner) AS owner
               FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
                AND NOT EXISTS (SELECT 1 FROM pg_depend d
                                 WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
              ORDER BY 2 LOOP
        IF r.oid = ANY (v_esenti) THEN
            RAISE NOTICE 'funzione % ESENTE (default/trigger di leads): anon la conserva', r.fn;
            CONTINUE;
        END IF;
        IF r.owner <> current_user THEN
            RAISE NOTICE 'funzione % di proprietario %: NON toccata', r.fn, r.owner;
            CONTINUE;
        END IF;
        PERFORM sicurezza_bk.chiudi_funzione(r.oid);
    END LOOP;
END
$b3_fun$;

-- ---------------------------------------------------------------------------
-- 3.2  SEQUENZE
-- ---------------------------------------------------------------------------
DO $b3_seq$
DECLARE
    r       record;
    v_leads oid := to_regclass('public.leads');
BEGIN
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind = 'S' LOOP
        EXECUTE format('GRANT USAGE, SELECT, UPDATE ON SEQUENCE %s TO service_role', r.obj);
        IF v_leads IS NOT NULL AND EXISTS (
               SELECT 1 FROM pg_depend d
                WHERE d.classid = 'pg_class'::regclass AND d.objid = r.oid
                  AND d.refclassid = 'pg_class'::regclass AND d.refobjid = v_leads
                  AND d.deptype IN ('a', 'i')) THEN
            RAISE NOTICE 'sequenza % di leads: anon conserva USAGE (INSERT della landing)', r.obj;
            EXECUTE format('REVOKE SELECT, UPDATE ON SEQUENCE %s FROM PUBLIC, anon', r.obj);
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon', r.obj);
    END LOOP;
END
$b3_seq$;

-- ---------------------------------------------------------------------------
-- 3.3  RELAZIONI (ribadisce il blocco 1) + 3.4 authenticated SOLO LETTURA
-- ---------------------------------------------------------------------------
DO $b3_rel$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT c.oid::regclass::text AS obj, c.relname
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') LOOP
        IF r.relname = 'leads' THEN
            EXECUTE format('REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE %s FROM PUBLIC, anon', r.obj);
            -- 3.4 su leads: authenticated conserva SELECT e INSERT (policy di security_lockdown.sql)
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE %s FROM authenticated', r.obj);
        ELSE
            EXECUTE format('REVOKE ALL ON TABLE %s FROM PUBLIC, anon', r.obj);
            -- 3.4
            EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE %s FROM authenticated', r.obj);
        END IF;
    END LOOP;
END
$b3_rel$;

-- ---------------------------------------------------------------------------
-- 3.5  DEFAULT PRIVILEGES di postgres su public: niente ad anon sugli oggetti
--      FUTURI (le migrazioni nuove non devono piu' ricordarsi il REVOKE ad anon).
--      Non tocca service_role (per il 30/10 vedi documento guida, 5.4).
-- ---------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES    FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon;

-- ---------------------------------------------------------------------------
-- 3.6  (OPZIONALE - DECISIONE DELL'UTENTE) chiudere anche il form della landing.
--      Oggi chiunque puo' lasciare un lead (INSERT anonimo, niente lettura).
--      Il form e' "best-effort" (AuthSection.tsx:72-83 cattura l'errore e mostra
--      comunque il banner): chiudendolo la pagina NON si rompe, semplicemente
--      i lead non vengono piu' salvati. Per applicarlo togliere i commenti:
-- ---------------------------------------------------------------------------
-- REVOKE INSERT ON TABLE public.leads FROM anon;
-- DROP POLICY IF EXISTS leads_anon_insert ON public.leads;
-- CREATE POLICY leads_anon_insert ON public.leads FOR INSERT TO authenticated WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 3.7  (OPZIONALE) Postgres concede EXECUTE a PUBLIC su ogni funzione nuova:
--      anon la eseguirebbe finche' la migrazione non fa `REVOKE ... FROM
--      PUBLIC, anon` (il progetto lo fa quasi sempre). Questa riga toglie il
--      default a livello globale per le funzioni create da postgres; dopo, ogni
--      migrazione DEVE concedere EXECUTE esplicito ad authenticated/service_role
--      (i default di Supabase su public lo fanno gia' per questi due ruoli).
--      Rollback: ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT EXECUTE ON FUNCTIONS TO PUBLIC;
-- ---------------------------------------------------------------------------
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

COMMIT;

-- ============================================================================
-- VERIFICA DEL BLOCCO 3 (SOLA LETTURA):
--     SELECT * FROM sicurezza_bk.verifica_b3() ORDER BY esito DESC, controllo;
-- Atteso: nessun 'KO'. Poi la prova di ruolo (documento guida, sezione 6).
-- ============================================================================
CREATE OR REPLACE FUNCTION sicurezza_bk.verifica_b3()
RETURNS TABLE (controllo text, esito text, dettaglio text)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $v$
DECLARE
    -- le 132 RPC chiamate dal frontend (grep `supabase.rpc('...` in frontend/src,
    -- esclusi test e banco di certificazione), 24/09/2026
    v_ui_rpc text[] := ARRAY[
        'ack_alert', 'add_personal_trade', 'add_to_watchlist', 'add_trade_leg', 'backtest_strategy',
        'cancel_live_risk_rule', 'delete_from_watchlist', 'delete_strategy', 'get_analytics',
        'get_analytics_filters', 'get_analytics_rows', 'get_betfair_direction_odds',
        'get_betfair_fixtures', 'get_betfair_full_odds', 'get_betfair_live_order',
        'get_betfair_odds', 'get_betfair_order_request', 'get_betfair_orders',
        'get_betfair_refresh_request', 'get_cash_movements', 'get_decisions',
        'get_decisions_filters', 'get_direction', 'get_direction_report',
        'get_direction_report_fixture', 'get_direction_report_matches', 'get_league_seasons',
        'get_live_alerts', 'get_live_audit', 'get_live_follows', 'get_live_journal',
        'get_live_orders', 'get_live_positions', 'get_live_positions_all',
        'get_live_positions_event', 'get_live_risk_rules', 'get_live_settings', 'get_live_settled',
        'get_live_xhedge', 'get_market_delays', 'get_market_frequency', 'get_mike_daily',
        'get_mike_day_trades', 'get_mike_state', 'get_mike_trades', 'get_omega_daily',
        'get_omega_day_trades', 'get_omega_events', 'get_omega_manual_requests', 'get_omega_market',
        'get_omega_missions', 'get_omega_proposte', 'get_omega_state', 'get_omega_trades',
        'get_personal_report', 'get_personal_trades', 'get_replay', 'get_replay_frames',
        'get_replay_meta', 'get_safe_activity', 'get_safe_daily', 'get_safe_day_trades',
        'get_safe_state', 'get_safe_trades', 'get_scalper_state', 'get_storico_stake',
        'get_tennis_bot_daily', 'get_tennis_bot_orders_today', 'get_tennis_bot_services',
        'get_tennis_bots_state', 'get_tennis_fixtures', 'get_tennis_follows',
        'get_tennis_full_odds', 'get_tennis_live_order', 'get_tennis_live_orders',
        'get_tennis_live_positions', 'get_tennis_live_positions_all', 'get_tennis_refresh_request',
        'get_watchlist', 'list_backtest_results', 'list_backtest_runs', 'list_replays',
        'list_strategies', 'mike_activate', 'mike_request', 'mike_stop', 'mike_update_params',
        'omega_activate', 'omega_eventi_chiusi_dall_utente', 'omega_evento_riprendi',
        'omega_mission_activate', 'omega_mission_follow', 'omega_mission_stop', 'omega_request',
        'omega_request_approve', 'omega_request_ignore', 'omega_stop', 'omega_update_params',
        'request_backtest', 'request_betfair_live_order', 'request_betfair_order',
        'request_betfair_refresh', 'request_live_risk_rule', 'request_tennis_live_order',
        'request_tennis_refresh', 'reset_personal_report', 'run_strategy', 'run_strategy_rows',
        'safe_activate', 'safe_request', 'safe_request_approve', 'safe_request_ignore', 'safe_stop',
        'safe_update_params', 'save_strategy', 'scalper_activate', 'scalper_stop',
        'set_follow_record', 'set_live_journal_note', 'set_live_kill_switch', 'set_live_settings',
        'set_trade_time_operative', 'set_watchlist_decision', 'set_watchlist_follow_live',
        'settle_personal_trade', 'tennis_bot_arm', 'tennis_bot_disarm',
        'tennis_bot_service_activate', 'tennis_bot_service_stop',
        'tennis_bot_service_update_params', 'tennis_follow_event', 'tennis_set_follow_record'
    ];
    v_leads oid := to_regclass('public.leads');
    t text;
    r record;
    v_n integer;
BEGIN
    -- anon non esegue nessuna funzione (salvo esenti di leads e funzioni altrui)
    FOR r IN SELECT p.oid, p.oid::regprocedure::text AS fn
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
                AND NOT EXISTS (SELECT 1 FROM pg_depend d
                                 WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
                AND has_function_privilege('anon', p.oid, 'EXECUTE') LOOP
        controllo := 'anon esegue ancora ' || r.fn;
        esito := CASE WHEN EXISTS (SELECT 1 FROM pg_trigger tg WHERE tg.tgrelid = v_leads AND tg.tgfoid = r.oid)
                        OR EXISTS (SELECT 1 FROM pg_attrdef ad JOIN pg_depend d
                                     ON d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid
                                    WHERE ad.adrelid = v_leads AND d.refobjid = r.oid)
                      THEN 'INFO' ELSE 'KO' END;
        dettaglio := CASE WHEN esito = 'INFO' THEN 'esente: default/trigger di leads' END;
        RETURN NEXT;
    END LOOP;

    -- la UI esegue ancora tutte le sue RPC (authenticated) e service_role pure
    FOREACH t IN ARRAY v_ui_rpc LOOP
        SELECT count(*) INTO v_n FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.proname = t;
        IF v_n = 0 THEN
            controllo := 'RPC UI ' || t; esito := 'INFO'; dettaglio := 'assente nel DB (migrazione non applicata?)';
            RETURN NEXT; CONTINUE;
        END IF;
        FOR r IN SELECT p.oid, p.oid::regprocedure::text AS fn
                   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'public' AND p.proname = t LOOP
            controllo := 'RPC UI ' || r.fn || ' eseguibile da authenticated';
            esito := CASE WHEN has_function_privilege('authenticated', r.oid, 'EXECUTE') THEN 'OK' ELSE 'KO' END;
            dettaglio := NULL; RETURN NEXT;
        END LOOP;
    END LOOP;
    FOR r IN SELECT p.oid::regprocedure::text AS fn
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
                AND NOT has_function_privilege('service_role', p.oid, 'EXECUTE') LOOP
        controllo := 'service_role NON esegue ' || r.fn; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
    END LOOP;
    controllo := 'authenticated esegue betfair_live_is_owner() (serve alle policy del realtime)';
    esito := CASE WHEN has_function_privilege('authenticated', 'public.betfair_live_is_owner()', 'EXECUTE')
                  THEN 'OK' ELSE 'KO' END;
    dettaglio := NULL; RETURN NEXT;

    -- sequenze
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind = 'S'
                -- CASE: il planner puo' valutare le condizioni in qualunque ordine e
                -- has_sequence_privilege su una relazione che non e' una sequenza da' errore
                AND CASE WHEN c.relkind = 'S' THEN has_sequence_privilege('anon', c.oid, 'USAGE, SELECT, UPDATE') ELSE false END LOOP
        controllo := 'anon su sequenza ' || r.obj;
        esito := CASE WHEN EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                                   AND d.objid = r.oid AND d.refobjid = v_leads AND d.deptype IN ('a', 'i'))
                           AND NOT has_sequence_privilege('anon', r.oid, 'SELECT, UPDATE')
                      THEN 'OK' ELSE 'KO' END;
        dettaglio := CASE WHEN esito = 'OK' THEN 'sequenza di leads: solo USAGE' END;
        RETURN NEXT;
    END LOOP;

    -- relazioni: anon niente (tranne INSERT leads), authenticated nessuna scrittura (tranne INSERT leads)
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj, c.relname
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') LOOP
        IF r.relname = 'leads' THEN
            IF has_table_privilege('anon', r.oid, 'SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
               OR has_table_privilege('authenticated', r.oid, 'UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
                controllo := 'leads: privilegi oltre INSERT (anon) / SELECT+INSERT (authenticated)';
                esito := 'KO'; dettaglio := NULL; RETURN NEXT;
            END IF;
            CONTINUE;
        END IF;
        IF has_table_privilege('anon', r.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
            controllo := 'anon ha privilegi su ' || r.obj; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
        END IF;
        IF has_table_privilege('authenticated', r.oid, 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
            controllo := 'authenticated puo'' scrivere su ' || r.obj; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
        END IF;
    END LOOP;

    -- default privileges futuri
    controllo := 'default privileges postgres/public: nessun grant ad anon';
    esito := CASE WHEN EXISTS (
                 SELECT 1 FROM pg_default_acl d
                  CROSS JOIN LATERAL aclexplode(d.defaclacl) a
                  WHERE pg_get_userbyid(d.defaclrole) = 'postgres'
                    AND d.defaclnamespace = 'public'::regnamespace
                    AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'anon'))
                  THEN 'KO' ELSE 'OK' END;
    dettaglio := NULL; RETURN NEXT;
END
$v$;
REVOKE ALL ON FUNCTION sicurezza_bk.verifica_b3() FROM PUBLIC, anon, authenticated, service_role;

-- ============================================================================
-- ROLLBACK DEL BLOCCO 3 (NON eseguire insieme all'applicazione!)
-- Rida' ad anon/authenticated/PUBLIC esattamente i grant fotografati prima del
-- blocco 3 (funzioni, sequenze, relazioni) e i default privileges:
--
--     BEGIN;
--     SELECT sicurezza_bk.ripristina('B3');
--     COMMIT;
--
-- Se era stata applicata l'opzione 3.7:
--     ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT EXECUTE ON FUNCTIONS TO PUBLIC;
-- Se era stata applicata l'opzione 3.6:
--     DROP POLICY IF EXISTS leads_anon_insert ON public.leads;
--     CREATE POLICY leads_anon_insert ON public.leads FOR INSERT TO anon, authenticated WITH CHECK (true);
--     GRANT INSERT ON TABLE public.leads TO anon;
-- ============================================================================
