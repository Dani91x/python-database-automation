# Audit ML e Poisson: previsioni pre-partita del calcio (02/10/2026)

**Perimetro.** L'audit è solo in lettura. Nessuna modifica al codice, nessun addestramento, nessuna scrittura sul DB.

**Come sono stati letti i dati.**
- Il DB è stato letto via REST con sole GET, dall'helper `q.py` (non committato).
- Gli script di valutazione (`fetch.py`, `valuta.py`, `mp_vs_clima.py`, `dati.py`) e le cache locali stanno in `.audit_ml_tmp/` del worktree, non committate.
- Finestra: partite con data dal 04/07 al 30/09/2026, cioè 90 giorni, più un controllo sugli ultimi 60 giorni.

**Convenzione Brier di questo referto.**
- Per i bersagli binari uso il **Brier standard**, `mean((p-y)^2)`: la moneta vale 0,25.
- Per 1X2 uso la somma sulle 3 classi.
- Quando cito `model_performance` uso la **sua** scala, cioè la somma sulle classi: lì la moneta binaria vale **0,50**, non 0,25 (vedi §3.1).

---

## 0. Risposta breve

1. **I Brier di `model_performance` non sono calcolati male.**
   - Sono Brier «somma sulle classi»: per un binario la moneta vale 0,50. I numeri di partenza (0,30-0,46) non sono quindi «peggio di una moneta».
   - Sono però **misurati contro il riferimento sbagliato**: la BSS si calcola contro la moneta, non contro la frequenza storica. Sono anche misurati su un holdout minuscolo (lega 536 = CONCACAF Nations League, ~43 partite).
   - **Contro la frequenza storica, il modello mediano è peggiore in 11 bersagli su 19** (tabella §3.1).
