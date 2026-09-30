# BACKEND PER LA UI (30/09/2026) - referto del delegato costruttore

Worktree: `.claude/worktrees/agent-a963491448762d67d` (base `a86b927`). Nessun commit, nessun
push, nessuno stash, nessuna scrittura sul DB. Diff: `AUDIT_2026-09-30/BACKEND_PER_UI.patch`
(`git diff HEAD` + i file nuovi, vedi in fondo).

Le quattro consegne sono FATTE. Letture di verifica sul DB vero: SOLO `SELECT`
(PostgREST con la chiave del `.env` e `execute_sql` dello strumento Supabase con query
`SELECT`/`WITH ... SELECT`; nessuna DDL, nessuna funzione creata).

---------------------------------------------------------------------------------------------

## 1. RPC `get_live_orders_account_open()` + reperto 23514

### 1a. Migrazione (DA APPLICARE, obbligatoria per la UI che chiama la RPC)

`migrations/live_orders_account_open_2026-09-30.sql` (nuovo). SECURITY DEFINER,
`SET search_path = public, pg_temp`, owner-only `betfair_live_is_owner()` (riga 69), come
`get_live_orders` (`betfair_live_order_queue.sql:349`). REVOKE da public/anon, GRANT a
authenticated/service_role. Solo `SELECT`. Ordine: dopo `betfair_live_order_queue.sql`,
`betfair_live_account_heartbeat.sql`, `betfair_live_pnl_journal.sql`,
`pnl_betfair_reale_2026-09-24.sql` (tutte gia' applicate: le colonne esistono sul DB, vedi 1c).

Forma ESATTA (copiata dal file, righe 150-213):

```
RETURN jsonb_build_object('rows', v_rows, 'letto_at', now());
riga: { 'bet_id', 'market_id', 'selection_id', 'event_id', 'event_name', 'market_name',
        'selection_name', 'side' (upper(b.side) -> 'BACK'|'LAY'),
        'price_matched' (average_price_matched; NULL se size_matched = 0),
        'size_matched', 'size_remaining', 'status', 'source', 'placed_at' }
ordine: placed_at DESC NULLS LAST, id DESC
```

Nota di forma: `price_matched` e' `numeric` oppure `null` quando nulla e' abbinato (lo
specchio scrive 0 per "niente abbinato": non e' un prezzo). La UI deve accettare null.

Quali righe (righe 72-100 del file):
- `mode='live'`; `source IN ('runner','account')` (le source dei bot `scalper`, `omega`, `safe`,
  `mike`, `safe_tennis`, `tennis_*` sono fuori);
- bet_id NON presente in `omega_trades` / `safe_strategy_trades` / `mike_trades` (mode live):
  stessa regola «chi e' di chi» di `reconcile_worker` (commento a `:589`);
- status `EXECUTABLE`/`EXECUTION_COMPLETE` con `size_matched > 0` o (EXECUTABLE e residuo > 0);
- NON regolato: `pnl_betfair_settled_at IS NULL`, nessuna riga live in `betfair_live_settled`
  per il mercato, bet_id non in `betfair_live_account.pnl_reale_oggi.bet_ids` (regolati di oggi
  da listClearedOrders), blocco del feed scanner non `CLOSED`, evento del catalogo non finito
  (`live_follow.status` non in CLOSED/UPLOADED: `runner._finalize_event` -> CLOSED).

Nomi (null se non risolvibili, mai inventati):
- `event_id`: riga specchio -> `live_markets.event_id` -> `safe_strategy_scan.event_id`;
- `event_name`: `safe_strategy_scan.payload.event_name` -> `live_follow.home_name || ' v ' ||
  away_name` (formato Betfair che `scanner.split_event_name` divide);
- `market_name`: `live_markets.market_name` del mercato -> nome VERO dello stesso `market_type`
  in `live_markets` (sonda del 30/09, 1:1 su 14 tipi: MATCH_ODDS 'Match Odds', CORRECT_SCORE
  'Correct Score', HALF_TIME_SCORE 'Half Time Score', HALF_TIME 'Half Time',
  BOTH_TEAMS_TO_SCORE 'Both teams to Score?', OVER_UNDER_05..85 'Over/Under N.5 Goals');
- `selection_name`: `live_markets.selections` del mercato -> `selections` del blocco del feed
  (cs/ht/ou/btts/ht_result; per il Match Odds `odds.home/away/p1/p2.selection_id` ->
  `payload.home/away/p1/p2`) -> stesso selection_id nello stesso market_type del catalogo.

Blocchi del feed letti (forma VERA, sonda `backend_per_ui_sonde/sonda_scan.py` sul DB):
`mo_market_id`/`mo_status`/`odds.{home,draw,away|p1,p2}.selection_id`/`home`/`away`/`p1`/`p2`,
`cs{market_id,status,selections[{selection_id,name}]}`, `ht{...}`, `ou[{market_id,status,
market_type,line,selections}]`, `btts{...,market_type}`, `ht_result` (null nella riga letta).
Produttore: `Betfair/safe_strategy/service.py::build_rows` (1858-1940) +
`scanner.build_market_block` (`scanner.py:629`) + `split_opportunity_blocks` (`:825`).

### 1b. Prova sul DB vero (sola lettura)

Il CORPO della funzione (estratto dal file con `backend_per_ui_sonde/estrai_select.py`, senza
guardia owner e senza INTO) eseguito come `WITH ... SELECT` il 30/09 alle 18:09 UTC:

```
{"rows":[
 {"bet_id":"445039090782","source":"account","status":"EXECUTION_COMPLETE","side":"BACK",
  "event_id":"36130526","event_name":"FC Vsetin v Bohemians 1905","market_id":"1.263075925",
  "market_name":"Over/Under 4.5 Goals","selection_id":1222347,"selection_name":"Under 4.5 Goals",
  "price_matched":1.44,"size_matched":5.18,"size_remaining":0,"placed_at":"2026-09-30T13:32:01+00:00"},
 {"bet_id":"445039002080", ... "market_name":"Over/Under 3.5 Goals","selection_name":"Over 3.5 Goals",
  "price_matched":1.92,"size_matched":0.09 ...},
 {"bet_id":"445039002079", ... "price_matched":1.92,"size_matched":4.34 ...}],
 "letto_at":"2026-09-30T18:09:28.231521+00:00"}
```

Sono i 3 ordini dell'utente dal sito citati nel reperto del coordinatore (righe 46716, 46717,
46768). Le altre 89 righe live candidate sono ESCLUSE correttamente: 86 su mercati del 10/07 in
`betfair_live_settled`, 3 del 01/09 (mercato 1.261754739) con `live_follow.status='UPLOADED'`.

### 1c. `\d`-like: tabelle e colonne lette davvero

| tabella | colonne usate | definite in |
|---|---|---|
| betfair_live_orders | id, bet_id, mode, source, event_id, market_id, selection_id, side, size_matched, size_remaining, average_price_matched, status, placed_at, pnl_betfair_settled_at | `betfair_live_order_queue.sql:80-107`; source `betfair_live_account_heartbeat.sql:87`; pnl_betfair_settled_at `pnl_betfair_reale_2026-09-24.sql:55-58` |
| betfair_live_settled | mode, market_id | `betfair_live_pnl_journal.sql:25-36` |
| betfair_live_account | id, pnl_reale_oggi (jsonb, chiave bet_ids) | colonna in `pnl_betfair_reale_2026-09-24.sql`; bet_ids scritta da `reconcile_worker.componi_regolati` (`:957`) |
| omega_trades / safe_strategy_trades / mike_trades | mode, bet_id | `omega_bot.sql:46,60`; `safe_strategy_bot.sql:59,69`; `mike_bot.sql:95,105` |
| live_markets | id, event_id, market_id, market_type, market_name, selections | `live_stream.sql:75-86` |
| live_follow | event_id, home_name, away_name, status | `live_stream.sql:33-46` |
| safe_strategy_scan | event_id, payload (jsonb), updated_at | `safe_strategy_scan.sql:28-33` |

Colonne verificate sul DB vero: `betfair_live_orders` (select * sonda `sonda_blo.py`: 28 colonne,
comprese source e pnl_betfair_settled_at), `betfair_live_settled`, `safe_strategy_scan`,
`live_markets`, `live_follow`, `omega_control`, `tennis_live_orders`, `tennis_live_follow`
(information_schema); la query intera e' stata eseguita senza errori.

### 1d. Reperto 23514 (`reconcile_worker._reconcile_orders`)

`Betfair/stream/reconcile_worker.py:348-358` (nuovi): `_REF_BOT_CON_TABELLA = {"mike","omega",
"safe"}` (i `customerStrategyRef` di `mike/config.py:30`, `omega/omega_config.py:19`,
`safe_strategy/bot_service.py:80`) e `_ref_bot_con_tabella(order)`.
`:365-377`: un ordine del conto NON nello specchio con quel ref NON viene piu' scritto
(prima: `source='bot:mike'` -> CHECK `betfair_live_orders_source_check` -> 23514 a ogni giro);
`:394-398`: un contatore a DEBUG. Invariati: gli ordini del sito (nessun ref o ref `live`) entrano
con `source='account'` + WARN come prima; gli ordini dei bot gia' nello specchio (via runner,
source='mike' ecc.) passano dal ramo delle divergenze come prima; ref di bot SENZA tabella
(es. `watchlist`) invariati (scritti come `bot:<ref>`, vedi «non fatto»).

