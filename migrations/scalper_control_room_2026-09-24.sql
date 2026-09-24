-- ============================================================================
-- scalper_control_room_2026-09-24.sql - LO SCALPER CALCIO IN CONTROL ROOM.
--
-- Decisione dell'utente (24/09): "lo scalper deve essere in Control Room come
-- tutti gli altri bot". Lo scalper si arma PER PARTITA (una riga per evento in
-- `scalper_control`, migrations/scalper_bot.sql): la Control Room non ha una
-- lettura di TUTTE le sessioni (get_scalper_state vuole un event_id) ne' uno
-- stop con guardia d'identita'. Questa migrazione aggiunge SOLO quelle due
-- cose, piu' un indice:
--
--   1. get_scalper_control_room()  - LETTURA owner-only: le sessioni vive o
--      toccate oggi (giorno di Roma) con partita e kickoff (live_follow),
--      l'ultima attivita' (scalper_activity) e gli ordini dello specchio della
--      sessione (betfair_live_orders) delle stesse partite, con il P&L reale
--      di Betfair per bet_id (colonne di pnl_betfair_reale_2026-09-24.sql).
--   2. scalper_stop_sessione(event, requested_at, mode) - lo STOP di UNA
--      sessione (force-flat + attesa flat: e' lo stesso 'stopping' che
--      scalper_stop scrive e che la sessione legge ogni 5 s,
--      scalper_session.py: `status in ("stopping","stopped","error")`), con la
--      GUARDIA D'IDENTITA': la sessione deve essere QUELLA vista dalla pagina
--      (stesso requested_at, stessa modalita'); altrimenti
--      'richiesta_ambigua' e niente viene scritto.
--   3. idx_blo_event su betfair_live_orders(event_id): la lettura filtra per
--      partita, e la tabella non aveva un indice per evento.
--
-- NIENTE di esistente cambia: scalper_activate / scalper_stop /
-- get_scalper_state restano identiche, il servizio non si tocca, nessuna
-- colonna nuova, nessun dato alterato.
--
-- QUALI ORDINI SONO DELLO SCALPER. Lo specchio della sessione
-- (scalper_session._make_session_mirror) scrive su betfair_live_orders con la
-- `source` di default ('runner') e con il customer_order_ref di flumine come
-- client_order_ref. Il terminale manuale dell'app usa invece `awlq<id>`, la
-- riconciliazione del conto `ext<bet_id>` con source 'account' o 'bot:<ref>'.
-- Quindi: ordine dello scalper = partita con una riga scalper_control, source
-- 'runner' o 'scalper', ref che NON comincia per 'awlq' ne' per 'ext'.
-- Le righe 'bot:<ref>' (ordini di un bot visti SOLO sul conto) restano fuori:
-- non sappiamo di quale bot sono.
--
-- IDEMPOTENTE. Da applicare a cura dell'utente (SQL editor di Supabase).
-- Richiede public.betfair_live_is_owner() (security_lockdown.sql) e le colonne
-- pnl_betfair* (pnl_betfair_reale_2026-09-24.sql): applicare DOPO quella.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3. indice per partita (additivo)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_blo_event
    ON public.betfair_live_orders (event_id);

-- ----------------------------------------------------------------------------
-- 1. LETTURA: sessioni + ordini dello scalper, per la Control Room.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_scalper_control_room(
    p_orders_limit integer DEFAULT 2000
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_oggi     date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_sessioni jsonb;
    v_ordini   jsonb;
    v_eventi   text[];
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- le sessioni: vive (qualunque giorno) o toccate OGGI (giorno di Roma)
    SELECT coalesce(array_agg(c.event_id), ARRAY[]::text[])
      INTO v_eventi
      FROM public.scalper_control c
     WHERE c.status IN ('requested','arming','armed','running','stopping')
        OR (c.updated_at   AT TIME ZONE 'Europe/Rome')::date = v_oggi
        OR (c.requested_at AT TIME ZONE 'Europe/Rome')::date = v_oggi;

    SELECT coalesce(jsonb_agg(
               to_jsonb(c.*)
               || jsonb_build_object(
                    'event_name', CASE WHEN f.event_id IS NULL THEN NULL
                                       ELSE f.home_name || ' v ' || f.away_name END,
                    'league_name', f.league_name,
                    'kickoff', f.open_date,
                    'ultima_attivita_at', a.ts,
                    'ultima_attivita_kind', a.kind)
               ORDER BY c.requested_at DESC), '[]'::jsonb)
      INTO v_sessioni
      FROM public.scalper_control c
      LEFT JOIN public.live_follow f ON f.event_id = c.event_id
      LEFT JOIN LATERAL (
            SELECT x.ts, x.kind
              FROM public.scalper_activity x
             WHERE x.event_id = c.event_id
             ORDER BY x.ts DESC
             LIMIT 1
      ) a ON TRUE
     WHERE c.event_id = ANY (v_eventi);

    SELECT coalesce(jsonb_agg(to_jsonb(o.*) ORDER BY o.id), '[]'::jsonb)
      INTO v_ordini
      FROM (
        SELECT b.id, b.bet_id, b.client_order_ref, b.mode, b.event_id,
               b.market_id, b.selection_id, b.side, b.order_type, b.price,
               b.size, b.size_matched, b.size_remaining, b.size_cancelled,
               b.size_lapsed, b.size_voided, b.average_price_matched,
               b.status, b.placed_at, b.matched_at, b.updated_at, b.source,
               b.pnl_betfair, b.commissione_betfair, b.pnl_betfair_settled_at
          FROM public.betfair_live_orders b
         WHERE b.event_id = ANY (v_eventi)
           AND coalesce(b.source, 'runner') IN ('runner', 'scalper')
           AND b.client_order_ref NOT LIKE 'awlq%'
           AND b.client_order_ref NOT LIKE 'ext%'
           AND (
                 (coalesce(b.placed_at, b.updated_at) AT TIME ZONE 'Europe/Rome')::date = v_oggi
              OR (b.pnl_betfair_settled_at AT TIME ZONE 'Europe/Rome')::date = v_oggi
              OR b.status IN ('PENDING', 'EXECUTABLE')
           )
         ORDER BY b.id DESC
         LIMIT least(greatest(coalesce(p_orders_limit, 2000), 1), 5000)
      ) o;

    RETURN jsonb_build_object(
        'sessions', v_sessioni,
        'orders', v_ordini,
        'giorno', v_oggi,
        'letto_at', now());
END;
$$;
REVOKE ALL    ON FUNCTION public.get_scalper_control_room(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_scalper_control_room(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 2. STOP DI UNA SESSIONE con guardia d'identita'.
--    Stesse transizioni di scalper_stop: running/arming/armed -> 'stopping'
--    (la sessione fa force-flat, aspetta il flat fino a 30 s e scrive
--    'stopped'); requested -> 'stopped' (nessun processo ancora partito).
--    Rifiuta ('richiesta_ambigua') se la riga non e' la sessione vista dalla
--    pagina: requested_at diverso (riarmata nel frattempo) o modalita'
--    diversa (paper e live mai mischiati). Rifiuta anche una sessione gia'
--    ferma: non si "chiude" cio' che non opera.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.scalper_stop_sessione(
    p_event_id     text,
    p_requested_at timestamptz,
    p_mode         text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row  public.scalper_control;
    v_mode text := lower(nullif(p_mode, ''));
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_requested_at IS NULL THEN
        RAISE EXCEPTION 'richiesta_ambigua: manca la firma della sessione (requested_at)';
    END IF;
    IF v_mode IS NULL OR v_mode NOT IN ('paper', 'live') THEN
        RAISE EXCEPTION 'richiesta_ambigua: modalita'' non dichiarata (paper|live)';
    END IF;

    SELECT * INTO v_row FROM public.scalper_control
     WHERE event_id = p_event_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta_ambigua: nessuna sessione scalper per %', p_event_id;
    END IF;
    IF v_row.requested_at <> p_requested_at THEN
        RAISE EXCEPTION 'richiesta_ambigua: la sessione di % e'' stata riarmata (% invece di %)',
            p_event_id, v_row.requested_at, p_requested_at;
    END IF;
    IF (CASE WHEN v_row.dry_run THEN 'paper' ELSE 'live' END) <> v_mode THEN
        RAISE EXCEPTION 'richiesta_ambigua: la sessione di % e'' in % e la richiesta dice %',
            p_event_id, CASE WHEN v_row.dry_run THEN 'paper' ELSE 'live' END, v_mode;
    END IF;
    IF v_row.status NOT IN ('requested', 'arming', 'armed', 'running') THEN
        RAISE EXCEPTION 'sessione non attiva (%): niente da fermare', v_row.status;
    END IF;

    UPDATE public.scalper_control
       SET status = CASE WHEN status IN ('running', 'arming', 'armed')
                         THEN 'stopping' ELSE 'stopped' END,
           stopped_at = CASE WHEN status = 'requested' THEN now() ELSE stopped_at END,
           updated_at = now()
     WHERE event_id = p_event_id
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.scalper_stop_sessione(text, timestamptz, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.scalper_stop_sessione(text, timestamptz, text) TO authenticated, service_role;
