# AI Engine - Documentazione Completa

## Scopo
La cartella `Ai Engine` contiene il motore di analisi e previsione interno basato su dati del database. Il sistema:
- costruisce feature da storico (senza CSV)
- addestra modelli per lega (league_id separato)
- produce predizioni calibrate
- genera report leggibili
- valuta qualit? con audit e holdout

## Flusso generale (end-to-end)
1. **Recupero dati** dal DB (matches, team stats, player stats, standings, raw odds).
2. **Feature engineering** per fixture future (form, stats, odds, window stats).
3. **Training** modelli per lega con leakage eliminato.
4. **Predizione** fixture singolo con calibrazione e reliability.
5. **Report** per utente finale.
6. **Audit/valutazione** qualit? (nulls + holdout).

## Componenti principali

### 1) `ai_engine/db_adapter.py`
Gestisce il fetch dal DB (Supabase). Funzioni principali:
- `fetch_fixtures_for_date(date)` ? fixtures del giorno da `fixture_predictions`.
- `fetch_matches_for_league_seasons([(league_id, season)])` ? storico partite da `matches`.
- `fetch_matches_full_for_league_seasons` ? storico completo con score HT/FT.
- `fetch_related_by_fixture_ids(table, fixture_ids, columns, ...)` ? eventi/stats per fixtures.
- `fetch_standings_by_league_seasons` ? standings per lega/stagione.
- `fetch_seasons_for_league(league_id)` ? lista stagioni disponibili.
- `fetch_fixture_prediction_by_id(fixture_id)` ? riga singola da `fixture_predictions` (incluso `raw_json_odds`).

Note:
- `fetch_related_by_fixture_ids` ottimizza `match_odds` con chunk/page size ridotti per evitare timeout.

### 2) `ai_engine/feature_pipeline.py`
Costruisce il dataset di feature.

**Feature incluse (pre-match)**
- **Form**: medie GF/GA/GD per team su finestre 5/10/15.
  - calcolate su storico, unite per `team_id` + `fixture_date` (merge_asof)
- **Team window stats**: statistiche aggregate per team su finestre 5/10/15.
- **Eventi**: goal, cartellini, minuto medio goal.
- **Team stats**: per stat_type (es. tiri, possesso...).
- **Player stats**: minuti, tiri, assist, passaggi, falli, ecc.
- **Standings**: rank, punti, form, ecc.
- **Odds pre-match**:
  - da `match_odds` quando presente
  - fallback su `fixture_predictions.raw_json_odds`

**Feature escluse**
- Injuries rimosse completamente.

**Funzioni chiave**
- `build_feature_dataframe_for_fixtures(fixtures_df, history_df, league_seasons, ...)`
- `_compute_form_features(history_df)`
- `_odds_features_from_raw_json(fixtures_df)`

### 3) `ai_engine/training_dataset.py`
Costruisce il dataset storico per training.
- Input: `matches` + feature engineering.
- Output: feature + target.
- `include_odds=True` per usare odds come feature.

### 4) `ai_engine/targets.py` (gi? esistente)
Crea target supervisionati a partire da:
- risultati match
- team stats
- events

### 5) `ai_engine/seriea_model_export.py`
Train & upload modelli per lega.

**Caratteristiche:**
- Modelli separati per `league_id`.
- Leakage rimosso:
  - drop di tutti `target_*`
  - drop `*_fixture_id`, `*_team_id`
  - drop colonne non predittive (score finali, ecc.)
- **Pesi temporali** (partite recenti contano di più).
- Calibrazione (`CalibratedClassifierCV`) quando possibile.
- Metriche salvate: accuracy, logloss, **brier**, **ece**, feature_count.
- Salvataggio su bucket `ai-models` e registry `ai_model_registry`.

### 6) `ai_engine/predict_fixture.py`
Predizione singolo fixture_id.

**Passaggi:**
1. Recupera fixture da `fixture_predictions`.
2. Recupera storico 3 anni per la lega.
3. Costruisce feature.
4. Carica modelli dal bucket per quella lega.
5. Predice probabilità (`targets_raw`).
6. Calibra output con shrink basato su reliability (`targets`).
7. **Applica Confidence Gates (4 livelli)** incluso quality check (Brier/ECE).
8. Calcola `profit_balance` se odds disponibili.
9. Scrive `model_predictions_json` in DB (se `--store`).

