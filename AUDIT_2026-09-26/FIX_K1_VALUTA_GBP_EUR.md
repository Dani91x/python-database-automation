# FIX K1: le size dello stream Betfair sono in GBP, ora entrano in EUR alla fonte

26/09/2026. Delegato di correzione (worktree `agent-a10f74a31fee6f30e`). Niente commit, niente DB, niente `.env`.

## 1. Reperto
- Fonte: `AUDIT_2026-09-25/e2e_fase2/ADMIN26_FEED_ATLANTE.md` sez. K1 e `E2E_FASE2_Z0_AVVIO_2026-09-26.md` K1.
- Betfair Exchange Stream API: «Market subscriptions are always in underlying exchange currency - GBP».
- Misura: size stream / size REST(EUR) = mediana 0,8599 su 94 coppie.
- Conferma in più, trovata in una registrazione reale (`_live_raw/35674515`): livelli da **0,86 / 1,73 / 2,59 / 3,45**. Sono ordini da 1 / 2 / 3 / 4 EUR visti in sterline.
- Nel repo non c'era nessuna conversione.

## 2. Causa
Tutte le fonti di book dello stream consegnano ai consumatori oggetti betfairlightweight con le size in GBP:
- runner calcio: flumine, `RawTeeMarketStream`;
- runner tennis: flumine;
- sessioni scalper: flumine;
- scanner del feed unico: bflw diretto, `Betfair/safe_strategy/stream.py`.

Il REST (`listMarketBook` senza `currencyCode`) risponde nella valuta del conto, cioè EUR, e finiva **negli stessi campi**.

## 3. Progetto (scelto prima di implementare)
Un solo modulo, `Betfair/stream/valuta.py`, con una sola funzione di conversione (`converti_libro`). La si aggancia alle fonti, prima di ogni consumatore:

| fonte | aggancio | perché lì |
|---|---|---|
| flumine (runner calcio, runner tennis, sessioni scalper) | `monta_su_flumine(framework)`: `MiddlewareValutaEur` inserito come **primo** middleware | `baseflumine._process_market_books` chiama i middleware dopo `market(market_book)` e **prima** di ogni strategia (recorder → ladder / `live_now` / canale 47331, specchio ordini, bot tennis e scalper). Essendo primo, gira anche prima del `SimulatedMiddleware`: il paper abbina su EUR, come il live. |
| scanner del feed (`source=stream`) | `StreamShard.drain()` converte ogni book | È il punto da cui i book dello stream entrano in `_apply_market_book`. `poll_books` (REST, già in EUR) non passa di qui. |
| banco di replay | `assicura_middleware_simulato(quadro)` monta lo **stesso** middleware nello **stesso** punto, a cambio fisso | Tutti i replay certificati (`certifica` → `replay_registrazioni` di Mike, Omega, Safe e scalper, `replay_bot` tennis, `trasporto_rapido`, `run_backtest`) passano da questa funzione. |

**Il cambio.** `CambioGbpEur`:
- si legge da `client.account.list_currency_rates(from_currency="GBP")` e si prende la riga EUR;
- lettura all'avvio (`CAMBIO.avvia(client)` nel main di runner calcio, runner tennis, scanner e sessione scalper), poi un thread daemon lo rinfresca ogni ora;
- cache su disco: `<LIVE_STREAM_DATA_DIR>/currency_rate.json`, cioè `_live_raw/currency_rate.json`, scritta in modo atomico;
- fallimento con un cambio già noto (Betfair o cache): si tiene l'ultimo noto e parte un alert **WARN**;
- nessun cambio noto: si usa `CAMBIO_RIPIEGO = 1/0,8586 = 1,164687` (EUR/GBP del 23/09/2026, fonte del referto K1) e parte un alert **CRITICAL** «cambio non letto» (`live_alerts`, codice `CAMBIO_GBP_EUR`);
- un valore fuori dalla banda 0,9-1,6 si scarta;
- nessuna eccezione esce mai verso il processo.

**Decisioni tecniche money-critical:**
1. **Mai modificare i livelli in place.**
   - Con flumine importato (`flumine/__init__.py`: `RunnerBookEX = EX`), `ex.available_to_back` È la lista di dict della cache di betfairlightweight.
   - I `RunnerBook` sono condivisi fra un book e il successivo (`RunnerBookCache.serialise` memorizza la risorsa). Il banco riusa perfino il `MarketBook`.
   - Per questo si sostituiscono le liste con liste nuove (`_LivelliEur`, che fa da marcatore) e si marcano runner (`_k1_eur`) e book (`size_gbp_convertite`). La conversione è idempotente per oggetto, sotto lock.
