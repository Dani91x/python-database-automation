-- ============================================================================
-- betfair_live_orders_source_bot_2026-09-26.sql
--
-- 26/09 (riavvio 2, reperto R9 / R-F2-16): regola dell'utente del 25/09
-- "gli ordini sono flaggati col nome del bot". Il motore ordini scrive nello
-- specchio ``betfair_live_orders.source`` = attore del comando ('omega',
-- 'safe', 'mike', ...) invece del DEFAULT 'runner' (che resta per il manuale
-- dell'app e per l'attore del desktop).
--
-- Il CHECK di oggi (scalper_auto_mode_2026-09-25.sql, sezione 7) ammette
-- ('runner', 'account', 'scalper'). Finche' questa migrazione NON e' applicata
-- il runner riscrive la riga SENZA source (db._upsert_specchio): nessuna riga
-- dello specchio si perde, resta solo l'etichetta 'runner' di prima.
--
-- Stessa regola della sezione 7 dello scalper: se il CHECK ESISTE lo si
-- ricrea con i nomi dei bot in piu' e NIENT'ALTRO; NOT VALID = le righe gia'
-- scritte non si ricontrollano. Se NON esiste non lo si reintroduce.
-- IDEMPOTENTE. Nessun dato toccato.
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'betfair_live_orders_source_check'
           AND conrelid = 'public.betfair_live_orders'::regclass
    ) THEN
        ALTER TABLE public.betfair_live_orders
            DROP CONSTRAINT betfair_live_orders_source_check;
        ALTER TABLE public.betfair_live_orders
            ADD CONSTRAINT betfair_live_orders_source_check
            CHECK (source IN ('runner', 'account', 'scalper',
                              'omega', 'safe', 'mike', 'safe_tennis',
                              'tennis_scalper', 'tennis_pro', 'tennis_flb',
                              'tennis_swing')) NOT VALID;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- VERIFICA (sola lettura, dopo l'applicazione)
--   SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'betfair_live_orders_source_check';
--   SELECT source, mode, count(*) FROM public.betfair_live_orders
--    WHERE updated_at::date = current_date GROUP BY 1, 2;
-- ----------------------------------------------------------------------------
