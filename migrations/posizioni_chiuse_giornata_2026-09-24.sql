-- ============================================================================
-- posizioni_chiuse_giornata_2026-09-24.sql - LE CHIUSE DI UNA GIORNATA.
--
-- Ordine dell'utente (24/09): "Posizioni chiuse / storico: e' LENTISSIMO nel
-- caricamento, i dati sono mischiati per giornata, sono confusionari [...]
-- IL TRADER DEVE FIDARSI DI QUELLO CHE VEDE."
--
-- La scheda "Posizioni chiuse" della Control Room mostra UNA giornata alla
-- volta (giorno di REGOLAMENTO, fuso Europe/Rome, la stessa regola della barra
-- di giornata e del conto Betfair) e UNA modalita' alla volta (paper e live
-- non si sommano mai). Oggi la vede SUBITO dalle righe gia' in memoria; questa
-- RPC serve a:
--   * completare OGGI: `get_safe_state` porta 200 righe paper+live insieme
--     (reperto B15) e `get_mike_state` solo quelle piazzate oggi: una chiusura
--     la cui apertura e' fuori da quelle righe risultava "orfana";
--   * leggere un GIORNO PASSATO a richiesta, una giornata per volta (il
--     client la memorizza: `frontend/src/lib/chiuseGiornata.ts`), invece di
--     portarsi dietro lo storico intero a ogni giro dei 30 s.
--
-- COSA RESTITUISCE: {giorno, mode, omega:[...], safe:[...], mike:[...],
-- tennis:[...]} con le righe `to_jsonb(t.*)` (le STESSE chiavi di
-- `get_omega_trades` / `get_safe_state` / `get_mike_state` /
-- `get_tennis_bot_orders_today`):
--   * Omega / Safe / Mike: ogni CICLO (apertura + TUTTA la catena di
--     chiusure A <- B <- C) con almeno una gamba REGOLATA nel giorno
--     (`settled_at` del bot o `pnl_betfair_settled_at` di Betfair). La
--     giornata definitiva del ciclo la decide il client (l'ultima gamba
--     regolata), con la stessa regola della barra.
--   * i 4 bot tennis: gli ordini regolati nel giorno. Non hanno legame
--     ingresso-uscita (reperto B13): il client li raggruppa per (bot, mercato,
--     selezione) e lo dichiara.
--
-- MIGRAZIONE ADDITIVA E IDEMPOTENTE: una funzione nuova, un aiutante interno,
-- cinque indici. Nessuna tabella, colonna o funzione esistente toccata.
-- PREREQUISITO: `pnl_betfair_reale_2026-09-24.sql` (colonne
-- `pnl_betfair_settled_at`). Finche' questa non e' applicata il client
-- RIPIEGA sulle RPC di storico per bot (`get_*_day_trades`) e lo scrive a
-- video: niente bot tennis per i giorni passati, catene al primo livello.
--
-- Da applicare a cura dell'utente (SQL editor di Supabase).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) INDICI. Le colonne di regolamento sono quelle su cui la giornata filtra.
--    Esistono gia': omega_trades(settled_at) parziale (omega_models_v4),
--    mike_trades(settled_at DESC) (mike_bot_v2), tennis_live_orders(mode,
--    settled_at) (tennis_bot_pnl_2026-09-17), e gli indici su closes_trade_id
--    dei tre bot (omega_cashout, safe_strategy_bot, mike_bot_v2) che servono
--    alla risalita/discesa delle catene. Mancano:
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_safe_trades_settled_at
    ON public.safe_strategy_trades (settled_at)
    WHERE settled_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_omega_trades_pnl_bf_settled
    ON public.omega_trades (pnl_betfair_settled_at)
    WHERE pnl_betfair_settled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_safe_trades_pnl_bf_settled
    ON public.safe_strategy_trades (pnl_betfair_settled_at)
    WHERE pnl_betfair_settled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mike_trades_pnl_bf_settled
    ON public.mike_trades (pnl_betfair_settled_at)
    WHERE pnl_betfair_settled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tlo_pnl_bf_settled
    ON public.tennis_live_orders (pnl_betfair_settled_at)
    WHERE pnl_betfair_settled_at IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2) AIUTANTE INTERNO: i cicli di UNA tabella dei bot con almeno una gamba
