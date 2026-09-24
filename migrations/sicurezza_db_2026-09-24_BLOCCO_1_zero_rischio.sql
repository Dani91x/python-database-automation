-- ============================================================================
-- SICUREZZA DB - BLOCCO 1 di 3 - "ZERO RISCHIO"            (24/09/2026)
-- ============================================================================
-- Ordine dell'utente: "Metti in sicurezza il DB: ci lavoro solo io e solo io
-- devo accedere (io = tutta l'app e il sistema che abbiamo costruito), nessun
-- altro. Il progetto deve continuare a funzionare in ogni sua parte."
-- Piu' il punto 14: "omega_activity deve avere il realtime".
--
-- Documento guida: SICUREZZA_DB_2026-09-24.md (radice del repo).
-- Si applica DAL SQL EDITOR di Supabase (ruolo postgres), UNA volta, per intero.
-- E' idempotente: rieseguirlo non fa danni (la fotografia resta la prima).
--
-- COSA FA
--   1. fotografia dei permessi (per il rollback) nello schema privato sicurezza_bk
--   2. omega_activity in tempo reale: SELECT ad authenticated + policy owner-only
--      + publication (la UI la ascolta da lib/omega.ts:1263 ma dal 12/09 e' muta)
--   3. anon: via OGNI privilegio su tabelle, viste e matview di public, TRANNE
--      INSERT su leads (form della landing, AuthSection.tsx:73)
--   4. viste: security_invoker = on (non scavalcano piu' la RLS delle tabelle)
--   5. 11 RPC SECURITY DEFINER SENZA controllo owner, revocate solo a PUBLIC e
--      quindi (con i default di Supabase) ancora eseguibili da anon: EXECUTE
--      tolto ad anon/PUBLIC, preservato ESATTAMENTE per authenticated
--   6. GRANT espliciti a service_role su tutte le tabelle e sequenze di public
--      (oggi li ha gia' tutti dai default: e' una conferma, serve per il 30/10)
--
-- PERCHE' E' A RISCHIO ZERO (prove nel documento guida, sezione 1)
--   * anon lo usano SOLO: la landing (INSERT su leads, mantenuto) e il login
--     (supabase.auth -> GoTrue, NON passa dai grant di public). Il bot Telegram
--     (telegram-bot) legge fixture_predictions con anon ma anon NON ha SELECT
--     dal 22/06 (security_lockdown.sql:103): oggi e' gia' cieco, resta com'e'.
--   * Il frontend dopo il login e' `authenticated`: in questo blocco authenticated
--     GUADAGNA solo la SELECT su omega_activity; non perde nulla.
--   * Python, GitHub Actions, make-daily-post: service_role (bypassa la RLS e
--     qui riceve solo conferme di grant).
--   * Nessuno legge le viste con anon o authenticated (grep: v_* mai usate dal
--     codice; bet_features letta solo da Python service_role e da RPC DEFINER).
--
-- RISCHIO RESIDUO dichiarato: un client ESTERNO al repo che usi la chiave anon
-- (uno scenario Make, uno script dimenticato). Prima di applicare: query sui log
-- API nel documento guida (sezione 4, "prerequisiti"). Se esce qualcosa, fermarsi.
--
-- EFFETTO COLLATERALE ATTESO: con omega_activity in realtime la pagina Omega
-- ricarica get_omega_state a ogni evento (con debounce 1,2 s, Omega.tsx:79,244)
-- invece che ogni 15 s: piu' letture DB mentre la pagina e' aperta.
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
-- APPLICAZIONE DEL BLOCCO 1 (una sola transazione: o tutto o niente)
-- ============================================================================
BEGIN;
-- search_path ridotto a pg_catalog: ogni nome generato qui sotto esce
-- qualificato con lo schema ("public.x"), nessuna ambiguita' possibile.
SET LOCAL search_path = pg_catalog;

SELECT sicurezza_bk.fotografa('B1');

-- ---------------------------------------------------------------------------
-- 1.1  omega_activity in TEMPO REALE (punto 14)
--      Stesso schema di mike_activity / safe_strategy_activity (mike_bot.sql:
--      170-176): RLS attiva, SELECT ad authenticated con policy owner-only,
--      niente ad anon, tabella nella publication supabase_realtime.
--      Senza SELECT + policy il realtime NON consegna righe anche se la tabella
--      e' pubblicata: e' il difetto rimasto aperto dopo la migrazione del 12/09
--      (omega_activity_realtime_2026-09-12.sql l'aveva solo pubblicata).
-- ---------------------------------------------------------------------------
ALTER TABLE public.omega_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.omega_activity FROM anon;
GRANT SELECT ON TABLE public.omega_activity TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.omega_activity TO service_role;
-- la policy usa betfair_live_is_owner(): authenticated deve poterla eseguire
-- (gia' concesso da realtime_orders_bots.sql:23, qui si ribadisce)
GRANT EXECUTE ON FUNCTION public.betfair_live_is_owner() TO authenticated, service_role;

DROP POLICY IF EXISTS omega_activity_select_owner ON public.omega_activity;
CREATE POLICY omega_activity_select_owner ON public.omega_activity
    FOR SELECT TO authenticated
    USING (public.betfair_live_is_owner());

DO $b1_seq$
DECLARE
    v_seq text := pg_get_serial_sequence('public.omega_activity', 'id');
BEGIN
    IF v_seq IS NOT NULL THEN
        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM anon, authenticated', v_seq);
        EXECUTE format('GRANT USAGE, SELECT, UPDATE ON SEQUENCE %s TO service_role', v_seq);
    END IF;
END
$b1_seq$;

DO $b1_pub$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                    WHERE pubname = 'supabase_realtime'
                      AND schemaname = 'public' AND tablename = 'omega_activity') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.omega_activity;
        RAISE NOTICE 'omega_activity aggiunta alla publication supabase_realtime';
    ELSE
        RAISE NOTICE 'omega_activity gia'' nella publication';
    END IF;
END
$b1_pub$;

-- ---------------------------------------------------------------------------
-- 1.2  anon: via TUTTO su tabelle, viste, matview e foreign table di public.
--      Eccezione UNICA: INSERT su leads (landing, AuthSection.tsx:73; la
--      policy leads_anon_insert di security_lockdown.sql:71-80 resta).
--      Le sequenze e le funzioni si chiudono nel BLOCCO 3.
-- ---------------------------------------------------------------------------
DO $b1_anon$
DECLARE
    r    record;
    priv text;
BEGIN
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj, c.relname
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') LOOP
        -- authenticated conserva ESATTAMENTE cio' che ha oggi, anche se lo avesse
        -- solo tramite PUBLIC (caso anomalo): diventa un grant esplicito.
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
            IF has_table_privilege('authenticated', r.oid, priv) THEN
                EXECUTE format('GRANT %s ON TABLE %s TO authenticated', priv, r.obj);
            END IF;
        END LOOP;
        IF r.relname = 'leads' THEN
            EXECUTE format('REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE %s FROM PUBLIC, anon', r.obj);
            EXECUTE format('GRANT INSERT ON TABLE %s TO anon', r.obj);
        ELSE
            EXECUTE format('REVOKE ALL ON TABLE %s FROM PUBLIC, anon', r.obj);
        END IF;
    END LOOP;
END
$b1_anon$;

-- ---------------------------------------------------------------------------
-- 1.3  viste: security_invoker = on (PG15+). Una vista senza security_invoker
--      gira come il suo proprietario e scavalca la RLS delle tabelle sotto
--      (es. v_es_* su engine_signals). Nessun client le legge con anon o
--      authenticated; service_role bypassa comunque la RLS; le RPC DEFINER
--      che le leggono girano come postgres, proprietario delle tabelle.
--      Si toccano solo le viste di cui postgres e' proprietario (le altre
--      vengono elencate in un NOTICE e restano come sono).
-- ---------------------------------------------------------------------------
DO $b1_viste$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT c.oid::regclass::text AS obj, pg_get_userbyid(c.relowner) AS owner
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind = 'v' LOOP
        IF r.owner = current_user THEN
            EXECUTE format('ALTER VIEW %s SET (security_invoker = on)', r.obj);
        ELSE
            RAISE NOTICE 'vista % di proprietario % : NON toccata', r.obj, r.owner;
        END IF;
    END LOOP;
END
$b1_viste$;

-- ---------------------------------------------------------------------------
-- 1.4  le 11 RPC SECURITY DEFINER senza controllo owner nel corpo e con il
--      solo `REVOKE ... FROM public` (che NON toglie il grant esplicito che i
--      default di Supabase danno ad anon). Due di esse SCRIVONO:
--      upsert_cash_movement, upsert_imported_trade.
--        get_betfair_fixtures, get_betfair_odds       (betfair_fixtures_rpc.sql:75-78)
--        get_betfair_full_odds, get_betfair_direction_odds (betfair_full_odds_rpc.sql:68-71)
--        get_direction                               (get_direction_rpc.sql:249-250)
--        get_omega_proposte                          (omega_proposte_coda_unica_2026-09-17.sql:287)
--        upsert_cash_movement, get_cash_movements    (personal_cash_movements.sql:92-95)
--        upsert_imported_trade, set_trade_time_operative (personal_tracking_import.sql:150-181)
--        leagues_needing_retrain                     (sql/leagues_needing_retrain_rpc.sql:70-71)
--      Per ognuna (sicurezza_bk.chiudi_funzione): chi OGGI la puo' eseguire
--      (authenticated e i ruoli di sistema, anche solo via PUBLIC) riceve un
--      grant ESPLICITO; service_role sempre; poi via PUBLIC e anon.
--      Ricerca per nome (tutte le firme presenti nel DB).
-- ---------------------------------------------------------------------------
DO $b1_rpc$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT p.oid
               FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public'
                AND p.proname IN ('get_betfair_fixtures', 'get_betfair_odds', 'get_betfair_full_odds',
                                  'get_betfair_direction_odds', 'get_direction', 'get_omega_proposte',
                                  'upsert_cash_movement', 'get_cash_movements', 'upsert_imported_trade',
                                  'set_trade_time_operative', 'leagues_needing_retrain') LOOP
        PERFORM sicurezza_bk.chiudi_funzione(r.oid);
    END LOOP;
END
$b1_rpc$;

-- ---------------------------------------------------------------------------
-- 1.5  service_role: grant ESPLICITI su tutto public (oggi gia' FULL dai
--      default: nessun cambiamento effettivo). Dal 30/10 Supabase toglie i
--      default alle tabelle nuove: questa riga conferma l'esistente.
-- ---------------------------------------------------------------------------
GRANT ALL ON ALL TABLES    IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

COMMIT;

-- ============================================================================
-- VERIFICA DEL BLOCCO 1 (SOLA LETTURA) - lanciare DOPO l'applicazione:
--     SELECT * FROM sicurezza_bk.verifica_b1() ORDER BY esito DESC, controllo;
-- Atteso: nessuna riga con esito 'KO'. Le righe 'INFO' sono difetti
-- preesistenti del realtime da portare all'utente (non causati dal blocco).
-- ============================================================================
CREATE OR REPLACE FUNCTION sicurezza_bk.verifica_b1()
RETURNS TABLE (controllo text, esito text, dettaglio text)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $v$
DECLARE
    v_ui_realtime text[] := ARRAY[
        'betfair_live_account', 'betfair_live_heartbeat', 'betfair_live_orders', 'betfair_live_positions',
        'betfair_live_risk_state', 'live_alerts', 'live_backtest_requests', 'live_follow', 'live_ladder',
        'live_now', 'live_signals', 'mike_activity', 'mike_control', 'mike_events', 'mike_requests',
        'mike_trades', 'omega_activity', 'omega_control', 'omega_manual_requests', 'omega_missions',
        'omega_trades', 'safe_strategy_activity', 'safe_strategy_control', 'safe_strategy_opportunities',
        'safe_strategy_requests', 'safe_strategy_scan', 'safe_strategy_status', 'safe_strategy_trades',
        'tennis_bot_activity', 'tennis_bot_control', 'tennis_live_ladder', 'tennis_live_now',
        'tennis_live_orders', 'tennis_live_positions', 'tennis_markets'];
    v_ui_dirette text[] := ARRAY[
        'fixture_predictions', 'betfair_live_account', 'betfair_live_heartbeat', 'betfair_live_risk_state',
        'live_follow', 'live_ladder', 'live_now', 'live_signals', 'mike_requests', 'safe_strategy_activity',
        'safe_strategy_opportunities', 'safe_strategy_requests', 'safe_strategy_scan', 'safe_strategy_status',
        'tennis_live_ladder', 'tennis_live_now'];
    t text;
    r record;
BEGIN
    -- omega_activity
    controllo := 'omega_activity: nella publication supabase_realtime';
    esito := CASE WHEN EXISTS (SELECT 1 FROM pg_publication_tables WHERE pubname = 'supabase_realtime'
                               AND schemaname = 'public' AND tablename = 'omega_activity') THEN 'OK' ELSE 'KO' END;
    dettaglio := NULL; RETURN NEXT;
    controllo := 'omega_activity: SELECT ad authenticated';
    esito := CASE WHEN has_table_privilege('authenticated', 'public.omega_activity', 'SELECT') THEN 'OK' ELSE 'KO' END;
    RETURN NEXT;
    controllo := 'omega_activity: policy SELECT owner-only per authenticated';
    esito := CASE WHEN EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'omega_activity'
                               AND policyname = 'omega_activity_select_owner' AND cmd = 'SELECT') THEN 'OK' ELSE 'KO' END;
    RETURN NEXT;
    controllo := 'omega_activity: RLS attiva e anon senza SELECT';
    esito := CASE WHEN (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.omega_activity'::regclass)
                   AND NOT has_table_privilege('anon', 'public.omega_activity', 'SELECT') THEN 'OK' ELSE 'KO' END;
    RETURN NEXT;

    -- anon: nessun privilegio sulle relazioni, salvo INSERT su leads
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj, c.relname
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') LOOP
        IF r.relname = 'leads' THEN
            controllo := 'anon su leads: solo INSERT';
            esito := CASE WHEN has_table_privilege('anon', r.oid, 'INSERT')
                           AND NOT has_table_privilege('anon', r.oid, 'SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
                          THEN 'OK' ELSE 'KO' END;
            dettaglio := NULL; RETURN NEXT;
        ELSIF has_table_privilege('anon', r.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
            controllo := 'anon ha ancora privilegi su ' || r.obj; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
        END IF;
    END LOOP;

    -- viste con security_invoker
    FOR r IN SELECT c.oid::regclass::text AS obj, c.reloptions
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind = 'v' LOOP
        controllo := 'vista ' || r.obj || ': security_invoker';
        esito := CASE WHEN r.reloptions @> ARRAY['security_invoker=on'] OR r.reloptions @> ARRAY['security_invoker=true']
                      THEN 'OK' ELSE 'KO' END;
        dettaglio := array_to_string(r.reloptions, ','); RETURN NEXT;
    END LOOP;

    -- le 11 RPC: anon non esegue; authenticated conserva quelle che la UI usa
    FOR r IN SELECT p.oid, p.oid::regprocedure::text AS fn, p.proname
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public'
                AND p.proname IN ('get_betfair_fixtures', 'get_betfair_odds', 'get_betfair_full_odds',
                                  'get_betfair_direction_odds', 'get_direction', 'get_omega_proposte',
                                  'upsert_cash_movement', 'get_cash_movements', 'upsert_imported_trade',
                                  'set_trade_time_operative', 'leagues_needing_retrain') LOOP
        controllo := 'RPC ' || r.fn || ': anon NON esegue';
        esito := CASE WHEN has_function_privilege('anon', r.oid, 'EXECUTE') THEN 'KO' ELSE 'OK' END;
        dettaglio := NULL; RETURN NEXT;
        controllo := 'RPC ' || r.fn || ': service_role esegue';
        esito := CASE WHEN has_function_privilege('service_role', r.oid, 'EXECUTE') THEN 'OK' ELSE 'KO' END;
        RETURN NEXT;
        IF r.proname NOT IN ('upsert_cash_movement', 'upsert_imported_trade', 'leagues_needing_retrain') THEN
            controllo := 'RPC ' || r.fn || ': authenticated (UI) esegue';
            esito := CASE WHEN has_function_privilege('authenticated', r.oid, 'EXECUTE') THEN 'OK' ELSE 'KO' END;
            RETURN NEXT;
        END IF;
    END LOOP;

    -- la UI (authenticated) legge ancora le sue tabelle dirette
    FOREACH t IN ARRAY v_ui_dirette LOOP
        CONTINUE WHEN to_regclass('public.' || t) IS NULL;
        controllo := 'UI legge ' || t || ' (SELECT authenticated + policy)';
        esito := CASE WHEN has_table_privilege('authenticated', ('public.' || t)::regclass, 'SELECT')
                       AND EXISTS (SELECT 1 FROM pg_policies pol WHERE pol.schemaname = 'public' AND pol.tablename = t
                                   AND pol.cmd IN ('SELECT', 'ALL')
                                   AND (pol.roles && ARRAY['authenticated', 'public']::name[]))
                      THEN 'OK' ELSE 'KO' END;
        dettaglio := NULL; RETURN NEXT;
    END LOOP;

    -- realtime della UI: pubblicata + SELECT + policy (INFO = difetto preesistente)
    FOREACH t IN ARRAY v_ui_realtime LOOP
        IF to_regclass('public.' || t) IS NULL THEN
            controllo := 'realtime UI ' || t; esito := 'INFO'; dettaglio := 'tabella assente nel DB'; RETURN NEXT;
            CONTINUE;
        END IF;
        controllo := 'realtime UI ' || t;
        dettaglio := concat_ws(', ',
            CASE WHEN NOT EXISTS (SELECT 1 FROM pg_publication_tables WHERE pubname = 'supabase_realtime'
                                  AND schemaname = 'public' AND tablename = t) THEN 'NON pubblicata' END,
            CASE WHEN NOT has_table_privilege('authenticated', ('public.' || t)::regclass, 'SELECT')
                 THEN 'authenticated senza SELECT' END,
            CASE WHEN NOT EXISTS (SELECT 1 FROM pg_policies pol WHERE pol.schemaname = 'public' AND pol.tablename = t
                                  AND pol.cmd IN ('SELECT', 'ALL')
                                  AND (pol.roles && ARRAY['authenticated', 'public']::name[]))
                 THEN 'nessuna policy SELECT per authenticated' END);
        esito := CASE WHEN dettaglio = '' THEN 'OK' ELSE 'INFO' END;
        RETURN NEXT;
    END LOOP;

    -- service_role: tutto su tutte le tabelle
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                AND NOT (has_table_privilege('service_role', c.oid, 'SELECT')
                     AND has_table_privilege('service_role', c.oid, 'INSERT')
                     AND has_table_privilege('service_role', c.oid, 'UPDATE')
                     AND has_table_privilege('service_role', c.oid, 'DELETE')) LOOP
        controllo := 'service_role senza CRUD completo su ' || r.obj; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
    END LOOP;
    controllo := 'service_role ha BYPASSRLS';
    esito := CASE WHEN (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN 'OK' ELSE 'KO' END;
    dettaglio := NULL; RETURN NEXT;
END
$v$;
REVOKE ALL ON FUNCTION sicurezza_bk.verifica_b1() FROM PUBLIC, anon, authenticated, service_role;

-- ============================================================================
-- ROLLBACK DEL BLOCCO 1 (NON eseguire insieme all'applicazione!)
-- Riporta grant, RLS, policy, viste, publication allo stato fotografato
-- prima del blocco 1. Copiare nel SQL Editor SOLO se serve tornare indietro:
--
--     BEGIN;
--     SELECT sicurezza_bk.ripristina('B1');
--     COMMIT;
--
-- Nota: se dopo il blocco 1 sono stati applicati i blocchi 2 e/o 3, prima si
-- ripristinano quelli, in ordine inverso: B3, poi B2, poi B1.
-- La fotografia resta in sicurezza_bk.fotografia (non si cancella da sola).
-- ============================================================================
