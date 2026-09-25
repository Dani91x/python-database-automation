-- ============================================================================
-- get_direction_eta_2026-09-25.sql  (ADDITIVA: solo funzioni NUOVE)
-- ============================================================================
-- Reperto R5 dell'audit tab Dashboard (AUDIT_2026-09-24/AUDIT_TAB_DASHBOARD_2026-09-24.md):
-- nessuna tab dichiarava l'ETA' del dato MATERIALIZZATO che usa. Il trader deve
-- vedere a colpo d'occhio se sta guardando un dato di oggi o di una settimana fa.
--
-- NON tocca migrations/get_direction_rpc.sql ne' la funzione get_direction: si
-- aggiungono due funzioni NUOVE, di sola lettura, chiamate dal frontend accanto
-- a quelle esistenti. Se non sono ancora applicate il frontend lo dice ("eta'
-- non disponibile") e il resto del pannello funziona come prima.
--
-- 1. get_direction_eta(p_fixture_id) -> jsonb
--      pagella_generated_at : max(direction_pagella.generated_at) delle righe
--                             engine='poisson' (le SOLE che get_direction legge
--                             per l'affidabilita', get_direction_rpc.sql:175-180)
--      quota_righe          : righe di analytics_bets per la partita
--      quota_con_prezzo     : di queste, quante hanno una quota
--                             (coalesce(odds_betfair, odds_book), come get_direction:165)
--      quota_eta            : SEMPRE null. analytics_bets NON ha una colonna di
--                             tempo (analytics_strategy.sql:85-129): l'eta' della
--                             quota non e' misurabile, se ne dichiara solo la
--                             presenza. Aggiungere un timestamp e' una modifica di
--                             schema fuori perimetro (va decisa a parte).
--      now                  : ora del server (riferimento per l'eta').
-- 2. get_poisson_calibration_eta(p_league_id) -> jsonb
--      data della calibrazione Poisson SETTIMANALE (poisson_calibration.generated_at)
--      con la stessa catena del calibratore (poisson_calibrator.py): riga della lega,
--      altrimenti la globale (league_id = 0). scope = 'lega' | 'globale' | null.
--      Via RPC SECURITY DEFINER perche' dal 24/09 (sicurezza_db BLOCCO 2) le tabelle
--      di calibrazione non sono garantite leggibili dal client con .from().
--
-- Sicurezza: SECURITY DEFINER, STABLE, search_path fissato, input validati,
-- EXECUTE solo ad authenticated e service_role (come get_direction).
-- Idempotente: CREATE OR REPLACE. La applica l'utente dal SQL Editor.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_direction_eta(p_fixture_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
SET statement_timeout = '10s'
AS $$
DECLARE
  v_pagella   timestamptz;
  v_righe     int;
  v_con_quota int;
BEGIN
  IF p_fixture_id IS NULL THEN
    RAISE EXCEPTION 'p_fixture_id nullo';
  END IF;

  SELECT max(pg.generated_at) INTO v_pagella
    FROM public.direction_pagella pg
   WHERE pg.engine = 'poisson';

  SELECT count(*)::int,
         (count(*) FILTER (WHERE coalesce(ab.odds_betfair, ab.odds_book) IS NOT NULL))::int
    INTO v_righe, v_con_quota
    FROM public.analytics_bets ab
   WHERE ab.fixture_id = p_fixture_id;

  RETURN jsonb_build_object(
    'fixture_id',           p_fixture_id,
    'pagella_generated_at', v_pagella,
    'quota_righe',          coalesce(v_righe, 0),
    'quota_con_prezzo',     coalesce(v_con_quota, 0),
    'quota_eta',            NULL,
    'now',                  now()
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.get_poisson_calibration_eta(p_league_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
SET statement_timeout = '10s'
AS $$
DECLARE
  v_lega    timestamptz;
  v_globale timestamptz;
BEGIN
  IF p_league_id IS NOT NULL AND p_league_id > 0 THEN
    SELECT pc.generated_at INTO v_lega
      FROM public.poisson_calibration pc WHERE pc.league_id = p_league_id;
  END IF;
  SELECT pc.generated_at INTO v_globale
    FROM public.poisson_calibration pc WHERE pc.league_id = 0;

  RETURN jsonb_build_object(
    'league_id',    p_league_id,
    'scope',        CASE WHEN v_lega IS NOT NULL THEN 'lega'
                         WHEN v_globale IS NOT NULL THEN 'globale' END,
    'generated_at', coalesce(v_lega, v_globale),
    'now',          now()
  );
END;
$$;

REVOKE ALL ON FUNCTION public.get_direction_eta(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_direction_eta(bigint) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.get_poisson_calibration_eta(bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.get_poisson_calibration_eta(bigint) TO authenticated, service_role;
