# AI Engine Project Plan - Best Practices & Automation

## Obiettivo
Costruire un sistema affidabile e automatizzato che, ogni giorno, produce analisi e report chiari per l’utente finale, integrando:
- pronostici API (api-football)
- odds pre-partita
- previsioni modelli ML
- report testuale finale (AI)

Il sistema deve essere scalabile e operare in automatico sulle leghe “complete”.

---

## Principi chiave (non negoziabili)
- **DB-first**: niente CSV in produzione.
- **Ripetibilità**: pipeline automatica, zero interventi manuali.
- **Affidabilità**: nessun consiglio se copertura dati insufficiente.
- **Tracciabilità**: ogni output deve riportare dati usati e copertura.
- **Separazione training/prediction**: training schedulato, prediction on demand.

---

## Architettura pipeline (batch giornaliero)

### 1) Ingest mattutino (predictions + odds)
- Script: `Prediction/today_predictions_backfill.py`
- Output in `fixture_predictions`:
  - `raw_json` (predictions API)
  - `raw_json_odds` (odds pre-match)
  - colonne “promosse” (winner, percent, goals_line, ecc)

### 2) Pre-calcolo ML (modelli)
- Script: `Ai Engine/ai_engine/seriea_model_export.py` (da generalizzare a tutte le leghe)
- Output:
  - Modelli salvati (bucket) + registry DB
  - Mediane feature salvate nel modello

### 3) Predizione giornaliera
- Script: `Ai Engine/ai_engine/predict_fixture.py`
- Per ogni fixture:
  - carica modelli
  - genera probabilità target
  - salva output su DB (JSON o colonne dedicate)

### 4) Report AI
- Generato automaticamente con:
  - predictions API
  - predictions ML
  - odds
  - copertura
- Output: `report_text` su DB

---

## Regole di Copertura (gating)

**Non generare consigli se:**
- Copertura feature < 60%
- Partite storiche minime < 10 per squadra
- Dati chiave mancanti (xG, team stats, ecc) oltre soglia

**Se dati insufficienti:**
- `analysis_status = partial`
- `analysis_notes` descrive cosa manca

---

## Strategia Training (best practice)

**Modelli per lega** (non mischiare campionati).

**Approccio multi-finestra:**
- Long: tutto storico disponibile
- Mid: ultimi 3–5 anni
- Short: ultimi 1–2 anni

**Opzione consigliata**: ensemble dei 3 modelli.

**Aggiornamento incrementale:**
- Retrain giornaliero o settimanale
- Salvare ultima partita processata per lega

---

## Scelta Leghe

**Fase 1 (ora)**
- Solo leghe con copertura completa (events/team_stats/player_stats/odds).

**Fase 2 (più avanti)**
- Leghe incomplete ma con dati minimi
- Segnalare in report “copertura parziale”

---

## Struttura dati consigliata (fixture_predictions)

Colonne minime:
- `raw_json` (predictions API)
- `raw_json_odds` (odds pre-match)
- `model_predictions_json` (output modelli)
- `analysis_status` (ok/partial/no_data)
- `analysis_notes`
- `report_text`

---

## Metriche e Validazione

**Sempre obbligatorie:**
- Accuracy, F1, LogLoss, Brier
- Profit Balance (odds)

**Monitoraggio:**
- Salva metriche in DB per lega e target
- Alert se metriche scendono sotto soglia

---

## Interpretabilità

Implementare:
- Feature importance (RF)
- Coefficienti (Logistic)
- Rules (Decision tree)

Uso:
- Non per l’utente finale
- Per debug e miglioramento modello

---

## Automatizzazione (operativa)

**Daily schedule consigliata:**
1. 07:00 UTC → prediction API + odds
2. 07:30 UTC → ML prediction
3. 08:00 UTC → report AI

---

## Controlli di qualità

- Se `raw_json` o `raw_json_odds` mancano → report parziale
- Se `model_predictions` assenti → segnalare
- Se database incompleto → skip

---

## Domande aperte (da definire)

1. Vuoi salvare `model_predictions` come JSON o colonne singole?
2. Vuoi un job automatico di retraining settimanale o giornaliero?
3. Preferisci AI report in tabella o su file + link?
4. Quali soglie minime di copertura vuoi applicare (es. 60%, 70%)?
5. Quali leghe consideriamo “complete” per fase 1?

---

## Prossimi Step

- Definire schema finale DB
- Implementare training multi-finestra
- Automatizzare batch completo
- Validare output su 1–2 leghe pilota

