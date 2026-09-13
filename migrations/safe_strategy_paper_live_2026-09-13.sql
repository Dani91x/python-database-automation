-- ============================================================================
-- SAFE STRATEGY — paper e live non devono MAI stare nello stesso numero
-- (13/09/2026, certificazione della sezione "Safe Strategy")
-- ============================================================================
-- IL PROBLEMA. La colonna ``safe_strategy_trades.mode`` esiste dal primo giorno
-- (``safe_strategy_bot.sql``) e fino a oggi NESSUNA query la leggeva. Il
-- risultato è che tutto ciò che il trader guarda — e tutto ciò su cui il bot
-- DECIDE — sommava le posizioni finte con quelle vere:
--
--   * «P&L oggi» e «P&L totale» in cima alla sezione: una settimana di paper
--     vincente gonfia il totale di un conto che non ha guadagnato un euro;
--   * «Liability aperta» e i cap di ``risk.py``: una giornata paper negativa
--     consuma ``daily_loss_stop`` e FERMA il bot vero; al contrario, profitti
--     paper mascherano perdite reali e tengono aperto il rubinetto;
--   * lo storico per giornata: i mesi di collaudo restano dentro il «P&L
--     totale» per sempre;
--   * l'IDEMPOTENZA: ``uq_safe_trades_signal`` non contiene ``mode``, quindi un
--     trade PAPER su un segnale impediva il trade LIVE sullo stesso segnale —
--     passando in live il bot saltava in silenzio tutto ciò che aveva appena
--     finito di collaudare.
--
-- Il backend Python è già stato corretto (``Betfair/safe_strategy/bot_db.py``:
-- ``aggregates``/``open_trades``/``traded_signal_keys``/
-- ``trade_by_idempotency_key`` accettano ``mode`` e ripiegano sulla scansione
-- Python quando la RPC non accetta il parametro). Questo file è la parte SQL.
--
-- ALTRI DUE BUCHI DELLA STESSA CERTIFICAZIONE, chiusi qui:
--
--   * DOPPIA CHIUSURA. L'unico indice unico esclude le gambe di chiusura, così
--     due processi (o due istanze dell'app aperte insieme) possono riservare
--     DUE chiusure per la stessa apertura: invece di chiudere la posizione la
--     INVERTONO, e il trader si ritrova esposto dalla parte opposta.
--   * MODALITÀ A BOT FERMO. ``safe_stop()`` lasciava ``control.mode`` a 'live':
--     chi riapre l'app il giorno dopo e preme Avvia manda il bot a piazzare con
--     SOLDI VERI senza aver toccato niente. E a bot fermo la modalità viveva
--     solo in uno ``useState`` del browser: nessun'altra sessione (e nemmeno il
--     servizio) poteva sapere in che modalità si trovasse la sezione.
--
-- SCELTA DI RETROCOMPATIBILITÀ (vale per TUTTE le RPC toccate qui).
-- ``p_mode`` è un parametro OPZIONALE e ``NULL`` significa «tutte le modalità»,
-- cioè esattamente il comportamento di oggi. Chi chiama senza argomenti
-- (``rpc('get_safe_aggregates', {})`` del Python e della UI attuale, la suite
-- ``frontend/src/certification/migrations.cert.test.ts``,
-- ``Betfair/tools/verifica_pnl_2026_09_12.py``) continua a funzionare senza una
-- riga di modifica. Per non lasciare comunque il trader al buio, gli aggregati
-- restituiscono SEMPRE anche ``realized_paper_total`` / ``realized_live_total``
-- e la chiave ``mode`` (quale filtro è stato applicato: ``null`` = tutte), così
-- la separazione si vede a schermo anche prima che la UI passi ``p_mode``.
--
-- ATTENZIONE ALL'OVERLOAD (è l'errore che ha già rotto lo storico di Mike,
-- 42725 «function ... is not unique», vedi mike_history_v2.sql punto R2).
-- Aggiungere un parametro con DEFAULT NON basta: finché in ``pg_proc`` resta
-- anche la firma vecchia senza parametro, una chiamata a zero argomenti ha DUE
-- candidati e Postgres si rifiuta di scegliere. Per questo ogni funzione qui è
-- preceduta dal ``DROP FUNCTION IF EXISTS`` della firma ESATTA precedente, e in
-- fondo al file c'è una verifica che ne sia rimasta UNA SOLA per nome.
--
-- IDEMPOTENTE e rieseguibile: ``CREATE OR REPLACE``, ``IF NOT EXISTS``,
-- ``DROP ... IF EXISTS`` con firme esatte (alla seconda esecuzione i DROP delle
-- firme vecchie sono no-op: quelle firme non esistono più). NON tocca dati:
-- nessun DELETE, nessun TRUNCATE, nessun DROP TABLE, nessun DROP COLUMN.
--
-- ORDINE DI APPLICAZIONE — DOPO:
--    1. betfair_live_order_queue.sql   (betfair_live_is_owner)
--    2. safe_strategy_scan.sql
--    3. safe_strategy_bot.sql
--    4. daily_history.sql
--    5. omega_daily_v2.sql             (trading_daily_history a 8/4 argomenti)
--    6. mike_history_v2.sql            (UNA sola firma delle funzioni condivise)
--    7. safe_strategy_bot_v2.sql
--    8. safe_strategy_paper_live_2026-09-13.sql   ← QUESTO FILE
--
-- ⚠️ SE IN FUTURO SI RIAPPLICA ``safe_strategy_bot_v2.sql`` (o
-- ``safe_strategy_bot.sql``, o ``daily_history.sql``, o ``omega_daily_v2.sql``)
-- tornano in vita le firme SENZA ``p_mode`` e l'overload ambiguo rinasce:
-- riapplicare SUBITO DOPO anche questo file. È la stessa avvertenza già scritta
-- in APPLY_ORDER_2026-09-11.md per trading_daily_history/trading_day_trades.
--
-- VERIFICA dopo l'applicazione (in fondo al file c'è anche un controllo
-- automatico che solleva un'eccezione parlante se qualcosa è rimasto doppio):
--   SELECT public.get_safe_aggregates();          -- tutte le modalità (come oggi)
--   SELECT public.get_safe_aggregates('live');    -- SOLO soldi veri
--   SELECT public.get_safe_aggregates('paper');   -- SOLO simulato
--   SELECT public.safe_set_mode('paper');         -- modalità persistita a bot fermo
--   SELECT indexdef FROM pg_indexes
--    WHERE indexname IN ('uq_safe_trades_signal_mode','uq_safe_trades_closing_inflight');
-- ============================================================================