2. **Ricalcolo dal vivo (90 giorni, previsioni scritte prima del calcio d'inizio):**
   - **il mercato batte tutti i nostri modelli su ogni bersaglio**;
   - ML, Poisson e TacticAI battono la frequenza storica solo di poco (2-5 %), su BTTS no;
   - mescolare l'ML al mercato **peggiora** il mercato su ogni bersaglio (§3.3).
3. **Fra i nostri modelli il migliore è TacticAI** (Dixon-Coles MLE), seguito dal Poisson calibrato. L'ML è il più debole sui gol (§3.4).
4. **Uso nei bot.** L'unica previsione che decide da sola è il **veto Under 3.5 di Mike**: blocca il 73-77 % dei casi in banda. Sui dati misurati non separa in modo statisticamente distinguibile le partite buone dalle cattive (§5.1). Le λ sono il prior dei modelli live di Mike e Omega (§5). Tutto il resto è decorativo.

---

## 1. Inventario

### 1.1 Modelli

| Modello | Codice | Chi lo addestra o calcola, e quando | Dove vive | Chi lo usa |
|---|---|---|---|---|
| **ML ensemble_v2**: RF + LightGBM/GB + XGBoost + LogReg, impilati con meta-learner, calibrazione isotonica o temperature, post-calibrazione per decili | `Ai Engine/ai_engine/ensemble_trainer.py` (1519 righe), `seriea_model_export.py:509` `train_and_save_all`, `retrain_all_leagues.py`, `cloud_retrain_shard.py` | GitHub Actions `retrain_models.yml`: a valle di «Daily Yesterday Backfill» più un ripiego alle 08:19 UTC (`:46-55`); planner `training_planner.py`; `last_n_seasons` = 20 (`:279`) | Storage Supabase `ai-models-league-<id>/ensemble_v2_<target>.pkl.gz` più `ai_model_registry` (20.532 righe) e `model_performance` (20.554 righe, **1.027 leghe × ~21 bersagli**) (`seriea_model_export.py:658-709`, `retrain_all_leagues.py:363-374`) | Previsioni: `serving_batch.run_for_date` → `fixture_predictions.model_predictions_json`. Bot: solo lo Scalper in modalità `bias`/`both`, che non è il default (§5) |
| **Post-calibrazione ML** | `compute_ml_post_calibration.py` | `ml_calibration.yml` alle 05:14 UTC più dopo ogni retrain | Tabella `ml_post_calibration` (940 righe) | Sostituisce `targets` in `model_predictions_json` |
| **Poisson «poisson_xg_hybrid_dc»** | `Prediction/today_predictions_backfill.py:1418` `compute_db_json_analisi` | `today_predictions_backfill.yml`: cron 02:18 UTC, partenza reale ~07:35, durata fino a 4 h | `fixture_predictions.db_json_analisi` (inputs λ, ρ, markets, markets_calibrated) | Mike (veto U3.5, ρ, λ di ripiego), Safe e Omega (λ di ripiego), Scalper bias, UI |
| **Calibrazione Poisson** per decili | `poisson_calibrator.py`, `generate_dynamic_cal.py`, `update_poisson_calibration.py` | `weekly_poisson_calibration.yml`, il lunedì alle 03:27 UTC | Tabella `poisson_calibration` (518 leghe) più `dynamic_cal.json` | `markets_calibrated` → `p_under35_cal` di Mike |
| **ρ Dixon-Coles per lega** | `generate_dc_rho.py` | Settimanale, stesso workflow | `dc_rho_by_league.json` (23 leghe, le altre −0,13) | `inputs.dc_rho` → `rho` del dossier Mike |
| **TacticAI** (Dixon-Coles MLE con time-decay) | `tactical_engine/model.py:103-189`, `tactical_engine/serving.py` (half-life 420 giorni, ridge 0,08) | Nello stesso job giornaliero (`today_predictions_backfill.py:2741-2746`) | `fixture_predictions.tactical_engine_json` | **Prima fonte delle λ pre-partita** per Mike, Omega e il motore live (`Betfair/stream/db.py:211-270`) |
| Vecchi `.pkl` | `_AUDIT_2026_05/cache/goals_*.pkl` (10 leghe) | Nessuno | Locali | Nessuno: residui di maggio |

### 1.2 Cadenza ML

- Il retrain è incrementale e per lega (`retrain_models.yml:30-49`). Esempio: la lega 536 è stata riaddestrata oggi alle 08:44.
- `validate_models.yml` (walk-forward, `validate_walkforward.py`) **non ha schedule**: va solo a mano.

---

## 2. Addestramento del modello ML principale

| Aspetto | Cosa fa il codice | Prova | Giudizio |
|---|---|---|---|
| **Unità** | Un modello **per lega e per bersaglio**: 1.027 leghe × ~21 bersagli ≈ 20.500 modelli | `model_performance` | **Difetto strutturale.** Il training mediano ha **745 partite** (p10 = **62**, p90 = 3.032). Lega 536: 321 di training e 66 di validazione, con 15 feature dopo la selezione (`ai_model_registry`) |
| Bersagli | 21: 1x2/ft_1x2 (duplicati), over 0,5-4,5, gol per squadra, btts, clean sheet (= complementi di away/home_over_0_5: stessi Brier, verificato), HT, ht_ft, first_goal_before_30, goal_in_2h | `seriea_model_export.py:577-603` | Bersagli ridondanti: lavoro sprecato e metriche gonfiate nel conteggio |
| **Split** | **Temporale**: train ~75 % / val 15 % / holdout 10 %, con purge di 30 giorni fra train e val; OOF walk-forward dentro il train | `temporal_train_val_holdout_split`, `seriea_model_export.py:234-236`; `ensemble_trainer.py:1053-1081` | **Corretto**: nessuna fuga dal futuro nello split |
| Feature | Finestre mobili di forma/statistiche (`merge_asof`, `allow_exact_matches=False`), xG pre-partita, h2h, Elo, quote API-Football; la classifica di fine stagione è esclusa | `feature_pipeline.py:263-306`, `:768-793`; `seriea_model_export.py:625-634` | Senza fuga; la vecchia fuga di classifica è corretta. Le quote come feature coprono solo una minoranza delle partite (§6) |
| NaN e imputazione | Mediane e scarto >50 % NaN calcolati **solo sul train** | `seriea_model_export.py:261-279` | Corretto |
| Selezione | Varianza, correlazione 0,95, MI top-60 | `seriea_model_export.py:281-286` | Ok |
| Bilanciamento | `class_weight="balanced"` se lo squilibrio è <0,35; **SVMSMOTE** su MEDIUM/LARGE se lo squilibrio è <0,35 | `ensemble_trainer.py:334-372`, `:477-503` | **Dannoso per le probabilità.** Sbilancia i priori proprio sui bersagli rari o quasi certi (over_0_5, away_over_2_5), quelli dove l'ML va peggio della frequenza (§3.1) |
| Iperparametri | Optuna (NLL OOF walk-forward) oppure default per tier | `ensemble_trainer.py:152-316` | Ok, ma su poche centinaia di righe è overfitting dell'ottimizzatore |
| Calibrazione | Isotonica o temperature **sui ~66-156 di val**, poi post-calibrazione per decili da celle holdout | `ensemble_trainer.py:773-873`; `compute_ml_post_calibration.py` | Isotonica su 66 righe = gradini rumorosi |
| Pesi temporali | Half-life 365 giorni, minimo 0,05 | `seriea_model_export.py:94-108` | Ok |
| **Metrica salvata** | Brier somma sulle classi sull'**holdout del 10 %**; BSS = 1 − Brier/((K−1)/K), cioè **contro la moneta** | `seriea_model_export.py:111-117`, `:377-425`; `retrain_all_leagues.py:62-68`; `confidence_gate.py:36-40` | **Riferimento sbagliato**: va confrontata con la frequenza storica e con il mercato. Holdout mediano ~100 partite: rumore ±0,03-0,06 |
| **Confronto con un riferimento** | Assente: né mercato né Poisson né frequenza | — | **Manca la cosa più importante** |

**Cosa manca rispetto a una buona pratica:**
1. Un modello **globale**, con la lega come effetto e le quote di mercato come feature o riferimento, al posto di 20 mila modelli su campioni minuscoli.
2. Skill misurata contro la frequenza storica **e** contro il mercato, su un holdout aggregato e grande.
3. Niente SMOTE sui modelli di probabilità.
4. La validazione walk-forward (`validate_models.yml`) messa a calendario come cancello del retrain.

---

## 3. Valutazione

### 3.1 `model_performance`: il Brier è calcolato bene, interpretato male

- `_brier_score` somma sulle classi (`seriea_model_export.py:111-117`). Per un binario `(p−y)²+((1−p)−(1−y))² = 2(p−y)²`: la moneta vale **0,50**, e la tabella lo scrive (`brier_random = 0.5`).
- Gli 0,30-0,46 della lega 536 vanno quindi divisi per 2 per la scala che usava l'utente: 0,15-0,23, quindi **non sono peggio di una moneta**.
- Con la stessa scala, contro la **frequenza storica** (base rate misurata su 35.040 partite FT dei 90 giorni da `matches`) la situazione è diversa:

| Bersaglio | Freq. | Brier clima (scala somma) | Brier mediano `model_performance` | BSS vs moneta (quella salvata) | **BSS vs frequenza** | % leghe peggiori della frequenza |
|---|---|---|---|---|---|---|
| over_0_5 | 0,941 | 0,1114 | 0,1368 | **+0,726** | **−0,228** | 63 % |
| goal_in_2h | 0,813 | 0,3040 | 0,3704 | +0,259 | **−0,219** | 78 % |
| over_1_5 | 0,786 | 0,3361 | 0,3720 | +0,256 | −0,107 | 65 % |
| ht_over_0_5 | 0,734 | 0,3902 | 0,4263 | +0,147 | −0,093 | 68 % |
| home_over_0_5 | 0,769 | 0,3549 | 0,3680 | +0,264 | −0,037 | 57 % |
| away_over_0_5 | 0,711 | 0,4113 | 0,4257 | +0,149 | −0,035 | 58 % |
| btts | 0,539 | 0,4969 | 0,5054 | −0,011 | −0,017 | 64 % |
| over_2_5 | 0,580 | 0,4871 | 0,4942 | +0,011 | −0,015 | 57 % |
| over_3_5 | 0,368 | 0,4651 | 0,4586 | +0,083 | +0,014 | 47 % |
| over_4_5 | 0,212 | 0,3336 | 0,3215 | +0,357 | +0,036 | 47 % |
| ft_1x2 | — | 0,6401 | 0,6095 | +0,086 | +0,048 | 26 % |
| home_over_1_5 | 0,466 | 0,4978 | 0,4735 | +0,053 | +0,049 | 27 % |
| away_over_1_5 | 0,389 | 0,4753 | 0,4412 | +0,118 | +0,072 | 30 % |
| home_over_2_5 | 0,239 | 0,3634 | 0,3347 | +0,331 | +0,079 | 38 % |
| away_over_2_5 | 0,180 | 0,2953 | 0,2709 | +0,458 | +0,083 | 42 % |
| ht_1x2 | — | 0,6608 | 0,6436 | +0,035 | +0,026 | 30 % |

Fonte: `.audit_ml_tmp/mp_vs_clima.py`, uscita in `out_mp_clima.txt`.

**Avvertenza.** La frequenza qui è globale. Una frequenza per lega sarebbe un riferimento ancora più duro, quindi il quadro reale è peggiore.

**Conseguenze:**
- Il cancello `MIN_BSS=0,12` (`confidence_gate.py:40`, `retrain_all_leagues.py:56`) lascia passare come «affidabile» over_0_5 (BSS 0,73 contro la moneta) proprio dove il modello è il **più peggiore della frequenza**.
- È un errore di riferimento, non di calcolo.

**Lega 536 (CONCACAF Nations League, nazionali, 2020-2025).**
- Dati: 321 di training, 66 di validazione, holdout ~43.
- Contro la frequenza:
  - goal_in_2h: 0,3032 contro 0,3040 → zero skill;
  - away_over_2_5: 0,3324 contro 0,2953 → **peggio**;
  - home_over_2_5: 0,3902 contro 0,3634 → **peggio**;
  - ft_1x2: 0,4943 contro 0,6401 → migliore, ma su ~43 partite è rumore (errore standard ~0,06).
- È un caso estremo e poco rappresentativo, ma mostra bene il difetto «un modello per lega».

### 3.2 Il mio ricalcolo dal vivo

**Dati.** `fixture_predictions`, 90 giorni (04/07-30/09):
- 30.219 righe, di cui 25.330 con esito FT;
- 4.348 senza esito e 541 non FT (AET/PEN) escluse.

**Filtro «scritta prima del calcio d'inizio»:**

| Previsore | Presenti | Scritte prima del KO | Scritte dopo il KO (escluse) |
|---|---|---|---|
| ML (`generated_at < fixture_date`) | 21.679 | 18.803 | **2.876 (13 %)** |
| Poisson | 11.926 | 10.625 | 1.301 (11 %) |
| TacticAI | 6.607 | 5.588 | — |
| Quote API-Football (`update < KO`) | — | 5.159 | — |

- `calibrated_at` del Poisson è sempre precedente al KO nella finestra: **nessuna calibrazione riscritta a posteriori** (`cache_calat.json`).
- Esempio verificato di previsione ML scritta dopo la partita: fixture 1639848 (KO 20/09 00:00), `model_predictions_json.generated_at` = 23/09 13:23.

**Riferimento di mercato.** Quote del primo bookmaker in `raw_json_odds`, senza margine (normalizzazione proporzionale). Non sono quote Betfair né di chiusura: il riferimento è prudente, perché Betfair è più efficiente.

**Tabella A: sottoinsieme comune** (stessa partita per tutte le colonne), Brier / log-loss, 90 giorni:

| Bersaglio | n | ML | Poisson (λ indip.) | Poisson (λ + DC) | **Mercato** | Frequenza | Freq. base |
|---|---|---|---|---|---|---|---|
| over_0_5 | 1.048 | 0,0742/0,275 | 0,0751/0,281 | 0,0756/0,282 | **0,0734/0,272** | 0,0759/0,288 | 0,942 |
| over_1_5 | 1.203 | 0,1833/0,552 | 0,1869/0,560 | 0,1866/0,560 | **0,1799/0,541** | 0,1923/0,574 | 0,787 |
| over_2_5 | 1.212 | 0,2444/0,689 | 0,2453/0,687 | 0,2453/0,687 | **0,2369/0,667** | 0,2543/0,702 | 0,580 |
| over_3_5 | 1.205 | 0,2013/0,596 | 0,2024/0,595 | 0,2024/0,595 | **0,1956/0,576** | 0,2136/0,619 | 0,367 |
| over_4_5 | 1.104 | 0,1249/0,417 | 0,1240/0,409 | 0,1240/0,409 | **0,1222/0,398** | 0,1336/0,440 | 0,212 |
| btts | 1.220 | 0,2460/0,691 | 0,2486/0,692 | 0,2480/0,691 | **0,2410/0,675** | 0,2486/0,690 | 0,539 |
| home_over_0_5 | 771 | 0,1672/0,517 | 0,1671/0,516 | 0,1671/0,516 | **0,1576/0,489** | 0,1677/0,518 | 0,771 |
| home_over_1_5 | 775 | 0,2363/0,667 | 0,2456/0,685 | 0,2456/0,685 | **0,2284/0,648** | 0,2488/0,691 | 0,468 |
| home_over_2_5 | 766 | 0,1636/0,511 | 0,1647/0,511 | 0,1647/0,511 | **0,1569/0,486** | 0,1696/0,523 | 0,240 |
| away_over_0_5 | 774 | 0,2142/0,629 | 0,2065/0,605 | 0,2065/0,605 | **0,2017/0,588** | 0,2187/0,629 | 0,710 |
| away_over_1_5 | 777 | 0,2230/0,649 | 0,2153/0,620 | 0,2153/0,620 | **0,2064/0,600** | 0,2270/0,647 | 0,388 |
| away_over_2_5 | 678 | 0,1233/0,414 | 0,1198/0,397 | 0,1198/0,397 | **0,1167/0,390** | 0,1230/0,413 | 0,180 |
| 1x2 (somma 3 classi) | 2.016 | 0,6143/1,026 | 0,6185/1,029 | 0,6198/1,032 | **0,5845/0,980** | 0,6443/1,068 | — |

Sugli ultimi 60 giorni (`out_60g.txt`) la classifica è identica: il mercato è primo su tutti i 13 bersagli.

**Skill rispetto alla frequenza** (1 − Brier/Brier_clima), dalla tabella A:

| Bersaglio | Mercato | ML | Poisson |
|---|---|---|---|
| over_2_5 | +6,8 % | +3,9 % | +3,5 % |
| over_3_5 | +8,4 % | +5,8 % | +5,2 % |
| btts | +3,1 % | +1,0 % | 0 % |
| 1x2 | +9,3 % | +4,7 % | +4,0 % |

I nostri modelli catturano circa **metà** dell'informazione che ha già il prezzo.

**Tabella B: tutti i previsori, ciascuno sul proprio n** (90 giorni, non confrontabili fra colonne):
- ML su 18.800 partite:
  - over_0_5: 0,0584 contro frequenza 0,0548 → **peggio della frequenza**;
  - btts: 0,2501 contro 0,2485 → **peggio**;
  - over_1_5: 0,1664 contro 0,1675 → pari;
  - over_2_5: 0,2389 contro 0,2436.
- Poisson calibrato su 10.625 partite: over_2_5 0,2333, btts 0,2435 (meglio della frequenza 0,2485), 1x2 0,6111.
- Dettaglio in `out_90g.txt`.

### 3.3 L'ML aggiunge informazione al mercato?

Test: miscela 50/50 ML + mercato contro il solo mercato, stessa partita, 90 giorni.

| | over_2_5 | over_3_5 | btts | 1x2 | away_over_1_5 |
|---|---|---|---|---|---|
| Mercato | **0,2349** | **0,2078** | **0,2435** | **0,5638** | **0,2046** |
| 50 % ML + 50 % mercato | 0,2365 | 0,2095 | 0,2447 | 0,5754 | 0,2107 |

Su **tutti i 15 bersagli** la miscela è uguale o peggiore del solo mercato. Quindi **l'ML non contiene informazione che il prezzo non abbia già**.

### 3.4 TacticAI contro Poisson contro ML

Sottoinsieme comune senza quote, 90 giorni, n = 4.259:

| Bersaglio | **TacticAI** | Poisson calibrato | Poisson λ+DC | ML | Frequenza |
|---|---|---|---|---|---|
| over_1_5 | **0,1599** | 0,1611 | 0,1620 | 0,1625 | 0,1646 |
| over_2_5 | **0,2298** | 0,2318 | 0,2351 | 0,2392 | 0,2424 |
| over_3_5 | **0,2215** | 0,2227 | 0,2246 | 0,2272 | 0,2350 |
| btts | 0,2451 | **0,2440** | 0,2484 | 0,2491 | 0,2469 |
| 1x2 | **0,5864** | 0,6021 | 0,6038 | 0,6012 | 0,6387 |

Sul sottoinsieme che ha anche le quote (n = 673-1.076):
- 1x2: TacticAI 0,5950 contro mercato 0,5744;
- over_2_5: 0,2425 contro 0,2366.

TacticAI è il più vicino al mercato, ma resta sotto. Sugli ultimi 60 giorni l'ordine è lo stesso.

---

## 4. Poisson

**Calcolo delle λ.** Le prove vengono dal delegato; i punti segnati «verificato» li ho riletti io.
- `today_predictions_backfill.py:1418-1590`.
- Medie di lega casa/trasferta della **stagione** (`:1287-1296`).
- Finestre 5/10/15 pesate 0,5/0,3/0,2 (`:1494`), separate casa/trasferta, minimo 5 partite.
- Restringimento k = 8 verso la media di lega (`:1522-1527`).
- Forza = 0,6 × rapporto gol + 0,4 × rapporto xG, se c'è l'xG (`:1575-1587`).
- `λ = media_lega · attacco · difesa` (`:1589-1590`).
- **Nessun vantaggio casa esplicito**: entra solo dalle medie separate. **Nessun uso delle quote nelle λ.** Nessuna correzione per la forza degli avversari affrontati.
- In DB (verificato) `home_matches_used` ≤ 15 e `xg_blend_active` è spesso false: nella riga d'esempio, lega 242, xG assente.

**Dixon-Coles.**
- ρ = −0,13 fisso, oppure per lega da `dc_rho_by_league.json` (23 leghe). È stimato a profilo con le λ già salvate come marginali fisse (`generate_dc_rho.py:81-161`).
- Correzione τ standard sulle 4 celle basse, griglia 11×11 (`:1193-1207`, `:1605-1614`).
- Nel ricalcolo l'effetto di ρ è **nullo o negativo**: λ+DC contro λ indipendenti differisce di ±0,001 (tabella A).

**Calibrazione (`markets_calibrated` → `p_under35_cal`).**
- Fattore per decile `hit_rate/avg_prob`, limitato a [0,2, 3], lega → globale con restringimento `n/(n+75)` (`poisson_calibrator.py:63-182`, `generate_dynamic_cal.py:351-477`).
- Settimanale, **su tutto lo storico, senza split temporale**. Per le righe nuove è comunque fuori campione, perché si usa la tabella del lunedì precedente.
- Lo script manuale `backfill_poisson_calibrated.py` può riscrivere lo storico in campione. Nella finestra 90 giorni non è successo (verificato, `calibrated_at` < KO su tutte le 10.625 righe).
- Nel ricalcolo la calibrazione **aiuta poco ma davvero**: over_2_5 da 0,2372 a 0,2340, btts da 0,2474 a 0,2437 (tabella «ML vs Poisson memorizzato», n = 8.349).

**`p_under35_cal` di Mike.**
- `= 1 − markets_calibrated.over_3_5.True` (`Betfair/mike/dossier.py:102-107`, verificato).
- Qualità, come complemento di over_3_5 calibrato: Brier 0,2191 su 10.625 partite, contro frequenza 0,2324 e contro il mercato 0,1956 sul sottoinsieme comune (Poisson λ 0,2024).
- È **meglio della frequenza, peggio del mercato**.

**Incoerenza di fonte.** Nel dossier di Mike:
- le λ vengono **prima da TacticAI** (`Betfair/stream/db.py:245-264`);
- ρ e `p_under35_cal` vengono dal Poisson ibrido (`dossier.py:96-107`).

Due motori diversi alimentano lo stesso calcolo.

---

## 5. Uso nei bot

Ricostruzione del delegato. La parte Mike l'ho verificata io (`config.py:152-157`, `engine.py:3460-3530`, `dossier.py:100-108`).

| Bot | Previsione | Ruolo | Decisiva o decorativa |
|---|---|---|---|
| **Mike** | `p_under35_cal` (Poisson calibrato) | **Veto** sull'ultimo ingresso Under 3.5 (10' prima del fischio) se `P < soglia(quota)`. Nodi: 1,30→0,807; 1,50→0,684; 2,00→0,514; 2,50→0,385; 3,00→0,275. Acceso di default | **Decisiva** |
| Mike | λ (TacticAI → Poisson) + ρ | Hazard, attesa della copertura, cash-out, uscita in perdita da modello (`dossier.py:298-411`) | Decisiva ma attenuata: il live condiziona il prior |
| Mike | `p4_pre` | Solo UI | Decorativa |
| Omega | λ fixture **solo se mancano le quote pre-KO** (`lambda_quote_prima=True`) | P della cella Correct Score (v3, fusa col mercato) | Di solito sostituita dalle quote |
| Omega advisor | `poisson_prob` | Informativa | Decorativa |
| Safe | λ (dopo le quote pre-KO) | Opportunità di modello `p ≥ 0,95` → solo **proposte** con tasto PIAZZA | Decorativa: nessun ordine automatico |
| Safe | `raw_json` API-Football (h2h, last5) | Filtro ESATTO `requireSelection` | Filtro decisivo, ma **non è ML né Poisson** |
| Scalper | ML `target_1x2` + Poisson grezzo 1x2 | Lato del bias | Solo in modalità `bias`/`both`; il default `maker` non lo usa |
| Atlante v4 | Nessuna λ («predicono peggio del proxy», `atlante_v4.py:27-38`) | — | — |
| Report, UI, `analytics_signals` | Tutto | Visualizzazione e analisi | Decorativa |

