# Fallimenti delle action: classificazione di OGNI run rossa e rimedi (09/10/2026, delegato Opus)

Ordine dell'utente: «DEVI SCONGIURARE IL RISCHIO DI FALLIMENTO DELLE ACTION [...] SE IL PROBLEMA E'
ALTRO DEVI RISOLVERLO UNA VOLTA PER TUTTE.»

Worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-fallimenti`, ramo `cantiere-fallimenti-action`
(da master `a38a7eb6`). Niente commit, niente push, nessun workflow lanciato o rilanciato, DB mai
toccato (ne' in lettura ne' in scrittura): tutte le righe vengono da `gh run view <id> --log[-failed]`
(anche `--attempt N`) e da `gh api .../runs/<id>`.

## 0. In breve

- Ultime 300 run (14/09 09:04 - 09/10 09:22 UTC): **31 `failure`, 3 `cancelled`**, 1 in corso.
- Classi: (a) DB transitorio **25** (18 per 57014, tutte del 15-28/09 e gia' risolte; 7 pagine
  Cloudflare 520/521/522 o connessione HTTP/2 terminata); (b) DB in crash del 09/10 **2**;
  (c) regola d'uscita sull'«API vuota» del Catchup **3** (+1 run che ha anche una causa (a));
  (d) codice/config **1** (tabelle dell'atlante assenti, 25/09); (e) GitHub **0**; (f) annullate a
  mano **3** (le 3 `cancelled`).
- Gia' risolte prima di oggi: **28 su 31**. Scoperte: Post-Calibration 05/10 (521), Retrain/rechain
  09/10 (522), Hazard 09/10 (520 sulla scrittura globale): sono quelle coperte da questo cantiere,
  insieme a tutti gli altri script delle action che avevano lo stesso buco (nessun ritentativo sul
  gateway) anche se non e' ancora capitato.
- **Reperto principale (correlazione, non prova)**: dal 02/10 OGNI run rossa di Leagues Mapping,
  Post-Calibration, Catchup (tentativo 1 dell'08/10) e Retrain e' caduta **nello stesso secondo** in
  cui l'atlante hazard mandava la sua scrittura globale da ~27 MB (`rpc/hazard_atlas_salva_versione`)
  e riceveva anch'esso 520 (tabella al par. 1.2). Il 09/10 l'atlante ha mandato 9 di queste scritture
  tra le 07:26 e le 07:52 UTC, cioe' dentro la finestra del «DB in crash» 07:25-07:51. Con la catena
  in fila (staffetta) le action non si sovrappongono piu', ma la scrittura resta strutturalmente
  fragile e cresce con le leghe: **decisione D-A per l'utente** (par. 5).

## 1. Parte 1 - classificazione di ogni run (fatti dai log)

### 1.1 Tabella

| Run | Inizio (UTC) | Workflow | Job / passo | Riga d'errore (log) | Classe | Risolto da |
|---|---|---|---|---|---|---|
| 37910820146 | 09/10 09:22 | Daily | run-backfill (1,5 min) | annullata, `workflow_dispatch` di Dani91x | (f) annullata a mano | n/a |
| 37899249882 | 09/10 07:28 | Seasons Catchup | catchup, alle 07:54:10 dentro un insert `match_events` | `##[error]The operation was canceled.` (25 min su 270 di tetto: non un timeout) | (f) annullata (l'API non dice chi annulla; attore Dani91x) | n/a |
| 37898960772 | 09/10 07:25 (4 tentativi) | Hazard Atlas | genera_atlante, scrittura globale | t1 07:27:22-07:37:52 520 x5; t2 07:43:34 520, 07:48:39 `The read operation timed out`, 07:49:43 502, 07:52:16 502 html; t3 08:13-08:24 520 x5; t4 08:53-09:03 520 x5 -> `versione globale (hazard_atlas) NON scritta dopo i ritentativi: HTTP Error 520` -> `SCRITTURA INCOMPLETA` exit 1 | (b) t1-t2 nel crash; t3-t4 (a) strutturale: payload da 382 leghe | **parziale, oggi** (par. 2.5) + **D-A** |
| 37898960743 | 09/10 07:25 | Retrain | rechain, `training_planner.py:104 _all_pages('ai_model_registry')` | `APIError {'message': 'JSON could not be generated', 'code': 522 ... <html` alle 07:28:21; i 3 shard di training erano `success` | (b) | **oggi** (par. 2.1, 2.3) |
| 37743110569 | 08/10 07:23 | Seasons Catchup | t1: `rpc/season_detail_gaps` | `HTTP/2 520` alle 07:28:24.09; t2 (rilancio del delegato, 14:53-15:07): `ConnectionTerminated ... last_stream_id:19999` + 57014 su `season_detail_gaps` | (a) | `d60fa53c`, `e81ebf43` (08/10) |
| 37277717856 | 05/10 07:26 | ML Post-Calibration | `compute_ml_post_calibration.py:103 _fetch_registry_cells` | `APIError ... 'code': 521` (pagina «521: Web server is down») alle 07:26:23.79 | (a) | **oggi** (par. 2.1, 2.2) |
| 37185437609 | 04/10 07:19 | Seasons Catchup | referto finale | `BUCO VECCHIO: lega 129 stagione 2026 ... API vuota su 8 partite-tabella` exit 1 | (c) regola d'uscita | `cdecd095` (04/10) |
| 37185344834 | 04/10 07:17 | Leagues Mapping | UPDATE lega 353 | `Errore UPDATE lega 353 stagione 2026 NON previsto: ... 'code': 520` (pagina datata 07:19:16) -> `LEAGUES MAPPER FALLITO: 1 batch` | (a) | `cdecd095` (ritentativi del mapper) + oggi |
| 37141249749 | 03/10 17:38 | Seasons Catchup | per_fixture, delete `match_player_stats` | `<ConnectionTerminated error_code:0, last_stream_id:19999>` -> BUCO VECCHIO lega 250; + 2 BUCO VECCHIO da API vuota | (a) + (c) | `d60fa53c` (08/10) + `cdecd095` |
| 37103519105 | 03/10 06:34 | Leagues Mapping | `leagues_mapper.py:49 get_existing_coverage_rows` | `RuntimeError: lettura api_coverage_by_season fallita (offset 0): ... 'code': 522` alle 06:36:00; poi `PGRST002 Could not query the database for the schema cache` alle 06:36:06 | (a) | `cdecd095` + oggi |
| 37049359939 | 02/10 18:43 | Seasons Catchup | per_fixture, insert `match_lineups` | `ConnectionTerminated ... 19999` -> BUCO VECCHIO lega 344 | (a) | `d60fa53c` |
| 36976589187 | 02/10 07:03 | Leagues Mapping | `get_existing_coverage_rows` | `... 'code': 522` alle 07:04:58 | (a) | `cdecd095` + oggi |
| 36821373801 | 01/10 05:46 | Seasons Catchup | referto finale | `BUCO VECCHIO: lega 10 ... API vuota su 69 partite-tabella` | (c) | `cdecd095` |
| 36615357543 | 29/09 18:54 | Seasons Catchup | referto finale | `BUCO VECCHIO: lega 667 ... API vuota su 9` | (c) | `cdecd095` |
| 36390445058 | 28/09 07:13 | Hazard Atlas | POST `hazard_atlas` | `urllib.error.HTTPError: HTTP Error 500` (57014 sotto carico) | (a) | `3134f9f5` (R-28-2) |
| 36338805869 | 27/09 17:56 | Seasons Catchup | RPC `season_gaps_summary` | `APIError ... '57014'` traceback | (a) 57014 | `0ffc3c65` |
| 36258896621 | 26/09 17:24 | Seasons Catchup | idem | idem | (a) 57014 | `0ffc3c65` |
| 36101390338 | 25/09 06:06 | Daily (job hazard-atlas di allora) | prerequisiti atlante | `urllib.error.HTTPError: HTTP Error 404: Not Found` (tabelle non migrate) | (d) config | `703a33a6` (atlante nel suo workflow) + migrazione applicata |
| 36011159941 | 24/09 14:12 | Predictions Results | enrich (gate) | `lega 667: lettura matches ... fallita dopo 5 tentativi: ... '57014'` | (a) 57014 | `8d43da0a` |
| 36002968576 | 24/09 13:02 | Predictions Results | enrich | idem lega 667 | (a) 57014 | `8d43da0a` |
| 35976004167 | 24/09 08:34 | Predictions Results | enrich + bets (gate) | `[ERR lega 292] ... analytics_signals ... '57014'` (e altre) | (a) 57014 | `29f50b03` |
| 35844019126 | 23/09 09:37 | Predictions Results | enrich | 9 leghe `analytics_signals ... 57014` | (a) 57014 | `29f50b03` |
| 35838543385 | 23/09 08:41 | Predictions Results | enrich | `lettura analytics_signals lega 929 ... 57014` | (a) 57014 | `5ed3bb94`/`29f50b03` |
| 35837906029 | 23/09 08:34 | Predictions Results | enrich (gate) | idem lega 929 | (a) 57014 | idem |
| 35837269470 | 23/09 08:27 | Today Predictions | run script | `Upsert batch fixture_predictions fallito (100 righe): ... '57014'` -> `Uscita con codice 1: 106 anomalie non recuperate` | (a) 57014 | `b418c77c` |
| 35833741799 | 23/09 07:49 | Today Predictions | run-predictions (3 min) | annullata, `schedule` | (f) annullata a mano | n/a |
| 35596470375 | 21/09 11:53 | Retrain | train shard 1 | `League 71: ... '57014'` | (a) 57014 | `774a47a8` |
| 35592896432 | 21/09 11:13 | Retrain | train shard 1 | `League 141: ... 57014` | (a) 57014 | `774a47a8` |
| 35589926333 | 21/09 10:39 | Retrain | train shard 0 | `League 239: ... 57014` | (a) 57014 | `774a47a8` |
| 35568831478 | 21/09 06:31 | Retrain | train shard 0 | `League 141/136/71: ... 57014` | (a) 57014 | `774a47a8` |
| 35494758357 | 20/09 06:38 | Retrain | train shard 0 | `League 40: ... 57014` | (a) 57014 | `774a47a8` |
| 35432041277 | 19/09 08:27 | Retrain | train shard 0 | `League 144: ... 57014` | (a) 57014 | `774a47a8` |
| 35425250583 | 19/09 05:56 | Retrain | train shard 0 | `League 144: ... 57014` | (a) 57014 | `774a47a8` |
| 34935960315 | 15/09 06:13 | Retrain | train shard 2 | `League 141: ... 57014` | (a) 57014 | `774a47a8` |

