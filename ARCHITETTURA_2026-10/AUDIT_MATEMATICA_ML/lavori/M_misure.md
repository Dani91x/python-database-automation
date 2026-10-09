# M - Misura quote vs Poisson vs ML servito (1X2, Over 2.5, BTTS) - audit in sola lettura, 09/10/2026

R = radice repo. Sonde: `R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/sonde/m_estrai.py` (unico accesso al DB), `m_misure.py`, `m_extra.py`
(entrambe leggono solo `m_dati.json`). Output integrali: `m_misure_output.txt`, `m_extra_output.txt`.
Rilancio: `R/.venv/Scripts/python.exe -I m_misure.py` (circa 45 s) dopo `m_estrai.py`.

## 0. Sintesi (tutti i numeri sono nel campione B, partite con ML; IC95 bootstrap 1000 sulle differenze appaiate)

1. 1X2: le quote battono tutto, di molto. Logloss/RPS: Q 0.9592/0.2008; ML 1.0081/0.2135; Poisson calibrato 1.0119/0.2165; Poisson grezzo 1.0128/0.2168;
   climatologia 1.0463/0.2301. Tutte le differenze vs Q sono significative (IC esclude 0). Nessuna miscela con peso > 0 migliora le quote
   (peso ottimo di ML o Poisson = 0.0 sia in-sample sia in CV a 5 fold: d_CV = 0.0000).
2. ML vs Poisson calibrato (1X2): ML leggermente meglio (RPS -0.0029 [-0.0075,+0.0018], logloss -0.0038 [-0.0195,+0.0127]) ma NON significativo.
3. Over 2.5: Q 0.6714; Poisson calibrato 0.6846; ML 0.6905; climatologia 0.6886. Il ML NON batte il tasso base (0.6905 vs 0.6886, differenza non significativa
   ma di segno sbagliato) e ha ECE 0.0485 contro 0.0149 delle quote. Il Poisson calibrato e' meglio del grezzo in modo significativo (logloss -0.0103 [-0.0177,-0.0035]).
4. BTTS: Q 0.6790; Poisson calibrato 0.6799 (indistinguibile dalle quote); ML 0.6955 (peggio della climatologia 0.6883). Miscela 50/50 Q+Poisson calibrato 0.6769
   (-0.0021 [-0.0067,+0.0024], non significativa; CV5 +0.0004 [-0.0037,+0.0043], cioe' nessun guadagno fuori campione).
5. L'ML non aggiunge informazione misurabile rispetto alle quote su nessuno dei tre mercati; il Poisson neppure (unico indizio debole: BTTS, peso ottimo 0.4-0.5
   in-sample, guadagno 0.002 di logloss non confermato in CV).
6. Leakage temporale: il 10.5% dei Poisson (160/1519) e il 13.2% degli ML (200/1510) hanno `generated_at` DOPO il calcio d'inizio (vedi par. 3).
   Le conclusioni 1-5 non cambiano restringendosi alle previsioni pre-kickoff (campioni C e D).

## 1. Metodo

- Campione: `fixture_predictions` con `result_status_short='FT'`, `fixture_date` in [2026-09-21, 2026-10-08), `db_json_analisi` e `raw_json_odds` non nulli
  (stesso filtro di `a_poisson_vs_quote_db.py:9-12`). Differenza dalla sonda A: A usava `.limit(800)` senza `order` (sottoinsieme non riproducibile); io ho usato
  8 finestre di data (2 giorni ciascuna, 1 SELECT per finestra, `order fixture_id`, limit 1000; nessuna finestra ha raggiunto il limite: 41, 21, 349, 213, 88, 131, 530, 146 righe)
  = 1519 partite, tutta la popolazione disponibile. Nessuna RPC, nessuna scrittura. Totale query: 8 (budget rispettato).
