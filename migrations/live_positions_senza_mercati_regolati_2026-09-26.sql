-- ============================================================================
-- LIVE P&L: niente posizioni FANTASMA (FIX-A, 26/09/2026)
-- ============================================================================
-- REPERTO (E2E fase 3 sessione B, U0275): /live-pnl mostrava «1 posizioni aperte ·
-- rischio 4,40 €» per la riga betfair_live_positions 14265 (mode live, evento
-- 35797769, mercato 1.259819675, ultimo aggiornamento 10/07/2026 19:29Z) su un
-- mercato REGOLATO il 10/07 19:31Z (betfair_live_settled id 18, live, +105).
-- Il runner scrive le posizioni ma non le toglie alla regolazione.
--
-- CORREZIONE alla SORGENTE della pagina: get_live_positions_all() esclude le
-- righe il cui mercato ha gia' una regolazione nella STESSA modalita'. Nessun
-- dato toccato: la pulizia della riga 14265 e' una PROPOSTA separata
-- (migrations/PROPOSTA_pulizia_posizione_fantasma_14265_2026-09-26.sql), non
-- necessaria per la pagina.
--
-- BASE: corpo VIVO (md5 senza \r 6a4f83dfdffbc98b540f7263e3b086b1 =
-- migrations/betfair_live_pnl_journal.sql). Generato da
-- AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs. IDEMPOTENTE.
--
-- VERIFICA: SELECT jsonb_array_length(public.get_live_positions_all()->'rows');
--   (26/09: 3 invece di 4; la riga 14265 non c'e' piu')
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_live_positions_all()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(p.*) ORDER BY p.updated_at DESC), '[]'::jsonb)
      INTO v_rows
      -- FIX-A 26/09: fuori le posizioni di un mercato gia' REGOLATO nella STESSA
      -- modalita' (betfair_live_settled): il runner non le cancella alla
      -- regolazione e la pagina le mostrava come aperte, con rischio.
      FROM (SELECT z.* FROM public.betfair_live_positions z
             WHERE NOT EXISTS (SELECT 1 FROM public.betfair_live_settled s
                                WHERE s.market_id = z.market_id AND s.mode = z.mode)
             ORDER BY z.updated_at DESC LIMIT 2000) p;
    RETURN jsonb_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_live_positions_all() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_live_positions_all() TO authenticated, service_role;