2. **Cambio congelato per mercato** (il primo visto). Il `SimulatedMiddleware` abbina il paper sul delta del `traded_volume`: un cambio che si muovesse a metà mercato creerebbe volume fantasma (size × Δcambio) a ogni prezzo.
3. **Import pigro di flumine in `valuta.py`.** Importare flumine nel processo dello scanner trasformerebbe i livelli in dict per tutto il processo (lo storico incidente citato in `scanner.livello_campo`).
4. **Cambio del banco fisso** = `CAMBIO_RIPIEGO`, sovrascrivibile con `BANCO_CAMBIO_EUR_PER_GBP`, così i referti sono riproducibili. Le registrazioni raw non portano il cambio del giorno.

**Marcatori:**
- sul book: `valuta='EUR'`, `size_gbp_convertite=True`, `cambio_gbp_eur`;
- sulla riga del feed: `payload.valuta = "EUR"`, chiave additiva, calcio e tennis;
- sul book serializzato del recorder (ladder / `live_now` / canale / file curato `<event>.jsonl`): `"valuta": "EUR"`, solo se il book è stato convertito. Se manca, è un file storico con size in GBP.

**Cosa NON cambia:**
- le registrazioni raw (tee in `raw_listener`) restano in GBP;
- nessuna soglia di strategia è stata toccata: cambia solo l'unità del dato in ingresso;
- `total_matched`, i volumi e `traded_volume` seguono la stessa regola.

## 4. Punti trovati e coperti

**Fonti di book dello stream.** Censimento con grep di `Flumine(`, `FlumineSimulation(`, `.create_stream(`, `StreamListener(` in `Betfair/` (fuori da test e tools):

| file | stato |
|---|---|
| `Betfair/stream/runner.py` (calcio: ladder, `live_now`, canale 47331, specchio ordini, paper affiancato) | **coperto** (middleware) |
| `Betfair/stream/tennis_live/tennis_runner.py` (ladder tennis, 4 bot tennis, paper affiancato) | **coperto** (middleware) |
| `Betfair/stream/scalper/scalper_session.py` (scalper, sniper, theta) | **coperto** (middleware) |
| `Betfair/safe_strategy/stream.py` (feed unico `safe_strategy_scan` + canale) | **coperto** (drain) |
| `Betfair/stream/backtest/banco_comune.py`, `trasporto_rapido.py`, `run_backtest.py` e i `replay_registrazioni` / `replay_bot` | **coperto** (`assicura_middleware_simulato`) |
| `record_multi.py`, `record_tennis.py` (registratori) | esenti: il raw resta GBP |
| `research_data.py`, `run_scalper.py`, `run_theta.py`, `backtest_pro.py`, `flb_backtest.py`, `tune_tennis.py` (laboratori) | esenti, **non convertiti** |
| `run_scalper_live.py`, `run_tennis_pro.py`, `run_tennis_scalper.py` (avviatori storici, non lanciati da `desktop/main.js`) | esenti, **non convertiti** |

**Consumatori a valle:** ora ricevono EUR senza modifiche al loro codice.
- Safe `execution.py:660-667` (chiusure): il `best_size` viene dal feed, ora EUR.
- Mike `engine.py:3335-3338`: `back_size` dal feed, ora EUR.
- Omega `omega_v3.py:834-835,1030` e `omega_service.py:6103`: dal feed, ora EUR.
- UI `frontend/src/lib/controlRoomProposte.ts:224-231,324-325`: dal canale 47331 o dallo scanner, ora EUR.
- Tutti i «prudenti» elencati in ADMIN26 K1.4:
  - scanner / engine / anomaly / combos / opportunity della Safe;
  - `omega_model`, `omega_engine`;
  - Mike `engine.py`;
  - `scalper_bot`, `theta_bot`, `sniper_bot`;
  - i 4 bot tennis;
  - `live_engine_pro`;
  - il paper `SimulatedExecution` di flumine;
  - `board_worker` (REST EUR + feed EUR: ora stessa unità).

L'elenco completo dei consumatori diretti di `available_to_back/lay`, con la fonte da cui leggono, è nel test di contratto (`_CONSUMATORI_AMMESSI`).

