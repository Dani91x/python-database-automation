# AUDIT FORENSE — MOTORE POISSON / Dixon-Coles

**Data audit:** 2026-06-10 · **Tipo:** read-only (43 agenti, 83 finding → 80 confermati, 3 refutati)
**Motore in produzione:** `Prediction/today_predictions_backfill.py` → `compute_db_json_analisi()` (righe 777-1060), model id `poisson_xg_hybrid_dc`.

> **VINCOLO FIX (sessione 2026-06-10):** fixare OGNI punto **SENZA cambiare strategia**. Mantenere l'**attuale** motore Poisson (NON sostituirlo col refactor `_AUDIT_2026_05/dc_model.py`, NON implementare CLV/line-shopping). Rendere ogni riga coerente, cablata, e far combaciare i fogli Google con i calcoli.

---

## DATA-FLOW (certificato)

`fixture_predictions` (Supabase) → `compute_db_json_analisi()` (λ casa/trasferta da forze euristiche + xG blend → matrice gol + Dixon-Coles τ → mercati) → colonna `db_json_analisi` (+ `ht_predictions`) → `betfair_report_manager.py` (legge la colonna, calibra, popola Google Sheet "Segnali") → `money_management.py::SlotManager.process_signals()` (EV/Kelly/commissione → stake) → `aggiorna_mm_sheets.py` (foglio strategia MM). Calibrazione: `generate_dynamic_cal.py` → `dynamic_cal.json` → consumato live da `money_management._apply_calibration()`.

---

## VERDETTO SULLE 6 DOMANDE (pre-fix)

| # | Domanda | Verdetto pre-fix |
|---|---------|------------------|
| 1 | Matematica verificata e validata? | ⚠️ formule core OK, calibrazione metodologica da sistemare |
| 2 | Ogni riga coerente e cablata? | ⚠️ nessun errore strutturale, incoerenze di wiring |
| 3 | Migliore soluzione possibile? | ❌ (refactor migliore esiste ma è dead code — *fuori scope: no cambio strategia*) |
| 4 | Foglio corrisponde alla realtà? | ❌ due edge incoerenti per riga, commissione hardcoded |
| 5 | Tecnologia al massimo? | ❌ scipy/numpy ignorati, max_goals troncato |
| 6 | Ogni calcolo Poisson corretto? | ✅ calcoli core certificati corretti |

---

## CERTIFICATO CORRETTO (nessun fix necessario)

- PMF Poisson `e^(−λ)λ^k/k!` (live + refactor) · Correzione Dixon-Coles τ (valore/segno/4 celle, ρ=−0.13 canonico)
- Matrice 7×7 + normalizzazione + derivazione 1x2/OU/BTTS/HT (riprodotta: H+D+A=1.000000)
- EV / Kelly frazionario / commissione Betfair / P&L (money_management + master_backtest), commissione solo su net winnings
- Formula edge Segnali = EV money management (identiche) · gestione unità prob (no errore 100×)
- P&L foglio strategia MM (`aggiorna_mm_sheets.py:35-36,208-211`) — commissione nettata una volta sola
- Scrittura DB verbatim (`AGGIORNA_CAMPO:283-292`) · idempotenza/checkpoint · xG effettivamente sfruttato (η=0.6)

---

## FINDING DA FIXARE (80 confermati) — vedi stato fix in fondo

### IN SCOPE (fix ora — no cambio strategia)
- **CRITICAL** calibrazione in-sample → la manifestazione dannosa (edge gonfiato che SI VEDE) è nel backtest/validazione: rendere il **backtest out-of-sample/onesto** + aggiungere **shrinkage empirical-Bayes** alla generazione tabella. La calibrazione live (tabella storica su fixture future) resta, ma robusta.
- **HIGH** `calibration_analysis.py:488` `math.sqrt` senza `import math` (NameError) + doppio writer di `dynamic_cal.json` → fonte unica = `generate_dynamic_cal.py`.
- **HIGH** `master_backtest.py` non fedele al live: selezione max-EV vs `edge×√prob`, solo static cal, salta i safety filter → allineare al live (non cambia strategia, la rende fedele).
- **HIGH** calibrazione per-lega `min_n=15` + cap [0.2,3.0] senza shrinkage → alzare min_n + shrinkage; eliminare path `min_per_bin=5`.
- **medium** foglio mostra due edge incoerenti (raw vs calibrato) + `calc_edge` hardcoda `commission=0.05` → leggere `commission_pct` da config; coerenza colonne.
- **medium** calibrazione stale + solo 8 mercati su 16 calibrabili dinamicamente → estendere `MARKET_CONFIG` + logica HT in `check_result`.
- **medium** write silenziosa a zero righe (`AGGIORNA_CAMPO:178-182`) → check `resp.data`.
- **medium** `market_intelligence/edge_scorer.py` no de-vig + pesi w_ml/w_xg caricati mai applicati + `w_total` dead → de-vig + wiring/rimozione dead.
- **medium** AET/PEN regolati su gol post-supplementari nel backtest → verificare campo, escludere/usare 90-min.
- **low** calibratore per-bin non-monotono → **forzare monotonia** sui fattori (mantiene formato tabella, no redesign).
- **low** vari: U2.5 mai mostrato sul foglio (ma puntato), header duplicati, xG selector substring→exact, goals None→0, griglia 6→10 goal, Brier/logloss + rename "Sharpe", failed_ids/None, MI cache stale gate, signals bookmaker selector, calibration_source label, ht backfill FT filter, BSS anti-doppio guard, CLV implied doc, devig.py Shin (codice audit).
- **info/tech** engine usa pure-Python `math` → `scipy.stats.poisson.pmf` + `numpy` (numeri identici, più sicuro/veloce).