- Colonne lette: `fixture_id, fixture_date (= calcio d'inizio), created_at, updated_at, result_home/away_goals, raw_json_odds,
  db_json_analisi->markets / ->markets_calibrated / ->>generated_at / ->>calibrated_at / ->>model,
  model_predictions_json->targets->target_1x2 | target_over_2_5 | target_btts, ->>generated_at, ->>run_id`.
  Le previsioni ML sono quelle SERVITE (`targets`, gia' con post-calibrazione `ml_post_calibration`; scritte da `Ai Engine/ai_engine/predict_fixture.py:1051-1089`,
  `update` di `fixture_predictions.model_predictions_json`, con `generated_at` a :1055). `targets` e' in scala 0-1 (verificato sui dati: nessuna anomalia di scala scartata).
- Quote: bookmaker scelto come in `generate_dynamic_cal.py:191-215` (Betfair se presente, altrimenti il primo): nel campione 1519/1519 sono "Betfair" (Sportsbook di API-Football,
  non l'exchange). 1X2 = "Match Winner"; Over 2.5 = "Goals Over/Under" valori "Over 2.5"/"Under 2.5"; BTTS = "Both Teams Score" Yes/No.
  De-vig: moltiplicativo (1/o normalizzato); power (esponente k con somma (1/o)^k = 1); Shin (z per bisezione, formula standard di Shin 1992/1993, Strumbelj 2014).
  Le partite senza quota O/U o BTTS sul bookmaker scelto sono escluse dal rispettivo mercato (507 su 1519 senza O/U, 499 senza BTTS) e contate a parte: n effettivo sotto.
- Metriche: logloss = -ln p(esito); Brier = somma sulle 3 classi per 1X2, (p_evento - o)^2 per i binari (quindi i Brier binari NON sono confrontabili con quello 1X2);
  RPS = sum_{k<K}(F_k - O_k)^2 / (K-1) con K=3 (ordine H,D,A; stessa formula di `a_poisson_vs_quote_db.py:14-15`); ECE a 10 bin equidistanti
  (1X2: media su 3 classi one-vs-rest; binari: classe "True"); curva di affidabilita' = `[bin]p_media>freq_osservata(n)` (1X2: tre classi impilate).
- Climatologia: tassi base del campione stesso (in-sample, nessun leave-one-out come da brief). Per costruzione ECE = 0 e quindi l'ECE della climatologia NON e' un metrodo di merito.
- Miscele lineari: 50/50 quote(molt.)+ML, 50/50 quote+Poisson calibrato (e grezzo), 1/3 Q+ML+Pcal. Inoltre peso ottimo w su griglia 0..1 passo 0.1 (in-sample) e CV a 5 fold
  (w scelto su 4 fold, valutato sul quinto).
- Bootstrap: 1000 ricampionamenti iid delle partite (seed 20261009) sulle differenze appaiate per-partita vs "Q molt."; `*` = IC95 percentile esclude lo zero.
  Per l'ECE il bootstrap ricalcola l'ECE su ogni ricampione.
- n effettivo: A = tutte le partite con quote+Poisson (1X2 n=1518; O25 n=1012; BTTS n=1020). B = campione comune con ML (n=1509; 1006; 1014): 9 partite (1X2) / 6 (O25) / 6 (BTTS)
  senza `targets` ML sono state escluse da B e non riempite con default (9 partite su 1519 non hanno proprio il ML). C = B con ML, Poisson e calibrato tutti generati prima del
  kickoff (1309; 845; 850). D = C con generazione >= 3 h prima del kickoff (1069; 684; 685).

## 2. Tabelle (campione B, confronto equo: stesse partite per tutti i modelli)

### 1X2 (n=1509; tassi base H/D/A 0.480/0.219/0.302)

| modello | logloss | Brier | RPS | ECE10 | d_logloss vs Q [IC95] | d_RPS vs Q [IC95] |
|---|---|---|---|---|---|---|
| Quote molt. | 0.9592 | 0.5693 | 0.2008 | 0.0321 | - | - |
| Quote power | 0.9555 | 0.5673 | 0.2001 | 0.0215 | -0.0037 [-0.0064,-0.0009]* | -0.0007 [-0.0014,-0.0000]* |
| Quote Shin | 0.9564 | 0.5678 | 0.2002 | 0.0237 | -0.0028 [-0.0046,-0.0010]* | -0.0006 [-0.0010,-0.0001]* |
| Poisson grezzo | 1.0128 | 0.6059 | 0.2168 | 0.0386 | +0.0536 [+0.0396,+0.0675]* | +0.0160 [+0.0113,+0.0207]* |
| Poisson calibrato | 1.0119 | 0.6056 | 0.2165 | 0.0285 | +0.0527 [+0.0382,+0.0672]* | +0.0156 [+0.0110,+0.0204]* |
| ML servito | 1.0081 | 0.6008 | 0.2135 | 0.0320 | +0.0489 [+0.0334,+0.0638]* | +0.0127 [+0.0082,+0.0174]* |
| Climatologia | 1.0463 | 0.6311 | 0.2301 | (0, banale) | +0.0871 [+0.0693,+0.1060]* | +0.0293 [+0.0232,+0.0354]* |
| 50/50 Q+ML | 0.9728 | 0.5783 | 0.2043 | 0.0331 | +0.0136 [+0.0064,+0.0209]* | +0.0034 [+0.0012,+0.0058]* |
| 50/50 Q+Poisson cal. | 0.9753 | 0.5799 | 0.2051 | 0.0319 | +0.0161 [+0.0090,+0.0233]* | +0.0043 [+0.0021,+0.0067]* |
| 50/50 Q+Poisson grezzo | 0.9754 | 0.5800 | 0.2053 | 0.0377 | +0.0162 [+0.0090,+0.0231]* | +0.0045 [+0.0022,+0.0067]* |
| 1/3 Q+ML+Pcal | 0.9785 | 0.5819 | 0.2058 | 0.0338 | +0.0193 [+0.0111,+0.0274]* | +0.0050 [+0.0025,+0.0076]* |

Differenze ECE vs Q: tutte non significative tranne la climatologia (banale). Appaiate: ML-Pcal logloss -0.0038 [-0.0195,+0.0127], RPS -0.0029 [-0.0075,+0.0018]; Pcal-Pgrezzo RPS -0.0003 [-0.0011,+0.0005]
(la calibrazione Poisson non cambia l'1X2 in modo misurabile). Peso ottimo di miscela: w*=0.0 per ML e per Poisson, CV5 = Q esatta.
Affidabilita' 1X2 (bin: pred>osservato(n)): le quote con de-vig moltiplicativo sottostimano i favoriti ([0.7] 0.75>0.87 n=77; [0.8] 0.85>0.94 n=36) e sovrastimano i
longshot ([0.0] 0.07>0.02 n=123): e' il noto favourite-longshot bias, che power e Shin riducono (da cui il leggero vantaggio significativo di power/Shin: per 1X2 il de-vig moltiplicativo
della sonda A e' il piu' debole dei tre). ML: sovrastima i bassi ([0.0] 0.06>0.09, [0.1] 0.16>0.20), ok al centro, ma ha 52 casi nel bin 0.7 con 0.74>0.69 (n piccoli).

### Over 2.5 (n=1006; tasso Over 0.548)

| modello | logloss | Brier(binario) | ECE10 | d_logloss vs Q [IC95] | d_Brier vs Q [IC95] |
|---|---|---|---|---|---|
| Quote molt. | 0.6714 | 0.2391 | 0.0149 | - | - |
| Quote power | 0.6733 | 0.2396 | 0.0228 | +0.0019 [-0.0005,+0.0045] | +0.0006 [-0.0004,+0.0015] |
| Quote Shin | 0.6724 | 0.2394 | 0.0174 | +0.0010 [-0.0005,+0.0025] | +0.0003 [-0.0003,+0.0009] |
| Poisson grezzo | 0.6948 | 0.2497 | 0.0644 | +0.0234 [+0.0098,+0.0376]* | +0.0106 [+0.0044,+0.0170]* |
| Poisson calibrato | 0.6846 | 0.2456 | 0.0291 | +0.0132 [+0.0030,+0.0240]* | +0.0066 [+0.0017,+0.0116]* |
| ML servito | 0.6905 | 0.2474 | 0.0485 | +0.0191 [+0.0058,+0.0336]* | +0.0084 [+0.0031,+0.0141]* |
| Climatologia | 0.6886 | 0.2477 | (0, banale) | +0.0172 [+0.0028,+0.0326]* | +0.0087 [+0.0021,+0.0159]* |
| 50/50 Q+ML | 0.6752 | 0.2411 | 0.0223 | +0.0038 [-0.0019,+0.0099] | +0.0021 [-0.0006,+0.0049] |
| 50/50 Q+Poisson cal. | 0.6745 | 0.2407 | 0.0488 | +0.0031 [-0.0021,+0.0085] | +0.0017 [-0.0007,+0.0041] |
| 50/50 Q+Poisson grezzo | 0.6767 | 0.2417 | 0.0350 | +0.0053 [-0.0012,+0.0120] | +0.0026 [-0.0005,+0.0058] |
| 1/3 Q+ML+Pcal | 0.6755 | 0.2413 | 0.0208 | +0.0040 [-0.0018,+0.0102] | +0.0022 [-0.0004,+0.0051] |

Appaiate: ML-Pcal +0.0060 [-0.0087,+0.0206]; Pcal-Pgrezzo -0.0103 [-0.0177,-0.0035]* (la calibrazione Poisson aiuta davvero su O25). Peso ottimo di miscela in-sample 0.0 (B), 0.1-0.2 (C, D);
CV5 d_vs_Q: ML +0.0006 [-0.0002,+0.0013], Pcal +0.0009 [-0.0000,+0.0019] (nessun guadagno; in C Pcal +0.0019 [+0.0004,+0.0033], cioe' leggermente peggio).
Affidabilita' (pred>osservato): il Poisson grezzo sottostima Over quando dice poco ([0.2] 0.26>0.49 n=53; [0.3] 0.36>0.45) e sovrastima quando dice molto ([0.8] 0.84>0.70);
il ML e' piatto e sottostima Over nel centro ([0.4] 0.45>0.53 n=350) ed e' sovra-confidente in alto ([0.7] 0.74>0.62 n=61). Il ML emette valori quasi costanti in alcuni casi
(0.01 in 3 partite: valore di clip, osservato 0.33 su 3 casi).

### BTTS (n=1014; tasso Yes 0.549)

| modello | logloss | Brier(binario) | ECE10 | d_logloss vs Q [IC95] | d_Brier vs Q [IC95] |
|---|---|---|---|---|---|
| Quote molt. | 0.6790 | 0.2428 | 0.0184 | - | - |
| Quote power | 0.6801 | 0.2432 | 0.0176 | +0.0011 [-0.0006,+0.0028] | +0.0004 [-0.0003,+0.0011] |
| Quote Shin | 0.6796 | 0.2430 | 0.0188 | +0.0006 [-0.0004,+0.0017] | +0.0002 [-0.0003,+0.0007] |
| Poisson grezzo | 0.6835 | 0.2450 | 0.0305 | +0.0045 [-0.0079,+0.0165] | +0.0022 [-0.0035,+0.0078] |
| Poisson calibrato | 0.6799 | 0.2434 | 0.0217 | +0.0008 [-0.0080,+0.0100] | +0.0006 [-0.0037,+0.0051] |
| ML servito | 0.6955 | 0.2473 | 0.0341 | +0.0165 [-0.0013,+0.0358] | +0.0045 [-0.0014,+0.0105] |
| Climatologia | 0.6883 | 0.2476 | (0, banale) | +0.0092 [-0.0019,+0.0190] | +0.0048 [-0.0005,+0.0095] |
| 50/50 Q+ML | 0.6795 | 0.2431 | 0.0257 | +0.0004 [-0.0056,+0.0064] | +0.0003 [-0.0025,+0.0031] |
| 50/50 Q+Poisson cal. | 0.6769 | 0.2419 | 0.0228 | -0.0021 [-0.0067,+0.0024] | -0.0009 [-0.0030,+0.0014] |
| 50/50 Q+Poisson grezzo | 0.6770 | 0.2419 | 0.0225 | -0.0021 [-0.0080,+0.0036] | -0.0009 [-0.0038,+0.0019] |
| 1/3 Q+ML+Pcal | 0.6774 | 0.2422 | 0.0322 | -0.0016 [-0.0076,+0.0043] | -0.0006 [-0.0035,+0.0022] |

Appaiate: ML-Pcal +0.0157 [-0.0014,+0.0341]; ML-Pgrezzo +0.0120 [-0.0080,+0.0337]. Peso ottimo Q+Pcal in-sample 0.5 (B), 0.4 (C), 0.6 (D); CV5: +0.0004 [-0.0037,+0.0043] (B), -0.0007 [-0.0079,+0.0061] (D):
nessun guadagno certo. Peso ottimo Q+ML in-sample 0.2, CV5 +0.0003 [-0.0025,+0.0031]. In C il ML e' peggiore delle quote in modo significativo (+0.0220 [+0.0037,+0.0446]).
Il ML ha casi estremi insensati: 5 partite con P(BTTS)<0.05 (bin [0.0]: pred 0.01, osservato 0.60 su n=5; in C 0.75 su n=4); Poisson e quote non scendono sotto 0.30.

### Campione A (nessun ML richiesto; n=1518 / 1012 / 1020) - solo Q, Poisson e miscele

1X2: Q 0.9585/RPS 0.2009; Poisson grezzo 1.0134/0.2172; calibrato 1.0123/0.2169; climatologia 1.0454/0.2302. O25: Q 0.6720; Pgrezzo 0.6968; Pcal 0.6859; clim 0.6886.
BTTS: Q 0.6793; Pgrezzo 0.6849; Pcal 0.6806; 50/50 Q+Pcal 0.6774 (-0.0019 [-0.0063,+0.0024]); CV5 -0.0010 [-0.0049,+0.0026]. Coerente con B.

Confronto con la sonda A (n=800 non ordinato): A: Q RPS 0.1969, Pgrezzo 0.2125, Pcal 0.2122 (gap Pcal-Q = +0.0153). Qui n=1518: 0.2009, 0.2172, 0.2169 (gap +0.0160): stesso ordine e quasi stesso gap;
i livelli assoluti differiscono perche' il campione e' diverso (A = sottoinsieme arbitrario di 800 su 1519). Non ho riprodotto il sottoinsieme esatto di A (non ordinato): NON VERIFICATO l'accordo riga per riga.

## 3. Leakage temporale (kickoff = `fixture_date`)

Ore tra `generated_at` e calcio d'inizio (positivo = prima del kickoff), su 1519 partite (ML 1510):

| campo | n | min | p25 | mediana | p75 | max | DOPO il kickoff | entro 1 h prima |
|---|---|---|---|---|---|---|---|---|
| Poisson `db_json_analisi.generated_at` | 1519 | -9.11 | 3.81 | 6.08 | 10.01 | 15.88 | 160 (10.5%) | 43 |
| Poisson calibrato `calibrated_at` | 1519 | -9.13 | 3.81 | 6.08 | 10.01 | 15.88 | 160 (10.5%) | 43 |
| ML `model_predictions_json.generated_at` | 1510 | -10.84 | 2.27 | 5.18 | 8.79 | 15.32 | 200 (13.2%) | 54 |
| riga `created_at` | 1519 | -9.14 | 3.83 | 6.08 | 10.02 | 1202.94 | 158 (10.4%) | 43 |
| riga `updated_at` | 1519 | -10.84 | 2.25 | 5.18 | 8.80 | 15.32 | 205 (13.5%) | 54 |

- 200 ML e 160 Poisson generati dopo il calcio d'inizio: esempi (fixture, kickoff, ML generato): 1549637 22/09 00:30 UTC -> 22/09 08:09; 1549791 21/09 01:15 -> 10:53; 1583770 22/09 01:00 -> 08:12.
  Sono partite a orari UTC antelucani (leghe asiatiche/oceaniche/americane): il batch giornaliero delle ~08 UTC le tratta come "di oggi" ma sono gia' iniziate o finite.
  Altri 54 ML e 43 Poisson sono generati nell'ultima ora prima del via. Quindi il servizio produce previsioni "pre-partita" che per il 10-13% delle partite pre-partita non sono.
- Se quelle previsioni usassero il risultato della partita stessa NON VERIFICATO (non ho letto la selezione dello storico nella generazione: B/feature_pipeline dichiarava H2H `< match_date`);
  il solo fatto temporale e' verificato. Firma statistica: differenza-nelle-differenze del logloss vs Q tra partite generate dopo e prima il kickoff (m_extra_output.txt):
  1X2 Pcal -0.0363 [-0.0782,+0.0048], ML -0.0240 [-0.0664,+0.0179]; O25 Pcal +0.0055 [-0.0201,+0.0317], ML +0.0204 [-0.0261,+0.0875];
  BTTS Pcal -0.0026 [-0.0283,+0.0228], ML -0.0341 [-0.0672,-0.0065] (unico significativo). CONFONDENTE non separabile: le partite post-kickoff hanno un mix di leghe/orari diverso
  (le quote possono essere meno nitide li'). Quindi: indizio non conclusivo, non prova di leakage.
- Robustezza: ripetendo tutte le tabelle sui campioni C (solo pre-kickoff) e D (>= 3 h prima) l'ordine dei modelli e le conclusioni non cambiano (output integrale). Esempio 1X2 in D (n=1069):
  Q RPS 0.1972, ML 0.2090, Pcal 0.2147, Pgrezzo 0.2154, 50/50 Q+ML 0.2005; il ML e' qui 0.0118 peggio delle quote (IC [+0.0071,+0.0168]); in D il vantaggio dell'ML sul Poisson cresce (logloss ML 0.9962 vs Pcal 1.0119).
  Per il ML in 1X2 per anticipo: 0-3 h 1.0489 (n=240), 3-8 h 0.9975 (n=629), >= 8 h 0.9944 (n=440), post-kickoff 1.0230 (n=200): le previsioni tardive sono le peggiori (non migliori), quindi non c'e' un
  segnale di leakage che migliori il ML.
- Timestamp delle QUOTE: `raw_json_odds` contiene la chiave top-level `update` (visto nelle chiavi: bookmakers, fixture, league, update) che NON ho estratto (budget di 8 query esaurito):
  quando le quote sono state registrate rispetto al kickoff e alla previsione e' NON VERIFICATO. Se fossero quote di chiusura, il benchmark delle quote sarebbe piu' forte di quanto disponibile all'ora della previsione (confronto sbilanciato a favore delle quote).
  Il tipo di quota ("Betfair" Sportsbook) e' 1519/1519.

## 4. Interpretazione

- L'ML aggiunge informazione rispetto alle quote? Non misurabile: nessuna miscela lo migliora (1X2 w*=0, O25 CV +0.0006, BTTS CV +0.0003; tutti IC includono lo zero o sono peggiori). Il ML e'
  peggio delle quote ovunque (1X2 e O25 in modo significativo; BTTS significativo solo in C) e sui mercati binari non batte il tasso base (O25 0.6905 vs 0.6886; BTTS 0.6955 vs 0.6883).
  Coerente con B_ml.md R1/R2 (mediana modelli binari non batte il tasso base della lega). Correlazione ML-Q sulla classe casa 0.736 (1X2), 0.70 (O25), 0.54 (BTTS): se l'ML usa le quote come feature
  (B_ml: odds_* tra le feature piu' frequenti) la parte utile e' in realta' quota; NON VERIFICATO sui modelli cloud serviti.
- Il Poisson aggiunge informazione? 1X2 no (w*=0). O25 no (peggiora anche in CV). BTTS: Poisson calibrato ~ quote (0.6799 vs 0.6790) e miscela 50/50 -0.0021 in-sample ma non confermata in CV: al massimo informazione marginale, da riconfermare su piu' dati.
- Calibrazione: la `markets_calibrated` migliora il Poisson in modo significativo solo su O25 (logloss -0.0103*, ECE 0.0644 -> 0.0291); su 1X2 e BTTS l'effetto non e' distinguibile da zero.
- Quale componente come prior? (a) Prior "migliore" in assoluto: le quote de-viggate (per 1X2 meglio power o Shin del moltiplicativo: -0.0037/-0.0028 logloss, significativo; per O25/BTTS il moltiplicativo basta e power/Shin non aiutano).
  (b) Se serve un prior indipendente dalle quote (per cercare edge): 1X2 ML ~ Poisson calibrato (differenza non significativa, ML marginalmente meglio, 0.0127 vs 0.0156 di RPS dal gap con le quote);
  O25 e BTTS: Poisson calibrato (ML peggiore, con uscite degeneri a 0.01). In nessun caso un prior "modello" pesa piu' di ~0-20% in miscela con le quote.
  Questa e' una misura, non una decisione: non si tocca nessuna strategia (Omega/Mike/Safe leggono comunque il Poisson `db_json_analisi`, non l'ensemble: vedi B_ml.md par. 1).

## 5. Limiti e NON VERIFICATO

- 17 giorni (21/09-07/10) e una sola stagione di calendario: stagionalita'/leghe non controllate; bootstrap iid ignora la correlazione per lega e per giornata (IC un po' stretti). Nessuna correzione per confronti multipli (molte righe e colonne: gli `*` marginali vanno letti con prudenza).
- O25/BTTS: 507/499 partite senza quota O/U-BTTS sul bookmaker scelto sono escluse: probabile selezione verso leghe maggiori (n=1012/1020).
- Climatologia in-sample (tassi del campione stesso): leggermente ottimistica; ECE banale a 0. ECE a 10 bin con n ~ 1000 ha rumore di fondo ~0.01-0.02 (i d_ECE sono quasi tutti non significativi).
- Il Brier binario e' per la sola classe positiva; non e' confrontabile con il Brier 1X2.
- Il ML valutato e' quello SERVITO (dopo post-calibrazione `ml_post_calibration`), non il modello grezzo; non ho scaricato/rieseguito modelli cloud. Qualita' "per lega" non misurata.
- `fixture_date` assunto = calcio d'inizio UTC (coerente con gli esempi: 17:30 e 00:30); NON VERIFICATO sul codice di scrittura. Timestamp delle quote: NON VERIFICATO (par. 3).
- I pesi di miscela sono lineari su probabilita'; non provate miscele logit/geometriche ne' stacking con piu' feature.
- Non ho letto il codice che costruisce lo storico delle feature del Poisson/ML alla generazione per capire se una partita gia' conclusa puo' contaminare la sua stessa previsione (cio' deciderebbe se il 10-13% post-kickoff e' un vero leak).

## 6. Metodo di ricerca (comandi)

- `git grep -n "model_predictions_json" -- '*.py'` -> scrittura in `Ai Engine/ai_engine/predict_fixture.py:1051-1089`, lettura target in `Betfair/stream/backtest/tools/misura_punto8/estrai_db.py:324-330`;
  `git grep -n "Goals Over/Under\|Both Teams Score"` -> nomi dei mercati quote (`value_betting.py:338-370`, `predict_fixture.py:268-271`); chiavi `markets_calibrated` in `Prediction/today_predictions_backfill.py:940-952`; `generate_dynamic_cal.py:30-60` per le chiavi 1x2/over_2_5/btts.
- 8 SELECT (m_estrai.py), nessun errore 57014, nessuna finestra a limite; file `m_dati.json` (2.9 MB, solo valori estratti, nessun segreto).
