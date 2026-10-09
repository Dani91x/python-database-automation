# INDAGINE DISCO DB - cosa si puo' togliere (SOLA LETTURA, 09/10/2026, master c4fc5fbf)

Ordine dell'utente: "FAI CONTROLLO SUL DATABASE PER ALLEGGERIRE IL DISCO, COSA POSSIAMO TOGLIERE CHE NON SERVE
ASSOLUTAMENTE A NULLA? SOLO INDAGINE". Nessuna DELETE, nessuna migrazione, DB non toccato (nessuna query: i numeri di
dimensione/righe/byte-per-colonna sono quelli misurati dal coordinatore; io ho solo letto il codice del repo).

Perimetro della ricerca: tutto il repo ESCLUSE le copie in `.claude/worktrees`, `_checkpoint_2026-09-28`, `AUDIT_*` e
i test. Cosa NON ho potuto verificare (da leggere con prudenza):
- funzioni/viste/trigger che esistono SOLO nel DB e non nel repo (un lettore nascosto in una funzione SQL non si vede);
- `pg_stat_user_indexes.idx_scan` di oggi (nel repo c'e' solo la misura del 21/09 su 4 indici di fixture_predictions);
- la ripartizione delle righe per `event_type` / per `market_name` (stimata solo da commenti del codice);
- se le migrazioni "DA APPLICARE" (es. `migrations/actions_57014_2026-09-21_DA_APPLICARE_DALL_UTENTE.sql:64-81`) sono state applicate.

## 0. Tre fatti che cambiano il ragionamento