### 5.1 Controfattuale sul veto di Mike

Dati: partite con quota bookmaker Under 3.5 tra 1,30 e 3,00 e P calibrata scritta prima del KO. Lo ROI è quello di un back flat dell'Under alla quota del bookmaker.

| 90 giorni, n = 760 | % vetate | ROI non vetate (n) | ROI vetate (n) |
|---|---|---|---|
| P calibrata reale | 72,9 % | −0,012 (206) | −0,074 (554) |
| P = moneta 0,5 | 91,6 % | +0,133 (64) | −0,074 (696) |
| P = mercato senza margine | 98,7 % | (10) | −0,063 (750) |

| 60 giorni, n = 498 | % vetate | ROI non vetate | ROI vetate |
|---|---|---|---|
| P calibrata reale | 77,1 % | −0,068 (114) | −0,081 (384) |

**Lettura.**
- **Se la previsione fosse una moneta, la decisione cambierebbe molto**: il veto passerebbe dal 73 % al 92 %, cioè quasi ogni ingresso sotto quota ~2,05 verrebbe bloccato. La previsione **non è decorativa**.
- Il vantaggio del filtro però **non si vede in modo affidabile**:
  - sui 90 giorni le non vetate rendono 6 punti meglio, con errore standard ~±6,5 punti su 206 casi;
  - sui 60 giorni la differenza è di 1 punto.