--    regolata in [p_from, p_to), catene intere.
--    - semi   : le gambe regolate nella finestra (indici su settled_at e
--               pnl_betfair_settled_at: BitmapOr);
--    - su     : si RISALE closes_trade_id fino alla radice;
--    - radici : senza padre, o col padre che non esiste piu' (orfana: resta
--               una riga sua, il client la dichiara);
--    - giu    : si SCENDE da ogni radice a tutta la catena (A <- B <- C).
--    UNION (non UNION ALL) nelle due ricorsioni: un ciclo nei dati (A chiude
--    B, B chiude A) si ferma al primo nodo gia' visto, mai un giro infinito.
--    Nome di tabella in lista bianca prima di finire in format(%I).
--    Solo chiamato da get_posizioni_chiuse_giornata (SECURITY DEFINER): a
--    nessun ruolo di client serve eseguirlo.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.posizioni_chiuse_tabella(
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
               AND ((t.settled_at >= $2 AND t.settled_at < $3)
                 OR (t.pnl_betfair_settled_at >= $2 AND t.pnl_betfair_settled_at < $3))
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
        giu (id) AS (
            SELECT id FROM radici
            UNION
            SELECT c.id
              FROM public.%1$I c
              JOIN giu g ON c.closes_trade_id = g.id
        )
        SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at, t.id), '[]'::jsonb)
          FROM public.%1$I t
         WHERE t.id IN (SELECT id FROM giu)
    $q$, p_table)
    INTO v_out
    USING p_mode, p_from, p_to;
    RETURN coalesce(v_out, '[]'::jsonb);
END;
$$;
REVOKE ALL ON FUNCTION public.posizioni_chiuse_tabella(text, text, timestamptz, timestamptz)
    FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.posizioni_chiuse_tabella(text, text, timestamptz, timestamptz)
    TO service_role;

-- ----------------------------------------------------------------------------
-- 3) LA RPC DELLA SCHEDA. Owner-only; `p_mode` OBBLIGATORIA (paper e live non
--    si sommano mai); giornata = giorno di Roma.
-- ----------------------------------------------------------------------------
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

    SELECT coalesce(jsonb_agg(to_jsonb(o.*) ORDER BY o.placed_at, o.id), '[]'::jsonb)
      INTO v_tennis
      FROM public.tennis_live_orders o
     WHERE o.source IN ('tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing')
       AND o.mode = v_mode
       AND ((o.settled_at >= v_from AND o.settled_at < v_to)
         OR (o.pnl_betfair_settled_at >= v_from AND o.pnl_betfair_settled_at < v_to));

    RETURN jsonb_build_object(
        'giorno', p_day,
        'mode',   v_mode,
        'omega',  public.posizioni_chiuse_tabella('omega_trades',         v_mode, v_from, v_to),
        'safe',   public.posizioni_chiuse_tabella('safe_strategy_trades', v_mode, v_from, v_to),
        'mike',   public.posizioni_chiuse_tabella('mike_trades',          v_mode, v_from, v_to),
        'tennis', v_tennis
    );
END;
$$;
REVOKE ALL ON FUNCTION public.get_posizioni_chiuse_giornata(date, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_posizioni_chiuse_giornata(date, text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4) VERIFICA (da eseguire dopo l'applicazione, SOLA LETTURA).
--
--   -- la firma c'e' ed e' chiusa ad anon:
--   SELECT p.proname, pg_get_function_identity_arguments(p.oid),
--          has_function_privilege('anon', p.oid, 'EXECUTE')          AS anon,
--          has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth
--     FROM pg_proc p WHERE p.proname IN ('get_posizioni_chiuse_giornata',
--                                        'posizioni_chiuse_tabella');
--   -- atteso: get_posizioni_chiuse_giornata anon=f auth=t;
--   --         posizioni_chiuse_tabella       anon=f auth=f
--
--   -- EXPLAIN ATTESO della parte piu' pesante (Safe, una giornata):
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT t.id FROM public.safe_strategy_trades t
--    WHERE t.mode = 'live'
--      AND ((t.settled_at >= '2026-09-23 22:00+00' AND t.settled_at < '2026-09-24 22:00+00')
--        OR (t.pnl_betfair_settled_at >= '2026-09-23 22:00+00'
--            AND t.pnl_betfair_settled_at < '2026-09-24 22:00+00'));
--   -- atteso: BitmapOr su idx_safe_trades_settled_at e
--   --   idx_safe_trades_pnl_bf_settled (niente Seq Scan sull'intera tabella
--   --   quando la tabella supera qualche migliaio di righe; su tabelle
--   --   piccole il planner puo' preferire il Seq Scan, ed e' corretto).
--   -- La risalita/discesa usa idx_safe_trades_closes / la chiave primaria.
--
--   -- una giornata vera (owner loggato, o service_role):
--   SELECT jsonb_array_length(r->'omega') AS omega, jsonb_array_length(r->'safe') AS safe,
--          jsonb_array_length(r->'mike') AS mike, jsonb_array_length(r->'tennis') AS tennis
--     FROM (SELECT public.get_posizioni_chiuse_giornata(current_date, 'live') AS r) x;
-- ----------------------------------------------------------------------------
