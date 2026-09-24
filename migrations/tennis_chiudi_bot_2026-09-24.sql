-- ============================================================================
-- tennis_chiudi_bot_2026-09-24.sql - il "CHIUDI ORA" dei 4 bot tennis (D3,
-- 24/09/2026). LA APPLICA L'UTENTE.
--
-- DECISIONE DELL'UTENTE: "il Chiudi deve funzionare anche per i 4 bot tennis".
-- La richiesta viaggia sulla coda che il runner tennis GIA' drena
-- (`tennis_live_order_queue`, `tennis_live_order_worker`): NESSUNA tabella
-- nuova, NESSUNA colonna nuova. Serve solo che la RPC di accodamento accetti
-- l'azione `chiudi_bot` (la whitelist di `request_tennis_live_order` la
-- rifiutava con "action non valida").
--
-- COSA CAMBIA (SOLO questo, il resto del corpo e' IDENTICO a
-- `migrations/tennis_orders.sql` 2.1):
--   * whitelist + 'chiudi_bot';
--   * per 'chiudi_bot' la RPC pretende `bot` fra i quattro bot tennis e
--     `event_id` + `market_id` presenti (le guardie d'identita' vere, contro il
--     bot ospitato, le fa il runner: `chiusura_manuale.richiesta_ambigua`).
--
-- FINCHE' NON E' APPLICATA: il clic sul "Chiudi" di una riga tennis riceve
-- subito l'errore della RPC ("action non valida: chiudi_bot") e il bottone
-- mostra "rifiutata: non inviata: ..." - nessun ordine, nessun effetto.
--
-- IDEMPOTENTE (CREATE OR REPLACE). OWNER-ONLY, SECURITY DEFINER, search_path
-- fisso, grant identici a quelli di `tennis_orders.sql` (e di
-- `sicurezza_db_2026-09-24_BLOCCO_3_revoke_anon.sql`: niente ad anon).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.request_tennis_live_order(p jsonb)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id         bigint;
    v_client_ref text := nullif(p->>'client_ref', '');
    v_action     text := nullif(p->>'action', '');
    v_mode       text := nullif(p->>'mode', '');
BEGIN
    -- OWNER-ONLY: denaro REALE in mode='live'.
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;

    IF v_client_ref IS NULL THEN
        RAISE EXCEPTION 'client_ref obbligatorio';
    END IF;
    IF v_action IS NULL THEN
        RAISE EXCEPTION 'action obbligatoria';
    END IF;
    IF v_mode IS NULL OR lower(v_mode) NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valida (paper|live)';
    END IF;

    -- Whitelist azioni (difesa in profondita', come il calcio).
    -- D3 (24/09): + 'chiudi_bot' ("chiudi ora" di un bot tennis).
    IF lower(v_action) NOT IN ('place','cancel','replace','greenup','cashout_all',
                               'cashout_event','chiudi_bot') THEN
        RAISE EXCEPTION 'action non valida: %', v_action;
    END IF;

    -- Bound numerici money-critical su place/replace: prezzo ladder Betfair [1.01, 1000],
    -- size/liability > 0. Blocca prezzi/size assurdi PRIMA di raggiungere flumine.
    IF lower(v_action) = 'place' THEN
        IF (p->>'price') IS NULL OR (p->>'price')::numeric < 1.01 OR (p->>'price')::numeric > 1000 THEN
            RAISE EXCEPTION 'price fuori range [1.01,1000]: %', (p->>'price');
        END IF;
        IF coalesce((p->>'size')::numeric, 0) <= 0 THEN
            RAISE EXCEPTION 'size deve essere > 0';
        END IF;
    ELSIF lower(v_action) = 'replace' THEN
        IF (p->>'new_price') IS NOT NULL
           AND ((p->>'new_price')::numeric < 1.01 OR (p->>'new_price')::numeric > 1000) THEN
            RAISE EXCEPTION 'new_price fuori range [1.01,1000]: %', (p->>'new_price');
        END IF;
    ELSIF lower(v_action) = 'chiudi_bot' THEN
        -- D3: la richiesta dice QUALE bot, QUALE partita, QUALE mercato. Il
        -- runner confronta tutto con il bot ospitato (fail-closed).
        IF coalesce(p->>'bot', '') NOT IN ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing') THEN
            RAISE EXCEPTION 'bot non valido per chiudi_bot: %', (p->>'bot');
        END IF;
        IF nullif(p->>'event_id', '') IS NULL OR length(p->>'event_id') > 64 THEN
            RAISE EXCEPTION 'event_id obbligatorio per chiudi_bot';
        END IF;
        IF nullif(p->>'market_id', '') IS NULL OR length(p->>'market_id') > 32 THEN
            RAISE EXCEPTION 'market_id obbligatorio per chiudi_bot';
        END IF;
    END IF;

    -- idempotenza: stesso client_ref -> stessa richiesta.
    SELECT id INTO v_id
      FROM public.tennis_live_order_queue
     WHERE client_ref = v_client_ref;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    INSERT INTO public.tennis_live_order_queue (client_ref, payload)
    VALUES (v_client_ref, p)
    ON CONFLICT (client_ref) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id
          FROM public.tennis_live_order_queue
         WHERE client_ref = v_client_ref;
    END IF;
    RETURN v_id;
END;
$$;

-- GRANT (ribaditi: CREATE OR REPLACE preserva i grant, ma il file deve essere
-- autoconsistente a prescindere dall'ordine di applicazione).
REVOKE ALL    ON FUNCTION public.request_tennis_live_order(jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.request_tennis_live_order(jsonb) TO authenticated, service_role;
