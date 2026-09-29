-- ============================================================================
-- 29/09/2026 - MIKE: RIENTRO SULL'UNDER 4,5 CON 1 O 2 GOL (piano Mike M6.1)
-- ============================================================================
-- Decisione 20 dell'utente: il rientro si fa con 1 o 2 gol (prima esattamente
-- 1). Nel codice il valore di serie di `reentry_max_goals` passa da 1 a 2 e il
-- limite massimo da 1 a 2 (Betfair/mike/config.py). Il valore SALVATO in
-- mike_control.params vince sul valore di serie: se vale ancora 1 (il vecchio
-- default, che la UI salvava insieme agli altri parametri) si porta a 2.
-- Un valore diverso da 1 (scelto dall'utente) NON si tocca.
-- SOLO DATI, IDEMPOTENTE. La applica l'utente.
-- ============================================================================

BEGIN;

UPDATE public.mike_control
   SET params = jsonb_set(params, '{reentry_max_goals}', '2'::jsonb)
 WHERE id = 1
   AND params ? 'reentry_max_goals'
   AND (params->>'reentry_max_goals') IN ('1', '1.0');

COMMIT;

-- Verifica (sola lettura):
--   SELECT params->'reentry_max_goals' FROM public.mike_control WHERE id = 1;