- Le soglie sono state stimate «al 97 % in campione» (`MISURA_PUNTO8_2026-09-25.md:761`, riferito dal delegato).
- **Cautela.** Uso quote di bookmaker con margine, più corte di Betfair: alle quote Betfair le soglie sarebbero più basse e il veto meno frequente. Il controfattuale vero va rifatto sulle quote Betfair registrate. Non l'ho fatto: non era nel perimetro e servono le registrazioni.

**Giudizio.** Il veto è l'unico punto dove una previsione pre-partita sposta soldi da sola. Oggi non ha una prova fuori campione di valore. Che resti acceso è una **decisione dell'utente**: la strategia non va toccata d'iniziativa.

---

## 6. Dati

| Voce | Misura |
|---|---|
| `matches`, ultimi 90 giorni | 36.002 partite: FT 35.040, PEN 543, AET 163; **NS passate 256** (rinviate o senza esito); duplicati di `fixture_id`: 0 |
| Ultima partita FT in `matches` | 01/10/2026 23:30, aggiornata |
| `fixtures` | **La tabella non esiste** (REST 404): l'elenco partite è `matches` |
| `fixture_predictions`, 90 giorni | 30.219 righe; 1.302 senza riga in `matches`; esiti mancanti 4.348 |
| Copertura previsioni sulle partite FT | ML 74 %, Poisson 42 %, TacticAI 22 %, **quote 20 %** |
| Buco di copertura giornaliero | Es. 05/09: 100 previsioni contro 1.485 partite (`fetch.log`) |
| `api_coverage_by_season_v2_mv` | **Ferma e inaffidabile**: 402 leghe; stagione 2026 = 58 partite passate, mentre in 90 giorni ci sono 35 mila FT; 374 leghe hanno 1 sola stagione. Non usarla come misura di copertura (refresh rimosso, vedi `test_orchestratore_niente_refresh_mv_2026_09_25.py`) |
| Copertura dettagli (dalla MV, storico) | events 85 %, team_stats (xG) 48 %, odds 2,2 % |
| `fixture_detail_checks` | 15.547 controlli, tutti «vuoto»: lineups 8.525, events 4.095, team_stats 1.579, player_stats 687, odds 661 |
| `model_performance` | 1.635 righe con Brier NULL (holdout <10 righe) |

