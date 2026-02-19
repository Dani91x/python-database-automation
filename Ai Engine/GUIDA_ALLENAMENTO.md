# 🎯 Guida Allenamento Modelli AI

> Documento semplice per allenare, aggiornare e gestire i modelli dell'AI Engine.
> Non serve essere tecnici per seguire questa guida.

---

## 📌 Concetti Base

- **Lega** = un campionato (es. Serie A = `135`, Premier League = `39`)
- **Modello** = il "cervello" che impara dai dati storici per prevedere le partite
- **Allenamento** = addestrare il modello con i dati delle partite già giocate
- **Ogni lega ha il suo modello** — non esiste un unico modello universale

---

## 🏗️ Prerequisiti

Prima di allenare un modello, servono dati nel database:

| Dato | Tabella | Minimo |
|------|---------|--------|
| Partite completate | `matches` | ≥ 150 per lega |
| Statistiche squadre | `match_team_stats` | ≥ 50% delle partite |
| Eventi (gol, cartellini) | `match_events` | ≥ 50% delle partite |
| Quote pre-match | `match_odds` | ≥ 70% delle partite |
| Classifica | `standings` | ≥ 1 stagione |

> **Come verificare?** Lancia il comando di audit (vedi sotto).

---

## 🔧 Tutti i Comandi

> ⚠️ Tutti i comandi vanno eseguiti dalla cartella `Ai Engine/`.

### 1) 🔍 Verificare i dati disponibili (FARE PRIMA)

```bash
python ai_engine/audit_nulls.py 135
```

Questo genera un report che mostra quali dati mancano per la lega 135.
Il report viene salvato in `Ai Engine/reports/audit_nulls_league_135.md`.

**Quando usarlo:** Prima di allenare, per capire se ci sono abbastanza dati.

---

### 2) 🧠 Allenare il Modello (COMANDO PRINCIPALE)

#### Per la Serie A (league_id = 135):
```bash
python ai_engine/seriea_model_export.py 135
```

#### Per la Premier League (league_id = 39):
```bash
python ai_engine/seriea_model_export.py 39
```

#### Per qualsiasi altra lega:
```bash
python ai_engine/seriea_model_export.py <LEAGUE_ID>
```

#### Con più stagioni di dati (default 3):
```bash
python ai_engine/seriea_model_export.py 135 5
```

**Cosa fa:**
1. Scarica i dati storici dal database
2. Costruisce le feature (statistiche, forma, quote)
3. Allena 3 modelli + 1 meta-modello (stacking ensemble)
4. Calcola Brier score ed ECE (metriche di affidabilità)
5. Salva il modello su Supabase (bucket `ai-models`)
6. Registra il modello nella tabella `ai_model_registry`

**Output:** Stampa a schermo per ogni target allenato:
```
Training ensemble models for league 135...
  target_1x2: acc=0.581, brier=0.241, ece=0.062
  target_btts: acc=0.672, brier=0.198, ece=0.045
  ...
Training complete. 8 models trained.
```

**Durata:** ~2-5 minuti per lega (dipende dalla quantità di dati).

---

### 3) 🔮 Fare una Predizione

```bash
python ai_engine/predict_fixture.py <FIXTURE_ID>
```

#### Per salvare il risultato nel database:
```bash
python ai_engine/predict_fixture.py <FIXTURE_ID> --store
```

**Cosa fa:**
1. Carica il modello allenato per la lega della partita
2. Costruisce le feature per la partita
3. Produce probabilità per ogni mercato (1X2, Over/Under, BTTS, ecc.)
4. Applica i 4 Gate di affidabilità
5. Genera segnali di valore (value bets)
6. Se `--store`: scrive il risultato nella colonna `model_predictions_json`

---

### 4) 📊 Backtest (Verificare che il Modello Funziona)

```bash
python ai_engine/backtest.py 135
```

