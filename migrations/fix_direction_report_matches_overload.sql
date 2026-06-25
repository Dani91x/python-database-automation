-- ============================================================================
-- fix_direction_report_matches_overload.sql
-- ----------------------------------------------------------------------------
-- FIX money-critical: il drill "partite" del report Reportistiche -> Direzioni
-- (frontend fetchDirMatches) chiamava get_direction_report_matches SENZA
-- p_commission, ma in DB esistevano DUE overload che combaciavano con quella
-- chiamata:
--   (date,date,bigint,text,boolean,boolean,integer,integer)            <- ORFANO
--   (date,date,bigint,text,boolean,boolean,numeric,integer,integer)    <- attuale
-- PostgREST non sapeva scegliere -> errore PGRST203
--   "Could not choose the best candidate function" -> il drill restava ROTTO.
--
-- Rimuove l'overload ORFANO (quello senza p_commission), lasciando solo la
-- versione corrente: la chiamata del client si risolve senza ambiguita'.
-- Idempotente (DROP IF EXISTS). Non tocca le funzioni in uso.
-- ============================================================================
drop function if exists
    public.get_direction_report_matches(date,date,bigint,text,boolean,boolean,integer,integer);
