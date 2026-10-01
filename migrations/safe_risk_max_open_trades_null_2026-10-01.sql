-- ============================================================================
-- SAFE — il tetto globale di posizioni aperte torna a quello del bot (R-06, 01/10)
-- ============================================================================
-- DIFETTO: il foglio parametri di Safe scriveva `params.risk.max_open_trades = 0`
-- quando la chiave era assente. Nel servizio (Betfair/safe_strategy/risk.py:203)
-- 0 = NESSUN tetto globale; chiave assente/NULL = vale `params.max_open_trades`
-- del bot (sul DB: 20). Verificato in sola lettura il 01/10: risk.max_open_trades = 0,
-- params.max_open_trades = 20. Il foglio e' corretto a parte (frontend).
-- EFFETTO: toglie la chiave dalla sezione risk (il servizio ripiega sul tetto del
-- bot alla prossima lettura dei parametri). Nessun'altra chiave toccata. Idempotente.
-- VERIFICA dopo: SELECT params->'risk'->'max_open_trades' FROM public.safe_strategy_control WHERE id = 1;
--   atteso: NULL (nessuna riga/valore). E: SELECT params->>'max_open_trades' ... → 20
UPDATE public.safe_strategy_control
   SET params = jsonb_set(params, '{risk}', (params->'risk') - 'max_open_trades')
 WHERE id = 1
   AND params ? 'risk'
   AND (params->'risk') ? 'max_open_trades'
   AND (params->'risk'->>'max_open_trades') = '0';
