# ML ENGINE — Training per-lega, Stack tecnologico, Validazione matematica

> Ultimo aggiornamento: 2026-06-09 (audit forense + fix "blindatura matematica")
> Riguarda SOLO il motore ML (ensemble in `Ai Engine/ai_engine/`). Il modello
> Poisson/Dixon-Coles (`Prediction/`) è un sistema separato, non trattato qui.

---

## 0. TL;DR operativo

1. **Stack core installato il 2026-06-09** (lightgbm 4.6, xgboost 3.2, optuna 4.9,
   imbalanced-learn 0.14): l'ensemble ora gira a piena potenza (RF+LGB+XGB+LogReg).
   Su una macchina nuova, ripristina con `pip install -r requirements.txt`.
   TensorFlow/Keras NON sono installabili su Python 3.13 → meta-learner MLP non
   disponibile, fallback LogisticRegression (ottimo, nessun problema — vedi §2).
2. **DEVI ri-addestrare tutte le leghe**: i modelli attuali sono stati addestrati
   con un leakage critico (classifica di fine stagione, vedi §1) E senza i modelli
   boosting (stack incompleto). Finché non ri-addestri, le probabilità sul foglio
   restano gonfiate/non affidabili.
3. **Training veloce di tutte le leghe** (vedi §3 per i dettagli):
   ```bash
   set RETRAIN_N_WORKERS=8
   set RETRAIN_PARALLEL_LEAGUES=1
   .venv/Scripts/python.exe retrain_all_leagues.py --source both --last-n-seasons 3
   ```
4. Dopo il training: `compute_ml_post_calibration.py` e (opzionale) `compress_models.py`.

---

## 1. Cosa è stato corretto (audit 2026-06-09) — "blindatura matematica"

Un audit forense multi-agente ha trovato 13 problemi confermati; tutti corretti.
Ogni numero che finisce sul Google Sheet ora poggia su matematica validata.

| # | Gravità | Problema | Fix | File |
|---|---------|----------|-----|------|
| C1 | CRITICO | **Leakage classifica**: `standings` è uno snapshot di fine stagione mergiato senza filtro data → ogni partita riceveva rank/punti/GD che già includono il risultato da predire. | Escluse `home_standings_*`/`away_standings_*` dalle feature. Il segnale di forza recente resta coperto leakage-free dalle window stats `stat_w*`. | `seriea_model_export.py` (drop_cols) |
| C2 | CRITICO | **Partite non giocate**: fixture future con gol NULL entravano con label `False` fittizie (pandas: `NaN>line → False`), gonfiando la classe negativa e abbassando P(True) di Over/BTTS. | Filtro: solo partite con risultato finale entrano nel training set. | `seriea_model_export.py` (`train_and_save_all`) |
| H1 | ALTO | `target_ht_ft` creava la pseudo-classe `"_"`/`"H_"` quando mancava HT o FT. | Emette `None` se manca una metà → rimosso da `dropna`. | `targets.py` |
| M1 | MEDIO | **Brier/ECE misuravano le probabilità PRE-calibrazione**, non quelle servite. | Le metriche ora instradano l'holdout attraverso `predict_ensemble` (stesso path di serving: meta + temperature scaling/isotonic). Rimossa la logica di stacking duplicata. | `seriea_model_export.py` |
| M2 | MEDIO | **Doppia calibrazione + feedback loop**: `compute_ml_post_calibration` imparava le correzioni da probabilità già corrette → stacking ad ogni rigenerazione. | `predict_fixture` salva `targets_model_calibrated` (pre-posthoc); `compute_ml_post_calibration` impara da quel campo. | `predict_fixture.py`, `compute_ml_post_calibration.py` |
| M3 | MEDIO | **Foglio MM senza commissione**: la formula P&L live mostrava la vincita lorda, gonfiando P&L/Cassa/Yield del 5% del profitto netto per ogni bet vinta. | Formula corretta: `stake*(quota-1)*(1-0.05)`. | `aggiorna_mm_sheets.py` |
| M4 | MEDIO | Metriche calcolate su `val` quando holdout<15 → ottimistiche (val usato per base_weights/early-stopping). | Metriche **sempre** su holdout; se troppo piccolo → `None`, mai val. | `seriea_model_export.py` |
| LOW | basso | Mediane di imputazione e drop colonne >50% NaN calcolati sull'intero dataset (leakage val/holdout→train). | Calcolati **solo sul train** dopo lo split, applicati a val/holdout/live. | `seriea_model_export.py` |
| LOW | basso | Target di conteggio (total_goals, corners, sot, cards, exact_score) addestrati come classificazione multiclasse ad alta cardinalità. | Esclusi dal training (i mercati gol bettabili restano coperti dai target binari over/under). | `seriea_model_export.py` |

