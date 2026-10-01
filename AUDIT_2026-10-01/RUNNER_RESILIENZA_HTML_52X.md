# Runner calcio morto per una pagina HTML 525 di Supabase/Cloudflare (01/10/2026)

Delegato Opus 5.5 di admin-01. Worktree `agent-a567f9902120927df`. Nessun commit, nessuna
scrittura sul DB, nessuna strategia toccata. Patch: `RUNNER_RESILIENZA_HTML_52X.patch`.

## Causa
Log `_logs/runner-calcio_2026-10-01T07-00-20-514Z.log`, alle 09:22:56: `GET live_follow` ha
ricevuto la risposta `HTTP/2 525`, con un corpo HTML ("supabase.co | 525: SSL handshake failed").
postgrest (`_sync/request_builder.py:50-55`) non riesce a leggerla come JSON (`ValidationError`
di pydantic) e solleva quindi `APIError(generate_default_error_message(r))`, con questi campi:
`code=525` (int, cioè il codice HTTP),
`message="JSON could not be generated"` e `details="b'<!DOCTYPE html>..."`.
`runner.py:2676 _attendi_se_rete` la passa a `e_errore_di_rete`, che riconosceva solo i guasti
di trasporto e quindi la rilanciava: `setup_and_run` → `_main` → rc=1, e il watchdog la registrava come «esito=crash».

## Modifica (solo `Betfair/stream/runner_lifecycle.py`, +28 righe)
- Nel ciclo cause/context di `e_errore_di_rete` c'è un caso in più: `_e_api_error_del_gateway(cur)`.
- Il nuovo helper importa `postgrest.exceptions.APIError` dentro un try/except. Restituisce True se:
  - `int(str(code))` sta in 500-504 o in 520-530, oppure
  - `message == "JSON could not be generated"` e `details` contiene `<!DOCTYPE html`.
- I codici PostgREST/PostgreSQL veri (`PGRST202`, `23514`, `42501`, `57014`, 400, None) restano
  NON di rete e vengono rilanciati.

## Runner tennis
Non serviva nessuna modifica. `tennis_runner.py:3016` (`list_pending_tennis_follows`) usa già
`e_errore_di_rete(e)`, la stessa funzione. Prima della correzione, con una APIError 525 sarebbe morto
anche il tennis (`raise`): stamattina se l'è cavata solo perché ha preso il timeout e non la 525.
Con la correzione è coperto anche lui. Non ho scritto un test dedicato al tennis: la funzione è la stessa.

## Test
Nuovo file: `Betfair/stream/tests/test_rete_gateway_html_2026_10_01.py`, 14 test. Contiene:
- (a) il dict ESATTO del log, con `code` int 525 e i primi caratteri veri dell'HTML;
- (b) 520;
- (c) "503" come stringa;
- (d/e/f) parametrizzati su PGRST202/23514/57014/42501/400/None, tutti False;
- «JSON non generato» senza HTML → False;
- HTML con codice ignoto 418 → True;
- (g) APIError come `__cause__`;
- (h) la catena di oggi riprodotta con il codice VERO di postgrest su una `httpx.Response(525)` HTML:
  verifica che `__context__` sia una `ValidationError` e che `code == 525`;
- un test su `runner._attendi_se_rete`: col 525 attende 15 s senza rilanciare, con PGRST202 rilancia.

Suite `Betfair/stream/tests` (pytest-timeout non è installato, quindi l'ho lanciata senza `--timeout`):
- PRIMA (codice HEAD, senza il file nuovo): **3199 passed, 25 skipped** (178.8 s)
- DOPO: **3213 passed, 25 skipped** (168.6 s), cioè +14 test, tutti verdi; nessuna regressione.
Restano verdi anche i test esistenti di `e_errore_di_rete` (`test_stream_stallo_2026_09_26.py`).

## Falsificazione
1. Correzione spenta (`if False and _e_api_error_del_gateway(cur)`): **7 failed, 7 passed**.
   - Rossi: test_a, test_b, test_c, test_g, test_h, html/418 e runner_calcio_non_rilancia_il_525.
   - Restano verdi solo i casi «non rete», come atteso.
2. Mutazione «ogni APIError è rete» (`return True` subito dopo isinstance): **8 failed, 6 passed**.
   - Rossi: d/e/f su tutti e sei i parametri (PGRST202, 23514, 57014, 42501, 400, None),
     «JSON non generato» senza HTML, e il PGRST202 rilanciato da `_attendi_se_rete`.
Ho ripristinato il file dalla copia e l'ho confrontato con `cmp`: IDENTICO. Dopo il ripristino: 48 passed
(file nuovo + test_stream_stallo).

## Attinenza
`git diff --stat`: tocca solo `Betfair/stream/runner_lifecycle.py` (+28) e il test nuovo (+106).

## Cosa non ho potuto verificare
- Non ho fatto una prova dal vivo con un vero 520/525 di Cloudflare. La catena è riprodotta con il codice
  di postgrest su una risposta httpx costruita a mano.
- Non ho rieseguito il replay del banco: la modifica non tocca nessuna strategia.
- Altri punti che leggono Supabase fuori da `_attendi_se_rete` e dal tennis (Mike, scanner, Omega)
  hanno retto con i loro WARNING. Non li ho analizzati uno per uno.
- La variante asincrona di postgrest (`_async`) usa la stessa `APIError`: è coperta per costruzione,
  ma non l'ho testata.
