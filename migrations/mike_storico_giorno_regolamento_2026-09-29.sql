-- ============================================================================
-- MIKE - lo STORICO conta il giorno del REGOLAMENTO (piano Mike 29/09, M8.10)
-- ============================================================================
-- DIFETTO D10: «Posizioni chiuse» (Control Room) attribuisce una posizione al
-- giorno in cui e' stata REGOLATA; lo Storico di Mike al giorno in cui e' stata
-- PIAZZATA. Una partita pre-partita delle 23:30 regolata alle 01:15 finiva in due
-- giorni diversi nelle due pagine. Decisione dell'utente: «uniformare»; criterio
-- scelto dal coordinatore: il giorno del REGOLAMENTO, come gia' fa la Control Room.
--
-- COSA CAMBIA: SOLO l'ultimo argomento con cui le due RPC di Mike chiamano il
-- motore comune (`trading_daily_history` / `trading_day_trades`): 'placed' ->
-- 'settled'. Il corpo e' quello VIVO di `mike_storico_per_modalita_2026-09-14.sql`
-- con la correzione dell'alias di `mike_storico_per_modalita_fix_alias_2026-09-14.sql`
-- (`o.mode` per `trading_day_trades`). Il motore comune supporta gia' 'settled'
-- (e' il suo valore di serie: `storico_esito_a_zero_2026-09-26.sql` riga 34,
-- `mike_history_v2.sql` riga 274). Omega e Safe NON cambiano.
--
-- Stesse firme (date,date,text) e (date,text), stessi permessi. Idempotente
-- (CREATE OR REPLACE). Nessuna modifica ai dati.
--
-- DA SAPERE: la pagina «Storico calcio» (`lib/storicoSport.ts`) somma per giorno
-- Omega, Safe e Mike: dopo questa migrazione Mike vi entra per regolamento, gli
-- altri due per piazzamento (differenza solo sulle posizioni a cavallo della
-- mezzanotte). La pagina di Mike va aggiornata insieme (patch MIKE_P6_4: il testo
-- dello Storico e il dettaglio del giorno usano 'settled' per Mike).
--
-- VERIFICA dopo l'applicazione (devono rispondere, non sollevare):
--   SELECT jsonb_array_length(public.get_mike_daily(NULL, NULL, 'paper'));
--   SELECT jsonb_array_length(public.get_mike_day_trades(current_date, 'paper'));
-- Confronto col prima (stessa modalita', ultimi 30 giorni): il TOTALE del P&L non
-- cambia, cambia solo il giorno a cui va:
--   SELECT sum((r->>'pnl_realized')::numeric)
--     FROM jsonb_array_elements(public.get_mike_daily(current_date - 30, current_date, 'paper')) r;
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_mike_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL,
    p_mode text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today  date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mode   text := nullif(btrim(lower(coalesce(p_mode, ''))), '');
    v_filter text;
    v_rows   jsonb;
    v_out    jsonb := '[]'::jsonb;
    v_row    jsonb;
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
    v_filter := format('t.mode = %L', v_mode);

    v_rows := public.trading_daily_history(
        'mike_trades',
        $e$coalesce(t.role, t.strategy)$e$,
        $e$'calcio'$e$,
        v_filter,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        NULL,
        -- M8.10 (29/09): giorno del REGOLAMENTO, come «Posizioni chiuse»
        'settled');

    FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP
        v_out := v_out || jsonb_build_array(
            v_row - 'goal' || jsonb_build_object('goal', NULL, 'mode', v_mode));
    END LOOP;
    RETURN v_out;
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_daily(date, date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_daily(date, date, text) TO authenticated, service_role;


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
    -- ALIAS `o` (aperture di `trading_day_trades`), vedi il fix del 14/09.
    -- M8.10 (29/09): 'settled' = anche le posizioni REGOLATE nel giorno.
    RETURN public.trading_day_trades('mike_trades', format('o.mode = %L', v_mode),
                                     p_day, 'settled');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_day_trades(date, text) TO authenticated, service_role;

-- Verifica (sola lettura), dopo l'applicazione: le due chiamate devono rispondere, non sollevare.
--   SELECT jsonb_array_length(public.get_mike_daily(NULL, NULL, 'paper'));
--   SELECT jsonb_array_length(public.get_mike_day_trades(current_date, 'paper'));
