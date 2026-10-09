# REFERTO W1-A2 - Comparto A: stream degli ordini del conto, ladder, profili, gestore dei flussi

Ramo `architettura/w1-a2` da `559a96df`. Agente W1-A2, 09/10/2026. Nessun file esistente modificato (verificato con
`git status` / `git diff --stat 559a96df`: solo file nuovi del dominio). Nessuna rete, nessun DB, nessun processo nuovo:
le connessioni dei test vanno a un server finto su 127.0.0.1.

## 1. Cosa ho costruito (e cosa NON fa)

(Righe al commit 589b8c26; quelle dopo la revisione sono nel par. 10.)

| File | Punti chiave | Cosa NON fa |
|---|---|---|
| `Betfair/nucleo/betfair/flusso_ordini_conto.py` (643 righe) | `ordine_dalla_cache` `:122` (UnmatchedOrder della cache di bfl -> `OrdineDalConto`, tutte le chiavi ocm); `normalizza_ordini` `:189` (valori di serie documentati e prova per ordine: reperto di W1-C2, vedi par. 9 D6); `_OrderStreamConto._process` `:232` (normalizza, la cache VERA si aggiorna, poi si leggono gli ordini toccati); `ListenerConto` `:240` (battito, `connectionsAvailable` anche 0, `heartbeatMs` rimandato, errore di elaborazione -> immagine piena); `FlussoOrdiniContoBetfair` `:371` (filtro `:387`, ciclo di riconnessione con backoff e clk `:544-610`, stato vivo/muto e tipo di sottoscrizione `:498`, consegna ai consumatori `:627`) | non piazza/annulla/modifica (test d'introspezione: nessun metodo pubblico oltre i 7 del contratto+estensioni, nessuna chiamata `.betting.`); non tocca lo stream ordini di flumine; non attribuisce (comparto C); nessun DB/file |
| `Betfair/nucleo/betfair/ladder.py` (523) | helper puri gemelli `:111-230` (UNA copia per calcio e tennis); `profilo_ladder` `:79` (stesse env di oggi); `LadderEvento` `:244`: `push_a_ogni_cambio` `:295`, coalescenza per mercato `_scaduti` `:442`, `esegui_scaduti` `:322` (anche il client nuovo del canale riceve tutto), DB in thread suo `esegui_db` `:346`/`_ciclo_db` `:426`, versione riusata da `ladder_canale.StatoLadder.versione` `:505-523` | non decide i mercati (li dice `meta`); non converte GBP->EUR; non apre connessioni |
| `Betfair/nucleo/betfair/profili.py` (207) | i 4 profili `:114-182` con `file:riga` di oggi e lo stesso parsing delle env; `filtro_dati` `:200` | nessun valore cambiato (U-01/U-02/U-03) |
| `Betfair/nucleo/betfair/flusso.py` (646) | `piano_connessioni` `:100` e `connessioni_concesse` `:127` (gemelli di `frammenti_mercato`); `ListenerFlusso` `:170`; `_Connessione` `:238` (sottoscrizione sostitutiva `:276`, ripresa clk `:323`, rifiuto non ritentato `:341`); `GestoreFlussi` `:364` (`imposta_mercati` `:409`, `manutenzione` `:500`, `stato_flusso` `:445`, conversione GBP->EUR alla fonte con `valuta.converti_libro` `:623`) | non e' agganciato a flumine: i bot di oggi continuano a ricevere i book da flumine; nessun tee raw (P5); niente piano a shard `id mod N` dello scanner (D2) |
| `Betfair/nucleo/betfair/doc/A2_FLUSSI_LADDER.md` | schema `COSA_FA.md` | |
| `tests/test_a2_*.py` (7 file, 100 test) | finti: server Stream API TLS su 127.0.0.1 + `APIClient` vero (`test_a2_finti.py`) | |
| `ondata1/W1-A2/misura_ladder.py`, `falsifica.py`, `falsifica_esito.jsonl` | strumenti rieseguibili ed esito | |

## 2. Contratto

Implementati: `FlussoOrdiniConto` (`FlussoOrdiniContoBetfair`), `Ladder` (`LadderEvento`), `FlussoMercato` (`GestoreFlussi`),
`ProfiloFlusso` (i 4 profili). Conformita' provata con `test_a2_finti.conforme` (i protocolli non sono `runtime_checkable`:
si confrontano nomi e parametri dei metodi). Usato `Sessione` come protocollo (nessun import di `sessione.py` di W1-A1).

Estensioni ADDITIVE proposte (in un mio file, contratto intatto):
1. `FlussoOrdiniConto.aggiungi_consumatore(cb, *, mercati=None)` (filtro per mercato, chiesto dal brief); `posizioni(market_id)`
   (posizione abbinata del CONTO `mb`/`ml` per selezione: base del P&L di mercato anche per gli ordini conclusi che dopo una
   caduta non tornano nell'immagine); `ordini_non_confermati()` (EXECUTABLE assenti dall'immagine piena dopo una caduta).
2. `FlussoMercato.capacita()`, `manutenzione()`, `avvia()`/`ferma()` (vita esplicita, regola 7 del brief).
3. `Ladder.consumatore(book)` (callback per `FlussoMercato`), `esegui_scaduti`/`esegui_db` (deterministici, il thread li chiama),
   `snapshot` ritorna la RIGA intera del topic `ladder` (`{event_id, market_id, market_type, market_name, status, ladder}`).
4. Interpretazioni dichiarate: `ProfiloFlusso.ladder_levels = 0` = "non inviato" (oggi lo scalper usa il filtro di serie di
   flumine senza `ladderLevels`; il contratto lo tipizza `int`: proposta `Optional[int]`); `riserva_connessioni = 0` per tennis,
   scanner, scalper (oggi solo il calcio la ha). `customer_order_ref`/`customer_strategy_ref` vuoti (`""`) -> `None`.

## 3. Parita'

| Oggi (file:riga) | Nuovo | Test | Esito |
|---|---|---|---|
| `runner.py:575-685` `_as_levels`, `compute_wom`, `build_ladder_selection`, `ladder_signature`, `build_ladder_payload` | `ladder.livelli`, `peso_del_denaro`, `selezione`, `firma`, `payload_ladder`, `firma_con_stato` | `test_payload_e_firma_identici_su_ogni_book[35760084]` | IDENTICI su 65.445 book su 65.445 (payload `==`, firma con stato `==`) |
| `tennis_runner.py:200-275` (gemelli) | idem | idem | IDENTICI sugli stessi book |
| idem, registrazione 35797769 | idem | `...[35797769]` | IDENTICI su 197.229 book su 197.229 (esecuzione COMPLETA del 09/10, 784 s su macchina carica); di serie la suite confronta 1 book su 7 (tutti ricostruiti e contati), `A2_PARITA_COMPLETA=1` = tutti |
| casi limite (livelli malformati, prezzo 0/negativo/None, size None, `max_levels` None/0/-1/1/3/10, WOM 0/1/3/20) | idem | `test_casi_limite_identici_alle_due_copie_di_oggi` (24 combinazioni x 5 runner x 2 copie) | identici |
| `runner.ladder_worker` `:689-757` + `MarketRecorderStrategy` vero + `StatoLadder` (cadenza 0) | `LadderEvento` (intervallo 0) | `test_sequenza_del_topic_identica_al_worker_di_oggi[calcio]` | sequenza IDENTICA messaggio per messaggio su 30.653 messaggi di 35760084: stesse righe canale (valori `==`, stesso ordine delle chiavi, `json.dumps` byte per byte ogni 25 righe), stesse righe DB alla cadenza di 2 s, `updated_ms` strettamente crescente, 21 mercati CLOSED |
| `tennis_runner.ladder_worker` `:1469-1517` + `_make_capture` vero | `LadderEvento` profilo tennis | `...[tennis]` | idem |
| worker di oggi a 200 ms | `LadderEvento` a 20 ms | `test_cadenza_20ms_contro_200ms_su_registrazione` | 0 righe diverse da cio' che oggi pubblicherebbe per lo stesso stato; 0 pubblicazioni dello stesso mercato sotto i 20 ms |
| `frammenti_mercato.pianifica` `:238-266` | `flusso.piano_connessioni` | `test_piano_identico_a_frammenti_mercato_su_griglie` (5 semi x 400 griglie) + casi limite | identico (bersagli, nuovi, fuori) |
| `GestoreFrammenti.massimo_adesso` `:446-465` (+ `motivo_limite` mostrato in UI) | `flusso.connessioni_concesse` / `GestoreFlussi.massimo_adesso` | `test_budget_identico_a_gestore_frammenti` (9 combinazioni x 5 aperte x 6 disponibili x 4 pause, listener VERI dei due mondi) | identico, testo compreso |
| costanti di `config_stream.py`, `auto_follow.tetto_mercati`, `GestoreFrammenti.da_ambiente`, `tennis_runner.py`, `iscrizione_a_caldo.tetto_mercati`, `safe_strategy/stream.py` (`StreamShard._subscribe` vero con uno stream spia), filtro di serie di flumine | `profili.py`, `profilo_ladder` | `test_profili_uguali_ai_valori_di_oggi` x 3 ambienti (di serie, cambiato, fuori limiti) in processo a parte | identici |

