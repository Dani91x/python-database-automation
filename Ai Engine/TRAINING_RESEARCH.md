# Ricerca: addestrare l'ensemble in modo EFFICACE e VELOCE (senza perdere settimane)

> Briefing 2026-06-09. Stack: stacking per-lega RF + LightGBM + XGBoost +
> LogisticRegression (meta LogReg), Optuna, SMOTE, calibrazione temperature/isotonic.
> Hardware: Ryzen 7 3750H (4 core / 8 thread), 16 GB, GTX 1650 4GB, Windows,
> Python 3.13, training CPU-only. Dataset piccoli: 80–1500 partite per lega.
> Operativo: vedi `ML_TRAINING_AND_STACK.md`. Qui il "perché" con fonti.

## Tesi di fondo
Su questi numeri il collo di bottiglia **non è la potenza di calcolo, è
l'overfitting e gli sprechi di tuning**. Ogni modello si addestra in
millisecondi–secondi; il rischio reale è bruciare giorni in trial Optuna inutili e
in modelli troppo complessi che memorizzano rumore.

## 1. Velocità per LightGBM / XGBoost su dati tabellari piccoli
- **Usa sempre `hist`**: XGBoost `tree_method="hist"` è il default moderno (binning, 255 bin); LightGBM è già histogram-based. Per <2000 righe non serve altro.
- **GPU: NON usarla.** Su dataset piccoli/bassa dimensionalità l'overhead GPU supera il guadagno (benchmark: GPU ~uguale o più lenta della CPU). La GTX 1650 4GB non darebbe vantaggi sotto le ~2000 righe; con Python 3.13 e build CPU-only è anche un grattacapo in meno.
- **`n_estimators` alto + early stopping**: tetto `n_estimators=1000–2000`, lascia che `early_stopping_rounds≈30–50` lo tagli. Su 80–350 partite si ferma spesso a 50–150 alberi. (Nel nostro codice: ES su fetta interna del train + refit sul totale col n° alberi ottimale.)
- **Limiti complessità per N piccolo**: `num_leaves=15–31` (NON 127), `max_depth=3–6`, `min_data_in_leaf`/`min_child_samples` 20–50. XGBoost `max_depth=3–4`, `min_child_weight≥5`.
- **Thread = core FISICI (4)**, non 8. Oltre i core fisici (SMT) il guadagno è marginale e i tempi diventano imprevedibili.
- **Tempi realistici per fit singolo**: LightGBM/XGBoost 0.1–2 s; RandomForest 1–3 s; LogReg <0.5 s. Ensemble per lega: pochi secondi.

```python
LGBMClassifier(n_estimators=1500, learning_rate=0.03, num_leaves=20,
               min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
               reg_alpha=0.5, reg_lambda=1.0, n_jobs=4)
XGBClassifier(tree_method="hist", n_estimators=1500, learning_rate=0.03,
              max_depth=4, min_child_weight=5, subsample=0.8,
              colsample_bytree=0.8, reg_alpha=0.5, reg_lambda=1.0, n_jobs=4)
```

## 2. Efficienza Optuna
- **Sampler**: `TPESampler(multivariate=True)` — cattura le dipendenze tra iperparametri, batte il TPE indipendente. (Già applicato nel nostro codice.)
- **Pruning**: `MedianPruner` su dati piccoli; **evita Hyperband** (consuma ~10 trial di warm-up per bracket → spreco con budget basso). NB: il pruning richiede report intermedi nell'objective; il nostro objective ritorna un solo NLL OOF, quindi il pruning non è collegato (scelta accettabile su budget piccolo).
- **Quanti trial valgono**: su 80–350 partite i rendimenti decrescono prestissimo. **15–30 trial** (come configurato per SMALL/MEDIUM) sono adeguati; oltre ~60 si overfitta lo split di validazione. Leghe con 1000+ partite: fino a 50.
- **`n_jobs` trial vs thread modello — la trappola dell'oversubscription**: con `optimize(n_jobs=4)` e modelli a `n_jobs=4` ottieni 16 worker su 8 thread. Regola: **se parallelizzi i trial → modello `n_jobs=1`**; se i modelli usano i thread → trial seriali. (Nel nostro codice i trial sono seriali per study e `n_jobs` dei modelli è il budget per-target.)
- **Persistenza/caching**: il warm-start più potente è **non rieseguire il tuning** se i dati non sono cambiati. Già implementato: cache JSON `optuna_params_{target}.json` per lega+target, re-tune solo se tier cambia o dataset ±20%.

