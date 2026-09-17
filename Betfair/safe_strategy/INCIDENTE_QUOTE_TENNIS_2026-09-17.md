# INCIDENTE — QUOTE ASSENTI SU TUTTO IL FEED (tennis **e** calcio), 17/09/2026

> Diagnosi in SOLA LETTURA. Nessuna modifica al codice, nessun processo toccato, nessun
> riavvio deciso da qui, nessun commit. Le patch sono PROPOSTE (diff), non applicate.
> Misure: DB via GET REST (service_role), codice del checkout principale, sorgenti di
> `betfairlightweight 2.23.2` in `.venv`, albero dei processi e porte in ascolto (Windows,
> sola lettura).

---

## 0. In una riga

Lo stream Betfair dello scanner Safe consegna **book con i runner presi dalla
`marketDefinition` e ZERO prezzi**; `service.py:_apply_market_book` li accetta come se
fossero un aggiornamento di quote e **sovrascrive le quote buone con `null`**, facendo
pure avanzare `odds_ts_ms`. Il fallback REST — che avrebbe coperto il buco in 10-20 s —
**non parte mai**, perché "coperto" è deciso sulla salute del SOCKET (heartbeat ogni 5 s),
non sulla consegna delle quote. Risultato: blackout **permanente e invisibile**
(`last_error: null`, badge STREAM verde), uscite automatiche congelate.

**Non è un problema del tennis: è l'intero feed** (tennis, calcio, mercati a gol).
**E non è il doppio avvio dei servizi: quello non esiste** (§3.6, con prova).

---

## 1. I fatti misurati

### 1.1 Prima del riavvio (letture 13:0x UTC, scanner partito alle 12:17:08)

| | tennis in gioco | tennis pre-KO | calcio in gioco |
|---|---|---|---|
| righe | 11 | 4 | 4 |
| `odds.*` | `{back:null, lay:null, back_size:null, lay_size:null, ltp:null, selection_id:<int>}` | idem | idem |
| `mo_status` | `OPEN` | `OPEN` | `OPEN` |
| `inplay` | `true` | `false` | `true` |
| `mo_total_matched` | `0.0` | `0.0` | `0.0` |
| `updated_at` | fresco (12:57) | 12:55 | fresco (12:57) |

`odds_ts_ms` = istante dell'ULTIMO CAMBIO delle quote (`service.py:530-532`):

* **calcio** `1789649224351/352/362` → **12:47:04 UTC** (tutte e 4 le partite delle 12:30,
  quelle armate da Mike, più i loro mercati a gol);
* **tennis** `1789649289678/679/680` → **12:48:09 UTC** (7 righe);
* le altre 4 righe tennis: 12:17:45.667 (×4 eventi, 37 s dopo `started_at`), 12:20:03,
  12:35:06, 12:40:02 — cioè il **primo** book mai applicato a quel mercato, già vuoto.

### 1.2 La prova che i book **continuano ad arrivare** (e sono vuoti)

Evento calcio `36079458` (Vilkhivtsi v Shakhtar), blocco di un mercato a gol:

```
ou OVER_UNDER_25  market_id 1.262547088  status OPEN
   ts_ms   1789649224351  -> 12:47:04   (ULTIMO CAMBIO di prezzo)
   seen_ms 1789649841815  -> 12:57:21   (ULTIMO BOOK RICEVUTO)
   sel0: {"name":"Under 2.5 Goals","selection_id":47972,
          "runner_status":"ACTIVE","back":null,"lay":null,
          "back_size":null,"lay_size":null}
```

`seen_ms` è scritto a OGNI book ricevuto (`service.py:612-618`), `ts_ms` solo al cambio di
prezzo. `seen_ms` fresco a 10 minuti dal blackout ⇒ **lo stream consegna book in
continuazione, e ognuno porta i runner con `runner_status` (che viene dalla DEFINIZIONE) e
nessun prezzo.** Lo conferma `fasi_p95.stream = 76,5 ms`: non è una coda vuota.

### 1.3 Dopo il riavvio dell'app delle 15:13 locali (13:13 UTC) — **NON è rientrato**

Letture alle 13:25 UTC, processo nuovo (`started_at 13:13:53`), sessione nuova,
sottoscrizione nuova:

```
status: source "stream", monitored 20, tennis_inplay 9, calcio_inplay 4,
        stream_markets 60, stream_capacity 720, stream_connections 1,
        last_error null, fasi_p95 {stream 7.6, book 0.0, scrittura 160.0}

scan  : TUTTE le righe (7 calcio + 12 tennis) con odds back/lay null,
        mo_total_matched 0.0, odds_ts_ms = 1789651092799..806 -> 13:18:12 UTC
        (cioe' il primo tick in cui e' stato scritto il blocco nullo)

ou OVER_UNDER_25 1.262547088: ts_ms 1789651495681 -> 13:24:55
                              seen_ms 1789651510958 -> 13:25:10  (ADESSO)
                              sel0 back null, lay null, runner_status ACTIVE
```

**Il riavvio non ha risolto.** `fasi_p95.book = 0.0`: il poll REST di fallback non ha
girato nemmeno una volta, né prima né dopo.

### 1.4 Lo stream non è saturo e il tennis non è escluso da nessun tetto

