# Verifica di completezza della scheda G (tabella per tabella, §9.5 del brief) - 08/10/2026

Strumento: `strumenti/verifica/g_copertura_tabelle.py` (sola lettura, exit 0 = nessuna mancante). Uscite salvate: `g_copertura_PRIMA.txt`, `g_copertura_DOPO.txt`.
Fonti dell'elenco: `00_INVENTARIO.md` §3.2, `strumenti/inventario/uscite/s03_matrice_tabelle.tsv` (89 tabelle con almeno una chiamata prod o frontend; escluse sigle dinamiche `<dinamico:*>` e righe senza chiamate: `hazard_atlas`, `omega_minute_*`, `x`) e `s03_matrice_rpc.tsv` (170 RPC; 72 scriventi = tutte tranne `get_*`/`list_*` e 10 di sola lettura/calcolo elencate nello script).
Sezione controllata: §1.3 e §4.3 di G (la sotto-sezione di aggiunte sta in §4.3).

## Prima

| Controllo | Esito |
|---|---|
| Tabelle dell'elenco (prod/FE) | 89, coperte 88, **mancante 1: `tennis_replay_mercati`** (nominata solo nella sigla `tennis_replay_eventi/_mercati/...`, ma lo script la conta mancante perche' il nome pieno non c'e'; in §4.3 non aveva riga propria) |
| RPC scriventi nell'elenco | 72, citate in G 4 (`request_betfair_live_order`, `set_live_kill_switch`, `live_order_mode_avvio`, `get_live_settings`), **mancanti 68** |

Controllo aggiuntivo (letto dalle definizioni SQL delle 68 RPC mancanti, `migrations/*.sql`, DML `insert/update/delete`): **6 tabelle scritte dalle RPC e fuori dalle 89**, non coperte da alcuna riga: `personal_trade_legs`, `personal_cash_movements`, `strategies`, `tennis_refresh_requests`, `omega_requests`, `betfair_live_settings` (quest'ultima nominata in G solo come appendice di T05, senza riga). La matrice `.table()` non le vede (`00 §3.4`, «mondo SQL»). Non sono nelle 89 ma sono scritte oggi dal frontend o da script di import: e' una lacuna reale rispetto a «nessuna tabella persa».

## Aggiunte (G, §4.3, sotto-sezione «Tabelle aggiunte dalla verifica di completezza 08/10», +60 righe, nessuna riga esistente toccata)

- **A (1 tabella dell'elenco)**: `tennis_replay_mercati` (`caricamento.py:79` scrive, `:97` rilegge; BATCH, resta com'e').
- **B (6 tabelle fuori elenco, scritte da RPC)**: `betfair_live_settings`, `personal_trade_legs`, `personal_cash_movements`, `strategies`, `tennis_refresh_requests`, `omega_requests`. Tutte restano cloud; `omega_requests` ha una **domanda aperta** (chi consuma le proposte di uscita; nessun lettore Python di produzione nella matrice) marcata «da chiarire», non decisa.
- **C (68 RPC scriventi mai citate)**: 32 righe per famiglia, ciascuna con chiamante `file:riga`, tabella scritta (con rimando a T01-T17 o a B), natura, proposta di domani, ritardo e verifica. Le RPC dei raccoglitori batch/import (`bulk_update_prediction_results`, `flush_analytics_snap_staging`, `record_fixture_detail_checks`, `refresh_analytics_bets_range`, `upsert_cash_movement`, `upsert_imported_trade`) sono «resta com'e', fuori dal perimetro dell'app».
- Nelle 89 le tabelle scritte SOLO da raccoglitori/workflow (T15-T17: `matches`, `match_*`, `standings`, `injuries`, `top_*`, `api_*`, `analytics_*`, ecc.) erano gia' in §4.3 come CLOUD «invariato»; la sotto-sezione ribadisce il perimetro nella nota finale.

## Dopo

| Controllo | Esito |
|---|---|
| Tabelle dell'elenco (prod/FE) | 89, coperte 89, mancanti 0 |
| Tabelle scritte da RPC fuori elenco | 6, citate 6, mancanti 0 |
| RPC scriventi | 72, citate 72, mancanti 0 |
| Exit code | 0 |

## Falsificazione e verifiche di persona

- Falsificazione: con la sotto-sezione di aggiunte rimossa da una copia di G lo script torna **rosso** (exit 1: `tennis_replay_mercati` + 5 delle 6 tabelle da RPC; la sesta, `betfair_live_settings`, resta citata da T05), poi G ripristinata e script verde. Una prima passata dopo l'inserimento ha dato 3 RPC mancanti (`tennis_bot_service_*`, scritte in forma abbreviata `_stop`): corrette scrivendo i nomi pieni, a conferma che il controllo e' sensibile alle abbreviazioni.
- `file:riga` campionati con `sed -n`: 11 chiamanti (`live.ts:691`, `mike.ts:2228`, `tennis.ts:123`, `scalperControlRoom.ts:166`, `personalReport.ts:325`, `liveOrders.ts:705`, `import_betfair_operations.py:194`, `season_gaps.py:455`, `enrich_analytics_snapshots.py:312`, `predictions_results_backfill.py:671`, `watchlist.ts:110`) e 6 definizioni SQL (`mike_bot.sql:183`, `personal_tracking_rpc.sql:368`, `scalper_bot.sql:69`, `analytics_strategies_store.sql:27`, `tennis_markets.sql:145`, `betfair_live_risk_limits_v4.sql:47`) coincidono con la riga dichiarata. `caricamento.py:75,79,97,108` verificati.

## Limiti (cosa non e' verificato)

- I bersagli DML delle RPC sono letti da regex sull'ultima definizione trovata in `migrations/` (ordine alfabetico dei file); Funzioni che delegano ad altre funzioni (`refresh_analytics_bets_range`, `omega_eventi_chiusi_dall_utente`) non mostrano DML: marcate come tali. Una definizione piu' recente nel DB vivo, non nel repo, non e' controllabile (nessuna SELECT eseguita).
- Le colonne «chi legge» marcate (nv) non sono verificabili dal repo.
- «Ritardo massimo» e «chi scrivera' domani» delle nuove righe ereditano le proposte di T01-T17 (da validare con l'utente); non sono decisioni nuove.
- Lo script controlla che i nomi siano **citati** nella sezione, non che le righe siano giuste: la correttezza del contenuto e' stata campionata a mano come sopra.
