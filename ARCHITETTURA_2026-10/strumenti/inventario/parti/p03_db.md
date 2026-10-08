## 3. Accesso al database (Supabase)

Script: `s03_db.py` (Python via AST: `.table(`, `.from_(`, `.rpc(`, `.storage`, REST diretto `rest/v1/`; TypeScript via regex:
`.from(`, `.rpc(`) -> `uscite/s03_chiamate.tsv` (966 chiamate, una riga per chiamata con `file`, `riga`, operazione,
categoria), `s03_matrice_tabelle.tsv`, `s03_matrice_rpc.tsv`, `s03_definizioni.tsv`, `s03_riepilogo.txt`; controllo `s05_tabelle_stringa.py`
(`uscite/s05_tabelle_stringa.tsv`); tabelle markdown `g01_tabelle_md.py` (`uscite/g01_tabelle_db.md`, `g01_rpc.md`).
Limite dichiarato: la lettura/scrittura di una chiamata e' dedotta dal metodo concatenato (`.select/.insert/.upsert/.update/.delete`); dove non si
vede (`.table(x)` passato a una funzione) la chiamata e' in «op?»; i nomi non letterali sono `<dinamico:...>` (6 nomi: `table`, `tabella`, `nome`, `name`, `t`, `MU.TABELLA_ORDINI_CONTO`; i primi due 22 punti,
tutti in helper generici di `Betfair/stream/db.py:564-596`, `Betfair/omega/omega_db.py:181`, `Ai Engine/ai_engine/db_adapter.py:231`,
`football_data_scraper/backfill.py:342`, `season_aggregates.py:229-238`, `Betfair/stream/live_order_worker.py:3288-3291`,
`Betfair/stream/scalper/scalper_session.py:962`).

### 3.1 Chi parla con il DB e quanto: il confronto con il brief

Un solo client di produzione (`db_client.py:75`, uno per thread) piu' uno secondo in `tennis_db.py:22`; 5 moduli DB «per bot» (uno per bot,
con 32-53 chiamate `.table(` ciascuno) piu' chiamate sparse nei servizi. I numeri del brief (§1) tornano tutti tranne uno
(`live_order_worker.py`: brief 18, misurato 17).

{{sez:s03_riepilogo.txt:chiamate trovate}}
{{sez:s03_riepilogo.txt:== A. }}
{{sez:s03_riepilogo.txt:== B. }}

Lettura: i tre moduli DB dei bot di punta (`omega_db.py` 44, `bot_db.py` 46, `mike/db.py` 32) e quello dello stream (`stream/db.py` 53) hanno le
stesse operazioni sulle stesse tabelle «ordini» (scrittura in coda `betfair_live_order_requests`: `mike/db.py:683`, `omega_db.py:674`,
`bot_db.py:1029`; lettura dello specchio `betfair_live_orders`: `mike/db.py:233`, `omega_db.py:687`, `bot_db.py:1040`): vedi 4.3.

### 3.2 Matrice tabella -> file che leggono / scrivono (89 tabelle toccate da produzione o frontend, piu' i nomi dinamici)