Nessuna run rossa per quota o 5xx di API-Football (classe (c) solo come regola d'uscita del Catchup
sull'«API vuota», gia' AVVISO dal 04/10). Nessuna run rossa di classe (e): nessun timeout di job,
nessun `gh` fallito (il `gh` del rechain e della staffetta non e' mai arrivato a girare nelle rosse).

### 1.2 Correlazione con la scrittura dell'atlante (stessi secondi, dai log)

| Giorno | `rpc/hazard_atlas_salva_versione` KO (atlante) | Run rossa di un altro workflow |
|---|---|---|
| 02/10 | 07:04:50.80 520 | Leagues 36976589187: 522 stampato alle 07:04:58 |
| 03/10 | 06:36:02.63 520 | Leagues 37103519105: 522 alle 06:36:00.08, PGRST002 «schema cache» alle 06:36:06 |
| 04/10 | 07:19:12.19 520 | Leagues 37185344834: pagina 520 datata 07:19:16 |
| 05/10 | 07:25:04 520, 07:25:11 502 «Network connection lost», 07:26:23.26 520 | Post-Cal 37277717856: 521 alle 07:26:23.79 |
| 08/10 | 07:27:10 520, 07:28:24.000 520 | Catchup 37743110569 t1: `season_detail_gaps` 520 alle 07:28:24.09 |
| 09/10 | t1: 07:27:22, 07:28:29, 07:29:37, 07:32:14, 07:37:52; t2: 07:43-07:52 | Retrain rechain: 522 alle 07:28:21; «DB in crash» 07:25-07:51 |

La stessa scrittura va in 520 ogni giorno (anche 29/09, 01/10, 06/10, 07/10, quando nessun altro
e' fallito) e riesce di solito al 2o-3o tentativo (06-08/10: 2 KO poi riuscita). Ogni tentativo
fallisce dopo ~40 s. Misura in locale (`hazard_atlas_live.json`, 381 leghe): corpo inviato
27.190.302 byte (JSON con spazi), di cui `h2h_hint` 13,2 MB, `by_team` 6,1 MB, `by_league` 2,5 MB,
`v4` 2,0 MB. NON verificato sul DB (vietato leggerlo) se i tentativi «KO» abbiano in realta' scritto
la riga (righe doppie) ne' la causa esatta lato Supabase (OOM/riavvio di PostgREST o Postgres).

## 2. Parte 2 - rimedi

### 2.1 (a)+(b) Un solo punto di resilienza per TUTTI gli script delle action: `db_client.py`
Invece di avvolgere a mano ~60 `.execute()` in 15 script, il client PostgREST dei processi delle
action ritenta **al livello del trasporto httpx**, con la stessa politica di `con_ritentativi`
(attese 2-4-8-16-32 s +-25%, log `[RETE]`, `STATISTICHE_RETE`, interruttore dopo 2 guasti
persistenti) **piu' un ritentativo lungo di 120 s** (`DB_RESILIENZA_ATTESA_LUNGA_S`), ~3 min per
chiamata.
- `TrasportoResiliente` (`db_client.py:508`), montato da `_installa_trasporto_resiliente` (`:587`) in
  `get_supabase_client` (`:107-109`) SOLO se `resilienza_action_attiva()` (`:460`): flag di processo
  (`attiva_resilienza_action`) o `DB_RESILIENZA_ACTION=1`. I bot non lo accendono mai: client,
  timeout e comportamento identici (test `test_senza_attivazione_...`, suite bot verde).
- Regole (`richiesta_idempotente` `:473`, `classifica_risposta_action` `:487`, `classifica_eccezione_action`):
  - non consegnata (ConnectError/ConnectTimeout/PoolTimeout, Cloudflare 521/522/523/525/526/530):
    sempre ritentata, anche un insert o una RPC che scrive (la richiesta non e' arrivata);
  - ambigua (520/524/502/503/504/527, 500 HTML, ReadTimeout, connessione terminata): ritentata SOLO
    se idempotente: GET/HEAD/OPTIONS/PUT/PATCH/DELETE, upsert (`Prefer: resolution=`), RPC di sola
    lettura (`RPC_LETTURA_ACTION`: season_detail_gaps, season_gaps_summary, season_aggregates_summary,
    leagues_needing_retrain, get_direction, fetch_missing_fixture_coverage). Insert puro, RPC che
    scrivono (`refresh_analytics_bets_range`, `flush_analytics_snap_staging`, bulk update di Results,
    `record_fixture_detail_checks`): mai alla cieca;
  - mai: 500 JSON di PostgREST (57014 resta ai meccanismi esistenti), 4xx.
  - Fuori da `/rest/v1/` (storage dei modelli, auth): intatto.
- Niente doppio strato: dentro `con_ritentativi` (Catchup) il trasporto passa intatto
  (`_TLS.dentro_ritentativi`, `db_client.py:298-303, 323`).
- Persistente: il trasporto restituisce l'ultima risposta, l'errore risale come prima.

### 2.2 Riga chiara al posto del traceback muto: `esegui_main_action` (`db_client.py:604`)
Il `__main__` di 14 script (daily_yesterday_backfill, Prediction/today_predictions_backfill,
Prediction/predictions_results_backfill, build_analytics_signals, merge_engine_signals,
enrich_analytics_snapshots, refresh_analytics_bets, build_direzione, leagues_mapper,
compute_ml_post_calibration, cloud_retrain_shard, generate_dynamic_cal, update_poisson_calibration,
seasons_catchup) ora e' `esegui_main_action(main, "<file>")`: accende la resilienza ed esegue `main`;
un errore che `classifica_guasto_rete` riconosce (anche come causa di un RuntimeError) diventa
`::error::GUASTO DB PERSISTENTE (<classe>) in <file>: <titolo della pagina> - rete PostgREST: ...`,
la stessa riga nel riepilogo del job, exit 1; il traceback resta in un gruppo richiudibile del log.
Ogni altro errore (codice) risale identico. `generate_dc_rho.py` non tocca il DB: non toccato.

### 2.3 Retrain: rechain e plan (`retrain_models.yml`, `training_planner.py`)
- `training_planner._incremental_todo` (`:162-170`): un guasto di rete/gateway NON e' piu' «RPC non
  disponibile -> []» (prima: 0 leghe incrementali in silenzio = training saltato o rechain fermo senza
  dirlo); ora risale. 404/PGRST202 (RPC assente) resta `[]` come prima.
- `select_leagues_to_train_con_attesa` (`:310`): attese lunghe 60/120/240 s SOLO sul guasto di rete.
- Passo `plan` (gate): `DB_RESILIENZA_ACTION=1`, `select_leagues_to_train_con_attesa` dentro
  `esegui_main_action` (riga chiara + exit 1 se persiste), timeout 8 -> 20 min.
- Passo `rechain`: `DB_RESILIENZA_ACTION=1`; guasto persistente -> `::warning::RECHAIN NON ESEGUITO:
  DB irraggiungibile ...`, riepilogo «Retrain: rechain rinviato», **exit 0**, nessun rilancio,
  `rilanciato` non scritto -> **la staffetta passa** (`needs.rechain.outputs.rilanciato != 'true'`).
  Errore di codice -> rosso come prima. Timeout 8 -> 25 min.
- `gh workflow run` del rechain: un ritentativo con controllo anti-doppio (stessa chiamata
  `gh api .../runs?event=workflow_dispatch&created>=` della staffetta): run gia' creata -> nessun
  secondo lancio; assente -> un solo nuovo lancio; stato illeggibile -> nessun rilancio, step rosso.

Effetto sulla run 37898960743: il 522 delle 07:28:21 viene ritentato (~3 min di attese brevi + lunga,
poi 60/120/240 s del planner = fino a ~10 min per lettura); con il DB giu' 26 minuti la run sarebbe
stata comunque **verde** con l'avviso «rechain rinviato», e Post-Calibration sarebbe partita.

### 2.4 Staffetta quando un job fallisce
`passa-testimone` ha `if: !cancelled() && inputs.catena == 'true'` (+ `rilanciato != 'true'` nel
Retrain) e `needs` = tutti i job: un job FALLITO non annulla la run, `!cancelled()` e' vero, il
testimone passa (documentazione GitHub, *Expressions / Status check functions*). Il rechain del
09/10 (rosso, `rilanciato` mai scritto perche' il guasto era prima) avrebbe gia' passato il testimone.
Non toccato (perimetro dell'altro delegato). NON verificato: che un job fermato da `timeout-minutes`
lasci `cancelled()` falso (stessa riserva del referto dell'orologio).

### 2.5 Atlante hazard (`genera_atlante.py`, `hazard_atlas.yml`)
- `_Scrittore._req` (`:933-975`): corpo JSON compatto (`separators=(",", ":")`: stesso valore,
  -11,7% di byte sull'atlante da 381 leghe: 27,19 -> 24,02 MB); parametro `gia_scritto`.
- `_scrivi_riga` (`:1066-1089`): dopo un esito AMBIGUO (52x/502/503/504/rete/timeout, MAI dopo un 500
  = 57014 annullato) si chiede al DB se la riga con lo stesso `generated_at` c'e' gia' (una GET, senza
  ritentativi): se si', nessun altro invio da 24 MB e nessuna riga doppia.
- Passo «Prerequisiti» del workflow: ritentativi 5/15/45/90 s su 5xx/52x/rete (prima un 520 qui =
  rosso); 404 (tabelle assenti) esce subito come prima.
- Exit 1 su «versione_globale NON scritta» **invariato**: la filigrana non avanza (la notte dopo
  l'incrementale rilegge, idempotente per fixture_id), ma e' un lavoro non fatto e resta dichiarato.
  La causa strutturale e' la **decisione D-A**.

### 2.6 (c) API-Football
Nessuna run rossa per quota/vuoto/5xx dell'API nelle 300 run oltre alla regola del Catchup gia'
risolta il 04/10 (`cdecd095`). Non toccato. Nota: `leagues_mapper` esce rosso se `/leagues` e' vuoto
(scelta del 25/09, «fallimento rumoroso»): mai successo; lasciato com'e'.

### 2.7 (e) GitHub: tetti dei job e dipendenze fisse
Durate MISURATE sulle run riuscite (job, non coda): Daily 9,6/29,4/32,0 min (mediana/p90/max, n=24);
Today 67,3/170,4/228,9 (n=25); Results 72,6/93,5/109,5 (n=24); Weekly calibrate 17,9/21,4/21,8 (n=4);
Post-Cal 0,6/1,1/1,7; Hazard 1,8/4,6/7,7; Leagues 1,4/2,4/2,9.
- Tetti nuovi (prima il default di 360 min): Daily 120, Today 330, Results 240, Weekly calibrate 90.
  Gli altri avevano gia' tetti adeguati (Hazard 60, Leagues 30, Post-Cal 20, Catchup 270, train 330).
- `ml_calibration.yml`: `pip install --upgrade pip supabase python-dotenv` (ultima versione: 2.32.0
  nella run del 05/10) -> `pip install -r requirements-planner.txt` (supabase==2.28.0 come tutti).

## 3. Test e falsificazione

`test_fallimenti_action_2026_10_09.py` (radice): **33 test**. Finti: client supabase/postgrest/httpx
VERO su `httpx.MockTransport` (pagine Cloudflare con i titoli veri dei log: «520: Web server is
returning an unknown error», «521: Web server is down», «522: Connection timed out»; corpi JSON veri
di PostgREST 57014/42501/PGRST202); eccezioni httpx vere (`ReadTimeout`, `ConnectError`,
`RemoteProtocolError` con il testo del GOAWAY); atlante con il finto di `urlopen` del suo test del
28/09; passo `rechain` eseguito con **bash** dal YAML vero, con `python`/`gh`/`sleep` finti.
Riproducono: il 522 del rechain (09/10) sulla funzione vera `_all_pages`; il 521 di Post-Cal (05/10)
su `_fetch_registry_cells`; il 520 dell'atlante (09/10) con riga gia' scritta / assente.

**Falsificazione: 26 mutazioni su 26 rosse** (`mutazioni_fallimenti.py`, esito in `mutazioni_esito.txt`;
ripristino dai byte originali, sha256 identico file per file, `git diff` uguale byte per byte prima/dopo,
sha256 del diff `c787ab5a...e952b`).

| Mutazione | Test rossi |
|---|---|
| M01 trasporto mai montato | 10 rossi: test_522_persistente_attese_brevi_poi_lunga_poi_interruttore, test_attivazione_da_ambiente_per_i_passi_inline, test_eccezioni_di_trasporto, test_insert_puro_si_ritenta_solo_se_non_consegnato[521-2], test_insert_puro_si_ritenta_solo_se_non_consegnato[522-2], test_patch_e_delete_si_ritentano_su_520, test_postcal_run_37277717856_521_poi_200, test_rechain_run_37898960743_522_poi_200_il_planner_legge, test_rpc_di_lettura_si_ritenta_rpc_che_scrive_no, test_upsert_si_ritenta_anche_su_520 |
| M02 insert puro ritentato su esito ambiguo | 2 rossi: test_eccezioni_di_trasporto, test_insert_puro_si_ritenta_solo_se_non_consegnato[520-1] |
| M03 RPC che scrive ritentata su esito ambiguo | 1 rossi: test_rpc_di_lettura_si_ritenta_rpc_che_scrive_no |
| M04 522 trattato come ambiguo | 3 rossi: test_insert_puro_si_ritenta_solo_se_non_consegnato[521-2], test_insert_puro_si_ritenta_solo_se_non_consegnato[522-2], test_rpc_di_lettura_si_ritenta_rpc_che_scrive_no |
| M05 500 JSON (57014) ritentato | 1 rossi: test_57014_e_4xx_mai_ritentati[<lambda>-57014] |
| M06 niente attesa lunga | 1 rossi: test_522_persistente_attese_brevi_poi_lunga_poi_interruttore |
| M07 interruttore ignorato dal trasporto | 3 rossi: test_522_persistente_attese_brevi_poi_lunga_poi_interruttore, test_esegui_main_action_guasto_persistente_riga_chiara_exit_1, test_incremental_todo_guasto_di_rete_risale_rpc_assente_resta_vuota |
| M08 il trasporto ritenta anche dentro con_ritentativi | 1 rossi: test_dentro_con_ritentativi_il_trasporto_non_raddoppia |
| M09 main | nessuna riga chiara (risale tutto): 1 rossi: test_esegui_main_action_guasto_persistente_riga_chiara_exit_1 |
| M10 main | inghiotte anche gli errori di codice: 1 rossi: test_esegui_main_action_errore_di_codice_risale_identico |
| M11 variabile d'ambiente ignorata | 1 rossi: test_attivazione_da_ambiente_per_i_passi_inline |
| M12 ritenta anche fuori da /rest/v1/ | 1 rossi: test_fuori_da_rest_v1_passa_intatto |
| M13 planner inghiotte di nuovo il guasto di rete | 1 rossi: test_incremental_todo_guasto_di_rete_risale_rpc_assente_resta_vuota |
| M14 planner senza attese lunghe | 1 rossi: test_planner_con_attesa |
| M15 rechain rosso sul guasto DB | 1 rossi: test_rechain_bash[guasto_db] |
| M16 rechain rilancia senza controllo anti-doppio | 1 rossi: test_rechain_bash[gh_ko_run_creata] |
| M17 rechain rilancia con stato illeggibile | 1 rossi: test_rechain_bash[gh_ko_stato_illeggibile] |
| M18 atlante | gia_scritto ignorato: 2 rossi: test_atlante_520_ma_riga_gia_scritta_nessun_ritentativo, test_atlante_520_riga_assente_ritenta_e_500_57014_non_controlla |
| M19 atlante | controllo anche dopo il 500 (57014): 1 rossi: test_atlante_520_riga_assente_ritenta_e_500_57014_non_controlla |
| M20 atlante | JSON non compatto: 1 rossi: test_atlante_corpo_compatto |
| M21 pre-controllo atlante senza ritentativi | 1 rossi: test_atlante_pre_controllo_ritenta_sul_520 |
| M22 Daily senza tetto di tempo | 1 rossi: test_workflow_contratti |
| M23 Post-Cal di nuovo senza versione fissa | 1 rossi: test_workflow_contratti |
| M24 leagues_mapper non passa da esegui_main_action | 1 rossi: test_entrypoint_dei_workflow_passano_da_esegui_main_action |
| M25 timeout di lettura non ritentato | 1 rossi: test_eccezioni_di_trasporto |
| M26 rechain | piano gate senza resilienza d'ambiente: 1 rossi: test_workflow_contratti |

## 4. Suite

Insieme dei test collegati: 18 file `test_*.py` della radice che importano gli script/`db_client`/i
workflow + `tools/test_catena_action_2026_10_09.py` + 22 file di `Betfair/stream/tests` che importano
`db_client` o l'atlante (41 file in tutto), `-n 3`, corsa normale. Comando:
`.venv/Scripts/python.exe -m pytest test_actions_fail_rumoroso_2026_09_25.py test_actions_pipeline_paginazione.py test_analytics_market_stats.py test_backfill_automatico_2026_09_25.py test_build_analytics_signals_kickoff_2026_09_26.py test_calibrazione_lettura_db.py test_catchup_57014_2026_09_28.py test_catchup_57014_ciclo_2026_10_08.py test_catchup_attesa_concorrenti_2026_09_26.py test_catchup_avviso_buchi_2026_10_04.py test_catchup_p4_2026_09_25.py test_catchup_rete_2026_10_08.py test_cloud_retrain_shard_ritentativi_2026_09_21.py test_daily_niente_aggregati_2026_09_25.py test_leagues_mapper_ritentativi_2026_10_04.py test_merge_engine_signals_kickoff_2026_09_26.py test_refresh_analytics_bets_v2_2026_09_24.py test_riserva_dinamica_2026_09_25.py tools/test_catena_action_2026_10_09.py Betfair/stream/tests/test_atlante_a_domanda_2026_09_25.py Betfair/stream/tests/test_atlante_v4_2026_09_25.py Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py Betfair/stream/tests/test_atlante_v4_stagione_rif_per_lega_2026_09_26.py Betfair/stream/tests/test_banco_comune_2026_09_16.py Betfair/stream/tests/test_certifica_freni_ambiente_d1quater_2026_09_29.py Betfair/stream/tests/test_controls.py Betfair/stream/tests/test_daily_stop_worker.py Betfair/stream/tests/test_db_client_timeout_bot_2026_09_28.py Betfair/stream/tests/test_genera_atlante_2026_09_24.py Betfair/stream/tests/test_genera_atlante_scrittura_ritentativi_2026_09_28.py Betfair/stream/tests/test_modo_ordini_ui_2026_09_24.py Betfair/stream/tests/test_motore_ordini_2026_09_24.py Betfair/stream/tests/test_net_retry.py Betfair/stream/tests/test_reconcile_worker.py Betfair/stream/tests/test_record_optin_2026_07_17.py Betfair/stream/tests/test_replay_scalper_db_isolato_2026_10_06.py Betfair/stream/tests/test_review_finale_2026_07_17.py Betfair/stream/tests/test_runner_guardia_canale_locale_2026_09_23.py Betfair/stream/tests/test_uploader_sweep_2026_07_17.py Betfair/stream/tests/test_validazione_hazard_2026_09_25.py test_fallimenti_action_2026_10_09.py -q -p no:cacheprovider -n 3`
- **prima** (master `a38a7eb6`, worktree temporaneo, poi smontato con rmdir della junction):
  **841 passed, 10 skipped**;
- **dopo** (questo ramo, + il file nuovo): **874 passed, 10 skipped** (841 + 33), nessun test
  esistente modificato.
- `actionlint 1.7.12 -shellcheck=` sui 10 workflow: 0 errori. Python dei passi `python - <<PY` compilato
  (tutti i workflow); `bash -n` del passo rechain: ok. ASCII su tutte le righe aggiunte.

## 5. Cosa resta NON coperto (con motivo) e decisioni

- **D-A (utente) - la scrittura globale dell'atlante**: un unico invio da ~24-27 MB che cresce di
  ~75 KB per lega (382 leghe oggi, 1.244 osservate in `matches`). Va in 520 ogni giorno e coincide al
  secondo con i 5xx degli altri workflow (par. 1.2). Opzioni: (1) non scrivere nella versione globale
  le parti che nessuno legge dal DB nel modo di default `domanda` (`h2h_hint` 13,2 MB e `by_team`
  6,1 MB: il PC le calcola da se'; servono solo al modo `scarica` di `hazard_atlas_sync`); (2) payload
  compresso (gzip ~3,7 MB) con decodifica in `hazard_atlas_sync`; (3) filigrana in una riga leggera
  separata. Tutte toccano il formato dei dati o un modulo del PC (fuori perimetro): non fatte.
  Verifica utile all'utente (sola lettura): `select generated_at, count(*) from hazard_atlas group by 1
  order by 1 desc limit 10;` (righe doppie = i «520» erano arrivati al DB).
- Un DB giu' piu' a lungo dei ritentativi (09/10: 26 min) fa ancora fallire gli script che non hanno
  un «rinvio» (Daily, Today, Results, Post-Cal, Leagues, Weekly, train): ora con una riga chiara e
  dopo ~3 min di ritentativi per chiamata. Solo il rechain (lavoro gia' salvato) e il Catchup
  (rinvio per lega) restano verdi. Rendere verdi gli altri con il DB giu' vorrebbe dire dichiarare
  fatto un lavoro non fatto.
- Il tetto «ritentativi brevi + 120 s» vale per chiamata; con l'interruttore (2 guasti persistenti
  di fila) le chiamate successive fanno un tentativo solo finche' una non riesce.
- RPC che scrivono e insert puri NON si ritentano su 520/524/502/503/504 (esito ambiguo): un 520 su
  quelle chiamate resta un errore come prima (riga chiara). Elenco delle RPC di lettura scritto a mano
  (`RPC_LETTURA_ACTION`): una RPC di lettura nuova va aggiunta li'.
- Il trasporto usa l'attributo privato `httpx.Client._transport` (httpx 0.28.1, vincolato da
  supabase==2.28.0 `httpx<0.29`): se cambia, `_installa_trasporto_resiliente` torna False e lo script
  gira come prima (nessun crash), ma senza ritentativi.
- `cancelled()` dopo un `timeout-minutes`: non verificato su GitHub.
- Nessuna prova dal vivo (vietato lanciare workflow): la prova vera e' la notte del 10/10.
- **Da fare dal coordinatore** (punti riservati all'altro delegato): nessuno necessario; i blocchi
  `inputs:`, `PROSSIMO_ANELLO`, `passa_testimone.sh`, `riserva_da_catena` non sono stati toccati.

## 6. Cosa guardare la mattina del 10/10

1. Pagina Actions: per ogni anello, nel log cercare `[RETE]` (ritentativi riusciti: classe, codice,
   attesa) e `GUASTO DB PERSISTENTE` (deve essere assente o accompagnato dal titolo della pagina).
2. Retrain: se c'e' `RECHAIN NON ESEGUITO` la run e' verde con avviso e Post-Cal deve essere partita.
3. Hazard: `[atlante] scrittura rpc/hazard_atlas_salva_versione KO (520)` quante volte; se compare
   `ma la riga RISULTA scritta sul DB` i 520 arrivavano al DB (conferma la necessita' di D-A).
4. Post-Cal: nel passo di installazione `supabase-2.28.0`.
5. Confronto con i tempi: nessun job vicino ai nuovi tetti (Daily 120, Today 330, Results 240).

## 7. File toccati

`db_client.py`, `training_planner.py`, `Betfair/stream/scalper/genera_atlante.py`, i `__main__` di
14 script (par. 2.2), `.github/workflows/retrain_models.yml`, `hazard_atlas.yml`, `ml_calibration.yml`,
`daily_yesterday_backfill.yml`, `today_predictions_backfill.yml`, `predictions_results_backfill.yml`,
`weekly_poisson_calibration.yml`. Nuovi: `test_fallimenti_action_2026_10_09.py`, questa cartella
(`REFERTO.md`, `mutazioni_fallimenti.py`, `mutazioni_esito.txt`). CRLF conservati, codice ASCII.

## 8. Blocco per CRONOSTORIA

```
### Checkpoint - fallimenti delle action (09/10/2026, delegato Opus, worktree wt-fallimenti, ramo cantiere-fallimenti-action)
- Parte 1: 300 run (14/09-09/10), 31 failure + 3 cancelled (a mano). (a) DB transitorio 25 (18 x 57014
  del 15-28/09, gia' risolte; 7 x 520/521/522/GOAWAY), (b) crash DB 09/10 2, (c) regola API vuota del
  Catchup 3 (risolta 04/10), (d) config 1 (25/09), (e) GitHub 0. Prima di oggi risolte 28/31; aperte:
  Post-Cal 05/10 (521), Retrain rechain 09/10 (522, shard riusciti), Hazard 09/10 (520).
- Reperto: dal 02/10 ogni rossa di Leagues/Post-Cal/Catchup/Retrain e' nello STESSO secondo di un 520
  della scrittura globale dell'atlante (~27 MB, rpc/hazard_atlas_salva_versione); il 09/10 l'atlante
  ha mandato 9 di queste scritture dentro la finestra del crash 07:25-07:51. DECISIONE D-A per l'utente.
- Rimedi: db_client.TrasportoResiliente (ritentativi a livello httpx per i SOLI processi delle action,
  regole di idempotenza, +1 attesa lunga 120 s), esegui_main_action nel __main__ di 14 script (riga
  "GUASTO DB PERSISTENTE" + exit 1, traceback in un gruppo); planner: guasto di rete non piu' inghiottito,
  attese lunghe 60/120/240; rechain: guasto DB persistente = avviso + exit 0 (staffetta passa), gh con
  ritentativo anti-doppio; atlante: JSON compatto (-11,7%), niente reinvio se la riga risulta gia'
  scritta, pre-controllo con ritentativi; tetti dei job (Daily 120, Today 330, Results 240, Weekly 90);
  Post-Cal con supabase==2.28.0 fisso.
- Test: test_fallimenti_action_2026_10_09.py 33/33; falsificazione 26/26 rosse, ripristino sha identico;
  suite collegata 841 -> 874 passed, 10 skipped; actionlint 0 errori.
- Non toccati: inputs:, PROSSIMO_ANELLO, passa_testimone.sh, riserva_da_catena (altro delegato).
- Ripresa: revisione del coordinatore; commit su percorsi espliciti; la mattina del 10/10 leggere
  [RETE] / GUASTO DB PERSISTENTE / RECHAIN NON ESEGUITO / "RISULTA scritta" nei log; decidere D-A.
```
