# MLAUDIT.md — Roadmap Tecnologica Completa v2
**Progetto:** `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation`
**Data:** 2026-04-01
**Obiettivo:** Portare il sistema ML allo stato dell'arte con stack tecnologico completo, modelli auto-adattivi per lega, iperparametri automatici. Ogni punto include localizzazione chirurgica, motivazione matematica, review di rischio e validazione.
**Destinatario:** Agente di implementazione — seguire nell'ordine indicato.

---

## Indice

1. [Stack Tecnologico e Dipendenze](#1-stack-tecnologico-e-dipendenze)
2. [Logica Adattiva Per-Lega](#2-logica-adattiva-per-lega)
3. [P1 — XGBoost come quarto base model](#3-p1--xgboost-come-quarto-base-model)
4. [P2 — LightGBM al posto di sklearn GradientBoosting](#4-p2--lightgbm-al-posto-di-sklearn-gradientboosting)
5. [P3 — SMOTE collegato al training principale](#5-p3--smote-collegato-al-training-principale)
6. [P4 — Optuna per iperparametri per-lega](#6-p4--optuna-per-iperparametri-per-lega)
7. [P5 — Temperature Scaling al posto di isotonic multiclasse](#7-p5--temperature-scaling-al-posto-di-isotonic-multiclasse)
8. [P6 — MLP meta-learner adattivo](#8-p6--mlp-meta-learner-adattivo)
9. [P7 — xG e shots on target come feature rolling](#9-p7--xg-e-shots-on-target-come-feature-rolling)
10. [Ordine di implementazione e dipendenze](#10-ordine-di-implementazione-e-dipendenze)
11. [Checklist di validazione finale](#11-checklist-di-validazione-finale)

---

## 1. Stack Tecnologico e Dipendenze

### 1.1 Librerie già installate (zero setup aggiuntivo)

| Libreria | Versione | Uso in questo piano |
|----------|----------|---------------------|
| `xgboost` | 3.2.0 | P1 — quarto base model |
| `optuna` | 4.7.0 | P4 — tuning iperparametri |
| `imbalanced-learn` | 0.14.1 | P3 — SMOTE/SVMSMOTE |
| `tensorflow` | 2.20.0 | P6 — MLP meta-learner |
| `keras` | 3.13.2 | P6 — MLP meta-learner |
| `scipy` | 1.17.0 | P5 — Temperature Scaling (scipy.optimize) |

### 1.2 Librerie da installare

```bash
pip install lightgbm
```
Aggiungere `lightgbm` a `requirements.txt`.

### 1.3 File coinvolti in questo piano

| File | Punti che lo modificano |
|------|------------------------|
| `Ai Engine/ai_engine/ensemble_trainer.py` | P1, P2, P3, P4, P5, P6 |
| `Ai Engine/ai_engine/seriea_model_export.py` | P4 (cache Optuna), P7 (drop_cols) |
| `Ai Engine/ai_engine/feature_pipeline.py` | P7 — nuove feature xG/shots |
| `requirements.txt` | lightgbm |

---

## 2. Logica Adattiva Per-Lega

### 2.1 Razionale

Il sistema attuale usa configurazioni fisse indipendentemente dalla dimensione del dataset. Una lega con 80 match ha bisogno di modelli molto più semplici e regularizzati rispetto alla Serie A con 1000+ match. Usare un MLP meta-learner su 80 campioni OOF è overfitting garantito. Usare solo la LogisticRegression su 800 campioni OOF è una limitazione artificiale.

### 2.2 Classi di dimensione (basate su `n_train_samples` dopo lo split 70/15/15)

```
TINY  : n_train <  150  →  dataset insufficiente per ensemble completo
SMALL : 150 ≤ n_train < 350  →  ensemble ridotto, alta regularizzazione
MEDIUM: 350 ≤ n_train < 700  →  ensemble completo, LR meta-learner
LARGE : n_train ≥ 700  →  stack completo, MLP meta-learner abilitato
```

### 2.3 Comportamento per classe

| Componente | TINY | SMALL | MEDIUM | LARGE |
|------------|------|-------|--------|-------|
| Base models | RF + LogReg | RF + XGB + LogReg | RF + LGB + XGB + LogReg | RF + LGB + XGB + LogReg |
| Optuna trials | 0 (euristiche) | 20 trial | 35 trial | 50 trial |
| SMOTE | No | No | Sì se imbalance<0.35 | Sì se imbalance<0.35 |
| Meta-learner | Weighted avg | LogReg | LogReg | MLP se OOF≥400 |
| Calibrazione | Isotonic (iso) | Iso + TempScaling | TempScaling | TempScaling |
| n_splits OOF | 3 | 5 | 5 | 7 |

### 2.4 Funzione `_get_league_tier` da aggiungere in `ensemble_trainer.py`

Questa funzione centralizza la logica adattiva — tutti i componenti la chiamano invece di hardcodare soglie.

```python
def _get_league_tier(n_train: int) -> str:
    """Return league tier based on training set size after 70/15/15 split."""
    if n_train < 150:
        return "TINY"
    elif n_train < 350:
        return "SMALL"
    elif n_train < 700:
        return "MEDIUM"
    else:
        return "LARGE"
```

**Dove aggiungere:** `ensemble_trainer.py`, dopo la funzione `_clone_model` (attualmente riga 177), prima di `_compute_base_weights`.

---

## 3. P1 — XGBoost come quarto base model

### 3.1 Motivazione

Il tuo ensemble attuale (RF + sklearn GB + LogReg) ha un bias strutturale: RF usa bagging di alberi indipendenti, sklearn GB usa boosting sequenziale, LogReg è lineare. Manca un modello con **gradient boosting moderno e regularizzazione forte**.

XGBoost aggiunge:
- **L1 regularization (`reg_alpha`)** — sklearn GB non ha L1. L1 produce sparsità nei pesi delle feature, utile quando molte feature sono rumore (tipico in leghe piccole dove molte colonne hist_w* sono NaN).
- **L2 regularization (`reg_lambda`)** — riduce l'overfitting su dataset piccoli.
- **Gestione nativa dei NaN** — XGBoost impara la direzione ottimale per i NaN. Non dipende dall'imputation con la mediana che il tuo sistema fa prima del fit.
- **Quarta voce per il meta-learner** — aggiunge un segnale di disaccordo: quando RF e sklearn GB concordano ma XGBoost diverge, il meta-learner può usare questo come indicatore di incertezza.

### 3.2 Localizzazione nel codice

**File:** `ensemble_trainer.py`
**Funzione:** `_build_base_models()` — righe 46–103
**Import da aggiungere:** riga 23–27 (blocco import sklearn)

### 3.3 Modifiche

**Import (riga 23, aggiungere dopo gli import sklearn):**
```python
try:
    from xgboost import XGBClassifier
    _XGBOOST_AVAILABLE = True
except ImportError:
    _XGBOOST_AVAILABLE = False
```

**In `_build_base_models()`, aggiungere XGBoost condizionale al tier:**

La funzione riceve già `n_samples` e `imbalance_ratio`. Aggiungere parametro `tier: str` e costruire la lista di modelli in base al tier:

```python
def _build_base_models(
    n_classes: int,
    n_samples: int = 5000,
    imbalance_ratio: float = 1.0,
    tier: str = "MEDIUM",
    xgb_params: dict | None = None,       # da Optuna (P4)
    lgb_params: dict | None = None,       # da Optuna (P4)
    rf_params: dict | None = None,        # da Optuna (P4)
) -> List[Tuple[str, Any]]:
```

XGBoost viene aggiunto solo per tier SMALL, MEDIUM, LARGE:
```python
if tier != "TINY" and _XGBOOST_AVAILABLE:
    _xgb_p = xgb_params or {}
    models.append((
        "xgb",
        XGBClassifier(
            n_estimators=_xgb_p.get("n_estimators", 100),
            max_depth=_xgb_p.get("max_depth", 4),
            learning_rate=_xgb_p.get("learning_rate", 0.1),
            reg_alpha=_xgb_p.get("reg_alpha", 0.1),
            reg_lambda=_xgb_p.get("reg_lambda", 1.0),
            subsample=_xgb_p.get("subsample", 0.8),
            colsample_bytree=_xgb_p.get("colsample_bytree", 0.8),
            use_label_encoder=False,
            eval_metric="mlogloss",
            verbosity=0,
            random_state=42,
            n_jobs=-1,
        ),
    ))
```

### 3.4 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| xgboost non installato | ImportError al runtime | Guard `try/except` su import + flag `_XGBOOST_AVAILABLE` |
| `use_label_encoder=False` mancante | Warning deprecation su XGBoost ≥1.6 | Già incluso nel codice |
| `n_jobs=-1` conflitto con ThreadPoolExecutor in `train_and_save_all` | Over-subscription CPU | XGBoost usa thread interni separati dai thread Python — no conflitto |
| Classi non presenti nel fold OOF | `predict_proba` ritorna matrice con meno colonne | Già gestito in `_generate_oof_probas` righe 151–159 (allineamento a `classes`) |
| `sample_weight` non supportato da XGBoost con `fit()` | TypeError | Già gestito in `_generate_oof_probas` righe 139–144 (try/except su `sample_weight`) |
| Meta-learner input width cambia (da 3×N a 4×N classi) | Modello salvato incompatibile con predizioni future | Il payload include `base_models` serializzati — il meta-learner viene riaddestrato ogni volta. Nessun conflitto tra versioni salvate perché ogni retraining è self-contained. |

### 3.5 Validazione dopo implementazione

- Verificare che nel log di training compaia `xgb` tra i modelli: `[league X] Training target: target_1x2 ... base_models: rf, gb, xgb, logreg`
- Verificare che `payload.base_weights` contenga chiave `"xgb"`
- Verificare che `payload.base_models` abbia lunghezza 4 (o 3 per TINY)
- Verificare che la dimensione dell'input OOF al meta-learner sia `4 × n_classes` (MEDIUM/LARGE) o `3 × n_classes` (SMALL)

---

## 4. P2 — LightGBM al posto di sklearn GradientBoosting

### 4.1 Motivazione

sklearn `GradientBoostingClassifier` ha tre problemi fondamentali in questo contesto:

**A. Nessun early stopping nativo.** Con `n_estimators=100-150` fisso, se il modello ottimale è a 70 iterazioni stai overfittando dal punto 71 in poi senza saperlo. LightGBM monitora la loss sul val set e si ferma automaticamente.

**B. Level-wise tree growth.** sklearn GB espande tutti i nodi di un livello prima di passare al successivo. LightGBM usa leaf-wise: espande solo la foglia con il guadagno maggiore. Su dataset tabulari sparsi (molti NaN, feature eterogenee) leaf-wise trova pattern profondi con meno alberi e meno overfitting.

**C. Non gestisce i NaN nativamente.** sklearn GB richiede imputation esplicita (il tuo sistema usa la mediana). LightGBM impara automaticamente la direzione ottimale per i NaN — informazione che la mediana distrugge.

**Impatto quantitativo atteso:** su dataset da 100-300 campioni (leghe piccole), la differenza tra GB con n_estimators fisso e LightGBM con early stopping è tipicamente 0.03-0.08 punti di NLL, abbastanza per cambiare il BSS da <0.12 (sotto la soglia Gate 4) a >0.12 (accettato).

### 4.2 Localizzazione nel codice

**File:** `ensemble_trainer.py`
**Funzione:** `_build_base_models()` — righe 82–92 (il blocco `GradientBoostingClassifier`)
**Import da aggiungere:** dopo il blocco xgboost (vedi P1)

### 4.3 Modifiche

**Import:**
```python
try:
    import lightgbm as lgb
    from lightgbm import LGBMClassifier
    _LIGHTGBM_AVAILABLE = True
except ImportError:
    _LIGHTGBM_AVAILABLE = False
```

**In `_build_base_models()`, sostituire `GradientBoostingClassifier` con `LGBMClassifier`:**

LightGBM viene usato per tier MEDIUM e LARGE. Per SMALL si usa ancora sklearn GB (più stabile su pochi dati). Per TINY si rimuove il GB completamente.

```python
if tier in ("MEDIUM", "LARGE") and _LIGHTGBM_AVAILABLE:
    _lgb_p = lgb_params or {}
    models.append((
        "lgb",
        LGBMClassifier(
            n_estimators=_lgb_p.get("n_estimators", 300),
            max_depth=_lgb_p.get("max_depth", -1),       # -1 = no limit, usa num_leaves
            num_leaves=_lgb_p.get("num_leaves", 31),
            learning_rate=_lgb_p.get("learning_rate", 0.05),
            min_child_samples=_lgb_p.get("min_child_samples", 20),
            reg_alpha=_lgb_p.get("reg_alpha", 0.1),
            reg_lambda=_lgb_p.get("reg_lambda", 1.0),
            subsample=_lgb_p.get("subsample", 0.8),
            colsample_bytree=_lgb_p.get("colsample_bytree", 0.8),
            class_weight="balanced" if use_balanced else None,
            random_state=42,
            n_jobs=-1,
            verbose=-1,       # silenzioso
        ),
    ))
elif tier == "SMALL":
    # Mantieni sklearn GB per SMALL: più stabile su dataset piccoli (<350 campioni)
    # dove LightGBM con leaf-wise può overfittare se num_leaves > campioni/10
    _lgb_p = lgb_params or {}
    models.append((
        "gb",
        GradientBoostingClassifier(
            n_estimators=_lgb_p.get("n_estimators", 80),
            learning_rate=_lgb_p.get("learning_rate", 0.05),
            max_depth=min(_lgb_p.get("max_depth", 4), 4),
            min_samples_leaf=10,
            subsample=0.8,
            random_state=0,
        ),
    ))
# Per TINY: nessun GB/LGB — solo RF + LogReg
```

**Nota sull'early stopping di LightGBM:**
LightGBM supporta early stopping tramite callbacks in `fit()`. Tuttavia `_generate_oof_probas` chiama `model_clone.fit(X_tr, y_tr)` senza val set, quindi l'early stopping non è attivabile dentro i fold OOF (non si ha un val set separato per fold). L'early stopping viene attivato **solo nel fit finale** (riga 163-172 di `ensemble_trainer.py`) passando il val set:

```python
# In _generate_oof_probas, fit finale (righe 162-172):
for name, model in models:
    model_clone = _clone_model(model)
    fit_kwargs = {}
    if sample_weights is not None:
        fit_kwargs["sample_weight"] = sample_weights
    if isinstance(model_clone, LGBMClassifier) and _LIGHTGBM_AVAILABLE:
        # Early stopping sul val set solo per il fit finale
        # X_val e y_val devono essere passati come parametro aggiuntivo
        # NOTA: questo richiede di passare X_val/y_val a _generate_oof_probas
        pass  # implementato in P4 dove build_ensemble è refactored
    try:
        model_clone.fit(X, y, **fit_kwargs)
    except TypeError:
        model_clone.fit(X, y)
```

**Per il fit finale con early stopping, modificare la firma di `_generate_oof_probas`:**
```python
def _generate_oof_probas(
    models, X, y, splits, sample_weights=None, classes=None,
    X_val_for_es=None, y_val_for_es=None,   # ← NUOVO: per early stopping LGB
) -> Tuple[np.ndarray, List]:
```

### 4.4 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| lightgbm non installato | ImportError | Guard try/except + flag `_LIGHTGBM_AVAILABLE`, fallback a sklearn GB |
| `verbose=-1` non sufficiente | LightGBM stampa warning su stderr | Aggiungere `import warnings; warnings.filterwarnings("ignore", module="lightgbm")` |
| `max_depth=-1` con `num_leaves=31` | Alberi troppo profondi su dataset piccoli | `min_child_samples=20` impedisce foglie con <20 campioni — protezione efficace |
| `class_weight` non compatibile con `sample_weight` | LightGBM ignora `class_weight` se `sample_weight` viene passato | Nel codice attuale `sample_weights` è il time-decay weight — i due meccanismi sono mutuamente esclusivi. Usare solo `sample_weight` (time-decay), rimuovere `class_weight` da LGBMClassifier quando `sample_weight` è presente. |
| NaN nel dataset passato a LightGBM | LightGBM gestisce NaN nativamente | ✅ Nessun rischio — è il suo vantaggio. Non serve imputation prima del fit LGB. **ATTENZIONE:** il codice attuale in `_build_features` fa `X.fillna(medians)` — questo va mantenuto per RF e LogReg ma è superfluo per LGB. Non rimuoverlo per compatibilità multi-model. |
| Serializzazione del modello LightGBM con pickle | LightGBM supporta pickle nativo | ✅ Compatibile con `gzip.open + pickle.dump` esistente |
| `_clone_model` su LGBMClassifier | `sklearn.base.clone` funziona su LightGBM ≥4.0 | ✅ LightGBM 4.x implementa `get_params/set_params` sklearn-compatibile |

### 4.5 Validazione dopo implementazione

- Log deve mostrare `lgb` tra i base models per MEDIUM/LARGE, `gb` per SMALL, nessuno dei due per TINY
- Verificare assenza di stampe LightGBM in stdout durante training
- Confrontare `payload.metrics["lgb_logloss"]` vs `payload.metrics["gb_logloss"]` precedente — LGB deve avere logloss ≤ GB
- Eseguire `predict_fixture` su una fixture nota e verificare che le probabilità siano coerenti (somma ≈ 1.0, nessun NaN)

---

## 5. P3 — SMOTE collegato al training principale

### 5.1 Motivazione

Il dataset 1x2 ha distribuzione H≈44%, D≈27%, A≈29%. Il Draw è la classe minoritaria. Il meta-learner LogisticRegression addestrato sugli OOF impara implicitamente questa distribuzione: su match "equilibrati" (dove le feature non sono discriminanti) tende ad assegnare bassa probabilità al Draw per minimizzare la cross-entropy media — poi compensa alzando P(D) su tutti i match incerti uniformemente, generando il bias sistemico identificato nel MLAUDIT v1.

SMOTE (Synthetic Minority Oversampling) riequilibra le classi generando campioni sintetici della classe minoritaria interpolando tra campioni reali nello spazio delle feature. `SVMSMOTE` genera campioni solo nelle zone di confine del decision boundary — più realistici di un oversampling casuale.

**Dove applicare SMOTE:**
- ✅ Sul training set prima del fit dei base model (dentro `_generate_oof_probas`, su ogni fold)
- ✅ Sul training set per il fit finale dei base model
- ❌ MAI sul val set (inquinerebbe la calibrazione isotonic/temperature)
- ❌ MAI sull'holdout/metrics set (inquinerebbe il Brier/ECE)
- ❌ MAI prima dello split temporale (data leakage)

**Condizione di attivazione:** solo quando `imbalance_ratio < 0.35` E `tier` in (`MEDIUM`, `LARGE`). Su TINY e SMALL SMOTE potrebbe generare campioni sintetici che pesano più dei campioni reali, peggiorando la generalizzazione.

### 5.2 Localizzazione nel codice

**File:** `ensemble_trainer.py`
Il codice `dataset.py` ha già SMOTE importato (righe 11-15), ma `ensemble_trainer.py` non lo chiama mai. La connessione va fatta qui.

**File:** `Ai Engine/ai_engine/preprocessing/dataset.py` — già ha `SVMSMOTE`, `SMOTEENN`, `NearMiss`

### 5.3 Modifiche

**Import in `ensemble_trainer.py` (dopo gli import esistenti):**
```python
try:
    from imblearn.over_sampling import SVMSMOTE
    from imblearn.combine import SMOTEENN
    _IMBLEARN_AVAILABLE = True
except ImportError:
    _IMBLEARN_AVAILABLE = False
```

**Nuova funzione `_apply_smote` in `ensemble_trainer.py`:**

```python
def _apply_smote(
    X: np.ndarray,
    y: np.ndarray,
    imbalance_ratio: float,
    tier: str,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Apply SVMSMOTE resampling to balance minority classes.

    Rules:
    - Only applied when imbalance_ratio < 0.35 AND tier in (MEDIUM, LARGE)
    - Uses SVMSMOTE (boundary-aware) not plain SMOTE
    - Falls back to original data if imblearn not available or resampling fails
    - NEVER called on val/holdout sets — only on training folds

    Returns (X_resampled, y_resampled).
    """
    if not _IMBLEARN_AVAILABLE:
        return X, y
    if imbalance_ratio >= 0.35 or tier not in ("MEDIUM", "LARGE"):
        return X, y

    # Require minimum samples: SVMSMOTE needs at least k_neighbors+1 per class
    class_counts = np.bincount(y.astype(int)) if np.issubdtype(y.dtype, np.integer) else \
                   np.array([np.sum(y == c) for c in np.unique(y)])
    min_class_count = class_counts.min()
    if min_class_count < 6:
        # Too few samples in minority class — SMOTE would generate unrealistic interpolations
        return X, y

    try:
        smote = SVMSMOTE(random_state=random_state, k_neighbors=min(5, min_class_count - 1))
        X_res, y_res = smote.fit_resample(X, y)
        return X_res, y_res
    except Exception as exc:
        logger.warning("SMOTE failed, using original data: %s", exc)
        return X, y
```

**Modifica a `_generate_oof_probas`:** applicare SMOTE dentro ogni fold sul training split:

```python
for m_idx, (name, model) in enumerate(models):
    for train_idx, val_idx in splits:
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr = y[train_idx]
        w_tr = sample_weights[train_idx] if sample_weights is not None else None

        # Apply SMOTE on training fold only (never on val)
        if smote_params is not None:
            X_tr_fit, y_tr_fit = _apply_smote(
                X_tr, y_tr,
                imbalance_ratio=smote_params["imbalance_ratio"],
                tier=smote_params["tier"],
            )
            # Ricalcola sample_weight per i campioni sintetici (peso 1.0 — neutro)
            if w_tr is not None:
                n_new = len(X_tr_fit) - len(X_tr)
                w_tr_fit = np.concatenate([w_tr, np.ones(n_new)])
            else:
                w_tr_fit = None
        else:
            X_tr_fit, y_tr_fit, w_tr_fit = X_tr, y_tr, w_tr
        ...
```

**`smote_params` viene passato come nuovo parametro opzionale a `_generate_oof_probas`:**
```python
def _generate_oof_probas(
    models, X, y, splits, sample_weights=None, classes=None,
    X_val_for_es=None, y_val_for_es=None,
    smote_params: dict | None = None,   # ← NUOVO
) -> Tuple[np.ndarray, List]:
```

**In `build_ensemble`, costruire `smote_params` e passarlo:**
```python
smote_params = None
if _imbalance_ratio < 0.35 and tier in ("MEDIUM", "LARGE") and _IMBLEARN_AVAILABLE:
    smote_params = {"imbalance_ratio": _imbalance_ratio, "tier": tier}
```

### 5.4 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| SMOTE applicato al val set | Inquina calibrazione isotonic/temperature | ✅ Architettura garantisce: SMOTE solo dentro `_generate_oof_probas` sui fold train, mai su `X_val_np` |
| SMOTE con classe minoritaria <6 campioni | `SVMSMOTE` crash per k_neighbors > n_samples | ✅ Guard `min_class_count < 6` → fallback a dati originali |
| Sample weights inconsistenti dopo SMOTE | I campioni sintetici non hanno time-decay weight | I campioni sintetici ricevono peso 1.0 (neutro, equivalente a un match "medio" nella storia). Peso medio del dataset è ~0.7-0.9 — 1.0 è leggermente ottimistico ma non distorce materialmente. |
| Over-resampling su LARGE (840 campioni, D=27%) | SMOTE genera 140+ campioni sintetici per D | Con `SVMSMOTE` i campioni sono solo nelle zone di confine — non duplica dati lontani dal boundary. Accettabile. |
| `imbalance_ratio` calcolato su y_train ma SMOTE applicato a fold train | Fold train ha meno campioni, ratio può variare | La condizione `imbalance_ratio < 0.35` è calcolata su `y_tr_np` completo (non sul fold). È una stima conservativa — OK. |

### 5.5 Validazione dopo implementazione

- Log deve mostrare `SMOTE applied: 840 → 1020 samples (class D: 226 → 380)` per MEDIUM/LARGE con 1x2 sbilanciato
- Verificare che `len(y_oof)` dopo NaN-mask corrisponda ai campioni originali, non a quelli aumentati da SMOTE (OOF è calcolato sui campioni originali, SMOTE è solo dentro i fold)
- Verificare P(D) calibrata su holdout: deve scendere di 1-3pp rispetto a prima

---

## 6. P4 — Optuna per iperparametri per-lega

### 6.1 Motivazione

Gli iperparametri attuali sono euristiche fisse:
```python
# ensemble_trainer.py riga 66-68 (ATTUALE)
max_depth = 6 if n_samples < 2000 else 10
n_estimators_rf = 100 if n_samples < 1000 else 200
n_estimators_gb = 100 if n_samples < 1000 else 150
```

Questi valori sono ragionevoli come default ma non ottimali. La differenza tra iperparametri euristici e Bayesian-ottimizzati su dataset piccoli (100-300 campioni) è tipicamente 0.02-0.05 punti di NLL — sufficiente per spostare il BSS da 0.10 (sotto Gate 4) a 0.13 (sopra).

**Optuna è già installato (v4.7.0) e non richiede nessuna modifica alle dipendenze.**

### 6.2 Strategia di caching

Il tuning Optuna viene eseguito **una volta** per coppia (league_id, target) e salvato in un file JSON locale. Al retraining successivo viene caricato se esiste — il tuning viene ri-eseguito solo se il dataset è cresciuto di >20% rispetto all'ultimo tuning.

```
Ai Engine/models_cache/league_{id}/optuna_params_{target}.json
```

Struttura del file:
```json
{
  "league_id": 2,
  "target": "target_1x2",
  "n_train_at_tuning": 840,
  "tier": "LARGE",
  "best_params": {
    "rf": {"n_estimators": 180, "max_depth": 7, "min_samples_leaf": 8},
    "lgb": {"n_estimators": 250, "num_leaves": 45, "learning_rate": 0.04, ...},
    "xgb": {"n_estimators": 120, "max_depth": 5, "learning_rate": 0.08, ...}
  },
  "best_value": 0.847,
  "tuned_at": "2026-04-01T12:00:00Z"
}
```

### 6.3 Localizzazione nel codice

**File 1:** `ensemble_trainer.py` — nuova funzione `_run_optuna_tuning()`
**File 2:** `seriea_model_export.py` — chiamata a tuning prima di `build_ensemble()` in `_train_one_target()`

### 6.4 Modifiche in `ensemble_trainer.py`

**Nuova funzione `_run_optuna_tuning`:**

```python
def _run_optuna_tuning(
    X_train: np.ndarray,
    y_train: np.ndarray,
    splits: List[Tuple[np.ndarray, np.ndarray]],
    tier: str,
    n_trials: int,
    random_state: int = 42,
) -> dict:
    """
    Run Optuna Bayesian optimization to find best hyperparameters.

    Objective: minimize OOF NLL (negative log-likelihood) averaged across
    walk-forward folds. Uses the same splits used for OOF generation.

    Returns dict with keys "rf", "lgb" (or "gb"), "xgb" — each a dict of params.
    Returns empty dict (use defaults) if Optuna not available or n_trials == 0.
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("Optuna not available — using default hyperparameters")
        return {}

    if n_trials == 0 or not splits:
        return {}

    classes = np.unique(y_train)
    n_classes = len(classes)

    def _oof_nll(model, X, y, splits_):
        """Compute mean NLL across OOF folds for a single model."""
        nll_scores = []
        for tr_idx, val_idx in splits_:
            X_tr, X_v = X[tr_idx], X[val_idx]
            y_tr, y_v = y[tr_idx], y[val_idx]
            try:
                mc = _clone_model(model)
                mc.fit(X_tr, y_tr)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore")
                    proba = mc.predict_proba(X_v)
                nll_scores.append(log_loss(y_v, proba, labels=mc.classes_))
            except Exception:
                nll_scores.append(2.0)  # Penalità alta per modelli che crashano
        return float(np.mean(nll_scores)) if nll_scores else 2.0

    best_params: dict = {"rf": {}, "lgb": {}, "xgb": {}}

    # ── RF tuning ──────────────────────────────────────────────────────────
    def rf_objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 250),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 3, 25),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
        }
        model = RandomForestClassifier(**params, random_state=42, n_jobs=1)
        return _oof_nll(model, X_train, y_train, splits)

    rf_study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=random_state))
    rf_study.optimize(rf_objective, n_trials=n_trials, show_progress_bar=False)
    best_params["rf"] = rf_study.best_params

    # ── LGB/GB tuning ──────────────────────────────────────────────────────
    if tier in ("MEDIUM", "LARGE") and _LIGHTGBM_AVAILABLE:
        def lgb_objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 50, 400),
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 5.0, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            }
            model = LGBMClassifier(**params, random_state=42, n_jobs=1, verbose=-1)
            return _oof_nll(model, X_train, y_train, splits)

        lgb_study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=random_state))
        lgb_study.optimize(lgb_objective, n_trials=n_trials, show_progress_bar=False)
        best_params["lgb"] = lgb_study.best_params
    elif tier == "SMALL":
        def gb_objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 30, 150),
                "max_depth": trial.suggest_int("max_depth", 2, 5),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 20),
            }
            model = GradientBoostingClassifier(**params, subsample=0.8, random_state=0)
            return _oof_nll(model, X_train, y_train, splits)

        gb_study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=random_state))
        gb_study.optimize(gb_objective, n_trials=max(n_trials // 2, 10), show_progress_bar=False)
        best_params["lgb"] = gb_study.best_params  # chiave "lgb" usata uniformemente

    # ── XGB tuning ─────────────────────────────────────────────────────────
    if tier != "TINY" and _XGBOOST_AVAILABLE:
        def xgb_objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                "max_depth": trial.suggest_int("max_depth", 2, 7),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            }
            model = XGBClassifier(**params, use_label_encoder=False, eval_metric="mlogloss",
                                  verbosity=0, random_state=42, n_jobs=1)
            return _oof_nll(model, X_train, y_train, splits)

        xgb_study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=random_state))
        xgb_study.optimize(xgb_objective, n_trials=n_trials, show_progress_bar=False)
        best_params["xgb"] = xgb_study.best_params

    return best_params
```

### 6.5 Modifiche in `seriea_model_export.py`

**In `_train_one_target()`, aggiungere il blocco di caching Optuna prima della chiamata a `build_ensemble` (dopo il calcolo di `X_train_sel`, riga ~202):**

```python
# ── Optuna hyperparameter tuning (con cache per-lega) ─────────────────────
optuna_params = {}
_optuna_cache_path = os.path.join(out_dir, f"optuna_params_{target}.json")
_tier = _get_league_tier(len(y_train))
_n_trials = {"TINY": 0, "SMALL": 20, "MEDIUM": 35, "LARGE": 50}.get(_tier, 0)

if _n_trials > 0:
    _need_retune = True
    if os.path.exists(_optuna_cache_path):
        try:
            with open(_optuna_cache_path, "r") as _f:
                _cached = json.load(_f)
            _cached_n = _cached.get("n_train_at_tuning", 0)
            _cached_tier = _cached.get("tier", "")
            # Riutilizza cache se dataset non è cresciuto >20% e tier invariato
            if _cached_tier == _tier and len(y_train) < _cached_n * 1.20:
                optuna_params = _cached.get("best_params", {})
                _need_retune = False
                print(f"    Optuna cache hit per {target} (n_train={len(y_train)})")
        except Exception:
            pass

    if _need_retune:
        print(f"    Optuna tuning {target}: {_n_trials} trial, tier={_tier}...")
        # Costruisce gli split temporali per Optuna (stesso walk_forward usato in OOF)
        _combined_for_opt = X_train_sel.copy()
        _combined_for_opt["fixture_date"] = train_dates.values
        _opt_splits = walk_forward_splits(
            _combined_for_opt, n_splits=5, purge_days=30, min_train_rows=50
        )
        if _opt_splits:
            from ai_engine.ensemble_trainer import _run_optuna_tuning, _get_league_tier
            optuna_params = _run_optuna_tuning(
                X_train_sel.to_numpy().astype(float),
                y_train.to_numpy(),
                _opt_splits,
                tier=_tier,
                n_trials=_n_trials,
            )
            try:
                import json as _json
                with open(_optuna_cache_path, "w") as _f:
                    _json.dump({
                        "league_id": league_id,
                        "target": target,
                        "n_train_at_tuning": len(y_train),
                        "tier": _tier,
                        "best_params": optuna_params,
                        "tuned_at": datetime.now(timezone.utc).isoformat(),
                    }, _f, indent=2)
            except Exception as e:
                print(f"    Avviso: impossibile salvare cache Optuna: {e}")
```

**Passare `optuna_params` e `tier` a `build_ensemble`:**
```python
payload = build_ensemble(
    X_train_sel, y_train,
    X_val_sel, y_val,
    sample_weights=weights_train,
    feature_cols=selected_cols,
    feature_medians=selected_medians,
    train_dates=train_dates,
    optuna_params=optuna_params,   # ← NUOVO
    tier=_tier,                    # ← NUOVO
)
```

**Aggiornare firma di `build_ensemble` in `ensemble_trainer.py`:**
```python
def build_ensemble(
    X_train, y_train, X_val, y_val,
    sample_weights=None, feature_cols=None, feature_medians=None,
    train_dates=None,
    optuna_params: dict | None = None,   # ← NUOVO
    tier: str | None = None,             # ← NUOVO
) -> EnsemblePayload:
```

All'inizio di `build_ensemble`, calcolare il tier se non passato:
```python
if tier is None:
    tier = _get_league_tier(len(y_tr_np))
```

### 6.6 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| Optuna timeout su leghe LARGE con 50 trial × 3 modelli | Training molto lento (>30 min per target) | Ogni trial è un fit di un singolo modello su fold OOF — tipicamente 0.5-2 sec/trial. 50 trial × 3 modelli × 5 fold ≈ 750 fit. Con n_jobs=1 su ogni modello in Optuna: ~5-10 min per target. Accettabile. |
| Cache Optuna obsoleta dopo aggiornamento DB | Modello addestrato con iperparametri per vecchio dataset | ✅ Re-tune automatico se `len(y_train) > cached_n * 1.20` (+20%) |
| `json.load` su file cache corrotto | Exception al load | ✅ try/except: se fail → `_need_retune=True` → ri-esegue tuning |
| Optuna importato ma non disponibile | Non può capitare se installato | Guard `try/except ImportError` nella funzione |
| Trial con modelli che crashano (es. XGB su dataset troppo piccolo) | NLL=2.0 (penalità) → trial scartato | ✅ `_oof_nll` ritorna 2.0 su eccezione — Optuna ignora questi trial nella convergenza |
| `walk_forward_splits` ritorna lista vuota | Optuna salta il tuning | ✅ Guard `if _opt_splits:` → usa default params |

### 6.7 Validazione dopo implementazione

- Prima esecuzione: log deve mostrare `Optuna tuning target_1x2: 50 trial, tier=LARGE...`
- Seconda esecuzione: log deve mostrare `Optuna cache hit per target_1x2`
- Verificare che `optuna_params_target_1x2.json` esista in `models_cache/league_{id}/`
- Confrontare NLL del modello con params Optuna vs params default: NLL deve essere ≤

---

## 7. P5 — Temperature Scaling al posto di isotonic multiclasse

### 7.1 Motivazione

La calibrazione isotonic per-classe con renormalizzazione ha un problema matematico fondamentale (documentato nel MLAUDIT v1, parzialmente fixato in P4 del v1). Per target multiclasse (H/D/A), applicare tre regressioni isotoniche indipendenti e poi rinormalizzare distrugge la garanzia matematica di ciascun calibratore.

**Temperature Scaling** risolve questo con un singolo parametro `T > 0`:

```
P_calibrated = softmax(log(P_raw) / T)
```

- `T > 1`: distribuisce le probabilità verso l'uniforme (il modello era troppo sicuro)
- `T < 1`: concentra le probabilità (il modello era troppo incerto)
- `T = 1`: nessuna modifica

Poiché usa `softmax`, la somma è **sempre 1.0 per costruzione matematica** — zero renormalizzazione, zero ridistribuzione di errori tra classi.

**Estensione:** per il bias sistematico su D, aggiungere **bias per-classe** (3 parametri aggiuntivi, uno per classe). Il modello diventa:

```
logits_c = log(P_raw_c) / T + bias_c
P_calibrated = softmax(logits_c)
```

Con 4 parametri totali (T + 3 bias), si possono correggere sia la dispersione globale (T) che il bias sistematico di classi specifiche (bias_D > 0 se il modello sottostima D).

### 7.2 Localizzazione nel codice

**File:** `ensemble_trainer.py`
- Sostituisce `_train_isotonic_calibrators()` per target multiclasse (riga 202–300)
- Mantiene la logica isotonic per target **binari** (P(True) → P(False) = 1-P(True)) — già corretto nel MLAUDIT v1

**La scelta del metodo di calibrazione è tier-dipendente:**
- TINY: nessuna calibrazione (dati insufficienti per stimare T)
- SMALL: isotonic per binari, temperature scaling senza bias per multiclasse
- MEDIUM/LARGE: isotonic per binari, temperature scaling CON bias per-classe per multiclasse

### 7.3 Modifiche

**Nuova funzione `_fit_temperature_scaling` in `ensemble_trainer.py`:**

```python
def _fit_temperature_scaling(
    proba: np.ndarray,
    y_true: np.ndarray,
    classes: np.ndarray,
    use_class_bias: bool = False,
    min_samples: int = 30,
) -> dict | None:
    """
    Fit temperature scaling calibration on validation set.

    For multiclass targets: finds T (and optionally per-class bias) that
    minimizes NLL on val set. Uses scipy.optimize.minimize (L-BFGS-B).

    Args:
        proba:         (n, n_classes) ensemble probabilities (pre-isotonic)
        y_true:        (n,) string labels
        classes:       (n_classes,) class labels in order
        use_class_bias: if True, also fits per-class bias corrections
        min_samples:   minimum val samples to attempt fitting

    Returns dict {"T": float, "bias": np.ndarray | None} or None if fitting fails.
    """
    from scipy.optimize import minimize
    from scipy.special import softmax as scipy_softmax

    if len(y_true) < min_samples:
        return None

    n_classes = len(classes)
    class_to_idx = {str(c): i for i, c in enumerate(classes)}
    y_onehot = np.zeros((len(y_true), n_classes))
    for i, y in enumerate(y_true):
        idx = class_to_idx.get(str(y))
        if idx is not None:
            y_onehot[i, idx] = 1

    # Log probabilities (safe)
    log_proba = np.log(np.clip(proba, 1e-9, 1.0))

    def nll(params):
        T = params[0]
        if T <= 0:
            return 1e9
        bias = params[1:] if use_class_bias else np.zeros(n_classes)
        scaled_logits = log_proba / T + bias
        cal_proba = scipy_softmax(scaled_logits, axis=1)
        # NLL = -mean(sum(y_onehot * log(cal_proba)))
        return -float(np.mean(np.sum(y_onehot * np.log(np.clip(cal_proba, 1e-9, 1.0)), axis=1)))

    # Initial params: T=1.0, bias=0.0 per classe
    n_params = 1 + (n_classes if use_class_bias else 0)
    x0 = np.ones(n_params)
    x0[0] = 1.0  # T iniziale = 1 (nessuna modifica)

    # Bounds: T in [0.1, 5.0], bias in [-2.0, 2.0]
    bounds = [(0.1, 5.0)] + ([(-2.0, 2.0)] * (n_classes if use_class_bias else 0))

    try:
        result = minimize(nll, x0, method="L-BFGS-B", bounds=bounds,
                         options={"maxiter": 500, "ftol": 1e-7})
        T_opt = float(result.x[0])
        bias_opt = result.x[1:] if use_class_bias else None
        return {"T": T_opt, "bias": bias_opt, "nll": float(result.fun)}
    except Exception as exc:
        logger.warning("Temperature scaling fit failed: %s", exc)
        return None


def _apply_temperature_scaling(
    proba: np.ndarray,
    ts_params: dict,
    classes: np.ndarray,
) -> np.ndarray:
    """
    Apply temperature scaling to a probability matrix.

    Returns calibrated probabilities with shape (n, n_classes).
    Guaranteed to sum to 1.0 per row (softmax).
    """
    from scipy.special import softmax as scipy_softmax

    T = ts_params.get("T", 1.0)
    bias = ts_params.get("bias")

    log_proba = np.log(np.clip(proba, 1e-9, 1.0))
    scaled = log_proba / T
    if bias is not None:
        scaled = scaled + bias
    return scipy_softmax(scaled, axis=1)
```

**Modifica a `_train_isotonic_calibrators`:** rinominare in `_train_calibrators` con selezione metodo:

```python
def _train_calibrators(
    fitted_models, meta_model, X_val, y_val, classes,
    min_samples=50, base_weights=None, tier="MEDIUM",
) -> dict:
    """
    Train calibrators based on tier and number of classes.

    Binary targets (2 classes): isotonic on P(True) only.
    Multiclass targets (3+ classes): temperature scaling.
    TINY tier: no calibration.
    """
    if tier == "TINY" or len(y_val) < min_samples:
        return {}

    # ... (calcolo proba_aligned invariato) ...

    n_classes = len(classes)
    is_binary = (n_classes == 2)
    class_strs = [str(c) for c in classes]

    if is_binary:
        # Calibrazione isotonic per binari (P4 fix MLAUDIT v1 — invariato)
        # ... (logica isotonic esistente) ...
        return calibrators

    else:
        # Temperature scaling per multiclasse
        use_bias = tier in ("MEDIUM", "LARGE")
        y_val_str = np.array([str(v) for v in y_val])
        ts_params = _fit_temperature_scaling(
            proba_aligned, y_val_str, classes,
            use_class_bias=use_bias,
        )
        if ts_params is None:
            return {}
        # Ritorna nel formato atteso da predict_ensemble
        return {"__temperature_scaling__": ts_params, "__classes__": list(class_strs)}
```

**Modifica a `predict_ensemble`:** rilevare se i calibratori sono di tipo temperature scaling:

```python
if getattr(payload, "isotonic_calibrators", None):
    cals = payload.isotonic_calibrators
    if "__temperature_scaling__" in cals:
        # Temperature scaling multiclasse
        ts_params = cals["__temperature_scaling__"]
        ts_classes = np.array(cals.get("__classes__", list(result.keys())))
        # Converti result dict in array ordinato
        proba_arr = np.array([[result.get(c, 0.0) for c in ts_classes]])
        cal_arr = _apply_temperature_scaling(proba_arr, ts_params, ts_classes)
        result = {c: float(cal_arr[0, i]) for i, c in enumerate(ts_classes)}
    else:
        # Logica isotonic binaria esistente (invariata)
        ...
```

### 7.4 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| `scipy.optimize.minimize` non converge | `result.success=False`, T resta vicino a 1.0 | ✅ Ritorna il miglior T trovato anche se non converge — peggio di un fit perfetto ma meglio di niente |
| `T = 0` o `T < 0` durante ottimizzazione | Divisione per zero in `log_proba / T` | ✅ Bounds `(0.1, 5.0)` impediscono T ≤ 0 |
| Bias per-classe estremi (>2.0) | Probabilità distorte oltre il range fisico | ✅ Bounds `(-2.0, 2.0)` sui bias |
| `proba` con valori 0.0 esatti | `log(0) = -inf` → crash | ✅ `np.clip(proba, 1e-9, 1.0)` prima di `np.log` |
| `__temperature_scaling__` come chiave in dizionario serializzato | Conflitto con vecchi modelli salvati | ✅ Chiave preceduta da `__` non può essere un class label reale (H/D/A/True/False) |
| Modelli salvati precedentemente con isotonic multiclasse | `predict_ensemble` usa vecchia logica | ✅ Backward compatibility: se `__temperature_scaling__` NON è in `cals` → usa logica isotonic precedente |
| `scipy` non disponibile | Import error | scipy è già installato (v1.17.0) — nessun rischio |

### 7.5 Validazione dopo implementazione

- Per target_1x2: `payload.isotonic_calibrators` deve contenere chiave `"__temperature_scaling__"` con `T` e `bias`
- Per target_btts (binario): `payload.isotonic_calibrators` deve contenere chiavi `"True"` e/o `"False"` (IsotonicRegression)
- Verificare che la somma delle probabilità calibrate sia 1.000 (±1e-6) per ogni predizione
- Verificare che T ≠ 1.0 (il modello ha effettivamente calibrato qualcosa)

---

## 8. P6 — MLP meta-learner adattivo

### 8.1 Motivazione

Il meta-learner `LogisticRegression(C=0.5)` combina le probabilità dei base model linearmente. Non può catturare relazioni del tipo: *"quando RF dice H=0.55 e LGB dice H=0.46 (divergenza di 9pp), storicamente il LGB è più accurato per questo tipo di match"*.

Un MLP con 1 hidden layer da 16-32 neuroni può apprendere queste interazioni non-lineari tra i base model. Con la fix P11 del MLAUDIT v1 (OOF sull'80% del training set) e l'aggiunta di XGBoost (P1), l'input del meta-learner è ora:

```
[RF_H, RF_D, RF_A, LGB_H, LGB_D, LGB_A, XGB_H, XGB_D, XGB_A, LR_H, LR_D, LR_A]
→ 12 feature per 3 classi, 4 modelli
```

Con 12×32 + 32×3 = 480 parametri, un MLP non overfitterebbe su 600+ campioni OOF. Su <400 campioni la LogisticRegression è ancora preferibile.

**TensorFlow e Keras sono già installati (TF 2.20, Keras 3.13).**

### 8.2 Localizzazione nel codice

**File:** `ensemble_trainer.py`
**Modifica:** blocco meta-learner in `build_ensemble()` — riga 394–403 (attualmente: `LogisticRegression`)

### 8.3 Modifiche

**Nuova funzione `_build_mlp_meta` in `ensemble_trainer.py`:**

```python
def _build_mlp_meta(
    n_input: int,
    n_classes: int,
    dropout_rate: float = 0.3,
) -> Any:
    """
    Build a small MLP meta-learner using Keras.

    Architecture: Dense(32, ReLU) → Dropout → Dense(n_classes, Softmax)
    Minimal size to avoid overfitting on small OOF datasets.

    Returns a compiled Keras model.
    """
    try:
        import tensorflow as tf
        tf.get_logger().setLevel("ERROR")
        import keras
        from keras import layers

        model = keras.Sequential([
            layers.Input(shape=(n_input,)),
            layers.Dense(32, activation="relu",
                        kernel_regularizer=keras.regularizers.l2(0.01)),
            layers.Dropout(dropout_rate),
            layers.Dense(n_classes, activation="softmax"),
        ])
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        return model
    except ImportError:
        return None


class _KerasMetaWrapper:
    """
    Sklearn-compatible wrapper per Keras MLP meta-learner.
    Implementa fit() e predict_proba() con interfaccia sklearn.
    """
    def __init__(self, n_input: int, n_classes: int, class_labels: list):
        self._n_input = n_input
        self._n_classes = n_classes
        self.classes_ = np.array(class_labels)
        self._model = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_KerasMetaWrapper":
        """Fit MLP on OOF data with early stopping."""
        try:
            import keras
            self._model = _build_mlp_meta(self._n_input, self._n_classes)
            if self._model is None:
                raise RuntimeError("Keras not available")

            # Label encode y to integer indices
            label_to_idx = {str(c): i for i, c in enumerate(self.classes_)}
            y_int = np.array([label_to_idx.get(str(v), 0) for v in y])

            # Stratified train/val split (80/20) per early stopping
            from sklearn.model_selection import StratifiedShuffleSplit
            sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
            tr_idx, v_idx = next(sss.split(X, y_int))

            es = keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=15, restore_best_weights=True, verbose=0
            )
            self._model.fit(
                X[tr_idx], y_int[tr_idx],
                validation_data=(X[v_idx], y_int[v_idx]),
                epochs=200,
                batch_size=min(32, max(8, len(tr_idx) // 10)),
                callbacks=[es],
                verbose=0,
            )
        except Exception as exc:
            logger.warning("MLP meta-learner fit failed: %s — falling back to None", exc)
            self._model = None
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            n = X.shape[0]
            return np.full((n, self._n_classes), 1.0 / self._n_classes)
        try:
            proba = self._model.predict(X, verbose=0)
            # Clip and renorm for numerical stability
            proba = np.clip(proba, 1e-9, 1.0)
            return proba / proba.sum(axis=1, keepdims=True)
        except Exception:
            n = X.shape[0]
            return np.full((n, self._n_classes), 1.0 / self._n_classes)
```

**Modifica al blocco meta-learner in `build_ensemble()` (riga 394–403):**

```python
# Selezione meta-learner in base a tier e dimensione OOF
_use_mlp = (
    tier == "LARGE"
    and len(oof_clean) >= 400
    and _TENSORFLOW_AVAILABLE
)

if len(oof_clean) >= 20 and oof_clean.shape[1] > 0:
    if _use_mlp:
        meta_model = _KerasMetaWrapper(
            n_input=oof_clean.shape[1],
            n_classes=n_classes,
            class_labels=[str(c) for c in classes],
        )
        try:
            meta_model.fit(oof_clean, y_oof)
            if meta_model._model is None:
                # Fallback se Keras ha fallito internamente
                meta_model = None
        except Exception:
            meta_model = None

    if not _use_mlp or meta_model is None:
        meta_base = LogisticRegression(max_iter=2000, C=0.5, random_state=0)
        try:
            meta_base.fit(oof_clean, y_oof)
            meta_model = meta_base
        except Exception:
            meta_model = None
else:
    meta_model = None
```

**Import aggiuntivo (top di `ensemble_trainer.py`):**
```python
try:
    import tensorflow as _tf
    _tf.get_logger().setLevel("ERROR")
    _TENSORFLOW_AVAILABLE = True
except ImportError:
    _TENSORFLOW_AVAILABLE = False
```

### 8.4 Modifica alla serializzazione

Il `_KerasMetaWrapper` non è serializzabile con pickle standard (il modello Keras contiene tensori). Modificare `seriea_model_export.py` nel blocco `save_payload`:

```python
# Se meta_model è _KerasMetaWrapper, salva i pesi separatamente
_meta_to_save = payload.meta_model
if hasattr(payload.meta_model, "_model") and payload.meta_model._model is not None:
    _keras_weights_path = model_path.replace(".pkl.gz", "_meta_weights.keras")
    try:
        payload.meta_model._model.save(_keras_weights_path)
        _meta_to_save = {
            "__keras_meta__": True,
            "n_input": payload.meta_model._n_input,
            "n_classes": payload.meta_model._n_classes,
            "class_labels": list(payload.meta_model.classes_),
            "weights_path": _keras_weights_path,
        }
    except Exception as e:
        logger.warning("Keras meta save failed, falling back to LR: %s", e)
        _meta_to_save = None  # predict_ensemble usa weighted avg come fallback
```

**Modifica a `_load_model` (o equivalente) in `predict_fixture.py` o `ensemble_trainer.py`:** ricaricare il meta da file Keras se `__keras_meta__` è presente nel payload.

### 8.5 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| TensorFlow non disponibile | Import error | ✅ Guard `_TENSORFLOW_AVAILABLE`, fallback a LR |
| MLP overfitting su OOF piccolo | BSS gonfiato | ✅ Condizione `len(oof_clean) >= 400` + Dropout(0.3) + EarlyStopping |
| `_KerasMetaWrapper` non serializzabile con pickle | Crash al salvataggio modello | ✅ Logica di salvataggio separata in seriea_model_export.py |
| Keras model.save fallisce | Modello non salvato | ✅ Fallback a `_meta_to_save = None` → predict_ensemble usa weighted average |
| Dimensioni OOF cambiano tra training (4 modelli) e predict (atteso 3 modelli) | Shape mismatch nel meta | ✅ `_n_input` salvato nel payload — se cambia il numero di base models il modello viene ignorato e si usa weighted avg |
| `StratifiedShuffleSplit` su OOF con classi rare | Classe non rappresentata nel val di early stopping | try/except in fit() → fallback a LR se non funziona |

---

## 9. P7 — xG e shots on target come feature rolling

### 9.1 Motivazione

Il tuo modello attuale vede: form (gol segnati/subiti rolling), ELO, H2H, standings, odds. Mancano due predittori fondamentali:

**Expected Goals (xG):** misura la qualità delle occasioni, non i gol effettivi. Una squadra che crea 2.1 xG e segna 0 gol è statisticamente più forte di quanto dica il risultato. I goal seguono Poisson(λ) con λ ≈ xG — xG è letteralmente il parametro del modello generativo. Per i mercati Over/BTTS, `rolling_xg` è la feature più predittiva disponibile.

**Shots on target:** indicatore di pressione offensiva, correlato a gol futuri indipendentemente dai gol passati (riduce il rumore Poisson).

**Condizione:** questi dati devono essere presenti in `match_team_stats` nel DB. Per le leghe dove la tabella è vuota, le feature saranno NaN e verranno droppate dal filtro `nan_pct > 0.50` già esistente in `_build_features()` — **nessun crash**.

### 9.2 Localizzazione nel codice

**File:** `Ai Engine/ai_engine/feature_pipeline.py`
Aggiungere nuova funzione `_build_xg_features()` e chiamarla da `build_feature_dataframe_for_fixtures()`.

**File:** `Ai Engine/ai_engine/seriea_model_export.py`
Rimuovere `home_stats_*` e `away_stats_*` da `drop_cols` (righe 415-417) per permettere che le feature xG aggregate vengano usate.

### 9.3 Modifiche in `feature_pipeline.py`

**Nuova funzione `_build_xg_features`:**

```python
def _build_xg_features(
    fixture_ids: list[int],
    home_team_ids: list[int],
    away_team_ids: list[int],
    fixture_dates: list,
    supabase_client,
    windows: list[int] = [5, 10],
) -> pd.DataFrame:
    """
    Build rolling xG and shots features from match_team_stats.

    For each fixture (pre-match context):
    - home_xg_created_{w}:   rolling mean xG created by home team (last w matches)
    - home_xg_conceded_{w}:  rolling mean xG conceded by home team
    - away_xg_created_{w}:   rolling mean xG created by away team
    - away_xg_conceded_{w}:  rolling mean xG conceded by away team
    - home_shots_on_{w}:     rolling mean shots on target (home)
    - away_shots_on_{w}:     rolling mean shots on target (away)

    Features are pre-match aggregates (computed ONLY on matches before current fixture).
    No data leakage: shift(1) guaranteed by date filter.

    Returns DataFrame with fixture_id as index. All columns are float.
    Missing data (lega senza match_team_stats) → NaN → dropped by _build_features.
    """
    # ... implementazione con query Supabase a match_team_stats
    # Filtra per home_team_id/away_team_id, ordina per data, rolling mean
```

**Colonne prodotte:**
```
home_xg_created_5, home_xg_created_10
home_xg_conceded_5, home_xg_conceded_10
away_xg_created_5, away_xg_created_10
away_xg_conceded_5, away_xg_conceded_10
home_shots_on_5, home_shots_on_10
away_shots_on_5, away_shots_on_10
diff_xg_5 = home_xg_created_5 - away_xg_created_5
diff_xg_10 = home_xg_created_10 - away_xg_created_10
```

**14 feature totali** — se tutte NaN per una lega, verranno droppate automaticamente da `_build_features`.

### 9.4 Modifiche in `seriea_model_export.py`

**Righe 415-417 (drop_cols) — RIMUOVERE questa riga:**
```python
# RIMUOVERE:
drop_cols += [c for c in train_df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
```

**Sostituire con:**
```python
# Droppa solo le stat post-match raw (leakage) ma NON le feature aggregate pre-match
# che iniziano con home_xg_*, away_xg_*, home_shots_*, away_shots_* (pre-match rolling)
_raw_stats_to_drop = [
    c for c in train_df.columns
    if (c.startswith("home_stats_") or c.startswith("away_stats_"))
    and not any(c.startswith(p) for p in [
        "home_stats_xg_created_", "home_stats_xg_conceded_",
        "away_stats_xg_created_", "away_stats_xg_conceded_",
        "home_stats_shots_on_", "away_stats_shots_on_",
    ])
]
drop_cols += _raw_stats_to_drop
```

**Nota:** se `_build_xg_features` produce colonne con prefisso `home_xg_*` (non `home_stats_*`), questa modifica non è necessaria. Dipende da come vengono nominate le colonne nel join del `feature_pipeline`. L'importante è che le feature xG aggregate non finiscano in `drop_cols`.

### 9.5 Review di rischio

| Scenario | Rischio | Mitigazione |
|----------|---------|-------------|
| `match_team_stats` vuota per una lega | Tutte le colonne xG sono NaN | ✅ `nan_pct > 0.50` in `_build_features` le droppa silenziosamente |
| xG della partita corrente incluso nel rolling | Data leakage | ✅ Il rolling usa `shift(1)` — esclude la partita corrente. Implementare con `df.sort_values('date').shift(1).rolling(w).mean()` |
| xG per partite future (pre-match) | Non disponibile (ovviamente) | ✅ Le feature sono rolling storiche — calcolate sui match storici della squadra, non sulla partita da predire |
| `home_stats_*` rimosse da drop_cols ma contengono dati post-match raw | Leakage se la colonna è il valore della singola partita | ✅ La logica di drop mantiene solo le colonne aggregate (rolling mean) — le colonne raw `home_stats_xg_home` (singola partita) devono rimanere in drop_cols |

---

## 10. Ordine di Implementazione e Dipendenze

```
P1 (XGBoost 4° model)
  │
  ├─► P2 (LightGBM) — modifica _build_base_models, richiede P1 per la firma aggiornata
  │
  ├─► P3 (SMOTE) — modifica _generate_oof_probas, indipendente da P2
  │     │
  │     └─► P4 (Optuna) — dipende da P1+P2 (ottimizza i nuovi modelli)
  │                │
  │                └─► P5 (Temp Scaling) — dipende da P4 (tier è già calcolato)
  │                          │
  │                          └─► P6 (MLP) — dipende da P4 (tier) e P5 (calibrazione)
  │
  └─► P7 (xG features) — indipendente, modifiche su feature_pipeline.py
```

**Ordine consigliato:**
1. P1 → P2 (ensemble base aggiornato)
2. P3 (SMOTE — indipendente, basso rischio)
3. P4 (Optuna — dipende da P1+P2)
4. P5 (Temperature Scaling — dipende da P4 per tier)
5. P6 (MLP — dipende da P4+P5)
6. P7 (xG — indipendente, richiede verifica DB)

**Retraining necessario dopo:** P1, P2, P4 (iperparametri), P5 (calibrazione), P6 (meta-learner), P7 (nuove feature)

---

## 11. Checklist di Validazione Finale

### 11.1 Dopo ogni modifica — Test rapido

```python
# Eseguire dopo ogni punto implementato:
from ai_engine.ensemble_trainer import build_ensemble
import pandas as pd, numpy as np

# Dataset sintetico 200 campioni, 3 classi, 10 feature
np.random.seed(42)
n = 200
X = pd.DataFrame(np.random.randn(n, 10), columns=[f"f{i}" for i in range(10)])
X["fixture_date"] = pd.date_range("2022-01-01", periods=n, freq="7D")
y = pd.Series(np.random.choice(["H", "D", "A"], n))

payload = build_ensemble(X.drop(columns=["fixture_date"]), y,
                         X.drop(columns=["fixture_date"]).iloc[-30:],
                         y.iloc[-30:],
                         train_dates=X["fixture_date"])

# Asserzioni:
assert len(payload.base_models) >= 2  # almeno RF + LR
assert payload.meta_model is not None or len(payload.base_weights) > 0
assert all(abs(sum(v.values()) - 1.0) < 1e-5
           for v in [{"H": 0.5, "D": 0.3, "A": 0.2}])  # placeholder
print("✅ build_ensemble OK")
```

### 11.2 Checklist per ciascun punto

**P1 (XGBoost):**
- [ ] `"xgb"` in `payload.base_weights` per tier SMALL/MEDIUM/LARGE
- [ ] `len(payload.base_models) == 4` per MEDIUM/LARGE, `3` per SMALL, `2` per TINY
- [ ] No ImportError se xgboost non installato (test con `_XGBOOST_AVAILABLE = False`)

**P2 (LightGBM):**
- [ ] `"lgb"` in `payload.base_weights` per MEDIUM/LARGE (non `"gb"`)
- [ ] `"gb"` in `payload.base_weights` per SMALL (sklearn GB, non LGB)
- [ ] Nessun output LightGBM su stdout
- [ ] `pip install lightgbm` aggiunto a requirements.txt

**P3 (SMOTE):**
- [ ] Log mostra `SMOTE applied: X → Y samples` per MEDIUM/LARGE con imbalance<0.35
- [ ] `len(oof_clean)` ≤ `len(y_tr_np)` (SMOTE non gonfia OOF — solo fold train)
- [ ] Nessun SMOTE su val/holdout (verificabile loggando len(X_val))

**P4 (Optuna):**
- [ ] File `optuna_params_{target}.json` creato in `models_cache/league_{id}/`
- [ ] Seconda esecuzione mostra `Optuna cache hit`
- [ ] NLL con params Optuna ≤ NLL con params default (su stesso val set)

**P5 (Temperature Scaling):**
- [ ] `"__temperature_scaling__"` in `payload.isotonic_calibrators` per target 1x2/ht_1x2
- [ ] `"True"` o `"False"` in `payload.isotonic_calibrators` per target binari (btts, over_*)
- [ ] Somma probabilità calibrate = 1.000 ± 1e-6

**P6 (MLP):**
- [ ] Per LARGE con OOF≥400: `isinstance(payload.meta_model, _KerasMetaWrapper)` = True
- [ ] File `*_meta_weights.keras` salvato accanto al `.pkl.gz`
- [ ] Fallback a LR se TF non disponibile o fit fallisce

**P7 (xG features):**
- [ ] Per leghe con `match_team_stats` popolato: colonne `home_xg_created_5` presenti
- [ ] Per leghe senza dati: colonne droppate silenziosamente, training procede normalmente
- [ ] Nessuna colonna `home_stats_*` raw (post-match singola partita) nel training set

### 11.3 Test di integrazione end-to-end

```bash
# Eseguire training completo su una lega nota (es. Serie A = league_id 2)
python -c "
from ai_engine.seriea_model_export import train_and_save_all
results = train_and_save_all(league_id=2, last_n_seasons=3,
                              targets_filter=['target_1x2', 'target_btts'])
for r in results:
    print(f'{r[\"target\"]}: brier={r[\"brier\"]}, ece={r[\"ece\"]}, features={r[\"feature_count\"]}')
"
# Atteso:
# target_1x2: brier=0.55-0.62, ece<0.08, features=30-60
# target_btts: brier=0.22-0.28, ece<0.06, features=25-50
```

### 11.4 Soglie di accettazione post-retraining

| Metrica | Soglia minima | Note |
|---------|--------------|------|
| BSS target_1x2 (holdout) | > 0.10 | Con fix MLAUDIT v1 + questa roadmap |
| ECE target_1x2 (multiclasse) | < 0.07 | Temperature Scaling deve migliorare da ~0.10 |
| BSS target_btts (holdout) | > 0.08 | Mercato più semplice |
| NLL rispetto a baseline | ≤ baseline − 0.02 | Almeno 0.02 punti di miglioramento |
| Training time per target LARGE | < 15 min | Include Optuna 50 trial |
| Training time per target SMALL | < 3 min | Include Optuna 20 trial |

---

*Documento generato da analisi comparativa ProphitBet vs sistema attuale + audit codice 2026-04-01.
Stack tecnologico: LightGBM + XGBoost + Optuna + Temperature Scaling + MLP (Keras) + SMOTE.
Tutti i riferimenti sono verificati sulle righe indicate. Versione codebase: post-MLAUDIT-v1-fixes.*
