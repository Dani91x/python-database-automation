-- ============================================================================
-- STORICO PER SPORT (17/09/2026) — due cose che mancavano alle dashboard
-- `/storico/calcio` e `/storico/tennis`.
--
-- Ordine dell'utente (17/09): «in "posizioni chiuse" voglio vedere SOLO le
-- posizioni della giornata; per i giorni precedenti uno STORICO dedicato al
-- tennis e uno al calcio, con la chiara distinzione dei profitti o loss per
-- bot». Paper e live restano due monete diverse e non si sommano mai.
--
-- ----------------------------------------------------------------------------
-- 1. OMEGA — lo storico NON sa separare i soldi veri dai simulati.
-- ----------------------------------------------------------------------------
-- VERIFICATO SUL DATABASE REALE il 17/09, non dedotto:
--
--   SELECT public.get_omega_daily('2026-08-01','2026-09-17','live');
--   → PGRST202: "Could not find the function public.get_omega_daily(
--     p_from, p_mode, p_to) in the schema cache"
--
-- `get_omega_daily` e `get_omega_day_trades` passano NULL come filtro a
-- `trading_daily_history` / `trading_day_trades`: nessuna delle due guarda
-- `omega_trades.mode`. Oggi e' innocuo solo per un motivo — sul DB reale
-- omega_trades ha 109 righe `paper` e ZERO `live` — ma e' esattamente lo stesso
-- difetto che Mike aveva il 14/09 e che `mike_storico_per_modalita_2026-09-14`
-- ha chiuso: il giorno in cui Omega apre il rubinetto, il «P&L totale» resta
-- inquinato PER SEMPRE dai mesi di paper che lo precedono. Non e' un errore che
-- si corregge dopo: e' un dato che si perde.
--
-- La cura e' la STESSA di Mike e di Safe, stesso alfabeto in tutta la
-- piattaforma:
--   * `p_mode` NULL (default) → la modalita' CORRENTE del bot (`omega_control.mode`)
--   * 'paper' / 'live'        → esplicita, per confrontare
--   * mai «tutte»: sommare in silenzio e' il difetto, non la comodita'.
-- In uscita si dichiara `mode`, cosi' la pagina non deve indovinarlo.
--
-- FINCHE' QUESTA MIGRAZIONE NON E' APPLICATA la dashboard NON mostra Omega
-- sotto «prova» o «soldi veri»: lo mette in un blocco a parte, «modalita' non
-- separabile», escluso dai totali. Fail-closed: ai soldi veri si arriva solo
-- dichiarandolo (regola 14/09), mai per un campo che la RPC non sa filtrare.
--
-- ----------------------------------------------------------------------------
-- 2. ROI SU STAKE — l'importo piazzato non esiste negli aggregati giornalieri.
-- ----------------------------------------------------------------------------
-- `trading_daily_history` espone `max_liability` (il MASSIMO di giornata), non
-- la SOMMA degli importi piazzati: con quella non si calcola nessun ROI.
-- Invece di riscrivere il motore condiviso dei tre bot — 200 righe di plpgsql
-- che reggono Omega, Safe e Mike insieme, e un refuso li rompe tutti — si
-- aggiunge UNA funzione a parte, additiva: se non c'e', l'unica cosa che manca
-- e' la colonna ROI, e la dashboard lo dichiara.
--
-- `stake_placed` = somma delle `size` delle APERTURE piazzate nel giorno
-- (`closes_trade_id IS NULL`), giornata operativa = PIAZZAMENTO, Europe/Rome:
-- le stesse regole di `placed` dentro `trading_daily_history`, predicato
-- `is_placed` compreso. E' l'IMPORTO messo a mercato, non la liability: su un
-- lay i due numeri sono diversi e la dashboard lo scrive.
--
-- ----------------------------------------------------------------------------
-- IDEMPOTENTE. Nessuna modifica ai dati: cambiano solo funzioni di lettura.
-- ORDINE: dopo daily_history.sql → omega_daily_v2.sql → omega_models_v4.sql →
-- mike_history_v2.sql → mike_storico_per_modalita*. Se si riapplica
-- `omega_daily_v2.sql` o `omega_models_v4.sql`, RIAPPLICARE anche questa
-- (altrimenti torna la firma a 2 argomenti senza `p_mode`).
--
-- VERIFICA dopo l'applicazione:
--   SELECT jsonb_array_length(public.get_omega_daily(NULL, NULL, 'paper')) AS giorni_paper,
--          jsonb_array_length(public.get_omega_daily(NULL, NULL, 'live'))  AS giorni_live;
--   -- 17/09: giorni_live DEVE essere 0 (omega_trades non ha righe live).
--   SELECT public.get_omega_day_trades(current_date, 'paper');
--   SELECT public.get_storico_stake('safe', current_date - 30, current_date, 'tennis', 'live');
-- ============================================================================
--
-- CORREZIONE 17/09 (revisione statica, `APPLY_ORDER_2026-09-16.md` §7): la
-- prima stesura di questo file aveva riscritto il merge dell'obiettivo
-- storicizzato di `get_omega_daily` ripartendo da `omega_daily_v2.sql:497-509`
-- (il vecchio LOOP plpgsql `FOR v_row IN ... END LOOP`), non dall'ULTIMA
-- definizione viva sul DB prima di oggi, che e' `omega_models_v4.sql:109-151`
-- (set-based: un solo `jsonb_agg(...) LEFT JOIN omega_daily_goal`, introdotto
-- apposta da v4 per «niente loop plpgsql riga per riga»). Corretto qui: base
-- = `omega_models_v4.sql`, con `|| jsonb_build_object('mode', v_mode)` in
-- ENTRAMBI i rami del `CASE` (non solo nell'`ELSE`) e il filtro `p_mode`
-- invariato. Nessun cambio di comportamento visibile, solo la prestazione che
-- v4 aveva gia' ottenuto e che qui era sparita in silenzio.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 0. via le firme SENZA il parametro.
--    Obbligatorio: lasciandole, una chiamata senza `p_mode` diventerebbe
--    ambigua fra la vecchia firma e la nuova con DEFAULT, e Postgres
--    risponderebbe «function ... is not unique» (42725) — lo stesso codice
--    nudo che la pagina Storico ha gia' mostrato una volta ed e' il motivo per
--    cui esiste `mike_history_v2.sql`.
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.get_omega_daily(date, date);
DROP FUNCTION IF EXISTS public.get_omega_day_trades(date);


-- ----------------------------------------------------------------------------
-- 1. OMEGA — calendario / grafico per giornata, per UNA modalita'.
--    Corpo identico a `omega_daily_v2.sql` (obiettivo storicizzato compreso):
--    cambia solo il filtro e il campo `mode` dichiarato in uscita.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_daily(
    p_from date DEFAULT NULL,
    p_to   date DEFAULT NULL,
    p_mode text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mode  text := nullif(btrim(lower(coalesce(p_mode, ''))), '');
    v_goal  numeric;
    v_rows  jsonb;
    v_out   jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- modalita': esplicita, oppure quella CORRENTE del bot. Mai «tutte».
    IF v_mode IS NULL THEN
        SELECT lower(btrim(c.mode)) INTO v_mode FROM public.omega_control c WHERE c.id = 1;
        v_mode := coalesce(v_mode, 'paper');
    END IF;
    IF v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live)', p_mode;
    END IF;

    SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;

    -- ALIAS `t`: dentro `trading_daily_history` la tabella delle aperture si
    -- chiama `t` (in `trading_day_trades` si chiama `o`). Scambiarli fa fallire
    -- la chiamata con 42P01 — successo davvero su Mike il 14/09.
    v_rows := public.trading_daily_history(
        'omega_trades',
        $e$coalesce(t.phase, 'none')$e$,
        $e$'calcio'$e$,
        format('t.mode = %L', v_mode),
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        v_goal,
        'placed');

    -- obiettivo STORICO del giorno (snapshot) quando c'e', altrimenti quello
    -- corrente dichiarato come NON storicizzato (H-10). Set-based
    -- (omega_models_v4.sql punto 4: «niente loop plpgsql riga per riga»), la
    -- modalita' viaggia SU OGNI RIGA: la pagina non deve dedurla.
    SELECT coalesce(jsonb_agg(
               CASE WHEN g.goal IS NOT NULL THEN
                   r.elem || jsonb_build_object(
                       'goal', g.goal,
                       'goal_pct', CASE WHEN g.goal > 0
                                        THEN round((r.elem->>'pnl_realized')::numeric / g.goal * 100, 1) END,
                       'goal_snapshot', true,
                       'mode', v_mode)
               ELSE r.elem || jsonb_build_object('goal_snapshot', false, 'mode', v_mode)
               END ORDER BY r.ord), '[]'::jsonb)
      INTO v_out
      FROM jsonb_array_elements(v_rows) WITH ORDINALITY AS r(elem, ord)
      LEFT JOIN public.omega_daily_goal g ON g.day = (r.elem->>'day')::date;
    RETURN v_out;
END;
$$;

REVOKE ALL    ON FUNCTION public.get_omega_daily(date, date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_daily(date, date, text) TO authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 2. OMEGA — le operazioni di UN giorno, per UNA modalita'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_day_trades(
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
        SELECT lower(btrim(c.mode)) INTO v_mode FROM public.omega_control c WHERE c.id = 1;
        v_mode := coalesce(v_mode, 'paper');
    END IF;
    IF v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live)', p_mode;
    END IF;
    -- ALIAS `o`, non `t`: `trading_day_trades` chiama `o` la tabella delle
    -- APERTURE. E' l'errore che ha rotto `get_mike_day_trades` il 14/09.
    RETURN public.trading_day_trades('omega_trades', format('o.mode = %L', v_mode),
                                     p_day, 'placed');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_omega_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_day_trades(date, text) TO authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 3. IMPORTO PIAZZATO PER GIORNATA — la base del ROI, per un bot e una
--    modalita'. Additiva: nessuna funzione esistente viene toccata.
--
--    Ritorna [{day, stake_placed, trades_placed}] ordinato per giorno.
--    `stake_placed` = somma delle `size` delle APERTURE piazzate nel giorno.
--    Sui lay NON e' la liability: sono due grandezze diverse e la dashboard lo
--    scrive accanto al numero.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_storico_stake(
    p_bot   text,
    p_from  date DEFAULT NULL,
    p_to    date DEFAULT NULL,
    p_sport text DEFAULT NULL,
    p_mode  text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_bot   text := nullif(btrim(lower(coalesce(p_bot, ''))), '');
    v_mode  text := nullif(btrim(lower(coalesce(p_mode, ''))), '');
    v_sport text := nullif(btrim(lower(coalesce(p_sport, ''))), '');
    v_table text;
    v_from  date;
    v_to    date;
    v_where text := 'true';
    v_out   jsonb;
    v_clamped boolean := false;
    v_row   jsonb;
    v_acc   jsonb := '[]'::jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- whitelist delle tabelle: la stessa di `trading_daily_history`. Il nome
    -- della tabella non arriva mai dal client.
    v_table := CASE v_bot
        WHEN 'omega' THEN 'omega_trades'
        WHEN 'safe'  THEN 'safe_strategy_trades'
        WHEN 'mike'  THEN 'mike_trades'
        ELSE NULL
    END;
    IF v_table IS NULL THEN
        RAISE EXCEPTION 'bot non ammesso: % (ammessi: omega, safe, mike)', p_bot;
    END IF;

    IF v_mode IS NOT NULL AND v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore)', p_mode;
    END IF;
    IF v_sport IS NOT NULL AND v_sport NOT IN ('calcio', 'tennis') THEN
        RAISE EXCEPTION 'sport non valido: %', p_sport;
    END IF;
    -- La colonna `sport` esiste su safe_strategy_trades e mike_trades, NON su
    -- omega_trades (verificato sul DB reale il 17/09: Omega e' calcio per
    -- costruzione). Chiedere 'tennis' a Omega non e' un errore da nascondere
    -- con un filtro che non esiste: sono zero righe, e si dichiarano.
    IF v_sport IS NOT NULL AND v_bot = 'omega' THEN
        IF v_sport <> 'calcio' THEN
            RETURN '[]'::jsonb;
        END IF;
        v_sport := NULL;
    END IF;

    v_to   := coalesce(p_to, v_today);
    v_from := coalesce(p_from, v_to - 90);
    IF v_from > v_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', v_from, v_to;
    END IF;
    -- stessa difesa di `trading_daily_history` (M-17): finestra oltre 400
    -- giorni = si restringe, non si solleva. Si dichiara in uscita con
    -- `window_clamped`, la stessa chiave di `trading_daily_history`
    -- (mike_history_v2.sql): prima era un clamp silenzioso.
    IF (v_to - v_from) > 400 THEN
        v_from := v_to - 400;
        v_clamped := true;
    END IF;

    IF v_mode IS NOT NULL THEN
        v_where := v_where || format(' AND t.mode = %L', v_mode);
    END IF;
    IF v_sport IS NOT NULL THEN
        v_where := v_where || format(' AND t.sport = %L', v_sport);
    END IF;

    EXECUTE format($q$
        WITH aperture AS (
            SELECT (t.placed_at AT TIME ZONE 'Europe/Rome')::date AS op_day,
                   coalesce(t.size, 0)::numeric AS size,
                   t.status,
                   -- PIAZZATA: identico predicato di `trading_daily_history`
                   (t.bet_id IS NOT NULL
                    OR (t.meta->>'flumine_client_ref') IS NOT NULL
                    OR t.meta->>'reason' = 'place_exception_reconciling') AS is_placed
              FROM public.%I t
             WHERE t.closes_trade_id IS NULL
               AND t.placed_at IS NOT NULL
               AND (%s)
               AND (t.placed_at AT TIME ZONE 'Europe/Rome')::date BETWEEN $1 AND $2
        ), piazzate AS (
            SELECT op_day, size FROM aperture
             WHERE status <> 'error'
               AND (status <> 'pending' OR is_placed)
        ), per_giorno AS (
            SELECT op_day, round(sum(size), 2) AS stake_placed, count(*) AS trades_placed
              FROM piazzate
             GROUP BY op_day
        )
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'day',           to_char(op_day, 'YYYY-MM-DD'),
                   'stake_placed',  stake_placed,
                   'trades_placed', trades_placed
               ) ORDER BY op_day), '[]'::jsonb)
          FROM per_giorno
    $q$, v_table, v_where)
    INTO v_out
    USING v_from, v_to;

    v_out := coalesce(v_out, '[]'::jsonb);
    IF v_clamped THEN
        -- la nota viaggia su ogni riga (stesso pattern di trading_daily_history):
        -- nessun campo nuovo obbligatorio per chi legge quando non e' clampata.
        FOR v_row IN SELECT * FROM jsonb_array_elements(v_out) LOOP
            v_acc := v_acc || jsonb_build_array(v_row || jsonb_build_object(
                'window_clamped', true,
                'window_from', to_char(v_from, 'YYYY-MM-DD'),
                'window_note', 'finestra ridotta agli ultimi 400 giorni'));
        END LOOP;
        RETURN v_acc;
    END IF;
    RETURN v_out;
END;
$$;

REVOKE ALL    ON FUNCTION public.get_storico_stake(text, date, date, text, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_storico_stake(text, date, date, text, text) TO authenticated, service_role;


-- ============================================================================
-- DOPO L'APPLICAZIONE, la prova che serve davvero — i due numeri devono essere
-- DIVERSI (o uno dei due vuoto), mai uguali per caso:
--
--   SELECT jsonb_array_length(public.get_omega_daily(NULL, NULL, 'paper')) AS paper,
--          jsonb_array_length(public.get_omega_daily(NULL, NULL, 'live'))  AS live;
--
-- 17/09: `live` deve essere 0 — omega_trades ha 109 righe paper e 0 live. Se non
-- lo e', qualcosa ha scritto righe `live` e va guardato PRIMA di aprire il
-- rubinetto.
--
--   SELECT public.get_storico_stake('safe', current_date - 30, current_date, 'tennis', 'live');
--   SELECT public.get_storico_stake('safe', current_date - 30, current_date, 'tennis', 'paper');
-- Le due somme non devono MAI coincidere con quella senza `p_mode`: se lo fanno,
-- una delle due modalita' e' vuota (va bene) oppure il filtro non sta filtrando.
-- ============================================================================