Colonne: `definita in` = file `.sql` tracciato che crea la tabella (`migrations`/`sql`) oppure «NON nei .sql tracciati»; `chiamate prod / FE` = n.
di chiamate Python di produzione / TypeScript non di test; `scrive`/`legge` = primi 3 `file:riga` (il numero in `(+N)` e' quanti altri);
`frequenza misurata` = SOLO le tabelle presenti in `SCHEMI_BOT/sistema/MISURE_2026-10-02.md` (finestra 60 s del 02/10/2026, 15:15:40-15:16:40
UTC, chiamate al minuto per servizio; `MISURE:NN` = riga di quel file). Nessun'altra frequenza e' scritta in questo inventario.

{{file:g01_tabelle_db.md}}

### 3.3 RPC (funzioni del database)

170 RPC distinte chiamate da produzione o frontend (`s03_riepilogo.txt`, sezione D); 150 dal frontend (`f01_frontend.py`). Frequenze misurate solo per
5 RPC (`MISURE:102`, `:136`, `:164`, `:68`, `:95`).

{{file:g01_rpc.md}}

RPC chiamate ma non definite nei `.sql` tracciati: `fetch_missing_fixture_coverage` (usata dal solo job di pipeline) e il nome letterale `rpc`
(falso positivo di una variabile). 49 funzioni definite nei `.sql` e mai chiamate da produzione o frontend sono elencate in
`uscite/s03_riepilogo.txt` sezione D (molte sono usate da `pg_cron`/altre funzioni: `omega_transitions_*`, `omega_build_minute_transitions_*`,
`refresh_analytics_*`: non verificabile dal repo).

### 3.4 Tabelle definite e mai usate / usate e non definite

{{sez:s03_riepilogo.txt:== C. }}

Controprova per stringa (`s05_tabelle_stringa.py`, nome come parola intera in tutto il codice di produzione, frontend e workflow):

- Delle 32 tabelle definite senza `.table()` letterale (`fixture_detail_checks` e' ora usata da `season_gaps.py`, modificato nell'albero di lavoro), **11 sono riferite per stringa** (es. `betfair_live_settings`: nominata nei commenti di
  `Betfair/omega/omega_service.py:2188` e `Betfair/safe_strategy/execution.py:144`, letta davvero dall'RPC `get_live_settings`,
  `Betfair/stream/live_order_worker.py:498`; `hazard_atlas` in
  `Betfair/mike/dossier.py:30` e nel workflow `.github/workflows/hazard_atlas.yml:86-90`; `live_market_snapshots` in `Betfair/stream/curator.py:104`,
  `Betfair/stream/db.py:629`; `live_score_timeline` in `Betfair/stream/db.py:634-635`; `tennis_replay_snapshots`/`tennis_replay_punteggio` in
  `Betfair/stream/tennis_replay/caricamento.py:35-36`; `omega_requests` in `Betfair/omega/certificazione.py:1603`; `book_odds_cache` in
  `refresh_analytics_bets.py:8`; `fixture_detail_checks` in `season_gaps.py:14`; `omega_ht_ft_transitions` in `Betfair/omega/omega_empirical.py:10`;
  `strategies` e' falso positivo: parola comune).
- **21 tabelle senza nessun riferimento in produzione/frontend/workflow**: `analytics_prob_staging`, `analytics_riepilogo_{decisioni,meta,segnali}`,
  `book_odds_cache_fonte`, `omega_build_jobs`, `omega_ht_ft_transitions_{pre_ledger,raw}`, `omega_minute_league_counts`,
  `omega_minute_league_counts_pre_ledger`, `omega_minute_transitions`, `omega_minute_transitions_{pre_ledger,raw}`, `omega_transitions_{league_counts,ledger,runs,state}`,
  `personal_cash_movements`, `personal_trade_legs`, `sicurezza_bk`, `tennis_refresh_requests`. Sono tabelle del «mondo SQL»: compaiono solo in
  piu' file `.sql` (le `omega_*` in 1-3 file, `personal_*` 2-3, `sicurezza_bk` 3): le popolano/leggono funzioni e job del database
  (`omega_transitions_nightly`, `refresh_analytics_riepilogo`, ...). Che il DB le usi ancora **non e' verificabile dal repo** (servirebbe `pg_cron`/`pg_stat_user_tables` in sola lettura).
- **17 tabelle usate e non definite nei `.sql` tracciati**: `ai_model_registry`, `api_call_log`, `api_coverage_by_season`, `fixture_predictions`,
  `injuries`, `leads`, `match_events`, `match_odds`, `match_team_stats`, `matches`, `ml_post_calibration`, `model_performance`,
  `season_backfill_state`, `standings`, `top_assists`, `top_cards`, `top_scorers`. Tutte e 17 sono nominate in `DOCUMENTAZIONE_DATABASE.md`
  (`s05_tabelle_stringa.tsv`, seconda parte): il loro schema vive fuori dalle migrazioni tracciate (create dal pannello Supabase o prima
  dell'uso delle migrazioni). Non c'e' modo di ricostruirle da zero dal repo.
- «55 tabelle usate» (brief): le tabelle toccate da produzione Python sono 88, dal frontend 17, unione 89 (`s03_riepilogo.txt` sezione C).

### 3.5 Frequenze misurate (l'unica fonte di numeri sul carico: `MISURE_2026-10-02.md`)

Condizioni della misura (righe 3-22 del file): registri vivi dell'app, sessione aperta il 02/10/2026 alle 14:25:16 UTC, finestra 60 s
15:15:40-15:16:40 UTC, il brief del piano (§1) la descrive come «solo Mike acceso su 2 partite» (`MISURE_2026-10-02.md` non lo scrive); l'inventario del 02/10 avverte che
Omega era fermo (5/min non rappresentano Omega acceso) e che non c'erano partite tennis ne' sessioni scalper (`INVENTARIO_ARCHITETTURA.md`, «Punti non chiariti» 3-4).

| Servizio | Chiamate/min (60 s) | Media 5 min | Principali (MISURE) |
|---|---:|---:|---|
| runner-calcio | 552 (`MISURE:99`) | 549 (`:111`) | `betfair_live_order_requests` GET 189 (`:100`), `betfair_live_risk_rules` GET 168 (`:101`), RPC `get_live_settings` 123 (`:102`), `live_follow` 29 (`:103`) |
| mike-service | 279 (`:62`) | 268 (`:72`) | `mike_trades` GET 116 (`:63`), `mike_control` GET 58 (`:64`), `mike_requests` GET 58 (`:65`), `mike_events` POST 25 (`:66`) |
| safe-strategy-bot | 269 (`:131`) | 263 (`:144`) | `safe_strategy_trades` GET 81 (`:132`), `safe_strategy_requests` PATCH 53 + GET 44 (`:133-134`), `safe_strategy_control` 36 + 19 (`:135,137`), RPC `get_safe_aggregates` 19 (`:136`) |
| safe-strategy-service (scanner) | 86 (`:161`) | 87 (`:167`) | `safe_strategy_scan` POST 68 (`:162`), `mike_events` GET 6, RPC `list_bot_exposures` 6, `safe_strategy_status` POST 5 |
| scalper-service | 54 (`:178`) | 55 (`:182`) | `scalper_control` 18, `get_live_settings` 18, `scalper_service_control` 18 (`:179-181`) |
| tennis-bot-service | 36 (`:188`) | 43 (`:193`) | `tennis_bot_control` GET 18, `tennis_bot_service_control` PATCH 12 + GET 3 (`:189-191`) |
| runner-tennis | 28 (`:125`) | 29 (`:127`) | `tennis_live_follow` GET 28 (`:126`) |
| omega-service | 5 (`:85`) | 11 (`:88`) | `omega_trades` GET 4 (`:86`) |
| tennis-odds | 0 (4 chiamate in 29,8 min, `:202-204`) | 0 | `tennis_markets` DELETE 2 + POST 2 |
| **Totale** | **1.309** (`:51`) | | circa 22 al secondo |

Il brief del piano riporta «1.400 richieste/min»: la misura citata e' **1.309** (finestra 60 s) e **1.340 solo di Mike su 5 minuti** (`:72`);
il brief arrotonda. «Safe 255/min pur fermo»: la misura e' 269 (60 s) / 263 (5 min) (`:131`, `:144`).

### 3.6 Storage (bucket Supabase)

7 chiamate di produzione a `storage`: modelli ML scaricati da `Ai Engine/ai_engine/predict_fixture.py:83` e
`Betfair/betfair_report_manager.py:1335`, caricati da `Ai Engine/ai_engine/seriea_model_export.py:679` (`create_bucket` `:58`); manutenzione in
`cleanup_models.py:41-64`, `reset_ai_models.py:43-80`. Nessun accesso storage nel percorso Betfair.

