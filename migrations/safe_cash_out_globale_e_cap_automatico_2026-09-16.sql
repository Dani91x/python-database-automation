-- ============================================================================
-- SAFE STRATEGY — CASH-OUT GLOBALE DI PARTITA, «RIPRENDI», CAP SOLO SUL BOT
-- 16 settembre 2026.  DA APPLICARE A MANO (l'utente).  IDEMPOTENTE.
--
-- ORDINE DELL'UTENTE (16/09, sera):
--   «SE CHIUDO IO IL BOT DEVE SAPERLO E NON DEVE GESTIRE POSIZIONI CHE NON
--    ESISTONO PIU'; se faccio un cash-out globale il bot al controllo successivo
--    lo capisce e NON FA ALTRO; il bot gestisce le SUE operazioni e ignora le
--    mie manuali.»
--
-- PERCHE' SERVE UNA MIGRAZIONE (e non se ne poteva fare a meno):
--   1. `safe_strategy_requests.kind` ha un CHECK che ammette SOLO
--      ('place','cashout','cancel') e la RPC `safe_request` rifiuta gli altri:
--      senza questa migrazione la UI non puo' nemmeno ACCODARE un cash-out
--      globale ne' un «Riprendi». E' il difetto 18 del catalogo (un CHECK che
--      non ammette uno stato del motore) preso PRIMA che faccia danni.
--   2. la RPC `get_safe_aggregates` torna i numeri della giornata senza
--      distinguere le righe del BOT da quelle che il trader apre a mano: i cap
--      del bot ne sono contagiati (misurati 32,80 EUR di responsabilita'
--      manuale dentro i cap). La serie `_auto` che i cap devono leggere e'
--      gia' calcolata dalla scansione Python; alla RPC va aggiunta (vedi §3:
--      qui NON la si tocca, e il motivo e' scritto).
--
-- IL MARCATORE «chiuso dall'utente» NON HA BISOGNO DI COLONNE NUOVE: vive in
-- `safe_strategy_trades.meta` (JSONB gia' esistente), chiave `chiuso_dall_utente`
-- = {"quando": iso, "come": "cashout"|"cashout_event"|"fuori_app", ...}.
--
-- SENZA QUESTA MIGRAZIONE il servizio funziona lo stesso ma:
--   · il cash-out globale e il «Riprendi» si possono solo simulare riga per riga
--     (il bot li riconosce comunque: chiusa l'ultima riga viva, la partita e'
--     chiusa dall'utente);
--   · i cap ripiegano sui numeri COMPLETI, cioe' piu' alti — piu' prudenti, mai
--     il contrario.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. I due kind nuovi della coda richieste
-- ----------------------------------------------------------------------------
ALTER TABLE public.safe_strategy_requests
    DROP CONSTRAINT IF EXISTS safe_strategy_requests_kind_check;
ALTER TABLE public.safe_strategy_requests
    ADD CONSTRAINT safe_strategy_requests_kind_check
    CHECK (kind IN ('place','cashout','cancel','cashout_event','riprendi_evento'));

-- ----------------------------------------------------------------------------
-- 2. safe_request: accetta i due kind nuovi e ne valida il payload
--    (resta owner-only e SECURITY DEFINER, come l'originale in
--     safe_strategy_bot_v2.sql: qui si aggiungono SOLO i due rami).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id       bigint;
    v_payload  jsonb := coalesce(p_payload, '{}'::jsonb);
    v_amount   numeric;
    v_fraction numeric;
    v_price    numeric;
    v_size     numeric;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('place','cashout','cancel','cashout_event','riprendi_evento') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;

    IF p_kind = 'place' THEN
        IF coalesce(v_payload->>'event_id','') = ''
           OR coalesce(v_payload->>'market_id','') = ''
           OR coalesce(v_payload->>'market_type','') = ''
           OR v_payload->>'selection_id' IS NULL
           OR coalesce(v_payload->>'side','') NOT IN ('back','lay')
           OR v_payload->>'price' IS NULL
           OR v_payload->>'size' IS NULL THEN
            RAISE EXCEPTION 'payload place incompleto (servono event_id, market_id, market_type, selection_id, side, price, size)';
        END IF;
        BEGIN
            v_price := nullif(v_payload->>'price','')::numeric;
            v_size  := nullif(v_payload->>'size','')::numeric;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'price/size non numerici: price=%, size=%',
                            v_payload->>'price', v_payload->>'size';
        END;
        IF v_price IS NULL OR v_price <= 1.0 THEN
            RAISE EXCEPTION 'price non valido: %', v_payload->>'price';
        END IF;
        IF v_size IS NULL OR v_size <= 0 THEN
            RAISE EXCEPTION 'size non valida: %', v_payload->>'size';
        END IF;
        IF coalesce(v_payload->>'mode','paper') NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    ELSIF p_kind = 'cashout' THEN
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cashout senza trade_id';
        END IF;
        BEGIN
            v_amount   := nullif(v_payload->>'amount','')::numeric;
            v_fraction := nullif(v_payload->>'fraction','')::numeric;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'amount/fraction non numerici: amount=%, fraction=%',
                            v_payload->>'amount', v_payload->>'fraction';
        END;
        IF v_amount IS NOT NULL AND v_amount <= 0 THEN
            RAISE EXCEPTION 'amount deve essere > 0: %', v_amount;
        END IF;
        IF v_fraction IS NOT NULL AND (v_fraction <= 0 OR v_fraction > 1) THEN
            RAISE EXCEPTION 'fraction deve essere in (0,1]: %', v_fraction;
        END IF;
    ELSIF p_kind IN ('cashout_event','riprendi_evento') THEN
        -- CASH-OUT GLOBALE / RIPRENDI: si ragiona per PARTITA, non per riga.
        -- Basta e avanza l'event_id: quali righe chiudere (o riprendere) lo
        -- decide il servizio leggendo le SUE tabelle, non il client.
        IF coalesce(v_payload->>'event_id','') = '' THEN
            RAISE EXCEPTION 'payload % senza event_id', p_kind;
        END IF;
    ELSE  -- cancel
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cancel senza trade_id';
        END IF;
    END IF;

    INSERT INTO public.safe_strategy_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_request(text,jsonb) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. get_safe_aggregates — NON TOCCATA QUI, E DI PROPOSITO.
-- ----------------------------------------------------------------------------
-- Servirebbe che la RPC tornasse, oltre ai numeri di oggi, la stessa serie
-- contata sulle SOLE posizioni del bot (chiavi con suffisso `_auto`):
--     aperture con coalesce(origin,'auto') <> 'manual'
--     + TUTTE le loro gambe di chiusura, qualunque sia l'origine della
--       chiusura (un cash-out manuale su una posizione del bot resta P&L del
--       bot: escluderlo darebbe un realizzato falso).
-- NON la si riscrive qui perche' `get_safe_aggregates` (in
-- `safe_strategy_bot_v2.sql`) ha un calcolo lungo e delicato — giornata
-- operativa Europe/Rome sul giorno di PIAZZAMENTO, liability RESIDUA dopo le
-- coperture, riconciliazione, won/lost per SEGNO del P&L totale — e una
-- CREATE OR REPLACE scritta al buio la romperebbe. Va rifatta una volta sola,
-- duplicando il blocco esistente sul sottoinsieme e appiccicando il suffisso
-- alle chiavi, da chi ha il file davanti.
--
-- FINCHE' NON E' FATTO, e va detto perche' e' importante:
--   · `bot_db.aggregates` non trova le chiavi `_auto` nella risposta della RPC;
--   · `bot_service._numeri_di_rischio` ripiega sui numeri COMPLETI, che sono
--     piu' ALTI: i cap giornalieri si chiudono PRIMA, mai dopo (prudente);
--   · i tetti che contano le POSIZIONI VIVE — `max_open_trades`, posizioni per
--     evento, cap di responsabilita' per evento — sono gia' corretti senza
--     nessuna migrazione, perche' il filtro lo fa Python su `open_trades`
--     (`bot_service.build_risk_ctx`);
--   · lo stato del ripiego e' DICHIARATO nelle stats che la UI legge:
--     `risk.cap_solo_automatico` = false finche' la RPC non porta le `_auto`.
-- Se la RPC non e' proprio applicata (`get_safe_aggregates` assente), la
-- scansione Python calcola gia' entrambe le serie e non manca nulla.
