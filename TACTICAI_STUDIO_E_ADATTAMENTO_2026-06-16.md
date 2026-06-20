# TacticAI — Studio approfondito + adattamento al nostro sistema (Terzo Motore)
**Data:** 2026-06-16 · Fonti primarie: Nature Communications 2024 (DOI 10.1038/s41467-024-45965-x), full text open PMC10951310, DeepMind blog, preprint arXiv:2310.10553.

> Obiettivo del documento: estrarre OGNI formula e OGNI idea di **come TacticAI predice gli eventi**, e mappare ciascuna sul nostro problema (predizione esiti calcio per betting Betfair). Non è una GNN da copiare: è un **metodo di predizione** da adattare. Il terzo motore sarà standalone (non tocca i 2 motori certificati), vedi decisione 2026-06-15.

---

## PARTE 1 — COSA FA TACTICAI (fatti)

Sistema DeepMind + Liverpool FC che assiste sui **calci d'angolo**. Predittivo + generativo. Tre domande:
1. **Chi riceve** il corner (receiver prediction).
2. **Ci sarà un tiro?** (shot/threat prediction).
3. **Generazione guidata**: ridisegnare le posizioni dei giocatori per ottimizzare l'esito.

**Dati:** 7.176 corner (da 9.693, scartati 2.517 invalidi), Premier League 2020-21 (+21-22, 22-23), tracking 25 fps, split 80/20. **Pochissimi dati** (~10 corner/partita) → tutta l'architettura è pensata per la **data-efficiency**.

**Risultati chiave:**
- Receiver: **top-3 accuracy 0.782 ± 0.039**.
- Shot: F1 **0.52** (diretto) → **0.68** (decomposto via receiver) → **0.71 ± 0.01** (con simmetria D₂).
- Studio esperti (5 rater Liverpool): generati **indistinguibili** dai reali (F1 rater 0.60, p>0.05); retrieval recall **0.59 vs 0.36** baseline (p<0.05); rifinitura tattica **90%** giudicata favorevole (p<0.001).
- Esempio counterfactual: aggiustamento difensivo abbassa P(tiro) da **0.75 ± 0.14 → 0.69 ± 0.16** (p<0.001).

---

## PARTE 2 — COME PREDICE (architettura + TUTTE le formule)

### 2.1 Rappresentazione a grafo
- **Nodi V**: 22 giocatori (entrambe le squadre). "Anonimi": contano solo gli attributi.
- **Feature nodo**: posizione XY, velocità XY, altezza, peso, indicatore possesso palla.
- **Grafo completamente connesso**: `E = V × V` (ogni coppia può interagire — conta la **relazione**, non la distanza assoluta).
- **Feature arco** `e_vu`: one-hot binario **compagno/avversario**.
- **Feature globali g** (dipendono dal task): receiver→nessuna; shot→ID receiver (one-hot); generazione→indicatore tiro + ID receiver.
- **Preprocessing**: posizioni zero-centrate e normalizzate su pitch **10 m × 10 m**, velocità riscalate; altezza/peso default 180 cm / 75 kg, scalati /100.

### 2.2 GNN = GATv2 (message passing con attenzione)
MPNN generico — **Eq (2)**:
```
h_u^(t) = φ( h_u^(t−1) , ⊕_{v∈N_u} ψ(h_u^(t−1), h_v^(t−1), e_vu, g) )
```
Refactor attentivo — **Eq (3)**:
```
h_u^(t) = φ( h_u^(t−1) , ⊕_{v∈N_u} a(h_u^(t−1), h_v^(t−1), e_vu, g) · ψ(h_v^(t−1)) )
```
Coefficienti di attenzione GATv2 — **Eq (4)**:
```
a(h_u, h_v, e_vu, g) = softmax_{v∈N_u} ( aᵀ · LeakyReLU( W₁ h_u + W₂ h_v + W_e e_vu + W_g g ) )
```
con W₁,W₂∈ℝ^{k×h}, W_e∈ℝ^{l×h}, W_g∈ℝ^{m×h}. **Config**: 4 layer group-conv (base GATv2), **8 teste**, 4 feature latenti/giocatore.

### 2.3 Geometric deep learning — simmetria D₂ (il cuore della data-efficiency)
Gruppo **G = D₂ = {id, ↔, ↕, ↔↕}** (diedrale, simmetrie a quadrante del campo). L'esito (chi riceve, se c'è tiro) **non cambia** sotto riflessione del campo.

