# REFERTO W1-A1 - Comparto A: sessione e REST (tappa T5), ondata 1

Agente W1-A1, ramo `architettura/w1-a1` (base `559a96df`), 09/10/2026. Nessun file esistente modificato; nessun push.
Documento del comparto: `Betfair/nucleo/betfair/doc/A1_SESSIONE_REST.md`.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Righe | Punti chiave |
|---|---|---|
| `Betfair/nucleo/betfair/limiti.py` | 228 | tabella dei pesi `PESI_LIST_MARKET_BOOK` (:54), `peso_list_market_book` (:139, regole ufficiali: combinazioni con `EX_TRADED` a peso proprio, ALL prevale su BEST, `bestPricesDepth` x max(1, d/3)), `mercati_massimi_per_richiesta`, `blocchi_per_peso` (:182), `e_metodo_conteso` (:206), endpoint .it, limiti di login/ban/istruzioni |
| `Betfair/nucleo/betfair/salute.py` | 144 | `SaluteBetfair`: login/keepAlive/relogin/frenati/ban, esiti per metodo e classe, ritenti, attese sul tetto, latenze p50/p99 con `Betfair.monitor.registro.Istogramma` (riusato); inoltro facoltativo al modulo Salute con gruppi propri |
| `Betfair/nucleo/betfair/sessione.py` | 522 | `FrenoLogin` (:98), `freno_del_conto` (:184, un freno per conto nel processo), `_ClientCustodito` (:205: il client visto da `auth.CustodeSessione`), `SessioneBetfair` (`client` :271 con via veloce senza lucchetto, `in_backoff` :322, `rifai_login` :357 col contatore di generazione e il backoff del custode, `_primo_login` :421, `_login_frenato` :437, `avvia/ferma/chiudi`), `sessione_del_processo` (:499) |
| `Betfair/nucleo/betfair/rest.py` | 352 | `LETTURE`/`MUTAZIONI` (:69/:84), `classifica_errore` (:115, funzioni di oggi importate), `rifiuto_di_sessione` (:131, solo per le mutazioni: `str(e)` e `__cause__`), `tetto_del_conto` (:177), `ClienteRestBetfair.lettura` (:238, suddivisione per peso), `mutazione` (:272), `_lettura_ritentata` (:293), `_chiama` (:325: semaforo del conto, latenza, esito) |
| `Betfair/nucleo/betfair/tests/test_a1_*.py` | 6 file | finto Betfair a livello di trasporto, prove mie, prove del revisore (`test_a1_rest_revisore.py`), prove delle correzioni (`test_a1_correzioni.py`) |

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
| `omega_market.call_mutating` (:89-112) | `mutazione` | `test_parita_mutazioni_con_call_mutating` (8 guasti), `test_a1_rest_revisore::test_parita_con_call_mutating_dentro_un_except_di_sessione`, `..._mutazione_chiamata_dentro_un_except_di_sessione_...` (4), `test_a1_correzioni::test_rifiuto_di_sessione_mai_dal_contesto` (6) | identico su rete, timeout, UNEXPECTED_ERROR, TOO_MANY_REQUESTS (1 invio), INVALID_SESSION_INFORMATION, NO_SESSION (2 invii) e, DOPO LA CORREZIONE ALTA-1, anche su una mutazione chiamata dentro un `except` per un errore di sessione che cade per un timeout (1 invio, come oggi: prima della correzione il nuovo ne mandava 2). Il rifiuto si legge come oggi da `str(e)` (piu' la sola causa esplicita `__cause__`). **Divergenza** NO_APP_KEY/INVALID_APP_KEY: oggi 2 invii, nuovo 1 (par. 9). **La parita' dichiarata nella prima consegna era sbagliata sul caso `__context__`.** |
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

- **Ultimo commit (dopo la seconda revisione)**: test W1-A1 **222 verdi** (correzioni 17 -> 21); falsificazione rilanciata
  per intero sui file finali: **117 mutazioni, 117 rosse** (le 103 qui sotto + le 14 del revisore X01-X14; X05, X06, X07, che
  prima sopravvivevano, ora rosse con i loro tre test nuovi), ripristini con sha256 identico, **88/88 funzioni** e
  **222/222 casi** visti rossi; `falsificazione.json` e' questo giro. sha256 cambiati: `sessione.py` bb954f9f...d6cdb205
  (solo docstring), `test_a1_correzioni.py` b6865428...3150ea3f. Suite intera non rilanciata (solo test, doc e docstring).
- Test W1-A1 (seconda consegna): **218 verdi** (finto 5, limiti 31, sessione 22, rest 115, revisore 28, correzioni 17).
- Falsificazione (rilancio FINALE sui file del commit di correzione): **103 mutazioni, 103 rosse** (le 86 della prima
  consegna, con le stringhe aggiornate dove il codice e' cambiato, piu' 17 sulle correzioni: R28-R34, S27-S34, L21-L22),
  ripristino con sha256 identico per tutte (copia di prova identica al repo dopo i ripristini); **84/84 funzioni di test**
  e **218/218 casi** visti rossi almeno una volta. La mutazione chiesta dal brief, **R01 «mutazione ritentata su qualunque
  errore» -> rosso** (21 test); la mutazione che prima sopravviveva (R30: ripetere dopo il relogin di un altro thread senza
  guardare l'errore) -> rosso (20 test, compresi i 16 casi del revisore); ALTA-1 (R28 `__context__`, R29) -> rosso.
  Elenco, test rossi e sha256 per mutazione: `falsificazione.json`; script: `mutazioni_a1.py` (gira su una COPIA del repo:
  `python3 -P mutazioni_a1.py <copia> <uscita.json>`); copertura: `python3 copertura_falsificazione.py falsificazione.json`.
- sha256 dei file consegnati (seconda consegna): `limiti.py` fd18da7f...b049bca3, `rest.py` 7e835cb5...e2ae38e2,
  `salute.py` 281c6a4c...56c4d372, `sessione.py` 973b9891...a4f8d31b; test: `correzioni` d65e019e...0d42fe6c, `finto`
  f830363a...60654c9f, `limiti` e17222f4...6a6e8fd3, `rest` 3413cd5c...507ae634, `rest_revisore` 69802c90...33f66b40,
  `sessione` 641a3b12...e223a2e1 (valori interi in `falsificazione.json`).
- Una mutazione equivalente trovata e tolta: `voci.discard("EX_BEST_OFFERS")` in `limiti.py` era codice morto (la precedenza
  di ALL su BEST la fa l'ordine dei rami); rimosso, e la mutazione L02 riscritta sulla precedenza vera.
- Difetto trovato DAI TEST di parita' e corretto prima della consegna: la generazione della sessione era letta prima del primo
  login, quindi al primo errore di sessione il REST ritentava senza relogin (`rest.py`, ora `_generazione_usata`, mutazione R13).
- Suite intera: vedi par. 5-bis.

### 5-bis. Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`)

Un solo giro valido (il primo e' andato perso, par. 9 punto 11), a fine lavoro sul ramo con questo codice:
**11.742 verdi, 0 rossi, 87 saltati, 6 xfail** in 637 s (= 11.571 della cima integrata del 09/10 + 171 test W1-A1: il 172o,
`test_reperto_keepalive_di_omega...`, e' stato aggiunto mentre la suite girava; e' verde da solo e nella falsificazione).

Seconda consegna (dopo le correzioni), un giro: **11.788 verdi, 1 rosso, 87 saltati, 6 xfail** in 660 s (= 11.571 + 218 test
W1-A1 - 1). Il rosso e' `Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`,
una MISURA di tempo (p95 < 20 ms) del motore ordini di oggi: rosso anche da solo in questo momento (p95 = 23,97 ms con load
average 12 su 4 CPU, macchina condivisa da 7 agenti), verde nel giro della prima consegna. Non importa nulla del nucleo e
nessun file fuori da `Betfair/nucleo/betfair/` e da questa cartella e' cambiato sul ramo (diff contro `559a96df` vuoto su
`Betfair/stream`, `Betfair/omega`, `Betfair/monitor`): e' carico della macchina, non una regressione. Da rilanciare a macchina
scarica.

## 5-ter. Correzioni dopo la revisione indipendente (seconda consegna)

La revisione del coordinatore su `241d0299` ha dato DA CORREGGERE. Le prove del revisore sono nel comparto come
`Betfair/nucleo/betfair/tests/test_a1_rest_revisore.py` (28 casi, tenuti com'erano: 9 erano rossi, ora tutti verdi; i 16
casi «generazione cambiata + errore generico» restano verdi e coprono la mutazione R30, che prima sopravviveva); le mie
prove sulle correzioni in `test_a1_correzioni.py` (17 casi). Unica modifica al file del revisore: in
`test_misura_una_mutazione_aspetta_il_keepalive_in_volo` l'attesa del keepAlive in volo era un ciclo senza fine (con la
mutazione S08 il test si BLOCCAVA invece di diventare rosso): ora attende al massimo 5 s e poi asserisce; il caso e'
identico. Lo script di falsificazione conta come vista anche una mutazione che blocca i test (timeout 300 s).

| Voce | Difetto | Correzione | Prova (mutazione rossa) |
|---|---|---|---|
| ALTA-1 (soldi) | `mutazione` classificava il rifiuto di sessione con `auth.e_errore_di_sessione`, che segue `__cause__ or __context__`: una mutazione chiamata dentro un `except` per un errore di sessione e caduta per timeout veniva RIPETUTA (possibile ordine doppio) | `rest.rifiuto_di_sessione(e)`: solo `str(e)` e `__cause__`, mai `__context__`; codici da `auth._ERRORI_DI_SESSIONE` (riuso) | revisore `..._dentro_un_except_di_sessione_...` x4, parita' con `call_mutating`; R28, R29, R30 |
| ALTA-2 | `rifai_login` scavalcava il backoff del custode: credenziali rifiutate, 30 letture = 19 login FALLITI verso Betfair | `SessioneBetfair.in_backoff()` (pubblico, anche in `stato()`): con fallimenti e backoff non scaduto `rifai_login` risponde False senza login; ora 30 letture = 1 login fallito | revisore `test_login_fallito_il_backoff_...`, `test_rifai_login_rifiutato_durante_il_backoff_poi_permesso`; S27, S33 |
| MEDIA-3 | `client()` prendeva il lucchetto unico che `rinnova` tiene durante l'HTTP: una cancellazione aspettava il keepAlive (fino a 16 s) | via veloce senza lucchetto quando la sessione c'e'; lucchetto del custode (`_lock_custode`: keepAlive e login) separato da quello dei campi (`_lock`, mai durante l'HTTP) | revisore `test_misura_una_mutazione_aspetta_il_keepalive_in_volo` (attesa < 0,5 s con keepAlive di 1 s in volo); S29 |
| MEDIA-4 | `call_mutating` chiama `_segnala_saldo("ordine")` dopo ogni mutazione tornata | obbligo dell'adattatore nell'aggancio (par. 8.2) | - (aggancio) |
| MEDIA-5 | freno e ban nell'istanza: chiudi e riapri = ban dimenticato | `freno_del_conto(conto, ora)`: UN freno per conto nel processo (chiave anche sull'orologio: in produzione e' sempre `time.monotonic`), come i semafori; dichiarati i limiti (par. 9 punto 12) | revisore `test_ban_ricordato_dopo_chiudi_e_riapri_...`, `test_freno_del_conto_condiviso_...`; S28 |
| MEDIA-6 | fattore d/3 sotto il peso base per d<3; un mercato oltre 200 = `ValueError` locale; finto con la stessa formula (prova circolare) | fattore `max(1, d/3)`; oltre 200 punti stimati: un mercato per richiesta e decide Betfair (`BetfairLimitHit` se rifiuta); finto con la lettura LETTERALE e piu' generosa (solo la quota delle migliori offerte scala, anche sotto 1) | `test_un_mercato_oltre_200_punti_...`, `test_profondita_sotto_3_...`; L21, R32 |
| BASSE | `market_ids` stringa spezzata in caratteri; periodo non validato; profondita' bool/decimale accettata; ban senza margine; `chiudi` azzerava la generazione; `customerRef` della ripetizione non dichiarato; testi illeggibili inghiottiti senza log | stringa -> `[stringa]`; `0 < periodo <= 1080 s` (`ValueError`); profondita' solo intera >= 1; ban 1200 + 30 s; generazione che non riparte mai (connessa = custode presente); ripetizione con gli STESSI parametri (stesso `customerRef` se passato; non imposto: la richiesta rifiutata non e' arrivata all'exchange) e test; `logger.debug` col motivo | revisore `test_misura_market_ids_stringa_...`, `test_periodo_keepalive_oltre_...`; `test_a1_correzioni`; R31, S30, S31, S32, L22 |

Conseguenza sul comportamento (dichiarata): dopo un login fallito del custode, per 15/30/60 s nessun relogin parte da
`rifai_login` (cioe' su richiesta del REST). [10/10, decisione 2 dell'utente: anche `segnala_errore` ora rispetta il
backoff; prima scavalcava l'attesa per parita' con `auth.py:214-224`. Vedi par. 10.] Durante il backoff: le letture e le mutazioni in quel tempo falliscono con l'errore di sessione invece di tentare un login
(oggi `odds_refresh`/`call` rifarebbero subito il login a ogni chiamata). E' il backoff del custode di oggi applicato a tutti.
Il primo login (`client()`) non ha backoff, come `build_client` oggi: lo limita il tetto dei TENTATIVI del freno
(`test_freno_tetto_dei_tentativi_al_minuto`).

## 5-quater. Seconda revisione (`4935fed5`: PASSA) - ultimo commit

- Tre test per le tre mutazioni del revisore sopravvissute (`test_a1_correzioni.py`): X05
  (`test_stato_e_conto_non_aspettano_un_keepalive_in_volo`), X06 (`test_chiudi_aspetta_il_keepalive_in_volo_prima_del_logout`),
  X07 (`test_ban_di_un_conto_non_frena_un_altro_conto_sullo_stesso_orologio`); piu' il test del contratto d'uso di
  `rifai_login` (par. 9 punto 16).
- Le 14 mutazioni del revisore (X01-X14) sono in `mutazioni_a1.py`: tutte rosse (numeri al par. 5).
- Solo test, documentazione e docstring: nessuna riga di codice eseguibile cambiata (`sessione.py`: solo la docstring del
  modulo e di `segnala_errore`), quindi la suite intera non e' stata rilanciata (indicazione del coordinatore).
- Referto: par. 5-ter (backoff: vale solo per `rifai_login`), par. 9 punti 12 (13 processi, due opzioni), 14, 15, 16.

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
| `Betfair/odds_refresh.py:66` (sessione condivisa di Omega, Mike, Safe, `order_exec`) | `get_shared_client()` restituisce un adattatore SOTTILE con l'API di `BetfairClient` (`betting_rpc`, `account_rpc`, `list_market_book`, `place_orders`...) sopra `ClienteRestBetfair` con `lightweight=True`: le mutazioni (`placeOrders`...) passano da `mutazione`, il resto da `lettura`. `call`/`call_mutating`/`_with_client`/`order_exec._call` restano ma non rifanno piu' il login da soli (lo fa la sessione). **Obbligo dell'adattatore (MEDIA-4)**: dopo OGNI mutazione tornata da Betfair (riuscita o rifiutata con risposta) chiama `omega_market._segnala_saldo("ordine")` come oggi `call_mutating` (`omega_market.py:106-109`), fuori dal percorso d'ordine e senza mai sollevare; test di parita' dell'aggancio: stesso numero di segnalazioni del saldo, vecchio contro nuovo |
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
7. **`bestPricesDepth`** (fonte: 02 par. 3.2, B-WEIGHT: «con `exBestOffersOverrides` peso x (profondita'/3)», senza dire
   nulla della combinazione con `EX_TRADED` ne' di profondita' < 3): il fattore si applica a tutto il peso della proiezione
   con le migliori offerte, anche alla combinazione, e non scende mai sotto 1 (d = 1-2 = peso base). Scelta prudente:
   blocchi piu' piccoli, mai `TOO_MUCH_DATA`. Se la NOSTRA stima di UN mercato supera 200 punti (es. BEST+TRADED con
   profondita' 33 = 220) non rifiuto in locale: un mercato per richiesta e decide Betfair (oggi la richiesta partirebbe).
8. **Blocchi da 40 invece di 25/20**: cambia il numero di richieste (meno), non i dati; `blocco_massimo` riproduce oggi.
9. **Letture e rete**: oggi `odds_refresh`/`call` rifanno il login anche su un errore di RETE; il nuovo no (un login in meno).
10. Rischi: i nomi privati riusati (`auth._descrivi_errore`, `odds_refresh._is_limit`) sono fragili a un rinomino (i test lo
    vedrebbero); il `keep_alive` di default di flumine resta un secondo keepAlive sullo stesso `APIClient` (come oggi);
    nessuna prova contro Betfair vero (vietata in questa ondata): i limiti sono quelli della documentazione.
11. Il primo giro della suite intera e' andato perso: il file d'uscita era nella cartella di lavoro CONDIVISA con gli altri
    agenti e risultava troncato (anche il mio script di mutazioni li' e' stato sovrascritto da un altro agente: rifatto in una
    sottocartella mia). La suite e' stata rilanciata una seconda volta, a fine lavoro (par. 5-bis).
12. **Freno dei login (MEDIA-5)**: il freno e' per CONTO dentro UN processo (10 riusciti e 20 tentativi al minuto di
    serie, `tetto_login_per_processo(10)`). I processi che oggi possono fare login INSIEME sono fino a **13**, non 10:
    gli 8 servizi sotto watchdog avviati da `desktop/main.js:419-480` (runner calcio, runner tennis, scalper-service,
    tennis-bot-service, safe-strategy-service, omega-service, safe-strategy-bot, mike-service; il backtest-worker non tocca
    Betfair), il job `betfair_tennis_odds.py` (`main.js`, `tennis-odds`) e fino a 4 processi scalper figli
    (`Betfair/stream/scalper/auto_mode.py:71-72`, `TETTO_MASSIMO = 4`). Con 13 processi x 10 = 130 > 100 il tetto del
    conto e' garantito solo se non tutti girano in un ciclo impazzito nello stesso minuto (a regime ogni processo fa 1 login
    ogni ~18 minuti). I login del codice VECCHIO (`build_client(login=True)`, `BetfairClient`, `odds_refresh`) NON passano
    dal freno: in ombra il freno non li vede e non li conta. **Due opzioni per l'utente** (il valore NON l'ho cambiato):
    (a) la sessione unica dell'app (par. 8.5: 1 login per tutta l'app, il problema sparisce); (b) quota per processo
    `tetto_login_per_processo(13)` = 7 login riusciti al minuto (13 x 7 = 91 <= 100).