---

## 7. Verdetto (per un non tecnico)

1. **Cosa funziona.** La macchina gira tutti i giorni: retrain, previsioni, calibrazioni. È scritta senza fughe dal futuro nello split. Poisson calibrato e TacticAI sono un po' meglio della «media storica».
2. **Cosa è rotto.** Il modo di giudicare l'ML. La «pagella» confronta i modelli con una moneta invece che con la media storica e con il mercato. Così un modello peggiore della media risulta «ottimo» (over 0,5: 0,73 di skill dichiarata, −0,23 reale).
3. Si addestrano **20 mila modelli piccoli** (uno per lega e bersaglio, mediana 745 partite, alcuni 60): per lo più imparano rumore.
4. Il 13 % delle previsioni ML viene riscritto **dopo** la partita. Il dato storico in tabella non è quindi sempre una vera previsione.
5. **Nessun nostro modello batte le quote**, su nessun bersaglio. Unire l'ML alle quote peggiora le quote.
6. **Cosa è decorativo.** ML quasi ovunque (UI, report, Safe, Omega advisor, Scalper non di default).
7. **Cosa decide.** Il veto Under 3.5 di Mike (blocca circa 3 ingressi su 4) e le λ come prior dei modelli live di Mike e Omega. Il veto non ha ancora una prova fuori campione di utilità.
8. **Onestamente, il vantaggio non sta nelle previsioni pre-partita**, che il mercato già prezza meglio di noi. Sta nell'esecuzione e nel live: tempi, liquidità, reazioni al gol, uscite.

