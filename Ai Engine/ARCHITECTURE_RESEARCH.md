# Architettura ottimale multi-lega — ricerca SOTA + audit del codice

> 2026-06-09. Domanda: qual è l'architettura più avanzata per predire ~1200 leghe
> con dati molto disuguali (grandi: 350+ match/stagione × 10 anni; piccole/amichevoli:
> ~100/anno o storia sparsa), massimizzando potenza predittiva e calibrazione,
> soprattutto sulle leghe povere? Sotto: conclusione SOTA + cosa costa nel NOSTRO codice.

## Conclusione (SOTA)
Il limite non è "quante stagioni" diamo a ogni modello: è che oggi alleniamo **1200 modelli
isolati che non comunicano**. Una lega piccola vede solo sé stessa → overfitta. La soluzione
vincente in letteratura è far sì che le leghe povere **"prendano in prestito forza"** dalle
ricche. Tre famiglie:

1. **Per-lega isolati (stato attuale)** — buoni dove ci sono dati, falliscono per costruzione su 1000+ leghe povere.
2. **Modello GLOBALE unico** con `league_id` come feature → massimo campione; le leghe piccole beneficiano di tutto il calcio mondiale. È l'approccio del **vincitore della 2017 Soccer Prediction Challenge** (Berrar et al., 216k match, 52 leghe: UN solo modello cross-lega, non uno per lega).
3. **Gerarchico / partial pooling** (effetti lega con shrinkage verso media globale) — la risposta teoricamente corretta; MCMC su 1200 leghe è proibitivo su macchina consumer → si approssima dentro un GBM globale.

## I 3 ingredienti del sistema migliore
1. **Backbone globale GBM** (LightGBM/CatBoost) — un modello per mercato (1x2/OU/BTTS) su TUTTE le leghe; `league_id` gestito con shrinkage categorico (`cat_smooth`/`cat_l2`) o **target-encoding gerarchico bayesiano** (confederazione→paese→lega): una lega oscura eredita la media del suo gruppo.
2. **Rating di forza-squadra GLOBALE (Elo/SPI cross-lega)** — la singola decisione a più alto ROI. Rating offensivo+difensivo in gol su scala mondiale; la forza-lega si stima dai **match inter-lega** (coppe continentali, amichevoli) regredita verso il valore di mercato (metodo 538/SPI). Posiziona automaticamente lega oscura/nazionale sulla scala globale.
3. **Calibrazione per-tier/per-lega sopra il backbone** — la calibrazione locale è ciò che rende redditizio un modello globale (studio Bundesliga: ROI da ~1% a ~10-15% con isotonic per-outcome su finestra 2 stagioni).

