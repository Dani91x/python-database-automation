# LATENZA TENNIS — dove se ne va il tempo, e come si arriva «al ms»

**Data**: 17/09/2026 · **Ordine dell'utente (verbatim)**: «la lentezza dei dati: capisci come
possiamo rendere in tempo reale il tutto, se possiamo usare la stream api invece che rest, nel
tennis tutto deve essere al ms».

**Natura di questo documento**: analisi e progetto. Nessuna riga di codice toccata, nessun processo
avviato, nessuna chiamata a Betfair, sole letture sul DB. Nessuna regola di strategia proposta in
modifica.

**Misure fatte oggi** (sola lettura, 17/09 h 09:00-09:20): latenze PostgREST dal client di
produzione, righe del feed vive, `meta.tempi`/`meta.esecuzione` dei trade 297/298/299, stato dello
scanner, giro su WebSocket di loopback (laboratorio in-processo), scarto dell'orologio contro NTP.
Ciò che non ho potuto misurare è elencato in fondo, con il perché.

---

## 0. Il risultato in tre righe

1. Il collo di bottiglia **non è la Stream API**: lo scanner la usa già (`source: "stream"`,
   1 connessione, 11 mercati, misurato oggi). Il collo di bottiglia è il **database usato come bus**
   fra scanner e bot, e il **poll** del bot.
2. Una chiamata PostgREST costa **92-307 ms** qualunque cosa chieda; un giro su WebSocket
   `127.0.0.1` con lo stesso dato costa **0,59 ms** (p50). Il canale locale è **~150-250× più
   veloce** del DB, ed **esiste già** (`Betfair/stream/local_channel.py`).
3. Dei **~8,5 s** misurati fra «prezzo visto dal nostro scanner» e «Betfair risponde», **~3 s sono
   il bet delay di Betfair** e non si toccano. Gli altri **~5,5 s sono nostri** e sono quasi tutti
   attese e tasse di rete verso Supabase.

⚠️ **Prima di tutto: l'orologio di questa macchina è indietro di 2,07 s.** Misurato ora contro due
NTP indipendenti (time.windows.com: +2082,5 / +2068,3 / +2069,2 ms; pool.ntp.org: +2078,7 / +2069,3
/ +2068,4 ms; RTT 11-57 ms). Il servizio Ora di Windows **non è avviato**
(`w32tm /query /status` → `0x80070426`, «Servizio non avviato»). Conseguenza: **ogni confronto fra
un nostro istante e un istante di Betfair è sbagliato di ~2 s.** Gli istanti interni (t0…t5) sono
tutti sullo stesso orologio e restano validi fra loro. Lo scarto era già noto e **zittito**:
`Betfair/safe_strategy/stream.py:180-182` mette `max_latency=None` con il commento «con l'orologio
locale sfasato (−2.8s misurati) il warning "Latency high" scattava a OGNI messaggio» — cioè l'unico
allarme che l'avrebbe detto è stato spento. Sistemare l'orologio **non toglie un millisecondo di
latenza vera**: toglie 2 s di errore di misura.

---

## 1. Budget di latenza, salto per salto (tennis in-play, percorso di oggi)

