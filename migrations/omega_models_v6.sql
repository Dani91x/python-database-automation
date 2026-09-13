-- ============================================================================
-- OMEGA — certificazione chirurgica 12/09/2026 (SQL + contratto UI).
--
-- ORDINE DI APPLICAZIONE (prerequisiti REALI, tutti necessari):
--     1. omega_bot.sql          4. omega_cashout.sql      7. omega_models_v4.sql
--     2. omega_v2.sql           5. omega_models_v3.sql    8. mike_history_v2.sql
--     3. omega_manual.sql       6. omega_daily_v2.sql     9. omega_models_v5.sql
--    10. omega_models_v6.sql  → QUESTO FILE (ultimo dell'ordine in
--        migrations/APPLY_ORDER_2026-09-11.md)
--
-- IDEMPOTENTE: CREATE OR REPLACE a firma INVARIATA (omega_aggregates_sql(),
-- get_omega_missions(): stessi argomenti e stesso RETURNS delle versioni
-- precedenti → nessun DROP necessario), DROP FUNCTION IF EXISTS con firme
-- esatte, REVOKE/GRANT ripetibili. Nessuna modifica ai dati.
-- NON ridefinisce trading_daily_history / trading_day_trades (proprietà di
-- mike_history_v2.sql): si limita a togliere gli overload STANTII a 7/3
-- argomenti e a verificare che ne resti UNO solo.
--
-- Contenuto (difetti dell'audit 12/09, numerazione del report):
--   S-01 omega_aggregates_sql(): due divergenze residue dal percorso PURO
--        omega_engine.aggregate_trades (la fonte di verità dichiarata §17.3):
--        (a) `meta ? 'hedged_size'` era vero anche con hedged_size = null JSON
--            → il residuo max(0,−if_win) veniva usato dove il Python usa la
--            liability piena; ora `(meta->>'hedged_size') IS NOT NULL`;
--        (b) locked_pnl_open(_today) filtrava SOLO status open/hedged: un
--            'pending' PIAZZATO (bet_id/ref/riconciliazione) a copertura
--            completa contava 0 dove il Python somma il bloccato. Allineato.
--   S-02 get_omega_missions() (omega_v2.sql): gli aggregati per gamba usavano
--        criteri VECCHI e diversi dai KPI: `hedged` non contava come vivo,
--        un 'pending' PAPER via flumine (flumine_client_ref) o in
--        RICONCILIAZIONE non contava come piazzato, e le gambe di CHIUSURA
--        (closes_trade_id) sommavano la loro liability (= stake del back) in
--        `open_liability` e contavano in `n_open`/`n_settled` → la scheda
--        missione mostrava un rischio DIVERSO dalla barra di giornata e
--        contava due volte una posizione coperta. Ora: stessi criteri di
--        omega_aggregates_sql (is_placed, hedge_complete → rischio 0, residuo
--        max(0,−if_win)); le chiusure restano nell'elenco `trades` (con
--        `closes_trade_id`, così la UI le mostra come chiusure) ma NON nei
--        conteggi di posizione. Nuove chiavi per gamba: `locked_pnl`,
--        `reconciling_liability`.
--   S-03 get_omega_missions(): la UI (MissionCard.missionTradeStatus /
--        missionTradeValue) legge `meta.reconciling`, `meta.locked_pnl`,
--        `meta.error_final`… su ogni trade, ma la RPC NON mandava `meta`:
--        «IN VERIFICA SU BETFAIR» ed «ERRORE (definitivo)» erano
--        irraggiungibili nel tab Missione e una gamba coperta diceva
--        «bloccato +0,00 €». Ora ogni trade porta un `meta` RIDOTTO alle
--        sole chiavi del contratto UI (§17.4) + `settled_at`.
--   S-04 omega_v2.sql aveva ricreato get_omega_missions SENZA REVOKE/GRANT
--        (l'ACL sopravviveva solo perché CREATE OR REPLACE la conserva):
--        qui sono espliciti, come in tutte le altre RPC.
--   S-05 overload 7/3 argomenti di trading_daily_history / trading_day_trades:
--        omega_models_v4.sql (CREATE OR REPLACE dell'8-arg) non li toglieva;
--        se daily_history.sql o mike_history.sql vengono riapplicati DOPO,
--        torna il bug R2 (42725 "is not unique"). Qui: DROP IF EXISTS delle
--        firme vecchie + verifica finale che ne resti ESATTAMENTE una
--        (eccezione con rimedio, mai uno stato ambiguo silenzioso).
--
-- SE NON APPLICATA: il servizio funziona (Python ha il proprio aggregate_trades),
-- ma (a) su un pending piazzato a copertura completa il bloccato di giornata
-- dell'RPC resta 0 (stop-loss/target del servizio leggono dall'RPC quando
-- c'è); (b) il tab Missione continua a mostrare rischio e conteggi diversi dai
-- KPI e a non dire mai «IN VERIFICA SU BETFAIR».
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. S-01 — aggregati: identici a omega_engine.aggregate_trades
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    -- UNA sola scansione di omega_trades (tabella piccola: ~200 righe/giorno);
    -- giorno della posizione = placed_at dell'APERTURA (join su PK).
    -- Usata da get_omega_state (UI) e da get_omega_aggregates (servizio).
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome') AS v_day
    ), raw AS (
        -- estrazioni dal meta, SEMPRE difensive (un valore non numerico scritto a
        -- mano non deve far fallire l'RPC di stato: la UI resterebbe cieca)
        SELECT o.id, o.status, o.pnl, o.placed_at, o.event_id, o.closes_trade_id,
               o.liability AS liability_gross,
               CASE WHEN (o.meta->>'locked_pnl')    ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'locked_pnl')::numeric    END AS m_locked,
               CASE WHEN (o.meta->>'residual_size') ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'residual_size')::numeric END AS m_residual,
               CASE WHEN (o.meta->>'if_win')        ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (o.meta->>'if_win')::numeric        END AS m_if_win,
               -- S-01(a): come omega_engine.residual_liability — hedged_size
               -- PRESENTE E NON NULL (un `null` JSON non è una copertura)
               ((o.meta->>'hedged_size') IS NOT NULL)                                       AS m_has_hedged,
               (o.meta->>'reconciling' IN ('true','t')
                OR o.meta->>'reason' = 'place_exception_reconciling')                      AS reconciling,
               (o.bet_id IS NOT NULL OR (o.meta->>'flumine_client_ref') IS NOT NULL)       AS has_order,
               coalesce(p.placed_at, o.placed_at)                                          AS pos_placed_at
          FROM public.omega_trades o
          LEFT JOIN public.omega_trades p ON p.id = o.closes_trade_id
    ), t AS (
        SELECT r.status, r.pnl, r.placed_at, r.event_id, r.closes_trade_id,
               r.liability_gross, r.reconciling, r.pos_placed_at,
               -- copertura COMPLETA: meta.locked_pnl è scritto SOLO a residuo nullo
               -- (safe_strategy.execution.hedge_state) → P&L bloccato, rischio 0
               (r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01) AS hedge_complete,
               CASE WHEN r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01
                    THEN r.m_locked END AS locked_pnl,
               -- H-06: liability VIVA. 0 a copertura completa; altrimenti il residuo
               -- max(0,−if_win) scritto dallo strato di esecuzione; altrimenti la
               -- liability piena (posizione nuda).
               CASE WHEN r.m_locked IS NOT NULL AND coalesce(r.m_residual, 0) <= 0.01 THEN 0
                    WHEN r.m_has_hedged AND r.m_if_win IS NOT NULL
                    THEN greatest(0, -r.m_if_win)
                    ELSE r.liability_gross END AS liability,
               -- H-02: 'pending' in RICONCILIAZIONE = ordine reale forse vivo
               (r.has_order OR r.reconciling) AS is_placed,
               -- esito della POSIZIONE (apertura + chiusure) per SEGNO del P&L totale
               CASE WHEN r.closes_trade_id IS NULL AND r.status IN ('won','lost','void') THEN
                    r.pnl + coalesce((SELECT sum(c.pnl) FROM public.omega_trades c
                                       WHERE c.closes_trade_id = r.id AND c.status IN ('won','lost','void')), 0)
               END AS total_pnl
          FROM raw r
    ), live AS (
        -- posizione VIVA adesso (stesso predicato di omega_engine: open/hedged, o
        -- pending PIAZZATO). Definito una volta sola: tutti i filtri sotto lo usano.
        SELECT t.*,
               (t.closes_trade_id IS NULL
                AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))) AS is_live
          FROM t
    )
    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.pos_placed_at >= d.v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.is_live), 0),
        -- H-06: P&L già BLOCCATO sulle posizioni vive (non realizzato, rischio 0).
        -- S-01(b): ANCHE un pending piazzato a copertura completa (come il Python)
        'locked_pnl_open', coalesce(sum(t.locked_pnl) FILTER (WHERE t.is_live AND t.hedge_complete), 0),
        -- review H1: la quota del bloccato attribuita alla GIORNATA (posizioni
        -- PIAZZATE oggi): pesa su stop-loss giornaliero e target dinamico
        'locked_pnl_open_today', coalesce(sum(t.locked_pnl) FILTER (WHERE t.is_live AND t.hedge_complete
                               AND t.placed_at >= d.v_day), 0),
        -- H-02: quanto di open_liability è un ordine a esito IGNOTO in riconciliazione
        'reconciling_liability', coalesce(sum(t.liability_gross) FILTER (WHERE t.closes_trade_id IS NULL
                               AND t.status = 'pending' AND t.reconciling), 0),
        'matches_traded',  count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))),
        'matches_traded_today', count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged','won','lost','void') OR (t.status = 'pending' AND t.is_placed))
                               AND t.placed_at >= d.v_day),
        'legs_today',      count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'events_today',    count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL AND t.status <> 'error'
                               AND (t.status <> 'pending' OR t.is_placed) AND t.placed_at >= d.v_day),
        'matches_open',    count(*) FILTER (WHERE t.is_live),
        -- H-08: partite DISTINTE con una posizione VIVA adesso (nessun giorno)
        'live_now',        count(DISTINCT t.event_id) FILTER (WHERE t.is_live),
        'matches_won',     count(*) FILTER (WHERE t.total_pnl > 0),
        'matches_lost',    count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',       count(*) FILTER (WHERE t.total_pnl > 0 AND t.placed_at >= d.v_day),
        'lost_today',      count(*) FILTER (WHERE t.total_pnl < 0 AND t.placed_at >= d.v_day)
    )
      FROM d LEFT JOIN live t ON true
     GROUP BY d.v_day;
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql() TO service_role;

