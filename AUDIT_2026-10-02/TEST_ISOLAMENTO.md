# Isolamento di due test fragili (02/10/2026)

Ramo `test-isolamento` da master `d56bb3b`. Solo conftest dei test: **nessuna
condotta di produzione cambiata**, nessuna funzione di produzione aggiunta.
Interprete: `.venv` del checkout principale (percorso assoluto), nessuna junction.

## (a) `Betfair/omega/tests/test_ref_strategia_per_attore_r1_2026_09_24.py::test_omega_piazza_con_omega_come_prima`

**Sintomo.** Rosso dopo `Betfair/mike` nella stessa sessione, verde da solo:
`assert ['mike', 'mike'] == ['omega', 'omega']` (Omega piazza col ref di Mike).

**Causa esatta.** `Betfair/mike/service.py:132-133`
(`_RealMarket._bind_strategy_ref`) scrive direttamente
`omega_market.CUSTOMER_STRATEGY_REF = "mike"` sulla costante di modulo
del vero `Betfair/omega/omega_market.py` (letta a `omega_market.py:39`,
`ref_di_strategia`). In produzione Mike è un processo separato e non deve
ripristinarla; in pytest resta `"mike"` per tutti i test successivi, e
nessuna fixture la rimetteva a posto. La chiamano place/cancel/
`list_current_orders`/`list_cleared_orders` dello sportello di Mike
(`service.py:146,164,186,194,201`).

**Inquinatore minimo (trovato per bisezione file → test):**
`Betfair/mike/tests/test_mike_p4_ordini_2026_09_29.py`, nei 6 test
`test_rilettura_alla_riapertura_con_lo_sportello_vero[*]` (5 parametri) e
`test_sospensione_e_riapertura_in_live_dice_cancellata_da_betfair`: passano da
`S._real_market` → `_rileggi_ordine_appoggiato` → `list_current_orders` →
`_bind_strategy_ref`. Ciascuno da solo, seguito dal test di Omega, lo rende rosso.
(Gli altri 5 file di Mike che nominano `_RealMarket` non inquinano: usano finti.)

