# A2 - Flussi e ladder (comparto A, W1-A2, ondata 1, 09/10/2026)

Schema del `COSA_FA.md` (`04_ARCHITETTURA_OBIETTIVO.md` par. 2.4). Quattro moduli nuovi in
`Betfair/nucleo/betfair/`: `flusso_ordini_conto.py`, `ladder.py`, `profili.py`, `flusso.py`.
Nessun file di oggi e' cambiato: l'aggancio e' dell'ondata 2 (referto `ARCHITETTURA_2026-10/ondata1/W1-A2/REFERTO.md` par. 8).

## 1. Scopo

- `flusso_ordini_conto.FlussoOrdiniContoBetfair` (`contratto.FlussoOrdiniConto`): lo stream degli ordini del CONTO,
  senza filtro di strategia, in sola lettura, con ripresa `initialClk`/`clk`: ogni ordine (app, bot, sito) in tempo reale.
- `ladder.LadderEvento` (`contratto.Ladder`): il ladder della UI pubblicato a OGNI cambio del book (coalescenza minima
  20 ms per mercato) invece del giro fisso di 200 ms, con lo STESSO JSON del topic `ladder` di oggi; il DB in un thread suo.
- `profili`: i quattro `ProfiloFlusso` (runner calcio, runner tennis, scanner, sessione scalper) con i valori ESATTI di oggi.
- `flusso.GestoreFlussi` (`contratto.FlussoMercato`): gli stream dei prezzi per profilo: suddivisione in connessioni,
  sottoscrizione sostitutiva, budget delle connessioni, ripresa, salute, consumatori; registro delle richieste di piu'
  consumatori sugli stessi mercati (UNIONE, mai connessioni doppie: decisioni 8 e 13 dell'utente, par. 15).

## 2. Entrate

| Modulo | Entrate |
|---|---|
| `flusso_ordini_conto` | `contratto.Sessione` (`client()` = `betfairlightweight.APIClient` con sessione valida; `rinnova_se_serve()`); messaggi `ocm` dal socket Betfair |
| `ladder` | `MarketBook` della libreria (`consumatore(book)` o `sorgente(market_id)`), `push_a_ogni_cambio(market_id)`, `meta(market_id) -> MetaLadder | None`, `canale_attivo()` |
| `profili` | nome del profilo, ambiente (`os.environ` di serie, letto alla chiamata) |
| `flusso` | `contratto.Sessione`, `ProfiloFlusso`, `imposta_mercati(ids)`, `richiedi_mercati(chi, ids)`/`rilascia_mercati(chi)`, `manutenzione()`; messaggi `mcm`/`status` dal socket |

## 3. Uscite

| Modulo | Uscite |
|---|---|
| `flusso_ordini_conto` | `OrdineDalConto` ai consumatori (thread di consegna; filtro per mercato), `ordini(market_id)`, `posizioni(market_id)` (`mb`/`ml` del conto), `ordini_non_confermati()`, `stato()` (vivo/muto/assente, clk, riconnessioni, eta' ultimo messaggio e ultimo ordine, `sottoscrizione` ripresa_clk|da_zero, `seme_rest_necessario`, `ordini_scartati`) |
| `ladder` | `pubblica("ladder", riga)` (riga = `{event_id, market_id, market_type, market_name, status, ladder:{updated_ms, selections}}`), `scrivi_db(riga)` a `db_sec` write-on-change, `snapshot(market_id)`, `stato()` |
| `profili` | `ProfiloFlusso`, `filtro_dati(profilo)` (il `marketDataFilter` di betfairlightweight) |
| `flusso` | `MarketBook` GIA' in EUR (`valuta.converti_libro`, K1) ai consumatori, `book(id)`, `stato()` (stesse chiavi di `GestoreFrammenti.stato()` + `profilo`, `battito_eta_s`), `stato_flusso(id)` in `vivo|muto|assente`, `capacita()` |

## 4. Dipendenze ammesse (04 par. 2.3)

- betfairlightweight (solo qui, nel comparto A): `APIClient.streaming.create_stream`, `StreamListener`, `OrderStream`,
  `UnmatchedOrder`, enum `Streaming*`, `filters`.
- Funzioni pure di oggi IMPORTATE (riuso, mai copia): `Betfair/stream/recorder.serialize_book`,
  `Betfair/stream/ladder_canale.StatoLadder.versione` e `updated_ms_del_book`, `Betfair/stream/stream_muto.stato_da_battiti`
  (+ costanti `BATTITI_PER_SOGLIA`, `HEARTBEAT_MS_RICHIESTO`), `Betfair/stream/valuta.converti_libro` e `valuta.CAMBIO` (K1).
- Riscritte con test di parita' (pezzi di file grandi legati a flumine): helper del ladder di `runner.py`/`tennis_runner.py`,
  `frammenti_mercato.pianifica` e `GestoreFrammenti.massimo_adesso`.
- Nessun import di bot, di Supabase, di flumine (salvo `recorder.py` che importa flumine per la sua classe; la funzione
  usata e' pura).

## 5. Funzionalita' coperte (`01_FUNZIONALITA.md`) e test che le provano

| Id | Cosa | Test |
|---|---|---|
| A-052 | helper del ladder (livelli, WOM, selezione, firma SHA-1, payload), calcio e gemelli tennis | `test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book`, `::test_casi_limite_identici_alle_due_copie_di_oggi`, `::test_firma_indipendente_dall_ordine_dei_runner` |
| A-053, A-069 | `ladder_worker` calcio e tennis: canale + DB, firme separate, stato nella firma, giro a costo zero senza client | `test_a2_ladder_parita.py::test_sequenza_del_topic_identica_al_worker_di_oggi[calcio|tennis]`, `test_a2_ladder.py::test_canale_senza_client_*`, `::test_db_nel_suo_thread_*`, `::test_thread_vero_*` |
| A-054 | `updated_ms` strettamente crescente, stesso payload a parita' di firma (riuso di `StatoLadder.versione`) | `test_sequenza_del_topic_*` (controllo per mercato), `test_a2_ladder.py::test_book_invariato_*` |
| A-046 (parte ladder) | chiusura: calcio marca CLOSED l'ultimo book, tennis serializza il book chiuso | `test_a2_ladder.py::test_chiusura_come_oggi_per_sport`, `::test_calcio_senza_book_prima_della_chiusura_non_pubblica`, `test_sequenza_*` (21 mercati CLOSED) |
| A-062 (stream) | parametri di stream in `config_stream.py` e gemelli | `test_a2_profili.py` (3 ambienti in processo a parte) |
| A-029, A-030 | gestore delle connessioni, piano puro (un mercato non cambia connessione) | `test_a2_flusso_piano.py::test_piano_identico_a_frammenti_mercato_su_griglie`, `test_a2_flusso.py::test_suddivisione_180_*` |
| A-031 | battito per connessione, `heartbeatMs` e `connectionsAvailable` (anche 0) | `test_a2_flusso_piano.py::test_budget_identico_a_gestore_frammenti`, `::test_vince_l_ultimo_connections_available_letto`, `test_a2_flusso.py::test_riserva_e_connections_available` |
| A-032 | riconnessione con `initialClk/clk`, mai dopo la chiusura | `test_a2_flusso.py::test_ripresa_con_initial_clk_e_clk_dopo_la_caduta`, `::test_cambio_di_mercati_a_connessione_giu_*`, `::test_ferma_chiude_tutto_*` |
| A-033 | connessione muta > 180 s chiusa e mercati ripiazzati; rifiuto e pausa 300 s | `test_a2_flusso.py::test_manutenzione_chiude_la_connessione_muta_e_ripiazza`, `::test_rifiuto_di_betfair_*` |
| A-034 | sottoscrizione a caldo sostitutiva sulla stessa connessione | `test_a2_flusso.py::test_suddivisione_180_e_risottoscrizione_solo_della_connessione_che_cambia` |
| A-077 (parte stream) | salute per mercato, 503 = latente | `test_a2_flusso.py::test_salute_vivo_muto_assente_e_503` |
| T11 (nuova, priorita' dell'utente) | stream ordini del conto senza filtro, sola lettura, anche ordini del sito senza `rfo`/`rfs` (esempio ufficiale), BSP, partenza da zero dichiarata | `test_a2_flusso_ordini_conto.py` (22 test) |
| K1 (valuta) | size dello stream GBP -> EUR alla fonte | `test_a2_flusso.py::test_size_dello_stream_convertite_gbp_eur_alla_fonte` |

Restano al codice di oggi (ondata 2 o tappe successive): A-020..A-028, A-035..A-045 (follow, catalogo, ciclo di vita del
runner, framework flumine), A-047..A-051 (tee raw: P5), A-055..A-061 (live_now, board, canali), A-063..A-068, A-070..A-075
(tennis), A-076 (piano a shard `id mod N` dello scanner: vedi referto par. 9, D2), A-078..A-086.

## 6. Interruttore previsto

`ARCH_LADDER=vecchio|ombra|nuovo` (T6); `ARCH_FLUSSO_<SPORT>=vecchio|nuovo` (T19, l'ombra e' sul banco);
`ARCH_ORDINI_CONTO=spento|ombra|acceso` (proposto, T11). Di serie: vecchio / spento.

## 7. Come si sostituisce

Un modulo nuovo che implementa lo stesso protocollo di `contratto.py` e fa passare `tests/test_a2_*.py` (i test di parita'
importano il codice di oggi: restano validi finche' il vecchio esiste; al taglio diventano test d'oro sui valori registrati).

## 8. Come si prova da solo

```
python -m pytest Betfair/nucleo/betfair/tests/ -q -p no:cacheprovider -k a2
python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py          # misura della cadenza
```
Finti: un server della Exchange Stream API su 127.0.0.1 in TLS (`tests/test_a2_finti.py`), con i messaggi e le chiavi
dello schema ufficiale; dalla parte nostra TUTTA la libreria vera (`BetfairStream`, listener, cache). `APIClient` vero con
token a mano; le chiamate di scommessa sono trappole. Book: registrazioni vere `registrazioni_banco/35760084`, `35797769`.

## 9. Misure

`ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py` (tempo della registrazione, `pt`): pubblicazioni e attesa
"arrivo del book -> pubblicazione" del ladder nuovo (20 ms) contro il worker di oggi (200 ms). Numeri nel referto par. 4.
Dal vivo: la sonda `ladder_pub_pt_ms` della Salute (T0A), in ombra.
`ARCHITETTURA_2026-10/ondata1/W1-A2/misura_cpu_ladder.py`: CPU del thread del ladder nuovo contro recorder +
worker di oggi, con N partite contemporanee (copie della registrazione 35797769). Numeri nel referto par. 10.

## 10. Voci di `PROCESSO_STANDARD_BOT.md`

Sollecitate: par. 6.1 (stream nativo `mcm` letto dal listener vero, stati OPEN/SUSPENDED/CLOSED), 6.5 (la riga del
ladder che la UI legge, stesse chiavi), 6.6 (connessioni e limiti Betfair), 6.7 (scenari di caduta, 503, rifiuto,
falsificazione), 6.8 (comandi esatti, versioni), par. 7 n. 9, 17 (sospeso/chiuso nel ladder), 19 (stato perso alla
caduta: ripresa con clk), 20 (battito vivo != dati: `vivo` per mercato solo con un book), 27 (finti con le chiavi vere),
29, 30, 33, 35. ⊘ con causa nel referto par. 7.


## 11. Dopo la revisione indipendente (09/10)

Correzioni (dettaglio, file:riga, test e mutazioni nel referto par. 10):

- **Ordini non confermati**: a fine immagine di SOTTOSCRIZIONE (`SUB_IMAGE` intera o `SEG_END`, anche vuota), di
  MERCATO o di RUNNER, ogni EXECUTABLE noto non riportato passa a `confermato=False` (riconsegnato ai consumatori) e in
  `ordini_non_confermati()`; torna confermato alla prima notizia dallo stream.
- **Posizioni**: una `fullImage` di mercato SOSTITUISCE le posizioni del mercato (base del P&L del comparto C).
- **Importi assenti**: None (mai 0) e dichiarati in `OrdineDalContoEsteso.campi_assenti`.
- **Backoff** azzerato dopo una connessione sana, nei due moduli: DIVERGENZA MIGLIORATIVA dichiarata rispetto a
  `frammenti_mercato.py` di oggi (che non lo azzera mai). "Sana" ristretta dalla seconda revisione (par. 12).
- **Watchdog** nei due moduli: connessione su senza NESSUN messaggio oltre 3 heartbeat (`BATTITI_WATCHDOG`, la soglia
  del "muto" dell'app; Betfair dice 2 = "forse disconnesso") -> socket chiuso, ripresa con `initialClk`/`clk`; evento
  `flusso_muto` nel gestore dei prezzi.
- **Ladder**: un errore di pubblicazione o di `marca_canale` rimette il SOLO mercato in attesa (gli altri del lotto
  escono); meta assente = attesa con riprova ogni `RIPROVA_META_S` (0,2 s, nessun giro a vuoto); invii SALTATI dal canale
  (`saltati`, contatore di `local_channel.statistiche()`) = ripubblicazione di tutti i mercati al massimo ogni
  `RIPARO_MIN_S` (0,5 s); la chiusura del calcio marca l'ULTIMO book ricevuto (anche se fuso), come il recorder di oggi.
- **Concorrenza del gestore**: nessuna rete sotto i lock della consegna (consumatori letti da una lista sostituita per
  intero; risottoscrizioni fuori dal lock del gestore; connessione e autenticazione fuori dal lock della connessione).
- **Eventi** del contratto nel gestore dei prezzi: `aggiungi_osservatore(cb)` con `mercato_chiuso`, `flusso_muto`,
  `capacita_cambiata`.
- **Slot di connessione** (stream ordini): regola SOSTITUITA dalla seconda revisione (par. 12).
- **Sessione**: `SessioneConSegnalazione.segnala_sessione_morta(motivo)` (estensione proposta) se c'e', altrimenti
  `rinnova_se_serve()`; nei due moduli.
- **Potatura**: ordini EXECUTION_COMPLETE oltre `TETTO_COMPLETATI` (5000); book dei mercati non piu' sottoscritti.
- **Valuta**: la conversione GBP->EUR del gestore non si spegne piu' dal costruttore (`converti_valuta` tolto).
- Orologio MONOTONO per vivo/muto dello stream ordini; ASCII; codice morto tolto.

Test nuovi: `tests/test_a2_ordini_revisione.py`, `tests/test_a2_flusso_ladder_revisione.py`.

## 12. Dopo la seconda revisione (09/10)

Correzioni (dettaglio, file:riga, test e mutazioni nel referto par. 11):

- **Backoff** (A3-1): si azzera SOLO se la connessione caduta era rimasta su oltre `VIVA_DOPO_S` (60 s) dalla
  sottoscrizione; "ha ricevuto dati" non basta piu' (un server che manda l'immagine e chiude a ogni giro faceva una
  tempesta di riconnessioni). Attese 2, 4, 8, ... 60 s (`attesa_di_backoff`), le ultime in `stato()["ultime_attese_s"]`
  (stream ordini) e `stato()["frammenti"][i]["ultime_attese_s"]` (gestore dei prezzi).
- **Watchdog** (A3-2): la durata della connessione si valuta PRIMA di azzerare il riferimento della sottoscrizione: una
  connessione su da ore che diventa muta riparte dal backoff minimo. Un giro del watchdog e' un metodo (`_veglia`,
  `veglia`) provato con l'orologio finto: soglia 3 heartbeat contata dalla sottoscrizione.
- **Slot dello stream ordini** (decisione del coordinatore, DIVERGENZA da confermare con l'utente): UNA connessione, la
  riserva NON vale per lui. Apre con libere >= 1 o valore ignoto; con 0 aspetta `ATTESA_SLOT_S` (30 s) UNA volta e poi
  prova comunque (mai "in attesa" per sempre); `MAX_CONNECTION_LIMIT_EXCEEDED` = nuovo tentativo con il backoff (non piu'
  300 s fissi). Dopo ogni SUA autenticazione il valore vero (`connectionsAvailable`) va in `connessioni_libere_note`.
- **Risottoscrizione** (N1): `imposta_mercati` non solleva MAI per un errore di rete; la connessione si chiude e riparte
  da immagine PIENA con l'insieme nuovo. Se la libreria ricollega lo stream fermato DENTRO l'invio
  (`BetfairStream._send`), quel socket orfano si chiude (`conti["connessioni_orfane_chiuse"]`). Una risottoscrizione di un
  piano piu' vecchio non vince su quella nuova (generazione del piano).
- **Book** (N2): `book()` e i consumatori vedono solo i mercati dell'insieme PIANIFICATO; un book in volo di un mercato
  tolto non si scrive ne' si consegna (`conti["book_fuori_insieme"]`).
- **Ladder**: un mercato che fallisce sempre si logga al massimo una volta al minuto (`flusso_prezzi.Promemoria`, M2);
  senza book e senza meta non si riprova (aspetta il push), con book e senza meta si riprova a 0,2 s e poi a intervalli
  doppi fino a 5 s, e un book nuovo fa riprovare subito (M3); dopo un riparo il contatore dei saltati si rilegge a
  ripubblicazione finita, cosi' un client lento non tiene il riparo in un ciclo (M5).

## 13. Dopo la terza revisione (09/10)

- **Durata del collegamento** (gestore dei prezzi): conta da `connessa_dal_mono`, impostato UNA volta per collegamento;
  le risottoscrizioni (auto-follow in gioco) e il watchdog non la toccano. `sottoscritta_mono` resta il riferimento del
  watchdog dei messaggi.
- **Mai clk con un filtro diverso**: la ripresa decisa prima del collegamento vale solo se i mercati non sono cambiati;
  insieme e decisione si leggono nello stesso lock dentro `_sottoscrivi`.
- **Slot dello stream ordini**: vince il valore PIU' RECENTE fra la nostra ultima autenticazione (+1: la nostra connessione
  e' giu') e `disponibili()` (meglio `GestoreFlussi.disponibili_con_istante`): dopo una caduta le riprese non pagano piu'
  l'attesa di slot per un valore vecchio.
- **Connessioni**: lo stream ordini del conto e' una connessione in piu'; proposta di sostituire con lui gli stream ordini
  di flumine all'aggancio (referto par. 12.1).

## 14. Decisione 12 dell'utente: cadenza di serie del ladder 20 ms (10/10/2026)

**«Massima velocita'» del ladder.** Verificato (agente D-A): la cadenza DI SERIE del ladder nuovo verso la UI e' 20 ms per
mercato ovunque nel comparto: `ladder.INTERVALLO_MIN_MS = 20` (`ladder.py:54`), default del costruttore
`LadderEvento(intervallo_min_ms=INTERVALLO_MIN_MS)` (`ladder.py:276`), `stato()["intervallo_min_ms"]` = 20, questo doc
(par. 1 e 9). `ProfiloLadder` NON ha un campo di cadenza della UI (solo profondita', livelli, WOM, `db_sec`, chiusura): le
variabili del worker di oggi che la tengono a 200 ms (`LIVE_LADDER_CANALE_MS`, `TENNIS_LADDER_CANALE_MS`,
`Betfair/stream/config_stream.py:74`) il ladder nuovo NON le legge. Nessuna costante o profilo da portare a 20: non c'era
un 200 di serie da cambiare. La cadenza del DB (`*_LADDER_PUBLISH_SEC`, 2 s, `profilo_ladder`) resta com'e'.

- `CONTROLLO_CANALE_S = 0.2` (`ladder.py:57`) NON e' una cadenza del ladder: e' il risveglio del thread quando non arriva
  nessun book, per accorgersi che il canale e' tornato ad avere client. Con i book che arrivano il thread si sveglia a ogni
  push (`push_a_ogni_cambio` -> `notify`) e il client nuovo e' visto al book successivo; solo su un mercato FERMO il primo
  fotogramma a un client appena collegato puo' tardare fino a 200 ms. Lasciato com'e' (portarlo a 20 ms = 50 risvegli al
  secondo a vuoto per sempre); se l'utente vuole anche questo caso a 20 ms, basta cambiare la costante.
- Test: `tests/test_a2_ladder_cadenza.py` (7): 20 ms scritto LETTERALMENTE nel test (non letto dal modulo): costante,
  default del costruttore, ladder costruito di serie per calcio e tennis anche con `LIVE_LADDER_CANALE_MS=200` e
  `TENNIS_LADDER_CANALE_MS=200` nell'ambiente vero del processo, `db_sec` = 2,0, nessun campo di cadenza nel profilo, e il
  comportamento sull'orologio finto (cambi a 25 ms: due pubblicazioni subito; a 10 ms: la seconda alla scadenza dei 20).
- Mutazioni (in `ondata1/W1-A2/falsifica.py`): C1 (costante a 200), C2 (default del costruttore a 200), C3 (la variabile di
  oggi a 200 riporta la cadenza), C4 (coalescenza fissa a 200 ms), C5 (DB trascinato alla velocita' del ladder): 5/5 rosse.
- In ombra si misura la CPU vera del processo (decisione 12): `misura_cpu_ladder.py` resta lo strumento di laboratorio.

## 15. Gestore unico dell'app (decisione 10/10)

**Decisioni 8 e 13 dell'utente (10/10/2026)**: lo stream ovunque possibile, la REST solo di riserva; UN gestore dei flussi
per tutta l'app (200 mercati per connessione) e UNO stream ordini; i servizi non aprono piu' stream propri; lo stream ordini
del conto SOSTITUISCE quelli che flumine apre in ogni processo, mai aggiunto.

**Capacita' aggiunta (agente D-A) a `flusso.GestoreFlussi`: il registro delle richieste.** Prima il gestore aveva UN solo
insieme (`imposta_mercati`, sostitutivo): due consumatori che lo chiamavano si cancellavano i mercati a vicenda. Ora:

- `richiedi_mercati(chi, mercati)`: il consumatore `chi` (bot, ladder, scanner, ...) dichiara il SUO insieme intero
  (sostituisce la sua richiesta precedente; vuoto = rilascia). Il gestore sottoscrive l'UNIONE: un mercato chiesto da tre
  consumatori occupa UN posto su UNA connessione. Ritorna i mercati di `chi` rimasti fuori (capacita' o budget).
- `rilascia_mercati(chi)`; `richieste()`; senza richieste le connessioni si chiudono (mai una sottoscrizione vuota).
- `aggiungi_consumatore(cb, richiesta=chi)`: il consumatore riceve i book dei mercati della sua richiesta e la segue quando
  cambia (estensione additiva: `mercati=` resta il filtro fisso; i due insieme = `ValueError`).
- `imposta_mercati(mercati)` (il contratto) e' la richiesta del consumatore `RICHIESTA_DIRETTA`: senza altre richieste il
  risultato e' IDENTICO a prima (tutti i test di prima verdi; le 42 mutazioni di prima su `flusso.py` rilanciate: 42
  rosse); con altre richieste NON toglie i loro mercati.
- `stato()`: `richieste` (consumatore -> quanti mercati), `mercati_richiesti_somma`, `mercati_unione` (il risparmio).
- Concorrenza: il registro si aggiorna sotto `_lock` e l'unione si legge DENTRO il lucchetto del piano
  (`_applica_richieste`): l'ultimo piano vede tutte le richieste arrivate prima; la rete resta fuori dal lucchetto e una
  risottoscrizione di un piano vecchio non vince (generazione di `_Connessione.risottoscrivi`).

`FlussoOrdiniContoBetfair` era gia' pronto per essere l'unico: una connessione, consumatori multipli con filtro per mercato
(`aggiungi_consumatore`), `avvia()` idempotente, chi arriva dopo legge lo stato da `ordini()`/`posizioni()` e riceve i cambi.

Test: `tests/test_a2_gestore_unico.py` (8), sulla libreria vera contro il server finto TLS: **3 consumatori sugli stessi
300 mercati = 2 connessioni (200 + 100), non 6**, 2 sole `marketSubscription` (il 2o e il 3o consumatore non mandano nulla),
ogni consumatore riceve i 300 mercati; il confronto col modello di oggi (un gestore per consumatore: 6 connessioni);
richieste diverse (unione, filtro per consumatore, `imposta_mercati` che non toglie gli altri, rilascio che toglie solo i
mercati di nessuno, tutti rilasciano = 0 connessioni); capacita' piena (i fuori sono del consumatore che non entra);
3 thread che cambiano richiesta insieme (l'ultimo piano = l'unione finale); 3 consumatori degli ordini = 1 connessione e 1
`orderSubscription`. Mutazioni G1-G9 e O1 in `ondata1/W1-A2/falsifica.py`: 10/10 rosse. Dopo la revisione indipendente:
`tests/test_a2_gestore_unico_revisione.py` (6: risottoscrizione di un piano vecchio arrivata dopo quella nuova, fuori che
entrano quando un altro rilascia, capacita' piena su 9 connessioni, consumatori calcio/tennis separati, stress 5 thread x 50
cambi); mutazioni R6_generazione e R5_filtro_unione rosse (referto W1-A2 par. 14).

**Connessioni di oggi per processo** (caso peggiore, LIVE; le 10 per app key sono del CONTO, condivise da tutti i processi):

| Processo | Stream dei prezzi | Stream ordini | Dove (file:riga) |
|---|---:|---:|---|
| runner-calcio | fino a 3 (180 mercati l'una, riserva 1) | 1 in LIVE (flumine, senza filtro), 0 in PAPER | `Betfair/stream/frammenti_mercato.py:88-91` (`DEFAULT_MAX_CONNESSIONI = 3`, `DEFAULT_RISERVA = 1`), `Betfair/stream/runner.py:2253` (`order_stream=True`, LIVE) |
| runner-tennis | 1 (stream unico cross-evento) | 1 in LIVE | `Betfair/stream/tennis_live/tennis_runner.py:476-492`, `:159` |
| safe-strategy-service (scanner) | fino a 4 (180 l'una) | 0 | `Betfair/safe_strategy/stream.py:82` (`DEFAULT_MAX_CONNECTIONS = 4`), `:474-476` |
| sessione scalper (un processo per partita, fino a 4: `scalper/auto_mode.py:72`) | 1 per partita | 1 per partita in LIVE | `Betfair/stream/scalper/scalper_session.py:936-942` (`order_stream: True`), `:1926` (`Flumine` proprio) |
| mike-service, omega-service, safe-strategy-bot, tennis-bot-service, job `tennis-odds` | 0 (leggono il feed dello scanner o la REST) | 0 (ordini via REST) | `ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/A_CONNESSIONE_BETFAIR.md` par. 1.6 |
| **Totale** | **8** | **2** (+1 per partita scalper LIVE) | **10/10** senza scalper; ogni partita scalper LIVE +2: OLTRE il limite (referto W1-A2 par. 12.1) |

Gli STESSI mercati vengono sottoscritti piu' volte: la partita di calcio seguita dal runner (EX_ALL_OFFERS), dallo scanner
(EX_BEST_OFFERS, conflate 1000 ms) e dallo scalper della partita (filtro di flumine) occupa tre posti su tre connessioni;
e il problema dello slot (decisione 8) nasce da qui, non dal numero di mercati.

**Con il gestore unico** (un `GestoreFlussi` per l'app, 200 mercati per connessione, piu' UN `FlussoOrdiniContoBetfair`):

| Mercati DISTINTI seguiti da tutta l'app (unione) | Connessioni dei prezzi | Stream ordini | Totale |
|---:|---:|---:|---:|
| fino a 200 | 1 | 1 | 2 |
| 300 (la prova del test: 3 consumatori sugli stessi 300) | 2 (200 + 100) | 1 | 3 |
| 1.000 | 5 | 1 | 6 |
| 1.800 (massimo) | 9 | 1 | **10/10** |

Le partite scalper non aggiungono connessioni: i loro mercati sono gia' nell'unione (o ne aggiungono pochi). Nota sul
testo della decisione 8 («con 10 connessioni = fino a 2.000 mercati»): con lo stream ordini che prende una connessione
le connessioni dei prezzi sono al massimo 9, quindi **1.800 mercati** (il gestore lo tiene con `riserva_connessioni = 1`,
che lascia uno slot libero allo stream ordini, regola dello slot del referto W1-A2 par. 11-12).

**Cosa resta all'ondata 2 (aggancio, NON fatto qui)**:

1. Un `GestoreFlussi` e un `FlussoOrdiniContoBetfair` per l'app (nel processo del custode della sessione unica, doc A1 par.
   6-ter), con i servizi come consumatori (`richiedi_mercati` + `aggiungi_consumatore(richiesta=...)`); per i servizi in
   processi separati i book arrivano dal canale locale (oggi 47336), mai da uno stream proprio.
2. **Profilo dell'app**: un gestore = un profilo. Il profilo unico e' il SUPERINSIEME (campi di calcio e scalper:
   EX_ALL_OFFERS, EX_TRADED, EX_TRADED_VOL, EX_LTP, EX_MARKET_DEF, SP_*; il libro EX_ALL_OFFERS serializza
   `available_to_back` a profondita' piena, `betfairlightweight/streaming/cache.py:153-161`, quindi copre chi legge le
   migliori offerte), `conflateMs` assente, 200 mercati per connessione, 9 connessioni e riserva 1 per lo stream ordini.
   Serve un nome nuovo in `contratto.NomeProfilo` (contratto fisso: **estensione proposta**, `"app"`). Le differenze per
   consumatore si applicano DAL LATO DEL CONSUMATORE: lo scanner oggi riceve i book a 1000 ms (U-01) e la strategia non si
   altera, quindi il suo consumatore deve fondere a 1000 ms per avere gli STESSI ingressi, con prova di parita' sul banco
   prima del `nuovo`.
3. Calcio e tennis: le connessioni sono trasporto, i consumatori restano separati per richiesta (un consumatore calcio
   chiede solo mercati di calcio). Se il coordinatore vuole anche le connessioni separate per sport, due gestori (calcio,
   tennis) costano al massimo una connessione mezza vuota in piu'.
4. Lo stream ordini del conto SOSTITUISCE quelli di flumine (`runner.py:2253`, `tennis_runner.py:159`,
   `scalper_session.py:936-942`): flumine riceve gli ordini dal nucleo (tappa C), mai uno stream in piu'.
