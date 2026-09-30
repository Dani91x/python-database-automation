-- ============================================================================
-- tennis_paper_voided_residuo_zero_2026-09-30.sql  (SOLO DATI, IDEMPOTENTE)
-- ============================================================================
-- PERCHE' (30/09): in Control Room, "Posizioni aperte", compariva
--   "Swing - paper - 14:41 - 36117569 - LAY - 1,21 - residuo 2,00".
-- E' la riga 46018 di `tennis_live_orders`: ordine PAPER mai abbinato di un
-- follow CLOSED dal 28/09. All'avvio dell'app (14:41) la ripresa del runner
-- tennis (`Betfair/stream/tennis_live/tennis_db.py`, `chiudi_specchio_paper_orfano`)
-- l'ha chiusa scrivendo `status = 'VOIDED'` e `updated_at = now()`, ma ha
-- lasciato `size_remaining = 2`. Con `placed_at` nullo la RPC
-- `get_tennis_bot_orders_today` la considera "di oggi" (coalesce(placed_at,
-- updated_at)) e la vista la contava aperta perche' il residuo era > 0.
--
-- La correzione VERA e' nel frontend (`residuoTennisSulBook`, lib/controlRoom.ts:
-- il residuo di un ordine in stato terminale non e' sul book) e vale dopo
-- `npm run build` + ricarica dell'app. Questa migrazione e' FACOLTATIVA: toglie
-- la riga SUBITO, senza ricostruire il frontend, e rende coerenti con Betfair
-- (un ordine annullato ha residuo 0 e la quota annullata in `size_voided`) le
-- righe paper gia' chiuse dalla ripresa (35 al 30/09, tutte VOIDED, mai
-- abbinate: 26/09 e 30/09).
--
-- COSA TOCCA: solo righe PAPER dei 4 bot tennis, gia' VOIDED, non regolate,
-- con residuo > 0. Mai righe LIVE, mai righe abbinate o regolate, nessuna
-- riga cancellata. Rilanciata una seconda volta non trova nulla (residuo 0).
--
-- Da applicare a cura dell'utente (SQL editor di Supabase).
-- ============================================================================

-- ANTEPRIMA (facoltativa): le righe che verranno toccate.
-- SELECT id, source, event_id, status, size, size_matched, size_remaining,
--        size_voided, placed_at, updated_at
--   FROM public.tennis_live_orders
--  WHERE mode = 'paper'
--    AND source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
--    AND status = 'VOIDED'
--    AND settled_at IS NULL
--    AND coalesce(size_matched, 0) = 0
--    AND size_remaining > 0
--  ORDER BY id;

UPDATE public.tennis_live_orders
   SET size_voided    = coalesce(size_voided, 0) + size_remaining,
       size_remaining = 0
 WHERE mode = 'paper'
   AND source IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')
   AND status = 'VOIDED'
   AND settled_at IS NULL
   AND coalesce(size_matched, 0) = 0
   AND size_remaining > 0;
