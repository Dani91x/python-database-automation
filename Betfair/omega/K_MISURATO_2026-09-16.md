# k MISURATO — favourite-longshot bias sul nostro book (Omega V3, Fase K)

> 16/09/2026. Misura riproducibile: `python -m Betfair.omega.tools.misura_k`
> Dati versionati: `Betfair/omega/data/k_misurato_2026-09-16.json`
> Codice: `Betfair/omega/tools/misura_k.py`

## 1. La domanda e la definizione

Con un lay di stake `s` a quota `L` e commissione `c` si incassa `s(1-c)` se il risultato
NON esce e si perde `s(L-1)` se esce. Il pareggio e'

```
p_implicita = (1 - c) / (L - c)
```

che e' **esattamente** la formula del motore (`omega_model.py:551` nel ramo v2). Il margine
che il progetto chiede (`PROGETTO_OMEGA_V3_2026-09-16.md` §3.3) e' `P_nostra <= p_implicita / k`,
con **EV per gamba = s(1-c)(1 - 1/k)**: indipendente dalla quota, dipendente solo da k.

`k` non si decide: si misura come `p_implicita / p_reale` per secchi di `p_implicita`.
E' la misura diretta del **favourite-longshot bias** (Thaler & Ziemba 1988, *Journal of
Economic Perspectives*; Cain, Law & Peel 2000, *Scottish Journal of Political Economy*, che
lo documenta proprio sui mercati a risultato esatto del calcio).

## 2. I dati