## 5. File toccati
- **nuovo** `Betfair/stream/valuta.py`
- **nuovo** `Betfair/stream/tests/test_valuta_k1_2026_09_26.py` (22 test, 22 passed)
- `Betfair/safe_strategy/stream.py`: import; conversione in `StreamShard.drain`
- `Betfair/safe_strategy/service.py`: import; `payload.valuta` (calcio e tennis); `CAMBIO.avvia(client)` nel `main`
- `Betfair/stream/runner.py`: import; `CAMBIO.avvia(api_client)`; `monta_su_flumine(framework)` dopo `Flumine(client=client)`
- `Betfair/stream/tennis_live/tennis_runner.py`: import; `CAMBIO.avvia(trading)`; `monta_su_flumine(framework)`
- `Betfair/stream/scalper/scalper_session.py`: `CAMBIO.avvia(trading)` e `monta_su_flumine(framework)` dopo `Flumine(...)`
- `Betfair/stream/backtest/banco_comune.py`: `assicura_middleware_simulato` monta la conversione (cambio del banco)
- `Betfair/stream/recorder.py`: marcatore `valuta` in `serialize_book`
- `Betfair/stream/tests/test_banco_comune_2026_09_16.py`: aggiunta la chiave additiva `valuta` a `PAYLOAD_VERO_CALCIO` e `PAYLOAD_VERO_TENNIS` (contratto della riga)
- `AUDIT_2026-09-26/falsifica_k1.py`, `k1_test_da_lanciare.txt`, `k1_pytest_dopo.txt`, `k1_falsificazione.txt`: referti e strumenti

## 6. Test
Tutti in `Betfair/stream/tests/test_valuta_k1_2026_09_26.py`.

**Libri usati.** I libri dello stream nascono dalla cache **vera** di betfairlightweight: `MarketBookCache.update_cache` + `create_resource`, con la `marketDefinition` di una registrazione reale. Il REST è un `MarketBook(**json)` di bflw. `CurrencyRate` è la classe vera.

**Unità:**
- `test_adattatore_converte_size_volumi_e_marca_il_libro`: 100 GBP → 116,47 EUR con 1,1647; 0,86 GBP → 1,00 EUR;
- `test_adattatore_idempotente_sullo_stesso_libro`;
- `test_lista_gia_convertita_non_si_riconverte`;
- `test_runner_condiviso_fra_book_non_si_converte_due_volte`;
- `test_la_cache_di_betfairlightweight_resta_in_gbp_anche_con_flumine`;
- `test_cambio_congelato_per_mercato`;
- `test_libro_none_non_rompe`.

**Cambio:**
- `test_cambio_letto_da_betfair_e_scritto_in_cache` (con riavvio senza rete);
- `test_rete_giu_con_cache_usa_ultimo_noto_e_warn`;
- `test_nessun_cambio_noto_usa_costante_e_critical`;
- `test_cambio_implausibile_scartato`;
- `test_avvia_non_fa_mai_cadere_il_processo`.

**Scanner (stessa unità stream / REST):**
- `test_scanner_stream_converte_alla_fonte`;
- `test_scanner_rest_non_si_converte_due_volte`;
- `test_la_riga_del_feed_dichiara_la_valuta`.

**Parità live / banco:**
- `test_runner_live_middleware_primo_e_strategia_vede_eur`;
- `test_monta_su_flumine_idempotente_e_resta_primo`;
- `test_parita_runner_banco_stesso_numero`: stesso book GBP, runner live (`Flumine` + `_process_market_books`) contro banco (`FlumineSimulation` + `MotoreReplay._a_flumine`) → stessa size EUR;
- `test_cambio_del_banco_fisso_e_riproducibile`.

**Contratto:**
- `test_contratto_ogni_fonte_di_book_dello_stream_e_convertita`: una fonte nuova non registrata, o registrata senza l'aggancio, fa diventare il test rosso;
- `test_contratto_il_banco_monta_la_conversione`;
- `test_contratto_consumatori_dei_livelli_registrati`: un consumatore nuovo di `available_to_back/lay` deve dichiarare la sua fonte.

**Marcatore:** `test_serialize_book_dichiara_la_valuta_solo_se_convertito`.

**RED → GREEN:**
- prima del cablaggio, 5 rossi: scanner, riga del feed, parità banco, 2 contratti;
- dopo il cablaggio, tutti verdi.

**Test esistenti dei moduli toccati:** 93 file, elenco in `k1_test_da_lanciare.txt`.
- Primo giro: 2 rossi.
  - Il contratto `PAYLOAD_VERO_TENNIS`, per la chiave additiva `valuta`: aggiornato.
  - Il mio test aggiungeva a mano un `SimulatedMiddleware`, vietato da `test_nessuno_nel_repo_monta_il_middleware_a_mano`: il test è stato corretto.
