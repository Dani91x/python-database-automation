# Calibrazione probabilistica PER-LEGA: verifica, garanzie e gap

> Briefing tecnico 2026-06-09 (citato). Risponde a: "abbiamo calibrato tutto
> perfettamente?". Verdetto sintetico: l'impianto è **solido e nella media-alta
> dello stato dell'arte, ma NON è "perfetto"** — i punti deboli sono le leghe
> piccole (80–350 match) e i gate a soglia fissa senza intervalli di confidenza.

## Setup attuale
Stacking RF+LGB+XGB+LogReg, meta LogReg. Calibrazione: **temperature scaling**
(T + bias per-classe) per 1x2/HT-FT; **isotonic per-classe** per i binari
(over/under, btts). Calibratori fittati sul validation temporale; Brier/ECE misurati
su holdout temporale separato. Gate: `BSS=1-brier/brier_random ≥ 0.12` ed `ECE ≤ 0.10`.

## 1. Come VERIFICARE la calibrazione per-lega
Sempre sull'**holdout temporale** (mai sui dati di fit del calibratore — già corretto).
- **Reliability diagram** per (mercato × lega): `sklearn.calibration.calibration_curve(y, p, n_bins=10, strategy='quantile')`. **Usare `strategy='quantile'`**: con 80–350 match i bin uniformi restano vuoti agli estremi → punti rumorosi. Per il 1x2 fare un diagramma one-vs-rest per classe.
- **Numeri per lega/mercato**: ECE (≤0.05 ottimo, ≤0.10 accettabile); **Brier**; per il 1x2 meglio il **RPS (Ranked Probability Score)** che rispetta l'ordine degli esiti; **BSS**; e soprattutto la **decomposizione di Murphy** `Brier = Reliability − Resolution + Uncertainty`: la componente **REL** isola la mis-calibrazione (→ ricalibra), **RES** la capacità discriminante (→ se bassa nessuna calibrazione salva il modello).
- "Buono" = curva aderente alla diagonale entro le bande di confidenza, ECE basso, REL≪RES, BSS positivo con IC che esclude lo zero.

## 2. Temperature scaling + isotonic: scelta giusta?
- **Temperature scaling** (Guo et al. 2017): 1 parametro, **non altera l'argmax**, robustissimo su N piccolo → giusto per 1x2/HT-FT. *Limite*: T globale assume mis-calibrazione monotona/uniforme; non corregge curve a S.
- **Isotonic**: non-parametrica, ma la doc sklearn la **sconsiglia sotto ~1000 campioni** (overfitting, gradini, estremi scoperti). Sui binari delle leghe 80–350 match è **il punto più rischioso dell'impianto**.
- **RACCOMANDAZIONE**: per i mercati binari usare **Platt/sigmoid** (`method='sigmoid'`, 2 parametri, robusto) quando N_cal < ~1000 (cioè quasi sempre), riservando l'isotonic alle sole leghe LARGE.

## 3. Problema leghe piccole (80–350 match)
Validation di calibrazione = forse 30–120 partite/mercato → ECE/Brier ad altissima varianza e calibratori che overfittano. Soluzioni (per leva):
1. **Calibrazione cross-validata**: `CalibratedClassifierCV(est, method=..., cv=StratifiedKFold(5), ensemble=True)` — usa tutti i dati, riduce varianza. Su leghe sparse **sempre StratifiedKFold**.
2. **Shrinkage gerarchico / partial pooling** verso un calibratore globale o di tier: `T_lega = (n·T_MLE + τ·T_global)/(n+τ)` (τ≈100). Leghe TINY → tendono al globale; LARGE → al proprio.
3. **Smoothing bayesiano** (prior Beta) sulle frequenze per-bin.
4. **Soglia minima campioni**: se N_cal < 50–80/mercato → niente calibratore dedicato, eredita quello di tier/globale.
5. **Gate più larghi/conservativi** per leghe piccole.

