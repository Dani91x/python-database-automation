## 2. Grafo degli import interni

Script: `s02_import.py` (AST su tutti i `.py` tracciati, nessun codice eseguito) -> `uscite/s02_moduli.tsv` (una riga per modulo:
categoria, righe, importatori per tipo, n. importazioni, riferimenti per stringa, `__main__`, librerie esterne),
`s02_archi.tsv` (importatore -> importato, 1.462 archi di produzione/strumenti), `s02_esterni.tsv` (per file e libreria: file:riga della
prima importazione), `s02_morti.txt`; poi `s07_cartelle_import.py` (grafo aggregato per cartella), `s08_morti_verifica.py` (controprova
per stringa), `k02_grafo_import.py` (secondo parere: import dinamici, `uscite/k02_import_dinamici.txt`).

**Correzioni fatte agli script del primo giro** (documentate perche' cambiano i numeri):
(a) `s02` non riconosceva gli import `from ai_engine.x import ...` come interni (la cartella `Ai Engine/` e' nel `sys.path`): 5 moduli
di `Ai Engine/` finivano per errore nel gruppo A dei morti; ora c'e' l'alias (commento in `s02_import.py`, sopra `cat = {...}`).
(b) `k02` decodificava senza BOM e dava 16 falsi `SyntaxError`; ora usa `utf-8-sig` (0 errori, 502 chiamate dinamiche registrate).
(c) `s01` contava come testo i binari senza NUL (PDF): corretto.

### 2.1 Numeri di sintesi e librerie

{{sez:s02_riepilogo.txt:moduli .py tracciati}}
{{sez:s02_riepilogo.txt:== Librerie chiave}}

### 2.2 Chi parla con l'esterno in PRODUZIONE (file:riga della prima importazione)

{{sez:s02_riepilogo.txt:== Chi parla con l'esterno}}

Letture di questa tabella (ogni punto e' un `file:riga` qui sopra):

- **Due client Betfair diversi.** `betfairlightweight` (27 file di produzione) e' la libreria dello STREAM e di tutto il percorso
  flumine (`Betfair/stream/runner.py:29`, `Betfair/stream/tennis_live/tennis_runner.py:45`, `Betfair/safe_strategy/stream.py:149`,
  `Betfair/stream/auth.py:13`, `Betfair/stream/reconcile_worker.py:493`). In parallelo esiste un **client proprio** su `requests`
  (JSON-RPC, login con certificato): `Betfair/client.py:10` (426 righe, importato da 6 file di produzione, tra cui `runner.py`,
  `betfair_report_manager.py`, `odds_refresh.py`, `betfair_full_odds.py`, `betfair_tennis_odds.py`) e `Betfair/omega/omega_market.py:508` (1.794 righe, il client
  «a domanda» importato da Mike, Safe e Omega per gli ordini veri e le quote di ripiego; 69 test lo importano).
  `Betfair/stream/auth.py:13-14` importa entrambe (`betfairlightweight` e `requests`).
- **`flumine`**: 61 file di produzione, ma i processi che lo usano come motore sono pochi: runner calcio (`runner.py:31`), runner tennis
  (`tennis_runner.py:49`), sessione scalper (`scalper_session.py`), il banco (`banco_comune.py`, `porta_banco.py`, `trasporto_rapido.py`) e
  le classi bot in `stream/trading/*` (`controls.py:40`, `dutching.py:25`, `greenup.py:49`, `risk_engine.py:36`).
  Nei file dei tre bot di punta (`mike/`, `omega/`, `safe_strategy/`) l'unico import di `flumine` e' pigro e di utilita'
  (`Betfair/safe_strategy/proposte_opportunita.py:679`, `from flumine.utils import PRICES_FLOAT`, la scala dei prezzi): i loro ordini
  passano dal runner (sezione 5).
- **Un solo client Supabase di produzione** (`db_client.py:6`, `from supabase import create_client`, un client PER THREAD,
  `db_client.py:75`) piu' un SECONDO `create_client` in `Betfair/stream/tennis_live/tennis_db.py:22` (che non passa da
  `db_client`) e uno script (`football_data_scraper/fix_snapshot_time.py:12`). Gli altri accessi al DB importano `db_client`
  (107 file di produzione, il modulo piu' importato del repo) e parlano `postgrest` via la libreria (`Betfair/stream/db.py:19`,
  `Betfair/stream/runner_lifecycle.py:279` importano solo `APIError`). `httpx` in produzione: `db_client.py:52` (timeout del profilo bot)
  e 6 job di pipeline (`enrich_analytics_snapshots.py:76`, `refresh_analytics_bets.py:67`, ...).
- **`requests`** (9 file): login/JSON-RPC Betfair (`Betfair/client.py:10`, `omega_market.py:508`, `auth.py:14`), API-Football
  (`api_client.py:3`, `api_quota.py:40`, `seasons_catchup.py:151`), `runner_lifecycle.py:242`, `tennis_live/paper_execution.py:36`.
- **`websockets`** (7 file) solo per i canali locali: server in `local_channel.py:292`, client in `esiti_ordini_canale.py:229`,
  `sveglia_canale.py:250`, `safe_strategy/canale_scan.py:407`, `safe_strategy/porta_ordini.py:535`,
  `tennis_live/canale_bot_tennis.py:107`, `mike/service.py:6814`.
- Non c'e' nessun `aiohttp`, `psycopg2`, `sqlalchemy`, `urllib` esplicito, `socket` esplicito nelle importazioni rilevate dallo script
  (il lock di istanza usa `socket` da `Betfair/stream/single_instance.py:18`: lo script riporta 0 perche' `socket` e' stdlib e
  non e' classificata come esterna; la riga «socket 0 file» della tabella e' un limite dello script, non un fatto).

### 2.3 Moduli piu' importati e piu' accoppiati (produzione)

{{sez:s02_riepilogo.txt:== Moduli di produzione piu' importati}}
{{sez:s02_riepilogo.txt:== Moduli di produzione con piu' import}}

### 2.4 Il grafo per cartella (tabella riassuntiva)

Archi = coppie file->file di produzione (`s07_cartelle_import.py`; dettaglio dei 1.462 archi in `uscite/s02_archi.tsv`, per cartella
in `uscite/s07_archi_cartelle.tsv`).

{{file:s07_cartelle.txt}}

Letture:

1. Le dipendenze **non vanno in una sola direzione**: `safe_strategy -> omega` (17 coppie) e `omega -> safe_strategy` (12) sono un ciclo;
   `mike` dipende da `safe_strategy` (10) e da `omega` (7); il banco (`stream/backtest`) dipende da `safe_strategy` (15), `omega` (10), `tennis_live` (9).
   Per sostituire Omega oggi si toccano almeno i file elencati in `s02_archi.tsv` con `omega` come importato: 34 archi in entrata da altre cartelle.
2. `Betfair/stream/*.py` (i 44 file piani, 25.850 righe) e' importato da altre cartelle 197 volte: e' il vero «nucleo» di fatto, ma contiene
   insieme runner, DB (`db.py`), canali, ordini, watchdog; non c'e' un confine fra «nucleo Betfair» e «servizi dei bot».
3. `stream/trading` (4.301 righe, 12 file) e' importato 79 volte da altre cartelle ma importa solo 4 volte verso l'esterno: e' l'unica
   cartella a foglia nel grafo interno (importa pero' `flumine`).
4. La radice (`<radice>`, 88 file) riceve 69 archi da altre cartelle; `db_client.py` da solo e' importato da 107 file di produzione, `config.py` da 17.

### 2.5 Candidati morti: gruppi A-D con la prova

Criterio (da `s02_morti.txt`, riga di testa): modulo di produzione (`py_codice_*`, no `__init__`) che nessun file di PRODUZIONE importa (AST).
A = nessun importatore di nessun tipo, nessun riferimento per stringa in file di codice non-audit, nessun `if __name__ == '__main__'`;
B = nessun importatore ma ha `__main__` o e' nominato per stringa; C = importato solo da test; D = importato solo da strumenti/audit.
La **controprova** (`s08_morti_verifica.py`) cerca il nome del file come parola intera in tutto il codice e nei lanciatori
(py, js, ts, yml, bat, ps1, sh), esclusi audit, test e il file stesso; esito ZERO = nessuna citazione in tutto il repo.

| Gruppo | Moduli | Righe | Esito della controprova |
|---|---:|---:|---|
| A nessun riferimento | 26 | 3.610 | **23 ZERO citazioni = morti certi** (3.419 righe); 3 citati per parola generica (`summary.py`, `trainer.py`, `parse.py`: lo stem e' una parola comune) |
| B solo `__main__` o stringa | 73 | 15.490 | 41 ZERO citazioni (script mai richiamati da nulla, ma lanciabili a mano); 32 citati (workflow, `.bat`, frontend, altri moduli; alcuni per stem generico: `pipeline`, `backfill`, `backtest`, `runner`, `cli`, `calibrate`, `test` danno falsi positivi, p.es. `market_intelligence/pipeline.py` non e' lanciato da nessun workflow) |
| C solo test | 1 | 402 | `Betfair/omega/liquidity_probe.py` (test: `test_liquidity_probe_2026_09_10.py`, `test_omega_matematica_2026_09_12.py`) |
| D solo strumenti/audit | 27 | 21.878 | NON morti: punti d'ingresso lanciati con `-m` (vedi sotto) e moduli del banco |

**Gruppo A, i 23 morti certi** (nome, righe; prova: `uscite/s08_morti_verifica.tsv` colonna `esito=ZERO`; rieseguibile con
`git grep -nw <stem>` sui file di codice):
`Ai Engine/ai_engine/analysis/advanced.py` 90, `Ai Engine/ai_engine/models/voting.py` 21, `Betfair/cleanup_reset.py` 32 (citato solo in
`MANUALE_OPERATIVO.md`, un documento), `_certify_betfair_full.py` 37, `analyze_recovery.py` 283, `analyze_threshold.py` 308,
`calibration_analysis.py` 622, `check_gh.py` 13, `laboratorio/scalper_lab/grid_strategy.py` 485 (nominato solo in documenti e test di contratto),
`refresh_dashboard.py` 20, `report_mm.py` 202, `simulate_recovery_forward.py` 287, `tactical_engine/_check_fixpred.py` 24,
`tactical_engine/_inspect_mismatch.py` 21, `tmp_analysis.py` 188, `tmp_analysis2.py` 139, `tmp_predict_today.py` 117, `tmp_smoke_stack.py` 138,
`tmp_today_predictions.py` 141, `tmp_validate_league.py` 66, `tmp_validate_predict.py` 76, `update_dashboard_only.py` 31,
`value_engine/generate_battery.py` 78. Sono script di analisi o di prova: ultimo commit tra il 18/02 e il 24/06/2026 per 22 su 23 (date da `git log -1` e da `uscite/k03_classifica.tsv`: `advanced.py` e `voting.py` 18/02,
`cleanup_reset.py` 04/03, `_check_fixpred.py` e `_inspect_mismatch.py` 20/06, `generate_battery.py` 17/06, `_certify_betfair_full.py` 24/06); l'eccezione e' `laboratorio/scalper_lab/grid_strategy.py`
(25/09, nominato dal test di contratto `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`).

**Gruppo B senza alcuna citazione** (41, script con `__main__`): `Ai Engine/ai_engine/{audit_nulls,bss_monitor,evaluate_holdout,generate_fixture_report}.py`,
`Ai Engine/backtest_ml.py`, `Betfair/stream/tennis_scalper/{record_tennis,tune_tennis}.py`, `Prediction/{analyze_sweet_spot,backfill_historical_analysis}.py`,
`_certify_{betfair,delay_context,direction,personal_report,signal_context}.py`, `_league_eval.py`, `_stack_eval.py`, `admin_reset_password.py`,
`backfill_poisson_calibrated.py`, `certify_backtest_strategy.py`, `cleanup_models.py`, `compress_models.py`, `football_data_scraper/fix_snapshot_time.py`,
`laboratorio/scalper_lab/{bt_theta,exp_families,validate_synth}.py`, `load_poisson_calibration_to_db.py`, `market_intelligence/backtest_audit.py`,
`missing_fixtures_backfill.py`, `reset_ai_models.py`, `sanity_check.py`, `sql/{_build_wc_xlsx_2013,_cert_wc_fetch,_cert_wc_full,_verify_delays_math}.py`,
`tactical_engine/{_verify_data_worldcup,run_worldcup}.py`, `tmp_smoke_{ml_fixes,poisson_fixes}.py`, `tmp_train_today.py`,
`valida_{motore_poisson,ventaglio}.py`. Sono script a riga di comando: non sono dimostrabilmente morti (si lanciano a mano), ma nessun
lanciatore automatico li richiama.

**Gruppo D, perche' NON e' morto** (prova: `uscite/s02_morti.txt`, sezione D, colonna «stringhe»): `Betfair/stream/runner.py` (3.171 righe,
lanciato da `desktop/main.js:419` via watchdog, default `watchdog.py:65`), `watchdog.py` (337), `backtest/worker.py` (102, `main.js:469`),
`scalper/scalper_service.py` (982, `main.js:427`), i job del cloud (`Prediction/predictions_results_backfill.py`, `build_direzione.py`,
`cloud_retrain_shard.py`, `daily_yesterday_backfill.py`, `enrich_analytics_snapshots.py`, `generate_dc_rho.py`, `generate_dynamic_cal.py`,
`leagues_mapper.py`, `merge_engine_signals.py`, `refresh_analytics_bets.py`, `update_poisson_calibration.py`: tutti citati da `.github/workflows/*.yml`) e i
moduli `certificazione.py` del banco (mike 2.084, omega 2.160, safe 2.036, safe_tennis 1.217, scalper 2.472, tennis 1.189 righe), che il
registro del banco importa con `import_module` (`Betfair/stream/backtest/registro_bot.py:66`, `:133`) e quindi l'AST non vede.

**Import dinamici** (che l'AST non vede): `Betfair/omega/omega_service.py:8815` (`__import__`), `Betfair/safe_strategy/bot_service.py:285`,
`Betfair/stream/backtest/registro_bot.py:66,133` (`import_module`), `Betfair/safe_strategy/tools/replay_registrazioni.py:914`;
elenco completo (502 voci tra codice, test e audit) in `uscite/k02_import_dinamici.txt`.

**Limiti noti del metodo**: (1) i moduli importati con `sys.path` fuori dai pacchetti sono risolti solo come fratelli di cartella o per alias
`ai_engine`; (2) un modulo che compare solo in una stringa `-m pacchetto.modulo` e' visto dal controllo per stringa, non dall'AST;
(3) i moduli «importati» da un altro modulo a sua volta morto contano come vivi (non c'e' un calcolo di raggiungibilita' a partire dai
punti d'ingresso): per questo i morti certi sono un limite INFERIORE.

