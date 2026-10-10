# A1 - Sessione e REST Betfair (comparto A, tappa T5) - COSA FA

Agente W1-A1, ondata 1 (09/10/2026). Schema di `04_ARCHITETTURA_OBIETTIVO.md` par. 2.4. Codice NON agganciato all'app
(regola dell'ondata 1): nessun file esistente lo importa. Referto: `ARCHITETTURA_2026-10/ondata1/W1-A1/REFERTO.md`.

## 1. Scopo

UNA sessione Betfair per processo e UN solo punto per le chiamate REST, al livello di un tool professionale, con le
regole del .it:

- `sessione.py` - `SessioneBetfair` (implementa `contratto.Sessione`): un login, un custode (quello di oggi,
  `auth.CustodeSessione`, riusato), keepAlive .it entro i 20 minuti (`identitysso.betfair.it/api/keepAlive`), backoff
  15/30/60 s, relogin su `INVALID_SESSION_INFORMATION`/`NO_SESSION` o al 90% della vita, FRENO dei login per conto a
  livello di processo (`freno_del_conto`: 10 riusciti e 20 tentativi al minuto di serie; ban di Betfair = 20 minuti + 30 s
  senza tentativi, ricordato anche se la sessione si chiude e si riapre), un solo relogin anche se piu' thread vedono lo
  stesso errore (contatore di generazione che non riparte mai), nessun relogin durante il backoff del custode
  (`in_backoff()`) ne' da `rifai_login` ne' da `segnala_errore` (decisione 2 dell'utente, 10/10), evento
  `sessione_rifatta`, thread del custode solo con `avvia()`. Due lucchetti: `client()` con la
  sessione gia' fatta non ne prende nessuno (una cancellazione non aspetta un keepAlive in volo).
  `sessione_del_processo()` = l'istanza unica del processo.
- `rest.py` - `ClienteRestBetfair` (implementa `contratto.ClienteRest`): `lettura` ritentabile con la classificazione
  degli errori di oggi; `mutazione` (place/cancel/replace/update) MAI ritentata su errore generico (parita' con
  `omega_market.call_mutating`: una ripetizione, con gli stessi parametri, solo dopo un rifiuto di sessione dichiarato e
  un relogin riuscito; il rifiuto si legge da `str(e)` e `__cause__`, MAI dal `__context__`: `rifiuto_di_sessione`);
  suddivisione automatica di `listMarketBook`/`listMarketProfitAndLoss` sotto i 200 punti con la proiezione chiesta; al
  massimo 3 richieste concorrenti per conto sui metodi contesi; keep-alive e gzip di betfairlightweight su UNA
  `requests.Session`.
- `limiti.py` - i limiti ufficiali (02 par. 3.2-3.3) come dati e le funzioni pure di calcolo.
- `salute.py` - `SaluteBetfair`: contatori in memoria (login, keepAlive, relogin, frenati, ban, esiti per metodo,
  ritenti, attese sul tetto, latenza per metodo p50/p99 con l'istogramma del modulo Salute).

## 2. Entrate

- Configurazione di oggi (`config.py` via `Betfair/stream/auth.build_client`, importato dentro i metodi).
- Orologio monotono (iniettabile), parametri: `periodo_keepalive_s` (480), `ritenti_s` (15/30/60), `FrenoLogin`,
  `PoliticaLettura` (2 tentativi, pausa 1 s), `concorrenti_per_conto` (3), `attesa_tetto_s` (30), `pausa_tra_blocchi_s` (0),
  `blocco_massimo` ({metodo: n}), `rifai_mutazione_su_sessione` (True).
- Chiamate: `lettura(metodo, **kwargs)` (un `market_ids` stringa vale come lista di un id) / `mutazione(metodo, **kwargs)` con i nomi Betfair (`listMarketBook`...) e i
  parametri di betfairlightweight (`market_ids`, `price_projection`, `lightweight`...).
- Errori visti altrove (stream): `segnala_errore(exc)`.

## 3. Uscite

- `client()`: l'`APIClient` di betfairlightweight con sessione valida.
- Risultati di betfairlightweight (risorse o dict); per le richieste suddivise la lista concatenata nell'ordine dei
  `market_ids`. Eccezioni: `BetfairLimitHit` (riusata da `odds_refresh`) sui limiti, `LoginFrenato`, `CodaContoPiena`,
  `BetfairStreamAuthError` (primo login fallito, come `build_client`), le eccezioni di betfairlightweight altrimenti.
- `stato()` della sessione e della salute (mai il token); evento `sessione_rifatta` ai consumatori registrati.
- Inoltro facoltativo al modulo Salute (`conta`/`tratto`) con gruppi propri: `betfair_sessione`, `betfair_rest_esiti`,
  tratti `a1_rest_ms.<metodo>` e `a1_attesa_tetto_ms`.

## 4. Dipendenze ammesse

`betfairlightweight`, `requests` (solo attraverso il client), libreria standard; codice di oggi importato per RIUSO di
funzioni pure o gia' certificate: `Betfair.stream.auth` (`build_client`, `CustodeSessione`, `e_errore_di_sessione`,
`_descrivi_errore`, `safe_logout`, `BetfairStreamAuthError`), `Betfair.odds_refresh` (`_is_limit`, `LIMIT_MARKERS`,
`BetfairLimitHit`), `Betfair.monitor.registro.Istogramma`. Nessun import di bot (in particolare NON `omega_market`).
Importare i quattro moduli non apre file, socket o thread (provato: solo libreria standard e `Betfair.monitor.registro`
al caricamento).

## 5. Funzionalita' coperte (id di `01_FUNZIONALITA.md`) e test che le provano

| Id | Cosa | Test |
|---|---|---|
| A-001 | login certificato .it, `requests.Session` riusata | `test_a1_sessione::test_endpoint_e_certificati_come_oggi`, `test_a1_rest::test_keep_alive_gzip_e_una_sola_sessione_http` |
| A-002 | keepAlive senza token nei log | `test_a1_sessione::test_parita_custode_di_oggi_stesso_copione`, `test_stato_senza_token_con_tutte_le_chiavi` |
| A-003 | errore di sessione riconosciuto | `test_a1_rest::test_classificazione_coincide_con_le_funzioni_di_oggi` |
| A-004 | descrizione errore senza token | idem (caso col token nel testo) |
| A-005 | custode: periodo, backoff, relogin al 90%, `stato()` | `test_parita_custode_di_oggi_stesso_copione`, `test_contatori_della_salute_seguono_il_copione`, `test_custode_tiene_viva_la_sessione_oltre_i_20_minuti`; backoff rispettato anche da `segnala_errore` (decisione 2): `test_a1_decisione2_backoff` (5 test) |
| A-006 | logout | `test_una_sessione_per_processo_un_login_con_dieci_thread` |
| A-007/A-008 | login e RPC con ritenti (oggi `client.py`) | sostituiti da A-001 + `lettura`: `test_lettura_errore_di_rete_un_ritento_con_pausa`, `test_lettura_due_errori_di_rete_rilancia`, `test_reperto_rest_del_runner_muore_a_20_minuti` |
| A-009..A-011 | `listEvents`, `listMarketCatalogue`, `listMarketBook` | `test_list_market_book_parita_col_ripiego_dello_scanner`, `test_letture_non_suddivise_passano_intere`, griglia di suddivisione |
| A-012 | `placeOrders` [$] | `test_mutazione_mai_ritentata`, `test_mutazione_riuscita_una_richiesta_esito_vero`, `test_parita_mutazioni_con_call_mutating`, `test_a1_rest_revisore` (relogin di un altro thread, `except` di sessione), `test_a1_correzioni::test_rifiuto_di_sessione_mai_dal_contesto` |
| A-013/A-014 | `listCurrentOrders`/`listClearedOrders` (senza paginazione: resta al chiamante) | `test_tre_concorrenti_per_conto_sui_metodi_contesi` |
| A-015 | Account API | `test_letture_non_suddivise_passano_intere` (`getAccountFunds`) |
| A-016 | sessione REST condivisa per processo, relogin, stop pulito al limite | `test_una_sessione_per_processo_un_login_con_dieci_thread`, `test_lettura_limite_stop_pulito_mai_ritentata`, `test_parita_letture_con_odds_refresh_with_client` |
| A-040, A-071, A-081, D-012, E2-088, E3-S17, I-048 | keepAlive per processo (runner idle, tennis, scanner, bot) | un solo custode: `test_custode_tiene_viva_la_sessione_oltre_i_20_minuti`, `test_thread_del_custode_solo_con_avvia_e_si_ferma` (aggancio in ondata 2) |
| A-078 | ripiego REST `poll_books` a blocchi | `test_blocco_massimo_e_pausa_fra_blocchi`, `test_blocco_massimo_riproduce_i_blocchi_di_oggi` |

Restano al codice di oggi: A-017/A-018 (prodotto «Aggiorna quote» e la sua coda), A-019 (cambio GBP->EUR), A-021/A-022
(catalogo per evento e `_catalog_events`: useranno `lettura("listMarketCatalogue")` nell'aggancio).

## 6. Interruttore previsto

`ARCH_SESSIONE=vecchio|ombra|nuovo` (A P1 `SESSIONE_UNICA`), di serie `vecchio`. Dettaglio per punto nel referto par. 8.

## 6-bis. Contratto d'uso per chi chiama (W1-A2 stream, comparto C ordini)

- **`rifai_login(errore, generazione_vista)`**: la `generazione_vista` va CATTURATA quando la connessione (stream) parte
  (`gen = sessione.generazione` subito dopo `client()`), NON letta al momento dell'errore. Letta all'errore, 5 errori
  scaglionati della stessa connessione fanno 5 login invece di 1 (`test_a1_correzioni::test_contratto_d_uso_generazione_catturata_alla_connessione`).
  `rifai_login` non fa login durante il backoff del custode (`in_backoff()`).
- **`segnala_errore(errore)`** (errore di sessione visto dallo stream) RISPETTA il backoff come `rifai_login`
  (**decisione 2 dell'utente, 10/10/2026: «si', sempre una sola connessione»**). Fuori dal backoff anticipa il giro dopo ad
  ADESSO, come il custode di oggi (`auth.py:214-224`). DURANTE il backoff dopo un login fallito l'errore e' preso in carico
  (ritorna True, la sessione e' segnata da rifare: a fine attesa il custode fa il LOGIN, non il keepAlive) ma il giro resta
  alla fine dell'attesa: il relogin parte allora, mai prima. Un errore NON di sessione non e' preso in carico (False). La
  chiamata prende il lucchetto del custode (controllo del backoff e presa in carico non si intrecciano con un login che
  fallisce in quel momento): chi chiama puo' aspettare un keepAlive o un login gia' in volo. Prova:
  `test_a1_decisione2_backoff::test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo` (5 thread che
  segnalano durante l'attesa: 0 login prima della fine, 1 dopo). Divergenza VOLUTA dal custode di oggi, che scavalca
  l'attesa (`auth.CustodeSessione.segnala_errore`, usata da `safe_strategy/service.py:755,2975,3000,3088`): all'aggancio
  quelle chiamate passano dalla sessione nuova e prendono la regola nuova.
- **Mutazione caduta per timeout DOPO l'esecuzione su Betfair**: A1 manda UNA richiesta e rilancia l'eccezione; non
  riconcilia e non ripete. Sapere se l'ordine c'e' e' compito del comparto C: riconciliazione per `customerOrderRef`
  (stream degli ordini del conto, `listCurrentOrders`), MAI un secondo invio.
- **Dopo ogni mutazione tornata** l'adattatore dell'aggancio chiama `_segnala_saldo("ordine")` come `call_mutating` oggi.

## 6-ter. Sessione unica dell'app (decisione 10/10)

**Decisione 1 dell'utente (10/10/2026): «si', una sola sessione per tutta l'app».** Il custode di questo comparto
(`SessioneBetfair`: login, keepAlive .it, backoff, freno, relogin una volta sola) e' l'UNICO punto di login e di keepAlive;
all'aggancio (ondata 2) nessun servizio fa piu' login proprio. Qui solo il documento: nessun file di produzione toccato,
nessun aggancio fatto.

**Come i servizi otterranno il client (ondata 2).** Due casi, perche' l'architettura obiettivo tiene 7 servizi in processi
separati (`04_ARCHITETTURA_OBIETTIVO.md` par. 5.1: isolamento del guasto sui soldi):

1. *Nello stesso processo del custode*: `sessione_del_processo().client()` per l'`APIClient` e
   `ClienteRestBetfair(sessione_del_processo())` per ogni chiamata REST (pesi, 3 concorrenti, blocchi). Gli stream
   (W1-A2 `GestoreFlussi`, `FlussoOrdiniContoBetfair`) prendono la stessa sessione e si registrano con
   `alla_sessione_rifatta(cb)`; su `INVALID_SESSION_INFORMATION`/`NO_SESSION` chiamano `rifai_login(exc, generazione_vista)`
   (REST) o `segnala_errore(exc)` (stream), mai `login()`.
2. *Negli altri processi* (finche' restano processi a parte: Mike, Omega, Safe bot, scanner, scalper, il job tennis):
   **prestito del token**. Il processo del custode tiene la sola sessione; gli altri costruiscono l'`APIClient` di oggi SENZA
   login (`auth.build_client(login=False)`) e ricevono il token dal custode sul canale locale 127.0.0.1 (betfairlightweight:
   `APIClient.set_session_token`), con la sua `generazione`. Su un errore di sessione chiedono il token nuovo dichiarando la
   generazione vista (stessa regola di `rifai_login`: UN relogin del custode per tutti, mai durante il backoff); non fanno
   ne' login ne' keepAlive (la vita .it di 20 minuti la tiene il custode per tutti: per la regola ufficiale solo keepAlive e
   login la prolungano, `limiti.VITA_SESSIONE_ITALIA_S`). Il token non va mai nei log ne' nello `stato()`. Da costruire
   all'ondata 2 come `Sessione` del contratto (stesso protocollo: `client()`, `rinnova_se_serve()` che non fa nulla,
   `stato()`), con test di parita' e di caduta del processo del custode (i servizi aspettano il token nuovo, nessuno fa
   login da solo). Il processo che tiene il custode lo sceglie il coordinatore all'aggancio (quello che vive di piu': il
   supervisore, se puo' importare betfairlightweight; altrimenti il primo servizio avviato).

Risultato atteso: **1 login e 1 keepAlive per tutta l'app** (oggi uno per processo piu' i relogin di ogni copia, fino a 13
processi insieme: referto W1-A1 par. 9 punto 12); il freno dei login per processo diventa un freno per l'app; il ban di 20
minuti per troppi login non e' piu' raggiungibile da un ciclo impazzito in un solo servizio.

**I login di oggi da sostituire all'ondata 2** (righe verificate sul commit base `d073ddcb`; "processo" = chi lo esegue,
`desktop/main.js:419-480`):

| # | Dove (file:riga) | Cosa fa oggi | Processo | All'aggancio |
|---|---|---|---|---|
| 1 | `Betfair/stream/auth.py:33-75` `build_client(login=True)` (`client.login()` a `:75`) | il costruttore di tutti i login dello stream | tutti quelli sotto | resta come fabbrica con `login=False` (lo usa gia' `_fabbrica_di_oggi`); il login lo fa solo il custode |
| 2 | `Betfair/stream/auth.py:244` `CustodeSessione.tick` -> `client.login()` | relogin del custode di OGNI processo | runner calcio, runner tennis, scanner, scalper | un solo custode (questo); gli altri custodi spariscono |
| 3 | `Betfair/odds_refresh.py:66-67` `_get_client` (`BetfairClient().login_cert()`), relogin con `_reset_client` in `_with_client` `:78-92`, pubblici `get_shared_client`/`reset_shared_client` `:95-102` | sessione JSON-RPC "condivisa" ma PER PROCESSO, relogin anche su errore di RETE | ogni processo che la usa (righe 4-6 e 8) | `get_shared_client()` = adattatore sopra `ClienteRestBetfair` (referto W1-A1 par. 8.2), nessun login |
| 4 | `Betfair/omega/omega_market.py:62-78` `get_client`/`call` e `:89-109` `call_mutating` (relogin con `reset_shared_client`), `:140-150` `keep_alive` (listEventTypes ogni 600 s, che sul .it NON rinnova: reperto in `test_a1_sessione`) | sessione di Omega per letture e ordini | omega-service | adattatore della riga 3; il "keepAlive" con `listEventTypes` sparisce |
| 5 | `Betfair/mike/service.py:130-150` (`_RealMarket`: la sessione di `omega_market` nel processo Mike, lucchetto 47319) | ordini e letture di Mike: un login in piu' (processo separato) | mike-service | come riga 4 |
| 6 | `Betfair/safe_strategy/bot_service.py:54` e `:11232`, `Betfair/safe_strategy/execution.py:1561` (`omega_market`) | ordini del Safe bot | safe-strategy-bot | come riga 4 |
| 7 | `Betfair/safe_strategy/service.py:3370` `build_client(login=True)` (+ custode del servizio; `segnala_errore` a `:755,2975,3000,3088`) | scanner: login + custode 900 s | safe-strategy-service | token prestato (o `sessione_del_processo(periodo_keepalive_s=900)` se il custode vive li') |
| 8 | `Betfair/order_exec.py:126-138` `_call` (relogin con `reset_shared_client`) | ordini manuali dalla UI | il processo che serve `order_exec` | adattatore della riga 3 |
| 9 | `Betfair/stream/runner.py:2710-2711` `BetfairClient().login_cert()` (sessione `rest` SENZA keepAlive ne' relogin: reperto) e `:2712` `build_client(login=True)` | DUE sessioni nello stesso processo | runner-calcio | una: `ClienteRestBetfair(sessione)` per il `rest`, la stessa sessione per flumine |
| 10 | `Betfair/stream/tennis_live/tennis_runner.py:3195` `build_client(login=True)`; relogin diretti `:839` (catalogo KO) e `:2946` (`session.trading.login()`) | login + relogin fuori dal custode | runner-tennis | sessione unica; i due relogin diretti diventano `rifai_login` |
| 11 | `Betfair/stream/scalper/scalper_session.py:1544` `build_client(login=True)` ("login DEDICATO a questo processo") | UN login per ogni partita con scalper | processo scalper per partita | token prestato (N partite = 0 login in piu') |
| 12 | `Betfair/stream/scalper/scalper_service.py:890`, `habitat_scan.py:89`, `run_scalper_live.py:230` | login del servizio e degli strumenti | scalper-service / a mano | token prestato |
| 13 | `betfair_tennis_odds.py:307-308` (`BetfairClient().login_cert()`) | il job tennis, lanciato dall'app ogni 30 min (`desktop/main.js:480`): un login a ogni lancio | job `tennis-odds` | token prestato (o assorbito nel runner tennis, `04` par. 5.1) |
| 14 | `betfair_full_odds.py:146-147`, `import_betfair_operations.py:393-394`, `Betfair/betfair_report_manager.py:68,149` | script e report: un login ciascuno | a mano / job | token prestato |
| 15 | `Betfair/stream/tennis_scalper/{record_multi.py:280, record_tennis.py:41, run_tennis_pro.py:88, run_tennis_scalper.py:219}` | script di ricerca: login proprio | a mano | token prestato (fuori dal giro h24) |

Fuori conto (non produzione): `laboratorio/`, le sonde `AUDIT_*`, `tennis_scalper/research_data.py:22` (`login=False`).
Interruttore dell'aggancio: `ARCH_SESSIONE=vecchio|ombra|nuovo` (par. 6); ombra e criterio «uguale o meglio» nel referto
W1-A1 par. 8.3 (in ombra: login e keepAlive del nuovo <= vecchio, 0 `INVALID_SESSION_INFORMATION` sul nuovo).

## 7. Come si sostituisce

Un altro `ClienteRest`/`Sessione` deve far passare `tests/test_a1_*.py` (contratto, parita', limiti, concorrenza,
falsificazioni). Il finto di Betfair (`tests/test_a1_finto_betfair.py`) e' indipendente da `limiti.py`: le regole di
Betfair le applica con una tabella sua.

## 8. Come si prova da solo

`python -m pytest Betfair/nucleo/betfair/tests -q -p no:cacheprovider -k a1` (nessuna rete: `APIClient` vero con
`HTTPAdapter` finto; gzip, keep-alive, JSON ufficiali, scadenza .it, ban dei login e tetto delle concorrenti simulati).

## 9. Misure

- Login: oggi uno per `build_client(login=True)` (12 punti) + uno per `BetfairClient` (6 punti) + relogin di
  `odds_refresh` anche sugli errori di RETE; domani uno per processo, relogin solo su errore di sessione (misura:
  `test_parita_letture_con_odds_refresh_with_client`, rete: 2 login -> 1).
- Login falliti con credenziali rifiutate: 30 letture = 1 login fallito (prima della correzione ALTA-2: 19).
- Errori di sessione dello stream durante il backoff (decisione 2): 5 thread che segnalano = 0 login prima della fine
  dell'attesa, 1 dopo (con lo scavalcamento di oggi rimesso il login parte al primo giro: test rosso).
- Attesa di una cancellazione con un keepAlive di 1 s in volo: < 0,5 s (via veloce di `client()`).
- Richieste `listMarketBook` EX_BEST_OFFERS: blocchi da 40 invece di 25 (scanner) o 20 (`odds_refresh`): 73 mercati in 2
  richieste invece di 3 (`test_list_market_book_parita_col_ripiego_dello_scanner`); i blocchi di oggi restano
  riproducibili con `blocco_massimo`.
- Latenze per metodo p50/p99 sugli stessi secchi del monitor (`salute.py`).

## 10. PROCESSO_STANDARD_BOT.md par. 6/7

Sollecitate: 6.6 (concorrenza e limiti: 3 concorrenti per conto con thread veri, 200 punti, 100 login/min), 6.7
(falsificazione: mutazioni nel referto), 6.8 (referto riproducibile: comandi e sha256), 7 n.9 (letture dei prezzi
come dict, `available_to_back[0]["price"]`), n.20 (sessione «viva» non vuol dire valida: scadenza .it simulata), n.27
(finti con chiavi e tipi del vero: JSON ufficiali e oggetti veri), n.29/n.30/n.35 (ogni test visto rosso). Le altre voci
⊘: riguardano bot, banco, ordini simulati, DB e UI, che questo comparto non tocca (causa per voce nel referto).
