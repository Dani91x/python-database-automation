-- ============================================================================
-- SICUREZZA DB - BLOCCO 2 di 3 - RLS SU TUTTO + POLICY PER authenticated (24/09/2026)
-- ============================================================================
-- Prerequisito: BLOCCO 1 applicato e verificato (verifica_b1 senza KO).
-- Documento guida: SICUREZZA_DB_2026-09-24.md. Si applica dal SQL Editor
-- (ruolo postgres), per intero; idempotente.
--
-- COSA FA
--   1. controllo di sicurezza PRIMA di toccare qualcosa: se una RPC SECURITY
--      DEFINER appartiene a un ruolo che NON bypasserebbe la nuova RLS, il
--      blocco si FERMA (nessuna modifica) e dice quale.
--   2. RLS attiva su OGNI tabella di public che oggi non ce l'ha
--      (dallo snapshot del 23/09: match_odds, standings, injuries, match_events,
--      match_lineups, match_player_stats, match_team_stats, top_scorers,
--      top_assists, top_cards, api_call_log, season_backfill_state,
--      signal_history, analytics_bets, betfair_market_odds, book_odds_cache,
--      direction_pagella, ed eventuali altre trovate nel DB).
--   3. Su quelle stesse tabelle, se authenticated oggi ha SELECT, una policy
--      `<tabella>_select_owner` (SELECT, solo owner via betfair_live_is_owner()):
--      l'owner loggato continua a leggere esattamente come prima.
--      NESSUNA policy di scrittura: authenticated non scrive MAI direttamente
--      (il frontend scrive solo via RPC SECURITY DEFINER, e con INSERT su leads
--      che ha gia' RLS e policy).
--   4. NIENTE `FORCE ROW LEVEL SECURITY`: il proprietario (postgres, che e'
--      anche il proprietario di tutte le RPC DEFINER) continua a bypassarla.
--
-- PERCHE' NON ROMPE NULLA
--   * service_role (bot Python, runner, GitHub Actions, make-daily-post) ha
--     BYPASSRLS: la RLS non lo riguarda (verifica_b2 lo controlla).
--   * Le 132 RPC chiamate dal frontend sono TUTTE SECURITY DEFINER (analisi
--     statica di migrations/ e sql/): girano come postgres, proprietario delle
--     tabelle, quindi la RLS non si applica (niente FORCE).
--   * Le letture dirette del frontend (.from) sono su fixture_predictions e su
--     tabelle del gruppo B, che hanno GIA' RLS e policy: non cambiano.
--   * Le tabelle nuove sotto RLS non sono lette da authenticated con .from() ne'
--     in realtime; se lo fossero, la policy owner-only le lascia leggere.
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
-- APPLICAZIONE DEL BLOCCO 2 (una sola transazione)
-- ============================================================================
BEGIN;
SET LOCAL search_path = pg_catalog;

-- ---------------------------------------------------------------------------
-- 2.0  CONTROLLO BLOCCANTE: chi possiede le RPC SECURITY DEFINER deve
--      bypassare la RLS delle tabelle che sta per riceverla: o e' superuser/
--      BYPASSRLS, o e' il proprietario della tabella. Altrimenti STOP.
--      Controllo prudente (per ruolo, non per singola query): un falso allarme
--      ferma il blocco senza danni; lo si indaga e si decide.
-- ---------------------------------------------------------------------------
DO $b2_guardia$
DECLARE
    v_problemi text;
BEGIN
    SELECT string_agg(DISTINCT format('RPC di %s vs tabella %s di %s', fo.owner, t.obj, t.owner), '; ')
      INTO v_problemi
      FROM (SELECT DISTINCT pg_get_userbyid(p.proowner) AS owner
              FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              JOIN pg_roles ro ON ro.oid = p.proowner
             WHERE n.nspname = 'public' AND p.prosecdef
               AND NOT (ro.rolsuper OR ro.rolbypassrls)) fo
      JOIN (SELECT c.oid::regclass::text AS obj, pg_get_userbyid(c.relowner) AS owner
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity) t
        ON t.owner <> fo.owner;
    IF v_problemi IS NOT NULL THEN
        RAISE EXCEPTION 'BLOCCO 2 FERMATO, nessuna modifica: %', v_problemi;
    END IF;

    IF NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN
        RAISE EXCEPTION 'BLOCCO 2 FERMATO: service_role senza BYPASSRLS, i bot si fermerebbero';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relforcerowsecurity) THEN
        RAISE NOTICE 'ATTENZIONE: esistono tabelle con FORCE RLS (preesistenti, non toccate)';
    END IF;