1. **Lo storico NON e' tagliabile per eta'.** Finestre massime dei lettori:
   - Training ML: workflow `.github/workflows/retrain_models.yml:304,313` passa `LAST_N_SEASONS = inputs.last_n_seasons || '20'`
     a `cloud_retrain_shard.py` (default del file `:176` = 3, ma il workflow lo sovrascrive con 20); `train_and_save_all`
     prende `seasons[-last_n_seasons:]` (`Ai Engine/ai_engine/seriea_model_export.py:511,524`). Quindi eventi, statistiche
     squadra/giocatore e quote di TUTTE le stagioni disponibili (fino a 20) possono servire al training.
   - Serving ML: 3 stagioni (`Ai Engine/ai_engine/predict_fixture.py:688` `PREDICT_LAST_N_SEASONS=3`; lo storico "profondo" e' solo `matches`, `:473-480`).
   - Poisson: `update_poisson_calibration.py:143-152` e `generate_dynamic_cal.py:118-128` leggono TUTTE le fixture FT con
     `db_json_analisi`, senza filtro di data (cursore su `fixture_id`).
   - Atlante hazard: 10 stagioni di gol per lega (`Betfair/stream/scalper/atlante_a_domanda.py:65` `stagioni_max: 10`);
     transizioni Omega: tutte le partite FT (`migrations/omega_transitions_catchup_2026-09-25.sql`, giro di controllo su tutto lo spazio id).
   => Nessuna riga "piu' vecchia della finestra piu' larga" e' dimostrabile oggi (la finestra piu' larga e' 20 stagioni = tutto).
   Le proposte sotto tolgono COLONNE, TABELLE e RIGHE DI MERCATO MAI LETTI, non righe per eta'.
2. **Togliere una colonna o delle righe NON libera disco da sola.** In Postgres serve riscrivere la tabella
   (CREATE TABLE AS + scambio, o pg_repack/VACUUM FULL). `UPDATE ... SET raw_json = NULL` fa il contrario: genera righe morte
   e AUMENTA il disco. Con 4-6 GB di margine si puo' riscrivere una tabella alla volta e solo se la copia nuova entra:
   match_team_stats, matches, match_events, match_player_stats entrano (copie nuove ~0,3 / 1,1 / 2,0 / 1,7 GB, stima da
   dimensione meno raw_json); match_odds NO con la riscrittura completa (copia da ~17 GB) ma SI con "copia solo delle righe lette" (~2 GB).
3. **Ogni scrittore va fermato PRIMA**, altrimenti la tabella ricresce: `per_fixture_backfill.py:383,447,647,748,867` scrivono
   `raw_json` in events/lineups/player_stats/team_stats/odds; `fixtures_backfill.py:88` in matches; `season_gaps.py` e
   `per_fixture_backfill.py:917-975` ri-scaricano e riscrivono per fixture.

## 1. Le sei tabelle match_* e matches

### 1.1 match_odds - 21 GB, 92,5 M righe (dati 17 / indici 3,8)
Contenuto: una riga per (fixture x bookmaker x mercato x valore). Colonne scritte da `per_fixture_backfill.py:840-870`:
fixture_id, league_id, season_year, bookmaker_id, bookmaker_name, market_key, market_name, label, odd_value,
snapshot_type ('api_football'), snapshot_time (None), raw_json (= `val`, cioe' {"value","odd"}: copia esatta di label+odd_value,
41 B su 175). Seconda fonte: 'football_data_csv' (`football_data_scraper/backfill.py:232,310`, raw_json = {"csv_col","value"}).
~4.300 righe per fixture, ~9% passa il filtro mercati (`Ai Engine/ai_engine/db_adapter.py:69-82,370-371`).
- SCRIVE: `per_fixture_backfill.py:922-975` (delete solo api_football + insert; cadenza: workflow seasons_catchup `47 13 * * *`
  e daily_yesterday_backfill), `football_data_scraper/backfill.py:460` (CSV), `fix_snapshot_time.py:45` (update).
- LEGGE (tutti i lettori trovati):
  - ML training+serving: `Ai Engine/ai_engine/feature_pipeline.py:622-629,636-642` con colonne
    `fixture_id,market_name,label,odd_value,snapshot_time` e filtro `market_name IN ("Match Winner","Goals Over/Under",
    "Both Teams Score","Over/Under","Goals Over Under")` (`:581-587`); poi `_odds_features` (`:35-81`) usa solo label 1/X/2,
    over/under 1.5-2.5-3.5 (`ai_config.py:12`), yes/no, mediana su TUTTI i bookmaker all'ultimo snapshot. NESSUN filtro per
    bookmaker: tutti i bookmaker dei 5 mercati sono letti.
  - `Ai Engine/ai_engine/backtest.py:58-65` (`_fetch_odds_by_fixture`, SENZA filtro mercati, colonne
    fixture_id,bookmaker_name,market_name,label,odd_value): nessun chiamante nel repo (grep `ai_engine.backtest`: solo il
    commento di `db_adapter.py:379`); usa comunque solo le chiavi match_winner / both_teams_score / goals_over/under 0.5..4.5 (`:42-50`).
  - `market_intelligence/backtest_audit.py:124,138,149`: `select("*")` con limit 3 / range, script di audit.
  - Solo "esistenza": `season_gaps.py` / `migrations/season_gaps_perf_2026-09-28.sql:153-168` (conta `snapshot_type='api_football'`),
    `daily_yesterday_backfill.py:153`.
  - Frontend: nessuno (`frontend/src/lib/safeBot.ts:1980` parla di un blocco 'match_odds' del feed Betfair, non della tabella).
- COLONNE: `raw_json` MAI LETTA (nessun `select` la nomina per match_odds) -> 3,8 GB. `market_key`, `bookmaker_id`, `league_id`,
  `season_year`: mai nei `select` dei lettori (non le conto: piccole, servono a chi riscrive).
- RIGHE: ~91% delle righe sta in mercati che nessun lettore in produzione richiede. Stima: 92,5 M x 91% = ~84 M righe non lette;
  copia dei soli mercati letti senza raw_json = ~8,3 M righe = ~1,5 GB dati + ~0,35 GB indici. RECUPERABILE ~19 GB (include i 3,8 di raw_json).
- ATTENZIONE: (a) irreversibile in pratica: `season_gaps.py:21` dichiara "non_disponibile solo match_odds, partita di oltre 7 giorni fa:
  API-Football non restituisce piu' le quote" - le quote storiche non si riscaricano. Prima esportare gli ~84 M in un file
  compresso fuori dal DB. (b) lo scrittore `map_odds` (`per_fixture_backfill.py:780-870`) deve filtrare ai 5 mercati, altrimenti
  il prossimo backfill li reinserisce. (c) un futuro modello che voglia altri mercati (handicap, corner...) non li troverebbe.
- INDICI (migrazioni): `migrations/sanatorie_2026-09-28.sql:604-613` dichiara che su match_odds esistono, oltre alla pkey,
  `idx_match_odds_fixture` (fixture_id) e un indice (league_id, season_year, fixture_id). I lettori filtrano SOLO per fixture_id
  (`db_adapter.py:388-415`, ordine `("fixture_id","id")` `:99`). L'indice composto league/season e' candidato all'eliminazione
  ma NON provato (serve `idx_scan`). Nota: `genera_atlante.py:727-731` (25/09) afferma che su match_events NON c'e' indice
  (league_id, season_year), mentre `sanatorie_2026-09-28.sql:611` (28/09) afferma che c'e': contraddizione, va misurata.

### 1.2 match_lineups - 7,6 GB, 24,3 M righe - MAI LETTA
- SCRIVE: `per_fixture_backfill.py:211,407-500,917` (endpoint /fixtures/lineups), `daily_yesterday_backfill.py:147`.
- LEGGE: nessuno. Grep `match_lineups` su Python/TS/SQL: solo `per_fixture_backfill.py`, `season_gaps.py:9,52`,
  `daily_yesterday_backfill.py:147`, e migrazioni di sola esistenza (`season_gaps_*.sql`, indici, RLS). Nessun `select` di colonne
  di match_lineups nel feature pipeline, nel tactical_engine, nel frontend, nei bot, nelle Edge function. Il `LineupsCard.tsx`
  del frontend legge `team.league.lineups` da `fixture_predictions.raw_json` (`frontend/src/lib/normalizePrediction.ts:59,194`), NON dalla tabella.
- Gli unici "lettori" sono i controlli di completezza (season_gaps, daily_yesterday): se la tabella sparisce vanno tolti
  dall'elenco delle tabelle richieste, altrimenti segnalano buchi eterni e ri-scaricano (quota API).
- RECUPERABILE: 7,6 GB (tabella intera, di cui raw_json 2,7).

### 1.3 match_player_stats - 6,8 GB, 5,4 M righe
- SCRIVE: `per_fixture_backfill.py:569-760` (raw_json `:647`).
- LEGGE: `feature_pipeline.py:606-615,643-650` (fixture_id,team_id,minutes,rating,shots_total,shots_on,goals_total,assists_total,
  passes_*,tackles_total,interceptions,duels_*,dribbles_*,fouls_*,yellow_cards,red_cards,offsides) e `predict_fixture.py`
  (stesse letture); storico = ultime 3 stagioni in serving, fino a 20 in training.
- COLONNE: `raw_json` 947 B su 1.097 B (86%) mai letta -> ~5,1 GB. Nessun lettore la nomina.

### 1.4 match_events - 5,6 GB, 9,8 M righe
- SCRIVE: `per_fixture_backfill.py:350-400` (`raw_json: ev` a `:383`).
- LEGGE: ML (`feature_pipeline.py:597-599,633-635`: fixture_id,team_id,event_type,detail,minute); `build_analytics_signals.py:376`
  (id,fixture_id,minute,detail,comments, solo Goal, finestra `--days`, `:329`); `build_inplay_intensity.py:88` (per event_type);
  `value_engine/calibrate.py:37` (Goal: minute,detail); atlante hazard `Betfair/stream/scalper/genera_atlante.py:642` (Goal+minute_extra,
  10 stagioni); Omega `estrai_transizioni.py` / `omega_transitions_*` (Goal, 0..90'); live_engine (intensita').
- COLONNE: `raw_json` 364 B su 502 B (72%) mai letta -> ~3,6 GB. `minute_extra` e `comments` sono GIA' colonne estratte
  (`per_fixture_backfill.py:366-382`; `atlante_v4.py:171` cita `raw_json.time.extra` solo nel commento di una misura).
  Nessun lettore ri-estrae campi dal raw_json di match_events.
- RIGHE: i lettori dedicati filtrano quasi tutti `event_type = 'Goal'` (il ML legge tutti i tipi). Righe di tipo mai letto
  (es. sostituzioni): NON quantificabili senza DB; non le conto.

### 1.5 match_team_stats - 1,36 GB, 6,4 M righe
- SCRIVE `per_fixture_backfill.py:700-760` (raw_json `:748`). LEGGE `feature_pipeline.py:595-605`
  (fixture_id,team_id,stat_type,value_numeric), `market_intelligence/audit.py:83`, `edge_scorer.py:472`, `signals.py:178`,
  `football_data_scraper/backfill.py:147` (esistenza).
- COLONNE: `raw_json` 51 B su 151 B mai letta -> ~0,33 GB.

### 1.6 matches - 3,0 GB, 1,49 M righe (dati 2,4 / indici 0,63)
- SCRIVE `fixtures_backfill.py:135` (raw_json `:88`), `daily_yesterday_backfill.py:75`. LEGGE: 40 punti di produzione
  (`ARCHITETTURA_2026-10/strumenti/inventario/uscite/s03_matrice_tabelle.tsv`), ML (`db_adapter.py:345-357` solo colonne scalari), Poisson, bot.
- COLONNE: `raw_json` 1.251 B su 1.446 B (86%) -> ~1,9 GB. E' LETTA, ma SOLO per tre campi, via proiezione JSON:
  1. `raw_json->league->>round`: `Betfair/safe_strategy/db.py:180-186` (round per il veto delle finali), `engine.py:598`,
     `veto_campionati.py:172`, `selezione.py:245`;
  2. `raw_json->fixture->status->extra` (recupero 2T): `genera_atlante.py:641` (`COLONNE_MATCH`), `validazione_hazard/raccogli.py:42-46`;
  3. `raw_json->fixture->periods->first/second` (inizio dei tempi): `validazione_hazard/raccogli.py:45-46`.
  Nessun lettore scarica l'intero raw_json (commento `safe_strategy/db.py:149`: "mai l'intero raw_json"). Dunque: estrarre
  questi 4 valori in colonne (round, status_extra, period_first, period_second) e raw_json diventa eliminabile. E' una
  MODIFICA DI CODICE in 3 lettori + 1 scrittore, non un semplice drop.

## 2. fixture_predictions - 1,07 GB (toast 689 MB), 122 k righe, riga ~6.391 B
Tutte le colonne grosse hanno lettori, nessuna e' eliminabile per intero:
- `raw_json` (3.495 B, ~427 MB): `frontend/src/pages/Dashboard.tsx:53-60`, `components/dashboard/FixtureSelector.tsx:31-40` (per singola
  fixture aperta), `Betfair/safe_strategy/db.py:149-186` (proiezioni h2h/comparison/last5, partite imminenti),
  `import_betfair_operations.py:44,61-62` (country), `Betfair/betfair_report_manager.py:63,344`. Letta per fixture aperta
  dall'utente o imminente; il taglio per eta' (stagioni passate) perde la scheda delle partite storiche nella Dashboard:
  decisione dell'utente, non "senza perdita".
- `raw_json_odds` (1.870 B): ML (`feature_pipeline.py:84-130,667`), `generate_dynamic_cal.py:122,278`, `calibration_analysis.py:354`,
  `market_intelligence/*` (audit/backtest/calibration/edge_scorer/pipeline/signals), `master_backtest.py:679-966`, RPC
  `migrations/analytics_strategy.sql:163-165` e `refresh_analytics_bets_range_v2_2026-09-24.sql:114-160` (unnest di tutta la storia).
- `model_predictions_json` (4.228 B): `build_analytics_signals.py`, `fix_storico_prob.py`, `master_backtest.py:679`, `MLPanel.tsx`,
  `fixtureModels.ts`, `get_direction_rpc.sql`, Telegram `telegram-bot/index.ts`.
- `db_json_analisi` (1.003 B): Poisson (`generate_dynamic_cal.py:122`, nessuna finestra), `build_analytics_signals.py:332`.
- `tactical_engine_json` (1.130), `flat_summary` (556), `ht_predictions` (148): tactical_engine, `get_direction_rpc.sql`,
  `analytics_features.sql`, `ventaglio_segnali.py`, Telegram.
- INDICI: `migrations/actions_57014_2026-09-21_DA_APPLICARE_DALL_UTENTE.sql:64-69` documenta 4 indici con idx_scan=0 al 21/09:
  `idx_fixture_predictions_raw_json_gin` 133 MB, `..._flat_summary_gin` 21 MB, `..._date` 2,5 MB (duplicato di `..._fixture_date`),
  `..._league_season` 1,1 MB. Non so se sono stati eliminati: da verificare (totale ~157 MB, ripristinabili con la definizione
  riportata `:77-81`). Il file stesso avverte di chiedere all'utente prima dei GIN.

## 3. Le altre tabelle sopra i 20 MB

| Tabella | Scrive | Legge | Note |
|---|---|---|---|
| live_market_snapshots 2,4 GB (ladder 1.495 B su 1.581) | `Betfair/stream/db.py:629-630` (curator `curator.py:104`, uploader) | RPC `get_replay*` (`migrations/live_stream_rpc_get_replay_perf.sql:88-110`, `live_stream_rpc_chunked.sql`), `frontend/src/lib/live.ts:339-417` (Replay UI) | `ladder` e' il contenuto: letta. Ultimo dato: ts 2026-09-01 (scheda G), `created_at` 22/09 (`live.ts:243-245`). Indici `idx_lms_event_market_ts`, `idx_lms_event_ts` (`migrations/live_stream.sql:109-112`). E' l'archivio del Replay UI; le registrazioni locali jsonl sono la fonte di certificazione dei bot, non questa tabella. Tagliare = perdere i replay UI di quegli eventi (decisione dell'utente). |
| analytics_signals 1,1 GB (indici 752 MB su 362 MB dati) | `build_analytics_signals.py:402`, `fix_storico_prob.py:59` | RPC `direction_report_rpc.sql:129,438,560`, `analytics_rpc_veloci_2026-09-26.sql:153-154,228,510,760`, `refresh_analytics_bets_range_v2_2026-09-24.sql:96,240`, `betfair_report_manager.py` | Indici da migrazioni: pkey, `signal_uid` UNIQUE (`analytics_signals.sql:35`), `idx_as_engine_market_league`, `idx_as_settled` (parziale), `idx_as_league_season`, `idx_as_kickoff`, `idx_as_fixture`, `idx_as_market_selection` (`analytics_signals.sql:96-106`), `idx_as_eval_cover` (include 8 colonne, `analytics_perf.sql:44-46`), `idx_as_league_id_id` (`analytics_signals_idx_league_id_2026-09-24.sql:28`). Filtri reali visti: engine+settled+kickoff range (`direction_report_rpc.sql:129-135`), settled+hit+prob (`rpc_veloci:228-231`), kickoff range (`refresh_..:96`), fixture_id. NESSUN filtro visto su (market, selection) da solo ne' su (league_id, season_year) da solo: `idx_as_market_selection` e `idx_as_league_season` sono candidati; `idx_as_eval_cover` serviva la scansione ampia che dal 26/09 e' sostituita da `analytics_riepilogo_segnali` (`rpc_veloci:50-75`) ma il refresh del riepilogo (`:222-231`) la usa ancora: da misurare. Recuperabile STIMATO 0,3-0,5 GB, richiede `idx_scan`. |
| analytics_bets 344 MB | funzione SQL `refresh_analytics_bets_range` (via `refresh_analytics_bets.py`) | RPC `get_direction_rpc.sql:163-167`, `get_direction_eta_2026-09-25.sql:62`, `analytics_strategy_rpc.sql:124,236`, `DirezioneDashboard.tsx`, `direzione.ts` | DERIVATA (ricostruibile da analytics_signals + book_odds_cache, `refresh_analytics_bets.py:1-30`). 4 indici (`analytics_strategy.sql:131-134`). Letta: non eliminabile. |
| analytics_decisions 66 MB, engine_signals 59 MB | `merge_engine_signals.py`, `migrations/backfill_engine_signals.py:278` | `DecisionsView.tsx`, `certify_backtest_strategy.py:103`, RPC analytics | Letti. |
| analytics_riepilogo_segnali 62 MB, book_odds_cache 61 MB | RPC di refresh | RPC `analytics_rpc_veloci`, `analytics_strategy` | Cache derivate, lette. Non eliminabili. |
| api_call_log 517 MB, 2,75 M righe | `logger.py:86,91` (ogni chiamata API) | SOLO `api_quota.py:144-185` (`conta_log_oggi`: oggi; `consumo_giorni_log`: ultimi 7 giorni + oggi) e `seasons_catchup.py:86,1002` (media 7 giorni) | Finestra massima dei lettori = 8 giorni. Nessuna politica di scarto (scheda G `:218`). Oltre ~10 giorni = eliminabile senza perdita. Non so quanti giorni copre il log (created_at minimo non misurato): se copre >=30 giorni si recuperano >=70% = >=0,35 GB. `params` 31 B: trascurabile. Nessun indice noto su created_at (`api_quota.py` lo dice): cancellare per `id` (pkey). |
| top_cards 435 MB, top_scorers 175 MB, top_assists 59 MB, injuries 189 MB | `season_aggregates.py:194-238` via `*_backfill.py` (aggiornate 07/10) | NESSUNO: `s03_matrice_tabelle.tsv` (prod_legge e frontend_legge vuoti), scheda G `G-041` ("nessun lettore Python in repo e nessun lettore frontend"), grep su .py/.ts/.tsx/.sql: solo backfill, `season_gaps.py` (esistenza), `leagues_mapper.py`, `db_delete_retry.py`, RLS | MAI LETTE (salvo funzioni solo-DB non verificabili). `raw_json` (`top_cards_backfill.py:209` ecc.) e' parte del peso. RECUPERABILE ~0,86 GB (tabelle intere) o circa meta' se si toglie solo raw_json. Rischio: dati "per una funzione futura"; `season_gaps` li conta come coperture. |
| standings 112 MB | `standings_backfill.py:208-289` | ML `db_adapter.py:119-126,404-413`, `feature_pipeline.py:661-665`, `training_planner.py` | Letta. Tenere. |
| omega_minute_transitions_raw 286 MB, omega_minute_transitions 270 MB, omega_transitions_ledger 141 MB, omega_minute_transitions_pre_ledger 70 MB | funzioni SQL `omega_transitions_nightly` (cron 04:00 UTC, `omega_transitions_catchup_2026-09-25.sql:74-380`) | bot via RPC `get_omega_minute_ft` (legge `omega_minute_transitions`, `omega_models_v4.sql:94-98`), `omega_empirical.py:164`, `estrai_transizioni.py:41`; `_raw` letta SOLO dalla pubblicazione e dalla verifica (`catchup.sql:387,722,826`, `verifica_transizioni_2026_09_25.py:43`) | NON sono doppioni puri: `_raw` = conteggi di TUTTE le leghe (2,05 M celle); `omega_minute_transitions` = pubblicazione (globale + leghe ammesse, 1,08 M celle); ledger = una riga per partita contata (anti doppio conteggio, necessario). `_pre_ledger` (1,07 M righe) e' la COPIA DI SICUREZZA dell'11/09 (creata `catchup.sql:694-709`, usata dal ripristino `:758-771` e dal confronto `:826-837`): l'unica davvero eliminabile, 70 MB, dopo che l'utente ha confermato la pubblicazione (CRONOSTORIA 25/09 h17: ricostruzione completa; la PUBBLICAZIONE e' ordine dell'utente: non so se e' avvenuta). Stessa natura per `omega_ht_ft_transitions_pre_ledger` e `omega_minute_league_counts_pre_ledger` (fuori dall'elenco > 20 MB). |
| tennis_replay_snapshots 257 MB | `Betfair/stream/tennis_replay/caricamento.py:75-108` | RPC replay tennis (`replay_tennis_2026-10-07.sql`), frontend replay | Letta. Tenere. |
| betfair_market_odds 75 MB | `Betfair/odds_refresh.py:254-257`, `betfair_full_odds.py:73-94` | `Betfair/order_exec.py:161`, `BetfairOddsPanel.tsx`, `betfair.ts`, tool Omega | Letta. Tenere. |
| hazard_atlas 52 MB (7 versioni da 5-6 MB), hazard_atlas_leghe 29 MB | `genera_atlante.py:1091-1109` (tiene `tieni=7`), action hazard_atlas | `hazard_atlas_sync.py:85-93` legge SOLO l'ultima versione (`order generated_at.desc limit 1`) | Le versioni 2..7 non sono lette da nessuno (rollback manuale). Portare `tieni` da 7 a 2: recupero ~27-33 MB. `hazard_atlas_leghe` e' lo stato incrementale: tenere. |
| ai_model_registry 30 MB, 20.534 righe | `seriea_model_export.py:686-689` (delete+insert per lega/target/modello), `cleanup_models.py` | `predict_fixture.py:512-516` legge solo 7 colonne (target,model_name,storage_bucket,storage_path,features_version,targets_version,trained_at); le altre da `betfair_report_manager.py:1224-1392` | Nulla di sensato da togliere (30 MB). |

