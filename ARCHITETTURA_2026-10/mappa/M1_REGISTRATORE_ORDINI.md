# M-1 - Registratore dello stream ordini e delle REST con soldi

Mappatura dei flussi reali, 11/10/2026. Ramo `mappa/m1-ordini` da `a3a58ad8` (cima di master).
Permesso: richiesta dell'utente «Voglio che mappi qualsiasi cosa per poi fare la v2 al pari dei competitor».
Buco che chiude: `ARCHITETTURA_2026-10/ondata2/PIANO_AGGANCIO.md` (ramo `ondata2/piano-aggancio`), rischio R3:
nessuna registrazione `ocm` nel repo, quindi lo stream ordini sostituito in LIVE non e' certificabile sul banco.

Codice: `Betfair/monitor/registratore_ordini.py` (registratore), `Betfair/monitor/analisi_ordini.py` (lettura),
`Betfair/monitor/tests/test_registratore_ordini_2026_10_11.py` (29 test), `ARCHITETTURA_2026-10/mappa/m1_mutazioni.py`
(25 mutazioni).

---

## 1. Cosa registra

Per ogni processo che usa Betfair, a interruttore acceso:

| record (`k`) | quando | contenuto |
|---|---|---|
| `avvio` | apertura del file (avvio o nuovo giorno) | servizio, pid, giorno, tetto, versioni di python/betfairlightweight/flumine |
| `sub` | ogni `subscribe_to_orders` dello stream ordini del processo (prima e ogni ripartenza) | `sid` (numero della sottoscrizione nel processo), filtro ordini, `initial_clk`/`clk` (ripresa o immagine piena), `conflate_ms`, `heartbeat_ms` |
| `stream` | ogni messaggio che arriva al listener dello stream ordini: `connection`, `status`, `ocm` (SUB_IMAGE, UPDATE, RESUB_DELTA, HEARTBEAT) | la riga GREZZA di Betfair **verbatim** in `msg` (nessuna ri-serializzazione), `sid`, istante di ricezione |
| `rest` | ogni `placeOrders`, `cancelOrders`, `replaceOrders`, `updateOrders` | `via` (`bflw` = APIClient di betfairlightweight, `rest_nostro` = `Betfair/client.py`), metodo, mercato, `attore`, `csr` (customerStrategyRef), `cref` (customerRef), `corefs` (customerOrderRef per istruzione), richiesta intera, risposta intera di Betfair (busta JSON-RPC o `result`), `stato`, `errore` (errorCode del rapporto o dell'APINGException), `codici` per istruzione, `eccezione` (tipo e testo) se la chiamata solleva, thread |
| `dec` | `tempi_ordine.place` (subito prima di `market.place_order` sulle strade del runner calcio e tennis) | `cor` = customerOrderRef che l'ordine avra' nella REST, id ordine flumine, chiave del comando, strada, azione, `decisione_ms` (da `emesso_ms` di `sonde.marca_emesso` o dalle altre chiavi di decisione del comando), ricezione |
| `chiusura` | fine processo (atexit) o cambio di giorno | motivo, righe scritte, righe perse in coda, righe scartate per tetto, errori di scrittura |

Ogni record porta `seq` (numero progressivo del processo: un buco = righe perse), `ep_us` (epoca in microsecondi)
e `mono_us` (orologio monotono `perf_counter` in microsecondi; su Windows e' QueryPerformanceCounter, comune a tutti i
processi della macchina). Il `rest` ha anche `risposta_ep_us`, `risposta_mono_us` e `durata_ms` (dal monotono).

**Chi l'ha fatta** (`attore`, dal `customerStrategyRef` della richiesta): `live`/`tennis` -> `desktop` (terminale
manuale, stessi valori di `tennis_scalper/ordini_esterni.py:68-69`), `watchlist` -> `desktop_watchlist`
(`order_exec.py:342`), ogni altro ref -> `bot:<ref>` (es. `bot:mike`, `bot:omega`, `bot:safe`). `cancelOrders`,
`replaceOrders`, `updateOrders` non portano il ref: `attore = "?"` nella riga, e l'analisi lo ricava dal `betId`
(piazzamento registrato, oppure `rfs` dello stream ordini).

**Non registra**: le intestazioni HTTP, il token di sessione, l'app key, la password (le chiamate betting non la
portano). Se Betfair li echeggiasse in un testo d'errore, token e app key sono sostituiti con `***` prima della scrittura
(test `test_acceso_rest_bflw_registra_e_non_cambia_gli_esiti`, mutazione M9). L'autenticazione dello stream
(`op=authentication`, con token e app key) e' un messaggio IN USCITA e non passa dal listener: non e' mai registrata.