-- ----------------------------------------------------------------------------
-- 2. S-02 / S-03 / S-04 — missioni: stessi criteri dei KPI, meta per la UI
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_missions()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows    jsonb;
    v_summary jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT coalesce(jsonb_agg(r ORDER BY (r->>'kickoff') NULLS LAST), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT to_jsonb(m.*)
               || jsonb_build_object(
                    'legs', (
                        SELECT coalesce(jsonb_object_agg(t.phase, t.agg), '{}'::jsonb)
                          FROM (
                            SELECT x.phase,
                                   jsonb_build_object(
                                     -- realizzato della GAMBA = apertura + chiusure regolate
                                     'realized', coalesce(sum(x.pnl) FILTER (WHERE x.status IN ('won','lost','void')), 0),
                                     -- rischio VIVO delle sole aperture (H-06: 0 a copertura completa,
                                     -- residuo a copertura parziale); mai lo stake di una chiusura
                                     'open_liability', coalesce(sum(x.liability_live) FILTER (WHERE x.is_live), 0),
                                     'reconciling_liability', coalesce(sum(x.liability) FILTER (WHERE x.closes_trade_id IS NULL
                                                               AND x.status = 'pending' AND x.reconciling), 0),
                                     'locked_pnl', coalesce(sum(x.locked_pnl) FILTER (WHERE x.is_live AND x.hedge_complete), 0),
                                     'n_open', count(*) FILTER (WHERE x.is_live),
                                     'n_settled', count(*) FILTER (WHERE x.closes_trade_id IS NULL AND x.status IN ('won','lost','void')),
                                     'trades', coalesce(jsonb_agg(jsonb_build_object(
                                         'id', x.id, 'runner_name', x.runner_name, 'side', x.side,
                                         'price', x.price, 'size', x.size, 'liability', x.liability,
                                         'status', x.status, 'pnl', x.pnl, 'mode', x.mode,
                                         'minute_at_entry', x.minute_at_entry, 'score_at_entry', x.score_at_entry,
                                         'placed_at', x.placed_at, 'settled_at', x.settled_at, 'origin', x.origin,
                                         'closes_trade_id', x.closes_trade_id,
                                         'meta', x.meta_ui)
                                       ORDER BY x.placed_at, x.id), '[]'::jsonb)
                                   ) AS agg
                              FROM (
                                SELECT y.*,
                                       (y.closes_trade_id IS NULL
                                        AND (y.status IN ('open','hedged')
                                             OR (y.status = 'pending' AND (y.has_order OR y.reconciling)))) AS is_live,
                                       (y.m_locked IS NOT NULL AND coalesce(y.m_residual, 0) <= 0.01) AS hedge_complete,
                                       CASE WHEN y.m_locked IS NOT NULL AND coalesce(y.m_residual, 0) <= 0.01 THEN y.m_locked END AS locked_pnl,
                                       CASE WHEN y.m_locked IS NOT NULL AND coalesce(y.m_residual, 0) <= 0.01 THEN 0
                                            WHEN y.m_has_hedged AND y.m_if_win IS NOT NULL THEN greatest(0, -y.m_if_win)
                                            ELSE y.liability END AS liability_live
                                  FROM (
                                    SELECT tr.id, tr.phase, tr.runner_name, tr.side, tr.price, tr.size, tr.liability,
                                           tr.status, tr.pnl, tr.mode, tr.minute_at_entry, tr.score_at_entry,
                                           tr.placed_at, tr.settled_at, tr.origin, tr.closes_trade_id,
                                           CASE WHEN (tr.meta->>'locked_pnl')    ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (tr.meta->>'locked_pnl')::numeric    END AS m_locked,
                                           CASE WHEN (tr.meta->>'residual_size') ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (tr.meta->>'residual_size')::numeric END AS m_residual,
                                           CASE WHEN (tr.meta->>'if_win')        ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN (tr.meta->>'if_win')::numeric        END AS m_if_win,
                                           ((tr.meta->>'hedged_size') IS NOT NULL) AS m_has_hedged,
                                           (tr.meta->>'reconciling' IN ('true','t')
                                            OR tr.meta->>'reason' = 'place_exception_reconciling') AS reconciling,
                                           (tr.bet_id IS NOT NULL OR (tr.meta->>'flumine_client_ref') IS NOT NULL) AS has_order,
                                           -- S-03: SOLO le chiavi del contratto UI (§17.4), niente blocchi
                                           -- pesanti (model/runners/greenup): jsonb_strip_nulls toglie le assenti
                                           jsonb_strip_nulls(jsonb_build_object(
                                               'reconciling',   tr.meta->'reconciling',
                                               'reason',        tr.meta->'reason',
                                               'error_final',   tr.meta->'error_final',
                                               'leg_failed',    tr.meta->'leg_failed',
                                               'error_at',      tr.meta->'error_at',
                                               'no_fill_at',    tr.meta->'no_fill_at',
                                               'locked_pnl',    tr.meta->'locked_pnl',
                                               'hedged_size',   tr.meta->'hedged_size',
                                               'residual_size', tr.meta->'residual_size',
                                               'if_win',        tr.meta->'if_win',
                                               'hedging',       tr.meta->'hedging',
                                               'exit_kind',     tr.meta->'exit_kind',
                                               'exit_reason',   tr.meta->'exit_reason',
                                               'exit_profit',   tr.meta->'exit_profit',
                                               'cashout',       tr.meta->'cashout')) AS meta_ui
                                      FROM public.omega_trades tr
                                     WHERE tr.event_id = m.event_id AND tr.phase IS NOT NULL
                                  ) y
                              ) x
                             GROUP BY x.phase
                          ) t
                    ),
                    'scalper', (
                        SELECT jsonb_build_object(
                                 'status', s.status, 'dry_run', s.dry_run,
                                 'pnl_locked', coalesce((s.stats->>'pnl_locked')::numeric, 0))
                          FROM public.scalper_control s
                         WHERE s.event_id = m.event_id
                    ),
                    'followed', EXISTS (SELECT 1 FROM public.live_follow f
                                         WHERE f.event_id = m.event_id)
                  ) AS r
          FROM public.omega_missions m
         -- oggi + ATTIVE e IN PAUSA di giorni passati (audit H3c + review 16/07)
         WHERE m.mission_date = (now() AT TIME ZONE 'Europe/Rome')::date
            OR m.status IN ('active','paused')
      ) sub(r);

    SELECT jsonb_build_object(
             'missions_total',  count(*),
             'missions_active', count(*) FILTER (WHERE status = 'active'))
      INTO v_summary
      FROM public.omega_missions
     WHERE mission_date = (now() AT TIME ZONE 'Europe/Rome')::date
        OR status IN ('active','paused');

    RETURN jsonb_build_object('missions', v_rows, 'summary', v_summary);