## 4. Duplicati e log (riepilogo)
- `omega_*`: solo `_pre_ledger` eliminabile.
- `analytics_bets` / `book_odds_cache` / `analytics_riepilogo_segnali`: derivate (ricostruibili) ma lette dalle RPC; eliminarle rompe
  `get_direction_*` e i report finche' non si rigenerano.
- `hazard_atlas`: 6 versioni vecchie mai lette.
- `api_call_log`: oltre 10 giorni mai letto.
- `match_odds.raw_json` duplica label+odd_value al 100% (`per_fixture_backfill.py:864` `"raw_json": val`).

## 5. TABELLA FINALE

GB recuperabili = a riscrittura completata (par. 0.2). Non sommare righe sovrapposte (match_odds).

| Tabella | GB | Lettori | Cosa si puo' togliere senza perdita per nessun lettore | GB recup. (stima) | Rischio |
|---|---|---|---|---|---|
| match_odds | 21 | ML train/serve (5 mercati, `feature_pipeline.py:581-642`), backtest.py (nessun chiamante), season_gaps (esistenza) | raw_json (copia di label+odd_value) + ~84 M righe di mercati non letti (copia dei soli 5 mercati senza raw_json) | ~19 (di cui 3,8 raw_json) | MEDIO: irreversibile (quote >7 gg non riscaricabili, `season_gaps.py:21`); esportare prima; filtrare lo scrittore |
| match_lineups | 7,6 | nessuno (solo controlli di esistenza) | tabella intera + smettere di scaricarla | 7,6 | BASSO-MEDIO: dato non usato oggi, perso per sempre; modificare season_gaps/daily/per_fixture |
| match_player_stats | 6,8 | ML (`feature_pipeline.py:606-650`) | colonna raw_json (86% della riga) | ~5,1 | BASSO |
| match_events | 5,6 | ML, analytics, atlante, Omega, calibrate | colonna raw_json (72%) | ~3,6 | BASSO |
| matches | 3,0 | 40 lettori; raw_json solo per round / status.extra / periods | raw_json dopo aver estratto 4 valori in colonne | ~1,9 | BASSO-MEDIO: cambia 3 lettori + 1 scrittore |
| live_market_snapshots | 2,4 | Replay UI (`get_replay*`) | niente "senza perdita": eventi vecchi = replay UI perso | 0 (decisione utente) | - |
| match_team_stats | 1,36 | ML, market_intelligence | colonna raw_json | ~0,33 | BASSO |
| analytics_signals | 1,1 | RPC direzione/analytics | indici candidati (market_selection, league_season, forse eval_cover) | ~0,3-0,5 da misurare | BASSO se idx_scan=0 |
| fixture_predictions | 1,07 | tutte le colonne lette | indici GIN raw_json/flat_summary + 2 btree duplicati (se ancora presenti) | ~0,16 | BASSO (chiedere per i GIN) |
| api_call_log | 0,52 | solo ultimi 8 giorni | tutto cio' che e' piu' vecchio di ~10 giorni | >=0,35 (dipende dalla copertura) | BASSISSIMO |
| top_cards + top_scorers + top_assists + injuries | 0,86 | NESSUNO | tabelle intere (o solo raw_json) | 0,86 (o ~0,4) | BASSO-MEDIO (dati "futuri"; contati da season_gaps) |
| omega_*_pre_ledger (3 copie) | 0,07+ | solo ripristino/confronto | dopo conferma della pubblicazione | ~0,08 | BASSO |
| hazard_atlas | 0,05 | solo ultima versione | 5 versioni vecchie | ~0,03 | BASSISSIMO |
| analytics_bets, book_odds_cache, riepilogo, decisions, engine_signals, standings, tennis_replay, betfair_market_odds, ai_model_registry, hazard_atlas_leghe, omega raw/pubblicate/ledger | ~1,6 | letti | nulla | 0 | - |