13. **Backoff esteso al REST (ALTA-2)**: vedi par. 5-ter, «Conseguenza sul comportamento».
14. **Due strade di relogin con regole diverse sul backoff** - **DECISA dall'utente il 10/10/2026 (decisione 2: «si',
    sempre una sola connessione»)**: anche `segnala_errore` rispetta il backoff come `rifai_login`. Fatto in D-A (par. 10):
    divergenza VOLUTA dal custode di oggi (`auth.CustodeSessione.segnala_errore`, che scavalca l'attesa).
15. **Mutazione caduta per timeout DOPO l'esecuzione su Betfair**: A1 non la riconcilia ne' la ripete (una sola richiesta
    sul filo, l'eccezione risale al chiamante). Sapere se l'ordine c'e' e' compito del comparto C: riconciliazione per
    `customerOrderRef` (stream degli ordini del conto / `listCurrentOrders`), MAI un secondo invio.
16. **Contratto d'uso di `rifai_login` per chi lo chiama (W1-A2, stream)**: la `generazione_vista` va CATTURATA quando la
    connessione parte, non letta al momento dell'errore; altrimenti 5 errori scaglionati della stessa connessione fanno 5
    login invece di 1 (`test_contratto_d_uso_generazione_catturata_alla_connessione`; prova del revisore
    `scratchpad/rev_w1a1_2/prove/test_e2.py`).

## 10. Decisioni dell'utente del 10/10/2026 (agente D-A, ramo `decisioni/d-a` su `d073ddcb`)

Fonte: `ondata1/DECISIONI_PER_L_UTENTE.md`, sezione «Risposte dell'utente (10/10/2026)», vincolanti.

### 10.1 Decisione 2 - `segnala_errore` rispetta il backoff (fatto)

- Codice: `Betfair/nucleo/betfair/sessione.py` `SessioneBetfair.segnala_errore` (docstring del modulo e del metodo
  aggiornate). Sotto il lucchetto del custode: fuori dal backoff `custode.segnala_errore(exc)` (giro dopo = ADESSO, come
  oggi); durante il backoff `custode.segnala_errore(exc, adesso=math.inf)`: `min(prossimo, inf)` lascia il giro alla fine
  dell'attesa e la sessione resta segnata da rifare (a fine attesa il custode fa il LOGIN, non il keepAlive). Nessun campo
  privato del custode toccato; `auth.py` non toccato. Il lucchetto serve a non intrecciare il controllo del backoff con un
  login che fallisce in quel momento (altrimenti l'attesa appena nata potrebbe essere scavalcata): e' una finestra di
  microsecondi, non provocabile in modo deterministico da un test (dichiarato). [Dopo la revisione, par. 10.3: l'effetto
  OSSERVABILE del lucchetto, cioe' che `segnala_errore` aspetta il keepAlive in volo, ora ha un test e una mutazione, D2f.]
- Test nuovi: `Betfair/nucleo/betfair/tests/test_a1_decisione2_backoff.py` (5): 5 thread che segnalano durante l'attesa
  dopo un login rifiutato -> 0 login prima della fine (giri a +0, +5, +14,9 s), 1 a fine attesa, nessun altro dopo; errore
  nel backoff nato da un keepAlive caduto -> a fine attesa LOGIN e non keepAlive (presa in carico); errore non di sessione
  nel backoff -> non preso in carico, a fine attesa keepAlive; fuori dal backoff anticipa ad adesso come oggi; prima del
  primo login non fa nulla. La parita' col custode di oggi (`test_parita_custode_di_oggi_stesso_copione`) resta verde: il
  suo copione segnala FUORI dal backoff.
- Falsificazione manuale (script fuori dal repo, nello scratchpad dell'agente: `d-a/falsifica_d2_manuale.py`): corpo di oggi rimesso (scavalca) -> **2
  rossi su 5**; ripristino -> 5 verdi; sha256 di `sessione.py` prima = dopo
  (`54e3e25b82cfc57fbbe03d1cfb896a54f0d0e243c15c61bf250132037948b4d9`).
- `mutazioni_a1.py`: aggiunte D2a (scavalcamento rimesso), D2b (nel backoff accettato ma non preso in carico), D2c (nel
  backoff rifiutato), D2d (nel backoff il giro torna ad ADESSO), D2e (fuori dal backoff giro non piu' anticipato); S16 e
  S27 con la stringa aggiornata (`if self.in_backoff():` c'e' ora anche in `segnala_errore`: S27 porta la riga dopo, per
  colpire ancora `rifai_login`). Esiti sulla copia del repo (tutti i test del comparto per mutazione):

  - S16 (segnala accetta tutto): **4 rossi**, ripristino sha256 identico; rossi: `test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo`, `test_fuori_dal_backoff_segnala_anticipa_ad_adesso_come_oggi`, `test_parita_custode_di_oggi_stesso_copione`, `test_rifai_login_ignora_errori_non_di_sessione`
  - S27 (ALTA-2: backoff scavalcato): **3 rossi**, ripristino sha256 identico; rossi: `test_rifai_login_rifiutato_durante_il_backoff_poi_permesso`, `test_login_fallito_il_backoff_del_custode_non_viene_aggirato_dalle_letture`, `test_freno_tetto_dei_login_riusciti_al_minuto`
  - D2a (D2: scavalcamento del backoff rimesso (come auth.py di oggi)): **2 rossi**, ripristino sha256 identico; rossi: `test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo`, `test_segnalazione_nel_backoff_dopo_un_keepalive_caduto_porta_al_login_non_al_keepalive`
  - D2b (D2: errore nel backoff accettato ma NON preso in carico): **2 rossi**, ripristino sha256 identico; rossi: `test_errore_non_di_sessione_nel_backoff_non_e_preso_in_carico`, `test_segnalazione_nel_backoff_dopo_un_keepalive_caduto_porta_al_login_non_al_keepalive`
  - D2c (D2: errore nel backoff rifiutato (perso)): **2 rossi**, ripristino sha256 identico; rossi: `test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo`, `test_segnalazione_nel_backoff_dopo_un_keepalive_caduto_porta_al_login_non_al_keepalive`
  - D2d (D2: nel backoff il giro torna ad ADESSO): **2 rossi**, ripristino sha256 identico; rossi: `test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo`, `test_segnalazione_nel_backoff_dopo_un_keepalive_caduto_porta_al_login_non_al_keepalive`
  - D2e (D2: fuori dal backoff il giro NON e' piu' anticipato): **3 rossi**, ripristino sha256 identico; rossi: `test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo`, `test_fuori_dal_backoff_segnala_anticipa_ad_adesso_come_oggi`, `test_parita_custode_di_oggi_stesso_copione`

  Totale: **7 su 7 rosse**, ripristino identico (copia del repo presa prima dei soli ritocchi ASCII alle docstring). Le
  altre 115 mutazioni di `mutazioni_a1.py` NON sono state rilanciate (il codice che colpiscono non e' cambiato): le loro
  stringhe sono ancora tutte presenti (controllo automatico: 122/122 trovate). Comando:
  `python3 -P mutazioni_a1.py <copia> <uscita.json> S16 S27 D2a D2b D2c D2d D2e`; esiti in `falsificazione_decisione2.json`.

### 10.2 Decisione 1 - una sola sessione per tutta l'app (solo documento)

Nessun aggancio adesso. Sezione «Sessione unica dell'app (decisione 10/10)» in `Betfair/nucleo/betfair/doc/A1_SESSIONE_REST.md`
(par. 6-ter): come i servizi otterranno il client dal custode unico (nello stesso processo: `sessione_del_processo()`; negli
altri processi: prestito del token con la generazione, mai login ne' keepAlive propri) e l'elenco dei 15 punti di login di
oggi (file:riga verificati su `d073ddcb`: `auth.py`, `odds_refresh`, `omega_market`, Mike, Safe bot e scanner, `order_exec`,
runner calcio e tennis con i due relogin diretti del tennis, scalper, il job tennis `betfair_tennis_odds.py:307-308`, script)
da sostituire all'ondata 2. Il par. 8.5 (proposta) diventa la decisione; la scelta del processo che tiene il custode resta al
coordinatore all'aggancio.

### 10.3 Dopo la revisione indipendente di `2d38504f` (PASSA sul codice; due lavori di TEST)

Commit nuovo sopra `2d38504f` (nessuna riscrittura, nessun push). Codice di produzione del nucleo NON cambiato: solo test,
mutazioni e documenti.

- **Test instabile corretto** `test_a1_correzioni.py::test_chiudi_aspetta_il_keepalive_in_volo_prima_del_logout`: misurava la
  morte del thread (`assert not t.is_alive()`), non la proprieta'; al thread restano `_notifica()` e lo smontaggio dopo il
  lucchetto. Ora: `assert finto.in_volo["keepAlive"] == 0` (correzione del revisore). Prova di ripetizione SOTTO CARICO (4
  processi da 25 ripetizioni in parallelo + un giro dei test TLS del comparto): **vecchia asserzione 2 rossi su 100, nuova 0
  su 100**; X06 (`chiudi` senza `_lock_custode`) ancora **rossa** su questo test.
- **Stesso schema cercato nel comparto** (`is_alive` senza `join`, sleep fissi prima di un'asserzione su un altro thread):
  corretti 3 test in `test_a2_flusso_ladder_revisione.py` (vedi referto W1-A2 par. 14). Lasciati, con la causa: le
  asserzioni `is_alive` dopo `join(...)` o dopo `ferma()` (che fa `join`) sono gia' deterministiche;
  `test_a1_rest_revisore.py::test_misura_keepalive_regolare_sotto_carico` (3 s di orologio vero, 8-11 keepAlive) e' una
  MISURA del ritmo del custode sotto carico, non riducibile a una condizione senza cambiarne il senso: verde in tutti i giri
  del revisore e miei, resta un rischio dichiarato.
- **Prove del revisore riscritte nel repo** (`tests/test_a1_decisione2_revisione.py`, 5): 5 thread in corsa che segnalano e
  fanno girare il custode mentre l'orologio avanza a passi di 1 s (3 giri; attese su condizioni, mai sleep fissi: la
  versione del revisore aspettava 0,3 s prima di fermare i thread e poteva perdere il relogin sotto carico); stato interno
  identico al custode di oggi fuori dal backoff; `segnala_errore` aspetta il keepAlive in volo (misurati 0,50 s con
  keepAlive lento 0,5 s; il revisore 0,40 s): la proprieta' e' "al ritorno nessun keepAlive in volo".
- **R7 del revisore** (`segnala_errore` senza `_lock_custode`): la gara che il lucchetto chiude resta non provocabile in modo
  deterministico (dichiarato), ma il suo effetto osservabile si': nuova mutazione **D2f** = R7, **rossa** sul test sopra.
  Nota d'uso nel doc A1 par. 6-bis: il thread dello stream che chiama `segnala_errore` puo' aspettare un keepAlive o un login
  in volo.
- **Mutazioni rilanciate sul posto** (senza copia del repo, per il disco; file ripristinati con sha256 identico) sui test
  A1 di sessione, correzioni e decisione 2: X06, D2a-D2f, S16, S27 = **9 su 9 rosse** (`falsificazione_revisione_d2.json`).
- Prove: cartella `Betfair/nucleo/betfair` lanciata **5 volte di fila: 5 su 5 verdi, 426 test ciascuna** (415 + 11 nuovi).

**Prove finali (D-A)**: test del comparto A `python -m pytest Betfair/nucleo/betfair -q -p no:cacheprovider` = **415 verdi** (395 di prima + 20 nuovi: 5 decisione 2, 8 gestore unico, 7 cadenza); suite intera UNA volta, `python -m pytest Betfair/ -q -p no:cacheprovider` = **12.953 verdi, 0 rossi, 101 saltati, 6 xfail** in 833 s (integrazione dell'ondata 1: 12.933 + i 20 nuovi).

**Prove dopo la revisione (D-A)**: comparto A 5 volte di fila = 5 su 5 verdi (426 test); suite intera UNA volta, `python -m pytest Betfair/ -q -p no:cacheprovider` = **12.964 verdi, 0 rossi, 101 saltati, 6 xfail** in 692 s (12.953 + gli 11 test nuovi).
