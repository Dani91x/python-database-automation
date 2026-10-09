# REFERTO W1-A1 - Comparto A: sessione e REST (tappa T5), ondata 1

Agente W1-A1, ramo `architettura/w1-a1` (base `559a96df`), 09/10/2026. Nessun file esistente modificato; nessun push.
Documento del comparto: `Betfair/nucleo/betfair/doc/A1_SESSIONE_REST.md`.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Righe | Punti chiave |
|---|---|---|
| `Betfair/nucleo/betfair/limiti.py` | ~225 | tabella dei pesi `PESI_LIST_MARKET_BOOK` (:51), `peso_list_market_book` (:136, regole ufficiali: combinazioni con `EX_TRADED` a peso proprio, ALL prevale su BEST, `bestPricesDepth` x d/3), `mercati_massimi_per_richiesta`, `blocchi_per_peso` (:180), `e_metodo_conteso` (:204), endpoint .it, limiti di login/ban/istruzioni |
| `Betfair/nucleo/betfair/salute.py` | ~145 | `SaluteBetfair`: login/keepAlive/relogin/frenati/ban, esiti per metodo e classe, ritenti, attese sul tetto, latenze p50/p99 con `Betfair.monitor.registro.Istogramma` (riusato); inoltro facoltativo al modulo Salute con gruppi propri |
| `Betfair/nucleo/betfair/sessione.py` | ~455 | `FrenoLogin` (:84), `_ClientCustodito` (:170: il client visto da `auth.CustodeSessione`), `SessioneBetfair` (`client`, `rinnova_se_serve`, `stato`, `rifai_login` :293 col contatore di generazione, `_primo_login` :354, `_login_frenato` :370, `avvia/ferma/chiudi`), `sessione_del_processo` (:431) |
| `Betfair/nucleo/betfair/rest.py` | ~315 | `LETTURE`/`MUTAZIONI` (:63/:78), `classifica_errore` (:109, funzioni di oggi importate), `tetto_del_conto` (:150), `ClienteRestBetfair.lettura` (:211, suddivisione per peso), `mutazione` (:234), `_lettura_ritentata` (:255), `_chiama` (:287: semaforo del conto, latenza, esito) |
| `Betfair/nucleo/betfair/tests/test_a1_*.py` | 4 file | finto Betfair a livello di trasporto + 172 casi (65 funzioni) |

Riuso (import, nessuna copia): `auth.build_client(login=False)` (il client di oggi: locale `italy`, certificati,
`requests.Session`), `auth.CustodeSessione` (periodo, backoff 15/30/60, relogin al 90% della vita), `auth.e_errore_di_sessione`,
`auth._descrivi_errore`, `auth.safe_logout`, `auth.BetfairStreamAuthError`; `odds_refresh._is_limit`, `LIMIT_MARKERS`,
`BetfairLimitHit`; `monitor.registro.Istogramma`. `auth` e `odds_refresh` si importano DENTRO i metodi: `config.py` chiama
`load_dotenv()` al caricamento (apre un file), quindi importare i moduli del nucleo non apre file, socket o thread (verificato:
al caricamento entrano solo libreria standard e `Betfair.monitor.registro`).

NON fa: non pagina `listCurrentOrders`/`listClearedOrders` (oggi `client.py:361-425`, resta al chiamante); non suddivide il
catalogo; non controlla i limiti delle istruzioni d'ordine (dati in `limiti.py` per il comparto C); non coordina login e
tetto delle 3 concorrenti FRA processi (proposta al par. 8); non ricostruisce lo stream dopo un relogin (emette
`sessione_rifatta`); non spegne il `keep_alive` di default di flumine (resta, come oggi).

## 2. Contratto

Implementati: `contratto.Sessione` (`SessioneBetfair`) e `contratto.ClienteRest` (`ClienteRestBetfair`); test di
conformita' delle firme (`test_implementa_il_contratto_sessione`, `..._cliente_rest`). Contratti NON modificati.

