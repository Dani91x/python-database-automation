-- ============================================================================
-- tennis_bot_daily_giorno_partita_2026-09-30.sql
--
-- 30/09 (backend per la UI): ``get_tennis_bot_daily`` raggruppa per il GIORNO
-- DELLA PARTITA (Europe/Rome) invece che per il giorno del REGOLAMENTO
-- (``settled_at``, definizione precedente: pnl_betfair_reale_2026-09-24.sql
-- sez. 4, la stessa letta in sola lettura da pg_get_functiondef il 30/09).
--
-- Giorno della partita = ``tennis_live_follow.open_date`` dell'evento (orario
-- di inizio Betfair, colonna open_date, chiave event_id). Se l'evento non e'
-- nel registro (riga assente o open_date NULL) il giorno resta quello del
-- regolamento, come prima: nessuna riga sparisce. Verifica in sola lettura del
-- 30/09: 17 righe regolate dei 4 bot (tutte paper), 17 risolte in
-- tennis_live_follow, 0 con giorno diverso da quello del regolamento.
--
-- INVARIATI: firma (date, date, text, text), tipo di ritorno json, owner-only,
-- p_mode obbligatoria (paper e live mai sommati), p_bot, le colonne della riga
-- (giorno, bot_key, ordini, vinti, persi, pnl_lordo, commissione, pnl_netto,
-- pnl_reale, pnl_stimato, stimati, volume), solo righe regolate.
-- IDEMPOTENTE (CREATE OR REPLACE). Da applicare DOPO pnl_betfair_reale_2026-09-24.sql.
-- ============================================================================
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
        SELECT g.giorno                                         AS giorno,
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
          LEFT JOIN LATERAL (
                SELECT f.open_date
                  FROM public.tennis_live_follow f
                 WHERE f.event_id = o.event_id
                   AND f.open_date IS NOT NULL
                 LIMIT 1
          ) p ON true
          CROSS JOIN LATERAL (
                SELECT (coalesce(p.open_date, o.settled_at) AT TIME ZONE 'Europe/Rome')::date AS giorno
          ) g
         WHERE lower(o.mode) = v_mode
           AND o.source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
           AND (p_bot IS NULL OR o.source = p_bot)
           AND o.settled_at IS NOT NULL
           AND g.giorno BETWEEN p_from AND p_to
         GROUP BY 1, 2
      ) r;

    RETURN json_build_object('rows', v_rows, 'mode', v_mode);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_bot_daily(date, date, text, text)
              TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- VERIFICA (sola lettura, dopo l'applicazione, dal SQL editor come owner):
--   SELECT public.get_tennis_bot_daily(current_date - 7, current_date, 'paper');
-- ----------------------------------------------------------------------------