Totale teorico con P1+P2+P3 (senza doppi conteggi): circa 10,9 + 19 + 7,6 = ~37,5 GB su 52 GB (margine da 4-6 a ~40 GB).

## 6. TRE PROPOSTE ordinate per GB recuperati / rischio

**P1 - raw_json mai letto di match_player_stats, match_events, match_team_stats (+ matches dopo estrazione di 4 campi): ~10,9 GB, rischio BASSO.**
Ordine di esecuzione per spazio: team_stats (0,33) -> matches (1,9) -> events (3,6) -> player_stats (5,1). Prima: fermare gli
scrittori (`per_fixture_backfill.py:383,447,647,748`, `fixtures_backfill.py:88`) e, per matches, aggiungere 4 colonne
(round, status_extra, period_first, period_second) e spostare i 3 lettori (`safe_strategy/db.py:180-186`, `genera_atlante.py:641`,
`raccogli.py:42-46`). Poi copia tabella senza raw_json + scambio (non UPDATE: farebbe crescere il disco). Falsificazione: i test
dei 3 lettori + un replay Safe sulla fascia "finali" (veto round).

**P2 - match_odds: tenere solo i 5 mercati letti, senza raw_json (copia + scambio): ~19 GB, rischio MEDIO.**
Maggior recupero e unico fattibile con il margine di 4-6 GB (copia da ~2 GB). Condizioni: (1) archivio compresso esterno degli
~84 M di righe scartate, perche' le quote storiche non si riscaricano (`season_gaps.py:21`); (2) filtro dei 5 mercati in `map_odds`
(`per_fixture_backfill.py:834-870`) e nel CSV, altrimenti la tabella ricresce; (3) controllo che i conteggi per fixture dei 5
mercati prima e dopo coincidano e che le feature `odds_*` del training siano identiche (confronto numero per numero); (4) l'utente
conferma di non voler altri mercati. Non cambia il risultato di nessun modello (le feature leggono esattamente quei 5 mercati
con le stesse label).