In PAPER non c'e' nulla da registrare: flumine usa `SimulatedOrderStream`, che non chiama mai `create_stream`, e
`SimulatedExecution`, che non fa REST. Il registratore e' spento per costruzione nel banco (`Betfair.stream.backtest`
caricato) e sotto pytest.

## 2. Dove

`<LIVE_STREAM_DATA_DIR>/_ordini/<AAAAMMGG>/ordini_<servizio>_<pid>.jsonl.gz`

* la cartella base e' quella del raw dei prezzi (`Betfair/stream/config_stream.py:24`, `DATA_DIR`, di serie
  `<repo>/_live_raw`); `REGISTRO_ORDINI_DIR` la sostituisce;
* un file per processo e per giorno UTC; `servizio` = servizio del monitor «Salute» se acceso, altrimenti il modulo di
  `python -m`, altrimenti il nome dello script;
* JSON per riga, gzip livello 6 svuotato (Z_SYNC_FLUSH) al piu' ogni secondo: un arresto brusco perde al piu' l'ultimo
  secondo; il lettore tollera la coda tronca e i gzip a piu' membri;
* rotazione: al cambio di giorno UTC si scrive `chiusura` (motivo `giorno`) e si apre il file del giorno nuovo. La riga
  va nel file del giorno in cui viene SCRITTA (a cavallo della mezzanotte puo' finire nel giorno dopo).

**Tetto di disco**: `REGISTRO_ORDINI_TETTO_MB` (di serie 512 MB; valori illeggibili o <= 0 -> 512). Controllato
all'apertura di ogni file e ogni 10 minuti: oltre il tetto si cancellano i file `ordini_*.jsonl.gz` piu' vecchi (per
data di modifica), mai il file aperto da questo processo e mai un file toccato negli ultimi 15 minuti (di un altro
processo vivo); si tolgono le cartelle di giorno rimaste vuote; se non basta si smette di scrivere fino al controllo
dopo, contando le righe scartate (`scartati_tetto` nella `chiusura`) con un WARNING.

## 3. Quanto pesa (misurato)

Misura con lo scrittore vero (`peso.py` nello scratchpad, righe con la forma reale): una giornata intera di un
processo con lo stream ordini sempre aperto = 17.280 battiti (`HEARTBEAT` ogni 5 s, il default di Betfair) +
gli ordini, ciascuno con `placeOrders`, tre `ocm` (E, parziale, EC) e un `cancelOrders` ogni due ordini.

| giornata di UN processo | righe | JSON grezzo | gzip su disco |
|---|---|---|---|
| 200 ordini, svuotamento a ogni battito (caso peggiore realistico) | 18.180 | 3,5 MB | **0,52 MB** |
| 200 ordini, svuotamento raro | 18.180 | 3,5 MB | 0,29 MB |
| 2.000 ordini | 26.280 | 8,5 MB | 0,47 MB (+ svuotamenti: ~0,7 MB) |

Processi con lo stream ordini LIVE: runner calcio, runner tennis, ogni sessione scalper LIVE; i processi solo-REST
(Omega, Mike, desktop watchlist) scrivono solo i loro `rest`. Stima: **1-6 MB al giorno** per l'intera app; col tetto di
serie (512 MB) restano mesi di storia.

Costo sul percorso caldo (misurato sulla macchina del cloud): `metti_stream` (thread dello stream ordini) p50 1,3 us,
p99 3,5 us; `registra_rest` (thread della REST, DOPO la risposta, comprende la serializzazione di richiesta e
risposta) p50 20 us, p99 69 us. Nessun lucchetto e nessuna attesa: un `deque.append`; se la coda supera 50.000 righe la
riga si perde (contata in `persi_coda`, visibile come buco nella `seq`). Gzip, rotazione e tetto li fa UN thread
demone (`registro-ordini`) avviato solo al primo record e solo se acceso.

## 4. Come si accende

`REGISTRO_ORDINI=1` nell'ambiente del processo (o nel `.env` della radice, letto da `config.py` prima dei punti
d'aggancio). Qualunque altro valore, o la variabile assente, = **spento** (di serie). Come `MONITOR_SALUTE` di
`Betfair/monitor/sonde.py`. La decisione si prende UNA volta per processo, al primo aggancio: cambiarla = riavvio
dell'app (lo fa solo l'utente). Variabili accessorie: `REGISTRO_ORDINI_DIR`, `REGISTRO_ORDINI_TETTO_MB`.

