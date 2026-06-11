# REPORT FINALE — INDAGINE MOTORE POISSON / DIXON-COLES xG-HYBRID
**File:** `Prediction/today_predictions_backfill.py` · **Scope:** sola indagine, zero modifiche · **Data:** 2026-06-11
**Metodo:** workflow multi-agente — 52 agenti, 7 moduli mappati riga-per-riga, 14 verifiche matematiche, 8 ricerche web, 22 raccomandazioni verificate in modo avversariale.

---

## 1. VERDETTO COMPLESSIVO

**Matematicamente corretto?** SÌ. Nessun bug di calcolo confermato nel cuore del modello. Tutte le formule (griglia Poisson indipendente, correzione Dixon-Coles τ, normalizzazione, derivazione mercati, shrinkage Bayesiano, blend convesso xG/gol, ricostruzione moltiplicativa di λ) sono dimensionalmente coerenti e fedeli alla letteratura canonica (Dixon-Coles 1997). Il modello collassa correttamente alla baseline per un matchup neutro (λ_home = league_home_avg quando attack=def=1.0): proprietà di chiusura verificata algebricamente.

**Posizione vs stato dell'arte: 6.5 / 10.**
- *Cosa lo tiene alto:* struttura DC corretta, blend xG presente, shrinkage empirical-Bayes a due livelli (forze + calibrazione `n/(n+75)`), correzione τ con ρ nel range di letteratura, derivazione coerente di tutti i mercati FT da un'unica griglia.
- *Cosa lo tiene sotto l'8:* le **forze attacco/difesa sono stimate via ratio-of-means euristico, non via MLE congiunto Dixon-Coles** → nessuna correzione per strength-of-schedule (calendario); **recency a finestre fisse [5,10,15] con pesi {0.5,0.3,0.2}** invece di time-decay esponenziale calibrato (Ley 2018: half-life ottimale 360-390 giorni); **costanti tutte hard-coded e mai calibrate OOS** (DC_RHO=-0.13, η=0.6, k_shrink=8, k_HT=12).