## 4. Migliorie misurate

Strumento: `python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py` (tempo = `pt` della registrazione; misura la CADENZA,
non CPU ne' rete; il ladder di oggi e quello nuovo girano insieme sugli stessi `MarketBook`).

| Registrazione | Sport (worker) | Pubblicazioni oggi (200 ms) | Pubblicazioni nuovo (20 ms) | Attesa oggi p50 / p95 / max / media (ms) | Attesa nuovo p50 / p95 / max / media (ms) | Righe nuove diverse da oggi | Stesso mercato < 20 ms |
|---|---|---:|---:|---|---|---:|---:|
| 35760084 (30.653 msg, 65.445 book) | calcio | 58.583 | 64.930 | 91,2 / 187,9 / 200 / 94,9 | 0 / 0 / 18 / 0,0 | 0 | 0 (*) |
| 35760084 | tennis | 58.583 | 64.930 | 91,2 / 187,9 / 200 / 94,9 | 0 / 0 / 18 / 0,0 | 0 | (*) |
| 35797769 (81.137 msg, 197.229 book) | calcio | 163.163 | 194.850 | 84,9 / 187,1 / 200 / 89,7 | 0 / 0 / 20 / 0,0 | 0 | 0 |
| 35797769 | tennis | 163.163 | 194.850 | 84,9 / 187,1 / 200 / 89,7 | 0 / 0 / 20 / 0,0 | 0 | (*) |

(*) La prima esecuzione dello strumento contava come "sotto i 20 ms" anche scarti di meno di 1 microsecondo dovuti al passo
dei float a 1,78e9 s (tempo della registrazione in secondi epoch): 56 su 35760084, 529 su 35797769. Con tolleranza 1 us
il conteggio e' 0 su 35760084 calcio (il test `test_cadenza_20ms_contro_200ms_su_registrazione`) e su 35797769 calcio
(rimisura); i due casi tennis non sono stati rimisurati (stessi book, stessi istanti, stessa cadenza dei casi calcio); in esercizio
l'orologio e' `time.monotonic` (valori piccoli), il problema non esiste. Calcio e tennis danno gli stessi numeri perche' i
due worker di oggi hanno la stessa cadenza e qui vedono gli stessi mercati (il tennis vero ha 1 mercato per evento).
Tempo di calcolo dello strumento su macchina condivisa (4 CPU, carico 8-9): 84-90 s per 35760084, 534-659 s per 35797769.

Lettura: il ladder nuovo pubblica il book appena arriva (attesa mediana 0 ms, mai oltre 20 ms per la coalescenza) contro
la media di ~95 ms e il massimo di 200 ms di oggi; le pubblicazioni crescono di circa il 10% (piu' messaggi al canale:
rischio R di T6, tetto di 64 invii in volo per client di `local_channel.py:176`, da misurare in ombra). Il DB esce dal
thread del ladder (thread suo, stessa cadenza 2 s write-on-change). Dal vivo la misura vera e' la sonda `ladder_pub_pt_ms`
della Salute in ombra.

## 5. Test e falsificazioni

- Test nuovi: 100 (`python -m pytest Betfair/nucleo/betfair/tests/ -q -p no:cacheprovider`), tutti verdi; i 5 test sulle registrazioni (`test_payload_*`, `test_sequenza_*`, `test_cadenza_*`) pesano ~6-8 minuti su macchina carica, gli altri 95 ~20 s.
- Falsificazione (`python ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py`, ripristino con sha256 verificato per ognuna):
  **34 mutazioni, 34 rosse, 34 ripristinate** (esito riga per riga in `falsifica_esito.jsonl`, rieseguito sul codice finale). Fra queste
  le tre di A par. 5 punto 6: togliere l'ordinamento per `selection_id` (M1, rosso anche SOLO il confronto su ogni book della
  registrazione vera, M1b), togliere `initialClk/clk` (M8 ordini, M15 prezzi), spegnere `connectionsAvailable` (M17); la
  conversione GBP->EUR tolta (M28, punto 6c); lo stream ordini filtrato per strategia (M9); l'ordine del sito senza `rfo`/`rfs` (M26), l'esempio ufficiale (M29), il BSP senza prezzo (M30), la partenza da zero
  non dichiarata (M31).
- Suite intera `python -m pytest Betfair/ -q -p no:cacheprovider`: eseguita DUE volte (regola del brief).
  1a (dopo le prime consegne): **11.687 verdi, 1 rosso, 65 saltati, 6 xfail** in 885 s; 2a (dopo la correzione rfo/rfs e la
  conversione GBP->EUR): **11.691 verdi, 1 rosso, 65 saltati, 6 xfail** in 634 s. L'unico rosso, in entrambe:
  `Betfair/stream/tests/test_valuta_k1_2026_09_26.py::test_contratto_ogni_fonte_di_book_dello_stream_e_convertita` = la guardia
  di K1 che vuole registrate le fonti nuove di book (`flusso.py`, `flusso_ordini_conto.py`) in un dizionario del test (file di
  oggi, non toccato): aggancio in par. 8.4. Dopo la 2a suite ho cambiato SOLO `flusso_ordini_conto.py` e il suo test (seconda
  richiesta del coordinatore: valori di serie per ordine, BSP, `sottoscrizione`/`seme_rest_necessario`): rieseguiti i 100 test
  del comparto (verdi) e le 34 mutazioni (rosse), non la suite (tetto di due).

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (test nel doc `A2_FLUSSI_LADDER.md` par. 5): A-052, A-053, A-054, A-069 (ladder), A-062 (parametri di stream),
A-029..A-034 (gestore, piano, battito, ripresa, muto, sottoscrizione a caldo), A-077 (parte stream: 503); nuova T11 (stream
ordini del conto). Restano al codice di oggi: A-020..A-028, A-035..A-051, A-055..A-061, A-063..A-068, A-070..A-076,
A-078..A-086 (follow, catalogo, ciclo di vita del runner, tee raw P5, canali P6, tennis, scanner, UI). G-014 (la riga
`live_ladder`) e J-078/J-084 (le pagine del ladder) non cambiano: stessa riga, stesso JSON.

