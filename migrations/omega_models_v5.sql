-- ============================================================================
-- OMEGA — AUDIT 11/09/2026 (sera), sezione 3 + review della stessa sera.
--
-- ORDINE DI APPLICAZIONE (prerequisiti REALI, tutti necessari):
--     1. omega_bot.sql        → omega_control, omega_trades, omega_activity
--     2. omega_v2.sql         → phase + uq_omega_trades_auto_leg
--     3. omega_manual.sql     → uq_omega_trades_leg, omega_events, manuale
--     4. omega_cashout.sql    → closes_trade_id, status 'hedged', unique parziali
--     5. omega_models_v3.sql  → tabelle per minuto
--     6. omega_daily_v2.sql   → omega_daily_goal, get_omega_aggregates,
--                               omega_snapshot_daily_goal  (QUESTA migrazione li USA)
--     7. omega_models_v4.sql  → indici, get_omega_daily set-based
--     8. omega_models_v5.sql  → QUESTO FILE
--   Applicarlo prima di omega_daily_v2.sql fallisce: omega_aggregates_sql qui
--   dentro è letta da get_omega_aggregates() (definita in omega_daily_v2) e
--   get_omega_state legge public.omega_daily_goal (creata in omega_daily_v2).
--
-- IDEMPOTENTE (CREATE OR REPLACE / IF NOT EXISTS / DROP INDEX IF EXISTS).
-- NON tocca le funzioni condivise trading_daily_history / trading_day_trades
-- (proprietà di un'altra revisione).
--
-- Contenuto:
--   1. omega_aggregates_sql(): UNA sola verità per i numeri di Omega.
--      • H-02 un 'pending' in RICONCILIAZIONE (ordine reale a esito IGNOTO,
--        meta.reconciling) CONTA come piazzato: liability, posizioni aperte,
--        gambe ed eventi della giornata. Prima spariva dai KPI mentre la
--        tabella lo mostrava: un lay reale forse vivo e invisibile.
--        Nuovo campo `reconciling_liability` (già dentro open_liability).
--      • H-06 a copertura COMPLETA il rischio è ZERO: la perdita bloccata è
--        già fatta, non può peggiorare. Prima una posizione greenata a −22 €
--        contava 22 € di "liability aperta" (danno contato due volte, cap di
--        esposizione falsato). Nuovo campo `locked_pnl_open` = P&L già
--        bloccato sulle posizioni vive (non realizzato, non a rischio).
--      • H-08 la giornata la dice SOLO la RPC: `legs_today`, `events_today`,
--        `won_today`, `lost_today`, `realized_today` e il nuovo `live_now`
--        (partite DISTINTE con una posizione viva adesso). 'error', riserve
--        mai piazzate e gambe di chiusura restano fuori.
--      • review H1 `locked_pnl_open_today`: la quota del P&L bloccato delle
--        partite di OGGI. Il servizio la usa per lo stop-loss giornaliero e per
--        il target dinamico (R efficace = realized_today + min(0, bloccato)):
--        una perdita bloccata è denaro perso anche se non ancora incassato.
--   2. get_omega_state(): H-02 lo stato di riconciliazione è leggibile;
--      M-22 l'attività è quella della GIORNATA OPERATIVA (Europe/Rome), non
--      "le ultime N righe" (a mezzanotte la UI mostrava le righe di ieri
--      etichettate "oggi"); `goal_today` accompagnato da `goal_snapshot`.
--   3. H-13 unique uq_omega_trades_auto_leg: esclude le gambe con
--      meta.leg_failed = true (esito CERTO negativo: FOK ucciso da Betfair,
--      paper senza fill, richiesta mai creata → NESSUN ordine reale esiste).
--      Così un FOK ucciso non brucia la gamba per tutta la partita. Le righe
--      'error' di riconciliazione (esito non verificato) continuano a
--      bloccare il ripiazzamento: la rete di sicurezza del live resta.
--
-- SE NON APPLICATA: il servizio funziona comunque (il Python legge gli stessi
-- numeri con omega_engine.aggregate_trades e tollera l'RPC vecchia), ma
-- (a) i KPI della UI continuano a NON contare il pending in riconciliazione e
-- a contare come rischio la perdita già bloccata; (b) l'attività di "oggi"
-- resta un elenco delle ultime righe; (c) una gamba con esito certo negativo
-- non si ripiazza (l'insert viene rifiutato e il ciclo logga 'already_reserved',
-- come oggi: nessun danno, solo l'occasione persa).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Aggregati: una sola verità (liability VERA, giornata operativa)
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
               (o.meta ? 'hedged_size')                                                   AS m_has_hedged,
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
    )
    SELECT jsonb_build_object(
        'realized_profit', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today',  coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void') AND t.pos_placed_at >= d.v_day), 0),
        'open_liability',  coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))), 0),
        -- H-06: P&L già BLOCCATO sulle posizioni vive (non realizzato, rischio 0)
        'locked_pnl_open', coalesce(sum(t.locked_pnl) FILTER (WHERE t.closes_trade_id IS NULL
                               AND t.status IN ('open','hedged') AND t.hedge_complete), 0),
        -- review H1: la quota del bloccato attribuita alla GIORNATA (posizioni
        -- PIAZZATE oggi). È quella che deve pesare su stop-loss giornaliero e
        -- target dinamico: con la liability a 0 dopo la copertura, dieci green-up
        -- chiusi a −22 € davano R=0 e nessuna guardia si accorgeva di −220 €.
        'locked_pnl_open_today', coalesce(sum(t.locked_pnl) FILTER (WHERE t.closes_trade_id IS NULL
                               AND t.status IN ('open','hedged') AND t.hedge_complete
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
        'matches_open',    count(*) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))),
        -- H-08: partite DISTINTE con una posizione VIVA adesso (nessun giorno: il
        -- rischio vivo non ha giorno — una partita di ieri ancora aperta conta)
        'live_now',        count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL
                               AND (t.status IN ('open','hedged') OR (t.status = 'pending' AND t.is_placed))),
        'matches_won',     count(*) FILTER (WHERE t.total_pnl > 0),
        'matches_lost',    count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',       count(*) FILTER (WHERE t.total_pnl > 0 AND t.placed_at >= d.v_day),
        'lost_today',      count(*) FILTER (WHERE t.total_pnl < 0 AND t.placed_at >= d.v_day)
    )
      FROM d LEFT JOIN t ON true
     GROUP BY d.v_day;
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql() TO service_role;

