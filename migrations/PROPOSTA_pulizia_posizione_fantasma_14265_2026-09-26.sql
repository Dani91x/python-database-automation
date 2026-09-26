-- ============================================================================
-- PROPOSTA (NON applicata, NON necessaria per la pagina) - FIX-A 26/09/2026
-- Pulizia della posizione FANTASMA betfair_live_positions id 14265
-- ============================================================================
-- La riga: mode 'live', evento 35797769, mercato 1.259819675, selezione 5851482,
-- esposizione 4,40, ultimo aggiornamento 10/07/2026 19:29:57Z. Il mercato e'
-- REGOLATO dal 10/07/2026 19:31:29Z (betfair_live_settled id 18, live,
-- profit +105, source 'cleared'). Il runner scrive le posizioni ma non le toglie
-- alla regolazione.
--
-- DECISIONE (referto FIX_A_SOLDI_MODALITA_2026-09-26.md, KO4): la correzione e'
-- alla SORGENTE, nella query (migrations/live_positions_senza_mercati_regolati_
-- 2026-09-26.sql): una posizione su un mercato regolato nella stessa modalita'
-- non e' aperta, oggi e per ogni fantasma futuro. Questa pulizia e' solo igiene
-- della tabella: la si applica SE si vuole, DOPO aver riletto la riga.
--
-- Guardie: cancella SOLO quella riga, SOLO se il mercato risulta ancora regolato
-- nella stessa modalita'; transazione con conteggio atteso = 1.
-- ============================================================================
BEGIN;

-- 1) rileggere PRIMA (deve tornare una riga, quella descritta sopra)
SELECT p.*, s.id AS settled_id, s.settled_at, s.profit
  FROM public.betfair_live_positions p
  JOIN public.betfair_live_settled s ON s.market_id = p.market_id AND s.mode = p.mode
 WHERE p.id = 14265;

-- 2) cancellare con le guardie
DO $$
DECLARE v_n integer;
BEGIN
    DELETE FROM public.betfair_live_positions p
     WHERE p.id = 14265
       AND p.mode = 'live'
       AND p.market_id = '1.259819675'
       AND EXISTS (SELECT 1 FROM public.betfair_live_settled s
                    WHERE s.market_id = p.market_id AND s.mode = p.mode);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> 1 THEN
        RAISE EXCEPTION 'attesa 1 riga, cancellate %: annullo', v_n;
    END IF;
END $$;

COMMIT;