## 7. PSB par. 6/7

Sollecitate: 6.1 (`mcm`/`ocm` nativi, listener vero, OPEN/SUSPENDED/CLOSED, registrazioni COMPLETE 35760084 e 35797769),
6.5 (la riga che la UI legge: stesse chiavi, stesso ordine), 6.6 (200 mercati, connessioni, `connectionsAvailable`,
rifiuto), 6.7 (scenari: caduta, `RESUB_DELTA`, `INVALID_CLOCK`, sessione scaduta, 503, muto, rifiuto, messaggio malformato;
falsificazione), 6.8 (comandi, versioni: flumine 2.13.11, betfairlightweight 2.23.2, Python 3.13.16);
7 n.9 (nessun `getattr` su dict: il ladder legge il dict con `.get` come oggi, il book con gli attributi della libreria),
n.17 (sospeso e chiuso pubblicati come oggi), n.19 (stato perso alla caduta: ripresa con clk, ordini non confermati),
n.20 (`vivo` per mercato solo con un book sulla sottoscrizione corrente), n.21 (avp assente resta None, non 0), n.27
(finti con le chiavi dello schema ufficiale e le classi vere), n.29/n.30/n.35 (ogni test visto rosso), n.33 (nessuna costante
duplicata: profili con `file:riga` e test).
⊘ con causa: 6.2 (scanner: lo scanner vero non e' toccato in questa ondata), 6.3 (servizio intero: i bot non passano dal
nucleo finche' non c'e' l'aggancio), 6.4 (ciclo di vita dell'ordine: e' del comparto C; qui solo la LETTURA degli stati
dello stream: parziali, annullati, scaduti, annullati da Betfair provati), 6.9 (nessun replay del banco in questa ondata);
7 n.1-8, 10-16, 18, 22-26, 31-32, 34, 36-37 (riguardano bot, banco, DB o UI, non toccati qui).

## 8. Aggancio proposto per l'ondata 2 (NON fatto)

### 8.1 Stream degli ordini del conto (T11)

**Dove nasce**: UNA volta per conto, nel runner calcio (`Betfair/stream/runner.py`, processo sempre vivo con l'app e padrone
del canale 47331 e del topic `conto`), dietro `ARCH_ORDINI_CONTO=spento|ombra|acceso` (di serie spento). Punto: subito dopo
`build_order_client` (`runner.py:2215-2320`), con la sessione del custode (`Sessione` di W1-A1), `avvia()` all'avvio dello
stream e `ferma()` in `arresto_ordinato`. Il runner tennis NON ne apre un secondo: il ladder tennis legge il topic `conto` del 47331
(o il processo tennis riceve gli ordini dal canale).

**Seme del libro**: a ogni `stato()['seme_rest_necessario']` vero (partenza da zero, D7) il libro ordini (C) chiede
`listCurrentOrders` (porta REST di W1-A1, pesi e 3 concorrenti) per gli EXECUTION_COMPLETE che lo stream non ripete; in ripresa
con clk nessun seme. **Cosa alimenta**: (a) il topic `conto` di oggi (`esiti_ordini_canale.py:647-677`, `payload_conto` `:774-796`): in ombra si confronta la
fotografia nuova (ordini da `ordini(mid)` nella grafia `listCurrentOrders` via `ordine_del_conto`) con quella di flumine per
ogni mercato; (b) il libro ordini del comparto C (`ordini/libro_conto.py` di W1-C2) via `aggiungi_consumatore`; (c) la Salute
(`stato()`).

**Connessioni (limite 10 per app key; oggi caso peggiore 10/10, A par. 1.3)**:

| Opzione | Calcio | Order calcio | Tennis | Order tennis | Scanner | Conto | Totale LIVE | Totale PAPER | Nota |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0. oggi | 3 | 1 | 1 | 1 | 4 | 0 | **10** | 8 | in PAPER nessuno stream ordini reale: il ladder non vede sito, Mike live, scalper |
| A. connessione conto SEMPRE | 3 | 1 | 1 | 1 | 4 | 1 | **11 (oltre)** | 9 | inaccettabile senza togliere una connessione |
| B. conto solo in PAPER; in LIVE si legge lo stream di flumine gia' aperto (osservatore, come `osserva_conto_su_flumine`) | 3 | 1 | 1 | 1 | 4 | 0/1 | **10** | **9** | nessuna connessione in piu' nel caso peggiore; in LIVE niente ripresa clk (flumine `OrderStream.run` non passa clk) e la posizione complessiva non c'e' (`include_overall_position=False`) |
| C. conto sempre + scanner a 3 connessioni (540 mercati) | 3 | 1 | 1 | 1 | 3 | 1 | **10** | 9 | lo scanner perde 180 mercati di capacita' (oggi ripiego REST per i fuori) |
| D. conto sempre + calcio a 2 frammenti (360 mercati) | 2 | 1 | 1 | 1 | 4 | 1 | **10** | 9 | il calcio torna sotto la capacita' del 26/09 (24 partite fuori quel giorno) |
| E. conto sempre + richiesta a Betfair di 1.000 mercati per connessione (U-04) | 1-3 | 1 | 1 | 1 | 1 | 1 | **6-8** | 5-7 | dipende da Betfair; nessun codice da cambiare oltre ai profili |

La scelta e' dell'utente. Nota tecnica: in LIVE il runner calcio e il runner tennis aprono OGGI due stream ordini del conto
NON filtrati (stessi dati): l'opzione B piu' "un solo order stream per conto" (tappa C) libererebbe una connessione.

### 8.2 Ladder (T6)

`ARCH_LADDER=vecchio|ombra|nuovo` (di serie vecchio).
- `vecchio`: tutto come oggi.
- `ombra`: in `runner.py` dopo la costruzione del recorder (`:2957-2975`) si crea `LadderEvento(profilo_ladder("calcio"), meta=...,
  pubblica=<registratore delle firme>, scrivi_db=None, marca_canale=None)`; `MarketRecorderStrategy.process_market_book`/
  `process_closed_market` (`recorder.py:189-235`) chiamano `ladder.consumatore(market_book)` (una riga, sotto interruttore).
  `meta(mid)` = `MetaLadder(session.market_to_event[mid], tipo/nome da session.markets_by_event, session.selection_names[mid])`,
  None se l'evento e' in `finished_events` (stessa selezione del worker `runner.py:713`). Il vecchio `ladder_worker` resta il
  publisher vero; un confronto registra per mercato la sequenza delle firme `status|sha1` dei due e conta le divergenze
  (criterio: 0 firme del nuovo che il vecchio non abbia per lo stesso book; `updated_ms` crescente; attesa `ts_pub_ms - pt` <= oggi).
  Tennis: `_Capture.process_market_book`/`process_closed_market` (`tennis_runner.py:429-458`), `meta` = solo `market_meta[ev].market_id`
  (come `tennis_runner.py:1482`).
- `nuovo`: `pubblica=_lc.publish`, `canale_attivo=_lc.channel_active`, `scrivi_db=db.upsert_live_ladder` (tennis:
  `tennis_db.upsert_tennis_ladder`), `marca_canale=_mon.marca_ladder` se `_mon.ATTIVO` (solo calcio, come oggi), e il
  `ladder_worker` non si registra (`runner.py:3108-3112`, `tennis_runner.py:3425-3428`).