## 3. Evitare overfitting su dataset minuscoli (80–350 partite)
- **Regolarizza forte**: `reg_alpha (lambda_l1)` 0.5–2, `reg_lambda (lambda_l2)` 1–5, `min_child_samples` 20–50, `subsample`/`colsample` 0.7–0.8. Sono esattamente le leve anti-overfitting della doc LightGBM.
- **Modelli più semplici sotto soglia**: il sistema a tier già lo fa (TINY/SMALL → RF+LogReg / +XGB, niente LGB/MLP). Sotto ~150 partite l'ensemble pesante perde contro una LogReg regolarizzata.
- **CV temporale, mai casuale**: usa `TimeSeriesSplit`/walk-forward (già fatto via `walk_forward_splits`) per non avere leakage dal futuro. Lo split singolo su N piccolo ha varianza enorme.
- **Tuning pesante = controproducente**: la generalizzazione viene dalla regolarizzazione, non dalla ricerca esaustiva.

## 4. Parallelismo per saturare 8 thread senza oversubscription
- Due assi paralleli naturali: **leghe** e **target**. Sfruttali invece di parallelizzare dentro il modello.
- **Schema**: `ProcessPoolExecutor`/orchestratore sulle leghe + modelli a `n_jobs` ridotto. La trappola: `threads_modello × leghe_parallele × n_jobs >> core`. Es. rotto: 4 leghe × 4 modelli a `n_jobs=4` = 64 thread su 8 → thrashing.
- **Regola d'oro**: `processi × n_jobs_per_modello ≤ 4` (core fisici). O parallelizzi le leghe (modelli mono/bi-thread) **o** dentro il modello (leghe seriali), mai entrambi al massimo. Nel nostro codice: `RETRAIN_N_WORKERS × RETRAIN_PARALLEL_LEAGUES × n_jobs_per_model ≈ 8`.

## 5. Quando ri-addestrare vs ricalibrare
- **La ricalibrazione costa ~1/5 del retraining**. Prima prova a ricalibrare.
- **Cadenza**: i dataset crescono lentamente (+5–10 partite/settimana per lega). Retrain ~ogni giornata di campionato / a mesi; tra un retrain e l'altro **ricalibra** sulle ultime partite (`compute_ml_post_calibration.py`).
- **Drift** (stagionale: mercato, allenatori): monitora il **Brier rolling** sulle ultime N partite; se peggiora oltre soglia → retrain, altrimenti ricalibra. (Il nostro `bss_monitor` fa già questo tipo di monitoraggio.)
- **Incrementale**: `--skip-existing` → ri-addestra solo le leghe coi dati cambiati.

## 6. Calibrazione delle probabilità per il betting
La calibrazione **conta più dell'accuracy**: EV = `p_calibrata × quota − 1`; probabilità mal calibrate generano scommesse a EV falso-positivo.
- **Metodi**: Platt/sigmoid per pochi dati (<300); **isotonic** solo con 1000+ campioni nel set di calibrazione (overfitta su pochi dati); **temperature scaling** ideale per output multiclasse (1 parametro T) — è ciò che usiamo sul 1x2, con isotonic sui binari.
- **Set di calibrazione held-out**, mai sovrapposto a train/test (nel nostro codice: fit su val, metriche su holdout).
- **Metriche**: **Brier** ed **ECE**, più bassi meglio, su un holdout temporale.

## 7. Playbook "non perdere settimane"
1. **Holdout veloce prima dei run completi**: misura Brier/ECE su una lega rappresentativa con 20 trial prima di lanciare tutto.
2. **Cache param tunati** + re-train solo se l'hash dati cambia.
3. **Allena prima solo i mercati bettable** (1X2, O/U 2.5, BTTS): non tunare ciò che non scommetti (`targets_filter`).
4. **Retrain incrementale** `--skip-existing`.
5. **Loop corto**: 15–30 trial, early stopping aggressivo, parallelismo sulle leghe → giro multi-lega in minuti.
6. **Compressione modelli** (`compress_models.py`).
7. **Degrada per N basso**: il tier system già lo fa.

## Fonti
- LightGBM — Parameters Tuning: https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html
- LightGBM — Parameters: https://lightgbm.readthedocs.io/en/latest/Parameters.html
- scikit-learn — Parallelism / resource management: https://scikit-learn.org/stable/computing/parallelism.html
- scikit-learn — Probability calibration: https://scikit-learn.org/stable/modules/calibration.html
- Optuna — Pruners / TPE: https://optuna.readthedocs.io/en/stable/reference/generated/optuna.pruners.HyperbandPruner.html
- Optuna — Multivariate TPE: https://tech.preferred.jp/en/blog/multivariate-tpe-makes-optuna-even-more-powerful/
- XGBoost GPU vs CPU su dataset piccoli: https://medium.com/hypatai/experiments-on-xgboost-part-1-318e5b4c1858
- Costo retraining vs ricalibrazione: https://arxiv.org/html/2604.02351
- Model monitoring / drift & retraining: https://21devs.com/model-monitoring/
- Hyperparameter Tuning LightGBM con early stopping: https://macalusojeff.github.io/post/HyperparameterTuningLGBM/