Invarianza delle etichette — **Eq (5)**: `y(g(X), g(E), g(g)) = y(X, E, g)`.

**Frame averaging** (per task invarianti) — **Eq (6)**:
```
f_inv(X,E,g) = (1/|G|) · Σ_{g∈G} f_G( g(X), g(E), g(g) )
```
→ tutte le versioni trasformate (l'"orbita" dell'input) danno **esattamente lo stesso output**.

Condizione di **equivarianza** (per task generativi) — **Eq (7)**: `g_G(g(H), g(E), g(g)) = g( g_G(H,E,g) )`.

**Group convolution** (mantiene una matrice latente per vista) — **Eq (8)**:
```
H_g^(t) = (1/|G|) · Σ_{h∈G} g_G( H_h^(t−1) ‖ H_{g⁻¹h}^(t−1) )
```

Decoder receiver — frame avg **Eq (9)**: `H_node = (H_id + H_↔ + H_↕ + H_↔↕)/4` → linear → 22 logit → softmax + **cross-entropy**.
Decoder shot — readout **Eq (10)**: `h_graph = (1/22) Σ_{u=1}^{22} h_u^node` → linear → 1 logit → sigmoid **BCE**.

> **Perché funziona** (citazione): "Geometric deep learning ensures that TacticAI's player representations will be identically computed under such reflections, such that this symmetry does not have to be learnt from data… as high-quality tracking data is often limited." Imporre la simmetria **nell'architettura** (non come data augmentation) riduce i parametri effettivi → meno overfit → generalizza con pochi dati.

### 2.4 I tre task

**Task 1 — Receiver (node classification).** Etichetta = primo giocatore a toccare palla. 22-vie softmax + categorical cross-entropy. Top-3 0.782.

**Task 2 — Shot (decomposizione condizionata) — Eq (1):**
```
P(shot | corner) = Σ_i P(shot | receiver=i, corner) · P(receiver=i | corner)
```
**L'idea centrale:** invece di predire l'evento finale **direttamente** (F1 0.52), lo si predice **attraverso una quantità intermedia** che si sa stimare bene (il receiver). Il receiver predittore alimenta lo shot predittore (ID receiver come feature globale) → F1 0.68 → 0.71 con D₂. "Encodes significantly more signal than the unconditional shot predictor."

**Task 3 — Generazione guidata (CVAE).** Latente per-giocatore h_u; condizionato su `o = (indicatore tiro, ID receiver)`; il decoder produce μ_u, σ_u per giocatore; campionamento con reparmeterization `x_u = μ_u + σ_u ⊙ ε_u`, ε~N(0,1). ELBO — **Eq (11)**:
```
L(θ,φ) = − E_{h_u~q_θ}[ log p_φ(x_u | h_u, o) ] + KL( q_θ(h_u | X,o) ‖ p(h_u | o) )
```

**Task 4 — Counterfactual / what-if.** Si fissano gli avversari, si modifica una squadra, si **ri-predice** P(tiro): se la modifica è sensata la probabilità si muove in modo sensato (0.75→0.69). È il modo in cui validano e usano il sistema.

---

## PARTE 3 — I 4 PRINCIPI TRASFERIBILI → adattamento al NOSTRO sistema

> Il nostro task è diverso: predire **esiti 1X2/OU/BTTS/HT** vs una **quota di mercato efficiente** (Brier mkt ~0.20). Rumore altissimo, segnale minuscolo. Quindi NON copiamo la GNN sui corner: copiamo **il metodo**. La metrica di successo è **calibrazione + CLV/ROI out-of-sample**, mai accuracy. I principi servono perché **riducono la varianza delle stime** — esattamente ciò che alimenta l'optimizer's curse diagnosticata.

### Principio 1 ⇒ **Predire i GOL e DERIVARE i mercati** (analogo Eq 1)
TacticAI non predice l'evento finale ma lo **marginalizza** su un latente coerente. Il nostro latente coerente è la **matrice dei punteggi** `P(x,y)` (gol casa = x, gol trasferta = y), generata da un **Poisson bivariato Dixon-Coles**:
```
P(x,y) = τ(x,y; ρ) · Poisson(x; λ_home) · Poisson(y; λ_away)
λ_home = exp( μ + h + att_home − def_away )
λ_away = exp( μ +     att_away − def_home )
```
(τ = correzione DC sui punteggi bassi 0-0,1-0,0-1,1-1; h = vantaggio campo). **Tutti i mercati = somme di celle**, quindi coerenti per costruzione:
- 1X2: `P(1)=Σ_{x>y}P(x,y)`, `P(X)=Σ_{x=y}`, `P(2)=Σ_{x<y}`
- Over 2.5: `Σ_{x+y>2}`; BTTS: `Σ_{x≥1,y≥1}`; clean sheet, team totals, HT, correct score, double chance, DNB… **gratis**.