END
$b2_guardia$;

SELECT sicurezza_bk.fotografa('B2');

-- ---------------------------------------------------------------------------
-- 2.1  RLS attiva + policy SELECT owner-only dove authenticated legge oggi
-- ---------------------------------------------------------------------------
DO $b2_rls$
DECLARE
    r        record;
    v_policy text;
BEGIN
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj, c.relname
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity
              ORDER BY c.relname LOOP
        IF has_table_privilege('authenticated', r.oid, 'SELECT')
           AND NOT EXISTS (SELECT 1 FROM pg_policy pol
                            WHERE pol.polrelid = r.oid AND pol.polcmd IN ('r', '*')) THEN
            v_policy := left(r.relname, 50) || '_select_owner';
            EXECUTE format('DROP POLICY IF EXISTS %I ON %s', v_policy, r.obj);
            EXECUTE format('CREATE POLICY %I ON %s FOR SELECT TO authenticated USING (public.betfair_live_is_owner())',
                           v_policy, r.obj);
        END IF;
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', r.obj);
        -- service_role esplicito (e' gia' cosi': conferma per il 30/10)
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE %s TO service_role', r.obj);
        RAISE NOTICE 'RLS attivata su %', r.obj;
    END LOOP;
END
$b2_rls$;

COMMIT;

-- ============================================================================
-- VERIFICA DEL BLOCCO 2 (SOLA LETTURA):
--     SELECT * FROM sicurezza_bk.verifica_b2() ORDER BY esito DESC, controllo;
-- Atteso: nessun 'KO'. Poi la PROVA DI RUOLO in fondo al documento guida
-- (sezione 6: SET LOCAL ROLE authenticated/anon dentro BEGIN ... ROLLBACK).
-- ============================================================================
CREATE OR REPLACE FUNCTION sicurezza_bk.verifica_b2()
RETURNS TABLE (controllo text, esito text, dettaglio text)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $v$
DECLARE
    r record;
BEGIN
    -- nessuna tabella di public senza RLS
    FOR r IN SELECT c.oid::regclass::text AS obj
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity LOOP
        controllo := 'tabella senza RLS: ' || r.obj; esito := 'KO'; dettaglio := NULL; RETURN NEXT;
    END LOOP;
    controllo := 'tabelle di public con RLS attiva';
    esito := 'INFO';
    dettaglio := (SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity);
    RETURN NEXT;

    -- dove authenticated ha SELECT deve esserci una policy SELECT che lo riguardi
    -- (INFO e non KO: vuol dire "l'owner vede 0 righe", ma nessun client le legge)
    FOR r IN SELECT c.oid, c.oid::regclass::text AS obj, c.relname
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                AND has_table_privilege('authenticated', c.oid, 'SELECT')
                AND NOT EXISTS (SELECT 1 FROM pg_policies pol
                                 WHERE pol.schemaname = 'public' AND pol.tablename = c.relname
                                   AND pol.cmd IN ('SELECT', 'ALL')
                                   AND pol.roles && ARRAY['authenticated', 'public']::name[]) LOOP
        controllo := 'authenticated ha SELECT ma nessuna policy: ' || r.obj; esito := 'INFO';
        dettaglio := 'owner loggato vede 0 righe (preesistente)'; RETURN NEXT;
    END LOOP;

    -- le policy create dal blocco 2 sono tutte owner-only
    FOR r IN SELECT pol.tablename, pol.policyname, pol.qual
               FROM pg_policies pol
              WHERE pol.schemaname = 'public' AND pol.policyname LIKE '%\_select\_owner'
                AND NOT EXISTS (SELECT 1 FROM sicurezza_bk.fotografia f
                                 WHERE f.blocco = 'B2' AND f.tipo = 'policy'
                                   AND f.oggetto = format('%I.%I', pol.schemaname, pol.tablename)
                                   AND f.valore = pol.policyname) LOOP
        controllo := 'policy nuova ' || r.policyname || ' su ' || r.tablename;
        esito := CASE WHEN r.qual LIKE '%betfair_live_is_owner()%' THEN 'OK' ELSE 'KO' END;
        dettaglio := r.qual; RETURN NEXT;
    END LOOP;

    -- nessuna FORCE RLS introdotta
    FOR r IN SELECT c.oid::regclass::text AS obj
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'public' AND c.relforcerowsecurity LOOP
        controllo := 'FORCE RLS su ' || r.obj; esito := 'KO';
        dettaglio := 'le RPC DEFINER del proprietario verrebbero filtrate'; RETURN NEXT;
    END LOOP;

    -- ruoli
    controllo := 'service_role ha BYPASSRLS';
    esito := CASE WHEN (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN 'OK' ELSE 'KO' END;
    dettaglio := NULL; RETURN NEXT;
    FOR r IN SELECT DISTINCT pg_get_userbyid(p.proowner) AS owner, ro.rolsuper, ro.rolbypassrls
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
               JOIN pg_roles ro ON ro.oid = p.proowner
              WHERE n.nspname = 'public' AND p.prosecdef LOOP
        controllo := 'proprietario RPC DEFINER: ' || r.owner;
        esito := CASE WHEN r.rolsuper OR r.rolbypassrls
                        OR NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                                        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                                          AND pg_get_userbyid(c.relowner) <> r.owner)
                      THEN 'OK' ELSE 'KO' END;
        dettaglio := format('super=%s bypassrls=%s', r.rolsuper, r.rolbypassrls); RETURN NEXT;
    END LOOP;

    -- la UI legge ancora le sue tabelle dirette
    FOR r IN SELECT unnest(ARRAY[
                 'fixture_predictions', 'betfair_live_account', 'betfair_live_heartbeat', 'betfair_live_risk_state',
                 'live_follow', 'live_ladder', 'live_now', 'live_signals', 'mike_requests', 'safe_strategy_activity',
                 'safe_strategy_opportunities', 'safe_strategy_requests', 'safe_strategy_scan', 'safe_strategy_status',
                 'tennis_live_ladder', 'tennis_live_now', 'omega_activity']) AS t LOOP
        CONTINUE WHEN to_regclass('public.' || r.t) IS NULL;
        controllo := 'UI legge ' || r.t;
        esito := CASE WHEN has_table_privilege('authenticated', ('public.' || r.t)::regclass, 'SELECT')
                       AND EXISTS (SELECT 1 FROM pg_policies pol WHERE pol.schemaname = 'public' AND pol.tablename = r.t
                                   AND pol.cmd IN ('SELECT', 'ALL')
                                   AND pol.roles && ARRAY['authenticated', 'public']::name[])
                      THEN 'OK' ELSE 'KO' END;
        dettaglio := NULL; RETURN NEXT;
    END LOOP;
END
$v$;
REVOKE ALL ON FUNCTION sicurezza_bk.verifica_b2() FROM PUBLIC, anon, authenticated, service_role;

-- ============================================================================
-- ROLLBACK DEL BLOCCO 2 (NON eseguire insieme all'applicazione!)
-- Disattiva la RLS sulle tabelle dove era spenta, toglie le policy nate col
-- blocco 2, riporta i grant allo stato fotografato prima del blocco 2:
--
--     BEGIN;
--     SELECT sicurezza_bk.ripristina('B2');
--     COMMIT;
--
-- Se il blocco 3 e' gia' applicato: prima ripristina('B3'), poi ripristina('B2').
-- ============================================================================
