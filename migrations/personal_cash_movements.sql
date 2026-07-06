-- ============================================================================
-- personal_cash_movements.sql — Movimenti di cassa Betfair (depositi/prelievi)
--
-- Traccia i DEPOSITI e PRELIEVI dal conto Betfair (Account API getAccountStatement),
-- per avere il quadro mensile completo (quanto immesso/prelevato). Sono movimenti
-- di CASSA: NON sono trade e NON entrano nell'equity curve del P&L (che resta pura
-- performance di trading). Servono a riconciliare il saldo reale.
--
-- Idempotente: chiave transaction_id (id transazione Betfair) UNIQUE.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.personal_cash_movements (
    id             BIGSERIAL PRIMARY KEY,
    transaction_id TEXT NOT NULL UNIQUE,     -- id transazione Betfair (idempotenza)
    ts             TIMESTAMPTZ NOT NULL,     -- istante del movimento
    move_date      DATE NOT NULL,            -- giorno (per raggruppamenti mensili)
    type           TEXT NOT NULL CHECK (type IN ('DEPOSIT','WITHDRAWAL')),
    amount         NUMERIC NOT NULL,         -- FIRMATO: deposito +, prelievo -
    balance        NUMERIC,                  -- saldo conto dopo il movimento
    description    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pcm_date ON public.personal_cash_movements (move_date);

ALTER TABLE public.personal_cash_movements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.personal_cash_movements FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.personal_cash_movements_id_seq FROM anon, authenticated;

-- ============================================================================
-- upsert_cash_movement — inserisce/aggiorna un movimento (idempotente su tx id).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.upsert_cash_movement(p jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_type text := upper(coalesce(p->>'type',''));
    v_tx   text := NULLIF(p->>'transaction_id','');
    v_id   bigint;
BEGIN
    IF v_tx IS NULL THEN RAISE EXCEPTION 'transaction_id obbligatorio'; END IF;
    IF v_type NOT IN ('DEPOSIT','WITHDRAWAL') THEN RAISE EXCEPTION 'type invalido: %', v_type; END IF;

    INSERT INTO public.personal_cash_movements (transaction_id, ts, move_date, type, amount, balance, description)
    VALUES (
        v_tx,
        (p->>'ts')::timestamptz,
        COALESCE(NULLIF(p->>'move_date','')::date, (p->>'ts')::timestamptz::date),
        v_type,
        (p->>'amount')::numeric,
        NULLIF(p->>'balance','')::numeric,
        p->>'description')
    ON CONFLICT (transaction_id) DO UPDATE SET
        ts = EXCLUDED.ts, move_date = EXCLUDED.move_date, type = EXCLUDED.type,
        amount = EXCLUDED.amount, balance = EXCLUDED.balance, description = EXCLUDED.description
    RETURNING id INTO v_id;

    RETURN (SELECT to_jsonb(m.*) FROM public.personal_cash_movements m WHERE id = v_id);
END;
$$;

-- ============================================================================
-- get_cash_movements — movimenti nel periodo + totali (depositi/prelievi/netto cassa).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_cash_movements(p_from date DEFAULT NULL, p_to date DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v jsonb;
BEGIN
    SELECT jsonb_build_object(
        'movements', COALESCE(jsonb_agg(to_jsonb(m.*) ORDER BY m.ts DESC), '[]'::jsonb),
        'deposits',    COALESCE(sum(amount) FILTER (WHERE type = 'DEPOSIT'), 0),
        'withdrawals', COALESCE(sum(amount) FILTER (WHERE type = 'WITHDRAWAL'), 0),
        'net_cash',    COALESCE(sum(amount), 0),
        'n',           count(*)
    ) INTO v
    FROM public.personal_cash_movements m
    WHERE (p_from IS NULL OR m.move_date >= p_from)
      AND (p_to   IS NULL OR m.move_date <= p_to);
    RETURN COALESCE(v, jsonb_build_object('movements','[]'::jsonb,'deposits',0,'withdrawals',0,'net_cash',0,'n',0));
END;
$$;

REVOKE ALL ON FUNCTION public.upsert_cash_movement(jsonb) FROM public;
REVOKE ALL ON FUNCTION public.get_cash_movements(date, date) FROM public;
GRANT EXECUTE ON FUNCTION public.upsert_cash_movement(jsonb) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_cash_movements(date, date) TO authenticated, service_role;
