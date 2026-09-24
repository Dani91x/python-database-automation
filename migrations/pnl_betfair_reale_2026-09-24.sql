-- ============================================================================
-- pnl_betfair_reale_2026-09-24.sql - IL P&L REALE DA BETFAIR (ordini 9 e 10
-- dell'utente, 24/09).
--
--   (9)  "il P&L delle operazioni va preso DIRETTAMENTE da Betfair e non
--        stimato, al netto di tutto (commissione)";
--   (10) "la barra di giornata deve avanzare considerando le operazioni di
--        TUTTI i bot attivi e le mie in manuale, sia dalla nostra app che dal
--        sito Betfair direttamente".
--
-- FONTE (docs.developer.betfair.com, ClearedOrderSummary + "listClearedOrders
-- - Roll-up Fields Available"): `profit` e' il LORDO della riga; `commission`
-- esiste SOLO raggruppando per MARKET/EVENT/EVENT_TYPE/EXCHANGE (mai per BET).
-- Netto di un ordine = profit(BET) - quota della commissione del suo mercato
-- (ripartita sui profit positivi, somma esatta). Lo calcola e lo scrive UN
-- SOLO punto: il giro dei regolati del runner
-- (`Betfair/stream/reconcile_worker.py::_sync_manual_pnl`, dentro il ciclo del
-- saldo gia' esistente; nessun processo nuovo).
--
-- MIGRAZIONE ADDITIVA E IDEMPOTENTE: nessuna colonna esistente toccata,
-- nessun dato esistente alterato, `pnl` dei bot INVARIATO (resta il loro
-- calcolo: il reale gli sta ACCANTO). Il codice funziona anche PRIMA che sia
-- applicata: le scritture falliscono, il runner lo logga e ritenta, la pagina
-- mostra il P&L calcolato marcato "stimato".
--
-- Da applicare a cura dell'utente (SQL editor di Supabase), in qualunque
-- momento. Nessun ordine con altre migrazioni in attesa.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) Le tre colonne del P&L reale, sulle 5 tabelle che hanno righe con bet_id.
--    NULL = Betfair non ha ancora regolato quell'ordine (o la riga e' paper,
--    che su Betfair non esiste): la pagina mostra il P&L calcolato, STIMATO.
-- ----------------------------------------------------------------------------
ALTER TABLE public.omega_trades
    ADD COLUMN IF NOT EXISTS pnl_betfair            NUMERIC,
    ADD COLUMN IF NOT EXISTS commissione_betfair    NUMERIC,
    ADD COLUMN IF NOT EXISTS pnl_betfair_settled_at TIMESTAMPTZ;

ALTER TABLE public.safe_strategy_trades
    ADD COLUMN IF NOT EXISTS pnl_betfair            NUMERIC,
    ADD COLUMN IF NOT EXISTS commissione_betfair    NUMERIC,
    ADD COLUMN IF NOT EXISTS pnl_betfair_settled_at TIMESTAMPTZ;

ALTER TABLE public.mike_trades
    ADD COLUMN IF NOT EXISTS pnl_betfair            NUMERIC,
    ADD COLUMN IF NOT EXISTS commissione_betfair    NUMERIC,
    ADD COLUMN IF NOT EXISTS pnl_betfair_settled_at TIMESTAMPTZ;

ALTER TABLE public.tennis_live_orders
    ADD COLUMN IF NOT EXISTS pnl_betfair            NUMERIC,
    ADD COLUMN IF NOT EXISTS commissione_betfair    NUMERIC,
    ADD COLUMN IF NOT EXISTS pnl_betfair_settled_at TIMESTAMPTZ;

ALTER TABLE public.betfair_live_orders
    ADD COLUMN IF NOT EXISTS pnl_betfair            NUMERIC,
    ADD COLUMN IF NOT EXISTS commissione_betfair    NUMERIC,
    ADD COLUMN IF NOT EXISTS pnl_betfair_settled_at TIMESTAMPTZ;

COMMENT ON COLUMN public.omega_trades.pnl_betfair IS
    'P&L NETTO regolato da Betfair (listClearedOrders: profit dell''ordine - quota della commissione del mercato). NULL = non ancora regolato: vale il pnl calcolato, STIMATO.';
COMMENT ON COLUMN public.safe_strategy_trades.pnl_betfair IS
    'P&L NETTO regolato da Betfair (listClearedOrders: profit dell''ordine - quota della commissione del mercato). NULL = non ancora regolato: vale il pnl calcolato, STIMATO.';
COMMENT ON COLUMN public.mike_trades.pnl_betfair IS
    'P&L NETTO regolato da Betfair (listClearedOrders: profit dell''ordine - quota della commissione del mercato). NULL = non ancora regolato: vale il pnl calcolato, STIMATO.';
COMMENT ON COLUMN public.tennis_live_orders.pnl_betfair IS
    'P&L NETTO regolato da Betfair (listClearedOrders: profit dell''ordine - quota della commissione del mercato). NULL = non ancora regolato: vale pnl - commission, STIMATO.';
COMMENT ON COLUMN public.betfair_live_orders.pnl_betfair IS
    'P&L NETTO regolato da Betfair (listClearedOrders: profit dell''ordine - quota della commissione del mercato). NULL = non ancora regolato.';

-- ----------------------------------------------------------------------------
-- 2) Il P&L reale di OGGI dell'intero conto, per voce, sulla riga singleton
--    `betfair_live_account` (id=1), gia' in realtime per la pagina.
--    Forma (scritta da `db.upsert_live_account_pnl_reale`):
--    {"day","netto","lordo","commissione","ordini","senza_commissione",
--     "sospetti_sito","per_fonte":{"omega"|"safe_calcio"|"safe_tennis"|"mike"|
--     "bot_tennis"|"manuale_app"|"manuale_sito"|"altri_bot":
--     {"netto","lordo","ordini","senza_commissione"}},"bet_ids":[...],
--     "letto_at"}
-- ----------------------------------------------------------------------------
ALTER TABLE public.betfair_live_account
    ADD COLUMN IF NOT EXISTS pnl_reale_oggi JSONB;

