# 🏦 ROADMAP DEFINITIVA — Da Paper Trading a Fondo di Investimento

## 📋 STATO ATTUALE (Cosa abbiamo)

### Infrastruttura Dati
- **Database Supabase** con 50+ leghe, storico completo (matches, standings, top scorers, injuries)
- **API-Football** per dati real-time (fixture, statistiche, xG)
- **Betfair Exchange API** per quote live su 6 mercati (1X2, O/U 2.5, BTTS, HT O0.5)
- Pipeline automatizzata: `daily_yesterday_backfill.py` → `today_predictions_backfill.py` → `betfair_report_manager.py`

### Motore Predittivo (Poisson/xG Hybrid)
- Modello Dixon-Poisson con Shrinkage Bayesiano (k=8)
- Blend xG/Gol Reali (60/40%) su finestre 5/10/15 partite
- 6 mercati: Home Win, Draw, Away Win, HT Over 0.5, Over 2.5, BTTS
- Blacklist dinamica leghe tossiche basata su P&L storico

### Money Management (Quant Fund v2)
- Edge Scanner Multi-Mercato con Confidence-Adjusted Score (Edge × √Prob)
- Kelly Criterion Frazionato (configurabile 1/4, 1/3, 1/2)
- Filtri: Edge minimo, Prob minima, dati minimi per squadra
- Dashboard Google Sheets con dropdown configurabili
- Report multi-giorno con risoluzione risultati automatica dal DB

### Paper Trading
- Test 3 giorni (Ven-Dom) con 1000€ virtuali
- ~22 selezioni/giorno su 90 eventi (24% acceptance rate)
- Risoluzione automatica risultati al lancio successivo

---

## 🚀 FASI EVOLUTIVE (Ordinate per Impatto/Priorità)

---

### FASE 1: CALIBRAZIONE E VALIDAZIONE (Prerequisito per investire)
**Tempo stimato: 1-2 settimane di raccolta dati**

#### 1.1 — Backtest Storico Automatizzato
Creare uno script che:
- Prende gli ultimi 3-6 mesi di partite già giocate dal DB
- Per ognuna, calcola le probabilità con `compute_db_json_analisi` (come se fosse pre-match)
- Confronta le probabilità con il risultato reale
- Produce un **Calibration Report**:
  - Quando il modello dice 70%, vince davvero il 70%? (Calibration Curve)
  - Brier Score (misura standard per calibrazione probabilistica)
  - Reliability Diagram per ogni mercato

#### 1.2 — Ottimizzazione Parametri Edge/Prob
Usare il backtest per trovare i parametri ottimali:
- Edge minimo: 3%, 5%, 7%, 10% → quale massimizza il Yield?
- Prob minima: 50%, 55%, 60%, 65% → quale massimizza il Win Rate?
- Kelly Fraction: 1/4, 1/3, 1/2 → quale massimizza il Sharpe Ratio?

#### 1.3 — Confidence Interval sulle Probabilità
Aggiungere all'output del modello l'**intervallo di confidenza**:
- Se `p = 0.72 ± 0.08`, il range è 64-80%
- Se l'intervallo è troppo largo → dati insufficienti, ridurre lo stake
- Questo permette di pesare la "certezza" della stima nel Kelly

---

### FASE 2: AI ENGINE (Machine Learning)
**Tempo stimato: 2-4 settimane**

#### 2.1 — Feature Engineering
Oltre ai dati Poisson attuali, aggiungere:
- **Form recente**: punti ultimi 5 match, gol ultimi 3, trend (crescente/decrescente)
- **Head-to-Head**: storico scontri diretti (ultimi 5-10)
- **Fattore campo**: rendimento specifico casa vs trasferta (non solo media lega)
- **Infortuni/Squalifiche**: impatto stimato sui lambda (giocatori chiave assenti)
- **Congestion**: giorni di riposo dal match precedente
- **Standings**: posizione classifica, distanza dalla zona retrocessione/promozione
- **Momentum**: EWMA (media mobile esponenziale) dei gol

#### 2.2 — Modello Ensemble
Architettura proposta:
```
Input Features (30+) → [XGBoost] → prob_xgb
                      → [LightGBM] → prob_lgbm  → MEDIA PESATA → prob_finale
Poisson Model        → prob_poisson          ↗
```
- Ensemble di 3 modelli: XGBoost + LightGBM + Poisson (attuale)
- Cross-validation Walk-Forward (no data leakage su dati temporali)
- Calibrazione isotonica (Platt scaling) per garantire calibrazione

#### 2.3 — Market-Specific Models
Un modello separato per ogni mercato (non un modello generico):
- **1X2**: Focus su standings, form, H2H
- **Over 2.5**: Focus su lambda, trend gol, stile di gioco
- **BTTS**: Focus su difese, media gol subiti
- **HT Over 0.5**: Focus su aggressività primo tempo, dati halftime

---

### FASE 3: AUTOMAZIONE COMPLETA
**Tempo stimato: 1-2 settimane**

#### 3.1 — Auto-Scheduling
- Script che gira automaticamente ogni 2 ore (Task Scheduler Windows / cron)
- Aggiorna quote Betfair in tempo reale
- Risolve risultati completati
- Ricalcola Edge con quote aggiornate

#### 3.2 — Piazzamento Automatico Scommesse
- Integrazione con Betfair API per piazzare ordini a mercato
- **Modalità "Semi-Auto"**: il sistema propone, l'utente conferma con un click
- **Modalità "Full-Auto"**: piazzamento automatico con guardie di sicurezza:
  - Stop Loss giornaliero (-10% bankroll)
  - Take Profit giornaliero (150€ o configurabile)
  - Max stake singolo (3% bankroll)
  - Max esposizione totale (30% bankroll in scommesse PENDING)
  - Cooldown dopo 3 perdite consecutive (pausa 30min)

