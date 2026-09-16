-- ============================================================================
-- CONSAPEVOLEZZA DELL'ORDINE — colonne mancanti sulle tre tabelle di trade
-- (C.12a del PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md; reperto della
--  MATRICE_CONSAPEVOLEZZA_ORDINI_2026-09-16.md §0 e §8c)
--
-- DA APPLICARE A MANO DALL'UTENTE. Nessun agente la applica.
--
-- IL PROBLEMA, in una riga: `omega_trades`, `safe_strategy_trades` e
-- `mike_trades` non hanno MAI avuto una colonna per il CHIESTO, il RESIDUO, il
-- PREZZO MEDIO ABBINATO e l'ULTIMO AGGIORNAMENTO DA BETFAIR. Alla conferma
-- `size` e `price` vengono SOVRASCRITTI con l'abbinato reale
-- (omega_service.py:1439 · safe_strategy/execution.py:426-428 ·
--  mike/service.py:620): il numero che il bot aveva chiesto sparisce, e con lui
-- la risposta alla domanda dell'utente del 16/09 — «ordine x a prezzo y: e'
-- stato abbinato? in che quantita'? tutto o parziale?».
-- `betfair_live_orders` e `tennis_live_orders` hanno tutti questi campi da
-- sempre (migrations/betfair_live_order_queue.sql): qui si portano anche dove i
-- tre bot principali scrivono davvero.
--
-- COSA NON FA: non cambia nessuna colonna esistente, nessun CHECK, nessuna RPC.
-- `size` e `price` restano ESATTAMENTE quello che sono oggi (l'abbinato), cosi'
-- nessun consumatore — backend, RPC, frontend — cambia comportamento. Le
-- colonne nuove si AFFIANCANO.
--
-- IDEMPOTENTE: `ADD COLUMN IF NOT EXISTS`, rieseguibile senza effetti.
--
-- RPC: nessuna da aggiornare. Tutte le letture passano da `to_jsonb(t.*)` su un
-- `SELECT *` (get_omega_trades omega_bot.sql:268-271 · get_safe_state
-- safe_strategy_bot.sql:271-274 · get_safe_trades :310-314 · get_mike_state
-- mike_bot.sql:266-267 · get_mike_trades :294-297), quindi le colonne nuove
-- arrivano alla UI da sole. Gli aggregati e gli storici
-- (mike_aggregati_per_modalita, omega_daily_v2, safe_strategy_bot_v2, ...)
-- enumerano solo pnl/liability/status: nessuno seleziona le colonne toccate.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- OMEGA
-- ----------------------------------------------------------------------------
ALTER TABLE public.omega_trades
    ADD COLUMN IF NOT EXISTS size_requested     numeric,
    ADD COLUMN IF NOT EXISTS size_matched       numeric,
    ADD COLUMN IF NOT EXISTS size_remaining     numeric,
    ADD COLUMN IF NOT EXISTS avg_price_matched  numeric,
    ADD COLUMN IF NOT EXISTS betfair_updated_at timestamptz;

COMMENT ON COLUMN public.omega_trades.size_requested     IS 'Size CHIESTA a Betfair (prima del cap di liquidita'' e del fill). `size` porta l''ABBINATO.';
COMMENT ON COLUMN public.omega_trades.size_matched       IS 'Size ABBINATA dichiarata da Betfair. Ridondante con `size` per costruzione: qui non verra'' mai sovrascritta da altro.';
COMMENT ON COLUMN public.omega_trades.size_remaining     IS 'Residuo ANCORA VIVO sul book secondo Betfair (`sizeRemaining`). 0 con FILL_OR_KILL. NULL = non lo sappiamo, che non e'' zero.';
COMMENT ON COLUMN public.omega_trades.avg_price_matched  IS 'Prezzo MEDIO realmente abbinato (`averagePriceMatched`), mai il prezzo chiesto.';
COMMENT ON COLUMN public.omega_trades.betfair_updated_at IS 'Quando lo abbiamo saputo DA BETFAIR (placedDate/matchedDate), non l''ora del nostro processo.';

-- ----------------------------------------------------------------------------
-- SAFE STRATEGY (base · esatto · punta · tennis: stessa tabella, `strategy` e' una colonna)
-- ----------------------------------------------------------------------------
ALTER TABLE public.safe_strategy_trades
    ADD COLUMN IF NOT EXISTS size_requested     numeric,
    ADD COLUMN IF NOT EXISTS size_matched       numeric,
    ADD COLUMN IF NOT EXISTS size_remaining     numeric,
    ADD COLUMN IF NOT EXISTS avg_price_matched  numeric,
    ADD COLUMN IF NOT EXISTS betfair_updated_at timestamptz;

COMMENT ON COLUMN public.safe_strategy_trades.size_requested     IS 'Size CHIESTA a Betfair. Sul place-and-trim (submin) un parziale con ok=true e'' NORMALE: senza questa colonna «chiesti 2,00 / abbinati 0,80» non era scrivibile da nessuna parte.';
COMMENT ON COLUMN public.safe_strategy_trades.size_matched       IS 'Size ABBINATA dichiarata da Betfair.';
COMMENT ON COLUMN public.safe_strategy_trades.size_remaining     IS 'Residuo ANCORA VIVO sul book (`sizeRemaining`). NULL = ignoto.';
COMMENT ON COLUMN public.safe_strategy_trades.avg_price_matched  IS 'Prezzo MEDIO realmente abbinato.';
COMMENT ON COLUMN public.safe_strategy_trades.betfair_updated_at IS 'Quando lo abbiamo saputo DA BETFAIR.';

-- ----------------------------------------------------------------------------
-- MIKE
-- ----------------------------------------------------------------------------
ALTER TABLE public.mike_trades
    ADD COLUMN IF NOT EXISTS size_requested     numeric,
    ADD COLUMN IF NOT EXISTS size_matched       numeric,
    ADD COLUMN IF NOT EXISTS size_remaining     numeric,
    ADD COLUMN IF NOT EXISTS avg_price_matched  numeric,
    ADD COLUMN IF NOT EXISTS betfair_updated_at timestamptz;

COMMENT ON COLUMN public.mike_trades.size_requested     IS 'Size CHIESTA a Betfair. Mike non la salvava da nessuna parte, nemmeno nel meta.';
COMMENT ON COLUMN public.mike_trades.size_matched       IS 'Size ABBINATA dichiarata da Betfair.';
COMMENT ON COLUMN public.mike_trades.size_remaining     IS 'Residuo ANCORA VIVO sul book, letto da `sizeRemaining` di listCurrentOrders — non piu'' dedotto da size-matched.';
COMMENT ON COLUMN public.mike_trades.avg_price_matched  IS 'Prezzo MEDIO realmente abbinato.';
COMMENT ON COLUMN public.mike_trades.betfair_updated_at IS 'Quando lo abbiamo saputo DA BETFAIR.';

COMMIT;

-- ============================================================================
-- VERIFICA (dopo l'applicazione):
--   SELECT table_name, column_name, data_type
--     FROM information_schema.columns
--    WHERE table_schema = 'public'
--      AND table_name IN ('omega_trades','safe_strategy_trades','mike_trades')
--      AND column_name IN ('size_requested','size_matched','size_remaining',
--                          'avg_price_matched','betfair_updated_at')
--    ORDER BY table_name, column_name;
--   -- attese: 15 righe (5 colonne x 3 tabelle)
--
-- FINCHE' NON E' APPLICATA il codice non si rompe: `execution.aggiorna_trade`
-- rileva UNA volta l'assenza delle colonne (errore 42703 / PGRST204) e riscrive
-- senza, come gia' fa `stream/runner.py:777-790` per `live_follow.record`.
-- ============================================================================
