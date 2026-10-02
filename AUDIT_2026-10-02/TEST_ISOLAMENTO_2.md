# Isolamento dei test, seconda parte (02/10/2026)

Ramo `test-isolamento-2`, partito da master `c0505ff` e poi portato sull'ultimo master. Si toccano solo i conftest e i test: **nessuna condotta di produzione cambiata** e nessuna funzione di produzione aggiunta.

STATO AL 13:45: fatto tutto (casi c, d, e, f, falsificazione, giri d'ordine, suite intera). Manca solo la revisione del coordinatore.

## (c) `test_audit_2026_09_11.py::test_l14_ttl_della_cache_lambda`

È verde da solo e rosso dopo il batch di 32 file.

**Inquinatore minimo**, trovato per bisezione file per file e poi test per test: `Betfair/omega/test_omega_greenup_2026_09_10.py::test_trigger_gol_esce_dopo_assestamento_e_marca_le_due_righe`, cioè ogni test di quel file che usa la fixture `lambdas`.

**Causa.**
- `Betfair/omega/omega_service.py:1000` definisce `_LAMBDA_CACHE`, la cache di processo dei lambda per `event_id`. La scrive `_prematch_lambdas` (riga :1238) e la legge per prima (riga :1143).
- La catena di Safe parte proprio da qui: `Betfair/safe_strategy/bot_service.py:7220` (`resolve_event_lambdas`) chiama `_prematch_lambdas` di Omega come primo anello.
- `svuota_le_cache` di Omega non la svuota, e nessuna fixture lo faceva a fine test.
- Il test di Omega lascia in cache `"e1"`. l14 usa lo stesso `"e1"` e, scaduto il TTL, trova i lambda di Omega invece di rifare la sua catena: `calls["n"] == 0`.

**Correzione.** `Betfair/conftest.py`, nuova fixture autouse `_svuota_cache_lambda_di_omega`. Svuota `_LAMBDA_CACHE` a fine test, e solo se il modulo è già importato.

## (d) `delenv` di variabili presenti nel `.env` vero

**Censimento.** `AUDIT_2026-10-02/cerca_delenv_env.py` legge del `.env` solo i nomi (41) e risolve anche gli argomenti scritti come costanti. Esito: **56 siti**.

**Criterio applicato.**
- Dove il test vuole solo l'interruttore spento, `delenv` diventa `setenv(X, "0")`. Sono **35 siti in 13 file** (elenco nel commit c52f5a8). Tutte queste variabili sono già nei 20 `INTERRUTTORI_CANALE`, che `Betfair/conftest.py` mette a `"0"` di serie, tranne `SAFE_BOT_GIRO_VELOCE`, letta con `canale_scan.acceso`. Quindi `"0"` è lo spento già in uso nella suite.
- Dove il test prova proprio l'**assenza**, `delenv` resta. Sono 21 siti:
  - `test_linterruttore_di_serie_e_spento` (Mike, Omega, Safe, tennis);
  - i parametri `valore=None`;
  - `test_senza_env_il_canale_e_spento`;
  - `test_interruttore_assente_e_spento`;
  - `test_di_default_e_spento` (`MIKE_LIVE_ENABLED`);
  - `test_interruttore_spento_nessuna_porta` (porta_f5:815-816);
  - il default di `LIVE_ORDER_MODE` (con `""` `live_order_mode()` renderebbe `""`, non `"OFF"`);
  - il default di `LIVE_LADDER_CANALE_MS`, che fa anche `importlib.reload(config_stream)`;
  - `test_sync_spento_di_default` (Supabase assente);
  - `test_contesto_accende_e_rimette_l_interruttore` (verifica `not in os.environ`).

  Passarli a `setenv` avrebbe indebolito il test. Questi siti li protegge la guardia generale descritta sotto.
- **Correzione alla radice.** `Betfair/conftest.py`, fixture autouse `_nessun_dotenv_a_meta_test`: durante ogni test `dotenv.load_dotenv` non fa nulla. Il riempimento a metà test veniva da `Betfair/stream/config_stream.py:16-17` alla prima importazione o a un `reload`. Gli import fatti alla raccolta restano come prima e li neutralizza già `_ambiente_neutro_canali_e_db`.
- **Escluso dopo verifica.** `test_tennis_iscrizione_a_caldo:260` usa `IAC.ENV_INTERRUTTORE`, cioè `TENNIS_ISCRIZIONE_A_CALDO`, che non è nel `.env` e acceso di serie. Lo script di censimento l'aveva risolto per omonimia: convertirlo dava 18 test rossi, quindi è stato rimesso com'era.

## (e) Quarto caso gemello, trovato lungo la strada

`Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py::test_1_interruttore_spento_chiamate_identiche_a_prima[None]` era rosso **sul master** con il file da solo e verde nella cartella.

- **Causa:** `Betfair/stream/flusso_prezzi.py:248` tiene `_NON_NOTO_AVVISATO`, che fa scrivere l'avviso `flusso_non_dichiarato` una sola volta per processo e per bot.
- Il test confronta due corse (PRIMA e DOPO) nello stesso processo: alla prima corsa del processo la riga compare solo in PRIMA.
- **Correzione:** `_sequenza` toglie `"mike"` da quel memo prima di ogni corsa, così le due corse partono dallo stesso stato.

## (f) Quinto caso, trovato dal giro in ordine inverso

`Betfair/safe_strategy/tests/test_cert_2026_09_13.py::test_aggregati_illeggibili_bloccano_i_nuovi_ingressi` era rosso in ordine inverso.

- **Inquinatore** (bisezione con `AUDIT_2026-10-02/bisezione_inquinatore.py`): `test_aggregati_stantii_si_riusano_per_poco_invece_di_bloccare`.
- **Causa:** `bot_service._AGG_ULTIMO_BUONO` (riga :6297, scritta a :6431, riusata a :6413 entro `_AGG_TTL_S`). Con lo stesso `NOW` fisso il test trovava una lettura "recente" invece del blocco.
- **Correzione:** fixture autouse `aggregati_buoni_dimenticati` in `Betfair/safe_strategy/tests/conftest.py`.

**Altro rosso dello stesso giro.** `test_velocita_feed_2026_09_30.py::test_worker_riparte_subito_alla_sveglia_ma_non_sotto_il_pavimento` è caduto una volta. La bisezione non lo riproduce nemmeno con tutti i 22 candidati, e al giro inverso successivo è verde. Il test misura i tempi con `time.sleep` (finestre da 0,25 a 0,9 s) ed è caduto a PC carico, con il giro inverso a 225 s invece di 80 s. È **fragile per i tempi, non per l'ordine**: non è corretto qui.

## Falsificazione (`falsifica_test_isolamento_2.py` e `_out.txt`): esito «TUTTO COME ATTESO»

| Mutazione | Combinazione | Atteso | Ottenuto |
|---|---|---|---|
| C, niente svuotamento della cache lambda | greenup → l14 | rosso | 1 failed, 19 passed |
| C | l14 da solo | verde | 1 passed |
| D, `load_dotenv` attivo | sonda: `delenv` poi `reload(config_stream)` | rosso (riacceso dal `.env`) | 1 failed |
| D | sonda: `setenv "0"` poi `reload` | verde | 1 passed |
| E, memo di Mike non azzerato | file Mike da solo | rosso | 1 failed, 24 passed |
| F, `_AGG_ULTIMO_BUONO` non azzerato | stantii → illeggibili | rosso | 1 failed, 1 passed |
| F | illeggibili da solo | verde | 1 passed |

A file ripristinati tutto torna verde, con lo sha256 verificato. Le sonde controllano solo se la variabile è presente o uguale a `"0"`: il valore del `.env` non viene mai letto né stampato.

## Esecuzioni

| Esecuzione | Esito | Durata |
|---|---|---|
| Batch dei 32 file + l14 (prima: 1 failed, 1129 passed) | 1130 passed | 63,8 s |
| File di test toccati | 462 passed | 52 s |
| `Betfair/safe_strategy/tests` | 2121 passed, 3 skipped, 1 xfailed | 81 s |
| **Suite intera `Betfair/`** | **9260 passed, 31 skipped, 1 xfailed** | 549 s |

La suite intera è stata lanciata prima del caso (f): quella correzione la coprono `safe_strategy/tests` e i giri d'ordine.

**Giri d'ordine su `safe_strategy/tests`** (plugin `ordine_test_plugin.py`), tutti con 2121 passed:

| Ordine | Durata |
|---|---|
| inverso | 83,6 s |
| casuale:11 | 135,9 s |
| casuale:12 | 260,3 s |
| casuale:13 | 245,9 s |

## NON VERIFICATO

- La suite intera non è stata rilanciata dopo il caso (f), che tocca solo il conftest di Safe.
- I giri casuali coprono solo `safe_strategy/tests`, non stream, tennis, mike e omega.
- Il test di velocità del feed resta fragile per i tempi.
- Il valore delle variabili del `.env` non è mai stato letto: si conoscono solo i nomi.
- Su master non esiste una suite intera di riferimento lanciata da me con cui confrontare i 9260.
