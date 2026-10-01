-- ============================================================================
-- giornata_di_riferimento_giorno_partita_2026-10-01.sql
-- LA GIORNATA DI RIFERIMENTO E' IL GIORNO DELLA PARTITA (tutti i bot calcio,
-- Safe tennis compreso, paper e live)
-- ============================================================================
-- ORDINE DELL'UTENTE (01/10/2026): «le chiusure devono essere assegnate alla
-- giornata di riferimento; oggi Posizioni chiuse e gli storici calcio/tennis
-- mostrano sotto OGGI le operazioni fatte IERI; tutto deve essere coerente per
-- il trader».
-- DECISIONE DEL COORDINATORE: giornata di riferimento = GIORNO DELLA PARTITA
-- (orario d'inizio dell'evento, fuso Europe/Rome). Correzione del coordinatore
-- (01/10, stessa giornata): ORDINE DI RICERCA, per Omega, Safe e Mike:
--   1. inizio partita dalla catena di fonti            -> giorno_da 'partita'
--   2. altrimenti STIMA dal minuto di gioco all'ingresso, solo se il minuto
--      e' > 0 (R-02 review 01/10: minuto 0 = ingresso pre-partita, non stima):
--      placed_at - minute_at_entry minuti               -> giorno_da 'partita'
--   3. altrimenti il giorno di PIAZZAMENTO               -> giorno_da 'piazzamento'
-- Il giorno di REGOLAMENTO non decide MAI (le righe orfane regolate giorni dopo
-- dal servizio finivano nel giorno sbagliato).
--
-- PRIMA (tre criteri diversi):
--   * get_omega_daily / get_omega_day_trades ...... 'placed' (piazzamento)
--   * get_safe_daily  / get_safe_day_trades ....... 'placed'
--   * get_mike_daily  / get_mike_day_trades ....... 'settled' (29/09)
--   * get_posizioni_chiuse_giornata ............... gamba REGOLATA nel giorno
--   * get_tennis_bot_daily (4 bot tennis) ......... GIA' giorno partita (30/09)
-- DOPO: tutti 'event' = giorno della partita; il tennis resta com'e'.
--
-- ----------------------------------------------------------------------------
-- DA DOVE SI RICAVA L'INIZIO PARTITA (verificato sul DB reale in SOLA LETTURA
-- il 01/10/2026 via REST; referto AUDIT_2026-10-01/GIORNATA_DI_RIFERIMENTO_SQL.md)
-- ----------------------------------------------------------------------------
--   Fonti (tutte timestamptz, chiave event_id text):
--     mike_events.ko_at (PK event_id)        omega_trades.kickoff (colonna propria)
--     omega_missions.kickoff (PK event_id)   live_follow.open_date (PK event_id)
--     omega_events.open_date (PK event_id)   tennis_live_follow.open_date (PK event_id)
--     tennis_markets.open_date (PK event_id)
--   Catena per tabella (`inizio_partita_sql`):
--     omega_trades         -> t.kickoff, poi catena CALCIO di inizio_partita_evento
--     mike_trades          -> catena CALCIO (prima mike_events.ko_at)
--     safe_strategy_trades -> catena dello SPORT della riga (t.sport)
--   catena CALCIO : mike_events.ko_at, min(omega_trades.kickoff),
--                   omega_missions.kickoff, live_follow.open_date, omega_events.open_date
--   catena TENNIS : tennis_live_follow.open_date, tennis_markets.open_date
--   Poi: minute_at_entry (integer, su tutte e tre le tabelle) -> stima, solo
--   con minuto > 0 (R-02 review 01/10: NULLIF(minute_at_entry, 0); col minuto 0
--   e senza catena la riga va a 'piazzamento', dichiarato). Sonda REST in sola
--   lettura del 01/10: righe con minute_at_entry = 0 -> Safe 0, Omega 0, Mike 43
--   (16 regolate + 27 'error'), tutte le 43 con l'inizio in catena: la tabella
--   qui sotto NON cambia.
--   Righe REGOLATE (won/lost/void) al 01/10, per fonte del giorno:
--                       catena  minuto  piazzamento   totale
--     mike_trades         425       0            0      425
--     omega_trades        122       1            2      125
--     safe calcio          85     101            3      189   (paper)
--     safe tennis          20       0          127      147   (106 paper, 21 live a piazzamento)
--     4 bot tennis         17       -            0       17   (tennis_live_follow)
--   Fonti discordanti sullo stesso evento: 0 (Mike, Omega, Safe).
--   Safe NON scrive l'inizio partita (nessuna colonna, nessuna chiave di meta);
--   Safe tennis non scrive nemmeno minute_at_entry: va a piazzamento.
--
-- ----------------------------------------------------------------------------
-- COSA SIGNIFICA 'event' NEL MOTORE COMUNE (trading_daily_history)
-- ----------------------------------------------------------------------------
--   la posizione INTERA (piazzamento, liability, P&L, V/P, chiusure,
--   commissioni) va al giorno di riferimento della sua apertura: partita
--   (catena o minuto) oppure, a ripiego, giorno di piazzamento dell'apertura.
--   La finestra dei candidati si allarga di 7 giorni per lato (una partita del
--   30/09 regolata il 01/10, o un pre-partita piazzato il 29/09, rientrano nel
--   30/09); il filtro finale resta per GIORNO.
--   'placed' e 'settled' restano IDENTICI a prima (l'inizio non viene nemmeno
--   calcolato: espressione NULL).
--   CHIAVI NUOVE PER RIGA (nessuna chiave esistente tolta):
--     trading_day_trades (solo in 'event') e get_posizioni_chiuse_giornata
--     (omega/safe/mike/tennis):
--       'giorno_partita' YYYY-MM-DD (Europe/Rome) dell'inizio, anche stimato
--                        dal minuto; NULL quando giorno_da = 'piazzamento'
--       'giorno_da'      'partita' | 'piazzamento' (= ripiego)
--       'in_day'         boolean, la riga appartiene al giorno chiesto (il
--                        giorno di riferimento cade nel giorno). Nelle righe
--                        restituite e' sempre true: e' la dichiarazione
--                        esplicita per il frontend.
--     righe tennis di get_posizioni_chiuse_giornata: anche 'event_name'
--     (tennis_live_follow player1/2_name, poi tennis_markets player1/2->>'name').
--   get_storico_stake (base del ROI): stessa giornata (partita, ripiego piazzamento).
--   P&L LIVE: verificato il 01/10 che pnl = pnl_betfair su TUTTE le righe live
--   regolate che hanno pnl_betfair (Mike 10/10; Omega 0 righe live; Safe 23
--   regolate live, nessuna con pnl_betfair): il motore resta su `pnl`.
--
-- FRONTEND (FUORI DA QUESTA MIGRAZIONE, da adeguare insieme, vedi referto):
--   * lib/dailyHistory.ts `attributionOf` / `summarizeDayTrades` filtrano il
--     dettaglio con placed_in_day/settled_in_day: in modo 'event' devono usare
--     `in_day`, altrimenti il dettaglio del 30/09 scarta le partite del
--     30/09 regolate il 01/10.
--   * lib/posizioniChiuse.ts rifiltra le righe per giorno di REGOLAMENTO: per le
--     righe con giorno_da='partita' la giornata la decide gia' il server (in_day).
--   * lib/chiuseGiornata.ts passa nomePartita=null a rigaDaOrdineTennis: per
--     vedere il nome deve passare la nuova `event_name` della riga.
--
-- IDEMPOTENTE (CREATE OR REPLACE a firme invariate). Nessuna modifica ai dati.
-- ORDINE: dopo storico_esito_a_zero_2026-09-26.sql, mike_history_v2.sql,
-- storico_sport_2026-09-17.sql, safe_strategy_paper_live_2026-09-13.sql,
-- mike_storico_giorno_regolamento_2026-09-29.sql, posizioni_chiuse_giornata_2026-09-24.sql.
--
-- ----------------------------------------------------------------------------
-- VERIFICA dopo l'applicazione (SQL editor, come owner/postgres; devono
-- RISPONDERE, non sollevare):
--   SELECT jsonb_array_length(public.get_omega_daily(NULL, NULL, 'paper'));
--   SELECT jsonb_array_length(public.get_safe_daily(NULL, NULL, NULL, 'paper'));
--   SELECT jsonb_array_length(public.get_mike_daily(NULL, NULL, 'live'));
--   SELECT jsonb_array_length(public.get_omega_day_trades(current_date, 'paper'));
--   SELECT jsonb_array_length(public.get_safe_day_trades(current_date, NULL, 'paper'));
--   SELECT jsonb_array_length(public.get_mike_day_trades(current_date, 'live'));
--   SELECT jsonb_array_length(r->'mike') FROM (SELECT public.get_posizioni_chiuse_giornata(current_date, 'live') r) x;
--   -- il criterio 'event' e' accettato, uno sconosciuto no:
--   SELECT public.trading_day_trades('mike_trades', NULL, current_date, 'event');      -- risponde
--   SELECT public.trading_day_trades('mike_trades', NULL, current_date, 'boh');        -- 'attribuzione non valida'
--
-- CONFRONTO ATTESO (test di accettazione, dati reali di ieri):
--   Mike LIVE, eventi 36132117 Follo v Sarpsborg, 36130526 FC Vsetin v
--   Bohemians 1905, 36134898 FC Farul Constanta (W) v Sparta Prague (W):
--   inizio 30/09 (ko_at 14:00Z, 13:30Z, 14:00Z), regolati il 01/10 ~07:00Z.
--   Devono stare sotto il 30/09, NON sotto il 01/10:
--     SELECT r->>'day', r->>'pnl_realized', r->>'settled', r->>'won', r->>'lost'
--       FROM jsonb_array_elements(public.get_mike_daily('2026-09-29','2026-10-01','live')) r;
--     -- atteso (modello Python sui dati del 01/10, solo Mike live in quei giorni):
--     --   PRIMA ('settled'): 30/09 pnl 0,00 piazzati 5 regolati 0;
--     --                      01/10 pnl +1,88 piazzati 0 regolati 5 (2V 3P)
--     --   DOPO  ('event')  : 30/09 pnl +1,88 piazzati 5 regolati 5 (2V 3P);
--     --                      01/10 nessuna riga
--     SELECT o->>'id', o->>'status', o->>'in_day', o->>'giorno_da', o->>'giorno_partita'
--       FROM jsonb_array_elements(public.get_mike_day_trades('2026-09-30','live')) o
--      WHERE o->>'event_id' IN ('36132117','36130526','36134898');
--     -- atteso: 6 aperture (5083 error, 5085, 5087, 5090, 5091, 5094),
--     -- tutte in_day=true, giorno_da='partita', giorno_partita='2026-09-30'
--     SELECT count(*) FROM jsonb_array_elements(public.get_mike_day_trades('2026-10-01','live')) o
--      WHERE o->>'event_id' IN ('36132117','36130526','36134898');
--     -- atteso: 0
--     SELECT count(*) FROM jsonb_array_elements(
--              public.get_posizioni_chiuse_giornata('2026-09-30','live')->'mike') r
--      WHERE r->>'event_id' IN ('36132117','36130526','36134898');
--     -- atteso: 14 (tutte le gambe dei cicli 5083, 5085, 5087, 5090, 5091, 5094;
--     -- prima: 0 sotto il 30/09 e 14 sotto il 01/10)
--     SELECT count(*) FROM jsonb_array_elements(
--              public.get_posizioni_chiuse_giornata('2026-10-01','live')->'mike') r
--      WHERE r->>'event_id' IN ('36132117','36130526','36134898');
--     -- atteso: 0
--     SELECT public.get_storico_stake('mike', '2026-09-29', '2026-10-01', NULL, 'live');
--     -- atteso: invariato [{"day":"2026-09-30","stake_placed":26.37,"trades_placed":5}]
--   Le 4 aperture Mike LIVE void con settled_at NULL (4780, 4812, 4819, 4821, partite
--   del 15/09) contano come VOID, non come vinte/perse:
--     SELECT r->>'trades_placed', r->>'settled', r->>'won', r->>'lost', r->>'void', r->>'pnl_realized'
--       FROM jsonb_array_elements(public.get_mike_daily('2026-09-15','2026-09-15','live')) r;
--     -- prima: 4 piazzate, 0 regolate, 0 void; atteso: 4, 4, 0, 0, 4, 0
--     -- (il contatore `settled` del motore include i void, come per ogni void)
--   Su 01/09-01/10 il TOTALE del P&L per bot e modalita' NON cambia, cambia solo il giorno:
--     SELECT sum((r->>'pnl_realized')::numeric)
--       FROM jsonb_array_elements(public.get_mike_daily('2026-09-01', '2026-10-01', 'paper')) r;
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1) AIUTANTI. L'inizio partita di un evento (catena di fonti, nessuna stima)
--    e l'espressione SQL che lo ricava per una tabella dei trade e un alias.
--    Solo per le funzioni SECURITY DEFINER qui sotto: nessun client li chiama.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.inizio_partita_evento(
    p_event_id text,
    p_sport    text
) RETURNS timestamptz
LANGUAGE sql STABLE SET search_path = public, pg_temp
AS $$
    SELECT CASE
        WHEN p_event_id IS NULL THEN NULL
        WHEN lower(coalesce(p_sport, '')) = 'tennis' THEN coalesce(
            (SELECT f.open_date FROM public.tennis_live_follow f WHERE f.event_id = p_event_id),
            (SELECT m.open_date FROM public.tennis_markets m     WHERE m.event_id = p_event_id))
        ELSE coalesce(
            (SELECT e.ko_at       FROM public.mike_events e    WHERE e.event_id = p_event_id),
            (SELECT min(o.kickoff) FROM public.omega_trades o  WHERE o.event_id = p_event_id),
            (SELECT m.kickoff     FROM public.omega_missions m WHERE m.event_id = p_event_id),
            (SELECT f.open_date   FROM public.live_follow f    WHERE f.event_id = p_event_id),
            (SELECT e.open_date   FROM public.omega_events e   WHERE e.event_id = p_event_id))
    END
