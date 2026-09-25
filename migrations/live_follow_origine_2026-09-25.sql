-- ============================================================================
-- live_follow_origine_2026-09-25.sql - AUTO-FOLLOW del runner calcio (25/09).
--
-- Ordine dell'utente: i bot armati operano su TUTTE le partite idonee da soli,
-- senza il clic "Segui live". Il runner calcio (Betfair/stream/auto_follow.py)
-- segue da solo i mercati su cui i bot mandano ordini (aggancio al volo) e le
-- partite del feed quando un bot calcio e' collegato al canale di comando.
-- Ogni evento seguito da solo ha la sua riga live_follow con origine='auto'
-- (status STREAMING mentre e' seguito, CLOSED quando esce): il Terminale
-- (/segui-live) mostra l'origine.
--
--   1. colonna live_follow.origine ('manuale' | 'auto', default 'manuale'):
--      tutte le righe esistenti e tutti i flussi di sempre (watchlist, "Segui
--      live", Trading/Omega, scalper) restano 'manuale' senza toccarli;
--   2. get_live_follows: STESSO corpo di live_follow_record.sql + la chiave
--      'origine' nelle due parti (watchlist e follow orfani).
--
-- Il runner NON scrive righe automatiche finche' questa migrazione non e'
-- applicata (sonda della colonna, auto_follow.FollowDb.verifica_colonna): senza
-- colonna l'auto-follow lavora solo in RAM e lo dichiara nello stato.
-- Il runner non riscrive MAI un follow dell'utente: insert ignore_duplicates e
-- update solo WHERE origine = 'auto'.
--
-- IDEMPOTENTE. Richiede live_stream.sql + live_follow_record.sql. Nessun
-- DELETE/DROP; GRANT invariati (CREATE OR REPLACE non li tocca).
-- ============================================================================

-- 1) colonna origine
ALTER TABLE public.live_follow
    ADD COLUMN IF NOT EXISTS origine TEXT NOT NULL DEFAULT 'manuale';

DO $mig$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'live_follow_origine_check'
           AND conrelid = 'public.live_follow'::regclass
    ) THEN
        ALTER TABLE public.live_follow
            ADD CONSTRAINT live_follow_origine_check
            CHECK (origine IN ('manuale', 'auto'));
    END IF;
END
$mig$;

-- il runner chiude all'avvio le righe automatiche rimaste aperte
CREATE INDEX IF NOT EXISTS idx_lf_origine_auto
    ON public.live_follow (status) WHERE origine = 'auto';

-- 2) get_live_follows con 'origine' (corpo di live_follow_record.sql)
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
                 'origine',      coalesce(f.origine, 'manuale'),
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
                 'origine',      coalesce(f.origine, 'manuale'),
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
