-- ============================================================================
-- live_follow_record.sql — REGISTRAZIONE OPT-IN del live CALCIO (17/07).
--
-- REQUISITO: la registrazione raw + l'upload nel Match Replay NON devono
-- avvenire per tutte le partite (troppi giga). Il pulsante "Segui live" è lo
-- strumento di SCELTA:
--   record = true  → il runner scrive il raw nativo (tee) per intero e a fine
--                    partita carica gli snapshot nel Replay;
--   record = false → streaming, missioni, Trading, bot, ladder, ordini:
--                    TUTTO identico, ma NIENTE file raw e NIENTE upload.
--
-- Chi imposta record:
--   * flusso storico "Segui live" (personal_watchlist.follow_live=true →
--     runner Betfair/stream/db.register_follow): record=TRUE — è lo scopo
--     storico del pulsante (registra la partita per intero);
--   * omega_mission_follow (pulsante Trading / prerequisito scalper da /omega):
--     record=FALSE — il follow serve allo stream, non alla registrazione;
--   * set_follow_record (nuova RPC): toggle esplicito dal pulsante "Segui
--     live" accanto a "Trading" in /omega, anche A PARTITA IN CORSO (il
--     runner rilegge i follow periodicamente e inizia/smette da lì).
--
-- FALLBACK RUNNER: se questa migrazione NON è applicata, il runner rileva la
-- colonna assente e registra TUTTO (comportamento storico) con warning nel log.
--
-- IDEMPOTENTE. Richiede live_stream.sql + omega_missions.sql +
-- live_follows_watchlist_driven.sql + betfair_live_is_owner().
-- Stesso pattern di sicurezza delle altre migrazioni: SECURITY DEFINER,
-- search_path fisso, REVOKE ALL FROM public/anon, GRANT a authenticated +
-- service_role.
-- ============================================================================

-- 1) colonna flag (default false: NESSUNA partita registrata finché non scelta)
ALTER TABLE public.live_follow
    ADD COLUMN IF NOT EXISTS record BOOLEAN NOT NULL DEFAULT false;

-- runner e sweep filtrano le poche righe con record=true → indice parziale
CREATE INDEX IF NOT EXISTS idx_lf_record
    ON public.live_follow (record) WHERE record;

