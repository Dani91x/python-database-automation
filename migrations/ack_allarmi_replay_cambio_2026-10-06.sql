-- ack_allarmi_replay_cambio_2026-10-06.sql
--
-- Segna come LETTI gli allarmi CAMBIO_GBP_EUR scritti dai REPLAY dello Scalper
-- lanciati sul PC (difetto del banco, corretto il 06/10 in
-- `Betfair/stream/scalper/tools/replay_registrazioni.py::_iniezioni`): il
-- replay passava alla sessione il Betfair FINTO del banco (`_TradingFinto`,
-- senza `account`), la lettura del cambio falliva e `valuta.py` scriveva
-- l'allarme nel DB vero. Il bot vero non c'entra.
--
-- Tocca SOLO gli allarmi il cui testo nomina `_TradingFinto` (un processo vero
-- non ha mai quel client): un allarme del cambio di un processo VERO resta
-- com'e'. Non cancella niente (lo storico resta), mette solo acknowledged.
-- Idempotente. La applica l'utente.

UPDATE public.live_alerts
   SET acknowledged = true
 WHERE code = 'CAMBIO_GBP_EUR'
   AND acknowledged = false
   AND position('_TradingFinto' in message) > 0;