**I 5 interventi, in ordine di valore** (stime per un agente, codice e verifica):

1. **Misurare fuori campione, sulle quote Betfair registrate, il veto Under 3.5 di Mike** e portare il referto all'utente per decidere se tenerlo, ritararlo o spegnerlo: 1-2 giorni. È l'unico punto dove una previsione muove soldi da sola.
2. **Rifare la pagella**:
   - BSS contro frequenza per lega **e** contro mercato, più log-loss, su un holdout aggregato e grande;
   - cancello del retrain = «batte la frequenza e non peggiora la miscela col mercato»;
   - `validate_models.yml` a calendario.

   Stima: 1-2 giorni.
3. **Congelare le previsioni al calcio d'inizio** (niente riscritture post-KO; partenza del job prima delle partite del mattino) e **alzare la copertura delle quote** (oggi 20 %) per avere sempre il riferimento: 2 giorni.
4. **Un solo motore di λ**: TacticAI, il migliore. Va reso coerente con ρ e con la calibrazione dello stesso motore (oggi Mike mescola le λ di TacticAI con ρ e P del Poisson ibrido). Si valuta poi un'ancora sulle quote pre-partita quando ci sono: 3-4 giorni.
5. **Sostituire i 20 mila modelli ML con un modello globale** (lega come variabile, niente SMOTE, scarto dal mercato come bersaglio o quote come feature) oppure **sospendere l'ML** dove non batte la frequenza: 5-8 giorni. Valore atteso basso: anche fatto bene, al massimo si avvicinerà al mercato.

