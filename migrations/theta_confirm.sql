-- ============================================================================
-- theta_confirm.sql — CONFERME MANUALI del bot THETA SCALPER (dossier 15/07).
--
-- Flusso (DB-as-bus, pattern omega_manual.sql): in modalita' MANUALE
-- (theta_confirm_mode) la sessione scalper PROPONE le azioni del theta
-- (entry / scratch / postgol) inserendo una riga 'awaiting' via service_role;
-- la UI la vede in realtime (countdown su expires_at) e decide con la RPC
-- theta_confirm_decide (claim ATOMICO: UPDATE ... WHERE status='awaiting').
--
-- SEMANTICA (spec utente confermata):
--   * la conferma e' SOLO un via-libera: i prezzi vengono SEMPRE ricalcolati
--     freschi dal bot al momento dell'esecuzione;
--   * TIMEOUT SCADUTO (autorita' del BOT, TTL 60s): le PROTEZIONI
--     (scratch/postgol) si eseguono COMUNQUE — mai posizione nuda; la ENTRY
--     scaduta/rifiutata si scarta;
--   * stati finali scritti dal bot: 'expired' (nessuna decisione in tempo)
--     e 'executed' (azione eseguita).
--
-- IDEMPOTENTE. RLS: tabella non scrivibile dalla UI; SELECT owner-only per il
-- realtime (pattern omega_manual). Richiede public.betfair_live_is_owner().
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.theta_confirm_requests (
    id           BIGSERIAL PRIMARY KEY,
    event_id     TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('entry','scratch','postgol')),
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {price,size,exit_price,exit_size,locked,line,minute,hazard_p3,...}
    status       TEXT NOT NULL DEFAULT 'awaiting'
                 CHECK (status IN ('awaiting','confirmed','rejected',
                                   'expired','executed')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT now() + interval '60 seconds',
    decided_at   TIMESTAMPTZ,        -- quando la UI ha deciso
    executed_at  TIMESTAMPTZ,        -- quando il bot ha eseguito
    result       JSONB               -- esito facoltativo scritto dal bot
);
CREATE INDEX IF NOT EXISTS idx_theta_confirm_event_status
    ON public.theta_confirm_requests (event_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_theta_confirm_awaiting
    ON public.theta_confirm_requests (status, created_at)
    WHERE status = 'awaiting';

ALTER TABLE public.theta_confirm_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.theta_confirm_requests FROM anon, authenticated;

-- Realtime per la UI (idempotente) + SELECT owner-only (pattern omega_manual).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname = 'supabase_realtime'
                     AND schemaname = 'public'
                     AND tablename = 'theta_confirm_requests') THEN
        ALTER PUBLICATION supabase_realtime
            ADD TABLE public.theta_confirm_requests;
    END IF;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;

DO $$
BEGIN
    DROP POLICY IF EXISTS theta_confirm_requests_select_owner
        ON public.theta_confirm_requests;
    CREATE POLICY theta_confirm_requests_select_owner
        ON public.theta_confirm_requests FOR SELECT TO authenticated
        USING (public.betfair_live_is_owner());
    GRANT SELECT ON TABLE public.theta_confirm_requests TO authenticated;
    REVOKE SELECT ON TABLE public.theta_confirm_requests FROM anon;
END $$;

-- ----------------------------------------------------------------------------
-- RPC: decisione UI con CLAIM ATOMICO. Solo 'awaiting' non scaduta e' decidibile
-- (doppio click / due tab: il secondo UPDATE non trova la riga e fallisce).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.theta_confirm_decide(
    p_id       bigint,
    p_decision text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.theta_confirm_requests;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_decision NOT IN ('confirmed','rejected') THEN
        RAISE EXCEPTION 'decisione non valida: % (confirmed|rejected)', p_decision;
    END IF;
    UPDATE public.theta_confirm_requests
       SET status = p_decision,
           decided_at = now()
     WHERE id = p_id
       AND status = 'awaiting'
       AND expires_at > now()
    RETURNING * INTO v_row;
    IF v_row IS NULL THEN
        RAISE EXCEPTION
            'richiesta % non decidibile (gia'' decisa, scaduta o inesistente)',
            p_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.theta_confirm_decide(bigint,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.theta_confirm_decide(bigint,text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- RPC: ultime richieste per il pannello UI (polling di riserva al realtime).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_theta_confirm_requests(
    p_event_id text,
    p_limit    integer DEFAULT 20
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb)
      INTO v
      FROM (SELECT * FROM public.theta_confirm_requests
             WHERE event_id = p_event_id
             ORDER BY created_at DESC
             LIMIT least(greatest(coalesce(p_limit, 20), 1), 100)) r;
    RETURN v;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_theta_confirm_requests(text,integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_theta_confirm_requests(text,integer) TO authenticated, service_role;