**Correzione.** `Betfair/conftest.py:79-107`, nuova fixture autouse
`_ripristina_ref_di_strategia_omega_market`: fotografa
`omega_market.CUSTOMER_STRATEGY_REF` prima del test e la ripristina dopo (se il
modulo è stato importato durante il test, la rimette a `omega_market._REF_OMEGA`,
il ref di Omega fissato all'import). Non importa il modulo se nessuno l'ha
importato (stesso schema di `_kill_switch_del_db_senza_rete`). Messa nel
conftest di `Betfair/` e non in quello di Mike perché chiunque chiami lo
sportello vero di Mike, da qualunque cartella, sporca la stessa costante (stesso
criterio della fixture R-4 su `flumine.config`).

## (b) `Betfair/safe_strategy/tests/test_audit_2026_09_11.py::test_l4_la_guardia_combo_decide_UGUALE_in_paper_e_in_live`

**Sintomo.** Rosso da solo **e anche col solo suo file** (1 failed, 69 passed);
verde nella cartella intera. `assert n_pap == n_liv` → `1 == 0`: in live la
seconda gamba della combo finisce in `canale_giu:apertura_non_inviata`
(log `canale di comando ws://127.0.0.1:47331/comando/safe non disponibile`).

**Causa esatta (strumentata con una sonda temporanea, poi cancellata).**
1. `Betfair/safe_strategy/tests/conftest.py:31-32` (master) faceva
   `monkeypatch.delenv("SAFE_ORDINI_VIA_CANALE")` (e la variante tennis):
   la variabile restava **assente**, annullando lo `"0"` messo da
   `Betfair/conftest.py::_ambiente_neutro_canali_e_db`.
2. Durante il giro live, `_esegui_combo_riservata` importa per la prima volta
   `Betfair.stream.config_stream` (con `controls`, `risk_engine`, `ladder_canale`):
   `Betfair/stream/config_stream.py:16-17` esegue `load_dotenv()`, che riempie
   **solo le variabili assenti** risalendo fino al `.env` vero del checkout
   principale, dove l'interruttore è acceso. Sonda: `porta_ordini.acceso(ENV_CANALE)`
   = False prima di `_esegui_combo_riservata` live, True subito dopo, con 66
   moduli nuovi importati in mezzo.
3. Da lì `bot_service._porta_di` (`bot_service.py:868-873`) trova la porta del
   canale accesa, senza token → fail-closed sulla gamba 2.
Nella cartella intera `config_stream` è già stato importato da un test
precedente (e la `setenv` del conftest di `Betfair/` ripristina l'env a fine
test), quindi il `load_dotenv` non scatta più a metà di l4: per questo era verde.

**Correzione.** `Betfair/safe_strategy/tests/conftest.py:38-39`: `delenv` →
`setenv(..., "0")`. `"0"` è spento per costruzione (`porta_ordini.VALORI_ACCESI`)
e `load_dotenv` (senza override) non lo tocca. Nessun test di Safe distingue
"assente" da `"0"` (verificato con grep; i test che provano l'interruttore lo
impostano da sé dentro il test).

## Falsificazione
`AUDIT_2026-10-02/falsifica_test_isolamento.py` (+ `_out.txt`): rimette ciascun
conftest com'è su master (`git show master:`), pretende ROSSO, ripristina
(sha256 verificato nel `finally`) e pretende VERDE; più le direzioni incrociate.
Esito: **TUTTO COME ATTESO**.

| Passo | Combinazione | Atteso | Ottenuto |
|---|---|---|---|
| 0 | inquinatore Mike → Omega | verde | 25 passed |
| 0 | l4 da solo | verde | 1 passed |
| A | conftest Betfair di master: inquinatore → Omega | rosso | 1 failed, 24 passed |
| A | Omega da solo | verde | 1 passed |
| A | l4 da solo (B intatta) | verde | 1 passed |
| B | conftest Safe di master: l4 da solo | rosso | 1 failed |
| B | file test_audit intero | rosso | 1 failed, 69 passed |
| B | inquinatore → Omega (A intatta) | verde | 25 passed |
| 3 | ripristinato: entrambe | verde | 25 passed / 1 passed |

## Esecuzioni (dopo la correzione)
| Comando | Esito | Durata |
|---|---|---|
| l4 da solo | 1 passed | 5,8 s |
| Omega `test_omega_piazza...` da solo | 1 passed | 4,4 s |
| `Betfair/mike` + file ref Omega (la combinazione rossa) | **1431 passed** (prima: 1 failed, 1430 passed) | 46,5 s |
| `test_audit_2026_09_11.py` intero | **70 passed** (prima: 1 failed, 69 passed) | 11,5 s |
| `Betfair/omega/tests` | 434 passed, 2 skipped | 26,9 s |
| `Betfair/safe_strategy/tests` | 2088 passed, 3 skipped, 1 xfailed | 72,2 s |
| `Betfair/mike` | 1416 passed | 45,9 s |

**Ordine.** `pytest-randomly` e `pytest-reverse` non sono installati (nel `.venv`
c'è solo pytest 9.1.1). Al loro posto il plugin `AUDIT_2026-10-02/ordine_test_plugin.py`
(`-p ordine_test_plugin`, `ORDINE_TEST=inverso|casuale:<seme>`) su
`Betfair/mike` + `Betfair/omega/tests` + `test_audit_2026_09_11.py`:
inverso 1920 passed, 2 skipped (59,6 s); semi 1, 2, 3: 1920 passed, 2 skipped
ciascuno (57,8 / 57,8 / 61,1 s).

## NON VERIFICATO
- Suite intera `Betfair/` non lanciata (fuori dal perimetro): la fixture nuova
  in `Betfair/conftest.py` gira per ogni test di `Betfair/`; verificata solo su
  mike, omega/tests, safe_strategy/tests.
- Il valore dell'interruttore nel `.env` vero non l'ho letto (lettura negata dal
  sistema): la riaccensione è dimostrata dalla sonda (`acceso()` passa da False
  a True all'import di `config_stream`), non dal file.
- Rischio affine NON corretto (fuori perimetro, da segnalare): qualunque test che
  fa `delenv` di una variabile presente nel `.env` vero può vederla riaccendersi
  al primo import di `config_stream` a metà test. Esempi: `test_porta_ordini_f5_2026_09_24.py:815-816,831`
  (oggi verdi). Il rimedio generale (spegnere con `"0"` invece di cancellare) è
  quello applicato qui.
- Ordini casuali su altre cartelle (stream, tennis) non provati.