Estensioni proposte (gia' implementate come metodi in piu' della classe, da aggiungere al protocollo se il coordinatore
approva): `Sessione.segnala_errore(exc) -> bool` (errore di sessione visto dallo stream), `Sessione.rifai_login(exc,
generazione_vista) -> bool` e l'attributo `generazione` (un solo relogin con piu' thread), `Sessione.alla_sessione_rifatta(cb)`
(l'evento `sessione_rifatta()` gia' elencato nei commenti del contratto), `avvia()/ferma()/chiudi()`, `conto`.

## 3. Parita' (vecchio contro nuovo, stessi ingressi)

Ingressi: il client VERO di oggi (`auth.build_client`) con la sua `requests.Session` vera, trasporto sostituito da un
`HTTPAdapter` che risponde con i JSON del formato ufficiale Betfair, compressi gzip in un `urllib3.HTTPResponse` vero. Il
finto applica le regole di Betfair con una tabella SUA (non importa `limiti.py`). Non esistono registrazioni REST nel repo
(`registrazioni_banco/` contiene solo stream): ⊘ ingressi veri registrati per il REST.

| Oggi (file:riga) | Nuovo | Test | Esito |
|---|---|---|---|
| `auth.build_client` (:33-85) endpoint, cert, locale, sessione HTTP | `SessioneBetfair.client()` | `test_endpoint_e_certificati_come_oggi` | identici (certlogin `identitysso-cert.betfair.it`, keepAlive `identitysso.betfair.it`, API `api.betfair.com`, cert tuple, 1200 s) |
| `auth.build_client(login=True)` errore di login | `client()` | `test_primo_login_fallito_stesso_errore_di_build_client` | stesso tipo, stesso messaggio, stessa causa |
| `auth.CustodeSessione.tick` (:226-249) | `SessioneBetfair.rinnova` | `test_parita_custode_di_oggi_stesso_copione` (39 passi: ok, ko di rete con backoff 15/30/60, relogin al 90%, NO_SESSION -> login, login fallito, errore segnalato) | esiti, richieste HTTP e `stato()` del custode identici |
| `omega_market.call_mutating` (:89-112) | `mutazione` | `test_parita_mutazioni_con_call_mutating` (8 guasti) | identico su rete, timeout, UNEXPECTED_ERROR, TOO_MANY_REQUESTS (1 invio), INVALID_SESSION_INFORMATION, NO_SESSION (2 invii); **divergenza** NO_APP_KEY/INVALID_APP_KEY: oggi 2 invii, nuovo 1 (par. 9) |
| `odds_refresh._with_client` (:78-91) | `lettura` | `test_parita_letture_con_odds_refresh_with_client` | stesso esito e stesse chiamate; su errore di RETE oggi 2 login, nuovo 1 (miglioria misurata) |
| `odds_refresh._is_limit`, `auth.e_errore_di_sessione` | `classifica_errore` | `test_classificazione_coincide_con_le_funzioni_di_oggi` (10 casi) | coincide |
| `safe_strategy/service.py:1672-1689` `poll_books` (blocchi 25) | `lettura("listMarketBook")` | `test_list_market_book_parita_col_ripiego_dello_scanner` (73 mercati) | stessi book, stesso ordine, best back/lay identici per runner; 2 richieste invece di 3 |
| blocchi di oggi (scanner 25, board 25, `odds_refresh` 20) | `blocchi_per_peso(..., blocco_massimo)` | `test_blocco_massimo_riproduce_i_blocchi_di_oggi` | identici |
| `runner.py:2710-2711` sessione `rest` senza keepAlive (REPERTO A par. 1.7) | `SessioneBetfair` + custode | `test_reperto_rest_del_runner_muore_a_20_minuti`, `test_custode_tiene_viva_la_sessione_oltre_i_20_minuti` | il vecchio muore a 1201 s (4 chiamate inutili, nessun relogin); il nuovo vive 96 minuti con 1 login e 12 keepAlive |

## 4. Migliorie misurate (sul finto, con i test citati)