### 1.b Fix dei percorsi attivati con lo stack (mai eseguiti prima dell'install)

Installati lightgbm/xgboost/optuna/imbalanced-learn, un secondo audit ha trovato e
corretto 4 bug nei percorsi finora dormienti (tutti code-review APPROVE):

| Gravità | Problema | Fix | File |
|---------|----------|-----|------|
| ALTO | I campioni sintetici **SMOTE** ricevevano peso `1.0` (massimo), sovrappesandoli rispetto ai campioni reali time-discounted. | Peso = media dei pesi reali del fold. | `ensemble_trainer.py` |
| ALTO | L'**early-stopping LightGBM** usava il val set poi usato per fittare calibratori e base_weights → calibrazione ottimistica. | ES su una fetta interna della coda del train; poi **refit su tutto il train** con il n° alberi ottimale. Val/holdout restano puliti. | `ensemble_trainer.py` |
| ALTO | `_train_calibrators` non gestiva `_KerasMetaWrapper._model=None` (payload TF deserializzato senza TF) → calibratori su distribuzione uniforme. | Aggiunta la stessa guardia già presente in predict/evaluate. | `ensemble_trainer.py` |
| MEDIO | **Optuna** usava `n_jobs=-1` nei trial RF/LGB → oversubscription CPU con target paralleli. | `n_jobs` passato dal budget per-target (`n_jobs_per_model`). | `ensemble_trainer.py`, `seriea_model_export.py` |

Migliorie (anti-overfit / efficienza, da ricerca — vedi §7):
- **TPE multivariato** (`TPESampler(multivariate=True)`): cattura le dipendenze tra iperparametri → tuning migliore.
- **`num_leaves` cap 63** (era 127): su dataset piccoli per-lega riduce l'overfitting.

Verifica stack: `.venv/Scripts/python.exe tmp_smoke_stack.py` → `STACK SMOKE PASSED`
(esercita SMOTE, Optuna rf/lgb/xgb, LGB early-stopping, round-trip pickle→serving).

**Verifica**: `tmp_smoke_ml_fixes.py` (smoke test standalone senza DB) valida targets,
calibrazione (temperature scaling, somma=1) e l'intero flusso `_train_one_target`.
Esegui: `.venv/Scripts/python.exe tmp_smoke_ml_fixes.py` → deve stampare
`SMOKE TEST PASSED`.

> **Conseguenza pratica**: i fix C1/C2 cambiano la distribuzione delle label e
> delle feature. Le metriche oneste post-fix saranno **più basse** di prima
> (prima erano gonfiate dal leakage). È corretto: ora sono reali. Serve un
> **retrain completo** per rendere i modelli e il foglio affidabili.

---

## 2. Audit dello STACK — stiamo usando tutta la tecnologia?

**Ora sì (aggiornato 2026-06-09).** Lo stack core è stato installato e l'ensemble
gira a piena potenza. Prima girava in modalità ridotta perché il codice degrada in
silenzio (import sotto `try/except`): se una libreria manca, il modello non viene
costruito — nessun crash, ma motore più debole.

| Libreria | Stato | A cosa serve |
|----------|-------|--------------|
| scikit-learn / scipy / pandas / numpy | ✅ | RF, LogReg, GradientBoosting, isotonic, temperature scaling |
| **lightgbm** 4.6 | ✅ installato 06-09 | Gradient boosting veloce (base model MEDIUM/LARGE) |
| **xgboost** 3.2 | ✅ installato 06-09 | 4° base model (boosting reg. L1/L2, NaN nativi) |
| **imbalanced-learn** 0.14 | ✅ installato 06-09 | SMOTE/SVMSMOTE (riequilibrio classe Pareggio) |
| **optuna** 4.9 | ✅ installato 06-09 | Tuning bayesiano iperparametri per-lega (cached) |
| tensorflow / keras | ❌ non installabili | Meta-learner MLP (LARGE). **Python 3.13 non supportato da TF** → fallback LogisticRegression (ottimo) |
| boruta | ❌ non usato | la selezione usa variance+correlazione+mutual-info |

**Prova diretta**: nello smoke test a tier MEDIUM i base model sono ora
`['rf','lgb','xgb','logreg']` (prima `['rf','logreg']`). SMOTE, Optuna (rf/lgb/xgb)
e l'early-stopping LightGBM sono stati verificati end-to-end (`tmp_smoke_stack.py`).

