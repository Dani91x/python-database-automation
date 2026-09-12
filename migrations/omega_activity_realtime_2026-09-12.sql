-- ---------------------------------------------------------------------------
-- OMEGA — il log del servizio in TEMPO REALE (certificazione 12/09/2026)
-- ---------------------------------------------------------------------------
-- Problema trovato: delle tre sezioni, Omega era l'unica il cui log di attivita'
-- NON arrivava in tempo reale.
--
--   Mike : mike_control, mike_events, mike_trades, mike_activity, mike_requests
--   Safe : safe_strategy_control, _trades, _requests, _activity
--   Omega: omega_control, omega_trades          <-- omega_activity MANCAVA
--
-- Conseguenza: ogni evento che non tocca una riga di omega_trades — green-up in
-- attesa, quota di mercato scartata perche' implausibile, skip, riconciliazione,
-- errori — compariva in UI solo al poll di sicurezza dei 15 secondi. Il trader
-- vedeva il motivo di una decisione fino a 15 secondi dopo che era stata presa.
--
-- La sottoscrizione lato UI e' gia' stata aggiunta (lib/omega.ts, canale
-- 'omega-live'), ma senza la tabella nella publication il canale resta MUTO:
-- Postgres non replica gli eventi di una tabella non pubblicata.
--
-- Idempotente: si puo' rieseguire. Stesso identico schema di mike_bot.sql.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname = 'supabase_realtime'
                     AND schemaname = 'public'
                     AND tablename = 'omega_activity') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.omega_activity;
        RAISE NOTICE 'omega_activity aggiunta alla publication supabase_realtime';
    ELSE
        RAISE NOTICE 'omega_activity era gia'' pubblicata: nessuna modifica';
    END IF;
EXCEPTION WHEN undefined_object THEN
    -- publication assente (ambiente non-Supabase): si ignora, come negli altri file
    NULL;
END $$;

-- ---------------------------------------------------------------------------
-- SAFE STRATEGY — stesso difetto, trovato nello stesso controllo
-- ---------------------------------------------------------------------------
-- `subscribeSafeBot` (lib/safeBot.ts) sottoscrive quattro tabelle, ma solo due
-- sono pubblicate:
--
--   pubblicate  : safe_strategy_control, safe_strategy_trades
--                 (piu' safe_strategy_scan e _status, altro canale)
--   sottoscritte: + safe_strategy_activity, + safe_strategy_requests
--
-- Le due sottoscrizioni in piu' erano quindi MUTE dal giorno in cui sono state
-- scritte: il commento nel codice dice "H-16: il log del servizio va visto in
-- tempo reale come i trade", ma senza la publication non e' mai successo. Anche
-- l'esito di un'azione manuale (safe_strategy_requests) arrivava solo al poll.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['safe_strategy_activity', 'safe_strategy_requests'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                       WHERE pubname = 'supabase_realtime'
                         AND schemaname = 'public'
                         AND tablename = t) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
            RAISE NOTICE '% aggiunta alla publication supabase_realtime', t;
        ELSE
            RAISE NOTICE '% era gia'' pubblicata: nessuna modifica', t;
        END IF;
    END LOOP;
EXCEPTION WHEN undefined_object THEN
    NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Verifica finale: le tre sezioni devono pubblicare le stesse cose che la UI
-- sottoscrive. Atteso dopo questa migrazione:
--   omega_activity, omega_control, omega_trades
--   safe_strategy_activity, _control, _requests, _scan, _status, _trades
--   mike_activity, mike_control, mike_events, mike_requests, mike_trades
-- ---------------------------------------------------------------------------
-- SELECT tablename FROM pg_publication_tables
--  WHERE pubname = 'supabase_realtime' AND schemaname = 'public'
--    AND (tablename LIKE 'omega%' OR tablename LIKE 'safe_strategy%'
--         OR tablename LIKE 'mike%')
--  ORDER BY tablename;