-- ----------------------------------------------------------------------------
-- 2) RPC set_follow_record — accende/spegne la REGISTRAZIONE su un follow
--    esistente (owner-only come le altre RPC live). Il toggle a partita in
--    corso è supportato: il runner risincronizza i follow a ogni ciclo.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_follow_record(
    p_event_id text,
    p_record   boolean
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.live_follow;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) = 0 OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF p_record IS NULL THEN
        RAISE EXCEPTION 'p_record obbligatorio (true/false)';
    END IF;

    UPDATE public.live_follow SET
        record     = p_record,
        updated_at = now()
    WHERE event_id = p_event_id
    RETURNING * INTO v_row;

    IF v_row.event_id IS NULL THEN
        RAISE EXCEPTION 'follow inesistente per event_id %: registra prima la partita (Segui live/Trading)', p_event_id;
    END IF;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.set_follow_record(text, boolean) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.set_follow_record(text, boolean) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3) omega_mission_follow — INVARIATO nella semantica (inserisce SOLO se
--    assente, mai tocca un follow esistente) ma il follow creato da missioni/
--    Trading NON registra: record=false ESPLICITO. La registrazione si accende
--    solo col pulsante "Segui live" (set_follow_record) o col flusso watchlist.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_mission_follow(
    p_event_id  text,
    p_home      text,
    p_away      text,
    p_open_date timestamptz
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_exists boolean;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_event_id IS NULL OR length(p_event_id) > 32 THEN
        RAISE EXCEPTION 'event_id non valido';
    END IF;
    IF coalesce(trim(p_home), '') = '' OR coalesce(trim(p_away), '') = '' THEN
        RAISE EXCEPTION 'home/away mancanti';
    END IF;
    IF p_open_date IS NULL THEN
        RAISE EXCEPTION 'open_date mancante';
    END IF;
    SELECT EXISTS (SELECT 1 FROM public.live_follow f WHERE f.event_id = p_event_id)
      INTO v_exists;
    IF NOT v_exists THEN
        -- record=false ESPLICITO (opt-in 17/07): il follow da missioni/Trading
        -- alimenta stream/bot/ladder ma NON la registrazione raw/Replay.
        INSERT INTO public.live_follow (event_id, home_name, away_name, open_date, status, record)
        VALUES (p_event_id, trim(p_home), trim(p_away), p_open_date, 'PENDING', false)
        ON CONFLICT (event_id) DO NOTHING;
    END IF;
    RETURN jsonb_build_object('event_id', p_event_id, 'followed', true,
                              'already', v_exists);
END;
$$;
REVOKE ALL    ON FUNCTION public.omega_mission_follow(text,text,text,timestamptz) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.omega_mission_follow(text,text,text,timestamptz) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4) get_omega_missions — aggiunge 'recording' (badge REC in /omega) accanto
--    al 'followed' esistente. Corpo IDENTICO a migrations/omega_missions.sql
--    salvo la riga 'recording'.
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
                            SELECT tr.phase,
                                   jsonb_build_object(
                                     'realized', coalesce(sum(tr.pnl) FILTER (WHERE tr.status IN ('won','lost','void')), 0),
                                     'open_liability', coalesce(sum(tr.liability) FILTER (WHERE tr.status = 'open' OR (tr.status='pending' AND tr.bet_id IS NOT NULL)), 0),
                                     'n_open', count(*) FILTER (WHERE tr.status = 'open' OR (tr.status='pending' AND tr.bet_id IS NOT NULL)),
                                     'n_settled', count(*) FILTER (WHERE tr.status IN ('won','lost','void')),
                                     'trades', coalesce(jsonb_agg(jsonb_build_object(
                                         'id', tr.id, 'runner_name', tr.runner_name, 'side', tr.side,
                                         'price', tr.price, 'size', tr.size, 'liability', tr.liability,
                                         'status', tr.status, 'pnl', tr.pnl, 'mode', tr.mode)
                                       ORDER BY tr.placed_at), '[]'::jsonb)
                                   ) AS agg
                              FROM public.omega_trades tr
                             WHERE tr.event_id = m.event_id AND tr.phase IS NOT NULL
                             GROUP BY tr.phase
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
                                         WHERE f.event_id = m.event_id),
                    -- opt-in 17/07: registrazione raw/Replay attiva su questa
                    -- partita? (badge REC nel pannello missioni)
                    'recording', EXISTS (SELECT 1 FROM public.live_follow f
                                          WHERE f.event_id = m.event_id AND f.record)
                  ) AS r
          FROM public.omega_missions m
         -- oggi + ATTIVE e IN PAUSA di giorni passati (audit H3c + review 16/07:
         -- una missione attiva o pausata di ieri era processata/riservata dal
         -- servizio ma INVISIBILE in UI → l'utente non poteva né riprenderla
         -- né chiuderla, e M7 teneva l'evento bloccato per sempre)
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
REVOKE ALL    ON FUNCTION public.get_omega_missions() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_missions() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 5) get_live_follows — espone 'record' (badge/chip REC nella pagina Segui
--    Live) e — FIX CRITICAL review 17/07 — include ANCHE i follow SENZA riga
--    watchlist (i follow creati da Omega/"Trading": omega_mission_follow non
--    scrive fixture_id né personal_watchlist → con la versione solo
--    watchlist-driven quelle partite NON comparivano MAI in /segui-live e la
--    pagina restava per sempre su "In attesa dello stream…" anche a stream
--    agganciato in pochi secondi. Era la vera causa del "Trading non parte").
--    Parte watchlist: corpo identico a live_follows_watchlist_driven.sql
--    (+ chiave 'record'); parte due: UNION dei live_follow orfani di watchlist.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_live_follows()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rows jsonb;
BEGIN
    SELECT coalesce(jsonb_agg(r ORDER BY od), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT DISTINCT ON (w.fixture_id)
               jsonb_build_object(
                 'event_id',     f.event_id,
                 'fixture_id',   w.fixture_id,
                 'league_name',  coalesce(f.league_name, w.league_name),
                 'home_name',    coalesce(f.home_name, w.home_team),
                 'away_name',    coalesce(f.away_name, w.away_team),
                 'open_date',    coalesce(f.open_date, w.kickoff),
                 'status',       coalesce(f.status, 'IN_ATTESA'),
                 'error_detail', f.error_detail,
                 'record',       coalesce(f.record, false),
                 'inplay',       n.inplay,
                 'minute',       n.minute,
                 'score_home',   n.score_home,
                 'score_away',   n.score_away,
                 'live_status',  n.status,
                 'score_source', n.score_source,
                 'updated_at',   n.updated_at
               ) AS r,
               coalesce(f.open_date, w.kickoff) AS od
          FROM public.personal_watchlist w
          LEFT JOIN public.live_follow f ON f.fixture_id = w.fixture_id
          LEFT JOIN public.live_now   n ON n.event_id   = f.event_id
         WHERE w.follow_live = true
           AND w.kickoff >= now() - interval '12 hours'
           AND coalesce(f.status, '') <> 'UPLOADED'
         ORDER BY w.fixture_id, f.updated_at DESC NULLS LAST
      ) s;

    -- follow ORFANI di watchlist (Omega/"Trading"): stessa shape, stessa
    -- finestra temporale, mai gli UPLOADED. fixture_id/league possono essere
    -- NULL: il frontend è già difensivo su quei campi.
    SELECT v_rows || coalesce(jsonb_agg(r ORDER BY od), '[]'::jsonb)
      INTO v_rows
      FROM (
        SELECT jsonb_build_object(
                 'event_id',     f.event_id,
                 'fixture_id',   f.fixture_id,
                 'league_name',  f.league_name,
                 'home_name',    f.home_name,
                 'away_name',    f.away_name,
                 'open_date',    f.open_date,
                 'status',       f.status,
                 'error_detail', f.error_detail,
                 'record',       coalesce(f.record, false),
                 'inplay',       n.inplay,
                 'minute',       n.minute,
                 'score_home',   n.score_home,
                 'score_away',   n.score_away,
                 'live_status',  n.status,
                 'score_source', n.score_source,
                 'updated_at',   n.updated_at
               ) AS r,
               f.open_date AS od
          FROM public.live_follow f
          LEFT JOIN public.live_now n ON n.event_id = f.event_id
         WHERE f.status <> 'UPLOADED'
           AND coalesce(f.open_date, now()) >= now() - interval '12 hours'
           AND NOT EXISTS (
                 SELECT 1 FROM public.personal_watchlist w
                  WHERE w.fixture_id = f.fixture_id
                    AND w.follow_live = true
                    AND w.kickoff >= now() - interval '12 hours')
      ) s;

    RETURN jsonb_build_object('rows', v_rows);
END;
$$;
-- (i GRANT esistenti su get_live_follows restano validi: CREATE OR REPLACE non li tocca)