### Nota su TensorFlow / meta-learner MLP
TensorFlow non ha wheel per Python 3.13 (supporta fino a 3.12). Il meta-learner MLP
per le leghe LARGE resta quindi **non disponibile**, e il sistema usa il
meta-learner **LogisticRegression** — che su dataset piccoli/medi (la norma qui) è
spesso preferibile all'MLP (meno overfitting, calibrazione più stabile). **Non è una
perdita pratica.** Se in futuro volessi l'MLP: crea un secondo venv con Python 3.12
e `pip install tensorflow keras`. Sconsigliato salvo necessità specifica.

### Ripristino su una macchina nuova
```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
# verifica:
.venv/Scripts/python.exe tmp_smoke_stack.py   # deve stampare STACK SMOKE PASSED
```

---

## 3. Training per-lega — come funziona e come renderlo VELOCE

### 3.1 Architettura del training (per `league_id`)
`train_and_save_all(league_id, last_n_seasons=3)` per ogni target:
1. `build_training_dataset` → feature pre-match leakage-free (form/ELO/H2H/odds/window-stats).
2. **Filtro partite giocate** (fix C2).
3. Split temporale **75/15/10** (train/val/holdout) + purge 30 giorni.
4. Imputazione mediane + drop colonne NaN **train-only** (fix LOW).
5. Feature selection: variance → correlazione (0.95) → mutual-info top-60.
6. **Optuna** (se installato): tuning iperparametri, **cache** in
   `models_cache/league_{id}/optuna_params_{target}.json`.
7. `build_ensemble`: base model per tier + OOF + SMOTE + meta-learner + calibrazione.
8. Metriche Brier/ECE su holdout (fix M1/M4).
9. Salvataggio `models_cache/league_{id}/ensemble_v2_{target}.pkl.gz` + upload Supabase.

### 3.2 Sistema a TIER (la complessità si adatta ai dati — già ottimizzato)
Calcolato su `n_train` (dopo lo split):

| Tier | n_train | Base models | Optuna trial | SMOTE | Meta-learner |
|------|---------|-------------|--------------|-------|--------------|
| TINY | <150 | RF + LogReg | 0 | no | weighted/LogReg |
| SMALL | 150–350 | RF + XGB + sklearn-GB + LogReg | 15 | no | LogReg |
| MEDIUM | 350–700 | RF + LGB + XGB + LogReg | 20 | sì (se sbil.) | LogReg |
| LARGE | ≥700 | RF + LGB + XGB + LogReg | 30 | sì (se sbil.) | MLP (se TF) o LogReg |

### 3.3 Comandi

**Una sola lega:**
```bash
.venv/Scripts/python.exe "Ai Engine/ai_engine/seriea_model_export.py" <league_id> 3
```

**Tutte le leghe (orchestratore con parallelismo + gate BSS):**
```bash
.venv/Scripts/python.exe retrain_all_leagues.py --source both --last-n-seasons 3
```
Flag utili:
- `--leagues 39,135,2` — solo queste leghe.
- `--skip-existing` — salta le leghe ri-addestrate di recente (retrain incrementale).
- `--parallel-leagues N` — N leghe in parallelo.
- `--source cache|db|both` — da dove prende l'elenco leghe (`cache` = cartelle
  già esistenti in `models_cache/`, `db` = `season_backfill_state`).
- `--dry-run` — simulazione.

### 3.4 Parallelismo (hardware: 8 thread)
Due variabili d'ambiente controllano la CPU:
- `RETRAIN_N_WORKERS` (default 4): target addestrati in parallelo per lega.
- `RETRAIN_PARALLEL_LEAGUES` (default 1): leghe in parallelo.
- `n_jobs_per_model = cpu_count // (RETRAIN_N_WORKERS × RETRAIN_PARALLEL_LEAGUES)`.

Regola d'oro: il prodotto `N_WORKERS × PARALLEL_LEAGUES × n_jobs_per_model` deve
≈ numero di thread (8), per saturare la CPU **senza** over-subscription.

| Scenario | Config consigliata |
|----------|--------------------|
| **Tante leghe da rifare** (throughput) | `PARALLEL_LEAGUES=2`, `N_WORKERS=4` → n_jobs=1 |
| **Poche leghe / latenza minima per lega** | `PARALLEL_LEAGUES=1`, `N_WORKERS=8` → n_jobs=1 |
| **Una lega grande, pochi target** | `N_WORKERS=2`, `n_jobs` auto=4 (boosting multi-thread) |

---

## 4. Ricetta "TEMPO MINIMO" (punto 7 — istruzioni, NON eseguito)