- Login: un solo login per processo (oggi uno per ogni `build_client(login=True)` e `BetfairClient`); niente relogin sugli
  errori di rete (`odds_refresh`: 2 login -> 1); relogin unico con 6-8 thread che vedono la sessione scaduta insieme
  (`test_errore_di_sessione_da_otto_thread_un_solo_relogin`, `test_sessione_scaduta_vista_da_sei_thread_un_solo_relogin`).
- `listMarketBook` EX_BEST_OFFERS: 40 mercati per richiesta invece di 25/20: 73 mercati in 2 richieste invece di 3.
- Nessun ban possibile per cicli impazziti: 1000 relogin forzati in 10 minuti -> al massimo 10 login al minuto, Betfair
  (finto) non banna (`test_freno_di_serie_mai_il_ban_di_betfair_anche_in_un_ciclo_impazzito`).
- Latenza: non misurata dal vivo (niente Betfair vero in questa ondata): ⊘, si misura in ombra (par. 8).

## 5. Test e falsificazioni

- Test W1-A1: **172 verdi** (finto 5, limiti 30, sessione 22, rest 115) in ~5 s.
- Falsificazione (rilancio FINALE sui file del commit): **86 mutazioni, 86 rosse**, ripristino con sha256 identico per
  tutte (e copia di prova identica al repo dopo i ripristini); **65/65 funzioni di test** e **172/172 casi** visti rossi
  almeno una volta. La mutazione chiesta dal brief, **R01 «mutazione ritentata su qualunque errore» -> rosso**
  (`test_mutazione_mai_ritentata`); R02 (interruttore della ripetizione ignorato) rosso. Elenco, test rossi e sha256 per
  mutazione: `falsificazione.json`; script: `mutazioni_a1.py` (gira su una COPIA del repo:
  `python3 -P mutazioni_a1.py <copia> <uscita.json>`); copertura: `python3 copertura_falsificazione.py falsificazione.json`.
- sha256 dei file consegnati: `limiti.py` cb0c1e66...1933, `rest.py` 85e4ed5e...d33b, `salute.py` 281c6a4c...d372,
  `sessione.py` a1955815...4c18, `test_a1_finto_betfair.py` f2c40473...1437, `test_a1_limiti.py` 042b6a57...aba,
  `test_a1_rest.py` 3413cd5c...e634, `test_a1_sessione.py` ab504ce6...2d0f (valori interi in `falsificazione.json`).