END;
$$;
-- S-04: ACL esplicita (omega_v2.sql l'aveva omessa)
REVOKE ALL    ON FUNCTION public.get_omega_missions() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_missions() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. S-05 — funzioni condivise dello storico: UNA sola firma viva

-- ----------------------------------------------------------------------------
-- S-05 (certificazione 12/09, UI): get_omega_events() restituiva l'INTERA
-- cache omega_events, senza alcun filtro di data. La scheda Missione e il menu
-- del Manuale mostravano cosi' partite di giorni prima, gia' finite, e
-- l'utente poteva attivare una missione o piazzare un ordine su un mercato
-- chiuso. Il client oggi filtra per conto suo, ma la RPC resta una fonte che
-- serve dati stantii a QUALUNQUE consumatore: si filtra alla radice.
--
-- Finestra: dalle 3 ore PRIMA di adesso in avanti (una partita iniziata da
-- meno di 3 ore e' ancora in corso o appena finita: deve restare operabile).
-- Firma INVARIATA (nessun argomento) -> CREATE OR REPLACE, nessun DROP.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_events()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(e.*) ORDER BY e.open_date NULLS LAST), '[]'::jsonb)
      INTO v
      FROM public.omega_events e
     WHERE e.open_date IS NULL
        OR e.open_date >= now() - interval '3 hours';
    RETURN v;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_events() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_events() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- Le firme a 7/3 argomenti (daily_history.sql / mike_history.sql) NON devono