-- ############################################################################
-- 1. INDICI — le due corse che possono costare soldi veri
-- ############################################################################

-- ----------------------------------------------------------------------------
-- 1.a UNA SOLA CHIUSURA IN VOLO PER APERTURA.
--
-- PERCHÉ ``status = 'pending'`` E NIENT'ALTRO.
-- Il ciclo di vita di una gamba di chiusura (``execution.cash_out``) è:
--   'pending'  → riga RISERVATA prima del piazzamento (reserve-first): l'ordine
--                può esistere a mercato o no, l'esito del fill è IGNOTO;
--   'open'     → fill CONFERMATO (la copertura è avvenuta, per intero o in
--                parte: l'apertura passa a 'hedged' solo a residuo nullo);
--   'error'    → chiusura fallita in modo terminale;
--   'won'/'lost'/'void' → regolata col mercato.
--
-- «In volo» = 'pending', e SOLO 'pending'. È l'unica finestra in cui una
-- seconda chiusura è un errore certo: due riserve contemporanee sulla stessa
-- apertura non la chiudono, la INVERTONO (si vende due volte la stessa
-- posizione e si finisce esposti dal lato opposto). Fuori da quella finestra
-- una nuova chiusura è una DECISIONE, non una corsa: il cash-out PARZIALE
-- ripetuto — coprire un pezzo adesso e il resto più tardi, o chiudere il
-- residuo lasciato da una size cappata — è una funzione che esiste e va
-- protetta (``execution.cash_out`` calcola il piano sul RESIDUO, e
-- ``safe_request`` accetta ``fraction`` proprio come frazione del residuo).
-- Includere anche 'open' nell'indice l'avrebbe uccisa: la prima chiusura resta
-- 'open' fino al settlement del mercato, cioè per ORE.
-- Escludere 'error' è automatico ('error' <> 'pending'): una chiusura fallita
-- deve restare ritentabile, altrimenti la posizione resterebbe scoperta.
--
-- L'indice duplica in DB una barriera che l'applicazione già prova a mettere
-- (``useSafeBot.isCashOutPending`` a schermo, ``meta.hedging`` nel servizio):
-- la differenza è che quelle barriere vivono in UN processo, questa vale per
-- tutti — due istanze dell'app, il servizio e la UI, o due tab aperte insieme.
-- ----------------------------------------------------------------------------
DO $mig$
DECLARE
    v_dup integer;
BEGIN
    -- Non si può creare un indice unico su dati che lo violano già: la CREATE
    -- fallirebbe e porterebbe con sé TUTTA la migrazione. Quindi prima si
    -- guarda, e se il caso patologico esiste davvero si avvisa e si prosegue —
    -- meglio una migrazione applicata senza QUESTO indice che una migrazione
    -- applicata a metà.
    SELECT count(*) INTO v_dup FROM (
        SELECT closes_trade_id
          FROM public.safe_strategy_trades
         WHERE closes_trade_id IS NOT NULL AND status = 'pending'
         GROUP BY closes_trade_id
        HAVING count(*) > 1
    ) x;

    IF v_dup > 0 THEN
        RAISE WARNING 'uq_safe_trades_closing_inflight NON creato: esistono già % aperture con più di una chiusura ''pending'' (posizioni potenzialmente INVERTITE, da sanare a mano prima di riprovare). Diagnosi: SELECT closes_trade_id, array_agg(id) FROM public.safe_strategy_trades WHERE closes_trade_id IS NOT NULL AND status = ''pending'' GROUP BY 1 HAVING count(*) > 1;', v_dup;
    ELSE
        BEGIN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_safe_trades_closing_inflight
                ON public.safe_strategy_trades (closes_trade_id)
                WHERE closes_trade_id IS NOT NULL AND status = 'pending';
        EXCEPTION WHEN unique_violation THEN
            -- corsa fra il conteggio qui sopra e la CREATE (il bot sta girando):
            -- non è un motivo per far fallire la migrazione.
            RAISE WARNING 'uq_safe_trades_closing_inflight non creato (conflitto durante la creazione): rieseguire questo file a bot fermo.';
        END;
    END IF;
END
$mig$;

-- ----------------------------------------------------------------------------
-- 1.b IDEMPOTENZA SEPARATA PER MODALITÀ.
--
-- ``uq_safe_trades_signal`` (event_id, coalesce(signal_key,'')) non contiene
-- ``mode``: il primo trade su un segnale — anche se PAPER — bruciava il segnale
-- per sempre, live compreso. Cioè: il giorno in cui si passa ai soldi veri il
-- bot NON entra su nulla di quello che ha appena collaudato, e lo fa in
-- silenzio (il servizio logga ``already_reserved`` e tira dritto).
--
-- PERCHÉ NON PUÒ FALLIRE A METÀ: il nuovo indice è strettamente PIÙ DEBOLE del
-- vecchio (stesse colonne più una). Qualunque riga che oggi soddisfa il vecchio
-- — e le soddisfa tutte, visto che il vecchio è attivo e le sta imponendo —
-- soddisfa anche il nuovo. Quindi si CREA PRIMA il nuovo e si TOGLIE DOPO il
-- vecchio, e solo se il nuovo c'è davvero: nel peggiore dei casi restano
-- entrambi (idempotenza più stretta di quella voluta, ma MAI un buco in cui
-- due riserve passano insieme).
-- ----------------------------------------------------------------------------
-- Il ragionamento «non può fallire» regge finché il vecchio indice è davvero
-- lì a imporre il vincolo. Se qualcuno l'avesse già rimosso a mano, righe
-- duplicate potrebbero esistere e la CREATE porterebbe giù tutta la migrazione:
-- quindi si guarda prima, esattamente come per la chiusura in volo.
DO $mig$
DECLARE
    v_dup integer;
BEGIN
    SELECT count(*) INTO v_dup FROM (
        SELECT event_id, coalesce(signal_key, '') AS k, mode
          FROM public.safe_strategy_trades
         WHERE origin = 'auto' AND status <> 'error' AND closes_trade_id IS NULL
         GROUP BY event_id, coalesce(signal_key, ''), mode
        HAVING count(*) > 1
    ) x;

    IF v_dup > 0 THEN
        RAISE WARNING 'uq_safe_trades_signal_mode NON creato: esistono già % chiavi (event_id, signal_key, mode) duplicate fra i trade automatici non in errore. uq_safe_trades_signal resta al suo posto (idempotenza condivisa fra paper e live). Diagnosi: SELECT event_id, coalesce(signal_key, ''''), mode, array_agg(id) FROM public.safe_strategy_trades WHERE origin = ''auto'' AND status <> ''error'' AND closes_trade_id IS NULL GROUP BY 1,2,3 HAVING count(*) > 1;', v_dup;
    ELSE
        BEGIN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_safe_trades_signal_mode
                ON public.safe_strategy_trades (event_id, coalesce(signal_key, ''), mode)
                WHERE origin = 'auto' AND status <> 'error' AND closes_trade_id IS NULL;
        EXCEPTION WHEN unique_violation THEN
            RAISE WARNING 'uq_safe_trades_signal_mode non creato (conflitto durante la creazione): rieseguire questo file a bot fermo.';
        END;
    END IF;

    -- il vecchio esce di scena SOLO se il nuovo c'è davvero: nel dubbio si
    -- resta con l'idempotenza più stretta, mai senza.
    IF EXISTS (SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public'
                 AND c.relname = 'uq_safe_trades_signal_mode'
                 AND c.relkind = 'i') THEN
        DROP INDEX IF EXISTS public.uq_safe_trades_signal;
    ELSE
        RAISE WARNING 'uq_safe_trades_signal_mode assente: uq_safe_trades_signal NON rimosso (l''idempotenza resta quella vecchia, condivisa fra paper e live).';
    END IF;
END
$mig$;

-- Indice di servizio per il filtro di modalità sulle letture di giornata
-- (aggregati, tab Trade, storico): senza, ogni lettura filtrata resta una
-- scansione completa della tabella.
CREATE INDEX IF NOT EXISTS idx_safe_trades_mode_placed
    ON public.safe_strategy_trades (mode, placed_at DESC);


-- ############################################################################
-- 2. AGGREGATI PER MODALITÀ
-- ############################################################################

-- Via le firme SENZA argomento: se restassero, ``safe_aggregates_sql()`` e
-- ``get_safe_aggregates()`` diventerebbero ambigue fra la vecchia a zero
-- argomenti e la nuova con DEFAULT NULL (42725 «is not unique»), ed è proprio
-- la chiamata a zero argomenti che fanno OGGI il Python e la UI.
DROP FUNCTION IF EXISTS public.safe_aggregates_sql();
DROP FUNCTION IF EXISTS public.get_safe_aggregates();

-- ----------------------------------------------------------------------------
-- Specchio ESATTO di ``bot_db.aggregate_rows`` (stessa matematica in due posti:
-- qui per la UI, in Python per il motore di rischio), con in più il filtro di
-- modalità. Il corpo è quello di safe_strategy_bot_v2.sql: l'unica cosa che
-- cambia è CHI entra nel conto.
--
-- ``p_mode``: NULL/'' = tutte le modalità (comportamento storico, nessun
-- chiamante rotto); 'paper'/'live' = solo quella. Un valore diverso non fa
-- passare nulla (zero righe, aggregati a zero) invece di mescolare: qui non si
-- può sollevare un'eccezione (LANGUAGE sql), ma «non rispondo» è sempre meglio
-- di «ti rispondo sommando i soldi veri a quelli finti». La validazione con
-- messaggio parlante sta nel chiamante owner-only, subito sotto.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_aggregates_sql(p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    WITH d AS (
        SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Rome')
                AT TIME ZONE 'Europe/Rome') AS v_day,
               nullif(lower(btrim(coalesce(p_mode, ''))), '') AS v_mode
    ), t AS (
        SELECT o.id, o.status, o.pnl::numeric AS pnl, o.event_id, o.closes_trade_id,
               o.strategy,
               -- M-26 + review C1/M10: liability RESIDUA dopo la copertura.
               -- 0 SOLO se la copertura e' COMPLETA e CONFERMATA (residuo <= 1c
               -- e nessuna gamba in volo). IGNOTO = PIENO: senza worst_case
               -- (nessuna chiusura fillata: ordine ancora in coda) o senza
               -- residual_size il rischio e' tutto ancora a mercato.
               CASE
                 WHEN (o.meta->'hedge'->>'remaining_liability') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      THEN greatest(0, (o.meta->'hedge'->>'remaining_liability')::numeric)
                 WHEN (o.meta->>'hedged_size') IS NOT NULL
                      AND (o.meta->>'residual_size') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      AND (o.meta->>'residual_size')::numeric <= 0.01
                      AND coalesce(jsonb_array_length(
                            CASE WHEN jsonb_typeof(o.meta->'hedge_pending_ids') = 'array'
                                 THEN o.meta->'hedge_pending_ids' END), 0) = 0 THEN 0
                 WHEN (o.meta->>'hedged_size') IS NOT NULL
                      AND (o.meta->>'residual_size') IS NOT NULL
                      AND (o.meta->>'worst_case') ~ '^-?[0-9]+(\.[0-9]+)?$'
                      THEN greatest(0, -(o.meta->>'worst_case')::numeric)
                 ELSE greatest(0, coalesce(o.liability, 0)::numeric)
               END AS liability,
               -- review H1: capitale IMPEGNATO nella giornata = liability
               -- d'apertura SEMPRE (coprire una posizione NON libera il cap)
               greatest(0, coalesce(o.liability, 0)::numeric) AS committed,
               -- ordine (potenzialmente) a mercato: conta nell'esposizione
               (o.bet_id IS NOT NULL
                OR (o.meta->>'flumine_client_ref') IS NOT NULL
                OR (o.meta->>'reason') = 'place_exception_reconciling') AS is_placed,
               -- H-03: 'pending' a esito IGNOTO (riconciliazione in corso)
               (o.status = 'pending'
                AND (o.meta->>'reason') = 'place_exception_reconciling') AS is_reconciling,
               -- C-01: giorno della POSIZIONE = piazzamento dell'APERTURA
               coalesce(p.placed_at, o.placed_at) AS pos_placed_at,
               o.placed_at,
               -- M-16: esito della POSIZIONE per SEGNO del P&L totale.
               -- M5: LATERAL aggregato (una passata sull'indice) invece di una
               -- sotto-query correlata per riga.
               CASE WHEN o.closes_trade_id IS NULL AND o.status IN ('won','lost','void') THEN
                    o.pnl + coalesce(cl.pnl_sum, 0)
               END AS total_pnl
          FROM public.safe_strategy_trades o
          LEFT JOIN public.safe_strategy_trades p ON p.id = o.closes_trade_id
          LEFT JOIN LATERAL (
              SELECT sum(c.pnl)::numeric AS pnl_sum
                FROM public.safe_strategy_trades c
               WHERE c.closes_trade_id = o.id
                 AND c.status IN ('won','lost','void')
                 -- per costruzione una chiusura eredita la modalità della sua
                 -- apertura (execution.cash_out); il predicato lo rende
                 -- STRUTTURALE: nessuna via per cui un P&L paper finisca dentro
                 -- il totale di una posizione live.
                 AND c.mode = o.mode
          ) cl ON o.closes_trade_id IS NULL
         -- il filtro che mancava: mai paper e soldi veri nello stesso numero
         WHERE (SELECT v_mode FROM d) IS NULL
            OR o.mode = (SELECT v_mode FROM d)
    ), altro AS (
        -- i realizzati di ENTRAMBE le modalità, SEMPRE (mai filtrati): la UI
        -- può mostrare l'altra faccia senza una seconda chiamata, e nessuno dei
        -- due mondi resta invisibile a chi legge un totale.
        SELECT coalesce(sum(x.pnl) FILTER (WHERE x.mode = 'paper'), 0) AS realized_paper,
               coalesce(sum(x.pnl) FILTER (WHERE x.mode = 'live'), 0)  AS realized_live
          FROM public.safe_strategy_trades x
         WHERE x.status IN ('won','lost','void')
    )
    SELECT jsonb_build_object(
        -- quale filtro è stato applicato: null = tutte le modalità. Chi legge
        -- un numero deve poter sapere di che soldi sta parlando.
        'mode',           d.v_mode,
        'realized_total', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')), 0),
        'realized_today', coalesce(sum(t.pnl) FILTER (WHERE t.status IN ('won','lost','void')
                              AND t.pos_placed_at >= d.v_day), 0),
        'realized_paper_total', (SELECT realized_paper FROM altro),
        'realized_live_total',  (SELECT realized_live  FROM altro),
        'open_liability', coalesce(sum(t.liability) FILTER (WHERE t.closes_trade_id IS NULL
                              AND (t.status IN ('open','hedged')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'open_count',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND (t.status IN ('open','hedged')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'reconciling_liability', coalesce(sum(t.liability) FILTER (
                              WHERE t.closes_trade_id IS NULL AND t.is_reconciling), 0),
        'reconciling_count',  count(*) FILTER (WHERE t.closes_trade_id IS NULL AND t.is_reconciling),
        -- CAPITALE IMPEGNATO nella giornata: base dei cap di risk.py (review
        -- H1: NON il residuo, altrimenti ogni green-up libera il cap)
        'day_liability',  coalesce(sum(t.committed) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'day_liability_model', coalesce(sum(t.committed) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND t.strategy = 'model'
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))), 0),
        'day_trades',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'legs_today',     count(*) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'events_today',   count(DISTINCT t.event_id) FILTER (WHERE t.closes_trade_id IS NULL
                              AND t.status <> 'void' AND t.pos_placed_at >= d.v_day
                              AND (t.status IN ('open','hedged','won','lost')
                                   OR (t.status = 'pending' AND t.is_placed))),
        'won',            count(*) FILTER (WHERE t.total_pnl > 0),
        'lost',           count(*) FILTER (WHERE t.total_pnl < 0),
        'won_today',      count(*) FILTER (WHERE t.total_pnl > 0 AND t.pos_placed_at >= d.v_day),
        'lost_today',     count(*) FILTER (WHERE t.total_pnl < 0 AND t.pos_placed_at >= d.v_day),
        'operating_day',  to_char(d.v_day AT TIME ZONE 'Europe/Rome', 'YYYY-MM-DD')
    )
      FROM d LEFT JOIN t ON true
     GROUP BY d.v_day, d.v_mode;
$$;
REVOKE ALL ON FUNCTION public.safe_aggregates_sql(text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.safe_aggregates_sql(text) TO service_role;

-- ----------------------------------------------------------------------------
-- RPC per il SERVIZIO e per la UI. Owner-only: senza il controllo, qualunque
-- utente autenticato leggerebbe l'esposizione del conto (M4).
-- ``get_safe_aggregates()`` e ``get_safe_aggregates('live')`` sono entrambe
-- valide: il DEFAULT risolve da solo e non esiste una seconda funzione con cui
-- l'overload possa diventare ambiguo (le firme vecchie sono state tolte sopra).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_aggregates(p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_mode text := nullif(lower(btrim(coalesce(p_mode, ''))), '');
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    -- un refuso nella modalità deve FERMARE la chiamata, non restituire in
    -- silenzio un aggregato vuoto che l'utente leggerebbe come "non ho nulla"
    IF v_mode IS NOT NULL AND v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
    END IF;
    RETURN public.safe_aggregates_sql(v_mode);
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_aggregates(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_aggregates(text) TO authenticated, service_role;


-- ############################################################################
-- 3. STATO, LISTA TRADE E STORICO — stesso trattamento
-- ############################################################################

DROP FUNCTION IF EXISTS public.get_safe_state();

-- ----------------------------------------------------------------------------
-- get_safe_state — stato completo per la dashboard.
-- Con ``p_mode`` filtra ANCHE la lista dei trade, non solo gli aggregati:
-- una tabella che mostra righe paper sotto un P&L live è un altro modo di
-- mescolare i due mondi, solo più subdolo.
-- ``activity`` NON è filtrata: il log del servizio contiene righe senza
-- modalità (feed cieco, parametri, errori di ciclo) e nasconderle a chi guarda
-- una modalità significherebbe nascondere proprio i guasti. Ogni riga scritta
-- dal servizio porta comunque ``payload.mode`` (bot_service.set_log_mode).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_safe_state(p_mode text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    c_activity integer := 80;
    v_mode     text := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_ctrl     jsonb;
    v_trades   jsonb;
    v_agg      jsonb;
    v_activity jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NOT NULL AND v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
    END IF;

    SELECT to_jsonb(c.*) INTO v_ctrl FROM public.safe_strategy_control c WHERE c.id = 1;

    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_trades
      FROM (SELECT t0.* FROM public.safe_strategy_trades t0
             WHERE v_mode IS NULL OR t0.mode = v_mode
             ORDER BY t0.placed_at DESC LIMIT 200) t;

    v_agg := public.safe_aggregates_sql(v_mode);

    -- H-16: il log del servizio (skip, risk_block, exit, exit_failed, settle,
    -- feed_blind, params_invalid...) era scritto e mai letto da nessuno.
    SELECT coalesce(jsonb_agg(to_jsonb(a.*) ORDER BY a.id DESC), '[]'::jsonb)
      INTO v_activity
      FROM (SELECT id, ts, kind, payload FROM public.safe_strategy_activity
             ORDER BY id DESC
             LIMIT c_activity) a;

    RETURN jsonb_build_object(
        'control',           v_ctrl,
        'trades',            v_trades,
        'aggregates',        v_agg,
        'activity',          v_activity,
        -- H-15: i parametri realmente in uso (il servizio li scrive in stats)
        'params_effective',  coalesce(v_ctrl->'stats'->'params_effective', 'null'::jsonb),
        'operating_day',     v_agg->'operating_day',
        -- quale modalità è stata filtrata (null = tutte). La modalità ATTIVA
        -- resta quella di ``control.mode``: sono due cose diverse e la UI non
        -- deve confonderle.
        'mode',              to_jsonb(v_mode)
    );
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_state(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_state(text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- get_safe_trades — è il FALLBACK della stessa tabella a schermo
-- (``fetchSafeTrades``, usato quando get_safe_state non porta righe): senza il
-- filtro, nel momento peggiore — quando la UI ripiega — tornerebbero righe
-- delle due modalità mischiate.
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.get_safe_trades(integer);
CREATE OR REPLACE FUNCTION public.get_safe_trades(
    p_limit integer DEFAULT 200,
    p_mode  text    DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode text := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_rows jsonb;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF v_mode IS NOT NULL AND v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(t.*) ORDER BY t.placed_at DESC), '[]'::jsonb)
      INTO v_rows
      FROM (SELECT t0.* FROM public.safe_strategy_trades t0
             WHERE v_mode IS NULL OR t0.mode = v_mode
             ORDER BY t0.placed_at DESC
             LIMIT least(greatest(coalesce(p_limit, 200), 1), 2000)) t;
    RETURN v_rows;
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_trades(integer,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_trades(integer,text) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- STORICO per giornata. Le funzioni CONDIVISE con Omega e Mike
-- (``trading_daily_history`` / ``trading_day_trades``) NON si toccano — è la
-- lezione di mike_history.sql: ridefinirle con firme diverse le rende ambigue e
-- rompe TUTTI i bot insieme. Il filtro di modalità viaggia dentro il parametro
-- che quelle funzioni già accettano, ``p_filter_expr``.
--
-- ATTENZIONE AGLI ALIAS (sono diversi fra le due funzioni condivise):
--   * trading_daily_history usa ``t`` sia per le aperture che per le chiusure;
--   * trading_day_trades usa ``o`` per le aperture (le chiusure le raccoglie
--     con un alias ``c`` interno, e per costruzione hanno la modalità della
--     loro apertura).
-- Il valore è già stato validato contro la whitelist prima di finire in
-- ``format(%L)``: nessuna via di iniezione nel frammento SQL.
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.get_safe_daily(date,date,text);
CREATE OR REPLACE FUNCTION public.get_safe_daily(
    p_from  date DEFAULT NULL,
    p_to    date DEFAULT NULL,
    p_sport text DEFAULT NULL,
    p_mode  text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_today  date   := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mode   text   := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_conds  text[] := ARRAY[]::text[];
    v_filter text   := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_conds := v_conds || format('t.sport = %L', p_sport);
    END IF;
    IF v_mode IS NOT NULL THEN
        IF v_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
        END IF;
        v_conds := v_conds || format('t.mode = %L', v_mode);
    END IF;
    IF array_length(v_conds, 1) > 0 THEN
        v_filter := array_to_string(v_conds, ' AND ');
    END IF;
    RETURN public.trading_daily_history(
        'safe_strategy_trades',
        $e$t.strategy$e$,
        $e$t.sport$e$,
        v_filter,
        coalesce(p_from, coalesce(p_to, v_today) - 90),
        coalesce(p_to, v_today),
        NULL,
        'placed');   -- C-01: giornata = giorno di PIAZZAMENTO
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_daily(date,date,text,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_daily(date,date,text,text) TO authenticated, service_role;

DROP FUNCTION IF EXISTS public.get_safe_day_trades(date,text);
CREATE OR REPLACE FUNCTION public.get_safe_day_trades(
    p_day   date,
    p_sport text DEFAULT NULL,
    p_mode  text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode   text   := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_conds  text[] := ARRAY[]::text[];
    v_filter text   := NULL;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_sport IS NOT NULL AND p_sport <> '' THEN
        IF p_sport NOT IN ('calcio', 'tennis') THEN
            RAISE EXCEPTION 'sport non valido: %', p_sport;
        END IF;
        v_conds := v_conds || format('o.sport = %L', p_sport);
    END IF;
    IF v_mode IS NOT NULL THEN
        IF v_mode NOT IN ('paper','live') THEN
            RAISE EXCEPTION 'modalità non valida: % (ammesse: paper, live, oppure nessun valore = tutte)', p_mode;
        END IF;
        v_conds := v_conds || format('o.mode = %L', v_mode);
    END IF;
    IF array_length(v_conds, 1) > 0 THEN
        v_filter := array_to_string(v_conds, ' AND ');
    END IF;
    RETURN public.trading_day_trades('safe_strategy_trades', v_filter, p_day, 'placed');
END;
$$;
REVOKE ALL    ON FUNCTION public.get_safe_day_trades(date,text,text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.get_safe_day_trades(date,text,text) TO authenticated, service_role;


-- ############################################################################
-- 4. LA MODALITÀ È UNO STATO DEL SISTEMA, NON UNA VARIABILE DEL BROWSER
-- ############################################################################

-- ----------------------------------------------------------------------------
-- 4.a safe_stop() riporta la modalità a 'paper'.
--
-- Perché è pericoloso non farlo: il control è un SINGLETON che sopravvive alla
-- chiusura dell'app. Fermando il bot in LIVE, ``mode`` restava 'live'; il
-- giorno dopo si riapre l'app, si preme Avvia (che passa la modalità del
-- browser, ma il servizio legge il DB) e si è di nuovo a piazzare con soldi
-- veri senza aver confermato niente. Il LIVE deve essere SEMPRE una scelta
-- esplicita e RECENTE, mai un'eredità.
--
-- Perché è sicuro farlo QUI, mentre lo stato è ancora 'stopping': le fasi di
-- PROTEZIONE del servizio (riconciliazione, settlement, uscite) NON usano
-- ``control.mode`` — ognuna lavora con la modalità della RIGA che sta trattando
-- (``trade['mode']``), quindi una posizione live aperta continua a essere
-- gestita in live anche dopo questa riscrittura. ``control.mode`` serve solo a
-- due cose: aprire NUOVE posizioni automatiche (e in 'stopping' non se ne apre
-- nessuna) e validare le richieste della UI (e rifiutare una richiesta LIVE
-- rimasta in coda mentre l'utente sta fermando il bot è esattamente ciò che si
-- vuole).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_stop()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE v_row public.safe_strategy_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    UPDATE public.safe_strategy_control SET
        status     = CASE WHEN status = 'running' THEN 'stopping' ELSE 'stopped' END,
        -- FAIL-SAFE: si riparte sempre da simulato. Per tornare in live serve
        -- un gesto nuovo (safe_set_mode o safe_activate('live')).
        mode       = 'paper',
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_stop() FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_stop() TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4.b safe_set_mode — persiste la modalità ANCHE a bot fermo.
--
-- Oggi, a bot fermo, la modalità vive SOLO in uno ``useState`` del browser
-- (``useSafeBot.desiredMode``): non esiste da nessun'altra parte. Conseguenze:
--   * un'altra sessione, un'altra tab, o chiunque guardi il DB non può sapere
--     in che modalità si trova la sezione;
--   * il backend, per validare una richiesta manuale, non ha un'autorità con
--     cui confrontarla: si fida di ciò che il client dichiara nel payload;
--   * un F5 la riporta a 'paper' senza dirlo, o — peggio — lascia la UI
--     convinta di una modalità diversa da quella che il servizio userà.
--
-- Stesse garanzie di ``safe_activate``: owner-only, whitelist del valore,
-- SECURITY DEFINER con ``search_path`` fissato. NON tocca ``status``: non
-- avvia e non ferma niente, dichiara soltanto in che modalità si opererà.
-- A bot in corsa il servizio la legge al ciclo successivo (2 s) — è lo stesso
-- effetto di ``safe_activate(mode)`` ma senza azzerare ``started_at``, i
-- parametri e l'eventuale errore.
--
-- NON scrive su ``safe_strategy_activity``: quel log ha una whitelist chiusa di
-- ``kind`` lato UI (``frontend/src/components/safestrategy/safeActivity.ts``,
-- «aggiungendone uno nuovo al backend va aggiunto QUI, con test»), e una
-- migrazione SQL non deve creare un badge senza etichetta. Il cambio resta
-- tracciato da ``updated_at`` e arriva a tutte le sessioni via Realtime, che
-- sul control è già attivo (safe_strategy_bot.sql).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.safe_set_mode(p_mode text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_mode text := nullif(lower(btrim(coalesce(p_mode, ''))), '');
    v_row  public.safe_strategy_control;
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    -- qui NULL non è "tutte le modalità": è una modalità mancante, e su una
    -- scelta paper/live il silenzio non è mai un valore accettabile.
    IF v_mode IS NULL OR v_mode NOT IN ('paper','live') THEN
        RAISE EXCEPTION 'mode non valido: % (ammessi: paper, live)', p_mode;
    END IF;
    UPDATE public.safe_strategy_control SET
        mode       = v_mode,
        updated_at = now()
    WHERE id = 1
    RETURNING * INTO v_row;
    RETURN to_jsonb(v_row);
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_set_mode(text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_set_mode(text) TO authenticated, service_role;


-- ############################################################################
-- 5. safe_request — la modalità della richiesta deve essere quella del control
-- ############################################################################
-- La modalità dichiarata nel payload è un'ASSERZIONE DEL CLIENT, non un
-- comando: l'autorità è ``safe_strategy_control.mode``. Il servizio Python fa
-- già questo controllo (``bot_service._request_place``, ``control_mode``), ma
-- lo fa al ciclo SUCCESSIVO e solo per chi passa da lì: il DB-as-bus accetta
-- richieste da qualunque altra via, e una richiesta LIVE accodata e poi
-- eseguita quando la sezione è in PAPER (o viceversa) è denaro vero mosso
-- mentre lo schermo dice un'altra cosa. La barriera deve stare ANCHE qui, dove
-- la richiesta nasce, così l'utente vede subito un errore invece di scoprire un
-- rifiuto minuti dopo.
--
-- Semantica IDENTICA al Python, per non creare due verità:
--   * 'place'  → modalità mancante = 'paper' (stesso default di
--                ``_request_place``), poi confronto con il control;
--   * 'cashout'/'cancel' → si controlla SOLO se la modalità è dichiarata: sono
--     comandi su un trade già esistente, che porta con sé la propria modalità.
-- Il resto della funzione è invariato rispetto a safe_strategy_bot_v2.sql.
-- ----------------------------------------------------------------------------
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
BEGIN
    IF NOT public.betfair_live_is_owner() THEN
        RAISE EXCEPTION 'non autorizzato (owner-only)';
    END IF;
    IF p_kind NOT IN ('place','cashout','cancel') THEN
        RAISE EXCEPTION 'kind non valido: %', p_kind;
    END IF;

    SELECT lower(btrim(c.mode)) INTO v_ctrl_mode
      FROM public.safe_strategy_control c WHERE c.id = 1;

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
        -- comando su un trade esistente: la modalità si controlla solo se c'è
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
       AND v_req_mode <> v_ctrl_mode THEN
        RAISE EXCEPTION 'modalità non corrispondente: la richiesta è in %, la sezione è in % — cambia modalità (e conferma il LIVE) prima di riprovare',
                        upper(v_req_mode), upper(v_ctrl_mode);
    END IF;

    INSERT INTO public.safe_strategy_requests (kind, payload)
    VALUES (p_kind, v_payload)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL    ON FUNCTION public.safe_request(text,jsonb) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.safe_request(text,jsonb) TO authenticated, service_role;


-- ############################################################################
-- 6. VERIFICA FINALE — mai uno stato ambiguo silenzioso
-- ############################################################################
-- Stesso pattern di omega_models_v6.sql (S-05): se di una di queste funzioni
-- restasse più di una firma, le chiamate a zero/pochi argomenti fallirebbero
-- con 42725 «is not unique» e la sezione mostrerebbe un codice nudo. Meglio
-- accorgersene ADESSO, con il rimedio scritto nel messaggio.
DO $mig$
DECLARE
    v_name text;
    v_n    integer;
BEGIN
    FOREACH v_name IN ARRAY ARRAY['safe_aggregates_sql','get_safe_aggregates',
                                  'get_safe_state','get_safe_trades',
                                  'get_safe_daily','get_safe_day_trades',
                                  'safe_stop','safe_set_mode','safe_request'] LOOP
        SELECT count(*) INTO v_n
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.proname = v_name;
        IF v_n <> 1 THEN
            -- NB: in RAISE il solo segnaposto è ``%`` (niente %I/%L: verrebbero
            -- stampati come una ''L'' di troppo dopo la sostituzione).
            RAISE EXCEPTION 'public.% ha % firme invece di 1: overload ambiguo (42725 alla prossima chiamata). Rimedio: elencarle con  SELECT oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = ''public'' AND p.proname = ''%'';  poi DROP FUNCTION di tutte tranne quella con p_mode creata da safe_strategy_paper_live_2026-09-13.sql, e rieseguire questo file.',
                            v_name, v_n, v_name;
        END IF;
    END LOOP;

    -- gli indici che proteggono i soldi: se mancano si deve sapere subito
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public' AND indexname = 'uq_safe_trades_signal_mode') THEN
        RAISE WARNING 'uq_safe_trades_signal_mode ASSENTE: paper e live condividono ancora lo spazio di idempotenza dei segnali.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public' AND indexname = 'uq_safe_trades_closing_inflight') THEN
        RAISE WARNING 'uq_safe_trades_closing_inflight ASSENTE: due chiusure contemporanee sulla stessa apertura restano possibili (rischio di INVERTIRE la posizione).';
    END IF;
END
$mig$;
