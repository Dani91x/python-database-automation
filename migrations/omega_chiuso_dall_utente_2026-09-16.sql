-- ============================================================================
-- OMEGA — «SE CHIUDO IO, IL BOT DEVE SAPERLO» (16/09/2026, sera)
--
-- ORDINE DELL'UTENTE (16/09 sera, verbatim):
--   «se chiudo io (anche fuori dall'app, direttamente su Betfair) il bot deve
--    saperlo e NON gestire posizioni che non esistono piu'; cash-out globale ->
--    al controllo dopo non fa altro; il bot gestisce le SUE operazioni e ignora
--    le mie manuali».
--
-- PREREQUISITI (ordine reale): i file di migrations/APPLY_ORDER_2026-09-11.md,
-- in particolare omega_manual.sql (tabella omega_events), omega_daily_v2.sql e
-- omega_models_v6.sql (omega_aggregates_sql / get_omega_aggregates).
--
-- NON APPLICATA. La applica l'utente. Finche' non lo e':
--     * il marker «chiuso dall'utente» vive solo in RAM nel processo del
--       servizio, che lo DICE forte nell'attivita' `evento_chiuso_dall_utente`
--       ("STATO NON SCRITTO"): il blocco vale fino al riavvio, poi si perde;
--     * gli aggregati con cui il bot decide si calcolano in casa leggendo le
--       righe — una scansione in piu' SOLO quando esistono davvero operazioni
--       manuali che contano (omega_db._esistono_manuali_che_contano).
--
-- CONTENUTO
--   1. omega_events.stato_utente (JSONB) — lo stato ESPLICITO per evento (R8)
--   2. omega_evento_riprendi(text) — il gesto che lo toglie («Riprendi»)
--   3. omega_eventi_chiusi_dall_utente() — l'elenco, per la UI
--   4. omega_aggregates_sql(boolean) + get_omega_aggregates() con il blocco
--      `auto`: i numeri con cui il BOT decide, senza le manuali dell'utente (R6)
--
-- IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, CREATE OR REPLACE a firma invariata,
-- una firma NUOVA (il boolean) aggiunta come overload. Nessuna modifica ai dati.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. R8 — LO STATO DELL'EVENTO
--
-- Prima del 16/09 questo stato non esisteva. Dopo un cash-out dell'utente il
-- bot smetteva di aprire su quella partita solo per EFFETTO COLLATERALE: la
-- gamba di chiusura nasce con origin='manual', l'evento finiva in
-- omega_db.manual_event_ids() e §8 lo escludeva — per TRE GIORNI, senza che
-- nessuno lo avesse mai dichiarato, e chiudere UNA gamba di due escludeva
-- anche l'altra. Adesso e' scritto, si legge, e si toglie SOLO con un gesto.
--
-- Forma del JSON (la scrive omega_service._chiudi_evento):
--   {"chiuso_dall_utente": true,
--    "dove": "cash-out nell'app" | "fuori dall'app",
--    "at": "2026-09-16T21:15:00+00:00",
--    ... dettaglio: trade_id, selezioni, netti di conto }
-- ----------------------------------------------------------------------------
ALTER TABLE public.omega_events
    ADD COLUMN IF NOT EXISTS stato_utente JSONB;

COMMENT ON COLUMN public.omega_events.stato_utente IS
    'Stato dell''evento deciso dall''UTENTE (16/09/2026). chiuso_dall_utente=true: '
    'il bot non apre e non copre piu'' su questa partita finche'' non si preme '
    'Riprendi (omega_evento_riprendi). NULL = nessuno stato.';

-- l'elenco lo legge il servizio a ogni respiro: indice PARZIALE, piccolissimo
CREATE INDEX IF NOT EXISTS ix_omega_events_stato_utente
    ON public.omega_events (event_id)
    WHERE stato_utente IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. IL GESTO ESPLICITO — «Riprendi»
--
-- Lo stato NON si azzera da solo: ne' col passare dei giorni, ne' quando la
-- partita finisce, ne' quando la cache eventi si rinfresca (omega_db.
-- replace_events non cancella piu' le righe che portano un marker). Si toglie
-- solo cosi', e il pulsante e' dell'utente.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_evento_riprendi(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_prima jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT stato_utente INTO v_prima
      FROM public.omega_events WHERE event_id = p_event_id;
    UPDATE public.omega_events
       SET stato_utente = NULL, updated_at = now()
     WHERE event_id = p_event_id;
    -- traccia: chi riprende una partita che aveva chiuso lo fa apposta, e
    -- deve restare scritto (stessa tabella delle altre attivita' di Omega)
    BEGIN
        INSERT INTO public.omega_activity (kind, payload)
        VALUES ('evento_ripreso',
                jsonb_build_object('event_id', p_event_id, 'prima', v_prima));
    EXCEPTION WHEN undefined_table OR undefined_column THEN
        NULL;   -- omega_activity con un'altra forma: il gesto vale lo stesso
    END;
    RETURN jsonb_build_object('event_id', p_event_id, 'ripreso', true,
                              'prima', v_prima);
END;
$fn$;
REVOKE ALL    ON FUNCTION public.omega_evento_riprendi(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_evento_riprendi(text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. L'ELENCO, per la UI (il servizio legge la tabella direttamente)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_eventi_chiusi_dall_utente()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $fn$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN coalesce((
        SELECT jsonb_agg(jsonb_build_object('event_id', e.event_id,
                                            'name', e.name,
                                            'stato_utente', e.stato_utente)
                         ORDER BY e.event_id)
          FROM public.omega_events e
         WHERE e.stato_utente ->> 'chiuso_dall_utente' IN ('true','t')
    ), '[]'::jsonb);
END;
$fn$;
REVOKE ALL    ON FUNCTION public.omega_eventi_chiusi_dall_utente() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_eventi_chiusi_dall_utente() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. R6 — I NUMERI CON CUI IL BOT DECIDE
--
-- Misurato il 16/09 sul banco: con una lay MANUALE dell'utente aperta sulla
-- stessa partita, il bot vedeva 70 EUR di liability «sua» contro 0 EUR delle
-- sue gambe — e su quei 70 EUR si muovevano target di gamba, stop_on_goal,
-- daily_loss_cap e max_open_liability.
--
-- Da qui: stesso identico calcolo, con un interruttore. Il corpo e' UNO SOLO
-- (l'overload senza argomenti chiama quello col boolean): due copie della
-- stessa matematica sono un difetto in attesa di succedere.
-- I TOTALI DI PAGINA restano completi; il blocco `auto` porta i numeri del bot.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql(p_solo_auto boolean)
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
         -- R6 (16/09, ordine dell'utente h18): con p_solo_auto restano SOLO le
         -- posizioni DEL BOT. Il proprietario di una riga e' l'origin della sua
         -- POSIZIONE: per un'apertura il proprio, per una gamba di chiusura
         -- quello dell'apertura che chiude (un cash-out fatto a mano su una
         -- gamba del bot porta origin='manual' ma il suo P&L e' del bot, e
         -- toglierlo renderebbe cieco il cap di perdita).
         -- Identico a omega_engine.posizione_manuale.
         WHERE NOT p_solo_auto
            OR coalesce(p.origin, o.origin, 'auto') <> 'manual'
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
REVOKE ALL ON FUNCTION public.omega_aggregates_sql(boolean) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql(boolean) TO service_role;

-- l'overload storico (nessun argomento) resta la STESSA COSA di prima: tutto,
-- comprese le operazioni manuali. Chi lo chiama oggi (get_omega_state per la
-- UI) non cambia di una virgola.
CREATE OR REPLACE FUNCTION public.omega_aggregates_sql()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT public.omega_aggregates_sql(false);
$$;
REVOKE ALL ON FUNCTION public.omega_aggregates_sql() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.omega_aggregates_sql() TO service_role;

-- per il SERVIZIO: i totali di pagina PIU' il blocco `auto` (i numeri del bot).
-- Una chiamata sola: il database non si scandisce due volte per giro (§18).
CREATE OR REPLACE FUNCTION public.get_omega_aggregates()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $fn$
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    RETURN coalesce(public.omega_aggregates_sql(false), '{}'::jsonb)
           || jsonb_build_object('auto',
                coalesce(public.omega_aggregates_sql(true), '{}'::jsonb));
END;
$fn$;
REVOKE ALL    ON FUNCTION public.get_omega_aggregates() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_aggregates() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- VERIFICA (a mano, dopo l'applicazione)
--   select jsonb_pretty(public.get_omega_aggregates());   -- deve avere 'auto'
--   select public.omega_eventi_chiusi_dall_utente();
--   select public.omega_evento_riprendi('<event_id>');
-- ----------------------------------------------------------------------------
