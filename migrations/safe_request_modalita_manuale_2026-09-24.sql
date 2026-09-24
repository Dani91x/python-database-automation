-- ============================================================================
-- SAFE STRATEGY - L'ORDINE A MANO HA LA SUA MODALITA' (strategy_modes.manual)
-- 24 settembre 2026.  DA APPLICARE A MANO (l'utente).  IDEMPOTENTE.
--
-- ORDINE DELL'UTENTE (24/09): "OGNI strumento che propone ingressi a mercato
-- deve avere sia la versione PAPER che LIVE, e in caso di LIVE gli ordini
-- devono partire DAVVERO."
--
-- COSA CAMBIA: la barriera di `safe_request` confrontava la modalita' di un
-- 'place' con `safe_strategy_control.mode` NUDO. Da oggi il servizio
-- (`bot_service._verifica_modalita_proposta`) confronta un ordine a mano con
-- `modalita_di_strategia('manual', control.mode, params)`: servizio in LIVE e
-- `strategy_modes.manual` scritto 'live' -> LIVE, qualunque altra cosa ->
-- PAPER. Senza questa migrazione la barriera SQL rifiuterebbe un ordine a mano
-- in PAPER mentre il servizio e' armato in LIVE per un'altra strategia (es. il
-- solo tennis): nessun ordine a mano possibile finche' `manual` non e' 'live'.
-- Fail-closed (nessun soldo si muove per sbaglio), ma lo strumento non
-- funzionerebbe in paper.
--
-- NESSUN'ALTRA RIGA CAMBIA: il corpo riparte TESTUALMENTE dall'ultima
-- definizione viva (`safe_cash_out_globale_e_cap_automatico_2026-09-16.sql`,
-- par. 2, corretta il 17/09). Le sole differenze: si legge anche `c.params`, il
-- ramo 'place' calcola `v_atteso` per strategia, la barriera confronta con
-- `v_atteso` (per gli altri kind `v_atteso` = `v_ctrl_mode`, come prima). La
-- barriera resta PRIMA dell'INSERT (vedi
-- `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py`).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.safe_request(p_kind text, p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_id        bigint;
    v_payload   jsonb := coalesce(p_payload, '{}'::jsonb);
    v_amount    numeric;
    v_fraction  numeric;
    v_price     numeric;
    v_size      numeric;
    v_req_mode  text;
    v_ctrl_mode text;
    v_ctrl_params jsonb;
    v_atteso    text;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('place','cashout','cancel','cashout_event','riprendi_evento') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;

    SELECT lower(btrim(c.mode)), c.params INTO v_ctrl_mode, v_ctrl_params
      FROM public.safe_strategy_control c WHERE c.id = 1;
    -- 24/09 - la modalita' ATTESA. Per cashout/cancel/cashout_event/
    -- riprendi_evento resta quella del servizio, come ieri.
    v_atteso := v_ctrl_mode;

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
        -- Cast GUARDATI: '' → NULL; testo non numerico → messaggio parlante
        -- invece del 22P02 grezzo (invalid_text_representation).
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
        v_req_mode := coalesce(nullif(lower(btrim(v_payload->>'mode')), ''), 'paper');
        IF v_req_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
        -- 24/09 - UN ORDINE NUOVO HA LA MODALITA' DELLA SUA STRATEGIA, non
        -- quella nuda del servizio (stessa regola di
        -- bot_service._verifica_modalita_proposta): senza `opp_key` e' un
        -- ordine A MANO (`strategy_modes.manual`), con `opp_key` e' una
        -- proposta del modello (`strategy_modes.model`). Il `mode` del servizio
        -- resta un TETTO: in paper si resta in paper. Con il servizio in LIVE
        -- vale LIVE solo la voce SCRITTA 'live'; assente o illeggibile = PAPER.
        IF v_ctrl_mode IS NOT NULL THEN
            v_atteso := CASE
                WHEN v_ctrl_mode = 'live'
                 AND lower(btrim(coalesce(v_ctrl_params->'strategy_modes'->>(
                         CASE WHEN coalesce(btrim(v_payload->>'opp_key'),'') <> ''
                              THEN 'model' ELSE 'manual' END), ''))) = 'live'
                THEN 'live' ELSE 'paper' END;
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
        -- M-06: la frazione si applica all'esposizione RESIDUA (cash out
        -- ripetuti sullo stesso trade): resta valida in (0,1].
        IF v_fraction IS NOT NULL AND (v_fraction <= 0 OR v_fraction > 1) THEN
            RAISE EXCEPTION 'fraction deve essere in (0,1]: %', v_fraction;
        END IF;
        -- comando su un trade esistente: la modalita' si controlla solo se c'e'
        v_req_mode := nullif(lower(btrim(v_payload->>'mode')), '');
        IF v_req_mode IS NOT NULL AND v_req_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    ELSIF p_kind IN ('cashout_event','riprendi_evento') THEN
        -- CASH-OUT GLOBALE / RIPRENDI: si ragiona per PARTITA, non per riga.
        -- Basta e avanza l'event_id: quali righe chiudere (o riprendere) lo
        -- decide il servizio leggendo le SUE tabelle, non il client. Oggi
        -- (17/09) ne' la UI ne' il servizio passano `mode` in questo payload
        -- (vedi referto: frontend/src/lib/chiusuraUtente.ts:164-175,
        -- Betfair/safe_strategy/bot_service.py `_request_cashout_event` /
        -- `_request_riprendi_evento`): il controllo resta comunque OPZIONALE,
        -- stessa semantica di cashout/cancel, cosi' un client futuro che lo
        -- passasse non aggirerebbe la barriera.
        IF coalesce(v_payload->>'event_id','') = '' THEN
            RAISE EXCEPTION 'payload % senza event_id', p_kind;
        END IF;
        v_req_mode := nullif(lower(btrim(v_payload->>'mode')), '');
        IF v_req_mode IS NOT NULL AND v_req_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    ELSE  -- cancel
        IF v_payload->>'trade_id' IS NULL THEN
            RAISE EXCEPTION 'payload cancel senza trade_id';
        END IF;
        v_req_mode := nullif(lower(btrim(v_payload->>'mode')), '');
        IF v_req_mode IS NOT NULL AND v_req_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'mode non valido: %', v_payload->>'mode';
        END IF;
    END IF;

    -- LA BARRIERA. Si applica solo quando entrambe le modalità sono note: con
    -- un control illeggibile (v_ctrl_mode NULL) NON si blocca l'operatività —
    -- sarebbe un guasto del DB che impedisce anche di CHIUDERE una posizione
    -- aperta, e il servizio ha comunque il suo controllo a valle.
    IF v_ctrl_mode IS NOT NULL AND v_req_mode IS NOT NULL
       AND v_req_mode <> v_atteso THEN
        RAISE EXCEPTION 'modalità non corrispondente: la richiesta è in %, per questo ordine vale % (servizio in %) - cambia modalità (e conferma il LIVE) prima di riprovare',
                        upper(v_req_mode), upper(v_atteso), upper(v_ctrl_mode);
    END IF;

    INSERT INTO public.safe_strategy_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_request(text,jsonb) TO authenticated, service_role;