**È profittevole? NO.** Reality check dirimente e ripetuto in tutta la verifica avversariale: **il modello live NON batte la closing line. CLV ≈ 0, ROI -2.5%/-5.5%.** Questo è il fatto che governa tutto il report: il problema non è la correttezza matematica (che c'è) né la micro-calibrazione delle costanti (cosmetica), ma l'**assenza di edge informativo rispetto al mercato**.

---

## 2. CORRETTEZZA RIGA-PER-RIGA

**Bug di calcolo confermati: ZERO.** Tutte le verifiche matematiche per componente concludono `verdict: correct` sulla meccanica. I `suspect` riguardano scelte metodologiche (subottimalità statistica), non errori aritmetici.

**Punti di attenzione confermati nel codice (NON bug, ma fragilità/scelte):**

| # | Riferimento | Natura | Impatto |
|---|---|---|---|
| 1 | `:788-790` `_window_stats` | `goals_for`/`goals_against` sommati **senza cast esplicito a float**. Se il driver DB restituisce stringhe, `sum()` concatena invece di sommare. Il cast è presente in `_build_xg_cache` (`value_numeric`) ma **assente qui**. | Latente — dipende dal tipo restituito dal driver. Da verificare. |
| 2 | `:586-594` `_poisson_prob` | Funzione PMF scalare **dichiarata ma mai chiamata** nel flusso principale (la pipeline usa `_build_score_grid` vettorizzato). Dead code / safety net. | Nullo. Cosmetico. |
| 3 | `:954` + `:962` blend xG | Quando `xg_blend is None`, `_shrink(None,...)` ritorna il prior → `xg_h/league_home_xg_avg = 1.0` esatto → il termine 0.4 collassa a costante **senza alcuna segnalazione**. Degrado silenzioso al solo-gol. | Reale ma silenzioso. Serve telemetria, non fix. |
| 4 | `:1030-1031` + `:1068` griglia HT | La griglia HT è un **modello autonomo** (non marginale condizionale della griglia FT). `p_goal_1h_poisson = 1 - e^(-λ_1h)` è calcolata **senza correzione DC**, mentre `p_ht_home/draw/away` usa la griglia DC-corrected. Incoerenza interna: per Over 0.5 la cella (0,0) è critica e DC la gonfia (ρ<0), quindi `p_goal_1h_poisson` **sovrastima leggermente** Over 0.5. | Piccolo, strutturale. |
| 5 | `:1064` `p_goal_1h_freq` | Assume **indipendenza** tra `p_home_1h` e `p_away_1h` (eventi che condividono il contesto-partita, non indipendenti). | Piccolo bias direzionale. |
| 6 | `:1045-1057` `_team_p_goal_1h` | Frequenza empirica grezza **senza shrinkage**, fallback fisso 0.5, finestra fissa 15. Per team con 1-2 partite HT → stima 0.0 o 1.0 (estremi, nessuna regressione al prior). Incoerente con la logica multi-window del resto del modello. | Medio su sample piccolo. |
| 7 | `:964-965` `home_def`/`away_def` | I termini difensivi usano **solo gol-subiti, nessun xGA**. Asimmetria con l'attacco (che blenda xG via η). Il peso 0.4-xG agisce su **un solo** dei due fattori di λ → influenza xG di fatto dimezzata. | Scelta progettuale, non documentata. |

**Verifiche numeriche superate:** τ(0,0)=1.2145, τ(1,1)=1.13, τ(1,0)=0.857 con λ=(1.5,1.1) — coerenti con la letteratura. H+D+A=1.000000 (già certificato). Floor `max(0.05,...)` su λ e floor `max(0.0,...)` su celle (1,0)/(0,1) sono guard innocue (la seconda si attiva solo per λ>7.7, irraggiungibile).

---

## 3. ANALISI PER MERCATO

### 3.1 — 1X2 (`p_home/p_draw/p_away`, `:982-988`)
- **Logica attuale:** somma celle della griglia DC-corrected normalizzata (`hg>ag`, `hg==ag`, `hg<ag`).
- **È la migliore?** Quasi. Per il 1X2 puro la struttura griglia-bivariata è corretta, ma **il gap della bivariata vs Poisson indipendente è nel 4° decimale** (Ley 2018: RPS 0.1953 biv vs 0.1954 indip su EPL 2008-2018). Lo SOTA per il *solo* 1X2 sono ensemble ML su rating (XGBoost+pi-ratings RPS ~0.2063, ~52% accuracy), ma su dataset/metriche non comparabili 1:1.
- **Gap reale:** non è la formula di estrazione, è la **stima delle forze** (ratio-of-means → no strength-of-schedule) e il **non-enforcement** di `p_home+p_draw+p_away=1` (floating point può dare 0.9999/1.0001, irrilevante in pratica).
- **Best practice:** MLE congiunto DC (att/def stimati simultaneamente con vincolo Σatt=Σdef=0) + γ home esplicito. **Differito per vincolo no-cambio-strategia.**

### 3.2 — Over/Under (1.5/2.5/3.5, `:989-994`)
- **Logica attuale:** somma celle con `tot_idx >= soglia`. Soglie 2/3/4 corrette per Over 1.5/2.5/3.5.
- **È la migliore?** La derivazione è corretta e l'OU è il mercato dove la griglia bivariata e la correzione DC **aiutano di più** (la massa sulla diagonale e sui low-score conta). Tuttavia l'OU dipende dal **livello assoluto** di λ_home+λ_away — quindi è il mercato più sensibile a (a) bias di baseline e (b) qualità del blend xG. La calibrazione dinamica per-mercato a valle corregge il livello.
- **Gap:** il livello di λ eredita la subottimalità della recency a finestre (over-weight ultime 5) e del peso η=0.6 non calibrato. Best practice: time-decay calibrato + peso xG data-driven (letteratura suggerisce xG > gol su finestre brevi).

### 3.3 — BTTS (`p_btts`, `:995-996`)
- **Logica attuale:** somma celle `(hg>0)&(ag>0)`. Maschera corretta.
- **È la migliore?** È il mercato che **più beneficia della dipendenza fra i gol**. Karlis-Ntzoufras: "anche un piccolo parametro di dipendenza migliora la previsione del numero di pareggi". Qui la dipendenza è catturata **solo** dalla correzione DC τ sulle 4 celle low-score, non da un λ3 bivariato pieno. È adeguato ma non SOTA.
- **Gap:** ρ=-0.13 fisso e globale (non per-lega). BTTS è sensibile a P(0,0)/P(diagonale), quindi un ρ mal-tarato per lega (es. leghe ad alto under) sposta direttamente la stima. Best practice: ρ stimato per-lega via MLE su finestra ampia (NON per-stagione: introduce rumore).

### 3.4 — HT / Primo Tempo (`first_half_over_0_5`, `:998-1069`)
- **Logica attuale:** modello **ibrido** = media 50/50 tra componente frequentista (`1-(1-p_h1h)(1-p_a1h)`) e componente Poisson (`1-e^(-λ_1h)`).
- **È la migliore? NO — è il mercato più debole del motore.** Problemi confermati:
  1. **Media 50/50 non calibrata** — nessuna giustificazione per il peso equo; le due componenti **non sono indipendenti** (stessi dati storici HT), quindi la media sottostima la varianza.
  2. **Griglia HT autonoma** (non condizionale dalla FT) → rompe la coerenza probabilistica (P_HT_home può eccedere P_FT_home in casi estremi).
  3. **Componente Poisson senza DC** → sovrastima Over 0.5.
  4. `_team_p_goal_1h` **senza shrinkage**, fallback 0.5, finestra fissa 15.
  5. `_compute_ht_ratio` shrinkage Beta-Binomiale **statisticamente corretto** (denominatore = `total_gf`, ogni gol è una prova Bernoulli "segnato nel 1T?"), cap [0.25,0.65] ragionevole.
- **Gap/best practice:** unificare il modello HT come marginale condizionale della griglia FT (coerenza), aggiungere shrinkage a `_team_p_goal_1h`, e calibrare il peso ibrido OOS invece del 50/50.

---

## 4. COMPONENTI MATEMATICHE TRASVERSALI — RATING & GAP

| Componente | Rif. | Rating | Gap principale |
|---|---|---|---|
| **Recency / time-decay** | `:884-893`, `:891` | ⚠️ **3/10** | Finestre annidate [5,10,15] {0.5,0.3,0.2} → peso effettivo per-match: 0.143 (1-5) / 0.043 (6-10) / 0.013 (11-15) = **decay step 10.7×, cutoff netto a 15**. Letteratura (Ley 2018): half-life ottimale **360-390gg** (decay LENTO, cross-stagione), RPS biv 0.1953 / indip 0.1954. Heuer: autocorrelazione goal-diff **piatta intra-stagione** → over-weight ultime-5 insegue rumore. *Il valore della correzione è però marginale su RPS (Δ 3°-4° decimale).* |
| **Shrinkage EB** | `:919-924` (k=8), `:998-1023` (k_HT=12), gen_dynamic_cal `:377` (SHRINK_K=75) | ✅ **7/10** | Tre forme di posterior-mean coniugata **corrette** (Poisson-Gamma, Beta-Binomiale, partial pooling). Gap: k tutti hard-coded, mai stimati via σ²/τ² (Efron-Morris), k identico per gol e xG (xG più stabile → meriterebbe k_xG minore). |
| **Blend xG** | `:920` (η=0.6), `:962-963` | ⚠️ **5/10** | η=0.6 hard-coded, mai calibrato. Letteratura xG (Mead 2023: Brier 58.6 xG vs 59.7 gol, ~1.8%; Beat the Bookie: r=0.574 xG vs 0.47 gol con gol futuri) suggerisce **xG ≥ gol → η<0.5**, ma nessuno studio dà un peso ottimale chiuso. xGA assente nella difesa. Degrado silenzioso quando xG manca. |
| **Costruzione λ** | `:967-968` | ⚠️ **6/10** | Forma moltiplicativa corretta (= exp(c+att+def+home) di DC), ma stima **ratio-of-means euristica, non MLE congiunto** → **no correzione strength-of-schedule**, no γ home esplicito. Bias reale su n piccolo + calendari sbilanciati. |
| **Dixon-Coles τ** | `:614`, `:617-631`, `:973-980` | ✅ **8/10** ("good") | Implementazione fedele e corretta (valore/segno/4 celle). Gap: ρ=-0.13 **fisso globale ereditato da EPL anni '90**, mai ri-stimato né per-lega. Impatto performance minuscolo (biv vs indip = 0.0001 RPS). |
| **Calibrazione** | gen_dynamic_cal `:298-377` | ✅ **7/10** | Partial pooling `w=n/(n+75)` corretto; backtest walk-forward OOS onesto già presente (master_backtest SECTION 5). Manca: calibrazione probabilistica post-modello (isotonic) — vedi §5. |
| **De-vig / EV / Kelly** | — | ❓ **non valutato** | Non presente nelle fonti dell'inventario. **Lacuna di copertura dell'indagine** — è esattamente il layer che determina il P&L reale (vedi §7). Da indagare separatamente. |

---

## 5. TECNICHE DA AGGIUNGERE (sopravvissute alla verifica avversariale, holds=true)

La verifica avversariale ha **confutato (holds=false) tutte le raccomandazioni di raffinamento del motore Poisson** come a bassa leva/cosmetiche rispetto al fallimento reale (CLV≈0). L'**unica tecnica con evidenza numerica forte e holds=true** è:

### ⭐ T1 — Calibrazione probabilistica post-modello (Isotonic Regression) — PRIORITÀ #1
- **Cosa:** layer di isotonic regression (o Platt) sopra le probabilità 1X2/mercati del modello, fittato su finestra walk-forward rolling, ricalibrato periodicamente. **Indipendente dal motore.**
- **Evidenza/numeri:** Wilkens 2026 (Bundesliga, 11 stagioni, 2118 partite): **senza calibrazione ROI ~1% → con isotonic ROI ~10%**; perdite away-win da -38% a -17%; log-loss modello 1.25 vs mercato 1.41. **È la leva con l'evidenza ROI più forte di tutte.**
- **Guadagno atteso:** documentato salto ROI 1%→10% in backtest. Migliora calibrazione senza toccare la discriminazione.
- **Sforzo:** **LOW** (layer additivo, harness OOS già esistente).
- *Caveat onesto:* dimostrato su una sola lega/sorgente; va validato sui nostri 71.699 fixture prima di trarre conclusioni. Anche con calibrazione perfetta, se CLV≈0 il guadagno può non materializzarsi (vedi §7).

### Tecniche secondarie (holds=true ma a guadagno marginale — solo come diagnostica low-cost)
- **T2 — Telemetria degrado xG silenzioso** (`xg_blend is None`): misurare la **frazione di λ calcolati col termine 0.4 inerte**. Costo nullo, non cambia output. Se la copertura xG è bassa su molte leghe, la conclusione operativa è "il blend xG è già largamente disattivato" — sposta l'energia altrove. **Sforzo: LOW.**
- **T3 — Diagnostica autocorrelazione goal-diff (Heuer-test):** calcolare l'autocorrelazione della differenza-reti vs Δn su 2-3 leghe campione. Check da 1-2 ore che **decide** se la recency a finestre va appiattita. Se piatta → la conclusione è **appiattire** verso media-stagione (cambio minimo), NON adottare decay esponenziale con half-life tarate (overfit). **Sforzo: LOW.**

---

## 6. COSA SCARTARE (confutato — holds=false — non tornarci sopra)

| Raccomandazione confutata | Perché scartarla |
|---|---|
| **Time-decay esponenziale / half-life calibrate al posto delle finestre [5,10,15]** | Ottimizza RPS/log-loss (Δ 3°-4° decimale, Ley: 0.1953 vs 0.1954) = **cosmetico**. Non inietta informazione che il mercato non prezza già → **nessun path a chiudere CLV≈0**. Tenere solo il *test diagnostico* T3, NON il re-design. |
| **Rimozione split casa/trasferta + HFA globale / random-effect gerarchico** | Lo split è **già quasi inerte**: con k_shrink=8 i prior venue-correct pesano 57-73% nel segmento 5-12 partite. Δ-log-loss atteso ≈ 0. Il re-design (HFA gerarchico) è **cambio di motore differito** per vincolo utente. |
| **Sweep OOS dei tre k (8/12/75) + stima k per-lega/per-stat** | La soglia stessa della raccomandazione (<1% log-loss → near-optimal) predice un nulla di fatto: i k sono prior a bassa leva (fixture puntabili n~10-15, k=8 pesa <40%). L'infrastruttura EB è **già aggiunta** (fix 2026-06-10). Ammesso solo: micro-check σ²/τ² su 3-4 leghe + eventuale abbassamento del solo k_xG. |
| **Grid-search su η=0.6 (blend xG)** | Ottimizza metrica cosmetica in-sample su modello che già perde vs closing line. Guadagno ROI atteso ≈ 0 + rischio overfit a costante singola. La premessa "letteratura suggerisce η<0.5" **non è supportata** dal research_dump locale (tratta weighted-MLE ranking, non blend xG/gol). |
| **Time-decay / DC-MLE come fonte delle baseline di lega** | La baseline si **cancella algebricamente** (λ_home = league_avg·(gf/league_avg)·(ga/league_avg)): fattore di scala di 2° ordine, simmetrico su H/A → quasi-cancellante sul 1X2. La promozione DC-MLE è **cambio di cuore del modello, differito**. |
| **xGA simmetrico nella difesa / η adattivo / ridge data-driven** | Ridisegni del modello che **violano il vincolo no-cambio-strategia**. Rinviare alla rifinitura congiunta finale dei due motori. |

**Principio comune della confutazione:** tutte queste leve ottimizzano RPS/Brier/log-loss (metriche *upstream* del fallimento). Con CLV≈0 il modello è già statisticamente indistinguibile dalla closing line: **migliorare la calibrazione interna non crea edge informativo.**

---

## 7. REALITY CHECK PROFITTABILITÀ

**Il fatto nudo:** il modello live **non batte la closing line**. ROI **-2.5% / -5.5%**, **CLV ≈ 0**.

**Cosa significa CLV≈0:** i prezzi del modello, dopo calibrazione, sono **statisticamente indistinguibili** dalla closing line. Il deficit è **informativo**, non di smoothing/calibrazione. Il mercato prezza già — e meglio — tutto ciò che il motore stima (forze, vantaggio-campo, dipendenza gol). Un modello può essere **perfettamente calibrato e avere CLV=0**: per questo ogni miglioramento di RPS/Brier/log-loss è **cosmetico finché non muove dimostrabilmente il CLV**.

**Perché raffinare il Poisson non basta:**
- Il gap vs closing line è guidato da **informazione real-time mancante**: formazioni, infortuni, rotazioni, meteo, motivazione, microstruttura di mercato/closing line movement. Nessuna di queste è nel motore.
- Constantinou-Fenton avvertono: RPS è la metrica giusta per il *ranking* ma non garantisce profitto. Wheatcroft: un forecast può vincere su RPS ed essere **inadatto al betting**.
- La letteratura che mostra ROI positivo (Koopman-Lit 2015 EPL 2010-12; Wilkens 2026 ~10%) lo fa su **finestre/leghe specifiche** e l'edge **può non reggere su mercati moderni efficienti** (margine bookmaker + erosione della closing line).

**Cosa servirebbe DAVVERO per generare edge (in ordine di leva):**
1. **Layer di esecuzione / line-shopping / CLV** — battere il *miglior prezzo disponibile*, non il prezzo medio. Catturare il movimento verso la closing line (scommettere presto su linee che si muoveranno a favore). **Attualmente fuori scope per vincolo, ma è il vero collo di bottiglia.**
2. **Calibrazione probabilistica (T1, isotonic)** — l'unica leva *interna* con evidenza ROI forte, ma subordinata al fatto che il modello abbia un edge grezzo da calibrare.
3. **Informazione che il mercato prezza male/tardi** — xG di alta qualità per-lega, dati formazioni/infortuni pre-match, segnali su leghe minori meno efficienti (dove il margine è più grande e il pricing più lento).
4. **Selezione mercati/leghe** — concentrarsi su mercati e leghe dove il mercato è meno efficiente (leghe minori, mercati derivati come HT/BTTS/correct-score) invece dei mercati liquidi 1X2/OU2.5 sulle top-5.

**Conclusione onesta:** il motore è un *buon stimatore di probabilità calibrate* ma **non un generatore di edge**. Spostare energia dal raffinamento Poisson (cosmetico) all'esecuzione/CLV/informazione-differenziale è l'unico percorso verso la profittabilità.

---

## 8. PIANO DI INDAGINE / VALIDAZIONE CONSIGLIATO (NON implementazione)

Ablation backtest **walk-forward out-of-sample** sui **71.699 fixture**, **una leva alla volta**, con **metriche multiple** (RPS + log-loss/Ignorance + Brier + reliability/ECE + **ROI/CLV vs closing line**). Regola d'oro: **giudicare il successo su CLV/ROI, non su RPS** — dato CLV≈0, trattare ogni miglioria RPS come cosmetica finché non muove il CLV.

**Sequenza (per impatto-atteso decrescente):**

| Step | Indagine | Costo | Criterio go/no-go |
|---|---|---|---|
| **0** | **Baseline CLV/ROI onesta:** misurare CLV e ROI del modello attuale per mercato/lega sui 71.699 fixture, vs closing line e vs best-price. **Questo è il numero che conta.** | Medio | È il riferimento per tutto il resto. |
| **1** | **T1 — Isotonic calibration (la leva #1):** fittare isotonic su finestra rolling, misurare ROI/CLV pre vs post. | Low | Va avanti solo se muove CLV, non solo log-loss. Atteso (Wilkens): ROI 1%→10% — **verificare se regge sui nostri dati**. |
| **2** | **T2 — Telemetria degrado xG:** frazione di λ con `xg_blend=None` per lega. | Low | Se alta → blend xG già disattivato; riallocare energia. |
| **3** | **T3 — Heuer-test:** autocorrelazione goal-diff vs Δn su 2-3 leghe. | Low | Se piatta → A/B {0.5,0.3,0.2} vs **media-stagione piatta** (cambio minimo). NO half-life tarate. |
| **4** | **Bias strength-of-schedule:** confronto OOS λ ratio-heuristic vs MLE-DC stagionale (penaltyblog/statsmodels). | Medio | Refactor solo se gap RPS > 0.002 (improbabile: Ley biv-vs-indip = 0.0001). **Atteso: no-go.** |
| **5** | **Micro-check shrinkage:** calcolare σ²/τ² su att/def per 3-4 leghe grandi; verificare se k∈[4,12]; misurare var(xG) vs var(gol) → eventuale solo k_xG<k_goals. | Mezza giornata | Se k∈[4,12] → chiudere "near-optimal confermato". |
| **6** | **Zona patologica split:** quante fixture cadono in "totali≥5 ma venue<3" (dove MIN_CTX=3 usa MENO dati del blend overall). | Low | Sanity check, non re-design. |

**Da NON mettere nel piano** (differiti per vincolo no-cambio-strategia): DC-MLE congiunto come fonte forze/baseline, modello gerarchico Baio-Blangiardo, GAS/Kalman/state-space (guadagno vs Poisson-già-time-weighted ≈ 0-3% RPS, spesso non significativo — Ley dimostra che un semplice Poisson time-weighted raggiunge già l'ottimo).

---

### Fonti chiave citate (coi numeri)
- **Dixon & Coles (1997)**, Applied Statistics 46(2):265-280 — ρ≈-0.13, τ low-score, MLE pesato ξ.
- **Ley, Van de Wiele, Van Eetvelde (2018/2019)**, arXiv:1705.09575 — half-period ottimale **390gg** (Biv Poisson RPS **0.1953**) / **360gg** (Indip Poisson RPS **0.1954**), EPL 2008-2018.
- **Heuer et al.** — autocorrelazione goal-diff **piatta intra-stagione** (forza ~costante entro stagione, cambia tra stagioni).
- **Mead, O'Hare, McMenemy (2023)**, PLoS One 18(4):e0282295 — Brier **58.6 (xG)** vs **59.7 (gol)**, benchmark Bet365 57.2; 8/10 top model usano xG.
- **Beat the Bookie (2021)** — xG vs gol futuri: r=**0.574** vs **0.47**; MSE 0.2013 vs 0.2925 (Premier).
- **Wilkens (2026)**, Sage 22150218261416681 — isotonic: ROI **~1%→~10%**; log-loss modello **1.25** vs mercato **1.41**; xG lookback n=3.
- **Karlis & Ntzoufras (2003)** — λ3≈0.05, |r|<0.05; dipendenza migliora previsione pareggi/BTTS.
- **Koopman & Lit (2015)**, JRSS-A 178(1) — dynamic biv Poisson, ROI positivo EPL 2010-12.
- **Efron-Morris (1975) / Baio-Blangiardo (2010)** — shrinkage EB ottimale k=σ²/τ²; gerarchico Bayesiano (differito).
- **Constantinou-Fenton (2012)** / **Wheatcroft (2019)** — RPS metrica ordinale corretta; ma Ignorance/log-score può essere preferibile per betting.

**Bottom line:** motore corretto (6.5/10 vs SOTA), zero bug di calcolo, ma **non profittevole perché non batte la closing line (CLV≈0)**. L'unica leva interna ad alta evidenza è la **calibrazione isotonica (T1)**; tutto il resto del raffinamento Poisson è cosmetico. Il vero collo di bottiglia è **esecuzione/CLV/informazione differenziale**, non la matematica del modello.
