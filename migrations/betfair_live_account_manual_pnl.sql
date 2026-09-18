-- ============================================================================
-- betfair_live_account_manual_pnl.sql — Parte B (18/09 sera) + AGGIORNATA nel
-- "terzo giro" (stessa sera): P&L di OGGI di TUTTO cio' che NON e' bot, ordine
-- esplicito dell'utente: "tutto cio' che non e' bot: dal sito Betfair O DALLA
-- NOSTRA APP". Due totali SEPARATI:
--   * manual_pnl_*     — dal SITO Betfair (nessun customerStrategyRef/
--     customerOrderRef leggibile su listClearedOrders);
--   * manual_app_pnl_* — dal TERMINALE DI TRADING MANUALE della nostra app
--     (calcio: customerStrategyRef="live"; tennis: customerStrategyRef=
--     "tennis" — MAI un bot: censimento in
--     reconcile_worker._classify_cleared_order, verificato file per file sotto
--     Betfair/stream/scalper/ e Betfair/stream/tennis_scalper/, i bot
--     AUTONOMI veri, che non usano questi ref).
--
-- Colonne ADDITIVE su betfair_live_account (STESSA riga singleton id=1: e'
-- gia' in realtime, subscribeLiveAccount la riceve senza un secondo canale).
-- Scritte da reconcile_worker.run_account_sync_if_due -> _sync_manual_pnl,
-- a cadenza bassa (60s) e subito dopo un cambio di saldo. MAI in paper: il
-- conto e' reale per definizione.
--
-- Migrazione ADDITIVA e IDEMPOTENTE: nessuna colonna esistente toccata, nessun
-- dato esistente alterato. Il codice (reconcile_worker.py) funziona ANCHE
-- PRIMA che questa migrazione sia applicata: l'upsert fallisce (colonne
-- assenti), l'eccezione e' loggata come WARNING dichiarato e NON blocca il
-- sincronizzatore del saldo (funzione/upsert separati) — vedi
-- db.upsert_live_account_manual_pnl.
-- ============================================================================

ALTER TABLE public.betfair_live_account
    -- --- manuale dal SITO Betfair --------------------------------------
    -- totale del giorno (giorno Rome, come romeDay() del frontend): NETTO di
    -- commissione se ricavabile su TUTTI gli ordini del bucket, altrimenti
    -- LORDO — mai finto netto: vedi manual_pnl_is_net.
    ADD COLUMN IF NOT EXISTS manual_pnl_eur NUMERIC,
    -- true = manual_pnl_eur e' NETTO di commissione; false = LORDO (la
    -- commissione non era leggibile su almeno un ordine); NULL = mai
    -- calcolato ancora.
    ADD COLUMN IF NOT EXISTS manual_pnl_is_net BOOLEAN,
    -- quanti ordini SETTLED di oggi sono entrati nel totale del sito.
    ADD COLUMN IF NOT EXISTS manual_pnl_orders INTEGER,
    -- quanti ordini di oggi sono stati ESCLUSI da ENTRAMBI i totali perche' il
    -- ref era irriconoscibile (ne' un nostro bot ne' manual_app ne'
    -- chiaramente il sito — "nel dubbio escludi e conta gli esclusi"):
    -- contatore UNICO condiviso, diagnostico per la UI/l'utente, MAI sommato
    -- in manual_pnl_eur ne' in manual_app_pnl_eur.
    ADD COLUMN IF NOT EXISTS manual_pnl_excluded INTEGER,
    -- giorno Rome (YYYY-MM-DD) a cui si riferisce il totale del sito.
    ADD COLUMN IF NOT EXISTS manual_pnl_day TEXT,
    -- ultimo aggiornamento SOLO di manual_pnl_* (write-on-change, separato da
    -- updated_at che il saldo aggiorna per available/exposure).
    ADD COLUMN IF NOT EXISTS manual_pnl_updated_at TIMESTAMPTZ,
    -- --- manuale dalla NOSTRA APP (terzo giro) --------------------------
    -- STESSA semantica di manual_pnl_eur/is_net/orders/day/updated_at ma per
    -- il terminale manuale calcio+tennis (ref "live"/"tennis").
    ADD COLUMN IF NOT EXISTS manual_app_pnl_eur NUMERIC,
    ADD COLUMN IF NOT EXISTS manual_app_pnl_is_net BOOLEAN,
    ADD COLUMN IF NOT EXISTS manual_app_pnl_orders INTEGER,
    ADD COLUMN IF NOT EXISTS manual_app_pnl_day TEXT,
    ADD COLUMN IF NOT EXISTS manual_app_pnl_updated_at TIMESTAMPTZ;

-- Nessuna modifica a RLS/GRANT/realtime: la riga (id=1) e la tabella sono
-- gia' pubblicate su supabase_realtime e leggibili da 'authenticated' dalla
-- migrazione betfair_live_account_heartbeat.sql — colonne nuove sulla stessa
-- riga arrivano gratis a chi gia' fa `select('*')` (fetchLiveAccount) o e'
-- sottoscritto al canale 'betfair_live_account:1' (subscribeLiveAccount).
