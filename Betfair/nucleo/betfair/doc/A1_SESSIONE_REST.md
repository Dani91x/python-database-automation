# A1 - Sessione e REST Betfair (comparto A, tappa T5) - COSA FA

Agente W1-A1, ondata 1 (09/10/2026). Schema di `04_ARCHITETTURA_OBIETTIVO.md` par. 2.4. Codice NON agganciato all'app
(regola dell'ondata 1): nessun file esistente lo importa. Referto: `ARCHITETTURA_2026-10/ondata1/W1-A1/REFERTO.md`.

## 1. Scopo

UNA sessione Betfair per processo e UN solo punto per le chiamate REST, al livello di un tool professionale, con le
regole del .it:

- `sessione.py` - `SessioneBetfair` (implementa `contratto.Sessione`): un login, un custode (quello di oggi,
  `auth.CustodeSessione`, riusato), keepAlive .it entro i 20 minuti (`identitysso.betfair.it/api/keepAlive`), backoff
  15/30/60 s, relogin su `INVALID_SESSION_INFORMATION`/`NO_SESSION` o al 90% della vita, FRENO dei login (per processo
  10 riusciti e 20 tentativi al minuto di serie; ban di Betfair = 20 minuti senza tentativi), un solo relogin anche se
  piu' thread vedono lo stesso errore (contatore di generazione), evento `sessione_rifatta`, thread del custode solo con
  `avvia()`. `sessione_del_processo()` = l'istanza unica del processo.
- `rest.py` - `ClienteRestBetfair` (implementa `contratto.ClienteRest`): `lettura` ritentabile con la classificazione
  degli errori di oggi; `mutazione` (place/cancel/replace/update) MAI ritentata su errore generico (parita' con
  `omega_market.call_mutating`: una ripetizione solo dopo un rifiuto di sessione dichiarato e un relogin riuscito);
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
- Chiamate: `lettura(metodo, **kwargs)` / `mutazione(metodo, **kwargs)` con i nomi Betfair (`listMarketBook`...) e i
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
| A-005 | custode: periodo, backoff, relogin al 90%, `stato()` | `test_parita_custode_di_oggi_stesso_copione`, `test_contatori_della_salute_seguono_il_copione`, `test_custode_tiene_viva_la_sessione_oltre_i_20_minuti` |
| A-006 | logout | `test_una_sessione_per_processo_un_login_con_dieci_thread` |
| A-007/A-008 | login e RPC con ritenti (oggi `client.py`) | sostituiti da A-001 + `lettura`: `test_lettura_errore_di_rete_un_ritento_con_pausa`, `test_lettura_due_errori_di_rete_rilancia`, `test_reperto_rest_del_runner_muore_a_20_minuti` |
| A-009..A-011 | `listEvents`, `listMarketCatalogue`, `listMarketBook` | `test_list_market_book_parita_col_ripiego_dello_scanner`, `test_letture_non_suddivise_passano_intere`, griglia di suddivisione |
| A-012 | `placeOrders` [$] | `test_mutazione_mai_ritentata`, `test_mutazione_riuscita_una_richiesta_esito_vero`, `test_parita_mutazioni_con_call_mutating` |
| A-013/A-014 | `listCurrentOrders`/`listClearedOrders` (senza paginazione: resta al chiamante) | `test_tre_concorrenti_per_conto_sui_metodi_contesi` |
| A-015 | Account API | `test_letture_non_suddivise_passano_intere` (`getAccountFunds`) |
| A-016 | sessione REST condivisa per processo, relogin, stop pulito al limite | `test_una_sessione_per_processo_un_login_con_dieci_thread`, `test_lettura_limite_stop_pulito_mai_ritentata`, `test_parita_letture_con_odds_refresh_with_client` |
| A-040, A-071, A-081, D-012, E2-088, E3-S17, I-048 | keepAlive per processo (runner idle, tennis, scanner, bot) | un solo custode: `test_custode_tiene_viva_la_sessione_oltre_i_20_minuti`, `test_thread_del_custode_solo_con_avvia_e_si_ferma` (aggancio in ondata 2) |
| A-078 | ripiego REST `poll_books` a blocchi | `test_blocco_massimo_e_pausa_fra_blocchi`, `test_blocco_massimo_riproduce_i_blocchi_di_oggi` |

Restano al codice di oggi: A-017/A-018 (prodotto «Aggiorna quote» e la sua coda), A-019 (cambio GBP->EUR), A-021/A-022
(catalogo per evento e `_catalog_events`: useranno `lettura("listMarketCatalogue")` nell'aggancio).

## 6. Interruttore previsto

`ARCH_SESSIONE=vecchio|ombra|nuovo` (A P1 `SESSIONE_UNICA`), di serie `vecchio`. Dettaglio per punto nel referto par. 8.

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