Spento: ogni aggancio e' `if _ro.attivo(): ...` falso. Nessuna istanza avvolta, nessuna cartella, nessun file, nessun
thread (test `test_spento_*`, mutazione M4).

## 5. Punti toccati (una riga ciascuno, piu' l'import)

| file:riga | riga | cosa copre |
|---|---|---|
| `Betfair/stream/auth.py:25` | `from ..monitor import registratore_ordini as _ro` | import |
| `Betfair/stream/auth.py:73` | `if _ro.attivo(): _ro.aggancia_api_client(client)` | TUTTI gli APIClient di betfairlightweight (`build_client` e' l'unico costruttore): runner calcio (`runner.py:2712`), runner tennis (`tennis_runner.py:3195`), sessioni scalper (`scalper_session.py:1544`), Safe (`safe_strategy/service.py:3370`). Avvolge sull'ISTANZA `betting.request` e `streaming.create_stream` |
| `Betfair/client.py:12` | `from Betfair.monitor import registratore_ordini as _ro` | import |
| `Betfair/client.py:192` | `if _ro.attivo() and _ro.metodo_soldi(method): return _ro.rest_nostro(...)` | il client REST nostro (`BetfairClient.betting_rpc`): `order_exec.py:340` (desktop watchlist), `omega_market.py:788/1131` e i `cancelOrders`/`replaceOrders` di `omega_market.py:950/1251/1374` (Omega e Mike LIVE) |
| `Betfair/stream/tempi_ordine.py:62` | `from ..monitor import registratore_ordini as _ro` | import |
| `Betfair/stream/tempi_ordine.py:207` | `if _ro.attivo(): _ro.decisione(order, voce)` | la decisione dietro ogni ordine delle strade del runner (`live_order_worker.py:1271/3388`, `tennis_live_order_worker.py:716/1080`) |

Dove passano oggi gli ordini di tutti, e quale punto li vede:

