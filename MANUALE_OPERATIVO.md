# MANUALE OPERATIVO — Sistema ML Betting
> Ultimo aggiornamento: 2026-03-16
> NON CANCELLARE QUESTO FILE

---

## INDICE
1. [Architettura del sistema](#1-architettura-del-sistema)
2. [Calibrazione ML post-hoc](#2-calibrazione-ml-post-hoc)
3. [Calibrazione Poisson dinamica](#3-calibrazione-poisson-dinamica)
4. [Riallenamento modelli ML](#4-riallenamento-modelli-ml)
5. [Compressione modelli (storage)](#5-compressione-modelli-storage)
6. [Backtest ufficiale](#6-backtest-ufficiale)
7. [Avvio giornaliero](#7-avvio-giornaliero)
8. [Calendario manutenzione](#8-calendario-manutenzione)
9. [Emergenze e reset](#9-emergenze-e-reset)

---

## 1. Architettura del sistema

```
fixture_predictions (DB)
        │
        ├── Poisson model ──► generate_dynamic_cal.py ──► dynamic_cal.json
        │                                                       │
        └── ML models ──────► compute_ml_post_calibration.py   │
                              └──► ml_post_calibration.json    │
                                           │                   │
                                    predict_fixture.py ◄───────┘
                                           │
                                    value_betting.py (EV, Kelly)
                                           │
                                    money_management.py (stake, slots)
                                           │
                                    betfair_report_manager.py (Google Sheets)
```

**File JSON live** (caricati automaticamente ad ogni run di predict_fixture.py):
- `ml_post_calibration.json` — correzioni probabilità ML per-target/classe/bin
- `dynamic_cal.json` — correzioni probabilità Poisson per-lega

---

## 2. Calibrazione ML post-hoc

### Cosa fa
Calcola fattori correttivi `cf = hit_rate_reale / prob_media_predetta` per ogni target
ML × classe × bin di probabilità, basandosi sulle predizioni già salvate in DB vs
risultati effettivi. Corregge bias sistematici senza riallenare.

### Sorgente dati
Tabella `fixture_predictions` — righe con:
- `result_status_short IN ('FT', 'AET', 'PEN')`
- `model_predictions_json NOT NULL`

### Comando
```bash
python compute_ml_post_calibration.py
# oppure con soglia minima campioni diversa (default 20):
python compute_ml_post_calibration.py --min-n 30
```

### Output
`ml_post_calibration.json` nella root del progetto. Viene caricato automaticamente
da `predict_fixture.py` al prossimo run.

### Frequenza consigliata
- **Ora (< 1000 fixture con predictions):** ogni 2-4 settimane
- **Con > 1000 fixture:** ogni mese
- **Trigger pratico:** quando hai accumulato ~200 partite nuove dall'ultimo run

### Come capire se serve ricalibrazione
Apri `ml_post_calibration.json` e guarda `n_active_corrections`.
Se è > 80 e noti che i segnali su un mercato specifico hanno win rate basso,
vale la pena ricalibrate.

### Note importanti
- Bin con N < 20 campioni NON vengono corretti (cf = 1.0 = nessuna modifica)
- Fattori cappati tra 0.3 e 3.0 (conservativo)
- Le correzioni binarie (over/under) mantengono la somma a 1.0 automaticamente
- Le multi-classe (1x2) vengono normalizzate dopo la correzione

---

## 3. Calibrazione Poisson dinamica

### Cosa fa
Calcola fattori correttivi per-lega per il modello Poisson, basandosi su 30k+
fixture storici con analisi JSON e quote reali. Sostituisce la tabella statica
hard-coded con dati reali per ogni lega.

### Sorgente dati
Tabella `fixture_predictions` — righe con `db_json_analisi` e `raw_json_odds` non null.

### Comando
```bash
python generate_dynamic_cal.py
```

### Output
`dynamic_cal.json` nella root del progetto. Caricato automaticamente da
`money_management.py` e dal modello Poisson.

### Frequenza consigliata
- **1-2 volte al mese** (i dati sono già 33k+ fixture, molto stabili)
- Non serve più spesso: il fattore per-lega cambia di frazioni di punto

### Note importanti
- Genera anche `divergence_stats.std` (sigma usato per filtro Z-score hallucination)
- Se una lega ha < 30 partite nel DB, usa il fattore globale come fallback
- Catena di lookup: per-lega → globale-dinamico → tabella statica (fallback)

---

## 4. Riallenamento modelli ML

### Quando riallenare
Riallenare i modelli **non è necessario frequentemente**. Fallo quando:
- Hai accumulato 6+ mesi di nuovi dati dall'ultimo training
- Il backtest mostra degradazione stabile del BSS (Brier Skill Score) < 0.05
- Hai aggiunto nuove feature al dataset (richiede reset completo)
- Vuoi supportare nuove leghe

**NON riallenare** solo perché il win rate è basso in un mese —
la post-hoc calibration è molto più veloce e meno rischiosa.

### Prerequisiti
- Python environment con scikit-learn, numpy, pandas, supabase
- Connessione DB con dati aggiornati (almeno 2 stagioni per lega)
- Storage sufficiente (~350MB per set completo, ~189MB dopo compressione)

### Procedura step-by-step

**Step 1 — Backup opzionale dei modelli esistenti**
```bash
# Copia la cartella models_cache in un posto sicuro prima di procedere
```

**Step 2 — Reset registro modelli (SOLO se riallenamento completo)**
```bash
# ATTENZIONE: questo svuota ai_model_registry su Supabase
python reset_ai_models.py
```

**Step 3 — Avvia riallenamento**
```bash
# Allena tutte le leghe attive in parallelo
python retrain_all_leagues.py

# Oppure solo una lega specifica:
python league_orchestrator.py --league-id 39
```

**Step 4 — Verifica risultati**
```bash
# Controlla il log generato automaticamente
# retrain_log_YYYYMMDD_HHMMSS.txt
```

**Step 5 — Ricalibra immediatamente dopo**
```bash
python compute_ml_post_calibration.py
python generate_dynamic_cal.py
```

### Nota su storage e performance
I modelli con 100 alberi RF e 100 GB raggiungono già convergenza.
Il riallenamento con più dati non cambia il numero di alberi ma aggiorna
i pesi — quindi il file è simile in dimensione.

Se lo storage è un problema, usa `compress_models.py --dry-run` per stimare
il risparmio PRIMA di applicare (vedi sezione 5).

---

## 5. Compressione modelli (storage)

### Cosa fa
Dimezza il numero di alberi in RF e GB nei modelli PKL.GZ esistenti.
Nessun retraining. Risparmio stimato: ~46% (349MB → 189MB).

### Performance loss (dati verificati 16/03/2026)
| Tipo modello | Diff MAX | Diff MEDIA | Accettabile? |
|-------------|---------|-----------|-------------|
| Leghe piccole (4 feature) | 1.0% | 0.5% | ✅ Sì |
| Leghe grandi (35 feature) | 7.4% | 1.9% | ✅ Sì (media conta) |
| Target binari (over/under) | 6.1% | 2.0% | ✅ Sì |
| Target multi-classe (8+) | 10.1% | 1.4% | ✅ Sì (media conta) |

**La differenza MAX è su sample casuali estremi, non su partite reali.
La differenza MEDIA (1-2%) è quella rilevante per il ROI.**

### Comandi
```bash
# Prima: stima senza modificare nulla
python compress_models.py --dry-run

# Poi: applica (IRREVERSIBILE senza backup)
python compress_models.py

# Solo cartella specifica:
python compress_models.py --dir downloaded
python compress_models.py --dir root
```

### Quando farlo
Solo DOPO che il sistema ha dimostrato stabilità (almeno 3 mesi di live).
Farlo dopo ogni riallenamento completo per mantenere storage ottimale.

---

## 6. Backtest ufficiale

### Comandi
```bash
# Backtest completo (Poisson + ML, ultimi 2 anni)
python master_backtest.py

# Solo Poisson:
python master_backtest.py --mode poisson

# Solo ML:
python master_backtest.py --mode ml

# Con date specifiche:
python master_backtest.py --from 2025-01-01 --to 2025-12-31
```

### Output generato
- `backtest_report_YYYYMMDD_HHMMSS.md` — report completo con statistiche
- `backtest_results_YYYYMMDD_HHMMSS.csv` — dati grezzi per analisi

### Interpretazione risultati
| Metrica | Soglia minima | Buono |
|---------|-------------|-------|
| ROI | > -3% (fase early) | > +3% |
| Win Rate | > break-even | > 55% (odds ~2.0) |
| Sharpe ratio | > 0.1 | > 0.5 |
| BSS ML | > 0.05 | > 0.15 |

**Nota (importante):** Il backtest attuale è su dati storici parziali.
Con < 300 scommesse i valori oscillano molto — non prendere decisioni
basate su singoli run. Valuta trend su 3+ mesi.

### Gestione file output
Tieni solo **l'ultimo report** — cancella i precedenti per non appesantire il repo.
```bash
# Tieni solo l'ultimo:
# backtest_report_YYYYMMDD_HHMMSS.md (più recente)
# backtest_results_YYYYMMDD_HHMMSS.csv (più recente)
```

---

## 7. Avvio giornaliero

### Script automatici (già configurati)
```bash
# Aggiorna dati, lancia predizioni, aggiorna Google Sheets
aggiorna_report.bat

# Solo aggiornamento fogli (senza nuove predizioni)
aggiorna_solo_fogli.bat

# Aggiorna modelli ML (predizioni + training se necessario)
aggiorna_modelli.bat
```

### Ordine manuale se serve
```bash
# 1. Aggiorna dati ieri (risultati, stats)
python daily_yesterday_backfill.py

# 2. Lancia predizioni di oggi
python Prediction/today_predictions_backfill.py

# 3. Risolvi scommesse pendenti e aggiorna Sheets
python Betfair/betfair_report_manager.py
```

---

## 8. Calendario manutenzione

| Frequenza | Operazione | Comando |
|-----------|-----------|---------|
| **Ogni giorno** | Dati + predizioni + Sheets | `aggiorna_report.bat` |
| **Ogni 2-4 settimane** | Ricalibrazione ML | `python compute_ml_post_calibration.py` |
| **Ogni mese** | Ricalibrazione Poisson | `python generate_dynamic_cal.py` |
| **Ogni 6 mesi** | Riallenamento completo | `python retrain_all_leagues.py` |
| **Dopo ogni training** | Comprimi modelli | `python compress_models.py` |
| **Dopo ogni calibrazione** | Verifica backtest | `python master_backtest.py` |

### Checklist mensile consigliata
```
[ ] python compute_ml_post_calibration.py  → aggiorna ml_post_calibration.json
[ ] python generate_dynamic_cal.py         → aggiorna dynamic_cal.json
[ ] python master_backtest.py              → verifica trend ROI
[ ] Cancella retrain_log_*.txt vecchi      → pulizia storage
[ ] Cancella backtest_report_* vecchi      → tieni solo ultimo
```

---

## 9. Emergenze e reset

### Se le predizioni ML sembrano assurde
```bash
# Rigenera calibrazione ML da zero
python compute_ml_post_calibration.py --min-n 10

# Se persiste, elimina la calibrazione (torna a probabilità raw)
# → cancella ml_post_calibration.json
```

### Se vuoi resettare completamente il sistema ML
```bash
# ATTENZIONE: operazione distruttiva irreversibile su Supabase
python reset_ai_models.py    # svuota ai_model_registry
python cleanup_models.py     # svuota modelli dal DB
# Poi riallenare da zero con retrain_all_leagues.py
```

### Se il money management è bloccato
```bash
# Visualizza stato corrente
cat Betfair/money_management_state.json

# Log storico scommesse
cat Betfair/mm_history.json

# Reset stato (usa solo se sicuro)
python Betfair/cleanup_reset.py
```

### Se dynamic_cal.json è corrotto
```bash
# Rigenera
python generate_dynamic_cal.py

# In attesa, il sistema usa automaticamente la tabella statica di fallback
# (nessun downtime)
```

---

*Fine documento — versione 1.0*