## Cosa costa nel NOSTRO codice (audit)
| Opzione | Cosa blocca | Effort | Rischio | Riusa codice |
|---|---|---|---|---|
| **A. Stagioni adattive per lega** | niente (la query c'è già) | **S** (<1g) | basso | 100% |
| **B. Modello globale unico** | training/registry/standings sono per-lega; serve audit anti-leakage sulle feature rolling | **M** (3-5g) | medio-alto | ~80% |
| **C. Pooling per tier** | manca metadata tier/confederazione; rischio "bleed" tra leghe | **L** | alto | ~60% |
| **D. Elo globale cross-lega** | servono match-ponte (amichevoli/coppe) nel DB | **S-M** | medio | 100% |
| **E. Backbone globale + ricalibrazione per-lega** | richiede prima B | **M** | medio | ~90% |

**Scoperte chiave dell'audit:**
- **ELO è GIÀ global-capable** (`elo_ratings.py`: nessun reset per-lega; team_id globali) → l'ingrediente #2 è a portata di mano.
- **Form e H2H sono già league-agnostic** (calcolati dallo storico); H2H cross-lega sarebbe persino più ricco.
- **Le standings sono l'unica feature per-lega** → già rimosse (erano il leakage). Le window stats coprono il segnale.
- Andando globale: da ~1200 modelli a ~20 → storage/serving molto più semplici; si perde il tuning per-tier (mitigato dalla calibrazione per-lega).
- Rischio principale di B: le feature rolling (form/Elo) NON isolano esplicitamente la lega → con un dataset globale serve disciplina per non mischiare male le finestre (audit anti-leakage obbligatorio).

## Raccomandazione (decisa, ordinata per ROI/rischio)
1. **Target architetturale**: **Backbone globale GBM + Elo/SPI globale + calibrazione per-tier.** È "il più avanzato realisticamente costruibile" sulla tua macchina, ed è ciò che farebbe un top practitioner.
2. **Percorso a tappe (per gestire il rischio):**
   - **Tappa 1 (quick win, basso rischio):** Elo globale (già supportato) + stagioni adattive. Migliorano subito il sistema attuale e sono mattoni del globale.
   - **Tappa 2 (il salto):** costruire il backbone globale per mercato + calibrazione per-tier; audit anti-leakage delle feature.
   - **Tappa 3:** validazione testa-a-testa globale vs per-lega su dati reali, poi (eventuale) ricalibrazione per-lega (opzione E).
3. **Conferma strategica:** NON fare il retrain di produzione delle 1200 leghe prima di decidere qui — sarebbe lavoro buttato.

> Caveat fonti: il sito FiveThirtyEight è dismesso; i dettagli SPI vengono da cache/repo dati, non dalla pagina live.

## AGGIORNAMENTO 2026 — verifica con ricerca recente (2022–2026)
Domanda: il GBDT è "roba del 2017" superata? **No, confermato con prove fresche** — e la priorità va RIORDINATA:
- **Il modello giusto resta un GBDT, oggi specificamente CatBoost** (gestione nativa di `league_id`/`team_id` ad alta cardinalità + calibrazione migliore out-of-the-box). NON è inerzia 2017: il campo ha provato seriamente a batterlo e ha fallito sul NOSTRO profilo (CPU, multi-lega, calibrazione):
  - Tabular deep learning (TabM ICLR'25, FT-Transformer, SAINT): al massimo **pareggia** i GBDT, a costo GPU molto più alto (Grinsztajn NeurIPS'22 non ribaltato; Booking.com'24: GBDT regge in produzione).
  - **TabPFN v2** (Nature'25): forte sui dataset piccoli ma tetto 10 classi/10k righe, crolla su scala/dimensione, GPU-first → al più jolly per singole leghe minuscole, non motore.
  - GNN/Transformer per l'ESITO partita: data-hungry, GPU-heavy, nessun ROI dimostrato vs GBDT+feature.
- **La leva n.1 NON è l'architettura, sono le FEATURE** (consenso unanime nel calcio): in ordine di impatto:
  1. **Le quote del mercato (opening line) come feature di input** — è la singola cosa più potente; battere il mercato è il vero benchmark.
  2. **xG / xT** (la feature predittiva più forte dopo le quote).
  3. **Rating di forza-squadra transferibili cross-lega** (Elo/Glicko-2/pi-ratings).
- **Calibrazione per-lega/cluster**: valutare **Dirichlet** (multiclasse 1x2) o Platt al posto dell'isotonica globale; validare con **RPS** e log-loss, non accuracy.
- **Pooling cross-lega** resta avallato (gerarchico bayesiano, "Transfer Portal" 423 leghe): è ciò che salva le leghe povere dall'overfit.

**Verdetto 2026 (riordinato):** *CatBoost cross-lega + feature dominanti (quote di mercato come feature, xG, rating globali) + calibrazione per-lega*. L'architettura globale è l'abilitatore strutturale (soprattutto per le leghe piccole), ma **il grosso dei guadagni viene dalle feature, non dal modello**. Da evitare come hype: transformer/GNN/TabPFN come motore principale.

Fonti aggiuntive: Grinsztajn 2022 (arxiv 2207.08815), TabM ICLR'25 (2410.24210), Booking.com 2024 (2405.13692), TabPFN v2 Nature'25 + "Closer Look" (2502.17361), CatBoost (1810.11363), Dirichlet calibration (NeurIPS'19), survey ML soccer betting 2025 (2410.21484).

## Fonti
- Survey ML soccer prediction: https://arxiv.org/pdf/2403.07669
- Berrar et al. 2017 Challenge (modello unico cross-lega): https://link.springer.com/article/10.1007/s10994-018-5763-8
- GBM + feature optimization: https://arxiv.org/html/2309.14807
- Baio & Blangiardo (gerarchico bayesiano): https://discovery.ucl.ac.uk/16040/1/16040.pdf
- Dixon-Coles time-weighting: https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/
- FiveThirtyEight SPI (cross-league bridging): https://github.com/fivethirtyeight/data/tree/master/soccer-spi
- LightGBM categorical: https://apxml.com/courses/mastering-gradient-boosting-algorithms/chapter-5-lightgbm-light-gradient-boosting/lightgbm-categorical-features
- CatBoost (ordered target encoding): https://arxiv.org/pdf/1706.09516
- Partial pooling/shrinkage: https://m-clark.github.io/posts/2019-05-14-shrinkage-in-mixed-models/
- Bundesliga calibrazione/ROI: https://journals.sagepub.com/doi/10.1177/22150218261416681
- Limiti transfer cross-lega: https://arxiv.org/html/2605.10796v1
