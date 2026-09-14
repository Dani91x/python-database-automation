-- ============================================================================
-- MIKE — IL FLUSSO DAL FISCHIO D'INIZIO NON È MAI PARTITO. NEMMENO UNA VOLTA.
-- ============================================================================
-- Il difetto più grave trovato il 14/09, ed è mio: il 13/09 ho aggiunto al
-- motore gli stati `LIVE_KO_GREEN` e `LIVE_SECOND_ENTRY` e i ruoli `ko_green` e
-- `under_second` (COSTITUZIONE §15, il flusso concordato con l'utente su quindici
-- esempi) — e **non li ho aggiunti ai vincoli del database**.
--
-- Conseguenza, misurata sul database vero prima di scrivere questa riga:
--
--     mike_trades  con strategy='ko_green'      ->  0 righe.  MAI.
--     mike_trades  con strategy='under_second'  ->  0 righe.  MAI.
--     mike_events  con state='LIVE_KO_GREEN'    ->  0 partite. MAI.
--     mike_events  con state='LIVE_SECOND_ENTRY'->  0 partite. MAI.
--     su 2000 righe di errore lette dal registro attività,
--     2000 SONO RIFIUTI DI QUESTO VINCOLO. Il 100%.
--
-- COME SI È MANIFESTATO, e perché è peggio di un errore singolo.
-- Al fischio d'inizio il motore decide correttamente (`engine.py:1771`) di
-- uscire a +N tick e emette la gamba `ko_green`. Il servizio prova a scrivere la
-- riga di riserva, il CHECK la rifiuta, la gamba viene annullata e **nessun
-- ordine parte**. Fin qui sarebbe un errore visibile.
--
-- Ma l'upsert rifiutato non salva nemmeno `ctx.live_since`. E
-- `finestra_uscita_scaduta` (`engine.py:2014`) misura i 180 s della finestra
-- **da `live_since`**. Ogni 60 s il servizio rilegge la partita, ritrova
-- `state='HOLD'` e `live_since` vuoto, e **la finestra non scade MAI**: il bot
-- riprova ogni pochi secondi, per sempre, senza mai arrivare al ramo successivo
-- — quello che avrebbe comprato la copertura Over 4.5 dopo tre minuti.
--
-- Quindi: **ogni partita entrata in gioco con una posizione aperta è rimasta
-- scoperta fino al fischio finale.** Senza uscita, senza copertura, senza
-- cash-out, senza cap di perdita. E la pagina mostrava HOLD con il feed verde.
--
-- E HA AVVELENATO LA CERTIFICAZIONE, che è la parte che fa più danno nel tempo.
-- La tabella 1→75 segnava la condizione 28 come «✓ paper (421)». Quei 421
-- riconoscimenti non sono 421 uscite riuscite: sono **la firma del guasto**, la
-- stessa frase riscritta ogni pochi secondi dal loop. Il criterio «riconosciuta
-- da: stringa nel motivo» ha contato il sintomo come prova di funzionamento.
-- Vanno ricontate col metro giusto: **la riga di `mike_trades` con il suo
-- esito**, come §16.4 stessa prescrive.
--
-- QUESTA MIGRAZIONE non cambia NESSUN dato e nessuna logica: allarga due
-- vincoli perché ammettano i valori che il motore dichiara già in
-- `engine.STATES` (21 stati) e `engine.ROLES` (11 ruoli).
--
-- Idempotente: DROP CONSTRAINT IF EXISTS + ADD, sul modello di
-- `betfair_live_greenup.sql`.
--
-- VERIFICA dopo l'applicazione — deve scrivere e poi cancellare, senza errori:
--   BEGIN;
--     INSERT INTO public.mike_trades (event_id, strategy, side, price, size, status, mode)
--     VALUES ('__prova__', 'ko_green', 'lay', 1.40, 2.00, 'pending', 'paper');
--     UPDATE public.mike_events SET state = 'LIVE_KO_GREEN' WHERE event_id = '__nessuna__';
--   ROLLBACK;
-- ============================================================================

-- 1. i RUOLI delle gambe -----------------------------------------------------
-- L'elenco è quello di `engine.ROLES`, nell'ordine del motore. I due che
-- mancavano sono `under_second` (la seconda puntata dopo un gol precoce) e
-- `ko_green` (l'uscita al fischio d'inizio): entrambi nati il 13/09 con §15.
ALTER TABLE public.mike_trades
    DROP CONSTRAINT IF EXISTS mike_trades_strategy_check;

ALTER TABLE public.mike_trades
    ADD CONSTRAINT mike_trades_strategy_check
    CHECK (strategy IN ('under_entry','under_green','under_last','under_second',
                        'ko_green','over_cover','under_close','over_close',
                        'reentry','reentry_green','manual_close'));


-- 2. gli STATI della partita -------------------------------------------------
-- L'elenco è quello di `engine.STATES`. I due che mancavano sono
-- `LIVE_KO_GREEN` (sta provando a uscire al fischio) e `LIVE_SECOND_ENTRY`
-- (sta entrando con la seconda puntata dopo un gol precoce).
ALTER TABLE public.mike_events
    DROP CONSTRAINT IF EXISTS mike_events_state_check;

ALTER TABLE public.mike_events
    ADD CONSTRAINT mike_events_state_check
    CHECK (state IN ('WATCH','PRE_ENTRY_PENDING','PRE_OPEN','PRE_GREEN_PENDING','HOLD',
                     'PRE_LAST_ENTRY_PENDING','IDLE_LIVE','LIVE_KO_GREEN','LIVE_SECOND_ENTRY',
                     'LIVE_UNCOVERED','LIVE_COVER_PENDING','LIVE_COVERED','LIVE_CLOSING','FLAT',
                     'REENTRY_PENDING','REENTRY_OPEN','REENTRY_GREEN_PENDING',
                     'SETTLING','SETTLED','ERROR','SKIPPED'));


-- ============================================================================
-- LA LEZIONE, perché non succeda di nuovo.
--
-- Un vincolo di database che elenca a mano dei valori che il codice dichiara
-- altrove è **due elenchi da tenere allineati a mano**, e prima o poi
-- divergono. Qui hanno divertito per dodici giorni senza che nessuno se ne
-- accorgesse, perché il servizio inghiottiva il rifiuto con un semplice
-- avviso (`service.py:_scrivi_evento`) — corretto nello stesso intervento:
-- **il fallimento della scrittura di stato di una partita con una posizione
-- aperta è money-critical e va gridato, non annotato.**
--
-- Esiste già un test che confronta i due elenchi
-- (`test_mike_audit_2026_09_11.py`, contratto stati/ruoli ↔ migrazione): va
-- esteso a QUESTA migrazione, altrimenti protegge il file sbagliato.
-- ============================================================================
