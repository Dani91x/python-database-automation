-- ============================================================================
-- sanatorie_2026-09-28.sql
-- Cantiere I "SANATORIE SQL E POSIZIONE FANTASMA" (ordine dell'utente, 28/09/2026)
-- ============================================================================
-- Verificato in SOLA LETTURA sul DB Supabase dqbwaocvlzbxfrpacsac il 28/09/2026
-- (progetto "Dani91x's Project", Postgres 17.6). Ogni sezione e' UNA transazione
-- indipendente (begin/commit separati): se una sezione fallisce o va in
-- eccezione, le altre gia' applicate restano valide. Tutte le sezioni sono
-- IDEMPOTENTI: rilanciare il file dopo un'applicazione riuscita non tocca piu'
-- nulla (i conteggi "dopo" restano a zero).
-- Nessuna sezione tocca partite in corso, ordini live veri o strategie.
--
-- GUARDIE A TETTO (corretto dopo la verifica del coordinatore, 28/09): ogni
-- sezione solleva eccezione SOLO se le righe toccate sono PIU' del numero
-- verificato oggi, mai se sono di meno. Se l'utente accende l'app prima di
-- incollare il file, la pulizia automatica del codice di produzione
-- (chiudi_orfani, avvio_app, scadi_proposte_opportunita) puo' aver gia' ridotto
-- alcune di queste righe: e' un bene, non un errore, e la sezione non deve
-- fermarsi per questo. Un numero PIU' ALTO di quello verificato invece e'
-- sospetto (la condizione potrebbe aver preso righe non previste) e ferma la
-- sezione con ROLLBACK automatico (eccezione dentro BEGIN/COMMIT).
--
-- L'ordine sotto e' quello di esecuzione consigliato; le sezioni non dipendono
-- l'una dall'altra salvo dove segnalato (4 dipende da 3, 6 dipende da 5, 9
-- dipende da 3 e 5).
-- ============================================================================


-- ============================================================================
-- 1) POSIZIONE FANTASMA 14265 (betfair_live_positions, mode live)
-- ============================================================================
-- Verifica 28/09 (sola lettura): id 14265 e' l'UNICA riga di
-- betfair_live_positions che ha una regolazione nella stessa modalita' in
-- betfair_live_settled (query di controllo sotto: 1 riga sola, sempre 14265).
-- Nessun vincolo FK in tutto il DB referenzia betfair_live_positions (query
-- pg_constraint eseguita: zero righe). La pagina /live-pnl e' GIA' corretta
-- alla fonte da get_live_positions_all() (migrations/
-- live_positions_senza_mercati_regolati_2026-09-26.sql, applicata): questa e'
-- SOLO igiene della tabella, la applica l'utente se vuole.
--
-- CONTEGGIO PRIMA (atteso oggi: 1 riga, id 14265, mode live, mercato
-- 1.259819675, profit regolamento +105.0):
--   select p.*, s.id as settled_id, s.settled_at, s.profit
--     from public.betfair_live_positions p
--     join public.betfair_live_settled s on s.market_id = p.market_id and s.mode = p.mode;
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    DELETE FROM public.betfair_live_positions p
     WHERE p.id = 14265
       AND p.mode = 'live'
       AND p.market_id = '1.259819675'
       AND EXISTS (SELECT 1 FROM public.betfair_live_settled s
                    WHERE s.market_id = p.market_id AND s.mode = p.mode);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    -- tetto: al massimo 1 (la riga verificata oggi); 0 e' normale a un rilancio
    IF v_n > 1 THEN
        RAISE EXCEPTION 'attesa al massimo 1 riga su betfair_live_positions.id=14265, cancellate %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo FROM public.betfair_live_positions WHERE id = 14265;
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su betfair_live_positions.id=14265: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 2) live_follow: follow dell'auto-mode scalper del 26/09 scritti senza
--    origine='auto' (rimasti 'manuale' per il bug corretto in FIX_SCALPER_E_
--    PAPER_FILL.md p.2). Finestra esplicita 26/09 (NON "oggi": oggi e' il
--    28/09) Europe/Rome.
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09): 9 righe, tutte status CLOSED, origine
-- 'manuale', event_id 36090788/36090854/36090936/36090937/36090941/36111764/
-- 36111770/36109062/36111427, tutte con un 'auto_armata' in scalper_activity
-- entro 1 minuto dalla creazione del follow.
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.live_follow f
       SET origine = 'auto', updated_at = now()
     WHERE f.origine = 'manuale'
       AND f.created_at >= '2026-09-26 00:00:00+02'::timestamptz
       AND f.created_at <  '2026-09-27 00:00:00+02'::timestamptz
       AND f.fixture_id IS NULL AND f.watchlist_id IS NULL AND coalesce(f.record, false) = false
       AND EXISTS (SELECT 1 FROM public.scalper_activity a
                    WHERE a.event_id = f.event_id AND a.kind = 'auto_armata'
                      AND a.ts BETWEEN f.created_at - interval '1 minute' AND f.created_at + interval '1 minute');
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 9 THEN
        RAISE EXCEPTION 'attese al massimo 9 righe corrette in live_follow (origine scalper 26/09), corrette %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe residue nella stessa condizione)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.live_follow f
     WHERE f.origine = 'manuale'
       AND f.created_at >= '2026-09-26 00:00:00+02'::timestamptz
       AND f.created_at <  '2026-09-27 00:00:00+02'::timestamptz
       AND f.fixture_id IS NULL AND f.watchlist_id IS NULL AND coalesce(f.record, false) = false
       AND EXISTS (SELECT 1 FROM public.scalper_activity a
                    WHERE a.event_id = f.event_id AND a.kind = 'auto_armata'
                      AND a.ts BETWEEN f.created_at - interval '1 minute' AND f.created_at + interval '1 minute');
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su live_follow origine scalper 26/09: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 3) R-28-3 (CALCIO): live_follow origine='auto' ancora STREAMING ad app
--    spenta. App confermata SPENTA dal coordinatore (0 processi python, 0
--    porte 47330-47338) dalle 19:40 PC del 26/09: nessun processo puo' star
--    davvero seguendo queste partite. Il codice che chiude questi orfani al
--    riavvio del runner (auto_follow.FollowDb.chiudi_orfani) NON e' ancora
--    girato perche' l'app non e' stata riavviata: questa e' la sanatoria UNA
--    TANTA per lo stato attuale, non sostituisce il fix di processo (cantiere
--    A, spegnimento/riavvio).
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09, confermato in modo indipendente dal
-- coordinatore: sono TUTTE le STREAMING esistenti oggi): 29 righe, tutte
-- origine='auto', status='STREAMING', created_at tra il 2026-09-26 15:55Z e
-- 17:38Z, updated_at non oltre le 17:38Z (nessun aggiornamento da quando
-- l'app e' spenta).
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.live_follow f
       SET status = 'CLOSED', updated_at = now()
     WHERE f.origine = 'auto'
       AND f.status = 'STREAMING'
       AND f.updated_at < '2026-09-27 00:00:00+00'::timestamptz;  -- prima dello spegnimento del 26/09
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 29 THEN
        RAISE EXCEPTION 'attese al massimo 29 righe chiuse in live_follow (R-28-3 calcio), chiuse %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe residue STREAMING/auto precedenti al 27/09)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.live_follow
     WHERE origine = 'auto' AND status = 'STREAMING'
       AND updated_at < '2026-09-27 00:00:00+00'::timestamptz;
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su live_follow STREAMING/auto (R-28-3): %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 4) live_now: righe "in-play" (inplay=true) mai ripulite, la piu' vecchia dal
--    2026-06-26. DIPENDE dalla sezione 3 (verificato che le 29 chiuse li' non
--    hanno nessuna riga qui: l'ordine e' solo per chiarezza, non per numeri).
--
--    NON si tocca la colonna `status`. Prova (file:riga): il runner calcio
--    scrive SOLO 'OPEN' o 'SUSPENDED' su live_now.status
--    (Betfair/stream/runner.py:365-368 e :392,
--    `db.update_live_now(event_id, ..., status="OPEN" if inplay else
--    "SUSPENDED", ...)`): 'CLOSED' non e' MAI scritto dal runner calcio su
--    questa tabella (e' scritto solo su live_follow.status via
--    `_safe_set_status`, runner.py:774, una tabella diversa). Introdurre qui
--    un valore che il codice di produzione non produce mai sarebbe un dato
--    "straniero": si azzera solo `inplay` (il campo che i lettori usano
--    davvero: MarketWatch.tsx:139-141 e :437 leggono `now.inplay`, non
--    `now.status`, per decidere il badge LIVE; nessun uso di `live_now.status`
--    di primo livello trovato ne' in MarketWatch.tsx ne' in
--    useControlRoom.ts).
--    Guardia: si tocca SOLO la riga di live_now il cui live_follow e' in uno
--    stato TERMINALE (CLOSED o UPLOADED): un follow ancora STREAMING non viene
--    toccato (nessuno oggi, verificato: tutte le 50 righe correnti hanno gia'
--    il follow CLOSED/UPLOADED).
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09, confermato in modo indipendente dal
-- coordinatore): 50 righe inplay=true su 50 in-play totali, dal 2026-06-26
-- 13:36Z (la piu' vecchia) al 2026-09-26 16:54Z (la piu' recente); TUTTE le 50
-- hanno live_follow.status in ('CLOSED','UPLOADED').
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.live_now n
       SET inplay = false, updated_at = now()
     WHERE n.inplay = true
       AND EXISTS (SELECT 1 FROM public.live_follow f
                    WHERE f.event_id = n.event_id AND f.status IN ('CLOSED', 'UPLOADED'));
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 50 THEN
        RAISE EXCEPTION 'attese al massimo 50 righe corrette in live_now (in-play orfane), corrette %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe inplay=true con follow terminale)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.live_now n
     WHERE n.inplay = true
       AND EXISTS (SELECT 1 FROM public.live_follow f
                    WHERE f.event_id = n.event_id AND f.status IN ('CLOSED', 'UPLOADED'));
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su live_now in-play orfane: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 5) EQUIVALENTE TENNIS di 3): tennis_live_follow ancora STREAMING ad app
--    spenta (stessa causa: nessun processo vivo dalle 19:40 PC del 26/09).
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09): 4 righe, event_id 36117569/36117343/
-- 36117739/36117538, created_at tra il 2026-09-26 16:06Z e 17:05Z, updated_at
-- non oltre le 17:23:39Z.
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.tennis_live_follow f
       SET status = 'CLOSED', updated_at = now()
     WHERE f.status = 'STREAMING'
       AND f.updated_at < '2026-09-27 00:00:00+00'::timestamptz;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 4 THEN
        RAISE EXCEPTION 'attese al massimo 4 righe chiuse in tennis_live_follow, chiuse %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe residue STREAMING precedenti al 27/09)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.tennis_live_follow
     WHERE status = 'STREAMING' AND updated_at < '2026-09-27 00:00:00+00'::timestamptz;
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su tennis_live_follow STREAMING: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 6) EQUIVALENTE TENNIS di 4): tennis_live_now in-play orfane. DIPENDE dalla
--    sezione 5 (3 delle 30 righe hanno il follow STREAMING chiuso appena
--    sopra: senza la 5 questa sezione ne correggerebbe solo 27).
--
--    QUI si tocca ANCHE `status` (a differenza della sezione 4): a differenza
--    del runner calcio, il runner tennis SCRIVE DAVVERO 'CLOSED' su
--    tennis_live_now.status come stato terminale, e i lettori lo gestiscono
--    gia'. Prova (file:riga):
--      Betfair/stream/tennis_live/tennis_runner.py:416-431
--        `process_closed_market` (fix R-FA-1, 26/09): quando flumine chiude un
--        mercato scrive `rec["status"] = "CLOSED"` nel record che finisce in
--        tennis_live_now.
--      tennis_runner.py:554-557 (commento + `self.now_chiusi`): "eventi con
--        tennis_live_now.status='CLOSED' gia' scritto (stato terminale: non si
--        riscrive, NON si svuota a reset_streams)" - il codice tratta
--        esplicitamente 'CLOSED' come valore noto e definitivo.
--    Scrivere 'CLOSED' qui e' quindi coerente con cio' che il runner tennis
--    stesso produce, non un valore estraneo.
-- ============================================================================
-- CONTEGGIO PRIMA (RICONTATO il 28/09 dopo la segnalazione del coordinatore:
-- il referto precedente diceva 31/28, ERRATO per un errore di conteggio mio
-- nello scorrere l'elenco a mano; la query e' la stessa, il dato NON e'
-- cambiato). Verificato e confermato in modo indipendente dal coordinatore:
-- 30 righe inplay=true totali (non 31); 3 con follow gia' CLOSED, 24 con
-- follow ERROR (27 gia' con follow terminale, non 28), 3 col follow ancora
-- STREAMING chiuso dalla sezione 5 (36117569/36117343/36117739). Dopo la
-- sezione 5 tutte e 30 rientrano nella guardia sotto. Una quarta riga
-- STREAMING in tennis_live_follow (36117538) non ha alcuna riga in
-- tennis_live_now: nessuna azione per quella.
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.tennis_live_now n
       SET inplay = false, status = 'CLOSED', updated_at = now()
     WHERE n.inplay = true
       AND EXISTS (SELECT 1 FROM public.tennis_live_follow f
                    WHERE f.event_id = n.event_id AND f.status IN ('CLOSED', 'ERROR'));
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 30 THEN
        RAISE EXCEPTION 'attese al massimo 30 righe corrette in tennis_live_now, corrette %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe inplay=true con follow terminale)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.tennis_live_now n
     WHERE n.inplay = true
       AND EXISTS (SELECT 1 FROM public.tennis_live_follow f
                    WHERE f.event_id = n.event_id AND f.status IN ('CLOSED', 'ERROR'));
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su tennis_live_now in-play orfane: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 7) mike_trades: "ingresso None-None" (F-5). Il servizio (mike/service.py,
--    _punteggio_ingresso) e' GIA' corretto: da qui in avanti scrive NULL
--    invece della stringa. Questa sanatoria pulisce le righe scritte PRIMA
--    del fix. Puramente cosmetico: nessuna decisione di Mike legge
--    score_at_entry (vedi commento nel servizio).
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09, confermato in modo indipendente dal
-- coordinatore: 407 paper + 49 live): 456 righe, placed_at tra il 2026-09-11
-- 14:06Z e il 2026-09-26 15:18Z. Nessun'altra variante sporca (controllato con
-- score_at_entry ILIKE '%none%': solo la stringa esatta 'None-None').
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.mike_trades
       SET score_at_entry = NULL
     WHERE score_at_entry = 'None-None';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 456 THEN
        RAISE EXCEPTION 'attese al massimo 456 righe corrette in mike_trades (None-None), corrette %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe residue)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo FROM public.mike_trades WHERE score_at_entry = 'None-None';
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su mike_trades.score_at_entry = None-None: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 8) safe_strategy_requests: proposte 'proposed' (kind='place') piu' vecchie
--    di 12 ore (F-6). Stessa marca di public.bot_db.scadi_proposte_opportunita
--    (Betfair/safe_strategy/bot_db.py:759), che il servizio chiama da solo a
--    ogni ciclo quando e' acceso: questa e' la stessa correzione, UNA TANTA,
--    per il tempo in cui il servizio e' stato spento (dalle 19:40 PC del
--    26/09). 'expired' non esiste nel CHECK di status: si usa 'rejected' +
--    result.decaduta, come nel servizio.
--    Limitata a kind='place' (come il servizio): le proposte 'cashout' sono
--    trattate a parte nella sezione 9 (condizione diversa e piu' stretta: la
--    decadenza per eta' da sola non basta per un cashout, serve la prova che
--    la partita sia davvero finita - il servizio infatti non le decade affatto).
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09, confermato in modo indipendente dal
-- coordinatore): 17 righe, id 291,292,295,297,303,304,305,306,307,308,310,
-- 312,313,314,316,317,322; created_at tutte il 2026-09-26 tra le 16:15Z e le
-- 17:34Z; #257 del 24/09 (l'esempio del brief) e' GIA' rejected (corretto dal
-- delegato UI del 26/09, updated_at 26/09 14:43Z): non e' in questo elenco.
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.safe_strategy_requests
       SET status = 'rejected',
           result = jsonb_build_object('decaduta', true, 'scaduta', true,
                     'motivo', 'proposta scaduta: piu'' vecchia di 12 ore (sanatoria 2026-09-28)'),
           updated_at = now()
     WHERE kind = 'place' AND status = 'proposed' AND created_at < (now() - interval '12 hours');
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 17 THEN
        RAISE EXCEPTION 'attese al massimo 17 righe decadute in safe_strategy_requests (place), decadute %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 righe residue place/proposed piu' vecchie di 12h)
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.safe_strategy_requests
     WHERE kind = 'place' AND status = 'proposed' AND created_at < (now() - interval '12 hours');
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su safe_strategy_requests place/proposed > 12h: %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 9) safe_strategy_requests: proposte di CASHOUT 'proposed' su partite GIA'
--    FINITE (richiesto dal coordinatore, 28/09): una proposta di uscita non
--    deve restare "Piazza"-bile quando la partita a cui si riferisce e' finita
--    da due giorni. DIPENDE dalle sezioni 3 e 5 (il "follow terminale" che fa
--    da prova per 4 delle 6 righe e' scritto li'): va incollata DOPO quelle
--    due, non prima.
--
--    Limitata ai 6 id verificati uno per uno (non una condizione generica su
--    tutti i 'cashout' scaduti: il servizio di produzione NON decade i
--    cashout per eta' da solo - vedi nota sotto - quindi qui si tocca SOLO
--    cio' che e' stato verificato riga per riga, non un pattern aperto).
--    Prova per ciascuno (la piu' solida disponibile a DB oggi):
--      id 311 (calcio, event 36107016): safe_strategy_trades.id=354 status
--        'lost' con settled_at 2026-09-26 17:31:50Z - POSIZIONE REGOLATA.
--      id 315 (tennis, event 36117452): safe_strategy_trades.id=350 status
--        'won' con settled_at 2026-09-26 17:16:05Z - POSIZIONE REGOLATA.
--      id 318 (calcio, event 35926090): trade 359 ancora 'open' (nessun
--        settlement in tabella) - prova = tennis/live_follow del suo evento
--        CHIUSO dalla sezione 3 (era nella lista dei 29 STREAMING/auto).
--      id 319 (calcio, event 35925583): trade 363 ancora 'open' - stessa
--        prova, evento nella lista della sezione 3.
--      id 320 (calcio, event 36090836): trade 361 ancora 'open' - stessa
--        prova, evento nella lista della sezione 3.
--      id 321 (calcio, event 36114311): trade 362 ancora 'open' - stessa
--        prova, evento nella lista della sezione 3.
--    Per 318/319/320/321 il trade e' ancora 'open' (nessuna regolazione in
--    tabella): la sanatoria NON tocca il trade (resta aperto, e' cura del
--    cantiere Safe/parita' capire perche' non si e' chiuso), tocca SOLO la
--    PROPOSTA scaduta: rifiutare una proposta vecchia di un'uscita non chiude
--    la posizione, toglie solo il pulsante "Piazza" su un suggerimento non
--    piu' attuale.
--
--    DIFETTO DI CODICE APERTO (non corretto qui, fuori perimetro sola
--    lettura): il servizio (Betfair/safe_strategy/bot_db.py:759,
--    scadi_proposte_opportunita) decade per eta' SOLO kind='place'; i
--    'cashout' non decadono mai da soli. Segnalato nel referto per il
--    cantiere che tocca Safe.
-- ============================================================================
-- CONTEGGIO PRIMA (verificato 28/09): 6 righe, id 311,315,318,319,320,321,
-- kind='cashout', status='proposed', created_at il 2026-09-26 tra le 16:54Z
-- e le 17:33Z, payload.mode='paper' su tutte.
-- ============================================================================
BEGIN;

DO $$
DECLARE v_n integer;
BEGIN
    UPDATE public.safe_strategy_requests r
       SET status = 'rejected',
           result = jsonb_build_object('decaduta', true, 'scaduta', true,
                     'motivo', 'proposta di cashout scaduta: partita finita, piu'' vecchia di 12 ore (sanatoria 2026-09-28)'),
           updated_at = now()
     WHERE r.id IN (311, 315, 318, 319, 320, 321)
       AND r.kind = 'cashout'
       AND r.status = 'proposed'
       AND r.created_at < (now() - interval '12 hours')
       AND (
             -- prova diretta: la posizione sottostante e' gia' regolata
             EXISTS (SELECT 1 FROM public.safe_strategy_trades t
                      WHERE t.id = (r.payload->>'trade_id')::bigint AND t.settled_at IS NOT NULL)
             -- oppure: il follow dell'evento e' in stato terminale (calcio)
          OR EXISTS (SELECT 1 FROM public.live_follow f
                      WHERE f.event_id = r.payload->>'event_id' AND f.status = 'CLOSED')
             -- oppure: il follow dell'evento e' in stato terminale (tennis)
          OR EXISTS (SELECT 1 FROM public.tennis_live_follow f
                      WHERE f.event_id = r.payload->>'event_id' AND f.status = 'CLOSED')
           );
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n > 6 THEN
        RAISE EXCEPTION 'attese al massimo 6 righe decadute in safe_strategy_requests (cashout), decadute %: annullo', v_n;
    END IF;
END $$;

-- CONTROLLO DOPO (atteso: 0 delle 6 righe verificate ancora 'proposed')
DO $$
DECLARE v_residuo integer;
BEGIN
    SELECT count(*) INTO v_residuo
      FROM public.safe_strategy_requests
     WHERE id IN (311, 315, 318, 319, 320, 321) AND status = 'proposed';
    IF v_residuo <> 0 THEN
        RAISE EXCEPTION 'residuo inatteso su safe_strategy_requests cashout (id verificati ancora proposed): %', v_residuo;
    END IF;
END $$;

COMMIT;


-- ============================================================================
-- 10) analytics_signals / analytics_decisions: kickoff sporco (dato dal
--     referto E2E fase 3 sessione B par.10; migrations/
--     analytics_signals_kickoff_pulizia_2026-09-26.sql e' una PROPOSTA con la
--     CORREZIONE COMMENTATA -- l'utente il 26/09 ha eseguito solo la DIAGNOSI.
--     Qui la correzione E' REALE (non commentata).
--
--     Verificato di persona il 28/09 che il fix a MONTE (chi scrive kickoff da
--     ora in avanti) e' su master e usato dal job:
--       merge_engine_signals.py:157   kickoff = (match or {}).get("fixture_date") or es.get("kickoff")
--       build_analytics_signals.py:241 "kickoff": (match or {}).get("fixture_date") or fp.get("fixture_date")
--     entrambi in radice del repo, richiamati da
--     .github/workflows/predictions_results_backfill.yml. Senza questo fix a
--     monte la correzione qui sotto verrebbe DISFATTA dal prossimo job
--     (03:23 UTC): col fix presente e' STABILE. Confermato inoltre dal
--     coordinatore: 84.535 righe create dal 27/09 in avanti, 0 sporche; le
--     ultime righe sporche risalgono al 24/09 (prima del fix).
-- ============================================================================
-- CONTEGGIO PRIMA (misurato il 28/09, sola lettura, confermato in modo
-- indipendente dal coordinatore; sul referto del 26/09 erano 255 partite /
-- 14.034 righe su una finestra di 60 giorni, oggi su TUTTA la tabella):
--   analytics_signals   : 778 partite / 33.251 righe con kickoff <> matches.fixture_date
--   analytics_decisions : 402 partite /  6.278 righe con kickoff <> matches.fixture_date
-- Fuori orario del job (03:23 UTC) e dei bot (app spenta il 28/09): sicuro.
-- Qui non c'e' un tetto sul numero di righe (l'UPDATE corregge TUTTE le righe
-- sporche trovate al momento, non un elenco fisso): la garanzia e' il
-- controllo "dopo", che deve dare zero su entrambe le tabelle o va in
-- ROLLBACK automatico.
-- ============================================================================
BEGIN;
SET LOCAL statement_timeout = '15min';

UPDATE public.analytics_signals s
   SET kickoff = m.fixture_date, updated_at = now()
  FROM public.matches m
 WHERE m.fixture_id = s.fixture_id
   AND m.fixture_date IS NOT NULL
   AND s.kickoff IS DISTINCT FROM m.fixture_date;

UPDATE public.analytics_decisions d
   SET kickoff = m.fixture_date, updated_at = now()
  FROM public.matches m
 WHERE m.fixture_id = d.fixture_id
   AND m.fixture_date IS NOT NULL
   AND d.kickoff IS DISTINCT FROM m.fixture_date;

-- CONTROLLO DOPO (deve dare 0 e 0: se anche una sola riga resta diversa, ROLLBACK)
DO $$
DECLARE v_sig integer; v_dec integer;
BEGIN
    SELECT count(*) INTO v_sig FROM public.analytics_signals s
      JOIN public.matches m ON m.fixture_id = s.fixture_id
     WHERE m.fixture_date IS NOT NULL AND s.kickoff IS DISTINCT FROM m.fixture_date;
    SELECT count(*) INTO v_dec FROM public.analytics_decisions d
      JOIN public.matches m ON m.fixture_id = d.fixture_id
     WHERE m.fixture_date IS NOT NULL AND d.kickoff IS DISTINCT FROM m.fixture_date;
    IF v_sig <> 0 OR v_dec <> 0 THEN
        RAISE EXCEPTION 'residuo kickoff sporco: analytics_signals=%, analytics_decisions=%', v_sig, v_dec;
    END IF;
END $$;

COMMIT;

-- Dopo il commit: il riepilogo (letto da get_analytics/get_decisions) porta
-- ancora i vecchi kickoff finche' non si rifa'. Nessun dato sbagliato per chi
-- legge (le RPC ricalcolano al bisogno), ma per vedere subito i numeri giusti:
SELECT public.refresh_analytics_riepilogo();


-- ============================================================================
-- NOTE (nessuna azione SQL, per completezza del cantiere I):
--
-- A) Le 5 migrazioni del 26/09 (storico_esito_a_zero, omega_state_per_
--    modalita, live_positions_senza_mercati_regolati, analytics_rpc_veloci,
--    betfair_live_orders_source_bot) sono state verificate APPLICATE dal
--    coordinatore (funzioni con aggregates_by_mode, tabelle
--    analytics_riepilogo_* piene, CHECK di source coi nomi dei bot): non
--    riverificate in questo file su sua indicazione esplicita.
--
-- B) I 9 indici facoltativi (aggregati_idx_2026-09-25_SOLO_SE_MANCANO.sql,
--    detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql): NESSUNO va creato.
--    Verificato a DB (pg_indexes) il 28/09, confermato in modo indipendente
--    dal coordinatore:
--      - i 4 di aggregati_idx (injuries/top_scorers/top_assists/top_cards su
--        (league_id, season_year)) esistono GIA' con lo stesso nome.
--      - i 5 di detail_fixture_idx (idx_match_events_fixture_id e i 4 gemelli
--        su match_lineups/match_player_stats/match_team_stats/match_odds) NON
--        esistono con QUEL nome, ma un indice EQUIVALENTE su fixture_id esiste
--        gia' su tutte le 5 tabelle con un altro nome (idx_match_events_
--        fixture, idx_match_lineups_fixture, idx_match_player_stats_fixture,
--        idx_match_team_stats_fixture, idx_match_odds_fixture), oltre a un
--        indice (league_id, season_year, fixture_id) su ognuna. Crearli
--        sarebbe un DOPPIONE (match_odds da solo pesa 20 GB): il file stesso
--        lo vieta ("si applica SOLO se l'avviso e' comparso"; l'avviso qui non
--        si sarebbe presentato, la capacita' c'era gia').
--
-- C) tennis_bot_service_control con status 'running'/'stopping' ad app spenta
--    (26/09, 4 righe): NESSUNA sanatoria. Verificato nel codice
--    (Betfair/stream/avvio_app.py, usato da
--    Betfair/stream/tennis_live/tennis_bot_service.py): ogni servizio bot
--    (mike/omega/safe/tennis/scalper) al PROSSIMO avvio dell'app confronta il
--    proprio APP_BOOT_ID e, se e' un avvio nuovo, si ferma da solo
--    (status='stopped', mode='paper') scrivendo un'attivita'
--    'avvio_app_bot_fermato'. Meccanismo automatico gia' in produzione: una
--    UPDATE manuale qui sarebbe superflua e rischierebbe di correre col
--    prossimo avvio reale dell'app.
-- ============================================================================
