-- architettura_uid_ombra_2026-10-09.sql
--
-- Migrazione dell'architettura (ARCHITETTURA_2026-10), comparto G, ondata 1, agente W1-G1.
-- Prerequisito delle tappe T8 (postino per i LOG) e T14 (stato del denaro + postino):
-- decisione U-50 di 05_PIANO_DI_MIGRAZIONE.md par. 8.2; scheda G par. 4.2; 04 par. 3.7
-- (versione e dipendenze delle righe); revisione critica R02, R06, R21.
--
-- NESSUN comportamento di oggi cambia: le colonne nuove sono facoltative (NULL), senza
-- default e senza riscrittura delle tabelle; i vecchi scrittori continuano identici.
-- Le tabelle d'ombra e le RPC non le usa nessuno finche' l'interruttore dell'ondata 2
-- (ARCH_POSTINO_LOG / ARCH_STATO_DENARO_<BOT>) non passa a "ombra" o "nuovo".
--
-- Contenuto:
--   1. colonna `uid uuid` + indice UNICO sulle 10 tabelle di LOG (G par. 4.2, "MANCA LA
--      CHIAVE"): il postino ritenta con INSERT ... ON CONFLICT (uid) DO NOTHING senza doppioni;
--   2. colonna `trade_uid uuid` + indice UNICO sulle 3 tabelle dei TRADE (U-50, U-80);
--   3. tabelle `<nome>_ombra` (STESSA FORMA: LIKE ... INCLUDING ALL, senza chiavi esterne,
--      sequenze proprie) per le tappe T8 e T14: in ombra il postino scrive SOLO li' (05 par. 0
--      regola 1 rettificata, R02, R21). T13 non ha tabelle: usa la chiave JSONB
--      `pnl_reale_oggi_ombra` (05 T13), fuori da questa migrazione;
--   4. RPC `postino_consegna`: UNA porta generica e idempotente per tutte le tabelle del
--      registro: insert ON CONFLICT DO NOTHING, upsert (fusione delle colonne come oggi),
--      patch e delete per chiave naturale; VERSIONE LOCALE PER ORIGINE (tabella
--      `postino_versioni`): una voce vecchia della STESSA origine (ritento, rientro da
--      dead_letter) non riporta mai indietro il cloud; fra origini diverse vince l'ultima
--      arrivata come oggi; l'orologio e `updated_at` non decidono nulla (R1, terza revisione);
--      esito PER RIGA (una riga rifiutata da un CHECK non ferma le altre, e torna con il
--      suo SQLSTATE: 23503 = transitorio con tetto lato postino, R06);
--   5. RPC `postino_impronte` (riconciliazione notturna: coppie [chiave, versione]);
--   6. RPC `postino_confronta_ombra` (criterio di T8: conteggi per giorno e gruppo fra la
--      tabella vera e la sua ombra, +/- 0).
--
-- Sicurezza (coerente con monitor_metrics_2026-10-09.sql e con il blocco di sicurezza del
-- 24/09): RLS attiva sulle tabelle d'ombra, nessun accesso per anon/authenticated salvo la
-- lettura dell'owner (betfair_live_is_owner()); RPC SECURITY INVOKER eseguibili SOLO da
-- service_role (il ruolo che i servizi Python usano gia' e che scrive gia' ogni tabella:
-- nessun privilegio nuovo). Le RPC accettano solo tabelle dello schema public e
-- identificatori citati con %I (niente SQL iniettabile).
--
-- IDEMPOTENTE (si puo' rilanciare). La applica l'utente (SQL Editor, ruolo postgres).
--
-- NOTA OPERATIVA (revisione B5): gli indici unici su uid/trade_uid si creano con CREATE UNIQUE INDEX
-- normale (il SQL Editor esegue lo script in UNA transazione, dove CONCURRENTLY non e' ammesso): sulle
-- tabelle di oggi (al massimo ~93.000 righe, scalper_activity) il blocco delle scritture dura frazioni di
-- secondo, ma va applicata FUORI dagli orari di trading, con l'app ferma o tutti i bot flat. Chi preferisce
-- CONCURRENTLY puo' lanciare a mano, PRIMA di questo file e una per volta fuori da una transazione:
--   CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS mike_activity_uid_key ON public.mike_activity (uid);
-- (dopo aver aggiunto la colonna); questo file poi le trova gia' create (IF NOT EXISTS).
-- Gli errori d'intestazione delle RPC usano lo SQLSTATE proprio GP001 (mai confusi con un dato non valido).
-- Provata su un PostgreSQL 16 usa-e-getta (referto ARCHITETTURA_2026-10/ondata1/W1-G1/REFERTO.md).

-- ============================================================================
-- 1. uid sulle 10 tabelle di log; 2. trade_uid sulle 3 tabelle dei trade
-- ============================================================================
DO $$
DECLARE
    v_tab text;
BEGIN
    FOREACH v_tab IN ARRAY ARRAY[
        'mike_activity', 'omega_activity', 'safe_strategy_activity', 'scalper_activity',
        'tennis_bot_activity', 'live_alerts', 'betfair_live_journal', 'betfair_live_audit',
        'signal_history', 'theta_confirm_requests']
    LOOP
        IF to_regclass(format('public.%I', v_tab)) IS NULL THEN
            RAISE NOTICE 'tabella % assente: uid saltato', v_tab;
            CONTINUE;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS uid uuid', v_tab);
        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.%I (uid)', v_tab || '_uid_key', v_tab);
        EXECUTE format('COMMENT ON COLUMN public.%I.uid IS %L', v_tab,
                       'Identita'' della riga generata nel punto di scrittura (postino, U-50): '
                       'ON CONFLICT (uid) DO NOTHING rende il ritento senza doppioni. NULL per i vecchi scrittori.');
    END LOOP;

    FOREACH v_tab IN ARRAY ARRAY['mike_trades', 'omega_trades', 'safe_strategy_trades']
    LOOP
        IF to_regclass(format('public.%I', v_tab)) IS NULL THEN
            RAISE NOTICE 'tabella % assente: trade_uid saltato', v_tab;
            CONTINUE;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS trade_uid uuid', v_tab);
        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.%I (trade_uid)', v_tab || '_trade_uid_key', v_tab);
        EXECUTE format('COMMENT ON COLUMN public.%I.trade_uid IS %L', v_tab,
                       'Identita'' locale del trade (U-50/U-80): l''id BIGINT resta la chiave di oggi '
                       '(customerOrderRef, closes_trade_id, P&L per posizione). NULL per i vecchi scrittori.');
    END LOOP;
END $$;

-- ============================================================================
-- 3. tabelle d'ombra (stessa forma)
-- ============================================================================
-- Crea o riallinea `<p_nome>_ombra`: LIKE INCLUDING ALL (colonne, default, CHECK, NOT NULL,
-- indici, identita'), mai le chiavi esterne (l'ombra non deve dipendere dai padri veri);
-- colonne aggiunte dopo alla tabella vera -> aggiunte anche all'ombra; i default
-- nextval() che puntano alla sequenza della tabella VERA passano a una sequenza propria
-- (l'ombra non consuma id della tabella vera: `mike-t<id>` resta identico).
CREATE OR REPLACE FUNCTION public._postino_crea_ombra(p_nome text)
RETURNS text
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_ombra   text := p_nome || '_ombra';
    v_col     record;
    v_seq     text;
    v_idx     record;
BEGIN
    IF to_regclass(format('public.%I', p_nome)) IS NULL THEN
        RAISE NOTICE 'tabella % assente: ombra saltata', p_nome;
        RETURN NULL;
    END IF;
    EXECUTE format('CREATE TABLE IF NOT EXISTS public.%I (LIKE public.%I INCLUDING ALL)', v_ombra, p_nome);

    -- colonne nate dopo sulla tabella vera
    FOR v_col IN
        SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS tipo
        FROM pg_attribute a
        WHERE a.attrelid = format('public.%I', p_nome)::regclass AND a.attnum > 0 AND NOT a.attisdropped
          AND NOT EXISTS (SELECT 1 FROM pg_attribute b
                          WHERE b.attrelid = format('public.%I', v_ombra)::regclass
                            AND b.attname = a.attname AND NOT b.attisdropped)
    LOOP
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN %I %s', v_ombra, v_col.attname, v_col.tipo);
    END LOOP;

    -- indici unici semplici nati dopo sulla tabella vera (es. uid, trade_uid)
    FOR v_idx IN
        SELECT i.indexrelid, array_agg(a.attname::text ORDER BY k.ord) AS colonne
        FROM pg_index i
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
        WHERE i.indrelid = format('public.%I', p_nome)::regclass AND i.indisunique
          AND i.indpred IS NULL AND i.indexprs IS NULL
        GROUP BY i.indexrelid
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_index j
            WHERE j.indrelid = format('public.%I', v_ombra)::regclass AND j.indisunique
              AND j.indpred IS NULL AND j.indexprs IS NULL
              AND (SELECT array_agg(b.attname::text ORDER BY k2.ord)
                   FROM unnest(j.indkey) WITH ORDINALITY AS k2(attnum, ord)
                   JOIN pg_attribute b ON b.attrelid = j.indrelid AND b.attnum = k2.attnum) = v_idx.colonne)
        THEN
            EXECUTE format('CREATE UNIQUE INDEX %I ON public.%I (%s)',
                           left(v_ombra || '_' || array_to_string(v_idx.colonne, '_'), 55) || '_key', v_ombra,
                           (SELECT string_agg(format('%I', c), ', ') FROM unnest(v_idx.colonne) AS c));
        END IF;
    END LOOP;

    -- sequenze proprie al posto di quelle della tabella vera
    FOR v_col IN
        SELECT a.attname, pg_get_expr(d.adbin, d.adrelid) AS espr
        FROM pg_attribute a
        JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = format('public.%I', v_ombra)::regclass AND a.attnum > 0 AND NOT a.attisdropped
          AND pg_get_expr(d.adbin, d.adrelid) LIKE 'nextval(%'
    LOOP
        v_seq := left(v_ombra || '_' || v_col.attname, 58) || '_seq';
        IF v_col.espr NOT LIKE '%' || v_seq || '%' THEN
            EXECUTE format('CREATE SEQUENCE IF NOT EXISTS public.%I OWNED BY public.%I.%I', v_seq, v_ombra, v_col.attname);
            EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I SET DEFAULT nextval(%L::regclass)',
                           v_ombra, v_col.attname, 'public.' || v_seq);
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO service_role', v_seq);
        END IF;
    END LOOP;

    -- sicurezza: come le tabelle del blocco 2 del 24/09 e monitor_metrics
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_ombra);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM public, anon, authenticated', v_ombra);
    EXECUTE format('GRANT ALL ON TABLE public.%I TO service_role', v_ombra);
    IF to_regprocedure('public.betfair_live_is_owner()') IS NOT NULL THEN
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', left(v_ombra, 50) || '_select_owner', v_ombra);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (public.betfair_live_is_owner())',
                       left(v_ombra, 50) || '_select_owner', v_ombra);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', v_ombra);
    END IF;
    EXECUTE format('COMMENT ON TABLE public.%I IS %L', v_ombra,
                   'Ombra di ' || p_nome || ' (architettura 2026-10, T8/T14): la scrive SOLO il postino in modo '
                   '"ombra"; si confronta con la tabella vera (postino_confronta_ombra / postino_impronte).');
    RETURN v_ombra;
