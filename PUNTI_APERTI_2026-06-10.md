# PUNTI APERTI — ripartenza prossima sessione (salvato 2026-06-10)

> Stato: motore **Poisson** auditato + fixato (codice), motore **ML** auditato + fixato ieri. Branch `fix/ml-audit-blindato`. Nessun resync di produzione eseguito. Doc di riferimento: `POISSON_AUDIT.md`, `Ai Engine/*_RESEARCH.md`, `research_dump.txt`.

---

## 🔴 PRIORITÀ DOMANI (nuove richieste utente)

1. **RILANCIARE la ricerca approfondita per validare DEFINITIVAMENTE entrambi i motori (Poisson + ML).** La deep-research di oggi è stata fermata: risultati parziali in `research_dump.txt`. **Numeri certi già ottenuti** (con fonte):
   - **Half-life ottimale ~360–390 giorni** (Ley, Van de Wiele, Van Eetvelde 2018, arXiv:1705.09575, EPL 2008–2017: Independent Poisson half-period 360gg RPS 0.1954; Bivariate 390gg RPS 0.1953) → **180gg del refactor è troppo corto**; ridurre anche il sovrappeso sulle ultime-5 nel motore attuale. Heuer: la forma intra-stagione è quasi solo rumore.
   - **Bivariate ≈ Independent Poisson** (RPS 0.1953 vs 0.1954) → modellare dipendenza/rho è **marginale, scartare**. τ Dixon-Coles indipendente va bene.
   - **Home-advantage NON costante** (Konaka 2021, arXiv:2101.00457: post-COVID cala, in Germania negativo, in Inghilterra invariato) → serve per-lega/per-squadra, non globale.
   - **Metrica**: RPS (Constantinou & Fenton 2012) + log-loss/ignorance (Wheatcroft 2019).
   - **DA COMPLETARE nella ricerca** (oggi nessun numero primario recuperato): (Q1) xG come predittore + blend ottimale; (Q6) quote di mercato come feature di calibrazione. ⚠️ nota: calibrare sul mercato migliora l'accuratezza ma **azzera l'edge**.
   - **Validazione sui NOSTRI dati**: tradurre le leve vincenti in **ablation backtest sui 71.699 fixture** (Brier/RPS/log-loss reali), una leva alla volta. Questa è la prova "certa" sul nostro sistema, non solo letteratura.

2. **DASHBOARD frequenze mercati per lega** — l'utente spiega meglio domani. (Idea: per ogni lega, frequenze storiche realizzate dei mercati — over/under, BTTS, 1x2, HT — da confrontare con le previsioni dei motori.)

---

## ⚙️ MOTORE POISSON — punti aperti

### A) Resync di produzione NON eseguito (condizione "foglio = calcoli" ancora aperta)
I fix engine/calibrazione cambiano gli output → il foglio mostra ancora i numeri vecchi finché non si rigenera. Catena (richiede OK utente — bloccata da classificatore sicurezza per scrittura di massa su Supabase prod, ~64.125 righe, irreversibile):
1. `python AGGIORNA_CAMPO_db_json_analisi.py --force`
2. `python Prediction/backfill_historical_analysis.py`
3. `python generate_dynamic_cal.py`
4. `python master_backtest.py`  (ROI più basso/onesto atteso)
5. `python -m market_intelligence.pipeline --all`
6. run report giornaliero → foglio coerente.
- Dry-run verificato: nuovo codice gira **0 errori** sul DB reale. Backup calibrazione consigliato prima.
- Consigliato partire da **pilota 1 lega** (`--league 135`) e verificare il foglio, poi full.

### B) Shadow column `db_json_analisi_2` (refactor in parallelo) — APPROVATA come idea, MESSA IN PAUSA
- Obiettivo: far girare il refactor `_AUDIT_2026_05/dc_model.py` in parallelo (modalità ombra, **nessuno ci scommette → strategia intatta**) per confrontarlo 1:1 col motore attuale prima di decidere se sostituirlo.
- **Bloccante tecnico individuato:** il refactor com'è è **probabilmente PEGGIORE** del motore attuale → **butta via gli xG** (oggi pesano 40%) e **perde lo split casa/trasferta** (un solo home-advantage globale). Guadagna solo correzione-avversari (MLE) + time-decay.
- **Decisione:** NON creare la colonna finché il refactor non è portato a **parità di feature** (xG + casa/trasferta + HT direct), altrimenti il confronto è ingiusto. Definire prima la **metrica di vittoria** (RPS/log-loss).
- Query pronta: `ALTER TABLE fixture_predictions ADD COLUMN IF NOT EXISTS db_json_analisi_2 jsonb;` (additiva, reversibile). DDL va fatto in dashboard Supabase o via MCP (il client REST non fa ALTER TABLE).
- Il refactor deve produrre **tutti** i mercati del motore attuale, HT inclusi (oggi fa solo 1x2/OU/BTTS).

### C) Differiti per vincolo "NESSUN CAMBIO DI STRATEGIA" (→ rifinitura finale)
- CLV / line-shopping (unica strategia con edge dimostrato +8.75% nell'audit, ma è strategia nuova).
- Productivize / swap al refactor `dc_model.py` (cambio motore) — vedi punto B.
- DC-MLE congiunto al posto delle forze euristiche.
- Calibrazione isotonic/Platt come modello (fatto solo: monotonia sulla tabella esistente).
- Walk-forward live per-fixture (fatto solo: backtest onesto + shrinkage).
- `market_intelligence/signals.py`: allineare de-vig alla validazione storica (fix parziale peggiora → insieme).
- `aggiorna_mm_sheets.py`: `MM_COMMISSION` hardcoded 5% (script standalone) → agganciare a config se cambia la commissione.
- Backtest AET/PEN: settlement su gol post-supplementari, tenuto identico al live (cambiare in entrambi insieme).

### D) Reality check Poisson
L'audit onesto: **il modello live NON batte la closing line** (ROI −2.5%/−5.5%, CLV ~0). Da tenere presente nella validazione: l'obiettivo è capire se un motore migliorato genera edge reale, non solo previsioni "più belle".

---

## 🤖 MOTORE ML — punti aperti (da sessione 2026-06-09)

- **Decisione architettura**: modello GLOBALE cross-lega (CatBoost) vs ~1200 modelli per-lega isolati (causa numeri assurdi su leghe deboli/amichevoli).
- **Overhaul feature ad alta leva** (la vera leva, non l'architettura): quote di mercato come feature + **xG** (P7 mai costruito) + stagioni adattive per lega + calibrazione per-lega robusta (Platt/IC bootstrap/RPS).
- **Retrain di produzione 363 leghe** col codice corretto (leakage-free + stack completo lightgbm/xgboost/optuna/SMOTE installato) — NON fatto, deciso di farlo **dopo** l'overhaul per non rifare il lavoro. Versione veloce: `aggiorna_modelli.bat` (~6-10h, solo mercati bettable).
- **`betfair_report_manager` end-to-end ML** non validato (rischio sul run giornaliero).
- **Amichevoli/nazionali** (lega 10/666): gestione no-bet di default.
- TensorFlow non installabile su Py 3.13 → meta MLP indisponibile, fallback LogReg (ok).

---

## ✅ FATTO oggi (Poisson) — riferimento
12 file fixati (+~890/−190), audit 80 finding, code-review dopo ogni modifica + re-review APPROVED, py_compile PASS, sanity matematico H+D+A=1.0 sul codice reale. Dettaglio in `POISSON_AUDIT.md`. **Nessun cambio di strategia** (confermato 7/7 verify + code-review).
