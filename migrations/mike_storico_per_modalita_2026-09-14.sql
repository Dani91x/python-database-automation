-- ============================================================================
-- MIKE — lo STORICO non deve mescolare euro veri ed euro simulati (14/09/2026)
-- ============================================================================
-- IL PROBLEMA, dichiarato da ieri in COSTITUZIONE_MIKE §16 e mai chiuso.
-- `get_mike_daily` chiama `trading_daily_history` passando **NULL** come filtro,
-- e `get_mike_day_trades` fa lo stesso con `trading_day_trades`. Nessuna delle
-- due guarda `mike_trades.mode`.
--
-- Finché Mike è girato solo in paper è stato innocuo. Ma il 14/09 la piattaforma
-- ha cominciato a tenere **soldi veri e soldi simulati nello stesso momento**
-- (tennis in live, calcio in paper), e questa è esattamente la condizione in cui
-- quel genere di errore si manifesta. Il giorno in cui Mike passa in live:
--
--   * il calendario e il grafico dello storico sommerebbero le due cose, e nulla
--     lo direbbe;
--   * il «P&L totale» resterebbe inquinato PER SEMPRE dai mesi di paper che lo
--     precedono — non è un errore che si corregge dopo, è un dato che si perde;
--   * l'elenco delle operazioni di un giorno mostrerebbe righe finte accanto a
--     righe vere, indistinguibili a colpo d'occhio.
--
-- Un trader che legge +42,10 € deve sapere se sono 42 euro o 42 finti.
--
-- LA SOLUZIONE è la STESSA già applicata agli aggregati
-- (`mike_aggregati_per_modalita_2026-09-13.sql`) e la stessa che Safe Strategy
-- usa in `safe_strategy_paper_live_2026-09-13.sql`: si aggiunge `p_mode`.
--   * `NULL` (default) → la modalità CORRENTE del bot (`mike_control.mode`):
--                        lo storico mostra la storia di quello che stai facendo;
--   * 'paper' / 'live' → esplicita, per chi vuole confrontare.
-- In uscita si dichiara quale modalità è stata usata, così la pagina non deve
-- indovinarlo e non può mostrarlo sbagliato.
--
-- Tre firme con lo stesso alfabeto in tutta la piattaforma: chi legge una pagina
-- non deve chiedersi se quel bot filtra o no.
--
-- Idempotente: CREATE OR REPLACE. Nessuna modifica ai dati, nessuna migrazione
-- di righe: cambiano solo le funzioni di lettura.
--
-- VERIFICA dopo l'applicazione:
--   SELECT public.get_mike_daily();                    -- modalità corrente
--   SELECT public.get_mike_daily(NULL, NULL, 'live');  -- solo soldi veri
--   SELECT public.get_mike_daily(NULL, NULL, 'paper'); -- solo simulato
--   SELECT public.get_mike_day_trades(current_date, 'paper');
-- ============================================================================

-- 0. via le versioni senza il parametro -------------------------------------
-- Obbligatorio: lasciandole, una chiamata senza `p_mode` diventerebbe ambigua
-- fra la vecchia firma e la nuova con DEFAULT, e Postgres risponderebbe
-- «function ... is not unique» (42725) — lo stesso codice nudo che la pagina
-- dello storico ha già mostrato una volta, ed è il motivo per cui esiste
-- `mike_history_v2.sql`.
DROP FUNCTION IF EXISTS public.get_mike_daily(date, date);
DROP FUNCTION IF EXISTS public.get_mike_day_trades(date);


-- 1. il calendario / grafico ------------------------------------------------
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

    -- modalità: esplicita, oppure quella CORRENTE del bot. Mai "tutte":
    -- sommare paper e live in silenzio è il difetto che questa migrazione chiude.
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
        'placed');

    -- Mike non ha un obiettivo giornaliero: si dichiara esplicitamente, così la
    -- UI non tratta un obiettivo di ripiego come uno storico (L-08).
    FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP
        v_out := v_out || jsonb_build_array(
            v_row - 'goal' || jsonb_build_object('goal', NULL, 'mode', v_mode));
    END LOOP;
    RETURN v_out;
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_daily(date, date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_daily(date, date, text) TO authenticated, service_role;


-- 2. le operazioni di un giorno ---------------------------------------------
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
    -- ALIAS `o`, non `t`. Le due funzioni condivise usano alias DIVERSI:
    --   trading_daily_history -> `t`      trading_day_trades -> `o` (aperture)
    -- Scrivere `t` qui faceva fallire OGNI chiamata con
    --   ERROR 42P01: missing FROM-clause entry for table "t"
    -- cioe' l'elenco delle operazioni del giorno era ROTTO, non impreciso.
    -- Corretto il 14/09 dopo averlo PROVATO: un filtro passato come testo e' un
    -- contratto che il compilatore non controlla.
    RETURN public.trading_day_trades('mike_trades', format('o.mode = %L', v_mode),
                                     p_day, 'placed');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_day_trades(date, text) TO authenticated, service_role;


-- ============================================================================
-- DOPO L'APPLICAZIONE, la prova che serve davvero: i due numeri devono essere
-- DIVERSI (o uno dei due vuoto), mai uguali per caso.
--
--   SELECT jsonb_array_length(public.get_mike_daily(NULL, NULL, 'paper')) AS giorni_paper,
--          jsonb_array_length(public.get_mike_daily(NULL, NULL, 'live'))  AS giorni_live;
--
-- Oggi (14/09) Mike non ha mai operato in live: `giorni_live` deve essere 0.
-- Se non lo è, qualcosa ha scritto righe `live` e va guardato PRIMA di aprire
-- il rubinetto.
-- ============================================================================
