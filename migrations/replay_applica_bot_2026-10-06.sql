-- replay_applica_bot_2026-10-06.sql
--
-- Match Replay, "APPLICA BOT": il bot con il codice di produzione sulla
-- registrazione della partita (banco comune, `Betfair/stream/backtest/applica_bot.py`),
-- eseguito dal worker del Backtest Automatico (`python -m Betfair.stream.backtest.worker`).
-- La richiesta passa dalla coda esistente (`request_backtest` con
-- params.tipo = 'applica_bot'); l'esito (cronologia degli ordini del bot, righe
-- `betfair_live_orders` con l'istante `_ms`) sta qui, una riga per richiesta.
-- La applica l'utente.

CREATE TABLE IF NOT EXISTS public.replay_bot_esiti (
    request_id  UUID PRIMARY KEY
                  REFERENCES public.live_backtest_requests(id) ON DELETE CASCADE,
    esito       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.replay_bot_esiti ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.replay_bot_esiti FROM public, anon, authenticated;
GRANT ALL ON TABLE public.replay_bot_esiti TO service_role;

-- get_replay_bot_esito(p_request_id) -> {status, error_detail, esito}
CREATE OR REPLACE FUNCTION public.get_replay_bot_esito(p_request_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_req public.live_backtest_requests;
    v_esito jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT * INTO v_req FROM public.live_backtest_requests WHERE id = p_request_id;
    IF v_req.id IS NULL THEN
        RAISE EXCEPTION 'richiesta inesistente';
    END IF;
    SELECT esito INTO v_esito FROM public.replay_bot_esiti WHERE request_id = p_request_id;
    RETURN jsonb_build_object('status', v_req.status, 'error_detail', v_req.error_detail,
                              'esito', v_esito);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_replay_bot_esito(uuid) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_replay_bot_esito(uuid) TO authenticated, service_role;