- Uguale o meglio: firme identiche al 100% per una giornata, attesa <= oggi, `localTransport.test.ts`, `canaleRunner.test.ts`,
  `localChannel.test.ts` verdi senza modifiche; conteggio dei salti del canale (`local_channel` `saltati`) non peggiore.

### 8.3 Gestore dei flussi (T19)

`ARCH_FLUSSO_<SPORT>=vecchio|nuovo`; ombra SOLO sul banco (mai due connessioni uguali sul live). Primo: tennis (1 connessione,
profilo `runner_tennis`), poi calcio (`runner_calcio`, al posto di `GestoreFrammenti`), poi scanner (`scansione`, decisione U-07).
La conversione GBP->EUR e' gia' nel gestore (`valuta.converti_libro`, come lo scanner). Prima dell'aggancio servono: il tee raw (P5)
e il ponte verso flumine (i bot di oggi ricevono i book da `Flumine`; un `MarketStream` di flumine alimentato dal `GestoreFlussi`).

### 8.4 Il test di contratto della valuta (file di oggi da aggiornare, NON toccato)

`Betfair/stream/tests/test_valuta_k1_2026_09_26.py::test_contratto_ogni_fonte_di_book_dello_stream_e_convertita` cerca in
tutto `Betfair/` chi costruisce una fonte di book (`\.create_stream\(`, `StreamListener\(`) e vuole ogni file registrato in
`_FONTI_CONVERTITE` o `_FONTI_ESENTI` (`:427-458`). I due moduli nuovi lo fanno e il test e' ROSSO nella suite di questo
ramo (unico rosso, vedi par. 5). Proposta (due righe, nel dizionario del test, da fare dal coordinatore):
```
_FONTI_CONVERTITE["Betfair/nucleo/betfair/flusso.py"] = "converti_libro("
_FONTI_ESENTI["Betfair/nucleo/betfair/flusso_ordini_conto.py"] = "stream ORDINI: importi gia' nella valuta del conto (EUR), nessun book"
```
`flusso.py` converte davvero alla fonte (`GestoreFlussi._consegna`, `valuta.converti_libro` col cambio di processo
`valuta.CAMBIO`, congelato per mercato; test `test_size_dello_stream_convertite_gbp_eur_alla_fonte`, mutazione M28 rossa).
Non ho aggirato la guardia (es. chiamando `create_stream` per `getattr`): sarebbe stato nasconderle una fonte.

## 9. Divergenze per l'utente, rischi, dubbi

- **D1 (premessa del brief smentita dal codice)**: lo stream ordini che flumine apre oggi NON e' filtrato per strategia:
  `flumine/streams/orderstream.py` passa `customer_strategy_refs=None` perche' `flumine.config.customer_strategy_ref` vale
  `None` e nessun file del repo lo imposta (`git grep`), come gia' scritto in `esiti_ordini_canale.py:647-660` (30/09). In LIVE
  gli ordini del sito arrivano gia' (e flumine li scarta nel blotter; il runner li pubblica sul topic `conto`). Il buco vero e':
  (a) in PAPER non esiste uno stream ordini reale (`runner.py:2270-2290`: `SimulatedOrderStream`), quindi il ladder non vede
  ordini del sito, di Mike live, dello scalper; (b) lo stream di flumine non riprende con clk (`flumine/streams/orderstream.py:40-50`: nessun
  `initial_clk`) e chiede `includeOverallPosition=False`. Il modulo nuovo copre entrambe le cose.