- Esito finale: `k1_pytest_dopo.txt` (2366 passed prima delle due correzioni) + rilancio mirato: 91 passed, 10 skipped.

Comando (PowerShell, dalla radice del worktree):
```
$env:SUPABASE_URL='http://127.0.0.1:9'; $env:SUPABASE_SERVICE_ROLE_KEY='x'; $env:SUPABASE_KEY='x'
python -m pytest Betfair/stream/tests/test_valuta_k1_2026_09_26.py -q -p no:cacheprovider
python -m pytest (Get-Content AUDIT_2026-09-26/k1_test_da_lanciare.txt) -q -p no:cacheprovider
```

## 7. Falsificazione
`python AUDIT_2026-09-26/falsifica_k1.py` (stesso ambiente, **senza timeout**). Applica 19 mutazioni una alla volta, lancia i test mirati, ripristina e verifica con sha256. Esito in `k1_falsificazione.txt`:

**19/19 ROSSO, file ripristinati e verificati (sha256, 8 file).** M1 scanner senza conversione, M2 banco senza
conversione, M3-M5 runner calcio/tennis/scalper senza middleware, M6 middleware in coda, M7 livelli modificati in
place, M8 runner condiviso riconvertito, M9 lista riconvertita, M10 libro riconvertito, M11 cambio non congelato,
M12 WARN->CRITICAL, M13 cambio implausibile accettato, M14 cache non scritta, M15 REST convertito due volte,
M16 total_matched non convertito, M17 riga senza valuta, M18 marcatore recorder tolto, M19 cambio del banco non fisso.
(Primo giro: M8/M9/M10 restavano verdi perche' le difese si coprono a vicenda: aggiunte le asserzioni su
`total_matched` e il test `test_lista_gia_convertita_non_si_riconverte`, poi tutte rosse.)

## 8. Cosa NON ho potuto verificare
- **Nessuna chiamata vera a `listCurrencyRates`** (nessun login). La forma della risposta è quella di bflw `CurrencyRate` (`currency_code`, `rate`). Che Betfair restituisca la riga EUR con `fromCurrency=GBP` è documentato («Returns a list of currency rates based on given currency») ma non l'ho misurato.
- **Nessun replay lungo lanciato**, come da brief. Il coordinatore lancia `python -m Betfair.stream.backtest.certifica <bot> --scenari rapidi` in sequenza. **Attesa:** i referti cambiano rispetto ai precedenti, perché il paper del banco vede il ~16 % di liquidità in più. Non è una regressione: il banco prima era specchio di un live sbagliato.
- `test_banco_calcio_*` è saltato: nel worktree manca la registrazione calcio.
- Nessuna prova sull'app viva, né ladder né UI.

## 9. Rischi residui e divergenze da portare all'utente
1. **Match Replay (frontend).** `frontend/src/lib/matching.ts` (`MIN_STAKE_GBP`) e `replay-pnl.ts` trattano i file curati come sterline (£). Dai file nuovi le size sono in EUR, con `"valuta":"EUR"` su ogni riga; i file vecchi restano GBP, senza marcatore. La pagina va adeguata leggendo il marcatore. È **fuori dal mio perimetro**: nessuna modifica al frontend.
2. **Cambio del banco fisso (1,1647).** Il cambio vero del giorno della registrazione può differire di ±1-2 %. Rimedio possibile in futuro: il runner scrive il cambio nella cartella della registrazione (non fatto, sarebbe una feature).
3. **Finestra di corsa di pochi bytecode.** Un thread diverso da quello principale di flumine che legge `market.market_book` fra l'assegnazione e il middleware vede ancora GBP. Unici casi:
   - `live_order_worker._book_snapshot`: fotografia diagnostica al click;
   - l'esecuzione simulata del paper.
   I prezzi non cambiano. Non corretto, per diff minimo.
4. **Book `CLOSED`.** flumine li manda a `process_closed_market` senza passare dai middleware: restano in GBP. Non portano liquidità utile.
5. **Laboratori e avviatori storici non convertiti.** Sono elencati come esenti nel contratto: se tornassero in produzione, il test di contratto li costringe a registrarsi.
6. **Alert nei test.** Un test che esegue `setup_and_run` dei runner con un client finto fa partire `CAMBIO.avvia`, che tenta un alert su `live_alerts`. Va lanciato con `SUPABASE_URL` fittizio, come prescrive il brief comune. In `test_punto6_b_*` il thread orario muore sul `time.sleep` finto (warning innocuo di pytest).
7. **`CAMBIO_RIPIEGO`** è una costante datata 23/09/2026: vale solo se Betfair non risponde e non esiste cache.
