-- ============================================================================
-- live_follow_league_id.sql — aggiunge league_id a live_follow (per i loghi lega
-- nel selettore Match Replay, come in dashboard: media.api-sports.io/.../leagues/{id}.png).
-- Idempotente.
-- ============================================================================
ALTER TABLE public.live_follow ADD COLUMN IF NOT EXISTS league_id BIGINT;