- **D2 (scanner)**: lo scanner oggi divide i mercati con `plan_shards` (`safe_strategy/stream.py:95-123`, shard = `id mod N`,
  priorita' in testa, i tagliati al ripiego REST), non col piano a riempimento del calcio. `GestoreFlussi` usa il piano del calcio
  per tutti i profili: portare lo scanner sul gestore (U-07) cambia la distribuzione (non i dati). Da decidere in T19.
- **D3 (chiusura del mercato nel ladder)**: calcio e tennis fanno cose diverse oggi (calcio: l'ultimo book marcato CLOSED,
  `recorder.py:220-225`; tennis: il book chiuso serializzato, `tennis_runner.py:433-458`). Il nuovo le riproduce ENTRAMBE
  (`ProfiloLadder.chiusura`); non ho scelto. Unificarle e' una decisione dell'utente (cambia cosa mostra il ladder di un mercato chiuso).
- **D4 (scanner oltre 200)**: oggi `SAFE_STRATEGY_STREAM_MARKETS_PER_CONN` arriva a 1000 (con avviso); il contratto dice
  "mai > 200": il profilo riporta il valore di oggi, il gestore lo limita a 200 (`limite_mercati`, alzabile solo se Betfair alza
  il limite, U-04).
- **D5 (heartbeat dello stream ordini)**: il modulo nuovo chiede `heartbeatMs=5000` esplicito (flumine non lo chiede): serve a
  dire "muto" con certezza (3 x 5 s). Non tocca i dati dei bot (e' uno stream nuovo, sola lettura).
- **D6 (reperto di W1-C2, verificato e corretto)**: in betfairlightweight 2.23.2 `UnmatchedOrder.__init__` ha `rfo`, `rfs`, `p`,
  `s`, `ot`, `pd`, `sm`, `sr`, `sl`, `sc`, `sv` OBBLIGATORI (`streaming/cache.py:420-446`; provato: `TypeError: missing 2 required
  positional arguments: 'rfo' and 'rfs'`) e `serialise` valida `side`/`status`/`ot` con gli enum (KeyError). La documentazione
  ufficiale (`AUDIT_2026-10-02/_fonti_betfair/bf_2687396.txt:909`) dice `rfs` "default is \"\"" e il suo ESEMPIO di ocm
  (`:1108-1114`) NON porta `rfo`/`rfs`: con la sola libreria quell'esempio fa cadere la cache, il messaggio intero e lo stream
  (e, con la ripresa a immagine piena, in un ciclo). Correzione nel mio file (`normalizza_ordini`): i campi assenti prendono il
  valore di serie documentato (`rfo`/`rfs` = "", importi = 0 come da nota BSP `:1120`, `p`/`s`/`pd` = None: MAI inventati) e
  ogni ordine si PROVA con la classe vera prima della cache; chi non va (es. senza `side`, codice sconosciuto) si toglie dal
  messaggio, si logga col motivo, si conta (`ordini_scartati`) e si segnala (`ordini_non_confermati`); gli altri passano.
  Test: l'esempio ufficiale VERBATIM (3 messaggi, parziale -> completo -> prezzo medio cambiato), ordine del sito senza
  `rfo`/`rfs`/`rac`/`rc` (catena vera e connessione vera), BSP `MARKET_ON_CLOSE` senza `p`/`s` (prezzo e importo None),
  ordini non applicabili scartati; mutazioni M26, M27, M29, M30 rosse. Due note: (a) BSP senza `p`/`s` NON verificato dal vivo;
  `OrdineDalConto.prezzo`/`importo` sono `float` nel contratto: PROPOSTA `Optional[float]` (oggi passa None); (b) lo stesso
  difetto della libreria vale per lo stream ordini di flumine di OGGI in LIVE (stessa cache): se Betfair manda un ordine senza
  `rfo`/`rfs` il runner LIVE perde lo stream ordini. Non verificato dal vivo (nessuna registrazione `ocm` nel repo): da guardare
  nei log del PC.
- **D7 (partenza da zero dello stream ordini)**: una sottoscrizione SENZA clk (prima apertura, `INVALID_CLOCK`, messaggio non
  applicabile) riceve SOLO gli EXECUTABLE: gli EXECUTION_COMPLETE precedenti arrivano "only when transitioning"
  (`bf_2687396.txt:941`). `stato()` porta `sottoscrizione` (`ripresa_clk` | `da_zero`), `sottoscrizione_ms` e
  `seme_rest_necessario` (vero dopo una partenza da zero): il libro ordini del comparto C deve allora seminare da
  `listCurrentOrders` (e i conclusi da `listClearedOrders`); `ordini_non_confermati` elenca gli EXECUTABLE noti spariti
  dall'immagine. Mutazione M31 rossa.
- **Proposta di W1-C2 (valutata)**: aggiungere `event_type_id` a `OrdineDalConto`. Lo stream ordini NON lo porta (l'`ocm` ha solo
  il market id); andrebbe preso dal catalogo (`listMarketCatalogue`) o dal `marketDefinition` dello stream dei prezzi: cioe' non e'
  "come lo dice Betfair" sullo stream ordini. Proposta: NON nel tipo del contratto ma come arricchimento del comparto C (che ha il
  catalogo) o come campo additivo facoltativo `event_type_id: Optional[str] = None` riempito da chi conosce il mercato. Contratto
  non toccato.
- **R1**: la libreria aggiorna `clk` PRIMA di applicare un messaggio (`stream.py` `on_update`): dopo un messaggio non applicabile
  riprendere da quel clk lo salterebbe. Gestito (immagine piena) e provato (M12).
- **R2**: la cache ordini di betfairlightweight 2.23.2 ignora i delta di `smc` (posizioni per strategia): per questo
  `partitionMatchedByStrategyRef=False` (motivo nel docstring).
- **R3**: in `ferma()` uno `stop` arrivato fra la sottoscrizione e la lettura farebbe ricollegare `BetfairStream.start`: gestito con
  stop ripetuto fino all'uscita del thread (provato: nessun thread vivo dopo `ferma`).
- **R4**: i test di parita' sulle registrazioni sono pesanti (ricostruzione di 262.674 book con la libreria vera): ~6-8 minuti
  di suite su macchina carica per `test_a2_ladder_parita.py`; il confronto completo di 35797769 (13 min) e' dietro
  `A2_PARITA_COMPLETA=1` (eseguito il 09/10: verde).
- **Dubbio**: il "minimo 20 ms" e' per mercato (due mercati diversi escono nello stesso istante). Se l'utente intendeva un
  minimo globale del canale, e' un parametro.

## 10. Correzioni dopo la revisione (09/10, revisione indipendente di 589b8c26: DA CORREGGERE, 9 rossi)

Commit nuovo sopra 589b8c26 (storia non riscritta, nessun push). Nessun file esistente toccato. Ogni correzione ha un
test nostro (i test del revisore incorporati con nomi nostri, asserzioni sul comportamento corretto) e una mutazione che
lo rende rosso, con ripristino verificato da sha256 (`falsifica.py`, esito riga per riga in `falsifica_esito.jsonl`:
`sha256_prima` = `sha256_dopo` per ogni mutazione). File di test nuovi: `tests/test_a2_ordini_revisione.py` (O),
`tests/test_a2_flusso_ladder_revisione.py` (FL).

| Punto | Correzione (file:riga) | Test (file::nome) | Mutazione rossa |
|---|---|---|---|
| A1 ordini stantii | `flusso_ordini_conto.py:336` `_on_change_message` (fine immagine di sottoscrizione: `SUB_IMAGE` intera o `SEG_END`, anche senza `oc`), `:828` `_su_fine_immagine`, `:410` immagine di RUNNER, `:836` `_non_piu_confermati` (riconsegna con `confermato=False`) | O::`test_ripartenza_da_zero_su_un_altro_mercato_segnala_gli_stantii` (R1), `::test_ripartenza_da_zero_con_immagine_vuota_senza_oc` (R2), `::test_fullimage_solo_di_runner_segnala_l_ordine_sparito` (R3), `::test_immagine_a_segmenti_si_chiude_solo_a_fine_segmento`, `::test_consumatore_riceve_l_ordine_non_confermato` (R7), `::test_fullimage_di_mercato_in_una_ripresa_segnala_l_ordine_sparito`, `::test_ordine_non_confermato_che_si_rifa_vivo_torna_confermato` (X1) | R1, R2, R3, R22, M11, X1 |
| A2 posizioni | `flusso_ordini_conto.py:816-818` (la `fullImage` di mercato SOSTITUISCE le posizioni del mercato), `:411` | O::`test_posizione_di_un_runner_assente_dalla_nuova_immagine_di_mercato_esce` (R6) | R4 |
| A3 backoff | SUPERATA dalla seconda revisione (par. 11): "ocm/mcm ricevuti" NON azzera piu' (tempesta), solo `VIVA_DOPO_S` = 60 s | O::`test_backoff_si_azzera_dopo_una_connessione_sana[True-2.0/False-60.0]` (R5), FL::`test_backoff_della_connessione_si_azzera_dopo_dati[...]` | R5, R6 |
| M1 watchdog | `flusso_ordini_conto.py:780` `_watchdog`; `flusso.py:604` `veglia`, `:731` `_ciclo_watchdog`; soglia `BATTITI_WATCHDOG` = 3 heartbeat (motivo: la stessa soglia del "muto" di tutta l'app, `stream_muto.BATTITI_PER_SOGLIA`; Betfair dice 2 = "forse disconnesso": un battito di margine contro il ritardo di un singolo heartbeat; con 500 ms chiesti = 1,5 s) | O::`test_watchdog_chiude_lo_stream_muto_e_riprende_con_clk`, FL::`test_watchdog_del_flusso_muto_riprende_con_clk_ed_emette_l_evento` (server TLS che smette di parlare SENZA chiudere) | R7, R8 |
| M2 ladder, errore di invio | `ladder.py:518-546` `_pubblica_mercato`: try per mercato, il mercato torna in attesa, gli altri del lotto escono; `:362-374` riprova | FL::`test_errore_di_pubblicazione_non_perde_lo_stato_ne_il_resto_del_lotto` (L1) | R9 |
| M3 meta in ritardo | `ladder.py:528-530` (`RIPROVA_META_S` = 0,2 s; nessun giro a vuoto) | FL::`test_meta_che_arriva_dopo_il_book_riaccende_la_pubblicazione` (L2), `::test_meta_assente_non_fa_girare_a_vuoto_il_thread` | R10 |
| M4 rete fuori dai lock | `flusso.py:752` (consegna senza lock), `:495` (risottoscrizioni DOPO il lock del gestore), `:300-314` e `:372` (connessione/autenticazione/invii su `_invio`, mai sotto `_lock`) | FL::`test_consegna_non_si_blocca_se_una_connessione_tiene_il_suo_lock` (F1), `::test_consegna_non_aspetta_il_lock_del_gestore`, `::test_rete_lenta_di_una_connessione_non_blocca_il_gestore`, `::test_nessun_deadlock_con_operazioni_concorrenti` | R11, R12 |
| M5a invii saltati | `ladder.py:474` `_ripara_se_saltati` (contatore `saltati()` = `local_channel.statistiche()` `saltati`+`saltati_client`; se cresce si ripubblica tutto, al massimo ogni `RIPARO_MIN_S` = 0,5 s) | FL::`test_invii_saltati_dal_canale_ripubblicano_tutto` | R13 |
| M5b CPU | strumento `misura_cpu_ladder.py` (numeri sotto) | - | - |
| M6 importi assenti | `flusso_ordini_conto.py:225` (None, mai 0), `:145` `OrdineDalContoEsteso.campi_assenti` (estensione proposta) | O::`test_importi_assenti_non_inventano_abbinato_ne_residuo` (R4) | R14 |
| libro_chiuso | `ladder.py:574` (chiusura sull'ULTIMO book RICEVUTO, anche se fuso nei 20 ms), `:311`, `:577` | FL::`test_chiusura_calcio_sull_ultimo_book_RICEVUTO_anche_se_fuso` | R15 |
| connectionsAvailable | SUPERATA dalla seconda revisione (par. 11, regola del coordinatore): la riserva non vale per lo stream ordini, 0 = un'attesa e poi si prova, rifiuto = backoff | (par. 11) | R16, R17 (testi nuovi) |
| sessione | `flusso_ordini_conto.py:156` `SessioneConSegnalazione`, `:449` `segnala_sessione` (usata anche da `flusso.py`) | O::`test_no_session_si_segnala_alla_sessione_senza_affidarsi_al_timer`, FL::`test_no_session_sulla_connessione_dei_prezzi_si_segnala` | R18, R23 |
| potatura | `flusso_ordini_conto.py:851` `_pota` (`TETTO_COMPLETATI` = 5000 EXECUTION_COMPLETE; gli EXECUTABLE mai), `flusso.py:716` `_pota_libri` | O::`test_potatura_dei_completati_oltre_il_tetto`, FL::`test_book_dei_mercati_non_piu_sottoscritti_escono` | R19, R20 |
| eventi del contratto | `flusso.py:508` `aggiungi_osservatore`: `mercato_chiuso`, `flusso_muto`, `capacita_cambiata` | FL::`test_eventi_mercato_chiuso_e_capacita_cambiata`, `::test_watchdog_del_flusso_muto_...` | R21, R8 |
| `converti_valuta` | tolto dal costruttore pubblico di `GestoreFlussi`: la conversione non si spegne | FL::`test_il_costruttore_non_permette_di_spegnere_la_conversione`, `::test_ogni_book_di_un_messaggio_con_piu_mercati_arriva_convertito` (X18) | X18, M28 |
| orologio monotono | `flusso_ordini_conto.py:299` `orologio_mono` per vivo/muto e watchdog | O (file di prima)::`test_vivo_latente_503_poi_muto_su_orologio_monotono` | M14 |
| mutanti sopravvissute | X2 (ripresa con un solo clk), X8 (autenticazione nello stato), X15 (connessione vuota chiusa) | O::`test_caduta_a_meta_immagine_segmentata_riparte_da_zero`, `::test_dopo_l_autenticazione_lo_stato_dice_autenticato`, FL::`test_connessione_rimasta_senza_mercati_si_chiude_non_si_sottoscrive_vuota` | X2, X8, X15 |
| bassi | guillemets tolti (`flusso.py`, `profili.py`: `grep -P '[^\x00-\x7F]'` = 0 nei file `.py`); `_OBBLIGATORI_UO` tolto; `_chiusi` ora letto (`stato()["mercati_chiusi"]`, nei due moduli) | - | - |

**Divergenza migliorativa dichiarata (A3)**: nel nuovo il backoff si AZZERA dopo una connessione sana;
`FrammentoMarketStream.run` di oggi (`Betfair/stream/frammenti_mercato.py:203-217`) non lo azzera mai (dopo qualche caduta
anche una connessione sana aspetta 60 s a ogni ripresa). Nuovo != vecchio su questo punto, di proposito; `frammenti_mercato.py`
NON toccato.

**Mutazioni**: **62 mutazioni, 62 rosse, 62 ripristinate** (sha256 prima = dopo per ognuna;
`python ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py`, esito in `falsifica_esito.jsonl`, rieseguito per intero sul codice
finale): le 34 di prima (testi aggiornati dove il codice e' cambiato: M11, M12, M13, M14, M20, M26, M28), le 23 della
revisione (R1-R23) e le 5 del revisore (X1, X2, X8, X15, X18). Durante il lavoro la prima esecuzione completa aveva 4
sopravvissute (M11, M14, R11, R12): M14 puntava a un test rinominato; M11, R11 e R12 erano coperte due volte (una correzione
copriva l'altra): aggiunti tre test mirati (`test_fullimage_di_mercato_in_una_ripresa_segnala_l_ordine_sparito`,
`test_consegna_non_aspetta_il_lock_del_gestore`, `test_rete_lenta_di_una_connessione_non_blocca_il_gestore`), ora rosse.
Del revisore: X1, X2, X8, X15 con i SUOI testi (rosse); X18 con il testo adattato (il ramo `if self._converti:` non esiste
piu': la stessa mutazione - conversione saltata sui messaggi con piu' book - sulla riga di `converti_libro`; rossa). X5 del
revisore (ms troncati invece che arrotondati) e' EQUIVALENTE: `utcfromtimestamp(pd/1e3)` arrotonda al microsecondo e l'errore
del float a 1,78e9 s e' ~0,1 us, quindi i microsecondi sono sempre multipli esatti di 1000 (cercato su 1.000 istanti
consecutivi: nessuna differenza); non c'e' un test che possa ucciderla. Il test F1 ORIGINALE del revisore
(`test_rev_ladder_flusso.py`) chiama `GestoreFlussi(..., converti_valuta=False)`: con il parametro tolto (punto basso della
revisione) solleva `TypeError`; la nostra copia (FL::`test_consegna_non_si_blocca_...`) usa un cambio fisso ed e' verde. Gli
altri 14 test originali del revisore sono verdi sul codice corretto.

**M5b - CPU del ladder** (`python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_cpu_ladder.py 1 10`; ETICHETTA CORRETTA dopo
la seconda revisione: le righe "3.000" sono sulla finestra di **3.000 messaggi** di 35797769 in gioco (`DA, A = 30000, 33000`)
= **334 s** di partita; `time.thread_time`, percentuale di UN core):

| Finestra | Partite insieme | Book | Pubblicazioni oggi / nuovo | CPU oggi (recorder + worker 200 ms) | CPU nuovo (thread del ladder, 20 ms) | Chi |
|---|---:|---:|---|---|---|---|
| 3.000 msg, 334 s | 1 | 10.286 | 8.539 / 10.093 | 3,21 s = 0,96% di un core | 3,88 s = 1,16% di un core | W1-A2 |
| 3.000 msg, 334 s | 10 | 102.860 | 85.390 / 100.930 | 68,55 s = 20,5% di un core | 46,27 s = 13,84% di un core | W1-A2 |
| 3.000 msg, 334 s | 1 | 10.286 | 8.539 / 10.093 | 2,58 s = 0,77% di un core | 3,16 s = 0,94% di un core | revisore (rieseguito) |
| 3.000 msg, 334 s | 10 | 102.860 | 85.390 / 100.930 | 62,39 s = 18,66% di un core | 40,11 s = 12,0% di un core | revisore (rieseguito) |
| 15.000 msg, 1.685 s | 1 | 54.149 | 44.623 / 53.406 | 21,23 s = 1,26% di un core | 23,78 s = 1,41% di un core | revisore |

Una mia prima esecuzione su 15.000 messaggi (1.685 s) aveva dato per UNA partita 1,38% oggi / 1,55% nuovo; quella da 10
copie su 15.000 messaggi e' stata fermata al limite di tempo della macchina (macchina condivisa: i numeri variano di
qualche decimo fra esecuzioni). **Cosa misura lo strumento**: la CPU del THREAD dentro le funzioni avvolte (recorder,
worker, ladder e la serializzazione JSON del canale), NON quella del processo (niente socket, listener di flumine, GIL
conteso dagli altri thread). La misura vera e' quella in OMBRA (Salute, CPU del processo runner). Il codice del ladder e'
cambiato dopo queste misure (seconda revisione: riprova del meta a intervalli doppi, riparo che si rilegge, log raro): i
cambi toccano solo i casi senza meta, con errore o con invii saltati, assenti nella registrazione; non rimisurato.
Lettura: per partita il nuovo costa circa quanto oggi (~1,2-1,6% di un core) perche' serializza solo i book che pubblica
mentre oggi il recorder li serializza TUTTI; con 10 partite il nuovo e' sotto oggi (il worker di oggi rigira ogni 200 ms
tutti i mercati del catalogo). In OMBRA i due costi si SOMMANO (34% di un core a 10 partite): e' il dato da guardare.

**M5c - proposta (NON applicata)**: l'intervallo minimo resta un parametro (`LadderEvento(intervallo_min_ms=...)`, di serie
20 ms come chiesto). Nella fase OMBRA il publisher vero resta quello di oggi a 200 ms: nessun default cambiato. Proposta per
l'aggancio: una variabile `LIVE_LADDER_EVENTO_MIN_MS` (di serie 20), letta dal profilo del ladder, da alzare a 50-100 ms se in
ombra la CPU del thread del ladder supera il 5% di un core o il canale salta invii (`ripari` > 0). Decisione dell'utente.

**K1 (guardia della valuta)**: le due righe da aggiungere all'integrazione in
`Betfair/stream/tests/test_valuta_k1_2026_09_26.py` (NON toccato):
```
_FONTI_CONVERTITE["Betfair/nucleo/betfair/flusso.py"] = "converti_libro("
_FONTI_ESENTI["Betfair/nucleo/betfair/flusso_ordini_conto.py"] = "stream ORDINI: importi gia' nella valuta del conto (EUR), nessun book"
```
Con `converti_valuta` tolto dal costruttore, `flusso.py` ha UNA sola strada (converte sempre): la guardia la vede tutta.

**Estensioni proposte del contratto** (contratto non toccato): `OrdineDalContoEsteso` (sottoclasse di `OrdineDalConto`) con
`campi_assenti: Tuple[str, ...]` e `confermato: bool`; `prezzo`, `importo`, `abbinato`, `residuo`, `scaduto`, `annullato`,
`annullato_da_betfair` come `Optional[float]` (oggi passano None quando Betfair non li manda); `SessioneConSegnalazione` con
`segnala_sessione_morta(motivo)` (da allineare con W1-A1 all'integrazione); `FlussoMercato.aggiungi_osservatore(cb)` per gli
eventi `mercato_chiuso`, `flusso_muto`, `capacita_cambiata`; `FlussoOrdiniConto` costruito con `disponibili` (lettore di
`connectionsAvailable` del processo, es. `GestoreFlussi._disponibili`); `riserva_connessioni` TOLTO nella seconda revisione
(la riserva non vale per lo stream ordini). **Per il comparto C**: gli importi di `OrdineDalContoEsteso` (`prezzo`,
`importo`, `abbinato`, `residuo`, `scaduto`, `annullato`, `annullato_da_betfair`, `prezzo_medio`) possono essere **None**
quando Betfair non li manda (BSP prima della riconciliazione, ordini del sito senza importi): il libro ordini e il P&L
devono trattarli come ASSENTI (mai 0) e guardare `campi_assenti`.

**Eventi**: `mercato_chiuso`, `flusso_muto`, `capacita_cambiata` implementati nel gestore dei prezzi. `sessione_rifatta` e
`book_aggiornato` ⊘: il primo e' della sessione (W1-A1), il secondo e' gia' il consumatore (`aggiungi_consumatore`).
`ordine_dal_conto` = consumatori di `FlussoOrdiniConto`.

**Numeri dopo la correzione** (rieseguiti di persona sul codice finale):
- test del comparto: 138 (`python -m pytest Betfair/nucleo/betfair/tests/ -q -p no:cacheprovider`); i 133 veloci verdi in 43 s
  (`-k "not ogni_book and not sequenza and not cadenza"` toglie anche `test_ogni_book_di_un_messaggio...`, verde nella suite);
- parita' di serie (5 test sulle registrazioni: payload e firma su ogni book di 35760084 e 1 su 7 di 35797769, sequenza del
  topic calcio e tennis, cadenza 20/200 ms): VERDI dopo le correzioni del ladder (prima in un giro dedicato, 1 rosso di
  `test_a2_flusso.py` dovuto al watchdog con l'orologio finto, corretto; poi nella suite finale);
- suite intera (UNA volta, alla fine): **11.730 verdi, 1 rosso, 65 saltati, 6 xfail** in 809 s; l'unico rosso e' la guardia K1
  (`test_valuta_k1_2026_09_26.py::test_contratto_ogni_fonte_di_book_dello_stream_e_convertita`), da sbloccare con le due righe
  sopra all'integrazione.

## 11. Seconda revisione (09/10, revisione di 91a19377: DA CORREGGERE, 10 punti)

Commit nuovo sopra 91a19377 (storia non riscritta, nessun push). Nessun file esistente toccato. Righe sul codice finale.

| Punto | Correzione (file:riga) | Test (file::nome) | Mutazioni rosse |
|---|---|---|---|
| 1. A3-1 tempesta | il backoff si azzera SOLO se la connessione caduta era su da oltre `VIVA_DOPO_S` = 60 s dalla sottoscrizione ("ha ricevuto dati" non basta): `flusso_ordini_conto.py:697` `_connessione_sana`, `:723`; `flusso.py:385` `_sana`, `:407`; attese `attesa_di_backoff` `flusso_ordini_conto.py:183` (2, 4, ... 60 s, valori di serie invariati; ora scalabili nei test), ultime attese nello stato | O::`test_backoff_si_azzera_solo_dopo_una_connessione_rimasta_su` (5 casi: immagine e chiusura subito, niente, 59 s, 61 s con e senza dati), `::test_tempesta_vera_immagine_e_chiusura_le_attese_crescono` (server TLS: immagine e chiusura a ogni giro, attese 0,05/0,1/0,2/0,4/0,4); FL::`test_backoff_della_connessione_si_azzera_solo_se_rimasta_su`, `::test_tempesta_vera_prezzi_immagine_e_chiusura_le_attese_crescono` | R5, R6, Y4, Y5, Z3, Z3b, Z4, Z4b, Z17 |
| 2. A3-2 watchdog | la durata si valuta PRIMA di azzerare il riferimento: `flusso_ordini_conto.py:850` (in `_veglia` `:833`, un giro del watchdog ora e' un metodo); `flusso.py:691` (`veglia`) | O::`test_watchdog_su_una_connessione_su_da_ore_non_raddoppia_il_backoff` (su da 1 h poi muta: 2 s a ogni ripresa; muta da subito: cresce), FL::idem | Z1, Z2 |
| 3. SLOT (decisione del coordinatore) | `flusso_ordini_conto.py:738` `_slot_libero`: la riserva NON vale per lo stream ordini (UNA connessione); apre con libere >= 1 o valore ignoto; con 0 aspetta `ATTESA_SLOT_S` = 30 s UNA volta e poi prova comunque (`:747`): mai in attesa per sempre; `:813` `MAX_CONNECTION_LIMIT_EXCEEDED` = backoff (tolti `PAUSA_SLOT_NEGATO_S` e `riserva_connessioni`); `:800` dopo ogni SUA autenticazione il valore vero va in `stato()["connessioni_libere_note"]` | O::`test_con_una_connessione_libera_o_valore_ignoto_lo_stream_ordini_apre[1/5/None]`, `::test_con_zero_libere_aspetta_poi_ritenta_mai_in_attesa_per_sempre` (valore fermo a 0: un'attesa, poi apre; autenticazione con 7 libere -> 7), `::test_rifiuto_di_betfair_ritenta_con_il_backoff_e_poi_apre` (3 rifiuti: attese 0,05/0,1/0,2, alla 4a apre) | R16, R17, Y16, Z5, Z6 |
| 4. N1 | `flusso.py:318` `risottoscrivi`: un errore di rete NON arriva a chi chiama (`:346`), lo stream si chiude e la connessione riparte da immagine PIENA con l'insieme nuovo (`_abbandona` `:356`, `_forza_immagine`); in piu' (prova S9 del revisore) se la libreria ricollega lo stream fermato DENTRO l'invio (`BetfairStream._send`: socket nuovo nel thread di chi chiama, che nessuno legge, budget 10) il socket si chiude (`:350`); una risottoscrizione di un piano piu' vecchio non vince (`:333`, generazione del piano) | FL::`test_risottoscrizione_fallita_non_solleva_e_riparte_da_immagine_piena` (stream VERO con RST all'invio: nessuna eccezione, ultima sottoscrizione = insieme intero senza clk, book dei mercati nuovi), `::test_stream_ricollegato_dentro_l_invio_si_chiude_nessuna_connessione_orfana` (nessun `BetfairStream` aperto oltre a quello della connessione), `::test_risottoscrizione_di_un_piano_vecchio_non_vince_su_quella_nuova` | Z7, Z8, Z9, Z12, M20 |
| 5. N2 | `flusso.py:562` (insieme coperto = insieme PIANIFICATO, aggiornato prima della rete; `_aggiorna_coperti` `:789`, anche a ogni apertura/chiusura), `:850` (`_consegna`: un book di un mercato fuori non si scrive ne' si consegna, `conti["book_fuori_insieme"]`; `_libri` sotto un lock suo, mai tenuto in rete o nei callback) | FL::`test_book_in_volo_di_un_mercato_tolto_non_si_scrive_ne_si_consegna`, `::test_book_dei_mercati_non_piu_sottoscritti_escono` | Z10, Z11, R20 |
| 6. M2 log | `ladder.py:586`: una riga per mercato al massimo ogni `LOG_ERRORE_OGNI_S` = 60 s (`Betfair/stream/flusso_prezzi.Promemoria`, riusata: `dovuto(chiave, adesso_s)`), con il totale degli errori; la riprova resta a ogni giro | FL::`test_errore_di_pubblicazione_permanente_una_riga_al_minuto_per_mercato` (290 giri in 58 s: 1 riga; dopo 60 s: 2) | Z16 |
| 7. M3 meta | `ladder.py:567` senza book e senza meta: nessuna riprova (aspetta il push); `:569` con book e senza meta: 0,2 s poi intervalli doppi fino a `RIPROVA_META_MAX_S` = 5 s; `:337` un book nuovo (o `push_a_ogni_cambio` di chi impara il meta) fa riprovare subito | FL::`test_senza_meta_e_senza_book_non_si_riprova_finche_non_arriva_un_push` (Y10), `::test_senza_meta_con_book_si_riprova_a_intervalli_crescenti_e_un_book_nuovo_riparte` | Y10, R10, Z14, Z15 |
| 8. M5 riparo | `ladder.py:503` `_ripara_se_saltati` + `:392`: il contatore dei saltati si rilegge DOPO la ripubblicazione del riparo (finche' i mercati marcati non sono usciti non si rilegge): i salti che il riparo stesso provoca a un client lento non lo fanno ripartire | FL::`test_riparo_non_si_autoalimenta_con_un_client_lento` (ogni invio saltato, nessun book nuovo: 1 riparo, poi niente) | Z13, Y13, R13 |
| 9a. A1 (Y1) | `flusso_ordini_conto.py:900` (solo gli EXECUTABLE diventano non confermati) | O::`test_eseguito_noto_resta_confermato_dopo_una_ripartenza_da_zero` | Y1 |
| 9b. M1 soglia (Y8) | soglia 3 heartbeat, numero SCRITTO nel test (3 x 5 s): a 14,99 s non chiude, a 15,01 s chiude | O::`test_watchdog_ordini_soglia_di_3_heartbeat_contati_dalla_sottoscrizione` | Y8, R7 |
| 9c. Y6/Y7 | NON equivalenti: il test mette l'ultimo battito della connessione PRECEDENTE 60 s prima della sottoscrizione; contando da li' il watchdog chiuderebbe una connessione appena sottoscritta | O::idem (Y6), FL::`test_watchdog_prezzi_soglia_di_3_heartbeat_contati_dalla_sottoscrizione` (Y7) | Y6, Y7 |

**DIVERGENZA da confermare con l'utente (punto 3, regola decisa dal coordinatore)**: lo stream ordini del conto non
lascia la riserva agli altri processi (oggi il calcio la lascia per scanner/scalper/tennis, `frammenti_mercato.py:91`): con
1 connessione libera la prende; con 0 dichiarate prova lo stesso dopo 30 s (Betfair rifiuta senza togliere lo slot a
nessuno, poi backoff fino a 60 s). Effetto possibile: nel caso peggiore di oggi (10/10, referto 8.1) lo stream ordini
prende l'ultima connessione libera prima di un frammento del calcio o di uno shard dello scanner, che allora vedono
`MAX_CONNECTION_LIMIT_EXCEEDED` e ripiegano (pausa 300 s del calcio, REST dello scanner). Le opzioni del par. 8.1 restano.

**Mutazioni**: **97 mutazioni, 97 rosse, 97 ripristinate** (sha256 prima = dopo per ognuna;
`python ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py`, esito in `falsifica_esito.jsonl`, rieseguito per intero sul codice
finale). Aggiunte: le 16 del revisore (`mut.py` Y1-Y16; testi adeguati dove il punto e' cambiato: Y4, Y5, Y6 (rientro), Y8,
Y10, Y11 = R12, Y13, Y16 sulla regola nuova "con 1 libera NON apre") e 19 nuove (Z1-Z17,
con Z3b/Z4b che provano da SOLA la tempesta sul server TLS); aggiornati i testi di M20, R5, R6, R7, R10, R12, R13, R16, R17,
R20 (codice cambiato). Il programma ora legge e scrive i file senza tradurre i fine riga (`newline=""`: su Windows il
ripristino sarebbe stato in CRLF; lo sha256 lo avrebbe detto).

**Numeri** (rieseguiti di persona sul codice finale):
- test del comparto: 164, tutti verdi (erano 138: i 6 test che fissavano le regole vecchie di backoff e slot riscritti sulle nuove, piu' i test nuovi della tabella; i veloci in ~3 min su macchina carica perche' i test sul server TLS aspettano backoff reali);
- parita' di serie: VERDI nella suite finale (`test_payload_e_firma_identici_su_ogni_book[35760084]` e `[35797769]` 1 su 7, `test_sequenza_del_topic_identica_al_worker_di_oggi[calcio]` e `[tennis]`, `test_cadenza_20ms_contro_200ms_su_registrazione`; rapporto junit letto riga per riga);
- suite intera (UNA volta, alla fine): **11.756 verdi, 1 rosso, 65 saltati, 6 xfail** in 639 s; l'unico rosso e' ancora la guardia K1 (`test_valuta_k1_2026_09_26.py::test_contratto_ogni_fonte_di_book_dello_stream_e_convertita`), da sbloccare con le due righe del par. 10 all'integrazione.