60 mercati con `DEFAULT_MARKETS_PER_CONN = 180` → `plan_shards` calcola
`n = ceil(60/180) = 1` (`stream.py:88`): **tutti** i 60 mercati (tennis compreso) stanno
nell'unico shard, e `stream_capacity 720` non è mai stato avvicinato. Nessun troncamento,
nessuna priorità che tagli fuori il tennis, nessun `covered_ids` parziale.
Verifica di rete: il PID dello scanner (17224) ha **una sola** connessione verso l'host
dello Stream API (`84.20.210.237:443`) — coerente con `stream_connections 1`, e nessun
altro servizio ne tiene una: **il limite Betfair di 10 connessioni/app key non c'entra.**

---

## 2. Chi scrive `odds` / `odds_ts_ms` (domanda 1)

Un solo punto in tutto il repo: **`Betfair/safe_strategy/service.py:494-542`
`Scanner._apply_market_book()`**, chiamato da due sorgenti:

1. **stream** — `service.py:1378-1381` (`for b in self.stream.drain(): self._apply_market_book(b)`);
2. **REST di fallback** — `service.py:1399-1406` → `poll_books()` (`service.py:625-640`,
   `list_market_book` con `EX_BEST_OFFERS`, chunk 25).

**Mappa `market_id → evento`**: `service.py:342-361 _rebuild_market_index()` costruisce
`self.market_meta = {market_id: (sport, meta)}` dal catalogo `MATCH_ODDS` per sport
(`refresh_catalogue`, `service.py:290-338`; chiave `event_id`; proiezione con
`RUNNER_DESCRIPTION`), più i mercati CS/HT/opportunità. I lati tennis (`p1`/`p2` →
`selection_id`) vengono da `scanner.tennis_sides()` (`scanner.py:257-265`, `sort_priority`
1/2). **La mappa è sana**: nelle righe malate i `selection_id` ci sono e sono corretti —
manca la parte "prezzi" del book, non l'accoppiamento mercato↔evento.