#### Con parametri personalizzati:
```bash
python ai_engine/backtest.py 135 3 5
```
(3 stagioni, 5 fold di validazione)

**Cosa fa:**
- Simula il comportamento del modello su partite passate
- Usa **quote reali** dalla tabella `match_odds`
- Calcola ROI, Win Rate, Sharpe Ratio, Brier Score
- Confronta con la baseline (scelta casuale)

**Output:** Report in `Ai Engine/reports/backtest_league_135.md`.

---

### 5) 📋 Report Giornaliero

```bash
python ai_engine/runner.py
```

**Cosa fa:** Genera previsioni per tutte le partite del giorno e crea un report leggibile.

---

### 6) 📄 Report Singola Partita

```bash
python ai_engine/generate_fixture_report.py <FIXTURE_ID>
```

---

## 📅 Quando Allenare / Riallenare

| Situazione | Cosa fare | Comando |
|------------|-----------|---------|
| **Prima volta per una lega** | Allenare da zero | `python ai_engine/seriea_model_export.py <ID>` |
| **Nuova stagione iniziata** | Riallenare con più dati | `python ai_engine/seriea_model_export.py <ID>` |
| **Ogni 4-6 settimane** | Riallenare per aggiornare | `python ai_engine/seriea_model_export.py <ID>` |
| **Dopo modifiche al codice** | Riallenare obbligatorio | `python ai_engine/seriea_model_export.py <ID>` |
| **Backtest con ROI negativo** | Analizzare e riallenare | Prima `backtest.py`, poi `seriea_model_export.py` |

### ⚠️ Riallenamento Obbligatorio Adesso

Dopo le modifiche fatte oggi (calibrazione Brier/ECE, Gate 4), **devi riallenare il modello della Serie A**:

```bash
python ai_engine/seriea_model_export.py 135
```

Il modello vecchio non contiene le metriche di calibrazione → il Gate 4 bloccherebbe tutte le scommesse.

---

## 🗺️ Leghe Supportate (ID comuni)

| Lega | League ID |
|------|-----------|
| Serie A 🇮🇹 | `135` |
| Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿 | `39` |
| La Liga 🇪🇸 | `140` |
| Bundesliga 🇩🇪 | `78` |
| Ligue 1 🇫🇷 | `61` |
| Serie B 🇮🇹 | `136` |
| Eredivisie 🇳🇱 | `88` |
| Liga Portugal 🇵🇹 | `94` |

> Per aggiungere una lega: basta avere i dati nel database e lanciare il comando di allenamento.

---

## ✅ Checklist: Aggiungere una Nuova Lega

1. ✅ Popolare il database con i dati della lega (matches, stats, events, odds)
2. ✅ Verificare i dati: `python ai_engine/audit_nulls.py <LEAGUE_ID>`
3. ✅ Allenare il modello: `python ai_engine/seriea_model_export.py <LEAGUE_ID>`
4. ✅ Verificare la qualità: `python ai_engine/backtest.py <LEAGUE_ID>`
5. ✅ Se backtest OK → iniziare a usare: `python ai_engine/predict_fixture.py <ID> --store`

---

## ❓ FAQ

**D: Quanto tempo ci vuole per allenare?**
R: 2-5 minuti per lega. Dipende dalla quantità di dati.

**D: Posso allenare più leghe insieme?**
R: Non c'è un comando unico, ma puoi lanciare i comandi uno dopo l'altro.

**D: Il modello migliora con più dati?**
R: Sì, fino a un certo punto. Con 3+ stagioni complete e buone statistiche, il modello raggiunge il suo potenziale.

**D: Come capisco se un modello è buono?**
R: Guarda il backtest. ROI positivo, Brier < 0.30, e accuracy superiore alla baseline = modello buono.

**D: Posso rompere qualcosa?**
R: No. L'allenamento sovrascrive il modello vecchio, ma i dati nel database rimangono intatti. Puoi sempre riallenare.
