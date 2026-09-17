-- ============================================================================
-- tennis_bot_pnl_2026-09-17.sql
--
-- PERCHE' ESISTE (audit dei 4 bot tennis, 17/09/2026 —
-- `Betfair/stream/tennis_live/AUDIT_4_BOT_TENNIS_2026-09-17.md` §F):
--
--   Il P&L dei quattro bot tennis oggi NON e' sommabile. Vive in due posti e
--   nessuno dei due e' uno storico:
--     * `tennis_bot_control.stats` — un JSON per (event_id, bot_key) che
--       l'heartbeat RISCRIVE PER INTERO a ogni battito: e' la FOTOGRAFIA della
--       sessione corrente, non una serie. Al riarmo la RPC `tennis_bot_arm` lo
--       azzera (`stats = NULL`), e con esso il P&L della partita;
--     * `tennis_live_orders` — lo specchio degli ordini, che pero' NON ha
--       nessuna colonna di profitto ne' di regolamento.
--   Risultato: lo Storico (`TradingHistory`, `HistoryVariant = omega|safe|mike`,
--   `frontend/src/lib/dailyHistory.ts:121`) non puo' nemmeno provarci: non
--   esiste una RPC `get_tennis_bot_daily` perche' non esiste il dato. Uno
--   storico costruito su `stats.pnl_*` mostrerebbe un numero LORDO e per-evento
--   (avvertenza gia' scritta in `frontend/src/lib/tennis.ts:552`).
--
-- COSA FA QUESTO FILE
--   1) aggiunge a `tennis_live_orders` le colonne del REGOLAMENTO: `pnl`
--      (profitto LORDO dell'ordine, come lo da' Betfair/flumine), `commission`
--      (la commissione applicata al mercato) e `settled_at`;
--   2) crea `get_tennis_bot_daily` / `get_tennis_bot_day_trades`, le due RPC
--      che lo Storico usa gia' per Omega, Safe e Mike, cosi' i quattro bot
--      possono entrare nella stessa pagina con lo stesso contratto;
--   3) NON tocca niente del calcio e nessuna riga esistente: le colonne nuove
--      sono NULL, e NULL vuol dire «non regolato», mai zero (regola
--      «dato assente = —, mai 0,00 €», `frontend/src/lib/format.ts:15`).
--
-- ⚠️ NON APPLICATA. Le migrazioni le applica l'utente (CLAUDE.md). Finche' non
--    e' applicata, il writer Python continua a scrivere le colonne vecchie e
--    queste restano NULL: nessuna rottura.
--
-- MONEY-CRITICAL: `mode` separa sempre paper e live e le RPC non sommano mai le
-- due modalita' insieme (catalogo §7 punto 21). IDEMPOTENTE.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) le colonne del regolamento sullo specchio ordini
-- ----------------------------------------------------------------------------
ALTER TABLE public.tennis_live_orders
    ADD COLUMN IF NOT EXISTS pnl         NUMERIC,     -- profitto LORDO dell'ordine
    ADD COLUMN IF NOT EXISTS commission  NUMERIC,     -- commissione del mercato
    ADD COLUMN IF NOT EXISTS settled_at  TIMESTAMPTZ; -- quando Betfair l'ha regolato

COMMENT ON COLUMN public.tennis_live_orders.pnl IS
    'Profitto LORDO dell''ordine al regolamento (Betfair cleared / flumine '
    'simulated.profit). NULL = non ancora regolato: la UI scrive un trattino, '
    'mai 0,00 euro.';
COMMENT ON COLUMN public.tennis_live_orders.commission IS
    'Commissione applicata dal mercato a questo ordine. NULL = ignota.';
COMMENT ON COLUMN public.tennis_live_orders.settled_at IS
    'Istante del regolamento. NULL = ordine non ancora regolato.';

-- lo storico interroga per giorno e per modalita': l'indice segue quella query
CREATE INDEX IF NOT EXISTS idx_tlo_settled
    ON public.tennis_live_orders (mode, settled_at)
    WHERE settled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tlo_source
    ON public.tennis_live_orders (source, mode);

-- ----------------------------------------------------------------------------
-- 2) get_tennis_bot_daily(p_from, p_to, p_mode, p_bot) -> json {rows: [...]}
--    Una riga per GIORNO (e per bot, se `p_bot` e' NULL): e' il contratto che
--    `frontend/src/lib/dailyHistory.ts` usa gia' per `get_safe_daily`.
--    `p_mode` e' OBBLIGATORIO: paper e live non si sommano MAI.
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
               count(*) FILTER (WHERE o.pnl > 0)                AS vinti,
               count(*) FILTER (WHERE o.pnl < 0)                AS persi,
               round(sum(o.pnl)::numeric, 2)                    AS pnl_lordo,
               round(sum(coalesce(o.commission, 0))::numeric, 2) AS commissione,
               round((sum(o.pnl) - sum(coalesce(o.commission, 0)))::numeric, 2)
                                                                AS pnl_netto,
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

-- ----------------------------------------------------------------------------
-- 3) get_tennis_bot_day_trades(p_day, p_mode, p_bot) -> json {rows: [...]}
--    Il dettaglio di UN giorno: gli ordini regolati, uno per riga.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tennis_bot_day_trades(
    p_day  date,
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
        RAISE EXCEPTION 'p_mode obbligatoria (paper|live)';
    END IF;
    IF p_day IS NULL THEN
        RAISE EXCEPTION 'p_day obbligatorio';
    END IF;

    SELECT coalesce(json_agg(to_jsonb(o.*) ORDER BY o.settled_at), '[]'::json)
      INTO v_rows
      FROM public.tennis_live_orders o
     WHERE lower(o.mode) = v_mode
       AND o.source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
       AND (p_bot IS NULL OR o.source = p_bot)
       AND o.settled_at IS NOT NULL
       AND (o.settled_at AT TIME ZONE 'Europe/Rome')::date = p_day;

    RETURN json_build_object('rows', v_rows, 'mode', v_mode);
END;
$$;

-- ----------------------------------------------------------------------------
-- GRANTS — owner-only dentro le RPC, come tutte le `tennis_*`.
-- ----------------------------------------------------------------------------
REVOKE ALL    ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              TO authenticated, service_role;

REVOKE ALL    ON FUNCTION public.get_tennis_bot_day_trades(date, text, text)
              FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_day_trades(date, text, text)
              TO authenticated, service_role;
