-- ============================================================================
-- CORREZIONE di mike_storico_per_modalita_2026-09-14.sql — l'alias sbagliato
-- ============================================================================
-- ERRORE MIO, trovato provando la funzione invece di fidarmi di averla scritta
-- bene. In `get_mike_day_trades` avevo passato il filtro come `t.mode = '...'`,
-- ma le due funzioni condivise usano alias DIVERSI:
--
--     trading_daily_history  → alias  t   (e li' `t.mode` e' giusto)
--     trading_day_trades     → alias  o   per le aperture  ← QUI
--
-- Risultato: ogni chiamata a `get_mike_day_trades` falliva con
--     ERROR 42P01: missing FROM-clause entry for table "t"
-- cioe' **l'elenco delle operazioni di un giorno era completamente rotto** per
-- Mike, in entrambe le modalita'. Non «impreciso»: rotto, per tutti i giorni.
--
-- Safe Strategy lo aveva gia' fatto giusto (`safe_strategy_paper_live`, riga
-- ~519: «trading_day_trades usa ``o`` per le aperture») — quindi la differenza
-- era perfino documentata, e l'ho ignorata perche' ho dato per scontato che le
-- due funzioni condivise si somigliassero. Non e' bastato leggere la firma:
-- serviva leggere il CORPO.
--
-- La lezione, che vale oltre questo caso: una funzione che costruisce SQL in
-- una stringa non ha modo di dirti che hai sbagliato finche' non la esegui. Il
-- filtro passato come testo e' un contratto che il compilatore non controlla —
-- va provato, sempre, e su tutte e due le funzioni, non su una sola.
--
-- VERIFICA dopo l'applicazione (deve rispondere, non sollevare):
--   SELECT jsonb_array_length(public.get_mike_day_trades(current_date, 'paper'));
--   SELECT jsonb_array_length(public.get_mike_day_trades(current_date, 'live'));
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_mike_day_trades(
    p_day  date,
    p_mode text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode text := nullif(btrim(lower(coalesce(p_mode, ''))), '');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NULL THEN
        SELECT lower(btrim(mode)) INTO v_mode FROM public.mike_control LIMIT 1;
        v_mode := coalesce(v_mode, 'paper');
    END IF;
    IF v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live)', p_mode;
    END IF;
    -- ALIAS `o`, non `t`: `trading_day_trades` chiama `o` la tabella delle
    -- APERTURE (le chiusure le raccoglie a parte come `c`). L'alias `t` esiste
    -- solo in `trading_daily_history`.
    RETURN public.trading_day_trades('mike_trades', format('o.mode = %L', v_mode),
                                     p_day, 'placed');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_day_trades(date, text) TO authenticated, service_role;
