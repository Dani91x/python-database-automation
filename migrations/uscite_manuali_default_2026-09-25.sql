-- ============================================================================
-- uscite_manuali_default_2026-09-25.sql — DEFAULT delle "uscite automatiche"
-- portato a MANUALE per TUTTI i bot. LA APPLICA L'UTENTE. ADDITIVA e
-- IDEMPOTENTE (nessun DROP, nessuna colonna tolta, sicura da rilanciare).
--
-- ORDINE DELL'UTENTE (testuale, 25/09 sera): «di default, tutte le uscite le
-- voglio spente, ovvero decido io se uscire o no, per tutti i bot».
--
-- Oggi (prima di questa migrazione) l'interruttore "uscite automatiche" per
-- singolo bot, introdotto la mattina del 25/09 (migrazioni
-- `uscite_automatiche_mike_2026-09-25.sql`,
-- `uscite_automatiche_scalper_2026-09-25.sql`,
-- `tennis_uscite_manuali_2026-09-25.sql`), nasceva ACCESO (comportamento di
-- prima, parita'): Mike, Safe base/esatto/punta/model, scalper e i 4 bot
-- tennis eseguivano le uscite discrezionali da soli; solo Omega era gia'
-- "avvisa e proponi" e solo il tennis di Safe seguiva il cancelletto storico
-- (anch'esso nato spento = automatiche). L'utente ha ribaltato la decisione
-- la sera stessa: TUTTE le uscite discrezionali nascono ora PROPOSTE, in
-- tutti i bot, in paper e in live; l'utente le approva o chiude a mano dalla
-- scheda. Le PROTEZIONI money-critical (stop, kill-switch, chiusura a
-- mercato in chiusura, cap perdita, copertura Over 4.5 di Mike, ecc. — vedi
-- la classificazione in AUDIT_2026-09-25/USCITE_AUTOMATICHE_PER_BOT.md §3 e
-- TENNIS_AUTO_MODE.md §3) NON sono toccate: restano sempre automatiche,
-- come oggi.
--
-- QUESTA migrazione fa DUE cose, nell'ordine:
--   1) porta a MANUALE, UNA VOLTA, i valori GIA' SCRITTI sulle righe di
--      controllo esistenti — anche quelli espliciti (l'utente ha detto "di
--      default TUTTE spente": non e' un rispetto di una scelta precedente,
--      e' l'ordine nuovo che la sostituisce). Non tocca nient'altro sulla
--      riga (status, mode, stake, altri parametri restano quelli di oggi).
--   2) cambia il DEFAULT delle colonne che hanno un default SQL vero
--      (le colonne booleane `uscite_automatiche` di `tennis_bot_service_control`
--      e `tennis_bot_control`, se la migrazione del tennis e' gia' stata
--      applicata con il vecchio DEFAULT true) da true a false, cosi' anche
--      una riga NUOVA nata prima che l'app aggiorni il codice nasce manuale.
--
-- Mike e Safe non hanno una colonna SQL dedicata: la chiave vive dentro
-- `params` JSONB, e il DEFAULT vero e' quello del codice applicativo
-- (`Betfair/mike/config.py` PARAM_SPEC, `Betfair/safe_strategy/bot_service.py`
-- DEFAULT_PARAMS) — gia' cambiato a manuale in questa stessa consegna. Il
-- codice funziona ANCHE SENZA questa migrazione: un DB non ancora aggiornato
-- legge comunque manuale dal default applicativo. Questa migrazione serve
-- SOLO a chi ha gia' scritto un valore esplicito (`true`, o una mappa con
-- qualche strategia accesa) prima di stasera, e lo vuole riportato a
-- manuale una volta, senza aprire ogni bot a mano dalla UI.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) MIKE — mike_control.params.uscite_automatiche (bool)
-- ----------------------------------------------------------------------------
UPDATE public.mike_control
   SET params = jsonb_set(coalesce(params, '{}'::jsonb),
                          '{uscite_automatiche}', 'false'::jsonb, true),
       updated_at = now()
 WHERE id = 1;

-- ----------------------------------------------------------------------------
-- 2) SAFE — safe_strategy_control.params.uscite_automatiche (mappa per
--    strategia) + .tennis_exit_approval (il cancelletto storico del tennis,
--    UNA sola verita' con la mappa: acceso = tennis manuale).
-- ----------------------------------------------------------------------------
UPDATE public.safe_strategy_control
   SET params = jsonb_set(
                 jsonb_set(coalesce(params, '{}'::jsonb),
                           '{tennis_exit_approval}', 'true'::jsonb, true),
                 '{uscite_automatiche}',
                 '{"base": false, "esatto": false, "punta": false, "tennis": false, "model": false}'::jsonb,
                 true),
       updated_at = now()
 WHERE id = 1;

-- ----------------------------------------------------------------------------
-- 3) SCALPER CALCIO — scalper_control.params.uscite_automatiche di OGNI
--    sessione (attiva o no: una sessione ferma che riparte deve comunque
--    nascere manuale) + scalper_service_control (l'interruttore
--    dell'auto-mode, se la migrazione `scalper_auto_mode_2026-09-25.sql` e'
--    gia' applicata: le sessioni nuove dell'auto-mode nascono con questo
--    valore).
-- ----------------------------------------------------------------------------
UPDATE public.scalper_control
   SET params = jsonb_set(coalesce(params, '{}'::jsonb),
                          '{uscite_automatiche}', 'false'::jsonb, true),
       updated_at = now();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'scalper_service_control') THEN
        UPDATE public.scalper_service_control
           SET params = jsonb_set(coalesce(params, '{}'::jsonb),
                                  '{uscite_automatiche}', 'false'::jsonb, true),
               updated_at = now()
         WHERE id = 1;
    END IF;
END;
$$;

-- ----------------------------------------------------------------------------
-- 4) TENNIS (4 bot: swing, pro, flb, scalper) — colonna BOOLEAN vera su
--    tennis_bot_service_control (l'interruttore del bot) e tennis_bot_control
--    (la riga per partita). Guardato con IF EXISTS: se la migrazione
--    `tennis_uscite_manuali_2026-09-25.sql` non e' ancora applicata la
--    colonna non esiste, e qui non si fa niente (il codice gia' legge
--    manuale di default, colonna assente compresa).
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'tennis_bot_service_control'
                  AND column_name = 'uscite_automatiche') THEN
        ALTER TABLE public.tennis_bot_service_control
            ALTER COLUMN uscite_automatiche SET DEFAULT false;
        UPDATE public.tennis_bot_service_control
           SET uscite_automatiche = false, updated_at = now();
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'tennis_bot_control'
                  AND column_name = 'uscite_automatiche') THEN
        ALTER TABLE public.tennis_bot_control
            ALTER COLUMN uscite_automatiche SET DEFAULT false;
        UPDATE public.tennis_bot_control
           SET uscite_automatiche = false, updated_at = now();
    END IF;
END;
$$;

-- ----------------------------------------------------------------------------
-- Verifica dopo l'apply (facoltativa, sola lettura):
--   SELECT id, params->'uscite_automatiche' FROM public.mike_control;
--   SELECT id, params->'tennis_exit_approval', params->'uscite_automatiche'
--     FROM public.safe_strategy_control;
--   SELECT event_id, params->'uscite_automatiche' FROM public.scalper_control;
--   SELECT bot_key, uscite_automatiche FROM public.tennis_bot_service_control;
-- ============================================================================