-- ----------------------------------------------------------------------------
-- 2. Stato per la UI: attività della GIORNATA OPERATIVA + obiettivo con flag
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_state(
    p_activity_limit integer DEFAULT 50
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl jsonb;
    v_act  jsonb;
    v_agg  jsonb;
    v_goal numeric;
    v_snap boolean := false;
    v_day  date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_day0 timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
    v_lim  integer := least(greatest(coalesce(p_activity_limit, 50), 1), 300);
    v_more integer := 0;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.omega_control c WHERE c.id = 1;
    v_agg := coalesce(public.omega_aggregates_sql(), '{}'::jsonb);

    -- M-22: SOLO la giornata operativa (Europe/Rome). Le righe di ieri non
    -- compaiono mai come "attività di oggi"; se la giornata ha più righe del
    -- limite si dice quante ne restano (activity_more) invece di mentire.
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb)
      INTO v_act
      FROM (SELECT * FROM public.omega_activity
             WHERE ts >= v_day0
             ORDER BY ts DESC
             LIMIT v_lim) a;
    SELECT greatest(0, count(*) - v_lim) INTO v_more
      FROM public.omega_activity WHERE ts >= v_day0;

    SELECT g.goal INTO v_goal FROM public.omega_daily_goal g WHERE g.day = v_day;
    IF v_goal IS NOT NULL THEN
        v_snap := true;
    ELSE
        SELECT c.daily_goal INTO v_goal FROM public.omega_control c WHERE c.id = 1;
    END IF;

    RETURN jsonb_build_object('control', v_ctrl, 'aggregates', v_agg, 'activity', v_act,
                              'activity_more', v_more,
                              'activity_day', v_day,
                              'goal_today', to_jsonb(v_goal),
                              'goal_snapshot', v_snap);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_state(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_state(integer) TO authenticated, service_role;

-- indice per il filtro di giornata sull'attività (la tabella cresce di molte
-- righe al giorno: senza indice get_omega_state farebbe un seq scan ogni 2 s)
CREATE INDEX IF NOT EXISTS idx_omega_activity_ts ON public.omega_activity (ts DESC);

-- ----------------------------------------------------------------------------
-- 3. H-13: l'unique della gamba automatica esclude gli esiti CERTI negativi
-- ----------------------------------------------------------------------------
-- meta.leg_failed = true lo scrive SOLO il servizio quando è PROVATO che nessun
-- ordine reale esiste (_leg_certain_failure, _flumine_no_fill_error): FOK ucciso
-- da Betfair, terminale senza fill, richiesta di coda mai creata o in errore.
-- Un esito IGNOTO non passa mai di lì (resta 'pending' + meta.reconciling).
DROP INDEX IF EXISTS public.uq_omega_trades_auto_leg;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_auto_leg
    ON public.omega_trades (event_id, coalesce(phase, ''))
    WHERE origin = 'auto' AND closes_trade_id IS NULL
      AND coalesce(meta->>'leg_failed', '') <> 'true';

-- review L1: lo STESSO criterio sull'altro unique parziale. Senza, una gamba
-- bruciata bloccava comunque il ripiazzamento sulla stessa (mercato, selezione,
-- lato): uq_omega_trades_leg escludeva solo status='error', ma una riga con
-- meta.leg_failed può essere 'error' o (delete fallito) ancora 'pending'.
DROP INDEX IF EXISTS public.uq_omega_trades_leg;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_leg
    ON public.omega_trades (event_id, market_id, selection_id, side)
    WHERE status <> 'error' AND closes_trade_id IS NULL
      AND coalesce(meta->>'leg_failed', '') <> 'true';

-- indice per i percorsi che filtrano le gambe bruciate (traded_legs, failed_legs:
-- il budget dei tentativi per gamba lo legge dal DB, review H4)
CREATE INDEX IF NOT EXISTS idx_omega_trades_leg_failed
    ON public.omega_trades (event_id, placed_at DESC)
    WHERE closes_trade_id IS NULL AND coalesce(meta->>'leg_failed', '') = 'true';