Riferimento: trade **297** e **298** (aperture automatiche tennis, live, percorso REST) e **299**
(chiusura approvata dall'utente). Tutti gli istanti in ms di orologio del mondo, presi dal codice
di produzione (`bot_service._catena_dei_tempi:3776-3823`, `execution.place:536-620`).

| salto | che cos'è | 297 | 298 | 299 | chi lo produce |
|---|---|---|---|---|---|
| **t(-1) → t0** | prezzo pubblicato da Betfair → il nostro scanner lo lavora | **non misurato** | — | — | conflate 1 s + tick scanner |
| **t0 → t1** | scanner lavora il book → riga scritta sul DB | 1,0 ms | 1,0 ms | — | `service.py:531` → `:1270` |
| **t1 → t2** | riga scritta → riga in mano al bot | **2.858,8 ms** | **2.018,6 ms** | — | poll 2 s + tassa PostgREST |
| **t2 → t3** | riga in mano → decisione presa | **911,5 ms** | **1.674,2 ms** | — | 8-12 giri PostgREST di ciclo |
| **t3 → t4** | decisione → ordine inviato | **213,6 ms** | **259,8 ms** | — | **una** INSERT di riserva |
| **t4 → t5** | invio → risposta di Betfair | **4.481,1 ms** | **3.213,0 ms** | **3.196,6 ms** | **bet delay Betfair + rete** |
| **totale t0→t5** | | **8.465 ms** | **7.167 ms** | — | |
| clic utente → invio (299) | | — | — | **4.300 ms** | poll richieste + corsia chiusure |

### 1.1 Il salto invisibile: prima di t0

`t0` **non è «quando il prezzo è cambiato su Betfair»**. È `odds_ts_ms`, e viene messo qui:

```
Betfair/safe_strategy/service.py:531      ev["odds_ts_ms"] = int(self._ora() * 1000)
```

cioè con l'**orologio locale**, nel momento in cui lo scanner **lavora** il book uscito dalla coda
dello stream (`_apply_book`). Fra la pubblicazione di Betfair e quell'istante ci sono due attese
strutturali, **oggi non misurate perché non esiste il campo per misurarle**:

* **conflate 1.000 ms** sulla sottoscrizione: `stream.py:49` `_CONFLATE_MS = 1000`, applicato a
  `:228`. Betfair accorpa i cambiamenti e ce li manda al massimo una volta al secondo → 0-1.000 ms,
  media ~500 ms.
* **cadenza del tick dello scanner**: `service.py:1674-1676` `while True: scan.tick(); time.sleep(0.5)`.
  Misurato oggi su `safe_strategy_status` (id=`scanner`): tick p50 **3,7 ms**, p95 **799,6 ms**,
  max 7.074,9 ms; fasi p95: `stream` 145,6 ms, `scrittura` **518,5 ms**. → 0-1,3 s, media ~0,65 s.

**Stima strutturale del salto cieco: 0,5-2,3 s.** Tutta la catena dei tempi che oggi leggiamo è
**ottimista di questa quantità**. È lo stesso difetto già corretto il 14/09 su t3 («un cronometro che
sbaglia a nostro favore è peggio di nessun cronometro», `bot_service.py:3806-3812`), ma un salto
più a monte.

**Come si apre, senza una sola chiamata in più**: il `MarketBook` che lo scanner ha già in mano
porta `publish_time` (betfairlightweight, `streaming/cache.py:411` `"publishTime"` →
`MarketBook.publish_time`). Basta scrivere accanto a `odds_ts_ms` una chiave **additiva**
`odds_pt_ms`, mai al posto dell'altra. ⚠️ è l'orologio di **Betfair**: non si può sottrarre dal
nostro finché l'orologio della macchina non è sincronizzato (§0).

### 1.2 t0 → t1 = 1 ms **è il caso migliore, non quello tipico**

Sui trade 297/298 la riga è uscita nello stesso tick in cui il prezzo è stato lavorato. Ma la
scrittura ha un freno per evento:

```
Betfair/safe_strategy/service.py:87-90    _PUBLISH_MIN_INTERVAL_SEC = 2.5
Betfair/safe_strategy/service.py:1163-1168
    if (self.written_crit.get(eid) == crit
        and mono - self.last_pub_mono.get(eid, 0.0) < _PUBLISH_MIN_INTERVAL_SEC): continue
```

Il freno **non** si applica quando cambia la firma CRITICA (`scanner.critical_signature:443`; per il
tennis: set/game/stato mercato/in-play/`score_raw`). Si applica invece a un cambiamento **di sole
quote**. 297 e 298 sono passati subito perché era cambiato anche lo stato IPS. **Un movimento di
prezzo puro può aspettare fino a 2,5 s prima di essere scritto.** Il freno è giusto e va tenuto — è
la lezione del 13/09 (budget IO esaurito) — ma non deve stare sul percorso della decisione (§3.2).

### 1.3 t1 → t2 = 2,0-2,9 s — dove vanno davvero

Non è «il poll di 2 s». È il poll **più il ciclo intero**, perché t2 viene timbrato dopo la lettura
del feed e il ciclo precedente deve finire prima che il successivo cominci:

```
bot_service.py:61      "poll_interval_s": 2
bot_service.py:6968    interval = float(params.get("poll_interval_s") or 2.0)
bot_service.py:7016    if _attesa_interrompibile(max(interval, 1.0), _APERTE.get("n", 0)):
bot_service.py:6460    control = db.read_control()       # prima lettura del ciclo
bot_service.py:6497    rows = list(db.fetch_scan_rows())  # feed unico, UNA lettura per ciclo
bot_service.py:6505    _LETTURA_FEED["ms"] = round(time.time() * 1000.0, 1)   # ← t2
```

**Tassa PostgREST misurata oggi** (client di produzione `bot_db`, 3 tentativi ciascuna):

| lettura | ms | mediana |
|---|---|---|
| `read_control()` | 2195,1 / 188,7 / 145,0 | 189 |
| `fetch_scan_rows()` (10 righe, 9,5 KB) | 307,0 / 187,7 / 156,8 | 188 |
| `pending_requests(limit=1)` | 173,2 / 96,4 / 94,4 | 96 |
| `pending_requests(limit=50)` | 165,0 / 180,4 / 131,5 | 165 |
| `open_trades()` | 224,3 / 245,9 / 93,2 | 224 |
| `aggregates()` | 305,4 / 361,5 / 171,3 | 305 |
| `place_attempts()` | 120,3 / 92,9 / 87,7 | 93 |
| `scanner_status()` | 118,9 / 131,3 | 125 |

**E non è la rete.** Misurato in diretta contro l'host Supabase:

* connessione TCP pura: **12,5-12,7 ms** (il primo 40,9 ms);
* `GET` di **una riga per chiave primaria**, connessione già calda: **485,3 → 113,3 → 162,4 →
  116,4 → 91,6 → 95,7 ms**;
* `GET` del feed intero (10 righe), connessione calda: **204,1 / 198,2 / 153,3 ms**;
* `GET` di una riga con **connessione nuova**: **956,8 / 548,4 / 611,8 ms**.

→ dei ~100-200 ms di una lettura, **~13 ms sono rete e il resto è server** (PostgREST + Postgres +
pooler). Non si ottimizza con un indice: è il **costo di esistere di ogni andata e ritorno**. E una
connessione fredda costa mezzo secondo — il che spiega anche i primi valori anomali della tabella.

**Conto del periodo effettivo del ciclo**: 2 s di attesa + 1,3-2,5 s di giri PostgREST (§1.4) =
**3,3-4,5 s**. Una riga scritta a caso dentro quel periodo aspetta in media 1,7-2,3 s, più
`read_control` più `fetch_scan_rows`. **2,0-2,9 s misurati: torna esattamente.**

### 1.4 t2 → t3 = 0,9-1,7 s — che cosa fa il bot fra lettura e decisione

**Non rilegge il feed. Non interroga la freschezza. Non tocca la conferma punteggio.** Fa passare
tutte le fasi di **protezione** che stanno per contratto prima delle aperture, e ognuna paga la sua
tassa PostgREST. In ordine, da `run_once` (`bot_service.py:6443`):

| # | fase | riga | letture DB |
|---|---|---|---|
| 1 | `poll_flumine` (coda flumine, sempre) | `:6513` | 1+ |
| 2 | `reconcile_pending` → `db.list_trades("pending")` | `:6515` / `:676` | 1 |
| 3 | `process_requests(solo_chiusure=True)` → `pending_requests()` | `:6543` / `:1908` | 1 (~165 ms) |
| 4 | `settle_open` | `:6548` | cond. |
| 5 | `seed_place_attempts` → `place_attempts()` | `:6552` | 1 (~93 ms) |
| 6 | `build_risk_ctx` → `open_trades()` + `aggregates(mode)` | `:6555` / `:4708`,`:4735` | 2 (~224+305 ms) |
| 7 | `check_feed_blind` | `:6562` | cond. |
| 8 | `unwind_incomplete_combos` | `:6566` | cond. |
| 9 | `process_requests` (completa) → `fail_stale_processing()` + `pending_requests()` | `:6574` | 2 |
| 10 | `process_exits` | `:6580` | cond. |
| 11 | `scan_and_place` → `engine.evaluate(rows)` (RAM) → `_traded_keys` → `_scanner_ts` | `:6605` / `:4976`,`:4991`,`:5051` | 2 (~125 ms + 1) |
| | **t3 timbrato** dentro `_catena_dei_tempi` al momento della riserva | `:3813`, chiamato da `:5223` | |

**8-12 andate e ritorno × 100-250 ms = 0,9-2,5 s.** Misurato 0,9-1,7 s: torna.

**La conferma del punteggio non c'entra e non si tocca.** È strategia: `engine.py:256`
`"scoreConfirmSec": 15` per la variante tennis, verificata da `_score_confirm_check:875-881` su un
tracker tenuto **in RAM** (`TennisScoreStability:1386`, `track_tennis_score_stability:1409-1417`,
mappa `self._tn_stab:1644`). Non costa una lettura e non entra in questo budget. **Ma**: quei 15 s
partono da *quando NOI osserviamo* il punteggio (`now_ms` a `:1732`). Arrivare 5 s prima sposta
l'ammissibilità 5 s prima **senza cambiare la regola di un millisecondo**. È il guadagno vero della
velocità su una strategia che ha una finestra di conferma.

### 1.5 t3 → t4 = 213-260 ms — è **una** scrittura

```
bot_service.py:5259    trade_id = db.insert_trade(row)  # RISERVA: l'unique index fa da lock
execution.py:536       t4 = _ora_ms()
```

Il pattern è **reserve-first**: la riga nasce `pending` con `meta.phase='reserved'`
(`_reserve_row:4226-4251`) e l'indice unico è il lucchetto contro il doppio ordine. Quei 250 ms sono
il prezzo di quel lucchetto, pagati **prima** che l'ordine parta.

### 1.6 t4 → t5 = 3,2-4,5 s — **non è nostro**

È il **bet delay** che Betfair impone agli ordini in-play. Valore misurato sulle registrazioni raw
reali del tennis, mai assunto:

* `_validazione_tennis_1tick_20260710/fisica_report.txt:2` — «betDelay in-play visti:
  Counter({(3,): 52, (5,): 7})»;
* `Betfair/stream/tennis_scalper/BIBBIA_SCALPER_TENNIS.md:240-241` — «betDelay tennis: **3s** (5s su
  alcuni ITF) — SEMPRE letto dai raw (`marketDefinition.betDelay`), mai hardcoded. Pre-match = 0.»

I numeri tornano al millisecondo: **3.213,0 ms** (298) e **3.196,6 ms** (299) = 3.000 ms di delay +
~200 ms di andata e ritorno REST. Il 297 (4.481,1 ms) ha ~1,5 s in più di risposta, non di delay.

**La verifica con `placedDate` è l'unica falsata dall'orologio.** Il brief riporta «placedDate
Betfair 08:40:42 vs invio 08:40:39,2 = +2,8 s». Con lo scarto di §0 (locale indietro di 2,07 s),
il nostro invio corrisponde alle 08:40:41,3 vere: **l'ordine ha raggiunto Betfair in ~0,7 s**, poi
3 s di delay, poi il ritorno. La lettura «Betfair ci mette 2,8 s ad accettare» è un artefatto
dell'orologio.

**Distinzione richiesta, in chiaro:**

* **ritardo imposto da Betfair**: 3.000 ms (5.000 su alcuni ITF). **Non riducibile.** Non con lo
  stream, non con flumine, non con una sessione più calda: la Stream API **non piazza ordini** — in
  flumine il place è REST esattamente come da noi, e l'order stream serve a sapere l'**esito**, non
  a mandare l'ordine.
* **latenza REST nostra**: ~200-700 ms di andata + il ritorno. Comprimibile di poco (sessione calda,
  §3.5), ma è già il termine piccolo.

---

## 2. Il `betDelay`: dove vive, chi lo legge, dove leggerlo

**Nasce** nel `marketDefinition` dello stream → `MarketBook.bet_delay` (betfairlightweight).
**Sopravvive integro** solo nei file `.raw.jsonl`; lo snapshot curato lo **butta via**
(`Betfair/stream/recorder.py:50-81` `serialize_book()` tiene `market_id, pt, status, inplay, tv,
runners{b,l,ltp,tv,trd}` e basta). **Non esiste nessuna colonna `bet_delay`** in `sql/` né in
`migrations/`: viaggia solo dentro il JSONB di `safe_strategy_scan.payload`.

**Il bot Safe NON lo legge prima di piazzare.** L'unica lettura di produzione è nello scanner:

```
Betfair/safe_strategy/service.py:595   bet_delay=scanner.num_or_none(getattr(book, "bet_delay", None))
Betfair/safe_strategy/scanner.py:542-545   if bet_delay is not None: blk["bet_delay"] = int(bet_delay)
```

ed è dentro `_apply_opp_book`, cioè **solo i mercati a gol del calcio** (serve a Mike, che con quel
numero differisce il place in paper: `Betfair/mike/service.py:3232`). I blocchi MATCH_ODDS e tutti i
blocchi **tennis** passano da `scanner.build_market_block` **senza** `bet_delay`. In
`Betfair/safe_strategy/execution.py` la parola compare solo in docstring (`:15`): zero occorrenze nel
codice di decisione e di piazzamento.

**Dove leggerlo, a costo zero**: nello stesso `book` che `_apply_book` ha già in mano
(`service.py:~500-531`), con la riga identica a quella già in produzione a `:595`. Una chiave
**additiva** nel payload tennis. Nessuna chiamata di rete, nessuna migrazione, nessuna colonna.

**Perché serve**: oggi il bot non sa a quale ritardo è soggetto; la pagina non lo mostra per il
tennis; e la certificazione sul replay non può verificare che il delay applicato sia quello vero di
*quel* mercato invece di un 3 s assunto. Le registrazioni raw tennis vere stanno **fuori dal repo**:
`C:\Users\Admin\Desktop\tennis_rec` (65 MB, **100 eventi** del 07/07, `betDelay` 3 s su 52 e 5 s su
7). In `_live_raw` (4,3 GB) **non c'è tennis reale**: i soli tennis lì dentro sono sintetici
(`_synth_safe_tennis`).

---

## 3. Stream vs REST — il percorso «al ms», salto per salto

**Premessa che cambia la domanda.** «Usare la Stream API invece del REST» è già fatto **dove
serviva**: lo scanner consuma la Exchange Stream API ufficiale su un pool shardato
(`Betfair/safe_strategy/stream.py`, `MarketStreamPool`), e oggi risulta `source: "stream"`,
`stream_connections: 1`, `stream_markets: 11`, `stream_capacity: 720`. Il REST resta solo come
fallback dei mercati non coperti. **Il pezzo lento non è la sorgente: è il tragitto dalla sorgente
al bot.** E il REST che resta davvero indispensabile è quello degli **ordini**, che non si può
sostituire con lo stream in nessun mondo.

**Misura di confronto dei due trasporti, fatta oggi:**

| trasporto | payload | p50 | p95 |
|---|---|---|---|
| PostgREST, 1 riga per chiave, connessione calda | ~100 B | **~113 ms** | ~162 ms |
| PostgREST, feed intero | 9,5 KB | **~188 ms** | ~307 ms |
| WebSocket `127.0.0.1`, 1 riga di scan tennis | 529 B | **0,594 ms** | 1,184 ms |
| WebSocket `127.0.0.1`, feed di 10 righe | 5.085 B | **0,740 ms** | 1,326 ms |

(loopback misurato in laboratorio **dentro un solo processo**, 300 andate e ritorno per taglia;
nessun servizio avviato. Coerente con il «<5 ms» già stimato in `PROGETTO_PAPER_VIA_FLUMINE §C3.4`.)

### S1 — Lo scanner **spinge** la riga che ha appena calcolato

**Oggi**: t1 → t2 = **2,0-2,9 s**.
**Atteso**: **< 2 ms** dal calcolo alla disponibilità nel bot.

**Cosa si riusa**: `Betfair/stream/local_channel.py` per intero — `start_channel:239`,
`LocalChannel.publish:169`, `publish` di modulo `:264`, `channel_active:259`. È lo stesso meccanismo
che il bot Safe usa già per sé (`bot_service.py:6869` `_PORTA_CANALE = 47335`, `_avvia_canale:6872`
con `solo_lettura=True`, `_pubblica_stato:6891` che spinge il topic `safe_stato`) e che il frontend
sa già parlare (`frontend/src/lib/localChannel.ts:46-49`, mappa porte
`{calcio:47331, tennis:47332, mike:47333, omega:47334, safe:47335}`).

**Cosa va scritto**: una `publish("safe_scan", riga)` accanto alla scrittura, dentro
`Scanner.publish` (`service.py:1270`, punto esatto `:1169-1171` dove la riga è già stata decisa) — e
l'avvio del canale nel processo dello scanner, che **oggi non ce l'ha** (nessun import di
`local_channel` in `service.py`).

⚠️ **Questa è l'unica risorsa nuova del progetto, ed è già a bilancio.** Il processo dello scanner ha
bisogno di **una** porta di canale locale. È **esattamente la stessa** che C3 richiede per il relay
del raw: `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md §C3.1` innesta il tee in
`safe_strategy/stream.py:109-112` e lo porta «su un topic nuovo del canale locale». **Un canale, due
topic**: `raw` per il driver flumine del paper, `safe_scan` per i bot. Non si apre una seconda
connessione a Betfair, non si avvia un secondo processo, non si duplica il feed unico.

**Rischio e come si chiude**: `publish` **scarta** i push oltre `_MAX_INVII_IN_VOLO = 64`
(`local_channel.py:36-38`, `:182-188`). Per il **raw** questo è inaccettabile (un delta perso
corrompe la cache del book per sempre — C3 lo dice e chiede consegna garantita). Per il topic
`safe_scan` **è corretto così**: una riga di scan è uno **stato completo**, non un differenziale, e
il fotogramma successivo ripara. È letteralmente il caso descritto nella docstring di `publish`.

**Doppia fonte di verità**: il DB continua a ricevere la stessa riga, invariata. Il push è una
**accelerazione, non una sostituzione** — è la stessa formula già scelta il 14/09 per lo stato del
bot (`bot_service.py:6862-6866`: «LO SCHERMO PRIMA DEL DISCO … il socket è un'accelerazione, non una
sostituzione»). La riga porta con sé `updated_at` e `odds_ts_ms`: chi la riceve sa quanto vale,
qualunque strada abbia fatto.

### S2 — Il freno di scrittura resta sul DB e **esce dal percorso della decisione**

`_PUBLISH_MIN_INTERVAL_SEC = 2.5` (`service.py:90`) nasce per proteggere l'IO di Supabase e **deve
restare sulla scrittura**. Sul canale non esiste budget IO: il push esce a **ogni** cambiamento.

**Oggi**: un movimento di sole quote può aspettare fino a **2,5 s** prima di essere visibile.
**Atteso**: visibile subito; il DB continua a respirare a 2,5 s esattamente come oggi.
**Cosa va scritto**: niente di nuovo — è la conseguenza di S1, purché il push stia **prima** del
`continue` del freno e non dentro il ramo che scrive.
**Rischio**: la pagina e il bot potrebbero vedere prezzi diversi per ≤2,5 s (il bot dal canale, la
pagina dal DB). Va dichiarato e risolto nel modo già in uso: **la pagina legge dallo stesso canale**
quando c'è (`useSafeBot.ts:370-392` fa già esattamente questo per le `stats`), altrimenti dal DB.

### S3 — Il bot tennis **consuma il push** invece di interrogare il DB

**Oggi**: attesa del poll + `read_control` + `fetch_scan_rows` = **2,0-2,9 s**.
**Atteso**: **< 2 ms** + il risveglio.

**Cosa si riusa**: `websockets` è già una dipendenza (usata da `local_channel.py:89`); il client
`frontend/src/lib/localChannel.ts:63-114` è il protocollo di riferimento, riga per riga.
**Cosa va scritto**: un piccolo client WS nel processo del bot che tiene le righe di scan in RAM e
sveglia la valutazione quando cambia la riga di un evento tennis seguito — più una **corsia calda**
tennis in `run_once`.

**Contratto che non si rompe** (è il punto più importante di tutto il documento):
il **DB resta la verità del LIBRO MASTRO** — posizioni, richieste, control, riserve. Il canale è la
verità **della sola quota**. Due fonti per un *prezzo* sono accettabili (vince l'ultima, e ogni riga
porta il proprio istante). Due fonti per una *posizione* no, mai.

**Fail-closed**: canale caduto → si torna al poll di oggi, senza una riga di differenza; e la
guardia di freschezza sulla riga (`_stale_reason:5869`, usata a `:2070`, `:5104`, `:5751`, `:5909`,
`:6264`) continua a fare il suo mestiere. **Mai una decisione su un prezzo senza istante.**

### S4 — Le fasi di protezione escono dal percorso critico dell'ingresso tennis

**Oggi**: t2 → t3 = **0,9-1,7 s** (§1.4).
**Atteso**: il tempo del motore, che è puro e in RAM (`engine.evaluate`, `engine.py:1630-1732`) →
decine di ms.

**Cosa NON si fa**: togliere quelle fasi o spostarle dopo. Il 15/09 ha già insegnato che cosa
succede a mettere la corsia delle chiusure davanti a `poll_flumine`/`reconcile_pending`
(`bot_service.py:6525-6540`: cancel su riserve già a mercato, cashout rifiutati con un motivo falso).
**L'ordine resta quello.**

**Cosa si fa**: smettere di **ripagarle** a ogni sveglia. Il contesto di rischio è già letto **una
volta per ciclo** (`build_risk_ctx:4681`) e già aggiornato in RAM a ogni riserva riuscita
(`_risk_commit:4824`); `_scanner_ts` è già memoizzato per ciclo (`_SCANNER_TS_CACHE:2600`,
`_scanner_ts:2609-2623`); `_traded_keys` è già una lettura per modalità (`:5051`). La corsia calda
**riusa** quegli oggetti invece di rifarli.

⚠️ **Questo è il punto delicato e va trattato come un contratto, non come una riga.** Un contesto di
rischio ha un'età: superata un'età massima **dichiarata**, la corsia calda **non apre** e aspetta il
ciclo. È esattamente la disciplina già scritta per il control degradato (`_CONTROL_CACHE_MAX_AGE_S`
`:6437`, `risk_ctx["unavailable"]` `:6557-6560`). Serve un test che **falsifichi**: contesto scaduto
→ nessuna apertura.

### S5 — L'invio: resta REST, e resta l'ultimo termine da guardare

**Oggi**: t3 → t4 = **213-260 ms**, ed è **una** INSERT di riserva (`bot_service.py:5259`).

Due strade, **entrambe money-critical: decide l'utente, non io.**

* **(a) Si lascia com'è.** 250 ms su 3.000 ms di bet delay sono l'8 %. Il lucchetto contro il doppio
  ordine resta dov'è, verificabile, su disco, prima che i soldi partano.
* **(b) Riserva locale + invio + scrittura subito dopo.** Il lucchetto in-processo esiste già
  (`traded_s` in `scan_and_place`, `:5240`), e la chiave forte contro il doppio ordine è già di
  Betfair: `customerOrderRef` (`Betfair/omega/omega_market.py:649-651`, «PERSISTITO sull'ordine e
  RITORNA in listCurrentOrders/listClearedOrders»), con `_reconciling` (`execution.py:638`) che già
  sa gestire l'esito ignoto. **Rischio**: un crash fra invio e scrittura lascia un ordine vero senza
  riga. Recuperabile dalla riconciliazione via `customerOrderRef` — ma solo se la riconciliazione
  gira, e solo al giro dopo. *Io non raccomando (b) senza una prova di falsificazione dedicata: è
  esattamente la forma del guasto del 15/09 (32 green-up in loop) vista da un altro lato.*

**Sessione calda**: `call_mutating` (`omega_market.py:51-65`) **non ritenta mai** una chiamata
mutante e rifà il login solo se l'exchange dice esplicitamente che la sessione non vale;
`keep_alive()` (`:68-77`) tiene viva la sessione condivisa in modo proattivo. Non c'è niente da
inventare: c'è da **verificare** che il keep-alive giri davvero nel processo del bot — **non
misurato**, il servizio era fermo.

### S6 — Consapevolezza dell'abbinamento dall'**order stream**, non da una rilettura REST

**Oggi, misurato**: i tre ordini tennis sono usciti con `meta.esecuzione.percorso: "rest"`. Il gate
flumine era chiuso, quindi **nessun order stream**: l'abbinamento si è saputo dalla risposta
sincrona del REST, che è arrivata dopo il bet delay. Consapevolezza sì, ma pagata con l'attesa.

**Cosa esiste già**: il runner apre l'order stream **anche in paper**
(`Betfair/stream/runner.py:1425`, `:1448`, `order_stream=True` con
`order_stream_conflate_ms`); il canale locale del runner accetta **comandi ordine veri** e li esegue
**con le stesse guardie della coda DB** (`live_order_worker._process_local_requests:3007`,
`_LOCAL_ACTIONS:2840`, audit con `_record_local_request:2966`); porte 47331 calcio
(`runner.py:1603`) e 47332 tennis (`tennis_live/tennis_runner.py:1480`).

**Cosa cambia con C3**: il gate passa da `live_follow.status == 'STREAMING'` a «mercato coperto dal
pool» (`safe_strategy/stream.py:308` `covered_ids()`), e i mercati tennis del pool diventano
eleggibili. A quel punto l'ordine può andare sul **canale locale del runner** (0,6-1,3 ms misurati)
invece che sulla coda DB, che costa `enqueue_live_order` (RPC, ~150 ms) + il poll del worker
(`LIVE_ORDER_QUEUE_POLL_SEC = 1.0`, `config_stream.py:184`, usato a `runner.py:1826`) + il ciclo
successivo del bot per conoscere l'esito.

⚠️ **`place_submin` è escluso dal canale locale** (`_LOCAL_ACTIONS:2840`) e resta sulla coda DB: con
importi sotto il minimo il place-and-trim tiene la sua latenza. Non è una regressione, ma va detto.

**Rischio: il runner diventa money-critical per tutti i bot.** È già scritto in C3 (§C3.8) e resta
vero qui.

### S7 — L'approvazione dell'utente: push invece di poll

**Oggi, misurato (trade 299)**: dal clic all'invio **4,3 s**, di cui 3,2 s di Betfair → ~1,1 s
nostri. Il percorso: clic → RPC `safe_request_approve`
(`frontend/src/lib/controlRoomProposte.ts:368`; funzione in
`migrations/safe_strategy_proposed_2026-09-14.sql:44`, owner-only, `FOR UPDATE`, `proposed→pending`)
→ riga `pending` → il bot la vede con la **sbirciata a 250 ms**
(`bot_service.py:6908` `_SBIRCIATA_S = 0.25`, query a `:6913`) **solo se ci sono posizioni aperte**,
altrimenti fino a `poll_interval_s` → ciclo anticipato (`:7016`) → corsia preferenziale delle
chiusure (`:6543`), che sta comunque dopo `poll_flumine` e `reconcile_pending`.

**Cosa esiste già e non è usato per questo**: **Supabase Realtime**, in produzione nel frontend
proprio su questa tabella — `frontend/src/lib/safeBot.ts:1133` (canale `safe-bot`, tabella
`safe_strategy_requests`, evento `*`) e `controlRoomProposte.ts:388` (canale
`control-room-proposte`). Lo stesso canale è disponibile per un client Python (`realtime` fa parte di
`supabase-py`). **Non misurato**: aprire una sottoscrizione Realtime significa tenere una connessione
persistente, e mi è stato ordinato di non avviare niente.

⚠️ **L'approvazione NON passa dal canale locale del bot**, e non deve. Il canale 47335 è
`solo_lettura=True` per decisione esplicita (`bot_service.py:6849`, motivata in
`local_channel.py:59-70`: «il canale del runner ESEGUE ORDINI VERI. Tenere i due livelli di fiducia
separati … vuol dire che aggiungere uno schermo non aggiunge mai una via per mandare soldi»). È già
scritto anche in `PIANO_MAESTRO_2026-09-14.md:287`. **Non si tocca.**

**Atteso**: dal clic all'invio da 4,3 s a **~0,5-1 s**, sostituendo la sbirciata con il push. E si
tolgono **4 letture al secondo** (240/min) dal DB ogni volta che c'è una posizione aperta.
**Onestà**: il clic di un essere umano **non sarà mai «al ms»**, e non è quello il percorso caldo.
Il percorso caldo è il **prezzo**.

### Quadro riassuntivo dei salti

| salto | oggi (misurato) | atteso | si riusa | va scritto |
|---|---|---|---|---|
| Betfair → scanner | 0,5-2,3 s *(non misurato)* | invariato | conflate 1 s, tick 0,5 s | `odds_pt_ms` da `publish_time` |
| scanner → bot | **2,0-2,9 s** | **< 2 ms** | `local_channel.py` (canale di C3) | topic `safe_scan` + client WS nel bot |
| freno di scrittura | fino a **2,5 s** su quote pure | **0** sul canale | `_PUBLISH_MIN_INTERVAL_SEC` resta sul DB | push prima del freno |
| fasi pre-decisione | **0,9-1,7 s** | decine di ms | `risk_ctx`, `_SCANNER_TS_CACHE`, `_traded_keys` | corsia calda + età massima dichiarata |
| decisione → invio | **213-260 ms** | 250 ms *(a)* / ~5 ms *(b)* | `traded_s`, `customerOrderRef` | **decisione dell'utente** |
| invio → risposta | **3,2-4,5 s** | **invariato** | — | **niente: è Betfair** |
| esito/abbinamento | risposta REST sincrona | push order stream | `order_stream=True`, canale runner | è C3, non extra |
| clic → invio | **4,3 s** | ~0,5-1 s | Supabase Realtime già in produzione | client Realtime in Python |

---

## 4. Il DB resta lo specchio, ma esce dal percorso critico

**Principio**: il database è **il libro mastro e lo schermo**, non il bus della decisione.

**Cosa resta sincrono, prima dei soldi, senza eccezioni**: la **riserva** (`insert_trade`, se si
sceglie l'opzione (a) di S5), lo **stato dei trade**, lo **stato delle richieste**. È il libro
mastro: una scrittura persa qui è una posizione persa.

**Cosa può stare dopo la decisione**:

* le righe di attività (`bot_db.log:54`) — **già** best-effort, già dentro un `try/except` che non
  ferma il bot;
* stats + heartbeat (`db.set_control` a `bot_service.py:6758`) — **già** dopo `_pubblica_stato:6756`,
  cioè già oggi lo schermo precede il disco;
* l'upsert delle opportunità — già limitato a `opps_interval_s: 10` (`:104`).

**Come**: una **coda di scrittura dentro il processo del bot**, drenata dal thread del ciclo. **Mai
un processo nuovo.** Limitata (si scarta il più vecchio con un contatore visibile, mai crescita
illimitata) — la stessa disciplina di `_MAX_INVII_IN_VOLO`. E la regola: **se la coda cresce, lo si
dice**, non lo si assorbe in silenzio.

**Rispetto della lezione del 13/09 (budget IO esaurito)**: questo progetto **abbassa** il carico, non
lo alza.

| voce | oggi | dopo |
|---|---|---|
| sbirciata richieste, con posizioni aperte | **4 letture/s** = 240/min | **0** (push, S7) |
| letture del ciclo | 8-12 per giro ogni ~3,5-4,5 s | invariate (il ciclo può anche rallentare) |
| scrittura righe di scan | throttle 2,5 s per evento | **identica** (il freno resta) |
| ordini via coda DB | RPC + poll 1 s + esito al ciclo dopo | canale locale, 1 riga di audit (C3) |

Il ciclo a 2 s **non va accelerato**. Anzi: una volta che non è più lui a decidere, può restare a 2 s
o allargarsi, e il DB respira di più di adesso.

---

## 5. Ore per fase, ordine consigliato

**Prerequisito, e non è codice**: sincronizzare l'orologio della macchina (servizio Ora di Windows
fermo, §0). ~0,5 h, e lo fa l'utente: è un'impostazione di sistema.

| # | contenuto | riusa | ore | perché in quest'ordine |
|---|---|---|---|---|
| **L0** | orologio + `odds_pt_ms` da `book.publish_time` (chiave additiva) + salto `pt→t0` nella catena | `service.py:531`, `_catena_dei_tempi:3776` | **0,5-1 g** | senza, ogni misura successiva vale ~2 s meno di quello che dice, e il salto cieco resta cieco |
| **L1** | `betDelay` nel payload tennis (chiave additiva, zero chiamate) | la riga già in produzione a `service.py:595` | **0,5 g** | il bot e la pagina smettono di ignorare il ritardo a cui sono soggetti; la certificazione smette di assumere 3 s |
| **L2** | canale nel processo scanner + topic `safe_scan` (push nel punto della scrittura) | `local_channel.py:239/169`; **stesso canale di C3-F1** | **1-2 g** | è il salto che vale 2-3 s. Si fa **insieme a C3-F1**: stesso file, stessa porta |
| **L3** | client WS nel bot + corsia calda tennis da RAM, ripiego sul DB | `localChannel.ts` come protocollo, `_stale_reason:5869` | **2-3 g** | richiede L2. Qui spariscono i 2-3 s |
| **L4** | riuso di `risk_ctx`/`_traded_keys`/`_scanner_ts` nella corsia calda, con **età massima dichiarata** e fail-closed | `build_risk_ctx:4681`, `_risk_commit:4824`, `_SCANNER_TS_CACHE:2600` | **2-3 g** | il più delicato: tocca ciò che rende vero lo stato di una riga. Richiede un test **falsificato** |
| **L5** | scritture asincrone per ciò che non è libro mastro (log, stats, opportunità) | `bot_db.log:54`, `_pubblica_stato:6891` | **1 g** | abbassa l'IO e accorcia il ciclo. Rischio nullo se il libro mastro resta sincrono |
| **L6** | approvazione via push (Realtime nel bot) al posto della sbirciata 250 ms | `safeBot.ts:1133` come riferimento | **1-2 g** | indipendente dal resto; toglie 240 letture/min |
| **L7** | ordine sul canale locale del runner quando il mercato è coperto + esito dall'order stream | `_process_local_requests:3007`, `runner.py:1425/1448`, `stream.py:308` | **dentro C3-F1/F2** | **non si fa a parte**: sarebbe costruire il gate due volte |

**Ordine**: L0 → L1 → **(L2 insieme a C3-F1)** → L3 → L4 → L5, con L6 in parallelo quando si vuole,
e L7 che arriva da solo con C3.

**Totale al netto di C3**: **7-10 giorni** (L0+L1+L3+L4+L5+L6). L2 e L7 sono **già dentro** il
preventivo di C3-F1 (4-6 giorni): il costo *aggiunto* del percorso tennis rispetto a C3 è quello dei
sei punti, non di otto.

**Certificazione, senza gradini saltati**: niente di tutto questo va in live senza il replay sulle
registrazioni reali con il codice di produzione, dal punto d'ingresso unico del banco comune
(`python -m Betfair.stream.backtest.certifica <bot> ...`). Per il tennis il corpus che porta il
delay vero è `C:\Users\Admin\Desktop\tennis_rec` (100 eventi, betDelay 3 s×52 / 5 s×7). Ogni test
nuovo va **falsificato**; i finti devono avere le **identiche chiavi** del vero.

---

## 6. Quello che questo progetto **non** promette

1. **Non accorcia il bet delay.** 3 s (5 s su alcuni ITF) sono di Betfair. Dopo tutti i
   miglioramenti, su un ingresso tennis in-play il termine dominante resta **quello**: da ~8,5 s
   misurati si scende a ~3,2-3,5 s. Il guadagno è reale (~5 s), il pavimento è il delay.
2. **«Tutto al ms» vale per la parte nostra**, non per l'andata e ritorno con l'exchange. È onesto
   dirlo adesso e non dopo.
3. **Non migliora i riempimenti.** Li rende possibili prima. Se a quel punto il prezzo c'è ancora è
   una domanda per il replay, non per questo referto. **Nessuna stima di rendimento è contenuta qui.**
4. **Non cambia una sola regola di strategia.** `scoreConfirmSec = 15` (`engine.py:256`), finestre,
   soglie, FOK: intoccati. I 15 s partono da *quando osserviamo*: arrivare prima sposta
   l'ammissibilità prima, **senza toccare la regola**.
5. **Non sistema l'orologio da solo**, e sistemarlo non toglie un millisecondo di latenza vera:
   toglie ~2 s di **errore di misura**.
6. **Non aggiunge né un processo né una connessione a Betfair.** L'unica risorsa nuova è **una porta
   di canale locale nel processo dello scanner**, che è la stessa che C3 ha già messo a bilancio.
7. **Non decide (a) o (b) per l'invio** (§S5): è money-critical e la decisione è dell'utente.

---

## 7. Non misurato, e perché

| cosa | perché |
|---|---|
| `publish_time` di Betfair → `t0` (conflate + tick) | `t0` lo timbriamo noi: **non esiste il campo** per fare la differenza. Limitato per costruzione da `_CONFLATE_MS = 1000` e dal tick (p95 799,6 ms) |
| periodo effettivo del ciclo del bot dal vivo | il bot era **`stopped`** (ultimo ciclo 08:59:50; heartbeat campionato per 25 s alle 09:06: nessun battito nuovo). Ricostruito dal numero di andate e ritorno × il costo misurato di ciascuna |
| latenza di Supabase Realtime da Python | richiede di **aprire una sottoscrizione persistente**: mi è stato ordinato di non avviare niente |
| `keep_alive()` davvero attivo nel processo del bot | il servizio era fermo |
| `betDelay` dei mercati esatti di 297/298/299 | il raw tennis del 17/09 **non esiste** (`tennis_rec` ha solo il 07/07). Il valore viene dal corpus del 07/07 e dai .md, non da quei mercati |
| carico del topic `safe_scan` a ~720 mercati | C3 ha misurato il **raw** (161 msg/s, ~40 KB/s a 720 mercati). Le righe di scan sono meno numerose e più grosse: non misurato, ma limitato in alto dal write-on-change che c'è già |
| effetto dello scarto d'orologio sulle **decisioni** | verificato che le guardie confrontano istanti tutti locali (`updated_at` scritto da noi vs `time.time()` del bot) → nessun effetto atteso; **non ho passato in rassegna ogni confronto** con campi che vengono da Betfair (`betfair_updated_at`, `placedDate`). Va fatto prima di fidarsi |

---

## 8. Correzioni al brief di partenza, per onestà della base

1. **«t0 = prezzo cambiato su Betfair»**: non è così. `t0` è `odds_ts_ms`, timbrato con l'orologio
   locale quando lo **scanner lavora** il book (`service.py:531`). Manca tutto il tratto prima.
2. **«riga scritta dallo scanner +1 ms»**: vero per 297/298, ma è il **caso migliore**. Un movimento
   di sole quote può aspettare fino a **2,5 s** (`_PUBLISH_MIN_INTERVAL_SEC`).
3. **«Betfair risponde +4,5 s (placedDate 08:40:42 vs invio 08:40:39,2)»**: quei 2,8 s contengono
   **2,07 s di orologio sbagliato**. Il tratto vero fino a Betfair è ~0,7 s; il resto è il bet delay.
4. **«canale WS locale 127.0.0.1:47331/47332»**: 47331 e 47332 sono i canali dei **runner** (calcio e
   tennis) e **eseguono ordini veri**. Il canale del **bot Safe** è la **47335** ed è
   `solo_lettura=True` per decisione esplicita. Lo scanner **non ha canale**: è la porta che C3
   introduce.
5. **«ordini via REST anche in flumine»**: confermato, ed è la ragione per cui il bet delay non si
   aggira. L'order stream serve all'**esito**, non all'invio.