## 4. I gate (BSS≥0.12, ECE≤0.10) sono ben tarati?
Direzione giusta, parametrizzazione migliorabile:
- **(a) Riferimento BSS**: oggi `brier_random=(n-1)/n` (uniforme) → gate "facile". Più onesto usare la **climatologia/base-rate per-lega** (battere le frequenze marginali è il vero test di skill). La 0.12 va ri-tarata se si cambia riferimento.
- **(b) Incertezza campionaria (punto più debole)**: su 100 match il BSS puntuale ha IC amplissimo → un BSS=0.13 può essere rumore (falso positivo del gate) o un buon modello fallire a 0.11 per sfortuna. **RACCOMANDAZIONE**: non confrontare il BSS puntuale con 0.12, ma calcolare un **IC bootstrap** (block-bootstrap temporale ~2000 resample) e richiedere che il **limite inferiore IC90% > 0** oltre a BSS≥0.12. Idem ECE.
- **(c) Soglie tier-dipendenti**: LARGE → ECE≤0.05 + IC_inf(BSS)>0; MEDIUM/SMALL → ECE≤0.10 + IC; TINY → calibratore pooled obbligatorio + se l'IC include 0 **blocca a prescindere**. Friendly/nazionali: gate più conservativo o escluse di default.

## 5. Drift di calibrazione tra stagioni
La calibrazione degrada **prima** della discriminazione sotto shift temporale (rose, allenatori, regole). Monitorare per-lega **ECE/Brier/REL rolling** (finestra 50–100 match); allarme se **REL** cresce con RES stabile → **ri-fit del solo calibratore** (economico). Refit completo solo se RES crolla. Trigger: inizio stagione, finestra sopra soglia, o IC(BSS) che torna a includere 0.

## 6. Protocollo concreto per "provare" la calibrazione per-lega
Per ogni (lega × mercato):
1. Split temporale rigoroso (train→modelli, val→calibratore, holdout→solo misura); leghe piccole → `CalibratedClassifierCV(cv=StratifiedKFold(5))`.
2. Guard numerosità: N_holdout < 50 (binario)/80 (1x2) → non certificare in isolamento, eredita calibratore di tier (shrinkage).
3. Calibratore per tier: TINY/SMALL → temperature(T globale) per 1x2, **sigmoid** per binari; MEDIUM → temperature+bias/sigmoid; LARGE → isotonic ammessa.
4. Calcola su holdout: reliability diagram (quantile), ECE, Brier/RPS, REL/RES/UNC, BSS con **riferimento climatologico**.
5. Quantifica incertezza: block-bootstrap temporale → IC90% su BSS/ECE; correggi bias BSS.
6. Gate tier-dipendenti: abilita mercato **solo se** ECE≤soglia_tier **E** BSS≥0.12 **E** IC_inf(BSS)>0.
7. Anti-overfit: confronta ECE val (fit) vs holdout; gap ampio → forza sigmoid/shrinkage.
8. Registra ECE/REL/BSS+IC per lega/stagione; monitora REL rolling.
9. Friendly/nazionali: conservativo o escludi.

## Verdetto e gap da chiudere (priorità)
L'approccio è corretto. Per renderlo "dimostrabilmente perfetto":
1. **Sigmoid/Platt al posto di isotonic per i binari sotto ~1000 campioni** (oggi rischio overfit su quasi tutte le leghe).
2. **IC bootstrap sul BSS nei gate** (oggi decide su un puntuale rumoroso per le leghe piccole).
3. **Shrinkage gerarchico** verso calibratori di tier per TINY/SMALL.
4. **RPS + riferimento climatologico** per il 1x2.
5. **Monitoraggio REL rolling** per il drift.

> Questi 5 punti NON sono ancora implementati nel codice: sono il prossimo
> incremento per portare la calibrazione da "misurata" a "dimostrata con incertezza".

## Fonti
- scikit-learn — Probability calibration: https://scikit-learn.org/stable/modules/calibration.html
- CalibratedClassifierCV: https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html
- Guo et al. 2017 (temperature scaling): https://arxiv.org/abs/1706.04599
- Understanding Model Calibration (ECE, reliability): https://arxiv.org/html/2501.19047v2
- Estimating Expected Calibration Errors: https://arxiv.org/pdf/2109.03480
- Classifier Calibration: a survey: https://arxiv.org/pdf/2112.10327
- Verification of probability forecasts for football (Brier decomp, RPS): https://arxiv.org/pdf/2106.14345
- Brier score (decomposizione): https://en.wikipedia.org/wiki/Brier_score
- Bradley et al. 2008 (IC su Brier/BSS): https://journals.ametsoc.org/view/journals/wefo/23/5/2007waf2007049_1.xml
- PyMC — multilevel modeling (partial pooling/shrinkage): https://www.pymc.io/projects/examples/en/2022.12.0/case_studies/multilevel_modeling.html
- Temporal dataset shift (calibrazione degrada prima): https://pmc.ncbi.nlm.nih.gov/articles/PMC8410238/
- AI Model Calibration for Sports Betting: https://www.sports-ai.dev/blog/ai-model-calibration-brier-score
