-- ============================================================================
-- live_order_mode_control_2026-09-24.sql - LA MODALITA' ORDINI SI SCEGLIE DALLA UI
--
-- Ordine dell'utente (24/09): "devo operare dalla UI, non dal codice".
-- LIVE_ORDER_MODE (OFF/PAPER/LIVE) viveva solo nel .env: gate del trading
-- manuale dal ladder E freno di Safe/Mike/Omega sugli ordini reali.
--
-- RISORSA RIUSATA (nessuna tabella nuova): public.betfair_live_settings, la
-- riga singleton (id=1) che porta GIA' il kill-switch da UI
-- (migrations/betfair_live_controls.sql) e che il runner rilegge a ~1 s via
-- RPC get_live_settings. Stesso schema di accesso: tabella chiusa ad anon e
-- authenticated, lettura/scrittura SOLO via RPC SECURITY DEFINER owner-only
-- (public.betfair_live_is_owner(): service_role oppure l'email del proprietario).
--
-- REGOLA (lato codice, Betfair/stream/modo_ordini.py): modo effettivo = il PIU'
-- RESTRITTIVO fra il .env (tetto dell'ambiente) e order_mode (scelta dalla UI).
-- Riga/colonna assente o illeggibile -> OFF. PRIMA DI APPLICARE: finche' la
-- migrazione manca il codice nuovo vede la colonna assente = OFF, cioe'
-- nessuna APERTURA dal runner (nemmeno paper) e nessun ordine reale dai bot;
-- le chiusure restano servite.
--
-- IDEMPOTENTE. Applicare DOPO betfair_live_controls.sql e
-- betfair_live_risk_limits_v4.sql. La applica l'utente (SQL editor Supabase).
-- ROLLBACK in coda al file (commentato).
-- ============================================================================


-- ============================================================================
-- 1. Colonne nuove sulla riga singleton
-- ============================================================================
ALTER TABLE public.betfair_live_settings
    -- la scelta dalla Control Room. Nasce 'paper': dopo la migrazione nessuno
    -- ha scelto LIVE, e ai soldi veri si arriva scrivendolo (regola 14/09).
    ADD COLUMN IF NOT EXISTS order_mode            TEXT NOT NULL DEFAULT 'paper',
    ADD COLUMN IF NOT EXISTS order_mode_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS order_mode_updated_by TEXT,
    -- avvio dell'app a cui appartiene la scelta (APP_BOOT_ID, avvio_app.py):
    -- a un avvio NUOVO la scelta scende a 'paper' (mai sale)
    ADD COLUMN IF NOT EXISTS order_mode_boot_id    TEXT,
    -- il TETTO dichiarato dal runner calcio al suo avvio (LIVE_ORDER_MODE del
    -- suo .env): solo per mostrarlo in UI, il codice usa il proprio .env
    ADD COLUMN IF NOT EXISTS order_mode_tetto      TEXT,
    ADD COLUMN IF NOT EXISTS order_mode_tetto_at   TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'betfair_live_settings_order_mode_valido'
          AND conrelid = 'public.betfair_live_settings'::regclass
    ) THEN
        ALTER TABLE public.betfair_live_settings
            ADD CONSTRAINT betfair_live_settings_order_mode_valido CHECK (
                order_mode IN ('off', 'paper', 'live')
                AND (order_mode_tetto IS NULL OR order_mode_tetto IN ('off', 'paper', 'live'))
            );
    END IF;
END $$;

-- la riga singleton deve esistere (idempotente, come in betfair_live_controls.sql)
INSERT INTO public.betfair_live_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;


-- ============================================================================
-- 2. set_live_order_mode - l'interruttore della Control Room (owner-only)
--    Scrive SOLO le colonne del modo: kill-switch e limiti non si toccano.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_live_order_mode(p_mode text)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode text := lower(btrim(coalesce(p_mode, '')));
    v_row  jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode NOT IN ('off', 'paper', 'live') THEN
        RAISE EXCEPTION 'modo ordini non valido: % (ammessi: off, paper, live)', p_mode;
    END IF;
    UPDATE public.betfair_live_settings
       SET order_mode            = v_mode,
           order_mode_updated_at = now(),
           order_mode_updated_by = coalesce(nullif(auth.jwt() ->> 'email', ''),
                                            nullif(auth.jwt() ->> 'role', ''),
                                            session_user::text),
           updated_at            = now()
     WHERE id = 1;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 3. live_order_mode_avvio - chiamata dal runner calcio al suo avvio
--    (Betfair/stream/runner.py _dichiara_modo_ordini_all_avvio).
--    * p_boot_id: APP_BOOT_ID dell'avvio corrente;
--    * p_modo: il modo da scrivere se e' un avvio NUOVO ('paper'), NULL se e'
--      un riavvio da watchdog (stesso avvio): NULL non tocca il modo;
--    * p_tetto: LIVE_ORDER_MODE del .env del runner (solo per la UI).
--    DIFESA IN PROFONDITA': questa RPC puo' solo SCENDERE (off < paper < live),
--    mai salire, qualunque p_modo le si passi.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.live_order_mode_avvio(p_boot_id text, p_modo text, p_tetto text)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_modo  text := nullif(lower(btrim(coalesce(p_modo, ''))), '');
    v_tetto text := nullif(lower(btrim(coalesce(p_tetto, ''))), '');
    v_row   jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_modo IS NOT NULL AND v_modo NOT IN ('off', 'paper', 'live') THEN
        RAISE EXCEPTION 'modo ordini non valido: %', p_modo;
    END IF;
    IF v_tetto IS NOT NULL AND v_tetto NOT IN ('off', 'paper', 'live') THEN
        RAISE EXCEPTION 'tetto non valido: %', p_tetto;
    END IF;
    UPDATE public.betfair_live_settings s
       SET order_mode = CASE
               WHEN v_modo IS NULL THEN s.order_mode
               WHEN array_position(ARRAY['off','paper','live'], v_modo)
                    < array_position(ARRAY['off','paper','live'], s.order_mode)
                   THEN v_modo
               ELSE s.order_mode
           END,
           order_mode_updated_at = CASE
               WHEN v_modo IS NOT NULL
                    AND array_position(ARRAY['off','paper','live'], v_modo)
                        < array_position(ARRAY['off','paper','live'], s.order_mode)
                   THEN now()
               ELSE s.order_mode_updated_at
           END,
           order_mode_updated_by = CASE
               WHEN v_modo IS NOT NULL
                    AND array_position(ARRAY['off','paper','live'], v_modo)
                        < array_position(ARRAY['off','paper','live'], s.order_mode)
                   THEN 'avvio_app'
               ELSE s.order_mode_updated_by
           END,
           order_mode_boot_id  = nullif(btrim(coalesce(p_boot_id, '')), ''),
           order_mode_tetto    = v_tetto,
           order_mode_tetto_at = now()
     WHERE s.id = 1;
    SELECT to_jsonb(s.*) INTO v_row FROM public.betfair_live_settings s WHERE s.id = 1;
    RETURN v_row;
END;
$$;


-- ============================================================================
-- 4. GRANT espliciti (regola B3: da ora ogni migrazione li dichiara)
--    Tabella: SOLO service_role (il runner la legge via RPC, ma i grant della
--    tabella restano dichiarati per il 30/10). authenticated e anon: nessun
--    accesso diretto alla tabella, come oggi (RLS attiva, REVOKE in
--    betfair_live_controls.sql): la UI passa SOLO dalle RPC owner-only.
-- ============================================================================
GRANT SELECT, UPDATE ON TABLE public.betfair_live_settings TO service_role;
REVOKE ALL ON TABLE public.betfair_live_settings FROM anon, authenticated;

REVOKE ALL    ON FUNCTION public.set_live_order_mode(text)                FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_live_order_mode(text)                TO authenticated, service_role;
-- l'avvio lo dichiara SOLO il runner (service_role): la UI non ne ha bisogno
REVOKE ALL    ON FUNCTION public.live_order_mode_avvio(text, text, text)  FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.live_order_mode_avvio(text, text, text)  TO service_role;
-- get_live_settings restituisce to_jsonb(s.*): le colonne nuove arrivano da sole
-- (grant invariati, ridichiarati per completezza)
REVOKE ALL    ON FUNCTION public.get_live_settings()                      FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_settings()                      TO authenticated, service_role;


-- ============================================================================
-- VERIFICA (sola lettura, da eseguire dopo):
--   SELECT order_mode, order_mode_updated_at, order_mode_updated_by,
--          order_mode_boot_id, order_mode_tetto, order_mode_tetto_at
--     FROM public.betfair_live_settings WHERE id = 1;     -- atteso: 'paper', ...
-- ============================================================================


-- ============================================================================
-- ROLLBACK (commentato: eseguire a mano SOLO se si torna al codice di prima;
-- con il codice nuovo la colonna assente vale OFF = nessuna apertura)
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.live_order_mode_avvio(text, text, text);
-- DROP FUNCTION IF EXISTS public.set_live_order_mode(text);
-- ALTER TABLE public.betfair_live_settings
--     DROP CONSTRAINT IF EXISTS betfair_live_settings_order_mode_valido;
-- ALTER TABLE public.betfair_live_settings
--     DROP COLUMN IF EXISTS order_mode_tetto_at,
--     DROP COLUMN IF EXISTS order_mode_tetto,
--     DROP COLUMN IF EXISTS order_mode_boot_id,
--     DROP COLUMN IF EXISTS order_mode_updated_by,
--     DROP COLUMN IF EXISTS order_mode_updated_at,
--     DROP COLUMN IF EXISTS order_mode;