END $$;

REVOKE ALL ON FUNCTION public._postino_crea_ombra(text) FROM PUBLIC, anon, authenticated;

SELECT public._postino_crea_ombra(t)
FROM unnest(ARRAY[
    -- T8: log (05 T8 elenco)
    'mike_activity', 'omega_activity', 'safe_strategy_activity', 'scalper_activity', 'tennis_bot_activity',
    'live_alerts', 'betfair_live_journal', 'betfair_live_audit', 'signal_history', 'theta_confirm_requests',
    'live_run_log',
    -- T14: stato del denaro (05 T14: specchio, posizioni, regolati, richieste d'ordine, trade)
    'betfair_live_order_requests', 'betfair_live_orders', 'betfair_live_positions', 'betfair_live_settled',
    'mike_trades', 'omega_trades', 'safe_strategy_trades',
    'tennis_live_order_queue', 'tennis_live_orders', 'tennis_live_positions'
]) AS t;

-- ============================================================================
-- 4. RPC postino_consegna e tabella postino_versioni
-- ============================================================================
-- VERSIONE (terza revisione del 09/10, R1, principio "IDENTICO A OGGI"): oggi vince
-- l'ultima scrittura arrivata e nessuna scrittura viene scartata. La versione serve SOLO a
-- impedire che una voce VECCHIA della STESSA origine (ritento del postino, rientro da
-- dead_letter, voce ripetuta dopo un crash) sovrascriva una voce piu' nuova della stessa
-- origine. L'origine e' il file locale che ha scritto la voce (processo/regime/id del file)
-- e la versione e' la sua sequenza LOCALE monotona (`vseq`), assegnata quando il bot scrive:
-- l'orologio non c'entra (un orologio che torna indietro non fa perdere nulla) e la colonna
-- del bot (`updated_at`) arriva TALE E QUALE. Fra origini diverse vince l'ultima arrivata.
--
-- `postino_versioni`: per (tabella, chiave naturale, origine) la versione piu' alta gia'
-- applicata. Le righe piu' vecchie di 90 giorni le toglie la RPC stessa (al massimo 100 per
-- chiamata): nessuna voce locale vive tanto (outbox FIFO per chiave, dead_letter di dato
-- archiviate dopo 7 rientri; resto dichiarato nel referto W1-G1).
CREATE TABLE IF NOT EXISTS public.postino_versioni (
    tabella    text        NOT NULL,
    chiave     jsonb       NOT NULL,
    origine    text        NOT NULL,
    versione   bigint      NOT NULL,
    aggiornato timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tabella, chiave, origine)
);
CREATE INDEX IF NOT EXISTS postino_versioni_aggiornato ON public.postino_versioni (tabella, aggiornato);
ALTER TABLE public.postino_versioni ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.postino_versioni FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.postino_versioni TO service_role;
COMMENT ON TABLE public.postino_versioni IS
    'Postino (architettura 2026-10, R1): versione locale piu'' alta applicata per (tabella, chiave, origine). '
    'Scarta SOLO le voci vecchie della stessa origine; fra origini diverse vince l''ultima arrivata.';