**Effetto:** ~2 parametri/squadra invece di 60×19 classificatori → bias-variance enormemente migliore; addestramento su **scoreline** (likelihood generativa, time-decay) invece di N cross-entropy indipendenti. **Abbiamo già `poisson_xg_hybrid_dc`** (zero bug): il terzo motore lo prende come **nucleo** e lo professionalizza.

### Principio 2 ⇒ **Grafo relazionale della LEGA** (analogo GATv2/Eq 2-4)
TacticAI impara **relazioni** tra nodi, non feature isolate, e i nodi "anonimi" (solo attributi) → niente memorizzazione di identità. Per noi:
- **Nodi = squadre**, **archi = partite** (time-decayed), feature nodo = forma recente, xG for/against, riposo, ecc., feature arco = competizione/derby/casa-trasferta.
- Un **GNN message-passing** propaga forza lungo la rete: una squadra con poche partite **prende in prestito forza statistica** dai vicini (Elo appreso). Output = embedding **(att_i, def_i)** per squadra → alimentano λ del Poisson (Principio 1).
- **Anonimizzare le squadre** (solo embedding+feature) come TacticAI anonimizza i giocatori → blocca l'overfit sui nomi.
- Realizza il **pooling gerarchico cross-lega** (Fase 4 diagnosi) in forma appresa end-to-end: UN modello con embedding squadra+lega, non N modelli per-lega. Abbatte il requisito EPV ~1.800 match/lega che oggi qualifica solo 24% delle leghe.

### Principio 3 ⇒ **Simmetria CASA/TRASFERTA = frame averaging** (analogo D₂/Eq 6,9) — **arma anti optimizer's-curse**
La simmetria del campo per TacticAI è D₂; la nostra è lo **scambio casa↔trasferta** (gruppo Z₂, |G|=2). Fisica: scambiando le due squadre e azzerando il vantaggio campo, la distribuzione gol deve scambiarsi: la forza att/def di una squadra **non dipende dal lato**, l'unico termine asimmetrico è **h** (vantaggio campo), parametro **unico e condiviso**.

