# CHECKPOINT OMEGA V3 — 16/09/2026 (delegato O2)

> Aggiornato a OGNI passo: se i crediti finiscono, chi riprende legge solo questo file.
> Progetto di partenza: `Betfair/omega/PROGETTO_OMEGA_V3_2026-09-16.md`.
> VINCOLO: `omega_service.py` e' di O1 (riconciliazione/chiusure/aggregati): NON TOCCARE
> finche' il coordinatore non dice che O1 ha consegnato.

## Ordine allargato (coordinatore, 16/09 sera)

«Trova tu la soluzione matematica e probabilistica piu' avanzata»: il motore v3 NON e' il
Poisson residuo e basta. Vanno COSTRUITI e CONFRONTATI sui nostri dati, con log-loss/Brier
out-of-sample e calibrazione per decile:

1. Poisson indipendente residuo (base)
2. Dixon-Coles (1997) — correzione rho sulle celle basse (decisiva per l'HT)
3. Dixon & Robinson (1998) — intensita' variabili nel tempo + effetto del punteggio
4. Poisson bivariato (Karlis & Ntzoufras 2003) — solo se i dati lo giustificano
5. aggiornamento bayesiano dei lambda in gioco dai segnali del feed (gol, rossi,
   pressure_index/corner/timeline IPS): il peso si STIMA, non si assume
6. fusione col MERCATO: shrinkage in logit fra P_modello e P_implicita, peso per fascia

Uscita: la proposta di green nasce da una TRAIETTORIA attesa del profitto bloccabile
(EV di tenere vs EV di chiudere), non da una soglia fissa.

## Stato

| passo | descrizione | stato |
|---|---|---|
| 0 | lettura progetto + codice | FATTO |
| 1 | MISURA DI k (`tools/misura_k.py`) -> `data/k_misurato_2026-09-16.json` | **FATTO — risultato sotto** |
| 1b | `K_MISURATO_2026-09-16.md` | FATTO |
| 2 | banco modelli 1-5 (`tools/banco_modelli.py`) + log-loss/Brier OOS | **FATTO — risultato sotto** |
| 2b | banco fusione col mercato (candidato 6, `tools/banco_fusione.py`) | IN CORSO |
| 3 | `omega_v3.py` (funzioni pure) + 41 test falsificati | **FATTO (verde)** |
| 4 | `omega_engine.py`: percorso v3 dietro `strategy_version=3` (default 2) | DA FARE |
| 5 | `certificazione.py` A8-A12/C5/G1/G2 + scenario `v3` nel replay + replay 35760084/35797769 | DA FARE |
| 6 | referto | DA FARE |

## PASSO 1 — RISULTATO DELLA MISURA DI k (il numero che decide il progetto)

Comando riproducibile: `python -m Betfair.omega.tools.misura_k`
Dati: `betfair_market_odds` (58.234 righe CS+HTS, 2.018 fixture) x `matches`
(1.997 esiti; 1.859 partite utili per il CS, 1.645 per l'HT). Quote **PRE-MATCH**.
Intervalli: **bootstrap a grappolo sulle partite** (le selezioni della stessa partita
non sono indipendenti: esce una sola scoreline).

**(a) k al prezzo di LAY realmente disponibile** — `k = p_implicita / p_reale`:

| mercato | secchio p_impl | n | partite | uscite | p_impl | p_reale | k | k prudente |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0-0,2% | 258 | 229 | 2 | 0,0016 | 0,0078 | 0,21 | 0,08 |
| Correct Score | 0,2-0,5% | 1.148 | 656 | 6 | 0,0036 | 0,0052 | 0,68 | 0,36 |
| Correct Score | 0,5-1% | 2.385 | 1.184 | 22 | 0,0071 | 0,0092 | 0,77 | 0,54 |
| Correct Score | 1-2% | 5.079 | 1.773 | 77 | 0,0149 | 0,0152 | 0,98 | 0,80 |
| Correct Score | 2-5% | 10.685 | 1.841 | 458 | 0,0340 | 0,0429 | 0,79 | 0,73 |
| Correct Score | 5-10% | 10.427 | 1.846 | 873 | 0,0705 | 0,0837 | 0,84 | 0,80 |
| Correct Score | >10% | 2.464 | 1.562 | 394 | 0,1403 | 0,1599 | 0,88 | 0,81 |
| Half Time Score | 0,2-0,5% | 281 | 240 | 1 | 0,0038 | 0,0036 | 1,08 | 0,34 |
| Half Time Score | 0,5-1% | 1.039 | 886 | 9 | 0,0071 | 0,0087 | 0,82 | 0,49 |
| Half Time Score | 1-2% | 1.699 | 1.099 | 22 | 0,0149 | 0,0129 | 1,15 | 0,81 |
| Half Time Score | 2-5% | 4.222 | 1.597 | 166 | 0,0331 | 0,0393 | 0,84 | 0,73 |
| Half Time Score | 5-10% | 3.625 | 1.595 | 363 | 0,0751 | 0,1001 | 0,75 | 0,69 |
| Half Time Score | >10% | 5.050 | 1.644 | 1.062 | 0,1793 | 0,2103 | 0,85 | 0,82 |

> **NESSUN SECCHIO E' OPERABILE**: `k prudente <= 1` ovunque. Al prezzo di lay che il book
> offre davvero, bancare la coda pre-match e' in media a EV NEGATIVO. §3.3 del progetto:
> «se nessun secchio supera 1, il progetto non ha edge e va detto».

**(b) k con probabilita' DEVIGATA (mid back/lay normalizzato a 1): la FORMA del bias**

| mercato | secchio p_equa | n | partite | uscite | p_equa | p_reale | k_equo | k_equo prudente |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0,5-1% | 3.855 | 1.391 | 21 | 0,0084 | 0,0054 | **1,53** | **1,07** |
| Correct Score | 1-2% | 3.700 | 1.481 | 48 | 0,0151 | 0,0130 | 1,16 | 0,90 |
| Correct Score | 2-5% | 12.060 | 1.846 | 396 | 0,0354 | 0,0328 | 1,08 | 0,99 |
| Correct Score | 5-10% | 11.881 | 1.847 | 865 | 0,0705 | 0,0728 | 0,97 | 0,92 |
| Correct Score | >10% | 3.681 | 1.700 | 518 | 0,1351 | 0,1407 | 0,96 | 0,90 |
| Half Time Score | 1-2% | 272 | 226 | 1 | 0,0154 | 0,0037 | 4,17 | **1,36** |
| Half Time Score | 2-5% | 5.811 | 1.596 | 139 | 0,0332 | 0,0239 | **1,39** | **1,20** |
| Half Time Score | 5-10% | 3.878 | 1.602 | 298 | 0,0717 | 0,0768 | 0,93 | 0,84 |
| Half Time Score | >10% | 6.331 | 1.643 | 1.199 | 0,1844 | 0,1894 | 0,97 | 0,94 |

> **IL FAVOURITE-LONGSHOT BIAS ESISTE E VA NELLA NOSTRA DIREZIONE** (coda sovraprezzata:
> k_equo 1,53 sul CS 0,5-1 %, 1,39 sull'HT 2-5 %, entrambi con estremo basso > 1), **ma se
> lo mangia interamente lo SPREAD**: la differenza fra (a) e (b) e' solo il prezzo a cui
> si opera. Conseguenza operativa per V3: **non si puo' raccogliere il bias attraversando
> lo spread** (FOK sul best availableToLay, che e' quello che Omega fa oggi). O l'edge
> viene dal MODELLO che batte il mercato su celle specifiche, o serve un ingresso PASSIVO
> a un prezzo dentro lo spread. Da portare all'utente come reperto, non da nascondere.

Il motore usa comunque `k_soglia = max(2, k_prudente)` e non scende MAI sotto 2 dove il
bias non e' dimostrato (`misura_k.tabella_k`).

## PASSO 2 — BANCO DEI MODELLI: chi vince, sui nostri dati, fuori campione

Comando: `python -m Betfair.omega.tools.estrai_transizioni --leghe 60` poi
`python -m Betfair.omega.tools.banco_modelli --max-iter 600`
Dati: `omega_minute_transitions`, **1,07 M righe** da ~1,4 M partite (globale 22.193
righe; 60 leghe campionate). Stati con n >= 200: **548**. Fit = massima verosimiglianza
multinomiale sui conteggi; prova su dati mai visti, con **due split indipendenti**
(meta' degli stati / 30 leghe contro 30). Metriche: log-loss e Brier multiclasse, piu'
la log-loss **della sola coda** (celle che il modello mette sotto il 2 %: e' li' che
Omega opera). Risultati in `data/banco_modelli_2026-09-16.json`.

| modello | logloss OOS (stati) | Brier | **coda <2 %** | HT | FT | logloss OOS (leghe) | coda (leghe) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **5 Gamma-Poisson (bayesiano)** | **2,13041** | **0,78179** | **4,95478** | 1,26203 | **2,42266** | **1,93221** | **4,91797** |
| 3 Dixon-Robinson (1998) | 2,13731 | 0,78186 | 5,17026 | **1,26171** | 2,43198 | 1,93301 | 5,01694 |
| 4 bivariato Karlis-Ntzoufras (2003) | 2,13737 | 0,78188 | 5,17044 | 1,26166 | 2,43208 | 1,93307 | 5,01757 |
| 0 **v2 di produzione** (DC + mistura log-normale cv 0,30) | 2,14697 | 0,78381 | 5,11069 | 1,26589 | 2,44349 | 1,93904 | 5,01360 |
| 2 Dixon-Coles (1997) | 2,14830 | 0,78393 | 5,22601 | 1,26582 | 2,44529 | 1,93921 | 5,02951 |
| 1 Poisson indipendente | 2,14840 | 0,78395 | 5,22668 | 1,26577 | 2,44544 | 1,93929 | 5,03001 |

**Le cinque cose che i numeri dicono** (stesso ordine nei due split: non e' rumore):

1. **Vince il Gamma-Poisson bayesiano**, e vince proprio DOVE CONTA: sulla coda
   (`4,955` contro `5,111` del v2 di produzione e `5,226` del Poisson puro). E' il
   modello che aggiorna il tasso di ciascuna squadra dai gol gia' visti
   (posteriore coniugato Gamma) e la cui predittiva e' una **binomiale negativa**.
2. **Il Poisson bivariato NON e' giustificato dai dati**: `lambda3` si ferma a **0,000**
   in entrambi gli split, cioe' il modello degenera nel Dixon-Robinson. Risposta chiara
   al candidato 4: non serve.
3. **Dixon-Coles quasi non guadagna qui** (2,14830 contro 2,14840 del Poisson) e il rho
   stimato e' **-0,015/-0,031**, molto piu' piccolo del **-0,13** cablato in produzione
   (`omega_model.py:41`). Onesta': su dati AGGREGATI sui lambda la correzione tau non si
   puo' isolare (l'eterogeneita' fra partite domina). Il rho va tenuto, non gonfiato.
4. **`forma_gamma` 6,7-13,3 => cv = 1/sqrt(a) = 0,27-0,39**: il `model_lambda_cv` 0,30 di
   produzione era azzeccato. Ma la mistura log-normale del v2 *spalma* quell'incertezza
   e basta; il Gamma-Poisson la spalma **e impara dai gol visti**. Da qui il vantaggio.
5. **`beta_squilibrio` viene NEGATIVO** (chi e' avanti segna di piu'), il contrario del
   «chi e' sotto attacca». Non e' un paradosso: su dati aggregati chi e' avanti e'
   di solito la squadra piu' forte, e la forza non si puo' separare dal comportamento.
   Conferma della struttura: nel Gamma-Poisson `beta` scende a **-0,013** (contro -0,098
   del Dixon-Robinson) **perche' il posteriore ha gia' assorbito la forza**.

`profilo_c1` = **0,41**: l'intensita' dei gol al 90' vale `exp(0,41) = 1,5` volte quella
d'inizio partita — il profilo crescente di Dixon & Robinson, misurato sui nostri dati.

Calibrazione fuori campione (split leghe), decile piu' basso (dove sta tutta l'attivita'
di Omega): Gamma-Poisson **p prevista 0,335 % contro 0,331 % osservata** su 241 M di
peso; v2 0,337 % contro 0,338 %. Entrambi calibrati; serve la risoluzione fine sulla
coda (passo 2c).

## PASSO 3 — `omega_v3.py`

Modulo nuovo, **tutto puro** (nessun I/O, nessun Betfair, nessun database), che contiene:
`Parametri` · `esposizione` (profilo temporale) · `intensita_residue` · `griglia_residua`
/ `griglia_finale` (i 5 modelli) · `fondi_col_mercato` (pool logaritmico in logit) ·
`probabilita_selezioni` (scoreline **e aggregati**) · `p_implicita` · `candidato` (il
cancello del margine k) · `finestra_ingresso` · `profitto_bloccabile` ·
`p_punteggio_invariato` · `traiettoria_bloccabile` · `proposta_uscita`.
Test: `Betfair/omega/test_omega_v3_2026_09_16.py`, **41 verdi**, ognuno falsificato.

**Due difetti trovati dalla falsificazione** (il banco ha corretto il codice, non il test):
- `p_implicita(1.00)` valeva 1,0 e faceva passare qualunque cosa il cancello -> guardia
  `L <= 1` (`omega_v3.py:p_implicita`).
- la traiettoria del bloccabile, guardata nel solo ramo «non succede niente», diceva
  **sempre** «aspetta» e non si sarebbe mai chiuso niente. Ora il valore dell'attesa e'
  pesato con `p_punteggio_invariato` e nell'altro ramo si torna a valere l'EV di tenere
  di oggi (`valore_attesa = P(regge)*bloccabile + (1-P)*EV_tenere`).

## Log

- creato il checkpoint.
- scritto `Betfair/omega/tools/misura_k.py` (sola lettura del DB, bootstrap a grappolo).
- eseguita la misura: k<=1 al prezzo di lay in tutti i secchi; bias reale solo devigato.