-- Argomenti (JSON di PostgREST): p_tabella, p_op ('insert'|'upsert'|'patch'|'delete'),
-- p_conflitto (colonne della chiave naturale), p_righe (array di oggetti con le colonne VERE
-- della tabella), p_origine (origine delle voci o NULL), p_versioni (array parallelo a
-- p_righe: la vseq di ogni voce o null; NULL = nessuna versione).
-- Risposta: array, un elemento per riga e nello stesso ordine:
--   {"esito":"ok"}       la riga e' stata scritta;
--   {"esito":"ignorata"} c'era gia' (insert idempotente, o la STESSA versione della stessa
--                        origine gia' applicata: ritento dopo una risposta persa);
--   {"esito":"vecchia"}  la stessa origine ha gia' applicato una versione PIU' NUOVA: la riga
--                        non si tocca (il postino lo segnala con un evento);
--   {"esito":"errore","codice":SQLSTATE,"messaggio":...} rifiutata (la sola riga).
-- Gli errori d'INTESTAZIONE (tabella assente, colonne di conflitto senza indice unico, op
-- sconosciuta) falliscono TUTTA la chiamata: il postino blocca la tabella e NON manda le
-- righe in dead_letter (non e' colpa delle righe).
DROP FUNCTION IF EXISTS public.postino_consegna(text, text, text[], text, jsonb);
CREATE OR REPLACE FUNCTION public.postino_consegna(
    p_tabella   text,
    p_op        text,
    p_conflitto text[],
    p_righe     jsonb,
    p_origine   text DEFAULT NULL,
    p_versioni  jsonb DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rel       regclass;
    v_colonne   text[];
    v_el        record;
    v_riga      jsonb;
    v_ver       bigint;
    v_prec      bigint;
    v_k         jsonb;
    v_kcol      text;
    v_guardia   boolean;
    v_chiavi    text[];
    v_ignote    text[];
    v_nonchiave text[];
    v_lista     text;
    v_sel       text;
    v_conf      text;
    v_set       text;
    v_dove      text;
    v_sql       text;
    v_n         bigint;
    v_esito     text;
    v_esiti     jsonb := '[]'::jsonb;
    v_stato     text;
    v_msg       text;
BEGIN
    IF p_op IS NULL OR p_op NOT IN ('insert', 'upsert', 'patch', 'delete') THEN
        RAISE EXCEPTION 'postino_consegna: operazione non ammessa: %', p_op USING ERRCODE = 'GP001';
    END IF;
    IF p_righe IS NULL OR jsonb_typeof(p_righe) <> 'array' THEN
        RAISE EXCEPTION 'postino_consegna: p_righe deve essere un array' USING ERRCODE = 'GP001';
    END IF;
    IF p_versioni IS NOT NULL AND jsonb_typeof(p_versioni) <> 'null' AND (jsonb_typeof(p_versioni) <> 'array'
       OR jsonb_array_length(p_versioni) <> jsonb_array_length(p_righe)) THEN
        RAISE EXCEPTION 'postino_consegna: p_versioni deve essere un array lungo quanto p_righe' USING ERRCODE = 'GP001';
    END IF;
    IF coalesce(cardinality(p_conflitto), 0) = 0 THEN
        RAISE EXCEPTION 'postino_consegna: chiave naturale vuota' USING ERRCODE = 'GP001';
    END IF;
    v_rel := to_regclass(format('public.%I', p_tabella));
    IF v_rel IS NULL THEN
        RAISE EXCEPTION 'postino_consegna: tabella public.% assente', p_tabella USING ERRCODE = '42P01';
    END IF;
    SELECT array_agg(a.attname::text ORDER BY a.attnum) INTO v_colonne
    FROM pg_attribute a WHERE a.attrelid = v_rel AND a.attnum > 0 AND NOT a.attisdropped;
    IF NOT (p_conflitto <@ v_colonne) THEN
        RAISE EXCEPTION 'postino_consegna: % non ha le colonne di conflitto %', p_tabella, p_conflitto
            USING ERRCODE = '42703';
    END IF;
    IF p_op IN ('insert', 'upsert') AND NOT EXISTS (
        SELECT 1 FROM pg_index i
        WHERE i.indrelid = v_rel AND i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL
          AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
               FROM pg_attribute a WHERE a.attrelid = v_rel AND a.attnum = ANY (i.indkey))
              = (SELECT array_agg(c ORDER BY c) FROM unnest(p_conflitto) AS c))
    THEN
        RAISE EXCEPTION 'postino_consegna: nessun indice unico su %(%) (migrazione non applicata?)',
            p_tabella, array_to_string(p_conflitto, ',') USING ERRCODE = '42P10';
    END IF;
    -- permessi: un rifiuto per permesso e' della TABELLA, non delle righe (niente dead_letter)
    IF NOT has_table_privilege(v_rel, CASE p_op WHEN 'patch' THEN 'UPDATE' WHEN 'delete' THEN 'DELETE' ELSE 'INSERT' END)
       OR (p_op = 'upsert' AND NOT has_table_privilege(v_rel, 'UPDATE')) THEN
        RAISE EXCEPTION 'postino_consegna: permesso negato su % per %', p_tabella, p_op USING ERRCODE = '42501';
    END IF;
    v_conf := (SELECT string_agg(format('%I', c), ', ') FROM unnest(p_conflitto) AS c);
    v_dove := (SELECT string_agg(format('t.%1$I IS NOT DISTINCT FROM r.%1$I', c), ' AND ') FROM unnest(p_conflitto) AS c);
    v_kcol := (SELECT string_agg(format('r.%I', c), ', ') FROM unnest(p_conflitto) AS c);

    -- versioni di oltre 90 giorni: al massimo 100 per chiamata (indice su tabella, aggiornato)
    IF p_origine IS NOT NULL THEN
        DELETE FROM public.postino_versioni WHERE ctid = ANY (ARRAY(
            SELECT ctid FROM public.postino_versioni
            WHERE tabella = p_tabella AND aggiornato < now() - interval '90 days' LIMIT 100));
    END IF;

    FOR v_el IN SELECT e.value, e.ord FROM jsonb_array_elements(p_righe) WITH ORDINALITY AS e(value, ord) LOOP
        v_riga := v_el.value;
        BEGIN
            IF jsonb_typeof(v_riga) <> 'object' THEN
                RAISE EXCEPTION 'riga non oggetto' USING ERRCODE = '22023';
            END IF;
            SELECT array_agg(k ORDER BY k) INTO v_chiavi FROM jsonb_object_keys(v_riga) AS k;
            v_ignote := ARRAY(SELECT unnest(v_chiavi) EXCEPT SELECT unnest(v_colonne));
            IF cardinality(v_ignote) > 0 THEN
                RAISE EXCEPTION 'colonne sconosciute in %: %', p_tabella, v_ignote USING ERRCODE = '42703';
            END IF;
            IF NOT (p_conflitto <@ v_chiavi) THEN
                RAISE EXCEPTION 'manca la chiave naturale %', p_conflitto USING ERRCODE = '22023';
            END IF;
            v_ver := NULL;
            IF p_versioni IS NOT NULL AND jsonb_typeof(p_versioni) = 'array'
               AND jsonb_typeof(p_versioni -> (v_el.ord::int - 1)) = 'number' THEN
                v_ver := (p_versioni ->> (v_el.ord::int - 1))::bigint;
            END IF;
            v_guardia := p_origine IS NOT NULL AND v_ver IS NOT NULL AND p_op <> 'insert';
            v_esito := NULL;
            IF v_guardia THEN
                -- chiave canonica: i valori con il TIPO della colonna (1 e '1' di un bigint coincidono)
                EXECUTE format('SELECT jsonb_build_array(%s) FROM jsonb_populate_record(NULL::public.%I, $1) AS r',
                               v_kcol, p_tabella) INTO v_k USING v_riga;
                SELECT pv.versione INTO v_prec FROM public.postino_versioni pv
                WHERE pv.tabella = p_tabella AND pv.chiave = v_k AND pv.origine = p_origine FOR UPDATE;
                IF FOUND AND v_prec > v_ver THEN
                    v_esito := 'vecchia';
                ELSIF FOUND AND v_prec = v_ver THEN
                    v_esito := 'ignorata';
                END IF;
            END IF;

            IF v_esito IS NULL THEN
                v_lista := (SELECT string_agg(format('%I', c), ', ') FROM unnest(v_chiavi) AS c);
                v_sel := (SELECT string_agg(format('r.%I', c), ', ') FROM unnest(v_chiavi) AS c);
                v_nonchiave := ARRAY(SELECT unnest(v_chiavi) EXCEPT SELECT unnest(p_conflitto));

                IF p_op = 'insert' OR (p_op = 'upsert' AND cardinality(v_nonchiave) = 0) THEN
                    v_sql := format('INSERT INTO public.%I AS t (%s) SELECT %s FROM jsonb_populate_record(NULL::public.%I, $1) AS r '
                                    'ON CONFLICT (%s) DO NOTHING', p_tabella, v_lista, v_sel, p_tabella, v_conf);
                ELSIF p_op = 'upsert' THEN
                    -- come l'upsert di PostgREST di oggi: le colonne scritte vincono, le altre restano
                    v_set := (SELECT string_agg(format('%1$I = EXCLUDED.%1$I', c), ', ') FROM unnest(v_nonchiave) AS c);
                    v_sql := format('INSERT INTO public.%I AS t (%s) SELECT %s FROM jsonb_populate_record(NULL::public.%I, $1) AS r '
                                    'ON CONFLICT (%s) DO UPDATE SET %s', p_tabella, v_lista, v_sel, p_tabella, v_conf, v_set);
                ELSIF p_op = 'patch' THEN
                    IF cardinality(v_nonchiave) = 0 THEN
                        RAISE EXCEPTION 'patch senza colonne da cambiare' USING ERRCODE = '22023';
                    END IF;
                    v_set := (SELECT string_agg(format('%1$I = r.%1$I', c), ', ') FROM unnest(v_nonchiave) AS c);
                    v_sql := format('UPDATE public.%I AS t SET %s FROM jsonb_populate_record(NULL::public.%I, $1) AS r WHERE %s',
                                    p_tabella, v_set, p_tabella, v_dove);
                ELSE
                    v_sql := format('DELETE FROM public.%I AS t USING jsonb_populate_record(NULL::public.%I, $1) AS r WHERE %s',
                                    p_tabella, p_tabella, v_dove);
                END IF;
                EXECUTE v_sql USING v_riga;
                GET DIAGNOSTICS v_n = ROW_COUNT;
                v_esito := CASE WHEN v_n > 0 THEN 'ok' ELSE 'ignorata' END;
                IF v_guardia THEN
                    -- nella STESSA sottotransazione della riga: se la riga fallisce, la versione non resta
                    INSERT INTO public.postino_versioni AS pv (tabella, chiave, origine, versione, aggiornato)
                    VALUES (p_tabella, v_k, p_origine, v_ver, now())
                    ON CONFLICT (tabella, chiave, origine) DO UPDATE
                        SET versione = greatest(pv.versione, EXCLUDED.versione), aggiornato = now();
                END IF;
            END IF;
            v_esiti := v_esiti || jsonb_build_array(jsonb_build_object('esito', v_esito));
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS v_stato = RETURNED_SQLSTATE, v_msg = MESSAGE_TEXT;
            v_esiti := v_esiti || jsonb_build_array(jsonb_build_object(
                'esito', 'errore', 'codice', v_stato, 'messaggio', left(v_msg, 500)));
        END;
    END LOOP;
    RETURN v_esiti;
END $$;

REVOKE ALL ON FUNCTION public.postino_consegna(text, text, text[], jsonb, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.postino_consegna(text, text, text[], jsonb, text, jsonb) TO service_role;

-- ============================================================================
-- 5. RPC postino_impronte (riconciliazione notturna)
-- ============================================================================
-- Coppie [chiave, versione] di `p_tabella`: le righe con `p_colonna_tempo` in [p_da, p_a)
-- (chiave non NULL: le righe dei vecchi scrittori senza uid restano fuori) PIU' le righe
-- le cui chiavi sono in `p_chiavi` (array di array, una per chiave). La chiave e'
-- jsonb_build_array(colonne della chiave naturale), la versione to_jsonb(p_rev) o null.
CREATE OR REPLACE FUNCTION public.postino_impronte(
    p_tabella       text,
    p_chiave        text[],
    p_rev           text DEFAULT NULL,
    p_colonna_tempo text DEFAULT NULL,
    p_da            timestamptz DEFAULT NULL,
    p_a             timestamptz DEFAULT NULL,
    p_chiavi        jsonb DEFAULT '[]'::jsonb)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rel     regclass;
    v_colonne text[];
    v_k       text;
    v_rv      text;
    v_nonnull text;
    v_cond    text[] := ARRAY[]::text[];
    v_out     jsonb;
BEGIN
    v_rel := to_regclass(format('public.%I', p_tabella));
    IF v_rel IS NULL THEN
        RAISE EXCEPTION 'postino_impronte: tabella public.% assente', p_tabella USING ERRCODE = '42P01';
    END IF;
    SELECT array_agg(a.attname::text) INTO v_colonne
    FROM pg_attribute a WHERE a.attrelid = v_rel AND a.attnum > 0 AND NOT a.attisdropped;
    IF coalesce(cardinality(p_chiave), 0) = 0 OR NOT (p_chiave <@ v_colonne)
       OR (p_rev IS NOT NULL AND NOT (p_rev = ANY (v_colonne)))
       OR (p_colonna_tempo IS NOT NULL AND NOT (p_colonna_tempo = ANY (v_colonne))) THEN
        RAISE EXCEPTION 'postino_impronte: colonne non valide per %', p_tabella USING ERRCODE = '42703';
    END IF;
    v_k := format('jsonb_build_array(%s)', (SELECT string_agg(format('t.%I', c), ', ') FROM unnest(p_chiave) AS c));
    v_rv := CASE WHEN p_rev IS NULL THEN 'NULL::jsonb' ELSE format('to_jsonb(t.%I)', p_rev) END;
    v_nonnull := (SELECT string_agg(format('t.%I IS NOT NULL', c), ' AND ') FROM unnest(p_chiave) AS c);
    IF p_colonna_tempo IS NOT NULL AND p_da IS NOT NULL THEN
        v_cond := v_cond || format('(t.%1$I >= $1 AND ($2::timestamptz IS NULL OR t.%1$I < $2) AND %2$s)',
                                   p_colonna_tempo, v_nonnull);
    END IF;
    IF p_chiavi IS NOT NULL AND jsonb_typeof(p_chiavi) = 'array' AND jsonb_array_length(p_chiavi) > 0 THEN
        v_cond := v_cond || format('(%s IN (SELECT e.value FROM jsonb_array_elements($3) AS e))', v_k);
    END IF;
    IF cardinality(v_cond) = 0 THEN
        RETURN '[]'::jsonb;
    END IF;
    EXECUTE format('SELECT coalesce(jsonb_agg(jsonb_build_array(%s, %s)), ''[]''::jsonb) FROM public.%I AS t WHERE %s',
                   v_k, v_rv, p_tabella, array_to_string(v_cond, ' OR '))
        INTO v_out USING p_da, p_a, p_chiavi;
    RETURN v_out;
END $$;

REVOKE ALL ON FUNCTION public.postino_impronte(text, text[], text, text, timestamptz, timestamptz, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.postino_impronte(text, text[], text, text, timestamptz, timestamptz, jsonb)
    TO service_role;

-- ============================================================================
-- 6. RPC postino_confronta_ombra (criterio di T8)
-- ============================================================================
-- Conteggio per (giorno UTC di p_colonna_tempo, p_gruppo...) nella tabella vera e nella sua
-- ombra, finestra [p_da, p_a). Ritorna SOLO i gruppi con conteggi diversi:
-- [{"giorno": "...", "gruppo": [...], "vera": n, "ombra": m}]. Vuoto = +/- 0.
CREATE OR REPLACE FUNCTION public.postino_confronta_ombra(
    p_tabella       text,
    p_gruppo        text[],
    p_colonna_tempo text,
    p_da            timestamptz,
    p_a             timestamptz)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rel     regclass;
    v_ombra   regclass;
    v_colonne text[];
    v_g       text;
    v_sql     text;
    v_out     jsonb;
BEGIN
    v_rel := to_regclass(format('public.%I', p_tabella));
    v_ombra := to_regclass(format('public.%I', p_tabella || '_ombra'));
    IF v_rel IS NULL OR v_ombra IS NULL THEN
        RAISE EXCEPTION 'postino_confronta_ombra: % o la sua ombra assente', p_tabella USING ERRCODE = '42P01';
    END IF;
    SELECT array_agg(a.attname::text) INTO v_colonne
    FROM pg_attribute a WHERE a.attrelid = v_rel AND a.attnum > 0 AND NOT a.attisdropped;
    IF NOT (coalesce(p_gruppo, ARRAY[]::text[]) <@ v_colonne) OR NOT (p_colonna_tempo = ANY (v_colonne)) THEN
        RAISE EXCEPTION 'postino_confronta_ombra: colonne non valide per %', p_tabella USING ERRCODE = '42703';
    END IF;
    v_g := coalesce((SELECT string_agg(format('t.%I', c), ', ') FROM unnest(p_gruppo) AS c), '');
    v_sql := format(
        'WITH v AS (SELECT (t.%1$I AT TIME ZONE ''UTC'')::date AS giorno, jsonb_build_array(%2$s) AS gruppo, count(*) AS n '
        '           FROM public.%3$I AS t WHERE t.%1$I >= $1 AND t.%1$I < $2 GROUP BY 1, 2), '
        '     o AS (SELECT (t.%1$I AT TIME ZONE ''UTC'')::date AS giorno, jsonb_build_array(%2$s) AS gruppo, count(*) AS n '
        '           FROM public.%4$I AS t WHERE t.%1$I >= $1 AND t.%1$I < $2 GROUP BY 1, 2) '
        'SELECT coalesce(jsonb_agg(jsonb_build_object(''giorno'', coalesce(v.giorno, o.giorno), '
        '       ''gruppo'', coalesce(v.gruppo, o.gruppo), ''vera'', coalesce(v.n, 0), ''ombra'', coalesce(o.n, 0)) '
        '       ORDER BY coalesce(v.giorno, o.giorno)), ''[]''::jsonb) '
        'FROM v FULL OUTER JOIN o ON v.giorno = o.giorno AND v.gruppo = o.gruppo '
        'WHERE coalesce(v.n, 0) <> coalesce(o.n, 0)',
        p_colonna_tempo, v_g, p_tabella, p_tabella || '_ombra');
    EXECUTE v_sql INTO v_out USING p_da, p_a;
    RETURN v_out;
END $$;

REVOKE ALL ON FUNCTION public.postino_confronta_ombra(text, text[], text, timestamptz, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.postino_confronta_ombra(text, text[], text, timestamptz, timestamptz)
    TO service_role;

-- PostgREST rilegge lo schema (le RPC nuove diventano visibili subito)
NOTIFY pgrst, 'reload schema';
