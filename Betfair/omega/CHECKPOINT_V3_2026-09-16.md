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
| 2 | banco modelli: costruzione candidati 1-6 + log-loss/Brier OOS + calibrazione | IN CORSO |
| 3 | `omega_v3.py` (funzioni pure) + test falsificati | DA FARE |
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

## Log

- creato il checkpoint.
- scritto `Betfair/omega/tools/misura_k.py` (sola lettura del DB, bootstrap a grappolo).
- eseguita la misura: k<=1 al prezzo di lay in tutti i secchi; bias reale solo devigato.
