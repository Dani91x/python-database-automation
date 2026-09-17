-- ============================================================================
-- OMEGA — LE PROPOSTE DI USCITA TORNANO SULLA CODA CHE IL SERVIZIO DRENA
--         (17/09/2026, correzione del reperto O-1)
--
-- IL REPERTO (money-critical, trovato dal coordinatore il 17/09)
-- ----------------------------------------------------------------------------
-- `migrations/omega_proposte_uscita_2026-09-16.sql` ha creato una TABELLA NUOVA
-- (`public.omega_requests`) e ci ha messo sopra le tre RPC della Control Room.
-- Ma il servizio di Omega drena SOLO `public.omega_manual_requests`
-- (`Betfair/omega/omega_db.py:pending_manual_requests`, `.eq("status","pending")`).
-- Conseguenza: una proposta APPROVATA dall'utente sarebbe passata da 'proposed'
-- a 'pending' su una tabella che NESSUNO legge — il trader avrebbe premuto
-- APPROVA, la scheda avrebbe detto «fatto», e la posizione sarebbe rimasta
-- aperta. Nessuno se ne sarebbe accorto fino al settlement.
--
-- LA DECISIONE (coordinatore, 17/09): UNA CODA SOLA, quella che esiste gia'.
-- Regola di casa: le risorse condivise si CERCANO prima di crearle; due code
-- che fanno la stessa cosa prima o poi ne fanno due diverse. Quindi 'proposed'
-- e 'rejected' diventano due stati IN PIU' su `omega_manual_requests` — che e'
-- esattamente quello che la Safe ha fatto il 14/09 su `safe_strategy_requests`
-- (`migrations/safe_strategy_proposed_2026-09-14.sql`), e che la migrazione del
-- 16/09 diceva a parole di voler fare («NON E' UNA TABELLA NUOVA») ma non ha
-- fatto.
--
-- IL PERNO RESTA LO STESSO: il servizio drena SOLO `status='pending'`. Una riga
-- 'proposed' sta ferma finche' un essere umano non la promuove. E' questo, e
-- solo questo, a fare il cancelletto; il controllo G1 della certificazione lo
-- verifica a ogni giro, e un test diventa rosso se quel filtro si allarga
-- (`test_omega_proposte_2026_09_17.py::test_il_servizio_non_drena_mai_una_proposta`).
--
-- MEMORIA CHE QUESTA MIGRAZIONE SERVE A ONORARE (12/09): tutte e cinque le
-- chiusure automatiche di Omega v2 erano sbagliate (-42,39 EUR contro +79,95 EUR
-- fatti dalle aperture). Su un lay la liability e' GIA' impegnata: chiudere non
-- riduce il rischio preso, lo trasforma in perdita certa. Da qui in poi quella
-- decisione la prende una persona, con i numeri davanti.
--
-- COSA CAMBIA PER LA UI: NIENTE. Le tre RPC hanno la stessa firma e lo stesso
-- ritorno di prima (`omega_request_approve(bigint)`, `omega_request_ignore(
-- bigint, text)`, `get_omega_proposte()`): cambia solo la tabella sotto. Il
-- canale realtime della pagina passa da `omega_requests` a
-- `omega_manual_requests` (`frontend/src/lib/omegaProposte.ts`), che e' gia'
-- pubblicata su `supabase_realtime` da `migrations/omega_manual.sql:190-200`.
--
-- E L'ELENCO DELLE RICHIESTE MANUALI? `get_omega_manual_requests(p_limit)`
-- (`omega_manual.sql:186-199`) torna TUTTE le righe, senza filtro di stato, e
-- la pagina Omega la legge (`frontend/src/lib/omega.ts:fetchManualRequests`).
-- Senza toccarla, da domani le proposte comparirebbero nell'elenco dei comandi
-- manuali dell'utente — cioe' in un posto dove non sono comandi suoi. Qui la si
-- ricrea con `WHERE status NOT IN ('proposed','rejected')`: le proposte vivono
-- SOLO in `get_omega_proposte`. Una proposta APPROVATA passa a 'pending' e poi
-- 'done'/'error' e da quel momento compare nell'elenco come qualsiasi cash-out:
-- e' giusto che ci sia (e' un ordine partito), e la UI la riconosce dal payload
-- (`approved_at` / `motivo_codice`).
--
-- IDEMPOTENTE: si puo' rieseguire.
-- DA APPLICARE DALL'UTENTE. Non e' stata applicata.
-- ORDINE DI APPLICAZIONE: dopo `omega_manual.sql` e `omega_cashout.sql`.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. LE COLONNE CHE SERVONO ALLA PROPOSTA.
--    `result` c'e' gia' (omega_manual.sql:81). `updated_at` NO: la coda manuale
--    aveva solo `created_at`/`processed_at`, perche' una richiesta manuale nasce
--    e muore. Una PROPOSTA invece VIVE: si aggiorna mentre il mercato si muove,
--    e `updated_at` e' quello che la Control Room mostra ("aggiornata alle...")
--    e che le RPC scrivono.
-- ----------------------------------------------------------------------------
ALTER TABLE public.omega_manual_requests
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ----------------------------------------------------------------------------
-- 1. GLI STATI: 'proposed' e 'rejected' in piu'. E' un SUPERSET del CHECK vivo
--    ('pending','processing','done','error', omega_manual.sql:80): nessuna riga
--    esistente puo' diventare invalida.
--    Si eliminano TUTTI i CHECK mono-colonna su `status` (il vincolo nato con
--    la tabella e' anonimo: ha il nome che gli ha dato Postgres) e se ne
--    aggiunge uno solo, con un nome dichiarato.
-- ----------------------------------------------------------------------------
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    FOR c_name IN
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conrelid = 'public.omega_manual_requests'::regclass
           AND c.contype = 'c'
           AND a.attname = 'status'
           AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format('ALTER TABLE public.omega_manual_requests DROP CONSTRAINT %I', c_name);
    END LOOP;
END; $$;

ALTER TABLE public.omega_manual_requests
    ADD CONSTRAINT omega_manual_requests_status_check
    CHECK (status IN ('proposed','pending','processing','done','rejected','error'));
COMMIT;

-- 1-bis. `kind`: 'cashout' deve essere ammesso (lo aggiunge gia'
--        `omega_cashout.sql:28-45`). Lo si riafferma qui perche' questa
--        migrazione non puo' dare per scontato l'ordine di applicazione: una
--        proposta di uscita e' una riga `kind='cashout'`.
BEGIN;
DO $$
DECLARE c_name text;
BEGIN
    FOR c_name IN
        SELECT c.conname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conrelid = 'public.omega_manual_requests'::regclass
           AND c.contype = 'c'
           AND a.attname = 'kind'
           AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format('ALTER TABLE public.omega_manual_requests DROP CONSTRAINT %I', c_name);
    END LOOP;
END; $$;

ALTER TABLE public.omega_manual_requests
    ADD CONSTRAINT omega_manual_requests_kind_check
    CHECK (kind IN ('refresh_events','load_markets','load_book','place','cashout'));
COMMIT;

-- ----------------------------------------------------------------------------
-- 2. UNA SOLA PROPOSTA VIVA PER GAMBA.
--    Senza questo indice un servizio riavviato a meta' ciclo potrebbe scriverne
--    due, e la Control Room mostrerebbe due pulsanti APPROVA per la stessa
--    posizione: due chiusure sulla stessa gamba, cioe' una posizione aperta al
--    contrario.
-- ----------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_omega_manual_requests_proposta_viva
    ON public.omega_manual_requests (((payload->>'trade_id')))
    WHERE status = 'proposed';

CREATE INDEX IF NOT EXISTS idx_omega_manual_requests_proposed
    ON public.omega_manual_requests (created_at DESC)
    WHERE status = 'proposed';

-- ----------------------------------------------------------------------------
-- 3. CHE COSA CONTIENE IL PAYLOAD DI UNA PROPOSTA (i 28 campi documentati nella
--    migrazione del 16/09, invariati: li scrive `Betfair/omega/omega_proposte.py`
--    e li legge `frontend/src/lib/omegaProposte.ts`).
--
--   trade_id, event_id, event_name, market_id, market_type, selection_id,
--   selection_name      -- che cosa si sta chiudendo
--   side                -- lato dell'ordine di CHIUSURA ('back' su un lay aperto)
--   entry_side, entry_price, size            -- com'era l'apertura
--   price_at_decision, size_available_at_decision
--                       -- FOTOGRAFIA al momento della decisione: serve a sapere
--                          su cosa il bot ha deciso e a misurare lo scostamento.
--                          NON e' il prezzo su cui si piazza: quello lo guarda
--                          l'utente, vivo, un istante prima (come nella Safe).
--   motivo_codice       -- 'blocca_il_profitto' | 'protezione' | 'cap' | ...
--   profitto_bloccabile -- EUR netti, uguali in ogni esito, se si chiude ORA.
--                          NEGATIVO = perdita che si BLOCCA (proposta di
--                          protezione: l'utente deve poter chiudere anche in
--                          perdita, ordine del 17/09).
--   back_price, back_size -- l'ordine che realizzerebbe quel risultato
--   ev_tenere           -- quanto vale portarla al settlement con la P di adesso
--   p_evento            -- P che il risultato bancato ESCA (modello V3)
--   liability           -- quanto e' impegnato su questa gamba
--   meglio_aspettare, bloccabile_max_atteso, minuto_del_massimo
--                       -- la TRAIETTORIA: se il punteggio regge, quanto si
--                          bloccherebbe piu' avanti e a che minuto.
--   minute, score, mode ('paper'|'live')
--   decided_at          -- istante della DECISIONE: NON si rinfresca mai
--   proposed_at         -- ultimo aggiornamento della proposta
--   approved_at         -- lo AGGIUNGE la RPC qui sotto, ed e' il segno con cui
--                          il servizio distingue una chiusura DECISA DAL BOT e
--                          firmata dall'utente da un «Cash out» premuto da lui
--                          (`omega_service._uscita_del_bot_approvata`).
--
-- `decided_at` fermo e `proposed_at` mobile sono i due istanti che rendono
-- misurabile la latenza vera di una chiusura approvata a mano (cert. Safe
-- 14/09). Il controllo G2 della certificazione di Omega verifica entrambi.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 4. APPROVA: proposed -> pending.
--    Da qui in poi il percorso e' quello di sempre, invariato: `process_manual`
--    drena la riga come un `cashout` e la esegue con `execution.close_trade`.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_request_approve(p_id bigint)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.omega_manual_requests%ROWTYPE;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    -- FOR UPDATE: fra la lettura e la scrittura il servizio potrebbe aver
    -- aggiornato la proposta col prezzo nuovo. Approvare e' un atto sui soldi:
    -- si prende il lock, non si spera.
    SELECT * INTO v_row FROM public.omega_manual_requests WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        -- non e' un errore del chiamante: e' una corsa fra due schede aperte, o
        -- l'utente che preme due volte. Si dichiara cosa e' successo.
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non e'' piu'' in attesa di approvazione');
    END IF;

    -- il payload si CONSERVA e si AGGIUNGE la firma: `exit_kind`/`motivo_codice`
    -- sono i campi con cui il servizio riconosce l'uscita del BOT, e rifarli da
    -- zero li butterebbe via (difetto 27 del catalogo, gia' visto sulla Safe).
    UPDATE public.omega_manual_requests
       SET status = 'pending',
           payload = v_row.payload || jsonb_build_object(
               'approved_at', to_char(now() AT TIME ZONE 'utc',
                                      'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'pending');
END;
$$;

-- ----------------------------------------------------------------------------
-- 5. IGNORA: proposed -> rejected, col motivo.
--    Non e' «non chiudere mai»: se la situazione CAMBIA (prezzo, punteggio,
--    profitto bloccabile) il servizio ripropone. «Torna alla prossima
--    occasione», come deciso dall'utente per la Safe il 14/09.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.omega_request_ignore(p_id bigint,
                                                       p_reason text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_row public.omega_manual_requests%ROWTYPE;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    SELECT * INTO v_row FROM public.omega_manual_requests WHERE id = p_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'richiesta % inesistente', p_id;
    END IF;
    IF v_row.status <> 'proposed' THEN
        RETURN jsonb_build_object(
            'ok', false, 'id', p_id, 'status', v_row.status,
            'note', 'la proposta non e'' piu'' in attesa di approvazione');
    END IF;

    UPDATE public.omega_manual_requests
       SET status = 'rejected',
           result = coalesce(v_row.result, '{}'::jsonb) || jsonb_build_object(
               'ignorata_dall_utente', true,
               'motivo', coalesce(nullif(btrim(p_reason), ''), 'nessun motivo indicato')),
           updated_at = now()
     WHERE id = p_id;

    RETURN jsonb_build_object('ok', true, 'id', p_id, 'status', 'rejected');
END;
$$;

-- ----------------------------------------------------------------------------
-- 6. LE PROPOSTE VIVE, per la Control Room (una lettura sola).
--    Stessa firma e stesso ritorno di prima: la UI non cambia.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_proposte()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
  SELECT coalesce(jsonb_agg(jsonb_build_object(
             'id', r.id, 'kind', r.kind, 'payload', r.payload,
             'created_at', r.created_at, 'updated_at', r.updated_at)
           ORDER BY r.created_at DESC), '[]'::jsonb)
    FROM public.omega_manual_requests r
   WHERE r.status = 'proposed';
$$;

REVOKE ALL ON FUNCTION public.omega_request_approve(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.omega_request_ignore(bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_omega_proposte() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.omega_request_approve(bigint) TO authenticated;
GRANT EXECUTE ON FUNCTION public.omega_request_ignore(bigint, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_omega_proposte() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 7. L'ELENCO DELLE RICHIESTE MANUALI non deve mostrare le proposte.
--    Stessa firma, stesso ritorno, stessi REVOKE/GRANT di `omega_manual.sql`:
--    cambia solo il WHERE. Una proposta 'proposed' e' una domanda del BOT
--    all'utente, non un comando dell'utente; una 'rejected' e' una domanda
--    scartata. Nessuna delle due e' una richiesta manuale.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_omega_manual_requests(p_limit integer DEFAULT 20)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(r.*) ORDER BY r.created_at DESC), '[]'::jsonb)
      INTO v FROM (SELECT * FROM public.omega_manual_requests
                    WHERE status NOT IN ('proposed','rejected')
                    ORDER BY created_at DESC
                    LIMIT least(greatest(coalesce(p_limit,20),1),100)) r;
    RETURN v;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_omega_manual_requests(integer) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_omega_manual_requests(integer) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 8. LA TABELLA ORFANA `public.omega_requests`.
--    L'ha creata la migrazione del 16/09 e non l'ha mai letta nessuno: il
--    servizio non la drena, e da adesso nemmeno le RPC la toccano. Si elimina
--    SOLO SE E' VUOTA: se qualcuno ci avesse gia' scritto una proposta (una
--    prova a mano, una sessione di sviluppo), buttarla via vorrebbe dire
--    cancellare una decisione sui soldi senza guardarla. In quel caso la
--    tabella resta e il messaggio dice cosa fare.
-- ----------------------------------------------------------------------------
DO $$
DECLARE n bigint;
BEGIN
    IF to_regclass('public.omega_requests') IS NULL THEN
        RAISE NOTICE 'omega_requests non esiste: niente da fare';
        RETURN;
    END IF;
    EXECUTE 'SELECT count(*) FROM public.omega_requests' INTO n;
    IF n = 0 THEN
        DROP TABLE public.omega_requests;
        RAISE NOTICE 'omega_requests era vuota: eliminata (coda unica)';
    ELSE
        RAISE NOTICE 'omega_requests contiene % righe: NON eliminata. Guardarle una '
                     'per una (sono proposte di chiusura mai eseguite), poi '
                     'DROP TABLE public.omega_requests;', n;
    END IF;
END; $$;

-- ----------------------------------------------------------------------------
-- 9. PROMEMORIA DI COSA *NON* CAMBIA, perche' e' la parte che regge tutto
--
--  * Le APERTURE non passano di qui: restano automatiche, coi loro cap.
--  * Il servizio non drena 'proposed'. Se un domani lo facesse, il cancelletto
--    sparirebbe senza che nessuno se ne accorga: e' per questo che G1 esiste.
--  * Nessun freno (fermo macchina, cap, stop giornaliero) puo' rendere una
--    proposta di chiusura non approvabile: quei freni valgono sulle APERTURE.
--    Chi ha una posizione aperta deve sempre poterla chiudere.
--  * Le protezioni che NON chiudono restano attive e automatiche: settlement
--    dal mercato Betfair e riconciliazione degli ordini a esito ignoto.
--  * «Quota rotta» o mercato chiuso NON producono un'uscita automatica: al
--    massimo una riga di attivita'. Nessuna uscita parte da sola.
-- ----------------------------------------------------------------------------
