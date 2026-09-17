-- ============================================================================
-- omega_trades_status_cancelled_lapsed_2026-09-17.sql — 'cancelled' e 'lapsed'
-- nel CHECK di omega_trades.status (T3, consapevolezza completa degli ordini).
--
-- IL PROBLEMA: omega_trades_status_check (migrations/omega_cashout.sql:73-74)
-- ammette solo ('pending','open','hedged','won','lost','void','error'). Un
-- ordine ANNULLATO dal bot (residuo cancellato, MAI abbinato) e un ordine
-- LAPSATO da Betfair (persistence LAPSE, mercato in-play) oggi ripiegano
-- entrambi su 'error' + meta.reason — indistinguibili da un place fallito o
-- da un errore di rete nella riga stessa, finche' non si apre il meta.
--
-- DA APPLICARE A MANO DALL'UTENTE. Nessun agente la applica (stesso obbligo
-- di trades_consapevolezza_ordine_2026-09-16.sql).
--
-- COSA NON FA: non tocca nessuna riga esistente, nessun'altra colonna, nessuna
-- RPC. Aggiunge SOLO i due valori ammessi dal CHECK — 'error'+meta.reason
-- resta un CHECK valido: il servizio sceglie quando scrivere l'uno o l'altro
-- (Betfair/omega/omega_service.py), qui si prepara solo lo schema.
--
-- IDEMPOTENTE: stesso pattern di omega_cashout.sql §2 — drop di OGNI CHECK
-- mono-colonna su omega_trades.status (mai un nome hard-coded: puo' differire
-- se la tabella e' nata da un CREATE inline), poi add con i due stati nuovi.
-- Rieseguibile senza effetti.
-- ============================================================================

BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    FOR c_name IN
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conrelid = 'public.omega_trades'::regclass
           AND c.contype = 'c'
           AND a.attname = 'status'
           AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format('ALTER TABLE public.omega_trades DROP CONSTRAINT %I', c_name);
    END LOOP;
END; $$;

ALTER TABLE public.omega_trades
    ADD CONSTRAINT omega_trades_status_check
    CHECK (status IN ('pending','open','hedged','won','lost','void','error',
                      'cancelled','lapsed'));
COMMIT;

-- ============================================================================
-- VERIFICA (dopo l'applicazione):
--   SELECT conname, pg_get_constraintdef(oid)
--     FROM pg_constraint
--    WHERE conrelid = 'public.omega_trades'::regclass AND contype = 'c'
--      AND conname = 'omega_trades_status_check';
--   -- atteso: CHECK (status = ANY (ARRAY['pending','open','hedged','won',
--   --          'lost','void','error','cancelled','lapsed']))
--
-- FINCHE' NON E' APPLICATA: il servizio continua a scrivere 'error' +
-- meta.reason per gli esiti oggi ripiegati (nessuna riga puo' rompersi: il
-- CHECK attuale resta valido finche' nessuno prova a scrivere i due valori
-- nuovi). Il servizio NON e' stato cambiato per scrivere 'cancelled'/'lapsed'
-- in questo giro: manca ancora, in questo worktree, il documento che
-- classifica QUALE esito diventa l'uno o l'altro (referto CHECKPOINT_T3:
-- PROGETTO_OMEGA_V4_2026-09-17.md e il §7.18 del catalogo citati nel mandato
-- non esistono in questo checkout, fermo al 16/09 sera) — scriverlo senza
-- quella classificazione sarebbe un'iniziativa sulla strategia, non solo
-- sullo schema. Questa migrazione prepara SOLO lo schema; il ripiego dichiarato
-- (schema_warn) e la scrittura degli stati nuovi restano un passo successivo,
-- da fare con la classificazione in mano.
-- ============================================================================
