-- ============================================================================
-- tennis_follow_record.sql — registrazione OPT-IN per-partita del tennis.
--
-- REQUISITO UTENTE (17/07): come per il calcio, la registrazione del raw nativo
-- di un match tennis dev'essere una SCELTA per-partita, non un default globale.
-- Colonna `record` su tennis_live_follow (default false = comportamento storico:
-- il runner tennis NON registra nulla) + RPC owner-only per il toggle dalla UI.
--
-- Il runner tennis (tennis_live/tennis_runner + tennis_live/tennis_recorder)
-- rilegge il flag periodicamente: il toggle A META' PARTITA funziona (il tee
-- parte/si ferma senza riavviare lo stream). Se questa migrazione NON è
-- applicata il runner degrada in modo conservativo: nessuna registrazione,
-- warning nel log — mai un crash.
--
-- Convenzioni: identiche alle migrazioni tennis esistenti (tennis_live.sql,
-- tennis_bots.sql): schema public, RLS già attiva sulla tabella, RPC SECURITY
-- DEFINER con guard `public.tennis_is_owner()` (definita in tennis_orders.sql /
-- tennis_bots.sql — risolta a CALL time, quindi l'ordine di applicazione non è
-- vincolante), REVOKE da public/anon, GRANT a authenticated/service_role.
-- Tutto IDEMPOTENTE.
-- ============================================================================

------------------------------------------------------------------------------
-- 1) Colonna opt-in: false = NON registrare (default storico del tennis).
------------------------------------------------------------------------------
ALTER TABLE public.tennis_live_follow
    ADD COLUMN IF NOT EXISTS record BOOLEAN NOT NULL DEFAULT false;

------------------------------------------------------------------------------
-- 2) RPC owner-only: tennis_set_follow_record(p_event_id, p_record) -> json
--    Imposta il flag di registrazione di UN evento seguito. Ritorna lo stato
--    aggiornato { event_id, record, status, updated_at }.
------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tennis_set_follow_record(
    p_event_id text,
    p_record   boolean
)
RETURNS json
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.tennis_live_follow;
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'accesso negato';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 64 THEN
        RAISE EXCEPTION 'p_event_id non valido';
    END IF;
    IF p_record IS NULL THEN
        RAISE EXCEPTION 'p_record non valido';
    END IF;

    UPDATE public.tennis_live_follow
       SET record     = p_record,
           updated_at = now()
     WHERE event_id = p_event_id
    RETURNING * INTO v_row;

    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'evento % non seguito (segui prima il match)', p_event_id;
    END IF;

    RETURN json_build_object(
        'event_id',   v_row.event_id,
        'record',     v_row.record,
        'status',     v_row.status,
        'updated_at', v_row.updated_at
    );
END;
$$;

REVOKE ALL    ON FUNCTION public.tennis_set_follow_record(text, boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.tennis_set_follow_record(text, boolean) TO authenticated, service_role;

------------------------------------------------------------------------------
-- 3) get_tennis_follows() — ricreata IDENTICA a tennis_live.sql + campo `record`
--    (la UI mostra lo stato REC per-partita). Self-contained: la colonna è
--    aggiunta al punto 1 di questo stesso file.
------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tennis_follows()
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows json;
BEGIN
    SELECT coalesce(json_agg(r ORDER BY (r->>'open_date')), '[]'::json)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',         f.event_id,
                 'competition_name', f.competition_name,
                 'player1_name',     f.player1_name,
                 'player2_name',     f.player2_name,
                 'open_date',        f.open_date,
                 'status',           f.status,
                 'error_detail',     f.error_detail,
                 'record',           f.record,
                 'inplay',           coalesce(n.inplay, f.inplay),
                 'score',            coalesce(n.score, f.score),
                 'live_status',      coalesce(n.status, f.live_status),
                 'updated_at',       coalesce(n.updated_at, f.updated_at)
               ) AS r
          FROM public.tennis_live_follow f
          LEFT JOIN public.tennis_live_now n ON n.event_id = f.event_id
         WHERE f.status IN ('PENDING','STREAMING','CLOSED')
      ) s;

    RETURN json_build_object('rows', v_rows);
END;
$$;

REVOKE ALL    ON FUNCTION public.get_tennis_follows() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_tennis_follows() TO authenticated, service_role;