### 1e. Test

- `Betfair/stream/tests/test_live_orders_account_open_2026_09_30.py` (nuovo, 8 test): chiavi
  della riga nel file SQL == contratto (14 chiavi, stesso ordine); busta `rows`+`letto_at`;
  owner-only/search_path/esclusioni bot/nessuna scrittura; la risposta VERA del DB rispetta il
  contratto; 4 risposte guaste rifiutate. 8 passed.
- `test_reconcile_worker.py` (+4 test): finto = `CurrentOrder` VERO di betfairlightweight
  costruito con le chiavi camelCase di listCurrentOrders; mike/omega/safe -> nessun upsert,
  nessun WARN, 1 riga DEBUG «1 ordini dei bot con tabella propria»; sito/`live`/`watchlist`
  invariati. File intero: 56 passed.

---------------------------------------------------------------------------------------------

## 2. `pnl_letto_at` (chiave additiva)

- Topic `conto` (canale 47331): `Betfair/stream/esiti_ordini_canale.py:716-719` (`_iso_ms`) e
  `:732-736` in `payload_conto`: `"pnl_letto_at": _iso_ms(int(ricevuto_ms))`.
  Formato: `"2025-09-30T18:09:28.231Z"` (ISO-8601 UTC al millisecondo con la `Z`).
  ISTANTE USATO: `ricevuto_ms` = arrivo del messaggio dello stream ordini (la LETTURA degli
  ordini del conto); la pubblicazione avviene nella stessa chiamata
  (`pubblica_conto_da_evento`), quindi lettura e invio coincidono al millisecondo. NON e' il
  `publish_time_ms` di Betfair (resta a parte, invariato).
  Chi pubblica: `pubblica_conto_da_evento` (stessa funzione, montata dal runner LIVE con
  `osserva_conto_su_flumine`): nessun cambio.