---

## 8. Cosa non ho potuto verificare

- **Il riferimento di mercato non è Betfair.** È il primo bookmaker di API-Football senza margine, non la quota di chiusura né Betfair, e copre solo il 20 % delle partite. Il controfattuale del veto di Mike va rifatto sulle quote Betfair registrate.
- **`first_goal_before_30` non valutato**: servono gli eventi.
- **Frequenza in campione e globale.** È calcolata sulla stessa finestra ed è globale, non per lega. Questo favorisce leggermente la frequenza nelle tabelle dal vivo e la sfavorisce nella tabella §3.1.
- **Parti del delegato non rilette tutte.** Le affermazioni su Poisson, TacticAI, Safe, Omega e Scalper vengono dai due delegati Explore, con file:riga. Io ho riletto di persona Mike (`config.py`, `engine.py`, `dossier.py`), lo split e la metrica ML (`seriea_model_export.py`, `temporal_split.py`, `retrain_all_leagues.py`, `confidence_gate.py`) e la fuga di classifica (`feature_pipeline.py`).
- **Esecuzione di `AGGIORNA_CAMPO_db_json_analisi.py --force` non provata.** Non ho prove che lo storico prima di luglio sia stato ricalcolato a posteriori. La mia finestra è filtrata su `generated_at < KO`, quindi non ne è toccata.
- **Ritardo reale dei job.** Il dato (partenza ~07:35 UTC, fino a 4 h) viene da `AUDIT_2026-09-25/ACTIONS_DIAGNOSI_E_FIX.md` e non l'ho rimisurato.
