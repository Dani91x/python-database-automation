-- ============================================================================
-- scalper_auto_mode_2026-09-25.sql - LO SCALPER CALCIO LAVORA DA SOLO SUL FEED.
--
-- Ordine dell'utente (25/09, testuale): «Lo scalper deve lavorare da solo su
-- tutte le partite del feed come gli altri bot, i suoi ordini devono finire
-- flaggati col nome "scalper", pubblicalo sul canale come tutti gli altri.»
--
-- Fino a oggi lo scalper si armava SOLO per partita dalla card (una riga
-- `scalper_control` per evento, migrations/scalper_bot.sql). Questa migrazione
-- aggiunge, SENZA toccare la strategia:
--
--   1. `scalper_control.origine` ('manuale' | 'auto', default 'manuale'): chi
--      ha armato la sessione. Il supervisore (`scalper_service.py`) ferma da
--      solo SOLO le sessioni 'auto' (partita uscita dal feed, interruttore
--      spento): quelle armate dall'utente non le tocca mai.
--   2. `scalper_service_control` (UNA riga, id=1): l'INTERRUTTORE GLOBALE,
--      come la riga di control degli altri bot. `status` running|stopped,
--      `mode` paper|live (la modalita' con cui NASCONO le sessioni automatiche:
--      `scalper_control.dry_run`), `strategia` maker|bias|both (e' il `mode`
--      della riga di sessione), `stake`, `params` (gli stessi della card, piu'
--      `auto_max_partite`, il tetto), `stats` (i fatti dell'auto-mode, scritti
--      dal supervisore). All'avvio NUOVO dell'app torna stopped/paper
--      (`avvio_app.ferma_al_nuovo_avvio`, FASE A): mai ereditato.
--   3. RPC owner-only: `scalper_auto_activate` (accende, sceglie paper/live),
--      `scalper_auto_stop` (spegne E ferma tutte le sessioni attive: e' il
--      FERMA della Control Room, stesse transizioni di `scalper_stop`),
--      `scalper_auto_update` (stake/params/strategia senza accendere niente).
--   4. `scalper_uscite_automatiche` ridefinita: scrive ANCHE sulla riga
--      dell'interruttore, cosi' le sessioni armate DOPO il cambio nascono con
--      la scelta dell'utente (dubbio 5 di USCITE_AUTOMATICHE_PER_BOT.md).
--   5. `scalper_activate` ridefinita con lo STESSO corpo + `origine =
--      'manuale'`: un riarmo dalla card rende la sessione dell'utente.
--   6. `get_scalper_control_room` ridefinita con lo STESSO corpo + la chiave
--      `servizio` (la riga dell'interruttore) nella risposta.
--   7. `betfair_live_orders.source`: il CHECK ammette 'scalper' (gli ordini
--      dello specchio della sessione, `scalper_session._SessionOrderMirror`).
--
-- ADDITIVA E IDEMPOTENTE. Da applicare a cura dell'utente (SQL editor di
-- Supabase), DOPO scalper_bot.sql, scalper_control_room_2026-09-24.sql,
-- pnl_betfair_reale_2026-09-24.sql e uscite_automatiche_scalper_2026-09-25.sql.
-- Richiede public.betfair_live_is_owner() (security_lockdown.sql).
-- Senza questa migrazione: l'auto-mode resta spento e lo si dice in Control
-- Room; la card per partita funziona come prima.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. chi ha armato la sessione
-- ----------------------------------------------------------------------------
ALTER TABLE public.scalper_control
    ADD COLUMN IF NOT EXISTS origine TEXT NOT NULL DEFAULT 'manuale';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'scalper_control_origine_check'
           AND conrelid = 'public.scalper_control'::regclass
    ) THEN
        ALTER TABLE public.scalper_control
            ADD CONSTRAINT scalper_control_origine_check
            CHECK (origine IN ('manuale', 'auto'));
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 2. l'interruttore globale
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scalper_service_control (
    id           SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    status       TEXT NOT NULL DEFAULT 'stopped'
                 CHECK (status IN ('running', 'stopped')),
    mode         TEXT NOT NULL DEFAULT 'paper'
                 CHECK (mode IN ('paper', 'live')),
    strategia    TEXT NOT NULL DEFAULT 'maker'
                 CHECK (strategia IN ('maker', 'bias', 'both')),
    stake        NUMERIC NOT NULL DEFAULT 25 CHECK (stake >= 2 AND stake <= 500),
    params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats        JSONB,
    started_at   TIMESTAMPTZ,
    stopped_at   TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.scalper_service_control (id) VALUES (1)
    ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.scalper_service_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scalper_service_control FROM anon, authenticated;
GRANT SELECT, UPDATE ON TABLE public.scalper_service_control TO service_role;
-- il supervisore scrive `origine` e la `source` dello specchio
GRANT SELECT, INSERT, UPDATE ON TABLE public.scalper_control TO service_role;

-- ----------------------------------------------------------------------------
-- 3a. ACCENDI (o conferma acceso). Paper/live SI SCRIVE sempre: ai soldi veri
--     si arriva scrivendolo. Gia' acceso in un'altra modalita' = rifiuto: le
--     sessioni leggono `dry_run` una volta sola all'armo, quindi cambiare
--     modalita' a caldo mischierebbe paper e live. Si spegne e si riaccende.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_auto_activate(
    p_mode      text,
    p_stake     numeric DEFAULT NULL,
    p_strategia text    DEFAULT NULL,
    p_params    jsonb   DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row  public.scalper_service_control;
    v_mode text := lower(nullif(btrim(coalesce(p_mode, '')), ''));
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalita'' non dichiarata (paper|live)';
    END IF;
    IF p_stake IS NOT NULL AND (p_stake < 2 OR p_stake > 500) THEN
        RAISE EXCEPTION 'stake fuori range [2,500]: %', p_stake;
    END IF;
    IF p_strategia IS NOT NULL AND p_strategia NOT IN ('maker', 'bias', 'both') THEN
        RAISE EXCEPTION 'strategia non valida: %', p_strategia;
    END IF;
    IF p_params IS NOT NULL AND jsonb_typeof(p_params) <> 'object' THEN
        RAISE EXCEPTION 'params non e'' un oggetto';
    END IF;

    SELECT * INTO v_row FROM public.scalper_service_control WHERE id = 1 FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO public.scalper_service_control (id) VALUES (1)
            RETURNING * INTO v_row;
    END IF;
    IF v_row.status = 'running' AND v_row.mode <> v_mode THEN
        RAISE EXCEPTION 'scalper gia'' acceso in %: spegnilo e riaccendilo in % (paper e live mai insieme)',
            v_row.mode, v_mode;
    END IF;

    UPDATE public.scalper_service_control
       SET status     = 'running',
           mode       = v_mode,
           stake      = coalesce(p_stake, stake),
           strategia  = coalesce(p_strategia, strategia),
           params     = coalesce(p_params, params),
           started_at = CASE WHEN status = 'running' THEN started_at ELSE now() END,
           stopped_at = NULL,
           updated_at = now()
     WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_auto_activate(text, numeric, text, jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_auto_activate(text, numeric, text, jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3b. SPEGNI = il FERMA della Control Room: l'interruttore torna stopped E
--     tutte le sessioni attive (automatiche e dalla card) si fermano con le
--     STESSE transizioni di `scalper_stop` (running/arming/armed -> stopping:
--     force-flat e attesa flat; requested -> stopped). Un solo gesto, atomico.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_auto_stop()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.scalper_service_control;
    v_n   integer;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.scalper_service_control
       SET status = 'stopped', stopped_at = now(), updated_at = now()
     WHERE id = 1
    RETURNING * INTO v_row;

    UPDATE public.scalper_control
       SET status = CASE WHEN status IN ('running', 'arming', 'armed')
                         THEN 'stopping' ELSE 'stopped' END,
           stopped_at = CASE WHEN status = 'requested' THEN now() ELSE stopped_at END,
           updated_at = now()
     WHERE status IN ('requested', 'arming', 'armed', 'running');
    GET DIAGNOSTICS v_n = ROW_COUNT;

    RETURN jsonb_build_object('servizio', to_jsonb(v_row), 'sessioni_fermate', v_n);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_auto_stop() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_auto_stop() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3c. stake / params / strategia SENZA accendere niente (`status` e `mode`
--     non si toccano). Vale per le sessioni armate da ora: quelle gia' armate
--     tengono i valori con cui sono nate (la sessione li legge all'armo).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_auto_update(
    p_stake     numeric DEFAULT NULL,
    p_params    jsonb   DEFAULT NULL,
    p_strategia text    DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.scalper_service_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_stake IS NOT NULL AND (p_stake < 2 OR p_stake > 500) THEN
        RAISE EXCEPTION 'stake fuori range [2,500]: %', p_stake;
    END IF;
    IF p_strategia IS NOT NULL AND p_strategia NOT IN ('maker', 'bias', 'both') THEN
        RAISE EXCEPTION 'strategia non valida: %', p_strategia;
    END IF;
    IF p_params IS NOT NULL AND jsonb_typeof(p_params) <> 'object' THEN
        RAISE EXCEPTION 'params non e'' un oggetto';
    END IF;
    UPDATE public.scalper_service_control
       SET stake      = coalesce(p_stake, stake),
           params     = coalesce(p_params, params),
           strategia  = coalesce(p_strategia, strategia),
           updated_at = now()
     WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_auto_update(numeric, jsonb, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_auto_update(numeric, jsonb, text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. «uscite automatiche»: sessioni attive (come prima) + riga dell'interruttore
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_uscite_automatiche(p_automatiche boolean)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_n integer;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_automatiche IS NULL THEN
        RAISE EXCEPTION 'p_automatiche non dichiarato (true|false)';
    END IF;
    UPDATE public.scalper_control
       SET params = coalesce(params, '{}'::jsonb)
                    || jsonb_build_object('uscite_automatiche', p_automatiche),
           updated_at = now()
     WHERE status IN ('requested', 'arming', 'armed', 'running');
    GET DIAGNOSTICS v_n = ROW_COUNT;
    -- 25/09: anche le sessioni che l'auto-mode armera' DOPO nascono cosi'
    UPDATE public.scalper_service_control
       SET params = coalesce(params, '{}'::jsonb)
                    || jsonb_build_object('uscite_automatiche', p_automatiche),
           updated_at = now()
     WHERE id = 1;
    RETURN v_n;
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_uscite_automatiche(boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_uscite_automatiche(boolean) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5. scalper_activate: STESSO corpo di migrations/scalper_bot.sql + origine
--    = 'manuale' (la card e' un gesto dell'utente, anche su una riga che
--    l'auto-mode aveva armato e che ora e' ferma).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_activate(
    p_event_id text,
    p_mode     text DEFAULT 'maker',
    p_dry_run  boolean DEFAULT true,
    p_stake    numeric DEFAULT 25,
    p_params   jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.scalper_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_mode NOT IN ('maker','bias','both') THEN
        RAISE EXCEPTION 'mode non valido: %', p_mode;
    END IF;
    IF p_stake IS NULL OR p_stake < 2 OR p_stake > 500 THEN
        RAISE EXCEPTION 'stake fuori range [2,500]: %', p_stake;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.live_follow f WHERE f.event_id = p_event_id) THEN
        RAISE EXCEPTION 'evento non seguito: % (segui prima la partita)', p_event_id;
    END IF;

    INSERT INTO public.scalper_control AS c
        (event_id, status, mode, dry_run, stake, params,
         bias, bias_meta, stats, error,
         requested_at, started_at, stopped_at, heartbeat_at, updated_at, origine)
    VALUES
        (p_event_id, 'requested', p_mode, coalesce(p_dry_run, true),
         p_stake, coalesce(p_params, '{}'::jsonb),
         NULL, NULL, NULL, NULL, now(), NULL, NULL, NULL, now(), 'manuale')
    ON CONFLICT (event_id) DO UPDATE SET
        status       = 'requested',
        mode         = EXCLUDED.mode,
        dry_run      = EXCLUDED.dry_run,
        stake        = EXCLUDED.stake,
        params       = EXCLUDED.params,
        bias         = NULL,
        bias_meta    = NULL,
        error        = NULL,
        requested_at = now(),
        started_at   = NULL,
        stopped_at   = NULL,
        updated_at   = now(),
        origine      = 'manuale'
    WHERE c.status IN ('stopped','done','error','requested','armed')
    RETURNING * INTO v_row;

    IF v_row IS NULL THEN
        RAISE EXCEPTION 'scalper gia'' attivo su %: fermalo prima', p_event_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_activate(text,text,boolean,numeric,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_activate(text,text,boolean,numeric,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 6. get_scalper_control_room: STESSO corpo di
--    scalper_control_room_2026-09-24.sql + la chiave `servizio`.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_scalper_control_room(
    p_orders_limit integer DEFAULT 2000
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_oggi     date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_sessioni jsonb;
    v_ordini   jsonb;
    v_eventi   text[];
    v_servizio jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- le sessioni: vive (qualunque giorno) o toccate OGGI (giorno di Roma)
    SELECT coalesce(array_agg(c.event_id), ARRAY[]::text[])
      INTO v_eventi
      FROM public.scalper_control c
     WHERE c.status IN ('requested','arming','armed','running','stopping')
        OR (c.updated_at   AT TIME ZONE 'Europe/Rome')::date = v_oggi
        OR (c.requested_at AT TIME ZONE 'Europe/Rome')::date = v_oggi;

    SELECT coalesce(jsonb_agg(
               to_jsonb(c.*)
               || jsonb_build_object(
                    'event_name', CASE WHEN f.event_id IS NULL THEN NULL
                                       ELSE f.home_name || ' v ' || f.away_name END,
                    'league_name', f.league_name,
                    'kickoff', f.open_date,
                    'ultima_attivita_at', a.ts,
                    'ultima_attivita_kind', a.kind)
               ORDER BY c.requested_at DESC), '[]'::jsonb)
      INTO v_sessioni
      FROM public.scalper_control c
      LEFT JOIN public.live_follow f ON f.event_id = c.event_id
      LEFT JOIN LATERAL (
            SELECT x.ts, x.kind
              FROM public.scalper_activity x
             WHERE x.event_id = c.event_id
             ORDER BY x.ts DESC
             LIMIT 1
      ) a ON TRUE
     WHERE c.event_id = ANY (v_eventi);

    SELECT coalesce(jsonb_agg(to_jsonb(o.*) ORDER BY o.id), '[]'::jsonb)
      INTO v_ordini
      FROM (
        SELECT b.id, b.bet_id, b.client_order_ref, b.mode, b.event_id,
               b.market_id, b.selection_id, b.side, b.order_type, b.price,
               b.size, b.size_matched, b.size_remaining, b.size_cancelled,
               b.size_lapsed, b.size_voided, b.average_price_matched,
               b.status, b.placed_at, b.matched_at, b.updated_at, b.source,
               b.pnl_betfair, b.commissione_betfair, b.pnl_betfair_settled_at
          FROM public.betfair_live_orders b
         WHERE b.event_id = ANY (v_eventi)
           AND coalesce(b.source, 'runner') IN ('runner', 'scalper')
           AND b.client_order_ref NOT LIKE 'awlq%'
           AND b.client_order_ref NOT LIKE 'ext%'
           AND (
                 (coalesce(b.placed_at, b.updated_at) AT TIME ZONE 'Europe/Rome')::date = v_oggi
              OR (b.pnl_betfair_settled_at AT TIME ZONE 'Europe/Rome')::date = v_oggi
              OR b.status IN ('PENDING', 'EXECUTABLE')
           )
         ORDER BY b.id DESC
         LIMIT least(greatest(coalesce(p_orders_limit, 2000), 1), 5000)
      ) o;

    SELECT to_jsonb(s.*) INTO v_servizio
      FROM public.scalper_service_control s WHERE s.id = 1;

    RETURN jsonb_build_object(
        'sessions', v_sessioni,
        'orders', v_ordini,
        'servizio', v_servizio,
        'giorno', v_oggi,
        'letto_at', now());
END;
$$;
REVOKE ALL    ON FUNCTION public.get_scalper_control_room(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_scalper_control_room(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 7. betfair_live_orders.source: 'scalper' ammesso.
--    Il CHECK storico (betfair_live_account_heartbeat.sql) e' ('runner',
--    'account'). Se ESISTE lo si ricrea con 'scalper' in piu' e NIENT'ALTRO
--    (le righe 'bot:<ref>' della riconciliazione restano come oggi); NOT VALID
--    = le righe gia' scritte non si ricontrollano. Se NON esiste (tolto a mano)
--    non lo si reintroduce: 'scalper' e' gia' ammesso.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'betfair_live_orders_source_check'
           AND conrelid = 'public.betfair_live_orders'::regclass
    ) THEN
        ALTER TABLE public.betfair_live_orders
            DROP CONSTRAINT betfair_live_orders_source_check;
        ALTER TABLE public.betfair_live_orders
            ADD CONSTRAINT betfair_live_orders_source_check
            CHECK (source IN ('runner', 'account', 'scalper')) NOT VALID;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- VERIFICA (sola lettura, dopo l'applicazione)
--   SELECT id, status, mode, strategia, stake, params, started_at
--     FROM public.scalper_service_control;           -- 1 riga, stopped/paper
--   SELECT column_name, column_default FROM information_schema.columns
--    WHERE table_name = 'scalper_control' AND column_name = 'origine';
--   SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'betfair_live_orders_source_check';
--   SELECT p.proname, has_function_privilege('anon', p.oid, 'EXECUTE') AS anon
--     FROM pg_proc p WHERE p.proname IN ('scalper_auto_activate',
--       'scalper_auto_stop', 'scalper_auto_update');   -- anon = f
-- ----------------------------------------------------------------------------