-- coesistere con quelle a 8/4 (omega_daily_v2.sql → mike_history_v2.sql):
-- ogni chiamata senza tutti gli argomenti fallirebbe con 42725. Il DROP è
-- idempotente; la verifica sotto non lascia mai uno stato ambiguo silenzioso.
DROP FUNCTION IF EXISTS public.trading_daily_history(text,text,text,text,date,date,numeric);
DROP FUNCTION IF EXISTS public.trading_day_trades(text,text,date);

DO $$
DECLARE
    n_hist  integer;
    n_day   integer;
    n_tab   integer;
BEGIN
    SELECT count(*) INTO n_hist
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trading_daily_history';
    SELECT count(*) INTO n_day
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trading_day_trades';
    IF n_hist <> 1 OR n_day <> 1 THEN
        RAISE EXCEPTION 'storico condiviso in stato ambiguo: trading_daily_history=% firme, trading_day_trades=% firme (attese 1 e 1). Rimedio: applicare mike_history_v2.sql (dopo omega_daily_v2.sql) e rieseguire questo file.',
            n_hist, n_day;
    END IF;
    -- la firma superstite deve essere quella a 8/4 argomenti con p_day_by:
    -- get_omega_daily / get_omega_day_trades la chiamano con 'placed'
    SELECT count(*) INTO n_tab
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = 'trading_daily_history'
       AND p.pronargs = 8;
    IF n_tab <> 1 THEN
        RAISE EXCEPTION 'trading_daily_history non è la versione a 8 argomenti (p_day_by): applicare omega_daily_v2.sql e mike_history_v2.sql.';
    END IF;
END $$;

-- VERIFICA (facoltativa):
--   select public.omega_aggregates_sql();           -- 17 chiavi, come §17.3
--   select public.get_omega_missions();             -- legs.*.trades[].meta / closes_trade_id
--   select count(*) from pg_proc where proname = 'trading_daily_history';   -- 1
--   select count(*) from pg_proc where proname = 'trading_day_trades';      -- 1
--   select jsonb_array_length(public.get_omega_events());  -- solo eventi operabili