**P3 - match_lineups: smettere di scaricarla e togliere la tabella: ~7,6 GB, rischio BASSO-MEDIO.**
Nessun lettore. Togliere `lineups` da `per_fixture_backfill.py:211,917`, `season_gaps.py:9,52`, `daily_yesterday_backfill.py:147`
(altrimenti i controlli la richiedono per sempre) e dal flag di coverage. Se l'utente vuole tenerla per un uso futuro
(formazioni per TacticAI), alternativa: tenerla senza raw_json (2,7 GB recuperati).

**Extra a costo quasi zero (misurare prima `idx_scan`):** retention `api_call_log` 10 giorni (>=0,35 GB); `hazard_atlas` tieni=2
(~0,03); drop `_pre_ledger` dopo la pubblicazione Omega (~0,08); indici GIN/duplicati di fixture_predictions (~0,16); indici di
analytics_signals e del composto league/season dei match_* (da misurare). Query di misura suggerita (SOLA LETTURA):
`select relname, indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid)) from pg_stat_user_indexes order by
pg_relation_size(indexrelid) desc limit 40;` e, per i mercati, un `group by market_name` su UN fixture_id campione (mai sull'intera
tabella da 92 M righe).

## 7. Divergenze da portare all'utente
- La finestra di training reale e' 20 stagioni (`retrain_models.yml:304`), mentre `training_planner.py:46-48` e la scheda G parlano
  di "ultime 3 stagioni": per questo nessuna riga e' tagliabile per eta'.
- Contraddizione sugli indici di match_events (`genera_atlante.py:727-731` vs `sanatorie_2026-09-28.sql:604-613`).
- `ai_engine/backtest.py` legge match_odds senza filtro e nessuno lo chiama: se un domani lo si usa, le chiavi di `TARGET_ODDS_MAP`
  sono gia' coperte dai 5 mercati.