- Equivalente del conto (P&L reale, stessa chiave): `Betfair/stream/reconcile_worker.py:1023-1025`
  `pnl_letto_at = datetime.now(timezone.utc).isoformat()` preso SUBITO DOPO la lettura REST
  degli ordini regolati (`_fetch_cleared_orders_today`), prima delle letture DB e delle
  scritture; `:1064` dentro `pnl_reale_oggi` (colonna `betfair_live_account.pnl_reale_oggi`,
  realtime) e `:1098` sul topic `account` del canale. Formato `"2026-09-30T18:00:00+00:00"`.
  `letto_at`/`checked_at` di prima INVARIATI (sono l'istante dopo le scritture). Nota: in DB
  `pnl_reale_oggi` si riscrive solo se la firma cambia (regola di sempre), quindi la chiave in
  DB porta l'ultima lettura CHE HA CAMBIATO i numeri; sul canale arriva a ogni giro che legge.
- Test: `test_conto_ordini_canale_2026_09_30.py` (+2: payload VERO dalla cache dello stream
  `OrderBookCache` -> `pnl_letto_at` == ricevuto_ms in ISO `Z`, publish_time separato, chiavi di
  prima tutte presenti; `MemoriaConto` accetta il payload) -> file 13 passed.
  `test_reconcile_worker.py::test_sync_manual_pnl_porta_pnl_letto_at_istante_della_lettura`:
  orologio finto che avanza di 7 s fra lettura e scrittura: la chiave porta la lettura.
  Consumatori esistenti: `Betfair/mike/tests/test_mike_conto_dal_canale_2026_09_30.py` verde
  nella suite (vedi §5).

---------------------------------------------------------------------------------------------

## 3. Omega `stats.stop_perdita`

`Betfair/omega/omega_service.py`:
- `:7548-7562` `_stop_perdita(params, aggregati_bot, legs_engine)` -> `{"soglia": float,
  "chiave": str, "scattato": bool}`. Regola IDENTICA alle aperture: motore legs
  (`scan_and_place_legs`, `:1844-1851`): `daily_loss_cap`, con `strategy_version >= 3`
  `v3_daily_loss_cap`; motore v1 (`scan_and_place`, `:2370`): `daily_loss_cap`. R =
  `E.realized_effective` dei numeri DEL BOT (come la decisione). `scattato` = soglia > 0 e
  R <= -soglia (oggi: gli aggregati sono della giornata operativa).
- `:8214` nelle stats del ciclo attivo; `:7577-7595` + `:7630` a bot fermo (`_idle_stats`)
  con gli ultimi parametri del ciclo (`_ULTIMI_PARAMS`) e i numeri del bot; senza parametri o
  aggregati resta il valore precedente (`**prev`).
- In produzione (`strategy_version` di serie 3, `omega_config.py:221`, motore forzato `legs`
  `:409`) la chiave e' `v3_daily_loss_cap`, soglia di serie 300 (`:262`); la riga vera di
  `omega_control` non ha `strategy_version` nei params (letta il 30/09): vale il default.
- Nessun cambiamento di comportamento: la funzione legge solo; decisioni invariate.
- Test `Betfair/omega/tests/test_stop_perdita_stats_2026_09_30.py` (nuovo, 7 test): finto
  della riga `omega_control` con le 12 colonne vere (information_schema), run_once intero
  (scattato con perdita -20 su cap 10, e non scattato con -5 + runner paper finto), unita' V3,
  soglia 0, bloccato in perdita, bot fermo con/senza parametri. 7 passed.

---------------------------------------------------------------------------------------------

## 4. `get_tennis_bot_daily` per giorno della PARTITA (fatto)

`migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql` (nuovo, DA APPLICARE; facoltativa
per la UI: senza, la RPC resta per giorno del regolamento). Ridefinisce la funzione con la
STESSA firma `(date, date, text, text) RETURNS json`, stesse colonne, stessi controlli.
Nota: la definizione attuale (letta con `pg_get_functiondef` sul DB) raggruppa per
`settled_at` (regolamento), non per piazzamento. Giorno nuovo =
`(coalesce(tennis_live_follow.open_date, settled_at) AT TIME ZONE 'Europe/Rome')::date`.
Prova in sola lettura: vecchio e nuovo corpo sulle 17 righe regolate (tutte paper, tutte
risolte in `tennis_live_follow`) -> JSON IDENTICO (nessuna partita a cavallo di mezzanotte oggi);
caso a cavallo di mezzanotte con VALUES: nuovo 29/09, vecchio 30/09. Effetto per la UI: una
partita iniziata alle 23:30 e regolata dopo mezzanotte conta nel giorno in cui e' iniziata.
Test `Betfair/stream/tests/test_tennis_bot_daily_giorno_partita_2026_09_30.py` (3 test: firma e
colonne uguali alla definizione precedente, giorno della partita con ripiego, grant). 3 passed.

---------------------------------------------------------------------------------------------

## 5. Falsificazione e suite

Script `AUDIT_2026-09-30/backend_per_ui_sonde/falsifica_backend_per_ui.py` (originale in
memoria, sostituzione esatta, test mirato, ripristino in `finally` + confronto byte a byte +
`MUTAZIONE` assente). Esito (`falsifica_backend_per_ui.out`): 15/15 ROSSI.

| mutazione | test rosso |
|---|---|
| M1 bot con tabella di nuovo copiati | reconcile (parametrico) |
| M1b 'mike' tolto dai ref | reconcile |
| M1c salta anche ref senza tabella | reconcile (sito/altri invariati) |
| M2 chiave selection_name rinominata | contratto RPC |
| M2b letto_at tolto | contratto RPC |
| M2c esclusione mike_trades tolta | contratto RPC |
| M3 pnl_letto_at dal publishTime | conto |
| M3b formato senza Z | conto |
| M4 pnl_letto_at = istante d'invio | reconcile |
| M4b chiave tolta dal canale account | reconcile |
| M5 chiave sempre daily_loss_cap | omega V3 |
| M5b R senza bloccato | omega |
| M5c stop_perdita tolto dal ciclo | omega run_once |
| M5d niente stop_perdita a bot fermo | omega idle |
| M6 giorno del regolamento | tennis |

Dopo lo script: `grep -c MUTAZIONE` = 0 sui 5 file, `git diff --stat` identico a prima.

### 5-bis. Suite (numeri reali)

Comando: `python -m pytest Betfair/stream/tests Betfair/omega
Betfair/mike/tests/test_mike_conto_dal_canale_2026_09_30.py -q -p no:cacheprovider`
(443 s). Primo giro: **7 failed, 4630 passed, 28 skipped**. I 7 rossi erano tutti in
`Betfair/omega/tests/test_omega_legge_canale_2026_09_23.py` (traccia d'oro delle chiamate al DB
di `run_once`, che confronta anche il dizionario `stats` intero della `set_control`): causa =
la chiave additiva `stop_perdita`. Correzione: aggiunta SOLO quella chiave nelle 3 `set_control`
della traccia `Betfair/omega/tests/traccia_canale_scan_2026_09_23.json` (+15 righe, nessun'altra
riga cambiata; script `backend_per_ui_sonde/aggiorna_golden_stop_perdita.py`; valore con i
parametri della traccia `{"engine": "legs"}` e la suite di Omega a `strategy_version` 2:
`{"chiave": "daily_loss_cap", "scattato": false, "soglia": 0.0}`). Le chiamate al DB restano
identiche (stessi nomi, stessi argomenti, zero scritture in piu'). Dopo: il file intero
**49 passed**. Il resto della suite non legge quella traccia (unico lettore:
`traccia_canale_scan_2026_09_23.py`/quel test), quindi non l'ho rilanciata intera: totale
atteso 4637 passed, dichiarato non rieseguito in un colpo solo.
Non lanciati: `Betfair/stream/tennis_live/tests`, `Betfair/mike/tests` (tranne il test del
conto), `Betfair/safe_strategy`, frontend (nessun file del frontend toccato).

---------------------------------------------------------------------------------------------

## 6. Cosa NON ho fatto / NON ho potuto verificare

- NON ho creato la funzione sul DB (vietato): il corpo e' stato eseguito come SELECT, la
  CREATE FUNCTION (plpgsql, grant) non e' stata compilata dal server. Rischio residuo: errori
  di sola sintassi plpgsql fuori dal corpo (DECLARE/IF/RETURN), copiati da `get_live_orders`.
  Idem per la ridefinizione tennis.
- RPC 1, LIMITE DICHIARATO (verificato sui dati): quando l'app e' chiusa i segnali di
  «regolato» non si aggiornano. Oggi alle 18:09 UTC la riga del feed dell'evento 36130526 era
  ferma alle 14:09 (minuto 39, mercati OPEN) e `betfair_live_settled` live e' fermo al 14/09
  (lo scrive solo la riconciliazione in LIVE); i 3 ordini risultano quindi «aperti» anche se la
  partita e' con ogni probabilita' finita. Con l'app accesa: la riga del feed passa a CLOSED o
  sparisce, e `pnl_reale_oggi.bet_ids` (giro del saldo, attivo in ogni modalita') li toglie
  appena Betfair li regola con commissione leggibile. Un ordine del sito su un mercato MAI
  seguito dall'app e regolato ad app chiusa (giorno precedente) resterebbe visibile: nessun
  campo del DB lo dice. Proposta (decisione del coordinatore/utente, non fatta): marcare nello
  specchio l'ultima volta che la riconciliazione ha visto l'ordine fra i current orders, o una
  finestra temporale sulle righe `account`.
- RPC 1: gli ordini manuali TENNIS del terminale dell'app stanno in `tennis_live_orders`, non
  nello specchio calcio: NON sono nella RPC (ci sono quelli dal sito sui mercati tennis, come
  `account`). Fuori perimetro del brief (sorgente indicata = `betfair_live_orders`).
- RPC 1: il ripiego del nome di selezione per `selection_id` nello stesso market_type (usato
  per «The Draw» del Match Odds dal feed) non e' esercitato dai dati di oggi.
- Reperto 23514: ref di bot SENZA tabella propria (`watchlist` di `order_exec.py:317`, o altri
  futuri) restano scritti come `bot:<ref>` e il CHECK li rifiuta come prima (nessuno visto oggi;
  non verificato sul log). Non li ho toccati: non richiesto, e l'ammissione di `bot:*` e' una
  decisione (li porterebbe nello specchio del terminale manuale).
- Tempo d'esecuzione della RPC non misurato con EXPLAIN ANALYZE (la query e' tornata
  normalmente dallo strumento).
- `stop_perdita` a bot fermo dopo un riavvio del servizio (senza un ciclo attivo:
  `_ULTIMI_PARAMS` = None) resta il valore precedente scritto in `stats`.

## 7. Decisioni per l'utente

Nessuna strategia toccata. Una proposta (vedi §6, limite della RPC 1): come dichiarare
«regolato» un ordine del sito su un mercato mai seguito mentre l'app era chiusa.

## 8. Da controllare dal vivo al prossimo avvio (app accesa, LIVE)

- log del runner: spariti i `23514 ... betfair_live_orders_source_check` a ogni giro; a DEBUG
  «N ordini dei bot con tabella propria ... non copiati nello specchio».
- canale 47331 topic `conto`: ogni messaggio ha `pnl_letto_at` = ISO `Z` pari a `ricevuto_ms`.
- topic `account` (giro dei regolati): `pnl_letto_at` presente, qualche ms/s prima di `checked_at`.
- `omega_control.stats.stop_perdita` = `{"soglia": 300, "chiave": "v3_daily_loss_cap",
  "scattato": false}` con i parametri di serie.
- dopo aver applicato la migrazione: `SELECT public.get_live_orders_account_open();` dal SQL
  editor come owner.

## Migrazioni da applicare (l'utente)

1. `migrations/live_orders_account_open_2026-09-30.sql` - obbligatoria per la UI che usa la RPC.
2. `migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql` - facoltativa (cambia il
   raggruppamento dei giorni del tennis bot).
Indipendenti fra loro; nessuna tocca dati.

## File toccati / nuovi

Modificati: `Betfair/stream/reconcile_worker.py`, `Betfair/stream/esiti_ordini_canale.py`,
`Betfair/omega/omega_service.py`, `Betfair/stream/tests/test_reconcile_worker.py`,
`Betfair/stream/tests/test_conto_ordini_canale_2026_09_30.py`,
`Betfair/omega/tests/traccia_canale_scan_2026_09_23.json` (solo la chiave `stop_perdita`, §5-bis).
Patch: `AUDIT_2026-09-30/BACKEND_PER_UI.patch` = `git diff HEAD --binary` (byte esatti) + i 5
file nuovi (`git diff --no-index /dev/null <file>`), scritta da
`backend_per_ui_sonde/scrivi_patch.py`; verificata con `git apply --check -R` = 0 sul worktree.
Dopo l'ultima modifica (virgolette «» tolte da 3 commenti per l'ASCII-only) rilanciati: i 7
file di test toccati/collegati = 149 passed; la falsificazione = 15/15 ROSSI.
Nuovi: `migrations/live_orders_account_open_2026-09-30.sql`,
`migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql`,
`Betfair/stream/tests/test_live_orders_account_open_2026_09_30.py`,
`Betfair/stream/tests/test_tennis_bot_daily_giorno_partita_2026_09_30.py`,
`Betfair/omega/tests/test_stop_perdita_stats_2026_09_30.py`,
`AUDIT_2026-09-30/backend_per_ui_sonde/` (sonde in sola lettura, estrattore del corpo SQL,
script di falsificazione e i suoi esiti), questo referto e la patch.