$$;
REVOKE ALL ON FUNCTION public.inizio_partita_evento(text, text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.inizio_partita_evento(text, text) TO service_role;

-- Testo SQL dell'inizio partita per (tabella, alias). Tabella e alias in lista
-- bianca: il risultato finisce dentro un EXECUTE format(...).
CREATE OR REPLACE FUNCTION public.inizio_partita_sql(
    p_table text,
    p_alias text
) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_alias NOT IN ('t', 'o') THEN
        RAISE EXCEPTION 'alias non ammesso: %', p_alias;
    END IF;
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    -- 1) catena delle fonti; 2) STIMA dal minuto di gioco all'ingresso
    --    (placed_at - minute_at_entry minuti: i bot in gioco lo scrivono sempre);
    -- NULL = nessuno dei due -> il chiamante ripiega sul PIAZZAMENTO.
    -- R-02 review 01/10: minute_at_entry = 0 (ingresso pre-partita) NON e' una
    -- stima dell'inizio (darebbe placed_at, il giorno di PIAZZAMENTO etichettato
    -- 'partita'): NULLIF lo tratta come «non noto», e senza catena la riga va a
    -- giorno_da = 'piazzamento', dichiarato. Dati del 01/10: nessun numero cambia
    -- (Safe e Omega 0 righe col minuto 0; Mike 43, tutte con l'inizio in catena).
    RETURN format('coalesce(%2$s, CASE WHEN NULLIF(%1$s.minute_at_entry, 0) IS NOT NULL '
                  'THEN %1$s.placed_at - NULLIF(%1$s.minute_at_entry, 0) * interval %3$L END)',
                  p_alias,
                  CASE p_table
                      WHEN 'omega_trades' THEN
                          format('coalesce(%1$s.kickoff, public.inizio_partita_evento(%1$s.event_id, %2$L))', p_alias, 'calcio')
                      WHEN 'mike_trades' THEN
                          format('public.inizio_partita_evento(%1$s.event_id, coalesce(%1$s.sport, %2$L))', p_alias, 'calcio')
                      WHEN 'safe_strategy_trades' THEN
                          format('public.inizio_partita_evento(%1$s.event_id, %1$s.sport)', p_alias)
                  END,
                  '1 minute');
END;
$$;
REVOKE ALL ON FUNCTION public.inizio_partita_sql(text, text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.inizio_partita_sql(text, text) TO service_role;


-- ----------------------------------------------------------------------------
-- 2) MOTORE COMUNE: trading_daily_history con il criterio 'event'.
--    Base = corpo VIVO di storico_esito_a_zero_2026-09-26.sql. Differenze
--    (tutte marcate «EVENT 01/10»): validazione, v_by_event ($7), finestra dei
--    candidati allargata solo in 'event', start_at (LATERAL) in originals e
--    closers, placed_day / op_settled_day / settled_day dei closers.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trading_daily_history(
    p_table         text,
    p_strategy_expr text,
    p_sport_expr    text,
    p_filter_expr   text,
    p_from          date,
    p_to            date,
    p_goal          numeric,
    p_day_by        text DEFAULT 'settled'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_from      timestamptz;
    v_to        timestamptz;
    v_out       jsonb;
    v_by_placed boolean;
    v_by_event  boolean;  -- EVENT 01/10
    v_start_t   text;     -- EVENT 01/10: inizio partita, alias t (aperture/chiusure)
    v_start_o   text;     -- EVENT 01/10: inizio partita, alias o (apertura della chiusura)
    v_from_d    date;
    v_clamped   boolean := false;
    v_row       jsonb;
    v_acc       jsonb := '[]'::jsonb;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed', 'event') THEN  -- EVENT 01/10
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'intervallo non valido: % → %', p_from, p_to;
    END IF;
    -- M-17: finestra troppo ampia = si RESTRINGE (ultimi 400 giorni) e lo si
    -- dichiara. Prima era un'eccezione: la pagina Storico restava vuota.
    v_from_d := p_from;
    IF (p_to - p_from) > 400 THEN
        v_from_d := p_to - 400;
        v_clamped := true;
    END IF;
    v_by_placed := (p_day_by = 'placed');
    v_by_event  := (p_day_by = 'event');  -- EVENT 01/10
    v_from := (v_from_d::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Rome');
    -- EVENT 01/10: in 'event' i CANDIDATI si cercano 7 giorni prima e dopo
    -- (pre-partita piazzato il giorno prima, regolamento il giorno dopo); la
    -- giornata la decide poi il filtro per GIORNO. Negli altri criteri l'inizio
    -- partita non si calcola nemmeno (NULL) e la finestra resta quella di prima.
    IF v_by_event THEN
        v_start_t := public.inizio_partita_sql(p_table, 't');
        v_start_o := public.inizio_partita_sql(p_table, 'o');
        v_from := v_from - interval '7 days';
        v_to   := v_to   + interval '7 days';
    ELSE
        v_start_t := 'NULL';
        v_start_o := 'NULL';
    END IF;

    EXECUTE format($q$
        WITH originals AS (
            SELECT t.id, t.status, t.pnl::numeric AS pnl, t.liability::numeric AS liability,
                   t.origin, t.placed_at, t.settled_at,
                   (%s)::text AS strategy, (%s)::text AS sport,
                   -- EVENT 01/10: in 'event' il PIAZZAMENTO conta nel giorno della partita
                   -- (ripiego: giorno di piazzamento)
                   CASE WHEN $7 AND st.start_at IS NOT NULL THEN (st.start_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.placed_at  AT TIME ZONE 'Europe/Rome')::date END AS placed_day,
                   (t.settled_at AT TIME ZONE 'Europe/Rome')::date AS settled_day,
                   CASE WHEN $6 THEN (t.placed_at AT TIME ZONE 'Europe/Rome')::date
                        -- EVENT 01/10: giorno della partita; ripiego = giorno di PIAZZAMENTO
                        WHEN $7 THEN (coalesce(st.start_at, t.placed_at) AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS op_settled_day,
                   -- PIAZZATA: bet_id reale, marker flumine, OPPURE riga
                   -- 'pending' in RICONCILIAZIONE (esito ignoto: l'ordine puo'
                   -- essere vivo su Betfair). Senza l'ultimo caso lo storico
                   -- contava meno trade piazzati dei KPI della stessa giornata,
                   -- che invece le contano aperte (review Safe 11/09).
                   (t.bet_id IS NOT NULL
                    OR (t.meta->>'flumine_client_ref') IS NOT NULL
                    OR t.meta->>'reason' = 'place_exception_reconciling') AS is_placed
              FROM public.%I t
              CROSS JOIN LATERAL (SELECT (%s)::timestamptz AS start_at) st  -- EVENT 01/10
             WHERE t.closes_trade_id IS NULL
               AND (%s)
               AND ((t.placed_at >= $1 AND t.placed_at < $2)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), closers AS (
            SELECT t.id, t.closes_trade_id, t.status, t.pnl::numeric AS pnl, t.market_id,
                   t.commission::numeric AS commission, t.meta, t.settled_at,
                   CASE WHEN $6 THEN (o.placed_at AT TIME ZONE 'Europe/Rome')::date
                        -- EVENT 01/10: la chiusura va nel giorno della partita della sua apertura
                        -- (ripiego: giorno di piazzamento dell'apertura)
                        WHEN $7 THEN (coalesce(st.start_at, o.placed_at) AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.settled_at AT TIME ZONE 'Europe/Rome')::date END AS settled_day
              FROM public.%I t
              JOIN public.%I o ON o.id = t.closes_trade_id
              CROSS JOIN LATERAL (SELECT (%s)::timestamptz AS start_at) st  -- EVENT 01/10
             WHERE t.closes_trade_id IS NOT NULL
               AND (%s)
               AND (t.closes_trade_id IN (SELECT id FROM originals)
                    OR (t.settled_at >= $1 AND t.settled_at < $2))
        ), placed AS (
            SELECT * FROM originals
             WHERE status <> 'error'
               AND (status <> 'pending' OR is_placed)
               AND placed_day BETWEEN $3 AND $4
        ), trade_raw AS (
            SELECT o.id, o.op_settled_day AS settled_day, o.status AS raw_status, o.strategy, o.sport, o.origin,
                   o.pnl + coalesce((SELECT sum(c.pnl) FROM closers c
                                      WHERE c.closes_trade_id = o.id
                                        AND c.status IN ('won','lost','void')), 0) AS total_pnl
              FROM originals o
             WHERE o.status IN ('won','lost','void')
               AND o.op_settled_day BETWEEN $3 AND $4
        ), trade_tot AS (
            -- esito della POSIZIONE (ciclo) per SEGNO del P&L totale: un ciclo
            -- greenato e' UNA vittoria, non 1 vinta + 1 persa (audit Mike H4)
            SELECT id, settled_day, strategy, sport, origin, total_pnl,
                   CASE WHEN total_pnl > 0 THEN 'won' WHEN total_pnl < 0 THEN 'lost'
                        -- FIX-A 26/09: a ZERO (scratch) non e' ne' V ne' P; void e ignoto restano com'erano
                        WHEN raw_status = 'void' OR total_pnl IS NULL THEN raw_status
                        ELSE 'scratch' END AS status
              FROM trade_raw
        ), settled_rows AS (
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM (SELECT o.op_settled_day AS settled_day, o.pnl, t.market_id, t.commission::numeric AS commission, t.meta
                      FROM originals o JOIN public.%I t ON t.id = o.id
                     WHERE o.status IN ('won','lost','void')) x
            UNION ALL
            SELECT settled_day AS op_day, pnl, market_id, commission, meta
              FROM closers WHERE status IN ('won','lost','void')
        ), days AS (
            SELECT placed_day AS op_day FROM placed
            UNION
            SELECT op_day FROM settled_rows WHERE op_day BETWEEN $3 AND $4
        ), comm_market AS (
            -- L-08: commissione REALE per (giorno, mercato) quando il servizio
            -- l'ha scritta (meta.commission_paid), stima dal netto positivo solo
            -- dove manca. Prima un solo mercato con il valore azzerava gli altri.
            SELECT op_day, market_id,
                   sum(nullif(meta->>'commission_paid','')::numeric) AS paid,
                   sum(pnl) AS net,
                   coalesce(avg(commission), 0.05) AS c
              FROM settled_rows
             WHERE op_day BETWEEN $3 AND $4
             GROUP BY op_day, market_id
        ), comm_day AS (
            SELECT op_day,
                   sum(CASE WHEN paid IS NOT NULL THEN paid
                            WHEN net > 0 AND c < 1 THEN net * c / (1 - c)
                            ELSE 0 END) AS commission_paid
              FROM comm_market GROUP BY op_day
        ), brk AS (
            SELECT op_day, dim, dim_key,
                   count(*) FILTER (WHERE kind = 'placed')            AS n,
                   coalesce(sum(total_pnl) FILTER (WHERE kind = 'settled'), 0) AS pnl,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'won')  AS won,
                   count(*) FILTER (WHERE kind = 'settled' AND status = 'lost') AS lost
              FROM (
                  SELECT placed_day AS op_day, 'strategy' AS dim, strategy AS dim_key, 'placed' AS kind, 0::numeric AS total_pnl, status FROM placed
                  UNION ALL SELECT placed_day, 'sport',  sport,  'placed', 0, status FROM placed
                  UNION ALL SELECT placed_day, 'origin', origin, 'placed', 0, status FROM placed
                  UNION ALL SELECT settled_day, 'strategy', strategy, 'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'sport',  sport,  'settled', total_pnl, status FROM trade_tot
                  UNION ALL SELECT settled_day, 'origin', origin, 'settled', total_pnl, status FROM trade_tot
              ) u
             GROUP BY op_day, dim, dim_key
        ), brk_json AS (
            SELECT op_day, dim,
                   jsonb_object_agg(coalesce(dim_key, 'none'),
                       jsonb_build_object('n', n, 'pnl', round(pnl, 2), 'won', won, 'lost', lost)) AS j
              FROM brk GROUP BY op_day, dim
        ), per_day AS (
            SELECT d.op_day,
                   (SELECT coalesce(round(sum(pnl), 2), 0) FROM settled_rows s WHERE s.op_day = d.op_day) AS pnl_realized,
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day) AS trades_placed,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day) AS settled,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'won')  AS won,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'lost') AS lost,
                   (SELECT count(*) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.status = 'void') AS n_void,
                   -- L-08: le chiusure ancora PENDING non hanno chiuso nulla
                   (SELECT count(*) FROM placed p WHERE p.placed_day = d.op_day
                       AND (p.status = 'hedged'
                            OR EXISTS (SELECT 1 FROM closers c WHERE c.closes_trade_id = p.id
                                         AND c.status NOT IN ('error','pending')))) AS hedged_closed,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS avg_win,
                   (SELECT round(avg(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS avg_loss,
                   (SELECT round(max(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS best_trade,
                   (SELECT round(min(total_pnl), 2) FROM trade_tot x WHERE x.settled_day = d.op_day) AS worst_trade,
                   (SELECT round(max(liability), 2) FROM placed p WHERE p.placed_day = d.op_day) AS max_liability,
                   (SELECT coalesce(round(sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl > 0) AS gross_profit,
                   (SELECT coalesce(round(-sum(total_pnl), 2), 0) FROM trade_tot x WHERE x.settled_day = d.op_day AND x.total_pnl < 0) AS gross_loss,
                   (SELECT round(commission_paid, 2) FROM comm_day cd WHERE cd.op_day = d.op_day) AS commission_paid,
                   (SELECT min(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS first_trade_at,
                   (SELECT max(placed_at) FROM placed p WHERE p.placed_day = d.op_day) AS last_trade_at,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'strategy') AS by_strategy,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'sport')    AS by_sport,
                   (SELECT j FROM brk_json b WHERE b.op_day = d.op_day AND b.dim = 'origin')   AS by_origin
              FROM days d
        )
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'day',             to_char(op_day, 'YYYY-MM-DD'),
                   'pnl_realized',    pnl_realized,
                   'trades_placed',   trades_placed,
                   'settled',         settled,
                   'won',             won,
                   'lost',            lost,
                   'void',            n_void,
                   'hedged_closed',   hedged_closed,
                   'win_rate',        CASE WHEN won + lost > 0 THEN round(won::numeric / (won + lost), 4) END,
                   'avg_win',         avg_win,
                   'avg_loss',        avg_loss,
                   'best_trade',      best_trade,
                   'worst_trade',     worst_trade,
                   'max_liability',   max_liability,
                   'gross_profit',    gross_profit,
                   'gross_loss',      gross_loss,
                   'profit_factor',   CASE WHEN gross_loss > 0 THEN round(gross_profit / gross_loss, 3) END,
                   'commission_paid', commission_paid,
                   'goal',            $5::numeric,
                   'goal_pct',        CASE WHEN $5::numeric > 0 THEN round(pnl_realized / $5::numeric * 100, 1) END,
                   'by_strategy',     coalesce(by_strategy, '{}'::jsonb),
                   'by_sport',        coalesce(by_sport, '{}'::jsonb),
                   'by_origin',       coalesce(by_origin, '{}'::jsonb),
                   'first_trade_at',  first_trade_at,
                   'last_trade_at',   last_trade_at
               ) ORDER BY op_day), '[]'::jsonb)
          FROM per_day
    $q$, p_strategy_expr, p_sport_expr, p_table, v_start_t, coalesce(p_filter_expr, 'true'),
         p_table, p_table, v_start_o, coalesce(p_filter_expr, 'true'), p_table)
    INTO v_out
    USING v_from, v_to, v_from_d, p_to, p_goal, v_by_placed, v_by_event;

    v_out := coalesce(v_out, '[]'::jsonb);
    IF v_clamped THEN
        -- la nota viaggia su ogni riga: nessun campo nuovo obbligatorio per chi legge
        FOR v_row IN SELECT * FROM jsonb_array_elements(v_out) LOOP
            v_acc := v_acc || jsonb_build_array(v_row || jsonb_build_object(
                'window_clamped', true,
                'window_from', to_char(v_from_d, 'YYYY-MM-DD'),
                'window_note', 'finestra ridotta agli ultimi 400 giorni'));
        END LOOP;
        RETURN v_acc;
    END IF;
    RETURN v_out;
END;
$$;
REVOKE ALL ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_daily_history(text,text,text,text,date,date,numeric,text) TO service_role;


-- ----------------------------------------------------------------------------
-- 3) MOTORE COMUNE: trading_day_trades con il criterio 'event'.
--    Base = corpo VIVO di mike_history_v2.sql (4 argomenti). In 'placed' e
--    'settled' la selezione e le chiavi sono IDENTICHE a prima. In 'event':
--      * inizio noto o stimato dal minuto -> le aperture la cui partita e' nel giorno;
--      * altrimenti -> le aperture PIAZZATE nel giorno;
--      * tre chiavi in piu' per riga: 'giorno_partita', 'giorno_da', 'in_day'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trading_day_trades(
    p_table       text,
    p_filter_expr text,
    p_day         date,
    p_day_by      text DEFAULT 'settled'
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_from  timestamptz;
    v_to    timestamptz;
    v_start text;  -- EVENT 01/10
    v_out   jsonb;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    IF p_day_by NOT IN ('settled', 'placed', 'event') THEN  -- EVENT 01/10
        RAISE EXCEPTION 'attribuzione non valida: %', p_day_by;
    END IF;
    IF p_day IS NULL THEN
        RAISE EXCEPTION 'giorno mancante';
    END IF;
    v_from := (p_day::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_day + 1)::timestamp AT TIME ZONE 'Europe/Rome');
    -- EVENT 01/10: l'inizio partita si calcola solo in 'event'
    v_start := CASE WHEN p_day_by = 'event' THEN public.inizio_partita_sql(p_table, 'o') ELSE 'NULL' END;

    EXECUTE format($q$
        SELECT coalesce(jsonb_agg(
                   to_jsonb(o.*)
                   || jsonb_build_object(
                          'placed_in_day',  (o.placed_at >= $1 AND o.placed_at < $2),
                          'settled_in_day', (o.settled_at >= $1 AND o.settled_at < $2),
                          'closes', coalesce((SELECT jsonb_agg(to_jsonb(c.*) ORDER BY c.placed_at)
                                                FROM public.%I c
                                               WHERE c.closes_trade_id = o.id), '[]'::jsonb),
                          'total_pnl', round(o.pnl::numeric + coalesce((SELECT sum(c.pnl::numeric)
                                                FROM public.%I c
                                               WHERE c.closes_trade_id = o.id
                                                 AND c.status IN ('won','lost','void')), 0), 2)
                      )
                   -- EVENT 01/10: a quale giornata appartiene la posizione e perche'
                   || CASE WHEN $3 = 'event' THEN jsonb_build_object(
                          'giorno_partita', to_char((st.start_at AT TIME ZONE 'Europe/Rome')::date, 'YYYY-MM-DD'),
                          'giorno_da', CASE WHEN st.start_at IS NOT NULL THEN 'partita' ELSE 'piazzamento' END,
                          'in_day', coalesce(coalesce(st.start_at, o.placed_at) >= $1
                                             AND coalesce(st.start_at, o.placed_at) < $2, false))
                      ELSE '{}'::jsonb END
                   ORDER BY o.placed_at), '[]'::jsonb)
          FROM public.%I o
          CROSS JOIN LATERAL (SELECT (%s)::timestamptz AS start_at) st  -- EVENT 01/10
         WHERE o.closes_trade_id IS NULL
           AND (%s)
           AND (($3 <> 'event'
                 AND ((o.placed_at >= $1 AND o.placed_at < $2)
                      OR ($3 = 'settled' AND o.settled_at >= $1 AND o.settled_at < $2)))
                -- EVENT 01/10: candidati a +/- 7 giorni, poi giorno della partita
                -- (ripiego: giorno di PIAZZAMENTO; il regolamento non decide mai)
                OR ($3 = 'event'
                    AND ((o.placed_at >= $1 - interval '7 days' AND o.placed_at < $2 + interval '7 days')
                         OR (o.settled_at >= $1 - interval '7 days' AND o.settled_at < $2 + interval '7 days'))
                    AND coalesce(st.start_at, o.placed_at) >= $1
                    AND coalesce(st.start_at, o.placed_at) < $2))
    $q$, p_table, p_table, p_table, v_start, coalesce(p_filter_expr, 'true'))
    INTO v_out
    USING v_from, v_to, p_day_by;

    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.trading_day_trades(text,text,date,text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trading_day_trades(text,text,date,text) TO service_role;


-- ----------------------------------------------------------------------------
-- 4) OMEGA. Corpi VIVI di storico_sport_2026-09-17.sql; cambia SOLO il
--    criterio: 'placed' -> 'event'.
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
        -- 01/10: giorno della PARTITA (ripiego: piazzamento)
        'event');

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
    -- 01/10: giorno della PARTITA (ripiego: piazzamento)
    RETURN public.trading_day_trades('omega_trades', format('o.mode = %L', v_mode),
                                     p_day, 'event');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_omega_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_day_trades(date, text) TO authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 5) SAFE. Corpi VIVI di safe_strategy_paper_live_2026-09-13.sql (senza i DROP
--    delle firme vecchie, gia' eseguiti allora); cambia SOLO il criterio:
--    'placed' -> 'event'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_daily(
    p_from  date DEFAULT NULL,
    p_to    date DEFAULT NULL,
    p_sport text DEFAULT NULL,
    p_mode  text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today  date   := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mode   text   := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_conds  text[] := ARRAY[]::text[];
    v_filter text   := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_conds := v_conds || format('t.sport = %L', p_sport);
    END IF;
    IF v_mode IS NOT NULL THEN
        IF v_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
        END IF;
        v_conds := v_conds || format('t.mode = %L', v_mode);
    END IF;
    IF array_length(v_conds, 1) > 0 THEN
        v_filter := array_to_string(v_conds, ' AND ');
    END IF;
    RETURN public.trading_daily_history(
        'safe_strategy_trades',
        $e$t.strategy$e$,
        $e$t.sport$e$,
        v_filter,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        NULL,
        'event');   -- 01/10: giorno della PARTITA (ripiego: piazzamento); era C-01 'placed'
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_daily(date,date,text,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_daily(date,date,text,text) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_safe_day_trades(
    p_day   date,
    p_sport text DEFAULT NULL,
    p_mode  text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode   text   := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_conds  text[] := ARRAY[]::text[];
    v_filter text   := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_conds := v_conds || format('o.sport = %L', p_sport);
    END IF;
    IF v_mode IS NOT NULL THEN
        IF v_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
        END IF;
        v_conds := v_conds || format('o.mode = %L', v_mode);
    END IF;
    IF array_length(v_conds, 1) > 0 THEN
        v_filter := array_to_string(v_conds, ' AND ');
    END IF;
    -- 01/10: giorno della PARTITA (ripiego: piazzamento)
    RETURN public.trading_day_trades('safe_strategy_trades', v_filter, p_day, 'event');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_day_trades(date,text,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_day_trades(date,text,text) TO authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 6) MIKE. Corpi VIVI di mike_storico_giorno_regolamento_2026-09-29.sql;
--    cambia SOLO il criterio: 'settled' -> 'event'.
-- ----------------------------------------------------------------------------
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
        -- 01/10: giorno della PARTITA (ripiego: piazzamento); era M8.10 'settled'
        'event');

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
    -- 01/10: giorno della PARTITA (ripiego: piazzamento); era M8.10 'settled'.
    RETURN public.trading_day_trades('mike_trades', format('o.mode = %L', v_mode),
                                     p_day, 'event');
END;
$$;

REVOKE ALL    ON FUNCTION public.get_mike_day_trades(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_day_trades(date, text) TO authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 6b) IMPORTO PIAZZATO PER GIORNATA (base del ROI dello Storico per sport).
--    Corpo VIVO di storico_sport_2026-09-17.sql (presente sul DB: POST
--    /rest/v1/rpc/get_storico_stake = 200 il 01/10). Prima raggruppava per
--    giorno di PIAZZAMENTO mentre il P&L dello storico va ora per giorno della
--    PARTITA: il ROI avrebbe diviso grandezze di giornate diverse. Ora l'apertura
--    conta nel giorno della partita (ripiego: giorno di piazzamento, la stessa
--    regola di `placed_day` di trading_daily_history in 'event').
--    Differenze marcate «EVENT 01/10»: inizio partita (LATERAL), candidati
--    piazzati fra 7 giorni prima e 7 dopo, giornata = op_day, filtro finale
--    per op_day. Stessa firma, stesse chiavi in uscita.
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
            -- EVENT 01/10: giornata = giorno della PARTITA, ripiego = piazzamento
            SELECT CASE WHEN st.start_at IS NOT NULL THEN (st.start_at AT TIME ZONE 'Europe/Rome')::date
                        ELSE (t.placed_at AT TIME ZONE 'Europe/Rome')::date END AS op_day,
                   coalesce(t.size, 0)::numeric AS size,
                   t.status,
                   -- PIAZZATA: identico predicato di `trading_daily_history`
                   (t.bet_id IS NOT NULL
                    OR (t.meta->>'flumine_client_ref') IS NOT NULL
                    OR t.meta->>'reason' = 'place_exception_reconciling') AS is_placed
              FROM public.%I t
              CROSS JOIN LATERAL (SELECT (%s)::timestamptz AS start_at) st  -- EVENT 01/10
             WHERE t.closes_trade_id IS NULL
               AND t.placed_at IS NOT NULL
               AND (%s)
               -- EVENT 01/10: candidati piazzati fra 7 giorni prima e 7 dopo
               AND (t.placed_at AT TIME ZONE 'Europe/Rome')::date BETWEEN $1 - 7 AND $2 + 7
        ), piazzate AS (
            SELECT op_day, size FROM aperture
             WHERE status <> 'error'
               AND (status <> 'pending' OR is_placed)
               AND op_day BETWEEN $1 AND $2  -- EVENT 01/10
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
    $q$, v_table, public.inizio_partita_sql(v_table, 't'), v_where)
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


-- ----------------------------------------------------------------------------
-- 7) POSIZIONI CHIUSE DI UNA GIORNATA per GIORNO DELLA PARTITA.
--    Aiutante NUOVO (il vecchio `posizioni_chiuse_tabella` resta com'e',
--    inutilizzato: rimetterlo in uso = riapplicare posizioni_chiuse_giornata_2026-09-24.sql).
--    Un CICLO (radice + catena intera A <- B <- C) appartiene al giorno se il
--    giorno di riferimento della RADICE cade nel giorno e almeno una gamba e'
--    regolata (settled_at o pnl_betfair_settled_at), quando che sia.
--    Giorno di riferimento = inizio partita (catena, poi stima dal minuto di
--    gioco) oppure, a RIPIEGO, il PIAZZAMENTO della radice. Il regolamento non
--    decide mai.
--    Candidati: gambe piazzate o regolate fra 7 giorni prima e 7 giorni dopo.
--    Ogni riga porta giorno_partita, giorno_da ('partita' | 'piazzamento'),
--    in_day (sempre true: il ciclo intero e' del giorno).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.posizioni_chiuse_tabella_partita(
    p_table text,
    p_mode  text,
    p_from  timestamptz,
    p_to    timestamptz
) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = public, pg_temp
AS $$
DECLARE
    v_out jsonb;
BEGIN
    IF p_table NOT IN ('omega_trades', 'safe_strategy_trades', 'mike_trades') THEN
        RAISE EXCEPTION 'tabella non ammessa: %', p_table;
    END IF;
    EXECUTE format($q$
        WITH RECURSIVE
        semi AS (
            SELECT t.id
              FROM public.%1$I t
             WHERE t.mode = $1
               AND ((t.placed_at >= $4 AND t.placed_at < $5)
                 OR (t.settled_at >= $4 AND t.settled_at < $5)
                 OR (t.pnl_betfair_settled_at >= $4 AND t.pnl_betfair_settled_at < $5))
        ),
        su (id, padre) AS (
            SELECT t.id, t.closes_trade_id
              FROM public.%1$I t
             WHERE t.id IN (SELECT id FROM semi)
            UNION
            SELECT p.id, p.closes_trade_id
              FROM public.%1$I p
              JOIN su ON p.id = su.padre
        ),
        radici AS (
            SELECT su.id
              FROM su
             WHERE su.padre IS NULL
                OR NOT EXISTS (SELECT 1 FROM public.%1$I x WHERE x.id = su.padre)
        ),
        giu (id, radice) AS (
            SELECT id, id FROM radici
            UNION
            SELECT c.id, g.radice
              FROM public.%1$I c
              JOIN giu g ON c.closes_trade_id = g.id
        ),
        inizio AS (
            -- riferimento = inizio partita (catena, poi minuto di gioco), ripiego PIAZZAMENTO della radice
            SELECT r.id AS radice, st.start_at, coalesce(st.start_at, t.placed_at) AS rif_at
              FROM radici r
              JOIN public.%1$I t ON t.id = r.id
              CROSS JOIN LATERAL (SELECT (%2$s)::timestamptz AS start_at) st
        ),
        scelte AS (
            SELECT i.radice, i.start_at
              FROM inizio i
             WHERE i.rif_at >= $2 AND i.rif_at < $3
               -- posizione CHIUSA: almeno una gamba regolata, quando che sia
               AND EXISTS (
                        SELECT 1
                          FROM giu g
                          JOIN public.%1$I x ON x.id = g.id
                         WHERE g.radice = i.radice
                           AND (x.settled_at IS NOT NULL OR x.pnl_betfair_settled_at IS NOT NULL))
        )
        SELECT coalesce(jsonb_agg(
                   to_jsonb(t.*) || jsonb_build_object(
                       'giorno_partita', to_char((s.start_at AT TIME ZONE 'Europe/Rome')::date, 'YYYY-MM-DD'),
                       'giorno_da', CASE WHEN s.start_at IS NOT NULL THEN 'partita' ELSE 'piazzamento' END,
                       -- il ciclo intero e' del giorno chiesto
                       'in_day', true)
                   ORDER BY t.placed_at, t.id), '[]'::jsonb)
          FROM giu g
          JOIN scelte s ON s.radice = g.radice
          JOIN public.%1$I t ON t.id = g.id
    $q$, p_table, public.inizio_partita_sql(p_table, 't'))
    INTO v_out
    USING p_mode, p_from, p_to, p_from - interval '7 days', p_to + interval '7 days';
    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.posizioni_chiuse_tabella_partita(text, text, timestamptz, timestamptz)
    FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.posizioni_chiuse_tabella_partita(text, text, timestamptz, timestamptz)
    TO service_role;

-- LA RPC DELLA SCHEDA: stessa firma, stesso output {giorno, mode, omega, safe,
-- mike, tennis}. I 4 bot tennis: giorno della partita da
-- tennis_live_follow.open_date (LA STESSA fonte di get_tennis_bot_daily del
-- 30/09), ripiego = giorno di PIAZZAMENTO (get_tennis_bot_daily ripiega invece
-- su settled_at: divergenza solo per ordini senza tennis_live_follow, 0 il 01/10).
CREATE OR REPLACE FUNCTION public.get_posizioni_chiuse_giornata(
    p_day  date,
    p_mode text
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode   text := lower(nullif(btrim(coalesce(p_mode, '')), ''));
    v_from   timestamptz;
    v_to     timestamptz;
    v_tennis jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'p_mode obbligatoria (paper|live): paper e live non si sommano mai';
    END IF;
    IF p_day IS NULL THEN
        RAISE EXCEPTION 'giorno mancante';
    END IF;
    v_from := (p_day::timestamp AT TIME ZONE 'Europe/Rome');
    v_to   := ((p_day + 1)::timestamp AT TIME ZONE 'Europe/Rome');

    SELECT coalesce(jsonb_agg(
               to_jsonb(o.*) || jsonb_build_object(
                   'giorno_partita', to_char((p.open_date AT TIME ZONE 'Europe/Rome')::date, 'YYYY-MM-DD'),
                   'giorno_da', CASE WHEN p.open_date IS NOT NULL THEN 'partita' ELSE 'piazzamento' END,
                   -- ogni ordine tennis e' selezionato da solo: se e' qui, e' del giorno
                   'in_day', true,
                   -- 01/10: nome della partita (tennis_live_orders non lo porta).
                   -- Registro tennis_live_follow, poi catalogo tennis_markets; NULL se nessuno dei due.
                   -- (concat_ws salta i NULL: un solo nome resta un nome, nessuno = NULL)
                   'event_name', coalesce(
                       nullif(concat_ws(' v ', nullif(btrim(fn.player1_name), ''),
                                               nullif(btrim(fn.player2_name), '')), ''),
                       nullif(concat_ws(' v ', nullif(btrim(tm.player1->>'name'), ''),
                                               nullif(btrim(tm.player2->>'name'), '')), '')))
               ORDER BY o.placed_at, o.id), '[]'::jsonb)
      INTO v_tennis
      FROM public.tennis_live_orders o
      LEFT JOIN LATERAL (
            SELECT f.open_date
              FROM public.tennis_live_follow f
             WHERE f.event_id = o.event_id
               AND f.open_date IS NOT NULL
             LIMIT 1
      ) p ON true
      LEFT JOIN public.tennis_live_follow fn ON fn.event_id = o.event_id
      LEFT JOIN public.tennis_markets     tm ON tm.event_id = o.event_id
     WHERE o.source IN ('tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing')
       AND o.mode = v_mode
       -- solo ordini REGOLATI (come prima)
       AND (o.settled_at IS NOT NULL OR o.pnl_betfair_settled_at IS NOT NULL)
       -- candidati: piazzati o regolati fra 7 giorni prima e 7 giorni dopo
       AND ((o.placed_at >= v_from - interval '7 days' AND o.placed_at < v_to + interval '7 days')
         OR (o.settled_at >= v_from - interval '7 days' AND o.settled_at < v_to + interval '7 days')
         OR (o.pnl_betfair_settled_at >= v_from - interval '7 days'
             AND o.pnl_betfair_settled_at < v_to + interval '7 days'))
       -- giorno della partita; ripiego = giorno di PIAZZAMENTO (il regolamento non decide)
       AND coalesce(p.open_date, o.placed_at) >= v_from
       AND coalesce(p.open_date, o.placed_at) <  v_to;

    RETURN jsonb_build_object(
        'giorno', p_day,
        'mode',   v_mode,
        'omega',  public.posizioni_chiuse_tabella_partita('omega_trades',         v_mode, v_from, v_to),
        'safe',   public.posizioni_chiuse_tabella_partita('safe_strategy_trades', v_mode, v_from, v_to),
        'mike',   public.posizioni_chiuse_tabella_partita('mike_trades',          v_mode, v_from, v_to),
        'tennis', v_tennis
    );
END;
$$;
REVOKE ALL ON FUNCTION public.get_posizioni_chiuse_giornata(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_posizioni_chiuse_giornata(date, text) TO authenticated, service_role;
