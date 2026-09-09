-- ============================================================================
-- OMEGA v2 (09/09/2026 sera): due gambe per partita (HT-CS nel 1T + CS nel 2T)
-- Applicare DOPO omega_bot.sql, omega_manual.sql, omega_missions.sql.
--   1) l'unique dell'automatico passa da "un trade per evento" a "un trade per
--      evento E gamba" (i trade v1 senza gamba restano unici per evento);
--   2) get_omega_missions espone per ogni trade minuto/punteggio all'ingresso,
--      orario e origine (UI live delle missioni).
-- ============================================================================
DROP INDEX IF EXISTS public.uq_omega_trades_auto_event;
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_trades_auto_leg
    ON public.omega_trades (event_id, coalesce(phase, ''))
    WHERE origin = 'auto';

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
                                         'status', tr.status, 'pnl', tr.pnl, 'mode', tr.mode,
                                         'minute_at_entry', tr.minute_at_entry, 'score_at_entry', tr.score_at_entry,
                                         'placed_at', tr.placed_at, 'origin', tr.origin)
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
                                         WHERE f.event_id = m.event_id)
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