**Output JSON**:
- `schema_version`: "2.0"
- `run_id`: UUID univoco
- `targets` (calibrati)
- `targets_raw` (grezzi)
- `targets_skipped`: target senza modello
- `targets_not_reliable`: target falliti al Gate 4
- `coverage` (features_pct, matches_home/away, detail)
- `profit_balance`
- `reliability` (score/grade/alpha)
- `calibration_metrics` (Brier/ECE)
- `confidence_gates`: risultato dei 4 gate
- `bet_signals`: value bets filtrate

### 7) `ai_engine/generate_fixture_report.py`
Genera report leggibile in `Ai Engine/reports/`.
- linguaggio semplificato
- top mercati ordinati per affidabilità
- include coverage, feature breakdown, profit balance

### 8) `ai_engine/metrics/balance.py`
Calcolo Profit Balance:
- metrica economica basata su odds
- utile per confrontare mercati

### 9) `ai_engine/coverage.py`
Calcolo coverage per gruppi feature:
- odds (1x2, ou, btts)
- form
- team stats, player stats, events
- team_window_stats
- standings
- **historical**: storico partite

### 10) `ai_engine/audit_nulls.py`
Audit dati mancanti per lega:
- report su nulls per feature
- coverage gruppi
- top colonne con più null

Output:
- `Ai Engine/reports/audit_nulls_league_<id>.md`

### 11) `ai_engine/backtest.py`
Backtest walk-forward realistico:
- Uso di **quote reali** da `match_odds`
- Metriche: ROI, Yield, Drawdown, Sharpe, **Brier**, **Baseline Accuracy**, **Lift**
- Report per target e globale

Output:
- `Ai Engine/reports/backtest_league_<id>.md`

---

## Campi DB usati

### Tabella `fixture_predictions`
- fixture_id, league_id, season_year, fixture_date
- home_team_id, away_team_id
- percent_home/draw/away (API)
- raw_json (API response)
- raw_json_odds (odds pre-match)
- model_predictions_json (output ML v2.0)
- db_json_analisi (terza analisi Poisson/xG - via Prediction)

### Tabella `matches`
- fixture_id, league_id, season_year, fixture_date
- goals_home, goals_away
- halftime_home, halftime_away
- status_short

### Tabella `match_team_stats`
- fixture_id, team_id, stat_type, value_numeric
- usata per xG reali quando disponibili

### Tabella `match_events`
- fixture_id, team_id, event_type, detail, minute

### Tabella `match_player_stats`
- fixture_id, team_id, minutes, shots, passes, etc.

### Tabella `match_odds`
- fixture_id, bookmaker_name, bet_name, bet_value, odd
- Usata per backtest realistico e value betting

### Tabella `standings`
- league_id, season_year, team_id
- rank, points, goals_for, goals_against, form

### Tabella `ai_model_registry`
- modelli per lega, path, metriche e versione

---

## Output principali

### `model_predictions_json` (v2.0)
Contiene:
- `run_id`: tracciabilità
- `targets`: output calibrato
- `targets_raw`: output grezzo
- `targets_skipped`: lista target ignorati
- `targets_not_reliable`: lista target scartati per calibrazione
- `coverage`: percentuale feature + dettagli
- `profit_balance`: 1x2/OU/BTTS
- `reliability`: score e grade
- `calibration_metrics`: Brier/ECE
- `confidence_gates`: 4 livelli (Dati, Modelli, Valore, Calibrazione)

### `db_json_analisi`
Terza analisi Poisson/xG:
- lambda home/away
- mercati (1x2, over2.5, btts, 1H goal)
- copertura xG e finestre

---

## Differenze chiave rispetto all’originale
- Nessun CSV
- Feature basate esclusivamente sul DB
- Modelli separati per lega
- Leakage rimosso (`train_df` scope fix)
- Calibrazione (`_ece_score`, `_brier_score`) + Gate 4
- Odds reali nel backtest
- Versionamento JSON output (v2.0)

---

## Note operative
- Ogni modifica in `Ai Engine` deve preservare: separazione per lega, no leakage, no CSV.
- `Predict_fixture.py` va rilanciato dopo ogni retrain per aggiornare `model_predictions_json`.