- Una mutazione equivalente trovata e tolta: `voci.discard("EX_BEST_OFFERS")` in `limiti.py` era codice morto (la precedenza
  di ALL su BEST la fa l'ordine dei rami); rimosso, e la mutazione L02 riscritta sulla precedenza vera.
- Difetto trovato DAI TEST di parita' e corretto prima della consegna: la generazione della sessione era letta prima del primo
  login, quindi al primo errore di sessione il REST ritentava senza relogin (`rest.py`, ora `_generazione_usata`, mutazione R13).
- Suite intera: vedi par. 5-bis.

### 5-bis. Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`)

Un solo giro valido (il primo e' andato perso, par. 9 punto 11), a fine lavoro sul ramo con questo codice:
**11.742 verdi, 0 rossi, 87 saltati, 6 xfail** in 637 s (= 11.571 della cima integrata del 09/10 + 171 test W1-A1: il 172o,
`test_reperto_keepalive_di_omega...`, e' stato aggiunto mentre la suite girava; e' verde da solo e nella falsificazione).

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (test nel doc del comparto, par. 5): A-001..A-006, A-007/A-008 (sostituite), A-009..A-016, A-040, A-071, A-078, A-081,
D-012, E2-088, E3-S17, I-048 (queste ultime come «un custode per processo»: l'effetto c'e' quando l'aggancio sostituisce i
keepAlive di oggi). Restano al vecchio codice: A-017/A-018 (Aggiorna quote e coda), A-019 (cambio GBP->EUR), A-021/A-022
(catalogo per evento: useranno `lettura("listMarketCatalogue", ..., lightweight=True)` nell'aggancio).

## 7. PROCESSO_STANDARD_BOT.md par. 6 e 7

- Sollecitate: 6.6 (limiti: 200 punti su griglia, 3 concorrenti per conto con thread veri e semaforo, 100 login/min e ban),
  6.7 (falsificazione: 86 mutazioni), 6.8 (riproducibile: script, json, sha256, comandi); 7 n.9 (i prezzi del book sono dict:
  il test del finto leggeva `.price` ed e' diventato rosso), n.20 (sessione «viva» ma scaduta: scadenza .it simulata e reperti
  del runner e di Omega), n.27 (finti con chiavi e tipi del vero: JSON ufficiali, oggetti veri di betfairlightweight, client
  di oggi), n.28/n.29 (le asserzioni sono sui conteggi del filo HTTP, non su cio' che il codice dichiara), n.30/n.35 (ogni test
  visto rosso).
- ⊘ con causa: 6.1-6.5 (dati di mercato, scanner, servizio intero, ciclo di vita dell'ordine, persistenza e UI: il comparto
  non decide e non tiene ordini ne' righe; li useranno C e i bot), 6.9 (nessun replay in questa ondata); 7 n.1-8, n.10-19,
  n.21-26, n.31-34, n.36-37 (riguardano bot, banco, DB, UI e il frontend, assenti in questo comparto; n.21 paper/live:
  la sessione e il REST servono solo il Betfair vero, il paper non passa da qui).

## 8. Aggancio proposto per l'ondata 2 (NON fatto)

Interruttore `ARCH_SESSIONE=vecchio|ombra|nuovo` (di serie `vecchio`), letto UNA volta all'avvio del processo.

### 8.1 I 12 punti `build_client(login=True)` (git grep al commit base; la scheda A D6 aveva righe vecchie)

| Punto | Oggi | `nuovo` |
|---|---|---|
| `Betfair/safe_strategy/service.py:3370` (+ custode `:555`, periodo `:173` 900 s) | login + `CustodeSessione` del servizio | `sessione_del_processo(periodo_keepalive_s=900).client()`; il custode del servizio diventa `sessione.rinnova()` o `avvia()`; `stato()` dalla sessione |
| `Betfair/stream/runner.py:2712` (+ custode `:1438-1444`, tick `:1698-1704`, idle `:2884-2896`) | login + custode 480 s + keepAlive idle | `sessione_del_processo(periodo_keepalive_s=480)`; `_dopo_relogin` registrato con `alla_sessione_rifatta`; il keepAlive idle sparisce (lo fa il custode) |
| `Betfair/stream/tennis_live/tennis_runner.py:3195` (+ custode `:1612-1613`, idle `:3291`) | idem tennis | idem |
| `Betfair/stream/scalper/scalper_session.py:1544` (+ custode `:951-958`, 600 s) | UN login per sessione scalper | la sessione del processo: N sessioni scalper nello stesso processo = 1 login |
| `Betfair/stream/scalper/scalper_service.py:890`, `habitat_scan.py:89`, `run_scalper_live.py:230` | login | `sessione_del_processo().client()` |
| `Betfair/stream/tennis_scalper/{record_multi.py:280, record_tennis.py:41, run_tennis_pro.py:88, run_tennis_scalper.py:219, backtest_pro.py:81}` | login (script) | idem |

(Fuori conto: `laboratorio/tennis_lab/lab_grid_score.py:101` e 7 sonde in `AUDIT_*`, non produzione.)

### 8.2 I 6 punti `BetfairClient()` (JSON-RPC nostro)

| Punto | `nuovo` |
|---|---|
| `Betfair/stream/runner.py:2710-2711` (sessione `rest`, il REPERTO) | `ClienteRestBetfair(sessione_del_processo())`; `fetch_event_markets` (`runner.py:138-171`) -> `lettura("listMarketCatalogue", filter=..., max_results=1000, market_projection=[...], lightweight=True)` (stesso dict del JSON-RPC) |
| `Betfair/odds_refresh.py:66` (sessione condivisa di Omega, Mike, Safe, `order_exec`) | `get_shared_client()` restituisce un adattatore SOTTILE con l'API di `BetfairClient` (`betting_rpc`, `account_rpc`, `list_market_book`, `place_orders`...) sopra `ClienteRestBetfair` con `lightweight=True`: le mutazioni (`placeOrders`...) passano da `mutazione`, il resto da `lettura`. `call`/`call_mutating`/`_with_client`/`order_exec._call` restano ma non rifanno piu' il login da soli (lo fa la sessione) |
| `Betfair/betfair_report_manager.py:68`, `betfair_full_odds.py:146`, `betfair_tennis_odds.py:307`, `import_betfair_operations.py:393` | lo stesso adattatore (job e script) |

Ripieghi REST: `safe_strategy/service.py:1672-1689` (`poll_books`) e `stream/board_worker.py:387` (`_poll_books_rest`) ->
`lettura("listMarketBook", market_ids=..., price_projection=...)` con `blocco_massimo={"listMarketBook": 25}` e
`pausa_tra_blocchi_s=0.35` in `ombra` (blocchi di oggi), senza in `nuovo`; `odds_refresh._market_books` (`:136-147`) idem
con 20 e 0,6 s.

### 8.3 Ombra e criterio «uguale o meglio»

- **Sessione**, un giorno: in `ombra` ogni processo tiene la sessione di oggi E una `SessioneBetfair` con il SUO login (un
  login in piu' per processo, sotto il freno) e il custode avviato; il monitor (`MONITOR_SALUTE=1`) conta per processo
  keepAlive e relogin del vecchio (gancio HTTP gia' esistente, gruppo `betfair_rest`) e del nuovo (`inoltra_a=sonde`, gruppo
  `betfair_sessione`). Criterio: nuovo keepAlive <= vecchio, relogin nuovo <= vecchio, **0** `INVALID_SESSION_INFORMATION` sul
  REST nuovo, nessun `LoginFrenato` ne' ban.
- **REST**, 1 ora sul PC: `poll_books` e il board chiamano le due fonti in parallelo sugli stessi id (peso raddoppiato, sotto
  i limiti); differenza = 0 sui best back/lay (prezzo e size del primo livello) per mercato e runner, scritta come conteggio
  nel monitor. Il test di parita' sul finto e' gia' questo confronto.
- **Mutazioni**: nessuna ombra (i soldi non si mandano due volte): si passa a `nuovo` solo dopo la parita' su
  `call_mutating` (fatta) e con il conteggio degli invii nel monitor uguale a quello degli ordini registrati.
- Ritorno: `vecchio`. Rischio (A par. 6 rischio c): dopo un relogin lo stream di flumine va ricostruito come oggi
  (`runner.py:1446-1460`): il nuovo emette `sessione_rifatta`, la ricostruzione resta quella di oggi.

### 8.4 Monitor (Salute) - aggancio proposto, `Betfair/monitor/` NON modificato

`SaluteBetfair(inoltra_a=sonde)` quando `sonde.ATTIVO`: i contatori finiscono nella riga `monitor_metrics` del servizio con
gruppi che non collidono col gancio HTTP gia' esistente (`betfair_rest`, `rest_ms.<metodo>`): `betfair_sessione`,
`betfair_rest_esiti` (`<metodo> <classe>`), `a1_rest_ms.<metodo>`, `a1_attesa_tetto_ms`. I nomi dei metodi coincidono con
quelli che `sonde._metodo_betfair` legge dalle risposte (provato). Il referto di 24 h li somma secchio per secchio come gli
altri tratti (stesso `Istogramma`).

### 8.5 Tetti fra processi (proposta)

Il conto ha 100 login al minuto e 3 richieste contese in coda IN TUTTO; qui i tetti sono per processo (10 login/min: 10
processi stanno nei 100). Proposta per l'ondata 2: **una sola sessione per l'app**, tenuta dal processo principale
(custode unico), che distribuisce il token ai servizi sul canale locale 127.0.0.1 (betfairlightweight ha
`set_session_token`); i servizi non fanno login, su `INVALID_SESSION_INFORMATION` chiedono il token nuovo. Risultato: 1 login
e 1 keepAlive per tutta l'app (oggi 1 per processo piu' i relogin). Lo stesso processo puo' tenere il semaforo delle 3
richieste contese per il conto (richiesta di posto sul canale). In alternativa minima: un contatore a finestra su file con
lucchetto (`msvcrt.locking`) in `_logs/`.

## 9. Divergenze per l'utente, rischi, dubbi

1. **Tre politiche di ripetizione delle MUTAZIONI oggi** (non ne ho scelta una in silenzio; il nuovo e' la parita' con
   `call_mutating`, come chiede il brief): `client.py:329-359` `place_orders(max_retries=2)` RIPETE il `placeOrders` su errori
   HTTP/RPC/rete contando sul `customerRef` (de-dup 60 s); `order_exec._call` (`:120-137`) rifa' login e RIPETE su qualunque
   errore non di limite (con `max_retries=1` dentro); `omega_market.call_mutating` ripete solo su errore di sessione. Con
   l'aggancio, il percorso `order_exec` (watchlist) perderebbe le sue ripetizioni: decisione dell'utente.
2. **Il contratto dice «MAI ritentata»**, `call_mutating` ripete UNA volta dopo `INVALID_SESSION_INFORMATION`/`NO_SESSION`
   (la richiesta e' rifiutata prima dell'exchange). Ho tenuto la parita' (`rifai_mutazione_su_sessione=True`), spegnibile.
3. **Due definizioni di «errore di sessione»**: `auth._ERRORI_DI_SESSIONE` (INVALID_SESSION_INFORMATION, NO_SESSION) e
   `omega_market._SESSION_ERRORS` (+ NO_APP_KEY, INVALID_APP_KEY). Il nuovo usa quella di `auth` (non importa un bot):
   su NO_APP_KEY/INVALID_APP_KEY il nuovo NON ripete la mutazione (oggi si'). Provato e dichiarato nel test.
4. **Periodi di keepAlive diversi per processo**: 480 s runner/tennis, 600 s scalper, 900 s scanner. Il nuovo li accetta come
   parametro (di serie 480); l'aggancio deve passare lo stesso valore di oggi per processo.
5. **REPERTO nuovo**: il «keepAlive» di Omega (`omega_market.keep_alive`, `:140-150`, ogni 600 s da `omega_service.py:8849`)
   chiama `listEventTypes`, che per la documentazione NON allunga la sessione .it: la sessione condivisa di Omega/Mike/Safe
   scade ogni 20 minuti e la regge solo il relogin su errore (`test_reperto_keepalive_di_omega...`, sul finto). Conferma dal
   vivo insieme a U-06.
6. **Peso del catalogo**: il runner chiede `listMarketCatalogue` con `maxResults=1000` e `MARKET_DESCRIPTION` (peso 1): con la
   formula letta in 02 sarebbero 1000 punti, eppure oggi funziona. Non applico limiti al catalogo (solo il dato); da chiarire
   sulla documentazione.
7. **`bestPricesDepth`**: ho applicato il fattore d/3 a tutto il peso della proiezione con le migliori offerte, anche alla
   combinazione con `EX_TRADED` (scelta prudente: blocchi piu' piccoli, mai `TOO_MUCH_DATA`).
8. **Blocchi da 40 invece di 25/20**: cambia il numero di richieste (meno), non i dati; `blocco_massimo` riproduce oggi.
9. **Letture e rete**: oggi `odds_refresh`/`call` rifanno il login anche su un errore di RETE; il nuovo no (un login in meno).
10. Rischi: i nomi privati riusati (`auth._descrivi_errore`, `odds_refresh._is_limit`) sono fragili a un rinomino (i test lo
    vedrebbero); il `keep_alive` di default di flumine resta un secondo keepAlive sullo stesso `APIClient` (come oggi);
    nessuna prova contro Betfair vero (vietata in questa ondata): i limiti sono quelli della documentazione.
11. Il primo giro della suite intera e' andato perso: il file d'uscita era nella cartella di lavoro CONDIVISA con gli altri
    agenti e risultava troncato (anche il mio script di mutazioni li' e' stato sovrascritto da un altro agente: rifatto in una
    sottocartella mia). La suite e' stata rilanciata una seconda volta, a fine lavoro (par. 5-bis).
