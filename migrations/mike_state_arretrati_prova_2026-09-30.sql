-- ============================================================================
-- mike_state_arretrati_prova_2026-09-30.sql
-- get_mike_state(): chiave ADDITIVA `arretrati_prova`.
--
-- PERCHE'. La giornata operativa di Mike e' il giorno di PIAZZAMENTO della
-- posizione (M6). Un ciclo paper aperto e giocato il 26/09 e regolato oggi
-- (30/09) non compare tra le righe "di oggi": la UI, per la prova di oggi, non
-- lo vedeva e non poteva dirlo. Qui la RPC porta anche quegli ARRETRATI, cioe'
-- le righe paper REGOLATE oggi (giorno di Roma) il cui ciclo appartiene a un
-- giorno precedente (giorno di Roma di coalesce(mike_events.ko_at, placed_at
-- dell'APERTURA del ciclo) < oggi).
--
-- COSA CAMBIA. Solo la funzione public.get_mike_state(): il corpo e' quello
-- VIVO di migrations/mike_bot_v2.sql (righe 149-196), copiato per intero, piu'
-- UNA chiave nel jsonb_build_object finale e le variabili che le servono.
-- Firma, SECURITY DEFINER, search_path, REVOKE/GRANT: identici. Le chiavi
-- esistenti (control, events, trades, activity, aggregates, requests,
-- day_start, day_by) sono INVARIATE.
--
-- FORMA della chiave (SEMPRE presente, anche senza righe: righe = []):
--   arretrati_prova: { day: 'YYYY-MM-DD' (giorno di Roma di oggi),
--     righe: [ { bot:'mike', mode:'paper', id, event_id, event_name, ko_at,
--                placed_at (dell'apertura del ciclo), settled_at, status,
--                pnl (netto, come mike_trades.pnl), closes_trade_id } ] }
--   * solo mike_trades.mode = 'paper' (le righe live NON entrano);
--   * TUTTE le gambe del ciclo regolate oggi (apertura + chiusure, anche a
--     catena A <- B <- C: l'apertura si risale seguendo closes_trade_id);
--   * ordine settled_at DESC, id DESC; tetto largo LIMIT 2000 (dichiarato:
--     oltre, le piu' vecchie in ordine di regolamento restano fuori).
--
-- IDEMPOTENTE (CREATE OR REPLACE). Solo struttura della funzione: nessun dato
-- scritto, nessuna tabella/colonna/indice toccati. La applica l'utente.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_mike_state()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_ctrl   jsonb;
    v_events jsonb;
    v_trades jsonb;
    v_agg    jsonb;
    v_act    jsonb;
    v_reqs   jsonb;
    v_arr    jsonb;
    v_day    timestamptz := (date_trunc('day', now() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome');
    v_oggi   date        := (now() AT TIME ZONE 'Europe/Rome')::date;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.mike_control c WHERE c.id = 1;
    SELECT coalesce(jsonb_agg(to_jsonb(e.*) ORDER BY e.ko_at ASC), '[]'::jsonb) INTO v_events
      FROM (SELECT * FROM public.mike_events
             WHERE state NOT IN ('SETTLED','SKIPPED','ERROR') OR updated_at >= now() - interval '24 hours'
             ORDER BY ko_at ASC LIMIT 200) e;
    -- M5 (review): tetto DURO e ordinamento esplicito (una giornata piena di
    -- cicli pre-match puo' fare centinaia di righe: la RPC non deve crescere
    -- senza limite).
    SELECT coalesce(jsonb_agg(x.row ORDER BY x.placed_at DESC), '[]'::jsonb) INTO v_trades
      FROM (
        SELECT to_jsonb(t.*)
               || jsonb_build_object('day_placed_at', coalesce(p.placed_at, t.placed_at)) AS row,
               t.placed_at
          FROM public.mike_trades t
          LEFT JOIN public.mike_trades p ON p.id = t.closes_trade_id
         WHERE coalesce(p.placed_at, t.placed_at) >= v_day
            OR t.status IN ('pending','open','hedged')
         ORDER BY t.placed_at DESC
         LIMIT 500
      ) x;
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.ts DESC), '[]'::jsonb) INTO v_act
      FROM (SELECT * FROM public.mike_activity WHERE ts >= v_day ORDER BY ts DESC LIMIT 400) a;
    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb) INTO v_reqs
      FROM (SELECT * FROM public.mike_requests ORDER BY created_at DESC LIMIT 50) r;
    v_agg := public.mike_aggregates_sql();

    -- ARRETRATI DELLA PROVA (30/09): righe paper regolate OGGI (giorno di Roma)
    -- il cui ciclo e' di un giorno precedente. Si parte dalle gambe regolate
    -- oggi e si risale la catena closes_trade_id fino all'APERTURA (riga senza
    -- closes_trade_id); il giorno del ciclo e' quello di
    -- coalesce(ko_at della partita, placed_at dell'apertura). Live escluse.
    WITH RECURSIVE su AS (
        SELECT t.id AS leg_id, t.id AS cur_id, t.closes_trade_id AS next_id, 1 AS depth
          FROM public.mike_trades t
         WHERE t.mode = 'paper'
           AND t.settled_at >= v_day
           AND (t.settled_at AT TIME ZONE 'Europe/Rome')::date = v_oggi
        UNION ALL
        SELECT su.leg_id, p.id, p.closes_trade_id, su.depth + 1
          FROM su
          JOIN public.mike_trades p ON p.id = su.next_id
         WHERE su.depth < 20
    ), radice AS (
        SELECT su.leg_id, su.cur_id AS open_id FROM su WHERE su.next_id IS NULL
    )
    SELECT coalesce(jsonb_agg(z.riga ORDER BY z.settled_at DESC, z.id DESC), '[]'::jsonb) INTO v_arr
      FROM (
        SELECT t.id, t.settled_at,
               jsonb_build_object(
                   'bot',             'mike',
                   'mode',            'paper',
                   'id',              t.id,
                   'event_id',        t.event_id,
                   'event_name',      coalesce(t.event_name, e.event_name),
                   'ko_at',           e.ko_at,
                   'placed_at',       ap.placed_at,
                   'settled_at',      t.settled_at,
                   'status',          t.status,
                   'pnl',             t.pnl,
                   'closes_trade_id', t.closes_trade_id
               ) AS riga
          FROM radice r
          JOIN public.mike_trades t  ON t.id  = r.leg_id
          JOIN public.mike_trades ap ON ap.id = r.open_id
          LEFT JOIN public.mike_events e ON e.event_id = t.event_id
         WHERE (coalesce(e.ko_at, ap.placed_at) AT TIME ZONE 'Europe/Rome')::date < v_oggi
         ORDER BY t.settled_at DESC, t.id DESC
         LIMIT 2000
      ) z;

    RETURN jsonb_build_object('control', v_ctrl, 'events', v_events, 'trades', v_trades,
                              'activity', v_act, 'aggregates', v_agg, 'requests', v_reqs,
                              'day_start', v_day, 'day_by', 'placed',
                              'arretrati_prova', jsonb_build_object(
                                  'day', to_char(v_oggi, 'YYYY-MM-DD'),
                                  'righe', coalesce(v_arr, '[]'::jsonb)));
END;
$$;
REVOKE ALL    ON FUNCTION public.get_mike_state() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_mike_state() TO authenticated, service_role;

-- VERIFICA (facoltativa; devono rispondere, non sollevare; da un ruolo owner):
--   SELECT jsonb_object_keys(public.get_mike_state());
--     -- deve includere 'arretrati_prova' oltre alle 8 chiavi di prima
--   SELECT public.get_mike_state() -> 'arretrati_prova' ->> 'day';
--   SELECT jsonb_typeof(public.get_mike_state() -> 'arretrati_prova' -> 'righe');   -- 'array'
--   SELECT jsonb_array_length(public.get_mike_state() -> 'arretrati_prova' -> 'righe');
--
-- LE RIGHE DI OGGI (attese 5 righe paper del 26/09, eventi 36109477 e 36093027,
-- regolate 2026-09-30 12:41 UTC, P&L -5,00 -2,50 -6,40 -6,67 +2,28):
--   SELECT r ->> 'id' AS id, r ->> 'event_id' AS event_id, r ->> 'event_name' AS partita,
--          r ->> 'ko_at' AS ko_at, r ->> 'placed_at' AS aperta, r ->> 'settled_at' AS regolata,
--          r ->> 'status' AS status, (r ->> 'pnl')::numeric AS pnl, r ->> 'closes_trade_id' AS chiude
--     FROM jsonb_array_elements(public.get_mike_state() -> 'arretrati_prova' -> 'righe') r;
