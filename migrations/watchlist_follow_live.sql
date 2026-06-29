-- ============================================================================
-- watchlist_follow_live.sql — flag "Segui live" sulla watchlist.
--
-- Aggiunge un flag ORTOGONALE allo stato (DA_VALUTARE/GIOCATA/SCARTATA): una
-- partita può essere seguita live indipendentemente dal fatto che sia giocata o
-- ancora da valutare. Il runner stream sottoscrive le partite con follow_live=true
-- OLTRE a quelle GIOCATA (vedi Betfair/stream/watchlist.py). NESSUN ordine reale:
-- lo stream è solo advisory.
--
-- IDEMPOTENTE: ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS /
-- CREATE OR REPLACE FUNCTION. get_watchlist espone follow_live automaticamente
-- (usa to_jsonb(w.*)) → nessuna modifica a get_watchlist necessaria.
-- ============================================================================

-- 1) colonna flag (default false: nessuna partita seguita finché non lo accendi)
ALTER TABLE public.personal_watchlist
    ADD COLUMN IF NOT EXISTS follow_live BOOLEAN NOT NULL DEFAULT false;

-- 2) indice parziale: il runner filtra le "seguite", poche righe → indice piccolo
CREATE INDEX IF NOT EXISTS idx_pw_follow_live
    ON public.personal_watchlist (follow_live)
    WHERE follow_live;

-- ============================================================================
-- RPC: set_watchlist_follow_live — accende/spegne il "Segui live" (toggle UI).
-- Mirror di set_watchlist_decision: VOLATILE, SECURITY DEFINER, ritorna la riga.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.set_watchlist_follow_live(
    p_id     bigint,
    p_follow boolean
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row jsonb;
BEGIN
    IF p_id IS NULL THEN
        RAISE EXCEPTION 'p_id nullo';
    END IF;
    IF p_follow IS NULL THEN
        RAISE EXCEPTION 'p_follow obbligatorio (true/false)';
    END IF;

    UPDATE public.personal_watchlist SET
        follow_live = p_follow,
        updated_at  = now()
    WHERE id = p_id
    RETURNING to_jsonb(personal_watchlist.*) INTO v_row;

    IF v_row IS NULL THEN
        RAISE EXCEPTION 'watchlist id % non trovato', p_id;
    END IF;
    RETURN v_row;
END;
$$;

-- ============================================================================
-- GRANTS — stesso pattern delle altre RPC watchlist:
-- REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role; revoke anon.
-- ============================================================================
REVOKE ALL     ON FUNCTION public.set_watchlist_follow_live(bigint, boolean) FROM public;
GRANT EXECUTE  ON FUNCTION public.set_watchlist_follow_live(bigint, boolean) TO authenticated, service_role;
REVOKE EXECUTE ON FUNCTION public.set_watchlist_follow_live(bigint, boolean) FROM anon;