Il book viene **dallo stream**, non dal REST: `mo_total_matched = 0.0` ovunque. Lo stream
non manda `tv` se non chiedi `EX_TRADED_VOL` (`betfairlightweight/streaming/cache.py:243`:
`total_matched` resta l'iniziale `0` di `cache.py:214`), mentre `listMarketBook`
restituisce sempre il `totalMatched` vero. `0.0` su tutto ⇒ REST mai girato.

---

## 3. La causa, passo per passo (con file:riga)

### 3.1 `betfairlightweight` pubblica un `MarketBook` senza prezzi

`streaming/cache.py:314-351 MarketBookCache._process_market_definition()`: per ogni runner
della **definizione**, se non c'è già lo crea (`_add_new_runner`, `cache.py:350`) — con
`selection_id`, `status`, e **scalette vuote**. Subito dopo
`streaming/stream.py:211-215 MarketStream._process()` fa `self.on_process(caches)`, cioè
**mette in coda il MarketBook di ogni mercato toccato**, anche quando il messaggio
conteneva solo `marketDefinition` e nessun `rc`.

Lato nostro: `runner.ex.available_to_back == []` → `scanner.price_pair()`
(`scanner.py:219-229`) → `{"back":None,"lay":None,"back_size":None,"lay_size":None}`.

**È esattamente l'impronta in tabella**: `selection_id` e `runner_status` presenti
(vengono dalla definizione), prezzi assenti, `totalMatched` 0.

### 3.2 Il nostro codice accetta quel book come aggiornamento di quote — **difetto n.1**

`Betfair/safe_strategy/service.py:506-533`:

```python
pairs[int(sid)] = {**scanner.price_pair(getattr(r, "ex", None)), ...}
...
odds = {side: pairs.get(sid) ... for side, sid in sides.items()}
ev = self.events.setdefault(meta["event_id"], {})
...
if ev.get("odds") != odds:
    ev["odds_ts_ms"] = int(self._ora() * 1000)   # <-- 530-531
ev["odds"] = odds                                 # <-- 532  SOVRASCRIVE
```

**Nessuna guardia.** Un book senza un solo prezzo cancella le quote buone e — peggio —
**fa avanzare `odds_ts_ms`**, cioè scrive "quote fresche delle 12:47:04" su un blocco che
di quote non ne ha. Stesso vizio in `_apply_opp_book` (`service.py:565-624`) e
`_apply_cs_book` (543-564).

Un book di sola definizione **non è un aggiornamento di prezzi** e non va applicato come
tale.

### 3.3 Il fallback REST non parte mai — **difetto n.2, quello che rende il buco eterno**

`service.py:1384` e `1399-1401`:

```python
covered = self.stream.covered_ids() if self.stream is not None else set()
...
uncovered = [mid for mid in self.relevant_market_ids(sport, now) if mid not in covered]
if uncovered: ... self.poll_books(sport, uncovered)
else:         st.books_ts = now_mono
```

`stream.py:303-309 covered_ids()` ritorna i mercati degli shard **`healthy()`**, e
`stream.py:185-191 healthy()` guarda **solo l'età dell'ultimo messaggio sul socket**,
aggiornata da `_HealthListener` a **ogni** messaggio, heartbeat compresi
(`stream.py:101-116`: `on_data` → `on_message()`), con `heartbeat_ms = 5000`
(`stream.py:48`). In più `_touch()` è chiamato a `stream.py:234` **subito dopo
`subscribe_to_markets`, prima di aver ricevuto un solo book**.

Conseguenza: **una connessione viva che non consegna quote resta "sana" per sempre**,
`covered_ids()` dichiara coperti tutti e 60 i mercati, `uncovered` è vuoto,
`st.books_ts = now_mono` e **`poll_books` non parte mai** (`fasi_p95.book = 0.0` lo
conferma, prima e dopo il riavvio). `last_error` resta `null`, `source` resta `"stream"`,
la UI mostra STREAM verde. **Il buco è permanente e invisibile.**

### 3.4 Cosa è cambiato alle 12:47 — la risottoscrizione continua (**difetto n.3**)

Le partite di calcio sono iniziate alle 12:30 UTC. **Al 15'** scatta
`scanner.py:35 HT_MINUTE_FROM = 15` → `is_ht_candidate()` (`scanner.py:420-423`) →
`service.py:1436-1440` chiama `refresh_ht_catalogue` → nascono i mercati `HALF_TIME_SCORE`,
che entrano in `ranked_relevant_markets` (`service.py:388-391`) → `refresh_stream_set`
(`service.py:469-492`) → `plan_shards` diverso → `MarketStreamPool.set_markets`
(`stream.py:283-288`) → `StreamShard.set_markets` → al primo `drain()` successivo
`maybe_resubscribe()` (`stream.py:170-183`) trova `desired != _subscribed` e, passato il
throttle di 30 s, chiama **`_kick()` = `stream.stop()` sull'UNICA connessione** → il thread
`_run` (`stream.py:206-245`) ricostruisce listener, cache e sottoscrizione.

12:30 + 15' ≈ 12:45-12:47 col minuto IPS: **coincide con il nulling del calcio alle
12:47:04**; il tennis alle 12:48:09 è il giro successivo.

Il punto grave non è il singolo evento: **finché c'è calcio in gioco il set dei mercati
cambia di continuo** (linee O/U che diventano vive, candidati CS al 30', HT dal 15',
partite seguite da Mike, ramo pre-KO), e con `_RESUB_MIN_INTERVAL = 30` (`stream.py:46`)
**l'unica connessione viene abbattuta e rifatta ogni 30 secondi, per ore**. Ogni
ricostruzione azzera la cache di `betfairlightweight` ed è un'occasione perché il primo
messaggio di un mercato sia di sola definizione. È anche, di per sé, un comportamento da
correggere: una risottoscrizione non deve costare la connessione intera.

### 3.5 Una corsa critica in `StreamShard._run` (difetto latente, da chiudere comunque)

`stream.py:216-236`:

```python
stream = self.client.streaming.create_stream(listener=listener)
self._stream = stream          # 219  -> da qui _kick() puo' agire
self._subscribed = set(ids)    # 220  -> dichiara "sottoscritto" prima di esserlo
...
stream.subscribe_to_markets(...)   # 222
self._touch()                      # 234 -> "sano" senza aver ricevuto niente
stream.start()                     # 236
```

`betfairstream.py:53-60 start()` fa `if not self._running: self._connect(); self.authenticate()`
e `stop()` (62-64) mette `_running = False`. Se un `_kick()` (che parte **due volte al
secondo**, da `drain()`) cade fra la 222 e la 236, `start()` **riapre e riautentica un
socket nuovo senza rimandare la `marketSubscription`**: connessione viva, autenticata,
muta. Con `healthy()` misurata sul socket è indistinguibile da uno shard sano.

### 3.6 ⚠️ SMENTITA — i servizi **NON** sono partiti in doppio

L'ipotesi "dopo il riavvio delle 15:13 ogni servizio gira due volte, sotto due alberi di
watchdog" è **falsa**. Prove, entrambe in sola lettura:

**(a) L'albero dei processi.** L'app desktop (PID 2320) ha **8 figli** alle 15:13:41 —
esattamente gli 8 `spawnRunner` di `desktop/main.js:258-292`, uno per servizio. Non due
alberi: uno.
Ogni processo `python.exe` del repo ha **un figlio con la riga di comando IDENTICA**:

```
17552 watchdog                  -> 16376 watchdog                 -> 9376 stream.runner -> 21276 stream.runner
19604 watchdog -- safe...service-> 8036  watchdog -- safe...service-> 22516 safe...service -> 17224 safe...service
15504 watchdog -- omega_service -> 25028 watchdog -- omega_service -> 1848 omega_service -> 1872 omega_service
7648  watchdog -- mike.service  -> 14408 watchdog -- mike.service  -> 17068 mike.service -> 21908 mike.service
...
```

Lo stesso raddoppio compare anche su processi **che l'app non ha lanciato**: il
`Betfair.stream.backtest.certifica` di un agente (21060 → 10052, riga identica) e un
banale `python.exe -` (22096 → 15792). **È il redirector di `.venv\Scripts\python.exe` su
questa macchina** (il launcher esegue l'interprete vero come processo figlio e aspetta):
un artefatto di lancio, non un doppio avvio dell'applicazione.

**(b) Le porte di singola istanza.** Ogni lock è tenuto da **un solo PID**, e in ogni caso
è quello **interno** (il processo vero, non il launcher):

```
47311 -> 21276 stream.runner          47315 -> 17224 safe_strategy.service
47312 -> 10040 tennis_runner          47318 -> 14228 safe_strategy.bot_service
47314 -> 20096 scalper_service        47319 -> 21908 mike.service
47331 -> 21276   47332 -> 10040   47333 -> 21908   47334 -> 1872 omega_service
```

Se ci fossero due istanze vere, la seconda avrebbe trovato la porta occupata e sarebbe
uscita (`single_instance.py:18-36`). **Il lock ha funzionato, e c'è un solo servizio per
tipo.** Non c'è quindi nessun doppio piazzamento ordini, nessun doppio processing della
coda, nessun rischio money-critical da duplicazione: **non è successo**.

**(c) `updated_at` che "salta" su `safe_strategy_scan`** non è la firma di due scanner: è
il throttle per-evento `_PUBLISH_MIN_INTERVAL_SEC = 2,5 s` combinato col write-on-change e
con il passaggio prioritario dei campi critici (`service.py:1163-1178`,
`scanner.critical_signature`): righe diverse vengono riscritte in momenti diversi.

**Resta però vero un problema di igiene**, da correggere a parte (non è la causa di oggi):

* `desktop/main.js` **non chiama `app.requestSingleInstanceLock()`**: due avvii dell'exe
  creerebbero davvero due alberi. Oggi non è successo, ma è possibile.
* `Betfair/stream/watchdog.py:36-37` — il watchdog per scelta **non** prende il lock:
  N watchdog possono coesistere, e la protezione è tutta nel figlio.
* `watchdog.classify_exit` (`watchdog.py:65-82`) riconosce "lock" solo se il figlio muore
  **entro `WATCHDOG_LOCK_GRACE_SEC = 5 s`**: qualunque servizio che prendesse il lock
  dopo una fase lenta (login, catalogo) verrebbe classificato **"crash"** e **riavviato in
  loop contro il lock**. Oggi tutti prendono il lock in testa a `main()` — va tenuto così,
  e vincolato da un test.
* `Betfair/omega/omega_service.py:6049-6065` ha una **copia locale** del lock che su porta
  occupata **ritorna `None`** invece di uscire; `main()` (6110-6113) logga e fa `return`,
  cioè **exit 0** → il watchdog classifica "clean" e si ferma. Funziona, ma è una seconda
  implementazione della stessa regola: va unificata su `single_instance.acquire_...`
  (fail-closed, `SystemExit`) o il giorno che qualcuno tocca quel `return` Omega parte in
  doppio in silenzio.

### 3.7 Perché 4 righe non hanno MAI avuto quote (domanda 3)

Stessa causa, solo più precoce: il **primo** book applicato a quei mercati era già di sola
definizione (12:17:45 — 37 s dopo `started_at` — e poi 12:20:03, 12:35:06, 12:40:02, ognuno
dopo una ricostruzione della connessione). Poiché `ev["odds"]` era `None`, il confronto
`ev.get("odds") != odds` era vero e `odds_ts_ms` è stato scritto **una volta sola**,
restando poi fermo. Non "non hanno mai avuto quote": **hanno ricevuto un book vuoto e
nessuno se n'è accorto.**

(Sono 3 doppi + 1 singolare con KO che il tennis sposta di continuo: entrati nella finestra
`RELEVANT_PRE_KO_SEC` di 20' — `scanner.py:319` — e poi usciti quando Betfair ha spostato
l'orario. `build_rows` usa `is_monitorable`, più larga di `is_relevant_market`: la riga
resta pubblicata, col blocco `null`, senza più nessuna fonte di quote. Anche questo va
detto nel payload invece che taciuto.)

---

## 4. Perché il bot tace (domanda 4)

Due silenzi diversi, entrambi reali:

1. **Tennis, apertura.** `bot_service.process_opportunities` → per `sport == "tennis"`
   chiama `tennis_opportunity.TennisModel.evaluate(payload, now_ts)`
   (`bot_service.py:5663-5668`). In `tennis_opportunity.py:302-307` il campo `odds`
   **esiste** (è un dict con `p1`/`p2`), quindi il `return []` di riga 304 non scatta; si
   arriva a `devig_pair(None, None)` e ogni `_try_side` torna `None` → `evaluate` ritorna
   `[]`. **Nessuna opportunità ⇒ nessun `skip`**: il log `skip` vive dentro
   `_auto_trade_opps`, che con zero opportunità non viene nemmeno chiamato. Non esiste un
   ramo "ho la riga ma non ho i prezzi".
2. **Calcio, apertura.** Il cecchino rivaluta solo le righe il cui `odds_ts_ms` è
   **cambiato** dall'ultimo giro (gate `odds_ts_ms` in `process_anomalies`): con
   `odds_ts_ms` congelato quelle righe non vengono più nemmeno guardate. Silenzio per
   costruzione.

Sul lato **uscite** un log c'è, ma **uno solo**: `_exit_wait(..., "prezzi_non_nel_feed")`
(`bot_service.py:2945`) è deduplicato **al cambio di motivo**
(`bot_service.py:3798-3811`). Scritto una volta alle 12:47, poi più niente.

---

## 5. Rischio per le posizioni aperte (domanda 5)

**Uscite automatiche: FERME, a tempo indeterminato.** Sequenza in `_process_exit`
(`bot_service.py` ≈2930-2950):

* `XE.feed_is_fresh(row, ...)` (`exits.py:399-423`) **passa**: guarda `row.updated_at`, che
  è fresco perché i punteggi continuano ad arrivare. La riga *sembra* viva.
* `XE.market_open(trade, payload)` **passa**: `mo_status` è `OPEN`.
* `prices_from_row(...)` (`bot_service.py:516-543`) trova il blocco della selezione (il
  `selection_id` c'è!) ma `back` e `lay` sono `null` →
  `if not prices or not (prices.get("back") or prices.get("lay"))` →
  **`_exit_wait(..., "prezzi_non_nel_feed")` e `return False`**.

Quindi **sì: le uscite tennis e calcio restano in `exit_wait prezzi_non_nel_feed` finché
il feed non torna.** Nessuna uscita a tempo, nessuna uscita in perdita, nessun green-up,
nessuna copertura Over 4.5 per le posizioni di Mike. Se una partita finisse adesso, la
posizione andrebbe a **settlement con la responsabilità intera**. È la "cecità parziale"
della certificazione 13/09, ma peggiore: **qui la riga è fresca e mente.**

**Cash-out MANUALE dalla UI: FUNZIONA ANCORA.** `_request_cashout`
(`bot_service.py:2291-2380`) ha il fallback H5: se `prices_for(..., allow_rest=False)`
torna vuoto, va a `_book_prices(market=market, trade=trade)`, cioè **legge il book via
REST** e chiude con quello (`res["source"] == "rest"`, `bot_service.py:2362-2372`).
Il **cash-out globale** `cashout_event` (`bot_service.py:2441-2492`) chiama
`_request_cashout` riga per riga ed **eredita lo stesso fallback**.
È, adesso, l'unica via di uscita affidabile.

**Aperture: rischio zero adesso.** Senza prezzi `evaluate` torna `[]` e i gate calcio non
girano: il bot non può aprire niente. Il rischio aperto è tutto sulle **uscite**.

---

## 6. Patch PROPOSTA (non applicata)

### 6.1 Un book senza prezzi non è un aggiornamento di quote

```diff
--- a/Betfair/safe_strategy/scanner.py
+++ b/Betfair/safe_strategy/scanner.py
@@ -229,6 +229,21 @@ def price_pair(ex: Any) -> Dict[str, Optional[float]]:
     }
 
 
+def has_any_price(pairs: Any) -> bool:
+    """Almeno UN prezzo (back o lay) nel book.
+
+    Serve a distinguere un aggiornamento di QUOTE da un book di sola
+    DEFINIZIONE: betfairlightweight, quando il messaggio porta solo
+    ``marketDefinition`` e nessun ``rc``, crea comunque i runner dalla
+    definizione (con selection_id e status) e pubblica il MarketBook con le
+    scalette VUOTE (streaming/cache.py:314-351 + streaming/stream.py:211-215).
+    Applicarlo come se fosse un prezzo cancella le quote buone: e' successo il
+    17/09/2026 alle 12:47:04 UTC su TUTTO il feed, ed e' sopravvissuto al
+    riavvio delle 13:13 UTC.
+    """
+    valori = pairs.values() if isinstance(pairs, dict) else (pairs or [])
+    return any(isinstance(p, dict) and (p.get("back") is not None or p.get("lay") is not None)
+               for p in valori)
+
+
 def selection_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
```

```diff
--- a/Betfair/safe_strategy/service.py
+++ b/Betfair/safe_strategy/service.py
@@ -520,16 +520,34 @@ class Scanner:
         ev = self.events.setdefault(meta["event_id"], {})
         ev["sport"] = sport
+        # la DEFINIZIONE si applica sempre: e' l'unica cosa che il book porta di sicuro
         ev["inplay"] = bool(getattr(book, "inplay", False))
         ev["mo_status"] = getattr(book, "status", None)
         ev["mo_total_matched"] = scanner.num_or_none(getattr(book, "total_matched", None))
-        # ts dell'ULTIMO CAMBIO delle quote 1X2 (non dell'ultimo poll): il motore
-        # opportunità penalizza i prezzi fermi, il write-on-change resta pulito
-        if ev.get("odds") != odds:
-            ev["odds_ts_ms"] = int(self._ora() * 1000)
-        ev["odds"] = odds
+        ora_ms = int(self._ora() * 1000)
+        # 17/09 — UN BOOK SENZA PREZZI NON E' UN AGGIORNAMENTO DI QUOTE.
+        # Sovrascrivere `odds` con un book di sola definizione cancella le quote
+        # buone E fa avanzare `odds_ts_ms`, cioe' dichiara fresche quote che non
+        # esistono: le uscite finiscono in `prezzi_non_nel_feed` per sempre e
+        # nessuno lo vede.
+        if scanner.has_any_price(pairs):
+            if ev.get("odds") != odds:
+                ev["odds_ts_ms"] = ora_ms
+            ev["odds"] = odds
+            ev["odds_seen_ms"] = ora_ms          # ultima osservazione CON prezzi
+            self.stream_price_mono[str(meta["market_id"])] = self._ora_mono()
+        else:
+            # il blocco nasce una volta sola, perche' la riga dica onestamente
+            # "quote assenti" — ma senza timestamp di prezzo
+            ev.setdefault("odds", odds)
+            ev["odds_vuote_ms"] = ora_ms
+            self.book_vuoti += 1
+            self.book_vuoti_mid.add(str(meta["market_id"]))
```

Stesso trattamento per `_apply_opp_book` (`service.py:565-624`) e `_apply_cs_book`
(543-564): se nessuna selezione ha un prezzo, **non sostituire** il blocco in cache —
aggiornare solo `seen_ms` e contare il book vuoto.

### 6.2 Il fallback REST si decide sulle QUOTE ricevute, non sul socket vivo

```diff
--- a/Betfair/safe_strategy/stream.py
+++ b/Betfair/safe_strategy/stream.py
@@ -46,6 +46,9 @@
 _RESUB_MIN_INTERVAL = 30.0
 _HEALTHY_MAX_AGE_SEC = 30.0
+# uno shard che riceve heartbeat ma non BOOK non copre niente: oltre questa
+# eta' i suoi mercati tornano al poll REST (17/09: ore di blackout invisibile
+# perche' healthy() guardava solo il socket)
+_SERVING_MAX_AGE_SEC = 20.0
 _HEARTBEAT_MS = 5000
@@ -128,6 +131,8 @@ class StreamShard:
         self._last_msg_mono = 0.0
+        self._last_book_mono = 0.0
+        self.books = 0
@@ -193,12 +198,26 @@ class StreamShard:
     def drain(self) -> List[Any]:
         out: List[Any] = []
         while True:
             try:
                 books = self.queue.get_nowait()
             except queue.Empty:
                 break
             if books:
                 out.extend(books)
+        if out:
+            self._last_book_mono = time.monotonic()
+            self.books += len(out)
         self.maybe_resubscribe()
         return out
+
+    def serving(self) -> bool:
+        """Sta consegnando BOOK, non solo heartbeat."""
+        return (self.healthy() and self._last_book_mono > 0.0
+                and time.monotonic() - self._last_book_mono < _SERVING_MAX_AGE_SEC)
+
+    def stato(self) -> dict:
+        """Referto per lo status (visibilita', 17/09)."""
+        mono = time.monotonic()
+        eta = lambda t: (round(mono - t, 1) if t else None)  # noqa: E731
+        return {"i": self.index, "desired": self.desired_count(),
+                "subscribed": len(self._subscribed), "books": self.books,
+                "eta_book_s": eta(self._last_book_mono),
+                "eta_msg_s": eta(self._last_msg_mono),
+                "eta_resub_s": eta(self._last_resub)}
@@ -303,8 +318,8 @@ class MarketStreamPool:
     def covered_ids(self) -> Set[str]:
-        """Mercati serviti da shard VIVI: tutto il resto va al fallback REST."""
+        """Mercati serviti da shard che CONSEGNANO: il resto va al fallback REST."""
         out: Set[str] = set()
         for s in self.shards:
-            if s.healthy():
+            if s.serving():
                 out |= s.subscribed_ids()
         return out
```

E, nel tick, il filtro fine **per mercato** — è questo che copre il caso di oggi, in cui i
book arrivano ma **senza prezzi**:

```diff
--- a/Betfair/safe_strategy/service.py
+++ b/Betfair/safe_strategy/service.py
@@ -1384,7 +1384,15 @@ class Scanner:
-            covered = self.stream.covered_ids() if self.stream is not None else set()
+            # COPERTO = lo stream ha dato QUOTE di quel mercato di recente.
+            # Un mercato sottoscritto che riceve solo definizioni NON e' coperto:
+            # deve tornare al REST, o resta senza prezzi per sempre (17/09).
+            covered = set()
+            if self.stream is not None:
+                for mid in self.stream.covered_ids():
+                    ts = self.stream_price_mono.get(mid)
+                    if ts is not None and now_mono - ts <= _STREAM_PRICE_MAX_AGE_SEC:
+                        covered.add(mid)
```

con `_STREAM_PRICE_MAX_AGE_SEC = 20.0` e `self.stream_price_mono: Dict[str, float] = {}`
inizializzato in `__init__`. Un mercato appena sottoscritto non ha ancora un prezzo →
finisce nel REST per un giro: è il comportamento voluto (mai un buco dati), e costa lo
stesso poll che il codice già fa quando lo stream è giù.

### 6.3 La risottoscrizione non deve costare la connessione

```diff
--- a/Betfair/safe_strategy/stream.py
+++ b/Betfair/safe_strategy/stream.py
@@ -170,10 +170,20 @@ class StreamShard:
     def maybe_resubscribe(self) -> None:
+        """Ricrea la subscription SOLO per un cambio che conta.
+
+        17/09 — con calcio in gioco il set cambia in continuazione (linee O/U,
+        candidati CS/HT, partite di Mike): cosi' com'era, l'UNICA connessione
+        veniva abbattuta e rifatta OGNI 30 SECONDI per ore. Ogni ricostruzione
+        azzera la cache di betfairlightweight ed e' un'occasione per ricevere
+        un'immagine di sola definizione.
+        """
         with self._lock:
             desired = set(self._desired)
         if self._stream is None:
             return
         if not desired:
             self._kick()
             return
-        if desired != self._subscribed and time.monotonic() - self._last_resub > _RESUB_MIN_INTERVAL:
+        mancanti = desired - self._subscribed          # mercati NUOVI: servono davvero
+        in_piu = self._subscribed - desired            # mercati usciti: costano poco
+        if not mancanti and len(in_piu) < _RESUB_EXTRA_TOLLERATI:
+            return                                     # niente strappo per soli mercati in meno
+        if time.monotonic() - self._last_resub > _RESUB_MIN_INTERVAL:
             self._last_resub = time.monotonic()
             self._kick()
```

e la corsa di §3.5 si chiude pubblicando `self._stream` **dopo** la sottoscrizione:

```diff
-                self._stream = stream
-                self._subscribed = set(ids)
-                self._last_resub = time.monotonic()
                 stream.subscribe_to_markets(...)
+                self._stream = stream            # solo ORA _kick() puo' agire
+                self._subscribed = set(ids)
+                self._last_resub = time.monotonic()
-                self._touch()
+                # NIENTE _touch() qui: la salute la fa il primo messaggio VERO
```

### 6.4 Lo status dice la verità

```diff
--- a/Betfair/safe_strategy/service.py
+++ b/Betfair/safe_strategy/service.py
@@ -1296,12 +1296,26 @@ class Scanner:
             "stream_markets": len(self.stream.covered_ids()) if self.stream else 0,
             "stream_capacity": self.stream.capacity if self.stream else 0,
             "stream_connections": self.stream.active_connections() if self.stream else 0,
+            # 17/09 — un book SENZA prezzi e' un evento da CONTARE, non da subire
+            "stream_books_vuoti": self.book_vuoti,
+            "stream_mercati_senza_quote": len(self.book_vuoti_mid),
+            "stream_shards": [s.stato() for s in self.stream.shards] if self.stream else [],
+            "mercati_rilevanti_senza_prezzo": senza_prezzo,
             "last_error": self.last_error,
```

più il **freno di visibilità**: se `senza_prezzo > 0` da oltre 30 s,
`self.last_error = f"quote assenti su {senza_prezzo} mercati da {eta:.0f}s"`.
Oggi `last_error` era `null` mentre il feed era morto da ore: è questo che ha reso
l'incidente invisibile al trader.

### 6.5 Il bot lo dice: `skip` con motivo «quote assenti»

```diff
--- a/Betfair/safe_strategy/bot_service.py
+++ b/Betfair/safe_strategy/bot_service.py
@@ (process_opportunities, ramo tennis, PRIMA di evaluate)
         if sport == "tennis":
             if tennis_model is None:
                 continue
+            # 17/09 — LA RIGA C'E' MA I PREZZI NO. `evaluate` tornerebbe []
+            # in silenzio e il trader non saprebbe MAI perche' il bot tace.
+            if not _ha_quote(payload):
+                _log_skip_dedup(db, {"event_id": event_id, "sport": "tennis",
+                                     "reason": "quote_assenti",
+                                     "signal_key": "quote_assenti",
+                                     "mo_market_id": payload.get("mo_market_id")})
+                continue
```

```python
def _ha_quote(payload: dict[str, Any]) -> bool:
    """Il payload porta almeno un prezzo utilizzabile sul MATCH_ODDS."""
    odds = payload.get("odds")
    if not isinstance(odds, dict):
        return False
    return any(isinstance(b, dict) and (b.get("back") is not None or b.get("lay") is not None)
               for b in odds.values())
```

Stesso controllo nel ramo calcio (prima di `resolve_event_lambdas`) e — dentro
`_process_exit` — `prezzi_non_nel_feed` deve **ri-loggare almeno una volta al minuto**
finché dura, invece di scriversi una volta sola.

### 6.6 Igiene di avvio (non è la causa di oggi, ma va chiuso)

* `desktop/main.js`: aggiungere `app.requestSingleInstanceLock()` in testa e uscire se
  torna `false` (oggi due avvii dell'exe creerebbero davvero due alberi).
* `Betfair/omega/omega_service.py:6049`: sostituire la copia locale del lock con
  `single_instance.acquire_single_instance_lock` (fail-closed, `SystemExit`), così la
  regola vive in un posto solo.
* Test di contratto: **ogni servizio prende il lock entro il primo secondo di `main()`**,
  prima di qualunque I/O di rete — altrimenti `watchdog.classify_exit` lo scambia per un
  crash (grazia 5 s, `watchdog.py:80`) e lo riavvia in loop contro il lock.

---

## 7. Test (RED prima della patch, falsificazione obbligatoria)

Finti con le chiavi e i tipi del vero (`RunnerBook.ex = None`, `status="ACTIVE"`,
`selection_id` int, `total_matched=0`, `inplay=True`, `status="OPEN"`): è esattamente
quello che `betfairlightweight` produce su un messaggio di sola definizione.

1. `test_book_di_sola_definizione_non_cancella_le_quote` — book con prezzi, poi book con
   gli stessi runner e `ex=None`: `ev["odds"]` **invariato**, `odds_ts_ms` **invariato**,
   `book_vuoti == 1`. *Falsificazione*: togliere la guardia 6.1 → deve fallire su `odds`.
2. `test_book_vuoto_non_fa_avanzare_odds_ts_ms` — solo book vuoti dall'inizio: `odds` è il
   blocco null (onesto) ma `odds_ts_ms is None`. *Falsificazione*: rimettere
   `ev["odds_ts_ms"] = ora` incondizionato → deve fallire.
3. `test_mercato_senza_prezzi_torna_al_poll_rest` — shard `healthy()` **vero** e
   sottoscritto, ma nessun book **con prezzi** da 25 s: il tick chiama `poll_books` con
   quel market_id. *Falsificazione*: riportare `covered` su `covered_ids()` → deve fallire.
   **È il test che oggi non c'è e che avrebbe impedito l'incidente.**
4. `test_shard_con_soli_heartbeat_non_e_serving` — `_touch()` chiamato, `drain()` sempre
   vuoto → `serving()` falso dopo `_SERVING_MAX_AGE_SEC`, `healthy()` ancora vero.
5. `test_resubscribe_solo_per_mercati_nuovi` — set che perde mercati ma non ne aggiunge:
   **nessun `_kick()`**. *Falsificazione*: vecchia condizione `desired != subscribed` →
   deve fallire (dimostra lo strappo ogni 30 s).
6. `test_status_denuncia_le_quote_assenti` — dopo N book vuoti: `stream_books_vuoti == N`,
   `stream_mercati_senza_quote` corretto, `last_error` non nullo oltre i 30 s.
7. `test_skip_quote_assenti_tennis` — payload in-play con `odds.p1/p2` tutti null →
   esattamente **un** `skip` con `reason == "quote_assenti"` per evento (dedup), e
   `evaluate` **non** chiamata.
8. `test_exit_wait_prezzi_non_nel_feed_si_ripete` — prezzi assenti per 3 minuti: almeno 3
   `exit_wait`, non uno solo.
9. `test_ogni_servizio_prende_il_lock_subito` (contratto) — per ciascun `main()` dei
   servizi: la prima chiamata di rete non precede `acquire_single_instance_lock`.
10. **Replay sul banco comune** — `python -m Betfair.stream.backtest.certifica safe ...` su
    una registrazione reale in cui si inietta
    `book con prezzi → book di sola definizione → book con prezzi`: la posizione aperta
    deve **uscire** (il feed non si è mai davvero interrotto), mentre col codice di oggi
    resta dentro. Copertura §6: consapevolezza dell'ordine invariata, nessun ordine nuovo
    generato dal book vuoto.

---

## 8. Cosa fare SUBITO, dal vivo (col rischio di ciascuna opzione)

> Il riavvio delle 15:13 **non ha risolto** (§1.3): non rifarlo aspettandosi un esito
> diverso.

**1. Proteggere le posizioni: chiudere a mano quello che va chiuso.**
Il bottone **Cash out** e il **cash-out globale** della partita **funzionano ancora**:
leggono il book via REST quando il feed non ha prezzi (`bot_service.py:2362-2372`,
`res["source"] == "rest"`). È l'unica via di uscita affidabile finché il feed non torna.
*Rischio*: nessuno di sistema; è una decisione di trading, che resta dell'utente.

**2. Stabilire dove si rompe, con due letture (nessuna scrittura).**
 a. `listMarketBook` (REST, `EX_BEST_OFFERS`) su 2-3 market_id malati
    (`1.262481547` tennis, `1.262547079` calcio): se il REST **ha** i prezzi, il problema è
    la nostra sottoscrizione stream.
 b. Una sottoscrizione stream di prova con gli **stessi identici parametri** del servizio
    — `fields=["EX_BEST_OFFERS","EX_MARKET_DEF"]`, `ladder_levels=1`,
    **`conflate_ms=1000`, `heartbeat_ms=5000`, `segmentation_enabled=True`, e gli stessi
    60 market_id** — non con una manciata di mercati: se la prova "ridotta" prende i prezzi
    e quella "identica" no, il colpevole è uno di quei parametri o il volume, ed è
    isolabile in due tentativi.
*Rischio*: una connessione stream in più per ~30 s (il conto app-key è a 1 su 10: §1.4).

**3. NON spegnere Safe tennis.**
Spegnere il bot **non chiude niente** e toglie l'unica automazione che riprenderebbe le
uscite appena il feed torna. In questo stato il bot **non può aprire nulla** (`evaluate`
torna `[]`): il rischio di apertura è già zero. Se si vuole comunque un freno, la cosa
corretta è spegnere il solo **auto-trading di apertura**, lasciando vive le uscite.

**4. NON toccare `SAFE_STRATEGY_STREAM_CONNS` / `..._MARKETS_PER_CONN`.**
Non c'entrano: 60 mercati su 720 di capacità, nessun troncamento. Alzarli aggiungerebbe
solo connessioni e risottoscrizioni.

**5. NON andare a caccia del doppio avvio.** Non esiste (§3.6): i lock sono tenuti da un
solo PID per servizio. Spegnere "il secondo processo" significherebbe uccidere il
launcher e con lui il servizio vero.

**6. Non applicare la patch a caldo sul checkout principale** senza il giro di
certificazione previsto (`PROCESSO_STANDARD_BOT.md` §6/§7): tocca il percorso che decide se
un prezzo è valido, cioè quello con cui si chiudono posizioni vere.

---

## 9. Cosa NON ho potuto verificare

* **Il perché lato Betfair.** So *cosa* arriva (definizioni sì, prezzi no), *da quando*
  (12:47:04 UTC) e che **sopravvive a un riavvio completo** (13:13 UTC → ancora vuoto alle
  13:25). Non so *perché*: servirebbe il log grezzo dello stream. `betfairlightweight`
  logga a INFO `[MarketStream: n]: ... added`, `status: ...`,
  `Missing marketDefinition ...` e a DEBUG ogni messaggio. Lo scanner gira con
  `logging.basicConfig(level=INFO)` (`service.py:1614-1616`) e lo stdout è catturato
  dall'app desktop: **non esiste un file di log su disco**. Da fare al prossimo avvio:
  redirigere lo stdout dei servizi su file (`desktop/main.js`, `spawn` con `stdio` su un
  file) o alzare a DEBUG `betfairlightweight.streaming` per 60 s. Senza quello, "problema
  di Betfair" e "sottoscrizione nostra che nasce monca" restano indistinguibili.
* **La prova (b) del §8.2** — subscription di prova con i parametri IDENTICI (conflate,
  heartbeat, segmentazione, 60 mercati) — non l'ho eseguita: è una connessione nuova verso
  Betfair, fuori dal mandato di sola lettura. È l'esperimento che chiude la diagnosi.
* **Gli altri consumatori Betfair.** Runner calcio (PID 21276), tennis (10040), Mike
  (21908), Omega (1872) sono vivi e nessuno di loro ha una connessione verso l'host dello
  Stream API: non ho potuto usarli come controprova.
* **`safe_strategy_activity`**: la GET ha risposto 400 (nome tabella/colonne diverso da
  quello provato), quindi non ho contato gli `exit_wait` né i `skip` reali. Le conclusioni
  del §4 sono lette sul codice, non sui dati.
* **La corsa di §3.5** è dimostrata sul codice (`stream.py:219-236` +
  `betfairstream.py:53-64`), non riprodotta.
* **L'atomicità del claim delle richieste in coda** (doppio piazzamento con due
  `bot_service`): non verificata — non serve più, perché la duplicazione non esiste
  (§3.6b). Resta un controllo da fare a freddo, come difesa in profondità.
