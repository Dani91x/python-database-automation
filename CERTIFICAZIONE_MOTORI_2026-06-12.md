# CERTIFICAZIONE MOTORI — 2026-06-12

Audit di ri-verifica su master (commit `d752cfe`+) con 5 agenti indipendenti:
Poisson core, catena Poisson→foglio, training ML, serving ML, infrastruttura training.
Ogni finding è stato verificato sul codice reale prima di entrare in questo documento.

---

## 1) MOTORE POISSON (`poisson_xg_hybrid_dc`) — ✅ CERTIFICATO

### Matematica core (Prediction/today_predictions_backfill.py)
| Componente | Verdetto |
|---|---|
| PMF Poisson (scipy, griglia 11×11, no overflow) | ✅ corretto |
| Dixon-Coles τ (4 celle, formula 1997 esatta, ρ per-lega + clamp + fallback −0.13) | ✅ corretto |
| Forze squadra (shrinkage bayesiano k=8, baseline di lega venue-specific, blend xG η=0.6, xGA derivato) | ✅ corretto |
| Mercati 1X2/OU/BTTS/HT (maschere esaustive, normalizzazione esplicita H+D+A=1.0 esatto) | ✅ corretto |
| Catena HT (Beta-Binomiale k=12, griglia HT con stesso ρ, blend w=n/(n+10)) | ✅ corretto |
| Calibrazione dinamica (shrinkage EB n/(n+75), monotonia PAVA, fallthrough a statica) | ✅ corretto |

### Catena segnali → foglio (money_management, mm_sheets, backtest)
| Stadio | Verdetto |
|---|---|
| Mapping 15 mercati JSON→MARKET_MAP→foglio (nessun drop silenzioso) | ✅ |
| Commissione Betfair 5%: applicata UNA volta (edge, stake, settlement coerenti) | ✅ |
| Calibrazione single-pass (lega→globale→statica, early-exit, mai doppia) | ✅ |
| Kelly frazionato 10%, cap 2%, floor €1, guardie idempotenti (correlated/concordance) | ✅ |
| P&L foglio = P&L live (MM_NET_FACTOR 0.95; ora da fonte unica, vedi fix sotto) | ✅ |
| master_backtest fedele al live (stesse soglie, stessa catena calibrazione, edge×√prob) | ✅ |

### Gap best-practice (matematicamente corretti, miglioramento marginale — già differiti per vincolo "nessun cambio strategia")
- Forze via ratio-of-means invece di DC-MLE congiunto (Δλ ~2-3%).
- Finestre fisse [5,10,15] invece di decay esponenziale half-life ~360-390gg (Ley 2018; ΔRPS ≈ 0.0001, cosmetico).
- η=0.6 xG hard-coded, non tarato per lega.

### Reality check (invariato dall'audit 2026-06-10)
Il motore è matematicamente sano ma NON batte la closing line (CLV≈0). Le leve vere
sono informative (line-shopping/CLV, differite come cambio strategia), non matematiche.

---

## 2) MOTORE ML — ✅ CERTIFICATO

### Training (ensemble_trainer.py + seriea_model_export.py)
Tutte le 8 aree certificate senza issue: split temporale 75/15/10 + purge 30gg,
feature selection train-only, OOF walk-forward senza contaminazione, SMOTE gated coi
pesi corretti, Optuna NLL + cache, meta-learner solo su OOF, calibrazione
isotonic/temperature su val e metriche su holdout calibrato, sistema a tier sensato.
I 13 fix anti-leakage + 4 fix stack del 2026-06-09 sono tutti presenti su master.

### Serving (predict_fixture.py) — falso allarme smentito
Un finding "HIGH" dell'audit (serving ignora il meta-learner) è stato **verificato e
smentito sul codice**: `results[target] = cal_probs` con `cal_probs = predict_ensemble(...)`
(ensemble_trainer.py:1274-1304 usa il meta-learner; la media pesata è solo fallback e
diagnostica `targets_raw`). EV/Kelly/gates corretti; loop di feedback M2 rotto correttamente.

### Sfruttamento tecnologia — verdetto onesto
| Tecnologia | Stato |
|---|---|
| XGBoost / LightGBM (tier SMALL+/MEDIUM+) | ✅ usati |
| Quote di mercato come feature (odds 1x2/OU/BTTS + fair prob) | ✅ usate |
| Optuna (TPE multivariate, cache per-lega) + SMOTE + time-decay | ✅ usati |
| Calibrazione isotonic + temperature scaling | ✅ usata |
| **xG / shots come feature (P7)** | ❌ ASSENTE — la leva più alta rimasta |
| Meta MLP (TensorFlow) | ⚠️ disponibile solo dove c'è TF; LogReg fallback (ok, parità garantita) |
| CatBoost, conformal prediction, monotonic constraints, GPU, RPS come metrica | ❌ assenti (valore atteso basso/medio sul tabulare per-lega) |
| Modello globale cross-lega | ❌ decisione aperta (alternativa ai ~1200 modelli per-lega) |

**Conclusione:** lo stack installato è sfruttato al completo del suo design. Ciò che manca
non è tecnologia "spenta" ma roadmap: (1) xG/quote-feature overhaul, (2) eventuale modello
globale, (3) retrain di produzione col codice onesto (ora possibile in cloud, vedi sotto).

---

## 3) STRUMENTO DI TRAINING CLOUD — NUOVO (questa sessione)

**GitHub Actions → "Retrain ML Models (cloud, all leagues)"** (`.github/workflows/retrain_models.yml`)
- Matrix a N shard (default 6) con round-robin deterministico (`cloud_retrain_shard.py`).
- Stack PINNATO = ambiente di serving del PC (sklearn 1.8.0, lgb 4.6.0, xgb 3.2.0,
  numpy 2.4.6, scipy 1.17.0, Python 3.13) → parità pickle garantita (`requirements-train.txt`).
- SENZA tensorflow (meta resta LogReg ovunque) con check di parità a runtime.
- Upload automatico su Supabase storage + `ai_model_registry`; il PC scarica i nuovi
  modelli da solo alla prima predizione dopo la scadenza cache (24h). Zero lavoro manuale.
- Resumabile: `skip_existing=true` + `max_age_days` → un job interrotto si rilancia e
  riparte da dove era arrivato.
- Budget: repo privato = 2000 min/mese gratis; run completo a freddo ~700-1200 min
  (1229 id in `season_backfill_state`, molti vuoti che falliscono in secondi).

### Fix applicati in questa sessione
1. `retrain_all_leagues.py`: stdout/stderr `errors="replace"` — i print con `→ ✓ ✗`
   crashavano i worker su Windows con output rediretto (bug noto, ora chiuso).
2. `aggiorna_mm_sheets.py`: `MM_COMMISSION` ora importata da
   `Betfair.money_management.DEFAULT_COMMISSION_PCT` (fonte unica, fallback 0.05).
3. Code-review dedicata: anti shell-injection negli input del workflow, validazione
   input leghe, pin requests/httpx, timeout sul job plan.

### Non-issue verificati e chiusi
- Validazione `dynamic_cal.json`: `_apply_calibration` è interamente `.get()`-safe,
  un file malformato degrada in automatico alla tabella statica (nessun fix necessario).