COMMENT ON COLUMN public.betfair_live_account.pnl_reale_oggi IS
    'P&L NETTO regolato OGGI (giorno Europe/Rome, settledDate di Betfair) su TUTTO il conto, per voce. Scritto dal runner (reconcile_worker._sync_manual_pnl). Mai paper.';

-- ----------------------------------------------------------------------------
-- 3) GRANT (dal 30/10 Supabase non da' piu' i default a service_role).
--    service_role: il runner scrive le colonne nuove.
--    authenticated: SELECT di colonna sulle tabelle che la pagina legge
--    DIRETTAMENTE (hanno gia' il SELECT di tabella + la policy owner: qui si
--    dichiara esplicitamente il minimo). omega_trades / safe_strategy_trades /
--    mike_trades restano CHIUSE ad authenticated per scelta (REVOKE ALL nelle
--    loro migrazioni): la pagina le legge dalle RPC SECURITY DEFINER
--    (`to_jsonb(t.*)`), che portano le colonne nuove da sole. Aprirle qui
--    allargherebbe l'accesso: non lo si fa.
-- ----------------------------------------------------------------------------
GRANT SELECT, UPDATE ON TABLE public.omega_trades         TO service_role;
GRANT SELECT, UPDATE ON TABLE public.safe_strategy_trades TO service_role;
GRANT SELECT, UPDATE ON TABLE public.mike_trades          TO service_role;
GRANT SELECT, UPDATE ON TABLE public.tennis_live_orders   TO service_role;
GRANT SELECT, UPDATE ON TABLE public.betfair_live_orders  TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.betfair_live_account TO service_role;

GRANT SELECT (pnl_betfair, commissione_betfair, pnl_betfair_settled_at)
    ON public.tennis_live_orders  TO authenticated;
GRANT SELECT (pnl_betfair, commissione_betfair, pnl_betfair_settled_at)
    ON public.betfair_live_orders TO authenticated;
GRANT SELECT (pnl_reale_oggi) ON public.betfair_live_account TO authenticated;

-- ----------------------------------------------------------------------------
-- 4) get_tennis_bot_daily: il netto dei 4 bot tennis e' quello di Betfair
--    quando c'e' (`pnl_betfair`), altrimenti il calcolo di sempre
--    (pnl - commission), e lo DICE: `pnl_reale` / `pnl_stimato` / `stimati`.
--    Firma, filtri, owner-only e separazione paper/live INVARIATI; le colonne
--    di prima restano con lo stesso nome (pnl_netto = reale + stimato).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tennis_bot_daily(
    p_from date,
    p_to   date,
    p_mode text,
    p_bot  text DEFAULT NULL
) RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
    v_mode text := lower(nullif(p_mode, ''));
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'p_mode obbligatoria (paper|live): paper e live non si sommano mai';
    END IF;
    IF p_from IS NULL OR p_to IS NULL OR p_to < p_from THEN
        RAISE EXCEPTION 'intervallo di date non valido';
    END IF;
    IF p_bot IS NOT NULL AND p_bot NOT IN
       ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing') THEN
        RAISE EXCEPTION 'p_bot non valido: %', p_bot;
    END IF;

    SELECT coalesce(json_agg(r ORDER BY r.giorno, r.bot_key), '[]'::json)
      INTO v_rows
      FROM (
        SELECT (o.settled_at AT TIME ZONE 'Europe/Rome')::date AS giorno,
               o.source                                        AS bot_key,
               count(*)                                        AS ordini,
               count(*) FILTER (WHERE coalesce(o.pnl_betfair, o.pnl - coalesce(o.commission, 0)) > 0)
                                                                AS vinti,
               count(*) FILTER (WHERE coalesce(o.pnl_betfair, o.pnl - coalesce(o.commission, 0)) < 0)
                                                                AS persi,
               round(sum(o.pnl)::numeric, 2)                    AS pnl_lordo,
               round(sum(coalesce(o.commissione_betfair, o.commission, 0))::numeric, 2)
                                                                AS commissione,
               round(sum(coalesce(o.pnl_betfair, o.pnl - coalesce(o.commission, 0)))::numeric, 2)
                                                                AS pnl_netto,
               round(coalesce(sum(o.pnl_betfair), 0)::numeric, 2) AS pnl_reale,
               round(coalesce(sum(o.pnl - coalesce(o.commission, 0))
                              FILTER (WHERE o.pnl_betfair IS NULL), 0)::numeric, 2)
                                                                AS pnl_stimato,
               count(*) FILTER (WHERE o.pnl_betfair IS NULL)    AS stimati,
               round(sum(o.size_matched)::numeric, 2)           AS volume
          FROM public.tennis_live_orders o
         WHERE lower(o.mode) = v_mode
           AND o.source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
           AND (p_bot IS NULL OR o.source = p_bot)
           AND o.settled_at IS NOT NULL
           AND (o.settled_at AT TIME ZONE 'Europe/Rome')::date BETWEEN p_from AND p_to
         GROUP BY 1, 2
      ) r;

    RETURN json_build_object('rows', v_rows, 'mode', v_mode);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              TO authenticated, service_role;