| chi | strada | REST vista da | stream ordini visto da |
|---|---|---|---|
| motore ordini (bot ospitati, Safe, Mike via `porta_ordini` e canale) | flumine `BetfairExecution` (`betfairexecution.py:54/115/150/227`) -> `betting_client.betting.*_orders` -> `Betting.request` | `auth.py:73` (`via=bflw`) | `auth.py:73` (stream ordini del runner calcio) |
| desktop ladder calcio/tennis (`live`/`tennis`) | coda/canale -> `live_order_worker` / `tennis_live_order_worker` -> flumine | `auth.py:73` | `auth.py:73` (runner calcio e tennis) |
| copertura di `live_order_worker` (`cancelOrders` diretto) | `live_order_worker.py:2434` `betting.cancel_orders` | `auth.py:73` | - |
| scalper (sessioni LIVE) | flumine della sessione | `auth.py:73` | `auth.py:73` (stream ordini della sessione) |
| tennis | flumine del runner tennis | `auth.py:73` | `auth.py:73` |
| desktop watchlist (`order_exec`) | `BetfairClient.place_orders` -> `betting_rpc` | `client.py:192` (`via=rest_nostro`) | (stream di chi e' acceso) |
| Omega e Mike LIVE (REST diretta, `omega_market`) | `BetfairClient.place_orders`/`betting_rpc` | `client.py:192` | (stream di chi e' acceso) |
| sito Betfair (utente) | - | - | gli `ocm` senza `rfo`/`rfs`, se lo stream ordini non e' filtrato per ref |

### Perche' QUI per lo stream ordini (e non altrove)

* `order_stream_cls` di flumine (`baseclient.py:35,63`, `streams.py:83-89`): cambia la STRADA con cui flumine crea lo
  stream (`add_custom_stream`, `custom=True`, niente `conflate_ms`/`streaming_timeout` del client) e va passato in ogni
  costruzione di `clients.BetfairClient` (runner, tennis, scalper): tre punti e un cambio di comportamento. Scartato.
* L'osservatore `esiti_ordini_canale.osserva_conto_su_flumine` (`esiti_ordini_canale.py:815`): vede i `CurrentOrders`
  GIA' parsati da betfairlightweight (non la riga grezza: niente `clk`, `ct`, `status`, `connection`, battiti), e solo
  dopo flumine; montato solo dove si e' scelto (strategia live del calcio, ordini esterni di scalper e tennis).
  Inadatto a una registrazione replayabile. Scartato.
* Il listener dello stream (`BetfairStream._data` -> `listener.on_data(raw)`, `betfairstream.py:276`): e' dove arriva
  la riga grezza, prima di qualunque parse, come per il raw dei prezzi (`raw_listener.RawTeeStreamListener.on_data`).
  Per arrivarci senza toccare flumine si avvolge, sulla SOLA istanza dell'APIClient, `streaming.create_stream`
  (chiamato da `OrderStream.run`, `orderstream.py:36`): lo stream restituito ha `subscribe_to_orders` avvolto, e il
  tee si monta sul listener SOLO quando si sottoscrivono gli ordini (`orderstream.py:40`). Gli stream dei prezzi non
  sono toccati (test `test_acceso_stream_dei_prezzi_non_registrato`, mutazione M10). Il tee chiama sempre l'`on_data`
  originale e ne restituisce il valore (il `False` che chiude lo stream resta identico; mutazione M20). Alle ripartenze
  (retry di tenacity di `OrderStream.run`) il listener e' lo stesso: il tee non si duplica, cambia il `sid`.
  Bonus: la riga e' registrata anche quando poi betfairlightweight non la sa parsare (es. un `uo` senza `rfo`/`rfs`,
  difetto D6 del piano d'aggancio).
* Per la REST, `Betting.request` (`baseendpoint.py:23`) e' il punto dove passano TUTTE le chiamate betting di
  betfairlightweight (`betting.py:37/65/95...`), con il JSON della risposta prima del parse e le eccezioni
  (`APIError` con la risposta). Avvolto sulla sola istanza.

## 6. Garanzie

* **Zero cambi di comportamento**: gli esiti visti dal bot sono identici a registratore spento e acceso (test
  `test_acceso_rest_bflw_esiti_identici_a_spento`, `test_acceso_stream_esiti_identici_a_spento`: stessi
  `CurrentOrders`, stessi byte inviati sul socket). Le eccezioni di Betfair tornano al chiamante tali e quali
  (stesso oggetto, `raise`).
* **Zero connessioni nuove, zero processi nuovi**: si usa lo stream ordini che il processo ha gia' aperto. Un solo
  thread demone di scrittura per processo, fuori dal percorso caldo.
* **Nessun errore del registratore arriva al bot**: due strati (le porte della coda non sollevano; ogni aggancio ha la
  sua cattura). Ogni errore e' loggato col motivo (WARNING `[registro-ordini] ...`, al piu' uno al minuto per motivo).
  Test `test_metti_non_solleva_mai`, `test_eccezioni_del_registratore_non_arrivano_al_bot`,
  `test_errore_di_disco_non_arriva_al_bot`; mutazioni M5-M7, M21-M24.
* **Disco**: tetto con potatura (M8, M25), rotazione giornaliera (M12), coda limitata (M11).

## 7. Come si analizza la giornata

```
python -m Betfair.monitor.analisi_ordini --giorno 20261011
python -m Betfair.monitor.analisi_ordini --giorno 20261011 --cartella D:\...\_live_raw\_ordini --json giornata.json --dettaglio 50
```

Legge tutti i file del giorno (tutti i processi) e stampa:

* **conteggi**: REST, ordini (nostri / del sito / di altri processi non registrati), rifiuti senza `betId`, decisioni legate;
* **latenze (ms)** p50/p90/p99/max: REST per metodo e per attore (monotono), risposta REST -> primo `ocm` e invio REST ->
  primo `ocm` (epoca, stesso PC), decisione -> invio REST (se il comando portava l'istante di decisione);
* **errori REST** per metodo e codice (`INSUFFICIENT_FUNDS`, `BET_TAKEN_OR_LAPSED`, `INVALID_SESSION_INFORMATION`, eccezioni...);
* **ocm prima della risposta REST**: gli ordini il cui primo `ocm` e' arrivato PRIMA della risposta del `placeOrders`
  (con l'anticipo in ms);
* **ordini del sito**: `uo` senza `rfo` ne' `rfs` e senza un piazzamento registrato;
* **buchi**, per file: ripartenze (sottoscrizioni dopo la prima, con «ripresa da clk» o «immagine piena»), immagini
  piene ripetute, `status` d'errore (`connectionClosed`, `errorCode`), messaggi di dati senza `clk`, silenzi oltre 3
  battiti (15 s di serie) per sottoscrizione, righe perse (buchi di `seq`, coda piena, oltre tetto), file senza
  `chiusura` (processo morto), coda gzip tronca, righe rotte. Riga finale `BUCHI: SI|nessuno`;
* **sequenze ordine per ordine**: `place` -> `E(sm=0)` -> `E(sm=..)` parziali -> `EC`, con `rest_cancelOrders`,
  `rest_replace_cancel` e l'ordine nato da un `replaceOrders` legato al padre (`nato_da`). Lo stesso `uo` visto da
  piu' processi conta una volta (il primo arrivo), le copie si contano (`copie_ocm`).

Da Python: `AO.analizza_giorno(cartella, giorno)` restituisce il dizionario completo; `AO.formatta(a)` il testo;
`AO.leggi_file(p)` le righe di un file (per il futuro trasporto sul banco: le righe `stream` hanno `msg` verbatim,
ordinate per `seq`, divise per `sid`).

## 8. Checklist del PC per FIRMARE

1. `git fetch` e `git log --oneline a3a58ad8..origin/mappa/m1-ordini` (o il ramo consegnato): un commit M-1.
   `git diff a3a58ad8 --stat`: SOLO aggiunte; nei tre file esistenti (`auth.py`, `client.py`, `tempi_ordine.py`) solo
   un import e una riga `if _ro.attivo(...)`. Rileggere il diff di persona.
2. Test nuovi: `python -m pytest Betfair/monitor/tests/test_registratore_ordini_2026_10_11.py -q -p no:cacheprovider`
   -> 29 verdi.
3. Mutazioni: `python ARCHITETTURA_2026-10/mappa/m1_mutazioni.py` -> 25 righe `ROSSO ... ripristino sha256 identico`,
   uscita 0; poi `git status` pulito.
4. Suite intera UNA volta: `python -m pytest Betfair/ -q -p no:cacheprovider` -> 0 rossi.
5. Giro PAPER a interruttore SPENTO (nessuna riga in `.env`): avvio dell'app da parte dell'utente, un bot in paper per
   qualche minuto. Controllare: nessuna cartella `_live_raw\_ordini`, nessun thread `registro-ordini`, nessuna riga
   `[registro-ordini]` nei log, comportamento del bot identico al giorno prima.
6. (facoltativo, solo con il si' dell'utente) un giro con `REGISTRO_ORDINI=1`: dopo il riavvio dell'app, nei log
   `[registro-ordini] ACCESO` e `scrivo ...\_ordini\<giorno>\ordini_<servizio>_<pid>.jsonl.gz`; a fine giro
   `python -m Betfair.monitor.analisi_ordini --giorno <AAAAMMGG>`; verificare a mano che nessun file contenga il token
   o l'app key (`python -c` con `gzip.open(...).read()` e `in`).

## 9. Limiti noti e cose NON verificate

* Nessuna riga `ocm` VERA di Betfair esiste nel repo: i test usano la forma documentata dello stream ordini, accettata
  dal listener VERO di betfairlightweight 2.23.2 e da flumine 2.13.11 (gli stessi della macchina del cloud). La
  forma reale si vedra' al primo giro acceso sul PC.
* Il client REST nostro ritenta dentro `_rpc` (fino a `max_retries`): il record `rest` e' UNO per chiamata a
  `betting_rpc` (istante d'invio del primo tentativo, risposta o eccezione finale), i singoli tentativi non si vedono.
* `decisione_ms` c'e' solo se il comando la porta (`emesso_ms` di `sonde.marca_emesso` a monitor «Salute» acceso, o
  le altre chiavi di `tempi_ordine._CHIAVI_DECISIONE`). Le REST dirette (Omega/Mike in `omega_market`, `order_exec`)
  non passano da `tempi_ordine`: per loro niente `dec`.
* `ocm` prima della risposta e latenza REST -> ocm confrontano istanti di processi diversi con l'orologio di parete
  dello stesso PC: corretti fra loro, non rispetto a Betfair (il `pt` dei messaggi resta nel `msg`).
* Lo stream ordini di flumine e' filtrato da `config.customer_strategy_ref` se impostato: gli ordini del sito
  compaiono solo se il filtro e' vuoto (oggi lo e': `flumine.config.customer_strategy_ref` = `None`).
* Non verificati qui (macchina condivisa del cloud, nessuna app): il giro paper e quello live sul PC; il comportamento
  su Windows della cancellazione di file aperti da altri processi (gestito: errore catturato e loggato) e di
  `perf_counter` fra processi (QueryPerformanceCounter e' di sistema).