### DIFFERITO — CAMBIO DI STRATEGIA (NON fatto per vincolo utente)
- ❌ Implementare CLV / line-shopping (nuova strategia di esecuzione).
- ❌ Produttivizzare / passare al refactor `_AUDIT_2026_05/dc_model.py` (cambio motore/architettura).
- ❌ DC-MLE congiunto al posto delle forze euristiche (cambia il cuore del modello).
- ❌ Sostituire l'architettura calibrazione per-bin con isotonic/Platt come modello (redesign) — *fatto invece il fix minimo: monotonia sui fattori esistenti*.
- ❌ Restructure calibrazione LIVE in walk-forward per-fixture (redesign) — *fatto invece: backtest onesto + shrinkage*.
- Tutti rinviati alla **rifinitura finale** (ottimizzazione congiunta dei due motori).

---

## STATO FIX — COMPLETATO 2026-06-10

**Metodo:** workflow multi-agente su gruppi di file disgiunti (no conflitti) + verifica adversariale per gruppo + **code-review dedicato (`code-reviewer`) su ogni modifica** + re-review dei follow-up + sanity numerico sul codice reale. Tutti i file `py_compile` PASS. **Nessun cambio di strategia** (confermato da 7/7 verifiche + 6 code-review). Branch `fix/ml-audit-blindato`, NON committato.

### Fixato (12 file, +907/−194)

| File | Fix principali |
|------|----------------|
| `Prediction/today_predictions_backfill.py` | PMF→scipy.stats.poisson + numpy (overflow-safe, numeri identici 1e-16); max_goals 6→10; xG selector exact-match+mean; baseline xG di lega; esclusi gol None; annotazione tuple; guard FK None |
| `Prediction/backfill_historical_analysis.py` | filtro fixture finite (FT/AET/PEN) |
| `generate_dynamic_cal.py` | shrinkage empirical-Bayes verso global (n/(n+75)); min_n 15→30; monotonia forzata; +7 mercati (O15/U15/O35/U35/HT_H/HT_D/HT_A); bin global low-N omessi→fallthrough a static |
| `calibration_analysis.py` | `import math` (NameError); non sovrascrive più dynamic_cal.json (→ diagnostic); +7 mercati sincronizzati |
| `Betfair/betfair_report_manager.py` | commissione da config (no hardcode 5%); colonne Under 2.5; header disambiguati raw/calibrato + Pois/ML; commento NUM_COLS |
| `Betfair/money_management.py` | guardia anti-doppio BSS; doc definizione CLV (solo commenti, zero logica) |
| `master_backtest.py` | selezione edge×√prob (=live); catena dynamic_cal by_league→global→static; safety filter (Z-score+trust); Brier/log-loss/BSS; flag USE_DYNAMIC_CAL/USE_HALLUCINATION_FILTER; rename "Sharpe" |
| `AGGIORNA_CAMPO_db_json_analisi.py` | check write a 0 righe (no falso "written"); failed_ids int+OverflowError |
| `market_intelligence/edge_scorer.py` | de-vig per gruppo; calibration_source='league'; hard-gate cache stale; rimosso w_total dead; cache-age robusto; assert _DEVIG_GROUPS |
| `market_intelligence/signals.py` | selettore Betfair coerente (no bookmakers[0]) |
| `market_intelligence/calibration.py`, `mi_config.py` | doc divergenza assi + hard-gate |
| `_AUDIT_2026_05/devig.py` | Shin canonico + brentq (codice audit, non-prod) |

### Verifica matematica
Sanity sul codice **reale** del motore: `H+D+A=1.0000000000` esatto per λ∈{(1.5,1.2),(0.4,0.3),(2.8,2.1),(0.05,3.5)}; grid sum=1; equivalenza scipy↔hand-rolled 1e-16.

### DIFFERITO (cambio di strategia / rifinitura finale — NON fatto per vincolo)
- CLV / line-shopping (nuova strategia di esecuzione).
- Productivize / swap al refactor `_AUDIT_2026_05/dc_model.py` (cambio motore).
- DC-MLE congiunto al posto delle forze euristiche.
- Architettura calibrazione isotonic/Platt come modello (fatta invece la monotonia sul formato tabella).
- Walk-forward calibrazione LIVE per-fixture (fatto invece: backtest onesto + shrinkage).
- `market_intelligence/signals.py` allineamento de-vig validazione storica (fix parziale peggiora — va fatto insieme alla validazione, rinviato).
- `aggiorna_mm_sheets.py` MM_COMMISSION hardcoded (modulo standalone senza SlotManager — coerente col 5% attuale).

### ⚠️ RESYNC OPERATIVO RICHIESTO (i fix engine/calibrazione cambiano gli output → il foglio deve essere riallineato)
1. `python AGGIORNA_CAMPO_db_json_analisi.py --force` (rigenera db_json_analisi)
2. `python Prediction/backfill_historical_analysis.py` (rigenera ht_predictions)
3. `python generate_dynamic_cal.py` (rigenera dynamic_cal.json sui nuovi output + 7 mercati)
4. `python master_backtest.py` (metriche oneste — ROI più basso/realistico atteso)
5. (MI) `python -m market_intelligence.pipeline --all` (sblocca hard-gate cache + de-vig)

Finché non si rilancia 1-3, il foglio mostra ancora i numeri del modello vecchio.