#### 3.3 — Filtro Liquidità Betfair
- Leggere `totalMatched` da ogni mercato Betfair
- Scartare mercati con `totalMatched < 5.000€`
- Calcolare lo spread bid-ask (Back vs Lay) → scartare se > 3 tick

#### 3.4 — Gestione Multi-Sessione
- Partite alle 15:00, 17:30, 20:45 → 3 sessioni separate
- Ricalcolo Edge per ogni sessione (le quote cambiano)
- Ottimizzazione bankroll: allocare budget per sessione

---

### FASE 4: RISK MANAGEMENT AVANZATO
**Tempo stimato: 1 settimana**

#### 4.1 — Drawdown Protection
- **Max Drawdown settimanale**: se perdi >15% del bankroll in 7 giorni → pausa automatica
- **Var (Value at Risk)**: calcolo Monte Carlo del rischio massimo giornaliero
- **Bankroll Progression**: Kelly ricalcolato ad ogni sessione sul bankroll attuale (non fisso)

#### 4.2 — Correlazione Scommesse
- Se punti "Home Win" su Juventus e "Over 2.5" su Juventus, le scommesse sono correlate
- Implementare un **Correlation Filter**: max 1 scommessa per evento
- Portfolio diversification: max 5 scommesse sulla stessa lega

#### 4.3 — Sharpe Ratio Tracking
- Calcolo giornaliero/settimanale/mensile del Sharpe Ratio
- Se il Sharpe scende sotto 1.0 → ridurre gli stake del 50%
- Se il Sharpe resta sopra 2.0 → aumentare gradualmente Kelly fraction

---

### FASE 5: SCALABILITÀ E DIVERSIFICAZIONE
**Tempo stimato: ongoing**

#### 5.1 — Espansione Leghe
- Aggiungere leghe minori con quote più inefficienti (più Edge)
- Leghe target: Turchia, Grecia, Norvegia, Svezia, MLS, J-League
- Attenzione: verificare che il modello mantenga la calibrazione su nuove leghe

#### 5.2 — Nuovi Mercati
- **Asian Handicap**: migliore liquidità su Betfair per i favoriti
- **Correct Score**: quote alte, Edge potenzialmente enorme con Poisson
- **Half-Time/Full-Time**: combinazioni con buon rapporto rischio/rendimento
- **Goal Range**: Under 0.5, Over 1.5, Over 3.5

#### 5.3 — Multi-Exchange
- Affiancare Betfair con **Smarkets** e **Betdaq** per:
  - Arbitraggio tra exchange (stesso evento, quote diverse)
  - Maggiore liquidità sulle partite minori
  - Rischio di controparte diversificato

#### 5.4 — Bankroll Scaling
Piano crescita progressiva:
| Bankroll | Kelly | Max Stake | Target/mese | Yield atteso |
|----------|-------|-----------|-------------|----------|
| €1.000 | 1/4 | €30 | €800-1.500 | 5-8% |
| €5.000 | 1/4 | €150 | €3.000-6.000 | 5-8% |
| €10.000 | 1/5 | €200 | €5.000-10.000 | 4-6% |
| €25.000 | 1/6 | €400 | €10.000-20.000 | 3-5% |
| €50.000 | 1/8 | €600 | €15.000-30.000 | 2-4% |

> Nota: il Yield % scende con bankroll più alti perché le quote peggiorano (il mercato assorbe lo stake) e si diventa più conservativi.

---

### FASE 6: MONITORING E INTELLIGENCE
**Tempo stimato: 1 settimana**

#### 6.1 — Dashboard Real-Time
- Web app (già hai il frontend in React) con:
  - P&L live, equity curve, drawdown chart
  - Heatmap per lega (quali leghe sono profittevoli)
  - Alert Telegram per ogni scommessa piazzata/risolta

#### 6.2 — Model Drift Detection
- Tracciare il Brier Score settimanale
- Se il modello peggiora (drift), trigger automatico per:
  - Ricalcolo parametri (`eta_goals`, `k_shrink`)
  - Retrain del modello ML
  - Alert per intervento manuale

#### 6.3 — Reporting Fiscale
- Log dettagliato di ogni operazione per dichiarazione fiscale
- Calcolo automatico di plusvalenze/minusvalenze per periodo
- Export CSV/PDF per il commercialista

---

## ⚙️ PARAMETRI CONSIGLIATI PER OGNI FASE

| Fase | Bankroll | Edge Min | Prob Min | Kelly | Max Stake |
|------|----------|----------|----------|-------|-----------|
| Paper Trading | €1.000 | 5% | 55% | 1/4 | 3% |
| Live Conservativo | €2.000 | 7% | 60% | 1/4 | 3% |
| Live Standard | €5.000 | 5% | 55% | 1/3 | 3% |
| Scalato | €10.000+ | 5% | 55% | 1/4 | 2% |

---

## 🎯 CHECKLIST PRE-INVESTIMENTO

Prima di mettere soldi reali, devi avere:

- [ ] 200+ eventi paper trading con Win Rate verificato
- [ ] Calibration Curve con Brier Score < 0.25
- [ ] Backtest storico 3+ mesi con Yield positivo
- [ ] Sharpe Ratio > 1.5 sul periodo di test
- [ ] Drawdown massimo mai superiore al 15% del bankroll
- [ ] Tutti i filtri attivi (Edge, Prob, Min Data, Blacklist, Liquidità)
- [ ] Piano di stop loss chiaro (giornaliero + settimanale)
- [ ] Automazione piazzamento pronta e testata
- [ ] Conto Betfair verificato con deposito pronto
