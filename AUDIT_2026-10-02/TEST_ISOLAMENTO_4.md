# Isolamento 4 - `test_db_client_is_per_thread` rosso solo nella suite intera (02/10)

Ramo locale `test-isolamento-4` (base `4472930`), worktree `agent-acfe2e24b0b2ec3e8`.
Solo test/conftest toccati: nessuna condotta di produzione cambiata.

## Inquinatore (bisezione)

Script `AUDIT_2026-10-02/bisezione_inquinatore_4.py`, uscita `bisezione_inquinatore_4_out.txt`:
391 file che precedono `stream/tests/test_net_retry.py` nell'ordine della suite -> ROSSO
(riprodotto, 665 s); dimezzamenti fino al file
`Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py`, poi fino al test

    Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py::test_R1_main_all_arresto_chiama_l_arresto_degli_ordini

Combinazione minima: quel test + `Betfair/stream/tests/test_net_retry.py::test_db_client_is_per_thread`.

## Causa esatta

- Il test inquinatore (`test_mike_riga_assente_e_arresto_2026_10_02.py:240` e `:244`) esegue
  il `main` VERO di Mike (`S.main()`), che a `Betfair/mike/service.py:7371` chiama
  `db_client.usa_timeout_bot()` reale (il test neutralizza canale, lock, segnali, ma non questo).
- `usa_timeout_bot` (`db_client.py:59-67`) scrive `_STATO["timeout"] = httpx.Timeout(...)`
  nello stato di PROCESSO (`db_client.py:33`) e nessuno lo rimette a `None`.
- Da li' in poi `get_supabase_client` prende il ramo `create_client(url, key, options=ClientOptions(...))`
  (`db_client.py:83-84`); il finto del bersaglio `_mk(url, key)` (`test_net_retry.py:189`)
  non accetta `options` -> `TypeError: _mk() got an unexpected keyword argument 'options'`.
- Non c'entrano `_TLS` (il bersaglio lo rimpiazza con `monkeypatch`), thread vivi o
  `sys.modules` duplicati (`db_client` si importa solo come `db_client`).
- Nota: il bersaglio e' del 28/09 (`3e96c82`), l'inquinatore e' entrato oggi con `09072ca`
  (14:11): il rosso e' "preesistente" alla sessione di audit ma nato oggi.

## Correzione (alla radice, in `Betfair/conftest.py`)

Fixture autouse `_ripristina_stato_di_processo_di_db_client`: se `db_client` e' gia'
importato (mai importato da qui) fotografa l'oggetto `_STATO` e il suo contenuto, l'oggetto
`_TLS` e il contenuto di `_TLS` del thread del test; a fine test li rimette (oggetto e
contenuto). Se il modulo e' stato importato DURANTE il test, `_STATO` torna allo stato di
import (`{"timeout": None}`). Copre ogni test presente e futuro che chiama il `main` vero di
un bot (Mike, Omega `omega_service.py:8517`, Safe `bot_service.py:10451`, scanner
`safe_strategy/service.py:3363`). Nessuna funzione di reset aggiunta in produzione.
Nessun riordino, xfail o skip.

## Falsificazione

`AUDIT_2026-10-02/falsifica_test_isolamento_4.py` -> `falsifica_test_isolamento_4_out.txt`:

| passo | esito |
|---|---|
| con correzione | VERDE (2 passed) |
| fixture tolta dal testo del conftest | ROSSO, `TypeError ... 'options'` |
| byte originali rimessi (`finally`) | VERDE (2 passed) |
| sha256 prima/dopo | `602b3831...139d59` identico |

## Esecuzioni (con correzione, nel worktree)

| cosa | esito |
|---|---|
| bersaglio da solo | 1 passed |
| combinazione minima | 2 passed |
| inquinatore + `test_db_client_timeout_bot_2026_09_28.py` + `test_net_retry.py` | 38 passed |
| `Betfair/stream/tests` intera | 3416 passed, 25 skipped, 331 s |
| suite intera `Betfair` (una volta) | **9555 passed, 0 failed**, 31 skipped, 9 xfailed, 443 s (`suite_isolamento_4.txt`) |

Totale raccolto identico a master (9595 = 9555+31+9 qui; 9585+1+9 sul principale). I 31
skipped compaiono anche nella corsa di bisezione SENZA correzione (391 file, 31 skipped):
sono d'ambiente del worktree (file non versionati assenti), non effetto della correzione.

## Altri candidati cercati (grep, punto 5)

- Sostituzioni di `_TLS`: solo `test_net_retry.py:194` e `test_db_client_timeout_bot_2026_09_28.py:28`,
  entrambe via `monkeypatch` (ripristinate). `_STATO`: solo quest'ultimo, via `monkeypatch`.
- Altri `main()` veri chiamati dai test: `test_p_blocco3_2026_09_28.py:65` (Omega) neutralizza
  `usa_timeout_bot` con `monkeypatch` (pulito); `test_backtest_opportunity.py:153` e' il main
  del backtest, non tocca `db_client`.
- Thread senza `join` (tutti `daemon`, nessuno tocca `db_client`, non sono la causa, non toccati):
  `safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py:928` (server ws `serve_forever`),
  `stream/tests/test_frammenti_tcp_2026_09_28.py:116,125` (server TCP finto),
  `stream/tests/test_banco_scalper_sniper_2026_09_28.py:160` (target vuoto, termina subito).

## NON VERIFICATO

- La suite intera e' girata sulla base `4472930`, non sull'ultimo master (`c0e3feb`, che ha
  cambiato `banco_comune.py` e altri file); il merge del ramo su master e' pulito
  (`git merge-tree`), ma la suite su master+correzione non l'ho rilanciata.
- Elenco preciso dei 31 skipped del worktree (non rilanciato con `-rs`).
- La patch e' `git diff master...HEAD` (dalla base comune): `git diff master` a due punti
  includerebbe al contrario i commit arrivati su master dopo la base.
- Il test inquinatore resta com'e' (chiama `usa_timeout_bot` vero): la scelta di
  neutralizzarlo anche li' con `monkeypatch` e' lasciata al coordinatore.