**Frame averaging (la nostra Eq 6 con |G|=2):**
```
p_finale = ½ · [ f(A_casa, B_fuori)  ⊕  swap( f(B_casa, A_fuori) ) ]
```
si impone l'equivarianza `f(swap(X)) = swap(f(X))`. Benefici, mappati 1-a-1 sulla diagnosi:
- forza att/def **invariante al lato** → niente parametri ridondanti per-lato → meno overfit;
- **dimezza la varianza** delle stime di forza (media sull'orbita) = la stessa data-efficiency di TacticAI;
- **riduce la sovra-dispersione** delle prob (la diagnosi: il modello sputa prob 3%-96% mentre la realtà è 36-64%). Meno varianza → meno code gonfiate → **più piccolo il gap che l'optimizer's curse sfrutta** (edge>40% → ROI −16.8%). Questo principio **attacca la causa radice**, non la maschera.

### Principio 4 ⇒ **Validazione controfattuale come GATE** (analogo Task 4)
TacticAI valida col what-if (muovi giocatore → P(tiro) cambia sensatamente). Noi trasformiamo i counterfactual in **test automatici di accettazione del modello** (oltre walk-forward + CLV):
- indebolisci l'attacco di una squadra (↓att_i) ⇒ `P(vittoria)` **deve** scendere monotòna;
- campo neutro (h=0) ⇒ sparisce il vantaggio casa;
- scambia att/def di due squadre ⇒ le predizioni si scambiano.
Se un target **non** reagisce così è curve-fitting / edge finto ⇒ **non viene servito** (gate causale, più forte del solo BSS≥0.12).

### Bonus trasferibili
- **Decomposizione condizionata (Eq 1)** oltre i gol: P(primo gol), P(clean sheet), HT/FT — tutte derivate dalla stessa `P(x,y)`, coerenti.
- **CVAE (Eq 11)** → analogo: **generatore di scenari/scoreline** coerenti per mercati esotici (correct score, HT/FT) e per simulazione in-play; campionamento con reparmeterization.
- **Group conv (Eq 8)** se un giorno aggiungiamo simmetrie extra (es. invarianza alla permutazione delle squadre nel grafo, già nativa nei GNN).

---

## PARTE 4 — ARCHITETTURA PROPOSTA DEL TERZO MOTORE (standalone)

**Nome di lavoro:** *GSG — Generative Symmetric Graph engine.* Pipeline end-to-end:
1. **Costruzione grafo lega** (squadre=nodi, partite=archi time-decayed `w_t = exp(−ξ(t₀−t))`, half-life ~360 gg).
2. **Encoder GNN (GATv2)** → embedding **(att_i, def_i)** per squadra + embedding lega (pooling). Anonimizza le squadre.
3. **Wrapper di frame averaging Z₂ casa/trasferta** attorno alla mappatura forza→λ; **h** unico parametro globale.
4. **Testa generativa Dixon-Coles** → `λ_home, λ_away` → matrice `P(x,y)` (con τ DC, ρ per-lega shrink-EB, blend xG η≈0.6 come nel motore esistente).
5. **Derivazione di TUTTI i mercati** come somme di celle (coerenti).
6. **Calibrazione isotonic walk-forward** su blocco temporale separato.
7. **Gate counterfactual + CLV** (Principio 4): scommette solo dove coerente e CLV>0.

**Training:** massimizzare la **likelihood delle scoreline osservate** (target generativo) con pesi time-decay — NON cross-entropy per-mercato. Una sola loss generativa → tutti i mercati gratis e coerenti.

**Dati disponibili (verificati):** 1.392.895 partite giocate (scoreline ✓), identità squadre ✓, date per time-decay ✓, xG parziale ✓, HT ✓. Tutto ciò che serve al modello generativo c'è.

**Avvertenza onesta (dalla diagnosi):** TacticAI predice eventi a basso rumore (quasi-fisica); noi vs mercato efficiente = alto rumore. I principi 1-3 **riducono la varianza** (curano l'optimizer's curse, rendono il modello calibrato e coerente) ma **non garantiscono profitto**: l'edge reale va cercato dove CLV>0 (nicchie illiquide/prezzi early). Il guadagno è una caccia (Fase 5), non un parametro.

---

## PARTE 5 — Mappa formula → uso
| TacticAI | Formula | Nostro uso |
|---|---|---|
| Decomp. condizionata | Eq (1) | Predire gol → derivare 1X2/OU/BTTS/… da `P(x,y)` |
| GATv2 attention | Eq (2-4) | Encoder grafo-lega → embedding att/def per squadra |
| Frame averaging | Eq (6),(9) | Simmetria casa/trasferta (Z₂) → −varianza, −optimizer's curse |
| Equivarianza | Eq (7) | `f(swap)=swap(f)` come vincolo del wrapper simmetrico |
| Group conv | Eq (8) | Estensione a simmetrie extra (opzionale) |
| Readout grafo | Eq (10) | Pooling embedding squadre → forza-lega |
| CVAE / ELBO | Eq (11) | Generatore scoreline per mercati esotici / in-play |
| Counterfactual | Task 4 | Gate causale di accettazione modello |

## Fonti
- Wang, Z., Veličković, P., Hennes, D. et al. *TacticAI: an AI assistant for football tactics.* Nature Communications 15, 1906 (2024). DOI 10.1038/s41467-024-45965-x
- Full text open: https://pmc.ncbi.nlm.nih.gov/articles/PMC10951310/ · Preprint: https://arxiv.org/pdf/2310.10553 · Blog: https://deepmind.google/blog/tacticai-ai-assistant-for-football-tactics/
- Background metodo: frame averaging (Puny et al., arXiv:2110.03336); GATv2 (Brody et al., "How Attentive are GATs?").

---

## PARTE 6 — VERIFICA FONTI UFFICIALI (2026-06-20)
Rilette direttamente: full-text PMC10951310, preprint via ar5iv (arXiv:2310.10553, appendice + Table S1/S2), blog DeepMind. Il documento sopra è **confermato corretto**. Qui i dettagli precisi estratti/corretti dalle fonti.

### 6.1 Iperparametri EFFETTIVAMENTE selezionati (Table S1) — non solo la griglia di ricerca
| Task | Tipo | GAT layers | Batch | LR | L2 (weight decay) |
|---|---|---|---|---|---|
| Receiver | node classification | **4** | 256 | 1e-4 | 1e-4 |
| Shot | graph classification | **2** | 128 | 1e-4 | 0.0 |
| Guided generation | node regression | **2** | 128 | 5e-5 | 1e-4 |

- **CORREZIONE** al §2.2 sopra: i 4 layer NON sono universali — solo il receiver usa 4 layer (T=4 message-passing); shot e generazione usano **2 layer** (T=2). 8 teste di attenzione e 4 feature latenti/giocatore restano confermati per tutti.
- Optimizer **Adam** (β₁=0.9, β₂=0.999, ε=1e-8). **50.000 training steps** (benchmark receiver). Seed fisso **42**. Hardware **NVIDIA Tesla P100**.
- Loss: **categorical cross-entropy** per i classificatori (receiver, shot), **MSE** per i regressori (generazione/VAE).
- Encoder GATv2 **identico nell'architettura ma con parametri NON condivisi** tra i 3 task; decoder task-specifici. (Conferma il nostro disegno: nucleo comune, teste separate.)

### 6.2 Tabella di ablazione (Table S2) — receiver top-3 accuracy
| Modello | Top-3 acc |
|---|---|
| CNN | 0.364 ± 0.031 |
| Deep Sets (no grafo) | 0.713 ± 0.022 |
| MPNN | 0.723 ± 0.017 |
| GATv2 (no D₂) | 0.748 ± 0.021 |
| GATv2 + D₂ **frame averaging** | 0.780 ± 0.011 |
| **GATv2 + D₂ group convolution** | **0.782 ± 0.039** (best) |

**Lettura per noi:** il salto grosso è grafo-vs-non-grafo (Deep Sets 0.713 → quasi tutto il guadagno dalla struttura relazionale, +35 punti su CNN); D₂ aggiunge ~3 punti finali e soprattutto **abbassa la varianza** (frame averaging σ 0.011, il valore più stabile). Conferma: la simmetria serve più per **stabilità/varianza** che per accuracy pura → esattamente la leva che ci serve contro l'optimizer's curse.

### 6.3 Dimensioni feature (precise)
- **Nodo k=7/giocatore**: posizione XY (2) + velocità XY (2) + altezza (1) + peso (1) + possesso-palla binario (1).
- **Arco l=1**: one-hot binario compagno/avversario.
- **Globale m**: task-dependent (receiver→∅; shot→ID receiver one-hot; generazione→ID receiver + indicatore tiro).
- Preprocessing: pitch reale **110m×63m** (default se mancante) → normalizzato **10m×10m**, zero-centrato sul punto del corner; velocità riscalate in proporzione. Default altezza/peso **180cm/75kg** (385 casi su 213.246). Anonimizzazione totale dei giocatori.

### 6.4 D₂ — dettagli che mancavano
- |𝔊|=4, e **tutte le riflessioni sono auto-inverse** (𝔤=𝔤⁻¹) → semplifica la group conv Eq(8).
- La riflessione orizzontale ↔ **nega la componente x della velocità** (non solo la posizione): la trasformazione agisce coerentemente su pos+vel.
- Task **invarianti** (receiver, shot) → frame averaging su **tutte e 4 le viste**. Task **equivariante** (generazione) → si usa **solo la vista identità** (peso 1.0, le altre azzerate). *Nota per noi:* il nostro caso Z₂ casa/trasferta è invariante per i mercati simmetrici (esito = distribuzione gol che si scambia) → si usa il frame averaging completo, come receiver/shot.

### 6.5 Risultati — numeri canonici + discrepanza onesta
- Receiver top-3 **0.782 ± 0.039**. Esperti umani top-3 0.79±0.18 (reali) / 0.77±0.21 (generati), nessuna differenza significativa.
- Shot: F1 **0.52 ± 0.03** (diretto) → **0.68 ± 0.04** (decomposto, GATv2) → **0.71 ± 0.01** (+D₂) nella narrativa Nature. ⚠️ Il **preprint riporta F1 0.64 ± 0.02** come modello condizionato di riferimento — discrepanza versioni: usare 0.52→0.68→0.71 come progressione qualitativa (il *messaggio* — la decomposizione condizionata + simmetria migliorano nettamente — è robusto in entrambe).
- Generazione: classificatore reale-vs-generato **F1 0.53 ± 0.05** (= caso, indistinguibili) su 200 campioni; aggiustamento difensivo P(tiro) **0.75±0.14 → 0.69±0.16** (z=2.62, p<0.001); aggiustamento offensivo **0.18±0.16 → 0.31±0.26** (z=−4.46, p<0.001).
- Retrieval: recall **0.63 ± 0.09** vs baseline cosine raw-feature **0.33 ± 0.10**. Esperti: 90% rifiniture giudicate favorevoli (mean rating 0.7±0.1, t₄₉≈9.20 p<0.001). 5 rater = 3 data scientist + 1 video analyst + 1 coaching assistant.
- Dataset: 9.693 → filtrati 2.517 invalidi → **7.176 corner** (1.736 con tiro / 5.440 senza ≈ 24% positivi), split 80/20, Premier League. Definizione shot: direct corner, goal, aerial, palo, parata, fuori.

### 6.6 Cosa cambia (o NON cambia) per il nostro terzo motore — sintesi della verifica
1. **Layer per task variabili** (4/2/2): per noi è irrilevante a livello di nucleo DC, ma è la conferma che il loro encoder è **piccolo e regolarizzato** (data-efficiency = parametri pochi + simmetria imposta, non profondità). Il nostro encoder grafo-lega deve restare **shallow** (2-4 layer GATv2 max), non grosso.
2. **Il guadagno di D₂ è soprattutto varianza** (σ 0.011): rinforza al 100% il Principio 3 (frame averaging Z₂ casa/trasferta) come arma anti optimizer's-curse — verificato numericamente, non solo teorico.
3. **Frame averaging completo** (tutte le viste) è il regime corretto per i nostri mercati simmetrici (caso invariante). Confermato.
4. **Encoder condiviso in architettura ma non in parametri** + teste task-specifiche: per noi, un nucleo grafo→(att,def) condiviso che alimenta la **singola testa generativa DC** (da cui derivano TUTTI i mercati) è ancora più semplice del loro (loro avevano 3 teste, noi 1 testa generativa + derivazioni analitiche).
5. Nessuna formula del documento §2-§3 va corretta: Eq(1)-(11) confermate verbatim dalle fonti.

---

---

## PARTE 7 — INVENTARIO DATI REALI (verificato dal vivo 2026-06-20) + adattamento ai NOSTRI dati

### 7.1 Volumi reali (conteggi stimati da pg_class; coperture da sondaggio campione)
| Tabella | Righe (~) | Cosa contiene / rilievo per il modello |
|---|---:|---|
| `matches` | **1.467.901** | Anagrafica + **scoreline FT/HT** (gol casa/trasferta, primo tempo). **Gol e HT: 100% copertura** sul campione. È il TARGET generativo. |
| `match_odds` | **80.008.445** | Quote multi-bookmaker × mercati × snapshot. Copertura top-lega ~96% (48/50). Books: Bet365, **Pinnacle**, **Bet365_closing** (=quote chiusura → CLV!), William Hill, BW, IW, VC Bet, Maximum, Average. **NESSUN "Betfair"** qui (stream Betfair è sistema a parte). |
| `match_lineups` | **25.792.451** | Formazioni: titolari/panchina, ruolo (G/D/M/F), griglia tattica, coach. → disponibilità/forza rosa. |
| `match_events` | **9.783.117** | Eventi con minuto: gol, cartellini, sostituzioni, VAR. → label temporali (primo gol, gol per intervallo). |
| `match_team_stats` | **6.549.656** | Stat squadra/partita: tiri, tiri in porta, tiri in area, **corner**, possesso, falli, cartellini, parate. **NO xG** nel campione. |
| `match_player_stats`| **5.635.489** | Stat individuali (rating, tiri, passaggi, dribbling, duelli…). |
| `injuries` | 157.086 | Infortuni/squalifiche per fixture. → aggiustamento forza. |
| `standings` | 98.349 | Classifiche (stagioni **2010–2027**). |
| `top_scorers / top_assists / top_cards` | 86k / 28k / 216k | Classifiche marcatori/assist/cartellini per lega-stagione. |
| `fixture_predictions` | (conteggio in timeout) | Predizioni API-Football (percentuali 1X2, advice, goals_home/away_line). |

### 7.2 Copertura critica (sondaggio mirato)
- **Gol FT + Halftime: 100%** (300/300 campione 2023). → il nucleo Dixon-Coles è alimentabile su TUTTO lo storico.
- **xG: assente/trascurabile** — 0/50 su Premier/SerieA/Liga 2023; "Expected Goals" non compare tra gli stat_type campionati. ⚠️ **Decisione di progetto: il terzo motore NON deve dipendere da xG** (rimuovere il blend η≈0.6 con xG previsto in PARTE 4, o renderlo opzionale solo dove presente). Memoria storica confermava "xG parziale".
- **Quote di chiusura presenti** (Bet365_closing, Pinnacle) sulle leghe principali → **CLV misurabile direttamente** dal DB, senza dipendere dallo stream Betfair. Questo abilita la metrica-verità (Principio onesto: l'edge è caccia al CLV).
- **NO tracking giocatori** (posizioni/velocità XY): l'input grezzo di TacticAI non esiste → si trasferisce il METODO, non la GNN sui corner. Confermato.

### 7.3 Distribuzione partite per lega (da `_league_played_by_season.json`, 1.392.895 partite, 1229 leghe)
| #partite giocate | #leghe |
|---|---:|
| ≥1800 | 296 |
| 800–1799 | 261 |
| 300–799 | 201 |
| 100–299 | 169 |
| 50–99 | 87 |
| <50 | 215 |

Mediana **602 partite/lega**; **1014 leghe idonee** (≥50). → Le ~557 leghe "ricche" (≥800) reggono un Dixon-Coles per-lega; le ~471 leghe magre (<300) sono **esattamente il caso TacticAI** (pochi dati) → giustificano l'**embedding gerarchico cross-lega** (le piccole prendono forza statistica dalle grandi).

### 7.4 Mappa: input TacticAI → nostro dato reale equivalente
| TacticAI (corner) | Nostro analogo disponibile |
|---|---|
| Nodo = giocatore, feature pos/vel XY | **Nodo = squadra**, feature = forma, media gol for/against, tiri/corner (da `match_team_stats`), riposo (da date), disponibilità rosa (da `injuries`+`match_lineups`) |
| Arco = relazione compagno/avversario | **Arco = partita giocata** (scoreline) con peso time-decay `exp(−ξΔt)` |
| Etichetta = ricevitore/tiro | **Etichetta = scoreline osservata** (x,y gol) → likelihood DC |
| Simmetria D₂ campo | **Simmetria Z₂ casa/trasferta** (frame averaging) |
| xG / tracking | **NON disponibile** → sostituito da proxy creazione-tiri (tiri, tiri in area, corner) dove servono |
| Validazione what-if | Gate counterfactual + **CLV vs Pinnacle/closing** (dato presente) |

### 7.5 Architettura aggiornata alla luce dei dati
Confermata la pipeline GSG di PARTE 4, con queste modifiche dettate dai dati reali:
1. **Drop dipendenza xG**: λ del Dixon-Coles stimati da gol + (opzionale) proxy tiri/corner dove esistono, NON da xG.
2. **Encoder cross-lega gerarchico raccomandato** (non N modelli per-lega): dato che 471 leghe hanno <300 partite, l'embedding lega+squadra condiviso è la leva data-efficiency diretta dal paper.
3. **CLV nativo**: usare `Bet365_closing`/`Pinnacle` come prezzo di chiusura per il gate (no dipendenza dallo stream Betfair per la validazione del motore).
4. **PoC invariato** ma ora eseguibile su dati certi: DC + frame-averaging Z₂ su 2–3 leghe top (scoreline 100% + closing odds) → misurare calibrazione (Brier/log-loss) **e CLV** vs Pinnacle chiusura, PRIMA di costruire l'encoder GNN.

---

## Stato
- [x] Studio TacticAI completo (architettura + tutte le formule estratte)
- [x] Mappatura 4 principi → nostro sistema con formule
- [x] Architettura terzo motore GSG proposta
- [x] **Verifica su fonti ufficiali (2026-06-20): PMC full-text + preprint ar5iv (Table S1/S2) + blog DeepMind. Iperparametri selezionati, ablazione, dimensioni feature estratti; 1 correzione (layer per-task 4/2/2). Formule Eq(1)-(11) confermate.**
- [ ] Validare numericamente il nucleo DC+frame-averaging su 2-3 leghe (walk-forward + CLV) prima di costruire l'encoder GNN
- [ ] Decidere granularità encoder (per-lega vs cross-lega globale) e budget training cloud