| | |
|---|---|
| quote | `betfair_market_odds`, mercati `Correct Score` e `Half Time Score`, back+lay, **58.234 righe** su **2.018 fixture** |
| quando | snapshot **PRE-MATCH** (`betfair_full_odds.py` gira sugli eventi del giorno); ultimo `run_date` 11/09/2026 |
| esiti | `matches` (`goals_home/away` per il CS, `halftime_home/away` per l'HT), solo `status_short` in FT/AET/PEN |
| utili | **1.859** partite per il CS, **1.645** per l'HT |
| scartate | 8.937 righe senza lato lay, 930 senza esito settlato, 0 nomi non interpretabili |

Gli aggregati (`Any Other Home Win`, `Any Other Away Win`, `Any Other Draw`, `Any Unquoted`)
**sono valutati**, non saltati: «si e' verificato» = il risultato vero non e' fra le scoreline
quotate di quel mercato **e** la direzione corrisponde.

**Intervalli: bootstrap a grappolo sulle PARTITE**, non su Wilson per selezione. In un
mercato a risultato esatto esce **una sola** scoreline: le ~20 righe della stessa partita
sono legate, e un intervallo binomiale su 10.685 selezioni sarebbe falsamente stretto.
2.000 ricampionamenti delle partite con reimmissione (`bootstrap_grappolo`, seed fisso).
Il Wilson per selezione resta nel JSON solo come riferimento.

## 3. Risultato (a): al prezzo di LAY realmente disponibile

`p_implicita` dal **best availableToLay**, cioe' il prezzo a cui Omega opera oggi (FOK taker).

| mercato | secchio | n sel. | partite | uscite | p_impl | p_reale | **k** | k prudente | operabile |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Correct Score | 0-0,2% | 258 | 229 | 2 | 0,0016 | 0,0078 | 0,21 | 0,08 | no |
| Correct Score | 0,2-0,5% | 1.148 | 656 | 6 | 0,0036 | 0,0052 | 0,68 | 0,36 | no |
| Correct Score | 0,5-1% | 2.385 | 1.184 | 22 | 0,0071 | 0,0092 | 0,77 | 0,54 | no |
| Correct Score | 1-2% | 5.079 | 1.773 | 77 | 0,0149 | 0,0152 | 0,98 | 0,80 | no |
| Correct Score | 2-5% | 10.685 | 1.841 | 458 | 0,0340 | 0,0429 | 0,79 | 0,73 | no |
| Correct Score | 5-10% | 10.427 | 1.846 | 873 | 0,0705 | 0,0837 | 0,84 | 0,80 | no |
| Correct Score | >10% | 2.464 | 1.562 | 394 | 0,1403 | 0,1599 | 0,88 | 0,81 | no |
| Half Time Score | 0-0,2% | 5 | 5 | 0 | 0,0019 | 0,0000 | — | — | no |
| Half Time Score | 0,2-0,5% | 281 | 240 | 1 | 0,0038 | 0,0036 | 1,08 | 0,34 | no |
| Half Time Score | 0,5-1% | 1.039 | 886 | 9 | 0,0071 | 0,0087 | 0,82 | 0,49 | no |
| Half Time Score | 1-2% | 1.699 | 1.099 | 22 | 0,0149 | 0,0129 | 1,15 | 0,81 | no |
| Half Time Score | 2-5% | 4.222 | 1.597 | 166 | 0,0331 | 0,0393 | 0,84 | 0,73 | no |
| Half Time Score | 5-10% | 3.625 | 1.595 | 363 | 0,0751 | 0,1001 | 0,75 | 0,69 | no |
| Half Time Score | >10% | 5.050 | 1.644 | 1.062 | 0,1793 | 0,2103 | 0,85 | 0,82 | no |

> **Nessun secchio ha `k prudente > 1`.** Al prezzo che il book offre davvero, bancare una
> scoreline pre-match e' in media a EV **negativo**: `k = 0,8` significa EV per gamba
> `0,95·(1 − 1/0,8) = −0,24 €` su 1 € di stake. Questo e' il verdetto che §3.3 chiedeva di
> dichiarare se fosse arrivato, ed e' arrivato.

## 4. Risultato (b): con probabilita' DEVIGATA — la forma del bias

La tabella (a) mescola due cose: **il bias** (il mercato sbaglia la coda?) e **lo spread**
(la somma delle `1/L` di un mercato sta sotto 1, quindi ogni `p_implicita` di lay e' piu'
bassa del vero solo per come e' fatto il book). Qui la probabilita' di mercato e' devigata —
mid di back/lay per selezione, normalizzato a 1 sul mercato (mercati con meno di 6 selezioni
prezzate o somma dei pesi <= 0,5 esclusi: normalizzare mezzo book inventa probabilita').

| mercato | secchio | n sel. | partite | uscite | p_equa | p_reale | **k_equo** | k_equo prudente |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Correct Score | 0-0,2% | 9 | 7 | 0 | 0,0017 | 0,0000 | — | — |
| Correct Score | 0,2-0,5% | 351 | 259 | 0 | 0,0038 | 0,0000 | — | — |
| Correct Score | 0,5-1% | 3.855 | 1.391 | 21 | 0,0084 | 0,0054 | **1,53** | **1,07** |
| Correct Score | 1-2% | 3.700 | 1.481 | 48 | 0,0151 | 0,0130 | 1,16 | 0,90 |
| Correct Score | 2-5% | 12.060 | 1.846 | 396 | 0,0354 | 0,0328 | 1,08 | 0,99 |
| Correct Score | 5-10% | 11.881 | 1.847 | 865 | 0,0705 | 0,0728 | 0,97 | 0,92 |
| Correct Score | >10% | 3.681 | 1.700 | 518 | 0,1351 | 0,1407 | 0,96 | 0,90 |
| Half Time Score | 0,5-1% | 98 | 82 | 0 | 0,0077 | 0,0000 | — | — |
| Half Time Score | 1-2% | 272 | 226 | 1 | 0,0154 | 0,0037 | 4,17 | **1,36** |
| Half Time Score | 2-5% | 5.811 | 1.596 | 139 | 0,0332 | 0,0239 | **1,39** | **1,20** |
| Half Time Score | 5-10% | 3.878 | 1.602 | 298 | 0,0717 | 0,0768 | 0,93 | 0,84 |
| Half Time Score | >10% | 6.331 | 1.643 | 1.199 | 0,1844 | 0,1894 | 0,97 | 0,94 |

> **Il bias c'e' ed e' dalla nostra parte**: nella coda la probabilita' equa di mercato
> sopravvaluta la frequenza reale di 1,5x (CS 0,5-1 %) e 1,4x (HT 2-5 %), con l'estremo
> basso del bootstrap sopra 1 in entrambi i casi. Sulle fasce grosse (>5 %) k_equo ~ 0,95:
> il mercato e' calibrato, come ci si aspetta.
> **Ma il bias vale 1,1-1,4x e lo spread costa di piu'.** Fra (a) e (b) non cambia il
> modello: cambia solo il PREZZO a cui si opera.

## 5. Che cosa impone questo risultato a V3

1. **Non si raccoglie il bias attraversando lo spread.** L'ingresso FOK sul best
   `availableToLay` (quello che Omega fa oggi) e' la ragione per cui (a) < 1. Le due strade
   sono: (i) un edge di **modello** su celle specifiche, dimostrato fuori campione; (ii) un
   ingresso **passivo** dentro lo spread. Sono cumulabili, non alternative.
2. **Il cancello k resta, con `k_soglia = max(2, k_prudente)`.** Dove il bias non e'
   dimostrato — cioe' ovunque, al prezzo di lay — il motore usa **k = 2** e non meno
   (`misura_k.tabella_k`, `motivo_soglia = "bias_non_dimostrato"`). Un margine di 2 sulla
   probabilita' e' cio' che deve coprire sia lo spread sia l'errore del modello.
3. **Limite dichiarato**: queste sono quote **pre-match**. Omega V3 entra al 25'-40' e al
   55'-85' su un book **live** condizionato al punteggio. Il bias live puo' essere diverso
   (in-play il book e' piu' sottile e lo spread piu' largo: verosimilmente **peggiore**).
   Questa misura vale come prior, e va rifatta sui book live registrati quando ce ne saranno
   abbastanza (oggi 42 registrazioni, 39 con esito: troppo poche per un evento all'1 %).
4. Le tabelle di frequenza (`omega_minute_transitions`, `omega_ht_ft_transitions`) sono
   **ferme all'11/09**: il veto empirico gira su dati vecchi di 5 giorni. Dichiarato, non
   aggirato.