Obiettivo: ri-addestrare tutte le leghe nel minor tempo possibile, senza perdere
giorni. I leveraggi, in ordine d'impatto:

1. **Installa `lightgbm`** (oltre a velocizzare, è il boosting che oggi manca).
   sklearn GradientBoosting è lento; LightGBM è 5–10× più rapido.
2. **Sfrutta la cache Optuna**: il tuning si paga **una volta** per lega/target.
   Il primo full-train è il più lento; i retrain successivi sono cache-hit
   (istantanei sul tuning). → Non rifare il tuning se i dati non sono cambiati
   >20% (già automatico).
3. **Prima passata solo sui mercati che scommetti** (dimezza i target):
   ```bash
   # training mirato ai mercati Betfair principali
   .venv/Scripts/python.exe -c "from ai_engine.seriea_model_export import train_and_save_all; \
   train_and_save_all(<league_id>, 3, targets_filter=['target_1x2','target_btts','target_over_2_5','target_over_1_5','target_over_3_5'])"
   ```
   Poi, con calma, una seconda passata per il resto.
4. **Parallelismo pieno**: satura gli 8 thread (vedi §3.4). Per molte leghe usa
   `PARALLEL_LEAGUES=2 N_WORKERS=4`.
5. **`--skip-existing`** per i retrain incrementali: ri-addestra solo ciò che è
   invecchiato, non tutto da capo ogni volta.
6. **`last_n_seasons=3`** è il giusto compromesso. Scendere a 2 velocizza ma
   riduce il segnale: non consigliato salvo emergenza.
7. **`compress_models.py`** dopo il training (dimezza lo storage, perdita ~1–2%).

**Stima realistica** (8 thread, lightgbm installato, cache Optuna calda):
- per-lega: ~1–4 min (dipende da tier e #target).
- full fleet con `PARALLEL_LEAGUES=2`: ~ (numero_leghe / 2) × per-lega.
- Il **primo** full-train (tuning Optuna a freddo) è più lento: metti in conto
  +50–100% sul primo giro, poi i retrain sono rapidi grazie alla cache.

> Non serve "perdere giorni": il costo vero è il primo tuning. Una volta in
> cache, i retrain sono veloci. Il collo di bottiglia diventa il numero di leghe
> × target, mitigato dal parallelismo e dal `targets_filter`.

---

## 5. Affidabilità — gate e validazione
- **Gate BSS ≥ 0.12** in `retrain_all_leagues`: un modello che non batte il caso
  casuale del 12% viene marcato FAIL (non bloccante, ma segnalato nella dashboard).
- **Metriche oneste** (post-fix M1/M4): Brier/ECE su holdout, sulle probabilità
  realmente servite. Se un target ha holdout <10 righe → metrica `None`
  (onesto: meglio nessun numero che uno gonfiato).
- **4 confidence gate** a prediction-time (coverage, agreement, EV>0, BSS/ECE):
  solo i segnali che passano tutti finiscono sul foglio come scommesse.

---

## 6. Checklist post-modifiche (da fare quando vuoi)
```
[ ] pip install -r requirements.txt        # stack completo (almeno lightgbm/xgboost/optuna/imbalanced-learn)
[ ] python tmp_smoke_ml_fixes.py           # deve stampare SMOKE TEST PASSED; a MEDIUM ora vedi lgb/xgb
[ ] python retrain_all_leagues.py --source both   # retrain OBBLIGATORIO (i vecchi modelli erano leaked)
[ ] python compute_ml_post_calibration.py  # ricalibrazione post-hoc (ora senza feedback loop)
[ ] python compress_models.py              # opzionale, storage
```
```
> Nota: la rimozione del leakage (C1/C2) farà scendere le metriche rispetto a
> prima. È il prezzo dell'onestà: i numeri ora sono reali e scommettibili.
```

---

## 7. Ricerca: best practice per un training efficace
Documento dedicato con il "perché" e le fonti: **[`Ai Engine/TRAINING_RESEARCH.md`](./TRAINING_RESEARCH.md)**.
Sintesi: su dataset piccoli per-lega il collo di bottiglia è l'overfitting e gli
sprechi di tuning, non la CPU. Punti chiave: `hist` (no GPU sotto ~2000 righe),
early stopping + n_estimators alto, `num_leaves`/`min_child_samples` per limitare
la complessità, thread = core fisici (4), TPE multivariato, 15–30 trial Optuna
(rendimenti decrescenti oltre), cache dei param, parallelizza leghe NON modelli,
ricalibra (1/5 del costo) tra un retrain e l'altro, calibrazione su holdout.
