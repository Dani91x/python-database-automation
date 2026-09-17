-- ============================================================================
-- tennis_bot_service_control_2026-09-17.sql
-- L'INTERRUTTORE PER BOT DELLA CONTROL ROOM (prerequisito di F3).
--
-- PERCHE' (17/09 sera): in Control Room ogni bot e' una riga INDIPENDENTE con
-- paper/live e stake, e la sua accensione vale per TUTTI gli eventi che passano
-- il suo filtro. Il tennis oggi ha solo `tennis_bot_control`, che e' PER EVENTO
-- (`tennis_bot_arm(event_id, bot_key, ...)`): e' il meccanismo INTERNO giusto,
-- ma non e' un interruttore, ed e' il motivo per cui i quattro bot tennis non
-- esistono nel modello della Control Room
-- (`AUDIT_4_BOT_TENNIS_2026-09-17.md` §H).
--
-- Questa tabella E' l'interruttore: una riga per `bot_key`, con lo stesso
-- vocabolario degli altri servizi (`status` + `mode` + `params` + `stats`),
-- cosi' il modello condiviso del frontend (`frontend/src/lib/interruttori.ts`)
-- la legge come legge Omega, Safe e Mike. Quando la riga e' `running`, il
-- runner tennis arma il bot su ogni evento tennis in gioco che passa il filtro
-- del bot — e l'armatura per evento resta esattamente quella di sempre.
--
-- ⚠️ NON APPLICATA. Le migrazioni le applica l'utente (CLAUDE.md). Finche' non
--    c'e', nessuno la interroga e niente cambia.
--
-- MONEY-CRITICAL: OWNER-ONLY; `mode` si SCRIVE sempre, non si eredita mai
-- (regola del 14/09: i soldi veri si raggiungono solo scrivendolo). IDEMPOTENTE.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tennis_bot_service_control (
    bot_key      TEXT PRIMARY KEY
                    CHECK (bot_key IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')),
    status       TEXT NOT NULL DEFAULT 'stopped'
                    CHECK (status IN ('stopped','running','stopping','error')),
    mode         TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper','live')),
    stake        NUMERIC NOT NULL DEFAULT 2 CHECK (stake >= 0 AND stake <= 100000),
    params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats        JSONB,          -- porta l'APP_BOOT_ID (guardia d'avvio)
    error        TEXT,
    started_at   TIMESTAMPTZ,
    stopped_at   TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.tennis_bot_service_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.tennis_bot_service_control FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- accensione: la modalita' si SCRIVE sempre, i params non si azzerano mai
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_bot_service_activate(
    p_bot_key text, p_mode text, p_stake numeric, p_params jsonb
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.tennis_bot_service_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NULL OR lower(p_mode) NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode obbligatoria (paper|live): non si eredita mai';
    END IF;
    INSERT INTO public.tennis_bot_service_control AS c
        (bot_key, status, mode, stake, params, error, started_at, stopped_at, updated_at)
    VALUES (p_bot_key, 'running', lower(p_mode), coalesce(p_stake, 2),
            coalesce(p_params, '{}'::jsonb), NULL, now(), NULL, now())
    ON CONFLICT (bot_key) DO UPDATE SET
        status = 'running', mode = lower(p_mode),
        stake = coalesce(p_stake, c.stake),
        -- ⚠️ `coalesce(p_params, c.params)`, MAI `coalesce(p_params,'{}')`:
        -- azzerare i params alla riaccensione e' il difetto 24 del catalogo.
        params = coalesce(p_params, c.params),
        error = NULL, started_at = now(), stopped_at = NULL, updated_at = now()
    RETURNING * INTO v_row;
    RETURN to_json(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION public.tennis_bot_service_stop(p_bot_key text)
RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.tennis_bot_service_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    -- `stopping`, non `stopped`: lo stato finale lo scrive il runner quando le
    -- posizioni sono chiuse. Uno `stopped` scritto dalla UI sarebbe bugiardo.
    UPDATE public.tennis_bot_service_control
       SET status = 'stopping', stopped_at = now(), updated_at = now()
     WHERE bot_key = p_bot_key
    RETURNING * INTO v_row;
    RETURN to_json(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION public.get_tennis_bot_services()
RETURNS json
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_rows json;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(json_agg(to_jsonb(s.*) ORDER BY s.bot_key), '[]'::json)
      INTO v_rows FROM public.tennis_bot_service_control s;
    RETURN json_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_bot_service_activate(text, text, numeric, jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_service_activate(text, text, numeric, jsonb) TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.tennis_bot_service_stop(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_service_stop(text) TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_tennis_bot_services() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_services() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 17/09 (Control Room, UI) — CAMBIARE SENZA ACCENDERE.
--
-- `tennis_bot_service_activate` porta `status` a 'running': usarlo per cambiare
-- lo STAKE o la MODALITA' di un bot FERMO lo accenderebbe. «I bot li accende
-- solo l'utente» — quindi serve la gemella che NON tocca mai `status`, come
-- `omega_update_params` / `mike_update_params` per il calcio.
--
-- Ogni argomento e' OPZIONALE e NULL vuol dire «non toccare»: `p_mode` NULL
-- conserva la modalita' (non la eredita: resta quella gia' SCRITTA), `p_params`
-- NULL conserva i parametri (azzerarli alla riscrittura e' il difetto 24).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_bot_service_update_params(
    p_bot_key text, p_mode text DEFAULT NULL, p_stake numeric DEFAULT NULL,
    p_params jsonb DEFAULT NULL
) RETURNS json
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.tennis_bot_service_control;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_mode IS NOT NULL AND lower(p_mode) NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida: %', p_mode;
    END IF;
    -- la riga DEVE esistere: creare qui una riga nuova vorrebbe dire inventare
    -- uno `status` e una `mode` che nessuno ha scelto.
    UPDATE public.tennis_bot_service_control AS c
       SET mode   = coalesce(lower(p_mode), c.mode),
           stake  = coalesce(p_stake, c.stake),
           params = coalesce(p_params, c.params),
           updated_at = now()
     WHERE c.bot_key = p_bot_key
    RETURNING * INTO v_row;
    IF v_row.bot_key IS NULL THEN
        RAISE EXCEPTION 'bot tennis sconosciuto o mai acceso: %', p_bot_key;
    END IF;
    RETURN to_json(v_row);
END;
$$;

-- ----------------------------------------------------------------------------
-- GLI ORDINI DI OGGI dei quattro bot — le POSIZIONI APERTE della giornata e la
-- scheda partita. Non e' il P&L: quello e' `get_tennis_bot_daily`
-- (`migrations/tennis_bot_pnl_2026-09-17.sql`), e resta l'unica verita' sui
-- numeri regolati. Qui ci sono le RIGHE, per sapere che cosa c'e' a mercato.
--
-- `p_mode` NULL = tutte e due le modalita': ogni riga PORTA la sua `mode`, e
-- chi legge le tiene separate. Sommarle e' vietato (catalogo §7 punto 21), ma
-- separare righe che si portano dietro l'etichetta e' esatto.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tennis_bot_orders_today(p_mode text DEFAULT NULL)
RETURNS json
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
    v_mode text := lower(nullif(p_mode, ''));
    v_day  date := (now() AT TIME ZONE 'Europe/Rome')::date;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NOT NULL AND v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'p_mode non valida (paper|live|null): %', p_mode;
    END IF;
    SELECT coalesce(json_agg(to_jsonb(o.*) ORDER BY o.placed_at), '[]'::json)
      INTO v_rows
      FROM public.tennis_live_orders o
     WHERE o.source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
       AND (v_mode IS NULL OR lower(o.mode) = v_mode)
       AND (coalesce(o.placed_at, o.updated_at) AT TIME ZONE 'Europe/Rome')::date = v_day;
    RETURN json_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_bot_service_update_params(text, text, numeric, jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_bot_service_update_params(text, text, numeric, jsonb) TO authenticated, service_role;
REVOKE ALL    ON FUNCTION public.get_tennis_bot_orders_today(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_orders_today(text) TO authenticated, service_role;
